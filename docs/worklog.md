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

- **Phase / milestone:** Phase 1. **Milestone 2 (Week 2, load generation and
  the latency/throughput curve) — complete, closed by the owner 2026-10-21.**
  Evidence: `benchmarks/results/2026-10-19-milestone2-sweep.md` (states the
  saturation concurrency and what limits it) and its raw output
  `benchmarks/results/2026-10-19-milestone2-sweep/`; methodology
  `benchmarks/methodology.md` "Concurrency sweep (Milestone 2)". The ADR-0003
  Milestone 2 checkpoint (a committed concurrency curve exists) is met, and
  ADR-0001's 30-day gate is cleared by this unprofiled result.
  **Milestone 1 is still open, so it stays the current milestone** (ADR-0003
  rule 4): methodology rule 4 (the Week 1 TTFT p99 spread, run 2; it recurs at
  concurrency 1 in the sweep) and its written, owner-reviewed explanation
  (ADR-0003 rule 2) are still owed.
- **In progress:** Week 2 LinkedIn article package, `docs/articles/week-2/`
  (untracked, like `docs/articles/week-1/`; not published). The Result 2
  latency table is now an image (`fig-d-latency-table.png`, Visual D),
  because a pasted table did not render well in the LinkedIn editor.
  Untracked means the other machine does not have either package.
- **Next actions:**
  - **Owner: review the Week 2 article package** —
    `docs/articles/week-2/publishing-checklist.md` (now includes uploading
    Visual D at its marker in Result 2).
  - **Owner: decide the decision-4 fix** (throughput window under bursty
    completion delivery) — listed under "Not yet decided" in
    `benchmarks/methodology.md`; to settle before Milestone 3.
  - **Milestone 3 (batching) planning, owner decisions, probably an ADR:**
    continuous-batching stack (vLLM or TGI; check docs for the installed
    version), static-batching design, and the cross-configuration comparison
    methodology ("Not yet decided" in `benchmarks/methodology.md`). Estimate
    GPU-hours once the design is fixed.
  - **Close Milestone 1:** investigate the TTFT p99 spread (local, raw JSON of
    both results), then the written explanation for owner review.
  - GPU session 2 (CPU-sampled Nsight trace, ADR-0003 rule 11) is now allowed;
    `scripts/profile-session.sh` needs the same lifetime / ssh-timeout /
    preemption fixes as `scripts/sweep-session.sh` (`35aa324`, `ef5e6cf`)
    before it runs.
  - Before publishing either article: confirm
    `github.com/ChiragVenkateshaiah/charon` is public; re-check the L4 spot
    price on publish day (carried).
- **Open questions / blockers:**
  - **c = 64 burst delivery** (new): completions reached the client in bursts
    while more than 40 requests were in flight; mechanism not established
    (`benchmarks/results/2026-10-19-milestone2-sweep.md` § 2).
  - **Force-added result files** (new): the sweep's `env/` and `*.log` were
    force-added in `fa6b7c2`, following the profile precedent (`c2a806e`);
    `/end-day` says never force-add. Same open `.gitignore` decision as below,
    now covering `benchmarks/results/` too.
  - **Run-label error** (new): Week 1's slow TTFT tail is run 2 in the raw
    JSON; the analysis, profile card and this file said run 1. Reported, not
    fixed — owner's call.
  - **`.gitignore` vs profile evidence** (new): `env/` and `*.log` are ignored
    generically, so the profile's environment records and logs were
    force-added in `c2a806e`. Decide: keep, or add negation rules for
    `benchmarks/profiles/` so future profiles don't need a force-add.
  - **Python version drift:** now pinned — `scripts/session-bootstrap.sh`
    syncs on Python 3.14.8 (`ef5e6cf`) and each session records it. Week 1's
    Python is still unrecorded.
  - **₹69/h "observed effective rate"** (new, owner-supplied) vs the ~₹41.9/h
    spot list price in `docs/gcp-setup.md` — unreconciled; both kept, neither
    overwritten.
  - `docs/incident-000-cpu-inference.md` gap (carried): the recalled 20–30 min
    CPU reply is still unquantified against a controlled CPU baseline.
  - transformers 5.x / torch 2.13 drift (carried). Keep watching
    `generate()` kwargs.
  - Week 6 7B checkpoint re-download (carried) — decide at Week 6 scoping.
  - **L4 spot capacity** (carried): `us-central1-c` took it first try on
    2026-10-06; `-a`/`-b` stocked out in August. `profile-session.sh` defaults
    to `-c` then `-a`. `asia-south1-a` is still dead.
  - `/healthz` doesn't capture driver / `nvidia-smi` detail (carried). The
    bootstrap now records it per session under the artifact dir, but the
    server itself still doesn't.
  - `Articles/` tracked-or-gitignored is an open owner decision (carried).
  - README "Current status" is stale — it still says the first measured number
    hasn't been produced. Owner edit.
  - **Visualization simulator is hypothetical** (new): the "what could
    change" section of `visualization.html` recombines the measured token
    budget under stated assumptions (batching idealized). None of its
    scenarios has been run; each needs an L4 run before it is a number.
