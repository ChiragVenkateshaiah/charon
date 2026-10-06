# Week 1 baseline — Nsight Systems profile (2026-10-06)

**Profiling-only.** This is a trace of the **unchanged** Week 1 naive server.
Nothing in `serving/`, `benchmarks/baseline_runner.py`, the prompts or `uv.lock`
was modified; all are byte-identical to the Week 1 result commit `b0faad1`.

The profiler slows the run down: requests took 5.65 s here against 3.71 s
unprofiled. So **no time measured here is a benchmark result** (ADR-0001), and
none replaces the Week 1 numbers. The trace exists to show *where* each token's
time goes.

Questions it answers:
- Does the GPU wait on the CPU?
- How many kernels run per token?
- Where does the idle time sit?
- Is synchronization significant?

Labels used below:
- **MEASURED:** read from this trace.
- **DERIVED:** arithmetic on measured values.
- **INFERRED:** a reasoned reading, not directly observed.
- **UNKNOWN:** not observable with this capture.

## Experiment metadata

| | |
|---|---|
| Date | 2026-10-06. Instance created 16:09:07 UTC, deleted 16:40:59 UTC (0.53 h) |
| Trace capture | server start 16:14:23 → requests 16:14:33–16:19:16 → server stopped 16:19:16 → report written 16:22:16 |
| Model | `Qwen/Qwen2.5-1.5B-Instruct` @ `989aa7980e4cf806f80c7fef2b1adb7bc71aa306`, `torch.bfloat16`, 3,087,429,632 B weights (from the server's `/healthz`, same as Week 1) |
| Requests | 20 warmup + **30 measured**, 1 run, concurrency 1, batch 1, **128** forced output tokens, default prompt set |
| GPU | NVIDIA L4, driver **580.173.02**, 23,034 MiB, 72 W limit, max SM 2040 MHz, PCIe Gen3 ×16 reported, persistence on. `CUDA_VISIBLE_DEVICES` unset (single GPU) |
| Image | `common-cu129-ubuntu-2204-nvidia-580-v20260818`, the same image as Week 1, pinned via `CHARON_IMAGE` |
| Stack | torch 2.13.0+cu130, transformers 5.16.1 (`uv sync --locked`, same as Week 1). Python 3.14.8 (Week 1's Python version was not recorded) |
| Profiler | Nsight Systems **2025.1.3.140**, preinstalled on the image. Nsight Compute 2025.2.0 is also present but was not used |
| Host | GCP `g2-standard-4` spot, `us-central1-c` |
| Git | `decbdf3-dirty` (uncommitted changes were the new scripts and docs only, not inference code) |

**Server under the profiler:**

```
/usr/local/cuda/bin/nsys profile --trace=cuda,nvtx,osrt --force-overwrite=true \
  --output=/home/chirag/prof/full/trace --sample=process-tree --cpuctxsw=process-tree \
  --python-sampling=true --cuda-memory-usage=false \
  .venv/bin/python -m uvicorn serving.naive_server:app --port 8000
```

**Client (unchanged Week 1 runner, output kept out of `benchmarks/results/`):**

```
.venv/bin/python benchmarks/baseline_runner.py --warmup 20 --requests 30 --runs 1 \
  --output-tokens 128 --out /home/chirag/prof/full/runner.json
```

**Reproduce:** `bash scripts/profile-session.sh` locally. It creates the instance,
runs setup, runs the smoke trace and then the full trace, copies everything
back, and tears down. Then run
`python3 benchmarks/nsys_analyze.py benchmarks/profiles/2026-10-06-week1-nsys/full`.

**Capture limitations:**
- **No CPU sampling.** `nsys` reported "CPU IP/backtrace sampling not
  supported" and "CPU context switch tracing not supported" on this VM, so the
  sampling flags had no effect and the trace has **no Python or CPU call stacks**.
  CPU-side evidence comes from CUDA API timing only.
- **No step markers.** Charon emits no NVTX ranges. The 51 NVTX rows present
  are library ranges (`cub::DeviceScan::InclusiveScan` once per request, plus
  one CCCL marker). Decode steps were therefore recovered from the LM-head GEMV
  (grid 37,984 = 151,936 vocab rows ÷ 4), which runs exactly once per token.
  Step 0 is prefill; steps 1–127 are decode.
- **One run.** `runs=1` violates methodology rule 4 on purpose: this is a
  profile, not a benchmark.

## Client view under the profiler (MEASURED, profiled, not a result)

| | Profiled (this run) | Week 1, unprofiled (the result) |
|---|---|---|
| Decode tok/s, p50 | 22.66 | 34.50 |
| TPOT, p50 | 44.1 ms | 29.0 ms |
| TTFT, p50 | 46.7 ms | 32.1 ms |
| E2E, p50 | 5.650 s | 3.713 s |
| `nvidia-smi` util, p50 | 37% | 53% |

## Findings

All figures cover 3,810 decode steps (30 requests × 127), measured under the profiler.

| Question | Evidence | Interpretation | Confidence |
|---|---|---|---|
| **GPU idle gaps** | **MEASURED.** The GPU (kernels, copies and memsets merged) is busy **32.8%** of decode wall time. Each step has a p50 of **1,196 idle gaps**, which is **one before almost every kernel**. Gaps: p50 18.7 µs, p95 75 µs, p99 105 µs. Idle per step: p50 27.5 ms. Gaps of 100 µs or more average 14.4 per step and hold only **11%** of idle time. | The GPU is not continuously busy. Idle time comes from many small, regular gaps repeated every token, not a few large stalls. | High |
| **Kernels per token** | **MEASURED.** **1,195** kernels per token across all steps; decode steps p50 1,185; prefill 1,239. **81%** of all kernels run for under 5 µs. | Very fine-grained eager execution: about 1,200 separate launches produce one token. | High |
| **Dominant kernels** | **MEASURED.** Two cuBLAS BF16 GEMV kernels take **86.4%** of kernel time: `gemvx[6]` 112 per token, 81.9 µs mean, 63.5%; `gemvx[7]` 83 per token, 39.8 µs mean, 23.0%. The other ~1,000 per token are small elementwise, reduce and flash-attention kernels of 1–8 µs each. | A few GEMVs (the weight matrix-vector products) dominate GPU *time*. Many tiny kernels dominate the *launch count*. | High |
| **Does the CPU feed the GPU fast enough?** | **MEASURED.** Launch-to-start lag (kernel start minus the end of its `cudaLaunchKernel` call) is p50 **1.0 µs**. **73%** of kernels start within 5 µs of their launch returning; 11% wait over 100 µs (queued behind the long GEMVs). GPU-busy time per step is **nearly constant** (p50 14.47 ms, p99 14.51 ms) while step wall time varies (p50 41.9 ms, p99 96.6 ms). | For most kernels nothing was queued, so the GPU ran each one as soon as the CPU handed it over and then sat idle until the next arrived. The step's length is set by the host, not the GPU. | High that the GPU is starved by the host; **UNKNOWN** which host component (no CPU stacks) |
| **CUDA API behavior** | **MEASURED, profiled.** `cudaLaunchKernel` 1,193 per token at a mean of 9.1 µs, so **10.8 ms of CPU per token in launch calls alone**. `cudaMemcpyAsync` 11.1 per token, `cudaMemsetAsync` 1.2 per token. The tracer inflates every API call's duration. | Launch overhead is large and repeated about 1,200 times per token. The unprofiled cost per launch is **UNKNOWN**; this capture inflates it. | Medium |
| **Synchronization** | **MEASURED.** `cudaStreamSynchronize` **2.06 per token**, mean 92 µs, so **0.19 ms per token** of CPU blocked, about 0.5% of a profiled step. 2.0 device-to-host copies per token (tiny, about 5 B each); 9.0 device-to-device copies per token (1.4 µs each). No device or context syncs in decode. | Syncs are regular (twice per token, in the generation loop) but cheap. Not a significant bottleneck. | High |
| **Logits processing** | Charon's `_StepTimer` logits processor is one Python call per token. Its CPU cost is not observable without CPU sampling (**UNKNOWN**). | It is 1 Python call per ~1,195 kernel launches, so it is unlikely to matter (INFERRED). Not established. | Low |
| **Memory behavior** | **DERIVED.** GEMV time per token = 112.1 × 81.9 µs + 83.3 × 39.8 µs ≈ **12.5 ms**. Moving 3.087 GB of weights in 12.5 ms ≈ **247 GB/s**, about **82%** of the 300 GB/s datasheet figure. | While the GEMVs run, they *may* be close to memory-bandwidth-limited. This is **not** measured DRAM bandwidth: it assumes each weight byte is read once and only weights are read. Only Nsight Compute can confirm it. | Low–medium |
| **Steady-state decode** | **MEASURED.** Prefill: 48.8 ms, 1,239 kernels, 34.7% busy. Decode: 41.9 ms per step, about 1,185 kernels, 32.8% busy, the same pattern every step. 1 warmup + 20 discarded requests precede the window. | Decode is uniform from token to token. Prefill at a ~45-token prompt looks like one more decode-shaped step, not a compute-heavy phase. | High |

## What drove step time: the profiler itself is evidence (INFERRED)

Profiling added about **12.9 ms of CPU-side work per token** (41.9 − 29.0
ms). That time went **straight into wall time**, while GPU-busy time per token
stayed at ~14.5 ms. If the GPU were the bottleneck, extra CPU work would hide
behind GPU execution. It didn't, so the decode loop is host-paced.

Kernel durations come from GPU timestamps and are much less sensitive to the
tracer than API calls. If the ~14.5 ms of GPU work per token is the same
unprofiled, then at Week 1's 29.0 ms TPOT the GPU would be busy about **50%** of
the time. That agrees with the **53%** `nvidia-smi` reading measured
independently in Week 1. This run gives a second agreement: 14.47 / 41.9 =
34.5% against `nvidia-smi`'s 37% under the profiler.

**Unprofiled token budget (INFERRED):** of Week 1's 29.0 ms per token, about
**14.5 ms is GPU work** (~12.5 ms of it GEMV) and about **14.5 ms is GPU idle,
waiting on the host**. That is roughly 12 µs of host time per kernel
(INFERRED: 14.5 ms ÷ ~1,196 gaps).

## Bottleneck hypotheses (ranked)

**1. Host-bound decode: launch and orchestration overhead.** The CPU issues about
1,195 small eager-mode kernels per token, one at a time, and the GPU waits for
it about half the time.
- *Evidence:*
  - 73% of kernels start within 5 µs of being launched (MEASURED).
  - About one idle gap per kernel, with idle making up 67% of a profiled step (MEASURED).
  - GPU-busy time per step is constant while wall time varies (MEASURED).
  - Profiler overhead on the CPU passed one-for-one into step time (INFERRED).
  - The ~50% busy estimate matches Week 1's 53% (INFERRED).
- *Evidence against or gaps:* there are no CPU stacks, so it's **UNKNOWN** how
  host time splits between the Python interpreter (HF `generate()` and module
  calls), the PyTorch dispatcher, and the CUDA driver launch path. Launch-call
  durations here are inflated by the tracer.
- *Confidence:* **high** that the GPU is host-starved; **medium** on the mechanism.
- *Confirm or refute:* repeat this trace with CPU sampling actually enabled
  (see Next experiment) to attribute the host time.

**2. The GEMVs, which are 86% of GPU time, are DRAM-bandwidth-limited.**
- *Evidence:* the DERIVED ~247 GB/s effective weight rate during GEMV execution,
  ~82% of datasheet. GEMV at batch 1 is the low-AI operation in the roofline model.
- *Evidence against or gaps:* derived, not measured. Achieved DRAM throughput,
  L2 hit rate and stall reasons are **UNKNOWN**.
- *Confidence:* **low–medium.**
- *Confirm or refute:* Nsight Compute on `gemvx[6]` and `gemvx[7]`: DRAM
  throughput as % of peak, memory-stall breakdown, achieved occupancy.

**3. Tiny-kernel granularity.** About 1,000 elementwise and reduce kernels per
token, each 1–3 µs, cost more host time to launch than GPU time to run.
- *Evidence:* 81% of kernels are under 5 µs (MEASURED). About 71% of decode
  idle time follows a small `at::native` elementwise kernel (MEASURED: gap
  attribution by preceding kernel).
- *Evidence against or gaps:* this is mostly *how* hypothesis 1 shows up, not a
  separate cause. Per-kernel GPU occupancy is **UNKNOWN**.
- *Confidence:* **medium**, as a mechanism under hypothesis 1.

**4. Synchronization or logits processing.**
- *Evidence against:* 2 syncs per token costing 0.19 ms (MEASURED); tiny
  device-to-host copies; the logits processor is one Python call per token.
- *Confidence:* **low** that either is significant.

## Roofline relationship

The roofline report (`docs/week1-roofline.md`) left a gap: decode reaches about
35.5% of the simplified memory roof, and ~64% of each 29 ms token was
unexplained by the ~10.3 ms bandwidth floor.

- **Accounts for most of the gap below the roof.** Under the profiler the GPU
  is idle about 67% of each step, and the inferred unprofiled figure is about
  50%. The point sits low on the chart mainly because the GPU is often doing
  nothing while it waits for the host, not because memory traffic is slow. The
  trace gives **no evidence** that the server *as a whole* is memory-bound.
- **Supports the roofline at kernel level.** When the GPU *is* busy, about 86% of
  that time is BF16 GEMV, the AI ≈ 1 operation the roofline model is about. The
  derived ~247 GB/s suggests those kernels may run near the memory roof. That
  claim needs Nsight Compute.
- **Does not address achieved DRAM bandwidth.** Nsight Systems doesn't measure it.

Net: the roofline hypothesis is **refined, not confirmed**. The evidence-backed
picture is a **host-bound decode loop wrapped around GEMV kernels that may be
bandwidth-limited**.

## Next experiment (one)

**Repeat this exact trace with host CPU sampling enabled** to attribute the
~14.5 ms per token of host-paced idle time to its source: the Python interpreter
(HF `generate()` loop and `nn.Module` call overhead), the PyTorch dispatcher, or
the CUDA driver launch path.
- **Setup:** same pinned image, same unchanged server and client, same 20 + 30
  requests.
- **The one change, to the throwaway VM only:** before profiling, lower
  `kernel.perf_event_paranoid` so `nsys` CPU and Python sampling actually run.
  This alters the instance, not Charon, but it is an environment change and
  needs your approval.
- **Why this before Nsight Compute:** hypothesis 1 (host-bound) explains about
  half of each token; hypothesis 2 (GEMV bandwidth) explains at most the other
  half. Knowing which host layer dominates decides the class of fix to evaluate
  later (fewer launches, cheaper launches, or less Python). Nsight Compute on
  the two `gemvx` kernels is the follow-up after that.
- **Cost (ESTIMATED, NOT MEASURED):** about 0.4 GPU-hours, so about ₹28 at ₹69/h
  (observed effective rate) or about ₹17 at ₹41.9/h (list price). That's slightly
  shorter than this session, now that stats export once.

## Cost of this session (ESTIMATED, NOT MEASURED)

Instance lifetime was 0.53 h. That is about **₹37 at ₹69/h (observed effective
rate)** or about **₹22 at ₹41.9/h (spot list price, `docs/gcp-setup.md`)**.
- Neither rate was changed in the repo.
- This is profiling cost only. It is **not** production economics and is not
  part of the Week 1 cost per token.
- Roughly 10 minutes of that was a script inefficiency: `nsys stats`
  re-exported the 1.3 GB sqlite for each of 8 reports. It is fixed in
  `scripts/profile-nsys.sh` (export once).

## Data quality: run-label inconsistency (reported, not fixed)

The Week 1 raw result `baseline-20260828T172338Z.json` labels runs 1, 2 and 3.
Recomputed from its raw records, TTFT p99 by run is **35.0 / 41.1 / 34.8 ms**, so
the slow tail is in **run 2**.

These documents attribute it to **run 1**:
- `benchmarks/results/2026-08-28-week1-baseline.md:35`
- `docs/week1-profile-card.md:37`
- `docs/worklog.md:41`

The raw JSON is correct and was not modified; the prose is the error. Fixing it
is the owner's call.

## Artifacts

Under `benchmarks/profiles/2026-10-06-week1-nsys/`:

| Path | Contents |
|---|---|
| `full/summary.json` | analysis output (`benchmarks/nsys_analyze.py`) |
| `full/stats/*.csv` | `nsys stats` summaries |
| `full/meta.json` | commands and times |
| `full/runner.json` | profiled client output; **not a result** |
| `full/server.log` | server output |
| `env/` | `nvidia-smi`, image, versions, `nsys` provenance |
| `smoke/` | the 1 + 2 request validation trace |
| `job.log` | on-instance job log |

The large binaries are **gitignored and local only**: `full/trace.nsys-rep`
(498 MB) and `full/trace.sqlite.gz` (444 MB). The 1.3 GB unpacked
`trace.sqlite` is regenerable from the `.gz`.
