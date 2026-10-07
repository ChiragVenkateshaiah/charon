# Steady-state decode on the L4: Nsight Systems investigation

**Subject:** Charon Week 1 naive server, unchanged. Qwen2.5-1.5B-Instruct, BF16,
NVIDIA L4.
**Trace:** this folder (`benchmarks/profiles/2026-10-06-week1-nsys/`), captured
2026-10-06. The earlier summary of the same trace is `report.md`.
**Written:** 2026-10-07. This is a read-only analysis of the existing trace:
nothing was optimized, no benchmark was run, and no code or result changed.
**Companion page:** `decode-deep-dive.html` in this folder. It has graphs and
animations for every section. Section 13 explains how to read them.

## Labels and one caveat

| Label | Meaning |
|---|---|
| **MEASURED** | read directly from this trace (or from the Week 1 result file) |
| **DERIVED** | arithmetic on measured values |
| **INFERRED** | a reasoned reading, not directly observed |
| **UNKNOWN** | not observable in this capture |

**Caveat that applies to every time below:** this is a *profiled* run. The
tracer adds CPU-side overhead to every CUDA call, so requests took 5.65 s here
against 3.71 s in the Week 1 benchmark. GPU kernel durations are close to
real. CPU-side times and step wall times are inflated. Counts, patterns and
ratios are what this trace is good for.

---

## 1. Profile metadata

| Item | Value |
|---|---|
| Nsight Systems | **2025.1.3.140**, preinstalled on the image |
| GPU | **NVIDIA L4**, 23,034 MiB, 72 W limit, max SM clock 2040 MHz, PCIe Gen3 ×16 reported |
| Driver | **580.173.02** |
| CUDA / PyTorch | **torch 2.13.0+cu130**, CUDA **13.0** runtime (from torch). transformers **5.16.1**, Python 3.14.8 |
| Image | `common-cu129-ubuntu-2204-nvidia-580-v20260818`, the same as Week 1 |
| Host | GCP `g2-standard-4` spot, `us-central1-c` |
| Profiled requests | **30 measured** (+ a separate 1 + 2 request smoke trace, not analyzed here) |
| Warmup requests | **20**, run first in the same capture and excluded from the analysis |
| Output tokens per request | **128** (forced: min = max) |
| Batch size / concurrency | **1 / 1** (one request at a time, global lock in the server) |
| Prompt length | 41–49 tokens (the Week 1 prompt set) |
| Profiling duration | capture 16:14:23 → 16:19:16 UTC (**4 min 53 s**); requests 16:14:33 → 16:19:16 (4 min 43 s); the 30 measured requests took about 5.65 s each |
| Capture limits | no CPU sampling, no context-switch tracing (the VM refused them), so there are **no Python or CPU call stacks**. No NVTX ranges from Charon |
| Decode thread | all CUDA calls come from one host thread, **`AnyIO worker th`**, the FastAPI worker thread that runs `model.generate()` |

## 2. Steady-state decode timeline (10 consecutive tokens)

Sample: request 16, decode steps 60–69. A "step" here runs from one LM-head
GEMV ending to the next, which is one generated token.

| Step | Wall (ms) | GPU busy (ms) | GPU idle (ms) | Kernels |
|---|---|---|---|---|
| 60 | 43.51 | 14.46 | 29.04 | 1,185 |
| 61 | 41.45 | 14.47 | 26.98 | 1,185 |
| 62 | 41.49 | 14.46 | 27.03 | 1,185 |
| 63 | 41.26 | 14.47 | 26.79 | 1,185 |
| 64 | 42.06 | 14.47 | 27.59 | 1,185 |
| 65 | 48.59 | 14.47 | 34.12 | 1,185 |
| 66 | 44.20 | 14.47 | 29.73 | 1,185 |
| 67 | 42.59 | 14.47 | 28.12 | 1,185 |
| 68 | 42.35 | 14.46 | 27.89 | 1,185 |
| 69 | 42.23 | 14.47 | 27.77 | 1,185 |

All MEASURED under the profiler.

- **Continuous or gaps?** Gaps. The GPU is idle between almost every pair of
  kernels: about **1,197 idle gaps per step**, roughly one per kernel. Across
  all 3,810 decode steps: gap median **18.7 µs**, p95 75 µs, p99 105 µs. The
  largest gap in a step is a median **217 µs**, at the token boundary (see §6).
  MEASURED.
