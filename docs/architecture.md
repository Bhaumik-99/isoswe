# Software and Cloud Infrastructure Architecture

## 1. Architectural Foundation & Separation of Concerns

The township operations platform adheres to a strict architectural principle:
- **Supabase** owns user identity (Phone OTP authentication) and persistent relational data storage (PostgreSQL).
- **AWS** owns serverless application execution (Lambda, API Gateway), asynchronous event queues (Amazon SQS + DLQs), file storage (Amazon S3), CDN (CloudFront), and operational security (WAF, KMS, Secrets Manager, CloudWatch).
- **FastAPI** owns core business rules, transactional authorization, and financial correctness.

---

## 2. Architectural Decision Records (ADRs)

### ADR 001: Supabase Auth & PostgreSQL with AWS Serverless (Option B)
- **Context**: The platform serves 2,400 flats, 28 towers, and 180 facility staff in Pune, India. Managing duplicate authentication and database systems (Cognito + RDS) introduces unnecessary complexity and high fixed networking costs (such as NAT Gateways).
- **Decision**: Adopt Supabase Auth (Phone OTP) and Supabase PostgreSQL in region `ap-south-1` (Mumbai) alongside AWS Serverless compute (FastAPI on AWS Lambda) and asynchronous messaging (Amazon SQS). Remove Amazon Cognito and AWS RDS. Lambda connects to Supabase PostgreSQL over TLS via its shared transaction pooler (port 6543 / PgBouncer), eliminating the need for expensive VPC NAT Gateways.
- **Consequences**: Zero lost messages, minimal operational overhead, native phone OTP authentication, enterprise connection pooling via PgBouncer, and predictable cloud expenditure.

### ADR 002: Supabase Shared Transaction Pooler & Psycopg 3 Engine Configuration
- **Context**: AWS Lambda's ephemeral, highly concurrent execution model can overwhelm PostgreSQL connection limits without connection pooling. Supabase provides a built-in transaction pooler powered by PgBouncer.
- **Decision**: Connect SQLAlchemy using Psycopg 3 to the Supabase shared transaction pooler (port 6543) with `sslmode=require`, `prepare_threshold=None` (disabling prepared statements for transaction pooling mode), `pool_size=1`, and `max_overflow=0`. The engine is instantiated at module scope so warm Lambda containers can reuse connections efficiently.
- **Consequences**: Guarantees stable database connectivity without running out of connection slots, prevents prepared statement caching conflicts, and maintains low latency.

### ADR 003: Asymmetric Supabase JWT Verification with No Email Fallback
- **Context**: Security tokens issued by Supabase Auth must be validated on every request by FastAPI without round-tripping to Supabase APIs on each request.
- **Decision**: Implement `SupabaseJwtVerifier` using asymmetric public keys from the Supabase JWKS endpoint (`/auth/v1/.well-known/jwks.json`). Enforce ES256/RS256 signature verification, strict issuer validation (`{SUPABASE_URL}/auth/v1`), audience verification (`authenticated`), and expiration check. User records are strictly queried by `supabase_uid` UUID (`auth.users.id`). Never fall back to email as an authentication identity.
- **Consequences**: Eliminates impersonation risks, supports automated key rotation, and strictly respects tenant identity.

### ADR 004: Reliable Asynchronous Messaging via Transactional Outbox
- **Context**: Actions such as invoice generation, payment receipts, AI complaint processing, and SMS notifications require reliable execution without blocking HTTP responses or risking dual-write inconsistencies.
- **Decision**: Implement the Transactional Outbox pattern paired with Amazon SQS standard queues and dedicated Dead Letter Queues (DLQs). Business changes and outbox records commit within the exact same database transaction. An outbox worker dispatches events using `SELECT ... FOR UPDATE SKIP LOCKED`.
- **Consequences**: Guarantees zero lost messages if SQS or the network is temporarily degraded. Consumers use the `processed_events` registry for idempotent exactly-once processing.

### ADR 005: Two-Role Application Model with Granular Permissions
- **Context**: The township operations platform specification identifies two primary application roles: `RESIDENT` and `HELPDESK`. Managing committee members require governance visibility into society metrics, billing totals, and audit trails without requiring a separate user role.
- **Decision**: Maintain strictly two application roles: `RESIDENT` and `HELPDESK`. Granular permissions within `HELPDESK` (`COMPLAINT_MANAGE`, `BANK_IMPORT`, `RECONCILIATION_REVIEW`, `COMMITTEE_REPORT_READ`) govern operational actions. The Committee Dashboard is exposed inside the authorized helpdesk portal with read-only reporting capabilities.
- **Consequences**: Prevents role explosion while ensuring complete auditability, role-aware routing, and strict tenant isolation.

### ADR 006: Strict Integer Paise Monetary Representation
- **Context**: Maintenance billing, sinking fund levies, and bank statement matching require financial precision.
- **Decision**: All financial amounts are stored as 64-bit BigInteger paise (1 INR = 100 paise). Floating-point data types (`FLOAT`, `REAL`, `DOUBLE PRECISION`) are prohibited in financial columns.
- **Consequences**: Eliminates IEEE 754 precision drift and rounding discrepancies in ledger audits.

---

## 3. System Architecture Diagram

