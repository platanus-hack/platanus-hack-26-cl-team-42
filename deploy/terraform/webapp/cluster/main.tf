########################
# ECS Cluster
########################
resource "aws_ecs_cluster" "main" {
  name = "${var.namespace}-ecs-cluster"

  service_connect_defaults {
    namespace = aws_service_discovery_private_dns_namespace.service_connect.arn
  }

  tags = {
    Name = "${var.namespace}-ecs-cluster"
  }
}

resource "aws_service_discovery_private_dns_namespace" "service_connect" {
  name        = var.namespace
  description = "Espacio de nombres de Service Connect para ${var.namespace}"
  vpc         = var.vpc_id
}

##########################
# ECS Task Execution Role
##########################
resource "aws_iam_role" "ecs_task_execution_role" {
  name = "${var.namespace}-ecs-task-execution-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "ecs_task_execution_logs" {
  name = "ecs-task-execution-logs"
  role = aws_iam_role.ecs_task_execution_role.id

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ],
        Resource = "arn:aws:logs:*:*:*"
      }
    ]
  })
}

resource "aws_iam_role_policy" "ecs_task_execution_secrets" {
  for_each = data.aws_secretsmanager_secrets.repository_credentials.arns

  name = "${var.namespace}-ecs-task-execution-secrets"
  role = aws_iam_role.ecs_task_execution_role.name


  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = [each.value]
      }
    ]
  })
}

data "aws_secretsmanager_secrets" "repository_credentials" {
  # Nota: El filtro de nombre hace coincidencia por prefijo
  filter {
    name   = "name"
    values = ["repository-credentials"]
  }
}

########################
# Log Group
########################
resource "aws_cloudwatch_log_group" "this" {
  name              = "/ecs/${var.namespace}"
  retention_in_days = 30
}
