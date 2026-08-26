# ADR-0001: Every phase must produce a measured number

- **Status:** Accepted
- **Date:** 2026-08-23
- **Phase:** All
- **Deciders:** Chirag

---

## Context

This project exists to build employable AI infrastructure skill, not to accumulate
knowledge about AI infrastructure. Those two goals look identical from the inside and
diverge completely in outcome.

The specific failure mode: performance and platform work has a large surface of
*plausible activity* — reading about continuous batching, scaffolding a benchmark
harness, configuring a serving stack, comparing tools on paper. All of it feels like
progress. None of it produces the thing interviews actually probe for, which is a
causal story: *it was doing X, the bottleneck was Y, I changed Z, now it does 3X.*

The risk is amplified by an AI-assisted workflow. A convincing benchmark harness can be
generated in minutes. Generating the harness is not measuring. The artifact that looks
like the work is not the work.

---

## Decision

Every phase of this project must produce at least one **new measured number**, recorded
in a committed benchmark table, before that phase is considered complete.

Qualifying numbers, by phase:

| Phase | Required number |
|-------|-----------------|
| 1 — Inference mechanics | Throughput and p50/p99 latency across at least three serving configurations |
| 2 — Compilation & hardware | Before/after figures for a compiled variant, plus the profiler evidence explaining *why* it changed |
| 3 — Platform | Time-to-deploy, time-to-rollback, and cost per 1000 inferences |
| 4 — Scale & reliability | Behaviour under spot interruption and under load beyond capacity |

A number qualifies only if it was produced on real hardware by a reproducible run whose
raw output is committed to the repo.

---

## The drift check

**Standing review question, applied monthly:**

> Has a new number entered a benchmark table in the last 30 days?

- **Yes** → continue.
- **No** → the project has drifted into content consumption. Stop all new work. The next
  work item is a measurement, chosen from the current phase's required list. No new
  tools, no new reading, no refactoring until a number lands.

This check is not advisory. It is the gate.

---

## Consequences

**Accepted costs.** Progress will feel slower and less broad. Fewer technologies will be
touched. Some interesting tools will go unexplored because measuring three things well
beats configuring ten things shallowly.

**Operational burden.** Benchmark methodology has to be good enough that the numbers
mean something — fixed hardware, discarded warmup, stated concurrency, multiple runs.
Sloppy numbers are worse than no numbers, because they produce false confidence and
collapse under interview questioning.

**Reversibility.** Cheap. But reversing it is the failure mode this ADR exists to
prevent, so treat any argument for suspending the gate as evidence the gate is working.

---

## Non-goals

- Not a demand for *impressive* numbers. A change that made things 15% worse, understood
  and explained, is a valid deliverable.
- Not a ban on reading or learning. It is a constraint on what counts as phase
  completion.
- Not benchmarking rigour at publication standard. Internal consistency and honest
  methodology notes are sufficient.

---

## Follow-ups

- [ ] Create `benchmarks/` in the repo with a fixed results schema
- [ ] Record hardware profile and load-generator config once, reference thereafter
- [ ] Add the drift check to the monthly review, alongside the Cerberus teardown check
- [ ] Note in `CLAUDE.md` that generated benchmark code is not a deliverable; results are
