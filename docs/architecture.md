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
- **Decision**: Maintain strictly two application roles: `RESIDENT` and `HELPDESK`. Granular permissions within `HELPDESK` (`COMPLAINT_MANAGE`, `BANK_IMPORT`, `RECONCILIATION_REVIEW`, `COMMITTEE_REPORT_READ`, `BILLING_MANAGE`, `GATE_OPERATIONS`) govern operational actions. The Committee Dashboard is exposed inside the authorized helpdesk portal with read-only reporting capabilities, and Gate Tablet Operations (`/gate`) are restricted to staff with `GATE_OPERATIONS` and an active temporal gate assignment.
- **Consequences**: Prevents role explosion while ensuring complete auditability, role-aware routing, and strict tenant isolation.

### ADR 006: Strict Integer Paise Monetary Representation
- **Context**: Maintenance billing, sinking fund levies, and bank statement matching require financial precision.
- **Decision**: All financial amounts are stored as 64-bit BigInteger paise (1 INR = 100 paise). Floating-point data types (`FLOAT`, `REAL`, `DOUBLE PRECISION`) are prohibited in financial columns.
- **Consequences**: Eliminates IEEE 754 precision drift and rounding discrepancies in ledger audits.

### ADR 007: Concurrency-Safe Payment Allocation via Row Locking (`SELECT FOR UPDATE`) & Mandatory Idempotency
- **Context**: Multiple concurrent payment requests against the same invoice can cause race conditions where total allocated funds exceed the invoice's outstanding balance. Furthermore, duplicate submissions can cause duplicate payments without durable idempotency guarantees.
- **Decision**: Require `Idempotency-Key` header on all payment initiation requests. Reserve the key atomically via `INSERT ON CONFLICT` with request payload hash. Lock the invoice row using PostgreSQL `SELECT ... FOR UPDATE` inside a single atomic transaction. Recalculate allocations and outstanding balance after acquiring the row lock. Persist both successful and failed outcomes to the idempotency record. Commit invoice updates, payment records, allocations, append-only ledger entries, audit trails, and outbox events in a single atomic transaction.
- **Consequences**: Eliminates concurrent over-allocation race conditions, guarantees reproducible idempotent retries for both successful and failed payment attempts, and ensures financial consistency under high concurrency.

### ADR 008: Database-Enforced Financial Immutability & Composite Multi-Tenant Ownership
- **Context**: Relying solely on application-level conventions for financial ledger immutability and multi-tenant scoping allows potential corruption if direct database connections or queries execute updates or cross-tenant references.
- **Decision**: Install PostgreSQL database trigger `financial_ledger_immutable` preventing `UPDATE` and `DELETE` on `financial_ledger_entries`. Add composite unique constraint `(society_id, id)` on `flats`, and enforce composite foreign keys `(society_id, flat_id)` on `invoices`, `payments`, and `financial_ledger_entries` with `ON DELETE RESTRICT` on the ledger.
- **Consequences**: Eliminates risks of ledger mutation or cascading deletion of historical accounting journals, and guarantees multi-tenant database integrity at the PostgreSQL engine level.

### ADR 009: Event-Driven Multi-Channel Notifications & Resident Inbox
- **Context**: Operational events across Billing, Complaints, and Gate Visitors must reliably reach residents and staff without coupling core write paths to external dispatch latency.
- **Decision**: Persist outbox events inside domain write transactions. An outbox worker emits messages to SQS, triggering dedicated background workers that process channel preferences, manage retry backoffs with jitter, enforce emergency overrides, and populate an indexed in-app notification inbox.
- **Consequences**: Guarantees zero dropped alerts, complete delivery telemetry, observable retries, and clean PII protection.

### ADR 010: Concurrency-Safe Amenity Slot Booking & Capacity Model
- **Context**: Multiple residents concurrently reserving scarce township amenities (badminton/tennis courts, party halls, swimming pools) can cause race conditions leading to double bookings and capacity oversubscription.
- **Decision**: Model amenity slots as discrete time windows with configurable capacities. Booking requests acquire a row lock on the `Amenity` row (`SELECT ... FOR UPDATE`) within the database transaction, verify resident lease validity for the target booking date, and check that active bookings plus requested units do not exceed total capacity. All fees and refunds are calculated strictly in integer paise.
- **Consequences**: Eliminates double-booking race conditions, serializes conflicting slot requests cleanly, and guarantees invariant protection across both single-capacity and shared multi-capacity facilities.

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

---

## 6. Phase 6 — Gate Visitor Management, Offline Operations & 90-Day Photo Retention

