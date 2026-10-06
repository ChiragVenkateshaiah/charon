#!/usr/bin/env bash
#
# session-bootstrap.sh — on-box setup for a Charon measurement session.
# Runs ON the GPU instance (copied there by scripts/profile-session.sh), from the
# repo root. Provisioning lives in session-start.sh; this only prepares the box.
#
#   bash scripts/session-bootstrap.sh <env-dir>
#
# What it does, in order:
#   1. records the GPU environment (nvidia-smi) into <env-dir>
#   2. installs uv if absent, then `uv sync --locked --group serving` — the
#      exact torch/transformers builds pinned in uv.lock, nothing re-resolved
#   3. finds Nsight Systems; if absent, installs it from NVIDIA's CUDA apt repo
#      (owner pre-approved installing nsys on the instance, 2026-10-06).
#      Nsight Compute is only detected, never installed.
#
# It does not touch serving/ or benchmarks/ code and starts no server.

set -euo pipefail

ENV_DIR="${1:?usage: session-bootstrap.sh <env-dir>}"
mkdir -p "${ENV_DIR}"
log() { echo "[bootstrap $(date -u +%H:%M:%S)] $*"; }

# ---- 1. GPU environment ------------------------------------------------------
log "waiting for the NVIDIA driver"
for _ in $(seq 1 30); do nvidia-smi >/dev/null 2>&1 && break; sleep 10; done
nvidia-smi | tee "${ENV_DIR}/nvidia-smi.txt"
nvidia-smi --query-gpu=name,driver_version,pci.bus_id,memory.total,power.limit,clocks.max.sm,clocks.max.mem,pcie.link.gen.current,pcie.link.width.current,persistence_mode,compute_mode \
  --format=csv > "${ENV_DIR}/nvidia-smi-query.csv"
echo "CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-<unset>}" > "${ENV_DIR}/cuda-visible.txt"
{ uname -a; cat /etc/os-release; nproc; free -g; } > "${ENV_DIR}/host.txt" 2>&1
curl -s -H 'Metadata-Flavor: Google' \
  'http://metadata.google.internal/computeMetadata/v1/instance/image' > "${ENV_DIR}/image.txt" || true

# ---- 2. Python environment from the lockfile ---------------------------------
if ! command -v uv >/dev/null 2>&1 && [[ ! -x "${HOME}/.local/bin/uv" ]]; then
  log "installing uv"
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="${HOME}/.local/bin:${PATH}"
log "uv sync --locked --group serving"
uv sync --locked --group serving
uv --version > "${ENV_DIR}/uv-version.txt"
.venv/bin/python - > "${ENV_DIR}/python-env.txt" <<'EOF'
import sys, torch, transformers
print("python", sys.version.split()[0])
print("torch", torch.__version__, "cuda", torch.version.cuda)
print("transformers", transformers.__version__)
print("cuda_available", torch.cuda.is_available(), torch.cuda.get_device_name(0))
EOF

# ---- 3. Nsight Systems -------------------------------------------------------
find_nsys() {
  command -v nsys 2>/dev/null && return 0
  local c
  for c in /usr/local/cuda/bin/nsys /opt/nvidia/nsight-systems/*/bin/nsys /usr/local/cuda-*/bin/nsys; do
    [[ -x "${c}" ]] && { echo "${c}"; return 0; }
  done
  return 1
}

NSYS="$(find_nsys || true)"
if [[ -z "${NSYS}" ]]; then
  log "nsys not on the image — installing from NVIDIA's CUDA apt repo"
  echo "installed-by-bootstrap" > "${ENV_DIR}/nsys-provenance.txt"
  sudo apt-get -o DPkg::Lock::Timeout=300 update -qq
  if ! apt-cache search --names-only '^nsight-systems-[0-9]' | grep -q .; then
    log "CUDA apt repo not configured — adding cuda-keyring"
    tmp="$(mktemp -d)"
    curl -fsSL -o "${tmp}/cuda-keyring.deb" \
      https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-keyring_1.1-1_all.deb
    sudo dpkg -i "${tmp}/cuda-keyring.deb"
    sudo apt-get -o DPkg::Lock::Timeout=300 update -qq
  fi
  PKG="$(apt-cache search --names-only '^nsight-systems-[0-9]' | awk '{print $1}' | sort -V | tail -n1)"
  [[ -n "${PKG}" ]] || { echo "ERROR: no nsight-systems package found in apt" >&2; exit 1; }
  log "apt-get install ${PKG}"
  sudo DEBIAN_FRONTEND=noninteractive apt-get -o DPkg::Lock::Timeout=300 install -y -qq "${PKG}"
  NSYS="$(find_nsys || true)"
  [[ -n "${NSYS}" ]] || { echo "ERROR: ${PKG} installed but nsys not found" >&2; exit 1; }
else
  echo "preinstalled-on-image" > "${ENV_DIR}/nsys-provenance.txt"
fi
echo "${NSYS}" > "${HOME}/.charon_nsys"
"${NSYS}" --version | tee "${ENV_DIR}/nsys-version.txt"
"${NSYS}" status --environment > "${ENV_DIR}/nsys-status.txt" 2>&1 || true

NCU="$(command -v ncu 2>/dev/null || ls /usr/local/cuda/bin/ncu 2>/dev/null || true)"
if [[ -n "${NCU}" ]]; then "${NCU}" --version > "${ENV_DIR}/ncu-version.txt" 2>&1 || true
else echo "ncu: not present (not installed by design)" > "${ENV_DIR}/ncu-version.txt"; fi

log "bootstrap done"
