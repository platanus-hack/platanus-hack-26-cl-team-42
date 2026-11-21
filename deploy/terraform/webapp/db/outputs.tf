output "rds_cluster_endpoint" {
  value = aws_rds_cluster.aurora.endpoint
}

output "security_group_id" {
  value = aws_security_group.this.id
}

output "database_url" {
  value = "postgresql://${local.app_username}:${local.app_password}@${aws_rds_cluster.aurora.endpoint}/${local.app_database}"
}
