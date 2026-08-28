#!/usr/bin/env python3
"""Social-image charts for the Week 1 baseline article.

    python3 Articles/charts/mkcharts.py

SVG -> PNG via `rsvg-convert` (librsvg), stdlib only. Reads the committed raw
result directly; every value in the output is traceable to that file or is
explicitly labelled 'derived'. Run from the repo root.
"""
import json, math, subprocess, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
LI, MD = ROOT / "Articles/LinkedIn", ROOT / "Articles/Medium"
RESULT = ROOT / "benchmarks/results/baseline-20260828T172338Z.json"

_d = json.load(open(RESULT))
_reqs = _d["raw"]["requests"]
_t0 = min(r["t_start"] for r in _reqs)
_samples = [s for s in _d["raw"]["gpu_samples"] if s["util_gpu_pct"] is not None]
_step = max(1, len(_samples) // 500)
GPU = [[round((s["t"] - _t0) / 60, 3), int(round(s["util_gpu_pct"]))] for s in _samples[::_step]]
# run-start times in minutes, for the boundary markers
_runs = {}
for _r in _reqs:
    _runs.setdefault(_r["run"], []).append(_r["t_start"] - _t0)
RUN_STARTS = [round(min(v) / 60, 2) for k, v in sorted(_runs.items())][1:]  # drop run 1 (=0)

BG = "#fbfaf7"
INK, MUTE, FAINT = "#221e17", "#6b6353", "#a49a89"
RULE, RULE2 = "#e7e2d7", "#d7d0c1"
ACCENT, ACCENT_SOFT = "#b4671e", "#f2e6d6"
WASTE = "#d8d1c1"
DISP = "Ubuntu, 'DejaVu Sans', sans-serif"
MONO = "'JetBrains Mono', 'DejaVu Sans Mono', monospace"
FOOT = "Charon · Phase 1 Week 1  ·  run 2026-08-28 on a GCP spot NVIDIA L4  ·  github.com/ChiragVenkateshaiah/charon"


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def txt(x, y, s, size, *, fill=INK, font=DISP, w=400, anchor="start", ls=0):
    a = f' letter-spacing="{ls}"' if ls else ""
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-family="{font}" font-size="{size}" '
            f'font-weight="{w}" fill="{fill}" text-anchor="{anchor}"{a}>{esc(s)}</text>')


def page(W, H, title, sub, marks):
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
        f'<rect width="{W}" height="{H}" fill="{BG}"/>',
        f'<rect width="{W}" height="6" fill="{ACCENT}"/>',
        txt(64, 96, title, 44, w=700),
        txt(64, 138, sub, 22, fill=MUTE),
        f'<line x1="64" y1="{H-58}" x2="{W-64}" y2="{H-58}" stroke="{RULE}" stroke-width="1.5"/>',
        txt(64, H - 30, FOOT, 14.5, fill=FAINT, font=MONO),
    ]
    out += marks
    out.append("</svg>")
    return "\n".join(out)


def render(name, chart):
    W, H = chart["W"], chart["H"]
    svg = page(W, H, chart["title"], chart["sub"], chart["marks"]).encode()
    for outdir, w in ((MD, W), (LI, min(W, 1200))):
        outdir.mkdir(parents=True, exist_ok=True)
        subprocess.run(["rsvg-convert", "-w", str(w), "-o", str(outdir / f"{name}.png")],
                       input=svg, check=True)
    print(f"  {name}  {W}x{H}")


