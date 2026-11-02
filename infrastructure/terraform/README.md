# Terraform — AWS reference infrastructure

Provisions one DeployMind environment on AWS:

| Concern | Resource |
| --- | --- |
| Network | VPC (2 AZs), public / private / database subnets, NAT |
| Compute | ECS Fargate cluster; services `api`, `web`, `worker`, `assistant` with deployment circuit breaker (auto-rollback) |
| Ingress | ALB with TLS 1.3 policy; `/api/*` → API, `assistant.*` → assistant, default → web |
| Data | RDS PostgreSQL 16 (pgvector), ElastiCache Redis (TLS, encrypted), S3 (private, versioned, SSE) |
| Secrets | Secrets Manager → injected as ECS task secrets |
| Images | ECR (immutable tags, scan on push) |
| CI/CD | GitHub OIDC role scoped to the repo + GitHub Environment |
| Logs | CloudWatch log group per service (30-day retention) |

```bash
cd infrastructure/terraform
terraform init
terraform plan  -var environment=staging -var domain_certificate_arn=arn:aws:acm:... -var github_repository=owner/repo
terraform apply -var environment=staging ...
```

After the first apply, set `SECRETS_ENCRYPTION_KEY` (and provider API keys) in the `deploymind/<env>/app` secret.
`terraform validate` passes (Terraform 1.9, AWS provider 5.x), but the configuration has **not been applied**: no AWS
account was used for the demo. Run `terraform plan` in your account and review it before applying.
