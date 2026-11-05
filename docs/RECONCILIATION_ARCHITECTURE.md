# Bank Statement Reconciliation System

See the comprehensive architecture specification in [services/api/docs/RECONCILIATION_ARCHITECTURE.md](../services/api/docs/RECONCILIATION_ARCHITECTURE.md).

## Highlights
- **Deterministic-First Matching Engine**: 5-level deterministic matching engine (Level 1: Exact UTR/Payment Ref, Level 2: Exact Amount + Ref Clue, Level 3: Narration Flat/Resident Clue, Level 4: Exact Invoice Amount, Level 5: Unmatched/Suspense).
- **Three-Tier Duplicate Prevention**: SHA-256 file payload checksum, SHA-256 transaction fingerprint unique per society, and bank UTR verification.
- **Zero Double-Posting**: Matches against existing online gateway payments without creating duplicate `Payment` or ledger entries.
- **Atomic Concurrency Protection**: Row-level locking (`SELECT FOR UPDATE`) on transaction and candidate invoices with post-lock balance recalculation.
- **Formula Injection Defense**: Automatic prefixing of CSV cells starting with `=`, `+`, `-`, or `@` to neutralize Excel/Sheets DDE exploits.
- **Integer Paise Representation**: All calculations use `Decimal` string arithmetic converted to integer paise (`BigInteger`). Zero floating-point math.
- **Mandatory Idempotency**: Financial settlement requires `Idempotency-Key` header with 24-hour response caching.
- **Multi-Flat Split Invariant**: Corporate/split bank transfers across multiple flats generate dedicated `Payment` records per flat to maintain cross-flat billing invariants.

