# GCP setup for Charon

Everything needed to get from a bare GCP project to a working
`scripts/session-start.sh`. Per [ADR-0002](../adr/0002-single-cloud-gcp.md)
Charon runs single-cloud on GCP; this is the groundwork that decision implies.

None of this consumes GPU-hours — it is console and local-CLI work, done on CPU
before any measurement session.

**Facts in this file are dated.** Quotas and API state change; where a value was
read from the live project it is labelled with the date it was checked. Re-verify
before relying on it (see [Re-checking quota](#re-checking-quota)).

---

## Project

| | |
|---|---|
| Project ID | `charon-506614` |
| Project number | `963666199880` |
| Project name | Charon |
| Billing | Pay-as-you-go (free trial exhausted). A full billing account can request GPU quota; a free-trial account cannot. |
| Account | `chiragvenkateshaiah95@gmail.com` |

### `CHARON_PROJECT_ID`

All three session scripts (`session-start.sh`, `session-end.sh`,
`cost-check.sh`) read `CHARON_PROJECT_ID` from the environment and fail loudly if
it is unset. Charon is worked from two machines — set it in the shell profile on
**both**:

```
export CHARON_PROJECT_ID=charon-506614
```

Added to `~/.zshrc` on the primary machine 2026-08-28. Still to do on the second.

---

## APIs

| API | State | Notes |
|---|---|---|
| `compute.googleapis.com` | Enabled 2026-08-28 | Required for any instance, disk, or quota read. Was disabled on project creation. |

```
gcloud services enable compute.googleapis.com --project=charon-506614
```

---

## Quota

GCP caps how much of a resource a project may allocate. A quota is **not**
billing and not reserved capacity — it is a ceiling. Raising one costs nothing;
you are billed only for what you actually run. The ₹1,000/month budget is
enforced by the billing alert and the session-script discipline, not by quota.

GPU quota defaults to `0` on almost every new project (GPUs are the prime target
for account-takeover abuse). GCP grants small amounts once an account is an
established payer.

### What `session-start.sh` needs

The script creates one spot `g2-standard-4` (4 vCPU) + 1× NVIDIA L4 in
`asia-south1-a`, falling back to `us-central1-a` if spot capacity is unavailable.
GCP checks **four** quotas and **all must pass**:

| Instance asks for | Quota | Scope |
|---|---|---|
| 1 L4 GPU, spot, in the region | `PREEMPTIBLE_NVIDIA_L4_GPUS` | per-region |
| 1 GPU, any type, project-wide | `GPUS_ALL_REGIONS` | global |
| 4 vCPU, spot, in the region | `PREEMPTIBLE_CPUS` | per-region |
| 100 GB boot disk | disk quota | per-region |

Spot (a.k.a. preemptible) instances count against **separate** quotas from
on-demand: their vCPUs bill against `PREEMPTIBLE_CPUS`, not `CPUS`, and GCP can
reclaim the instance at ~30s notice. Charon uses spot deliberately
(ADR-0002) — sessions are short and restartable, and `session-start.sh` pairs
`--provisioning-model=SPOT` with `--instance-termination-action=DELETE` so a
preemption deletes the box and its disk rather than leaving them billing.

### State as checked 2026-08-28

| Quota | Scope | Limit | Enough for one spot g2-standard-4 + L4? |
|---|---|---|---|
| `PREEMPTIBLE_NVIDIA_L4_GPUS` | asia-south1 | **1** | ✅ granted by default |
| `PREEMPTIBLE_NVIDIA_L4_GPUS` | us-central1 | **1** | ✅ granted by default |
| `NVIDIA_L4_GPUS` (on-demand) | both regions | 1 | ✅ (not used — script is spot-only) |
| `CPUS` (on-demand) | asia-south1 | 100 | ✅ (not used — script is spot-only) |
| `CPUS` (on-demand) | us-central1 | 200 | ✅ (not used — script is spot-only) |
| `GPUS_ALL_REGIONS` | global | **0** | ❌ **blocks any GPU instance** |
| `PREEMPTIBLE_CPUS` | asia-south1 | **0** | ❌ **blocks the spot vCPUs** |
| `PREEMPTIBLE_CPUS` | us-central1 | **0** | ❌ blocks the fallback zone |

There is no `G2_CPUS` family quota — G2 machines count against generic
`CPUS` / `PREEMPTIBLE_CPUS`.

The L4 GPU quota itself is **already sufficient** — no GPU quota request is
needed. Only the aggregate GPU switch and the preemptible-CPU counters are at
zero.

### Requests to file

| Quota | Scope | 0 → | Rationale |
|---|---|---|---|
| `GPUS_ALL_REGIONS` | global | **1** | master switch; one GPU project-wide |
| `PREEMPTIBLE_CPUS` | asia-south1 | **8** | 4 vCPU of the spot g2-standard-4, with headroom for a possible g2-standard-8 later |
| `PREEMPTIBLE_CPUS` | us-central1 | **8** | same, for the fallback zone |

Justification text (same for all three):

> Personal learning project benchmarking LLM inference. One spot g2-standard-4
> (1× L4, 4 vCPU), created and deleted per measurement session, never left
> running. Hard budget cap of ₹1,000/month.

Upgraded billing account + small values are often auto-approved within minutes;
worst case is quoted at ~2 business days.

### How to request — Console (recommended)

1. Console → **IAM & Admin → Quotas & System Limits**, project `charon-506614`.
2. Search `GPUS_ALL_REGIONS` → tick the row (no region) → **Edit Quotas** →
   `1` → submit.
3. Search `Preemptible CPUs` → tick the `asia-south1` and `us-central1` rows →
   **Edit Quotas** → `8` → submit.

### How to request — CLI

```
# discover the quota IDs (they differ from the metric names)
gcloud beta quotas info list --service=compute.googleapis.com \
  --project=charon-506614 \
  --filter="metric:(GPUS_ALL_REGIONS OR PREEMPTIBLE_CPUS)" \
  --format="table(name, metric, quotaId, dimensions)"

# then one preference per row, using the quotaId from above
gcloud beta quotas preferences create \
  --project=charon-506614 --service=compute.googleapis.com \
  --quota-id=<QUOTA_ID> --preferred-value=8 \
  --dimensions=region=asia-south1 \
  --justification="spot g2-standard-4, 1x L4, created/deleted per session"
```

The global `GPUS_ALL_REGIONS` request takes no `--dimensions`.

### Re-checking quota

```
gcloud compute regions describe asia-south1 --project=charon-506614 --format=json \
  | python3 -c 'import json,sys; [print(f"{q[\"metric\"]:<32} {q[\"limit\"]}") for q in json.load(sys.stdin)["quotas"] if "L4" in q["metric"] or q["metric"] in ("CPUS","PREEMPTIBLE_CPUS")]'

gcloud compute project-info describe --project=charon-506614 --format=json \
  | python3 -c 'import json,sys; [print(f"{q[\"metric\"]:<20} {q[\"limit\"]}") for q in json.load(sys.stdin)["quotas"] if q["metric"]=="GPUS_ALL_REGIONS"]'
```

---

## Still open

- [ ] **Billing budget alert** — ₹1,000/month with a threshold notification.
      Blocking before the first real `session-start.sh` run
      ([ADR-0002](../adr/0002-single-cloud-gcp.md) follow-up).
- [ ] **Quota requests** — the three above; not yet filed as of 2026-08-28.
- [ ] **`CHARON_PROJECT_ID` on the second machine.**
- [ ] **Confirm `g2-standard-4` spot capacity and current L4 spot price in
      `asia-south1`** before booking a session (ADR-0002 follow-up). The
      us-central1 fallback is already wired into `session-start.sh`. No spot
      price is asserted anywhere in this repo until it is checked against the
      live console — it is not a Charon measurement.

---

## Once quota clears — the session loop

```
bash scripts/session-start.sh     # create the spot instance
# ssh in, start serving/naive_server.py, run benchmarks/baseline_runner.py
# commit the results JSON under benchmarks/results/
bash scripts/session-end.sh       # delete the instance, verify it's gone
bash scripts/cost-check.sh        # confirm nothing is still billing
```
