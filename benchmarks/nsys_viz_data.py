#!/usr/bin/env python3
"""Extract the data behind the profile visualization from an nsys trace.

    python3 benchmarks/nsys_viz_data.py <profile-dir> [request] [step]

Stdlib only. Reads <profile-dir>/trace.sqlite(.gz) + runner.json (same inputs
as nsys_analyze.py) and writes <profile-dir>/viz-data.json:

  step      one real decode step, kernel by kernel and launch by launch
  series    wall vs GPU-busy time for every decode step
  gaps/lags log-binned histograms of idle gaps and launch-to-start lag
  classes   kernel time share vs launch share by kernel class

and renders <profile-dir>/../visualization.html from nsys_viz_template.html.
To re-render from an existing viz-data.json without re-reading the trace:

    python3 -c "import sys; sys.path.insert(0,'benchmarks'); import nsys_viz_data as v, pathlib as p; \\
      d=p.Path('<profile-dir>'); v.render((d/'viz-data.json').read_text(), d.parent/'visualization.html')"

All of it is MEASURED under the profiler (times inflated by tracing; not a
benchmark result, ADR-0001). Steps are delimited by the LM-head GEMV, exactly
as in nsys_analyze.py.
"""
import collections, json, math, pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from nsys_analyze import open_db  # noqa: E402


def klass(name):
    if "gemvx" in name:
        return "gemv6" if "(int)6" in name else "gemv7"
    if "flash" in name:
        return "attention"
    if "reduce_kernel" in name:
        return "reduce"
    if "elementwise" in name:
        return "elementwise"
    return "other"


def log_hist(values_ns, lo_us=0.5, hi_us=20000, per_decade=6):
    edges = [lo_us * 10 ** (i / per_decade)
             for i in range(int(math.log10(hi_us / lo_us) * per_decade) + 1)]
    counts = [0] * (len(edges) - 1)
    under = over = 0
    for v in values_ns:
        u = v / 1e3
        if u < edges[0]:
            under += 1
        elif u >= edges[-1]:
            over += 1
        else:
            counts[min(len(counts) - 1, int(math.log10(u / lo_us) * per_decade))] += 1
    return {"edges_us": edges, "counts": counts, "under": under, "over": over}


def main(argv):
    d = pathlib.Path(argv[1])
    pick_req = int(argv[2]) if len(argv) > 2 else 15
    pick_step = int(argv[3]) if len(argv) > 3 else 64
    c = open_db(d)
    S = dict(c.execute("select id, value from StringIds"))
    t0 = c.execute("select utcEpochNs from TARGET_INFO_SESSION_START_TIME").fetchone()[0]
    runner = json.loads((d / "runner.json").read_text())
    reqs = [r for r in runner["raw"]["requests"] if not r["is_warmup"]]
    n_out = runner["config"]["output_tokens"]

    series, gaps, lags = [], [], []
    cls_ns, cls_n = collections.Counter(), collections.Counter()
    head = None
    step = None
    for ri, r in enumerate(reqs):
        a, b = int(r["t_start"] * 1e9 - t0), int(r["t_end"] * 1e9 - t0)
        K = c.execute("""select start, end, correlationId, demangledName, gridX, gridY, gridZ
                         from CUPTI_ACTIVITY_KIND_KERNEL where start >= ? and end <= ? order by start""",
                      (a, b)).fetchall()
        M = c.execute("""select start, end, copyKind from CUPTI_ACTIVITY_KIND_MEMCPY
                         where start >= ? and end <= ?""", (a, b)).fetchall()
        R = c.execute("""select start, end, nameId, correlationId from CUPTI_ACTIVITY_KIND_RUNTIME
                         where start >= ? and end <= ?""", (a, b)).fetchall()
        if head is None:
            n, tot = collections.Counter(), collections.Counter()
            for s, e, _, nm, gx, gy, gz in K:
                n[(nm, gx, gy, gz)] += 1
                tot[(nm, gx, gy, gz)] += e - s
            head = max((k for k, v in n.items() if v == n_out), key=lambda k: tot[k] / n[k])
        bounds = [e for s, e, _, nm, gx, gy, gz in K if (nm, gx, gy, gz) == head]
        launch = {cid: (s, e, S[nid]) for s, e, nid, cid in R}
        acts = sorted([(s, e) for s, e, *_ in K] + [(s, e, ) for s, e, _ in M])

        for s, e, _, nm, *_ in K:
            k = klass(S[nm])
            cls_ns[k] += e - s
            cls_n[k] += 1

        for i in range(1, len(bounds)):
            lo, hi = bounds[i - 1], bounds[i]
            busy, cur_s, cur_e = 0, None, None
            for s, e in acts:
                if s < lo or s >= hi:
                    continue
                if cur_e is None:
                    cur_s, cur_e = s, e
                elif s > cur_e:
                    busy += cur_e - cur_s
                    gaps.append(s - cur_e)
                    cur_s, cur_e = s, e
                else:
                    cur_e = max(cur_e, e)
            if cur_e is not None:
                busy += cur_e - cur_s
            ks = [k for k in K if lo <= k[0] < hi]
            lags.extend(k[0] - launch[k[2]][1] for k in ks if k[2] in launch)
            series.append([round((hi - lo) / 1e3, 1), round(busy / 1e3, 1)])

            if ri == pick_req and i == pick_step:
                rel = lambda t: round((t - lo) / 1e3, 3)
                step = {
                    "request": ri, "step": i, "wall_us": rel(hi),
                    "kernels": [[rel(s), rel(e), klass(S[nm])] for s, e, _, nm, *_ in ks],
                    "launches": [[rel(launch[cid][0]), rel(launch[cid][1]), j]
                                 for j, (s, e, cid, *_) in enumerate(ks) if cid in launch],
                    "syncs": [[rel(s), rel(e)] for s, e, nid, _ in R
                              if lo <= s < hi and "Synchronize" in S[nid]],
                    "copies": [[rel(s), rel(e), k] for s, e, k in M if lo <= s < hi],
                }

    total_ns, total_n = sum(cls_ns.values()), sum(cls_n.values())
    out = {
        "note": "MEASURED under nsys (profiled; times inflated by tracing). Not a benchmark result.",
        "source": str(d),
        "step": step,
        "series": series,
        "gaps": log_hist(gaps),
        "lags": log_hist(lags, lo_us=0.25),
        "classes": {k: {"time_share": cls_ns[k] / total_ns, "launch_share": cls_n[k] / total_n,
                        "per_token": cls_n[k] / (len(reqs) * n_out),
                        "mean_us": cls_ns[k] / cls_n[k] / 1e3} for k in cls_ns},
    }
    data = json.dumps(out, separators=(",", ":"))
    (d / "viz-data.json").write_text(data)
    print(f"wrote {d / 'viz-data.json'}: step {pick_req}/{pick_step} with "
          f"{len(step['kernels'])} kernels, {len(series)} steps in series")
    render(data, d.parent / "visualization.html")


def render(data, out_path):
    """Inline the data into nsys_viz_template.html -> a standalone page."""
    tmpl = (pathlib.Path(__file__).resolve().parent / "nsys_viz_template.html").read_text()
    body = tmpl.replace("__DATA__", data.replace("</", "<\\/"))
    out_path.write_text('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
                        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
                        "</head>\n<body>\n" + body + "\n</body>\n</html>\n")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main(sys.argv)
