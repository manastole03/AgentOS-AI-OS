# Incident response runbook

1. **Detect and triage:** acknowledge the alert, assign severity, open a restricted incident channel, and capture error/request/trace IDs without copying PHI.
2. **Contain:** revoke sessions or provider keys, disable affected integrations, isolate workloads with NetworkPolicy, or use Argo CD to roll back. Do not delete evidence.
3. **Investigate:** correlate immutable audit events, EKS audit logs, VPC flow logs, RDS logs, traces, and image provenance. Limit evidence access and maintain chain of custody.
4. **Recover:** follow the backup runbook, rotate secrets, validate migrations and security controls, and restore traffic incrementally.
5. **Notify:** security/privacy counsel determines whether the event is a reportable breach and owns regulatory and individual notification timelines.
6. **Learn:** complete a blameless review, track corrective actions, update detections and threat models, and preserve the final report under the retention policy.

Critical alerts include sustained 5xx errors, authentication anomalies, disabled audit export, backup failure, unexpected privileged access, data-service TLS failure, and AI provider data-boundary violations.
