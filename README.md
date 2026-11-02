# Township Operations Platform (`township-ops`)

[![Continuous Integration](https://github.com/organization/township-ops/actions/workflows/ci.yml/badge.svg)](https://github.com/organization/township-ops/actions/workflows/ci.yml)
[![Security Policy](https://img.shields.io/badge/Security-Fail--Closed-green.svg)](docs/security.md)
[![Database](https://img.shields.io/badge/System%20of%20Record-PostgreSQL%2016-blue.svg)](docs/database.md)

Production-grade technical engineering foundation for a multi-tenant **Society Operations Platform** serving gated townships in Pune, India.

---

## 1. Product Context & Operational Scale

The platform is designed to operate:
- **2,400 apartments** across **28 residential towers**.
- **180 facility-management staff** and technicians.
- **Residents Federation** governance and committee auditing.
- Automated monthly maintenance formula calculations (₹3.50/sq ft + sinking funds).
- Digital payment collections and daily bank statement reconciliation.
- Facility helpdesk ticket lifecycle with AI classification.

### Core User Roles
1. `RESIDENT`: Apartment owner or tenant with access strictly restricted to approved flats and non-expired tenancy dates.
2. `HELPDESK`: Facility management desk handling technician dispatch.
3. `FINANCE`: Society accounting team managing billing batches and bank reconciliation.
4. `COMMITTEE_VIEWER`: Managing committee member with read-only audit and financial oversight.
5. `PLATFORM_ADMIN`: Township administrator with global platform provisioning.

---

## 2. Technology Stack

### Frontend Application Shell
- **React 18** with **TypeScript** and **Vite**
- **Tailwind CSS** (curated slate typography and restrained indigo primary accents; no AI slop)
- **TanStack Query v5** (caching and asynchronous state management)
- **React Router v6** (role-aware protected routing and responsive mobile drawers)
- **Lucide React** (consistent accessible SVG iconography)
- Centralized API client with token injection and distributed tracing headers (`X-Request-ID`, `X-Correlation-ID`)

### Backend Monolith
- **Python 3.11+** with **FastAPI**
- **Pydantic v2** and **Pydantic-Settings** (fail-closed environment validation)
- **SQLAlchemy 2.0** with **Psycopg 3**
- **Alembic** (strict database migrations; zero `create_all()` in runtime code)
- **Transactional Outbox Pattern** with **Amazon SQS** and dedicated Dead Letter Queues (DLQs)
- **Amazon Cognito** JWT validation using JWKS; isolated fail-closed local dev mock provider

### Cloud Infrastructure (AWS CDK)
- **VPC** (Public, Private with Egress for Lambdas, Isolated for RDS)
- **RDS PostgreSQL 16** (Multi-AZ, KMS encryption at rest, automated backups, PITR)
- **Amazon RDS Proxy** (Connection pooling and connection storms prevention)
- **Amazon SQS** (`billing-jobs`, `payment-events`, `reconciliation-jobs`, `complaint-ai-jobs`, `notification-jobs`) + dedicated DLQs
- **Amazon S3** (Private document buckets & web hosting with CloudFront OAC)
- **AWS WAF** (SQL injection rules, OWASP top 10, rate-limiting)
- **AWS KMS** (Customer Managed Keys for encryption at rest)
- **AWS Secrets Manager** (Automatic database credentials rotation)
- **AWS CloudTrail** & **CloudWatch** (Compliance audit logging and alarms)

---

## 3. Repository Organization

```text
township-ops/
│
├── apps/
│   └── web/                     # React + TypeScript + Vite frontend application
│       ├── src/
│       │   ├── app/             # Application entrypoint & QueryClient provider
│       │   ├── components/      # UI components (Button, Card, Badge, Skeleton, Alert)
│       │   ├── features/        # Auth, Resident, Staff, and Committee views
│       │   ├── layouts/         # Auth, Resident, Staff, and Committee layouts
│       │   ├── routes/          # Role-based route guards and path definitions
│       │   ├── services/        # Central API client abstraction
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
│       │   │   └── billing/     # Clean domain boundaries stubbed for future phases
│       │   ├── integrations/    # Cognito JWT verifier & local mock auth provider
│       │   ├── messaging/       # SQS & Local queue publishers, outbox worker, consumer
│       │   ├── workers/         # Platform health check worker & background runner
│       │   ├── middleware/      # Correlation ID, Request ID & structured logger
│       │   └── handlers/        # Mangum Lambda API handler & SQS Lambda trigger
│       ├── migrations/          # Alembic versioned migrations
│       └── tests/               # 13 mandatory unit and integration test suites
│
├── infra/
│   └── cdk/                     # AWS CDK Python infrastructure
│       ├── app.py               # CDK app entrypoint
│       ├── stacks/              # TownshipStack primary composition
│       ├── constructs/          # Reusable Network, DB, Auth, SQS, S3, Compute, WAF
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

## 5. Seed Identities & Personas

The database is seeded idempotently with real-world scenarios for Pune township testing:
- **Neeraj Kulkarni** (`dev-token-neeraj`): Resident & Owner of **T07-1203** (1,150 sq ft).
- **Swati Joshi** (`dev-token-swati`): Resident & Tenant of **T12-0408** (980 sq ft) with time-bound active lease.
- **Aamir Shaikh** (`dev-token-aamir`): Resident & Owner of **T21-1601** (1,640 sq ft).
- **Rajesh Shinde** (`dev-token-helpdesk`): Facility management staff (`HELPDESK`).
- **Priya Deshmukh** (`dev-token-finance`): Society accountant (`FINANCE`).
- **Aniket Patwardhan** (`dev-token-committee`): Managing committee member (`COMMITTEE_VIEWER`).
- **Vikram Joshi** (`dev-token-admin`): Platform administrator (`PLATFORM_ADMIN`).

---

## 6. Testing & Quality Verification

Run the complete test suite:
```bash
cd services/api && pytest -v
cd infra/cdk && pytest -v
```

All 13 mandatory engineering assertions pass with zero failures:
1. Invalid JWT rejected (401 Unauthorized)
2. Expired JWT rejected (401 Unauthorized)
3. Resident cannot access another resident's flat (403 Forbidden)
4. Help-desk user cannot perform restricted finance operations (403 Forbidden)
5. Committee viewer cannot modify records (403 Forbidden)
6. Tenant access stops after membership lease expiry (403 Forbidden)
7. Society-level isolation works (Cross-society access denied)
8. Outbox event committed atomically with business transaction
9. Duplicate event cannot be processed twice (Idempotency handler)
10. Failed SQS publishing leaves event recoverable
11. Health endpoints behave correctly (`/health/live`, `/health/ready`)
12. Database migration works from an empty database
13. Seed script is idempotent
