# Bank Statement Reconciliation Operations & Engineering Guide

## 1. Domain Model Reference

The Reconciliation domain operates 5 authoritative entities within Supabase PostgreSQL, strictly isolated by `society_id`:

1. **`BankStatementImport`**: Ingested bank statement file metadata, SHA-256 checksum, parsed row metrics, bank profile, and lifecycle state.
2. **`BankTransaction`**: Individual statement line item normalized to integer paise (`debit_paise`, `credit_paise`, `balance_paise`), reconciliation status, UTR reference, and SHA-256 fingerprint.
3. **`ReconciliationMatch`**: Candidate match between a bank transaction and open maintenance invoices or existing online gateway payments with explainable confidence scoring (HIGH, MEDIUM, LOW) and structured evidence JSON.
4. **`ReconciliationAllocation`**: Direct ledger linkage between an approved bank credit and an invoice outstanding balance.
5. **`ReconciliationReview`**: Immutable audit record of helpdesk review actions (`SUGGESTED`, `APPROVED`, `REJECTED`, `UNIDENTIFIED`) capturing staff ID and rationale notes.

---

## 2. Statement Import Lifecycle & CSV Mapping

### Lifecycle State Machine
```mermaid
stateDiagram-v2
    [*] --> UPLOADED: File uploaded & SHA-256 checksum verified
    UPLOADED --> VALIDATING: Column header mapping & delimiter sniffing
    VALIDATING --> READY_FOR_IMPORT: Ingestion preview generated
    VALIDATING --> FAILED: Checksum duplicate or corrupted file
    READY_FOR_IMPORT --> PROCESSING: Operator confirms import
    READY_FOR_IMPORT --> CANCELLED: Operator cancels preview
    PROCESSING --> COMPLETED: Deterministic matching complete
    PROCESSING --> COMPLETED_WITH_ERRORS: Minor row parse errors recorded
    PROCESSING --> FAILED: Critical database failure
    COMPLETED --> [*]
```

### Supported CSV Column Mappings

| Standard Field | HDFC Profile | ICICI Profile | SBI Profile | Axis Profile |
|---|---|---|---|---|
| **Date** | `Date` / `Txn Date` | `Transaction Date` | `Txn Date` | `Tran Date` |
| **Value Date** | `Value Dt` | `Value Date` | `Value Date` | `Value Date` |
| **Narration** | `Narration` | `Transaction Remarks` | `Description` | `Particulars` |
| **Reference / UTR** | `Chq/Ref No` | `Cheque No` / `Ref No` | `Ref No./Cheque No.` | `Chq No` |
| **Withdrawal (Debit)** | `Withdrawal Amt` | `Debit Amount` | `Debit` | `Dr Amount` |
| **Deposit (Credit)** | `Deposit Amt` | `Credit Amount` | `Credit` | `Cr Amount` |
| **Closing Balance** | `Closing Balance` | `Balance` | `Balance` | `Bal` |

*Custom Mappings*: Operators can pass a `custom_mapping` JSON dictionary to dynamically bind non-standard bank export headers.

---

## 3. Matching Rules & Weighting Algorithm

```mermaid
sequenceDiagram
    autonumber
    participant Op as Helpdesk Operator
    participant API as Reconciliation API
    participant Engine as Matching Engine
    participant DB as PostgreSQL DB

    Op->>API: POST /reconciliation/statements/{id}/confirm
    API->>DB: Batch insert normalized BankTransactions
    API->>Engine: Run Deterministic Matching Engine
    loop For each CREDIT transaction
        Engine->>DB: Check Level 1: Exact UTR against Payments & Invoices
        alt Level 1 Match Found
            Engine->>DB: Record match (Confidence: 95-100%, Tier: HIGH)
        else Level 2: Exact Amount + Ref Clue
            Engine->>DB: Check invoices with exact outstanding balance + partial ref
            Engine->>DB: Record match (Confidence: 85-90%, Tier: HIGH)
        else Level 3: Narration Flat / Resident Clue
            Engine->>DB: Parse tower/flat clues (e.g. T07-1203)
            Engine->>DB: Record match (Confidence: 70-80%, Tier: MEDIUM)
        else Level 4: Exact Invoice Amount
            Engine->>DB: Find single open invoice matching amount
            Engine->>DB: Record match (Confidence: 55-65%, Tier: MEDIUM)
        else Level 5: Unmatched
            Engine->>DB: Flag status as UNMATCHED (Queue for Staff Review)
        end
    end
    API-->>Op: Return import record with matching summary
```

### Evidence Scoring Weighting

$$\text{Confidence Score} = w_{\text{UTR}} \cdot E_{\text{UTR}} + w_{\text{amount}} \cdot E_{\text{amount}} + w_{\text{resident}} \cdot E_{\text{resident}} + w_{\text{date}} \cdot E_{\text{date}}$$

- **Exact UTR match** ($w = 60$): Exact match with existing payment reference or invoice payment code.
- **Exact amount match** ($w = 20$): Bank credit equals current invoice outstanding balance.
- **Resident/Flat match** ($w = 10$): Narration contains verified tower/unit number or resident name.
- **Date proximity** ($w = 10$): Transaction date within billing cycle due window.

---

## 4. Financial Settlement & Concurrency Protection

