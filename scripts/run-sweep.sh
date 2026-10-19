#!/usr/bin/env bash
#
# run-sweep.sh — the Milestone 2 concurrency sweep against the UNCHANGED Week 1
# naive server. Runs ON the GPU instance, from the repo root, after
# session-bootstrap.sh. Started detached by scripts/sweep-session.sh.
#
#   bash scripts/run-sweep.sh <out-dir> <rerun-cutoff-epoch>
#
# Unprofiled (ADR-0003 rule 11): no Nsight or other profiler is attached. The
# server is started exactly as in Week 1 (serving/README.md); the driver runs
# with its defaults, which are benchmarks/methodology.md "Concurrency sweep
# (Milestone 2)". The only argument added is the [M5] re-run time box, derived
# from <rerun-cutoff-epoch> so a re-run cannot start too late to finish inside
# the session's approved GPU time.

set -euo pipefail

OUT="${1:?usage: run-sweep.sh <out-dir> <rerun-cutoff-epoch>}"
RERUN_CUTOFF="${2:?usage: run-sweep.sh <out-dir> <rerun-cutoff-epoch>}"
PORT=8000
mkdir -p "${OUT}"
log() { echo "[sweep $(date -u +%H:%M:%S)] $*"; }

SERVER_CMD=(.venv/bin/python -m uvicorn serving.naive_server:app --port "${PORT}")
log "starting: ${SERVER_CMD[*]}"
"${SERVER_CMD[@]}" > "${OUT}/server.log" 2>&1 &
SERVER_PID=$!
stop_server() { kill -INT "${SERVER_PID}" 2>/dev/null || true; wait "${SERVER_PID}" 2>/dev/null || true; }
trap stop_server EXIT

log "waiting for /healthz (model load)"
for i in $(seq 1 180); do
  curl -sf "http://localhost:${PORT}/healthz" > "${OUT}/healthz.json" 2>/dev/null && break
  kill -0 "${SERVER_PID}" 2>/dev/null || { echo "ERROR: server exited; see ${OUT}/server.log" >&2; exit 1; }
  [[ "${i}" == 180 ]] && { echo "ERROR: server not ready after 15 min" >&2; exit 1; }
  sleep 5
done

TIME_BOX_MIN=$(( (RERUN_CUTOFF - $(date +%s)) / 60 ))
(( TIME_BOX_MIN < 1 )) && TIME_BOX_MIN=1
TS="$(date -u +%Y%m%dT%H%M%SZ)"
DRIVER_CMD=(.venv/bin/python benchmarks/sweep_driver.py
            --time-box-min "${TIME_BOX_MIN}" --out "${OUT}/sweep-${TS}.json")
log "running: ${DRIVER_CMD[*]}"
set +e
"${DRIVER_CMD[@]}" > "${OUT}/driver.stdout" 2> "${OUT}/driver.log"
RC=$?
set -e
log "driver exit ${RC}"
cat "${OUT}/driver.stdout"
exit "${RC}"
