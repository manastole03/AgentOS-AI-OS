output "cluster_name" {
  value = module.eks.cluster_name
}
output "cluster_endpoint" {
  value = module.eks.cluster_endpoint
}
output "database_endpoint" {
  value     = aws_db_instance.healthos.endpoint
  sensitive = true
}
output "redis_endpoint" {
  value     = aws_elasticache_replication_group.healthos.configuration_endpoint_address
  sensitive = true
}
output "runtime_secret_arn" {
  value = aws_secretsmanager_secret.runtime.arn
}
output "external_secrets_role_arn" {
  value = aws_iam_role.external_secrets.arn
}
output "github_deploy_role_arn" {
  value = aws_iam_role.github_deploy.arn
}
output "compliance_bucket" {
  value = aws_s3_bucket.compliance.id
}
