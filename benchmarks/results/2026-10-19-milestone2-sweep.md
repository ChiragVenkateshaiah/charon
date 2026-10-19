# Milestone 2 — concurrency sweep, naive server, concurrency 1 → 64

**Raw data:** [`2026-10-19-milestone2-sweep/`](2026-10-19-milestone2-sweep/) — the
driver output
[`sweep-20261019T155446Z.json`](2026-10-19-milestone2-sweep/sweep-20261019T155446Z.json)
(schema `charon-sweep-v1`, `complete: true`; 7 levels × 3 runs × (max(20, N) warmup
+ 100 measured), 128 forced output tokens; 2,688 request records and every
`nvidia-smi` sample committed in full), plus the server log, driver log,
`/healthz`, git revision and on-box environment captures (`env/`).

Methodology: `benchmarks/methodology.md`, "Concurrency sweep (Milestone 2)",
decisions 1–10 as amended 2026-10-19. Design: ADR-0003. Pre-run validation:
`docs/milestone-2-sweep-validation.md`.

## Environment

| | |
|---|---|
| Server | `serving/naive_server.py`, byte-identical to Week 1 (decision 8) — plain `transformers.generate`, one generation at a time behind `_GEN_LOCK`, greedy, no batching / compilation / quantization. FastAPI sync handler → anyio thread pool, default limit 40 threads |
| Model | `Qwen/Qwen2.5-1.5B-Instruct` @ `989aa7980e4cf806f80c7fef2b1adb7bc71aa306`, bf16, 3.087 GB weights (`weights_vram_bytes`) |
| GPU | NVIDIA L4, 23034 MiB, driver 580.173.02, power limit 72 W, max SM clock 2040 MHz, max mem clock 6251 MHz, PCIe reported Gen3 ×16 at idle (`env/nvidia-smi-query.csv`) |
| Image | `common-cu129-ubuntu-2204-nvidia-580-v20260818` (same pinned image as Week 1) |
| Stack | Python 3.14.8, torch 2.13.0+cu130, transformers 5.16.1, uv 0.13.1, `uv sync --locked` |
| Host | GCP `g2-standard-4` (4 vCPU, 16 GB), **spot**, **`us-central1-a`** (Week 1: `us-central1-c`, stocked out this session) |
| Code | `ef5e6cf` (`git-rev.txt`) |
| Driver | `benchmarks/sweep_driver.py`, closed loop on the same host as the server (localhost), defaults; `nvidia-smi` sampled at 200 ms |
| Run order | seed `2893316706`; rounds `[32,4,1,8,64,2,16]`, `[32,1,8,64,4,16,2]`, `[4,2,8,64,32,16,1]` (decision 9) |
| Prompt set | `benchmarks/prompts/baseline.json`, as Week 1 |

## Measured

Every number below is measured in this session. Values are the median across the
three runs of each per-run statistic; "spread" is the cross-run spread
(`(max − min) / median`) used by the gates (decision 6).

### Throughput and client latency (primary curve, decision 3)

| c | req/s [dec. 4] | output tok/s [dec. 4] | spread req/s | whole-run req/s (supplementary) | client e2e p50 | p95 | p99 | spread p50 | spread p99 |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 0.2659 | 34.04 | 0.4% | 0.2662 | 3.764 s | 3.808 s | 3.820 s | 0.6% | 0.5% |
| 2 | 0.2653 | 33.96 | 0.5% | 0.2655 | 7.533 s | 7.604 s | 7.636 s | 0.5% | 1.2% |
| 4 | 0.2659 | 34.04 | 1.9% | 0.2657 | 15.041 s | 15.177 s | 15.257 s | 2.0% | 1.8% |
| 8 | 0.2654 | 33.98 | 0.5% | 0.2655 | 30.112 s | 30.359 s | 30.417 s | 0.4% | 0.9% |
| 16 | 0.2656 | 33.99 | 0.5% | 0.2656 | 60.269 s | 60.432 s | 60.447 s | 0.5% | 0.3% |
| 32 | 0.2649 | 33.91 | 2.4% | 0.2651 | 120.734 s | 121.009 s | 121.047 s | 2.4% | 3.0% |
| 64 | **0.2953 ⚠** | **37.79 ⚠** | 0.2% | **0.2654** | 199.787 s | 282.376 s | 282.377 s | 0.3% | 0.3% |

