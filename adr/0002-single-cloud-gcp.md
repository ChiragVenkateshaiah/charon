# ADR-0002: Charon runs single-cloud on Google Cloud

- **Status:** Accepted
- **Date:** 2026-08-26
- **Phase:** All
- **Deciders:** Chirag
- **Supersedes / Related:** None

---

## Context

Charon needs a cloud GPU provider before Phase 1 can produce its first measured
number — there is no local GPU, so every measurement in this project runs on rented
hardware. That forces a provider choice up front, not something to defer.

**Constraints in play:**

- **Budget:** a flexible target of ~₹1,000/month (~24 GPU-hours at current spot
  list price — see `docs/gcp-setup.md` and the Follow-ups below; the "36–40" this
  ADR originally carried was an unmeasured guess). Extendable when a specific
  measurement needs it, but modest enough that the provider choice should be made
  once and not re-litigated mid-project.
- **Hardware available:** none locally with a GPU. All GPU compute is rented, spot
  only, powered on only for the duration of a measurement.
- **Existing platform commitments:** the active project portfolio is already
  AWS-heavy — Cerberus runs on EMR Serverless / Athena / S3 Iceberg / OpenTofu in
  `ap-south-1`, and novapay-sre runs on EC2 managed with Ansible. Both represent real,
  demonstrated AWS depth already.
- **Phase 3 target:** the platform phase of this project (promotion, canary rollout,
  SLO-driven rollback) is scoped against GKE from the outset, not against a
  provider-neutral "some Kubernetes" — see `docs/phase-1-plan.md` and the project
  README.
- **Time box:** none explicit; this is a standing decision for the life of the
  project, not a per-phase one.

---

## Decision

Charon runs entirely on Google Cloud — single-cloud, deliberately, for the life of the
project. All compute (currently a spot `g2-standard-4`, 1× NVIDIA L4) and the Phase 3
platform layer (GKE) live on GCP. No AWS resources are provisioned for Charon.

This is a project-scoped decision, not an organizational one. The rest of the active
portfolio (Cerberus, novapay-sre) stays on AWS.

---

## Measured evidence

**Not applicable.** This ADR does not claim GCP is cheaper, faster, or otherwise
technically superior to AWS for GPU inference — no comparative benchmark exists between
the two, and none is planned. It is a scope decision made for the reasons in
*Options considered* below, primarily portfolio diversification and Phase 3's GKE
target, not a performance or cost claim. Per ADR-0001, any number in this project that
*is* a performance or cost claim still has to be measured on real hardware and
committed — this ADR just isn't one of those.

---

## Options considered

### Option A — GCP only (chosen)

- **How it works:** all Charon compute, storage, and eventually GKE, provisioned on a
  single GCP project.
- **Pros:** Phase 3 already targets GKE, so building single-cloud avoids cross-cloud
  networking and auth friction between the GPU-serving layer and the orchestration
  layer later. It also diversifies the active portfolio — three of four other active
  projects are AWS-only, and GCP-specific experience (IAM, networking, billing,
  Compute Engine spot semantics, GKE) is a real gap those projects don't close.
  Existing Kubernetes/Helm/Prometheus knowledge transfers reasonably well to GKE, so
  the learning curve is narrower than it looks.
- **Cons:** none of the AWS-specific tooling and account setup already built for
  Cerberus and novapay-sre (OpenTofu modules, IAM patterns, budget alerting) carries
  over. Starts from a colder start on GCP's console/CLI/billing idioms specifically.
- **Rejected because:** not rejected — this is the chosen option.

### Option B — AWS only, consistent with the rest of the portfolio

- **How it works:** run Charon on EC2 GPU instances (e.g. `g5.xlarge`), reusing the
  AWS account, billing setup, and IAM patterns already established for Cerberus and
  novapay-sre.
- **Pros:** no new cloud to learn operationally; billing and budget alerting patterns
  from Cerberus are directly reusable.
