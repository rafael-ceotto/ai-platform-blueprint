variable "aws_region" {
  description = "AWS region to provision the VPC/EKS cluster in."
  type        = string
  default     = "us-east-1"
}

variable "cluster_name" {
  description = "Name of the EKS cluster (also used to derive the VPC name)."
  type        = string
  default     = "konsole-ai"
}

variable "cluster_version" {
  description = "Kubernetes `<major>.<minor>` version for the EKS control plane. Check current AWS-supported versions (https://docs.aws.amazon.com/eks/latest/userguide/kubernetes-versions-standard.html) before applying -- this default is not guaranteed to stay current."
  type        = string
  default     = "1.33"
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC."
  type        = string
  default     = "10.0.0.0/16"
}

variable "azs" {
  description = "Availability zones to spread subnets across. Two is the minimum EKS requires."
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b"]
}

# --- Default (CPU) node group ---

variable "node_instance_types" {
  description = "Instance types for the default, always-on node group. CPU-only -- mirrors docker-compose.yml's commented-out-by-default GPU block for the ollama service."
  type        = list(string)
  default     = ["t3.large"]
}

variable "node_group_min_size" {
  type    = number
  default = 1
}

variable "node_group_max_size" {
  type    = number
  default = 3
}

variable "node_group_desired_size" {
  type    = number
  default = 1
}

# --- Optional GPU node group (Ollama), scale-to-zero, off by default ---
#
# A GPU node kept running costs roughly $300-800/month (see
# docs/adr/0014-kubernetes-and-cloud-deployment.md) -- not something to
# leave on between interview cycles. This toggle exists so the capability
# is provisioned-but-off, matching the ollama service's commented-out GPU
# block in docker-compose.yml.

variable "enable_gpu_node_group" {
  description = "Whether to provision a second, GPU-backed EKS managed node group for Ollama."
  type        = bool
  default     = false
}

variable "gpu_instance_type" {
  description = "Instance type for the optional GPU node group."
  type        = string
  default     = "g4dn.xlarge"
}

variable "gpu_node_min_size" {
  type    = number
  default = 0
}

variable "gpu_node_max_size" {
  type    = number
  default = 1
}

variable "gpu_node_desired_size" {
  type    = number
  default = 0
}

# The taint applied to GPU nodes so only pods that explicitly tolerate it
# get scheduled there. `helm/konsole-ai/values.yaml`'s `ollama.gpu.taintKey`
# / `ollama.gpu.taintValue` must stay set to these same literals -- this is
# the one contract shared between the two artifacts, since Terraform never
# deploys the Helm chart itself. See docs/adr/0017.
variable "gpu_taint_key" {
  type    = string
  default = "nvidia.com/gpu"
}

variable "gpu_taint_value" {
  type    = string
  default = "true"
}

variable "tags" {
  description = "Tags applied to every resource this configuration creates."
  type        = map(string)
  default = {
    Project   = "konsole-ai"
    ManagedBy = "terraform"
  }
}
