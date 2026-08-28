"""
benchmarks/baseline_runner.py — Charon Phase 1, Week 1.

Drives serving/naive_server.py at concurrency 1 and produces the baseline row of
the benchmark table: TTFT, TPOT, end-to-end latency, decode tokens/sec, GPU
utilization, peak VRAM — aggregated as percentiles across repeated runs.

This is NOT the Week 2 load generator. It has no concurrency model: it sends one
request at a time, on purpose, because the Week 1 lesson is what a single-stream
server does to a GPU. Week 2 replaces the aggregation and the sweep with a proper
tool (benchmarks/methodology.md, 'Not yet decided').

Follows the seven methodology rules (benchmarks/methodology.md):
  1. fixed output length      — forced server-side via min_tokens == max_tokens
  2. discard warmup           — --warmup N requests dropped before aggregation
  3. percentiles not averages — p50/p95/p99 (nearest-rank) on every metric
  4. >=3 runs, report spread  — --runs N; p50 spread across runs is flagged
  5. record the environment   — pulled from /healthz into the output file
  6. one variable per run     — the runner changes nothing between runs; you do
  7. commit raw output        — every per-request record and GPU sample is kept

Stdlib only — no new dependencies (CLAUDE.md, 'no tooling additions'). Needs a
server already running (serving/README.md); it does not launch one.

Per ADR-0001 the file this writes is a *result* only when the run happened on the
GCP L4. A run against a local CPU server is a correctness check of this script and
nothing more — do not commit its output.

Usage:
    # correctness check against a local CPU server (fast, not a result)
    uv run python -m uvicorn serving.naive_server:app --port 8000   # in another shell
    python benchmarks/baseline_runner.py --warmup 2 --requests 5 --runs 1

    # the real Week 1 measurement, on the L4
    python benchmarks/baseline_runner.py            # defaults match the methodology
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import statistics
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PROMPTS = REPO_ROOT / "benchmarks" / "prompts" / "baseline.json"
RESULTS_DIR = REPO_ROOT / "benchmarks" / "results"

SCHEMA = "charon-baseline-v1"
# Metrics read straight off the server's /generate response and aggregated here.
METRICS = ("ttft_s", "tpot_s", "e2e_s", "decode_tokens_per_s")
PERCENTILES = (50, 95, 99)


# --------------------------------------------------------------------------- #
# HTTP (stdlib only)
# --------------------------------------------------------------------------- #
def get_healthz(base_url: str, timeout: float = 30.0) -> dict:
    url = base_url.rstrip("/") + "/healthz"
    with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310
        return json.loads(resp.read())


def post_generate(
    base_url: str, prompt: str, output_tokens: int, timeout: float
) -> tuple[dict, float]:
    """Return (server response, client round-trip seconds)."""
    url = base_url.rstrip("/") + "/generate"
    body = json.dumps(
        {"prompt": prompt, "max_tokens": output_tokens, "min_tokens": output_tokens}
    ).encode()
    req = urllib.request.Request(  # noqa: S310
        url, data=body, headers={"content-type": "application/json"}, method="POST"
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            payload = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise RuntimeError(f"server returned {exc.code}: {detail}") from exc
    return payload, time.time() - t0


# --------------------------------------------------------------------------- #
# GPU sampling — nvidia-smi in a background thread, aligned to request windows
# --------------------------------------------------------------------------- #
_SMI_FIELDS = (
    "utilization.gpu",
    "utilization.memory",
    "memory.used",
    "memory.total",
    "power.draw",
    "clocks.current.sm",
    "temperature.gpu",
)
_SMI_KEYS = (
    "util_gpu_pct",
    "util_mem_pct",
    "mem_used_mb",
    "mem_total_mb",
    "power_w",
    "clock_sm_mhz",
    "temp_c",
)


def _num(token: str) -> float | None:
    try:
        return float(token)
    except ValueError:
        return None  # nvidia-smi prints "[N/A]" for unsupported fields


class GpuSampler(threading.Thread):
    """Streams `nvidia-smi ... -lms <interval>` and timestamps each row locally.

    Absent hardware is not an error: on the local CPU box `status` just reports
    why there are no samples, and GPU aggregates come out null.
    """

    def __init__(self, interval_ms: int) -> None:
        super().__init__(daemon=True)
        self.interval_ms = interval_ms
        self.samples: list[dict] = []
        self.status = "pending"
        self._stop_evt = threading.Event()
        self._proc: subprocess.Popen | None = None

    def run(self) -> None:
        exe = shutil.which("nvidia-smi")
        if exe is None:
            self.status = "unavailable: nvidia-smi not on PATH"
            return
        cmd = [
            exe,
            f"--query-gpu={','.join(_SMI_FIELDS)}",
            "--format=csv,noheader,nounits",
            "-lms",
            str(self.interval_ms),
        ]
        try:
            self._proc = subprocess.Popen(  # noqa: S603
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
        except OSError as exc:
            self.status = f"unavailable: {exc}"
            return
        self.status = "ok"
        assert self._proc.stdout is not None
        for line in self._proc.stdout:
            if self._stop_evt.is_set():
                break
            parts = [p.strip() for p in line.split(",")]
            if len(parts) != len(_SMI_KEYS):
                continue
            sample = {"t": time.time()}
            sample.update((k, _num(v)) for k, v in zip(_SMI_KEYS, parts))
            self.samples.append(sample)

    def stop(self) -> None:
        self._stop_evt.set()
        if self._proc is not None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()


# --------------------------------------------------------------------------- #
# Aggregation
# --------------------------------------------------------------------------- #
def percentile(values: list[float], p: float) -> float | None:
    """Nearest-rank percentile. Crude by design at small N — see the schema note."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(0, math.ceil(p / 100 * len(ordered)) - 1)
    return ordered[rank]


