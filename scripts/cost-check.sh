#!/usr/bin/env bash
#
# cost-check.sh — list everything in the project that could currently be billing:
# running instances and disks of any kind, in any zone.
#
# WHY THIS SCRIPT EXISTS (read before changing it):
# The project's entire budget is ~1,000 INR/month, roughly 36-40 GPU-hours. A single
# forgotten instance or an orphaned disk (persistent disks bill even with nothing
# attached) can consume a meaningful fraction of that in a day. This script is meant
# to be run on a whim, with no arguments, any time there's doubt about what's live —
# not just after session-end.sh. It intentionally does not filter by name, so it
# also catches anything created outside the session scripts.

set -euo pipefail

PROJECT_ID="${CHARON_PROJECT_ID:?Set CHARON_PROJECT_ID to your GCP project id}"

echo "=== Running instances (any zone) — project: ${PROJECT_ID} ==="
gcloud compute instances list \
  --project="${PROJECT_ID}" \
  --filter="status=RUNNING" \
  --format="table(name,zone,machineType.basename(),status,scheduling.provisioningModel)"

echo
echo "=== All disks (any zone) — project: ${PROJECT_ID} ==="
gcloud compute disks list \
  --project="${PROJECT_ID}" \
  --format="table(name,zone,sizeGb,status,users.list())"

echo
echo "If anything above is unexpected, resolve it now — don't leave it for later."
