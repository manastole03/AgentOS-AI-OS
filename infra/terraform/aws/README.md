# AWS production foundation

This module provisions a three-AZ VPC, private EKS workers, encrypted Multi-AZ PostgreSQL and Redis, KMS, immutable compliance storage, AWS Backup, workload secret delivery, and a GitHub OIDC deployment role.

```bash
cp backend.hcl.example backend.hcl
cp terraform.tfvars.example terraform.tfvars
terraform init -backend-config=backend.hcl
terraform plan -out=production.tfplan
terraform apply production.tfplan
```

Use a remote S3 backend with state locking and tightly scoped operator access. Supply sensitive variables from the CI secret store rather than committing `terraform.tfvars`. After apply, place `external_secrets_role_arn` into the External Secrets Helm release and use the generated GitHub role as the protected production environment secret `AWS_DEPLOY_ROLE_ARN`.

Before the first workload sync, replace the example DNS, mail, OAuth, and third-party provider settings. Run an organization security review and execute the recovery exercise in [BACKUP_RECOVERY.md](../../../docs/operations/BACKUP_RECOVERY.md).
