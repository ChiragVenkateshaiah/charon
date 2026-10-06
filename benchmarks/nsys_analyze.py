#!/usr/bin/env python3
"""Summarize an Nsight Systems trace of the naive server, per decode step.

    python3 benchmarks/nsys_analyze.py <profile-dir>      # dir with trace.sqlite[.gz] + runner.json

Stdlib only; runs locally on CPU against the sqlite that `nsys stats` exported
on the instance. Writes <profile-dir>/summary.json and prints a short digest.

Everything here is MEASURED by the profiler on a PROFILED run: absolute times
are inflated by tracing overhead and must not be compared with or substituted
for benchmark results (ADR-0001). Ratios and counts (kernels/token, the
GPU-idle fraction, launch-to-start lag) are what this is for.

Step segmentation: Charon emits no NVTX, so steps are recovered from the trace.
The LM-head GEMV is the one kernel signature (name + grid) that runs exactly
once per generated token in every request — `generate()` keeps logits for the
last position only — so its end times delimit forward passes. Pass 0 is
prefill; passes 1..N-1 are steady-state decode.
"""
import collections, gzip, json, pathlib, re, shutil, sqlite3, statistics, sys


def pct(xs, p):
    if not xs:
        return None
    xs = sorted(xs)
    k = max(0, min(len(xs) - 1, round(p / 100 * len(xs) + 0.5) - 1))
    return xs[k]


def dist(xs, scale=1e-3):
    """p50/p95/p99/mean of ns values, reported in µs by default."""
    if not xs:
        return None
    return {"p50": pct(xs, 50) * scale, "p95": pct(xs, 95) * scale, "p99": pct(xs, 99) * scale,
            "mean": statistics.fmean(xs) * scale, "n": len(xs)}


def open_db(d):
    db = d / "trace.sqlite"
    if not db.exists() and (d / "trace.sqlite.gz").exists():
        with gzip.open(d / "trace.sqlite.gz") as src, open(db, "wb") as dst:
            shutil.copyfileobj(src, dst)
    return sqlite3.connect(db)


def short(name):
    """Readable kernel name from a demangled one, keeping gemv template ids distinct."""
    for pre in ("void ", "std::enable_if<!T7, void>::type "):
        name = name.removeprefix(pre)
    base = name.split("<")[0].split("(")[0]
    if "gemvx" in name:  # the (int)N template arg distinguishes the two cuBLAS GEMV variants
        m = re.search(r"\(int\)(\d+)", name)
        base += f"[{m.group(1)}]" if m else ""
    return base


