output "bucket_name" {
  description = "Nombre del bucket de media"
  value       = aws_s3_bucket.media.bucket
}

output "domain_name" {
  description = "Dominio del bucket de media"
  value       = aws_s3_bucket.media.bucket_regional_domain_name
}

output "access_policy_arn" {
  description = "ARN de la política de acceso al bucket de media"
  value       = aws_iam_policy.media.arn
}