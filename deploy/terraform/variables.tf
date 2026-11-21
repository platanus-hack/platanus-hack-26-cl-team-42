########################
# AWS
########################
variable "aws_account_id" {
  description = "ID de la cuenta AWS"
  type        = string
  default     = ""
}

variable "aws_region" {
  description = "Región de AWS"
  type        = string
  default     = "us-east-2"
}

########################
# Entorno
########################
variable "environment" {
  description = "Entorno de despliegue. Usar nombres convencionales: prd, stg, tst."
  type        = string
  default     = "tst"

  validation {
    condition     = contains(["prd", "stg", "tst"], var.environment)
    error_message = "Usar nombres de entornos conocidos (prd, stg, tst)"
  }
}


########################
# Credenciales GHCR
#
# Configúralas en el variable set de tu organización
# en Terraform Cloud (o vía TF_VAR_* / -var).
########################
variable "GITOPS_USER_USERNAME" {
  description = "Nombre de usuario para el usuario de GitOps"
  type        = string
  default     = null
}

variable "GITOPS_USER_PAT" {
  description = "Token de Acceso Personal para el usuario de GitOps"
  type        = string
  default     = null
  sensitive   = true
}

