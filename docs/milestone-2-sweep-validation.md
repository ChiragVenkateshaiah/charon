# Milestone 2 — concurrency sweep: local validation

- **Date:** 2026-10-18
- **Scope:** local, read-only review of the planned Milestone 2 sweep (ADR-0003,
  rule 11, GPU session 1). No GPU, no cloud, no model, no measurement.
- **Not a result.** Nothing in this file is a benchmark number (ADR-0001). Every
  runtime and cost figure below is an estimate and is labelled as one.
- **Tests:** `benchmarks/tests/test_sweep_driver_preflight.py`, how to run in
  `benchmarks/tests/README-sweep-preflight.md`.

Labels used throughout: **VERIFIED** (read in a source file or reproduced from
committed data), **ESTIMATE** (arithmetic on verified inputs plus a stated
assumption), **INFERENCE** (reasoning from code or docs, not observed),
**UNRESOLVED** (not known; needs a check or a decision).

---

## Decision

**NOT READY** for GPU session 1.

Blockers (all local, none needs a GPU):

1. **No sweep driver exists.** `benchmarks/baseline_runner.py` is concurrency-1
   only, and no other driver or adopted tool is in the repo.
2. **Week 2 methodology is not fixed.** `benchmarks/methodology.md` is a stub,
   and its "Not yet decided" list is still open. The sweep also adds decisions
   that are not on that list (warmup at concurrency above 1, reported latency
   metric, throughput window, failure policy, p99 spread handling).
3. **Thread-pool behaviour is unchecked** for the locked FastAPI / anyio /
   uvicorn versions. At concurrency 64 it decides where requests queue.
4. **Owner approval** of the sweep and its estimated GPU-hours has not been
   given (ADR-0003 follow-ups).

The TTFT p99 preflight step is **done and bounded** (below). It is not a
blocker.

**Update 2026-10-18 (later).** Blockers 1 and 2 are cleared in the working
tree, not yet committed: the owner fixed the Week 2 decisions in
`benchmarks/methodology.md` ("Concurrency sweep (Milestone 2)"), and
`benchmarks/sweep_driver.py` implements them, with group C passing (26 tests,
no skips). Still **NOT READY**: blockers 3 (thread pool) and 4 (owner
approval) remain. The ~3 GPU-hour figure below predates the max(20, N)
warmup decision, which adds 168 requests per sweep: about **3.2 GPU-hours**
planning figure (ESTIMATE), plus ~0.17 h per re-run at most. The
"Unresolved questions" below were answered by those decisions; the list is
kept as asked.

**Update 2026-10-19.** Blocker 3 cleared: thread pool is 40 (F7). Blocker 4
cleared: the owner approved 3.2 GPU-hours. The session is
`scripts/sweep-session.sh` (unprofiled; instance lifetime capped at 192 min;
[M5] re-runs start only if one can finish inside the cap). With the load
estimated at ~2.77 h, re-runs are unlikely to fit (ESTIMATE).

---

## Findings

