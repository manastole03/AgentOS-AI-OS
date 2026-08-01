data "aws_availability_zones" "available" {
  state = "available"
}
data "aws_caller_identity" "current" {}
data "tls_certificate" "github" {
  url = "https://token.actions.githubusercontent.com/.well-known/openid-configuration"
}

locals {
  prefix = "${var.name}-${var.environment}"
  azs    = slice(data.aws_availability_zones.available.names, 0, 3)
  tags = {
    Application        = var.name
    Environment        = var.environment
    ManagedBy          = "terraform"
    DataClassification = "PHI"
  }
}

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "5.21.0"

  name                                 = local.prefix
  cidr                                 = var.vpc_cidr
  azs                                  = local.azs
  private_subnets                      = [for i, _ in local.azs : cidrsubnet(var.vpc_cidr, 4, i)]
  public_subnets                       = [for i, _ in local.azs : cidrsubnet(var.vpc_cidr, 8, i + 48)]
  intra_subnets                        = [for i, _ in local.azs : cidrsubnet(var.vpc_cidr, 8, i + 64)]
  enable_nat_gateway                   = true
  single_nat_gateway                   = false
  one_nat_gateway_per_az               = true
  enable_dns_hostnames                 = true
  enable_dns_support                   = true
  enable_flow_log                      = true
  create_flow_log_cloudwatch_iam_role  = true
  create_flow_log_cloudwatch_log_group = true
  flow_log_max_aggregation_interval    = 60
  public_subnet_tags                   = { "kubernetes.io/role/elb" = 1 }
  private_subnet_tags                  = { "kubernetes.io/role/internal-elb" = 1 }
}

resource "aws_kms_key" "healthos" {
  description             = "HealthOS PHI envelope encryption"
  enable_key_rotation     = true
  deletion_window_in_days = 30
}
resource "aws_kms_alias" "healthos" {
  name          = "alias/${local.prefix}"
  target_key_id = aws_kms_key.healthos.key_id
}

module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "20.36.0"

  cluster_name                             = local.prefix
  cluster_version                          = var.kubernetes_version
  cluster_endpoint_public_access           = true
  cluster_endpoint_public_access_cidrs     = var.cluster_public_access_cidrs
  cluster_endpoint_private_access          = true
  cluster_enabled_log_types                = ["api", "audit", "authenticator", "controllerManager", "scheduler"]
  cloudwatch_log_group_kms_key_id          = aws_kms_key.healthos.arn
  cloudwatch_log_group_retention_in_days   = 365
  enable_irsa                              = true
  enable_cluster_creator_admin_permissions = true
  vpc_id                                   = module.vpc.vpc_id
  subnet_ids                               = module.vpc.private_subnets
  control_plane_subnet_ids                 = module.vpc.intra_subnets

  cluster_addons = {
    coredns            = { most_recent = true }
    kube-proxy         = { most_recent = true }
    aws-ebs-csi-driver = { most_recent = true }
    vpc-cni = {
      most_recent          = true
      configuration_values = jsonencode({ enableNetworkPolicy = "true" })
    }
  }
  eks_managed_node_groups = {
    general = {
      instance_types = ["m7i.large", "m7a.large"]
      capacity_type  = "ON_DEMAND"
      min_size       = 3
      desired_size   = 3
      max_size       = 20
      subnet_ids     = module.vpc.private_subnets
      block_device_mappings = {
        xvda = {
          device_name = "/dev/xvda"
          ebs = {
            volume_size           = 100
            volume_type           = "gp3"
            encrypted             = true
            kms_key_id            = aws_kms_key.healthos.arn
            delete_on_termination = true
          }
        }
      }
    }
  }

  access_entries = {
    github_deploy = {
      principal_arn = aws_iam_role.github_deploy.arn
      policy_associations = {
        production_deployer = {
          policy_arn = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"
          access_scope = {
            type       = "namespace"
            namespaces = ["argocd"]
          }
        }
      }
    }
  }
}

