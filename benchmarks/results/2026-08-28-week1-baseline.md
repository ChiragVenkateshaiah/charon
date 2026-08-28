# Week 1 — naive baseline, concurrency 1

**Raw data:** [`baseline-20260828T172338Z.json`](baseline-20260828T172338Z.json)
(3 runs × (20 warmup + 100 measured), 128 forced output tokens; 360 request
records + 6683 `nvidia-smi` samples committed in full).

## Environment

| | |
|---|---|
| Server | `serving/naive_server.py` — plain `transformers.generate`, one request at a time behind a global lock, greedy, no batching / compilation / quantization |
| Model | `Qwen/Qwen2.5-1.5B-Instruct` @ `989aa7980e4cf806f80c7fef2b1adb7bc71aa306`, bf16 |
| GPU | NVIDIA L4 (Ada, compute capability 8.9), 23034 MiB, driver 580.173.02, CUDA-13 runtime (torch cu130) |
| L4 datasheet (not measured here) | ~300 GB/s memory bandwidth; ~121 TFLOPS dense bf16 tensor-core (2× with sparsity); 72 W; PCIe Gen4 ×16 |
| L4 runtime config (from `nvidia-smi` on the instance) | power limit 72 W, max SM clock 2040 MHz, max mem clock 6251 MHz, PCIe reported Gen3 ×16 at idle |
| Stack | torch 2.13.0+cu130, transformers 5.16.1, fastapi/uvicorn |
| Host | GCP `g2-standard-4` (4 vCPU, 16 GB), **spot**, `us-central1-c` |
| Runner | `benchmarks/baseline_runner.py`, defaults, `nvidia-smi` sampled at 200 ms |
| Prompt set | `benchmarks/prompts/baseline.json` (provisional; input length 41–49 tokens across the set) |

## Measured

| Metric | p50 | p95 | p99 | cross-run spread (p50) |
|---|---|---|---|---|
| TTFT | 32.1 ms | 33.8 ms | 35.0 ms | 1.2% |
| TPOT (inter-token latency) | 29.0 ms | 29.6 ms | 30.0 ms | 1.1% |
| End-to-end (128 tok) | 3.713 s | 3.788 s | 3.838 s | 1.1% |
| Decode throughput | 34.50 tok/s | 35.30 | 35.54 | 1.1% |
| GPU utilization (`nvidia-smi`, in-flight windows) | 53% | 54% | 54% (max 55%) | — |
| Peak VRAM | 3.106 GB (`torch.cuda.max_memory_allocated`) / 3.244 GB (`nvidia-smi mem.used`) | | | |

Cross-run spread is ~1%, far under the 10% methodology threshold — the setup is
controlled. Client-side HTTP overhead (localhost) was ~3 ms p50, so the
server-reported timings above are effectively the whole story.

## Analysis

### 1. Decode is memory-bandwidth-bound, and we reach ~36% of that bound

Every decode step streams the full weight tensor through the GPU once. With
**3.106 GB of bf16 weights** (measured) and the L4's **~300 GB/s** bandwidth
(datasheet), the memory-bound ceiling is:

    300 GB/s ÷ 3.106 GB ≈ 96 tok/s          (estimate, from datasheet bandwidth)

Measured decode: **34.5 tok/s ≈ 36% of that ceiling.** Equivalently, TPOT is
29.0 ms/token against a memory-transfer floor of ~10.4 ms — so **~18.6 ms/token
(~64%) is not memory transfer.** In eager-mode `transformers.generate` at batch 1
that time goes to: hundreds of small unfused kernel launches per token, the
Python generation loop, the per-step `LogitsProcessor` callback (our own timing
hook — a few hundred µs/token, and part of the measured cost by design),
sampling/argmax, cache bookkeeping, and CPU↔GPU sync points between steps.

### 2. "GPU utilization 53%" — and why that is not a contradiction of ~0% useful work

`docs/phase-1-plan.md` predicted 10–30% GPU utilization. We measured **53%**.
The prediction and the number are measuring different things:

- `nvidia-smi` "GPU utilization" is defined as *the fraction of the sample window
  during which at least one kernel was executing* — a busy-time percentage. 53%
  means roughly half of each request's wall-clock had a kernel running and half
  was idle (Python, launch latency, sync).
- It says nothing about **how much of the GPU's parallel capacity** those kernels
  used. Model FLOPs at batch 1 ≈ 2 × 1.5e9 ≈ 3 GFLOP/token; at 34.5 tok/s that is
  ~0.1 TFLOP/s delivered against ~121 TFLOPS dense bf16 peak — **model FLOPs
  utilization on the order of 0.01–0.1%.**

So both are true: the GPU is "busy" ~53% of the time and doing **~0.01–0.1%** of
the math it is capable of. The Week 1 lesson stands and is sharper than the
prediction implied — at batch 1 the L4's tensor cores are essentially idle,
because decode never assembles a batch large enough to make the matmuls
compute-bound. That is the entire motivation for Week 3's batching.

### 3. Memory headroom

3.24 GB used of 22.5 GB — **~85% of VRAM sits idle** at concurrency 1 with a
128-token context. That headroom is what batching and a larger KV cache will
consume (Weeks 3–4).

## What this does not tell us

- **TTFT scaling.** 32 ms is prefill for a ~45-token prompt only. TTFT grows with
  input length (prefill is compute-bound); this is a floor, not a curve.
- **Saturation behaviour.** Concurrency 1 only. The throughput/latency knee is
  Week 2.
- **The incident-000 CPU comparison.** incident-000's ~20–30 min CPU reply is
  still unquantified against a controlled CPU baseline — that needs a deliberate
  CPU run (different exercise from this GPU row).
- **`nvidia-smi` GPU utilization is a coarse proxy.** A real occupancy / MFU
  number needs Nsight or the PyTorch profiler — that is Phase 2 tooling.

## Methodology notes

- Seven rules followed; the runner emitted no warnings.
- Prompt-set input length varies 41–49 tokens (~19%). Under the runner's flag
  threshold, but the canonical Week 2 prompt set should fix input length exactly.
- `/healthz` does not record driver version or `nvidia-smi` detail — the
  Environment table above was filled by hand from the live instance. Follow-up:
  have the server or runner capture `nvidia-smi` fields automatically.
- Session ops: first run was aborted at run 3 / 90 by an over-tight SSH timeout
  on the client (the runner writes results only after all runs complete, so
  nothing was salvageable); re-run from a detached process succeeded. Measurement
  itself unaffected. GPU time this session ≈ 1.1 h (spot L4 stockout in
  `us-central1-a/-b` and `asia-south1-a` also cost wall-clock; landed in
  `us-central1-c`).
