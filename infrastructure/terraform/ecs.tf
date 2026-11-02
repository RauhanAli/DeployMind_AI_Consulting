locals {
  name = "deploymind-${var.environment}"
  services = {
    api       = { port = 8000, cpu = 512, memory = 1024, count = var.api_desired_count, health = "/health", public = true }
    web       = { port = 3000, cpu = 256, memory = 512, count = 2, health = "/", public = true }
    worker    = { port = 0, cpu = 512, memory = 1024, count = 1, health = "", public = false }
    assistant = { port = 8080, cpu = 256, memory = 512, count = var.environment == "production" ? 2 : 1, health = "/health", public = true }
  }
  redis_url = "rediss://${aws_elasticache_replication_group.redis.primary_endpoint_address}:6379"
  common_env = [
    { name = "APP_ENV", value = var.environment == "production" ? "production" : "staging" },
    { name = "REDIS_URL", value = "${local.redis_url}/0" },
    { name = "CELERY_BROKER_URL", value = "${local.redis_url}/1" },
    { name = "CELERY_RESULT_BACKEND", value = "${local.redis_url}/2" },
    { name = "STORAGE_BACKEND", value = "s3" },
    { name = "S3_BUCKET", value = aws_s3_bucket.documents.bucket },
    { name = "S3_REGION", value = var.region },
    { name = "COOKIE_SECURE", value = "true" },
    { name = "DEPLOY_ADAPTER", value = "aws_ecs" },
    { name = "AWS_ECS_CLUSTER", value = aws_ecs_cluster.this.name },
    { name = "AWS_ECR_REPOSITORY", value = aws_ecr_repository.repo["assistant"].repository_url },
    { name = "OTEL_ENABLED", value = "true" },
  ]
  secret_keys = ["DATABASE_URL", "JWT_SECRET", "SECRETS_ENCRYPTION_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"]
}

resource "aws_ecr_repository" "repo" {
  for_each             = toset(["api", "worker", "web", "assistant"])
  name                 = "deploymind-${each.key}"
  image_tag_mutability = "IMMUTABLE"
  image_scanning_configuration { scan_on_push = true }
  encryption_configuration { encryption_type = "AES256" }
}

resource "aws_ecs_cluster" "this" {
  name = local.name
  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_cloudwatch_log_group" "svc" {
  for_each          = local.services
  name              = "/ecs/${local.name}/${each.key}"
  retention_in_days = 30
}

data "aws_iam_policy_document" "ecs_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "execution" {
  name               = "${local.name}-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

resource "aws_iam_role_policy_attachment" "execution" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "execution_secrets" {
  role = aws_iam_role.execution.id
  policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Action = ["secretsmanager:GetSecretValue"], Resource = [aws_secretsmanager_secret.app.arn] }]
  })
}

resource "aws_iam_role" "task" {
  name               = "${local.name}-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

resource "aws_iam_role_policy" "task" {
  role = aws_iam_role.task.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"], Resource = ["${aws_s3_bucket.documents.arn}/*"] },
      # The worker's aws_ecs deployment adapter updates the assistant service only.
      { Effect = "Allow", Action = ["ecs:DescribeServices", "ecs:UpdateService", "ecs:DescribeTaskDefinition", "ecs:RegisterTaskDefinition"], Resource = ["*"] },
      { Effect = "Allow", Action = ["iam:PassRole"], Resource = [aws_iam_role.execution.arn, aws_iam_role.task.arn] },
    ]
  })
}

resource "aws_ecs_task_definition" "svc" {
  for_each                 = local.services
  family                   = "${local.name}-${each.key}"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = each.value.cpu
  memory                   = each.value.memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn
  container_definitions = jsonencode([{
    name         = each.key
    image        = "${aws_ecr_repository.repo[each.key].repository_url}:${var.image_tags[each.key]}"
    essential    = true
    portMappings = each.value.port > 0 ? [{ containerPort = each.value.port }] : []
    environment  = each.key == "assistant" ? [] : local.common_env
    secrets      = each.key == "assistant" ? [] : [for k in local.secret_keys : { name = k, valueFrom = "${aws_secretsmanager_secret.app.arn}:${k}::" }]
    logConfiguration = {
      logDriver = "awslogs"
      options   = { awslogs-group = aws_cloudwatch_log_group.svc[each.key].name, awslogs-region = var.region, awslogs-stream-prefix = each.key }
    }
  }])
}

resource "aws_ecs_service" "svc" {
  for_each        = local.services
  name            = "${local.name}-${each.key}"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.svc[each.key].arn
  desired_count   = each.value.count
  launch_type     = "FARGATE"
  network_configuration {
    subnets         = module.vpc.private_subnets
    security_groups = [aws_security_group.services.id]
  }
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }
  dynamic "load_balancer" {
    for_each = each.value.public ? [1] : []
    content {
      target_group_arn = aws_lb_target_group.svc[each.key].arn
      container_name   = each.key
      container_port   = each.value.port
    }
  }
  lifecycle { ignore_changes = [task_definition] } # releases are rolled by the deploy workflow / adapter
}
