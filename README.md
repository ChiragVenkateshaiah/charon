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

## Project Goal and Primary Success Metric

**Charon's primary objective is to minimize serving cost per 1 million successful
generated output tokens**, subject to acceptable latency, reliability, and
output-quality requirements. Charon succeeds by lowering that number — not by
maximizing GPU utilization or tokens per second, and not by adopting any particular
framework.

The primary metric:

```
Cost per 1M successful output tokens = (Total serving cost / Total successful generated output tokens) × 1,000,000
```

**Before any cost claim is comparable, the project must define and apply consistently:**

- the cost-accounting scope (what counts as "total serving cost");
- what makes a request successful;
- how output tokens are counted;
- how failed requests, idle time, and other serving costs (setup, disk, egress) are
  treated.

None of these is defined yet (see "Open definitions" below). Until they are, no
figure in this repo is the primary metric — at most an estimate of it.

**The hierarchy** — recorded in
[`adr/0004`](adr/0004-cost-per-1m-successful-output-tokens-is-the-sole-primary-goal.md)
and kept the same across every document in this repo:

| Level | What | Role |
|---|---|---|
| **Primary goal** | Cost per 1M successful output tokens | The only measure of project success. |
| **Mandatory service constraints** | Latency, reliability, output quality | Must stay within defined acceptable limits. Actively optimized where evidence shows it is valuable, but not competing primary goals. |
| **Optimization dimensions** | Latency, reliability, output quality, throughput, resource efficiency | Improved where that lowers cost or enables more cost-efficient serving. |
| **Diagnostic metrics** | GPU utilization, memory use, kernel activity, CPU overhead, queueing (and TTFT/TPOT breakdowns) | Explain why serving costs what it does and where a change may lower it. |
| **Implementation choices** | Profiling tools, concurrency strategies, vLLM, Kubernetes, other technologies | Means to the objective, never goals in themselves. |

**Decision rule for every optimization:**

1. Measure the current cost per 1M successful output tokens using a consistent
   accounting method.
2. Identify a cost-relevant limitation using evidence.
3. Form a hypothesis explaining how changing that limitation could reduce cost.
4. Run a controlled experiment and measure the resulting cost metric.
5. Check the effects on latency, reliability, output quality, and relevant operational
   constraints.
6. Accept the change as an improvement only if it produces a credible cost benefit
   without violating required service constraints. If cost does not improve, do not
   claim success because another metric improved.

**What is not success.** A better latency, throughput, or utilization figure on its
own. It counts when it demonstrably reduces cost, enables lower-cost serving, or is
needed to meet a service constraint. Equally, a lower apparent cost bought with
excessive failures, unacceptable latency, or degraded output quality is not success.
When a change improves quality or reliability but raises cost, the trade-off is
reported openly; cost regressions are never hidden behind secondary metrics.

### Current cost estimates — not a baseline

**ESTIMATED, NOT MEASURED.** Two estimates exist, both derived from the Week 1
measured decode throughput (34.5 output tok/s, one stream, concurrency 1) and an
hourly rate that Charon did not measure:

| Hourly rate assumed | Source of the rate | Estimate |
|---|---|---|
| ~₹41.9 / GPU-hour | GCP spot list price, all-in ([`docs/gcp-setup.md`](docs/gcp-setup.md)) | **≈ ₹337 per 1M output tokens** |
| ~₹69 / GPU-hour | Owner-supplied observed effective rate; not traced to a committed billing record ([`docs/week1-roofline.md`](docs/week1-roofline.md)) | **≈ ₹556 per 1M output tokens** |

The two rates have not been reconciled, so neither estimate is the definitive cost
baseline. Both assume 100% duty — every billed second spent generating, with no idle
time, setup, or prefill — so real cost per token is higher. Neither uses the
"successful output tokens" definition above, because it does not exist yet. No
optimization in this repo has been shown to reduce cost; that claim needs comparable
before-and-after evidence.

### Open definitions (owner decisions)

ADR-0004 requires these to be recorded in
[`benchmarks/methodology.md`](benchmarks/methodology.md) before any cost figure is
compared across configurations:

- Cost-accounting scope: GPU-hours only, or the whole session (boot, model download,
  teardown, boot disk)?
- Which hourly rate is authoritative, and how is it sourced (list price or billing
  export)?
- Success criteria for a request, and the latency, reliability, and quality thresholds
  that constrain the metric.
- Output-token counting method, and how failed requests and idle time enter the
  numerator and denominator.

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

