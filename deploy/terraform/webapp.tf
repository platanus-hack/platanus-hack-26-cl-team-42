#######################
# Cognito Auth
#######################
module "auth" {
  source = "./webapp/auth"

  namespace        = "core"
  user_pool_domain = local.project.name
  alb_domain_name  = local.project.dns.domain_name
}


#######################
# VPC Network
#######################
module "network" {
  source = "./webapp/network"

  namespace  = local.project.namespace
  cidr_block = "10.0.0.0/16"

}


#######################
# DB
#######################
module "db" {
  source = "./webapp/db"

  namespace = local.project.namespace

  subnet_ids = module.network.private_subnet_ids

  trusted_security_groups = {
    for label, service in local.services_with_db_access : label => service.security_group_id
  }
}


########################
# DNS
########################

resource "aws_route53_zone" "zone" {
  name = local.project_base_domain
}

locals {
  route53_zone_id = aws_route53_zone.zone.zone_id
}


resource "aws_route53_record" "ingress" {
  zone_id = local.route53_zone_id
  name    = local.project.dns.domain_name
  type    = "A"

  alias {
    name                   = module.ingress.alb_dns_name
    zone_id                = module.ingress.alb_zone_id
    evaluate_target_health = true
  }
}



#######################
# Ingress
#######################
module "ingress" {
  source    = "./webapp/ingress"
  namespace = local.project.namespace

  zone_id     = local.route53_zone_id
  domain_name = local.project.dns.domain_name

  vpc_id     = module.network.vpc_id
  subnet_ids = module.network.public_subnet_ids
}



#######################
# Cluster
#######################
module "cluster" {
  source = "./webapp/cluster"

  namespace = local.project.namespace
  vpc_id    = module.network.vpc_id
}

############################
# GHCR Config
############################
resource "aws_secretsmanager_secret" "ghcr_credentials" {
  count = var.GITOPS_USER_USERNAME != null ? 1 : 0
  name  = "repository-credentials/ghcr.io/example"
}


resource "aws_secretsmanager_secret_version" "ghcr_credentials" {
  count     = var.GITOPS_USER_USERNAME != null ? 1 : 0
  secret_id = aws_secretsmanager_secret.ghcr_credentials[0].id
  secret_string = jsonencode({
    username = var.GITOPS_USER_USERNAME
    password = var.GITOPS_USER_PAT
  })
}



#######################
# Storage
#######################
module "media" {
  source = "./webapp/storage"

  domain_name = local.project.dns.domain_name
}


#######################
# Twingate
#######################
module "twingate" {
  source = "./webapp/twingate"

  ecs_cluster_arn  = module.cluster.ecs_cluster_arn
  subnet_ids       = module.network.private_subnet_ids
  aws_region       = var.aws_region
  twingate_network = "example"

  prefix = local.project.namespace
  name   = local.project_slug
}
