variable "namespace" {
  description = "Espacio de nombres a utilizar para el ingress"
  type        = string
}

variable "zone_id" {
  description = "ID de la zona DNS a utilizar para el ingress"
  type        = string
}

variable "domain_name" {
  description = "Nombre de dominio a utilizar para el ingress"
  type        = string
}

variable "vpc_id" {
  description = "ID de la VPC a utilizar para el ingress"
  type        = string
}

variable "subnet_ids" {
  description = "IDs de las subredes a utilizar para el ingress"
  type        = list(string)
}