def summarize_run(records: list[dict]) -> dict:
    out: dict = {"n": len(records)}
    for metric in METRICS:
        series = [r["server"][metric] for r in records]
        out[metric] = {f"p{p}": percentile(series, p) for p in PERCENTILES}
    prompt_tokens = [r["server"]["prompt_tokens"] for r in records]
    output_tokens = {r["server"]["output_tokens"] for r in records}
    peak_vram = [
        r["server"]["peak_vram_bytes"]
        for r in records
        if r["server"].get("peak_vram_bytes") is not None
    ]
    overhead = [r["client_rtt_s"] - r["server"]["e2e_s"] for r in records]
    out["prompt_tokens"] = {"min": min(prompt_tokens), "max": max(prompt_tokens)}
    out["output_tokens_seen"] = sorted(output_tokens)
    out["peak_vram_bytes"] = max(peak_vram) if peak_vram else None
    out["client_overhead_s_p50"] = percentile(overhead, 50)
    return out


def spread(values: list[float]) -> float | None:
    vals = [v for v in values if v is not None]
    if len(vals) < 2:
        return None
    med = statistics.median(vals)
    if med == 0:
        return None
    return (max(vals) - min(vals)) / abs(med)


def across_runs(per_run: list[dict]) -> dict:
    out: dict = {}
    for metric in METRICS:
        out[metric] = {}
        for p in PERCENTILES:
            key = f"p{p}"
            vals = [run[metric][key] for run in per_run]
            clean = [v for v in vals if v is not None]
            out[metric][key] = {
                "median": statistics.median(clean) if clean else None,
                "spread": spread(vals),
                "per_run": vals,
            }
    return out


def gpu_summary(sampler: GpuSampler, measured: list[dict]) -> dict:
    windows = sorted((r["t_start"], r["t_end"]) for r in measured)

    def in_flight(t: float) -> bool:
        return any(start <= t <= end for start, end in windows)

    all_samples = sampler.samples
    live = [s for s in all_samples if in_flight(s["t"])]
    result: dict = {
        "status": sampler.status,
        "sample_interval_ms": sampler.interval_ms,
        "samples_total": len(all_samples),
        "samples_in_flight": len(live),
    }
    if not live:
        result["util_gpu_pct"] = None
        result["mem_used_mb_max"] = None
        return result
    util = [s["util_gpu_pct"] for s in live if s["util_gpu_pct"] is not None]
    mem = [s["mem_used_mb"] for s in all_samples if s["mem_used_mb"] is not None]
    result["util_gpu_pct"] = {f"p{p}": percentile(util, p) for p in PERCENTILES}
    result["util_gpu_pct"]["max"] = max(util) if util else None
    result["mem_used_mb_max"] = max(mem) if mem else None
    return result


