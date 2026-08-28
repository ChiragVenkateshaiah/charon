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
- README "Current status" is the curated, high-level claim — kept accurate but
  deliberately not session-granular. This file is the fast, session-granular log
  and carries the detail the README summarises.

Phase 1 started: 2026-08-27

## Now

- **Phase / week:** Phase 1, Week 1 (naive baseline) — in progress. Server and
  concurrency-1 runner are both built and CPU-tested against each other; the Week 1
  measurement itself (concurrency-1 metrics, first row of the benchmark table) is
  not done, so the Week 1 exit condition is not met.
- **In progress:** Week 1 baseline. `serving/naive_server.py` and
  `benchmarks/baseline_runner.py` both done; dry-run on CPU confirmed the
  server/runner contract. No GPU session yet.
- **Next actions:**
  - Re-check the current L4 spot price in `us-central1` (`docs/gcp-setup.md` has
    the 2026-08-28 figure) and set `CHARON_PROJECT_ID` on the second machine if
    it will be used.
  - First measurement session on `g2-standard-4` spot in `us-central1`: start
    `naive_server`, run `baseline_runner.py`, commit the Week 1 concurrency-1
    baseline row under `benchmarks/results/`. Estimated well under 1 GPU-hour of
    run time; book ~2–3h for setup and margin.
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
  - The wired fallback zone `asia-south1-a` is effectively dead until its
    `PREEMPTIBLE_CPUS` quota becomes adjustable — if `us-central1-a` spot
    capacity is unavailable, `session-start.sh` fails rather than falling back.
    Acceptable (fails loud); self-heals if the quota opens.
- **GCP:** ready. Project `charon-506614`, Compute Engine API on, quota approved
  (`GPUS_ALL_REGIONS`=1, `PREEMPTIBLE_CPUS` us-central1=8, L4 spot=1), budget
  alert live, `us-central1` primary (`asia-south1` preemptible-CPU quota not
  adjustable). Full detail in `docs/gcp-setup.md`.
- **Budget:** flexible target ~₹1,000/month ≈ ~24 GPU-hours at current spot list
  price (~₹42/hr all-in, checked 2026-08-28 — `docs/gcp-setup.md`); extendable if
  a measurement needs it. Spent this month: 0h (hand-tracked). No GPU session yet.
- **Last session:** 2026-08-28 — concurrency-1 baseline runner built + CPU
  dry-run against `naive_server`; GCP fully provisioned (API, quota, budget
  alert, `us-central1` promoted to primary); L4 spot price checked; ₹1,000
  budget reframed repo-wide as a flexible target (~24 GPU-hours).

## Sessions

<!-- new entries here -->

### 2026-08-28

**Done — committed**
- `benchmarks/baseline_runner.py` + `benchmarks/prompts/baseline.json` +
  `benchmarks/README.md` — the concurrency-1 baseline runner. Stdlib only (no new
  deps); drives `naive_server` one request at a time, aggregates the server's own
  per-request metrics as p50/p95/p99 across ≥3 runs with cross-run spread, samples
  `nvidia-smi` over in-flight request windows, pulls the environment from
  `/healthz`, writes raw JSON to `benchmarks/results/`. Encodes the seven
  methodology rules; warns on violations. Not the Week 2 load generator. Dry-run
  on CPU against `naive_server` confirmed the server/runner contract (field names,
  forced output length, warmup discard, null-VRAM path, results schema).
  Provisional prompt set — canonical set stays a Week 2 decision. (`88f8207`)
- `docs/gcp-setup.md` — new: the full GCP groundwork record. Project
  `charon-506614`, Compute Engine API enabled this session, `CHARON_PROJECT_ID`
  env setup for the two-machine workflow, quota state, request list, Cost section,
  re-check snippets. (`66f54a2` + later commits)
- GCP provisioning:
  - `us-central1` promoted to primary zone in `scripts/session-start.sh`,
    `asia-south1-a` demoted to fallback — asia-south1 `PREEMPTIBLE_CPUS` quota is
    not adjustable for this project. ADR-0002 follow-up updated. (`63f3ad2`)
  - Quota approved and verified via API: `GPUS_ALL_REGIONS`=1,
    `PREEMPTIBLE_CPUS` (us-central1)=8 (`PREEMPTIBLE_NVIDIA_L4_GPUS`=1 was
    already default). Billing budget alert created: ₹1,000/month, whole billing
    account, thresholds 50/90/100/150%. (`3f1cfd3`)
  - Default Gemini project deleted — Charon is the only project on the billing
    account. (`bd6dbfa`)
  - L4 spot price checked via the Cloud Billing Catalog API, recorded in
    `docs/gcp-setup.md` (Cost section). GCP list price, not a Charon
    measurement. (`0f41208`)
- Budget reframe: owner clarified the ₹1,000/month budget is a flexible target,
  not a hard cap. Replaced "hard constraint / 36–40 GPU-hours" with "flexible
  target / ~24 GPU-hours at spot list price" across `CLAUDE.md`, `README.md`,
  `adr/0002`, `docs/phase-1-plan.md`, this file, `docs/gcp-setup.md`, the
  `/start-day` and `/end-day` command files, and the three `scripts/` headers.
  GPU-on discipline unchanged and now the explicit constraint. (`4b5186a`,
  `74276df`)
- `README.md` "Current status" refreshed — was "Phase 1, not yet started / no
  serving code" (wrong); now "Phase 1, Week 1 — in progress". (`9ebc503`)

**Tried, didn't work**
- `gcloud beta quotas` (eligibility reason, CLI quota requests) — the `beta`
  component isn't installed; didn't auto-install it, used the console for all
  quota work.

**Decisions**
- **GPU zone: `us-central1` primary** (was `asia-south1`), forced by the
  non-adjustable asia-south1 preemptible-CPU quota. Within ADR-0002's scope —
  recorded in its follow-ups and `scripts/session-start.sh`; no new ADR.
- **Budget is a flexible target, not a hard cap** (owner). Softened directly in
  CLAUDE.md / README / ADR-0002; no new ADR.
- No ADR owed.

**Numbers committed**
- none. Still only `.gitkeep` under `benchmarks/results/`. The L4 spot price
  (~₹42/hr all-in) in `docs/gcp-setup.md` is a GCP list price, explicitly not a
  Charon measurement (ADR-0001).

**GPU**
- Used this session: no — all work was local CPU + GCP console/API. Approx
  GPU-hours: 0. Teardown verified by cost-check: n/a — cost-check ran clean (no
  instances, no disks); no instance was ever created.

**Left for next time**
- First measurement session on `g2-standard-4` spot in `us-central1`: start
  `naive_server`, run `baseline_runner.py`, commit the Week 1 concurrency-1
  baseline row. Re-check the L4 spot price first; set `CHARON_PROJECT_ID` on the
  second machine if it's used.
- `.gitignore` has an uncommitted `career/` line — the owner's intentional
  change, left for them.

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
