#!/usr/bin/env bash
#
# session-end.sh — tear down the Charon GPU instance at the end of a measurement
# session, and verify it's actually gone.
#
# WHY THIS SCRIPT EXISTS (read before changing it):
# On a ~1,000 INR/month budget (36-40 GPU-hours), a GPU instance that fails to
# delete and goes unnoticed is the single most expensive mistake available in this
# project. This script does not just issue a delete — it confirms the delete
# actually happened, and fails loudly (non-zero exit, clear error) if the instance
# is still visible afterwards, rather than trusting that the gcloud command
# succeeded silently. Never comment out or skip the verification step.

set -euo pipefail

PROJECT_ID="${CHARON_PROJECT_ID:?Set CHARON_PROJECT_ID to your GCP project id}"
INSTANCE_NAME="${CHARON_INSTANCE_NAME:-charon-gpu}"

echo "Looking up zone for instance '${INSTANCE_NAME}'..."
ZONE="$(gcloud compute instances list \
  --project="${PROJECT_ID}" \
  --filter="name=${INSTANCE_NAME}" \
  --format="value(zone)" | head -n1)"

if [[ -z "${ZONE}" ]]; then
  echo "No instance named '${INSTANCE_NAME}' found in project '${PROJECT_ID}'. Nothing to delete."
  exit 0
fi

echo "Deleting '${INSTANCE_NAME}' in ${ZONE}..."
gcloud compute instances delete "${INSTANCE_NAME}" \
  --project="${PROJECT_ID}" \
  --zone="${ZONE}" \
  --quiet

echo "Verifying deletion..."
REMAINING="$(gcloud compute instances list \
  --project="${PROJECT_ID}" \
  --filter="name=${INSTANCE_NAME}" \
  --format="value(name)")"

if [[ -n "${REMAINING}" ]]; then
  echo "ERROR: instance '${INSTANCE_NAME}' still exists after delete was requested." >&2
  echo "Do not leave this unresolved — check the console and delete it manually now." >&2
  exit 1
fi

echo "Confirmed: '${INSTANCE_NAME}' no longer exists."
echo "Run scripts/cost-check.sh now to confirm nothing else is running or billing."