resource "aws_db_subnet_group" "healthos" {
  name       = local.prefix
  subnet_ids = module.vpc.intra_subnets
}
resource "aws_security_group" "database" {
  name                   = "${local.prefix}-database"
  vpc_id                 = module.vpc.vpc_id
  revoke_rules_on_delete = true
}
resource "aws_vpc_security_group_ingress_rule" "database" {
  security_group_id            = aws_security_group.database.id
  referenced_security_group_id = module.eks.node_security_group_id
  from_port                    = 5432
  to_port                      = 5432
  ip_protocol                  = "tcp"
}
resource "random_password" "database" {
  length  = 32
  special = false
}
resource "aws_db_parameter_group" "healthos" {
  name   = local.prefix
  family = "postgres17"
  parameter {
    name  = "rds.force_ssl"
    value = "1"
  }
  parameter {
    name  = "log_min_duration_statement"
    value = "1000"
  }
  parameter {
    name         = "shared_preload_libraries"
    value        = "pg_stat_statements"
    apply_method = "pending-reboot"
  }
}
resource "aws_db_instance" "healthos" {
  identifier                            = local.prefix
  engine                                = "postgres"
  engine_version                        = "17.4"
  instance_class                        = var.database_instance_class
  allocated_storage                     = var.database_allocated_storage
  max_allocated_storage                 = 1000
  storage_type                          = "gp3"
  storage_encrypted                     = true
  kms_key_id                            = aws_kms_key.healthos.arn
  db_name                               = "healthos"
  username                              = "healthos_admin"
  password                              = random_password.database.result
  port                                  = 5432
  db_subnet_group_name                  = aws_db_subnet_group.healthos.name
  vpc_security_group_ids                = [aws_security_group.database.id]
  parameter_group_name                  = aws_db_parameter_group.healthos.name
  multi_az                              = true
  publicly_accessible                   = false
  deletion_protection                   = true
  backup_retention_period               = 35
  backup_window                         = "03:00-04:00"
  maintenance_window                    = "sun:05:00-sun:06:00"
  copy_tags_to_snapshot                 = true
  skip_final_snapshot                   = false
  final_snapshot_identifier             = "${local.prefix}-final"
  enabled_cloudwatch_logs_exports       = ["postgresql", "upgrade"]
  performance_insights_enabled          = true
  performance_insights_kms_key_id       = aws_kms_key.healthos.arn
  performance_insights_retention_period = 731
  auto_minor_version_upgrade            = true
  tags                                  = { Backup = "healthos-daily" }
}

resource "aws_security_group" "redis" {
  name                   = "${local.prefix}-redis"
  vpc_id                 = module.vpc.vpc_id
  revoke_rules_on_delete = true
}
resource "aws_vpc_security_group_ingress_rule" "redis" {
  security_group_id            = aws_security_group.redis.id
  referenced_security_group_id = module.eks.node_security_group_id
  from_port                    = 6379
  to_port                      = 6379
  ip_protocol                  = "tcp"
}
resource "random_password" "redis" {
  length  = 32
  special = false
}
resource "aws_elasticache_subnet_group" "healthos" {
  name       = local.prefix
  subnet_ids = module.vpc.intra_subnets
}
resource "aws_elasticache_replication_group" "healthos" {
  replication_group_id       = local.prefix
  description                = "HealthOS session, cache, and queue service"
  node_type                  = var.redis_node_type
  engine                     = "redis"
  engine_version             = "7.1"
  port                       = 6379
  parameter_group_name       = "default.redis7.cluster.on"
  subnet_group_name          = aws_elasticache_subnet_group.healthos.name
  security_group_ids         = [aws_security_group.redis.id]
  automatic_failover_enabled = true
  multi_az_enabled           = true
  num_node_groups            = 2
  replicas_per_node_group    = 1
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
  kms_key_id                 = aws_kms_key.healthos.arn
  auth_token                 = random_password.redis.result
  snapshot_retention_limit   = 35
  snapshot_window            = "02:00-03:00"
  maintenance_window         = "sun:06:00-sun:07:00"
  auto_minor_version_upgrade = true
}

resource "aws_s3_bucket" "compliance" {
  bucket              = "${local.prefix}-compliance-${data.aws_caller_identity.current.account_id}"
  object_lock_enabled = true
}
resource "aws_s3_bucket_versioning" "compliance" {
  bucket = aws_s3_bucket.compliance.id
  versioning_configuration {
    status = "Enabled"
  }
}
resource "aws_s3_bucket_server_side_encryption_configuration" "compliance" {
  bucket = aws_s3_bucket.compliance.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.healthos.arn
    }
    bucket_key_enabled = true
  }
}
resource "aws_s3_bucket_public_access_block" "compliance" {
  bucket                  = aws_s3_bucket.compliance.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket_object_lock_configuration" "compliance" {
  bucket = aws_s3_bucket.compliance.id
  rule {
    default_retention {
      mode = "COMPLIANCE"
      days = 2555
    }
  }
}
resource "aws_s3_bucket_lifecycle_configuration" "compliance" {
  bucket = aws_s3_bucket.compliance.id
  rule {
    id     = "archive"
    status = "Enabled"
    filter {}
    transition {
      days          = 90
      storage_class = "GLACIER"
    }
    expiration { days = 2555 }
  }
}

resource "aws_backup_vault" "healthos" {
  name        = local.prefix
  kms_key_arn = aws_kms_key.healthos.arn
}
resource "aws_backup_plan" "healthos" {
  name = local.prefix
  rule {
    rule_name         = "daily-long-term"
    target_vault_name = aws_backup_vault.healthos.name
    schedule          = "cron(0 4 * * ? *)"
    start_window      = 60
    completion_window = 360
    lifecycle {
      cold_storage_after = 30
      delete_after       = 2555
    }
  }
}
data "aws_iam_policy_document" "backup_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["backup.amazonaws.com"]
    }
  }
}
resource "aws_iam_role" "backup" {
  name               = "${local.prefix}-backup"
  assume_role_policy = data.aws_iam_policy_document.backup_assume.json
}
resource "aws_iam_role_policy_attachment" "backup" {
  role       = aws_iam_role.backup.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSBackupServiceRolePolicyForBackup"
}
resource "aws_backup_selection" "healthos" {
  name         = local.prefix
  iam_role_arn = aws_iam_role.backup.arn
  plan_id      = aws_backup_plan.healthos.id
  resources    = [aws_db_instance.healthos.arn]
}

