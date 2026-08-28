# nvidia-smi said my GPU was 53% utilized. Its tensor cores were doing about 0.09% of their work.

*Newsletter #1 — Charon, week 1*

---

I put a small language model behind the simplest possible server and measured it on a rented NVIDIA L4.

`nvidia-smi` reported **53% GPU utilization.** That's measured.

The tensor cores were delivering about **0.09%** of the arithmetic the datasheet says they can — derived, not measured, but the order of magnitude is solid.

Both numbers are correct. The gap between them is the reason this project exists.

---

**[IMAGE: 01-two-measurements.png]**

---

## What I actually built

Week 1 of an eight-week project to learn — by measuring, not reading — what happens between an inference request arriving and a token coming back.

The server is the *worst reasonable implementation*, on purpose:

- Plain Hugging Face `transformers.generate`
- One request at a time, behind a lock
- A minimal FastAPI endpoint
- No batching, no compilation, no quantization

Model: `Qwen2.5-1.5B-Instruct`, pinned by commit hash, bf16. Stack: torch 2.13.0, transformers 5.16.1, locked in a `uv` lockfile. Hardware: a GCP `g2-standard-4` spot instance with one L4, created and deleted per session, ~₹42/hour (GCP list price, checked 2026-08-28), GPU on only while a measurement runs.

Why build something bad on purpose? **You can't measure what an optimization buys you without a number for life without it.** This is that number.

## The result

Naive server, concurrency 1, 128-token replies, 3 runs × 100 measured requests:

| | p50 | p99 |
|---|---|---|
| Time to first token | 32.1 ms | 35.0 ms |
| Inter-token latency | 29.0 ms | 30.0 ms |
| End-to-end (128 tokens) | 3.71 s | 3.84 s |
| Decode throughput | 34.5 tok/s | 35.5 tok/s |
| GPU utilization (nvidia-smi) | 53% | 54% |
| Peak VRAM | ~3.2 GiB of 22.5 | |

p50 spread across runs was ~1%. Honesty note: TTFT *p99* spread was 18% — one run had a slow first-token tail I haven't explained, and my harness only gates on p50 spread. A week-2 fix.

## The one thing worth carrying from this

**`nvidia-smi` "utilization" is not compute utilization.**

It's a busy-time percentage — the fraction of wall-clock during which *some* kernel was running. It tells you nothing about whether that kernel used the hardware.

The number that matters is model-FLOPs utilization: work delivered ÷ hardware peak. Here that's roughly **0.09%** — 2N FLOPs per token against the L4's datasheet ~121 dense bf16 TFLOPS.

So: the GPU is "busy" half the time and delivering a thousandth of its compute. A batch of one is not a compute workload. The tensor cores that make an L4 worth renting sit idle because decode never assembles a batch big enough to keep them fed.

That is the entire economic case for batching — and now I have the baseline that proves I need it.

**[IMAGE: 03-token-budget.png]**

Each token takes 29 ms (measured). About 10 of those are the bandwidth-bound floor — streaming ~3.09 GB of weights out of memory, once per token, against the L4's datasheet ~300 GB/s. The other ~19 ms is time that floor doesn't account for: hundreds of tiny kernel launches, the Python loop, CPU–GPU sync. Attributing it precisely needs a profiler — that's a later phase.

**[IMAGE: 02-utilization-timeline.png]**

Three runs, back to back, 6,683 samples. The meter never leaves ~53% — and that number still says nothing about the tensor cores.

## What's next

**[IMAGE: 04-the-arc.png]**

- **Week 2:** concurrency sweep, 1 → 64 — find where throughput plateaus and p99 explodes
- **Week 3:** add continuous batching — I *expect* a large multiple and better tail latency under load. That's a hypothesis until it's a measured number.
- **The open question I can't answer yet:** on this model, at what context length does the KV cache overtake the weights? That's week 4, and it decides how many concurrent users an instance can hold.

Every future number stays labelled as a hypothesis until it's measured on real hardware. That's the project's first rule.

---

The repo — pinned deps, committed raw output, the full methodology, and the script that drew these charts — is at **github.com/ChiragVenkateshaiah/charon**.

If you want the whole arc, one measured result a week, subscribe.

*This is the slowest it will ever be.*
