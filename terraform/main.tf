################################################################################
# VPC
################################################################################

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 6.0"

  name = var.cluster_name
  cidr = var.vpc_cidr

  azs             = var.azs
  private_subnets = [for k, az in var.azs : cidrsubnet(var.vpc_cidr, 4, k)]
  public_subnets  = [for k, az in var.azs : cidrsubnet(var.vpc_cidr, 8, k + 48)]

  # One NAT gateway, not one per AZ -- cost discipline over HA, same
  # reasoning as the rest of this project's zero-live-cost stance (see
  # docs/adr/0014). A real production cluster would set this false.
  enable_nat_gateway = true
  single_nat_gateway = true

  # Required so EKS can auto-discover subnets for load balancers.
  public_subnet_tags = {
    "kubernetes.io/role/elb" = 1
  }
  private_subnet_tags = {
    "kubernetes.io/role/internal-elb" = 1
  }

  tags = var.tags
}

################################################################################
# EKS
################################################################################

module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 21.0"

  name               = var.cluster_name
  kubernetes_version = var.cluster_version

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets

  # Reachable from a workstation for `kubectl`/`helm install`, not just from
  # inside the VPC -- this is a single-cluster demo target, not a
  # production multi-account setup with a bastion/VPN.
  endpoint_public_access = true

  # Grants the identity running `terraform apply` cluster-admin via an EKS
  # access entry -- the current recommended replacement for hand-editing
  # the aws-auth ConfigMap.
  enable_cluster_creator_admin_permissions = true

  # Creates the OIDC provider so pods can assume IAM roles (IRSA) if this
  # cluster ever needs to reach other AWS services -- not currently used by
  # the Helm chart (which has no AWS-service-calling code), but cheap to
  # have available.
  enable_irsa = true

  addons = {
    coredns = {}
    eks-pod-identity-agent = {
      before_compute = true
    }
    kube-proxy = {}
    vpc-cni = {
      before_compute = true
    }
  }

  # The GPU node group is included as a conditional map *key* via `merge`,
  # not via a resource-level `count` -- `eks_managed_node_groups` is a map
  # argument this module consumes internally, not a resource this root
  # module owns directly, so `count`/`for_each` on the module block itself
  # isn't the right tool here.
  eks_managed_node_groups = merge(
    {
      general = {
        instance_types = var.node_instance_types
        ami_type       = "AL2023_x86_64_STANDARD"
        min_size       = var.node_group_min_size
        max_size       = var.node_group_max_size
        desired_size   = var.node_group_desired_size
      }
    },
    var.enable_gpu_node_group ? {
      gpu = {
        instance_types = [var.gpu_instance_type]
        ami_type       = "AL2023_x86_64_NVIDIA"
        min_size       = var.gpu_node_min_size
        max_size       = var.gpu_node_max_size
        desired_size   = var.gpu_node_desired_size

        taints = {
          gpu = {
            key    = var.gpu_taint_key
            value  = var.gpu_taint_value
            effect = "NO_SCHEDULE"
          }
        }
        labels = {
          (var.gpu_taint_key) = var.gpu_taint_value
        }
      }
    } : {}
  )

  tags = var.tags
}
