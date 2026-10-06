#!/usr/bin/env python3
"""Simplified roofline for a committed benchmark result.

    python3 benchmarks/roofline.py [benchmarks/roofline-week1.json]

Stdlib only (no matplotlib — see CLAUDE.md on tooling additions); writes an SVG
and prints the numbers as Markdown tables. Run from the repo root.

This is an analysis over a committed run, not a measurement: it produces no new
number (ADR-0001). Every value it emits carries one of five kinds:

    measured      read from the committed result file, never copied into config
    datasheet     vendor peak figures, not measured here
    assumption    modelling choices and owner-supplied rates
    derived       arithmetic over the above — inherits their caveats
    hypothetical  what-if throughputs; not results of any run

The traffic model is deliberately simplified: bytes/token = the weight set, read
once per decode step. It ignores KV-cache, activation and logits traffic and is
not a profiler measurement. Nothing here establishes what bounds the server.
"""
import json, math, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "benchmarks/roofline-week1.json"
KINDS = ("measured", "datasheet", "assumption", "derived", "hypothetical")


# ---------------------------------------------------------------- formulas
def ridge_point(peak_flops, bandwidth):
    """FLOP/byte where the memory roof meets the compute roof."""
    return peak_flops / bandwidth


def attainable(ai, peak_flops, bandwidth):
    """Roofline ceiling at arithmetic intensity `ai`: min(compute, BW × AI)."""
    return min(peak_flops, bandwidth * ai)


def model_flops_per_s(params, tok_s, flops_per_param=2):
    """2N approximation: FLOP/s = flops_per_param × params × tok/s."""
    return flops_per_param * params * tok_s


def cost_per_1m_tokens(inr_per_hour, tok_s, duty_cycle=1.0):
    """₹ per 1M output tokens = hourly / (3600 × tok/s × duty) × 1e6."""
    return inr_per_hour / (3600 * tok_s * duty_cycle) * 1_000_000


# ---------------------------------------------------------------- inputs
def _dig(obj, path):
    for k in path:
        obj = obj[k]
    return obj


def load(config_path=DEFAULT_CONFIG):
    cfg = json.loads(pathlib.Path(config_path).read_text())
    for name, spec in cfg["measured"].items():
        if "value" in spec:
            raise ValueError(f"measured input {name!r} has an inline value; "
                             "measured values must be read from result_file by path")
    result = json.loads((ROOT / cfg["result_file"]).read_text())
    measured = {k: _dig(result, s["path"]) for k, s in cfg["measured"].items()}
    return cfg, measured


def compute(cfg, measured):
    """Return {name: {"value", "unit", "kind", "basis"}} plus the scenario rows."""
    ds, asm = cfg["datasheet"], cfg["assumptions"]
    peak = ds["peak_bf16_flops"]["value"]
    bw = ds["memory_bandwidth_bytes_per_s"]["value"]
    params = asm["parameters"]["value"]
    fpp = asm["flops_per_param_per_token"]["value"]
    rate = asm["gpu_cost_inr_per_hour"]["value"]
    duty = asm["cost_duty_cycle"]["value"]
    tok_s = measured["decode_tokens_per_s"]
    bytes_tok = measured["weights_vram_bytes"]  # simplified traffic model

    v = {}

    def put(name, value, unit, kind, basis):
        assert kind in KINDS, kind
        v[name] = {"value": value, "unit": unit, "kind": kind, "basis": basis}

    for k, s in cfg["measured"].items():
        put(k, measured[k], s["unit"], "measured", f"{cfg['result_file']}: {'.'.join(s['path'])}")
    put("peak_bf16_flops", peak, "FLOP/s", "datasheet", ds["peak_bf16_flops"]["source"])
    put("memory_bandwidth", bw, "B/s", "datasheet", ds["memory_bandwidth_bytes_per_s"]["source"])
    put("parameters", params, "params", "assumption", asm["parameters"]["source"])
    put("gpu_cost_inr_per_hour", rate, "INR/h", "assumption", asm["gpu_cost_inr_per_hour"]["source"])

    flops_tok = fpp * params
    put("flops_per_token", flops_tok, "FLOP", "derived", "flops_per_param × parameters")
    put("bytes_per_token", bytes_tok, "B", "derived",
        "= weights_vram_bytes under the weight-traffic-only model (an under-count)")
    ai = flops_tok / bytes_tok
    put("arithmetic_intensity", ai, "FLOP/B", "derived", "flops_per_token / bytes_per_token")
    put("ridge_point", ridge_point(peak, bw), "FLOP/B", "derived", "peak_bf16_flops / memory_bandwidth")
    perf = model_flops_per_s(params, tok_s, fpp)
    put("model_flops_per_s", perf, "FLOP/s", "derived", "flops_per_param × parameters × measured tok/s")
    put("mfu", perf / peak, "fraction", "derived", "model_flops_per_s / peak_bf16_flops")
    put("weight_traffic_rate", tok_s * bytes_tok, "B/s", "derived",
        "measured tok/s × weights_vram_bytes — NOT measured DRAM bandwidth")
    roof = attainable(ai, peak, bw)
    put("memory_roof_at_ai", roof, "FLOP/s", "derived", "memory_bandwidth × arithmetic_intensity")
    put("fraction_of_roof", perf / roof, "fraction", "derived", "model_flops_per_s / memory_roof_at_ai")
    put("bw_bound_tok_s_ceiling", bw / bytes_tok, "tok/s", "derived",
        "memory_bandwidth / bytes_per_token — ceiling under this model at batch 1")

    rows = [{"tok_s": tok_s, "kind": "measured"}]
    rows += [{"tok_s": float(t), "kind": "hypothetical"} for t in cfg["hypothetical_tokens_per_s"]]
    for r in rows:
        r["flops_per_s"] = model_flops_per_s(params, r["tok_s"], fpp)
        r["ai"] = ai  # same bytes/token at batch 1 — that is the scenario's premise
        r["above_memory_roof"] = r["flops_per_s"] > roof
        r["inr_per_1m"] = cost_per_1m_tokens(rate, r["tok_s"], duty)
    return v, rows


