# Backend Decisions Summary

**Date:** January 8, 2026
**Project:** tickerTap — Backend Architecture Decisions

---

## Purpose
Concise decisions and implementation guidance covering: programming language, database communication, calculation strategy, packaging to prevent source leakage, and security measures for login and data protection.

---

## 1. Programming Language
- **Primary:** `Python 3.11+`
  - Rationale: mature finance ecosystem (NumPy, pandas), fast developer productivity, rich web frameworks (`FastAPI`, `Django`), strong DB and testing tooling.
- **Alternatives:** `Go` (concurrency, compiled binaries), `TypeScript/Node.js` (I/O performance). Choose if latency or binary distribution is a strict requirement.

---

## 2. Database Communication
- **DB:** `PostgreSQL` (primary recommendation).
- **Drivers/Libraries:** `asyncpg` or `psycopg` + ORM (`SQLAlchemy` or `SQLModel`) for typed models.
- **Connection Pooling:** App-level pooling (SQLAlchemy `QueuePool`) + PgBouncer for production.
- **Patterns:**
  - Use explicit transactions for money operations.
  - Parameterized queries and prepared statements.
  - Read routing: writes → primary, reads → replicas (separate engines or router layer).
  - Retries with exponential backoff and idempotency keys for safe replays.
- **Example connection string:** `postgresql://app_user:SECRET@db-primary.region:5432/tickerTap`

---

## 3. Calculation Strategy (Server vs Client)
- **Authoritative calculations on server:** All monetary, settlement, accounting, tax, and portfolio calculations must run server-side for correctness and auditability.
- **Client-side:** Only for UI previews and non-authoritative calculations.
- **Heavy compute:** Offload to background workers (`Celery`, `RQ`, or modern orchestrators like `Prefect`); use optimized libraries (NumPy/pandas) or implement hot paths in `Rust`/`Go` exposed via RPC.
- **Streaming:** Use Kafka/Pulsar for market-data ingestion and near-real-time processing.
- **Precision:** Use fixed-precision decimals (`decimal.Decimal`) and enforce determinism in business logic.

### Determinism and numeric policy
- Use `decimal.Decimal` for all monetary calculations with a project-wide `Decimal` context. Avoid binary floats for money.
- Define a `monetary_precision` policy (e.g., 2 decimal places for fiat, configurable for crypto) and enforce it at input, validation and DB schema (DECIMAL(18,2) etc.).
- Include reconciliation tests that assert ledger balance invariants and add nightly batch reconciliations to detect drift.

---

## 4. Packaging to Prevent Source Leakage
- **Do not distribute backend source.** Keep code in private repos.
- **Containerize:** Multi-stage Docker builds; final image only contains runtime artifacts.
- **Private registries:** Store images in ECR/GCR/ACR with restricted access and image signing.
- **Native binaries (optional):** Compile critical components (PyInstaller/Nuitka for Python or write in Go/Rust) if additional obfuscation required.
- **CI/CD controls:** Ephemeral build runners, artifact signing, minimal artifact retention, branch protections, and least-privilege deploy keys.
- **Secrets:** Never bake secrets into images; inject at runtime from a secrets manager.
- **Client apps:** Minify/obfuscate but assume client code is inspectable; never embed secrets.

### Secrets usage pattern (example)
- Store DB credentials and API keys in AWS Secrets Manager (or Vault). Grant application instances an IAM role with least-privilege to retrieve only the secrets they need.
- In CI, use ephemeral secrets retrieval and avoid printing secrets in logs. Use short-lived deploy tokens for registries and rotate them.

---

## 5. Security Measures (Login & Data Protection)
- **Authentication:** OAuth2/OpenID Connect where possible; otherwise JWT/session with rotation. Passwords hashed with `Argon2` (or bcrypt). Enforce MFA (TOTP/WebAuthn).
- **Authorization:** RBAC + scope checks; use DB Row-Level Security (RLS) for data isolation.
- **Transport encryption:** TLS 1.2+/1.3 across all services; HSTS; secure cookies.
- **Encryption at rest:** Provider-managed disk encryption + application-level field encryption (pgcrypto) for PII.
- **Key management:** Use KMS (AWS KMS / Azure Key Vault / GCP KMS) with rotation.
- **Secrets management:** AWS Secrets Manager / HashiCorp Vault; inject at runtime.
- **Audit & monitoring:** Immutable audit logs (who/what/when/ip), IDS/alerts, log aggregation (CloudWatch/Datadog), alerting to PagerDuty/OpsGenie.
- **API security:** Server-side validation (Pydantic), rate limiting, WAF, strict schema checks.
- **Data protection:** Minimize PII; tokenization; retention and deletion policies for compliance (GDPR/PCI as applicable).
- **DevSecOps:** Dependency scanning (Dependabot/Snyk), static analysis (Bandit/semgrep), pen tests, and security gates in CI.

### Token and session policy
- Use short-lived access tokens (e.g., 5–15 minutes) and rotating refresh tokens with revocation lists. Store refresh tokens securely (server-side storage or encrypted cookie).
- On password change, logout, or suspicious activity, revoke refresh tokens and rotate session identifiers.

### KMS usage
- Use a centralized KMS (AWS KMS / Azure Key Vault) for envelope encryption keys; rotate data-encryption keys every 90 days and keep audit logs of key usage.

---

## 6. Minimal Recommended Stack
- Backend: `Python 3.11+` + `FastAPI`
- DB: `PostgreSQL` (AWS RDS Multi-AZ) + `asyncpg`/`SQLModel`
- Worker: `Celery`/`RQ` (Redis/RabbitMQ)
- Cache: `Redis` (ElastiCache)
- Auth: OAuth2/OpenID Connect + `Argon2` + MFA
- Packaging: Docker (multi-stage) → Private registry (ECR) → IaC (Terraform)
- Secrets: AWS Secrets Manager / KMS
- Monitoring: CloudWatch/Datadog + pganalyze or pg_stat monitoring

---

## 7. Checklist / Next Steps
- Scaffold `FastAPI` project with DB layer, migrations (`alembic`), and a sample transactional endpoint.
- Implement auth: password hashing, token lifecycle, MFA stub.
- Set up background worker and a sample heavy-calculation job using `decimal`.
- Create Dockerfile (multi-stage) and CI pipeline to build/push to private registry.
- Configure secrets access (Secrets Manager) and DB (PgBouncer) for staging/prod.
- Enable monitoring, alerting, and audit logging.

---

## 8. Notes
Keep business-critical math server-side and instrument everything with tests and audit trails. This file is a concise companion to the full `DATABASE_EVALUATION.md`.

---

*File generated by tickerTap engineering assistant.*