### 6.1 Decoupled Approval & Entry State Machines
- **Approval State (`ApprovalStatus`)**: `PENDING` -> `APPROVED` | `REJECTED`, or `AUTO_APPROVED` (via verified Guest Pass redemption).
- **Physical Entry State (`EntryStatus`)**: `EXPECTED` -> `CHECKED_IN` -> `CHECKED_OUT`.
- **Invariant**: A gate guard cannot transition a visitor to `CHECKED_IN` unless `approval_status` is `APPROVED` or `AUTO_APPROVED`.

### 6.2 Offline-First Tablet Operation & Replay-Protected Synchronization
- **IndexedDB Queue (`TownshipGateDB`)**: When gate tablets lose network connectivity, walk-in visitor registrations and captured JPEG photographs are persisted locally in IndexedDB with stable UUIDv4 `client_event_id`s and canonical SHA-256 payload hashes.
- **Fail-Closed Offline Invariants**:
  - Offline visitor registrations always enter `PENDING` approval and `EXPECTED` entry status; offline capture never grants automatic entry.
  - Pre-approved guest pass (`GP-XXXX`) verification fails closed while offline to prevent replay of revoked or exhausted passes.
- **Batch Sync (`POST /api/v1/gate/sync`)**: Processes reconnection batches using nested database savepoints so a single malformed or tampered event (`409 CONFLICT_EVENT_PAYLOAD_MODIFIED`) never aborts valid events in the same batch.

### 6.3 Visitor Photo Privacy & Mandatory 90-Day Retention
- **Private Storage & Short-Lived Presigned URLs**: Visitor photos are stored under `visitor-photos/{society_id}/{year}/{month}/{visitor_id}.jpg` in the private KMS-encrypted S3 bucket and served exclusively via 15-minute presigned URLs to authorized flat residents or on-duty gate staff.
- **Defense-in-Depth 90-Day Retention**:
  1. Logical 90-day cutoff in `PhotoRetentionService` immediately blocks expired photo access with `410 PHOTO_EXPIRED`.
  2. Daily batch worker (`purge_expired_photos`) deletes expired S3 objects and scrubs `photo_s3_key` in PostgreSQL.
  3. AWS CDK S3 lifecycle rule (`VisitorPhotos90DayRetention`) enforces a hard 90-day storage expiration on `visitor-photos/`.

---

## 7. Phase 7 — Event-Driven Notifications & Resident Communication

### 7.1 Asynchronous Transactional Architecture
- **Atomic Event Generation**: Core business operations in Billing, Complaints, and Gate emit domain events directly into the `outbox_events` table within the primary database transaction. No external HTTP or API calls are ever made synchronously inside business workflows.
- **SQS Fan-Out & Dedicated Worker**: The scheduled Outbox publisher publishes pending outbox events into the SQS `notification-jobs` queue with deduplication and correlation IDs.
- **Dedicated Notification Worker (`app/workers/notification_worker.py`)**: Asynchronously consumes events from SQS and invokes `NotificationService.process_domain_event()`.

### 7.2 Multi-Channel Delivery State Machine
Every dispatch attempt across In-App, Email, and SMS is modeled with strict state transitions:
`PENDING` -> `PROCESSING` -> `SENT` | `DELIVERED` | `RETRYING` | `FAILED` | `SUPPRESSED`
- **In-App Delivery**: Persisted immediately to `notifications` and associated with a `DELIVERED` delivery record.
- **Email & SMS Delivery**: Evaluated against user channel preferences and dispatched through the provider abstraction layer.
- **Transient vs Permanent Failure Handling**:
  - Transient errors (e.g. AWS SES/SNS throttling, temporary connection drops) transition to `RETRYING`, increment `attempt_count`, and schedule exponential backoff: `backoff_seconds = (2 ^ attempt_count) * 10 + jitter(1..5)`.
  - Permanent errors (e.g. invalid recipient address, account suspended) transition immediately to `FAILED` without retrying.

