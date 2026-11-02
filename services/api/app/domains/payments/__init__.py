"""Payments Domain Package

Responsible for payment gateway integration (UPI/Netbanking/Cards), transaction receipts,
and webhook idempotency.
Phase 2+: PG webhooks, transaction states (INITIATED, SETTLED, FAILED), refunds.
Note: Monetary values must be stored strictly as integer paise.
"""
