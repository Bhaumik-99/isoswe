"""Bank Statement CSV Parser & Header Mapping

Provides robust CSV parsing for Indian bank statements:
- Configurable bank column mappings (HDFC, ICICI, SBI, Axis, and Generic auto-detection)
- UTF-8 and UTF-8 BOM (Byte Order Mark) decoding
- Flexible delimiter detection (comma, semicolon, tab)
- Multi-format date parsing (DD/MM/YYYY, DD-MM-YYYY, YYYY-MM-DD, etc.)
- Safe decimal to integer paise conversion
- Row-level validation and explicit rejected record logging
"""

import contextlib
import csv
import io
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from app.domains.reconciliation.models import TransactionType
from app.domains.reconciliation.normalizer import (
    compute_file_checksum,
    compute_transaction_fingerprint,
    decimal_to_paise,
    extract_upi_vpa,
    extract_utr_and_reference,
    normalize_narration,
)

# Common column variations across Indian banks
DATE_HEADERS = [
    "date",
    "txn_date",
    "transaction_date",
    "tran_date",
    "post_date",
    "value_date",
    "txn date",
    "transaction date",
    "post date",
    "booking date",
]

VALUE_DATE_HEADERS = [
    "value_date",
    "val_date",
    "val date",
    "value date",
    "effective_date",
]

DESCRIPTION_HEADERS = [
    "description",
    "narration",
    "particulars",
    "remarks",
    "transaction_details",
    "transaction description",
    "details",
    "transaction remarks",
]

REFERENCE_HEADERS = [
    "chq_ref_no",
    "ref_no",
    "reference_no",
    "reference",
    "ref",
    "utr",
    "utr_number",
    "chq_no",
    "cheque_no",
    "cheque_number",
    "chq / ref no",
    "chq/ref no",
    "cheque/reference no",
    "ref no./utr",
    "tran id",
]

DEBIT_HEADERS = [
    "debit",
    "withdrawal",
    "dr",
    "withdrawal_amt",
    "debit_amount",
    "withdrawal amount",
    "debit amount",
    "dr amount",
    "debit (inr)",
]

CREDIT_HEADERS = [
    "credit",
    "deposit",
    "cr",
    "deposit_amt",
    "credit_amount",
    "deposit amount",
    "credit amount",
    "cr amount",
    "credit (inr)",
]

BALANCE_HEADERS = [
    "balance",
    "closing_balance",
    "bal",
    "available_balance",
    "closing balance",
    "net balance",
    "balance (inr)",
]

SUPPORTED_DATE_FORMATS = [
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%Y-%m-%d",
    "%d/%m/%y",
    "%d-%m-%y",
    "%d %b %Y",
    "%d-%b-%Y",
    "%d %B %Y",
    "%d-%b-%y",
    "%Y/%m/%d",
    "%d.%m.%Y",
]


@dataclass
class ParsedTransactionRow:
    source_row_number: int
    transaction_date: datetime
    value_date: datetime | None
    description: str
    normalized_description: str
    reference_number: str | None
    utr_number: str | None
    transaction_type: TransactionType
    debit_paise: int
    credit_paise: int
    balance_paise: int | None
    transaction_fingerprint: str
    payer_vpa: str | None = None
    raw_row: dict[str, Any] = field(default_factory=dict)


@dataclass
class RejectedRow:
    source_row_number: int
    reason: str
    raw_row: dict[str, Any] = field(default_factory=dict)


@dataclass
class ParseResult:
    total_rows: int
    valid_rows: list[ParsedTransactionRow]
    rejected_rows: list[RejectedRow]
    file_checksum: str
    detected_headers: dict[str, str]
    bank_profile: str