# --------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------- #
def load_prompts(path: Path) -> list[str]:
    data = json.loads(path.read_text())
    prompts = data["prompts"] if isinstance(data, dict) else data
    if not prompts or not all(isinstance(p, str) and p for p in prompts):
        raise ValueError(f"{path}: expected a non-empty list of prompt strings")
    return prompts


def run_once(
    args: argparse.Namespace, prompts: list[str], run_index: int
) -> list[dict]:
    total = args.warmup + args.requests
    records: list[dict] = []
    for i in range(total):
        prompt = prompts[i % len(prompts)]
        t_start = time.time()
        payload, rtt = post_generate(args.url, prompt, args.output_tokens, args.request_timeout)
        t_end = time.time()
        records.append(
            {
                "run": run_index,
                "index": i,
                "is_warmup": i < args.warmup,
                "prompt_index": i % len(prompts),
                "t_start": t_start,
                "t_end": t_end,
                "client_rtt_s": rtt,
                "server": payload,
            }
        )
        done = i + 1
        if done % 10 == 0 or done == total:
            tag = "warmup" if i < args.warmup else "measured"
            print(
                f"  run {run_index}: {done}/{total} ({tag})  "
                f"last e2e={payload['e2e_s']:.3f}s tok/s={payload['decode_tokens_per_s']:.1f}",
                file=sys.stderr,
            )
    return records


def build_report(args: argparse.Namespace, health: dict, records: list[dict],
                 sampler: GpuSampler, started: str) -> dict:
    measured = [r for r in records if not r["is_warmup"]]
    per_run = [
        summarize_run([r for r in measured if r["run"] == run])
        for run in range(1, args.runs + 1)
    ]
    gpu = gpu_summary(sampler, measured)

    warnings: list[str] = []
    if args.runs < 3:
        warnings.append(f"runs={args.runs}: methodology rule 4 wants >=3.")
    for metric in METRICS:
        s = spread([run[metric]["p50"] for run in per_run])
        if s is not None and s > args.spread_threshold:
            warnings.append(
                f"{metric} p50 spread {s:.1%} across runs exceeds "
                f"{args.spread_threshold:.0%} (rule 4: something is uncontrolled)."
            )
    seen = sorted({t for run in per_run for t in run["output_tokens_seen"]})
    if seen != [args.output_tokens]:
        warnings.append(
            f"output_tokens not uniformly {args.output_tokens}: saw {seen} "
            "(rule 1 violated — runs not comparable)."
        )
    pt_lo = min(run["prompt_tokens"]["min"] for run in per_run)
    pt_hi = max(run["prompt_tokens"]["max"] for run in per_run)
    if pt_hi - pt_lo > 0.25 * pt_lo:
        warnings.append(
            f"prompt_tokens range {pt_lo}-{pt_hi} is wide; aggregates mix input sizes."
        )
    if gpu["status"] != "ok":
        warnings.append(f"GPU sampling {gpu['status']} — utilization not measured.")
    elif not gpu["samples_in_flight"]:
        warnings.append("nvidia-smi produced no samples during any request window.")

    return {
        "schema": SCHEMA,
        "concurrency": 1,
        "started_at": started,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "config": {
            "url": args.url,
            "prompts_file": str(args.prompts.relative_to(REPO_ROOT))
            if args.prompts.is_relative_to(REPO_ROOT)
            else str(args.prompts),
            "output_tokens": args.output_tokens,
            "warmup": args.warmup,
            "requests_per_run": args.requests,
            "runs": args.runs,
            "gpu_sample_interval_ms": args.gpu_sample_interval_ms,
            "spread_threshold": args.spread_threshold,
        },
        "environment": {"healthz": health, "runner": "baseline_runner.py stdlib"},
        "summary": {
            "per_run": per_run,
            "across_runs": across_runs(per_run),
            "gpu": gpu,
            "peak_vram_bytes": max(
                (r["peak_vram_bytes"] for r in per_run if r["peak_vram_bytes"]),
                default=None,
            ),
        },
        "warnings": warnings,
        "raw": {"requests": records, "gpu_samples": sampler.samples},
    }


