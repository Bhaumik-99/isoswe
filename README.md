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

## 5. Seed Personas (Local Development)

The database is seeded idempotently with scenarios matching Marvel Greenfield Residences, Pune:
- **Neeraj Kulkarni** (`dev-token-neeraj`): Resident & Owner of **T07-1203** (1,150 sq ft).
- **Swati Joshi** (`dev-token-swati`): Resident & Tenant of **T12-0408** (980 sq ft) with time-bound active lease.
- **Aamir Shaikh** (`dev-token-aamir`): Resident & Owner of **T21-1601** (1,640 sq ft).
- **Rajesh Shinde** (`dev-token-helpdesk`): Facility management staff (`HELPDESK`).