# ---------------------------------------------------------------- SVG
BG, INK, MUTE, FAINT = "#fbfaf7", "#221e17", "#6b6353", "#a49a89"
RULE, ACCENT, HYPO = "#e7e2d7", "#b4671e", "#5b6f8a"
DISP = "Ubuntu, 'DejaVu Sans', sans-serif"
MONO = "'JetBrains Mono', 'DejaVu Sans Mono', monospace"


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def txt(x, y, s, size, *, fill=INK, font=DISP, w=400, anchor="start"):
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-family="{font}" font-size="{size}" '
            f'font-weight="{w}" fill="{fill}" text-anchor="{anchor}">{esc(s)}</text>')


def line(x1, y1, x2, y2, stroke, w=1.5, dash=None):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="{stroke}" stroke-width="{w}"{d}/>')


def dot(x, y, kind, r=7):
    if kind == "measured":
        return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{ACCENT}" stroke="{BG}" stroke-width="2"/>'
    return (f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r - 1}" fill="{BG}" '
            f'stroke="{HYPO}" stroke-width="2" stroke-dasharray="3 2"/>')


def fmt_g(flops):
    return f"{flops / 1e9:,.0f} GFLOP/s"


def render_svg(cfg, v, rows):
    W, H = 1440, 880
    peak, bw = v["peak_bf16_flops"]["value"], v["memory_bandwidth"]["value"]
    ai, ridge = v["arithmetic_intensity"]["value"], v["ridge_point"]["value"]
    base = rows[0]
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
           f'<rect width="{W}" height="{H}" fill="{BG}"/>',
           f'<rect width="{W}" height="6" fill="{ACCENT}"/>',
           txt(56, 64, cfg["chart_heading"], 30, w=700),
           txt(56, 98, cfg["subtitle"] + "  ·  a hypothesis, not a diagnosis: no kernel-level profile behind it", 18, fill=MUTE)]

    # ---- left panel: log-log roofline
    L, R, T, B = 110, 860, 150, 700
    xlo, xhi, ylo, yhi = -1, 4, 1, 6  # 0.1..10^4 FLOP/B ; 10..10^6 GFLOP/s
    X = lambda a: L + (math.log10(a) - xlo) / (xhi - xlo) * (R - L)
    Y = lambda g: B - (math.log10(g) - ylo) / (yhi - ylo) * (B - T)
    for e in range(xlo, xhi + 1):
        out += [line(X(10 ** e), T, X(10 ** e), B, RULE, 1),
                txt(X(10 ** e), B + 24, f"{10 ** e:g}", 14, fill=MUTE, font=MONO, anchor="middle")]
    for e in range(ylo, yhi + 1):
        out += [line(L, Y(10 ** e), R, Y(10 ** e), RULE, 1),
                txt(L - 10, Y(10 ** e) + 5, f"{10 ** e:,.0f}", 14, fill=MUTE, font=MONO, anchor="end")]
    out += [txt((L + R) / 2, B + 54, "Arithmetic intensity (FLOP/byte, log)", 15, fill=MUTE, anchor="middle"),
            f'<text transform="translate({L - 78},{(T + B) / 2}) rotate(-90)" font-family="{DISP}" '
            f'font-size="15" fill="{MUTE}" text-anchor="middle">Performance (GFLOP/s, log)</text>']
    # roofs (datasheet)
    pk_g = peak / 1e9
    out += [line(X(10 ** xlo), Y(bw * 10 ** xlo / 1e9), X(ridge), Y(pk_g), INK, 2.5),
            line(X(ridge), Y(pk_g), X(10 ** xhi), Y(pk_g), INK, 2.5),
            line(X(ridge), Y(pk_g), X(ridge), B, FAINT, 1.2, "4 4"),
            txt(X(ridge) + 8, Y(pk_g) - 12, f"Compute roof {pk_g:,.0f} GFLOP/s", 13, fill=INK),
            txt(X(ridge) + 8, Y(pk_g) + 22, "(datasheet BF16 dense)", 13, fill=MUTE),
            txt(X(ridge) + 8, B - 12, f"ridge ≈ {ridge:.0f} FLOP/B", 13, fill=MUTE, font=MONO)]
    mx = 3.0  # label the memory roof along its slope
    out.append(f'<text transform="translate({X(mx):.1f},{Y(bw * mx / 1e9) - 10:.1f}) rotate(-45)" '
               f'font-family="{DISP}" font-size="13" fill="{INK}">Memory roof {bw / 1e9:.0f} GB/s × AI (datasheet)</text>')
    # points
    for r in rows[1:]:
        out.append(dot(X(ai), Y(r["flops_per_s"] / 1e9), "hypothetical", 6))
    out.append(dot(X(ai), Y(base["flops_per_s"] / 1e9), "measured", 7))
    ax, ay = X(ai) + 60, Y(base["flops_per_s"] / 1e9) - 30
    out += [line(X(ai) + 9, Y(base["flops_per_s"] / 1e9), ax - 6, ay - 5, MUTE, 1),
            txt(ax, ay, cfg["title"], 15, w=700),
            txt(ax, ay + 21, cfg["subtitle"], 13, fill=MUTE),
            txt(ax, ay + 44, f"{base['tok_s']:.1f} tok/s  (measured p50)", 13, font=MONO),
            txt(ax, ay + 63, f"≈ {base['flops_per_s'] / 1e9:.0f} GFLOP/s  (derived, 2N × tok/s)", 13, font=MONO),
            txt(ax, ay + 82, f"≈ {ai:.2f} FLOP/B  (derived, weight-traffic model)", 13, font=MONO),
            txt(ax, ay + 101, f"ridge ≈ {ridge:.0f} FLOP/B (~{float(f'{ridge / ai:.2g}'):.0f}× to the right)", 13, font=MONO)]

    # ---- right panel: linear zoom at AI ≈ 1
    L2, R2, T2, B2 = 990, 1390, 170, 640
    roof_g = v["memory_roof_at_ai"]["value"] / 1e9
    ymax = 350
    Y2 = lambda g: B2 - g / ymax * (B2 - T2)
    out += [txt(L2 - 10, 140, f"Zoom at AI ≈ {ai:.0f} FLOP/B (linear)", 16, w=700)]
    for g in range(0, ymax + 1, 50):
        out += [line(L2, Y2(g), R2, Y2(g), RULE, 1),
                txt(L2 - 10, Y2(g) + 5, f"{g}", 13, fill=MUTE, font=MONO, anchor="end")]
    out += [line(L2, Y2(roof_g), R2, Y2(roof_g), INK, 2.5),
            txt(L2 + 6, Y2(roof_g) - 9, f"memory roof here ≈ {roof_g:.0f} GFLOP/s", 13),
            txt(L2 + 6, Y2(roof_g) + 19, f"= {v['bw_bound_tok_s_ceiling']['value']:.1f} tok/s ceiling at batch 1", 13,
                fill=MUTE)]
    step = (R2 - L2) / len(rows)
    for i, r in enumerate(rows):
        cx, g = L2 + step * (i + 0.5), r["flops_per_s"] / 1e9
        out += [line(cx, B2, cx, Y2(g), RULE, 2), dot(cx, Y2(g), r["kind"], 8),
                txt(cx, Y2(g) - 16, f"{g:.0f}", 13, font=MONO, anchor="middle",
                    fill=INK if r["kind"] == "measured" else HYPO),
                txt(cx, B2 + 24, f"{r['tok_s']:.1f}" if r["kind"] == "measured" else f"{r['tok_s']:.0f}", 14,
                    font=MONO, anchor="middle"),
                txt(cx, B2 + 44, r["kind"], 12, fill=MUTE, anchor="middle")]
        if r["above_memory_roof"]:
            out.append(txt(cx, Y2(g) - 34, "above roof", 12, fill=HYPO, anchor="middle"))
    out.append(txt((L2 + R2) / 2, B2 + 72, "output tok/s (x) · model GFLOP/s = 2N × tok/s (y)", 14, fill=MUTE, anchor="middle"))

    # ---- legend + footer
    ly = H - 82
    out += [dot(116, ly - 5, "measured"), txt(132, ly, "measured throughput (committed run)", 14),
            dot(436, ly - 5, "hypothetical", 7), txt(452, ly, "hypothetical throughput — not a result", 14),
            line(790, ly - 5, 830, ly - 5, INK, 2.5), txt(840, ly, "roofs — L4 datasheet, not measured", 14),
            line(56, H - 52, W - 56, H - 52, RULE),
            txt(56, H - 26, f"Charon · source: {cfg['result_file']} · generated by benchmarks/roofline.py · "
                "AI and bytes/token use a weight-traffic-only model (under-counts bytes); not Nsight data",
                12.5, fill=FAINT, font=MONO),
            "</svg>"]
    return "\n".join(out)


