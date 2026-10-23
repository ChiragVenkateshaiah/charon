# ADR-0003: Milestones are authoritative; calendar weeks are reporting periods only

- **Status:** Accepted
- **Date:** 2026-10-11 (original decision: milestones are authoritative; historical
  metadata carried from the first draft of this ADR; **unverified** — no other
  repo record confirms this date)
- **Revised:** 2026-10-18 (owner decisions on numbering, exit evidence, checkpoints,
  the measurement gate and its order, separate GPU sessions, the TTFT time box, the
  configuration definition, the Phase 1 target and the Milestone 1 explanation
  path). Where this ADR states the project's position "now", it means 2026-10-18.
- **Revised:** 2026-10-23 — one-time, owner-authorized edit of this accepted ADR to
  align it with ADR-0004 (sole primary goal). Added: the last sentence of rule 9. The
  decision is unchanged. Open for the owner: whether rule 6's "cut Milestone 7" still
  holds, since Milestone 7 is the cost model.
- **Phase:** All
- **Deciders:** Chirag
- **Supersedes / Related:** ADR-0001 (measurement discipline; unchanged by this ADR),
  ADR-0004 (sole primary goal)

---

## Context

`docs/phase-1-plan.md` is written in calendar weeks: "**Duration:** 8 weeks",
sections "Week 1" to "Week 8", and drift checkpoints at "End of Week 2 / 4 / 6".
Each week section also carries its own **Build / Measure / Number produced /
Exit** criteria. Since Phase 1 began (2026-08-27, `docs/worklog.md`), those two
readings have split:

