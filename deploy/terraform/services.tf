#######################
# Servicios
#######################
locals {
  services_with_db_access = {
    # Agrega aquí los servicios que necesitan acceso a la base de datos
    httpbin = module.service-httpbin,
  }


  # Declara los repositorios que se esperan en el image lock
  imagelock_repositories = [
    "kennethreitz/httpbin",
  ]
}

#########################################
# Services
#   * Agrega tus servicios aquí
#   * Prefiere el módulo ./webapp/custer-service.
#   * Nombra tus servicios como "service-<name>"
#########################################
module "service-httpbin" {
  source = "./webapp/cluster-service"

  namespace = local.project.namespace
  name      = "httpbin"

  # image_uri = module.images["kennethreitz/httpbin"].image_uri  # URI de imagen desde el módulo de imágenes
  image_uri = "kennethreitz/httpbin:latest"

  base_container_definition = {
    environment = [
      # local.sentry_envvars["backend"].ENVIRONMENT,
      # local.sentry_envvars["backend"].DSN,
      { name = "MEDIA_URL", value = "https://${module.media.domain_name}/" },
      { name = "MEDIA_BUCKET_NAME", value = module.media.bucket_name },
      { name = "DATABASE_URL", value = module.db.database_url },
    ]
  }

  task_execution_role_arn = module.cluster.ecs_task_execution_role_arn

  subnet_ids = module.network.private_subnet_ids

  listener_arn          = module.ingress.https_listener_arn
  port                  = 80
  alb_security_group_id = module.ingress.alb_security_group_id

  enable_cognito_auth         = true
  cognito_user_pool_arn       = module.auth.user_pool_arn
  cognito_user_pool_client_id = module.auth.alb_user_pool_client_id
  cognito_user_pool_domain    = module.auth.user_pool_domain

  depends_on = [
    module.auth,
    module.ingress,
    module.cluster,
  ]
}
