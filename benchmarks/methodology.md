# Benchmark Methodology

**Status: Week 2 decisions recorded 2026-10-18.** The seven rules below apply to every
run. The section "Concurrency sweep (Milestone 2)" fixes how they apply to a sweep at
concurrency above 1; the owner made those decisions on 2026-10-18. Items still open are
listed at the end. Per the working agreement, any later change to this file is a
deliberate, called-out decision, not a drift.

Per [ADR-0001](../adr/0001-measurement-discipline.md): a number only counts if it was
produced on real hardware by a reproducible run whose raw output is committed to the
repo. These rules exist so the numbers mean something.

## The seven rules

1. **Fixed input and output token counts.** Variable-length outputs make runs
   incomparable. Use a fixed prompt set and `min_tokens = max_tokens` so every request
   generates exactly N tokens.
2. **Discard warmup.** First requests include compilation, cache allocation, and CUDA
   context setup. Drop the first 30 seconds or first 20 requests.
3. **Report percentiles, never averages alone.** p50, p95, p99. Averages hide the
   behaviour that matters.
4. **Three runs minimum**, report median and spread. If spread exceeds ~10%, something
   is uncontrolled — find it before continuing.
5. **Record the environment every time:** GPU model, driver, CUDA version, framework
   versions, model revision hash, exact server flags.
6. **Change one variable per experiment.** Tempting to bundle; don't.
7. **Commit raw output**, not just the summary table.

## Concurrency sweep (Milestone 2)

Decided by the owner on 2026-10-18. Applies to the Milestone 2 sweep
(`docs/phase-1-plan.md`, Week 2; ADR-0003) and to every later sweep unless a change is
recorded here. Background and findings: `docs/milestone-2-sweep-validation.md`.

**Fixed by ADR-0003, not re-decided here.** Levels 1, 2, 4, 8, 16, 32, 64. Three runs
per level. 128 output tokens (`min_tokens = max_tokens`). Prompt set
`benchmarks/prompts/baseline.json`, as in Week 1.

1. **Load generator: hand-rolled.** A stdlib-only Python closed-loop driver against
   the server's `/generate` endpoint. At level N, exactly N requests are in flight
   from the client at all times until the run's last request is sent; the client
   never exceeds N. Its contract is checked by group C of
   `benchmarks/tests/test_sweep_driver_preflight.py` against a fake server before any
   GPU run.
2. **Warmup: the first max(20, N) requests sent, by sequence number.** The loop runs
   continuously; there is no drain between warmup and measurement. This refines rule 2
   for N > 1: with fewer warmup requests than N, measured requests are part of the
   start-up wave and see queue waits from zero to N − 1 positions, so their latency
   is not steady-state. At N ≤ 20 this is rule 2's "first 20 requests" unchanged.
   Sequence number is assigned at send time, so the warmup set is deterministic and
   auditable from raw output.
3. **Latency: client end-to-end and server TTFT/TPOT, reported separately.** Client
   end-to-end (`t_end − t_start`, measured by the driver) is the primary
   latency-vs-concurrency curve, because it includes queue wait. Server-reported TTFT
   and TPOT go in a separate, labelled table. The two are never combined or presented
   under one name. Server TTFT excludes time spent waiting for the generation lock.
4. **Throughput window: first to last measured completion.** Requests/s =
   (n − 1) / (`t_end` of last measured completion − `t_end` of first measured
   completion), over successful measured requests in that run; output tokens/s is the
   same window with token counts. Warmup requests still in flight do not enter the
   window's numerator.
5. **Failures: no request retries; a failed run is re-run once, else flagged.** An
   HTTP error or timeout is recorded per request and does not stop the run. A run with
   any failure is marked incomplete. Incomplete runs are re-run once, at the end of the
   session, if the session time box allows. If the re-run also fails, the run is
   reported flagged with its failure count, and that level is not used for the
   saturation (knee) claim. Raw output of every attempt, including failed ones, is
   committed.
6. **Percentiles and spread: n = 100 measured requests per run; spread gate on p50.**
   Percentiles are nearest-rank. At n = 100, p99 is the second-largest sample, so it
   depends on two events per run. Each level reports per-run p50/p95/p99, the spread
   of p50 and of p99 across runs, and a pooled p99 over the three runs' 300 measured
   requests. Rule 4's ~10% threshold is applied to p50 spread; p99 spread is reported,
   not gated.
7. **Client timeout: 1800 s per request.** A client timeout does not stop the server's
   generation, and a closed loop would then send a new request, putting more than N
   requests on the server. The timeout is set high so that it is not expected to fire;
   if it does, rule 5 above applies and the event is called out in the results.
8. **Server unchanged.** `serving/naive_server.py` is run byte-identical to the Week 1
   baseline, so concurrency is the only variable (rule 6). Alignment of requests with
   GPU samples uses the driver's wall-clock `t_start` / `t_end`.

**Raw output per request:** sequence number, warmup flag, ok / error, wall-clock
`t_start` and `t_end`, and the server payload. GPU samples and the environment block
(rule 5, including the Python version) are recorded each session.

## Not yet decided

- Hardware profile block (GPU model, driver, CUDA, framework versions — recorded once,
  referenced thereafter). Until it exists, each results file records its own
  environment (rule 5).
- Methodology for comparisons across serving configurations (Milestone 3 onward).
