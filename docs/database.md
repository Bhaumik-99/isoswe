# Database Architecture & Schema Specification

## 1. System of Record Overview

The multi-tenant Society Operations Platform uses **PostgreSQL 16** as its authoritative system of record.
- **Engine**: PostgreSQL 16
- **Driver**: Psycopg 3 (`psycopg[binary]>=3.1.18`)
- **ORM**: SQLAlchemy 2.0 with strict typing (`Mapped[...]`, `mapped_column`)
- **Schema Management**: Alembic migrations only (zero `create_all()` in production code)
- **Monetary Precision**: All monetary values are strictly represented in integer paise (e.g. ₹1,000.00 is stored as `100000`). Storing money in floating-point columns is strictly prohibited to eliminate IEEE 754 rounding errors.

---

## 2. Entity Relationship Diagram (ERD)

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
        string cognito_sub UK
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

## 3. Table Specifications & Constraints

### 3.1 Identity Domain

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

#### `users`
- Platform accounts mapped to Cognito subjects.
- Constraints: `cognito_sub` (UNIQUE, INDEXED), `email` (UNIQUE, INDEXED).
- Status: `ACTIVE`, `INACTIVE`, `SUSPENDED`.

#### `flat_memberships`
- Relationship binding an individual user to a specific apartment.
- Supports residents belonging to multiple flats.
- Check Constraint: `ck_membership_valid_dates` enforces `valid_until IS NULL OR valid_until >= valid_from`.
- Tenant Leases: `valid_until` is enforced on all resident requests. If current timestamp exceeds `valid_until`, access is denied automatically by the security layer.

#### `user_roles`
- Role-based authorization per society.
- Roles: `RESIDENT`, `HELPDESK`. Committee reporting is a read-only helpdesk capability, not a separate role.
- Composite Unique Constraint: `(user_id, society_id, role)`.

---

### 3.2 Platform Reliability & Messaging Domain

#### `audit_events`
- Append-only compliance log.
- Indexed by `correlation_id`, `resource_id`, `actor_id`, and `society_id` for distributed transaction tracing.

#### `outbox_events`
- Implements the Transactional Outbox pattern.
- Columns: `event_type`, `aggregate_type`, `aggregate_id`, `payload` (JSONB), `status` (PENDING, PUBLISHED, FAILED), `attempts`, `published_at`.
- Index: `(status, attempts, created_at)` allows high-throughput polling workers using `SELECT ... FOR UPDATE SKIP LOCKED` without locking table scans.

#### `processed_events`
- Prevents duplicate message execution across SQS consumers.
- Primary Key: `(consumer_name, event_id)` guarantees consumer idempotency within the business transaction.

#### `idempotency_keys`
- API-level idempotency store for payment operations, bill generation, and state-mutating requests.
- Unique Constraint: `(scope, idempotency_key)` with automatic expiry TTL.

---

## 4. Migration Strategy

Schema changes follow zero-downtime expand/contract rules:
1. **Never edit existing migration scripts**: Always generate forward migrations using `alembic revision -m "..."`.
2. **Backward-compatible changes first**: Add new columns as nullable or with defaults before updating code.
3. **Automated CI Validation**: CI executes migrations against an empty PostgreSQL database instance on every pull request.
