#!/usr/bin/env bash
#
# session-start.sh — bring up the Charon GPU instance for one measurement session.
#
# WHY THIS SCRIPT EXISTS (read before changing it):
# The whole project runs on a ~1,000 INR/month budget, roughly 36-40 GPU-hours.
# That budget only survives if the GPU is on for the duration of a measurement and
# nothing more. Spot + --instance-termination-action=DELETE means a preemption
# deletes the instance outright instead of leaving it (or its disk) stopped and
# still billing. This is not a style choice: a persistent disk left behind after a
# stopped instance would burn roughly a third of the monthly budget on its own.
#
# This script does not run any serving/benchmark code. It only provisions the box.
# All development, debugging, and analysis happens locally on CPU, before and after
# this script runs — never while deciding what to run next.

set -euo pipefail

PROJECT_ID="${CHARON_PROJECT_ID:?Set CHARON_PROJECT_ID to your GCP project id}"
INSTANCE_NAME="${CHARON_INSTANCE_NAME:-charon-gpu}"
MACHINE_TYPE="g2-standard-4"
ACCELERATOR="type=nvidia-l4,count=1"

# Primary zone per project decision; fallback used only if spot capacity is
# unavailable in the primary zone at request time.
#
# us-central1 is primary, not asia-south1: the preemptible-CPU quota in
# asia-south1 was not adjustable for this project as of 2026-08-28 (project age
# or regional capacity — "you cannot adjust this quota" in the console), so a
# spot g2-standard-4 cannot be created there. asia-south1-a is kept as the
# fallback in case that quota opens up later. See docs/gcp-setup.md and the
# ADR-0002 follow-ups.
PRIMARY_ZONE="${CHARON_PRIMARY_ZONE:-us-central1-a}"
FALLBACK_ZONE="${CHARON_FALLBACK_ZONE:-asia-south1-a}"

IMAGE_FAMILY="${CHARON_IMAGE_FAMILY:-common-cu124}"
IMAGE_PROJECT="${CHARON_IMAGE_PROJECT:-deeplearning-platform-release}"
BOOT_DISK_SIZE="${CHARON_BOOT_DISK_SIZE:-100GB}"

create_instance() {
  local zone="$1"
  echo "Attempting to create '${INSTANCE_NAME}' in ${zone} (spot, ${MACHINE_TYPE}, ${ACCELERATOR})..."
  gcloud compute instances create "${INSTANCE_NAME}" \
    --project="${PROJECT_ID}" \
    --zone="${zone}" \
    --machine-type="${MACHINE_TYPE}" \
    --accelerator="${ACCELERATOR}" \
    --image-family="${IMAGE_FAMILY}" \
    --image-project="${IMAGE_PROJECT}" \
    --boot-disk-size="${BOOT_DISK_SIZE}" \
    --boot-disk-auto-delete \
    --provisioning-model=SPOT \
    --instance-termination-action=DELETE \
    --maintenance-policy=TERMINATE
}

if create_instance "${PRIMARY_ZONE}"; then
  echo "Instance '${INSTANCE_NAME}' created in ${PRIMARY_ZONE}."
elif create_instance "${FALLBACK_ZONE}"; then
  echo "Primary zone unavailable (likely no spot capacity). Instance '${INSTANCE_NAME}' created in fallback zone ${FALLBACK_ZONE}."
else
  echo "ERROR: failed to create instance in both ${PRIMARY_ZONE} and ${FALLBACK_ZONE}." >&2
  exit 1
fi

echo
echo "Reminder: this instance bills from now until scripts/session-end.sh deletes it."
echo "Run scripts/cost-check.sh at any time to confirm what's currently running."
