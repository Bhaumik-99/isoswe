# Payment Architecture — Demo-Only Simulated Gateway

## Overview

This system uses a **simulated payment gateway only**. No real money is transferred.  
No Razorpay, Stripe, or external payment provider credentials are required.  
The architecture is designed so a real provider can be integrated later by implementing  
the `PaymentProvider` interface, without modifying billing settlement logic.

> **IMPORTANT**: This is an assignment submission. The payment gateway is simulated for demonstration only.

## Payment Lifecycle

```
CREATED → PROCESSING → SUCCEEDED / FAILED
```

1. **CREATED**: Resident initiates payment for an invoice with positive amount and unique `Idempotency-Key`.
2. **PROCESSING**: Invoice row is locked via `SELECT FOR UPDATE`. Outstanding balance is recalculated. A persistent payment record is created in the database with status `PENDING` (representing the intent).
3. **SUCCEEDED / FAILED**: The simulated payment provider executes synchronously:
   - On **SUCCEEDED**: Payment marked `SUCCESS`, `PaymentAllocation` recorded, immutable `FinancialLedgerEntry` entries appended, invoice financial status derived and updated (`PAID` or `PARTIALLY_PAID`), transactional audit and outbox events recorded.
   - On **FAILED**: Payment marked `FAILED`, failure recorded in audit log and outbox, no allocations or ledger entries created, invoice balance remains unchanged.
   - Interrupted/abandoned `PENDING` payments (stuck > 5 minutes) can be recovered via `POST /admin/payments/recover-interrupted`.

## Simulated Provider

`SimulatedPaymentProvider` in `app/domains/billing/provider.py` implements the `PaymentProvider` ABC:

- **Default behaviour**: Returns `success=True` with a unique `SIM-xxxx` reference.
- **Failure simulation**: Pass `simulate_failure=True` in `InitiatePaymentRequest` to receive a `FAILED` result.
  This flag is guarded by `ENVIRONMENT in ("development", "demo", "test")` — it has no effect in production.

## Financial Invariants

| Invariant | How enforced |
|---|---|
| Integer paise arithmetic | All monetary fields are `BigInteger` (never float, 1 INR = 100 paise) |
| No over-allocation | `SELECT FOR UPDATE` on invoice row + balance re-check after lock |
| Idempotent payments | `IdempotencyKey` with atomic `INSERT ON CONFLICT` prevents duplicate processing |
| No cross-flat/society allocations | `CHECK CONSTRAINT` + composite FK at DB level + DB trigger |
| Append-only ledger | DB trigger rejects `UPDATE` and `DELETE` on `financial_ledger_entries` |
| No receipt for failed payments | `get_invoice_receipt()` raises 404 if no successful allocations exist |

## API Flow

1. Resident clicks "Pay Now" → frontend calls `POST /api/v1/billing/invoices/{id}/payments`
2. Backend validates ownership, locks invoice row, checks outstanding balance
3. Simulated provider called synchronously → returns success or failure
4. If SUCCESS: payment + allocation + ledger entries + audit + outbox committed atomically
5. If FAILED: payment marked FAILED, no allocation created, ledger unchanged
6. Response returned; idempotency key cached for 24h

## Bank Statement Reconciliation Integration (Phase 4)

In addition to resident-initiated online payments via payment providers, the platform supports offline direct credits (NEFT, RTGS, IMPS, UPI) reconciled through the Bank Reconciliation domain:

- **Settled Direct Credits**: Approved bank statement credits create `Payment` entries with `provider = 'BANK_TRANSFER'`, accompanied by `PaymentAllocation` rows and standard `FinancialLedgerEntry` records (`PAYMENT_RECEIVED`, `PAYMENT_ALLOCATED`).
- **Zero Double-Posting**: When an incoming bank statement line reflects an online payment previously settled through the gateway, reconciliation marks the transaction `POSTED` and links `existing_payment_id` without creating duplicate `Payment` or ledger entries.
- **Pessimistic Locking & Post-Lock Re-Check**: The reconciliation service locks target invoices with `SELECT FOR UPDATE` and re-verifies outstanding balances before allocation to prevent concurrent over-collection across both online and offline channels.

## Running Payment Tests Locally

```bash
cd services/api
python -m pytest tests/test_billing_endpoints.py -v
```

## Adding a Real Payment Provider (Future)

1. Implement `PaymentProvider` ABC in `app/domains/billing/provider.py`:
   ```python
   class RazorpayPaymentProvider(PaymentProvider):
       @property
       def provider_name(self) -> str:
           return "RAZORPAY"

       def process_payment(
           self, amount_paise: int, currency: str, metadata: dict[str, Any]
       ) -> PaymentResult: ...
   ```
2. Inject the new provider into `BillingService.__init__()` via dependency injection or settings.
3. No changes to `process_invoice_payment()` financial settlement logic needed.

## Security Notes

- `simulate_failure` flag only works in development/demo/test environments.
- No magic-string bypasses; all payment validation is server-side.
- Frontend never claims payment succeeded; only the backend decides.
- All payment state transitions are server-authoritative.

