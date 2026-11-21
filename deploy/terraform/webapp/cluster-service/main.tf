#########################################
# Configura un servicio alojado en ECS
# en una ruta específica del ALB de ingress
#########################################

#########################################################
# Nombres convencionales para búsqueda y nomenclatura de recursos
#########################################################
locals {
  alb_name         = var.namespace
  ecs_cluster_name = "${var.namespace}-ecs-cluster"
  log_group_name   = "/ecs/${var.namespace}"
  task_name        = "${var.namespace}-${var.name}"
  image_uri_match  = regex("^(?:(?P<registry>.*)/)?(?P<repository>[^/]+)/(?P<image_name>[^:]+)(?::(?P<label>.*))?$", var.image_uri)
}


############################
# Configuración de Ingress
############################
resource "aws_lb_target_group" "this" {
  count = var.listener_arn != null ? 1 : 0

  name_prefix = substr(local.task_name, 0, 6)
  port        = var.port
  protocol    = "HTTP"
  vpc_id      = data.aws_subnet.first.vpc_id
  target_type = "ip"

  health_check {
    path                = var.health_check_path
    protocol            = "HTTP"
    matcher             = "200-399"
    interval            = 10
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 2
  }

  deregistration_delay = 5

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_lb_listener_rule" "this" {
  count = var.listener_arn != null ? 1 : 0

  listener_arn = var.listener_arn
  priority     = var.listener_rule_priority

  dynamic "action" {
    for_each = var.enable_cognito_auth ? [1] : []
    content {
      type  = "authenticate-cognito"
      order = 1

      authenticate_cognito {
        user_pool_arn       = var.cognito_user_pool_arn
        user_pool_client_id = var.cognito_user_pool_client_id
        user_pool_domain    = var.cognito_user_pool_domain

        on_unauthenticated_request = "authenticate"
        scope                      = "openid email profile"
        session_cookie_name        = "AWSELBAuthSessionCookie"
        session_timeout            = 3600
      }
    }
  }

  action {
    type             = "forward"
    order            = var.enable_cognito_auth ? 2 : 1
    target_group_arn = aws_lb_target_group.this[0].arn
  }

  condition {
    path_pattern {
      values = var.path_patterns
    }
  }
}

############################
# Servicio
############################
resource "aws_ecs_service" "this" {
  name            = var.name
  cluster         = data.aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.this.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  # Ensure listener rule attaches target group to ALB before creating service
  depends_on = [aws_lb_listener_rule.this]

  network_configuration {
    subnets          = var.subnet_ids
    security_groups  = [aws_security_group.this.id]
    assign_public_ip = false
  }

  dynamic "load_balancer" {
    for_each = var.listener_arn != null ? [1] : []

    content {
      target_group_arn = aws_lb_target_group.this[0].arn
      container_name   = var.name
      container_port   = var.port
    }
  }

  service_connect_configuration {
    enabled = true

    service {
      port_name = var.name

      client_alias {
        port     = var.port
        dns_name = var.name
      }
    }
  }
  deployment_minimum_healthy_percent = 50
  deployment_maximum_percent         = 200
}

data "aws_ecs_cluster" "this" {
  cluster_name = local.ecs_cluster_name
}


############################
# Grupo de Seguridad
############################
resource "aws_security_group" "this" {
  name_prefix = "${local.task_name}-"
  description = local.task_name
  vpc_id      = data.aws_subnet.first.vpc_id
  tags        = { Name = local.task_name }

  lifecycle {
    create_before_destroy = true
  }
}

# Allow all outbound traffic (for pulling Docker images and external API calls)
resource "aws_vpc_security_group_egress_rule" "allow_all_outbound" {
  security_group_id = aws_security_group.this.id
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
  tags              = { Name = "${local.task_name}-egress-all" }

  lifecycle {
    create_before_destroy = true
  }
}

# Allow inbound traffic from ALB on the container port
resource "aws_vpc_security_group_ingress_rule" "from_alb" {
  count                        = var.alb_security_group_id != null ? 1 : 0
  security_group_id            = aws_security_group.this.id
  referenced_security_group_id = var.alb_security_group_id
  from_port                    = var.port
  to_port                      = var.port
  ip_protocol                  = "tcp"
  tags                         = { Name = "${local.task_name}-ingress-alb" }

  lifecycle {
    create_before_destroy = true
  }
}

data "aws_subnet" "first" {
  id = var.subnet_ids[0]
}


############################
# Definición de Tarea
############################
resource "aws_ecs_task_definition" "this" {
  family                   = local.task_name
  requires_compatibilities = ["FARGATE"]
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = var.task_execution_role_arn
  task_role_arn            = aws_iam_role.task.arn
  network_mode             = "awsvpc"

  container_definitions = jsonencode(concat(
    [local.base_container_definition],
    var.extra_container_definitions
  ))
}

resource "aws_iam_role" "task" {
  name = "${var.namespace}-ecs-task-${var.name}"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "task" {
  for_each   = var.task_role_policy_arns
  role       = aws_iam_role.task.name
  policy_arn = each.value
}

locals {
  default_container_definition = {
    essential = true

    repositoryCredentials = var.repository_credentials_secret_arn != null ? {
      credentialsParameter = var.repository_credentials_secret_arn
    } : null,

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-region        = data.aws_region.current.region
        awslogs-stream-prefix = var.name
        awslogs-group         = local.log_group_name
      }
    }
  }

  base_container_definition = merge(
    local.default_container_definition,
    {
      name         = var.name
      image        = var.image_uri
      portMappings = [{ containerPort = var.port, name = var.name }]
    },
    var.base_container_definition
  )

  extra_container_definitions = [
    for d in var.extra_container_definitions
    : merge(local.default_container_definition, d)
  ]
}

data "aws_region" "current" {}
