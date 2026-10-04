---
description: Close a Charon session — commit all work, record it in the worklog, and push to GitHub.
argument-hint: [optional summary note]
allowed-tools: Read, Grep, Glob, Edit, Write, Bash(git fetch:*), Bash(git status:*), Bash(git log:*), Bash(git branch:*), Bash(git rev-list:*), Bash(git rev-parse:*), Bash(git diff:*), Bash(git show:*), Bash(git add:*), Bash(git commit:*), Bash(git pull --rebase:*), Bash(git rebase --abort:*), Bash(git push:*), Bash(git check-ignore:*), Bash(ls:*), Bash(du:*), Bash(bash scripts/cost-check.sh:*)
---

You are ending a work session on Charon. Record it honestly, commit everything
the session produced, update `docs/worklog.md` so the next `/start-day` picks up
cleanly, and push it all to `origin` so the other machine has it.

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

## 3. Commit the session's work

Everything done today should be committed before the worklog is written, so the
worklog can cite commits rather than "uncommitted" work.

- List everything outstanding: `git status --porcelain` (staged, unstaged and
  untracked).
- **Never stage** — leave out and report instead:
  - secrets or credentials: `.env*`, keys, `*.pem`, service-account JSON, or any
    diff line that looks like a token/password (check `git diff` before
    staging);
  - model weights, caches or any single file over ~50 MB (`du -h`);
  - anything already covered by `.gitignore` (confirm with `git check-ignore`
    if unsure) — never force-add.
- Stage by explicit path, never `git add -A` / `git add .`, and group into
  logical commits by area using the repo's existing prefix style
  (`benchmarks:`, `serving:`, `docs:`, `adr:`, `scripts:`, `articles:` …). Read
  `git log --oneline -15` to match it. Each message says what changed and why,
  in the same honest register as the worklog — a harness is a harness, not a
  result.
- Raw benchmark output under `benchmarks/results/` is committed as-is
  (methodology rule 7): no editing, trimming or reformatting before commit.
- `README.md` and ADRs are owner-edited: commit the owner's own changes to them
  if present, but don't make new edits to them as part of this command.
- If a change is clearly half-done and committing it would leave `main` broken
  (a script that no longer runs, a syntax error), say so and ask whether to
  commit it as WIP or leave it out — don't decide silently.

## 4. Update `docs/worklog.md`

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

## 5. Loose ends

- If the README's "Current status" is now out of step with the Now block, point
  it out — but don't edit the README; that's the owner's call.
- Anything deliberately left out of step 3 (secrets, large files, WIP the user
  chose not to commit) goes under **Done — not yet committed** in the entry and
  in the final report, so it isn't forgotten when switching machines.

## 6. Commit the worklog and push

1. Commit `docs/worklog.md` on its own — never bundled with other changes — with
   a message like `worklog: session YYYY-MM-DD`.
2. `git fetch origin`. If the branch is behind `origin/<branch>` (the other
   machine pushed), run `git pull --rebase origin <branch>`. On any conflict,
   run `git rebase --abort`, stop, and report the conflicting files — don't
   resolve conflicts on your own.
3. `git push origin <branch>` (add `-u` if the branch has no upstream). **Never
   force-push.** If the push is rejected, stop and report the error verbatim.
4. Confirm with `git status -sb` that the branch is level with
   `origin/<branch>`.

Report: the SHAs and one-line messages of every commit made this session, the
push result, and anything left uncommitted. Then show the updated Now block and
the new entry.

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
- **Budget:** flexible target ~₹1,000/month ≈ ~24 GPU-hours at GCP spot list
  price (`docs/gcp-setup.md`); extendable if a measurement needs it. Spent this
  month: <n>h (hand-tracked).
- **Last session:** —

## Sessions

<!-- new entries here -->
```
