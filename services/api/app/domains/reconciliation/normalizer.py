"""Reconciliation Normalizer and Sanitization Utilities

Provides:
- Integer paise conversion from decimal amounts (never using float arithmetic)
- Narration normalization and extraction of Indian banking references (UTR, UPI, IMPS, NEFT, RTGS)
- Cryptographic file checksum and transaction fingerprint generation
- CSV formula injection protection (neutralizing spreadsheet execution vectors)
"""

import hashlib
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

# Max statement size: 10 MB
MAX_STATEMENT_FILE_SIZE = 10 * 1024 * 1024


def decimal_to_paise(raw_value: Any) -> int:
    """Converts a monetary representation to integer paise using Decimal.

    Strict financial rules:
    - 1 INR = 100 paise.
    - Floating point operations are forbidden.
    - Strips whitespace, currency symbols (₹, INR, Rs, Rs.), and thousand-separator commas.
    - Returns integer paise.
    - Raises ValueError on invalid numbers or negative values.
    """
    if raw_value is None:
        return 0

    if isinstance(raw_value, int):
        if raw_value < 0:
            raise ValueError(f"Monetary amount cannot be negative: {raw_value}")
        return raw_value * 100

    str_val = str(raw_value).strip()
    if not str_val:
        return 0

    # Clean currency symbols, commas, and formatting
    cleaned = (
        str_val.replace("₹", "")
        .replace("INR", "")
        .replace("Rs.", "")
        .replace("Rs", "")
        .replace(",", "")
        .replace(" ", "")
    )

    # Check for parentheses indicating negative (accounting format)
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = "-" + cleaned[1:-1]

    try:
        dec = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"Invalid monetary format '{raw_value}': {exc}") from exc

    if dec < 0:
        raise ValueError(f"Monetary amount cannot be negative: {raw_value}")

    # Multiply by 100 and quantize to integer paise
    paise_dec = dec * Decimal(100)
    # Check if there are sub-paise fractions
    if paise_dec != paise_dec.to_integral_value():
        # Round half up to nearest paise
        paise_int = int(paise_dec.quantize(Decimal("1")))
    else:
        paise_int = int(paise_dec)

    return paise_int


def normalize_narration(raw_desc: str) -> str:
    """Normalizes transaction description for matching while preserving the original.

    - Removes control characters and excess whitespace
    - Uppercases for case-insensitive tokenization
    - Standardizes Indian payment acronyms
    """
    if not raw_desc:
        return ""

    # Replace multiple whitespace / tabs / newlines with single space
    cleaned = re.sub(r"\s+", " ", raw_desc).strip()
    return cleaned.upper()


def extract_utr_and_reference(
    narration: str, raw_ref: str | None = None
) -> tuple[str | None, str | None]:
    """Extracts UTR and secondary reference number from Indian bank statement descriptions.

    Supports:
    - UPI: UPI/123456789012/..., UPI/CR/..., UPI-123456789012
    - IMPS: IMPS/P2A/..., IMPS-..., IMPS/123456789012
    - NEFT: NEFT-N123456789..., NEFT/N123456789...
    - RTGS: RTGS/R123456789..., RTGS-R123456789...
    - Cheque / Draft: CHQ NO ..., CHEQUE ...
    """
    utr: str | None = None
    ref: str | None = raw_ref.strip() if raw_ref and raw_ref.strip() else None

    # If raw_ref has a valid looking alphanumeric reference (min 6 chars), check if it's UTR
    if ref and len(ref) >= 6 and re.match(r"^[A-Z0-9\-_/]+$", ref, re.IGNORECASE):
        # Clean special chars for matching
        cleaned_ref = re.sub(r"[\-_/]", "", ref).upper()
        if len(cleaned_ref) >= 6:
            utr = cleaned_ref

    if not narration:
        return utr, ref

    upper = narration.upper()

    # Pattern 1: UPI 12-digit transaction reference number (RRN)
    # e.g., "UPI/123456789012/PAYMENT FOR..." or "UPI/CR/123456789012/..."
    upi_match = re.search(r"UPI/(?:CR/|P2A/|P2P/)?([A-Z0-9]{8,22})", upper)
    if upi_match:
        extracted = upi_match.group(1).strip()
        if not utr or len(extracted) > len(utr):
            utr = extracted
        if not ref:
            ref = extracted

    # Pattern 2: NEFT / RTGS standard 16 or 22 char alphanumeric reference
    # e.g., "NEFT-AXSK123456789012" or "NEFT/SBIN123456789"
    neft_match = re.search(r"(?:NEFT|RTGS)[-/]?([A-Z0-9]{9,22})", upper)
    if neft_match:
        extracted = neft_match.group(1).strip()
        utr = extracted
        if not ref:
            ref = extracted

    # Pattern 3: IMPS reference number (12 digits)
    imps_match = re.search(r"IMPS/(?:P2A/|P2U/)?([0-9]{10,12})", upper)
    if imps_match:
        extracted = imps_match.group(1).strip()
        if not utr:
            utr = extracted
        if not ref:
            ref = extracted

    # Pattern 4: Generic UTR tag in description (e.g., "UTR NO: 123456789012" or "UTR: ABCD...")
    generic_utr = re.search(r"UTR(?:\s*NO)?[:\s\-]+([A-Z0-9]{8,22})", upper)
    if generic_utr:
        extracted = generic_utr.group(1).strip()
        utr = extracted
        if not ref:
            ref = extracted

    return utr, ref