# ---------------------------------------------------------------- 01 two measurements (dot plot on log axis)
def c_two():
    W, H = 1200, 760
    L, R, T = 110, 110, 230
    pw = W - L - R
    lo, hi = -2.0, 2.0  # 0.01% .. 100%
    x = lambda v: L + (math.log10(v) - lo) / (hi - lo) * pw
    ax_top, ax_bot = T - 30, T + 250
    m = []
    for g in (0.01, 0.1, 1, 10, 100):
        m.append(f'<line x1="{x(g):.1f}" y1="{ax_top}" x2="{x(g):.1f}" y2="{ax_bot}" stroke="{RULE}" stroke-width="1.5"/>')
        m.append(txt(x(g), ax_bot + 34, f"{g:g}%", 18, fill=FAINT, font=MONO, anchor="middle"))
    m.append(txt(L, ax_bot + 62, "share of the L4's capacity  ·  log scale", 15, fill=FAINT, font=MONO))
    rows = [("what nvidia-smi reported", 53.0, "53%", "fraction of wall-clock a kernel was running  ·  measured"),
            ("what the tensor cores did", 0.09, "0.09%", "model-FLOPs utilization  ·  derived from datasheet FLOPS, not measured")]
    ys = [T + 30, T + 175]
    for (lab, v, disp, note), yy in zip(rows, ys):
        m.append(txt(L, yy - 32, lab, 24, w=600))
        m.append(f'<circle cx="{x(v):.1f}" cy="{yy}" r="16" fill="{ACCENT}"/>')
        m.append(txt(x(v) + 30, yy + 9, disp, 32, w=700, fill=ACCENT, font=MONO))
        m.append(txt(L, yy + 40, note, 16, fill=FAINT))
    m.append(txt(64, H - 92, "Same L4, same 22 minutes. Not one number two ways — two different measurements answering", 17, fill=MUTE))
    m.append(txt(64, H - 70, "two different questions. Neither is a headroom estimate for the other.", 17, fill=MUTE))
    return dict(W=W, H=H, title="nvidia-smi said 53%. The tensor cores did 0.09%.",
                sub="NVIDIA L4 · naive single-stream server · batch size 1", marks=m)


# ---------------------------------------------------------------- 02 gpu timeline
def c_timeline():
    W, H = 1600, 820
    L, R, T, B = 92, 60, 190, 96
    pw, ph = W - L - R, H - T - B
    xmax = GPU[-1][0]
    x = lambda v: L + v / xmax * pw
    y = lambda v: T + (1 - v / 100) * ph
    m = []
    for gy in (0, 25, 50, 75, 100):
        m.append(f'<line x1="{L}" y1="{y(gy):.1f}" x2="{L+pw}" y2="{y(gy):.1f}" stroke="{RULE}" stroke-width="1.5"/>')
        m.append(txt(L - 16, y(gy) + 6, str(gy), 18, fill=FAINT, font=MONO, anchor="end"))
    for gx in (0, 5, 10, 15, 20):
        m.append(txt(x(gx), H - B + 36, str(gx), 18, fill=FAINT, font=MONO, anchor="middle"))
    m.append(txt(L + pw - 4, H - B + 36, "min", 16, fill=FAINT, font=MONO, anchor="end"))
    m.append(txt(L, T - 18, "nvidia-smi util %", 15, fill=FAINT, anchor="start"))
    for rb in RUN_STARTS:
        m.append(f'<line x1="{x(rb):.1f}" y1="{T}" x2="{x(rb):.1f}" y2="{y(0):.1f}" stroke="{RULE2}" stroke-width="1.5" stroke-dasharray="2 4"/>')
    pts = " ".join(f"{x(t):.1f},{y(u):.1f}" for t, u in GPU)
    m.append(f'<polygon points="{x(GPU[0][0]):.1f},{y(0):.1f} {pts} {x(GPU[-1][0]):.1f},{y(0):.1f}" fill="{ACCENT_SOFT}"/>')
    m.append(f'<polyline points="{pts}" fill="none" stroke="{ACCENT}" stroke-width="2" stroke-linejoin="round"/>')
    m.append(txt(x(11.2), y(52) - 200, "three runs, back to back", 21, w=600, fill=MUTE, anchor="middle"))
    m.append(txt(x(11.2), y(52) - 174, "each one lands on the same ~53% line — and that number", 18, fill=FAINT, anchor="middle"))
    m.append(txt(x(11.2), y(52) - 152, "still says nothing about the tensor cores", 18, fill=FAINT, anchor="middle"))
    m.append(txt(x(GPU[-1][0]) - 6, y(53) - 12, "~53%", 22, w=700, fill=ACCENT, font=MONO, anchor="end"))
    return dict(W=W, H=H, title="What the utilization meter did for 22 minutes",
                sub="All 6,683 nvidia-smi samples · dashed lines mark the 3 run boundaries · dips are sampling noise", marks=m)


