# Security Hardening Plan — FinanceBuy

**Date:** January 8, 2026
**Purpose:** Ensure the application and databases follow industry best practices so the network is not exposed and sensitive information is protected.

---

## Goals / Acceptance Criteria
- Network must not be exposed publicly.
- Use latest industry standards (TLS 1.3, NIST/CIS recommendations, OWASP top-10 controls).
- Implement improved security measures for application and databases.

---

## 1. Network Hardening (no public exposure)
- Place all databases and internal services in private subnets inside a VPC.
- Do NOT expose DB endpoints publicly. Disable public accessibility for managed DBs.
- Use security groups and network ACLs with explicit allow rules only for required ports and CIDR ranges.
- Provide admin access via a hardened bastion host or a VPN/Direct Connect/PrivateLink; restrict to specific admin IPs and require MFA.
- Use VPC endpoints (AWS PrivateLink) for managed services (S3, Secrets Manager) to avoid internet egress.
- Implement subnet segregation: prod/stage/dev in separate VPCs/accounts with strict peering and IAM controls.
- Block outbound egress where not required; use NAT only for approved services.

---

## 2. Encryption & Key Management
- Enforce TLS 1.3 (fallback to TLS 1.2 only if necessary) with strong ciphers (AEAD suites). Terminate TLS at trusted load balancer or use mutual TLS for service-to-service.
- Enable encryption at rest for all disks and managed services; ensure backups are encrypted.
- Use application-level field encryption for highly sensitive fields (PII, SSNs, private keys) via `pgcrypto` or app-side envelope encryption.
- Use a centralized KMS (AWS KMS / Azure Key Vault / GCP KMS) with strict access controls and automated rotation policies.
- Do not store keys in source or container images—fetch keys at runtime with least privilege.

---

## 3. Database Hardening
- Disable public access on DB; bind to private network only.
- Enforce least-privilege DB roles: separate roles for app, analytics, admin; grant minimal privileges.
- Enable Row-Level Security (RLS) for per-user/tenant isolation where applicable.
- Enforce strong authentication: database users via IAM auth where supported (e.g., RDS IAM) or managed secrets.
- Harden `pg_hba.conf` (or cloud equivalent) to allow only required IPs and auth methods.
- Enable and regularly review auditing (pg_audit / native audit), write audit logs to an immutable store (S3 with versioning & Object Lock if required).
- Enable `pg_stat_statements` and slow query logging; monitor for anomalous queries.
- Use connection pooling (PgBouncer) and restrict connections to reduce attack surface.
- Periodic vulnerability scanning and configuration checks against CIS PostgreSQL benchmarks.
- Ensure backups are encrypted, access-controlled, and test restore procedures regularly.

---

## 4. Application Security
- Follow OWASP Top 10: input validation, SQL injection prevention (parameterized queries / prepared statements), XSS protections, etc.
- Use strong authentication flows: OAuth2/OIDC, session cookies with `Secure`/`HttpOnly`/`SameSite=strict`, JWTs with short expiry plus refresh-token rotation.
- Enforce MFA for accounts with elevated privileges and admin access.
- Use `Argon2` for password hashing (tunable parameters) or equivalent modern KDF.
- Implement RBAC and scope checks; centralize authorization logic in middleware/services.
- API protections: rate limiting, quotas, request size limits, strict schema validation (Pydantic), and WAF at the edge.
- Secure headers and CSP: HSTS, X-Content-Type-Options, X-Frame-Options, Referrer-Policy, Content-Security-Policy.
- Avoid secrets in client-side code. For SPAs, use secure backend-for-frontend patterns and short-lived tokens.

---

## 5. CI/CD, Build & Supply Chain Security
- Use private container registries (ECR/GCR/ACR) with image signing (Cosign/Notary) and least-privilege pull permissions.
- Multi-stage Docker builds; final images contain only runtime artifacts and non-sensitive files.
- Enforce SCA (Dependabot/Snyk) and static-analysis (Bandit/semgrep) in pipeline; fail builds on critical vulnerabilities.
- Use ephemeral build runners and avoid storing secrets in CI logs or runners; use vault integration or secrets manager in pipeline.
- Scan IaC (Terraform/CloudFormation) with tfsec/checkov for misconfigurations before deploy.
- Require branch protections, PR reviews, and signed commits for main branches.

---

