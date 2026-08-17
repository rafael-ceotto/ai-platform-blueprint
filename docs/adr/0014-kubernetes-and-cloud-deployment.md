# ADR-0014: Kubernetes / Cloud Deployment — Documented, Not Implemented Yet

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-08-13 |
| **Deciders** | Konsole.ai team |
| **Related** | [ADR-0002: LLM Runtime](0002-llm-runtime-ollama-vs-external-apis.md), [ADR-0011: Docker Compose Profiles](0011-docker-compose-profiles.md), [ADR-0012: CI/CD & GHCR Publishing](0012-ci-cd-ghcr-publishing.md), [ADR-0017: Terraform (AWS EKS) + Helm Chart](0017-terraform-aws-eks-and-helm-chart.md) |

## Context

The blueprint currently ships as a single-host `docker-compose.yml`
(`api`, `ui`, `ollama`, plus an opt-in `observability` profile per
ADR-0011), with images published to GHCR on every push to `main`
(ADR-0012). Whether to go further — Kubernetes manifests/Helm chart,
and/or an actual live deployment on GCP or AWS — comes up naturally
once images are already being built and pushed.

## Decision Drivers

- This is a **portfolio project evaluated by senior engineers**, not a
  system under real load. The audience reads artifacts (manifests,
  ADRs, architecture docs) far more often than they click a live demo
  link — and a live link that's down or slow during an interview is a
  worse outcome than no link at all.
- **Ollama has no GPU in most reasonable deployment targets.** A GPU
  node pool on GKE/EKS costs roughly $300-800/month kept running, which
  is not something to leave on indefinitely between interview cycles.
  CPU-only inference is slow enough to make a live demo feel broken
  rather than impressive.
- ADR-0002 already anticipated this: LLM access goes through a narrow
  client interface, with `LLM_PROVIDER=ollama|anthropic|openai` called
  out as an additive future change specifically for deployments where
  local inference isn't viable — a live cloud deployment would lean on
  that revisit trigger, not on this ADR.
- Every dependency/infra layer this blueprint has added has been tied
  to a concrete need (hybrid retrieval, SSE streaming, compose
  profiles) rather than "what production systems typically have" — the
  same discipline applied to the message-broker question in ADR-0009
  applies here.

## Options Considered

### Option A — Manifests/Helm chart only, validated locally (`kind`), no live deployment

**Pros**
- Zero ongoing cost, zero uptime risk during a job search.
- Still demonstrates the actual skill being signaled: correct
  Deployments/Services/Ingress, resource requests/limits, HPA,
  ConfigMaps/Secrets, and reasoning about a GPU node pool for Ollama —
  reviewable as static artifacts plus a `kind`-cluster smoke test.
- Fully reversible; no cloud account, billing, or IAM setup required.

**Cons**
- No clickable live demo link — a recruiter has to read the manifests
  rather than click something.

### Option B — Live deployment on GKE/EKS (or GKE Autopilot / Cloud Run)

**Pros**
- A real, clickable demo link — highest immediate impact if it happens
  to come up in conversation and is up and responsive at that moment.
- Forces genuinely production-shaped decisions (ingress/TLS, secrets
  management, autoscaling under real constraints) rather than a
  `kind`-only approximation.

**Cons**
- Ongoing cost: either pay for a GPU node to keep Ollama fast, or swap
  to a hosted LLM API (via the ADR-0002 `LLM_PROVIDER` hook) and pay
  per-token instead — either way, a recurring bill for a project with
  no real traffic.
- Ongoing maintenance burden (cert rotation, cluster upgrades, cost
  monitoring) that competes with actual feature work on the blueprint.
- Outage/latency risk at exactly the wrong moment — during an
  interview or a recruiter's five-minute look.

### Option C — Terraform/IaC for a single cloud VM (no Kubernetes)

**Pros**
- Still demonstrates cloud/IaC fluency, cheaper and simpler than a
  full cluster.

**Cons**
- Weaker signal for "senior platform engineering" than Kubernetes
  specifically, which is the more commonly expected artifact at that
  level — doesn't clearly beat Option A for the cost/benefit it adds.

## Decision

**Document the trade-off now (this ADR); build manifests later, as a
static/local-only artifact (Option A), if and when we get to it — no
live cloud deployment.** The reasoning mirrors ADR-0009: the
infrastructure a portfolio reviewer wants to see is a well-reasoned,
correct artifact, not a running service that costs money to keep alive
between interview cycles.

## Revisit Triggers

Move to Option B (an actual live deployment) if:

- A specific interview process asks for a hosted, clickable demo as
  part of the process (at which point the cost is bounded and
  justified).
- The `LLM_PROVIDER` external-API adapter from ADR-0002 gets built,
  removing the GPU-cost blocker for a responsive live demo.

Build the Option A manifests/Helm chart when there's time to treat it
as its own artifact worth reviewing carefully, rather than a rushed
addition.

## Consequences

- No new services, manifests, or cloud accounts from this ADR — it
  exists to record the reasoning so the question doesn't need
  re-litigating, and so the trade-off is visible to anyone reviewing
  this blueprint's architecture decisions.
- The manifests/Helm chart and Terraform this ADR deferred were built
  under ADR-0017, still never applied live.
