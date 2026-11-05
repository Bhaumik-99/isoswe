# Bank Statement Reconciliation Operations Guide

See the comprehensive operations and runbook specification in [services/api/docs/RECONCILIATION_OPERATIONS.md](../services/api/docs/RECONCILIATION_OPERATIONS.md).

## Operational Highlights
- **Supported Bank Formats**: Out-of-the-box support for HDFC Bank, ICICI Bank, State Bank of India (SBI), Axis Bank, and generic CSV layouts.
- **Three-Tier Duplicate Elimination**: SHA-256 file checksum, transaction fingerprint, and bank UTR duplicate detection.
- **Asynchronous Worker Invariants**: Idempotent message consumption, transient vs. permanent error classification, and bounded SQS retries with Dead Letter Queue (DLQ) protection.
- **Troubleshooting Runbooks**: Prescriptions for handling duplicate statement uploads, concurrent over-allocations, and DLQ inspection.
