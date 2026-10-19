#!/usr/bin/env bash
#
# sweep-session.sh — GPU session 1 of ADR-0003 rule 11: the Milestone 2
# concurrency sweep, unprofiled. Runs LOCALLY; drives the instance end to end:
#
#   session-start.sh (pinned Week 1 image) -> copy repo -> session-bootstrap.sh
#   (Nsight skipped) -> run-sweep.sh -> fetch -> session-end.sh -> cost-check.sh
#
#   bash scripts/sweep-session.sh
#
# Same safety pattern as profile-session.sh: teardown is a trap, so once the
# instance exists it is deleted on success, failure, Ctrl-C, and when the
# deadline passes; the on-box job runs detached and is polled.
#
# Budget: the owner approved 3.2 GPU-hours (2026-10-19). CHARON_MAX_INSTANCE_MINUTES
# (default 192 = 3.2 h) caps the whole instance lifetime, measured from just
# before creation. The on-box job is killed FETCH_MARGIN_MIN before that cap so
# fetch and delete fit inside it. [M5] re-runs only start if one can still finish
# (RERUN_WORST_MIN) before the job deadline. The driver rewrites its results
# file after every run, and that file is copied to this machine every
# PARTIAL_EVERY_MIN, so a preemption loses at most the runs since the last copy.
#
# Artifacts land in benchmarks/results/<UTC date>-milestone2-sweep/. Nothing is
# committed.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT}"
command -v gcloud >/dev/null 2>&1 || export PATH="${HOME}/google-cloud-sdk/bin:${PATH}"
PROJECT_ID="${CHARON_PROJECT_ID:?Set CHARON_PROJECT_ID to your GCP project id}"
INSTANCE_NAME="${CHARON_INSTANCE_NAME:-charon-gpu}"
export CHARON_IMAGE="${CHARON_IMAGE:-common-cu129-ubuntu-2204-nvidia-580-v20260818}"  # Week 1 image
export CHARON_PRIMARY_ZONE="${CHARON_PRIMARY_ZONE:-us-central1-c}"   # where Week 1 got capacity
export CHARON_FALLBACK_ZONE="${CHARON_FALLBACK_ZONE:-us-central1-a}"
MAX_INSTANCE_MIN="${CHARON_MAX_INSTANCE_MINUTES:-192}"
FETCH_MARGIN_MIN=6     # fetch + delete, after the job deadline
RERUN_WORST_MIN=12     # one c=64 run (~10 min, ESTIMATE) + margin
LOCAL_OUT="${ROOT}/benchmarks/results/$(date -u +%Y-%m-%d)-milestone2-sweep"
log() { echo "[session $(date -u +%H:%M:%S)] $*"; }

if [[ -n "$(git status --porcelain -- serving benchmarks/sweep_driver.py benchmarks/baseline_runner.py benchmarks/methodology.md scripts)" ]]; then
  echo "ERROR: serving/, the driver, the methodology or scripts/ have uncommitted changes." >&2
  echo "The sweep must run a committed revision. Commit first." >&2
  exit 1
fi
if [[ -n "$(gcloud compute instances list --project="${PROJECT_ID}" \
      --filter="name=${INSTANCE_NAME}" --format='value(name)')" ]]; then
  echo "ERROR: '${INSTANCE_NAME}' already exists — another session may be live." >&2
  echo "Not touching it. Resolve with scripts/cost-check.sh / session-end.sh first." >&2
  exit 1
fi

SESSION_T0=$(date +%s)
HARD_END=$(( SESSION_T0 + MAX_INSTANCE_MIN * 60 ))
JOB_DEADLINE=$(( HARD_END - FETCH_MARGIN_MIN * 60 ))
RERUN_CUTOFF=$(( JOB_DEADLINE - RERUN_WORST_MIN * 60 ))

ZONE=""; CREATED_AT=""; FETCHED=0
# Timeouts so a dead (e.g. preempted) host fails in ~1 min, not ~17 (2026-10-19).
SSH_OPTS=(-oConnectTimeout=20 -oServerAliveInterval=15 -oServerAliveCountMax=4)
ssh_box() {
  gcloud compute ssh "${INSTANCE_NAME}" --project="${PROJECT_ID}" --zone="${ZONE}" --quiet \
    "${SSH_OPTS[@]/#/--ssh-flag=}" --command "$1"
}
scp_box() {
  gcloud compute scp "${SSH_OPTS[@]/#/--scp-flag=}" --project="${PROJECT_ID}" --zone="${ZONE}" --quiet "$@"
}
instance_exists() {
  [[ -n "$(gcloud compute instances list --project="${PROJECT_ID}" \
        --filter="name=${INSTANCE_NAME}" --format='value(name)' 2>/dev/null)" ]]
}

