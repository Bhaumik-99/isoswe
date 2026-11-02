# Software and Cloud Infrastructure Architecture

## 1. Architectural Decisions (ADRs)

### ADR 001: Modular Monolith Architecture
- **Context**: The platform serves 2,400 flats, 28 towers, and 180 facility staff. Domain boundaries encompass Identity, Billing, Payments, Reconciliation, Complaints, and Reporting.
- **Decision**: Adopt a modular monolith rather than microservices. Domain logic is strictly partitioned into distinct Python modules (`app/domains/*`), interacting via explicit interfaces and domain services rather than distributed network calls.
- **Consequences**: Minimizes operational overhead, avoids distributed transaction failures across billing and ledger updates, simplifies local development, and allows frictionless serverless deployment via AWS Lambda and Mangum.

### ADR 002: Reliable Asynchronous Messaging via Transactional Outbox
- **Context**: Actions such as invoice generation, payment receipts, AI complaint processing, and SMS notifications require reliable execution without blocking HTTP responses or risking dual-write inconsistencies.
- **Decision**: Implement the Transactional Outbox pattern paired with Amazon SQS standard queues and dedicated Dead Letter Queues (DLQs). Business changes and outbox records commit within the exact same database transaction. An outbox worker dispatches events using `SELECT ... FOR UPDATE SKIP LOCKED`.
- **Consequences**: Guarantees zero lost messages if SQS or the network is temporarily degraded. Consumers use the `processed_events` registry for idempotent exactly-once processing.

### ADR 003: Multi-Tenant Data Isolation Strategy
- **Context**: While initial deployment is a single gated township in Pune (Marvel Greenfield Residences), cross-society leakage must be structurally prevented for future township federations.
- **Decision**: Enforce tenant boundaries through mandatory `society_id` foreign keys, composite database unique indexes, and backend FastAPI dependency barriers (`require_society_access`, `require_flat_access`). Never rely on client-side claims.
- **Consequences**: Prevents accidental data exposure across distinct societies and residential units.

### ADR 004: Strict Integer Paise Monetary Representation
- **Context**: Maintenance billing, sinking fund levies, and bank statement matching require financial precision.
- **Decision**: All financial amounts are stored as 64-bit BigInteger paise (1 INR = 100 paise). Floating-point data types (`FLOAT`, `REAL`, `DOUBLE PRECISION`) are prohibited in financial columns.
- **Consequences**: Eliminates IEEE 754 precision drift and rounding discrepancies in ledger audits.

---

## 2. AWS Target Architecture Diagram

```mermaid
flowchart TB
    subgraph Users ["Client Tier"]
        Browser["Resident & Staff Web App (React / Vite)"]
    end

    subgraph Edge ["Edge & Perimeter Security"]
        CF["Amazon CloudFront CDN (TLS 1.3)"]
        WAF["AWS WAF (SQLi, Rate Limiting, OWASP Top 10)"]
        OAC["Origin Access Control (OAC)"]
        S3Web["Private S3 Bucket (Static Web Assets)"]
    end

    subgraph Auth ["Identity Provider"]
        Cognito["Amazon Cognito User Pool<br/>(Passwordless OTP & MFA)"]
    end

    subgraph Ingress ["API Gateway Tier"]
        APIGW["Amazon API Gateway (REST API)"]
    end

    subgraph VPC ["Amazon VPC (ap-south-1)"]
        subgraph AppSubnets ["Private Application Subnets"]
            ApiLambda["FastAPI Backend Lambda (Mangum)"]
            WorkerLambda["SQS Worker Lambda"]
        end

        subgraph SQS ["Asynchronous Messaging Tier"]
            Q1["billing-jobs + DLQ"]
            Q2["payment-events + DLQ"]
            Q3["reconciliation-jobs + DLQ"]
            Q4["complaint-ai-jobs + DLQ"]
            Q5["notification-jobs + DLQ"]
        end

        subgraph DBSubnets ["Private Isolated Database Subnets"]
            RDSProxy["Amazon RDS Proxy<br/>(Connection Pooling)"]
            PostgreSQL[("Amazon RDS PostgreSQL 16<br/>Multi-AZ & KMS Encrypted")]
        end
    end

    subgraph SecurityTier ["Security & Observability"]
        KMS["AWS KMS Master Key"]
        Secrets["AWS Secrets Manager"]
        CloudWatch["Amazon CloudWatch Logs & Alarms"]
        CloudTrail["AWS CloudTrail Audit Trail"]
    end

    Browser -->|HTTPS| CF
    CF -->|OAC| S3Web
    Browser -->|Auth OTP / MFA| Cognito
    Browser -->|API Requests with JWT| APIGW
    WAF -.->|Inspects & Filters| APIGW
    APIGW -->|Proxies| ApiLambda

    ApiLambda -->|Secrets & Decrypt| Secrets
    ApiLambda -->|Connection Pool| RDSProxy
    RDSProxy --> PostgreSQL

    ApiLambda -->|Writes Outbox Event| PostgreSQL
    ApiLambda -->|Enqueues Asynchronous Work| SQS

    SQS -->|Event Source Mapping| WorkerLambda
    WorkerLambda -->|Idempotent Processing| RDSProxy

    KMS -.->|Encrypts at Rest| PostgreSQL
    KMS -.->|Encrypts at Rest| SQS
    KMS -.->|Encrypts at Rest| S3Web
```

