variable "aws_region" {
  type    = string
  default = "us-east-1"
}
variable "environment" {
  type    = string
  default = "production"
}
variable "name" {
  type    = string
  default = "healthos"
}
variable "vpc_cidr" {
  type    = string
  default = "10.42.0.0/16"
}
variable "kubernetes_version" {
  type    = string
  default = "1.32"
}
variable "database_instance_class" {
  type    = string
  default = "db.r7g.large"
}
variable "database_allocated_storage" {
  type    = number
  default = 100
}
variable "redis_node_type" {
  type    = string
  default = "cache.r7g.large"
}
variable "github_repository" {
  type        = string
  description = "owner/repository used by GitHub OIDC"
}
variable "cluster_public_access_cidrs" {
  type        = list(string)
  description = "CIDRs allowed to reach the EKS public API endpoint"
}

variable "google_client_id" {
  type        = string
  description = "Google OAuth client ID"
  default     = ""
}
variable "google_client_secret" {
  type        = string
  description = "Google OAuth client secret"
  sensitive   = true
  default     = ""
}
variable "smtp_username" {
  type      = string
  sensitive = true
  default   = ""
}
variable "smtp_password" {
  type      = string
  sensitive = true
  default   = ""
}
variable "openai_api_key" {
  type      = string
  sensitive = true
  default   = ""
}
variable "anthropic_api_key" {
  type      = string
  sensitive = true
  default   = ""
}
variable "gemini_api_key" {
  type      = string
  sensitive = true
  default   = ""
}
variable "ocr_api_key" {
  type      = string
  sensitive = true
  default   = ""
}
variable "fhir_access_token" {
  type      = string
  sensitive = true
  default   = ""
}
variable "insurance_api_key" {
  type      = string
  sensitive = true
  default   = ""
}
variable "stripe_secret_key" {
  type      = string
  sensitive = true
  default   = ""
}
variable "stripe_webhook_secret" {
  type      = string
  sensitive = true
  default   = ""
}
