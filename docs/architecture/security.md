# Security baseline

This repository provides controls, not a compliance certification. Before handling PHI or production insurance data:

- Replace every placeholder secret through a managed secret store; never commit `.env` files.
- Prefer an asymmetric JWT algorithm and managed signing keys when multiple issuers/verifiers exist.
- Configure exact CORS origins, Google OAuth redirect URIs, TLS, HSTS, and gateway rate limits.
- Use managed encrypted PostgreSQL and Redis services with private networking, authentication, backups, and tested restore procedures.
- Add audit-event storage, tenant isolation, field-level access policies, retention/deletion controls, and PHI-safe log redaction before domain endpoints.
- Pin release image digests, scan SBOMs and containers, sign artifacts, and enforce admission policies.
- Complete HIPAA/HITRUST threat modeling, vendor BAAs, risk assessment, incident response, and access reviews with the appropriate security and compliance owners.

Application logs are structured and correlation-aware. Future code must not log tokens, cookies, prompts containing PHI, raw upstream bodies, or database connection strings.

## Authentication controls

- Passwords are hashed with pwdlib's recommended Argon2 configuration and are never logged or returned.
- Access JWTs expire after 15 minutes by default. Refresh JWTs use a separate key, rotate on every use, and are represented in PostgreSQL only by SHA-256 digests.
- Refresh-token reuse revokes the complete token family. Password reset increments the user's token version and revokes every active session.
- Browser tokens use HttpOnly, Secure-in-production, SameSite cookies. State-changing cookie-authenticated requests require a matching non-HttpOnly CSRF cookie and `X-CSRF-Token` header.
- OTPs are generated with a cryptographic RNG, HMAC-hashed at rest, single-use, rate-limited, attempt-limited, and expire after ten minutes by default.
- Password-reset requests return the same response for existing and non-existing accounts. SMTP is mandatory when `ENVIRONMENT=production`.
- RBAC decisions are loaded from PostgreSQL on each authorized request. Access-token role claims are informational and are not the final authorization source.
- Every session is server-side revocable. Authentication lifecycle events are written to `audit_events` without credentials or OTP values.

The Next.js middleware improves navigation behavior but does not establish authorization. FastAPI dependencies are the security boundary.