def parse_bank_date(date_str: str) -> datetime:
    """Parses Indian bank date strings into timezone-aware UTC datetime."""
    cleaned = date_str.strip()
    if not cleaned:
        raise ValueError("Transaction date cannot be empty")

    # If timestamp has time part, split or try parsing with time
    cleaned_date = cleaned.split(" ")[0] if " " in cleaned and ":" in cleaned else cleaned

    for fmt in SUPPORTED_DATE_FORMATS:
        try:
            parsed = datetime.strptime(cleaned_date, fmt)
            return parsed.replace(tzinfo=UTC)
        except ValueError:
            continue

    # Try full isoformat
    try:
        parsed = datetime.fromisoformat(cleaned)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    except Exception as exc:
        raise ValueError(
            f"Unable to parse date '{date_str}'. Expected format DD/MM/YYYY or YYYY-MM-DD."
        ) from exc


def normalize_header(header: str) -> str:
    """Normalizes header string for mapping comparison."""
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", header.strip().lower())
    return cleaned.strip("_")


def map_columns(headers: list[str], custom_mapping: dict[str, str] | None = None) -> dict[str, str]:
    """Detects and maps standard bank column semantics from CSV headers."""
    normalized_map = {normalize_header(h): h for h in headers}
    field_mapping: dict[str, str] = {}

    if custom_mapping:
        for standard_key, csv_col in custom_mapping.items():
            if csv_col in headers:
                field_mapping[standard_key] = csv_col
            elif normalize_header(csv_col) in normalized_map:
                field_mapping[standard_key] = normalized_map[normalize_header(csv_col)]

    def find_match(candidates: list[str]) -> str | None:
        for c in candidates:
            norm_c = normalize_header(c)
            if norm_c in normalized_map:
                return normalized_map[norm_c]
            # Partial match
            for norm_h, original_h in normalized_map.items():
                if norm_c == norm_h or norm_c in norm_h:
                    return original_h
        return None

    if "date" not in field_mapping:
        date_col = find_match(DATE_HEADERS)
        if date_col:
            field_mapping["date"] = date_col

    if "value_date" not in field_mapping:
        vdate_col = find_match(VALUE_DATE_HEADERS)
        if vdate_col and vdate_col != field_mapping.get("date"):
            field_mapping["value_date"] = vdate_col

    if "description" not in field_mapping:
        desc_col = find_match(DESCRIPTION_HEADERS)
        if desc_col:
            field_mapping["description"] = desc_col

    if "reference" not in field_mapping:
        ref_col = find_match(REFERENCE_HEADERS)
        if ref_col:
            field_mapping["reference"] = ref_col

    if "debit" not in field_mapping:
        debit_col = find_match(DEBIT_HEADERS)
        if debit_col:
            field_mapping["debit"] = debit_col

    if "credit" not in field_mapping:
        credit_col = find_match(CREDIT_HEADERS)
        if credit_col:
            field_mapping["credit"] = credit_col

    if "balance" not in field_mapping:
        bal_col = find_match(BALANCE_HEADERS)
        if bal_col:
            field_mapping["balance"] = bal_col

    return field_mapping


