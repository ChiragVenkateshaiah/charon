# ADR-NNNN: <Short decision title, stated as the decision>

- **Status:** Proposed | Accepted | Superseded by ADR-NNNN | Deprecated
- **Date:** YYYY-MM-DD
- **Phase:** 1 Inference mechanics | 2 Compilation & hardware | 3 Platform | 4 Scale & reliability
- **Deciders:** Chirag
- **Supersedes / Related:** ADR-NNNN, ADR-NNNN

---

## Context

What is true right now that forces a decision? Constraints, not opinions.

State the forcing function explicitly — a benchmark result, a cost overrun, a failure,
a blocked dependency. If you cannot name what changed, you may not need an ADR yet.

**Constraints in play:**

- Budget:
- Hardware available:
- Existing platform commitments (AWS-only, Terraform-managed, EKS, Prometheus):
- Time box:

---

## Decision

One paragraph, active voice, present tense. "We will ..."

Be specific enough that someone could implement it without asking a follow-up question.

---

## Measured evidence

> Required for any decision touching performance, cost, or capacity.
> If this section is empty, the decision is a **hypothesis**, and Status must
> remain `Proposed`. See ADR-0001.

| Variant | Throughput (req/s) | p50 (ms) | p99 (ms) | GPU util % | Cost / 1k inferences | Notes |
|---------|--------------------|----------|----------|------------|----------------------|-------|
| baseline |                   |          |          |            |                      |       |
| candidate |                  |          |          |            |                      |       |

**How these numbers were produced:**

- Hardware:
- Model / artifact version:
- Load generator, concurrency level, duration:
- Warmup discarded:  yes / no
- Runs averaged:
- Raw results committed at:  `benchmarks/<path>`

---

## Options considered

### Option A — <name>

- How it works:
- Pros:
- Cons:
- Rejected because:

### Option B — <name>

- How it works:
- Pros:
- Cons:
- Rejected because:

---

## Consequences

**Accepted costs.** What gets worse. Every real decision makes something worse; if you
cannot name it, you have not understood the tradeoff.

**Operational burden.** New things that must now be monitored, patched, paid for, or
rotated.

**Reversibility.** Cheap / moderate / expensive to undo, and what the undo path is.

**Blast radius if wrong.** Which parts of the platform break.

---

## Non-goals

What this decision explicitly does *not* attempt. Guard against scope creep by writing
these down at decision time rather than arguing about them later.

---

## Follow-ups

- [ ] Instrumentation to add
- [ ] Alert / SLO to define
- [ ] Runbook entry
- [ ] Teardown or cost-control step
- [ ] Revisit date, and the specific number that would trigger a revisit
