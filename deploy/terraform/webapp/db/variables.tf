variable "namespace" {
  description = "Espacio de nombres para los recursos de base de datos."
  type        = string
}

variable "subnet_ids" {
  description = "Lista de IDs de subredes donde desplegar la base de datos."
  type        = list(string)
}

variable "trusted_security_groups" {
  description = "Mapa de nombres de grupos de seguridad a IDs que tienen permitido acceder a la base de datos. { label => security_group_id}"
  type        = map(string)
  default     = {}
}

variable "aurora_instance_type" {
  description = "Tipo de instancia a utilizar para la base de datos."
  type        = string
  default     = "db.t4g.medium"
}