⚠ **c = 64 throughput under decision 4 is distorted by bursty completion delivery
and overstates the server's rate** — see Analysis §2. It is kept here, as the
methodology requires, next to the whole-run figure. "Whole-run req/s" = all
requests of the run, warmup included, ÷ (last `t_end` − first `t_start`); it is a
supplementary figure, reported per the 2026-10-19 amendment, not a replacement for
decision 4.

### Server-reported timings (separate table, decision 3)

Server TTFT and TPOT exclude time spent waiting for the server's generation lock.

| c | TTFT p50 | TTFT p95 | TTFT p99 | TTFT p99 per run | spread TTFT p99 | TPOT p50 | TPOT p99 | server e2e p50 |
|---|---|---|---|---|---|---|---|---|
| 1 | 32.7 ms | 33.7 ms | 36.4 ms | 39.4 / 36.4 / 33.5 | **16.3%** | 29.34 ms | 29.78 ms | 3.761 s |
| 2 | 35.2 ms | 43.7 ms | 44.7 ms | 44.3 / 44.7 / 45.1 | 1.7% | 29.34 ms | 29.92 ms | 3.763 s |
| 4 | 35.1 ms | 42.7 ms | 44.7 ms | 45.2 / 44.5 / 44.7 | 1.5% | 29.29 ms | 29.99 ms | 3.757 s |
| 8 | 35.2 ms | 43.7 ms | 44.4 ms | 44.1 / 44.4 / 46.8 | 6.2% | 29.35 ms | 29.96 ms | 3.763 s |
| 16 | 35.2 ms | 40.5 ms | 44.4 ms | 43.7 / 44.4 / 44.9 | 2.8% | 29.35 ms | 29.89 ms | 3.763 s |
| 32 | 35.0 ms | 43.8 ms | 44.6 ms | 45.5 / 44.6 / 44.2 | 2.9% | 29.41 ms | 30.03 ms | 3.772 s |
| 64 | 34.1 ms | 43.8 ms | 56.5 ms | 56.4 / 56.5 / 56.8 | 0.6% | 29.38 ms | 29.97 ms | 3.770 s |

### GPU and memory

| | value |
|---|---|
| GPU utilization (`nvidia-smi`, in-flight windows), p50 per run | 51–52% at every level (max 53–54%) |
| `nvidia-smi mem.used`, max per run | 3776–3920 MB at every level |
| `peak_vram_bytes` (server, `torch.cuda.max_memory_allocated`), max per run | 3.370–3.438 GB at every level |

### Gates and problems

21 of 21 runs complete; 0 failed requests; 0 re-runs; no validation problems; no
warnings. All p50 and throughput spreads ≤ 2.4%, under the 10% gate. All seven
levels are `usable_for_knee` by the driver's rules — but see §2 for why the c = 64
throughput value is not used for the knee claim below.

## Analysis

### 1. The knee is at concurrency 1: the server is fully serialized

Throughput is flat from c = 1 to c = 32 at 0.265–0.266 req/s (~34 output tok/s),
inside the cross-run spread. Adding concurrency adds no throughput, only waiting.

The raw records show why, directly. For every run at every level, the sum of the
server's per-request generate times equals the run's wall time
(sum / wall = 0.9991 at c = 1, 0.9998–0.9999 at c ≥ 2). The server ran exactly one
generation at a time, back to back, and was never idle at c ≥ 2. At c = 1 the 0.09%
idle is the client's turnaround between one response and the next send (~4 ms per
request). This is `_GEN_LOCK` doing what the server's design says it does, now
shown with measured data rather than inferred from the code.

