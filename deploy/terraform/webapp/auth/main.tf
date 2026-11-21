resource "aws_cognito_user_pool" "this" {
  name                     = var.namespace
  auto_verified_attributes = ["email"]

  password_policy {
    minimum_length    = 8
    require_lowercase = true
    require_uppercase = true
    require_numbers   = true
    require_symbols   = false
  }

  #{% raw %}
  verification_message_template {
    default_email_option = "CONFIRM_WITH_LINK"
    email_message        = file("${path.module}/html/verification_email.html")
    email_subject        = "Por favor valide su correo electrónico"
    sms_message          = "Su código de verificación es {####}"
  }

  admin_create_user_config {
    allow_admin_create_user_only = true
    invite_message_template {
      email_message = file("${path.module}/html/invite_email.html")
      email_subject = "Bienvenido"
      sms_message   = "Bienvenido Usuario: {username}, Contraseña temporal: {####}. Por favor inicie sesión y cambie su contraseña."
    }
  }
  #{% endraw %}
}

resource "aws_cognito_user_pool_domain" "this" {
  domain       = var.user_pool_domain
  user_pool_id = aws_cognito_user_pool.this.id

  managed_login_version = 2
}

########################
# Cliente para Integración con ALB
########################
resource "aws_cognito_user_pool_client" "alb" {
  count        = var.alb_domain_name != null ? 1 : 0
  name         = "${var.namespace}-alb"
  user_pool_id = aws_cognito_user_pool.this.id

  # Genera un secreto de cliente - requerido para autenticación con ALB
  generate_secret = true

  allowed_oauth_flows = [
    "code"
  ]
  allowed_oauth_scopes = [
    "openid",
    "email",
    "profile"
  ]
  allowed_oauth_flows_user_pool_client = true

  callback_urls = [
    "https://${var.alb_domain_name}/",
    # URL de callback de Cognito
    "https://${var.alb_domain_name}/oauth2/idpresponse",
  ]

  logout_urls = [
    "https://${var.alb_domain_name}/",
    "https://${var.alb_domain_name}/logout",
  ]

  # Configuración de validez de tokens
  refresh_token_validity = 30
  access_token_validity  = 1
  id_token_validity      = 1

  explicit_auth_flows = [
    "ALLOW_USER_PASSWORD_AUTH",
    "ALLOW_USER_SRP_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH"
  ]

  # Prevenir errores de existencia de usuario
  prevent_user_existence_errors = "ENABLED"

  # Configuración de tokens
  token_validity_units {
    refresh_token = "days"
    access_token  = "hours"
    id_token      = "hours"
  }
}
