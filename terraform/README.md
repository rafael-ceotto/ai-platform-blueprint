# Terraform — AWS EKS (validate-only)

Provisions a VPC + EKS cluster (control plane, IRSA/OIDC provider, a
default CPU-only managed node group, and an optional scale-to-zero
GPU-backed node group) on AWS, using the community
[`terraform-aws-modules/vpc`](https://registry.terraform.io/modules/terraform-aws-modules/vpc/aws/latest)
and [`terraform-aws-modules/eks`](https://registry.terraform.io/modules/terraform-aws-modules/eks/aws/latest)
modules rather than hand-rolled resources.

**This configuration has never been, and is not intended to be, run with
`terraform apply` against a real AWS account.** See
[`docs/adr/0017-terraform-aws-eks-and-helm-chart.md`](../docs/adr/0017-terraform-aws-eks-and-helm-chart.md)
and [`docs/adr/0014-kubernetes-and-cloud-deployment.md`](../docs/adr/0014-kubernetes-and-cloud-deployment.md)
for why: a GPU node kept running costs roughly $300-800/month, which isn't
something to leave on between interview cycles for a portfolio project
with no real traffic.

The only things ever actually run here are:

```bash
terraform fmt -check -recursive
terraform init -backend=false
terraform validate
```

None of those need AWS credentials. This is also exactly what the
`iac-validate` CI job runs on every push/PR (see `.github/workflows/ci.yml`).

## Why no `backend` block

There's no S3 bucket or DynamoDB lock table for this project, so state
stays local (and untracked -- see `.gitignore`). A real deployment would
add:

```hcl
terraform {
  backend "s3" {}
}
```

configured via `terraform init -backend-config=...` at init time, rather
than faking a backend config for a bucket that doesn't exist.

## The GPU node group toggle

`enable_gpu_node_group` (default `false`) mirrors the commented-out-by-default
GPU block on the `ollama` service in the repo root's `docker-compose.yml`.
When `true`, a second EKS managed node group is added
(`gpu_instance_type`, default `g4dn.xlarge`, scaled 0-1 by default) with a
`nvidia.com/gpu=true:NoSchedule` taint and matching label.

**That taint key/value is a contract with the Helm chart**:
`helm/konsole-ai/values.yaml`'s `ollama.gpu.taintKey` / `ollama.gpu.taintValue`
must stay set to the same literals as this configuration's
`gpu_taint_key` / `gpu_taint_value` variables, since this Terraform never
deploys the Helm chart itself -- the two artifacts are validated
independently (see the "Two independently-reviewable artifacts" note in
ADR-0017) and only agree on this one string pair.

## If this were ever actually applied

1. `cp terraform.tfvars.example terraform.tfvars` and adjust.
2. Add a real `backend "s3" {}` block and `terraform init -backend-config=...`.
3. `terraform plan` / `terraform apply` with real AWS credentials.
4. `$(terraform output -raw configure_kubectl)` to point `kubectl` at the
   new cluster.
5. `helm install konsole-ai ../helm/konsole-ai` -- Terraform stops at
   infrastructure; deploying the app is a separate, manual step (see
   `helm/konsole-ai/README.md`).