Client latency is the queue: client e2e p50 ≈ N × 3.76 s up to c = 32
(7.53 / 15.04 / 30.11 / 60.27 / 120.73 s = 2.00 / 4.00 / 8.00 / 16.0 / 32.1 × the
c = 1 value). p99 stays within ~0.3% of p50 at c ≤ 32: each request waits for the
N − 1 ahead of it and then gets the same ~3.76 s of service.

The GPU does not change across levels: utilization is 51–52% busy-time at c = 1 and
at c = 64, and memory use is flat. More concurrent clients give the GPU no more
work per unit time, because they cannot reach it together. The lever that would
change this is batching (Week 3); how much it would help is a **hypothesis** until
measured.

### 2. c = 64: bursty completion delivery distorts the decision-4 window

At c = 64 the server stayed fully serialized (sum of generate times = wall time,
616.8 / 616.9 s in run 1), so its rate was the same as at every other level:
whole-run 0.2658 / 0.2653 / 0.2654 req/s. Decision 4 measured 0.2953 / 0.2953 /
0.2946 req/s, ~11% higher.

The cause is in when the client received completions. In all three runs, the first
125 completions reached the client in **5 bursts of 25**, one burst every ~94 s
(≈ 25 × 3.76 s); the remaining 39 arrived one at a time:

| run | burst arrival times (s from first send) | measured requests in each burst | then |
|---|---|---|---|
| 1 | 93.9, 187.8, 281.6, 375.7, 469.8 | 0, 0, 11, 25, 25 | 39 singly, to 616.9 s |
| 2 | 94.5, 188.8, 282.9, 377.2, 471.2 | 0, 0, 11, 25, 25 | 39 singly, to 618.1 s |
| 3 | 94.0, 188.0, 282.0, 376.2, 470.4 | 0, 0, 11, 25, 25 | 39 singly, to 618.0 s |

The first measured completion arrives inside the third burst, so the window opens
at ~282 s. That burst delivers 11 measured results whose server work was done over
the ~94 s before the window opened. The window therefore credits ~100 requests' work
(~376 s of server time) to ~335 s of wall time. Decision 4 assumed completions reach
the client about when the server finishes them; at c = 64 that did not hold.

**Mechanism: not established.** The bursts happen only while more than 40 requests
are in flight — the anyio thread-pool limit — and stop once 39 remain (~470 s). No
burst occurred at c ≤ 32, where in-flight never exceeds 40. A link to the 40-thread
limit is a **hypothesis**, not tested. The c = 64 client latencies are real client
experience of this server and are reported as measured; only the decision-4
throughput value is distorted.

The c = 64 latency distribution also differs from the c ≤ 32 pattern: p50 199.8 s
but p95/p99 282.4 s, mean 220 s, against 64 × 3.77 s ≈ 241 s for a strict FIFO
queue. Requests were not served in send order at c = 64. Why is not established;
it plausibly has the same cause as the bursts (**hypothesis**).

### 3. Server TTFT hides the queue

Server TTFT p50 is ~33–35 ms at every level while client latency grows to minutes.
This is by design (decision 3: server TTFT excludes lock wait), and it is the
reason decision 3 keeps the two apart: a server-side TTFT dashboard on this server
would show a healthy ~35 ms while users wait 2 minutes at c = 32.

Server TTFT p99 does move: 36.4 ms at c = 1, ~44.5 ms at c = 2–32, 56.5 ms at
c = 64. p95 moves similarly (33.7 → ~43 ms). The cause is not established. One
**hypothesis**: CPU contention from threads waiting on the lock on a 4-vCPU host
slows the prefill launch path. A profiler trace at c ≥ 2 would test it.

### 4. c = 1 against Week 1

| metric (p50 unless noted) | Week 1 (2026-08-28) | this sweep, c = 1 | change |
|---|---|---|---|
| TTFT | 32.1 ms | 32.7 ms | +2% |
| TTFT p99 | 35.0 ms | 36.4 ms | +4% |
| TPOT | 29.0 ms | 29.3 ms | +1.3% |
| server e2e (128 tok) | 3.713 s | 3.761 s | +1.3% |
| decode tok/s | 34.50 | 34.06 | −1.3% |
| GPU utilization | 53% | 52% | −1 pt |
| peak VRAM (`max_memory_allocated`) | 3.106 GB | 3.370–3.438 GB | +0.26–0.33 GB |