- **Do gaps repeat per token?** Yes. Every token shows the same pattern and
  the same count. GPU-busy time is almost identical from token to token
  (14.46–14.47 ms in the sample; p05–p95 14.39–14.50 ms over all steps), while
  wall time wanders (41.3–48.6 ms in the sample). MEASURED.
- **GPU busy per token:** **≈ 14.47 ms** (p50 over 3,810 steps). That is
  **34%** of the profiled step. MEASURED.
- **CPU / non-GPU time per token:** the GPU is idle **≈ 27.5 ms** per step
  (p50). On the decode thread, per step (p50):
  - time inside CUDA API calls: **≈ 9.7 ms**;
  - time outside any CUDA API call: **≈ 32.2 ms**.

  These two add up to the step wall time. They run concurrently with GPU work,
  not after it. MEASURED, profiled.

## 3. Kernels per token

| Quantity | Value |
|---|---|
| Decode steps analyzed | 3,810 (30 requests × 127; step 0 of each request is prefill) |
| Kernel launches during steady-state decode | **4,551,474** |
| Kernels per generated token | **1,185 (median)**, mean 1,194.6. Every step has either 1,185 or 1,213 |
| Including prefill (all 3,840 tokens) | 1,195.3 per token |
| `cudaLaunchKernel` calls per step | 1,194.6 mean, which matches the kernel count one-for-one |

**How the estimate was obtained (MEASURED):**
1. The LM-head GEMV (grid 37,984 = 151,936 vocabulary rows ÷ 4) runs exactly
   once per generated token in every request, so its end times split each
   request into 128 forward passes.
2. Every GPU kernel whose start time falls inside a pass counts toward that
   token.
3. Pass 0 is prefill; passes 1–127 are steady-state decode.
4. The total matches the `cudaLaunchKernel` count on the decode thread.

Charon has no NVTX ranges, so this boundary rule replaces them.

**Where the 1,185 come from** (structure from kernel order; op names INFERRED from kernel types):

| Section | Kernels | Wall (µs) | GPU busy (µs) |
|---|---|---|---|
| Token setup: logits processing, argmax, bookkeeping, embedding, rotary setup, first norm | 64 | ≈ 1,570 | ≈ 120 |
| Each of 28 decoder layers | 40 | ≈ 1,370 | ≈ 446 (GEMV ≈ 384) |
| LM head (one GEMV) | 1 | ≈ 1,830 | ≈ 1,827 |
| **Total** | **64 + 28 × 40 + 1 = 1,185** | | |

Wall and busy are p50 over steps 60–69 (MEASURED).

## 4. Top 10 GPU kernels (steady-state decode only)

| Rank | Kernel (short) | Calls | Total GPU time | % GPU time | Per token |
|---|---|---|---|---|---|
| 1 | `internal::gemvx::kernel` (cuBLAS, template `(int)6`) | 430,530 | 35,192.3 ms | **63.97%** | 113 |
| 2 | `internal::gemvx::kernel` (cuBLAS, template `(int)7`) | 320,040 | 12,743.1 ms | **23.17%** | 84 |
| 3 | `at::native::elementwise_kernel` (MulFunctor) | 426,720 | 811.3 ms | 1.47% | 112 |
| 4 | `at::native::reduce_kernel` (MeanOps) | 217,170 | 601.1 ms | 1.09% | 57 |
| 5 | `at::native::unrolled_elementwise_kernel` (direct_copy) | 224,790 | 579.1 ms | 1.05% | 59 |
| 6 | `pytorch_flash::flash_fwd_kernel` | 70,056 | 549.4 ms | 1.00% | 18.4 |
| 7 | `at::native::vectorized_elementwise_kernel` (CUDAFunctor_add) | 426,720 | 536.2 ms | 0.97% | 112 |
| 8 | `at::native::CatArrayBatchedCopy` | 213,360 | 481.3 ms | 0.87% | 56 |
| 9 | `at::native::vectorized_elementwise_kernel` (MulFunctor) | 323,850 | 412.6 ms | 0.75% | 85 |
| 10 | `at::native::elementwise_kernel` (neg_kernel) | 213,360 | 390.0 ms | 0.71% | 56 |

MEASURED. "% GPU time" is the share of all kernel time inside decode steps
(≈ 14.44 ms per step). The whole-capture equivalent is in the repo at
`full/stats/cuda_gpu_kern_sum_cuda_gpu_kern_sum.csv`, with the same top two.

