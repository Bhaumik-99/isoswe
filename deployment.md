# Township Operations Platform — Production Deployment Guide
**Target System**: Gated Township Operations (Pune, Maharashtra — 2,400 Apartments, 28 Towers, 180 Staff)  
**Deliverable**: Phase 5 Complete Financial Governance, Service Desk, Automated Reconciliation & Offline PWA

---

## 1. System Architecture & Topology

The platform is designed as a cloud-native, multi-tenant township management system adhering to strict SOC 2 financial governance, tenant isolation, and high availability.

```mermaid
flowchart TD
    subgraph ClientTiers["Client Presentation Layer"]
        PWA["Offline-Capable Resident PWA (Vite / React 18 / Tailwind)"]
        StaffPortal["Staff Operations Desktop (Helpdesk, Billing, Recon, Committee)"]
    end

    subgraph EdgeCDN["AWS CloudFront Edge Layer"]
        CF["CloudFront Distribution (HTTPS / TLS 1.3, HSTS, CSP)"]
        S3Web["S3 Static Bucket (SPA Assets & sw.js with Cache-Control: no-cache)"]
    end

    subgraph Compute["AWS Application Compute"]
        ALB["Application Load Balancer / API Gateway HTTP API"]
        FastAPIService["FastAPI Container (ECS Fargate / Lambda Web Adapter)"]
        WorkerService["Background Event Consumer (Outbox Processor / Job Runner)"]
    end

    subgraph Persistence["Storage & Database Layer"]
        RDS["PostgreSQL 16 Multi-AZ (Row-Level Security, FORCE RLS)"]
        SecretsMgr["AWS Secrets Manager (Structured DB & JWT Credentials)"]
        S3Docs["S3 Bucket (Invoices, Receipts, Bank Statements, CSV Exports)"]
    end

    ClientTiers --> CF
    CF --> S3Web
    CF --> ALB
    ALB --> FastAPIService
    FastAPIService --> RDS
    FastAPIService --> SecretsMgr
    FastAPIService --> S3Docs
    FastAPIService --> WorkerService
    WorkerService --> RDS
```

---

## 2. Prerequisites & Environment Setup

### 2.1 Required Toolchains
- **Python**: `3.11+` (Required for FastAPI backend and AWS CDK infrastructure)
- **Node.js**: `20.x` or `22.x` LTS with `npm 10+`
- **AWS CLI**: `v2.x` configured with deployment IAM credentials (`AdministratorAccess` or scoped CDK role)
- **AWS CDK CLI**: `npm install -g aws-cdk@^2.100.0`
- **Docker**: `24+` with Buildx support
- **PostgreSQL Client**: `psql` (libpq 16+)

### 2.2 Repository Checkout
All deployment commands assume `REPO_ROOT` is set to the cloned repository root so sections can be executed sequentially or independently without working-directory drift:
```bash
git clone https://github.com/Bhaumik-99/isoswe.git
cd isoswe
export REPO_ROOT="$(pwd)"
```

---

## 3. Environment Variables & Secrets Management

The platform adheres to 12-factor configuration. In `staging` and `production`, secrets **must never** be committed to source control and are retrieved from AWS Secrets Manager.

### 3.1 Backend Configuration (`services/api/.env`)

```ini
# Core Environment
ENVIRONMENT=production
DEBUG=false
TZ=Asia/Kolkata

# Multi-Tenant Database
DATABASE_URL=postgresql+psycopg://app_user:<SECRET_PASSWORD>@db.township.internal:5432/township_ops
DB_POOL_SIZE=20
DB_MAX_OVERFLOW=10
DB_POOL_TIMEOUT=30

# Authentication & Supabase
SUPABASE_URL=https://<project-id>.supabase.co
SUPABASE_JWT_SECRET=<MIN_32_CHAR_HMAC_OR_ED25519_SECRET>
SUPABASE_SERVICE_ROLE_KEY=<SUPABASE_SERVICE_ROLE_KEY>
ENABLE_LOCAL_AUTH_BYPASS=false

# CORS & Trusted Origins
ALLOWED_ORIGINS=["https://township.example.com", "https://d1234abcd.cloudfront.net"]

# Outbox & Reliability
MESSAGING_PROVIDER=sqs
SQS_OUTBOX_QUEUE_URL=https://sqs.ap-south-1.amazonaws.com/123456789012/township-outbox-prod
EVENT_RETRY_MAX_ATTEMPTS=5
```

