# Architecture Decision Records

Decision log for the AI Infrastructure / MLOps platform.

## Conventions

- Files are named `NNNN-kebab-case-title.md`, numbered sequentially, never renumbered.
- ADRs are immutable once **Accepted**. To change a decision, write a new ADR and mark
  the old one `Superseded by ADR-NNNN`. Do not edit history.
- Titles state the decision, not the topic. `0007-serve-on-cpu-by-default` beats
  `0007-serving-strategy`.
- One decision per ADR. If the title needs "and", split it.

## When to write one

Write an ADR when a choice is **expensive to reverse** or **non-obvious to a future
reader**:

- Serving stack, batching strategy, or quantization level
- Compilation target and when the compiled path is used
- Model registry, artifact format, promotion path
- Instance types, spot vs on-demand, autoscaling signal
- Anything where you rejected the obvious option

Do not write one for reversible implementation detail. Library choices, file layout, and
naming go in code review or `CLAUDE.md`.

## Status lifecycle

```
Proposed  →  Accepted  →  Superseded / Deprecated
```

An ADR touching performance, cost, or capacity **cannot move to Accepted with an empty
Measured evidence section.** Until numbers exist it is a hypothesis, and hypotheses stay
`Proposed`. See [ADR-0001](0001-measurement-discipline.md).

## Monthly review

Run alongside the existing Cerberus review:

1. **Drift check** — has a new number entered a benchmark table in the last 30 days?
   If not, all new work stops until one does. (ADR-0001)
2. Any `Proposed` ADR older than 30 days — measure it or close it.
3. Any ADR whose revisit trigger has fired.
4. Cost review — is anything running that should have been torn down?

## Working with AI assistance

Architecture decisions are the author's; implementation is delegable. Applied to this
directory:

- ADRs are written by hand, or drafted with assistance and then argued with. An ADR you
  did not interrogate is not a decision, it is a summary.
- The **Options considered** and **Consequences** sections are where the thinking lives.
  If those read as generic, the ADR is decoration.
- Generated benchmark code is not evidence. Only committed results from real runs are.

## Index

| ADR | Title | Status |
|-----|-------|--------|
| [0000](0000-adr-template.md) | Template | — |
| [0001](0001-measurement-discipline.md) | Every phase must produce a measured number | Accepted |