class BankStatementParser:
    """Parses and validates bank statement CSV files."""

    def __init__(self, society_id: UUID) -> None:
        self.society_id = society_id

    def parse(
        self,
        file_bytes: bytes,
        custom_mapping: dict[str, str] | None = None,
        bank_profile: str = "AUTO",
    ) -> ParseResult:
        file_checksum = compute_file_checksum(file_bytes)

        # Decode with utf-8-sig to automatically strip UTF-8 BOM
        try:
            content = file_bytes.decode("utf-8-sig")
        except UnicodeDecodeError:
            # Fallback to latin-1 / windows-1252 if strictly needed
            content = file_bytes.decode("latin-1")

        # Detect delimiter
        sample = content[:4096]
        delimiter = ","
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
            delimiter = dialect.delimiter
        except Exception:
            # Default to comma
            delimiter = ","

        reader = csv.reader(io.StringIO(content), delimiter=delimiter)
        raw_rows = list(reader)

        if not raw_rows:
            return ParseResult(
                total_rows=0,
                valid_rows=[],
                rejected_rows=[RejectedRow(source_row_number=0, reason="Uploaded file is empty")],
                file_checksum=file_checksum,
                detected_headers={},
                bank_profile=bank_profile,
            )

        # Locate header row: skip preliminary metadata rows (account details, address, etc.)
        header_row_index = -1
        header_candidates: list[str] = []

        for idx, row in enumerate(raw_rows[:25]):
            row_str = " ".join(normalize_header(c) for c in row if c)
            # Check if this row contains date and (description or narration or particulars or credit or debit)
            has_date = any(
                normalize_header(dh) in row_str for dh in ["date", "txn_date", "post_date"]
            )
            has_desc_or_amt = any(
                normalize_header(h) in row_str
                for h in [
                    "narration",
                    "description",
                    "particulars",
                    "credit",
                    "debit",
                    "withdrawal",
                    "deposit",
                ]
            )
            if has_date and has_desc_or_amt:
                header_row_index = idx
                header_candidates = [c.strip() for c in row if c is not None]
                break

        if header_row_index == -1:
            # Fall back to row 0
            header_row_index = 0
            header_candidates = [c.strip() for c in raw_rows[0] if c is not None]

        col_mapping = map_columns(header_candidates, custom_mapping)

        # Check required columns
        missing_required = []
        if "date" not in col_mapping:
            missing_required.append("Transaction Date")
        if "description" not in col_mapping:
            missing_required.append("Description/Narration")
        if "credit" not in col_mapping and "debit" not in col_mapping:
            missing_required.append("Credit/Debit Amount")

        if missing_required:
            return ParseResult(
                total_rows=0,
                valid_rows=[],
                rejected_rows=[
                    RejectedRow(
                        source_row_number=header_row_index + 1,
                        reason=f"Missing essential bank statement columns: {', '.join(missing_required)}",
                        raw_row={"detected_headers": header_candidates},
                    )
                ],
                file_checksum=file_checksum,
                detected_headers=col_mapping,
                bank_profile=bank_profile,
            )

        valid_rows: list[ParsedTransactionRow] = []
        rejected_rows: list[RejectedRow] = []

        # Map header name to list index
        header_idx_map: dict[str, int] = {}
        for h_key, h_name in col_mapping.items():
            with contextlib.suppress(ValueError):
                header_idx_map[h_key] = header_candidates.index(h_name)

        total_data_rows = 0

        for row_num, row_data in enumerate(
            raw_rows[header_row_index + 1 :], start=header_row_index + 2
        ):
            # Skip empty rows
            if not row_data or not any(str(c).strip() for c in row_data):
                continue

            total_data_rows += 1
            raw_dict = {
                header_candidates[i]: row_data[i]
                for i in range(min(len(header_candidates), len(row_data)))
            }

            try:
                # 1. Parse Date
                date_idx = header_idx_map.get("date")
                if date_idx is None or date_idx >= len(row_data):
                    rejected_rows.append(
                        RejectedRow(
                            source_row_number=row_num,
                            reason="Missing transaction date cell",
                            raw_row=raw_dict,
                        )
                    )
                    continue

                raw_date = row_data[date_idx].strip()
                if not raw_date:
                    rejected_rows.append(
                        RejectedRow(
                            source_row_number=row_num,
                            reason="Empty transaction date",
                            raw_row=raw_dict,
                        )
                    )
                    continue

                txn_date = parse_bank_date(raw_date)

                # Optional value date
                value_date: datetime | None = None
                vdate_idx = header_idx_map.get("value_date")
                if vdate_idx is not None and vdate_idx < len(row_data):
                    raw_vdate = row_data[vdate_idx].strip()
                    if raw_vdate:
                        try:
                            value_date = parse_bank_date(raw_vdate)
                        except Exception:
                            value_date = None

                # 2. Parse Description
                desc_idx = header_idx_map.get("description")
                raw_desc = (
                    row_data[desc_idx].strip()
                    if desc_idx is not None and desc_idx < len(row_data)
                    else ""
                )
                if not raw_desc:
                    rejected_rows.append(
                        RejectedRow(
                            source_row_number=row_num,
                            reason="Missing transaction description or narration",
                            raw_row=raw_dict,
                        )
                    )
                    continue

                norm_desc = normalize_narration(raw_desc)

                # 3. Parse Reference
                ref_idx = header_idx_map.get("reference")
                raw_ref = (
                    row_data[ref_idx].strip()
                    if ref_idx is not None and ref_idx < len(row_data)
                    else None
                )

                utr_num, ref_num = extract_utr_and_reference(raw_desc, raw_ref)

                # 4. Parse Amounts (Debit / Credit)
                debit_paise = 0
                credit_paise = 0

                debit_idx = header_idx_map.get("debit")
                if debit_idx is not None and debit_idx < len(row_data):
                    raw_debit = row_data[debit_idx].strip()
                    if raw_debit:
                        debit_paise = decimal_to_paise(raw_debit)

                credit_idx = header_idx_map.get("credit")
                if credit_idx is not None and credit_idx < len(row_data):
                    raw_credit = row_data[credit_idx].strip()
                    if raw_credit:
                        credit_paise = decimal_to_paise(raw_credit)

                # Validate transaction amount logic
                if debit_paise == 0 and credit_paise == 0:
                    rejected_rows.append(
                        RejectedRow(
                            source_row_number=row_num,
                            reason="Both debit and credit amounts are zero or empty",
                            raw_row=raw_dict,
                        )
                    )
                    continue

                if debit_paise > 0 and credit_paise > 0:
                    rejected_rows.append(
                        RejectedRow(
                            source_row_number=row_num,
                            reason=f"Ambiguous record: contains both debit (₹{debit_paise / 100:.2f}) and credit (₹{credit_paise / 100:.2f})",
                            raw_row=raw_dict,
                        )
                    )
                    continue

                txn_type = TransactionType.CREDIT if credit_paise > 0 else TransactionType.DEBIT

                # 5. Parse Balance
                balance_paise: int | None = None
                bal_idx = header_idx_map.get("balance")
                if bal_idx is not None and bal_idx < len(row_data):
                    raw_bal = row_data[bal_idx].strip()
                    if raw_bal:
                        try:
                            balance_paise = decimal_to_paise(raw_bal)
                        except Exception:
                            balance_paise = None

                # Extract UPI VPA if present in description
                payer_vpa = extract_upi_vpa(raw_desc)

                # Compute deterministic fingerprint
                fingerprint = compute_transaction_fingerprint(
                    society_id=self.society_id,
                    txn_date=txn_date,
                    credit_paise=credit_paise,
                    debit_paise=debit_paise,
                    reference=utr_num or ref_num,
                    normalized_desc=norm_desc,
                    source_row_number=row_num,
                )

                valid_rows.append(
                    ParsedTransactionRow(
                        source_row_number=row_num,
                        transaction_date=txn_date,
                        value_date=value_date,
                        description=raw_desc,
                        normalized_description=norm_desc,
                        reference_number=ref_num,
                        utr_number=utr_num,
                        transaction_type=txn_type,
                        debit_paise=debit_paise,
                        credit_paise=credit_paise,
                        balance_paise=balance_paise,
                        transaction_fingerprint=fingerprint,
                        payer_vpa=payer_vpa,
                        raw_row=raw_dict,
                    )
                )

            except Exception as row_exc:
                rejected_rows.append(
                    RejectedRow(
                        source_row_number=row_num,
                        reason=f"Row parsing failed: {row_exc}",
                        raw_row=raw_dict,
                    )
                )

        return ParseResult(
            total_rows=total_data_rows,
            valid_rows=valid_rows,
            rejected_rows=rejected_rows,
            file_checksum=file_checksum,
            detected_headers=col_mapping,
            bank_profile=bank_profile,
        )
