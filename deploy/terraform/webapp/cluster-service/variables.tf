variable "namespace" {
  type        = string
  description = "Espacio de nombres a utilizar para la tarea"
}

variable "name" {
  type        = string
  description = "Nombre a utilizar para la tarea"
}

variable "image_uri" {
  type        = string
  description = "URI de la imagen a utilizar para la tarea"
  validation {
    condition     = regex("^(?:(?P<registry>.*)/)?(?P<repository>[^/]+)/(?P<image_name>[^:]+)(?::(?P<label>.*))?$", var.image_uri) != null
    error_message = "URI de imagen inválida"
  }
}

variable "port" {
  type        = number
  description = "Puerto a utilizar para la tarea"
  default     = 8000
}

variable "base_container_definition" {
  type        = any
  description = "Definición base del contenedor a utilizar. Se fusionará con la definición de contenedor por defecto"
  default     = {}
}

variable "extra_container_definitions" {
  type        = list(any)
  description = "Definiciones de contenedor adicionales para agregar a la definición de tarea. Las definiciones se fusionarán con la definición de contenedor por defecto."
  default     = []
}

variable "subnet_ids" {
  type        = list(string)
  description = "IDs de las subredes a utilizar para la tarea"

  validation {
    condition     = length(var.subnet_ids) > 0
    error_message = "Se requiere al menos una subred"
  }
}

variable "task_execution_role_arn" {
  type        = string
  description = "ARN del rol de ejecución de la tarea"
}
variable "task_role_policy_arns" {
  type        = map(string)
  description = "Mapa de nombres de políticas a ARNs para adjuntar al rol de la tarea"
  default     = {}
}

variable "listener_arn" {
  type        = string
  description = "ARN del listener HTTPS del ALB para crear la regla del listener"
  default     = null
}

variable "listener_rule_priority" {
  type        = number
  description = "Prioridad de la regla del listener (debe ser única por listener)"
  default     = 10
}

variable "alb_security_group_id" {
  type        = string
  description = "ID del grupo de seguridad del ALB para permitir tráfico desde el ALB hacia las tareas"
  default     = null
}

variable "path_patterns" {
  type        = list(string)
  description = "Patrón de ruta a utilizar para la regla del listener del balanceador de carga"
  default     = ["/*"]
}

variable "enable_cognito_auth" {
  type        = bool
  description = "Habilitar autenticación de Cognito para este servicio"
  default     = false
}

variable "cognito_user_pool_arn" {
  type        = string
  description = "ARN del User Pool de Cognito (requerido si enable_cognito_auth es true)"
  default     = null
}

variable "cognito_user_pool_client_id" {
  type        = string
  description = "ID del cliente de Cognito (requerido si enable_cognito_auth es true)"
  default     = null
}

variable "cognito_user_pool_domain" {
  type        = string
  description = "Dominio del User Pool de Cognito (requerido si enable_cognito_auth es true)"
  default     = null
}

variable "repository_credentials_secret_arn" {
  type        = string
  description = "ARN del secreto de credenciales del repositorio"
  default     = null
}

variable "health_check_path" {
  type        = string
  description = "Ruta de salud del endpoint de la tarea"
  default     = "/"
}
