# Database Architecture & Schema Specification

## 1. System of Record Overview

The multi-tenant Society Operations Platform uses **Supabase PostgreSQL** (Mumbai `ap-south-1`) as its authoritative system of record.
- **Engine**: PostgreSQL 16 (hosted on Supabase)
- **Connection Endpoint**: Supabase Shared Transaction Pooler (PgBouncer port `6543`)
- **Driver**: Psycopg 3 (`psycopg[binary]>=3.1.18`)
- **ORM**: SQLAlchemy 2.0 with strict typing (`Mapped[...]`, `mapped_column`)
- **Schema Management**: Version-controlled Alembic migrations only (zero `create_all()` in production code)
- **Security & RLS**: PostgreSQL Row-Level Security (RLS) enabled on all core tables for defense-in-depth
- **Monetary Precision**: All monetary values are strictly represented in integer paise (e.g. ₹1,000.00 is stored as `100000`). Storing money in floating-point columns is strictly prohibited to eliminate IEEE 754 rounding errors.

---

## 2. Supabase Shared Transaction Pooler & Lambda Configuration

AWS Lambda instances connect to Supabase PostgreSQL using its shared transaction pooler:
```python
engine = create_engine(
    settings.DATABASE_URL,
    pool_size=1,
    max_overflow=0,
    pool_pre_ping=True,
    connect_args={
        "sslmode": "require",
        "prepare_threshold": None,  # Disables prepared statements for PgBouncer transaction mode
    },
)
```

### Critical Invariants:
1. **Disable Prepared Statements (`prepare_threshold: None`)**: PgBouncer in transaction pooling mode routes individual transactions across heterogeneous backend connections. Prepared statements must be disabled in Psycopg 3 to prevent "prepared statement does not exist" errors.
2. **Small Per-Lambda Pool (`pool_size=1, max_overflow=0`)**: Prevents connection exhaustion when multiple Lambda concurrent workers scale.
3. **Module-Scoped Engine**: Retained in global memory across warm Lambda invocations to eliminate connection handshake latency.
4. **Secrets Manager Storage**: The exact transaction pooler connection URI is stored securely in AWS Secrets Manager and encrypted with AWS KMS.

---

## 3. Entity Relationship Diagram (ERD)

```mermaid
erDiagram
    societies ||--o{ towers : "contains"
    societies ||--o{ flats : "scopes"
    societies ||--o{ user_roles : "assigns"
    societies ||--o{ flat_memberships : "authorizes"
    societies ||--o{ audit_events : "audits"

    towers ||--o{ flats : "houses"

    users ||--o{ flat_memberships : "holds"
    users ||--o{ user_roles : "granted"
    users ||--o{ audit_events : "acts_in"

    flats ||--o{ flat_memberships : "occupied_by"

    outbox_events {
        uuid id PK
        string event_type
        string aggregate_type
        string aggregate_id
        json payload
        string status
        int attempts
        timestamptz created_at
        timestamptz published_at
    }

    processed_events {
        string consumer_name PK
        uuid event_id PK
        timestamptz processed_at
    }

    idempotency_keys {
        uuid id PK
        string scope
        string idempotency_key
        string request_hash
        int response_status
        text response_body
        timestamptz created_at
        timestamptz expires_at
    }

    societies {
        uuid id PK
        string name
        string timezone
        string preferred_currency
        string status
        timestamptz created_at
        timestamptz updated_at
    }

    towers {
        uuid id PK
        uuid society_id FK
        string tower_number
        string name
        timestamptz created_at
    }

    flats {
        uuid id PK
        uuid society_id FK
        uuid tower_id FK
        string flat_number
        int area_sqft
        string status
        timestamptz created_at
        timestamptz updated_at
    }

    users {
        uuid id PK
        uuid supabase_uid UK
        string phone
        string email UK
        string full_name
        string status
        timestamptz created_at
        timestamptz updated_at
    }

    flat_memberships {
        uuid id PK
        uuid society_id FK
        uuid user_id FK
        uuid flat_id FK
        string membership_type
        timestamptz valid_from
        timestamptz valid_until
        boolean is_primary
        string status
        timestamptz created_at
        timestamptz updated_at
    }

    user_roles {
        uuid id PK
        uuid user_id FK
        uuid society_id FK
        string role
        timestamptz created_at
    }

    audit_events {
        uuid id PK
        uuid society_id FK
        uuid actor_id FK
        string action
        string resource_type
        string resource_id
        string correlation_id
        json metadata
        timestamptz created_at
    }
```

---

## 4. Table Specifications & Constraints

### 4.1 Identity Domain

#### `societies`
- Root tenant anchor. All residential assets, billing ledgers, and access boundaries scope directly to a society.
- Columns: `id` (UUID PK), `name` (VARCHAR 255), `timezone` (VARCHAR 64, default 'Asia/Kolkata'), `preferred_currency` (VARCHAR 8, default 'INR'), `status` (ACTIVE, ONBOARDING, SUSPENDED), `created_at`, `updated_at`.

#### `towers`
- Tower buildings within a society (e.g. Tower 7, Tower 12, Tower 21).
- Composite Unique Constraint: `(society_id, tower_number)` prevents duplicate tower numbering within the same township.

#### `flats`
- Physical apartment units.
- Composite Unique Constraint: `(tower_id, flat_number)` guarantees unit number uniqueness per tower.
- Foreign Key with `ON DELETE CASCADE` to both `societies` and `towers`.

#### `users` (Application Profile Table)
- Application user profile table linked to `auth.users` via `supabase_uid`.
- Constraints: `supabase_uid` (UUID, UNIQUE, INDEXED), `phone` (VARCHAR 32, INDEXED), `email` (VARCHAR 255, NULLABLE, UNIQUE).
- Never modified directly by Supabase Auth; synced via application domain logic.

#### `flat_memberships`
- Links a user to a specific flat as an `OWNER`, `TENANT`, or `FAMILY_MEMBER`.
- Check Constraint: `valid_until IS NULL OR valid_until >= valid_from` ensures lease integrity.
- Compound Index: `(user_id, status)` for fast authorization lookup.

#### `user_roles`
- Granular RBAC assignments.
- Valid Roles: `RESIDENT` and `HELPDESK`.
- Unique Constraint: `(user_id, society_id, role)` prevents duplicate role assignments.

---

## 5. Row-Level Security (RLS)

All application tables enable PostgreSQL Row-Level Security:
```sql
ALTER TABLE societies ENABLE ROW LEVEL SECURITY;
ALTER TABLE flats ENABLE ROW LEVEL SECURITY;
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
...
```
Permissive policies allow the FastAPI application connection (operating via the authenticated connection / service role) to perform verified business transactions, while preventing direct unauthenticated SQL tampering.
