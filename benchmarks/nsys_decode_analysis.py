#!/usr/bin/env python3
"""Steady-state decode deep-dive on an Nsight Systems trace of the naive server.

    python3 benchmarks/nsys_decode_analysis.py <profile-dir>/full

Stdlib only; opens trace.sqlite read-only (unpack trace.sqlite.gz first, or run
nsys_analyze.py once, which does). Writes <profile-dir>/full/decode-summary.json:
per-step wall / GPU-busy / idle, host time inside vs outside CUDA calls on the
decode thread, kernels per token, the decode-only top-10 kernels with exact
names, sync positions and durations, prefill vs decode, and how many distinct
per-token kernel sequences occur. Used by nsys_decode_page.py and
decode-investigation.md. MEASURED under the profiler: not a benchmark result.
"""
import collections, json, re, sqlite3, statistics as st, sys, pathlib

PROF = pathlib.Path(sys.argv[1])
c = sqlite3.connect(f"file:{PROF / 'trace.sqlite'}?mode=ro", uri=True)
S = dict(c.execute("select id, value from StringIds"))
t0 = c.execute("select utcEpochNs from TARGET_INFO_SESSION_START_TIME").fetchone()[0]
runner = json.loads((PROF / "runner.json").read_text())
reqs = [r for r in runner["raw"]["requests"] if not r["is_warmup"]]
NOUT = runner["config"]["output_tokens"]
MAIN = c.execute("select globalTid from CUPTI_ACTIVITY_KIND_RUNTIME group by globalTid order by count(*) desc limit 1").fetchone()[0]
main_name = c.execute("select nameId from ThreadNames where globalTid=?", (MAIN,)).fetchone()


def kshort(name):
    n = name
    for pre in ("void ", "std::enable_if<!T7, void>::type "):
        n = n.removeprefix(pre)
    base = n.split("<")[0].split("(")[0]
    if "gemvx" in name:
        m = re.search(r"\(int\)(\d+)", name)
        base += f"[{m.group(1)}]"
    if base.startswith("at::native::") and "Functor" in name:
        m = re.search(r"(\w+Functor)", name)
        if m:
            base += "<" + m.group(1) + ">"
    return base


def union(iv):
    iv = sorted(iv)
    out = []
    for s, e in iv:
        if out and s <= out[-1][1]:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return out


head = None
steps = []                      # per decode step metrics
prefill = []
pre_host = []                   # request start -> first kernel (host pre-processing incl. tokenizer)
post_host = []                  # last kernel -> request end
dec_kern_ns, dec_kern_n = collections.Counter(), collections.Counter()
seq_hashes = collections.Counter()
sync_pos = []                   # (relative position 0..1, duration_us)
api_by_name = collections.Counter()
api_ns_by_name = collections.Counter()

for ri, r in enumerate(reqs):
    a, b = int(r["t_start"] * 1e9 - t0), int(r["t_end"] * 1e9 - t0)
    K = c.execute("""select start, end, correlationId, demangledName, gridX, gridY, gridZ, blockX
                     from CUPTI_ACTIVITY_KIND_KERNEL where start >= ? and end <= ? order by start""", (a, b)).fetchall()
    M = c.execute("select start, end, copyKind, bytes from CUPTI_ACTIVITY_KIND_MEMCPY where start >= ? and end <= ?", (a, b)).fetchall()
    Z = c.execute("select start, end from CUPTI_ACTIVITY_KIND_MEMSET where start >= ? and end <= ?", (a, b)).fetchall()
    R = c.execute("""select start, end, nameId, correlationId from CUPTI_ACTIVITY_KIND_RUNTIME
                     where globalTid = ? and start >= ? and end <= ? order by start""", (MAIN, a - 5_000_000, b)).fetchall()
    if head is None:
        n, tot = collections.Counter(), collections.Counter()
        for s, e, _, nm, gx, gy, gz, bx in K:
            n[(nm, gx, gy, gz)] += 1
            tot[(nm, gx, gy, gz)] += e - s
        head = max((k for k, v in n.items() if v == NOUT), key=lambda k: tot[k] / n[k])
    bounds = [e for s, e, _, nm, gx, gy, gz, bx in K if (nm, gx, gy, gz) == head]
    gpu_iv = [(s, e) for s, e, *_ in K] + [(s, e) for s, e, *_ in M] + [(s, e) for s, e in Z]
    pre_host.append((K[0][0] - a) / 1e3)
    post_host.append((b - max(e for s, e in gpu_iv)) / 1e3)

    def window(lo, hi):
        g = union([(s, e) for s, e in gpu_iv if lo <= s < hi])
        busy = sum(min(e, hi) - s for s, e in g)
        gaps = [g[i + 1][0] - g[i][1] for i in range(len(g) - 1)]
        if g:
            gaps = [g[0][0] - lo] + gaps          # idle from window start to first activity
        api = [(s, e, nm) for s, e, nm, _ in R if lo <= s < hi]
        api_u = union([(s, min(e, hi)) for s, e, _ in api])
        api_t = sum(e - s for s, e in api_u)
        syncs = [(s, e) for s, e, nm in api if "Synchronize" in S[nm]]
        launches = sum(1 for s, e, nm in api if "LaunchKernel" in S[nm])
        ks = [k for k in K if lo <= k[0] < hi]
        return {"wall": hi - lo, "busy": busy, "gaps": gaps, "api": api_t, "host_outside_api": (hi - lo) - api_t,
                "sync": syncs, "launches": launches, "kernels": len(ks), "ks": ks}

    w = window(a, bounds[0])
    prefill.append({k: w[k] for k in ("wall", "busy", "kernels", "launches", "api")})
    for i in range(1, len(bounds)):
        lo, hi = bounds[i - 1], bounds[i]
        w = window(lo, hi)
        for s, e, _, nm, *_ in w["ks"]:
            dec_kern_ns[nm] += e - s
            dec_kern_n[nm] += 1
        seq_hashes[hash(tuple(k[3] for k in w["ks"]))] += 1
        for s, e in w["sync"]:
            sync_pos.append(((s - lo) / (hi - lo), (e - s) / 1e3))
        for s, e, nm, _ in R:
            if lo <= s < hi:
                api_by_name[S[nm]] += 1
                api_ns_by_name[S[nm]] += e - s
        steps.append({"req": ri, "step": i, "wall": w["wall"], "busy": w["busy"], "n_gaps": len(w["gaps"]),
                      "idle": sum(w["gaps"]), "max_gap": max(w["gaps"]) if w["gaps"] else 0,
                      "api": w["api"], "outside": w["host_outside_api"], "kernels": w["kernels"],
                      "launches": w["launches"], "sync_ns": sum(e - s for s, e in w["sync"]), "n_sync": len(w["sync"])})

