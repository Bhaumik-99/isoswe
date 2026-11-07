# Township Operations Platform (`township-ops`)

[![Continuous Integration](https://github.com/Bhaumik-99/isoswe/actions/workflows/ci.yml/badge.svg)](https://github.com/Bhaumik-99/isoswe/actions/workflows/ci.yml)
[![Security Policy](https://img.shields.io/badge/Security-Fail--Closed-green.svg)](docs/security.md)
[![Database](https://img.shields.io/badge/Database-Supabase%20PostgreSQL-3ECF8E.svg)](docs/database.md)
[![Compute](https://img.shields.io/badge/Compute-AWS%20Serverless%20Lambda-FF9900.svg)](docs/architecture.md)

Production-grade technical engineering foundation for a multi-tenant **Society Operations Platform** serving gated townships in Pune, India.

---

## 1. Product Context & Operational Scale

The platform is designed to operate:
- **2,400 apartments** across **28 residential towers**.
- **180 facility-management staff** and technicians.
- **Residents Federation** governance and committee auditing.
- Automated monthly maintenance formula calculations (₹6.50/sq ft + sinking funds).
- Digital payment collections and daily bank statement reconciliation.
- Facility helpdesk ticket lifecycle with AI classification.

### Core User Roles
1. `RESIDENT`: Apartment owner or tenant with access strictly restricted to approved flats and non-expired tenancy dates.
2. `HELPDESK`: Facility management desk handling technician dispatch, status management, bank statement import, reconciliation review, and read-only committee reporting.

*Note: The platform demo model strictly implements two application roles (`RESIDENT` and `HELPDESK`). Committee reporting is accessible inside the authorized helpdesk portal with read-only permissions.*

---

## 2. Technology Stack (Option B: Supabase + AWS Serverless)

| Component | Selected Technology | Notes |
| :--- | :--- | :--- |
| **Frontend** | React + TypeScript + Vite | Tailwind CSS, Lucide React, TanStack Query v5 |
| **Authentication** | Supabase Auth | Passwordless Phone OTP via official `@supabase/supabase-js` |
| **Primary Database** | Supabase PostgreSQL | Region `ap-south-1` (Mumbai), Row-Level Security enabled |
| **Backend Framework** | FastAPI + Python 3.11+ | Pydantic v2, Mangum adapter for AWS Lambda |
| **ORM & Driver** | SQLAlchemy 2.0 + Psycopg 3 | Shared transaction pooler, `prepare_threshold=None` |
| **Migrations** | Alembic | Version-controlled, zero runtime `create_all()` |
| **API Hosting** | AWS Lambda | Serverless execution, direct TLS to Supabase (no NAT GW) |
| **API Gateway** | Amazon API Gateway | REST API with AWS WAF integration |
| **Messaging** | Amazon SQS | 5 domain queues with dedicated Dead Letter Queues (DLQs) |
| **File Storage** | Amazon S3 | Private buckets with Origin Access Control |
| **CDN** | Amazon CloudFront | TLS 1.3 edge distribution |
| **Security & Secrets** | AWS WAF + KMS + Secrets Manager | CMK encryption at rest, connection strings in Secrets Manager |
| **Monitoring** | Amazon CloudWatch + CloudTrail | Structured JSON logs and compliance audit trail |
| **Infrastructure as Code** | AWS CDK | Modular Python constructs for dev, staging, and prod |
| **CI/CD** | GitHub Actions | Automated lint, typing, tests, build, and CDK synth |

---

## 3. Repository Organization

```text
township-ops/
│
├── apps/
│   └── web/                     # React + TypeScript + Vite frontend application
│       ├── src/
│       │   ├── app/             # Application entrypoint & QueryClient provider
│       │   ├── components/      # Accessible UI components (Button, Card, Alert, etc.)
│       │   ├── features/        # Auth, Resident, Staff, and Committee views
│       │   ├── layouts/         # Auth, Resident, Staff, and Committee layouts
│       │   ├── routes/          # Role-based route guards and path definitions
│       │   ├── services/        # Supabase Auth adapter & central API client
│       │   └── types/           # Domain and API response TypeScript contracts
│       ├── package.json
│       └── vite.config.ts
│
├── services/
│   └── api/                     # FastAPI backend modular monolith
│       ├── app/
│       │   ├── core/            # Config, database engine, logging, security, errors
│       │   ├── domains/         # Domain models, schemas, repositories, services
│       │   │   ├── identity/    # Societies, Towers, Flats, Memberships, Roles
│       │   │   ├── reliability/ # AuditEvents, OutboxEvents, IdempotencyKeys
│       │   │   └── billing/     # Domain boundaries stubbed for future phases
│       │   ├── integrations/    # Supabase JWT verifier & local mock auth provider
│       │   ├── messaging/       # SQS & Local queue publishers, outbox worker, consumer
│       │   ├── workers/         # Platform health check worker & background runner
│       │   ├── middleware/      # Correlation ID, Request ID & structured logger
│       │   └── handlers/        # Mangum Lambda API handler & SQS Lambda trigger
│       ├── migrations/          # Alembic versioned migrations (001, 002)
│       └── tests/               # Unit and integration test suites
│
├── infra/
│   └── cdk/                     # AWS CDK Python infrastructure
│       ├── app.py               # CDK app entrypoint
│       ├── stacks/              # TownshipStack primary composition
│       ├── township_constructs/ # Reusable SQS, S3, Compute, Security, ApiGateway
│       ├── environments/        # Dev, Staging, and Production configurations
│       └── tests/               # Infrastructure unit tests
│
├── scripts/
│   ├── seed.py                  # Idempotent synthetic township seed script
│   └── generate_sample_data.py  # Scale generator for 28 towers and 2,400 flats
│
├── docs/
│   ├── architecture.md          # Architecture decisions, Mermaid diagrams, flows
│   ├── security.md              # Auth, RBAC, tenant isolation, STRIDE threat model
│   ├── database.md              # Mermaid ERD, table specs, integer paise monetary rule
│   └── development.md           # Setup, environment variables, local testing
│
├── .github/
│   └── workflows/
│       ├── ci.yml               # Automated CI (lint, typecheck, pytest, build, audit)
│       └── codeql.yml           # CodeQL advanced SAST analysis
│
├── docker-compose.yml           # PostgreSQL, API, Worker, and Web frontend
├── .env.example                 # Clean environment variable template
├── .gitignore                   # Multi-tier gitignore
├── Makefile                     # Standard developer commands
└── README.md
```

---

## 4. Quick Start (Local Development)

### Option A: One-Command Docker Startup
```bash
docker compose up --build
```
Access the application:
- **Web App**: http://localhost:5173
- **API Server**: http://localhost:8000
- **Swagger Documentation**: http://localhost:8000/docs
- **Health Live Probe**: http://localhost:8000/health/live
- **Health Ready Probe**: http://localhost:8000/health/ready

### Option B: Native Host Execution
```bash
# 1. Install dependencies
make setup

# 2. Run database migrations
make migrate

# 3. Seed synthetic data idempotently
make seed

# 4. Run automated test suite
make test
```

---

## 5. Seed Personas & Demo Billing Scenarios

The database is seeded idempotently with real financial scenarios matching Marvel Greenfield Residences, Pune:
- **Neeraj Kulkarni** (`dev-token-neeraj`): Resident & Owner of **T07-1203** (1,150 sq ft). Monthly maintenance: **₹7,475.00** (747,500 paise), status: `UNPAID`.
- **Swati Joshi** (`dev-token-swati`): Resident & Tenant of **T12-0408** (980 sq ft). Monthly maintenance: **₹6,370.00** (637,000 paise), 47 days overdue, status: `OVERDUE`.
- **Aamir Shaikh** (`dev-token-aamir`): Resident & Owner of **T21-1601** (1,640 sq ft). Monthly maintenance: **₹10,660.00** (1,066,000 paise), with **₹5,000.00** paid and **₹5,660.00** remaining balance, 18 days overdue, status: `PARTIALLY_PAID` / `OVERDUE`.
- **Rajesh Shinde** (`dev-token-helpdesk`): Facility management staff (`HELPDESK`), authorized for society billing runs, overview monitoring, and committee reporting.

---

## 6. Phase 2 — Maintenance Billing & Payment Foundation

### Financial Formula & Invariants
- **Monthly Maintenance Calculation**:
  $$\text{Maintenance (paise)} = \text{Area (sq ft)} \times 650 \quad (\text{₹}6.50/\text{sq ft})$$
- **Monetary Precision**: All monetary values are strictly stored as `BIGINT` integer paise (1 INR = 100 paise). Zero floating-point arithmetic.
- **Append-Only Financial Ledger**: `financial_ledger_entries` is strictly append-only. No financial records are ever updated or deleted. Corrections are applied through explicit compensating reversal or adjustment entries.
- **Derived Outstanding Balance**:
  $$\text{Outstanding} = \text{Invoice Total} - \sum \text{Valid Payment Allocations}$$
  Payments do not overwrite invoice balances directly; invoice status and remaining balance are dynamically derived from validated allocations where `payment.status == 'SUCCESS'`.
- **Simulated Payment Engine**: Uses `PaymentProvider` interface with `SimulatedPaymentProvider` for demonstration. Supports controlled success/failure outcomes, duplicate submission protection via `Idempotency-Key` headers, and atomic transactional allocations.

### API Endpoints
| Method | Endpoint | Access | Purpose |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/billing/me/summary` | Resident | Live outstanding balance, invoice counts, and next due date |
| `GET` | `/api/v1/billing/me/invoices` | Resident | List invoices for authorized active flat memberships |
| `GET` | `/api/v1/billing/me/payments` | Resident | Payment history and allocation details |
| `GET` | `/api/v1/billing/invoices/{id}` | Resident / Helpdesk | Detailed invoice with line items and allocations |
| `GET` | `/api/v1/billing/invoices/{id}/receipt` | Authorized User | Official payment receipt for allocated invoice |
| `POST` | `/api/v1/billing/invoices/{id}/payments` | Resident | Initiate simulated payment (supports full or partial payment) |
| `GET` | `/api/v1/billing/payments/{id}` | Authorized User | Payment status and allocation breakdown |
| `GET` | `/api/v1/billing/staff/overview` | Helpdesk | Society-wide billed, collected, outstanding, and overdue totals |
| `GET` | `/api/v1/billing/staff/invoices` | Helpdesk | Search and filter society invoices by tower, flat, period, status |
| `POST` | `/api/v1/billing/staff/runs/preview` | Helpdesk | Preview eligible units, expected charges, and excluded units |
| `POST` | `/api/v1/billing/staff/runs` | Helpdesk | Execute monthly batch billing run (conflict-safe and idempotent) |
| `GET` | `/api/v1/billing/staff/runs/{id}` | Helpdesk | Inspect billing run execution summary and audit metadata |

---

## 7. Phase 3 — Complaints Management, Helpdesk Operations & AI Triage

### Core Capabilities
- **Deterministic Multilingual Safety Escalation & Priority Lock**: Immediate detection of fire, gas leaks, lift entrapments, electrical sparking, and structural collapse across English, Hindi, and Marathi. Flags `safety_escalated = True` and locks priority to `CRITICAL` before AI classification; API strictly rejects downgrades below `CRITICAL`.
- **Asynchronous AI Triage (Google Gemini)**: Complaint submission returns immediately with `ai_status = PENDING`. Background worker executes `gemini-2.5-flash` with structured JSON schema (`responseSchema`), prompt injection defenses, resident PII minimization, and deterministic offline fallback.
- **Worker Reliability & Lock Freedom**: Atomic job claiming marks `PROCESSING` and releases DB locks prior to calling Gemini. Transient network errors re-raise `RetryableWorkerError` preventing message loss in SQS, while permanent errors acknowledge poison messages without re-raising. Active leases (300s) and bounded retries (3 attempts) ensure safe concurrent execution and crash recovery.
- **Resident Privacy & Data Minimization**: Multi-lingual redaction (`minimize_resident_data()`) sanitizes phone numbers (including Devnagari numerals), emails, flat/tower codes, postal PIN codes, resident names in English, Hindi, and Marathi, and credentials before dispatch.
- **Configurable SLA Policies**: Strict deadlines calculated from creation time (Critical: 5m first response, 2h resolution; High: 30m/8h; Medium: 4h/48h; Low: 12h/5d). Priority changes dynamically recalculate resolution deadlines.
- **Workload-Based Auto-Assignment**: Assigns newly triaged tickets to active helpdesk staff with the lowest open ticket count in the society.
- **Privacy Separation**: Strict isolation between public resident conversations and private internal helpdesk notes.
- **Strict Storage Metadata Verification**: S3/Mock storage enforces exact declared-vs-actual size equality (zero tolerance), non-empty files, 5MB limits, and rejects missing or mismatched ContentType headers. Frontend validates presigned PUT HTTP status before completion.

### Complaints API Endpoints
| Method | Endpoint | Access | Purpose |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/complaints` | Resident | Raise new complaint (triggers safety check, AI triage & assignment) |
| `GET` | `/api/v1/complaints/me` | Resident | List complaints for resident's authorized flats |
| `GET` | `/api/v1/complaints/me/{id}` | Resident | Inspect ticket details, public comments, and status |
| `POST` | `/api/v1/complaints/me/{id}/comments` | Resident | Add public comment or message to facility staff |
| `POST` | `/api/v1/complaints/me/{id}/attachments`| Resident | Request presigned upload URL for photo attachment (max 5MB) |
| `POST` | `/api/v1/complaints/me/{id}/attachments/{att_id}/complete`| Resident | Complete and verify uploaded photo attachment |
| `POST` | `/api/v1/complaints/me/{id}/reopen` | Resident | Reopen resolved ticket within 7-day window |
| `POST` | `/api/v1/complaints/me/{id}/rating` | Resident | Submit satisfaction rating (1-5 stars) and feedback |
| `GET` | `/api/v1/complaints/helpdesk/dashboard` | Helpdesk | Operational KPI metrics (counts, overdue SLA, turnaround averages) |
| `GET` | `/api/v1/complaints/helpdesk` | Helpdesk | Multi-filter ticket search (category, priority, tower, SLA breaches) |
| `GET` | `/api/v1/complaints/helpdesk/{id}` | Helpdesk | Full ticket view with duplicate candidates and internal notes |
| `PATCH` | `/api/v1/complaints/helpdesk/{id}/status` | Helpdesk | Advance lifecycle state machine (records first response & resolution) |
| `PATCH` | `/api/v1/complaints/helpdesk/{id}/assign` | Helpdesk | Assign or reassign ticket to active staff member |
| `PATCH` | `/api/v1/complaints/helpdesk/{id}/priority` | Helpdesk | Adjust priority and automatically recalculate SLA targets (safety locked) |
| `POST` | `/api/v1/complaints/helpdesk/{id}/comments` | Helpdesk | Add public resident reply or private internal helpdesk note |
| `POST` | `/api/v1/complaints/helpdesk/{id}/attachments/{att_id}/complete` | Helpdesk | Complete and verify staff attachment upload |

---

## 8. Phase 4 — Bank Statement Reconciliation

### Core Capabilities
- **Multi-Bank Statement Ingestion**: Automated CSV parsing supporting UTF-8 BOM, delimiter sniffing (`,`, `;`, `	`), and automatic profile detection for HDFC Bank, ICICI Bank, State Bank of India (SBI), Axis Bank, and generic society formats.
- **Three-Tier Duplicate Prevention**:
  1. *File Checksum*: SHA-256 hash on file contents rejects re-uploading identical statement files with `409 Conflict`.
  2. *Transaction Fingerprint*: SHA-256 hash on `(society_id, date, type, paise, ref, normalized_narration)` prevents ingesting duplicate lines inside or across files.
  3. *Bank Reference/UTR Matching*: Validates Indian banking transaction references against settled records.
- **Layered Deterministic Matching Engine**: 5 deterministic matching tiers:
  - *Level 1 (HIGH, 95-100%)*: Exact Bank UTR or payment reference match against online payments or invoice codes.
  - *Level 2 (HIGH, 85-90%)*: Exact transaction amount plus partial reference clue match.
  - *Level 3 (MEDIUM, 70-80%)*: Normalized narration clues identifying Tower/Flat (e.g. `T07-1203`) or resident name.
  - *Level 4 (MEDIUM, 55-65%)*: Exact single invoice outstanding balance match without narration clue.
  - *Level 5 (LOW, 0-30%)*: Unmatched credits or partial receipts queued for manual operator review or suspense classification.
- **Zero Double-Posting Guarantee**: Bank credits matching existing online gateway payments are linked to `payment_id` and marked `POSTED` without creating duplicate payments or duplicate ledger credits.
- **Atomic Concurrency & Balance Recalculation**: `SELECT FOR UPDATE` locks both transaction and candidate invoices, recalculating remaining balances post-lock to guarantee neither credits nor invoices can be over-allocated.
- **Direct Bank Transfer Settlement**: Direct credits generate a `Payment` (`provider = 'BANK_TRANSFER'`), `PaymentAllocation` rows, and immutable `FinancialLedgerEntry` items (`PAYMENT_RECEIVED`, `PAYMENT_ALLOCATED`). Multi-flat splits generate flat-specific payments to maintain billing invariants.
- **Spreadsheet Formula Injection Defense**: Pre-pends `'` to export cells starting with `=`, `+`, `-`, or `@` to neutralize DDE formula execution in spreadsheet software.
- **Mandatory Idempotency**: Financial settlement requires an `Idempotency-Key` header with 24-hour response caching.

### Reconciliation API Endpoints
| Method | Endpoint | Access | Purpose |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/reconciliation/statements` | Helpdesk | Upload CSV bank statement and receive validation preview |
| `GET` | `/api/v1/reconciliation/statements` | Helpdesk | List previously uploaded bank statements and parsing status |
| `POST` | `/api/v1/reconciliation/statements/{id}/confirm` | Helpdesk | Confirm validated statement and trigger deterministic matching |
| `POST` | `/api/v1/reconciliation/statements/{id}/cancel` | Helpdesk | Cancel and discard unconfirmed statement import |
| `GET` | `/api/v1/reconciliation/transactions` | Helpdesk | Filter and search normalized bank transactions |
| `GET` | `/api/v1/reconciliation/transactions/{id}` | Helpdesk | Inspect single transaction with candidate matches |
| `GET` | `/api/v1/reconciliation/queue` | Helpdesk | Fetch manual review queue filtered by category |
| `POST` | `/api/v1/reconciliation/transactions/{id}/suggest` | Helpdesk | Suggest manual match with flat and invoice |
| `POST` | `/api/v1/reconciliation/transactions/{id}/approve` | Helpdesk | Atomic financial ledger settlement (requires `Idempotency-Key`) |
| `POST` | `/api/v1/reconciliation/transactions/{id}/reject` | Helpdesk | Reject candidate match and return transaction to unmatched |
| `POST` | `/api/v1/reconciliation/transactions/{id}/mark-unidentified`| Helpdesk | Move unidentified mystery credit to suspense account |
| `GET` | `/api/v1/reconciliation/summary` | Helpdesk | Retrieve society-wide reconciliation KPIs and ratios |
| `GET` | `/api/v1/reconciliation/reports/export` | Helpdesk | Download formula-sanitized CSV reconciliation report |

---

## 9. Phase 6 — Perimeter Gate, Visitor Management & Offline Synchronization

### Core Capabilities
- **Decoupled Approval and Entry State Machines**: Separate tracking of visitor authorization (`PENDING` -> `APPROVED` | `REJECTED` | `AUTO_APPROVED`) and physical perimeter movement (`EXPECTED` -> `CHECKED_IN` -> `CHECKED_OUT`).
- **Encrypted Offline-First Gate Operations**: Full perimeter checkpoint functionality preserved when connectivity is lost using IndexedDB AES-GCM encrypted persistence with SHA-256 payload integrity validation.
- **Fail-Closed Offline Invariants**: Offline walk-in entries always remain in `PENDING` approval; guest pass verification fails closed while offline to prevent replay of revoked or exhausted passes.
- **Mandatory 90-Day Visitor Photo Retention & Automated Purge**: Hard 90-day logical cutoff in queries, scheduled Lambda purge deleting expired S3 photos and scrubbing database keys, and S3 lifecycle rule defense-in-depth.

---

## 10. Phase 7 — Event-Driven Notifications & Resident Communication

### Core Capabilities
- **Multi-Channel Dispatch Engine**: Dispatches observable, retryable notifications across In-App, Email (AWS SES / Mock), and SMS (AWS SNS / Mock).
- **Asynchronous Transactional Outbox Worker**: Decoupled from core business transactions. Domain events persist atomically in `outbox_events` and route via SQS `notification-jobs` queue to background Lambda workers.
- **17 Mapped Domain Events**: Complete lifecycle event coverage across Billing (`invoice_generated`, `payment_succeeded`, `payment_failed`, `invoice_paid`, `run_completed`), Complaints (`created`, `assigned`, `status_changed`, `resolved`, `safety_escalated`), and Gate Visitors (`approval_requested`, `approved`, `rejected`, `checked_in`, `overstay_alert`, `pass.revoked`).
- **Idempotency & State Machine Tracking**: Durable delivery tracking (`PENDING`, `PROCESSING`, `SENT`, `DELIVERED`, `RETRYING`, `FAILED`, `SUPPRESSED`) with exponential backoff and jitter for transient errors.
- **Mandatory Emergency Safety Bypass**: Critical safety alerts (`complaint.safety_escalated`, `URGENT` priority) bypass user opt-out preferences and guarantee delivery across all active channels to residents and helpdesk staff.
- **Privacy & PII Protection**: Automatic email and phone number masking in logs (`mask_email()`, `mask_phone()`), strict IDOR isolation per user, and exclusion of private helpdesk internal notes from resident notifications.
- **Mock Provider Fail-Closed Invariant**: Mock email and SMS providers record dispatches in memory for testing but return `SUPPRESSED` with `MOCK_PROVIDER_EXTERNAL_DELIVERY_DISABLED`, never falsely claiming external delivery.

### Notifications API Endpoints
| Method | Endpoint | Access | Purpose |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/notifications/me` | Resident / Staff | Paginated in-app notification inbox (newest-first, unread filter) |
| `GET` | `/api/v1/notifications/me/unread-count` | Resident / Staff | Live unread counter for notification bell badge |
| `PATCH` | `/api/v1/notifications/me/{id}/read` | Resident / Staff | Mark specific notification as read (with IDOR ownership protection) |
| `PATCH` | `/api/v1/notifications/me/read-all` | Resident / Staff | Mark all user notifications as read in current society |
| `GET` | `/api/v1/notifications/me/preferences` | Resident / Staff | Retrieve user communication channel preferences |
| `PUT` | `/api/v1/notifications/me/preferences` | Resident / Staff | Update communication preferences (Email, SMS, In-App per domain) |
| `GET` | `/api/v1/notifications/staff/overview` | Helpdesk Staff | Operational delivery telemetry, retry backoff metrics, and provider error tracking |

---

## 11. Phase 8 Part 1 — Amenity Booking Backend Foundation

### Core Capabilities
- **Domain Modeling**: Amenity resource management covering diverse facilities (Clubhouse, Badminton Courts, Tennis Courts, Swimming Pool, Gym, Community Hall, Guest Rooms).
- **Slot Capacity & Concurrency Protection**: Supports single-unit facilities (court, hall) and multi-capacity shared facilities (gym, pool) with row-level locking (`with_for_update()`) to prevent race conditions and overbooking.
- **Resident Eligibility & Tenancy Lease Enforcement**: Validates approved membership in target flat, checks that resident tenancy lease has not expired for the requested booking date, and enforces amenity-specific `allowed_membership_types` (`OWNER`, `TENANT`, `FAMILY_MEMBER`).
- **Timing & Operating Windows**: Validates opening/closing hours, slot interval alignment, advance booking limits (`advance_booking_days`), minimum booking lead time (`min_advance_hours`), and prevents past bookings.
- **Fair-Share Booking Quotas**: Enforces daily booking quotas per resident (`max_slots_per_day_per_resident`) to prevent resource hoarding.
- **Strict Integer Paise Monetary Precision**: All booking fees and refund amounts stored exclusively as integer paise (`BigInteger`).
- **Automated Cancellation & Refund Engine**: Resident cancellation checks `cancellation_deadline_hours` and computes pro-rata refunds via `refund_percentage`. Staff emergency overrides grant 100% refund with mandatory audit logging.
- **Auditability & Transactional Outbox**: Emits structured `AuditEvent` records and asynchronous `OutboxEvent` (`amenity.booking_created`, `amenity.booking_cancelled`) for event-driven resident communication.

### Amenity Booking API Endpoints
| Method | Endpoint | Access | Purpose |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/amenities` | Resident | List active amenities in township (optional `amenity_type` filter) |
| `GET` | `/api/v1/amenities/{id}` | Resident | Retrieve amenity details, guidelines, capacity, and operating rules |
| `GET` | `/api/v1/amenities/{id}/slots` | Resident | View slot availability, booked units, and remaining capacity for a date |
| `POST` | `/api/v1/amenities/{id}/bookings` | Resident | Book an amenity slot with concurrency lock and instant fee calculation |
| `GET` | `/api/v1/amenities/bookings/me` | Resident | View own bookings (upcoming, past, filtered by status) |
| `GET` | `/api/v1/amenities/bookings/{id}` | Resident | View single booking details with strict IDOR protection |
| `POST` | `/api/v1/amenities/bookings/{id}/cancel` | Resident | Cancel eligible booking with automated refund calculation |
| `POST` | `/api/v1/amenities/staff` | Helpdesk Staff | Create a new amenity resource with operating rules and fee structure |
| `PATCH` | `/api/v1/amenities/staff/{id}` | Helpdesk Staff | Update amenity properties, operating hours, and booking fees |
| `POST` | `/api/v1/amenities/staff/{id}/status` | Helpdesk Staff | Activate or deactivate amenity |
| `GET` | `/api/v1/amenities/staff/bookings` | Helpdesk Staff | List all community bookings with filters (`amenity_id`, `date`, `status`, `flat`) |
| `POST` | `/api/v1/amenities/staff/bookings/{id}/cancel` | Helpdesk Staff | Administrative cancellation with mandatory audit reason and 100% refund |

---

## 12. Phase 9 — Official Township Notices & Resident Communications

### Core Capabilities
- **Official Township Communications**: Replaces fragmented WhatsApp circulars with one authenticated, auditable broadcast system covering 2,400 apartments across 28 residential towers.
- **9 Notice Categories**: `GENERAL`, `CIRCULAR`, `MAINTENANCE`, `WATER`, `ELECTRICITY`, `SECURITY`, `EVENT`, `EMERGENCY`.
- **Dynamic Multi-Tower & Multi-Flat Targeting**: Array targeting (`target_tower_ids`, `target_flat_ids`) dynamically validated against society entities without hardcoding. Broadcasts can target the entire township, specific towers, or individual flats.
- **Lifecycle & Background Scheduling**: State machine transitions (`DRAFT` -> `SCHEDULED` -> `PUBLISHED` -> `ARCHIVED`). Future scheduled notices remain withheld until publication time; worker processes due notices every 30 seconds with PostgreSQL `FOR UPDATE SKIP LOCKED` distributed locking.
- **Revision Versioning & Audit Trail**: Monotonically increasing revision sequence (`Notice.version`), revision audit trail, and version-scoped broadcast keys (`notice_publish:{id}:v{version}`, `notice_emergency:{id}:v{version}`).
- **Granular Staff Permissions**: All notice authoring, updating, publishing, scheduling, and archiving require the dedicated `COMMUNICATIONS_MANAGE` permission. Gate-only personnel are rejected with HTTP 403 Forbidden.
- **Resident Security & IDOR Prevention**: Detail retrieval (`GET /resident/notices/{id}`) and read receipts (`POST /resident/notices/{id}/read`) strictly enforce society membership, flat/tower audience predicates, published status, and temporal validity window.
- **Read Receipts & Unread Badging**: Per-resident read receipts, unread counter badge (`GET /resident/notices/unread-count`), and bulk read (`POST /resident/notices/read-all`).
- **Trilingual Localization**: Full UI internationalization across English (`en`), Hindi (`hi`), and Marathi (`mr`).

### Official Notices API Endpoints
| Method | Endpoint | Access | Purpose |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/notifications/resident/notices` | Resident | Paginated, filtered feed of targeted notices |
| `GET` | `/api/v1/notifications/resident/notices/{id}` | Resident | Notice details with strict IDOR and temporal predicates |
| `GET` | `/api/v1/notifications/resident/notices/unread-count` | Resident | Live unread notice counter for badge display |
| `POST` | `/api/v1/notifications/resident/notices/{id}/read` | Resident | Mark specific notice as read |
| `POST` | `/api/v1/notifications/resident/notices/read-all` | Resident | Mark all visible notices as read |
| `GET` | `/api/v1/notifications/staff/notices/overview` | `COMMUNICATIONS_MANAGE` | 6 KPI overview cards (Total, Published, Scheduled, Draft, Archived, Emergency) |
| `GET` | `/api/v1/notifications/staff/notices/targeting-options` | `COMMUNICATIONS_MANAGE` | Dynamic tower and flat directory for broadcast selection |
| `POST` | `/api/v1/notifications/staff/notices` | `COMMUNICATIONS_MANAGE` | Create draft, scheduled, or published notice |
| `PUT` | `/api/v1/notifications/staff/notices/{id}` | `COMMUNICATIONS_MANAGE` | Edit notice details, multi-targeting, or schedule |
| `POST` | `/api/v1/notifications/staff/notices/{id}/publish` | `COMMUNICATIONS_MANAGE` | Publish notice and trigger outbox broadcast |
| `POST` | `/api/v1/notifications/staff/notices/{id}/archive` | `COMMUNICATIONS_MANAGE` | Archive notice |
| `POST` | `/api/v1/notifications/staff/notices/publish-scheduled` | `COMMUNICATIONS_MANAGE` | Trigger scheduled notice publication run |