**Exact kernel names, as Nsight reports them:**

1. `std::enable_if<!T7, void>::type internal::gemvx::kernel<int, int, __nv_bfloat16, __nv_bfloat16, __nv_bfloat16, float, (bool)0, (bool)1, (bool)1, (bool)0, (int)6, (bool)0, cublasGemvParamsEx<int, cublasGemvTensorStridedBatched<const __nv_bfloat16>, cublasGemvTensorStridedBatched<const __nv_bfloat16>, cublasGemvTensorStridedBatched<__nv_bfloat16>, float>>(T13)`
2. `std::enable_if<!T7, void>::type internal::gemvx::kernel<int, int, __nv_bfloat16, __nv_bfloat16, __nv_bfloat16, float, (bool)0, (bool)1, (bool)1, (bool)0, (int)7, (bool)0, cublasGemvParamsEx<int, cublasGemvTensorStridedBatched<const __nv_bfloat16>, cublasGemvTensorStridedBatched<const __nv_bfloat16>, cublasGemvTensorStridedBatched<__nv_bfloat16>, float>>(T13)`
3. `void at::native::elementwise_kernel<(int)128, (int)4, void at::native::gpu_kernel_impl_nocast<at::native::BinaryFunctor<c10::BFloat16, c10::BFloat16, c10::BFloat16, at::native::binary_internal::MulFunctor<float>>>(at::TensorIteratorBase &, const T1 &)::[lambda(int) (instance 1)]>(int, T3)`
4. `void at::native::reduce_kernel<(int)512, (int)1, at::native::ReduceOp<float, at::native::MeanOps<float, float, float, float>, unsigned int, float, (int)4, (int)4>>(T3)`
5. `void at::native::unrolled_elementwise_kernel<at::native::direct_copy_kernel_cuda(at::TensorIteratorBase &)::[lambda() (instance 3)]::operator ()() const::[lambda() (instance 7)]::operator ()() const::[lambda(float) (instance 1)], std::array<char *, (unsigned long)2>, (int)4, TrivialOffsetCalculator<(int)1, unsigned int>, TrivialOffsetCalculator<(int)1, unsigned int>, at::native::memory::LoadWithCast<(int)1>, at::native::memory::StoreWithCast<(int)1>>(int, T1, T2, T4, T5, T6, T7)`
6. `void pytorch_flash::flash_fwd_kernel<Flash_fwd_kernel_traits<(int)128, (int)128, (int)32, (int)4, (bool)0, (bool)0, cutlass::bfloat16_t, Flash_kernel_traits<(int)128, (int)128, (int)32, (int)4, cutlass::bfloat16_t>>, (bool)0, (bool)0, (bool)0, (bool)0, (bool)0, (bool)1, (bool)0, (bool)0>(pytorch_flash::Flash_fwd_params)`
7. `void at::native::vectorized_elementwise_kernel<(int)4, at::native::CUDAFunctor_add<c10::BFloat16>, std::array<char *, (unsigned long)3>>(int, T2, T3)`
8. `void at::native::<unnamed>::CatArrayBatchedCopy<at::native::<unnamed>::OpaqueType<(unsigned int)2>, unsigned int, (int)4, (int)64, (int)64>(T1 *, at::native::<unnamed>::CatArrInputTensorMetadata<T1, T2, T4, T5>, at::native::<unnamed>::TensorSizeStride<T2, (unsigned int)4>, int, T2)`
9. `void at::native::vectorized_elementwise_kernel<(int)4, at::native::BinaryFunctor<c10::BFloat16, c10::BFloat16, c10::BFloat16, at::native::binary_internal::MulFunctor<float>>, std::array<char *, (unsigned long)3>>(int, T2, T3)`
10. `void at::native::elementwise_kernel<(int)128, (int)4, void at::native::gpu_kernel_impl_nocast<at::native::neg_kernel_cuda(at::TensorIteratorBase &)::[lambda() (instance 2)]::operator ()() const::[lambda() (instance 9)]::operator ()() const::[lambda(c10::BFloat16) (instance 1)]>(at::TensorIteratorBase &, const T1 &)::[lambda(int) (instance 1)]>(int, T3)`

**Which projections use which GEMV kernel.** This mapping comes from the
order of kernels in each layer. The byte counts come from the Qwen2.5-1.5B
config, which I checked against the measured weight bytes: the config gives
1.5436 B parameters, and the measured weights give 1.5437 B.

