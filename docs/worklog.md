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

Phase 1 started: 2026-08-27

## Now

- **Phase / week:** Phase 1, Week 1 (naive baseline) — in progress. The server is
  built and CPU-smoke-tested; the Week 1 measurement (concurrency-1 metrics, first
  row of the benchmark table) is not done, so the Week 1 exit condition is not met.
- **In progress:** Week 1 baseline. `serving/naive_server.py` done; no measurement
  runner yet, no GPU session yet.
- **Next actions:**
  - Build the baseline runner (local CPU dev): fixed prompt set, warmup discard,
    ≥3 runs, percentile aggregation over the server's per-request metrics, plus
    `nvidia-smi` sampling for GPU util. Not the Week 2 load generator — just enough
    for the concurrency-1 row.
  - Estimate GPU-hours for the first measurement session; scope it to one 3–4h
    block.
  - First measurement session on `g2-standard-4` spot: Week 1 concurrency-1
    metrics → baseline row committed under `benchmarks/results/`.
- **Open questions / blockers:**
  - `docs/incident-000-cpu-inference.md` still leaves one gap open: decode
    bandwidth explains only a fraction of the recalled 20–30 min CPU reply;
    prefill on a long system prompt, thermal throttling, swapping, and iGPU bus
    contention are unranked suspects. Not chased directly — the machine was an
    office laptop and is unrecoverable (model tag and memory config both closed
    as unrecoverable in the doc). The Week 1 controlled CPU baseline, on the GCP
    instance's own CPU, is what addresses it.
  - Serving stack is transformers 5.x / torch 2.13 (pinned in `uv.lock`).
    Recalled APIs are 4.x-shaped — verify against the installed version before
    relying on remembered behaviour (CLAUDE.md version-drift rule).
  - Week 6 scale-up: the instance is deleted per GPU session, so a 7B checkpoint
    re-downloads every time (~5–15 GB). Decide GCS model cache vs. eat the
    download during Week 6 scoping.
  - `scripts/cost-check.sh` needs `CHARON_PROJECT_ID` set in the shell to be
    useful at session start; currently unset locally.
- **Budget:** flexible target ~₹1,000/month ≈ ~24 GPU-hours at current spot list
  price (~₹42/hr all-in, checked 2026-08-28 — `docs/gcp-setup.md`); extendable if
  a measurement needs it. Spent this month: 0h (hand-tracked). No GPU session yet.
- **Last session:** 2026-08-27 — session tooling built; incident-000 corrected;
  Week 1 model chosen; naive baseline server written and CPU-smoke-tested.

## Sessions

<!-- new entries here -->

### 2026-08-27

**Done — committed**
- `/start-day` and `/end-day` slash commands + this worklog (Now block +
  append-only Sessions). Drafted, reviewed by Opus, then landed. (`0ba0462`)
- incident-000 correction: response time ~5 min → ~20–30 min, status
  Measured → Recalled; token arithmetic reworked (~6–9k implied output tokens,
  which widens the unexplained gap); the two forensic TODOs closed as
  unrecoverable (office laptop, no access). Propagated to README and this
  worklog. (`a680d29`)
- Week 1 model decision recorded — see Decisions. (`8287ec2`)
- `serving/naive_server.py` — naive single-stream baseline: FastAPI +
  `transformers.generate`, one request at a time behind a global lock, greedy,
  forced output length; per-request `ttft_s` / `tpot_s` / `e2e_s` / `itl_s` /
  `peak_vram_bytes`; `/healthz` records the environment. Per-token timing via a
  `LogitsProcessor`. Plus `pyproject` `[dependency-groups] serving`,
  `[tool.uv] package = false`, and `uv.lock`. Smoke-tested on CPU. (`8555a6c`)

**Tried, didn't work**
- Per-token timing via a `StoppingCriteria` subclass — transformers 5.x changed
  the `__call__` return contract. Switched to a `LogitsProcessor` before the
  first run.
- `torch_dtype="auto"` — renamed to `dtype=` in transformers 5.x. Server now
  tries the new name and falls back to the old.

**Discussed, not started**
- Baseline runner for the concurrency-1 measurement — proposed, not begun.
- GPU-hours estimate for the first measurement session.
- Week 6 per-session checkpoint re-download (GCS cache vs. eat it) — deferred to
  Week 6 scoping.
- Local-CPU-dev vs all-on-GCP workflow — raised and resolved: keep the
  documented workflow (develop/debug locally on CPU, measure only on GCP).

**Decisions**
- Week 1 model: `Qwen/Qwen2.5-1.5B-Instruct`, revision
  `989aa7980e4cf806f80c7fef2b1adb7bc71aa306`. Apache 2.0, plain instruct (no
  thinking mode), same-generation path to `Qwen2.5-7B-Instruct` for Week 6.
  Reversible benchmark input, not an ADR; rationale to be written up in
  `benchmarks/methodology.md` in Week 2.
- No ADR owed this session.

**Numbers committed**
- none. (CPU smoke-test timings are a correctness check, not a result — not
  recorded here per the paths-not-numbers rule.)

**GPU**
- Used this session: no — all work was local CPU. Approx GPU-hours: 0.
  Teardown verified by cost-check: not-checked (`CHARON_PROJECT_ID` unset; no
  instance was ever created this session).

**Left for next time**
- Build the baseline runner, then estimate and scope the first measurement
  session.
