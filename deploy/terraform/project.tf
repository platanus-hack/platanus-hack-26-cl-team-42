locals {
  project_slug        = "multiplayer-medico"
  project_base_domain = "multiplayer-medico.example.cloud"

  project = {
    name      = local.project_slug
    namespace = "${var.environment}-${local.project_slug}"
    dns = {
      domain_name = var.environment == "prd" ? local.project_base_domain : "${var.environment}.${local.project_base_domain}"
    }
    sentry = {}
  }
}
