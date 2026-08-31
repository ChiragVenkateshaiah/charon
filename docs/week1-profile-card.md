# Week 1 — profiling card

A condensed profiling digest of the Week 1 naive baseline. Every value is either
read from the committed run or explicitly labelled as datasheet / derived / not
measured.

- **Source run:** [`benchmarks/results/baseline-20260828T172338Z.json`](../benchmarks/results/baseline-20260828T172338Z.json)
  (3 runs × 100 measured requests, 360 total; GPU telemetry = the 5,563
  `nvidia-smi` samples that fell inside a request window).
- **Full writeup:** [`benchmarks/results/2026-08-28-week1-baseline.md`](../benchmarks/results/2026-08-28-week1-baseline.md)
- **Not a result in itself** (ADR-0001): this file only re-tabulates the run
  above. It produces no new number.

## Configuration

| Field | Value | Source |
|---|---|---|
| Model | `Qwen/Qwen2.5-1.5B-Instruct` @ `989aa7980e4cf806f80c7fef2b1adb7bc71aa306` (1.54B params) | measured (`/healthz`) |
| GPU | NVIDIA L4 — Ada, compute capability 8.9, 23,034 MiB (≈22.5 GiB) | measured (`/healthz`, `nvidia-smi`) |
| CUDA version | PyTorch CUDA build **13.0** (cu130 wheels); NVIDIA driver **580.173.02**; DLVM `common-cu129-ubuntu-2204` | measured (`/healthz`) / recorded by hand (driver, image) |
| PyTorch version | **2.13.0+cu130** (transformers 5.16.1, accelerate 1.14.0) | measured (`/healthz`) |
| Precision | **bfloat16** (`torch.bfloat16`), no quantization | measured (`/healthz`) |
| Prompt length | **41–49 tokens** across the 8-prompt set (recorded per request; provisional set, Week 2 fixes it exactly) | measured |
| Output length | **128 tokens**, forced (`min_new_tokens == max_new_tokens`) | measured (config + `output_tokens_seen == [128]`) |
| Batch size | **1** (concurrency 1, one request at a time behind a global lock) | by construction |
| Host | GCP `g2-standard-4` — 4 vCPU, 16 GB RAM, **spot**, `us-central1-c` | recorded by hand |

## Latency & throughput

| Metric | p50 | p95 | p99 | cross-run spread (p50) | Source |
|---|---|---|---|---|---|
| Time to first token (TTFT) | **32.1 ms** | 33.8 ms | 35.0 ms | 1.2% | measured |
| Time per output token (TPOT) | **29.0 ms** | 29.6 ms | 30.0 ms | 1.1% | measured (per-request mean ITL, then percentiled) |
| Tokens/sec (decode phase, batch 1) | **34.50** | 35.30 | 35.54 | 1.1% | measured |
| Request latency (end-to-end, 128 output tok) | **3.713 s** | 3.788 s | 3.838 s | 1.1% | measured |

*TTFT p99 spread across the 3 runs was **18%** (run 1: 41.1 ms vs 35.0 / 34.8 ms)
— one unexplained slow tail; the runner only gates on p50 spread. Client-side
HTTP overhead (localhost) was ~3 ms p50, so server-reported timings are
effectively the whole story.*

## GPU telemetry (`nvidia-smi`, samples inside a request window)

| Metric | p50 | p95 | p99 | max | idle (before load) | Source |
|---|---|---|---|---|---|---|
| GPU utilization (busy-time %) | **53%** | 54% | 54% | 55% | 0% | measured |
| GPU memory utilization (`utilization.memory`, bus-active %) | **51%** | 53% | 53% | 54% | 0% | measured |
| VRAM used (`memory.used`) | **3.244 GB** of 23.0 GB → ~14% occupied, **~86% idle** | — | — | 3.244 GB | ~3.19 GB | measured |
| Power draw | **59.8 W** | 61.1 W | 61.6 W | 62.6 W | ~29 W | measured (power limit 72 W — never hit) |
| SM clock | **2040 MHz** | 2040 | 2040 | 2040 | 2040 MHz | measured (pinned at max the entire run → **no throttling**) |
| Temperature | **76 °C** | 79 °C | 79 °C | 80 °C | 56 °C | measured (well under the ~90 °C throttle point) |
| CPU utilization | **not measured** — the runner does not sample host CPU | — | — | — | — | Week 2 follow-up candidate |
| Memory bandwidth | **not directly measurable** with this harness | — | — | — | — | see below |

## Memory bandwidth — what can and can't be said

| Quantity | Value | Status |
|---|---|---|
| L4 peak memory bandwidth | ~300 GB/s | **datasheet, not measured** |
| Effective bandwidth *used* by decode | 34.5 tok/s × 3.087 GB/token ≈ **~106 GB/s** of weight traffic | **derived** — a lower bound on bytes actually moved, not a measured bus figure |
| Fraction of datasheet bandwidth | ~106 / 300 ≈ **~36%** | **derived** |

There is no counter in this run that reports achieved GB/s. `utilization.memory`
(51%) is the fraction of time the memory *interface* was active — a busy-time
metric, not a throughput metric. A real achieved-bandwidth number needs Nsight
Compute (Phase 2).

## Derived reference numbers (not measured — hypotheses / datasheet math)

| Quantity | Value | Basis |
|---|---|---|
| Weights in VRAM | 3.087 GB (`weights_vram_bytes` at load) | measured |
| Peak VRAM (PyTorch tensors) | 3.106 GB (`torch.cuda.max_memory_allocated`, **bit-identical across all 3 runs**) | measured |
| Bandwidth-bound decode ceiling | ~97 tok/s | 300 GB/s ÷ 3.087 GB — **datasheet-derived** |
| Bandwidth-bound TPOT floor | ~10.3 ms/token | 3.087 GB ÷ 300 GB/s — **datasheet-derived** |
| Unaccounted TPOT (overhead) | ~18.7 ms/token (~64%) | 29.0 − 10.3 — **derived** |
| Model-FLOPs utilization (MFU) | **~0.09%** | 2 × 1.54e9 × 34.5 tok/s ÷ 121 TFLOPS (datasheet bf16) — **order-of-magnitude estimate** |

## The one-line reading

`nvidia-smi` says the GPU is busy ~53% of the time; measured throughput is ~36%
of the datasheet bandwidth ceiling; the tensor cores are delivering ~0.09% of
their arithmetic. At batch 1 this server is launch-overhead-bound — it never
reaches the regime where decode becomes memory-bandwidth-bound, let alone
compute-bound. That gap is the motivation for the Week 2 sweep and Week 3
batching.
