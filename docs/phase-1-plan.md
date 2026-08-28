# Phase 1 — Inference Mechanics

**Duration:** 8 weeks
**Location:** local CPU primarily; GCP spot GPU only for measurements that need one
**Exit condition:** a committed benchmark table covering at least six serving
configurations, with methodology notes good enough that someone else could reproduce it

The goal of this phase is **not** to build a platform. It is to develop physical
intuition for what happens between a request arriving and a token coming back, and to
learn to measure it honestly. Everything in Phase 3 depends on this being real.

---

## Before Week 1 — hardware decision

Phase 1 needs a GPU with at least 12 GB VRAM to be comfortable; 8 GB works for the
small-model weeks with quantization.

| Situation | Approach |
|-----------|----------|
| Local GPU ≥ 16 GB | Everything local except Week 6 |
| Local GPU 8–12 GB | Weeks 1–5 local at small model size; Week 6 on `g2-standard-4` spot |
| No local GPU | All weeks on `g2-standard-4` spot, batched into 3–4 hour sessions |

Charon's actual situation is the last row: no local GPU. All development, debugging,
and analysis happens locally on CPU; the GPU is a GCP `g2-standard-4` (1× NVIDIA L4,
24 GB VRAM) spot instance, powered on only for the duration of a measurement. See the
Constraints section of the root `README.md` and `CLAUDE.md` for the budget this
enforces.

Spot only, billing budget alarm configured, teardown script wired before the
first launch (see `scripts/session-start.sh` and `scripts/session-end.sh`).
Sessions are booked and closed the same day. A GPU instance left running
overnight is the most expensive mistake available in this phase.

**Laptop caveat:** if using a laptop GPU, thermal throttling will corrupt long
benchmark runs. Check clocks with `nvidia-smi dmon` during a run; if they sag, shorten
runs and increase repetitions.

---

## Vocabulary to fix before measuring anything

These four are separate and get conflated constantly. Confusing them makes every number
you produce meaningless.

- **TTFT** — time to first token. Dominated by the *prefill* phase, which is
  compute-bound and scales with input length.
- **TPOT / ITL** — time per output token, or inter-token latency. Dominated by the
  *decode* phase, which is memory-bandwidth-bound and scales with batch size and KV
  cache size.
- **End-to-end latency** — `TTFT + (TPOT × output_tokens)`. The number users feel.
- **Throughput** — requests/second *and* output tokens/second. These diverge; report
  both.

The single most important concept in this phase: **prefill and decode have opposite
performance characteristics.** Nearly every serving optimization exists to exploit that.

---

## Methodology rules — fix these in Week 2 and never change them

Bad numbers are worse than no numbers, because they survive into your README and then
collapse under interview questioning.

1. **Fixed input and output token counts.** Variable-length outputs make runs
   incomparable. Use a fixed prompt set and `min_tokens = max_tokens` so every request
   generates exactly N tokens.
2. **Discard warmup.** First requests include compilation, cache allocation, and CUDA
   context setup. Drop the first 30 seconds or first 20 requests.
3. **Report percentiles, never averages alone.** p50, p95, p99. Averages hide the
   behaviour that matters.
4. **Three runs minimum**, report median and spread. If spread exceeds ~10%, something is
   uncontrolled — find it before continuing.
5. **Record the environment every time:** GPU model, driver, CUDA version, framework
   versions, model revision hash, exact server flags.
6. **Change one variable per experiment.** Tempting to bundle; don't.
7. **Commit raw output**, not just the summary table.

---

## Week 1 — Naive baseline

**Build.** One small model (1–3B parameters, an open-weights instruct model) served with
plain `transformers` behind a minimal FastAPI endpoint. No batching, no optimization,
one request at a time. Deliberately the worst reasonable implementation.

**Measure.** At concurrency 1: TTFT, TPOT, end-to-end latency, output tokens/sec, GPU
utilization, VRAM used.

**Expect.** GPU utilization somewhere around 10–30%. This is the phase's first real
lesson: a naive server leaves most of the hardware idle, because decode is
memory-bandwidth-bound and a batch size of one wastes nearly all available compute.

**Number produced:** baseline row of the benchmark table.

**Exit:** you can explain, without notes, why a single-stream LLM server underutilizes a
GPU.

---

## Week 2 — Load generation and the latency/throughput curve

**Build.** A proper load generator — or adopt one and understand its concurrency model.
It must support fixed concurrency levels, fixed token counts, warmup discard, and
percentile reporting. Write `benchmarks/methodology.md` this week.

**Measure.** Concurrency sweep: 1, 2, 4, 8, 16, 32, 64 against the Week 1 server.

**Expect.** Throughput rises then plateaus; p99 latency rises gently then explodes. The
inflection is the saturation point. Past it, you are queueing, not serving.

**Number produced:** throughput-vs-concurrency curve, and the identified knee.

**Exit:** you can state your server's saturation concurrency and what limits it.

---

## Week 3 — Batching

**Build.** Two comparisons against the Week 1 baseline:
1. Naive static batching — collect requests for a fixed window, run as one batch.
2. A continuous-batching server (vLLM or TGI) with the same model.

