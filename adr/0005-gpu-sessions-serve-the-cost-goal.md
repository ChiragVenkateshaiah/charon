# ADR-0005: GPU sessions serve the cost goal, under one session discipline

- **Status:** Accepted
- **Date:** 2026-10-23
- **Revised:** 2026-10-23 — owner-authorized in-place edit of this accepted ADR (an
  exception to `adr/README.md`'s immutability rule). The first version split sessions
  into "learning" and "measurement" and treated learning spend as its own category.
  That misread the owner's intent: learning is how the work toward the cost goal is
  done, not a separate kind of session or a separate budget line. Title, file name,
  Decision, Options and Consequences were rewritten; the number is unchanged.
- **Phase:** All
- **Deciders:** Chirag
- **Supersedes / Related:** Replaces one clause of ADR-0002 ("powered on only for the
  duration of a measurement", in its Constraints) — ADR-0002 is otherwise unchanged
  and is not edited. Related: ADR-0001 (what counts as a result), ADR-0004 (primary
  goal).

---

## Context

Until now the rule was: the GPU is on only while a measurement runs; all development,
debugging, analysis and investigation happen locally on CPU. It is written in
`CLAUDE.md`, `README.md`, `docs/phase-1-plan.md`, `scripts/session-start.sh` and
ADR-0002.

That rule protects the budget, but it works against how Charon is meant to be done.
The owner learns inference engineering by pursuing the cost goal on a real GPU on GCP:
the learning *is* the pursuit. Many steps toward the goal need the GPU but are not
benchmark runs — investigating why throughput is flat, watching KV cache memory grow
before choosing a concurrency limit, timing a cold start to scope cost, debugging a
server that misbehaves only on the L4. Some Stage 0 cost definitions (ADR-0004) need a
real session too: the ~₹41.9/h list price and the ₹69/h observed rate can only be
reconciled against a billed session.

The forcing function is the owner's decision on 2026-10-23: Charon is a GPU
playground for pursuing the cost metric.

**Constraints in play:**

- Budget: ~₹1,000/month target, unchanged. *Estimate, not measured:* that is about 24
  GPU-hours at the ₹41.9/h list price, or about 14.5 hours at the ₹69/h observed
  rate. The two rates are unreconciled.
- Hardware available: one GCP `g2-standard-4` spot (1× L4), created and deleted per
  session.
- Existing platform commitments: single-cloud GCP (ADR-0002); session scripts
  `scripts/session-start.sh` / `scripts/session-end.sh`.
- Time box: standing decision for the life of the project.

---

## Decision

The GPU may be used for **any work that serves the cost goal** (ADR-0004), not only
for benchmark runs: measurement, investigation, debugging, and settling Stage 0
definitions. There is one kind of session. Every session follows four rules:

1. **Delete the instance after every session.** Never leave it stopped. The session
   scripts stay the only way in and out.
2. **Every session states its cost question, a time box, and a GPU-hour estimate
   before it starts.** The cost question names what the session serves: a term of the
   cost formula, a Stage 0 definition, or a hypothesis. "Is the flat throughput caused
   by the generation lock? 1 h" qualifies. "Try a few things while it's up" does not.
3. **Investigation runs are not results.** A session may contain investigation runs
   and measurement runs. Only runs that follow `benchmarks/methodology.md` and commit
   raw output go into `benchmarks/results/` (ADR-0001). A number from an
   investigation run is labeled as such wherever it is written.
4. **There is one spend.** All session spend is Charon's spend, planned inside the
   ~₹1,000/month target. There is no separate learning category. How session overhead
   relates to the primary metric is decided by Stage 0 definition 6 (cost scope), not
   by this ADR.

The ~₹1,000/month target stays. The existing flexibility to extend it stays reserved
for a specific measurement that needs it. Before planning a session, check the month's
GPU-hours so far (the worklog records GPU-hours per session).

---

## Measured evidence

**Not applicable.** This ADR changes when the GPU may be used, not any performance,
cost or capacity claim. The GPU-hour figures in Context are estimates from list and
owner-supplied rates.

---

## Options considered

### Option A — Keep GPU for benchmark runs only (status quo)

- How it works: as before; investigation and debugging on local CPU.
- Pros: lowest spend; every GPU-hour produces a committed number.
- Cons: the work toward the goal that needs the GPU but is not a benchmark run cannot
  be done; some Stage 0 definitions (rate source, cost scope) cannot be settled.
- Rejected because: it blocks the pursuit the project exists for.

### Option B — GPU for everything, open-ended

- How it works: bring the GPU up whenever useful, no stated question.
- Pros: most hands-on time.
- Cons: open-ended sessions are the most expensive mistake available; investigation
  numbers leak into results.
- Rejected because: it gives up the controls that keep spend and results honest.

### Option C — Separate learning and measurement sessions (this ADR's first version)

- How it works: two session types, learning spend tracked as its own category.
- Pros: makes playground time visible.
- Cons: treats learning as apart from the goal, which it is not; invents a spend
  category the cost scope would then have to explain.
- Rejected because: learning is the pursuit of the cost goal, not a parallel track.

### Option D — Any goal-serving work, one session discipline (chosen)

- How it works: as in Decision.
- Pros: hands-on work on the real GPU; every session tied to the cost goal; spend
  bounded per session; results stay clean.
- Cons: see Consequences.

---

## Consequences

**Accepted costs.** Fewer GPU-hours remain for benchmark runs inside ₹1,000/month; in
some months an investigation session will displace a measurement. An investigation
number can be tempting to cite; rule 3 forbids it.

**Operational burden.** A cost question, a time box and a GPU-hour estimate before
every session; a month-to-date GPU-hour check before planning one.

**Reversibility.** Cheap: revert to Option A.

**Blast radius if wrong.** Budget overrun (bounded by the GCP budget alert from
ADR-0002) and, if rule 3 slips, unvalidated numbers in documents.

---

## Non-goals

- Not a budget increase.
- Not permission to leave an instance running or stopped between sessions.
- Not a change to `benchmarks/methodology.md` or to what counts as a result.
- Not a change to writing and code editing, which still happen locally; the GPU
  session is for work that needs the GPU.

---

## Follow-ups

- [ ] Track month-to-date GPU-hours in the worklog's Now block.
- [ ] Revisit if sessions push the month over ₹1,000 two months running.
