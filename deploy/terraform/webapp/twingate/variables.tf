variable "prefix" {
  description = "Prefijo para los recursos de Twingate"
  type        = string
}

variable "name" {
  description = "Nombre utilizado para los recursos de Twingate"
  type        = string
}

variable "ecs_cluster_arn" {
  description = "ARN del cluster ECS donde se desplegará el conector de Twingate."
  type        = string
}

variable "twingate_image_uri" {
  description = "Imagen Docker a utilizar para el conector de Twingate."
  type        = string
  default     = "twingate/connector:latest"
}

variable "aws_region" {
  description = "Región de AWS para ECS y logs de CloudWatch."
  type        = string
}

variable "subnet_ids" {
  description = "IDs de subredes para el conector de Twingate"
  type        = list(string)
}

variable "twingate_network" {
  description = "Slug de la red Twingate (cuenta) a la que se conecta el connector"
  type        = string
}
