variable "namespace" {
  type = string
}

variable "user_pool_domain" {
  type = string
}

variable "alb_domain_name" {
  description = "Nombre de dominio del ALB para configurar los callbacks"
  type        = string
  default     = null
}
