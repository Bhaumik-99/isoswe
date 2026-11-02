# Application Security & Threat Model Specification

## 1. Authentication Architecture

### 1.1 Amazon Cognito Integration (Production & Staging)
- **Token Verification**: Tokens are validated using maintained cryptographic libraries (`pyjwt` with `cryptography`) and the Cognito User Pool JWKS endpoint (`/.well-known/jwks.json`).
- **Validation Criteria**:
  1. Cryptographic RSA-256 signature verification using rotating public keys cached from JWKS.
  2. Issuer assertion: `iss` must strictly match `https://cognito-idp.{region}.amazonaws.com/{user_pool_id}`.
  3. Audience / client check: `aud` or `client_id` must match `settings.COGNITO_APP_CLIENT_ID`.
  4. Expiry validation: `exp` must be in the future.
  5. Token usage validation: `token_use` must be either `"id"` or `"access"`.
  6. Subject resolution: `sub` is mapped to an internal application user in PostgreSQL.
- **Resident OTP Flow**: Passwordless authentication via SMS and Email OTP challenges.
- **Privileged MFA**: Mandatory Multi-Factor Authentication (TOTP / SMS) enforced for helpdesk accounts.

### 1.2 Local Development Mock Identity Provider
- **Purpose**: Enables local offline development and automated CI testing without live AWS Cognito dependencies.
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
| `RESIDENT` | Flat Memberships | View assigned unit details, view maintenance invoices, make payments, lodge complaints | Cannot access other resident units or financial admin operations |
| `HELPDESK` | Assigned Society | Complaint assignment and status, bank statement import, reconciliation review, read-only committee reporting | Cannot access another society; committee reporting is read-only |

The assignment's demo authentication model has exactly two application roles: `RESIDENT` and `HELPDESK`. The Committee Dashboard is exposed inside the authorized helpdesk application and grants reporting access only; it is not a separate user role. Operational capabilities are granular permissions within HELPDESK.

### 2.2 Flat-Level Access Control for Residents
Residents can only query flat-level resources if:
1. They hold an approved record in `flat_memberships`.
2. For `TENANT` memberships: Current timestamp must be within `valid_from` and `valid_until`. If a lease expires, access stops immediately.
3. The flat belongs to the user's assigned society.

### 2.3 Cross-Society Multi-Tenant Isolation
All queries strictly enforce tenant boundaries through `society_id` scopes. Even though the initial deployment hosts a single township, the data architecture ensures zero cross-society data leakage.

---

## 3. Data Protection and Cryptography

- **Encryption at Rest**:
  - PostgreSQL RDS storage encrypted using AWS KMS Customer Managed Keys (CMK).
  - SQS Queues and DLQs encrypted using KMS CMK.
  - S3 Private Buckets enforce default SSE-KMS encryption.
- **Encryption in Transit**:
  - Enforced TLS 1.3 on all external endpoints (CloudFront and API Gateway).
  - Enforced TLS connections between Lambda functions and PostgreSQL / RDS Proxy.
  - Plain HTTP traffic is automatically redirected to HTTPS.
- **Secrets Management**:
  - Zero hardcoded passwords, database URIs, or API keys in source control.
  - Production database credentials managed and rotated via AWS Secrets Manager.

---

## 4. STRIDE Threat Model & Mitigations

| Threat Category | Potential Attack Vector | Applied Engineering Mitigation |
| :--- | :--- | :--- |
| **Spoofing** | Forged JWT tokens or spoofed caller identities | Strict RSA-256 signature verification against Cognito JWKS; mock auth fails closed in prod |
| **Tampering** | Modifying flat IDs or roles in frontend payload | Backend resolves all roles and flat memberships from PostgreSQL system of record; client claims never trusted |
| **Repudiation** | Denying financial actions or data modifications | Append-only `audit_events` and CloudTrail logging recording actor, action, timestamp, and correlation ID |
| **Information Disclosure**| Cross-society data leakage or stack trace exposure | Standardized error format hiding raw exceptions; strict database tenant scoping on every endpoint |
| **Denial of Service** | Connection pool exhaustion from Lambda functions | Amazon RDS Proxy connection pooling; AWS WAF rate-limiting; SQS DLQ redrive policies |
| **Elevation of Privilege**| Helpdesk staff attempting billing or ledger updates | Reusable `require_roles` dependencies enforcing granular RBAC barriers before handler execution |