- **By the calendar**, 2026-10-18 is in the eighth week of Phase 1.
- **By exit criteria**, Phase 1 is still at Week 1. The Week 1 deliverable is
  committed (`benchmarks/results/baseline-20260828T172338Z.json`), but the week
  is not closed. Methodology rule 4 is open (TTFT p99 cross-run spread of 18%,
  unexplained), and the exit condition ("explain, without notes, why a
  single-stream LLM server underutilizes a GPU") is a private self-check that
  leaves no reviewable evidence.

The worklog has carried this ambiguity as an open item ("Plan structure: decide
calendar weeks vs milestones advanced on exit conditions. Probably an ADR."). As
long as both clocks claim to be the status, "where are we?" has two answers.
The calendar answer also invites the failure ADR-0001 exists to prevent: marking
work done because time passed, not because evidence landed.

A second problem sits under the first. The last committed result is dated
2026-08-28. ADR-0001's 30-day measurement gate has been failing since about
2026-09-27, and all three of the plan's calendar drift checkpoints have passed
with their conditions unmet. A change to how status is counted must not hide
that.

**Constraints in play:**

- **Budget:** a flexible target of ~₹1,000/month (~24 GPU-hours, `docs/gcp-setup.md`).
  Milestones can't be paced by GPU access alone. Every GPU session is scoped and
  costed first (`CLAUDE.md`).
- **Hardware available:** no local GPU. Measurements happen in short, deliberate
  GCP spot sessions, so progress is lumpy by nature.
- **Existing commitments:** ADR-0001 (Accepted) — its 30-day gate and its
  per-phase required numbers. ADRs are immutable once Accepted (`adr/README.md`).
- **Time box:** standing decision for the life of the project.
- **Outputs that run on a weekly rhythm:** learning notes and LinkedIn articles
  (the Week 1 article package is in `docs/articles/week-1/`, uncommitted).

---

## Decision

We will treat **milestones** as the only measure of Charon's progress. Calendar
weeks are **reporting periods** only.

1. **What a milestone is.** Each "Week N" section of `docs/phase-1-plan.md` is
   Phase 1 milestone N. Its existing label ("Week 1 — Naive baseline") stays as
   the milestone's identifier, and nothing is renamed. Future phases define
   their milestones the same way.
2. **Exit criteria produce reviewable evidence.** Every milestone has a written
   list of exit criteria, and each criterion names the evidence it produces: a
   committed file the owner can review. A criterion that leaves no such
   evidence must be restated before the milestone can close.
   - "You can explain X, without notes" becomes: **a written technical
     explanation of X, committed to the repo and reviewed by the owner.** This
     applies to every "explain" exit in the plan, starting with Milestone 1.
   - Private self-checks ("without notes", "on paper", "to someone who has
     never heard of it") stay as **supplementary learning exercises**. They are
     encouraged, they are not recorded as evidence, and they never gate a
     milestone.
3. **Completion needs evidence.** A milestone is **complete** only when every exit
   criterion has its evidence committed, the owner has reviewed it, and the
   owner has recorded the completion (date + evidence paths) in the worklog.
   Evidence that is a performance, cost or capacity number must meet ADR-0001: a
   committed result from real hardware. A diagnostic artifact (a profile, a
   roofline, an analysis) can support a criterion. It doesn't satisfy a
   "number produced" criterion. Elapsed time, written plans, harness code,
   prompts and drafts are never evidence of completion.
4. **The current milestone** is the lowest-numbered milestone in the current
   phase that is not complete. Work may begin on a later milestone early. That
   doesn't change which milestone is current.
5. **Calendar weeks are reporting periods.** The worklog, weekly learning notes and
   LinkedIn articles may be dated or labelled by calendar week. They report what
   happened in that period. They **do not** set, imply or change milestone status.
   An article may cover a milestone's work before that milestone is complete, if
   it doesn't claim the milestone is complete.
6. **Two kinds of checkpoint, kept separate.**
   - **Milestone checkpoints** replace the plan's calendar drift checkpoints
     from now on. Each one is evaluated at a milestone boundary: when the named
     milestone is closed, or when work starts on any later milestone, whichever
     comes first. The plan's three checkpoints become:
     - **At Milestone 2:** a committed concurrency curve exists; if not, stop and
       produce one.
     - **At Milestone 4:** the master table has at least four serving
       configurations; if not, stop and measure.
     - **At Milestone 6:** the second model scale has been run; if not, cut
       Milestone 7 rather than skip it.
   - **The monthly review** stays on the calendar, as `adr/README.md` defines
     it. It runs ADR-0001's 30-day gate regardless of milestone position. It is
     the backstop for a milestone that stays open too long.
7. **ADR-0001's 30-day gate is unchanged and stays the gate.** Milestone-based
   status exempts no period from producing a measured number. The gate is
   cleared only by a **new, unprofiled serving measurement**: throughput and
   p50/p99 latency (ADR-0001's Phase 1 list), produced on real hardware by a
   reproducible run, with its raw output committed. **Diagnostic profiling does
   not satisfy the gate**: an Nsight Systems or Nsight Compute trace is
   perturbed by the profiler and is not a benchmark result.
8. **Two configuration bars, deliberately different.**
   - **ADR-0001's minimum stays three.** Phase 1 cannot be called complete with
     fewer than three serving configurations measured. ADR-0001 is not edited
     and not superseded for this.
   - **The plan's target stays six.** `docs/phase-1-plan.md`'s exit condition
     ("at least six serving configurations") is the stricter Phase 1 target,
     and milestone exit criteria cite it.
   - Six satisfies "at least three", so the two don't conflict. Three is the
     floor that the measurement-discipline ADR enforces; six is what the plan
     aims for. A report on Phase 1 says which bar it means.
9. **What a serving configuration is.** A serving configuration is a
   **distinct serving setup**: what changes is how the server serves (for
   example its serving stack, batching mode, precision or model size).
   Concurrency levels, prompt sets and repeat runs are **not** separate
   configurations; they are how one configuration is measured. Which six
   setups Phase 1 will measure is **not** decided by this ADR. The plan's week
   sections suggest candidates, but they are not an approved implementation
   list. Each one is chosen when its milestone is planned, under ADR-0004's
   decision rule: it must test a cost-relevant hypothesis or enable a required
   service constraint.
10. **ADR numbering is preserved.** ADR-0001, ADR-0002 and this ADR keep their
    numbers. The future ADRs that `docs/phase-1-plan.md` (Week 8) names as
    "ADR-0002", "ADR-0003" and "ADR-0004" take the next free number when each
    is actually written. The plan's references are renumbered then, not now.
11. **Order: measurement first, then the diagnostic trace, in two separate GPU
    sessions.**
    - **GPU session 1: the qualifying sweep.** Prepare the concurrency sweep
      locally, then run it (below). It produces throughput and p50/p99 latency
      on real hardware. Its raw output is committed to the repo. Nothing else
      runs in this session.
    - **GPU session 2: the CPU-sampled Nsight Systems trace**, in a separate
      session that starts only **after session 1's result is committed**. It
      repeats the Week 1 trace with CPU sampling enabled, on the same pinned
      image with the unchanged server and client, as the worklog and
      `benchmarks/profiles/2026-10-06-week1-nsys/report.md` describe it. It
      needs owner approval to lower `kernel.perf_event_paranoid` on the
      throwaway VM. The report estimates about 0.4 GPU-hours (estimated, not
      measured).
    - The trace is **diagnostic**. It does not satisfy ADR-0001's gate (rule 7),
      before or after session 1.
    - Nsight Compute on the dominant GEMV kernels follows only if the trace
      justifies it. This ADR changes no other technical plan, and it runs,
      books or starts nothing.

### The smallest qualifying serving measurement

Inspected against ADR-0001 and `docs/phase-1-plan.md` on 2026-10-18. Not run.

**Exact requirement.** ADR-0001's gate asks: "Has a new number entered a
benchmark table in the last 30 days?" If no, "the next work item is a
measurement, chosen from the current phase's required list." Phase 1's list is
"throughput and p50/p99 latency across at least three serving configurations".
A number qualifies only if it was "produced on real hardware by a reproducible
run whose raw output is committed to the repo."

So the gate needs **one new, unprofiled throughput and p50/p99 measurement on
the L4, with its raw output committed**. ADR-0001 does not say "unprofiled" in
those words; rule 7 of this ADR reads it that way, because a profiled run is
perturbed and is not a benchmark result. The gate does not need a new
configuration. The configuration bars (three minimum, six target) are for
phase completion, not for the 30-day gate.

**Recommended measurement: the Milestone 2 concurrency sweep against the
existing naive server.** Concurrency 1, 2, 4, 8, 16, 32, 64 (the plan's Week 2
levels), three runs per level, with the fixed 128 output tokens and the
`benchmarks/prompts/baseline.json` prompt set from Week 1.

- **Why this one:** it is the smallest step that is also the plan's next
  required number. It needs no new server, model or precision: the server,
  model revision and image are the ones already measured. It reports
  throughput and p50/p99 at every level, so it clears the gate. It also
  produces Milestone 2's number and fires the Milestone 2 checkpoint.
- **What it does not do:** under rule 9, it adds no new serving configuration.
  Concurrency is a load level, not a configuration. Progress toward the three
  minimum and the six target starts at Milestone 3.
- **Expected shape (hypothesis, not a finding):** `serving/naive_server.py`
  serializes `model.generate` behind `_GEN_LOCK`. Throughput is therefore
  expected to stay flat from concurrency 1, and latency to grow with queue
  depth. That prediction comes from reading the code. Only the run can confirm
  it.
- **Default levels:** 1, 2, 4, 8, 16, 32, 64, as the plan states. They stay the
  default proposal. A change to them is a methodology decision for the owner,
  made before the run and recorded in `benchmarks/methodology.md`.
- **Cost (ESTIMATED, NOT MEASURED):** the Week 1 run at concurrency 1 took
  22.3 min wall time for 3 × 120 requests (from `started_at` / `finished_at` in
  the raw JSON). If each level takes about the same, 7 levels ≈ 2.6 h of load
  time. Past GPU sessions spent more instance time than their measurement
  (0.53 and ~1.1 GPU-hours in the worklog, the second mostly stockout
  retries). Planning figure: **about 3 GPU-hours**, so about ₹125 at the
  ~₹41.9/h list price, or about ₹205 at the ₹69/h observed effective rate. The
  two rates are unreconciled (worklog).
- **Assumptions behind the estimate, to validate locally before booking:**
  1. *Per-level wall time is constant.* `_GEN_LOCK` serializes
     `model.generate` only. On its own it does not prove the sweep's duration.
     The estimate also assumes that the driver keeps the server busy at
     every level, and that the work outside the lock (HTTP, chat template,
     tokenizer, response) adds no idle gaps between requests. Check by
     reading the server, and with a short local CPU run of the new driver
     against a stub server.
  2. *120 requests per run at every level* (20 warmup + 100 measured). At
     concurrency 64, warmup by request count needs a definition (first 20
     sent? first 20 completed? first 30 s?). Fix it in `methodology.md`.
  3. *No client timeouts.* At concurrency 64, a request may wait for about 63
     others, about 4 min if Week 1's ~3.7 s per request holds. The runner's
     default `--request-timeout` is 600 s. Confirm the new driver keeps a
     safe margin.
  4. *The server accepts 64 concurrent requests.* The `/generate` endpoint
     is synchronous, so FastAPI runs it in a worker thread pool. The Nsight
     trace shows decode running on an `AnyIO worker th` thread. The pool size
     for the locked anyio 4.14.2 / FastAPI 0.141.1 / uvicorn 0.52.4 was not
     checked. Requests above the pool size would queue before the lock. The
     expectation is that this changes where the queue wait shows up, not the
     total time, but that is unverified. Check the installed versions' docs
     and source.
  5. *Instance overhead* (bootstrap, model load, teardown) is about 0.3–0.4 h.
     This comes from past sessions, not from a measurement of this session.
     Check `job.log` timestamps from earlier sessions.
  6. *The runner design.* `benchmarks/baseline_runner.py` is concurrency-1
     only ("It has no concurrency model"). The sweep needs a new driver. Its
     design (how it holds concurrency N, when it counts a request as warmup,
     how it timestamps requests) sets both the run time and what the numbers
     mean. Review it locally before any GPU session.
- **Local prerequisites (no GPU):**
  1. The time-boxed TTFT p99 step (below).
  2. Fix the Week 2 parts of `benchmarks/methodology.md`: load generator, the
     default sweep levels, and warmup discard at concurrency above 1.
  3. Write the sweep driver. That is harness code, not progress (ADR-0001).
     Only the committed result counts.

**The Week 1 TTFT p99 spread vs the gate.** Methodology rule 4 says that a
spread above ~10% means "something is uncontrolled — find it before
continuing". The Week 1 TTFT p99 spread is 18%, from run 2 alone. ADR-0001 says
the gate is mandatory. An open-ended investigation must not block the gate, so:

- **Time box (owner-approved, 2026-10-18): one bounded local work session.** No
  precise duration in hours is set. The investigation ends when that one
  session ends, whatever the result. It does not continue into later sessions
  unless the owner decides so explicitly.
- **Inputs: the existing committed raw result only**,
  `benchmarks/results/baseline-20260828T172338Z.json`. Read-only: the baseline,
  its raw JSON and its analysis are not modified or overwritten.
  - `raw.requests`: run 2's per-request TTFT and `t_start` / `t_end`. Is the
    tail one or two requests or many? Where do they fall in the run: near
    the start (warmup bleed), clustered (a one-off pause), or spread out?
  - Compare with runs 1 and 3.
  - `raw.gpu_samples`: utilization, clocks, power and temperature around the
    slow requests.
- **Output: a short written record in three parts.** (1) What the evidence
  **explains**. (2) What it only **bounds**: what the spread is not, and its
  size in absolute terms. (3) What stays **unknown**. A cause is stated only
  if the data supports it. Otherwise the record says "not established".
- **If the spread is only bounded, proceed to prepare the sweep.** The
  investigation does not block the gate. The sweep's concurrency-1 level
  repeats the Week 1 condition, so it re-tests the spread as a control. The
  sweep driver records per-request timestamps and checks p99 spread as well as
  p50 spread. The Week 1 analysis already lists this as a Week 2 harness fix.
- **For Milestone 1**, the explained-or-bounded record is what counts. The
  spread does not have to disappear.

---

## Measured evidence

**Not applicable.** This is a governance decision about how status is recorded.
It makes no performance, cost or capacity claim. The cost figures in the
measurement section above are estimates and are labelled as such. Every
performance, cost or capacity claim in the project still falls under ADR-0001.

---

## Options considered

### Option A: Calendar weeks are authoritative (the plan as written)

- **How it works:** status follows the date. Week N ends after seven days, and a
  week that misses its exit is either cut or carried as "late".
- **Pros:** it gives a natural deadline and forces scope cuts. It is easy to
  report.
- **Cons:** the plan has already diverged from the calendar by about seven
  weeks. Status by date would call Weeks 2–7 "late" or "skipped" while their
  work is still undone. It also pressures the project to close milestones
  without evidence, which is the failure ADR-0001 names.
- **Rejected because:** a status that can be reached without evidence is not
  compatible with ADR-0001.

### Option B: Milestones are authoritative; calendar weeks report (chosen)

- **How it works:** as in *Decision*.
- **Pros:** there is one answer to "where are we?", and it can only move on
  evidence. Weekly writing and learning continue without affecting status.
- **Cons:** there is no built-in deadline per milestone. Readers see two labels:
  "reporting week 8, milestone 1".
- **Chosen because:** it matches how the project already works in practice. The
  worklog already reports "Week 1 by exit conditions". Time pressure stays
  where ADR-0001 already puts it: the monthly review.

### Option C: Milestones with calendar deadlines (hybrid)

- **How it works:** milestones are authoritative, but each one has a due date.
  Missing it triggers a re-plan.
- **Pros:** it gives a deadline per milestone.
- **Cons:** it brings back a second status clock ("on time / overdue") next to
  "complete / open". GPU sessions are lumpy and budget-gated, so per-milestone
  dates would be guesses.
- **Rejected because:** ADR-0001's monthly gate already supplies the time
  pressure, at the level that matters (a number every 30 days).

### Option D: No decision (status quo)

- **How it works:** both readings stay in the docs.
- **Rejected because:** that is the ambiguity this ADR exists to remove.

---

## Handling of historical work

- **Nothing is rewritten.** Past worklog entries, commit messages, results,
  profiles, analyses and article drafts keep their dates and wording. Where they
  say "Week 1", that now reads as "milestone 1", which is what they meant.
- **Raw results and profiler artifacts are untouched** (ADR-0001). That includes
  `benchmarks/results/` and `benchmarks/profiles/`.
- **Milestone 1 (Week 1 — Naive baseline) stays open.** Its committed baseline
  is its "number produced" evidence. The roofline analysis
  (`docs/week1-roofline.md`) and the Nsight Systems profile and investigation
  (`benchmarks/profiles/2026-10-06-week1-nsys/`) are diagnostic material for
  the written explanation. They are not results, and they are not the
  explanation itself. Milestone 1 closes under rule 3 when two items are done:
  - methodology rule 4 (the TTFT p99 spread) is explained or bounded (see
    *The Week 1 TTFT p99 spread vs the gate*);
  - the written technical explanation of single-stream GPU underutilization is
    committed and reviewed (rule 2). The owner authors it. Its path and
    required content are below; the file is not created by this ADR.
- **No milestone after Milestone 1 is complete**, and none is marked in progress
  by this ADR. Work already done toward Milestone 2 (methodology notes, the
  `scripts/` session tooling) counts when Milestone 2's exit is assessed.
- **Overdue checkpoints for explicit review.** These fired under the old rules
  with their conditions unmet. The owner reviews each one and records the
  outcome in the worklog. They are not re-dated or deleted quietly.

  | Checkpoint | Source | Fired (calendar, from 2026-08-27) | Condition | State on 2026-10-18 |
  |---|---|---|---|---|
  | End of Week 2 | plan | ~2026-09-09 | concurrency curve exists | **unmet** — none committed |
  | End of Week 4 | plan | ~2026-09-23 | master table ≥ 4 configurations | **unmet** — 1 (naive, concurrency 1) |
  | End of Week 6 | plan | ~2026-10-07 | second model scale run | **unmet** — not run |
  | 30-day gate | ADR-0001 | ~2026-09-27 | new number in last 30 days | **failing** — last result 2026-08-28 |

  These states are historical and stay **overdue / unmet**. A later
  measurement does not mark them complete in retrospect. When the recommended
  sweep lands, it clears the 30-day gate from that date and satisfies the
  Milestone 2 checkpoint going forward. The record still shows that the Week 2
  checkpoint was missed on ~2026-09-09. The Week 4 and Week 6 checkpoints move
  to their milestone forms (rule 6) after the owner has reviewed them.

  **Worklog follow-up (not made by this ADR):** add one dated entry that lists
  the four items above with their state on 2026-10-18 ("overdue / unmet",
  "failing"), the owner's review outcome for each, and the evidence path that
  clears each one later. Earlier worklog entries are not edited.
- **The calendar position** (reporting week 8 of Phase 1 as of 2026-10-18,
  counting from the 2026-08-27 start) is a reporting fact. It isn't a status.

### Milestone 1 written explanation (path decided, file not created)

- **Author:** the owner. This ADR does not create the file.
- **Path:** `docs/week1-explanation.md`. It sits next to
  `docs/week1-roofline.md` and `docs/week1-profile-card.md`, and it keeps the
  "Week 1" milestone label (rule 1).
- **It counts as evidence only when committed and then reviewed by the
  owner.** The committed file plus its owner-review record is the evidence
  that closes Milestone 1's explanatory exit criterion (rules 2–3).
- **Required content:**
  1. **The claim.** Why a single-stream LLM server underutilizes the GPU.
  2. **The mechanism.** Token-by-token decoding, kernel-launch cadence, and
     host/GPU coordination.
  3. **Charon evidence**, cited by exact path: the baseline result
     (`benchmarks/results/baseline-20260828T172338Z.json` and
     `benchmarks/results/2026-08-28-week1-baseline.md`), the roofline
     (`docs/week1-roofline.md`) and the Nsight Systems report and
     investigation (`benchmarks/profiles/2026-10-06-week1-nsys/report.md`,
     `decode-investigation.md`). Each value is labelled **measured** or
     **estimated / derived / inferred**, as those documents label them.
     Profiled timings are marked as profiled, because the tracer inflates
     them.
  4. **Evidence gaps.** CPU sampling was disabled in the 2026-10-06 trace
     (`nsys` refused it), so there are no CPU or Python call stacks. The
     host-side cause of the idle GPU time is **not yet proven**.
  5. **Predictions that the CPU-sampled trace can test.** For example, which
     host component (Python, the PyTorch dispatcher or the CUDA launch path)
     takes the time between kernel launches. They are labelled as hypotheses.
  6. **Owner-review record.** Review date, what was checked against the cited
     evidence, and the uncertainties that remain.

---

## Open questions (owner)

Earlier drafts listed five conflicts and three smaller questions. The owner
resolved all of them by 2026-10-18:

- numbering (rule 10);
- reviewable exit evidence (rule 2);
- the two configuration bars (rule 8);
- the configuration definition (rule 9);
- measurement order and separate GPU sessions (rule 11);
- the TTFT time box (one bounded local work session, *The Week 1 TTFT p99
  spread vs the gate*);
- the explanation path (`docs/week1-explanation.md`).

One note is recorded.

1. **Original decision date.** 2026-10-11 is carried from the first draft of
   this ADR as historical metadata. No other repo record confirms it: the
   other 2026-10-11 entries in `docs/articles/week-1/` concern article checks,
   not this decision. **Resolved 2026-10-18:** the owner kept 2026-10-11 as
   historical metadata. The date remains unverified.

---

## Consequences

**Accepted costs.**
- There is no built-in deadline per milestone. Slow progress shows up only
  through the monthly review and through reporting.
- Status reports carry two labels (reporting week, milestone), which readers
  can confuse. Articles and notes must not imply that a milestone is done.
- Every "explain" exit now needs a committed written explanation. That is
  real writing work at the end of most Phase 1 milestones, and it applies
  once retroactively to Milestone 1.
- Phase 1 carries two configuration bars (three minimum, six target, rule 8).
  Aiming for six means more GPU sessions before Phase 1 closes, and every
  Phase 1 status report must say which bar it refers to.
- The measurement-first order (rule 11) delays the CPU-sampled trace, and with
  it the host-CPU attribution that the Milestone 1 explanation would cite.
  The explanation can be committed with that gap stated (its section 4).
- Two separate GPU sessions pay for instance bootstrap, model load and
  teardown twice. Past sessions suggest roughly 0.3–0.4 GPU-hours of overhead
  each (estimated, not measured). That is the price of keeping the gate's
  measurement apart from the profiled run.
- Milestone checkpoints can fire late if milestones stall. That is the
  intended trade: the monthly review, not the checkpoints, carries the time
  pressure.

**Operational burden.**
- The worklog **Now** block records the current milestone and the reporting
  period as separate fields. The current milestone is the source of truth.
- Completing a milestone becomes an explicit, dated owner action with evidence
  paths. It never happens as a side effect.
- The monthly review runs alongside the milestone checkpoints, with the four
  overdue items above reviewed once explicitly.

**Reversibility.** Cheap. It is a documentation and status convention, with no
code or infrastructure involved. To undo it, supersede it with a new ADR.

**Blast radius if wrong.** Limited to status reporting and planning. No
measurement, result or system behaviour depends on it. The main risk is a
milestone that stays open indefinitely. The ADR-0001 monthly gate is the guard
against that, and it is failing now, so the first test of this ADR is whether
the next work item is a measurement.

---

## Non-goals

- It does not create the roadmap, charter, experiment register, architecture
  or learning documents. Those are separate follow-ups.
- It does not change ADR-0001, ADR-0002, the plan's technical content, the
  methodology rules or the budget.
- It does not mark any milestone or checkpoint complete, in the present or in
  retrospect, and it does not re-scope any milestone.
- It does not approve a concrete list of the six serving configurations.
- It does not run, or schedule, the recommended measurement or the
  CPU-sampled trace.
- It does not limit how often learning notes or articles are published.

---

## Follow-ups

**ADR**

- [x] Owner reviewed this ADR and approved acceptance on 2026-10-18. The
      original decision date 2026-10-11 is retained as historical metadata,
      explicitly unverified (*Open questions* 1).

**Before GPU session 1 (local, no GPU)**

- [ ] TTFT p99 step: one bounded local work session on the committed raw
      result; write the explains / bounds / unknown record. If only bounded,
      proceed.
- [ ] Validate the six assumptions listed under the recommended measurement,
      including thread-pool behavior and the new driver's design.
- [ ] Finalize the Week 2 parts of `benchmarks/methodology.md` (load generator,
      default levels 1–64, warmup at concurrency above 1, p99 spread check).
- [ ] Write the sweep driver.
- [ ] Owner: approve the sweep and its estimated GPU-hours before any instance
      is created.

**GPU session 1, then GPU session 2 (rule 11)**

- [ ] Session 1: run the sweep; commit its raw output and analysis. This clears
      ADR-0001's gate from that date.
- [ ] Session 2, only after session 1's result is committed: the CPU-sampled
      Nsight Systems trace (owner approval for `kernel.perf_event_paranoid`
      first). Diagnostic; does not count toward the gate.

**Milestone 1**

- [ ] Owner: write and commit `docs/week1-explanation.md` with the six required
      parts, then review it and record the review. This is evidence for
      Milestone 1 only after the review is recorded.

**Edits to other documents (listed here, not made by this ADR)**

- [ ] `docs/phase-1-plan.md`: header ("Duration: 8 weeks"); the "explain" exits
      restated as written explanations (rule 2); the drift checkpoints restated
      as milestone checkpoints (rule 6); a note that the exit condition's "six"
      is the target and ADR-0001's three is the minimum (rule 8). No change to
      the technical content. Leave the Week 8 ADR numbers until those ADRs are
      written (rule 10).
- [ ] `docs/worklog.md`, **Now** block: separate *current milestone* and
      *reporting period* fields; replace the open item "Plan structure: decide
      calendar weeks vs milestones" with a pointer to this ADR; replace
      "Decide the next profiling step vs Week 2 first" with the rule 11 order.
- [ ] `docs/worklog.md`, new dated entry: the four overdue checkpoints, as in
      *Handling of historical work*.
- [ ] `README.md` "Current status", which is stale. It still says no number has
      been measured.
- [ ] `adr/README.md` index: update the status column when this ADR is
      Accepted.
- [ ] When the roadmap is created, give it a per-milestone table of exit
      criteria and evidence paths.
- [ ] Revisit if milestone status stays unchanged across two consecutive monthly
      reviews. That would mean milestones are too large or criteria can't be
      met.
