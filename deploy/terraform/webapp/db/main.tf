locals {
  master_username = "postgres"
  app_username    = "app"
  app_password    = "app"
  app_database    = "app"
}

resource "random_password" "app_password" {
  length  = 16
  special = true
}

##################################
# Cluster
##################################
resource "aws_rds_cluster" "aurora" {
  cluster_identifier     = "${var.namespace}-aurora-cluster"
  engine                 = "aurora-postgresql"
  engine_mode            = "provisioned"
  master_username        = local.master_username
  master_password        = random_password.master_password.result
  db_subnet_group_name   = aws_db_subnet_group.this.name
  vpc_security_group_ids = [aws_security_group.this.id]
  skip_final_snapshot    = true
  enable_http_endpoint   = true

  serverlessv2_scaling_configuration {
    min_capacity = 0.5
    max_capacity = 2
  }
  tags = { Name = "${var.namespace}-aurora-cluster" }
}

resource "aws_rds_cluster_instance" "writer" {
  identifier         = "${var.namespace}-aurora-writer"
  cluster_identifier = aws_rds_cluster.aurora.id
  instance_class     = "db.serverless"
  engine             = aws_rds_cluster.aurora.engine

  tags = { Name = "${var.namespace}-aurora-writer" }
}


##################################
# Networking
##################################
resource "aws_db_subnet_group" "this" {
  name       = "${var.namespace}-db-subnet-group"
  subnet_ids = var.subnet_ids
  tags       = { Name = "${var.namespace}-db-subnet-group" }
}

resource "aws_vpc_security_group_ingress_rule" "postgres" {
  for_each          = var.trusted_security_groups
  security_group_id = aws_security_group.this.id

  referenced_security_group_id = each.value

  ip_protocol = "tcp"
  from_port   = 5432
  to_port     = 5432

  tags = { Name = "${var.namespace}-sg-db-${each.key}" }
}

resource "aws_security_group" "this" {
  name        = "${var.namespace}-db"
  description = "${var.namespace} DB"
  vpc_id      = data.aws_subnet.first.vpc_id
  tags        = { Name = "${var.namespace}-db" }
}

data "aws_subnet" "first" {
  id = var.subnet_ids[0]
}

##################################
# Master Password
##################################
resource "aws_secretsmanager_secret" "master_password" {
  name        = "${var.namespace}-database-credentials"
  description = "Credenciales para Aurora PostgreSQL"
}

resource "aws_secretsmanager_secret_version" "master_password" {
  secret_id = aws_secretsmanager_secret.master_password.id
  secret_string = jsonencode({
    username = local.master_username
    password = random_password.master_password.result
  })
}

resource "random_password" "master_password" {
  length  = 16
  special = true
}


##################################
# Permitir acceso a RDS Data API
##################################
resource "aws_iam_policy" "rds_data_api_policy" {
  name = "${var.namespace}-rds-data-api-policy"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "rds-data:BatchExecuteStatement",
          "rds-data:BeginTransaction",
          "rds-data:CommitTransaction",
          "rds-data:ExecuteStatement",
          "rds-data:RollbackTransaction"
        ]
        Resource = aws_rds_cluster.aurora.arn
      },
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = aws_secretsmanager_secret.master_password.arn
      }
    ]
  })
}
