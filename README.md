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
- **Asynchronous AI Triage (Google Gemini)**: Complaint submission returns immediately with `ai_status = PENDING`. Background worker executes `gemini-2.5-flash` with structured JSON schema (`responseSchema`), prompt injection defenses, resident PII redaction (`[PHONE_REDACTED]`, `[EMAIL_REDACTED]`, `[UNIT_REDACTED]`, `[NAME_REDACTED]`), and deterministic offline fallback.
- **Worker Idempotency**: Row-locked processing (`with_for_update()`) ensures duplicate queue events skip already completed AI triage.
- **Configurable SLA Policies**: Strict deadlines calculated from creation time (Critical: 5m first response, 2h resolution; High: 30m/8h; Medium: 4h/48h; Low: 12h/5d). Priority changes dynamically recalculate resolution deadlines.
- **Workload-Based Auto-Assignment**: Assigns newly triaged tickets to active helpdesk staff with the lowest open ticket count in the society.
- **Privacy Separation**: Strict isolation between public resident conversations and private internal helpdesk notes.
- **Two-Phase Presigned Attachments**: S3/Mock storage validating JPEG, PNG, and WebP up to 5MB with randomized UUID keys, client PUT verification, and backend metadata verification (object existence, actual size, MIME type).

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


