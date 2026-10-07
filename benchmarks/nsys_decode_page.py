#!/usr/bin/env python3
"""Render decode-deep-dive.html for an Nsight Systems trace of the naive server.

    python3 benchmarks/nsys_decode_page.py <profile-dir>/full [request] [first-step]

Stdlib only; opens trace.sqlite read-only and needs decode-summary.json from
nsys_decode_analysis.py. Takes 10 consecutive decode steps (default: request
16, steps 60-69) with every kernel and launch, derives per-GEMV weight rates
from the Qwen2.5-1.5B config, and inlines everything into
nsys_decode_template.html -> <profile-dir>/decode-deep-dive.html.
"""
import collections, json, math, re, sqlite3, statistics as st, pathlib, sys

PROF = pathlib.Path(sys.argv[1])
REQ = int(sys.argv[2]) if len(sys.argv) > 2 else 15
FIRST = int(sys.argv[3]) if len(sys.argv) > 3 else 60
c = sqlite3.connect(f"file:{PROF / 'trace.sqlite'}?mode=ro", uri=True)
S = dict(c.execute("select id, value from StringIds"))
t0 = c.execute("select utcEpochNs from TARGET_INFO_SESSION_START_TIME").fetchone()[0]
runner = json.loads((PROF / "runner.json").read_text())
reqs = [r for r in runner["raw"]["requests"] if not r["is_warmup"]]
MAIN = c.execute("select globalTid from CUPTI_ACTIVITY_KIND_RUNTIME group by globalTid order by count(*) desc limit 1").fetchone()[0]
summ = json.loads((PROF / "decode-summary.json").read_text())

CLS = ["gemv6", "gemv7", "elementwise", "reduce", "attention", "copycat", "other"]
def cls(name):
    if "gemvx" in name: return 0 if "(int)6" in name else 1
    if "flash" in name: return 4
    if "CatArray" in name or "direct_copy" in name: return 5
    if "reduce_kernel" in name: return 3
    if "elementwise" in name: return 2
    return 6

r = reqs[REQ]
a, b = int(r["t_start"] * 1e9 - t0), int(r["t_end"] * 1e9 - t0)
K = c.execute("""select start, end, correlationId, demangledName, gridX from CUPTI_ACTIVITY_KIND_KERNEL
                 where start >= ? and end <= ? order by start""", (a, b)).fetchall()
R = c.execute("""select start, end, nameId, correlationId from CUPTI_ACTIVITY_KIND_RUNTIME
                 where globalTid = ? and start >= ? and end <= ? order by start""", (MAIN, a - 5_000_000, b)).fetchall()
heads = [e for s, e, _, nm, gx in K if gx == 37984 and "gemvx" in S[nm]]
lo, hi = heads[FIRST - 1], heads[FIRST + 9]   # 10 consecutive decode steps
bounds = [x - lo for x in heads[FIRST - 1:FIRST + 10]]
rel = lambda t: round((t - lo) / 1e3, 2)
ks = [k for k in K if lo <= k[0] < hi]
corr_idx = {k[2]: i for i, k in enumerate(ks)}
launch = [[rel(s), rel(e), corr_idx[cid]] for s, e, nm, cid in R if cid in corr_idx and "Launch" in S[nm]]
syncs = [[rel(s), rel(e)] for s, e, nm, cid in R if lo - 1_000_000 <= s < hi + 1_000_000 and "Synchronize" in S[nm]]
kern = [[rel(s), rel(e), cls(S[nm])] for s, e, _, nm, gx in ks]

# per-layer GEMV roles from all 10 steps (order inside a layer: q k v o gate up down)
roles = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
role_d = collections.defaultdict(list)
head_d = []
for i in range(10):
    s_lo, s_hi = heads[FIRST - 1 + i], heads[FIRST + i]
    st_k = [k for k in K if s_lo <= k[0] < s_hi]
    head_d.append((st_k[-1][1] - st_k[-1][0]) / 1e3)
    for j in range(28):
        seg = st_k[64 + 40 * j: 104 + 40 * j]
        g = [(e - s) / 1e3 for s, e, _, nm, gx in seg if "gemvx" in S[nm]]
        if len(g) == 7:
            for role, d in zip(roles, g):
                role_d[role].append(d)
H, I, KV, V = 1536, 8960, 256, 151936      # Qwen2.5-1.5B config; cross-checked: total params = weights_vram_bytes / 2
role_bytes = {"q_proj": H * H * 2, "k_proj": H * KV * 2, "v_proj": H * KV * 2, "o_proj": H * H * 2,
              "gate_proj": H * I * 2, "up_proj": H * I * 2, "down_proj": I * H * 2, "lm_head": V * H * 2}
role_d["lm_head"] = head_d
bw = [{"role": k, "us": st.median(v), "mb": role_bytes[k] / 1e6, "gbps": role_bytes[k] / (st.median(v) * 1e3)}
      for k, v in role_d.items()]
param_check = (28 * (2 * H * H + 2 * H * KV + 3 * H * I) + V * H) / 1e9

# histograms over the 10 steps: host launch-to-launch interval, kernel durations
L = sorted(x for x in launch)
intervals = [L[i + 1][0] - L[i][0] for i in range(len(L) - 1)]
durs = [k[1] - k[0] for k in kern]
def hist(xs, lo=0.5, hi=3000, per=5):
    edges = [lo * 10 ** (i / per) for i in range(int(math.log10(hi / lo) * per) + 1)]
    cnt = [0] * (len(edges) - 1)
    for x in xs:
        if edges[0] <= x < edges[-1]:
            cnt[min(len(cnt) - 1, int(math.log10(x / lo) * per))] += 1
    return {"edges": edges, "counts": cnt, "n": len(xs)}

data = {
    "tl": {"bounds": bounds and [round(x / 1e3, 2) for x in bounds], "kernels": kern, "launches": launch, "syncs": syncs},
    "classes": CLS,
    "summary": summ,
    "bw": bw, "param_check_B": param_check,
    "intervals": hist(intervals), "durations": hist(durs),
    "interval_p50": st.median(intervals), "launch_call_p50": st.median([l[1] - l[0] for l in launch]),
    "duration_p50": st.median(durs),
}
tmpl = (pathlib.Path(__file__).resolve().parent / "nsys_decode_template.html").read_text()
body = tmpl.replace("__DATA__", json.dumps(data, separators=(",", ":")).replace("</", "<\\/"))
out = PROF.parent / "decode-deep-dive.html"
out.write_text('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
               '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
               "</head>\n<body>\n" + body + "\n</body>\n</html>\n")
print(f"wrote {out}")
print("kernels", len(kern), "launches", len(launch), "syncs", len(syncs), "bounds", data["tl"]["bounds"])
print("param check (B):", round(param_check, 4))
for x in bw: print(f"{x['role']:10s} {x['us']:8.1f} us {x['mb']:8.1f} MB {x['gbps']:6.0f} GB/s")
print("interval p50", data["interval_p50"], "launch call p50", data["launch_call_p50"], "kernel dur p50", data["duration_p50"])
print(len(json.dumps(data)) // 1024, "KB")
