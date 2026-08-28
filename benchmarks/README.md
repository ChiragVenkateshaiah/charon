# benchmarks/

Measurement lives here. Per [ADR-0001](../adr/0001-measurement-discipline.md) a
number counts only if it was produced on real hardware by a reproducible run
whose raw output is committed under `results/`. Harness code is not a result.

- `methodology.md` — the seven rules. Stub until Week 2 finalizes the load
  generator, canonical prompt set, and fixed token counts.
- `prompts/baseline.json` — provisional Week 1 prompt set (see the file's `note`).
- `baseline_runner.py` — the concurrency-1 runner (Week 1 only).
- `results/` — committed raw output from real GPU runs. Nothing else goes here.

## `baseline_runner.py` — Week 1 concurrency-1 baseline

Drives a running `serving/naive_server.py` at concurrency 1 and produces the
baseline row of the benchmark table. Stdlib only; it does not launch the server.

**This is not the Week 2 load generator.** No concurrency model — one request at
a time, deliberately. Week 2 replaces the aggregation and adds the sweep.

### Run it

Local (correctness check of the script — CPU, not a result, do not commit output):

```
uv run python -m uvicorn serving.naive_server:app --port 8000   # shell 1
python benchmarks/baseline_runner.py --warmup 2 --requests 5 --runs 1   # shell 2
```

On the GCP L4, inside a measurement session (see `scripts/session-start.sh`):

```
python benchmarks/baseline_runner.py       # defaults match the methodology
```

Defaults: 3 runs × (20 warmup + 100 measured) requests, 128 forced output
tokens, `nvidia-smi` sampled every 200 ms. Output written to
`results/baseline-<timestamp>.json`.

### How it maps to the seven rules

| Rule | In the runner |
|------|---------------|
| 1 fixed I/O tokens | `min_tokens == max_tokens == --output-tokens`; `prompt_tokens` recorded per request, wide spread flagged |
| 2 discard warmup | first `--warmup` requests per run excluded from aggregation, kept in `raw` |
| 3 percentiles | p50/p95/p99 (nearest-rank) on ttft/tpot/e2e/decode-tok-per-s |
| 4 ≥3 runs + spread | `--runs` (default 3); p50 spread across runs flagged above `--spread-threshold` (default 10%) |
| 5 record environment | `/healthz` (GPU, driver, CUDA, torch/transformers, model revision) embedded verbatim |
| 6 one variable | the runner changes nothing between runs — the operator changes one thing between invocations |
| 7 commit raw output | every request record and every GPU sample kept under `raw` |

GPU utilization is sampled from `nvidia-smi` and reported over the samples that
fall inside a measured request window (`samples_in_flight`). No GPU / no
`nvidia-smi` is not an error — those fields come out null with a warning.

### Output schema — `charon-baseline-v1`

Provisional, versioned by the `schema` field. Top-level keys:

- `config` — every knob the run used.
- `environment.healthz` — the recorded environment (rule 5).
- `summary.per_run[]` — per-run percentiles, `prompt_tokens` range,
  `output_tokens_seen`, `peak_vram_bytes`, client-overhead p50.
- `summary.across_runs` — for each metric/percentile: `median`, `spread`,
  `per_run` values (rule 4).
- `summary.gpu` — `status`, sample counts, in-flight utilization percentiles,
  `mem_used_mb_max`.
- `warnings` — methodology-rule violations detected in this run.
- `raw.requests[]` / `raw.gpu_samples[]` — everything, unaggregated (rule 7).

Percentiles are nearest-rank and crude at small N; p95 and p99 coincide below
~100 samples. Use the default request count for a real run.