**Measure.** Full concurrency sweep for each. Same fixed token counts as Week 2.

**Expect.** A large throughput multiple, and — counterintuitively — often *better* p99
under load than static batching, because continuous batching doesn't make short requests
wait for long ones to finish. GPU utilization climbs substantially.

**Investigate.** Read what continuous batching actually does at the scheduler level.
Static batching wastes the tail of every batch; continuous batching evicts and admits
sequences per decode step. This distinction is a standard interview question.

**Number produced:** three-way comparison — naive / static batch / continuous batch —
across the concurrency sweep.

**Exit:** you can explain continuous batching to someone who has never heard of it, and
you have measured its cost in p99 as well as its benefit in throughput.

---

## Week 4 — Memory and the KV cache

**Build.** No new server. Instrumentation and deliberate breakage.

**Measure.**
- Memory budget breakdown: weights vs KV cache vs activations vs framework overhead.
- Sweep context length (512 / 2k / 8k / 32k) at fixed concurrency; watch KV cache grow.
- Push concurrency until OOM at each context length. Record the ceiling.
- Compare KV cache memory with and without paged attention.

**Expect.** KV cache overtakes weights as the dominant memory consumer surprisingly
early. Max concurrency is a function of context length, not a fixed property of the
server.

**Number produced:** max concurrent sequences by context length; memory breakdown table.

**Exit:** you can compute, on paper, roughly how much KV cache a given model, batch
size, and context length requires — and explain why that determines your instance sizing.

---

## Week 5 — Quantization

**Build.** The same model at FP16 baseline, then INT8/FP8, then 4-bit (AWQ or GPTQ).

**Measure.** For each precision: throughput, TTFT, TPOT, VRAM, max concurrency at fixed
context length. Plus a **quality smoke check** — a fixed set of ~50 prompts, outputs
diffed against the FP16 baseline, judged manually or by a simple metric. Not a rigorous
eval; just enough to catch a variant that has visibly degraded.

**Expect.** 4-bit gives large memory savings and enables far higher concurrency, but the
per-token speedup is smaller than advertised at low batch sizes, and quality
degradation is real but often acceptable. Quantization is a memory optimization first, a
speed optimization second.

**Number produced:** precision comparison table including the quality column.

**Exit:** you can articulate the quantization tradeoff in terms of cost per token rather
than "it's faster".

---

## Week 6 — Larger model, real memory pressure

**Build.** Move to a 7–8B model. Likely the first week requiring the GCP spot instance
if local VRAM is limited.

**Measure.** Repeat the Week 3–5 experiments at the new size.

**Expect.** Constraints bind differently. What was compute-limited becomes
memory-limited. Configurations that worked at 1B fall over. Quantization stops being
optional.

**Number produced:** the same tables at a second model scale, with an explicit note on
what changed and why.

**Exit:** you can explain which bottlenecks are model-size-dependent and which aren't —
the difference between someone who ran a benchmark and someone who understands one.

---

## Week 7 — Cost model

**Build.** No new serving work. A script that converts benchmark output into money.

**Measure.** Cost per 1M output tokens for every configuration measured so far, on:
`g2-standard-4` on-demand, `g2-standard-4` spot, and one larger GCP instance for
comparison. Include idle cost — a GPU at 20% utilization is paid for at 100%.

**Expect.** The ranking by cost differs from the ranking by latency. This is the tension
the whole platform exists to manage, and it's the framing that reads as senior.

**Number produced:** cost-per-1M-tokens column added to every row of the master table.

**Exit:** you can answer "how would you cut our inference cost 40%?" with a specific
answer and the measurement that supports it.

---

## Week 8 — Consolidate

No new experiments. Produce:

- `benchmarks/results/` — the master table, all configurations, all metrics
- `benchmarks/methodology.md` — finalized
- **ADR-0002** — project scope and non-goals
- **ADR-0003** — serving stack selection, with the Week 3 evidence in the Measured
  Evidence section
- **ADR-0004** — default precision, with the Week 5 evidence
- A short written narrative: what surprised you, what you got wrong, what you'd measure
  next

That narrative is the most valuable artifact in the phase. It is the thing that becomes
your interview answer.

---

## Drift checkpoints

Per ADR-0001, a number must land every month. In this phase the cadence is weekly:

- **End of Week 2** — if no concurrency curve exists, stop and produce one.
- **End of Week 4** — if the master table has fewer than four configurations, stop and
  measure.
- **End of Week 6** — if the second model scale hasn't been run, cut Week 7 rather than
  skipping it.

The failure mode to watch for: spending Week 3 reading about batching strategies instead
of measuring two of them. The reading is only useful attached to a number you produced.

---

## What Phase 1 deliberately excludes

- Kubernetes. Everything here is local or single-instance.
- Terraform. Phase 3.
- Autoscaling, rollout, canaries, monitoring stack. Phase 3.
- Compilation (`torch.compile`, TensorRT). Phase 2 — with one exception: note in Week 3
  whether your serving framework is already compiling under the hood, since that changes
  what Phase 2's baseline means.
- Any model training or fine-tuning. Permanently out of scope.
