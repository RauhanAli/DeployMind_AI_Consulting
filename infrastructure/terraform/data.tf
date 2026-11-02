resource "random_password" "db" {
  length  = 32
  special = false
}

resource "aws_db_subnet_group" "this" {
  name       = "deploymind-${var.environment}"
  subnet_ids = module.vpc.database_subnets
}

# PostgreSQL 16 on RDS supports the pgvector extension (CREATE EXTENSION vector is run by the first migration).
resource "aws_db_instance" "postgres" {
  identifier                   = "deploymind-${var.environment}"
  engine                       = "postgres"
  engine_version               = "16.4"
  instance_class               = var.db_instance_class
  allocated_storage            = 50
  max_allocated_storage        = 500
  storage_encrypted            = true
  db_name                      = "deploymind"
  username                     = "deploymind"
  password                     = random_password.db.result
  db_subnet_group_name         = aws_db_subnet_group.this.name
  vpc_security_group_ids       = [aws_security_group.data.id]
  multi_az                     = var.environment == "production"
  backup_retention_period      = var.environment == "production" ? 14 : 3
  deletion_protection          = var.environment == "production"
  skip_final_snapshot          = var.environment != "production"
  performance_insights_enabled = true
  auto_minor_version_upgrade   = true
}

resource "aws_elasticache_subnet_group" "this" {
  name       = "deploymind-${var.environment}"
  subnet_ids = module.vpc.private_subnets
}

resource "aws_elasticache_replication_group" "redis" {
  replication_group_id       = "deploymind-${var.environment}"
  description                = "DeployMind Celery broker and rate limiting"
  engine                     = "redis"
  node_type                  = "cache.t4g.small"
  num_cache_clusters         = var.environment == "production" ? 2 : 1
  automatic_failover_enabled = var.environment == "production"
  subnet_group_name          = aws_elasticache_subnet_group.this.name
  security_group_ids         = [aws_security_group.data.id]
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
}

resource "aws_s3_bucket" "documents" {
  bucket_prefix = "deploymind-${var.environment}-documents-"
}

resource "aws_s3_bucket_public_access_block" "documents" {
  bucket                  = aws_s3_bucket.documents.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "documents" {
  bucket = aws_s3_bucket.documents.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}

resource "aws_s3_bucket_versioning" "documents" {
  bucket = aws_s3_bucket.documents.id
  versioning_configuration { status = "Enabled" }
}

# Application secrets live in Secrets Manager and are injected into tasks as environment secrets.
resource "random_password" "jwt" {
  length  = 64
  special = false
}

resource "aws_secretsmanager_secret" "app" {
  name = "deploymind/${var.environment}/app"
}

resource "aws_secretsmanager_secret_version" "app" {
  secret_id = aws_secretsmanager_secret.app.id
  secret_string = jsonencode({
    DATABASE_URL           = "postgresql+psycopg://deploymind:${random_password.db.result}@${aws_db_instance.postgres.address}:5432/deploymind"
    JWT_SECRET             = random_password.jwt.result
    SECRETS_ENCRYPTION_KEY = "set-me: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
    OPENAI_API_KEY         = ""
    ANTHROPIC_API_KEY      = ""
  })
  lifecycle { ignore_changes = [secret_string] } # rotated / edited out-of-band after first apply
}
