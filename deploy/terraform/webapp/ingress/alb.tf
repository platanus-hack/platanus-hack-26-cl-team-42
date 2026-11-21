########################
# Ingress
########################
resource "aws_lb" "this" {
  name               = var.namespace
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.ingress.id]
  subnets            = var.subnet_ids
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.this.arn
  port              = 80
  protocol          = "HTTP"
  default_action {
    type = "redirect"
    redirect {
      port        = "443"
      protocol    = "HTTPS"
      status_code = "HTTP_301"
    }
  }
}

resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.this.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-2016-08"
  certificate_arn   = module.acm.acm_certificate_arn

  default_action {
    type = "fixed-response"

    fixed_response {
      content_type = "text/plain"
      message_body = "Modo de Mantenimiento"
      status_code  = "200"
    }
  }
}

########################
# Security Groups
########################
resource "aws_security_group" "ingress" {
  description = "Permite trafico HTTP y HTTPS desde internet hacia el ALB"
  vpc_id      = var.vpc_id
  tags        = { Name = "${var.namespace}-ingress" }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_vpc_security_group_ingress_rule" "ingress_allow_all" {
  for_each          = toset(["80", "443"])
  security_group_id = aws_security_group.ingress.id

  from_port   = each.value
  to_port     = each.value
  ip_protocol = "tcp"
  cidr_ipv4   = "0.0.0.0/0"

  tags = {
    Name = "${var.namespace}-allow-public-${each.value}"
  }
}

resource "aws_vpc_security_group_egress_rule" "ingress_allow_all" {
  security_group_id = aws_security_group.ingress.id

  ip_protocol = "-1"
  cidr_ipv4   = "0.0.0.0/0"

  tags = {
    Name = "${var.namespace}-allow-all"
  }
}