# ---------------------------------------------------------------- 03 token budget
def c_budget():
    W, H = 1600, 640
    L, R, T = 92, 92, 190
    pw = W - L - R
    total = 29.0
    x = lambda v: L + v / total * pw
    bh, by = 74, T + 24
    m = [txt(L, by - 22, "measured TPOT p50 = 29.0 ms", 19, w=600, fill=INK, font=MONO)]
    for g in (5, 10, 15, 20, 25):
        m.append(f'<line x1="{x(g):.1f}" y1="{by-12}" x2="{x(g):.1f}" y2="{by+bh+12}" stroke="{RULE}" stroke-width="1.5"/>')
        m.append(txt(x(g), by + bh + 38, str(g), 16, fill=FAINT, font=MONO, anchor="middle"))
    m.append(txt(W - R, by - 22, "ms per output token", 16, fill=FAINT, anchor="end"))
    segs = [(10.3, ACCENT, "~10.3 ms", "the bandwidth-bound floor: 3.09 GB of weights / ~300 GB/s", "derived"),
            (18.7, WASTE, "~18.7 ms", "everything the bandwidth bound does not account for", "the remainder")]
    cur = 0.0
    for i, (w, col, disp, note, tag) in enumerate(segs):
        x0 = x(cur) + (2 if i else 0)
        m.append(f'<rect x="{x0:.1f}" y="{by}" width="{max(4, x(cur+w)-x0):.1f}" height="{bh}" rx="7" fill="{col}"/>')
        cur += w
    ly = by + bh + 80
    for i, (w, col, disp, note, tag) in enumerate(segs):
        yy = ly + i * 54
        m.append(f'<rect x="{L}" y="{yy-20}" width="24" height="24" rx="5" fill="{col}"/>')
        m.append(txt(L + 38, yy, disp, 22, w=700, fill=INK, font=MONO))
        m.append(txt(L + 190, yy, note, 19, fill=MUTE))
        m.append(txt(W - R, yy, tag, 17, fill=FAINT, anchor="end"))
    m.append(txt(L, ly + 2 * 54 + 24, "The 29.0 ms is measured. The split uses the L4's datasheet ~300 GB/s — derived, not measured. "
                "Precise attribution of the remainder needs a profiler (Phase 2).", 16, fill=FAINT))
    return dict(W=W, H=H, title="Where each token's 29 milliseconds goes",
                sub="Inter-token latency vs. the bandwidth-bound floor set by the L4 datasheet", marks=m)


# ---------------------------------------------------------------- 04 the arc
def c_arc():
    W, H = 1600, 660
    L, R, T = 150, 150, 250
    pw = W - L - R
    steps = [
        ("Week 1", "Naive baseline", "34.5 tok/s · measured", True),
        ("Week 2", "Concurrency sweep", "the saturation knee", False),
        ("Week 3", "Continuous batching", "big multiple — hypothesis", False),
        ("Week 4", "KV-cache ceiling", "when cache > weights?", False),
        ("Week 5", "Quantization", "INT8 / 4-bit", False),
        ("Week 7", "Cost / 1M tokens", "the deciding number", False),
    ]
    n = len(steps)
    xs = [L + pw * i / (n - 1) for i in range(n)]
    yline = T + 60
    dx = xs[0]
    for (wk, ti, no, done), xc in zip(steps, xs):
        if done:
            dx = xc
    m = [
        f'<line x1="{xs[0]:.0f}" y1="{yline}" x2="{xs[-1]:.0f}" y2="{yline}" stroke="{RULE2}" stroke-width="3"/>',
        f'<line x1="{xs[0]:.0f}" y1="{yline}" x2="{dx:.0f}" y2="{yline}" stroke="{ACCENT}" stroke-width="3"/>',
    ]
    for (wk, ti, no, done), xc in zip(steps, xs):
        col = ACCENT if done else MUTE
        if done:
            m.append(f'<circle cx="{xc:.0f}" cy="{yline}" r="14" fill="{ACCENT}"/>')
        else:
            m.append(f'<circle cx="{xc:.0f}" cy="{yline}" r="12" fill="{BG}" stroke="{MUTE}" stroke-width="2.5" stroke-dasharray="3 4"/>')
        m.append(txt(xc, yline - 44, wk, 19, w=700, fill=col, font=MONO, anchor="middle"))
        m.append(txt(xc, yline + 64, ti, 21, w=600, fill=INK, anchor="middle"))
        m.append(txt(xc, yline + 94, no, 16, fill=(MUTE if done else FAINT), anchor="middle"))
    m.append(txt(64, H - 88, "Selected milestones. Every future number is a hypothesis until it is measured on real hardware — the project's first rule.", 17, fill=MUTE))
    return dict(W=W, H=H, title="This is the slowest it will ever be",
                sub="Phase 1, selected milestones — one committed, measured number per step", marks=m)


if __name__ == "__main__":
    for d in (LI, MD):
        d.mkdir(parents=True, exist_ok=True)
    print("rendering...")
    render("01-two-measurements", c_two())
    render("02-utilization-timeline", c_timeline())
    render("03-token-budget", c_budget())
    render("04-the-arc", c_arc())
    print("done.")