## 6. Monitoring, Logging & Incident Response
- Centralize logs (application, DB, network) to SIEM/Log store (Datadog, CloudWatch, ELK) with tamper-evident storage and retention per compliance.
- Generate immutable audit trails for all security-sensitive actions; retain per regulatory requirements.
- Instrument metrics and alerts: failed logins, sudden surge in DB queries, replication lag, privilege escalations, anomalous IP access.
- Integrate alerts to on-call (PagerDuty/OpsGenie) with documented escalation steps.
- Maintain an incident response runbook: containment, forensics, recovery, communication, and post-mortem.
- Regularly run tabletop exercises and disaster recovery tests.

---

## 7. Data Protection & Privacy Controls
- Minimize PII collection; pseudonymize or tokenize where possible.
- Implement data retention and deletion policies; provide mechanisms for data subject requests (GDPR).
- Use field-level encryption for extremely sensitive data; perform encryption/decryption in a secure service.
- Ensure backups and logs containing PII are access-controlled and encrypted.

---

## 8. Access Management & Operational Controls
- Enforce least-privilege IAM for cloud accounts, with role separation between infra and app teams.
- Require MFA for all privileged accounts; implement Just-in-Time access where possible.
- Rotate credentials and keys regularly; revoke unused accounts and keys.
- Maintain inventories of secrets and rotate compromised credentials immediately.

---

## 9. Standards & Compliance
- Follow relevant standards: TLS 1.3, OWASP Top 10, NIST CSF, CIS Benchmarks, and PCI-DSS if handling payments.
- Use managed provider compliance programs (SOC2/ISO27001) as part of evidence.
- Map controls to compliance requirements and produce attestation artifacts.

---

## 10. Checklist (Immediate Actions)
- [ ] Move DB to private subnet and disable public accessibility.
- [ ] Enforce TLS 1.3 on all ingress/egress and enable HSTS.
- [ ] Configure KMS for encryption & enable key rotation.
- [ ] Implement Secrets Manager integration in CI/CD and runtime.
- [ ] Enable DB auditing and ship logs to immutable store.
- [ ] Add WAF and rate limiting to API gateway.
- [ ] Add SCA and static scanning to CI/CD.
- [ ] Create incident response runbook and schedule tabletop exercise.

---

## 11. Next Steps / Implementation Plan
1. Execute Immediate Actions checklist (1-2 weeks).
2. Harden DB and app per CIS and OWASP recommendations (2-4 weeks).
3. Deploy monitoring, SIEM, and alerts; validate with test incidents (1-2 weeks).
4. Schedule third-party pentest and compliance assessment (4-8 weeks).
5. Iterate on findings and formalize policies and runbooks.

---

## 12. Operational Targets, Retention and Exceptions

- **RTO / RPO Targets:**
	- Production primary services: RTO = 1 hour, RPO = 5 minutes
	- Reporting/analytics: RTO = 4 hours, RPO = 15 minutes
	- Disaster recovery full restore (worst case): RTO = 24 hours, RPO = 1 hour

- **Backup Retention (recommended):**
	- Transaction DB backups: daily full, keep 90 days; PITR logs retained 30 days; cross-region copies.
	- Audit logs and immutable evidence: retain 7 years (or per legal/compliance requirements).
	- Short-term logs/metrics: retain 30 days hot, 1 year cold.

- **Key rotation & cryptography cadence:**
	- KMS root/CMKs: rotate asymmetric keys annually and rotate data-encryption (envelope) keys every 90 days.
	- TLS certs: renew 60 days before expiry; prefer automated renewal (ACME).

- **Alert thresholds (examples to tune):**
	- Replication lag &gt; 1s: P1 alert
	- CPU &gt; 80% sustained for 5 minutes: P2 alert
	- Failed login surge &gt; 50 events/min: P1 alert
	- Slow queries &gt; 1s (95th percentile): P2 alert

- **Exceptions & Risk Acceptance:**
	- Any deviation from these controls must be documented in an Exceptions Register with owner, compensating controls, and expiry date.


---

## 13. References
- OWASP Top Ten: https://owasp.org/www-project-top-ten/
- CIS Benchmarks: https://www.cisecurity.org/cis-benchmarks/
- NIST CSF: https://www.nist.gov/cyberframework
- TLS Best Practices: IETF RFCs and Mozilla Server Side TLS

---

*File created by FinanceBuy engineering assistant.*
