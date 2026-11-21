resource "twingate_remote_network" "vpc" {
  name     = "[${var.prefix}] ${var.name} (VPC Network)"
  location = "AWS"
}

resource "twingate_connector" "vpc_connector" {
  remote_network_id = twingate_remote_network.vpc.id
  name              = "[${var.prefix}] ${var.name} (VPC Connector)"
}

resource "twingate_connector_tokens" "vpc_connector_tokens" {
  connector_id = twingate_connector.vpc_connector.id
}

resource "aws_iam_role" "twingate_task_execution" {
  name = "${var.prefix}-twingate-ecs-task-execution-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "twingate_task_execution_policy" {
  role       = aws_iam_role.twingate_task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role" "twingate_task_role" {
  name = "${var.prefix}-twingate-ecs-task-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "twingate_task_execution_logs" {
  name = "${var.prefix}-twingate-ecs-task-execution-logs"
  role = aws_iam_role.twingate_task_execution.id

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Action = [
          "logs:CreateLogGroup"
        ],
        Resource = "arn:aws:logs:*:*:*"
      }
    ]
  })
}

resource "aws_ecs_task_definition" "twingate_connector" {
  family                   = "${var.prefix}-twingate-connector"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "1024"
  memory                   = "2048"
  execution_role_arn       = aws_iam_role.twingate_task_execution.arn
  task_role_arn            = aws_iam_role.twingate_task_role.arn
  depends_on               = [aws_cloudwatch_log_group.twingate_connector]

  container_definitions = jsonencode([
    {
      name      = "twingate-connector"
      image     = var.twingate_image_uri
      essential = true
      environment = [
        { name = "TWINGATE_ACCESS_TOKEN", value = twingate_connector_tokens.vpc_connector_tokens.access_token },
        { name = "TWINGATE_REFRESH_TOKEN", value = twingate_connector_tokens.vpc_connector_tokens.refresh_token },
        { name = "TWINGATE_NETWORK", value = var.twingate_network },
        { name = "TWINGATE_LABEL_DEPLOYED_BY", value = "terraform-module" }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.twingate_connector.name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "ecs"
        }
      }
    }
  ])
}

resource "aws_ecs_service" "twingate_connector" {
  name            = "twingate-connector"
  cluster         = var.ecs_cluster_arn
  task_definition = aws_ecs_task_definition.twingate_connector.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    # Estos deben ser proporcionados como variables o conectados desde tu módulo de VPC/red
    subnets          = var.subnet_ids
    security_groups  = [aws_security_group.this.id]
    assign_public_ip = false
  }

  deployment_minimum_healthy_percent = 50
  deployment_maximum_percent         = 200
}


resource "aws_cloudwatch_log_group" "twingate_connector" {
  name              = "/ecs/${var.prefix}/twingate-connector"
  retention_in_days = 30
}


resource "aws_security_group" "this" {
  name        = "${var.prefix}-twingate"
  description = "${var.prefix} Twingate"
  vpc_id      = data.aws_subnet.first.vpc_id
  tags        = { Name = "${var.prefix}-twingate" }
}


data "aws_subnet" "first" {
  id = var.subnet_ids[0]
}
