# ADR-0004: Cost per 1M successful output tokens is Charon's sole primary goal

- **Status:** Accepted
- **Date:** 2026-10-23
- **Phase:** All
- **Deciders:** Chirag
- **Supersedes / Related:** ADR-0001 (Phase 3 cost metric replaced; rest unchanged),
  ADR-0002, ADR-0003 (both aligned, decisions unchanged). See "One-time edit of
  accepted ADRs" below.

---

## Context

Charon's README has always said the project is about "cost per token", but no
document made it the authoritative objective, and the documents disagreed on the unit:

- the README table used "Cost / 1M tokens";
- `docs/phase-1-plan.md` Week 7 used "cost per 1M output tokens";
- ADR-0001's Phase 3 row used "cost per 1000 inferences";
- the ADR template's evidence table used "Cost / 1k inferences".

Meanwhile most recorded effort since Milestone 1 went to diagnostics and methodology
(Nsight profiling, sweep methodology, articles) rather than to configurations that
can change cost. Two Phase 1 results exist, both for the naive server, and no cost
figure is in a results table. The ₹337 and ₹556 per 1M output tokens figures in the
articles are estimates from a measured throughput and two unreconciled hourly rates
(₹41.9/h list price, ₹69/h owner-supplied observed rate).

Without one stated objective, a faster kernel, a higher GPU utilization figure, or a
framework adoption can each be presented as progress. The forcing function is the
2026-10-23 alignment review, which found the project's direction right but its focus
and its cost unit inconsistent.

**Constraints in play:**

- Budget: ~₹1,000/month target, flexible (CLAUDE.md, ADR-0002).
- Hardware available: one GCP `g2-standard-4` spot (1× L4), per measurement only.
- Existing platform commitments: single-cloud GCP (ADR-0002); milestones are
  authoritative (ADR-0003); every phase produces a measured number (ADR-0001).
- Time box: standing decision for the life of the project.

---

## Decision

Charon has **one primary objective: minimize the cost per 1 million successful
generated output tokens.**

```
Cost per 1M successful output tokens = (Total serving cost / Total successful generated output tokens) × 1,000,000
```

Every other metric and activity is ranked under it:

| Level | What | Role |
|---|---|---|
| **Primary goal** | Cost per 1M successful output tokens | The only measure of project success. |
| **Mandatory service constraints** | Latency, reliability, output quality | Must stay within defined acceptable limits. Actively optimized where evidence shows improvement is valuable, but not competing primary goals. |
| **Optimization dimensions** | Latency, reliability, output quality, throughput, resource efficiency | Improved where doing so lowers cost or enables more cost-efficient serving. |
| **Diagnostic metrics** | GPU utilization, memory use, kernel activity, CPU overhead, queueing, and similar | Explain why serving costs what it does and where a change may lower it. |
| **Implementation choices** | Profiling tools, concurrency strategies, vLLM, Kubernetes, other technologies | Means to the objective, never goals in themselves. |

**Decision rule for every optimization:**

1. Measure the current cost per 1M successful output tokens using a consistent
   accounting method.
2. Identify a cost-relevant limitation using evidence.
3. Form a hypothesis explaining how changing that limitation could reduce cost.
4. Run a controlled experiment and measure the resulting cost metric.
5. Check the effects on latency, reliability, output quality, and relevant
   operational constraints.
6. Accept the change as an improvement only if it produces a credible cost benefit
   without violating required service constraints. If cost does not improve, do not
   claim success merely because another metric improved.

**What does not count as success:**

- An improvement in latency, throughput, or utilization alone. It counts when it
  demonstrably reduces cost, enables lower-cost serving, or is needed to meet a
  service constraint while preserving the primary objective.
- A lower apparent cost bought with excessive failures, unacceptable latency, or
  degraded output quality.

**Trade-offs are reported, not hidden.** When a change improves service quality or
reliability but raises cost, the trade-off is reported in the results file. The change
is adopted only when it is needed to meet the agreed constraints or when its overall
impact supports the cost objective. A cost regression is never hidden behind an
improvement in a secondary metric.

**Comparable cost claims need fixed definitions first.** Before any cost figure is
compared across configurations, `benchmarks/methodology.md` must record:

- the cost-accounting scope (what is in "total serving cost");
- the hourly-rate source;
- what makes a request successful, and the latency, reliability, and quality limits;
- how output tokens are counted;
- how failed requests, idle time, and other serving costs are treated.

