module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.13"

  name                 = "deploymind-${var.environment}"
  cidr                 = "10.40.0.0/16"
  azs                  = ["${var.region}a", "${var.region}b"]
  public_subnets       = ["10.40.0.0/24", "10.40.1.0/24"]
  private_subnets      = ["10.40.10.0/24", "10.40.11.0/24"]
  database_subnets     = ["10.40.20.0/24", "10.40.21.0/24"]
  enable_nat_gateway   = true
  single_nat_gateway   = var.environment != "production"
  enable_dns_hostnames = true
}

resource "aws_security_group" "alb" {
  name   = "deploymind-${var.environment}-alb"
  vpc_id = module.vpc.vpc_id
  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "services" {
  name   = "deploymind-${var.environment}-services"
  vpc_id = module.vpc.vpc_id
  ingress {
    from_port       = 0
    to_port         = 65535
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }
  ingress {
    from_port = 0
    to_port   = 65535
    protocol  = "tcp"
    self      = true
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "data" {
  name   = "deploymind-${var.environment}-data"
  vpc_id = module.vpc.vpc_id
  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.services.id]
  }
  ingress {
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [aws_security_group.services.id]
  }
}