| Kernel | Projection(s) | Per token |
|---|---|---|
| `gemvx (int)6` | q_proj, o_proj, gate_proj, up_proj (×28) + LM head | 113 |
| `gemvx (int)7` | k_proj, v_proj, down_proj (×28) | 84 |

## 5. CPU activity

| What to find | Evidence in this trace | Reading |
|---|---|---|
| **Python execution** | No direct evidence: there is no CPU sampling. Indirect: the decode thread spends **≈ 32.2 ms per step outside any CUDA call** (MEASURED). Over steps 60–69 the thread issues a kernel launch every **27.7 µs** (p50), but each `cudaLaunchKernel` call takes only **7.2 µs** (p50) (MEASURED). | ≈ 20 µs of host time per kernel happens outside the CUDA runtime, in Python and the PyTorch dispatcher (**INFERRED**; which one owns it is **UNKNOWN**). |
| **`model.generate()` loop** | One thread (`AnyIO worker th`) issues all decode work. The same kernel sequence repeats every token. Each token has 2 small device-to-host copies (≈ 5 B each) and 2 stream syncs (MEASURED). | This is the per-token loop of `generate()`: run the forward pass, read back the new token, check whether to stop (INFERRED from the pattern). |
| **Logits processing** | Each token starts with **64 kernels** before the first GEMV: fill, scatter, a `MaxNan` reduce, compare and copy kernels. They take ≈ 1.57 ms of wall but only ≈ 0.12 ms of GPU time (MEASURED). | These are consistent with the logits processors (`min_new_tokens` masks EOS), greedy argmax, and loop bookkeeping, plus the embedding and rotary setup (INFERRED from kernel types). Charon's `_StepTimer` runs on the CPU only, so it is not visible separately (UNKNOWN). |
| **Tokenizer work** | Not in the decode loop. Before each request's first kernel there are **≈ 3.27 ms** of host time (p50); after its last kernel, **≈ 1.31 ms** (MEASURED intervals). | The before-gap covers HTTP, chat template, tokenizer and input copy; the after-gap covers detokenizing and the JSON response (INFERRED attribution). |
| **CUDA API calls** | Per decode step: `cudaLaunchKernel` 1,194.6 (mean 9.1 µs, profiled); `cuKernelGetName` 1,194.6 (0.19 µs, tool-side); `cudaMemcpyAsync` 11.0 (14 µs); `cudaStreamSynchronize` 2.0 (95 µs mean); `cudaMemsetAsync` 1.0; `cuLaunchKernelEx` 1.0 (MEASURED). | Kernel launches dominate the API time, at ≈ 9.7 ms per step (profiled). |
| **CPU waiting** | Sync wait is **≈ 0.22 ms per step** (p50) (MEASURED). | The CPU rarely waits for the GPU. Mostly the GPU waits for the CPU. |
| **Other orchestration** | OS-runtime calls on other threads are `poll`, `epoll_pwait`, `read`, `sem_clockwait` (the server's event loop and helpers, waiting) (MEASURED). | Not on the decode path. |

## 6. Synchronization

| Pattern | What synchronizes | Frequency | Time | Per token? |
|---|---|---|---|---|
| **End-of-token sync** | `cudaStreamSynchronize` after a tiny device-to-host copy, as the GPU finishes the LM-head GEMV (1.83 ms) and the token is read back | ≈ 1 per token (2,751 land just before the step boundary; others start just after it) | **p50 ≈ 228 µs** (p05 156, p95 295) | **Yes, every token** |
| **Early-step sync** | `cudaStreamSynchronize` ≈ 0.7 ms into the step, after another tiny device-to-host copy | ≈ 1 per token | **p50 ≈ 7 µs** | **Yes, every token** |
| Device or context sync | none seen in decode | 0 | — | — |

All MEASURED. Nsight labels the sync type "Stream wait sync". The purpose of
each copy (reading the new token id, checking the stop condition) is INFERRED
from the `generate()` pattern.

- The end-of-token sync is the one place per token where the **CPU waits for
  the GPU**. During the long LM-head GEMV the CPU gets ahead, then blocks
  until the token is ready.
- Both syncs together are ≈ 0.22 ms of a ≈ 41.9 ms profiled step, about
  **0.5%**. **Not a significant bottleneck.**

## 7. Prefill vs decode

| | Prefill (pass 0) | Steady-state decode (passes 1–127) |
|---|---|---|
| Wall per pass | ≈ 48.8 ms | ≈ 41.9 ms |
| GPU busy | ≈ 17.1 ms (35%) | ≈ 14.5 ms (34%) |
| Kernels | 1,239 | 1,185 (or 1,213) |
| Host time in CUDA calls | ≈ 10.4 ms | ≈ 9.7 ms |

All MEASURED, profiled, p50 over 30 requests.

- **Prefill.** With a 41–49 token prompt, prefill looks like one slightly
  larger decode step. The 30 prefills take a little more GPU time and have the
  same idle pattern. It also costs ≈ 3.3 ms of host work before the first
  kernel. It is 1 pass of 128, so it barely moves the per-token average.
- **Decode.** All 127 remaining passes follow the pattern in §8. The
  conclusions below are about decode.

## 8. Token-level pattern

**Yes, the same sequence repeats every token.** Across 3,810 decode steps
there are only **4 distinct exact kernel sequences**: two at 33% each and two
at 17% each, of length 1,185 or 1,213. The 1,213 variant has 28 extra kernels,
one per layer; the cause is not identified (MEASURED).

**The repeated pattern, one token** (op names INFERRED from kernel types):

```
CPU  (decode thread)  : launch, launch, launch, ...   one cudaLaunchKernel every ~28 µs
GPU                   :
  [token setup]   64 tiny kernels      logits processing, argmax, bookkeeping,
                                        embedding, rotary setup, RMSNorm
  [layer] × 28    40 kernels each:
        RMSNorm (~6 tiny)
        q_proj GEMV ~22 µs, k_proj ~5 µs, v_proj ~5 µs (+ bias adds)
        rotary embedding (~10 tiny: mul, neg, cat, add)
        KV-cache append (2 × CatArrayBatchedCopy)
        flash attention (~9 µs)
        o_proj GEMV ~22 µs, residual add
        RMSNorm (~6 tiny)
        gate_proj GEMV ~110 µs, up_proj GEMV ~110 µs, SiLU × mul
        down_proj GEMV ~109 µs, residual add
  [LM head]       1 GEMV ~1,827 µs     151,936-row vocabulary projection
sync pattern      : short sync ~0.7 ms in; long sync at the token boundary
```

**Why the GPU idles.** In each layer:
- 7 GEMVs take ≈ 384 µs of GPU time.
- 33 tiny kernels take 1–3 µs each.
- The host needs ≈ 28 µs to issue each kernel (measured interval).

During a ~110 µs GEMV, the CPU issues about four kernels ahead, so the queue
fills. In each run of tiny kernels, the GPU finishes each kernel in ~2 µs and
waits ~26 µs for the next. That pattern repeats 28 times per token.

## 9. Bottleneck hypotheses (ranked)

**1. D — CPU/Python orchestration** (host-side issue rate). **Confidence: high**
that the host sets the pace; **medium** on how the host time splits.
- *For:*
  - The GPU is idle ≈ 66% of each profiled step, in ~1,197 small gaps.
  - GPU-busy time is constant (14.46–14.47 ms) while wall time varies.
  - 73% of kernels start within 5 µs of their launch returning, so nothing
    was queued.
  - The host issues one kernel per ~28 µs, while most kernels run 1–3 µs.
  - Only ≈ 7 µs of each 28 µs interval is inside `cudaLaunchKernel`; the rest
    is outside the CUDA runtime.
  - Profiler overhead added to the CPU went straight into step time.
- *Against or gaps:* there is no CPU sampling, so Python vs the PyTorch
  dispatcher vs other host work is **UNKNOWN**. The profiler inflates host
  time, so the unprofiled size of each part is unknown.

**2. C — Kernel launch overhead.** **Confidence: medium.**
- *For:* 1,194 launches per token, each a real `cudaLaunchKernel` call of
  7–9 µs (profiled), ≈ 9.7 ms per step in CUDA API calls. Removing launches is
  the obvious lever.
- *Against:* the launch call itself is the smaller part of the per-kernel host
  interval (≈ 7 of ≈ 28 µs), and CUPTI instrumentation inflates exactly this
  call. Its unprofiled cost is UNKNOWN.

**3. B — Memory bandwidth, inside the GEMV kernels only.** **Confidence:
medium-low.**
- *For:* GEMVs are 87% of GPU time. While they run, the big ones move weights
  at **≈ 250 GB/s** and the LM head at **≈ 255 GB/s**, about 83–85% of the
  300 GB/s datasheet (DERIVED: config bytes ÷ measured duration). This is
  typical of a low-AI operation near its memory roof.
- *Against:* it is derived, not measured DRAM bandwidth. It also explains only
  the ≈ 34% of the step when the GPU is busy. It does not explain the
  end-to-end rate.

**Not ranked:**
- **A — compute:** GEMV at batch 1 has AI ≈ 1, and the GPU does almost no
  arithmetic. No evidence.
- **E — synchronization:** ≈ 0.5% of the step.
- **F — occupancy/parallelism:** small kernels are short, but their occupancy
  is UNKNOWN without Nsight Compute.
- **G — other:** nothing seen.

**Charon is not shown to be memory-bound or compute-bound as a whole.** The
trace shows a host-paced decode loop. Only its GEMV kernels look
bandwidth-limited, and that is a derived reading.

## 10. Roofline connection

The trace **suggests launch and CPU overhead** for the end-to-end rate. It
**weakens** the memory-bound explanation for the token rate, but **supports**
memory-limited behavior inside the GEMVs.

The two readings reconcile in one line of arithmetic (DERIVED, using the
unprofiled Week 1 TPOT):

```
average weight traffic  = 3.087 GB per token ÷ 29.0 ms per token ≈ 106.5 GB/s
GEMV time per token     ≈ 12.5 ms   (GPU kernel time from the trace)
rate while GEMVs run    ≈ 3.087 GB ÷ 12.5 ms ≈ 247 GB/s   (~82% of 300)
share of time in GEMV   ≈ 12.5 ÷ 29.0 ≈ 43%
247 GB/s × 43%          ≈ 106 GB/s   ← the roofline's "35.5% of the memory roof"
```

So the 35.5% is mostly a **duty-cycle** effect: the kernels themselves come
close to the bandwidth roof, but they run less than half of the time. The rest
is the GPU waiting on the host.
- The ~106.5 GB/s is **derived weight traffic, not measured DRAM bandwidth**.
- The ~247–255 GB/s per-kernel figures are also derived.
- Only Nsight Compute can measure real DRAM throughput.

## 11. Nsight Compute decision

**Not next. Run a CPU-side experiment first.** About two-thirds of each
profiled token is the GPU waiting on the host. Nsight Compute can only explain
the busy third.

**First: the CPU/system experiment.**
- **What:** repeat this exact Nsight Systems run with CPU sampling enabled.
  Use the same pinned image, the unchanged server and client, and 20 + 30
  requests.
- **Setup:** lower `kernel.perf_event_paranoid` on the throwaway VM. This
  changes the VM, not Charon, and needs your approval.
- **Question it answers:** whose host time sits in the ≈ 20 µs per kernel
  outside `cudaLaunchKernel`? The candidates are the Python interpreter (the
  HF `generate()` loop and `nn.Module` calls), the PyTorch dispatcher, or the
  CUDA driver.
- **Cost (ESTIMATED, NOT MEASURED):** about 0.4 GPU-hours.

**Then: Nsight Compute on 2 kernels, 3 instances.**
1. **`gemvx (int)6`, the gate_proj/up_proj instance:** 64% of decode GPU time
   for kernel 6 as a whole. These are the ~110 µs GEMVs, two per layer.
2. **`gemvx (int)6`, the LM-head instance** (grid 37,984): the single longest
   kernel, ≈ 1.83 ms per token.
3. **`gemvx (int)7`, the down_proj instance:** 23% of decode GPU time.

Select instances with `--kernel-name` regex plus `--launch-skip` and
`--launch-count`. Check the options on the installed ncu 2025.2.0 first
(`ncu --list-sections`).

| Metric needed | Why |
|---|---|
| Achieved DRAM bandwidth (`dram__bytes_read.sum.per_second`, % of peak) | Tests the derived ≈ 250 GB/s |
| Memory throughput + L2 hit rate (Memory Workload Analysis) | Confirms weights stream from DRAM, not cache |
| Achieved occupancy (Occupancy section) | Hypothesis F |
| SM utilization / SM throughput (Speed of Light) | Compute headroom |
| Warp stall reasons (Warp State Statistics) | Memory latency vs bandwidth |
| FLOP / instruction throughput | Confirms the tiny arithmetic load |
| Roofline chart (Speed of Light roofline) | Places each kernel on the measured roofline |

## 12. Final summary

GPU timeline: Busy only ≈ 34% of each profiled token, about 1,197 idle gaps per token, in an identical pattern every token.
Dominant behavior: About 1,185 kernels per token issued one by one from one Python thread, roughly every 28 µs, while most kernels run 1–3 µs.
Most likely bottleneck: Host-side orchestration (Python/PyTorch per-kernel overhead plus kernel launch cost) starving the GPU; the GEMVs themselves look bandwidth-limited (derived).
Confidence: High that the GPU is host-starved; medium on the split between Python, dispatcher and launch; medium-low on GEMV bandwidth.
Next experiment: Re-run the same Nsight Systems trace with CPU sampling enabled (VM setting, needs approval); then Nsight Compute on the gate/up, LM-head and down GEMV instances.

---

## 13. How to read the companion page (`decode-deep-dive.html`)

**A. "Ten tokens, live" (animation).**
- *What it shows:* the real trace for steps 60–69, replayed slowly.
  - Grey ticks on the top lane: the CPU launching kernels.
  - Colored blocks on the bottom lane: the GPU running them. Blue is GEMV,
    orange is elementwise, and so on.
  - Hatching: the GPU idle.
  - Red outlines: stream syncs.
  - Thin lines: each launch joined to its kernel.
- *What it tells you:* the top lane is almost never empty; the CPU is always
  busy. The bottom lane is mostly hatched; the GPU is often idle. The joining
  lines are near-vertical, so each kernel starts the moment it is launched.
  Nothing is waiting in a queue.

**B. "Anatomy of one token" (animation).**
- *What it shows:* a cursor walks through the 64 setup kernels, the 28 layer
  blocks, and the LM head. For each section, the bar pair compares wall time
  with GPU-busy time.
- *What it tells you:* every layer looks the same: ≈ 1.37 ms of wall for
  ≈ 0.45 ms of GPU work. The token setup is almost all waiting, at 1.57 ms for
  0.12 ms. Only the LM head keeps the GPU busy, because it is one long kernel.

**C. "The CPU issues slower than the GPU finishes" (two histograms).**
- *What it shows:* the time between kernel launches on the CPU, next to how
  long each kernel runs on the GPU.
- *What it tells you:* most kernels run in 1–3 µs, but the CPU sends one about
  every 28 µs. Whenever the kernels are shorter than the launch interval, the
  GPU must wait. That is the core of hypothesis 1.

**D. "Where the decode thread's time goes" (stacked bars).**
- *What it shows:* the thread's time per step, split into inside CUDA calls
  and outside them, next to GPU-busy time.
- *What it tells you:* most host time is outside the CUDA runtime. That points
  more at Python and dispatcher overhead than at the launch call. It is a
  profiled split, so read it as a direction, not a size.

**E. "Top 10 kernels" (bar chart + table).**
- *What it shows:* GPU time by kernel, with the exact Nsight names on hover
  and in the table.
- *What it tells you:* two cuBLAS GEMV kernels are 87% of GPU time. Everything
  else is small. If you profile kernels, start there.

**F. "Syncs per token" (dot timeline).**
- *What it shows:* where each `cudaStreamSynchronize` falls in the 10 tokens,
  and how long it is.
- *What it tells you:* there are two per token, in the same places every time.
  The longer one, at the token boundary, is the CPU waiting for the LM head. In
  total they are tiny.

**G. "Prefill vs decode" (paired bars).**
- *What it shows:* wall time, GPU-busy time and kernel count for the two phases.
- *What it tells you:* with short prompts, prefill is just a slightly bigger
  decode step. The decode pattern is what matters.

**H. "Kernels near the memory roof, a GPU that is often idle" (bandwidth bars).**
- *What it shows:* the derived weight-streaming rate of each GEMV while it
  runs, against the 300 GB/s datasheet line and the 106.5 GB/s token average.
- *What it tells you:* the big GEMVs come close to the roof while they run.
  The low average comes from how rarely they run, which is the duty-cycle
  reconciliation in §10.

**I. Hypotheses and decision.**
- *What it shows:* confidence meters for hypotheses D, C and B, and the next
  experiment.
- *What it tells you:* fix the evidence gap before the kernels. Find out who
  owns the host time; only then measure the GEMVs with Nsight Compute.
