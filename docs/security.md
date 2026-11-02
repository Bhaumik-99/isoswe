# Application Security & Threat Model Specification

## 1. Authentication Architecture

### 1.1 Supabase Auth Integration (Production & Staging)
- **Token Verification**: Tokens are validated using maintained cryptographic libraries (`pyjwt` with `cryptography`) and the project's Supabase Auth JWKS endpoint (`/auth/v1/.well-known/jwks.json`).
- **Validation Criteria**:
  1. Cryptographic asymmetric signature verification (ES256 / RS256) using rotating public keys cached from the Supabase JWKS endpoint.
  2. Issuer assertion: `iss` must strictly match `{settings.SUPABASE_URL}/auth/v1`.
  3. Audience verification: `aud` must strictly match `"authenticated"`.
  4. Expiry validation: `exp` must be in the future.
  5. Canonical Subject resolution: `sub` must be a valid UUID format, strictly mapped to `users.supabase_uid` in PostgreSQL.
  6. **No Email Fallback**: The system strictly maps identity by `supabase_uid` UUID; email is never used as an authentication fallback.
- **Resident Phone OTP Flow**: Passwordless SMS OTP verification via Supabase Auth and official `@supabase/supabase-js` SDK.
- **Client Security**: React client only holds the Supabase publishable key. Database connection strings and Supabase service-role keys are kept exclusively on the backend.

### 1.2 Local Development Mock Identity Provider
- **Purpose**: Enables local offline development and automated CI testing without requiring live Supabase credentials.
- **Fail-Closed Security Invariant**:
  ```python
  if settings.ENVIRONMENT in ("production", "staging"):
      raise AuthenticationError(
          "Mock authentication is strictly forbidden in non-development environments",
          code="SECURITY_VIOLATION"
      )
  ```
- Unsigned or arbitrary bypass tokens are strictly rejected if `ENABLE_LOCAL_AUTH_BYPASS` is false or the environment is not `development`/`test`.

---

## 2. Authorization and Access Control (RBAC & Multi-Tenancy)

### 2.1 Role Matrix

| Role | Scope | Capabilities | Restrictions |
| :--- | :--- | :--- | :--- |
| `RESIDENT` | Flat Memberships | View assigned unit details, view maintenance invoices, make payments, lodge complaints | Cannot access other resident units or administrative operations |
| `HELPDESK` | Assigned Society | Complaint assignment and status, bank statement import, reconciliation review, read-only committee reporting | Cannot access another society; committee reporting is strictly read-only |

The demo authorization model maintains strictly two application roles: `RESIDENT` and `HELPDESK`. Operational capabilities are enforced through granular permissions (`COMPLAINT_MANAGE`, `BANK_IMPORT`, `RECONCILIATION_REVIEW`, `COMMITTEE_REPORT_READ`). The Committee Dashboard is exposed within the authorized helpdesk portal with read-only reporting access.

### 2.2 Flat-Level Access Control for Residents
Residents can only query flat-level resources if:
1. They hold an approved record in `flat_memberships`.
2. For `TENANT` memberships: Current timestamp must be within `valid_from` and `valid_until`. If a lease expires, access stops immediately.
3. The flat belongs to the user's assigned society.

### 2.3 Cross-Society Multi-Tenant Isolation
All queries strictly enforce tenant boundaries through `society_id` scopes. Even though the initial deployment hosts a single township, the data architecture prevents cross-society data leakage.

---

## 3. Data Protection and Cryptography

- **Encryption at Rest**:
  - Supabase PostgreSQL storage encrypted at rest (AES-256).
  - SQS Queues and DLQs encrypted using AWS KMS Customer Managed Keys (CMK).
  - S3 Private Buckets enforce default SSE-KMS encryption.
- **Encryption in Transit**:
  - Enforced TLS 1.3 on all external endpoints (CloudFront and API Gateway).
  - Enforced TLS connections between Lambda functions and Supabase shared transaction pooler (`sslmode=require`).
  - Plain HTTP traffic is automatically redirected to HTTPS.
- **Secrets Management**:
  - Zero hardcoded passwords, database URIs, or API keys in source control.
  - Supabase transaction pooler connection strings and integration keys are stored in AWS Secrets Manager.
- **Row-Level Security (RLS)**:
  - Enabled across all PostgreSQL application tables as a secondary defense layer.

---

## 4. STRIDE Threat Model & Mitigations

| Threat Category | Potential Attack Vector | Applied Engineering Mitigation |
| :--- | :--- | :--- |
| **Spoofing** | Forged JWT tokens or spoofed caller identities | Strict ES256/RS256 asymmetric signature verification against Supabase JWKS; mock auth fails closed in prod |
| **Tampering** | Modifying flat IDs or roles in frontend payload | Backend resolves all roles and flat memberships from PostgreSQL system of record; client claims never trusted |
| **Repudiation** | Denying financial actions or data modifications | Append-only `audit_events` and CloudTrail logging recording actor, action, timestamp, and correlation ID |
| **Information Disclosure**| Cross-society data leakage or stack trace exposure | Standardized error format hiding raw exceptions; strict database tenant scoping on every endpoint |
| **Denial of Service** | Connection pool exhaustion from Lambda functions | Supabase PgBouncer transaction pooler (`prepare_threshold: None`); AWS WAF rate-limiting; SQS DLQ redrive policies |
| **Elevation of Privilege**| Unauthorized role or action escalation | Reusable `require_roles` dependencies enforcing granular RBAC barriers before handler execution |
