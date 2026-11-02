# Developer Guide & Local Environment Setup

## 1. Prerequisites

- Python 3.11+
- Node.js 20+ and npm 10+
- Docker and Docker Compose
- AWS CLI & AWS CDK CLI (optional for local development, required for cloud deployments)

---

## 2. Environment Variables Configuration

Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

Key environment configuration variables:
| Variable | Default (Dev) | Description |
| :--- | :--- | :--- |
| `ENVIRONMENT` | `development` | Deployment environment (`development`, `staging`, `production`) |
| `ENABLE_LOCAL_AUTH_BYPASS`| `true` | Enables deterministic dev mock logins. **Must remain false in staging/prod**. |
| `DATABASE_URL` | `postgresql+psycopg://postgres:postgres@localhost:5432/township_ops` | PostgreSQL connection string |
| `MESSAGING_PROVIDER` | `local` | `local` uses in-memory queues; `aws` uses real Amazon SQS |
| `AWS_REGION` | `ap-south-1` | Target AWS region (Mumbai) |

---

## 3. One-Command Local Startup (Docker Compose)

Spin up PostgreSQL, the FastAPI backend, the outbox worker, and the Vite frontend:
```bash
docker compose up --build
```

- **Frontend**: http://localhost:5173
- **Backend API**: http://localhost:8000
- **Swagger Docs (Dev only)**: http://localhost:8000/docs
- **Liveness Probe**: http://localhost:8000/health/live
- **Readiness Probe**: http://localhost:8000/health/ready

To shut down containers and reset local database volume:
```bash
make down
```

---

## 4. Manual / Native Local Development

### 4.1 Backend Setup
```bash
cd services/api
python -m venv .venv
# On Windows PowerShell:
.venv\Scripts\activate
# On Linux/macOS:
source .venv/bin/activate

pip install -r requirements-dev.txt
```

### 4.2 Database Migrations
Apply Alembic migrations to your database:
```bash
cd services/api
alembic upgrade head
```

### 4.3 Seeding Synthetic Township Data
Populate Marvel Greenfield Residences, towers, flats, and demo users idempotently:
```bash
python scripts/seed.py
```

### 4.4 Running Backend & Worker
In terminal 1 (FastAPI API Server):
```bash
cd services/api
uvicorn app.main:app --reload --port 8000
```

In terminal 2 (Outbox & Queue Worker):
```bash
cd services/api
python app/workers/runner.py
```

### 4.5 Frontend Setup
In terminal 3:
```bash
cd apps/web
npm install
npm run dev
```

---

## 5. Testing & Quality Commands

### Run Backend Unit & Integration Tests
```bash
cd services/api
pytest -v
```

### Run Infrastructure Unit Tests
```bash
cd infra/cdk
pytest -v
```

### Synthesize AWS CDK Stacks
```bash
cd infra/cdk
cdk synth -c env=dev
cdk synth -c env=staging
cdk synth -c env=prod
```

### Linting & Type Checking
```bash
# Backend lint
cd services/api && ruff check .

# Backend type check
cd services/api && mypy app

# Frontend build & type check
cd apps/web && npm run build
```

---

## 6. Phase 2 Demo Billing & Payment Testing

### Seed Scenarios
After running `python scripts/seed.py`:
1. **Neeraj Kulkarni** (`dev-token-neeraj`):
   - Flat **T07-1203** (1,150 sq ft)
   - Monthly maintenance: ₹7,475.00 (`UNPAID`)
   - Test flow: Log in, click "Pay", simulate payment of ₹7,475.00 -> invoice transitions to `PAID`.
2. **Swati Joshi** (`dev-token-swati`):
   - Flat **T12-0408** (980 sq ft)
   - Monthly maintenance: ₹6,370.00 (`OVERDUE` by 47 days)
   - Test flow: Verifies tenant lease validity and overdue tracking.
3. **Aamir Shaikh** (`dev-token-aamir`):
   - Flat **T21-1601** (1,640 sq ft)
   - Monthly maintenance: ₹10,660.00, ₹5,000 paid, ₹5,660 outstanding (`PARTIALLY_PAID` / `OVERDUE`)
   - Test flow: Test partial payment and receipt generation.
4. **Helpdesk (Rajesh Shinde)** (`dev-token-helpdesk`):
   - Navigate to `/staff/billing`.
   - View society-wide metrics (Billed, Collected, Outstanding, Overdue).
   - Test "Run Monthly Billing" preview and execution. Verify idempotent conflict-safe behavior.

