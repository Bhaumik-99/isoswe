# Technical Design Document (TDD)
# Township Operations Platform
**Target Scope**: 2,400 Apartments | 28 Towers | 180 Facility Staff | Pune, Maharashtra  
**Document Revision**: Phase 5 Complete  
**Date**: November 2026  
**Status**: APPROVED & IMPLEMENTED  

---

## 1. Executive Summary & Problem Context

The Township Operations Platform is an enterprise-grade multi-tenant property governance system purpose-built for a large-scale residential gated community in Pune, Maharashtra comprising:
- **2,400 residential flats** distributed across **28 residential towers**.
- **180 on-site facility management staff** across helpdesk, electrical, plumbing, civil, security, and administrative teams.
- **₹6.50 per sq. ft. per month** standard maintenance billing (e.g., ₹7,475/month for a 1,150 sq. ft. 2BHK flat).
- **Payment channels**: Cheque, NEFT/RTGS bank transfer, and UPI.
- **Key operational challenges**: Automated invoice reconciliation against noisy bank narrations, tenant onboarding with lease tracking, SLA enforcement for emergency complaints, and committee-level financial governance.

---

## 2. Architecture & Multi-Tenancy Principles

### 2.1 Two-Role Strict RBAC with Granular Permissions
The platform enforces strictly two application roles at the identity layer:
- `RESIDENT`: Scoped strictly to active, approved flat memberships.
- `HELPDESK`: Authorized facility management staff.

Operational capabilities are granted via granular permissions:
- `COMPLAINT_MANAGE`: Triage, update, assign, and resolve complaint tickets.
- `BANK_IMPORT`: Upload and confirm bank statement CSV files.
- `RECONCILIATION_REVIEW`: Propose and approve financial matching allocations.
- `BILLING_MANAGE`: Configure billing cycles, generate monthly invoice runs, and apply late fees.
- `COMMITTEE_REPORT_READ`: Explicitly granted permission enabling access to executive financial summaries, ageing arrears, and CSV export.

### 2.2 PostgreSQL Row-Level Security (RLS)
Every financial and transactional table enforces `FORCE ROW LEVEL SECURITY`:
- Financial tables (`invoices`, `payments`, `payment_allocations`, `financial_ledger_entries`, `bank_transactions`) enforce tenant isolation by `society_id`.
- Residents can read only records bound to flats for which they hold an active, non-expired `FlatMembership`.
- Staff access is strictly restricted to assigned societies via security definer helper `public.is_helpdesk_for_society(society_id)`.

---

## 3. Core Domain Subsystems

### 3.1 Identity & Resident Registry
- **Membership Types**: `OWNER`, `TENANT`, `FAMILY_MEMBER`.
- **Lease Window Enforcement**: Leases require `valid_from` and `valid_until` with validation ensuring end date is not prior to start date. Expired tenant leases automatically forfeit flat data access.
- **Resident Onboarding**: Phone numbers normalized to international E.164 (`+91XXXXXXXXXX`). Self-registration requests enter `PENDING` state until staff verification.
- **Audit Logging**: Every membership state change records structured audit events (`identity.membership.created`, `identity.membership.updated`, `identity.membership.approved`, `identity.membership.terminated`).

### 3.2 Maintenance Billing & Append-Only Financial Ledger
- **Integer Paise Arithmetic**: All monetary quantities are stored as 64-bit BigInt paise (₹1.00 = 100 paise) preventing floating-point rounding discrepancies.
- **Formula**: `area_sqft * rate_paise_per_sqft` (1,150 sq. ft. * 650 paise = 747,500 paise = ₹7,475.00).
- **Snapshot Pricing**: Generated invoices snapshot current rates, shielding historical obligations from future tariff modifications.
- **Append-Only Ledger**: Balances are calculated dynamically from immutable ledger entries (`INVOICE`, `PAYMENT`, `ADJUSTMENT`, `LATE_FEE`). Updates or deletes to ledger entries are blocked by database triggers.
- **Late-Fee Engine**: Society bye-law policy evaluation supporting Flat Fee (paise), Monthly Percentage (basis points), and Daily Simple Interest (`(unpaid * amount_or_rate_bps * days + 1825000) // 3650000`).

### 3.3 Automated Bank Statement Reconciliation
- **Deduplication**: Concurrency-safe SHA-256 fingerprinting on `(society_id, transaction_date, amount_paise, narration)` with unique database constraint.
- **UPI VPA Normalization**: Regex extraction of UPI VPAs from banker narrations (`UPI/123456789012/PAYMENT/resident@okhdfcbank/...`).
- **Confidence Scoring & Promotion**:
  - Exact UPI VPA mapping match: `confidence = 0.98` -> Auto-promoted to match.
  - Narration containing exact Tower + Flat + Amount: `confidence = 0.95` -> Promoted to match.
  - Partial match: Suggestion created for manual review.
- **Financial Maker-Checker**: Mandatory separation of duties. Users cannot approve proposals they submitted; requires `PENDING_APPROVAL` status before financial settlement.

### 3.4 Complaints & Service Desk
- **Auto-Assignment**: Round-robin assignment to active staff in the society with the fewest open tickets.
- **SLA Tracking**:
  - First Response SLA (e.g. 15 minutes for EMERGENCY, 2 hours for HIGH).
  - Resolution SLA (e.g. 4 hours for EMERGENCY, 24 hours for HIGH).
- **Category Correction & Duplication**: Staff can reclassify misrouted categories while preserving `original_category`, and link duplicate complaints to a primary parent ticket.
- **Persistent Safety Alerts**: Dedicated high-priority emergency queue for urgent health/safety hazards.

### 3.5 Committee Financial Governance
- **SQL Aggregates**: Zero memory limit aggregation over all 2,400 flats directly in database queries.
- **Ageing Arrears Buckets**: Live segregation of outstanding receivables:
  - 0-30 Days (Current)
  - 31-60 Days (Overdue)
  - 61-90 Days (Delinquent)
  - 90+ Days (Critical Recovery)
- **Tower Breakdown**: Tower-by-tower collection percentages and complaint volume.
- **CSV Export Sanitization**: Formula injection mitigation (CWE-1236) prepending single-quote `'` to cells starting with `=`, `+`, `-`, `@`, `\t`, or `\r`.

### 3.6 Offline-Capable Resident PWA
- Progressive Web Application with responsive layout, app shell caching via `sw.js`, and installable web manifest.
- 1-tap quick actions: Pay Maintenance Bill, Raise Urgent Complaint.

---

## 4. Infrastructure & Deployment Architecture

- **AWS CDK v2**: Infrastructure-as-code deploying VPC, RDS PostgreSQL 16 Multi-AZ, ECS Fargate API container, and CloudFront S3 SPA distribution.
- **Secrets Management**: AWS Secrets Manager with fail-closed production validation.
- **CI/CD Pipeline**: GitHub Actions running Ruff linting, Mypy strict typing, Pytest unit/integration tests, Vitest frontend tests, Gitleaks secret scanning, and CodeQL SAST.