### 7.3 Security, Privacy & Compliance Invariants
1. **PII Masking**: Email addresses and phone numbers are strictly sanitized in application logs and trace metadata (`mask_email()`, `mask_phone()`).
2. **Mock Provider Fail-Closed**: In test and unconfigured environments, `MockEmailProvider` and `MockSMSProvider` record dispatch attempts in memory for verification but return `SUPPRESSED` with `MOCK_PROVIDER_EXTERNAL_DELIVERY_DISABLED`, never falsely claiming external delivery.
3. **Mandatory Emergency Override**: Critical safety escalations (`complaint.safety_escalated`, `URGENT` priority) bypass user opt-out preferences and guarantee delivery across all active channels to both residents and helpdesk staff.
4. **Internal Helpdesk Isolation**: Private internal helpdesk notes are strictly excluded from resident notification bodies.
5. **Least-Privilege IAM**: SES and SNS publishing permissions (`ses:SendEmail`, `ses:SendRawEmail`, `sns:Publish`) are granted exclusively to the background worker Lambda execution role. API, Outbox, and Retention Lambda roles have zero notification provider access.

---

## 8. Phase 8 — Amenity & Clubhouse Booking Management System

### 8.1 Domain Entities & Multi-Tenant Separation
- **Amenities (`amenities`)**: Configurable township facilities (badminton courts, tennis courts, clubhouse lounge, community halls, swimming pool, gym). Tracks capacity, slot duration, operating hours, booking fees in integer paise, advance booking limits, cancellation deadlines, and permitted membership types (`OWNER`, `TENANT`, `FAMILY_MEMBER`).
- **Amenity Bookings (`amenity_bookings`)**: Discrete reservations linked to authenticated residents, flats, and time slots. Lifecycle managed through strict state machine (`PENDING_PAYMENT`, `CONFIRMED`, `CANCELLED`, `COMPLETED`, `PAYMENT_FAILED`).
- **Amenity Maintenance Blocks (`amenity_blocks`)**: Temporal staff-created blocks for routine maintenance, private repairs, or society functions that mask capacity and reject booking attempts (`409 SLOT_BLOCKED`).
- **Tenant Isolation**: Every query and database transaction strictly scopes records by `society_id`. Residents cannot view or reserve amenities outside their registered society.

### 8.2 Concurrency Safety & Overbooking Prevention
- **Row-Level Transaction Locking**: During booking creation, the amenity row is locked using PostgreSQL `SELECT ... FOR UPDATE` (or SQLite serialized lock). Active confirmed and unexpired pending reservations are tallied against total capacity before admitting a new booking.
- **Race Condition Immunity**: Parallel concurrent attempts on final capacity serialize cleanly; one succeeds (`201 Created` / `CONFIRMED`) and competing attempts receive `409 Conflict` with `CAPACITY_EXCEEDED`.
- **Daily Quota Enforcement**: `max_slots_per_day_per_resident` prevents slot hoarding, ensuring fair township access across all 2,400 apartments.

### 8.3 Payment Integration & Fee Immutability
- **Integer Paise Arithmetic**: All booking fees, payments, and refunds are calculated and stored strictly in 64-bit integer paise (e.g. ₹150.00 = 15000 paise).
- **Payment Lifecycle & Idempotency**:
  - Unpaid bookings enter `PENDING_PAYMENT` with a 15-minute lock (`payment_expires_at`).
  - Payments are processed through the existing `PaymentProvider` abstraction (`SimulatedPaymentProvider` in test/staging).
  - Every payment submission accepts a client-provided `Idempotency-Key` preventing double charges or duplicate allocations on retries or delayed callbacks.
  - Expired or failed payments transition bookings to `PAYMENT_FAILED` and release capacity.
- **Historical Fee Immutability**: Staff fee adjustments (e.g., updating court fee from ₹150 to ₹250) only affect future reservations. Existing bookings retain their historical `booking_fee_paise` and payment records.

### 8.4 Cancellation Policies & Refund Rules
- **Resident Self-Service Cancellation**: Permitted only prior to `cancellation_deadline_hours` (e.g., 2 hours before slot start). Applies configured `refund_percentage` (e.g., 80% refund). Expired deadlines fail with `409 CANCELLATION_DEADLINE_EXPIRED`.
- **Staff Operational Override**: Facility staff can cancel bookings at any time with an explicit operational reason (e.g., emergency plumbing, power outage). Staff cancellations automatically issue a 100% full refund and record an audit trail.

### 8.5 Transactional Outbox & Audit Logging
All booking creations, confirmations, cancellations, and payment failures emit transactional outbox events (`amenity.booking_created`, `amenity.booking_confirmed`, `amenity.booking_cancelled`, `amenity.booking_payment_failed`) and audit log records (`AMENITY_BOOKING_CREATED`, `AMENITY_BOOKING_CONFIRMED`, `AMENITY_BOOKING_CANCELLED`, `AMENITY_BLOCK_CREATED`, `AMENITY_BLOCK_DELETED`) within the same atomic transaction as the state change.