The c = 1 level reproduces Week 1 to within ~1–2% on latency and throughput. The
session differs from Week 1 in the zone (`us-central1-a` vs `us-central1-c`, so a
different physical L4) and in Python (3.14.8 here; not recorded in Week 1). The
~1.3% shift cannot be attributed to either from this data.

Peak VRAM is higher than Week 1 at every level and differs between runs.
`max_memory_allocated` is a process-lifetime peak and this server process served
all 21 runs, including c = 64, so the figure depends on run history; Week 1's
process served c = 1 only. Not investigated further.

### 5. The Week 1 TTFT p99 spread recurs at c = 1

c = 1 TTFT p99 spread is 16.3% (39.4 / 36.4 / 33.5 ms), against 18% in Week 1.
p99 at n = 100 is the second-largest sample, so two slow prefills per run decide
it. At c ≥ 2 the spread is ≤ 6.2%. The recurrence suggests this is a property of
the setup at c = 1, not a one-off; the cause is still unexplained. p99 is reported,
not gated (decision 6), so this does not fail the run.

## What this does not tell us

- **Batched serving.** This is the naive server only. Week 3's batching is the
  next variable; no number here predicts its throughput.
- **The burst mechanism at c = 64.** Observed and characterized; cause untested.
- **Longer inputs or outputs.** Fixed 128 output tokens and 41–49-token prompts.
  The per-request service time (~3.76 s) sets every number here.
- **Network clients.** The driver ran on the same host (localhost). Remote clients
  would add network time to client e2e.
- **Open-loop load.** A closed loop never queues more than N; arrival-rate
  (open-loop) behaviour is a different experiment.

## Methodology notes

- All ten decisions followed as written; no re-runs were needed (decision 5).
- **Decision 4 at c = 64:** reported as measured, marked distorted, with the
  whole-run figure beside it (owner decision, 2026-10-19; amendment recorded in
  `benchmarks/methodology.md`). A change to decision 4 itself is listed there as
  not yet decided, to settle before Milestone 3.
- **Session-start drift.** The first two runs of the session (c = 32 run 1 and
  c = 4 run 1, round 1) were 2.2% and 1.9% slower than their levels' other runs
  (whole-run 0.2574 and 0.2609 req/s; server work, not idle time). Both are within
  the gate. Decision 9's shuffled order turned this into spread rather than into an
  apparent effect of concurrency.
- Server log: 2,688 `POST /generate`, matching the driver's record count; one
  unauthenticated Hugging Face Hub warning at model load (model revision pinned).
- **Sessions and cost.** Three GPU sessions on 2026-10-19; only the third produced
  results.
  - Session 1 (`us-central1-c`): spot preemption ~1 min after creation. The script
    reported 0.29 h, which was wrong (it measured to the end of a hung `scp`);
    fixed in `35aa324`.
  - Session 2 (`us-central1-c`): bootstrap failed (uv chose CPython 3.15, for
    which torch 2.13.0 has no wheel). 0.08 h. Fixed in `ef5e6cf` (Python pinned to
    3.14.8).
  - Session 3 (`us-central1-a`): this sweep. Instance lifetime 2.92 h
    (15:50:15 → 18:45:19 UTC); driver time 2.82 h (15:54:47 → 18:43:57 UTC).
  - Total ≈ 3.0 instance-hours against 3.2 approved. Cost **ESTIMATED, NOT
    MEASURED**: ~₹127 at ₹41.9/h spot list price, ~₹208 at the ₹69/h observed
    effective rate (list price: `docs/gcp-setup.md`; observed rate: owner-supplied
    2026-10-05, `docs/worklog.md`; the two rates are not reconciled).
