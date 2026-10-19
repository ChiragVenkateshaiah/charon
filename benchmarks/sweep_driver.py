"""
benchmarks/sweep_driver.py — Charon Phase 1, Milestone 2 (Week 2).

Closed-loop concurrency sweep against serving/naive_server.py. Implements the
"Concurrency sweep (Milestone 2)" section of benchmarks/methodology.md; each
numbered decision there is marked below as [M1]..[M8]. If this file and the
methodology disagree, the methodology wins and this file is the bug.

  [M1] hand-rolled stdlib closed loop: exactly N client requests in flight
  [M2] warmup = first max(20, N) requests *sent*, by sequence number, no drain
  [M3] client end-to-end latency primary; server TTFT/TPOT reported separately
  [M4] throughput = (n - 1) / (last measured t_end - first measured t_end)
  [M5] no request retries; a failed run is re-run once at session end, else flagged
  [M6] n = 100 per run, nearest-rank; spread gate on p50; p99 spread + pooled p99
  [M7] client timeout 1800 s
  [M8] server unchanged; GPU samples aligned on client wall-clock t_start/t_end

Reuses baseline_runner.py's GPU sampler, percentile, spread, /healthz and
prompt loading, so Week 1 and Week 2 numbers share the same arithmetic.

Stdlib only. Needs a server already running (serving/README.md). Per ADR-0001
the output is a *result* only when the run happened on the GCP L4; a run
against a local CPU server is a correctness check — do not commit its output.

The output file is rewritten after every run, so a preempted spot instance
loses at most the run in progress.

Usage:
    # correctness check against a local CPU server (not a result)
    python benchmarks/sweep_driver.py --levels 1,2,4 --runs 1 --requests 5 --warmup-base 2

    # the Milestone 2 sweep, on the L4 (defaults match the methodology)
    python benchmarks/sweep_driver.py
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import socket
import statistics
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import baseline_runner as br  # noqa: E402

SCHEMA = "charon-sweep-v1"
DEFAULT_LEVELS = (1, 2, 4, 8, 16, 32, 64)
WARMUP_BASE = 20
SERVER_METRICS = ("ttft_s", "tpot_s", "e2e_s", "decode_tokens_per_s")
PERCENTILES = br.PERCENTILES


def warmup_for(concurrency: int, base: int = WARMUP_BASE) -> int:
    """[M2] Requests discarded per run at level N: max(base, N)."""
    return max(base, concurrency)


# --------------------------------------------------------------------------- #
# One request
# --------------------------------------------------------------------------- #
def _post(url: str, prompt: str, output_tokens: int, timeout_s: float) -> dict:
    body = json.dumps(
        {"prompt": prompt, "max_tokens": output_tokens, "min_tokens": output_tokens}
    ).encode()
    req = urllib.request.Request(  # noqa: S310
        url.rstrip("/") + "/generate", data=body,
        headers={"content-type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:  # noqa: S310
        return json.loads(resp.read())


def _classify(exc: BaseException) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        try:
            detail = exc.read().decode(errors="replace")[:200]
        finally:
            exc.close()
        return f"http {exc.code}: {detail}"
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return f"timeout: {exc}"
    if isinstance(exc, urllib.error.URLError):
        if isinstance(exc.reason, (TimeoutError, socket.timeout)):
            return f"timeout: {exc.reason}"
        return f"url error: {exc.reason}"
    return f"{type(exc).__name__}: {exc}"


# --------------------------------------------------------------------------- #
# One run at one level
# --------------------------------------------------------------------------- #
def run_level(url: str, prompts: list[str], *, concurrency: int, warmup: int,
              requests: int, output_tokens: int, timeout_s: float,
              progress: str | None = None) -> dict:
    """[M1] Closed loop: N workers, each sends its next request as soon as its
    previous one ends. Sequence numbers and t_start are taken together under one
    lock, so seq order is dispatch order and [M2]'s warmup set is the first
    `warmup` requests sent. A failed request is recorded and never retried [M5].
    """
    total = warmup + requests
    lock = threading.Lock()
    state = {"next": 0, "in_flight": 0, "max_in_flight": 0, "done": 0}
    records: list[dict | None] = [None] * total

    def worker() -> None:
        while True:
            with lock:
                seq = state["next"]
                if seq >= total:
                    return
                state["next"] += 1
                state["in_flight"] += 1
                state["max_in_flight"] = max(state["max_in_flight"], state["in_flight"])
                in_flight_at_send = state["in_flight"]
                t_start = time.time()
                p0 = time.perf_counter()
            rec = {
                "seq": seq,
                "is_warmup": seq < warmup,
                "prompt_index": seq % len(prompts),
                "in_flight_at_send": in_flight_at_send,
                "ok": False,
                "error": None,
                "t_start": t_start,
                "t_end": None,
                "client_e2e_s": None,
                "server": None,
            }
            try:
                rec["server"] = _post(url, prompts[seq % len(prompts)], output_tokens, timeout_s)
                rec["ok"] = True
            except Exception as exc:  # noqa: BLE001 — a dead worker would lower N
                rec["error"] = _classify(exc)
            finally:
                rec["client_e2e_s"] = time.perf_counter() - p0
                rec["t_end"] = time.time()
                with lock:
                    state["in_flight"] -= 1
                    state["done"] += 1
                    done = state["done"]
                records[seq] = rec
            if progress and (done % 20 == 0 or done == total):
                print(f"  {progress}: {done}/{total}", file=sys.stderr)

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(concurrency)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return {
        "concurrency": concurrency,
        "warmup": warmup,
        "requests": requests,
        "output_tokens": output_tokens,
        "timeout_s": timeout_s,
        "max_in_flight": state["max_in_flight"],
        "records": [r for r in records if r is not None],
    }


def validate_level(result: dict, *, warmup: int, requests: int) -> list[str]:
    """Completeness and integrity checks. [] means the run is clean."""
    problems: list[str] = []
    recs = result["records"]
    total = warmup + requests
    seqs = [r["seq"] for r in recs]
    if len(seqs) != len(set(seqs)):
        problems.append("duplicate seq in records")
    if set(seqs) != set(range(total)):
        problems.append(f"incomplete: expected {total} distinct seqs, got {len(set(seqs))}")
    if any(r["is_warmup"] != (r["seq"] < warmup) for r in recs):
        problems.append(f"warmup flags do not match the first {warmup} seqs")
    failed = [r for r in recs if not r["ok"]]
    if failed:
        problems.append(f"{len(failed)} failed request(s)")
    concurrency = result.get("concurrency")
    if concurrency is not None:
        if result["max_in_flight"] > concurrency:
            problems.append(f"max_in_flight {result['max_in_flight']} exceeds concurrency {concurrency}")
        elif result["max_in_flight"] < min(concurrency, total):
            problems.append(f"concurrency {concurrency} never reached (max {result['max_in_flight']})")
        # [M2] the start-up wave is seqs 0..N-1; none of it may be measured.
        # (in_flight_at_send is kept as audit data only: a closed loop briefly
        # has N - 1 in flight between one completion and that worker's next send.)
        if warmup < concurrency:
            problems.append(f"warmup {warmup} < concurrency {concurrency}: measured requests "
                            "include the start-up wave [M2]")
    expected_tokens = result.get("output_tokens")
    if expected_tokens is not None:
        seen = {r["server"]["output_tokens"] for r in recs if r["ok"]}
        if seen - {expected_tokens}:
            problems.append(f"output_tokens not uniformly {expected_tokens}: saw {sorted(seen)}")
    return problems


def _pcts(values: list[float]) -> dict:
    return {f"p{p}": br.percentile(values, p) for p in PERCENTILES}


def summarize_level(result: dict) -> dict:
    """Per-run summary over successful measured requests."""
    measured = [r for r in result["records"] if not r["is_warmup"]]
    ok = [r for r in measured if r["ok"]]
    out: dict = {
        "n": len(ok),
        "n_failed": len(measured) - len(ok),
        "n_warmup_failed": sum(1 for r in result["records"] if r["is_warmup"] and not r["ok"]),
        "client_e2e_s": _pcts([r["client_e2e_s"] for r in ok]),  # [M3] primary
    }
    for metric in SERVER_METRICS:  # [M3] server-side, reported separately
        out[metric] = _pcts([r["server"][metric] for r in ok])

    # [M4] window from first to last measured completion
    by_end = sorted(ok, key=lambda r: r["t_end"])
    window = by_end[-1]["t_end"] - by_end[0]["t_end"] if len(by_end) >= 2 else 0.0
    if window > 0:
        out["requests_per_s"] = (len(by_end) - 1) / window
        out["output_tokens_per_s"] = sum(r["server"]["output_tokens"] for r in by_end[1:]) / window
    else:
        out["requests_per_s"] = None
        out["output_tokens_per_s"] = None
    out["throughput_window_s"] = window
    return out


# --------------------------------------------------------------------------- #
# Across runs at one level
# --------------------------------------------------------------------------- #
LATENCY_KEYS = ("client_e2e_s",) + SERVER_METRICS
THROUGHPUT_KEYS = ("requests_per_s", "output_tokens_per_s")


def aggregate_level(attempts: list[dict], spread_threshold: float) -> dict:
    """[M6] Median and spread of per-run p50/p99, pooled percentiles over all
    measured requests, and the p50 spread gate. Uses the last attempt of each
    run (the re-run when there is one)."""
    final: dict[int, dict] = {}
    for a in attempts:
        final[a["run"]] = a  # attempts are appended in order, so the last wins
    runs = [final[k] for k in sorted(final)]
    summaries = [a["summary"] for a in runs]
    measured_ok = [r for a in runs for r in a["result"]["records"] if not r["is_warmup"] and r["ok"]]

    out: dict = {"runs_used": [{"run": a["run"], "attempt": a["attempt"]} for a in runs]}
    for key in LATENCY_KEYS:
        out[key] = {}
        for p in PERCENTILES:
            vals = [s[key][f"p{p}"] for s in summaries]
            clean = [v for v in vals if v is not None]
            out[key][f"p{p}"] = {
                "median": statistics.median(clean) if clean else None,
                "spread": br.spread(vals),
                "per_run": vals,
            }
        series = [r["client_e2e_s"] if key == "client_e2e_s" else r["server"][key]
                  for r in measured_ok]
        out[key]["pooled"] = {**_pcts(series), "n": len(series)}
    for key in THROUGHPUT_KEYS:
        vals = [s[key] for s in summaries]
        clean = [v for v in vals if v is not None]
        out[key] = {"median": statistics.median(clean) if clean else None,
                    "spread": br.spread(vals), "per_run": vals}

    warnings: list[str] = []
    for key in LATENCY_KEYS:
        s = out[key]["p50"]["spread"]
        if s is not None and s > spread_threshold:
            warnings.append(f"{key} p50 spread {s:.1%} exceeds {spread_threshold:.0%} "
                            "(rule 4: something is uncontrolled)")
    flagged = [a["run"] for a in runs if a["problems"]]
    if flagged:
        warnings.append(f"runs {flagged} still incomplete after re-run policy; "
                        "level not used for the knee claim [M5]")
    out["flagged_runs"] = flagged
    out["usable_for_knee"] = not flagged
    out["warnings"] = warnings
    return out


# --------------------------------------------------------------------------- #
# The sweep
# --------------------------------------------------------------------------- #
def run_sweep(url: str, prompts: list[str], *, levels: tuple[int, ...], runs: int,
              requests: int, warmup_base: int, output_tokens: int, timeout_s: float,
              spread_threshold: float = 0.10, rerun_failed: bool = True,
              deadline: float | None = None, on_progress=None) -> list[dict]:
    """Levels ascending, runs consecutive within a level. Every attempt is kept.
    After all levels, each run with problems is re-run once [M5], unless the
    time box (`deadline`, time.monotonic()) has passed."""
    out = [{"concurrency": n, "warmup": warmup_for(n, warmup_base), "attempts": [],
            "reruns_skipped": []} for n in levels]

    def attempt(level: dict, run: int, number: int) -> None:
        n, w = level["concurrency"], level["warmup"]
        started = datetime.now(timezone.utc).isoformat()
        result = run_level(url, prompts, concurrency=n, warmup=w, requests=requests,
                           output_tokens=output_tokens, timeout_s=timeout_s,
                           progress=f"c={n} run {run} attempt {number}")
        level["attempts"].append({
            "run": run, "attempt": number, "started_at": started,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "problems": validate_level(result, warmup=w, requests=requests),
            "summary": summarize_level(result),
            "result": result,
        })
        level["across_runs"] = aggregate_level(level["attempts"], spread_threshold)
        if on_progress:
            on_progress(out)

    for level in out:
        for run in range(1, runs + 1):
            attempt(level, run, 1)

    if rerun_failed:
        for level in out:
            failed = [a["run"] for a in level["attempts"] if a["attempt"] == 1 and a["problems"]]
            for run in failed:
                if deadline is not None and time.monotonic() >= deadline:
                    level["reruns_skipped"].append({"run": run, "reason": "time box reached"})
                    continue
                attempt(level, run, 2)
            if level["reruns_skipped"] and on_progress:
                on_progress(out)
    return out


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #
def _environment(health: dict) -> dict:
    return {
        "healthz": health,
        "client": {
            "python": sys.version,
            "platform": platform.platform(),
            "hostname": socket.gethostname(),
            "driver": "sweep_driver.py stdlib",
        },
    }


def build_report(args: argparse.Namespace, health: dict, levels: list[dict],
                 sampler: br.GpuSampler, started: str, complete: bool) -> dict:
    for level in levels:
        for a in level["attempts"]:
            if "gpu" not in a:
                measured = [r for r in a["result"]["records"] if not r["is_warmup"]]
                a["gpu"] = br.gpu_summary(sampler, measured)
    warnings = [f"c={lv['concurrency']}: {w}" for lv in levels
                for w in lv.get("across_runs", {}).get("warnings", [])]
    warnings += [f"c={lv['concurrency']} run {s['run']}: re-run skipped ({s['reason']})"
                 for lv in levels for s in lv["reruns_skipped"]]
    if sampler.status != "ok":
        warnings.append(f"GPU sampling {sampler.status} — utilization not measured.")
    if not complete:
        warnings.append("sweep did not finish; this file holds the runs completed so far.")
    return {
        "schema": SCHEMA,
        "complete": complete,
        "started_at": started,
        "written_at": datetime.now(timezone.utc).isoformat(),
        "methodology": "benchmarks/methodology.md, 'Concurrency sweep (Milestone 2)'",
        "config": {
            "url": args.url,
            "prompts_file": str(args.prompts.relative_to(br.REPO_ROOT))
            if args.prompts.is_relative_to(br.REPO_ROOT) else str(args.prompts),
            "levels": list(args.levels),
            "runs": args.runs,
            "requests_per_run": args.requests,
            "warmup_base": args.warmup_base,
            "warmup_rule": "max(warmup_base, concurrency), first sent by seq",
            "output_tokens": args.output_tokens,
            "request_timeout_s": args.request_timeout,
            "spread_threshold": args.spread_threshold,
            "rerun_failed": not args.no_rerun,
            "time_box_min": args.time_box_min,
            "gpu_sample_interval_ms": args.gpu_sample_interval_ms,
            "order": "levels ascending; runs consecutive within a level; re-runs after all levels",
        },
        "environment": _environment(health),
        "levels": levels,
        "warnings": warnings,
        "raw": {"gpu_samples": sampler.samples, "gpu_sampler_status": sampler.status},
    }


def write_report(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(report, indent=2))
    os.replace(tmp, path)


def print_summary(report: dict) -> None:
    health = report["environment"]["healthz"]
    print()
    print(f"Charon sweep — {health.get('model_id')} on {health.get('device')}")
    header = (f"{'c':>4}{'req/s':>9}{'tok/s':>9}{'e2e p50':>10}{'e2e p99':>10}"
              f"{'ttft p50':>10}{'ttft p99':>10}{'spread e2e p50':>16}  usable")
    print(header)
    print("-" * len(header))

    def f(v, w=10, d=3):
        return f"{'n/a':>{w}}" if v is None else f"{v:>{w}.{d}f}"

    for lv in report["levels"]:
        a = lv.get("across_runs")
        if not a:
            continue
        sp = a["client_e2e_s"]["p50"]["spread"]
        print(f"{lv['concurrency']:>4}"
              f"{f(a['requests_per_s']['median'], 9)}{f(a['output_tokens_per_s']['median'], 9, 1)}"
              f"{f(a['client_e2e_s']['p50']['median'])}{f(a['client_e2e_s']['p99']['median'])}"
              f"{f(a['ttft_s']['p50']['median'])}{f(a['ttft_s']['p99']['median'])}"
              f"{'n/a' if sp is None else f'{sp:.1%}':>16}  {'yes' if a['usable_for_knee'] else 'NO'}")
    print()
    for w in report["warnings"]:
        print(f"WARNING: {w}", file=sys.stderr)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Closed-loop concurrency sweep for naive_server.")
    p.add_argument("--url", default="http://localhost:8000", help="naive_server base URL")
    p.add_argument("--prompts", type=Path, default=br.DEFAULT_PROMPTS)
    p.add_argument("--levels", default=",".join(map(str, DEFAULT_LEVELS)),
                   help="comma-separated concurrency levels (ADR-0003)")
    p.add_argument("--runs", type=int, default=3, help="runs per level (rule 4)")
    p.add_argument("--requests", type=int, default=100, help="measured requests per run [M6]")
    p.add_argument("--warmup-base", type=int, default=WARMUP_BASE,
                   help="warmup per run is max(this, N) [M2]")
    p.add_argument("--output-tokens", type=int, default=128)
    p.add_argument("--request-timeout", type=float, default=1800.0, help="seconds [M7]")
    p.add_argument("--spread-threshold", type=float, default=0.10)
    p.add_argument("--no-rerun", action="store_true", help="disable the [M5] re-run")
    p.add_argument("--time-box-min", type=float, default=None,
                   help="minutes from start after which [M5] re-runs are skipped")
    p.add_argument("--gpu-sample-interval-ms", type=int, default=200)
    p.add_argument("--out", type=Path, default=None,
                   help="output path (default: benchmarks/results/sweep-<ts>.json)")
    args = p.parse_args(argv)
    args.levels = tuple(int(x) for x in args.levels.split(","))
    if any(n < 1 for n in args.levels):
        p.error("--levels must be positive integers")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    args.prompts = args.prompts.resolve()
    prompts = br.load_prompts(args.prompts)

    try:
        health = br.get_healthz(args.url)
    except urllib.error.HTTPError as exc:
        print(f"error: {args.url}/healthz returned {exc.code} — server up but not "
              "ready (model still loading?). Retry shortly.", file=sys.stderr)
        return 2
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        print(f"error: no server at {args.url} ({exc}). Start it first — see "
              "serving/README.md.", file=sys.stderr)
        return 2
    if health.get("status") != "ok":
        print(f"error: /healthz not ok: {health}", file=sys.stderr)
        return 2

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = args.out or (br.RESULTS_DIR / f"sweep-{ts}.json")
    started = datetime.now(timezone.utc).isoformat()
    deadline = (time.monotonic() + args.time_box_min * 60) if args.time_box_min else None
    total = sum(args.runs * (warmup_for(n, args.warmup_base) + args.requests) for n in args.levels)
    print(f"server up: {health['model_id']} on {health['device']}. levels {list(args.levels)}, "
          f"{args.runs} run(s) each, {total} requests before re-runs. output: {out_path}",
          file=sys.stderr)

    sampler = br.GpuSampler(args.gpu_sample_interval_ms)
    sampler.start()
    time.sleep(0.3)  # let the first nvidia-smi row land before request 1
    levels: list[dict] = []

    def checkpoint(current: list[dict]) -> None:
        levels[:] = current
        write_report(out_path, build_report(args, health, current, sampler, started, False))

    complete = False
    try:
        levels = run_sweep(
            args.url, prompts, levels=args.levels, runs=args.runs, requests=args.requests,
            warmup_base=args.warmup_base, output_tokens=args.output_tokens,
            timeout_s=args.request_timeout, spread_threshold=args.spread_threshold,
            rerun_failed=not args.no_rerun, deadline=deadline, on_progress=checkpoint,
        )
        complete = True
    except KeyboardInterrupt:
        print("interrupted — writing the runs completed so far.", file=sys.stderr)
    finally:
        sampler.stop()
        sampler.join(timeout=5)
        report = build_report(args, health, levels, sampler, started, complete)
        write_report(out_path, report)

    print_summary(report)
    print(f"\noutput: {out_path}", file=sys.stderr)
    if health.get("device", "").startswith("cpu"):
        print("note: CPU server — this is a correctness check, not a result. "
              "Do not commit the output file (ADR-0001).", file=sys.stderr)
    return 0 if complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
