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
| Other projects | None. Charon is the only project on this billing account (the default Gemini project was deleted 2026-08-28), so account-wide billing == Charon billing. |

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
`us-central1-a`, falling back to `asia-south1-a` if spot capacity is unavailable.
(`us-central1` is primary because `asia-south1` quota could not be raised — see
[the adjustability finding](#adjustability-asia-south1-blocked) below.)
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

### Initial state (2026-08-28, before requests)

| Quota | Scope | Limit | Enough for one spot g2-standard-4 + L4? |
|---|---|---|---|
| `PREEMPTIBLE_NVIDIA_L4_GPUS` | asia-south1 | **1** | ✅ granted by default |
| `PREEMPTIBLE_NVIDIA_L4_GPUS` | us-central1 | **1** | ✅ granted by default |
| `NVIDIA_L4_GPUS` (on-demand) | both regions | 1 | ✅ (not used — script is spot-only) |
| `CPUS` (on-demand) | asia-south1 | 100 | ✅ (not used — script is spot-only) |
| `CPUS` (on-demand) | us-central1 | 200 | ✅ (not used — script is spot-only) |
| `GPUS_ALL_REGIONS` | global | **0** | ❌ **blocks any GPU instance** |
| `PREEMPTIBLE_CPUS` | us-central1 | **0** | ❌ **blocks the spot vCPUs** |
| `PREEMPTIBLE_CPUS` | asia-south1 | **0** | ❌ and not adjustable — see below |

There is no `G2_CPUS` family quota — G2 machines count against generic
`CPUS` / `PREEMPTIBLE_CPUS`.

The L4 GPU quota itself is **already sufficient** — no GPU quota request is
needed. Only the aggregate GPU switch and the preemptible-CPU counter are at
zero.

<a id="adjustability-asia-south1-blocked"></a>
#### Adjustability: asia-south1 blocked (2026-08-28)

The console refuses an increase on `PREEMPTIBLE_CPUS` in `asia-south1` —
*"you cannot adjust this quota."* `us-central1` takes the request without issue.
The reason wasn't retrievable via CLI (`gcloud beta` not installed) but is
almost certainly project age / billing history, or a regional capacity hold on
that resource in `asia-south1` (Mumbai is a smaller region where this is common).

Consequence: a spot `g2-standard-4` cannot be created in `asia-south1`.
`scripts/session-start.sh` was changed to make `us-central1-a` the primary zone,
with `asia-south1-a` kept as the fallback in case the quota opens up later.
Recorded in the [ADR-0002](../adr/0002-single-cloud-gcp.md) follow-ups. This is
not a change to the single-cloud decision — both zones are GCP.

Cost of running from `us-central1` instead of `asia-south1`: interactive SSH
round-trip during a session is ~200 ms from India vs. ~10–30 ms. Benchmark
numbers are unaffected — the runner measures the server's own timings on the
instance, not network latency to the laptop.

### Requests — approved 2026-08-28

| Quota | Scope | 0 → | Verified |
|---|---|---|---|
| `GPUS_ALL_REGIONS` | global | **1** | `limit=1.0` |
| `PREEMPTIBLE_CPUS` | us-central1 | **8** | `limit=8.0` |

With `PREEMPTIBLE_NVIDIA_L4_GPUS` = 1 (us-central1, granted by default), all
four quotas a spot `g2-standard-4` + L4 needs are now satisfied in us-central1.

`asia-south1` `PREEMPTIBLE_CPUS` is **not requestable** right now (above). Left
at 0; retry if the console later allows it.

Justification text used (kept here in case a re-request is needed):

> Personal learning project benchmarking LLM inference. One spot g2-standard-4
> (1× L4, 4 vCPU), created and deleted per measurement session, never left
> running. Hard budget cap of ₹1,000/month.

Both were approved the same day they were filed.

### How to request — Console (recommended)

1. Console → **IAM & Admin → Quotas & System Limits**, project `charon-506614`.
2. Search `GPUs (all regions)` → tick the row (no region) → **Edit Quotas** →
   `1` → submit.
3. Search `Preemptible CPUs` → filter to region `us-central1` → tick that row →
   **Edit Quotas** → `8` → submit. (The `asia-south1` row shows "you cannot
   adjust this quota" — skip it.)

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
  --dimensions=region=us-central1 \
  --justification="spot g2-standard-4, 1x L4, created/deleted per session"
```

The global `GPUS_ALL_REGIONS` request takes no `--dimensions`. `gcloud beta` is
not installed on the primary machine's SDK as of 2026-08-28 — the console path
above is the one that's been used.

### Re-checking quota

```
gcloud compute regions describe us-central1 --project=charon-506614 --format=json \
  | python3 -c 'import json,sys; [print(f"{q[\"metric\"]:<32} {q[\"limit\"]}") for q in json.load(sys.stdin)["quotas"] if "L4" in q["metric"] or q["metric"] in ("CPUS","PREEMPTIBLE_CPUS")]'

gcloud compute project-info describe --project=charon-506614 --format=json \
  | python3 -c 'import json,sys; [print(f"{q[\"metric\"]:<20} {q[\"limit\"]}") for q in json.load(sys.stdin)["quotas"] if q["metric"]=="GPUS_ALL_REGIONS"]'
```

As of 2026-08-28 this reads `GPUS_ALL_REGIONS 1.0`, `PREEMPTIBLE_CPUS 8.0`,
`PREEMPTIBLE_NVIDIA_L4_GPUS 1.0` — all sufficient.

---

## Still open

- [x] **Billing budget alert** — done 2026-08-28. ₹1,000/month, whole billing
      account (= Charon only), thresholds 50 / 90 / 100 / 150%. Notifies only;
      does not cap spend.
- [x] **Quota requests** — approved and verified 2026-08-28: `GPUS_ALL_REGIONS`
      = 1, `PREEMPTIBLE_CPUS` (us-central1) = 8.
- [x] **`asia-south1` spot capacity** — not usable; quota not adjustable
      (2026-08-28). `us-central1` promoted to primary zone. See the adjustability
      finding above.
- [x] **L4 spot price** — checked 2026-08-28, see [Cost](#cost) below.
- [ ] **`CHARON_PROJECT_ID` on the second machine.**

---

## Cost

**GCP list price, checked 2026-08-28 — not a Charon measurement.** Retrieved from
the Cloud Billing Catalog API (`cloudbilling.googleapis.com`, Compute Engine
service `6F81-5844-456A`), INR, `us-central1`. Spot prices float and GCP can move
the spot ceiling — re-check if it has been a while. The Week 7 cost model uses
*measured* throughput against a rate like this; it does not live here.

### Spot `g2-standard-4` + 1× L4, us-central1

| Component | Rate | Qty | ₹/hour |
|---|---|---|---|
| L4 GPU (spot) | ₹32.13 / GPU-hr | 1 | 32.13 |
| G2 vCPU (spot) | ₹1.4337 / vCPU-hr | 4 | 5.73 |
| G2 RAM (spot) | ₹0.16796 / GiB-hr | 16 | 2.69 |
| 100 GB balanced PD | ₹9.565 / GiB-month | 100 | ~1.31 |
| **All-in** | | | **~₹41.9 / hour** |

On-demand equivalent from the same catalog is ~₹67/hr of compute — spot is
roughly **40% off**, not the 70–90% often quoted for GPUs. The L4 spot discount
is modest.

The boot disk bills only while the instance exists (`--boot-disk-auto-delete`,
deleted per session), so between sessions the cost is ₹0 — the reason
`scripts/session-start.sh` deletes rather than stops.

### Budget headroom

₹1,000/month ÷ ~₹41.9/hour ≈ **24 GPU-hours/month**.

⚠️ The repo's standing figure of **"36–40 GPU-hours"** (README, CLAUDE.md,
ADR-0002, phase-1-plan) is a working estimate, never measured. At today's list
price it is optimistic by ~1.5×. Revising it repo-wide is a pending decision for
the owner.

---

## The session loop

Quota and budget are in place as of 2026-08-28. A measurement session is:

```
bash scripts/session-start.sh     # create the spot instance
# ssh in, start serving/naive_server.py, run benchmarks/baseline_runner.py
# commit the results JSON under benchmarks/results/
bash scripts/session-end.sh       # delete the instance, verify it's gone
bash scripts/cost-check.sh        # confirm nothing is still billing
```