- **Cons:** does nothing to close the GCP/GKE gap, and would force Phase 3 to either
  target EKS instead of GKE (a scope change from the project's own plan) or introduce
  a second cloud later anyway, at a point where switching is more disruptive.
- **Rejected because:** would leave the entire active portfolio single-provider, which
  undersells breadth, and defers rather than avoids the eventual GKE question.

### Option C — Multi-cloud / hybrid (cheapest spot capacity wherever available)

- **How it works:** shop GPU spot capacity across both providers per session, optimizing
  for whichever is cheaper or has capacity at the time.
- **Pros:** theoretically minimizes GPU cost within the ₹1,000/month budget.
- **Cons:** doubles the operational surface (two billing consoles, two sets of
  credentials, two networking models) for a project whose actual constraint is
  discipline around a small number of GPU-hours, not squeezing out marginal spot
  savings. Fragments budget tracking across two billing accounts, which works against
  the project's own measurement discipline.
- **Rejected because:** the complexity cost is disproportionate to the benefit at this
  budget scale, and it doesn't produce a cleaner story for Phase 3's GKE work either.

---

## Consequences

**Accepted costs.** Slower initial ramp on GCP-specific IAM, networking, billing UI,
and CLI idioms, none of which is reusable from the AWS work already done elsewhere in
the portfolio.

**Operational burden.** A second cloud billing account and budget alert to configure
and monitor independently of the AWS ones already in place for other projects — see
Follow-ups.

**Reversibility.** Moderate. Nothing about the GCP setup is architecturally
irreversible — spot instances, no persistent state between sessions — but Phase 1's
benchmark numbers are specific to the L4 hardware they were measured on. Switching
providers mid-project would not invalidate the methodology, but it would mean the
existing benchmark table stops being an apples-to-apples comparison and a new hardware
baseline would be needed.

**Blast radius if wrong.** Contained. Nothing downstream depends on this yet — worst
case is re-running Phase 1's measurements on different hardware.

---

## Non-goals

- Not a claim that GCP is technically or economically better than AWS for GPU
  inference generally — no such comparison was made or is planned.
- Not a permanent, org-wide cloud decision. Other projects remain on AWS by design;
  this ADR governs Charon only.
- Not an attempt to build cross-cloud portability into Charon's tooling or scripts.

---

## Follow-ups

- [x] GCP billing budget alert configured — done 2026-08-28. ₹1,000/month,
      "Specified amount", scoped to the whole billing account, alert thresholds
      at 50 / 90 / 100 / 150%. The account holds only the Charon project (the
      default Gemini project was deleted 2026-08-28), so account-wide spend and
      Charon spend are the same thing. It notifies; it does not cap spend — the
      teardown script and session discipline are the actual cap.
- [x] Confirm `g2-standard-4` spot capacity in `asia-south1` — **not usable as of
      2026-08-28.** The preemptible-CPU quota in `asia-south1` is not adjustable for
      this project (console: "you cannot adjust this quota"; likely project age or
      regional capacity), so a spot `g2-standard-4` cannot be created there.
      `us-central1` was promoted to primary zone in `scripts/session-start.sh`;
      `asia-south1-a` stays as the fallback in case the quota opens up later. This
      does not change the single-cloud decision — both zones are GCP. See
      `docs/gcp-setup.md`. Revisit if `asia-south1` quota becomes adjustable.
- [x] Confirm current L4 spot price — checked 2026-08-28 via the Cloud Billing
      Catalog API. Spot `g2-standard-4` + 1× L4 in `us-central1` is ~₹41.9/hour
      all-in (GCP list price, not a Charon measurement). That is ~24 GPU-hours in
      a ₹1,000 month, vs the "36–40" this ADR and other docs carried. The budget
      is a flexible target (owner, 2026-08-28), so the number was corrected to
      ~24 repo-wide rather than the plan being cut. See `docs/gcp-setup.md`.
- [ ] Revisit trigger: none anticipated within this project's scope. Would only
      revisit if GCP spot L4 pricing or capacity changed materially enough to threaten
      the ₹1,000/month budget.
