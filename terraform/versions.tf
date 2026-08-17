terraform {
  required_version = ">= 1.9.0"

  required_providers {
    # >= 6.59 is the floor required by terraform-aws-modules/eks/aws ~> 21.0;
    # capped below 7.0 so a future major bump is a deliberate, reviewed step.
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.59.0, < 7.0.0"
    }
  }

  # No `backend` block: this project never applies against a real AWS
  # account (see terraform/README.md and docs/adr/0017), so there is no S3
  # bucket/DynamoDB lock table to point a remote backend at. State stays
  # local (and untracked, see .gitignore). A real deployment would add
  # `backend "s3" {}` here and supply the bucket/key/region via
  # `terraform init -backend-config=...` at init time.
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = var.tags
  }
}