```mermaid
flowchart TB
    subgraph Clients ["Client Tier"]
        Browser["Resident & Staff Web App (React / Vite / TypeScript)"]
    end

    subgraph Supabase ["Supabase Cloud (ap-south-1 Mumbai)"]
        SupabaseAuth["Supabase Auth<br/>(Phone OTP & JWKS)"]
        TxPooler["Supabase Transaction Pooler<br/>(PgBouncer Port 6543)"]
        PostgreSQL[("Supabase PostgreSQL<br/>(Application Schema + RLS)")]
        TxPooler --> PostgreSQL
    end

    subgraph AWS ["Amazon Web Services (ap-south-1 Mumbai)"]
        subgraph Edge ["Edge & Perimeter Security"]
            CF["Amazon CloudFront CDN (TLS 1.3)"]
            WAF["AWS WAF (SQLi, OWASP Top 10)"]
            S3Web["Private S3 Bucket (Static Web Assets)"]
            CF --> S3Web
        end

        subgraph Ingress ["API Gateway Tier"]
            APIGW["Amazon API Gateway (REST API)"]
            WAF -.->|Inspects & Filters| APIGW
        end

        subgraph Serverless ["Serverless Compute Tier (AWS Lambda)"]
            ApiLambda["FastAPI Lambda (Mangum)<br/>pool_size=1, prepare_threshold=None"]
            WorkerLambda["SQS Worker Lambda<br/>Idempotent Consumer"]
            APIGW -->|Proxies Requests| ApiLambda
        end

        subgraph SQS ["Asynchronous Messaging Tier"]
            Q1["billing-jobs + DLQ"]
            Q2["payment-events + DLQ"]
            Q3["reconciliation-jobs + DLQ"]
            Q4["complaint-ai-jobs + DLQ"]
            Q5["notification-jobs + DLQ"]
        end

        subgraph SecurityTier ["Security & Secrets"]
            KMS["AWS KMS Master Key"]
            Secrets["AWS Secrets Manager<br/>(DATABASE_URL & Keys)"]
            CloudWatch["Amazon CloudWatch Logs & Metrics"]
            CloudTrail["AWS CloudTrail Audit Trail"]
        end

        subgraph Storage ["Document Storage"]
            S3Docs["Private S3 Bucket (Receipts & Statements)"]
        end
    end

    Browser -->|HTTPS| CF
    Browser -->|Phone OTP Authentication| SupabaseAuth
    Browser -->|API Requests with Bearer JWT| APIGW
    ApiLambda -->|Verify JWT via Cached JWKS| SupabaseAuth
    ApiLambda -->|TLS Connection (PgBouncer)| TxPooler
    WorkerLambda -->|TLS Connection (PgBouncer)| TxPooler

    ApiLambda -->|Fetch Credentials| Secrets
    ApiLambda -->|Enqueues Outbox Events| Q1 & Q2 & Q3 & Q4 & Q5
    Q1 & Q2 & Q3 & Q4 & Q5 -->|Batch Trigger| WorkerLambda

    ApiLambda -->|Upload / Download Files| S3Docs
    KMS -.->|Encrypts at Rest| S3Docs
    KMS -.->|Encrypts at Rest| Q1 & Q2 & Q3 & Q4 & Q5
    KMS -.->|Encrypts Secrets| Secrets
```

---

## 4. Asynchronous Queue Architecture

All five core asynchronous flows run over dedicated Amazon SQS queues with paired Dead Letter Queues (DLQs) and KMS CMK encryption:

| Queue Name | Purpose | DLQ Name | Max Receive Count |
| :--- | :--- | :--- | :--- |
| `township-billing-jobs-{env}` | Monthly maintenance batch bill generation | `township-billing-jobs-dlq-{env}` | 3 (dev) / 5 (prod) |
| `township-payment-events-{env}` | Razorpay webhook processing & ledger credit | `township-payment-events-dlq-{env}` | 3 (dev) / 5 (prod) |
| `township-reconciliation-jobs-{env}` | Bank statement parser & auto-reconciliation | `township-reconciliation-jobs-dlq-{env}` | 3 (dev) / 5 (prod) |
| `township-complaint-ai-jobs-{env}` | Bedrock ticket categorization & routing | `township-complaint-ai-jobs-dlq-{env}` | 3 (dev) / 5 (prod) |
| `township-notification-jobs-{env}` | Resident payment reminders & alert dispatch | `township-notification-jobs-dlq-{env}` | 3 (dev) / 5 (prod) |

---

## 5. Phase 2 — Maintenance Billing & Simulated Payment Architecture

### Domain Layer Separation of Concerns
1. **Billing Domain Service (`app/domains/billing/service.py`)**:
   - Authoritative business engine for society monthly billing preview, execution, and ledger entry creation.
   - Enforces integer paise arithmetic: `maintenance_paise = area_sqft * 650` (₹6.50/sq ft).
   - Dynamically evaluates effective invoice status (`UNPAID`, `PARTIALLY_PAID`, `PAID`, `OVERDUE`, `VOID`) based on due dates and allocated payments.
   - Emits transactional audit (`audit_events`) and outbox (`outbox_events`) events atomically with financial mutations.

2. **Billing Repository (`app/domains/billing/repository.py`)**:
   - Encapsulates database queries for invoices, line items, payments, allocations, ledger entries, and billing runs.
   - Preserves society-level tenant scoping and membership validation.

3. **Payment Provider Interface (`app/domains/billing/provider.py`)**:
   - `PaymentProvider` abstract base class defining `process_payment(request: PaymentRequest) -> ProviderPaymentResult`.
   - `SimulatedPaymentProvider`: Local development implementation supporting deterministic success and controlled failure simulation for testing.
   - **Future Integration Boundary**: To integrate live Razorpay or Stripe in later phases, an implementation of `PaymentProvider` (e.g. `RazorpayPaymentProvider`) is injected without altering billing calculation or ledger accounting business logic.

4. **Append-Only Financial Ledger Invariant**:
   - Every invoice generation appends a `CHARGE` entry to `financial_ledger_entries`.
   - Every successful payment appends `PAYMENT_RECEIVED` and `PAYMENT_ALLOCATED` entries.
   - No financial records are ever edited or deleted. Reversals or adjustments must be recorded as explicit compensating entries referencing original records.

