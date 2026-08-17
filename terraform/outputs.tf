output "cluster_name" {
  description = "Name of the EKS cluster."
  value       = module.eks.cluster_name
}

output "cluster_endpoint" {
  description = "Endpoint for the Kubernetes API server."
  value       = module.eks.cluster_endpoint
}

output "cluster_certificate_authority_data" {
  description = "Base64-encoded certificate data required to communicate with the cluster."
  value       = module.eks.cluster_certificate_authority_data
  sensitive   = true
}

output "region" {
  description = "AWS region the cluster was provisioned in."
  value       = var.aws_region
}

output "vpc_id" {
  description = "ID of the VPC the cluster runs in."
  value       = module.vpc.vpc_id
}

output "configure_kubectl" {
  description = "Command to configure kubectl against this cluster. Terraform never invokes Helm itself (see docs/adr/0017) -- this is the manual next step, then `helm install konsole-ai helm/konsole-ai`."
  value       = "aws eks update-kubeconfig --region ${var.aws_region} --name ${module.eks.cluster_name}"
}