def print_summary(report: dict) -> None:
    health = report["environment"]["healthz"]
    cfg = report["config"]
    across = report["summary"]["across_runs"]
    gpu = report["summary"]["gpu"]
    rev = str(health.get("model_revision", "?"))[:9]

    print()
    print("Charon baseline runner — concurrency 1")
    print(
        f"server: {health.get('model_id')} @ {rev}  "
        f"device={health.get('device')} dtype={health.get('dtype')}  "
        f"torch={health.get('torch')} transformers={health.get('transformers')}"
    )
    print(
        f"runs: {cfg['runs']} x ({cfg['warmup']} warmup + {cfg['requests_per_run']} measured)  "
        f"output_tokens={cfg['output_tokens']} (forced)"
    )
    print()
    header = f"{'metric':<22}{'p50':>12}{'p95':>12}{'p99':>12}   spread(p50)"
    print(header)
    print("-" * len(header))
    for metric in METRICS:
        row = across[metric]
        vals = []
        for p in PERCENTILES:
            v = row[f"p{p}"]["median"]
            vals.append("      n/a" if v is None else f"{v:12.4f}")
        sp = row["p50"]["spread"]
        sp_txt = "   n/a" if sp is None else f"   {sp:.1%}"
        print(f"{metric:<22}{''.join(vals)}{sp_txt}")
    print()
    if isinstance(gpu.get("util_gpu_pct"), dict):
        u = gpu["util_gpu_pct"]
        print(
            f"gpu utilization (in-flight): p50 {u['p50']}%  p95 {u['p95']}%  "
            f"p99 {u['p99']}%  max {u['max']}%   [{gpu['samples_in_flight']} samples]"
        )
    else:
        print(f"gpu utilization: not measured ({gpu['status']})")
    vram = report["summary"]["peak_vram_bytes"]
    if vram:
        print(f"peak vram (server): {vram / 1e9:.2f} GB", end="")
        if gpu.get("mem_used_mb_max"):
            print(f"   mem.used max (nvidia-smi): {gpu['mem_used_mb_max'] / 1e3:.2f} GB")
        else:
            print()
    print()
    for w in report["warnings"]:
        print(f"WARNING: {w}", file=sys.stderr)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Concurrency-1 baseline runner for naive_server.")
    p.add_argument("--url", default="http://localhost:8000", help="naive_server base URL")
    p.add_argument("--prompts", type=Path, default=DEFAULT_PROMPTS)
    p.add_argument("--output-tokens", type=int, default=128,
                   help="forced output length; provisional until Week 2 fixes it")
    p.add_argument("--warmup", type=int, default=20, help="requests discarded per run (rule 2)")
    p.add_argument("--requests", type=int, default=100, help="measured requests per run")
    p.add_argument("--runs", type=int, default=3, help="repeated runs (rule 4)")
    p.add_argument("--gpu-sample-interval-ms", type=int, default=200)
    p.add_argument("--spread-threshold", type=float, default=0.10)
    p.add_argument("--request-timeout", type=float, default=600.0)
    p.add_argument("--out", type=Path, default=None,
                   help="output path (default: benchmarks/results/baseline-<ts>.json)")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    args.prompts = args.prompts.resolve()
    prompts = load_prompts(args.prompts)

    try:
        health = get_healthz(args.url)
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
    out_path = args.out or (RESULTS_DIR / f"baseline-{ts}.json")
    started = datetime.now(timezone.utc).isoformat()

    print(f"server up: {health['model_id']} on {health['device']}. "
          f"{args.runs} run(s), {args.warmup}+{args.requests} req each, "
          f"{args.output_tokens} output tokens.", file=sys.stderr)

    sampler = GpuSampler(args.gpu_sample_interval_ms)
    sampler.start()
    time.sleep(0.3)  # let the first nvidia-smi row land before request 1
    try:
        records: list[dict] = []
        for run_index in range(1, args.runs + 1):
            records.extend(run_once(args, prompts, run_index))
    finally:
        sampler.stop()
        sampler.join(timeout=5)

    report = build_report(args, health, records, sampler, started)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2))
    print_summary(report)
    print(f"\noutput: {out_path}", file=sys.stderr)
    if health.get("device", "").startswith("cpu"):
        print("note: CPU server — this is a correctness check, not a result. "
              "Do not commit the output file (ADR-0001).", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
