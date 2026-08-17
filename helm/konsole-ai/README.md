# konsole-ai (Helm chart)

Deploys the `api`, `ollama`, and `ui` containers from the repo root's
`docker-compose.yml` onto *some* Kubernetes cluster -- this chart doesn't
care whether that cluster is `kind`, EKS, GKE, or anything else. It's
validated independently from `terraform/` (which provisions an AWS EKS
cluster but never installs this chart itself) -- see
[`docs/adr/0017-terraform-aws-eks-and-helm-chart.md`](../../docs/adr/0017-terraform-aws-eks-and-helm-chart.md)
for why the two are kept decoupled.

**This chart has only ever been validated via `helm lint`, `helm template`,
and a local `kind` smoke test.** It has never been installed against a
real cloud cluster.

## Validating

```bash
helm lint helm/konsole-ai
helm template konsole-ai helm/konsole-ai
helm template konsole-ai helm/konsole-ai --set ollama.gpu.enabled=true --set ingress.enabled=true
```

These are exactly what the `iac-validate` CI job runs on every push/PR.

For an actual cluster smoke test (builds local images, spins up a `kind`
cluster, installs the chart, reports pod status, then tears down):

```bash
make kind-smoke-test
make kind-smoke-test-clean
```

## Design notes

- **`api` runs a single, fixed replica -- there is no `api` HorizontalPodAutoscaler
  in this chart at all.** This isn't an oversight: `api`'s FAISS indexes
  (content + ingestion log) and the SQLite LLM trace store (ADR-0015) are
  local files on one PVC (`api.persistence`, mounted at `/app/data`,
  matching `docker-compose.yml`'s `api_data:/app/data` volume exactly). A
  second `api` pod would mean two processes writing the same files
  concurrently, which is unsafe for both FAISS and SQLite-on-a-shared-volume.
  Scaling `api` for real would require moving those stores off local disk
  first -- out of scope here.
- **`ui` is the only component that safely autoscales** (`ui.autoscaling`,
  off by default) -- it's a stateless HTTP client to `api`
  (`ui/app.py` + `ui/api_client.py`, ADR-0010) with no local state.
- **`ollama` is a StatefulSet, not a bare Deployment+PVC** -- stable
  identity plus a `volumeClaimTemplate` for the pulled-model volume
  (`ollama.persistence`, 50Gi default), mirroring the `ollama_data` named
  volume in `docker-compose.yml`.
- **`ollama.gpu.enabled`** (default `false`) mirrors `docker-compose.yml`'s
  commented-out-by-default GPU block for the `ollama` service, and
  Terraform's `enable_gpu_node_group` toggle. When enabled, the `ollama`
  pod gets a toleration + `nodeSelector` for
  `ollama.gpu.taintKey=ollama.gpu.taintValue` (default
  `nvidia.com/gpu=true`) and a `nvidia.com/gpu` resource limit
  (`ollama.gpu.resourceLimit`, NVIDIA device-plugin convention). **These
  literals must stay identical to `terraform/variables.tf`'s
  `gpu_taint_key` / `gpu_taint_value`** -- the one contract shared between
  this chart and the Terraform config, since Terraform never installs
  this chart itself.
- **`secrets.apiKeys`** defaults to `'["dev-local-key"]'`, matching
  `Settings.API_KEYS`'/`.env.example`'s existing dev default exactly.
  **Override this for any real deployment** -- same warning that default
  carries everywhere else in this project. It's injected as a plain
  Kubernetes `Secret` (`stringData`), no external secrets-manager
  integration -- this project has never used more than plain env vars for
  secrets.
- **No `jaeger`/`prometheus`/`grafana` templates in this chart (v1 scope)**
  -- `api.env.TRACING_ENABLED` / `METRICS_ENABLED` default `false`, same
  as `docker-compose.yml` without the `observability` profile (ADR-0011).
  Adding those containers to this chart is a listed revisit trigger in
  ADR-0017, not built yet.
- **`ingress.enabled`** defaults to `false`. When enabled, routes `/api` to
  the `api` Service and `/` to the `ui` Service through
  `ingress.className` (default `nginx` -- assumes an ingress controller is
  already installed on the cluster; this chart doesn't install one).

## Values

See [`values.yaml`](values.yaml) -- every non-secret field maps 1:1 to a
`docker-compose.yml` environment entry or a `backend/config/settings.py`
`Settings` field, with an inline comment wherever the mapping isn't
obvious.
