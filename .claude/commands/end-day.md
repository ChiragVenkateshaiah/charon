---
description: Close a Charon session — record what happened and refresh the state /start-day reads.
argument-hint: [optional summary note]
---

You are ending a work session on Charon. Record it honestly and update
`docs/worklog.md` so the next `/start-day` picks up cleanly.

## 1. Reconstruct what actually happened

Ground everything in evidence, not memory or intention:

- `git log --oneline --since=<date of the most recent worklog entry>` (use the
  repo's first commit date if the worklog is new).
- `git status -sb` and `git diff --stat` for uncommitted work.
- Look at what changed under `benchmarks/results/`, `adr/`, `serving/`,
  `optimize/`, `infra/`, `docs/`.

Sort the work into four buckets, and never promote one to another:

- **done and committed**
- **done but uncommitted**
- **tried, didn't work**
- **discussed, not started** — a session spent only reading or designing lands
  here; that is exactly the drift ADR-0001 watches for, so name it plainly.

## 2. Measurement and budget check (per CLAUDE.md)

- Did a benchmark run on real hardware? If so, are the raw results committed
  under `benchmarks/results/`? A load generator, a framework, or a table of
  placeholder numbers is **not** a deliverable — say so if that's all there is.
- The worklog records **paths, not numbers.** Never write a metric value into
  it. `docs/phase-1-plan.md` is full of predictions ("expect ~10–30% GPU util",
  "a large throughput multiple") — those must not turn up in a session entry
  stripped of their "expected" framing.
- Run `bash scripts/cost-check.sh` to see whether the GPU instance is live now.
  If it can't run, say so — don't assume it's down. If it's up, stop and tell
  the user to run `scripts/session-end.sh` then `scripts/cost-check.sh` before
  anything else; an instance left running is the most expensive mistake in this
  project.
- Ask the user for the approximate GPU-hours used this session (hand-tracked).

## 3. Update `docs/worklog.md`

If the file is missing, create it from the template at the bottom of this
command.

Insert a dated entry directly below the `<!-- new entries here -->` line under
**Sessions** (newest first):

```markdown
### YYYY-MM-DD

**Done — committed**
- <grounded in commits / diff>

**Done — not yet committed**
- <or omit this heading>

**Tried, didn't work**
- <or omit>

**Discussed, not started**
- <or omit>

**Decisions**
- <any; link the ADR. If a hard-to-reverse decision was made and no ADR exists,
  write "ADR owed — <topic>" here so it survives past the terminal.>

**Numbers committed**
- <paths added under benchmarks/results/, or "none">

**GPU**
- Used this session: yes/no. Approx GPU-hours: <n> (hand-tracked).
  Teardown verified by cost-check: yes/no/not-checked.

**Left for next time**
- <feeds the Now block>
```

Then rewrite the **Now** block:

- **Phase / week** — advance only if the current week's exit condition in
  `docs/phase-1-plan.md` is genuinely met; otherwise leave it and note what's
  left.
- **In progress** — what's half-done, including uncommitted work.
- **Next actions** — concrete, ordered; the top one should be startable in about
  five minutes.
- **Open questions / blockers** — carry unresolved ones forward, add new ones.
- **Budget** — previous GPU-hours + this session's.
- **Last session** — today's date and a one-line summary.

Fold in the user's note ($ARGUMENTS) if given.

## 4. Loose ends

- If the README's "Current status" is now out of step with the Now block, point
  it out — but don't edit the README; that's the owner's call.
- Note (don't fix) any other uncommitted work that belongs to the user, so they
  can decide whether to commit it before switching machines.

## 5. Commit the worklog

Commit `docs/worklog.md` on its own — never bundled with other changes — with a
message like `worklog: session YYYY-MM-DD`. This file is the state the other
machine reads; left uncommitted the whole start-day/end-day loop breaks. Report
the commit SHA. Don't push, and don't touch any other file unless asked.

Then show the updated Now block and the new entry.

---

## Worklog template (used only when `docs/worklog.md` is missing)

```markdown
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

- **Phase / week:** <from docs/phase-1-plan.md and git history>
- **In progress:** nothing
- **Next actions:**
  - <concrete, ordered>
- **Open questions / blockers:**
  - <none, or list>
- **Budget:** ₹1,000/month, ~36–40 GPU-hours (working estimate). Spent this
  month: 0h (hand-tracked).
- **Last session:** —

## Sessions

<!-- new entries here -->
```
