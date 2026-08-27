# Charon worklog

Running log of work sessions, newest first. The **Now** block is the single
source of truth for where things stand; **Sessions** is the append-only history.
Maintained by `/start-day` and `/end-day`, but it is a plain file — hand-edit it
whenever the commands get it wrong.

Rules for this file:
- It records **paths, not numbers**. A measured figure lives in
  `benchmarks/results/`; nothing else counts as a result.
- "session" here means a work session. The paid GPU instance is always the
  "GPU session" or "measurement session", kept verbally distinct.
- README "Current status" is the curated, owner-edited claim that moves at phase
  boundaries. This file is the fast, session-granular log. They will disagree
  between phase boundaries; that is expected.

Phase 1 started: not yet

## Now

- **Phase / week:** Phase 1 not started. Week 1 (naive baseline) is next — see
  `docs/phase-1-plan.md`. Hardware decision is already settled: no local GPU, so
  every week runs on a `g2-standard-4` spot instance batched into 3–4 hour
  measurement sessions.
- **In progress:** nothing. Scaffolding only — repo structure, docs, session
  scripts, ADR-0001/0002.
- **Next actions:**
  - Choose the Week 1 model: one 1–3B open-weights instruct model. Pin its
    revision hash.
  - Write the naive server in `serving/` — plain `transformers` behind a minimal
    FastAPI endpoint, one request at a time, no batching. Develop and smoke-test
    locally on CPU.
  - Scope the first measurement session: Week 1 metrics at concurrency 1 (TTFT,
    TPOT, end-to-end latency, output tok/s, GPU util, VRAM). Estimate GPU-hours
    and keep it to a single 3–4 hour block.
- **Open questions / blockers:**
  - `docs/incident-000-cpu-inference.md` still leaves one gap open: decode
    bandwidth explains only a fraction of the recalled 20–30 min CPU reply;
    prefill on a long system prompt, thermal throttling, swapping, and iGPU bus
    contention are unranked suspects. Not chased directly — the machine was an
    office laptop and is unrecoverable (model tag and memory config both closed
    as unrecoverable in the doc). The Week 1 controlled CPU baseline, on the GCP
    instance's own CPU, is what addresses it.
- **Budget:** ₹1,000/month, ~36–40 GPU-hours (working estimate). Spent this
  month: 0h (hand-tracked). Nothing measured yet.
- **Last session:** —

## Sessions

<!-- new entries here -->