def analyze(d):
    c = open_db(d)
    S = dict(c.execute("select id, value from StringIds"))
    t0 = c.execute("select utcEpochNs from TARGET_INFO_SESSION_START_TIME").fetchone()[0]
    sync_names = dict(c.execute("select id, label from ENUM_CUPTI_SYNC_TYPE"))
    copy_names = dict(c.execute("select id, label from ENUM_CUDA_MEMCPY_OPER"))
    runner = json.loads((d / "runner.json").read_text())
    reqs = [r for r in runner["raw"]["requests"] if not r["is_warmup"]]
    out_tokens = runner["config"]["output_tokens"]

    steps, prefill, per_req = [], [], []
    api_tot, api_ns = collections.Counter(), collections.Counter()
    kern_tot, kern_ns = collections.Counter(), collections.Counter()
    copies, syncs = collections.Counter(), collections.Counter()
    copy_ns, sync_ns = collections.Counter(), collections.Counter()
    lag_all, gaps_all = [], []
    gap_after = collections.Counter()
    head_sig = None

    for r in reqs:
        a, b = int(r["t_start"] * 1e9 - t0), int(r["t_end"] * 1e9 - t0)
        K = c.execute("""select start, end, correlationId, demangledName, gridX, gridY, gridZ
                         from CUPTI_ACTIVITY_KIND_KERNEL where start >= ? and end <= ? order by start""",
                      (a, b)).fetchall()
        M = c.execute("""select start, end, copyKind, bytes from CUPTI_ACTIVITY_KIND_MEMCPY
                         where start >= ? and end <= ?""", (a, b)).fetchall()
        Z = c.execute("select start, end from CUPTI_ACTIVITY_KIND_MEMSET where start >= ? and end <= ?",
                      (a, b)).fetchall()
        R = c.execute("""select start, end, nameId, correlationId from CUPTI_ACTIVITY_KIND_RUNTIME
                         where start >= ? and end <= ?""", (a, b)).fetchall()
        Y = c.execute("""select start, end, syncType from CUPTI_ACTIVITY_KIND_SYNCHRONIZATION
                         where start >= ? and end <= ?""", (a, b)).fetchall()
        if not K:
            continue

        # LM-head signature: once per token, longest mean duration among such signatures
        if head_sig is None:
            sig_n, sig_ns = collections.Counter(), collections.Counter()
            for s, e, _, n, gx, gy, gz in K:
                sig_n[(n, gx, gy, gz)] += 1
                sig_ns[(n, gx, gy, gz)] += e - s
            cands = [k for k, v in sig_n.items() if v == out_tokens]
            if not cands:
                raise SystemExit("no kernel signature runs exactly once per token; cannot segment steps")
            head_sig = max(cands, key=lambda k: sig_ns[k] / sig_n[k])
        bounds = [e for s, e, _, n, gx, gy, gz in K if (n, gx, gy, gz) == head_sig]

        launch_end = {cid: e for s, e, nid, cid in R}
        for s, e, nid, cid in R:
            api_tot[S[nid]] += 1
            api_ns[S[nid]] += e - s
        for s, e, k, nbytes in M:
            copies[copy_names.get(k, k)] += 1
            copy_ns[copy_names.get(k, k)] += e - s
        for s, e, t in Y:
            syncs[sync_names.get(t, t)] += 1
            sync_ns[sync_names.get(t, t)] += e - s

        # GPU activity intervals (kernels + copies + memsets), merged
        acts = sorted([(s, e) for s, e, *_ in K] + [(s, e) for s, e, *_ in M] + [(s, e) for s, e in Z])

        def window(lo, hi, label):
            ks = [k for k in K if lo <= k[0] < hi]
            iv = [x for x in acts if lo <= x[0] < hi]
            busy, gaps, cur_s, cur_e = 0, [], None, None
            names = {s: n for s, e, _, n, *_ in ks}
            prev_name = None
            for s, e in iv:
                if cur_e is None:
                    cur_s, cur_e = s, e
                elif s > cur_e:
                    busy += cur_e - cur_s
                    gaps.append(s - cur_e)
                    gap_after[short(S.get(prev_name, "memcpy/memset")) if prev_name else "?"] += s - cur_e
                    cur_s, cur_e = s, e
                else:
                    cur_e = max(cur_e, e)
                prev_name = names.get(s)
            if cur_e is not None:
                busy += cur_e - cur_s
            lags = [k[0] - launch_end[k[2]] for k in ks if k[2] in launch_end]
            return {"label": label, "wall_ns": hi - lo, "kernels": len(ks), "busy_ns": busy,
                    "gaps": gaps, "lags": lags}

        pre = window(a, bounds[0], "prefill")
        prefill.append(pre)
        req_steps = [window(bounds[i - 1], bounds[i], "decode") for i in range(1, len(bounds))]
        steps.extend(req_steps)
        for w in req_steps:
            gaps_all.extend(w["gaps"])
            lag_all.extend(w["lags"])
        for s, e, _, n, *_ in K:
            kern_tot[S.get(n, n)] += 1
            kern_ns[S.get(n, n)] += e - s
        per_req.append({"wall_ns": b - a, "kernels": len(K), "head_kernels": len(bounds)})

    n_req, n_tok = len(per_req), len(per_req) * out_tokens
    gpu_kernel_ns = sum(kern_ns.values())
    dec_wall = [w["wall_ns"] for w in steps]
    dec_busy = [w["busy_ns"] for w in steps]
    big = [g for g in gaps_all if g >= 100_000]
    summary = {
        "note": "Profiled run: absolute times include tracing overhead. Not a benchmark result.",
        "requests_analyzed": n_req,
        "tokens_analyzed": n_tok,
        "lm_head_signature": {"kernel": S.get(head_sig[0], head_sig[0]), "grid": head_sig[1:]},
        "per_request_wall_s": dist([r["wall_ns"] for r in per_req], 1e-9),
        "kernels_per_token": sum(r["kernels"] for r in per_req) / n_tok,
        "decode_step": {
            "count": len(steps),
            "wall_us": dist(dec_wall),
            "gpu_busy_us": dist(dec_busy),
            "gpu_busy_fraction": sum(dec_busy) / sum(dec_wall),
            "kernels": dist([w["kernels"] for w in steps], 1),
            "idle_gaps_per_step": dist([len(w["gaps"]) for w in steps], 1),
            "idle_gap_us": dist(gaps_all),
            "idle_total_per_step_us": dist([sum(w["gaps"]) for w in steps]),
            "gaps_ge_100us_per_step": len(big) / max(1, len(steps)),
            "gaps_ge_100us_total_share_of_idle": sum(big) / max(1, sum(gaps_all)),
            "launch_to_start_lag_us": dist(lag_all),
        },
        "prefill": {
            "wall_us": dist([w["wall_ns"] for w in prefill]),
            "gpu_busy_fraction": sum(w["busy_ns"] for w in prefill) / sum(w["wall_ns"] for w in prefill),
            "kernels": dist([w["kernels"] for w in prefill], 1),
        },
        "top_kernels": [
            {"kernel": short(k), "share_of_kernel_time": v / gpu_kernel_ns,
             "per_token": kern_tot[k] / n_tok, "mean_us": v / kern_tot[k] / 1e3}
            for k, v in kern_ns.most_common(10)],
        "kernel_time_top2_share": sum(v for _, v in kern_ns.most_common(2)) / gpu_kernel_ns,
        "kernels_under_5us_share_of_launches":
            None,  # filled below
        "launch_lag_share_under_5us": sum(1 for x in lag_all if x < 5000) / max(1, len(lag_all)),
        "launch_lag_share_over_100us": sum(1 for x in lag_all if x > 100_000) / max(1, len(lag_all)),
        "decode_idle_by_preceding_kernel": [
            {"kernel": k, "share_of_decode_idle": v / max(1, sum(gaps_all))}
            for k, v in gap_after.most_common(8)],
        "cuda_api_per_token": [
            {"api": k, "per_token": v / n_tok, "mean_us": api_ns[k] / v / 1e3,
             "cpu_ms_per_token": api_ns[k] / n_tok / 1e6}
            for k, v in api_tot.most_common(12)],
        "memcpy_per_token": {k: {"per_token": v / n_tok, "mean_us": copy_ns[k] / v / 1e3}
                             for k, v in copies.items()},
        "sync_per_token": {k: {"per_token": v / n_tok, "mean_us": sync_ns[k] / v / 1e3}
                           for k, v in syncs.items()},
    }
    tiny = c.execute("""select count(*) from CUPTI_ACTIVITY_KIND_KERNEL k
                        where (k.end - k.start) < 5000""").fetchone()[0]
    total = c.execute("select count(*) from CUPTI_ACTIVITY_KIND_KERNEL").fetchone()[0]
    summary["kernels_under_5us_share_of_launches"] = tiny / total
    return summary


def main(argv):
    d = pathlib.Path(argv[1])
    s = analyze(d)
    (d / "summary.json").write_text(json.dumps(s, indent=2))
    ds = s["decode_step"]
    print(f"requests {s['requests_analyzed']}, tokens {s['tokens_analyzed']}, "
          f"kernels/token {s['kernels_per_token']:.0f}")
    print(f"decode step wall p50 {ds['wall_us']['p50']:.0f} us, GPU busy {ds['gpu_busy_fraction']:.1%}, "
          f"gaps/step p50 {ds['idle_gaps_per_step']['p50']:.0f}, gap p50 {ds['idle_gap_us']['p50']:.1f} us, "
          f"launch->start lag p50 {ds['launch_to_start_lag_us']['p50']:.1f} us")
    for k in s["top_kernels"][:5]:
        print(f"  {k['share_of_kernel_time']:.1%}  {k['per_token']:.0f}/tok  {k['mean_us']:.1f} us  {k['kernel']}")
    print(f"wrote {d / 'summary.json'}")


if __name__ == "__main__":
    main(sys.argv)
