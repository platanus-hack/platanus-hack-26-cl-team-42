variable "namespace" {
  description = "Prefijo utilizado para nombrar recursos."
  type        = string
}

variable "vpc_id" {
  description = "ID de la VPC donde se desplegarán los recursos."
  type        = string
}
