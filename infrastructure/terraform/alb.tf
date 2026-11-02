resource "aws_lb" "this" {
  name                       = "deploymind-${var.environment}"
  load_balancer_type         = "application"
  subnets                    = module.vpc.public_subnets
  security_groups            = [aws_security_group.alb.id]
  drop_invalid_header_fields = true
}

resource "aws_lb_target_group" "svc" {
  for_each    = { for k, v in local.services : k => v if v.public }
  name        = "dm-${var.environment}-${each.key}"
  port        = each.value.port
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = module.vpc.vpc_id
  health_check {
    path    = each.value.health
    matcher = "200"
  }
}

resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.this.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = var.domain_certificate_arn
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.svc["web"].arn
  }
}

resource "aws_lb_listener_rule" "api" {
  listener_arn = aws_lb_listener.https.arn
  priority     = 10
  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.svc["api"].arn
  }
  condition {
    path_pattern { values = ["/api/*", "/docs", "/health", "/metrics"] }
  }
}

resource "aws_lb_listener_rule" "assistant" {
  listener_arn = aws_lb_listener.https.arn
  priority     = 20
  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.svc["assistant"].arn
  }
  condition {
    host_header { values = ["assistant.*"] }
  }
}