```mermaid
flowchart TD
    A["Operator clicks Approve Settlement"] --> B["Validate Idempotency-Key"]
    B -- "Cached Response" --> C["Return HTTP 200 (Idempotent)"]
    B -- "New Key" --> D["Acquire SELECT FOR UPDATE on BankTransaction"]
    D --> E{"Check unallocated_paise >= allocation_sum"}
    E -- "Insufficient Credit" --> F["Reject with 400 Bad Request"]
    E -- "Sufficient Credit" --> G["Acquire SELECT FOR UPDATE on Invoices (ordered)"]
    G --> H["Recalculate invoice outstanding post-lock"]
    H --> I{"Check allocation <= current outstanding"}
    I -- "Over-allocation" --> J["Reject with 400 Bad Request"]
    I -- "Valid Allocation" --> K{"Is Online Gateway Payment?"}
    K -- "Yes (Existing Payment)" --> L["Link payment_id & mark POSTED<br/>(Zero double-posting in ledger)"]
    K -- "No (Direct Bank Transfer)" --> M["Create Payment (provider='BANK_TRANSFER')<br/>Create PaymentAllocation rows<br/>Append FinancialLedgerEntries (immutable)"]
    L --> N["Emit Transactional Outbox Event"]
    M --> N
    N --> O["Record AuditEvent"]
    O --> P["Commit Database Transaction"]
```

---

## 5. Background Processing & SQS Queue Architecture

```mermaid
flowchart LR
    A["Outbox Table (PostgreSQL)"] -->|"Outbox Dispatcher"| B["QUEUE_RECONCILIATION_JOBS (SQS)"]
    B -->|"Event Envelope"| C["Reconciliation Worker"]
    C --> D{"Event Type?"}
    D -->|"reconciliation.process_bank_statement"| E["Async Statement Parsing & Matching"]
    D -->|"reconciliation.statement_imported"| F["Audit & Ingestion Confirmation"]
    D -->|"reconciliation.approved_and_posted"| G["Audit & Settlement Confirmation"]
    C -->|"Transient DB/Lock Error"| H["RetryableReconciliationWorkerError<br/>(Re-raise for SQS retry)"]
    C -->|"Poison Pill / Invalid UUID"| I["PermanentReconciliationWorkerError<br/>(Acknowledge & DLQ)"]
    B -->|"Max Receives Exceeded"| J["RECONCILIATION_JOBS_DLQ"]
```

### Worker Reliability Invariants
1. **Idempotency**: Processing checks current database status (`imp.status == COMPLETED` or `txn.reconciliation_status == POSTED`) before doing work; duplicates are safely skipped.
2. **Short DB Transactions**: DB locks are released immediately; heavy parsing and matching are staged outside long-running lock windows.
3. **Bounded Retries**: SQS redrive policy caps retries at 3 attempts with exponential backoff before sending failed jobs to the Dead Letter Queue (`QUEUE_RECONCILIATION_JOBS_DLQ`).
4. **Audit Logging**: Every worker execution produces an `AuditEvent` with the original `correlation_id` from the triggering client request.

---

## 6. Security & Formula Injection Defense

1. **Spreadsheet Formula Injection Defense**: When generating CSV exports (`/api/v1/reconciliation/reports/export`), values starting with `=`, `+`, `-`, or `@` are automatically prepended with a single quote (`'`). This prevents malicious spreadsheet command execution in Microsoft Excel or Google Sheets.
2. **Row-Level Security (RLS)**: PostgreSQL tables `bank_statement_imports`, `bank_transactions`, `reconciliation_matches`, `reconciliation_allocations`, and `reconciliation_reviews` enforce tenant isolation by `society_id`.
3. **Role Authorization**: All reconciliation mutations require role `HELPDESK`. Direct financial mutations by `RESIDENT` role tokens are strictly rejected with `HTTP 403 Forbidden`.

---

## 7. Operational Troubleshooting & Runbooks

### Issue 1: "File already imported in this society" (`409 Conflict`)
- **Cause**: The SHA-256 checksum of the uploaded file matches an existing record in `bank_statement_imports`.
- **Resolution**: Check the statement history in the Overview tab. If the statement was uploaded previously, review existing transactions rather than re-uploading. If a new monthly statement has identical contents, verify with the bank.

### Issue 2: Transactions Flagged as `DUPLICATE`
- **Cause**: The SHA-256 fingerprint `(society_id + date + type + paise + ref + narration)` matches an existing transaction.
- **Resolution**: This is normal when overlapping statement date ranges are uploaded. Duplicate transactions are marked `is_duplicate = True` and excluded from matching to prevent double-counting.

### Issue 3: Invoice Over-Allocation Rejected (`400 Bad Request`)
- **Cause**: The target invoice received a payment through another channel (e.g. resident paid online) between the time the suggestion was generated and the operator clicked approve.
- **Resolution**: The pessimistic lock detected that `allocation > current_outstanding`. Refresh the review queue; the updated invoice balance will be reflected.

### Issue 4: Poison Message in SQS DLQ
- **Cause**: Malformed payload or unresolvable society ID in event envelope.
- **Resolution**: Inspect the message in AWS SQS Console under `township-ops-reconciliation-jobs-dlq`. Check `correlation_id` in CloudWatch structured JSON logs:
  ```json
  {"action": "reconciliation.process_bank_statement.processed", "resource_type": "Reconciliation"}
  ```
