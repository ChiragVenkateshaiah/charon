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

- **Phase / week:** Phase 1 — **Week 1 complete.** First measured number is
  committed (`benchmarks/results/baseline-20260828T172338Z.json`, concurrency-1
  naive baseline on the L4) with an analysis that satisfies the Week 1 exit
  condition ("explain why a single-stream server underutilizes a GPU" —
  `benchmarks/results/2026-08-28-week1-baseline.md`). **Week 2 next: the
  concurrency sweep.**
- **In progress:** nothing half-built. Uncommitted: `docs/worklog.md` (this
  entry) and `.gitignore` (owner's `career/` line, not ours).
- **Next actions:**
  - **Week 2 — user drives the GPU provisioning by hand this time**
    (`session-start.sh`, SSH, bootstrap, run, teardown), one hands-on pass now
    that Week 1 de-risked the path; then back to scripted/delegated.
    Interpretation is never delegated. See memory `infra-provisioning-split`.
  - Write `scripts/session-bootstrap.sh` from the scratchpad `remote_run.sh`
    pattern — the repo provisions the box but has nothing for the on-box
    setup+run. Good first hands-on task.
  - Finalize `benchmarks/methodology.md` (Week 2 owns it): load-generator
    choice, canonical prompt set with fixed input length, hardware profile
    block, the standard concurrency-sweep levels.
  - Week 2 measurement session: concurrency sweep 1 / 2 / 4 / 8 / 16 / 32 / 64
    against the naive server → the throughput-vs-concurrency curve and its knee,
    committed under `benchmarks/results/`.
  - Before publishing the Week 1 articles: confirm
    `github.com/ChiragVenkateshaiah/charon` is public; re-check the L4 spot
    price on publish day.
- **Open questions / blockers:**
  - `docs/incident-000-cpu-inference.md` gap (carried): the recalled 20–30 min
    CPU reply is still unquantified against a controlled CPU baseline — needs a
    deliberate CPU run (separate from the GPU work).
  - transformers 5.x / torch 2.13 drift (carried): mostly navigated this
    session — `dtype=`, the `StoppingCriteria` change, and torch cu13 needing
    driver R580 all handled. Keep watching `generate()` kwargs.
  - Week 6 7B checkpoint re-download (carried) — GCS cache vs. eat it, decide at
    Week 6 scoping.
  - **L4 spot capacity in `us-central1` is tight** — this session hit stockout
    in 3 zones before `us-central1-c` took it. Week 2's session may need to try
    several zones (`session-start.sh` takes `CHARON_PRIMARY_ZONE` /
    `CHARON_FALLBACK_ZONE`). `asia-south1-a` is still dead (quota not adjustable).
  - `/healthz` doesn't capture driver / `nvidia-smi` detail — Environment tables
    hand-filled. Fix in the server for Week 2.
  - `Articles/` tracked-or-gitignored is an open owner decision.
- **GCP:** ready. Project `charon-506614`, Compute Engine API on, quota approved
  (`GPUS_ALL_REGIONS`=1, `PREEMPTIBLE_CPUS` us-central1=8, L4 spot=1), budget
  alert live, `us-central1` primary (`asia-south1` preemptible-CPU quota not
  adjustable). Full detail in `docs/gcp-setup.md`.
- **Budget:** flexible target ~₹1,000/month ≈ ~24 GPU-hours at current spot list
  price (~₹42/hr all-in, checked 2026-08-28 — `docs/gcp-setup.md`); extendable
  if a measurement needs it. Spent this month: **~1.1h** (hand-tracked; the Week
  1 measurement session).
- **Last session:** 2026-08-28 — first GPU measurement session: Week 1
  concurrency-1 baseline committed (the first measured number); analysis
  corrected after an Opus review; Medium + LinkedIn draft articles + charts
  written. ~1.1 GPU-hours.

## Sessions

<!-- new entries here -->

### 2026-08-28 — first GPU measurement session

**Done — committed**
- `scripts/session-start.sh` — the DLVM image family `common-cu124` was retired
  from `deeplearning-platform-release` ("resource not found" on create).
  Switched to `common-cu129-ubuntu-2204-nvidia-580` (driver R580, covers the
  CUDA-13 runtime libs bundled with the pinned torch 2.13). Verified present
  before launch. (`b55e7e3`)
- **First GPU measurement session.** Spot L4 stockout in `us-central1-a` / `-b`
  and `asia-south1-a`; instance landed in `us-central1-c` (via the script's zone
  env overrides). Ran `serving/naive_server.py` + `benchmarks/baseline_runner.py`
  at concurrency 1 → the Week 1 baseline, committed as
  `benchmarks/results/baseline-20260828T172338Z.json` (raw: 360 request records
  + 6683 nvidia-smi samples) plus the analysis writeup
  `benchmarks/results/2026-08-28-week1-baseline.md`. Instance deleted,
  cost-check clean. (`b0faad1`)
- Analysis corrections after an Opus review of the result + writeup: the
  weight-streaming argument had used peak VRAM where it meant weights;
  retitled "launch-overhead-bound, not bandwidth-bound"; the ~1% cross-run
  spread is p50 only (TTFT p99 spread is ~18%, one run's slow tail — the runner
  only gates p50); added a determinism check and a busy-time / bandwidth-ceiling
  cross-check. (`47ecaa5`)
- `Articles/` — draft Medium (~2.4k words) and LinkedIn-newsletter (~700 words)
  posts on the Week 1 result, four social-image charts, and
  `Articles/charts/mkcharts.py` (self-contained SVG→PNG via `rsvg-convert`,
  reads the committed result JSON). Reviewed by Opus; ~20 findings applied,
  incl. a methodologically-broken hero chart (log-scaled bars → dot plot) and
  unlabelled derived numbers. (`c211ddd`)

**Done — not yet committed**
- `docs/worklog.md` — this entry + Now-block rewrite.

**Tried, didn't work**
- First measurement run aborted at run 3 / 90 by an over-tight `timeout` on the
  SSH command driving it. `baseline_runner.py` writes its results file only
  after all runs finish, so nothing was salvageable. Re-ran as a detached
  process polled from the laptop. Measurement unaffected; wall-clock paid twice.
- `remote_run.sh` / `rerun.sh` / `drive_session.sh` — scratchpad orchestration
  for the on-box setup+run. Worked, but are session artifacts, not in the repo.

**Decisions**
- Instance created in `us-central1-c` this session (the `-a` primary and `-b`
  were stockout). No config change — `session-start.sh` env overrides handled
  it. No ADR owed.

**Numbers committed**
- `benchmarks/results/baseline-20260828T172338Z.json` — Week 1 naive baseline,
  concurrency 1, on the L4. **First committed measured result.** Analysis in
  `benchmarks/results/2026-08-28-week1-baseline.md`. (Metric values live in
  those files — paths-not-numbers rule.)

**GPU**
- Used this session: yes — one GCP spot L4 in `us-central1-c`. Approx
  GPU-hours: ~1.1 (hand-tracked; most of it spot-stockout retries + the aborted
  run, not the measurement). Teardown verified by cost-check: yes — instance
  deleted, no disks, ₹0 ongoing; re-verified at end-day.

**Left for next time**
- Week 2 concurrency sweep (1→64) against the naive server → the
  throughput-vs-concurrency curve and its knee.
- Build `scripts/session-bootstrap.sh` from the scratchpad `remote_run.sh`
  pattern — the repo provisions the box but has nothing for the on-box
  setup+run.
- Add `nvidia-smi` / driver capture to `/healthz` (Environment table was
  hand-filled this run).
- `benchmarks/methodology.md` is still a stub — Week 2 finalizes it.
- Before publishing the articles: confirm `github.com/ChiragVenkateshaiah/charon`
  is public; re-check the L4 spot price on publish day.
- Decide whether `Articles/` stays tracked or gets gitignored (like `career/`).

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
