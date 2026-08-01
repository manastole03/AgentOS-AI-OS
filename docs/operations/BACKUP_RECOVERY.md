# Backup and recovery runbook

Target objectives: database RPO ≤ 5 minutes using RDS point-in-time recovery, infrastructure RPO ≤ 24 hours, and service RTO ≤ 4 hours. Business owners must approve these targets.

## Automated controls

- RDS automated backups and transaction logs are retained for 35 days.
- AWS Backup creates daily KMS-encrypted recovery points and transitions them to cold storage for seven years.
- Final snapshots and deletion protection guard destructive database changes.
- ElastiCache retains 35 daily snapshots; queues must tolerate replay from the durable run table.
- Terraform state uses a separate versioned, encrypted S3 backend with locking.
- Compliance exports use an object-locked, versioned, KMS-encrypted S3 bucket.

## PostgreSQL point-in-time restore

1. Declare an incident, freeze deployments, record the requested recovery timestamp, and preserve audit evidence.
2. Restore RDS to a new isolated instance; never overwrite the affected instance.
3. Run consistency checks: Alembic heads, row counts, foreign keys, authentication session integrity, pgvector dimensions, and latest audit timestamps.
4. Start a temporary HealthOS release against the restored database with outbound provider traffic disabled.
5. Execute smoke and portal integration tests. Security and clinical owners approve the recovery point.
6. Rotate database credentials, update Secrets Manager, allow External Secrets reconciliation, and shift traffic gradually.
7. Retain the old instance until incident closure, then destroy through approved Terraform change.

## Kubernetes and application recovery

Recreate EKS from Terraform, bootstrap Argo CD/External Secrets/monitoring, and apply the Argo applications. Argo CD reconstructs stateless workloads; AWS data services retain state. Confirm alert delivery, tracing, backups, and image signature enforcement before reopening traffic.

Every six months, restore into an isolated account, measure actual RPO/RTO, record evidence, and update this runbook.