### 3.2 Frontend Build Configuration (`apps/web/.env.production`)

```ini
VITE_API_BASE_URL=https://api.township.example.com
VITE_SUPABASE_URL=https://<project-id>.supabase.co
VITE_SUPABASE_ANON_KEY=<SUPABASE_PUBLIC_ANON_KEY>
```

### 3.3 AWS Secrets Manager Provisioning & Guest-Pass HMAC Secret

In staging and production, secrets are managed centrally in AWS Secrets Manager under secret name `township-supabase-credentials-<env>` (e.g., `township-supabase-credentials-prod`), encrypted with the stack's Customer Managed KMS Key (CMK).

#### Automated Secret Generation via AWS CDK
The CDK `SecurityConstruct` (`infra/cdk/township_constructs/security.py`) automatically provisions the secret JSON with:
1. `GUEST_PASS_HMAC_SECRET`: Automatically generated 64-character high-entropy cryptographic secret via `SecretStringGenerator(password_length=64)`. This strictly satisfies the platform invariant requiring `>= 32` characters in staging/production, eliminating runtime HTTP 500 errors.
2. `DATABASE_URL` & `SUPABASE_URL`: Initialized in the JSON template for operator configuration.

> [!SECURITY]
> **Never commit `GUEST_PASS_HMAC_SECRET`, database passwords, or private keys to Git.**

#### Operator Configuration & Secrets Population Command
After CDK stack deployment, administrators populate the live connection strings using the AWS CLI. To preserve or set the 64-character `GUEST_PASS_HMAC_SECRET`:

```bash
# Retrieve existing generated secret or generate a fresh 64-character secret
EXISTING_HMAC=$(aws secretsmanager get-secret-value \
  --secret-id "township-supabase-credentials-prod" \
  --region ap-south-1 \
  --query "SecretString" --output text 2>/dev/null | jq -r '.GUEST_PASS_HMAC_SECRET // empty')

if [ -z "$EXISTING_HMAC" ]; then
  EXISTING_HMAC=$(openssl rand -hex 32)
fi

# Update Secrets Manager with live credentials while preserving GUEST_PASS_HMAC_SECRET
aws secretsmanager put-secret-value \
  --secret-id "township-supabase-credentials-prod" \
  --region ap-south-1 \
  --secret-string "{
    \"DATABASE_URL\": \"postgresql+psycopg://app_user:<STRONG_PASSWORD>@db.township.internal:5432/township_ops\",
    \"SUPABASE_URL\": \"https://<project-id>.supabase.co\",
    \"GUEST_PASS_HMAC_SECRET\": \"$EXISTING_HMAC\"
  }"
```

---

## 4. Database Provisioning & Migrations

The database utilizes **PostgreSQL 16** with **Row Level Security (RLS)** strictly enforced on all financial and tenant tables.

### 4.1 Execute Alembic Migrations
Run Alembic migrations up to head to create tables, triggers, indexes, and RLS policies:

```bash
cd "$REPO_ROOT/services/api"
python -m venv .venv
source .venv/bin/activate  # Or on Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Run migrations to head
python -m alembic upgrade head
cd "$REPO_ROOT"
```

### 4.2 Seed Baseline Demographics & Society Data
From the repository root, seed the Pune township baseline data (Marvel Greenfield Residences: 3 Towers, Sample Flats, Resident Accounts, and Authorized Helpdesk/Committee staff) and optionally populate the full 2,400-flat / 28-tower / 180-staff target-scale dataset:

```bash
cd "$REPO_ROOT"
PYTHONPATH=services/api python scripts/seed.py

# Optional: Populate full target-scale township population (28 towers, 2,400 flats, 180 staff)
PYTHONPATH=services/api python scripts/generate_sample_data.py
```

### 4.3 Database Verification Commands
```sql
-- Verify FORCE ROW LEVEL SECURITY on critical tables
SELECT tablename, rowsecurity FROM pg_tables 
WHERE schemaname = 'public' 
AND tablename IN ('societies', 'flats', 'invoices', 'payments', 'financial_ledger_entries', 'bank_transactions', 'user_permissions');

-- Confirm all migrations applied cleanly
SELECT version_num FROM alembic_version;
-- Expected: 012_user_permissions
```