resource "tls_private_key" "access_jwt" {
  algorithm = "RSA"
  rsa_bits  = 4096
}
resource "tls_private_key" "refresh_jwt" {
  algorithm = "RSA"
  rsa_bits  = 4096
}
resource "random_password" "otp" {
  length  = 48
  special = false
}
resource "random_password" "litellm" {
  length  = 48
  special = false
}
resource "random_password" "langgraph" {
  length  = 32
  special = false
}
resource "random_id" "fernet" {
  byte_length = 32
}
resource "aws_secretsmanager_secret" "runtime" {
  name                    = "${var.name}/${var.environment}/runtime"
  kms_key_id              = aws_kms_key.healthos.arn
  recovery_window_in_days = 30
}
resource "aws_secretsmanager_secret_version" "runtime" {
  secret_id = aws_secretsmanager_secret.runtime.id
  secret_string = jsonencode({
    DATABASE_URL           = "postgresql+asyncpg://healthos_admin:${random_password.database.result}@${aws_db_instance.healthos.address}:5432/healthos?ssl=require"
    LITELLM_DATABASE_URL   = "postgresql://healthos_admin:${random_password.database.result}@${aws_db_instance.healthos.address}:5432/healthos?sslmode=require"
    REDIS_URL              = "rediss://:${random_password.redis.result}@${aws_elasticache_replication_group.healthos.configuration_endpoint_address}:6379/0"
    REDIS_HOST             = aws_elasticache_replication_group.healthos.configuration_endpoint_address
    REDIS_PASSWORD         = random_password.redis.result
    JWT_SECRET_KEY         = tls_private_key.access_jwt.private_key_pem
    JWT_REFRESH_SECRET_KEY = tls_private_key.refresh_jwt.private_key_pem
    OTP_SECRET_KEY         = random_password.otp.result
    LITELLM_MASTER_KEY     = random_password.litellm.result
    AI_DATA_ENCRYPTION_KEY = random_id.fernet.b64_std
    LANGGRAPH_AES_KEY      = random_password.langgraph.result
    GOOGLE_CLIENT_ID       = var.google_client_id
    GOOGLE_CLIENT_SECRET   = var.google_client_secret
    SMTP_USERNAME          = var.smtp_username
    SMTP_PASSWORD          = var.smtp_password
    OPENAI_API_KEY         = var.openai_api_key
    ANTHROPIC_API_KEY      = var.anthropic_api_key
    GEMINI_API_KEY         = var.gemini_api_key
    OCR_API_KEY            = var.ocr_api_key
    FHIR_ACCESS_TOKEN      = var.fhir_access_token
    INSURANCE_API_KEY      = var.insurance_api_key
    STRIPE_SECRET_KEY      = var.stripe_secret_key
    STRIPE_WEBHOOK_SECRET  = var.stripe_webhook_secret
  })
}

data "aws_iam_policy_document" "external_secrets_policy" {
  statement {
    actions   = ["secretsmanager:GetSecretValue", "secretsmanager:DescribeSecret"]
    resources = [aws_secretsmanager_secret.runtime.arn]
  }
  statement {
    actions   = ["kms:Decrypt"]
    resources = [aws_kms_key.healthos.arn]
  }
}
resource "aws_iam_policy" "external_secrets" {
  name   = "${local.prefix}-external-secrets"
  policy = data.aws_iam_policy_document.external_secrets_policy.json
}
data "aws_iam_policy_document" "external_secrets_assume" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [module.eks.oidc_provider_arn]
    }
    condition {
      test     = "StringEquals"
      variable = "${module.eks.oidc_provider}:sub"
      values   = ["system:serviceaccount:external-secrets:external-secrets"]
    }
    condition {
      test     = "StringEquals"
      variable = "${module.eks.oidc_provider}:aud"
      values   = ["sts.amazonaws.com"]
    }
  }
}
resource "aws_iam_role" "external_secrets" {
  name               = "${local.prefix}-external-secrets"
  assume_role_policy = data.aws_iam_policy_document.external_secrets_assume.json
}
resource "aws_iam_role_policy_attachment" "external_secrets" {
  role       = aws_iam_role.external_secrets.name
  policy_arn = aws_iam_policy.external_secrets.arn
}

resource "aws_iam_openid_connect_provider" "github" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [data.tls_certificate.github.certificates[0].sha1_fingerprint]
}
data "aws_iam_policy_document" "github_assume" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repository}:ref:refs/heads/main", "repo:${var.github_repository}:ref:refs/tags/v*"]
    }
  }
}
resource "aws_iam_role" "github_deploy" {
  name               = "${local.prefix}-github-deploy"
  assume_role_policy = data.aws_iam_policy_document.github_assume.json
}
resource "aws_iam_role_policy" "github_deploy" {
  name = "eks-deploy"
  role = aws_iam_role.github_deploy.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["eks:DescribeCluster"]
      Resource = module.eks.cluster_arn
    }]
  })
}
