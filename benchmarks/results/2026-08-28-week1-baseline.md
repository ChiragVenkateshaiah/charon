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
| Weights in VRAM | 3.087 GB (`weights_vram_bytes`, at load) | | | |
| Peak VRAM | 3.106 GB (`torch.cuda.max_memory_allocated`) / 3.244 GB (`nvidia-smi mem.used`) | | | |

**Spread:** p50 spread is ~1% on every metric — but this is the *p50* figure, and
the runner only gates on p50 (`baseline_runner.py`). TTFT p99 spread is **18%**:
run 1's TTFT p99 was 41.1 ms against 35.0 / 34.8 ms in runs 2–3 — one slow tail in
one run, unexplained, small in absolute terms. Every other metric's p95/p99 spread
is ≤ 3%. Gating on p99 spread too is a Week 2 harness fix.

**Determinism check:** `peak_vram_bytes` was **bit-identical (3105718272)** across
all three runs — exactly what greedy decoding at a forced length should produce,
and evidence the harness is deterministic. Client-side HTTP overhead (localhost)
was ~3 ms p50, so the server-reported timings are effectively the whole story.

## Analysis

### 1. Decode should be memory-bandwidth-bound — this server doesn't get close

Every decode step streams the full weight tensor through the GPU once. With
**3.087 GB of bf16 weights** (measured, `weights_vram_bytes`) and the L4's
**~300 GB/s** bandwidth (datasheet), the memory-bound ceiling is:

    300 GB/s ÷ 3.087 GB ≈ 97 tok/s          (estimate, from datasheet bandwidth)

Measured decode: **34.5 tok/s ≈ 36% of that ceiling.** TPOT is 29.0 ms/token
against a bandwidth-bound floor of ~10.3 ms — so **~18.7 ms/token (~64%) is time
the bandwidth bound does not account for.** At 36% of the memory ceiling with two
thirds of TPOT outside the transfer, this server is *launch-overhead-bound*, not
bandwidth-bound: decode only becomes memory-bound in a regime (fused kernels,
CUDA graphs, or a real batch) that this server never reaches.

Attributing the 18.7 ms precisely needs a profiler (Nsight / PyTorch profiler,
Phase 2). The plausible contributors: hundreds of small unfused kernel launches
per token, the Python generation loop, the per-step `LogitsProcessor` callback
(our own timing hook — a few hundred µs/token, part of the measured cost by
design), sampling/argmax, cache bookkeeping, and CPU↔GPU sync between steps.
The floor is also a *lower bound*, not a serial stage — transfer overlaps with
compute and launch latency rather than queueing behind them.

### 2. "GPU utilization 53%" and "~0.09% of the compute" are both true

`docs/phase-1-plan.md` predicted 10–30% GPU utilization. We measured **53%**.
The prediction and the number are measuring different things:

- `nvidia-smi` "GPU utilization" is defined as *the fraction of the sample window
  during which at least one kernel was executing* — a busy-time percentage. 53%
  means roughly half of each request's wall-clock had a kernel running and half
  was idle (Python, launch latency, sync).
- It says nothing about **how much of the GPU's parallel capacity** those kernels
  used. Forward FLOPs ≈ 2N per token (N = 1.54B params; the tied LM head is a real
  matmul, the input embedding is a gather); at 34.5 tok/s that is ~0.11 TFLOP/s
  delivered against ~121 TFLOPS dense bf16 peak (datasheet) — **model-FLOPs
  utilization ≈ 0.09%** (ignores attention, small at 128-token context).

So both are true: the GPU is "busy" ~53% of the time and delivering **~0.09%** of
the arithmetic it is capable of. The Week 1 lesson stands and is sharper than the
prediction implied — at batch 1 the L4's tensor cores are essentially idle,
because decode never assembles a batch large enough to make the matmuls
compute-bound. That is the entire motivation for Week 3's batching.

### 3. Memory headroom

3.24 GiB used of 22.5 GiB (`nvidia-smi mem.used`) — **~86% of VRAM sits idle** at
concurrency 1 with a 128-token context. That headroom is what batching and a
larger KV cache will consume (Weeks 3–4).

### 4. Two independent numbers bracket the same gap

The 53% busy-time (`nvidia-smi`) and the 36% of the bandwidth ceiling (measured
throughput vs datasheet) are derived from completely different measurements and
roughly agree on "the GPU is doing about a third to a half of *something*" — while
the FLOPs-utilization estimate says the *something* is nowhere near arithmetic.
The two coarse numbers corroborating each other is a small confidence signal that
the run is not an artifact.

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

- Seven rules followed; the runner emitted no warnings — but see the p99 spread
  note above: "no warnings" is partly because the runner only checks p50 spread.
- TPOT here is a *per-request mean* inter-token latency (`sum(itl_s)/len(itl_s)`
  in `naive_server.py`), then percentiled across requests. So "TPOT p99" is the
  99th-percentile request by mean ITL, not a true per-token p99. Per-token
  percentiles are a Week 2 addition.
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