fetch() {
  [[ -n "${ZONE}" && "${FETCHED}" == 0 ]] || return 0
  instance_exists || { log "instance no longer exists (preempted?) — nothing to fetch"; return 1; }
  log "fetching artifacts -> ${LOCAL_OUT#"${ROOT}"/}"
  mkdir -p "${LOCAL_OUT}"
  ssh_box 'tar czf ~/sweep.tgz -C ~ sweep' || true
  scp_box "${INSTANCE_NAME}:~/sweep.tgz" "${LOCAL_OUT}/sweep.tgz" || { rmdir "${LOCAL_OUT}" 2>/dev/null; return 1; }
  tar xzf "${LOCAL_OUT}/sweep.tgz" -C "${LOCAL_OUT}" --strip-components=1 && rm "${LOCAL_OUT}/sweep.tgz"
  FETCHED=1
}

# A preemption deletes the boot disk and the driver's results file with it, so
# completed runs are copied off the box every PARTIAL_EVERY_MIN while the job runs.
PARTIAL_EVERY_MIN="${CHARON_PARTIAL_EVERY_MIN:-10}"
fetch_partial() {
  instance_exists || return 1
  mkdir -p "${LOCAL_OUT}"
  # exit 1 = "file changed as we read it" (the driver may be mid-write): still usable
  ssh_box 'tar czf ~/sweep-partial.tgz --exclude="*.tmp" -C ~ sweep; [ $? -le 1 ]' >/dev/null 2>&1 || return 1
  scp_box "${INSTANCE_NAME}:~/sweep-partial.tgz" "${LOCAL_OUT}/partial.tgz.tmp" >/dev/null 2>&1 || return 1
  mv "${LOCAL_OUT}/partial.tgz.tmp" "${LOCAL_OUT}/partial.tgz"
  log "partial results copied ($(du -h "${LOCAL_OUT}/partial.tgz" | cut -f1))"
}

teardown() {
  local rc=$?
  trap - EXIT INT TERM
  if [[ -n "${ZONE}" ]]; then
    if fetch; then
      rm -f "${LOCAL_OUT}/partial.tgz" "${LOCAL_OUT}/partial.tgz.tmp"
    else
      log "WARNING: artifact fetch failed — deleting the instance anyway"
      rm -f "${LOCAL_OUT}/partial.tgz.tmp"
      if [[ -f "${LOCAL_OUT}/partial.tgz" ]]; then
        mkdir -p "${LOCAL_OUT}/partial" && tar xzf "${LOCAL_OUT}/partial.tgz" -C "${LOCAL_OUT}/partial" --strip-components=1 \
          && rm "${LOCAL_OUT}/partial.tgz" && log "kept the last partial copy in ${LOCAL_OUT#"${ROOT}"/}/partial"
      fi
    fi
  fi
  log "teardown"
  bash scripts/session-end.sh || log "ERROR: session-end failed — check the console NOW"
  bash scripts/cost-check.sh || true
  if [[ -n "${CREATED_AT}" ]]; then
    # End of life = GCP's first preempt/delete operation after creation, so time
    # spent waiting on a dead host is not counted (2026-10-19). Falls back to now.
    local ended
    ended="$(gcloud compute operations list --project="${PROJECT_ID}" \
      --filter="targetLink~instances/${INSTANCE_NAME}\$ AND (operationType=compute.instances.preempted OR operationType=delete) AND insertTime>=${CREATED_AT}" \
      --sort-by=insertTime --format='value(insertTime,operationType)' 2>/dev/null | head -n1 || true)"
    python3 - "${CREATED_AT}" "${ended}" <<'EOF'
import sys, datetime as dt
utc = dt.timezone.utc
t0 = dt.datetime.fromisoformat(sys.argv[1]).astimezone(utc)
end = sys.argv[2].split()
t1 = dt.datetime.fromisoformat(end[0]).astimezone(utc) if end else dt.datetime.now(utc)
how = end[1] if end else "no delete/preempt operation found; measured to now"
h = (t1 - t0).total_seconds() / 3600
print(f"\ninstance lifetime: {h:.2f} h ({t0:%H:%M:%S} -> {t1:%H:%M:%S} UTC; end = {how})")
print(f"ESTIMATED, NOT MEASURED cost: ~₹{h*69:.0f} at ₹69/h (observed effective rate); "
      f"~₹{h*41.9:.0f} at ₹41.9/h (spot list price, docs/gcp-setup.md)")
EOF
  fi
  exit "${rc}"
}
trap teardown EXIT
trap 'exit 130' INT TERM