One serving configuration so far: the naive server
([`serving/naive_server.py`](serving/naive_server.py) — plain `transformers.generate`,
one generation at a time, no batching), `Qwen/Qwen2.5-1.5B-Instruct` bf16, on one L4
spot instance, 128 forced output tokens. Concurrency is a load level, not a
configuration (ADR-0003 rule 9), so the rows below are one configuration at different
loads. Every value is copied from a committed result; the full tables, spreads, and
environment are in the linked files.

| Variant | Throughput (req/s) | Output tok/s | TTFT p50 | TTFT p99 | TPOT p50 | GPU util | VRAM (peak) | Cost / 1M successful output tokens |
|---|---|---|---|---|---|---|---|---|
| Naive, concurrency 1 — [Week 1](benchmarks/results/2026-08-28-week1-baseline.md) | not reported | 34.50 ¹ | 32.1 ms | 35.0 ms | 29.0 ms | 53% | 3.106 GB | not measured ³ |
| Naive, concurrency 1 — [Milestone 2](benchmarks/results/2026-10-19-milestone2-sweep.md) | 0.2659 | 34.04 ² | 32.7 ms | 36.4 ms | 29.34 ms | 51–52% | 3.370–3.438 GB | not measured ³ |
| Naive, concurrency 32 — [Milestone 2](benchmarks/results/2026-10-19-milestone2-sweep.md) | 0.2649 | 33.91 ² | 35.0 ms | 44.6 ms | 29.41 ms | 51–52% | 3.370–3.438 GB | not measured ³ |

¹ Per-request decode throughput, p50. ² Aggregate output tok/s across concurrent
requests (methodology decision 4). TTFT and TPOT are server-reported and exclude time
waiting for the server's generation lock. GPU util is `nvidia-smi` busy time during
in-flight windows. VRAM is `torch.cuda.max_memory_allocated`.
³ The primary metric is not measured yet, because its definitions are still open (see
above). The ₹337 / ₹556 figures are estimates, not entries for this column.

**What the numbers say:** throughput is flat from concurrency 1 to 32 (~34 output
tok/s) because this server runs one generation at a time. More load adds only queueing
delay, so for this configuration cost per token cannot fall with load. Concurrency 64
is left out here because its throughput figure is distorted by bursty delivery — see
§ 2 of the Milestone 2 result.

## Current status

**Phase 1.** Milestone 2 (load generation and the latency/throughput curve) was closed
by the owner on 2026-10-21. **Milestone 1 (naive baseline) is still open, so it is
still the current milestone** (ADR-0003 rule 4): it still needs an explanation of the
Week 1 TTFT p99 spread (methodology rule 4), and the owner must review it.

- Serving configurations measured: **1** — against a minimum of three (ADR-0001) and a
  Phase 1 target of six (ADR-0003 rule 8). The ADR-0003 Week 4 checkpoint (≥ 4
  configurations) is recorded as unmet.
- Cost per 1M successful output tokens: **not measured**; estimates only (see
  "Current cost estimates").
- Next planned measurement: Milestone 3 (batching — static batching and a
  continuous-batching server), which is in planning and not started. *Hypothesis, not
  a finding:* batching is the first change that can raise aggregate throughput on this
  hardware and so lower cost per token.

See [`docs/worklog.md`](docs/worklog.md) for session-level detail and
[`docs/phase-1-plan.md`](docs/phase-1-plan.md) for the plan (calendar weeks there are
reporting periods; milestones are authoritative — ADR-0003).

## Phases

1. **Inference mechanics** — batching, KV cache, quantization, the latency/throughput
   curve. Physical intuition for what happens between a request arriving and a token
   coming back.
2. **Compilation and hardware** — `torch.compile`, TensorRT, profiling with Nsight.
3. **Platform** — GKE, model registry, promotion, canary rollout, SLO-driven rollback.
4. **Scale and reliability** — spot interruption, autoscaling on queue depth, capacity
   planning.

Each phase's required number is defined in
[`adr/0001-measurement-discipline.md`](adr/0001-measurement-discipline.md). The phases
are the route, not the goal: each one is judged by what it shows about cost per 1M
successful output tokens (see "Project Goal and Primary Success Metric").

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
- **GPU-on discipline:** the GPU is for learning and measurement sessions
  ([ADR-0005](adr/0005-gpu-sessions-for-learning-and-measurement.md)). Every session
  has a stated goal, a time box and a GPU-hour estimate. Instances are created and
  deleted per session — never left stopped, since the 100 GB boot disk alone bills
  hundreds of ₹/month for a box doing nothing. Exploration runs are not results, and
  session spend is not serving cost.

See [`CLAUDE.md`](CLAUDE.md) for the working agreement on AI-assisted work in this repo,
and [`adr/`](adr/) for the decision log.