| # | Finding | Label | Source |
|---|---|---|---|
| F1 | The existing runner has no concurrency model: one request at a time. | VERIFIED | `benchmarks/baseline_runner.py:4-8`, `run_once` at `:275` |
| F2 | The runner aborts the whole run on the first HTTP error (`RuntimeError`) or timeout (uncaught `OSError`). Nothing is recorded for the failed request. | VERIFIED (code + group A tests) | `baseline_runner.py:73-90`, `run_once` |
| F3 | The runner gates only on **p50** spread; p95/p99 spread is not checked. | VERIFIED | `baseline_runner.py:321` |
| F4 | Percentiles are nearest-rank. At n = 100, p99 is the second-largest sample. | VERIFIED (code + test) | `baseline_runner.py:183-189` |
| F5 | The server serializes `model.generate` behind a process-wide `threading.Lock`. Tokenization and the chat template run outside the lock. | VERIFIED | `serving/naive_server.py:42`, `:159` |
| F6 | `/generate` is a synchronous `def`, so FastAPI runs it in a worker thread pool. The Nsight trace shows decode on an `AnyIO worker th` thread. | VERIFIED | `naive_server.py:137-138`; `benchmarks/profiles/2026-10-06-week1-nsys/decode-investigation.md:46` |
| F7 | **Resolved 2026-10-19.** A sync `def` endpoint runs via `starlette.concurrency.run_in_threadpool` → `anyio.to_thread.run_sync` on the default `CapacityLimiter(40)`; its wait queue is FIFO. `naive_server.py` does not change it. So at c=64, at most 40 requests are in worker threads (1 in `_GEN_LOCK`, the rest waiting on the non-FIFO lock) and the other 24 wait in anyio's FIFO queue on the event loop. Confirmed by running a stand-in app (same structure, sleep instead of the model) under the locked stack: 32 handlers in flight at c=32, 40 at c=64. Client-side concurrency [M1] is unaffected; all queue time is in client latency. | VERIFIED (source + stand-in, not the real server) | locked packages in a scratchpad venv: `fastapi/routing.py`, `starlette/concurrency.py:32`, `anyio/_backends/_asyncio.py:3093` |
| F8 | Server-side TTFT starts at `t0`, taken **inside** the lock. It excludes queue wait, HTTP and the chat template. `t0` is `perf_counter`, not wall time. | VERIFIED | `naive_server.py:163`, `:186` |
| F9 | So server TTFT should stay near its concurrency-1 value at every level, and queueing shows only in client-side latency (`t_end − t_start`). The responses are not streamed, so client-side TTFT cannot be measured. | INFERENCE (supported by group B on a stub) | F8; test `test_queue_wait_shows_in_client_latency_not_server_time` |
| F10 | Python's `threading.Lock` does not guarantee FIFO wake-up order. At concurrency above 1, which waiting request runs next is not defined. Client latency tails at high concurrency may reflect lock scheduling, not only queue depth. | INFERENCE (Python docs; not observed here) | `threading.Lock.acquire` documentation |
| F11 | The server is started with default uvicorn options (one worker). | VERIFIED | `scripts/profile-nsys.sh:42` |
| F12 | The plan allows a hand-rolled or an adopted load generator. | VERIFIED | `docs/phase-1-plan.md:104-106` |
| F13 | The plan's levels are 1, 2, 4, 8, 16, 32, 64. | VERIFIED | `docs/phase-1-plan.md:108` |
| F14 | `benchmarks/methodology.md` lists load generator, prompt set, hardware block and sweep levels as "Not yet decided". | VERIFIED | `benchmarks/methodology.md:29-38` |

---

## Request count and runtime (ESTIMATE)

**Verified inputs** (`benchmarks/results/baseline-20260828T172338Z.json`):
`config` = 3 runs × (20 warmup + 100 measured) = 360 requests, 128 output
tokens; `started_at` 17:23:38.704 → `finished_at` 17:45:56.993 = **1,338.3 s**,
so **3.717 s per request** of wall time, all overhead included.

| Quantity | Value | Assumption |
|---|---|---|
| Requests per level | 360 | Same 3 × (20 + 100) as Week 1 |
| Requests per sweep | 2,520 | 7 levels |
| Load time per level | ≈ 22.3 min | Serialized server keeps per-request time at ~3.72 s at every level (F5) |
| Load time per sweep | ≈ 9,368 s ≈ **2.60 h** | As above, no idle gaps between requests |
| Instance overhead | ≈ 0.3–0.4 h | From past sessions (0.53 GPU-hours, `docs/worklog.md:220`; ~1.1, mostly stockout retries, `:281`); not measured for this session |
| Planning figure | ≈ **3 GPU-hours** | Sum, rounded |
| Cost | ≈ ₹125 at ~₹41.9/h list; ≈ ₹205 at ₹69/h observed | The two rates are **unreconciled** (worklog) |

**Assumptions to check before the session:**

- The lock keeps the GPU busy back to back. Group B shows this for a stub only.
  On the real server, the work outside the lock (HTTP, template, tokenizer,
  ~3.3 ms before the first kernel per `decode-investigation.md:168`) overlaps
  with another request's `generate` only if a second request is already
  waiting. At concurrency 1 it does not overlap. This is why the
  concurrency-1 level is expected to be slightly slower per request than the
  others (INFERENCE).
- If the thread pool is smaller than 64 (F7), requests above the pool size
  wait before the lock. The total time should not change (INFERENCE), but
  this is unverified.

---

## Concurrency, queueing, timeouts and failures

**Queue wait at concurrency 64 (ESTIMATE).** With a FIFO queue, a request
waits for the ~63 requests ahead of it: 63 × 3.717 s ≈ **234 s**. The
default `--request-timeout` is 600 s (`baseline_runner.py:439`), so ~2.6×
margin under FIFO. Lock wake-up is **not** FIFO (F10), so a single request
can wait longer than 234 s. No bound on that is known. A 600 s timeout could
fire at concurrency 64 (UNRESOLVED).

**Consequences for the driver:**

- A timeout or HTTP error must be **recorded and counted**, not raised (F2).
  One failure must not lose the other records of the level.
- A failed request is **never retried**. A retry changes the load and
  duplicates work. Group C test `test_request_accounting_and_no_retries`
  checks this.
