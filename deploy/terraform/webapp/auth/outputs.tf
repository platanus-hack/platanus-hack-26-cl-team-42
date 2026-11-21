output "user_pool_arn" {
  value = aws_cognito_user_pool.this.arn
}

output "user_pool_id" {
  value = aws_cognito_user_pool.this.id
}

output "user_pool_domain" {
  value = aws_cognito_user_pool_domain.this.domain
}

output "alb_user_pool_client_id" {
  value = length(aws_cognito_user_pool_client.alb) > 0 ? aws_cognito_user_pool_client.alb[0].id : null
}