us = lambda xs: {"p50": st.median(xs) / 1e3, "p05": sorted(xs)[len(xs) // 20] / 1e3, "p95": sorted(xs)[len(xs) * 19 // 20] / 1e3,
                 "mean": st.fmean(xs) / 1e3}
total_dec_ns = sum(dec_kern_ns.values())
n_steps = len(steps)
summ = {
    "main_thread": S.get(main_name[0]) if main_name else None,
    "requests": len(reqs), "decode_steps": n_steps,
    "decode_kernels_total": sum(s["kernels"] for s in steps),
    "decode_kernels_per_step": us([s["kernels"] * 1000 for s in steps]),
    "decode_launch_calls_per_step": us([s["launches"] * 1000 for s in steps]),
    "wall_us": us([s["wall"] for s in steps]), "busy_us": us([s["busy"] for s in steps]),
    "idle_us": us([s["idle"] for s in steps]), "n_gaps": us([s["n_gaps"] * 1000 for s in steps]),
    "max_gap_us": us([s["max_gap"] for s in steps]),
    "host_in_cuda_api_us": us([s["api"] for s in steps]),
    "host_outside_cuda_api_us": us([s["outside"] for s in steps]),
    "sync_us_per_step": us([s["sync_ns"] for s in steps]), "n_sync": us([s["n_sync"] * 1000 for s in steps]),
    "prefill": {"wall_us": us([p["wall"] for p in prefill]), "busy_us": us([p["busy"] for p in prefill]),
                "kernels": us([p["kernels"] * 1000 for p in prefill]), "api_us": us([p["api"] for p in prefill])},
    "pre_host_us": {"p50": st.median(pre_host), "min": min(pre_host), "max": max(pre_host)},
    "post_host_us": {"p50": st.median(post_host), "min": min(post_host), "max": max(post_host)},
    "distinct_step_sequences": len(seq_hashes), "top_sequence_share": seq_hashes.most_common(1)[0][1] / n_steps,
    "top_sequences": [v / n_steps for _, v in seq_hashes.most_common(5)],
    "decode_top10": [{"name": S[k], "short": kshort(S[k]), "calls": dec_kern_n[k], "total_ms": v / 1e6,
                      "pct": 100 * v / total_dec_ns, "per_token": dec_kern_n[k] / n_steps} for k, v in dec_kern_ns.most_common(10)],
    "decode_api": [{"api": k, "per_step": v / n_steps, "mean_us": api_ns_by_name[k] / v / 1e3,
                    "ms_per_step": api_ns_by_name[k] / n_steps / 1e6} for k, v in api_by_name.most_common(12)],
    "sync_positions": collections.Counter(round(p, 1) for p, _ in sync_pos).most_common(),
    "sync_early_us": us([d * 1e3 for p, d in sync_pos if p < 0.5]) if any(p < 0.5 for p, _ in sync_pos) else None,
    "sync_late_us": us([d * 1e3 for p, d in sync_pos if p >= 0.5]) if any(p >= 0.5 for p, _ in sync_pos) else None,
    "sync_early_count": sum(1 for p, _ in sync_pos if p < 0.5), "sync_late_count": sum(1 for p, _ in sync_pos if p >= 0.5),
}
(PROF / "decode-summary.json").write_text(json.dumps(summ, indent=1))
print(f"wrote {PROF / 'decode-summary.json'}")
print(json.dumps({k: summ[k] for k in summ if k not in ("decode_top10",)}, indent=1)[:6000])
for t in summ["decode_top10"]:
    print(f"{t['pct']:5.1f}% {t['calls']:7d} {t['total_ms']:9.1f} ms  {t['short']}")