---

## 3. Request Execution Flow (Synchronous API)

```mermaid
sequenceDiagram
    autonumber
    actor Resident as Resident (Neeraj)
    participant Web as Web Frontend (React)
    participant APIGW as API Gateway
    participant Lambda as FastAPI Backend
    participant DB as RDS PostgreSQL

    Resident->>Web: Opens "My Flat Overview"
    Web->>APIGW: GET /api/v1/flats/{flat_id} [Bearer JWT, X-Request-ID]
    APIGW->>Lambda: Dispatches request to Mangum Handler
    Note over Lambda: CorrelationIdMiddleware injects tracing context
    Lambda->>Lambda: Validates JWT signature, exp, issuer against Cognito JWKS
    Lambda->>DB: Resolves user, active roles, and flat memberships
    Lambda->>Lambda: Evaluates require_flat_access dependency
    alt Valid Membership
        Lambda->>DB: Fetches flat specifications (Tower, Sqft, Status)
        Lambda-->>APIGW: 200 OK [FlatDetail JSON, X-Request-ID]
        APIGW-->>Web: Renders Unit Specifications
    else Another Resident's Flat OR Expired Lease
        Lambda-->>APIGW: 403 Forbidden {"error": {"code": "FLAT_ACCESS_DENIED"}}
        APIGW-->>Web: Displays Access Denied notification
    end
```

---

## 4. Transactional Outbox & Asynchronous Messaging Flow

```mermaid
sequenceDiagram
    autonumber
    participant App as Backend Transaction
    participant OutboxTable as PostgreSQL outbox_events
    participant Publisher as Outbox Publisher Worker
    participant SQS as Amazon SQS Queue
    participant Worker as Worker Consumer
    participant ProcessedTable as PostgreSQL processed_events

    Note over App: 1. Business Transaction
    App->>OutboxTable: INSERT business record AND outbox_events in SAME ACID TX
    Note over App,OutboxTable: Commit guarantees zero lost events

    loop Every 2 Seconds
        Publisher->>OutboxTable: SELECT ... FOR UPDATE SKIP LOCKED WHERE status = 'PENDING'
        Publisher->>SQS: SendMessage(Envelope, CorrelationId)
        alt SQS Send Success
            Publisher->>OutboxTable: UPDATE outbox_events SET status = 'PUBLISHED'
        else SQS or Network Failure
            Publisher->>OutboxTable: UPDATE attempts = attempts + 1 (Leaves event for retry)
        end
    end

    Note over Worker: 2. SQS Consumption
    SQS->>Worker: Delivers Event Message
    Worker->>ProcessedTable: Checks if (consumer_name, event_id) exists
    alt Event Already Processed (Duplicate Delivery)
        Worker-->>SQS: Acknowledges / Deletes message (No duplicate side effect)
    else New Event
        Worker->>Worker: Executes business logic
        Worker->>ProcessedTable: Records (consumer_name, event_id) in transaction
        Worker-->>SQS: Deletes message from Queue
    end
```
