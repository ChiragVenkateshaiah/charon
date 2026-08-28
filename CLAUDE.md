# Working agreement: AI assistance on Charon

This file governs how AI assistance (Claude Code or otherwise) operates in this repo.
It exists because the failure modes of AI-assisted infrastructure work are specific and
predictable, and this document is how they get headed off in advance rather than argued
about mid-task.

## Who decides what

**Architecture decisions are mine. Implementation is delegable.**

Choice of serving stack, batching strategy, quantization level, compilation target,
instance type, cloud provider, scaling signal — these get decided by the project owner,
argued with, and recorded in `adr/`. An AI assistant may draft an ADR, propose options,
or point out a tradeoff that was missed, but the decision and the "why" belong to the
owner. An ADR that reads as generic, or that wasn't interrogated before being accepted,
is decoration, not a decision. See `adr/README.md` for the full convention.

Writing code, debugging, running the load generator, fixing a broken benchmark script,
scaffolding boilerplate — all of that is fair game to delegate.

## Measurement discipline

This is the project's core constraint, and it binds AI assistance specifically:

- **Never assert a performance, cost, or capacity number that wasn't measured on real
  hardware in this project.** Not from training data, not from "typically," not from a
  vendor benchmark, not from a similar-sounding setup. If a number would be useful and
  none exists yet, say so and propose how to measure it.
- **Flag every suggested figure explicitly as a hypothesis** if it isn't backed by a
  committed result in `benchmarks/results/`. "This should be roughly 2x faster" is a
  hypothesis, not a finding, and must be labeled as one in whatever gets written.
- **Generated benchmark harness code is not progress.** A convincing load-testing
  script, a benchmarking framework, a nicely formatted results table with placeholder
  numbers — none of these are deliverables. Only committed results from real runs on
  real hardware count. See `adr/0001-measurement-discipline.md`.
- **This rule applies to every document in the repo, permanently** — README, ADRs,
  incident writeups, benchmark methodology, everything. Where a number is estimated
  rather than measured, it must be visibly labeled as an assumption. `docs/incident-000-
  cpu-inference.md` is the reference example for how to do this: an explicit
  Measured / Estimated / Unknown table, and an honest gap left open rather than papered
  over with a plausible-sounding guess.

## Version drift

vLLM, TensorRT, and PyTorch move fast enough that recalled flags, APIs, and defaults go
stale within a few releases. Check current docs for the actual installed version before
relying on remembered behavior — especially for CLI flags, config schema, and anything
related to quantization or compilation, where breaking changes are common. Don't assume
an API surface from a stale mental model.

## The budget

**Target budget: ~₹1,000/month, flexible.** At current spot list price (~₹42/hour
all-in for a `g2-standard-4` + L4 in `us-central1`, checked 2026-08-28 — see
`docs/gcp-setup.md`) that is ~24 GPU-hours. The budget can be extended when a
specific measurement needs it; it is a target to plan against, not a wall.

The **discipline** is not flexible. Any suggestion that involves a running GPU
instance must account for it explicitly:

- The GPU is powered on only while a measurement is actively running. Development,
  debugging, analysis, and writing happen locally on CPU — don't suggest spinning up the
  instance for anything that doesn't need the GPU.
- Instances are created and deleted per session via `scripts/session-start.sh` /
  `scripts/session-end.sh`, never left stopped — the 100 GB boot disk alone bills
  ~₹400–950/month (depending on disk type) for a box doing nothing.
- Before proposing a benchmark run, estimate its GPU-hours (and so its rough cost) and
  say so. Sessions should be scoped and time-boxed, not open-ended "let's try a few
  things while it's up."
- If asked to help debug something GPU-related, prefer reasoning from logs, code, and
  prior committed results over "spin it up and see."

## Conventions

- **ADRs for expensive-to-reverse decisions.** Serving stack, batching strategy,
  quantization level, compilation target, model registry/promotion path, instance
  types, spot vs. on-demand, autoscaling signal, or anywhere the obvious option was
  rejected. Template and full guidance in `adr/README.md`. Reversible implementation
  detail (library choice, file layout, naming) doesn't need one.
- **Benchmark methodology is fixed once set, and not to be silently changed between
  runs.** The seven rules in `benchmarks/methodology.md` (fixed token counts, discarded
  warmup, percentiles not averages, three runs minimum, recorded environment, one
  variable per experiment, committed raw output) apply to every run. If methodology
  needs to change, that's a deliberate decision to call out explicitly, not a drift.
- **No tooling additions beyond what's been chosen.** Don't introduce Docker Compose,
  CI pipelines, pre-commit hooks, or similar without being asked — these are decisions
  the owner makes deliberately, typically with an ADR, not defaults to inherit from a
  generic project template.
