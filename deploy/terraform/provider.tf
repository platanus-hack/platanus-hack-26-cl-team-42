
terraform {
  cloud {
    organization = "example"

    workspaces {
      project = "multiplayer-medico"
      tags    = ["multiplayer-medico"]
    }
  }

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">=6.4.0"
    }
    sentry = {
      source  = "jianyuan/sentry"
      version = "0.14.5"
    }
    random = {
      source  = "hashicorp/random"
      version = ">= 3.0"
    }
  }
}



provider "aws" {
  allowed_account_ids = [var.aws_account_id]
  region              = var.aws_region

  assume_role {
    role_arn = "arn:aws:iam::${var.aws_account_id}:role/terraform-cloud"
  }

  default_tags {
    tags = {
      Environment = var.environment
      Repository  = "git@github.com:example/multiplayer-medico"
      Project     = local.project.name
    }
  }
}

provider "sentry" {}
