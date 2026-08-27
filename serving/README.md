# serving/

Serving implementations, one per approach. Each is a deliberate step on the
Phase 1 path (`docs/phase-1-plan.md`), kept so later weeks can be compared
against earlier ones. New approaches get new files — the earlier files are not
edited to keep up.

## `naive_server.py` — Week 1 baseline

Plain `transformers` `model.generate`, one request at a time (global lock), no
batching, no optimization, no compilation. The deliberately-worst reasonable
implementation. Serves `Qwen/Qwen2.5-1.5B-Instruct` at the revision pinned in
`docs/worklog.md` (env-overridable via `CHARON_MODEL_ID` / `CHARON_MODEL_REVISION`
for the Week 6 scale-up).

### Run it

First time: `uv sync --group serving` (pulls torch + transformers, ~2 GB).

```
uv run python -m uvicorn serving.naive_server:app --port 8000
```

Locally this is a **correctness smoke test only** — CPU, slow, one request. All
measurement runs happen on the GCP `g2-standard-4` spot instance (CLAUDE.md).

```
curl -s localhost:8000/healthz | jq
curl -s localhost:8000/generate -H 'content-type: application/json' \
  -d '{"prompt": "Explain a hash join in two sentences.", "max_tokens": 64}' | jq
```

Smoke-test checklist:

- `/healthz` reports `model_revision` matching the pinned SHA, plus the actual
  `torch` / `transformers` versions and `cuda_available` (methodology rule 5 —
  recorded environment).
- `output_tokens` in the `/generate` response equals `max_tokens` exactly.
- `ttft_s`, `tpot_s`, `e2e_s`, `decode_tokens_per_s` are populated and plausible.
- `len(itl_s) == output_tokens - 1`.

On the L4, `/healthz` `device` reads `cuda:0` and responses carry
`peak_vram_bytes`.

### What it measures

Per request: `ttft_s`, `tpot_s` (mean inter-token latency), `e2e_s`,
`decode_tokens_per_s`, the full inter-token latency list `itl_s`, and
`peak_vram_bytes`. Output length is forced (`min_new_tokens == max_new_tokens`),
so runs are comparable — methodology rule 1. Decoding is greedy
(`do_sample=False`) for reproducibility.

**GPU utilization is not reported by the server** — sample it with `nvidia-smi`
alongside the run. The Week 2 load generator will own utilization sampling and
percentile aggregation.

### What it deliberately does not do

No batching, no continuous batching, no paged attention beyond the framework
default, no quantization, no `torch.compile`. Those are Weeks 3–5, in their own
files.
