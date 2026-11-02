output "alb_dns_name" { value = aws_lb.this.dns_name }
output "ecs_cluster" { value = aws_ecs_cluster.this.name }
output "ecr_repositories" { value = { for k, r in aws_ecr_repository.repo : k => r.repository_url } }
output "documents_bucket" { value = aws_s3_bucket.documents.bucket }
output "github_deploy_role_arn" { value = aws_iam_role.github_deploy.arn }
output "app_secret_arn" { value = aws_secretsmanager_secret.app.arn }
