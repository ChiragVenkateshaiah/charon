# ADR-0005: GPU sessions are for learning and measurement, under the same session discipline

- **Status:** Accepted
- **Date:** 2026-10-23
- **Phase:** All
- **Deciders:** Chirag
- **Supersedes / Related:** Replaces one clause of ADR-0002 ("powered on only for the
  duration of a measurement", in its Constraints) — ADR-0002 is otherwise unchanged
  and is not edited. Related: ADR-0001 (what counts as a result), ADR-0004 (primary
  goal).

---

## Context

Until now the rule was: the GPU is on only while a measurement runs; all development,
debugging, analysis and learning happen locally on CPU. It is written in `CLAUDE.md`,
`README.md`, `docs/phase-1-plan.md`, `scripts/session-start.sh` and ADR-0002.

That rule protects the budget, but it works against the reason Charon exists. The
owner's purpose is to learn inference engineering by working on a real GPU on GCP.
Watching a server serve, seeing KV cache memory grow, timing a cold start, or
reconciling a billing export cannot be learned from a CPU stand-in. The Stage 0
cost definitions (ADR-0004) include items that need a real session, for example the
rate source: the ~₹41.9/h list price and the ₹69/h observed rate can only be
reconciled with a billed session.

The forcing function is the owner's decision on 2026-10-23: Charon is a learning
playground on the GPU, in pursuit of the cost metric.

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

The GPU may be used for **learning sessions** as well as **measurement sessions**.
Both kinds of session follow the same four rules:

1. **Delete the instance after every session.** Never leave it stopped. The session
   scripts stay the only way in and out.
2. **Every session has a stated goal and a time box, decided before it starts,** plus
   a GPU-hour estimate. "Learn how KV cache memory grows, 1.5 h" qualifies. "Try a few
   things while it's up" does not.
3. **Exploration is not a result.** A learning-session run teaches; it is not a
   benchmark result. Only runs that follow `benchmarks/methodology.md` and commit raw
   output go into `benchmarks/results/` (ADR-0001). Exploration notes may be written
   up, but any number in them is labeled as exploratory.
4. **Learning spend is not serving cost.** What Charon spends on sessions is project
   cost. It never enters the numerator of ADR-0004's primary metric, cost per 1M
   successful output tokens.

The ~₹1,000/month target stays. Learning sessions are planned inside it; the existing
flexibility to extend it stays reserved for a specific measurement that needs it.
Before planning a session, check the month's GPU-hours so far (the worklog records
GPU-hours per session).

---

## Measured evidence

**Not applicable.** This ADR changes when the GPU may be used, not any performance,
cost or capacity claim. The GPU-hour figures in Context are estimates from list and
owner-supplied rates.

---

## Options considered

### Option A — Keep GPU for measurement only (status quo)

- How it works: as before; everything else on local CPU.
- Pros: lowest spend; every GPU-hour produces a committed number.
- Cons: the owner cannot learn on the hardware the project is about. Some Stage 0
  definitions (rate source, cost scope) cannot be settled from CPU.
- Rejected because: it defeats the project's purpose.

### Option B — GPU for everything, open-ended

- How it works: bring the GPU up whenever useful, no per-session goal.
- Pros: most hands-on time.
- Cons: open-ended sessions are the most expensive mistake available; quick
  experiments leak into results as numbers.
- Rejected because: it gives up the controls that keep spend and results honest.

### Option C — Learning and measurement sessions, same discipline (chosen)

- How it works: as in Decision.
- Pros: hands-on learning on the real GPU; spend stays bounded per session; results
  stay clean.
- Cons: see Consequences.

---

## Consequences

**Accepted costs.** Fewer GPU-hours remain for measurement inside ₹1,000/month. Some
months a learning session will displace a measurement. A playground run can also be
tempting to cite; rule 3 forbids it.

**Operational burden.** A goal, a time box and a GPU-hour estimate before every
session; a month-to-date GPU-hour check before planning one; exploration notes kept
apart from `benchmarks/results/`.

**Reversibility.** Cheap: revert to Option A by superseding this ADR.

**Blast radius if wrong.** Budget overrun (bounded by the GCP budget alert from
ADR-0002) and, if rule 3 slips, unvalidated numbers in documents.

---

## Non-goals

- Not a budget increase.
- Not permission to leave an instance running or stopped between sessions.
- Not a change to `benchmarks/methodology.md` or to what counts as a result.
- Not a change to development and writing, which still happen locally; the GPU is
  for work that needs the GPU.

---

## Follow-ups

- [ ] Owner: decide where exploration notes live (for example a `docs/learning/`
      folder), if they are kept at all.
- [ ] Track month-to-date GPU-hours in the worklog's Now block.
- [ ] Revisit if learning sessions push the month over ₹1,000 two months running.
