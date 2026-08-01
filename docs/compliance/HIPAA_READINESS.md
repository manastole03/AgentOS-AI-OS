# HIPAA readiness controls

This is an engineering control baseline, not a compliance attestation. Production use with electronic protected health information still requires an organization-wide risk analysis, policies, workforce training, incident procedures, retention decisions, vendor due diligence, and executed BAAs.

| Safeguard area               | Implemented technical evidence                                                                           | Operational requirement                                                    |
| ---------------------------- | -------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| Unique identity and access   | Role-specific identities, Argon2 passwords, Google OIDC, short JWTs, rotating server-side sessions, RBAC | Quarterly access review and prompt termination workflow                    |
| Emergency access             | Admin role and auditable operational CLI                                                                 | Document and test emergency-access procedure                               |
| Automatic logoff             | 15-minute access tokens and revocable sessions                                                           | Define workstation controls and maximum session policy                     |
| Audit controls               | Authentication, portal, document, integration, AI, EKS, VPC, and database audit events                   | Central immutable export, review cadence, and seven-year policy validation |
| Integrity                    | TLS, authenticated encryption, SHA-256 document digests, signed images, immutable backups                | Key rotation, change approval, and restore testing                         |
| Person/entity authentication | Password/OIDC verification, OTP, session binding                                                         | MFA enforcement for workforce and administrators before go-live            |
| Transmission security        | TLS-required production configuration, private networking, HSTS                                          | Validate certificates and provider TLS/BAAs                                |
| Minimum necessary            | Tenant/owner scopes, role module allowlists, document access auditing                                    | Data classification and job-function access matrices                       |
| Contingency plan             | Multi-AZ services, PITR, AWS Backup, recovery runbook                                                    | Semiannual restore exercise and documented RTO/RPO sign-off                |
| Security incidents           | Correlation IDs, sanitized errors, alerts, trace context                                                 | Staffed escalation, breach assessment, evidence preservation               |

Never put PHI in metric labels, traces, logs, GitHub artifacts, Terraform state outputs, issue trackers, or model-provider calls without an approved BAA and data-use configuration.