# ---------------------------------------------------------------- tables
def tables(v, rows, rate):
    def f(name, scale=1, digits=1, suffix=""):
        return f"{v[name]['value'] * scale:,.{digits}f}{suffix}"

    out = ["| Quantity | Value | Kind | Basis |", "|---|---|---|---|"]
    show = [("decode_tokens_per_s", 1, 2, " tok/s"), ("tpot_s", 1e3, 1, " ms"), ("ttft_s", 1e3, 1, " ms"),
            ("e2e_s", 1, 3, " s"), ("gpu_util_pct", 1, 0, " %"), ("weights_vram_bytes", 1e-9, 3, " GB"),
            ("vram_used_mb_max", 1e-3, 3, " GB"), ("peak_bf16_flops", 1e-12, 0, " TFLOP/s"),
            ("memory_bandwidth", 1e-9, 0, " GB/s"), ("parameters", 1e-9, 2, " B"),
            ("flops_per_token", 1e-9, 2, " GFLOP"), ("bytes_per_token", 1e-9, 3, " GB"),
            ("arithmetic_intensity", 1, 3, " FLOP/B"), ("ridge_point", 1, 1, " FLOP/B"),
            ("model_flops_per_s", 1e-9, 1, " GFLOP/s"), ("mfu", 100, 3, " %"),
            ("weight_traffic_rate", 1e-9, 1, " GB/s"), ("memory_roof_at_ai", 1e-9, 1, " GFLOP/s"),
            ("fraction_of_roof", 100, 1, " %"), ("bw_bound_tok_s_ceiling", 1, 1, " tok/s")]
    for name, s, d, u in show:
        out.append(f"| `{name}` | {f(name, s, d, u)} | {v[name]['kind']} | {v[name]['basis']} |")
    out += ["", f"| Throughput (tok/s) | Kind | Model GFLOP/s | Above memory roof at AI≈1? | ₹ / 1M output tokens @ ₹{rate}/h |",
            "|---|---|---|---|---|"]
    for r in rows:
        out.append(f"| {r['tok_s']:.1f} | {r['kind']} | {r['flops_per_s'] / 1e9:.1f} | "
                   f"{'yes' if r['above_memory_roof'] else 'no'} | ₹{r['inr_per_1m']:.2f} |")
    return "\n".join(out)


def main(argv):
    cfg_path = pathlib.Path(argv[1]) if len(argv) > 1 else DEFAULT_CONFIG
    cfg, measured = load(cfg_path)
    v, rows = compute(cfg, measured)
    svg_path = ROOT / cfg["output_svg"]
    svg_path.write_text(render_svg(cfg, v, rows) + "\n")
    print(f"wrote {svg_path.relative_to(ROOT)}\n")
    print(tables(v, rows, cfg["assumptions"]["gpu_cost_inr_per_hour"]["value"]))


if __name__ == "__main__":
    main(sys.argv)
