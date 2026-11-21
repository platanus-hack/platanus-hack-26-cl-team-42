output "security_group_id" {
  description = "ID del grupo de seguridad para el servicio"
  value       = aws_security_group.this.id
}