These are owner decisions and are **not** made by this ADR. Until they are recorded,
any cost figure is an estimate and is labeled as one (ADR-0001).

---

## Measured evidence

**Not applicable.** This ADR defines the objective and how results are judged. It
makes no performance, cost, or capacity claim. The ₹337 / ₹556 per 1M output tokens
figures cited in Context are estimates, not evidence, and are not a baseline.

---

## Options considered

### Option A — Throughput (tok/s) or latency as the primary goal

- How it works: optimize the serving numbers ADR-0001 already requires.
- Pros: directly measured today; no cost-accounting decisions needed.
- Cons: higher throughput can come with idle hardware, failures, or a costlier
  instance, and still read as success. It rewards the diagnostic, not the outcome.
- Rejected because: throughput is an input to cost, not the cost.

### Option B — A balanced scorecard of cost, latency, throughput, and quality

- How it works: track several metrics with equal standing.
- Pros: nothing is ignored.
- Cons: no tie-break. Any change improves something on the card, so any change can be
  called progress.
- Rejected because: it does not settle which result wins when metrics disagree.

### Option C — Cost per 1000 inferences (ADR-0001's Phase 3 metric)

- How it works: total cost divided by requests served.
- Pros: maps to what a product team pays per call.
- Cons: depends on how many tokens each request generates, so two configurations
  are comparable only on an identical length mix. It also counts failed requests
  unless defined otherwise.
- Rejected because: cost per successful output token normalizes for length and
  excludes failures by definition.

### Option D — Cost per 1M successful output tokens, with service constraints (chosen)

- How it works: as in Decision.
- Pros: one number decides; failures cannot lower it; latency, reliability, and
  quality stay binding as constraints.
- Cons: see Consequences.

---

## Consequences

**Accepted costs.**

- Input tokens and prefill work are not in the denominator. A workload with long
  prompts and short answers looks expensive per output token. Charon's fixed prompt
  set keeps comparisons fair inside the project, but the figure does not transfer
  directly to other workloads.
- Diagnostic work (profiling, rooflines) has to justify itself by a cost hypothesis.
  Some interesting investigations will not be done.
- No cost comparison is possible until the accounting definitions are recorded, which
  is extra owner work before the metric can be used.

**Operational burden.** Every results file that compares configurations needs a cost
line under one fixed accounting method, plus a check of the service constraints.

**Reversibility.** Cheap to reverse on paper, but reversing it would reopen the
"every activity is progress" failure mode this ADR closes.

**Blast radius if wrong.** Documentation and prioritization only. No measured result
changes.

---

## One-time edit of accepted ADRs

On 2026-10-23 the owner authorized, **for this decision only**, direct edits to
accepted ADRs so that the goal reads the same everywhere. This is an exception to
`adr/README.md`'s immutability rule, not a change to it. Each edited ADR carries a
`Revised: 2026-10-23` line that names what changed:

- **ADR-0001:** Context names the primary objective; Phase 3's "cost per 1000
  inferences" becomes "cost per 1M successful output tokens"; every phase reports the
  primary metric once the accounting method exists; a regression is reported as a
  regression.
- **ADR-0002:** states that GCP is an implementation choice under this ADR. The
  decision is unchanged.
- **ADR-0003:** milestone configurations are chosen under this ADR's decision rule.
  The decision is unchanged.

---

## Non-goals

- Not a definition of the accounting scope, success criteria, or service limits.
  Those are recorded separately (Follow-ups).
- Not a claim that any change so far has reduced cost.
- Not a ban on diagnostics. Profiling stays useful when it is attached to a cost
  hypothesis.

---

## Follow-ups

- [ ] Owner: record the cost-accounting definitions in `benchmarks/methodology.md`
      (listed there under "Not yet decided").
- [ ] Owner: reconcile the ₹41.9/h and ₹69/h rates, or choose the authoritative
      source (for example a billing export).
- [ ] Owner: decide whether ADR-0003 rule 6 ("cut Milestone 7" if Milestone 6 is not
      run) still holds, since Milestone 7 is the cost model.
- [ ] Add a cost line to each results file that compares configurations, from
      Milestone 3 on.
- [ ] Revisit if a constraint (latency, reliability, quality) repeatedly decides
      outcomes over cost, which would suggest the hierarchy is wrong for this project.
