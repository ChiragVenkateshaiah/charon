#!/usr/bin/env bash
#
# profile-nsys.sh — Nsight Systems trace of the UNCHANGED Week 1 naive server.
# Runs ON the GPU instance, from the repo root, after session-bootstrap.sh.
#
#   bash scripts/profile-nsys.sh <out-dir> smoke   # 1 warmup + 2 requests: validates the command
#   bash scripts/profile-nsys.sh <out-dir> full    # 20 warmup + 30 requests, 1 run
#
# Profiling only. The server and runner are invoked exactly as in Week 1
# (serving/naive_server.py, benchmarks/baseline_runner.py, default prompts and
# 128 forced output tokens); the only differences are the request count and that
# the runner's output goes to <out-dir>, never benchmarks/results/ — a profiled
# run is perturbed by the profiler and is not a benchmark result (ADR-0001).
#
# Trace stop: the server runs until killed, so after the runner finishes this
# script sends SIGINT to the server; nsys finalizes the report when it exits.

set -euo pipefail

OUT="${1:?usage: profile-nsys.sh <out-dir> smoke|full}"
MODE="${2:?usage: profile-nsys.sh <out-dir> smoke|full}"
case "${MODE}" in
  smoke) WARMUP=1;  REQUESTS=2  ;;
  full)  WARMUP=20; REQUESTS=30 ;;
  *) echo "mode must be smoke or full" >&2; exit 2 ;;
esac
OUTPUT_TOKENS=128   # Week 1 value, also the runner default — stated, not changed
PORT=8000
NSYS="$(cat "${HOME}/.charon_nsys")"
mkdir -p "${OUT}"
log() { echo "[profile:${MODE} $(date -u +%H:%M:%S)] $*"; }

# ---- options: only ones this nsys version advertises -------------------------
HELP="$("${NSYS}" profile --help 2>&1)"
has() { grep -q -- "$1" <<<"${HELP}"; }
OPTS=(--trace=cuda,nvtx,osrt --force-overwrite=true --output="${OUT}/trace")
has '--sample='           && OPTS+=(--sample=process-tree)
has '--cpuctxsw='         && OPTS+=(--cpuctxsw=process-tree)
has '--python-sampling='  && OPTS+=(--python-sampling=true)
has '--cuda-memory-usage' && OPTS+=(--cuda-memory-usage=false)

SERVER_CMD=(.venv/bin/python -m uvicorn serving.naive_server:app --port "${PORT}")
RUNNER_CMD=(.venv/bin/python benchmarks/baseline_runner.py
            --warmup "${WARMUP}" --requests "${REQUESTS}" --runs 1
            --output-tokens "${OUTPUT_TOKENS}" --out "${OUT}/runner.json")
PROFILE_CMD=("${NSYS}" profile "${OPTS[@]}" "${SERVER_CMD[@]}")

# ---- run ---------------------------------------------------------------------
T_START="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
log "starting: ${PROFILE_CMD[*]}"
"${PROFILE_CMD[@]}" > "${OUT}/server.log" 2>&1 &
NSYS_PID=$!

log "waiting for /healthz (model load)"
for i in $(seq 1 180); do
  curl -sf "http://localhost:${PORT}/healthz" >/dev/null 2>&1 && break
  kill -0 "${NSYS_PID}" 2>/dev/null || { echo "ERROR: server exited; see ${OUT}/server.log" >&2; exit 1; }
  [[ "${i}" == 180 ]] && { echo "ERROR: server not ready after 15 min" >&2; exit 1; }
  sleep 5
done

T_REQ_START="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
log "running: ${RUNNER_CMD[*]}"
"${RUNNER_CMD[@]}" > "${OUT}/runner.log" 2>&1
T_REQ_END="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

log "stopping server (SIGINT) so nsys finalizes"
# signal the server process only — not nsys or its launcher, whose cmdlines
# carry the same arguments
for pid in $(pgrep -f "uvicorn serving\.naive_server:app" || true); do
  [[ "${pid}" == "${NSYS_PID}" ]] && continue
  tr '\0' ' ' < "/proc/${pid}/cmdline" 2>/dev/null | grep -q nsys && continue
  kill -INT "${pid}" 2>/dev/null || true
done
for _ in $(seq 1 240); do kill -0 "${NSYS_PID}" 2>/dev/null || break; sleep 5; done
if kill -0 "${NSYS_PID}" 2>/dev/null; then echo "ERROR: nsys still running after 20 min" >&2; exit 1; fi
wait "${NSYS_PID}" || true
T_END="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
[[ -s "${OUT}/trace.nsys-rep" ]] || { echo "ERROR: no trace.nsys-rep written" >&2; exit 1; }

# ---- summaries (CSV), using only report names this version has ---------------
log "nsys stats"
mkdir -p "${OUT}/stats"
AVAIL="$("${NSYS}" stats --help-reports 2>&1 || true)"
# export the sqlite once; every report then reuses it (re-exporting a large trace
# per report cost ~10 min of instance time in the 2026-10-06 session)
FORCE=true
for r in cuda_api_sum cuda_gpu_kern_sum cuda_kern_exec_sum cuda_gpu_mem_time_sum \
         cuda_gpu_mem_size_sum cuda_api_gpu_sum osrt_sum nvtx_sum; do
  grep -qw "${r}" <<<"${AVAIL}" || { echo "skip ${r} (not in this version)" >> "${OUT}/stats/skipped.txt"; continue; }
  "${NSYS}" stats --report "${r}" --format csv --force-export="${FORCE}" \
    --output "${OUT}/stats/${r}" "${OUT}/trace.nsys-rep" >> "${OUT}/stats/stats.log" 2>&1 || \
    echo "failed ${r}" >> "${OUT}/stats/skipped.txt"
  FORCE=false
done
# stats leaves trace.sqlite next to the report; keep it (gzip) for local analysis
[[ -f "${OUT}/trace.sqlite" ]] && gzip -1 -f "${OUT}/trace.sqlite"

# ---- metadata ------------------------------------------------------------------
python3 - "${OUT}/meta.json" <<EOF
import json, sys
json.dump({
  "mode": "${MODE}",
  "warmup": ${WARMUP}, "requests": ${REQUESTS}, "runs": 1, "output_tokens": ${OUTPUT_TOKENS},
  "t_start": "${T_START}", "t_requests_start": "${T_REQ_START}",
  "t_requests_end": "${T_REQ_END}", "t_end": "${T_END}",
  "nsys": "${NSYS}",
  "profile_cmd": """${PROFILE_CMD[*]}""",
  "server_cmd": """${SERVER_CMD[*]}""",
  "runner_cmd": """${RUNNER_CMD[*]}""",
  "git_rev": "$(cat .charon_git_rev 2>/dev/null || echo unknown)",
}, open(sys.argv[1], "w"), indent=2)
EOF
log "done -> ${OUT}"