- A level with any failure is **flagged incomplete**. Whether its numbers can
  be reported, or the level must be re-run, is a **methodology decision**
  (UNRESOLVED).
- Concurrency must be **held at N**, closed loop, and **never exceeded**.
  Group C `test_concurrency_limit_respected_and_reached`.

**Warmup at concurrency above 1 (UNRESOLVED).** "First 20 requests" is
ambiguous when 64 are in flight and lock order is not FIFO: first 20 *sent*
and first 20 *completed* are different sets. The tests check only the count
(and exclusion at concurrency 1). The definition is the owner's to fix in
`methodology.md`.

**Throughput window (UNRESOLVED).** Warmup requests can still be queued or
running while measured requests complete. The window over which throughput is
computed (for example, first measured start to last measured end, or
completions only) changes the number at high concurrency. Methodology
decision.

---

## Measurement-integrity requirements

For the sweep to clear ADR-0001's gate (ADR-0003 rule 7), every level must
meet all of these:

1. **Unprofiled.** No Nsight or other profiler attached in GPU session 1
   (ADR-0003 rule 11).
2. **Throughput and p50/p99 latency per level,** with both requests/s and output
   tokens/s (`docs/phase-1-plan.md` vocabulary).
3. **Latency metric named.** Client-side end-to-end (`t_end − t_start`) and
   server-side TTFT / TPOT are reported separately and never mixed (F8, F9).
4. **Raw output committed,** per request: sequence number, warmup flag, ok /
   error, `t_start`, `t_end`, server payload, plus GPU samples (methodology
   rule 7).
5. **Fixed token counts** (`min_tokens = max_tokens = 128`) and the same prompt
   set as Week 1 (methodology rule 1).
6. **Three runs per level,** with spread reported for p50 **and** p99 (rule 4;
   F3). At n = 100, p99 is the second-largest sample (F4), so the p99 gate is
   sensitive to two events per run. How to treat it is a methodology decision.
7. **Environment recorded** each session, including Python version (methodology
   rule 5; worklog notes Python was not recorded in Week 1).
8. **Completeness checked** before analysis: expected record count, no
   duplicate sequence numbers, failure count reported.

Useful additions with no GPU cost (from the TTFT preflight): record the
server's `t0` in wall time (so TTFT windows can be aligned with GPU samples),
keep `itl_s`, and write host timestamps into the raw output.

---

## Required implementation changes, by importance

1. **Write the sweep driver** (or adopt a tool) that holds concurrency N closed
   loop and records every request, including failures (F1, F2). Leave
   `baseline_runner.py` unchanged; it produced the committed Week 1 result.
2. **Per-request failure and timeout accounting,** no retries, incomplete-level
   flag (F2, queue-wait section).
3. **Completeness validation** before any summary: count, duplicates, failures.
4. **Summaries over measured, successful requests only,** with failures counted
   separately.
5. **p99 spread check** next to p50 (F3).
6. **Client-side and server-side latencies kept separate** in the output (F9).
7. **Timeout chosen from the concurrency-64 estimate** with explicit margin, and
   recorded in the output.
8. **Server `t0` in wall time** in the payload. This changes
   `serving/naive_server.py`, which the plan treats as the fixed Week 1
   server. It is an owner decision whether a payload-only change is
   acceptable or whether this waits.

---

## Local preflight checklist

| Item | State on 2026-10-18 |
|---|---|
| TTFT p99 step (ADR-0003): explained or bounded | **Done — bounded** (see below) |
| Groups A and B of the preflight tests pass | **Done** — 7 passed |
| Group C passes against the real driver, zero skips | **Done (uncommitted)** — 19 passed |
| Thread-pool size for the locked versions checked | **Done** — 40 threads, FIFO limiter (F7) |
| `methodology.md` Week 2 decisions written | **Done (uncommitted)** — decisions [M1]–[M8] |
| Timeout value chosen and justified | **Done** — 1800 s [M7] |
| Dry run of the driver against a stub server, full 7-level schedule with short service time | **Done** — 2 ms stub, 2,688 requests received (= planned, no retries), 21 clean runs; not a result |
| Owner approval of the sweep and its estimated GPU-hours | **Open** |

---

## TTFT p99 preflight result (from committed raw data)

Source: `benchmarks/results/baseline-20260828T172338Z.json`, fields
`raw.requests[].{run, index, is_warmup, prompt_index, t_start, t_end,
client_rtt_s, server.ttft_s, server.tpot_s, server.itl_s, server.prompt_tokens}`
and `raw.gpu_samples[].{t, util_gpu_pct, clock_sm_mhz, power_w, temp_c}`.

