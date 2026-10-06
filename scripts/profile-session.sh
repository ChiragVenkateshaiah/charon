#!/usr/bin/env bash
#
# profile-session.sh — one scoped GPU session: Nsight Systems trace of the
# unchanged Week 1 baseline. Runs LOCALLY; drives the instance end to end:
#
#   session-start.sh (pinned Week 1 image) -> copy repo -> session-bootstrap.sh
#   -> profile-nsys.sh smoke -> profile-nsys.sh full -> fetch artifacts
#   -> session-end.sh -> cost-check.sh
#
#   bash scripts/profile-session.sh
#
# Teardown is a trap: once the instance exists it is deleted on success, on
# failure, on Ctrl-C, and when the deadline passes. The full trace runs only if
# the smoke trace succeeded. The on-box job runs detached and is polled, so a
# dropped SSH connection cannot kill it (the Week 1 session lost a run that way).
#
# Artifacts land in benchmarks/profiles/<UTC date>-week1-nsys/. Large binaries
# (*.nsys-rep, *.sqlite.gz) are gitignored; summaries, logs and metadata are not.
# Nothing is committed.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT}"
command -v gcloud >/dev/null 2>&1 || export PATH="${HOME}/google-cloud-sdk/bin:${PATH}"
PROJECT_ID="${CHARON_PROJECT_ID:?Set CHARON_PROJECT_ID to your GCP project id}"
INSTANCE_NAME="${CHARON_INSTANCE_NAME:-charon-gpu}"
export CHARON_IMAGE="${CHARON_IMAGE:-common-cu129-ubuntu-2204-nvidia-580-v20260818}"  # Week 1 image
export CHARON_PRIMARY_ZONE="${CHARON_PRIMARY_ZONE:-us-central1-c}"   # where Week 1 got capacity
export CHARON_FALLBACK_ZONE="${CHARON_FALLBACK_ZONE:-us-central1-a}"
MAX_MINUTES="${CHARON_MAX_MINUTES:-75}"   # hard deadline for the on-box job
LOCAL_OUT="${ROOT}/benchmarks/profiles/$(date -u +%Y-%m-%d)-week1-nsys"
log() { echo "[session $(date -u +%H:%M:%S)] $*"; }

if [[ -n "$(gcloud compute instances list --project="${PROJECT_ID}" \
      --filter="name=${INSTANCE_NAME}" --format='value(name)')" ]]; then
  echo "ERROR: '${INSTANCE_NAME}' already exists — another session may be live." >&2
  echo "Not touching it. Resolve with scripts/cost-check.sh / session-end.sh first." >&2
  exit 1
fi

ZONE=""; CREATED_AT=""; FETCHED=0
ssh_box() { gcloud compute ssh "${INSTANCE_NAME}" --project="${PROJECT_ID}" --zone="${ZONE}" --quiet --command "$1"; }

fetch() {
  [[ -n "${ZONE}" && "${FETCHED}" == 0 ]] || return 0
  log "fetching artifacts -> ${LOCAL_OUT#"${ROOT}"/}"
  mkdir -p "${LOCAL_OUT}"
  ssh_box 'tar czf ~/prof.tgz -C ~ prof' || true
  gcloud compute scp "${INSTANCE_NAME}:~/prof.tgz" "${LOCAL_OUT}/prof.tgz" \
    --project="${PROJECT_ID}" --zone="${ZONE}" --quiet || return 1
  tar xzf "${LOCAL_OUT}/prof.tgz" -C "${LOCAL_OUT}" --strip-components=1 && rm "${LOCAL_OUT}/prof.tgz"
  FETCHED=1
}

teardown() {
  local rc=$?
  trap - EXIT INT TERM
  if [[ -n "${ZONE}" ]]; then
    fetch || log "WARNING: artifact fetch failed — deleting the instance anyway"
  fi
  log "teardown"
  bash scripts/session-end.sh || log "ERROR: session-end failed — check the console NOW"
  bash scripts/cost-check.sh || true
  if [[ -n "${CREATED_AT}" ]]; then
    python3 - "${CREATED_AT}" <<'EOF'
import sys, datetime as dt
t0 = dt.datetime.fromisoformat(sys.argv[1]); t1 = dt.datetime.now(dt.timezone.utc)
h = (t1 - t0).total_seconds() / 3600
print(f"\ninstance lifetime: {h:.2f} h ({t0:%H:%M:%S} -> {t1:%H:%M:%S} UTC)")
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
log "instance up in ${ZONE} (created ${CREATED_AT})"

for i in $(seq 1 30); do
  ssh_box true >/dev/null 2>&1 && break
  [[ "${i}" == 30 ]] && { echo "ERROR: SSH not reachable after ~5 min" >&2; exit 1; }
  sleep 10
done

# ---- copy repo (tracked + untracked-not-ignored; no articles/results) ---------
REV="$(git rev-parse HEAD)$(git diff --quiet HEAD -- . 2>/dev/null || echo -dirty)"
TARBALL="$(mktemp --suffix=.tgz)"
git ls-files -co --exclude-standard -z \
  | grep -zv -e '^Articles/' -e '^benchmarks/results/' -e '^benchmarks/profiles/' \
  | tar --null -czf "${TARBALL}" -T -
gcloud compute scp "${TARBALL}" "${INSTANCE_NAME}:~/charon.tgz" --project="${PROJECT_ID}" --zone="${ZONE}" --quiet
rm -f "${TARBALL}"
ssh_box "rm -rf ~/charon ~/prof && mkdir -p ~/charon ~/prof && tar xzf ~/charon.tgz -C ~/charon && echo '${REV}' > ~/charon/.charon_git_rev"

# ---- detached on-box job -----------------------------------------------------
JOB='cd ~/charon && bash scripts/session-bootstrap.sh ~/prof/env && bash scripts/profile-nsys.sh ~/prof/smoke smoke && bash scripts/profile-nsys.sh ~/prof/full full'
ssh_box "setsid nohup bash -c '${JOB}; echo \$? > ~/prof/EXIT' > ~/prof/job.log 2>&1 < /dev/null &"
log "on-box job started (deadline ${MAX_MINUTES} min); polling"

DEADLINE=$(( $(date +%s) + MAX_MINUTES * 60 ))
STATUS=""
while (( $(date +%s) < DEADLINE )); do
  sleep 30
  OUTP="$(ssh_box 'cat ~/prof/EXIT 2>/dev/null; echo ---; tail -n 2 ~/prof/job.log' 2>/dev/null || true)"
  STATUS="$(sed -n '1{/^---$/d;p}' <<<"${OUTP}")"
  echo "  $(tail -n 1 <<<"${OUTP}")"
  [[ -n "${STATUS}" ]] && break
done

if [[ -z "${STATUS}" ]]; then log "ERROR: deadline reached — tearing down"; exit 1; fi
if [[ "${STATUS}" != 0 ]]; then log "ERROR: on-box job failed (exit ${STATUS}) — see job.log in artifacts"; exit 1; fi
log "on-box job finished OK"
fetch
