# ADR-0017: Terraform (AWS EKS) + Helm Chart — Static, Validate-Only IaC

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-08-17 |
| **Deciders** | Konsole.ai team |
| **Related** | [ADR-0014: Kubernetes / Cloud Deployment](0014-kubernetes-and-cloud-deployment.md) (extends), [ADR-0011: Docker Compose Profiles](0011-docker-compose-profiles.md), [ADR-0012: CI/CD & GHCR Publishing](0012-ci-cd-ghcr-publishing.md) |

## Context

ADR-0014 accepted Option A -- build Kubernetes manifests/a Helm chart as a
static, `kind`-validated artifact only, never a live cloud deployment --
but nothing under it was ever built: no `kubernetes/`, `helm/`, or
`terraform/` directory existed in the repo. This ADR is that build, scoped
explicitly to AWS via Terraform provisioning an EKS cluster (not GCP, and
not ADR-0014's rejected single-VM Option C), plus the Helm chart ADR-0014
always implied but never wrote.

## Decision Drivers

- ADR-0014's reasoning applies unchanged: this is a portfolio project
  reviewed as text far more often than clicked as a live link, and a GPU
  node kept running for Ollama costs roughly $300-800/month -- not
  something to leave on between interview cycles for a project with no
  real traffic.
- Community Terraform modules
  ([`terraform-aws-modules/vpc`](https://registry.terraform.io/modules/terraform-aws-modules/vpc/aws/latest),
  [`terraform-aws-modules/eks`](https://registry.terraform.io/modules/terraform-aws-modules/eks/aws/latest))
  over hand-rolled `aws_*` resources -- this is what real EKS Terraform
  looks like in practice, and `terraform validate` needs no AWS
  credentials either way, so there's no cost trade-off to using them.
- Terraform and the Helm chart are kept independently reviewable: this
  configuration has no `helm` or `kubernetes` Terraform provider, and
  never runs `helm install`. Coupling them would force one to depend on
  the other being live, which contradicts the whole point of validating
  both without ever applying either against a real account.
- `api`'s single-replica constraint (no HPA object for it anywhere in the
  chart) is a genuine inherited architectural limit -- FAISS indexes
  (ADR-0001, ADR-0013) and the SQLite LLM trace store (ADR-0015) are local
  files on one PVC, and a second writer would be unsafe -- not a Helm
  oversight. Stated plainly here since a Kubernetes-literate reviewer will
  otherwise wonder why it's missing.

## Options Considered

### Option A — Terraform for AWS EKS + a Helm chart, both validate-only

**Pros**
- Demonstrates both IaC (Terraform + community modules) and Kubernetes
  packaging (Helm) skill as static, reviewable artifacts.
- Zero ongoing cost, zero uptime risk -- `terraform validate` and
  `helm lint`/`helm template` need no cloud credentials at all.
- Matches what was explicitly requested and scoped (AWS, full EKS
  cluster, not a lighter-weight alternative).

**Cons**
- No clickable live demo -- a reviewer reads Terraform/Helm source rather
  than clicking a link.
- Two more directories/toolchains to keep in sync with the rest of the
  repo (`docker-compose.yml`, `Settings`) as it evolves.

### Option B — Skip Terraform, Helm chart only

**Pros**
- Less surface area; the Helm chart alone already satisfies ADR-0014's
  Option A.

**Cons**
- Doesn't demonstrate IaC/cloud-provisioning skill at all, only Kubernetes
  packaging -- weaker signal for the "senior platform engineering"
  audience ADR-0014 was already written for.
- Contradicts the explicit request that motivated this ADR.

### Option C — Actually apply against a real (even free-tier) AWS account

**Pros**
- A genuinely live, clickable cluster.

**Cons**
- Directly contradicts ADR-0014's cost/uptime reasoning: EKS itself bills
  hourly for the control plane on top of any node cost, and a GPU node for
  Ollama is $300-800/month if left running. Rejected outright, same as it
  was in ADR-0014.

## Decision

**Build `terraform/` (VPC + EKS control plane + a default CPU-only managed
node group + an opt-in scale-to-zero GPU node group + IRSA) and
`helm/konsole-ai/` (Deployments/StatefulSet/Services/ConfigMap/Secret/PVC/
optional HPA+Ingress) as described above (Option A). Terraform never
installs the Helm chart -- the two are validated independently.**

Validation is three-tiered:

1. **CI-gated on every push/PR**, via a new `iac-validate` job in
   `.github/workflows/ci.yml` (not wired into `publish`'s `needs:` -- IaC
   correctness doesn't gate image publishing): `terraform fmt -check`,
   `terraform init -backend=false`, `terraform validate`; `helm lint`;
   `helm template` with default values and again with
   `--set ollama.gpu.enabled=true --set ingress.enabled=true` to exercise
   both conditional template branches. None of these need AWS credentials.
2. **A manual, reproducible `make kind-smoke-test`** (builds local images,
   creates a `kind` cluster, loads the images, `helm install`s with
   `pullPolicy=Never`, reports pod status) plus `make kind-smoke-test-clean`
   to tear it down. **Deliberately not CI-gated.** The readiness probe
   this chart wires up (`GET /api/v1/health/ready`, backed by
   `OllamaClient.is_reachable()` in `llm/ollama/client.py`) only performs a
   bare `GET /api/version` against the Ollama daemon -- it does not check
   that any model has actually been pulled. So a pod can go "Ready" in a
   fresh `kind` cluster with zero real capability, and pulling the
   multi-GB `ollama/ollama` image plus a model on every push would be
   slow and flaky for reasons unrelated to whether the Terraform/Helm YAML
   itself is correct. Even a fully green pod would prove nothing about
   real `/documents/ask` behavior without a pulled model -- exactly what
   static `helm lint`/`helm template` already prove, at zero runtime cost.
   Static validation stays the required CI gate; `kind` stays a
   reviewer-runnable local target.
3. **`terraform plan` / `terraform apply` are never run against a real AWS
   account in this project -- no exceptions.**

## Revisit Triggers

Same as ADR-0014:
- A specific interview process asks for a hosted, clickable demo.
- The `LLM_PROVIDER` external-API adapter (ADR-0002) gets built, removing
  the GPU-cost blocker for a responsive live demo.

Additionally:
- A GCP variant of `terraform/`, if a specific process asks for it.
- `jaeger`/`prometheus`/`grafana` templates added to the Helm chart, if the
  observability stack (currently Compose-profile-only, ADR-0011) is ever
  needed on a real cluster.
- A `values.schema.json` for the chart, if it grows enough to warrant CI
  schema validation beyond `helm lint`.

## Consequences

- New `terraform/` and `helm/konsole-ai/` top-level directories, both
  outside `pyproject.toml`'s scope -- no ruff/mypy coupling, same as
  `infra/`.
- New `iac-validate` CI job; `lint-and-test`, `docker-build`, and
  `publish` are unchanged.
- New `.gitignore` entries for Terraform's local state/cache
  (`terraform/.terraform/`, `*.tfstate`, `*.tfstate.*`, `crash.log`,
  `override.tf*`) -- `terraform/.terraform.lock.hcl` is committed, per
  standard Terraform practice.
- No live cloud account, no billing, no change to any existing service or
  `docker-compose.yml`.