- **Explained (VERIFIED, reproduced):** per-run TTFT p99 = 35.048 / 41.097 /
  34.761 ms, spread 0.1808. Run 2's p99 comes from **3 of its 100** measured
  requests (40.7–41.2 ms, positions 20 / 59 / 70). No request in runs 1 or 3
  is above 36 ms.
- **Bounded or ruled out (at the resolution available):** not warmup bleed,
  not prompt identity or length, not client / HTTP overhead or gaps between
  requests, not a slowdown of the whole request (TPOT normal), no sustained
  clock throttling (`clock_sm_mhz` 2040 in every sample). Size: about +6–9 ms
  on 1% of requests.
- **Unknown:** the cause. Host CPU, OS / VM scheduling, or a GPU / driver
  event shorter than the 200 ms GPU sampling interval are all possible. Not
  established.
- **Limits:** no host metrics; `t0` not in wall time; 200 ms GPU sampling vs a
  ~32–41 ms TTFT window; 3 events only; runs sequential, not interleaved.

The sweep's concurrency-1 level re-tests this as a control.

---

## Test results (2026-10-18, this machine: Python 3.14.4, stdlib only)

| Run | Command | Result |
|---|---|---|
| Repo as-is | `python3 -m unittest benchmarks/tests/test_sweep_driver_preflight.py -v` | **Ran 14, OK, skipped 7.** Groups A + B: 7 passed. Group C: 7 skipped (no driver). One `ResourceWarning` from `baseline_runner.post_generate` (unclosed `HTTPError`), not a failure. |
| Group C vs scratchpad prototype | `CHARON_SWEEP_DRIVER=<scratchpad>/sweep_driver_proto.py python3 -m unittest …SweepDriverContract -v` | **Ran 7, OK.** The prototype is throwaway, outside the repo, and not a proposed implementation. It only shows that the tests can pass. |
| Group C vs broken mutant | same, with a copy that exceeds concurrency by 1, mislabels HTTP errors and skips duplicate detection | **Ran 7, FAILED 3** — exactly the three injected defects. Shows the tests can fail. |

| Driver, full suite | `python3 -m unittest benchmarks/tests/test_sweep_driver_preflight.py` | **Ran 26, OK** (3 repeats). |
| Driver after 2026-10-19 amendments ([M6] throughput gate, [M9], [M10]) | same | **Ran 29, OK.** Four more single-rule mutants (no shuffle, consecutive order, no throughput gate, indented output) **each FAILED**. Full 7-level dry run on the 2 ms stub: 2,688 requests received, seed and schedule recorded. |
| Driver vs 6 mutants (scratchpad) | one decision broken per copy: warmup = 20 only, throughput window from first start, no re-run, gate on p99, seq taken outside the lock, server e2e as client latency | **Each FAILED** (1–2 failures each). |

Not testable locally: real thread-pool limit, real lock fairness, real
latency at concurrency 64, GPU behaviour under sustained queueing.

---

## Unresolved questions (owner)

1. Hand-rolled driver or adopted load generator (F12)? Group C assumes a
   hand-rolled Python driver.
2. Warmup definition at concurrency above 1.
3. Reported latency: client end-to-end, server TTFT / TPOT, or both (both is
   recommended above, but the choice is the owner's).
4. Throughput window definition.
5. Failure policy: re-run a level with any failure, or report it flagged.
6. p99 spread handling at n = 100 (F4).
7. Whether a payload-only change to `naive_server.py` (wall-time `t0`) is
   acceptable before the sweep.

---

## Evidence paths

- `benchmarks/baseline_runner.py` — `:4-8`, `:73-90`, `:183-189`, `:212-218`,
  `:275-305`, `:321`, `:439`
- `serving/naive_server.py` — `:42`, `:137-138`, `:159`, `:163`, `:186`
- `scripts/profile-nsys.sh:42`
- `benchmarks/results/baseline-20260828T172338Z.json` — `config`,
  `started_at`, `finished_at`, `summary.per_run`, `raw.requests`,
  `raw.gpu_samples`
- `benchmarks/results/2026-08-28-week1-baseline.md:33-37`
- `benchmarks/profiles/2026-10-06-week1-nsys/decode-investigation.md:46`, `:168`
- `benchmarks/methodology.md:29-38`
- `docs/phase-1-plan.md:102-116`
- `docs/worklog.md:220`, `:281`
- `adr/0003-milestones-are-authoritative.md` — rules 7, 11; *The smallest
  qualifying serving measurement*
- `uv.lock` — anyio 4.14.2, fastapi 0.141.1, starlette 1.6.0, uvicorn 0.52.4
