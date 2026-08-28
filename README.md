# Charon

A self-service inference platform where a model artifact is deployed, optimized, rolled
out safely, and measured for cost per token — with the optimization path as a
first-class, benchmarked deployment target.

Charon is the ferryman: every request crosses a boundary, and every crossing has a toll.
Here the toll is cost per token, and the engineering discipline of this project is about
lowering the fare — deliberately, and with numbers to show for it.

This is a learning and portfolio project, built by a data engineer moving into ML
infrastructure. It is in progress. Nothing below should be read as finished, and nothing
is listed as a feature until it has been built and measured.

---

## Where this started

The project exists because of a 20-to-30-minute Slack reply from a local CPU-only LLM in
a production bot (a wall time recalled after the fact, not logged). The full writeup —
what's actually known, what's assumed, and the open question that's still unresolved — is
in
[`docs/incident-000-cpu-inference.md`](docs/incident-000-cpu-inference.md). It is a
motivating observation, not a benchmark; it's uncontrolled and not comparable to
anything measured later on the actual GPU. The first controlled number in this repo
comes from Phase 1, Week 1.

## Governing rule

Every phase must produce a measured number, on real hardware, committed to the repo — or
the project has drifted into content consumption. This is the project's actual
constitution: [`adr/0001-measurement-discipline.md`](adr/0001-measurement-discipline.md).
Generated benchmark *code* is never the deliverable here; committed *results* from real
runs are.

## What's measured so far

Nothing yet. This table exists now so the columns are fixed before the first row is
written — the schema is a decision, not an afterthought bolted on after Week 3.

| Variant | Throughput (req/s) | Output tok/s | TTFT p50 | TTFT p99 | TPOT | GPU util | VRAM | Cost / 1M tokens |
|---|---|---|---|---|---|---|---|---|
| _(empty — Week 1 fills the first row)_ | | | | | | | | |

## Current status

**Phase 1, not yet started.** Scaffolding — repo structure, documentation, and tooling —
is in place. No serving, benchmarking, or infrastructure code has been written yet;
those are deliberate decisions made phase by phase, not generated up front. See
[`docs/phase-1-plan.md`](docs/phase-1-plan.md) for the week-by-week plan.

## Phases

1. **Inference mechanics** — batching, KV cache, quantization, the latency/throughput
   curve. Physical intuition for what happens between a request arriving and a token
   coming back.
2. **Compilation and hardware** — `torch.compile`, TensorRT, profiling with Nsight.
3. **Platform** — GKE, model registry, promotion, canary rollout, SLO-driven rollback.
4. **Scale and reliability** — spot interruption, autoscaling on queue depth, capacity
   planning.

Each phase's required number is defined in
[`adr/0001-measurement-discipline.md`](adr/0001-measurement-discipline.md).

## Constraints

- **Budget: target ~₹1,000/month, flexible.** At current spot list price that is
  ~24 GPU-hours (~₹42/hour all-in; checked 2026-08-28, see
  [`docs/gcp-setup.md`](docs/gcp-setup.md)). Extendable when a measurement needs
  it — the number is a planning target; the GPU-on discipline below is the real
  constraint.
- **Hardware:** `g2-standard-4` (1× NVIDIA L4, 24 GB VRAM), spot only,
  `us-central1` primary (`asia-south1` preemptible-CPU quota is not adjustable —
  see [`docs/gcp-setup.md`](docs/gcp-setup.md)).
- **Single cloud:** Google Cloud, deliberately, even though other projects here run on
  AWS. The reasoning is recorded as an ADR rather than left implicit.
- **GPU-on discipline:** the instance is powered on only while a measurement is actively
  running. All development, debugging, analysis, and writing happens locally on CPU.
  Instances are created and deleted per session — never left stopped, since the 100 GB
  boot disk alone bills hundreds of ₹/month for a box doing nothing.

See [`CLAUDE.md`](CLAUDE.md) for the working agreement on AI-assisted work in this repo,
and [`adr/`](adr/) for the decision log.