---

## 5. Infrastructure as Code (AWS CDK) Deployment

The infrastructure is defined under `infra/cdk` (`infra/cdk/app.py` reads context key `-c env=<dev|staging|prod>`) in AWS Region `ap-south-1` (Mumbai).

```bash
cd "$REPO_ROOT/infra/cdk"
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Synthesize CloudFormation templates (valid env values: dev, staging, prod)
cdk synth -c env=prod

# Bootstrap CDK environment (first-time deployment only)
cdk bootstrap aws://123456789012/ap-south-1

# Deploy TownshipOps-Prod stack
cdk deploy --all -c env=prod --require-approval never
cd "$REPO_ROOT"
```

The CDK deploys:
1. **NetworkStack**: VPC with 2 public subnets, 2 private application subnets, and 2 isolated database subnets with NAT Gateways.
2. **DatabaseStack**: Amazon RDS PostgreSQL 16 Multi-AZ instance, automated daily snapshots, storage auto-scaling.
3. **ComputeStack**: ECS Fargate Service with auto-scaling (min 2, max 10 tasks) fronted by an Application Load Balancer with ACM SSL certificate.
4. **FrontendStack**: Amazon S3 bucket for SPA assets with CloudFront Origin Access Control (OAC), TLS 1.3, security headers Lambda@Edge/CloudFront Functions.

---

## 6. Frontend Build & Static Deployment

The frontend Progressive Web Application (PWA) is built and uploaded to Amazon S3:

```bash
cd "$REPO_ROOT/apps/web"
npm ci

# Run ESLint and Vitest unit test suite
npm run lint
npm test -- --run

# Compile TypeScript and Vite production bundle
npm run build

# Synchronize assets to S3
aws s3 sync dist/ s3://township-ops-frontend-prod/ --delete \
  --cache-control "public, max-age=31536000, immutable" \
  --exclude "index.html" \
  --exclude "sw.js" \
  --exclude "manifest.webmanifest"

# Upload entry files with strict cache revalidation
aws s3 cp dist/index.html s3://township-ops-frontend-prod/index.html \
  --cache-control "no-cache, no-store, must-revalidate"
aws s3 cp dist/sw.js s3://township-ops-frontend-prod/sw.js \
  --cache-control "no-cache, no-store, must-revalidate"
aws s3 cp dist/manifest.webmanifest s3://township-ops-frontend-prod/manifest.webmanifest \
  --cache-control "no-cache, no-store, must-revalidate"

# Invalidate CloudFront edge cache
aws cloudfront create-invalidation \
  --distribution-id E12345EXAMPLE \
  --paths "/*"
cd "$REPO_ROOT"
```

---

## 7. Health Checks, Verification & Monitoring

### 7.1 Health Check Endpoints
- **Liveness Probe**: `GET https://api.township.example.com/health` (Returns HTTP 200 `{ "status": "healthy" }`)
- **Readiness Probe**: `GET https://api.township.example.com/health/ready` (Verifies PostgreSQL connection pool, SQS connectivity, and cache availability)

### 7.2 CloudWatch Metrics & Alarms
- **API Latency (p95)**: Alarm if `p95 > 500ms` for 3 consecutive 1-minute periods.
- **5xx HTTP Errors**: Alarm if `HTTPCode_Target_5XX_Count > 5` over a 5-minute period.
- **Dead Letter Queue (DLQ)**: Alarm if `ApproximateNumberOfMessagesVisible > 0` on `township-outbox-dlq`.

---

## 8. Rollback & Disaster Recovery Procedures

### 8.1 Zero-Downtime Application Rollback
If an application defect is detected post-deployment:
```bash
# Roll back ECS service to previous task definition revision
aws ecs update-service \
  --cluster township-ops-prod \
  --service api-service \
  --task-definition township-api-prod:<PREVIOUS_REVISION_NUMBER> \
  --force-new-deployment
```

### 8.2 Database Rollback Strategy
Database migrations are written with clean, reversible `downgrade()` routines:
```bash
cd "$REPO_ROOT/services/api"
# Revert the latest migration
python -m alembic downgrade -1
cd "$REPO_ROOT"
```

For major state recovery:
- RDS Point-in-Time Recovery (PITR) is enabled with 35-day retention.
- Automated snapshots are taken before every scheduled release window.