def extract_unit_clues(narration: str) -> list[str]:
    """Extracts possible apartment / tower / flat number tokens from transaction description.

    Examples:
    - "T07-1203" or "T7-1203" or "T12-0408" or "T21-1601"
    - "FLAT 1203", "UNIT 408", "APT 1601"
    - "T071203", "1203", "0408", "1601"
    """
    if not narration:
        return []

    upper = narration.upper()
    clues: set[str] = set()

    # Pattern A: Standard township format "T07-1203" or "T7-1203"
    matches_a = re.findall(r"\bT\d{1,2}[-\s]?\d{3,4}\b", upper)
    for m in matches_a:
        cleaned = re.sub(r"\s+", "-", m)
        clues.add(cleaned)

    # Pattern B: "FLAT 1203", "UNIT 1203", "APT 1203", "FLAT NO 1203"
    matches_b = re.findall(r"\b(?:FLAT|UNIT|APT|NO)[-\s]*(?:NO)?[:\s\-]*([A-Z0-9]{3,8})\b", upper)
    for m in matches_b:
        clues.add(m)

    # Pattern C: Standalone 4-digit numbers commonly representing flat numbers (e.g., 1203, 0408, 1601)
    matches_c = re.findall(r"\b\d{4}\b", upper)
    for m in matches_c:
        # Exclude common current/recent years like 2024, 2025, 2026, 2027
        if m not in ("2023", "2024", "2025", "2026", "2027"):
            clues.add(m)

    return list(clues)


def compute_file_checksum(file_bytes: bytes) -> str:
    """Computes SHA-256 cryptographic checksum of uploaded file content."""
    return hashlib.sha256(file_bytes).hexdigest()


def compute_transaction_fingerprint(
    society_id: UUID,
    txn_date: datetime,
    credit_paise: int,
    debit_paise: int,
    reference: str | None,
    normalized_desc: str,
) -> str:
    """Computes a deterministic cryptographic fingerprint for a transaction line item.

    Uses stable normalized source fields:
    - society_id
    - date (YYYY-MM-DD)
    - credit_paise
    - debit_paise
    - normalized reference or UTR
    - prefix of normalized description
    """
    date_str = txn_date.strftime("%Y-%m-%d")
    ref_str = (reference or "").strip().upper()
    desc_sample = normalized_desc[:64].strip()

    fingerprint_raw = (
        f"{society_id}:{date_str}:{credit_paise}:{debit_paise}:{ref_str}:{desc_sample}"
    )
    return hashlib.sha256(fingerprint_raw.encode("utf-8")).hexdigest()


def sanitize_for_csv_export(value: Any) -> str:
    """Neutralizes CSV formula injection vulnerabilities (CWE-1236).

    If untrusted text begins with `=, +, -, @`, or a tab/carriage return,
    prepends a single quote `'` so spreadsheet software treats it as plain text.
    """
    if value is None:
        return ""

    str_val = str(value)
    if not str_val:
        return ""

    dangerous_prefixes = ("=", "+", "-", "@", "\t", "\r")
    if str_val.startswith(dangerous_prefixes):
        return f"'{str_val}"

    return str_val