- **GCP:** ready, on **both machines** now. Project `charon-506614`, Compute
  Engine API on, quota approved (`GPUS_ALL_REGIONS`=1, `PREEMPTIBLE_CPUS`
  us-central1=8, L4 spot=1), budget alert live. Second machine (WSL): gcloud
  in `~/google-cloud-sdk`, `CHARON_PROJECT_ID` in `~/.bashrc`, uv in
  `~/.local/bin` (2026-10-06) — `docs/gcp-setup.md`'s "second machine"
  checkbox can be ticked. Full detail in `docs/gcp-setup.md`.
- **Budget:** flexible target ~₹1,000/month ≈ ~24 GPU-hours at current spot list
  price (~₹42/hr all-in, checked 2026-08-28 — `docs/gcp-setup.md`); extendable
  if a measurement needs it. Spent this month (October): **~3.55h**
  (hand-tracked: ~0.53h Nsight profile 2026-10-06; ~3.0h instance time over
  three sweep GPU sessions 2026-10-19, 3.2h approved). August: ~1.1h.
  September: 0.
- **Last session:** 2026-10-22 — Week 2 article: Result 2 table replaced by an
  image (untracked); no GPU. Previous: 2026-10-21 — Milestone 2 closed; Week 2
  article package drafted.

## Sessions

<!-- new entries here -->

### 2026-10-22

**Done — committed**
- None, apart from this worklog entry.

**Done — not yet committed**
- `docs/articles/week-2/`: the Result 2 table in `the-knee-was-at-one.md` is
  replaced by a placeholder for a new image, `fig-d-latency-table.png` (+ SVG),
  drawn by a new `latency_table()` in `make_visuals.py` from the committed
  sweep JSON (same values as the old table). `README.md` (placement, caption,
  alt text, provenance), `publishing-checklist.md` and `claim-verification.md`
  updated to match. Left untracked by owner choice, like `docs/articles/week-1/`.

**Discussed, not started**
- Next steps after Milestone 2 (decision-4 fix, closing Milestone 1, Milestone 3
  planning): set out in chat, nothing started. Already in the Now block.

**Decisions**
- Owner: keep `docs/articles/` untracked at this `/end-day`.

**Numbers committed**
- none

**GPU**
- Used this session: no. Approx GPU-hours: 0 (owner-confirmed).
  Teardown verified by cost-check: yes (no instances, no disks).

**Left for next time**
- Owner review of the Week 2 article package; then the Now block's next actions,
  starting with the decision-4 fix.

### 2026-10-18 to 2026-10-21 — Milestone 2: methodology, driver, sweep, close

**Done — committed**
- ADR-0003: milestones are authoritative; calendar weeks report only
  (`e1c38dd`).
- `benchmarks/methodology.md`: owner decisions 1–8 for the concurrency sweep
  (`f0e69fb`); amended 2026-10-19 with decisions 9–10 and the throughput gate
  (`a64e9cb`); amended again after the sweep with the c = 64 reporting rule and
  the open decision-4 item (`fa6b7c2`).
- `benchmarks/sweep_driver.py`, its fake-server preflight tests
  (`benchmarks/tests/test_sweep_driver_preflight.py`) and the local validation
  `docs/milestone-2-sweep-validation.md` (`3d328b7`, `a64e9cb`). A harness, not
  a result.
