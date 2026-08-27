---
description: Brief on where Charon stands at the start of a session. Does not start work.
argument-hint: [optional note about today's focus]
allowed-tools: Read, Grep, Glob, Bash(git fetch:*), Bash(git status:*), Bash(git log:*), Bash(git branch:*), Bash(git rev-list:*), Bash(git diff:*), Bash(ls:*), Bash(bash scripts/cost-check.sh:*)
---

You are starting a work session on Charon. Produce a short briefing and stop.
Do **not** write code, edit files, or launch anything — this command only
orients. It cannot create or change the worklog; that is `/end-day`'s job.

Keep the whole briefing under ~20 lines. Omit a heading rather than writing
"none" under it.

## 1. Repo and sync state

- `git fetch origin`, then `git status -sb` and `git log --oneline -10`.
- If the tree is dirty, report it first — uncommitted work doesn't travel
  between machines, and this repo is worked from two.
- If the branch has diverged from `origin/<branch>` after the fetch, say so and
  tell the user to reconcile before starting.

## 2. Read the worklog

Read `docs/worklog.md`. Read only the **Now** block and the most recent 2–3
entries under **Sessions**; don't summarize older history. If the file is
missing, say so — the first `/end-day` creates it — and brief from git history
and `docs/phase-1-plan.md` instead.

## 3. Cross-check Now against reality

The Now block is a hand-maintained cache and can be wrong. Verify, and in the
briefing report reality where they disagree:

- **Phase / week:** does it match `docs/phase-1-plan.md` and what the commits
  show was actually done?
- **Next actions:** omit any already done in git history; note they look
  complete.
- **Numbers:** run `ls benchmarks/results/` and
  `git log -1 --format=%cd -- benchmarks/results/`. That date is the last time a
  measured number landed. Per `adr/0001-measurement-discipline.md` nothing else
  counts as a result — not harness code, not a table of placeholders. If the
  worklog implies a number that isn't committed there, report the discrepancy.
- **Drift:** check the cadence rules at the end of `docs/phase-1-plan.md` and
  ADR-0001's "a number every month" against that date. If a checkpoint is
  overdue, lead the briefing with it.

## 4. Budget and GPU state

- Run `bash scripts/cost-check.sh`. If it can't run (`CHARON_PROJECT_ID` unset,
  gcloud not authenticated), say the check did not run — a failed check is not
  evidence that nothing is live. If anything is running, lead the briefing with
  it, before everything else.
- Report GPU-hours spent this month from the worklog's Budget line
  (hand-tracked, approximate). The hard constraint is ₹1,000/month; ~36–40
  GPU-hours is the working estimate of what that buys, not a measured figure.
- If today's work needs a GPU run, estimate its GPU-hours and check the headroom
  before anything launches. Don't propose launching the instance for work that
  doesn't need it — development, debugging, analysis and writing happen locally
  on CPU. The instance is created and deleted per session via
  `scripts/session-start.sh` / `scripts/session-end.sh`, never left stopped.

## 5. Briefing

Print, concisely:

- **Where we are** — phase / week, one line.
- **Done recently** — from the last session(s), grounded in commits; if the
  worklog claims something the commits don't show, report the discrepancy.
- **Today's focus** — the worklog's Next actions, adjusted for what's already
  done and for the user's note ($ARGUMENTS) if given.
- **Watch out for** — overdue drift checkpoint, dirty tree, live GPU instance,
  README "Current status" out of step with Now.
- **Open questions / blockers** — carried from the worklog.

End by proposing the next action, drawn from `docs/phase-1-plan.md` and the
worklog's Next actions — don't invent one. If those two disagree, say so and ask
which. Phrase it as a question and wait; do not start it.