# ---- create ------------------------------------------------------------------
bash scripts/session-start.sh
ZONE="$(gcloud compute instances list --project="${PROJECT_ID}" \
  --filter="name=${INSTANCE_NAME}" --format='value(zone.basename())' | head -n1)"
CREATED_AT="$(gcloud compute instances describe "${INSTANCE_NAME}" --project="${PROJECT_ID}" \
  --zone="${ZONE}" --format='value(creationTimestamp)')"
log "instance up in ${ZONE} (created ${CREATED_AT}); hard end $(date -u -d "@${HARD_END}" +%H:%M:%S) UTC"

for i in $(seq 1 30); do
  ssh_box true >/dev/null 2>&1 && break
  instance_exists || { echo "ERROR: instance gone before SSH (preempted?)" >&2; exit 1; }
  [[ "${i}" == 30 ]] && { echo "ERROR: SSH not reachable after ~5 min" >&2; exit 1; }
  sleep 10
done

# ---- copy repo (tracked + untracked-not-ignored; no articles/results) ---------
REV="$(git rev-parse HEAD)$(git diff --quiet HEAD -- . 2>/dev/null || echo -dirty)"
TARBALL="$(mktemp --suffix=.tgz)"
git ls-files -co --exclude-standard -z \
  | grep -zv -e '^Articles/' -e '^docs/articles/' -e '^benchmarks/results/' -e '^benchmarks/profiles/' \
  | tar --null -czf "${TARBALL}" -T -
scp_box "${TARBALL}" "${INSTANCE_NAME}:~/charon.tgz" || { rm -f "${TARBALL}"; echo "ERROR: repo copy failed" >&2; exit 1; }
rm -f "${TARBALL}"
ssh_box "rm -rf ~/charon ~/sweep && mkdir -p ~/charon ~/sweep && tar xzf ~/charon.tgz -C ~/charon && echo '${REV}' > ~/charon/.charon_git_rev && cp ~/charon/.charon_git_rev ~/sweep/git-rev.txt"

# ---- detached on-box job -----------------------------------------------------
JOB="cd ~/charon && CHARON_SKIP_NSYS=1 bash scripts/session-bootstrap.sh ~/sweep/env && bash scripts/run-sweep.sh ~/sweep ${RERUN_CUTOFF}"
ssh_box "setsid nohup bash -c '${JOB}; echo \$? > ~/sweep/EXIT' > ~/sweep/job.log 2>&1 < /dev/null &"
log "on-box job started; job deadline $(date -u -d "@${JOB_DEADLINE}" +%H:%M:%S) UTC, re-runs only before $(date -u -d "@${RERUN_CUTOFF}" +%H:%M:%S) UTC; polling"

STATUS=""; NEXT_PARTIAL=$(( $(date +%s) + PARTIAL_EVERY_MIN * 60 ))
while (( $(date +%s) < JOB_DEADLINE )); do
  sleep 60
  if (( $(date +%s) >= NEXT_PARTIAL )); then
    fetch_partial || log "WARNING: partial copy failed"
    NEXT_PARTIAL=$(( $(date +%s) + PARTIAL_EVERY_MIN * 60 ))
  fi
  if ! OUTP="$(ssh_box 'cat ~/sweep/EXIT 2>/dev/null; echo ---; tail -n 1 ~/sweep/job.log; tail -n 1 ~/sweep/driver.log 2>/dev/null' 2>/dev/null)"; then
    instance_exists || { log "ERROR: instance gone during the job (preempted?) — keeping the last partial copy"; exit 1; }
    echo "  (poll failed; instance still exists — retrying)"; continue
  fi
  STATUS="$(sed -n '1{/^---$/d;p}' <<<"${OUTP}")"
  echo "  $(sed '1,/^---$/d' <<<"${OUTP}" | tail -n 1)"
  [[ -n "${STATUS}" ]] && break
done

if [[ -z "${STATUS}" ]]; then log "ERROR: job deadline reached — fetching completed runs and tearing down"; exit 1; fi
if [[ "${STATUS}" != 0 ]]; then log "ERROR: on-box job failed (exit ${STATUS}) — see job.log and driver.log in artifacts"; exit 1; fi
log "on-box job finished OK"
fetch