- GPU session scripts: `scripts/sweep-session.sh`, `scripts/run-sweep.sh`,
  bootstrap Nsight skip (`c7cc319`); survive preemption, ssh timeouts, true
  instance lifetime (`35aa324`); pin Python 3.14.8 (`ef5e6cf`).
- The sweep result and write-up (`fa6b7c2`). Pushed to `origin/main`.

- Status note in `docs/milestone-2-sweep-validation.md` (`66b9296`).

**Done — not yet committed**
- Week 2 article package `docs/articles/week-2/` (untracked, as Week 1's):
  article, share post, claim verification, publishing checklist, three
  figures and three GIFs generated from the committed sweep JSON by
  `make_visuals.py`.

**Tried, didn't work**
- Sweep GPU session 1 (`us-central1-c`): spot preemption about a minute after
  creation; the scp hung and the script over-reported the lifetime. Fixed in
  `35aa324`.
- Sweep GPU session 2 (`us-central1-c`): bootstrap failed — uv chose CPython
  3.15, no torch 2.13.0 wheel; the poll hid the exit code. Fixed in `ef5e6cf`.
- Session 3 ran in `us-central1-a` (`-c` stocked out).

**Decisions**
- Methodology decisions 1–10 and both amendments, all owner decisions,
  recorded in `benchmarks/methodology.md`.
- c = 64 throughput: report the decision-4 value marked as distorted, with the
  whole-run figure beside it (owner, 2026-10-19). A change to decision 4 itself
  is open.
- Milestone 2 closed by the owner, 2026-10-21 (evidence paths in the Now
  block).

**Numbers committed**
- `benchmarks/results/2026-10-19-milestone2-sweep.md`
- `benchmarks/results/2026-10-19-milestone2-sweep/` (raw driver JSON, logs,
  environment)

**GPU**
- Used this session: yes, three sweep GPU sessions on 2026-10-19. Approx
  GPU-hours: ~3.0 instance-hours (hand-tracked; per-session lifetimes in the
  results file, Methodology notes). Teardown verified by cost-check: yes — no
  instances, no disks (re-checked 2026-10-19 after the push).

**Left for next time**
- See the Now block: article review, decision-4 fix, Milestone 3 planning,
  Milestone 1 close-out, profile-session.sh fixes.

### 2026-10-06 (later) — trace visualization

**Done — committed**
- Interactive page for the 2026-10-06 Nsight trace:
  `benchmarks/nsys_viz_data.py` extracts one real decode step, the per-step
  series, and gap / launch-lag histograms from the trace sqlite and renders
  `benchmarks/profiles/2026-10-06-week1-nsys/visualization.html` from
  `benchmarks/nsys_viz_template.html` (data in `full/viz-data.json`). Replay
  animation, measured evidence charts, and an optimization simulator labelled
  hypothetical throughout. Also published as a private claude.ai artifact.
  (`866c348`)

**Tried, didn't work**
- No browser on this machine, so the page was not visually previewed — only
  a JavaScript syntax check (esprima) and a hand check of the simulator
  arithmetic against the Week 1 baseline. Layout issues, if any, are unseen.
- `quickjs` would not install on Python 3.14 (used esprima instead).

**Decisions**
- Owner reply-style preference recorded globally in `~/.claude/CLAUDE.md`
  (outside the repo; ASD-STE100 + a closing "In a nutshell" section). Not a
  project decision; no ADR.

**Numbers committed**
- `benchmarks/results/`: none. The page re-presents the profiled trace and
  adds hypothetical scenarios; it produces no result.

**GPU**
- Used this session: no. Approx GPU-hours: 0 (no instance since the earlier
  profiling session). Teardown verified by cost-check: yes — no instances, no
  disks.

**Left for next time**
- Unchanged from the earlier entry: run-label fix, TTFT p99 (run 2), Week 1
  self-check, plan-structure decision, next profiling step vs Week 2.
- Look at `visualization.html` in a browser once and report any layout break.

### 2026-10-06 — roofline + Nsight Systems profile (spans 2026-10-05/06)

**Done — committed**
- Simplified roofline for the Week 1 baseline: `benchmarks/roofline.py`, inputs
  `benchmarks/roofline-week1.json` (measured values read from the result JSON
  by key path), checks `benchmarks/test_roofline.py`, report
  `docs/week1-roofline.md` + chart `docs/week1-roofline.svg`. Analysis over
  the committed run, not a result. (`9d230e6`)
- Session scripts: `scripts/session-start.sh` takes `CHARON_IMAGE` to pin an
  exact DLVM image; `scripts/session-bootstrap.sh` (on-box env record + `uv sync
  --locked` + find/install nsys); `scripts/profile-nsys.sh` (smoke then full
  trace of the unchanged server/runner, SIGINT stop, stats export);
  `scripts/profile-session.sh` (laptop-side driver with a teardown trap).
  `.gitignore` excludes trace binaries under `benchmarks/profiles/`. Dry-run
  tested locally with stub nsys/gcloud before any GPU time. (`be2f84c`)
- **Profiling-only GPU session:** Nsight Systems trace of the unchanged Week 1
  server on the pinned Week 1 image, 20 warmup + 30 measured requests.
  Analyzer `benchmarks/nsys_analyze.py`; report, summary, stats, env records
  and logs under `benchmarks/profiles/2026-10-06-week1-nsys/`. Reading: a
  host-bound decode loop around GEMV kernels that may be bandwidth-limited —
  a hypothesis with evidence, not a diagnosis; see the report. (`c2a806e`)
- `decbdf3` (commands update from 2026-10-04) pushed along with the above.
- Pushed: `ab847b2..c2a806e`.

**Done — not yet committed**
- Large trace binaries, local only and gitignored by design:
  `benchmarks/profiles/2026-10-06-week1-nsys/full/trace.nsys-rep`,
  `full/trace.sqlite.gz`, the unpacked `full/trace.sqlite` (regenerable from
  the `.gz`), and `smoke/trace.nsys-rep` / `smoke/trace.sqlite.gz`. They exist
  **only on this machine**.

**Tried, didn't work**
- First profiling attempt stopped at step 1: no nsys, GPU or gcloud on this
  machine (correct stop per the brief).
- nsys CPU IP/backtrace sampling and context-switch tracing: "not supported"
  on the GCE VM, so the trace has no CPU/Python stacks.
- `gcloud auth login` couldn't open a browser from WSL; worked by pasting the
  URL into the Windows browser.
- Auto-editing `~/.bashrc` / installing uv was refused by the permission
  classifier; the owner ran those by hand.
- `profile-nsys.sh` re-exported the trace sqlite for every stats report
  (~10 min of instance time). Fixed in the committed script (export once).

**Discussed, not started**
- Week 1 close-out: TTFT p99 investigation, owner self-check, run-label fix.
- Weeks-vs-milestones plan structure (ADR likely).
- Week 2: methodology, concurrency sweep. No new benchmark result this session
  — the monthly ADR-0001 checkpoint remains overdue.

**Decisions**
- Reproductions pin the exact image (`CHARON_IMAGE`) rather than the family.
  Reversible; no ADR.
- Owner pre-approved installing nsys on the throwaway instance (it turned out
  to be preinstalled); profiling session kept profiling-only; unprofiled
  sanity pass dropped.
- Profiling artifacts live in `benchmarks/profiles/<date>-<name>/`; binaries
  gitignored. Reversible convention; no ADR.
- Owner: commits are asked for after a task, not made mid-task.

**Numbers committed**
- `benchmarks/results/`: none.
- Diagnostic (profiled, not a result):
  `benchmarks/profiles/2026-10-06-week1-nsys/`.

**GPU**
- Used this session: yes — one spot L4 in `us-central1-c`, pinned image
  `common-cu129-ubuntu-2204-nvidia-580-v20260818`. Approx GPU-hours: 0.53
  (instance lifetime from GCE timestamps). Teardown verified by cost-check:
  yes — by the session script and again by hand, and again at end-day.

**Left for next time**
- See Now → Next actions: run-label fix, TTFT p99 (run 2), Week 1 self-check,
  plan-structure decision, next profiling step vs Week 2.

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
