#########################################
# Variables de Entorno de Sentry
# - Produce un mapa de nombres de servicio a un mapa de nombres de variables de entorno a valores
#########################################
locals {
  sentry_envvars = {
    for service, sentry_project in local.project.sentry :
    service => {
      DSN         = { name = "SENTRY_DSN", value = data.sentry_key.all[service].dsn.public },
      ENVIRONMENT = { name = "SENTRY_ENVIRONMENT", value = var.environment },
    }
  }
}


data "sentry_key" "all" {
  for_each = local.project.sentry

  organization = "example"
  project      = "${local.project.name}-${each.key}"
}
