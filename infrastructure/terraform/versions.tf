terraform {
  required_version = ">= 1.6"
  required_providers {
    aws    = { source = "hashicorp/aws", version = "~> 5.70" }
    random = { source = "hashicorp/random", version = "~> 3.6" }
  }
  # Configure remote state per environment, e.g.:
  # backend "s3" { bucket = "deploymind-tfstate" key = "prod/terraform.tfstate" region = "eu-west-2" dynamodb_table = "tf-locks" encrypt = true }
}

provider "aws" {
  region = var.region
  default_tags { tags = { Project = "deploymind", Environment = var.environment, ManagedBy = "terraform" } }
}
