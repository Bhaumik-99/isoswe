"""Reconciliation Matching Engine

Provides transparent, deterministic layered matching between bank statement credits
and society resident records, payments, and outstanding invoices:

Level 1: Exact UTR / Provider Payment Reference Match (Weight: 60)
Level 2: Exact Amount + Reference Token Match (Weight: 20)
Level 3: Amount, Date & Resident Identity / Unit Clues (Weight: 10)
Level 4: Amount & Outstanding Invoice Balance Heuristic (Weight: 10)
Level 5: Unmatched / Ambiguous Review Queue Routing (< 70 Score)

CONFIDENCE TIERS:
- HIGH: 90 - 100
- MEDIUM: 70 - 89
- LOW: < 70 (Requires manual review before approval)

TOWER-FLAT COMPOSITE MATCHING:
- Flat numbers are unique within a tower, but NOT across towers (UniqueConstraint on tower_id+flat_number).
- A narration clue such as "T07-1203" is resolved to the exact tower-flat pair.
- A bare flat number (e.g. "1203") resolves unambiguously only when exactly one flat across
  all towers has that number; otherwise it is treated as ambiguous (LOW confidence).
- A flat-only match is NEVER promoted to a confident tower match.
"""

import re
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from app.domains.billing.models import (
    Invoice,
    InvoiceStatus,
    Payment,
    PaymentStatus,
)
from app.domains.identity.models import Flat, FlatMembership, MembershipStatus, User
from app.domains.reconciliation.models import (
    BankTransaction,
    MatchConfidenceTier,
    MatchingLevel,
    ResidentUPIMapping,
)
from app.domains.reconciliation.normalizer import (
    extract_unit_clues,
    extract_upi_vpa,
    normalize_vpa,
)


def _parse_tower_flat_clue(clue: str) -> tuple[str | None, str | None]:
    """Parse a unit clue into an optional tower prefix and flat number.

    Handles formats produced by ``extract_unit_clues`` Pattern A:
    - "T07-1203"  → ("T07", "1203")
    - "T7-1203"   → ("T7", "1203")
    - "T12-0408"  → ("T12", "0408")
    - "B-408"     → ("B", "408")

    For bare flat-number clues (Pattern B/C) the tower is None:
    - "1203"      → (None, "1203")
    - "0408"      → (None, "0408")
    - "FLAT101"   → (None, "FLAT101")

    Returns (tower_upper, flat_upper) or (None, flat_upper).
    Both components are uppercased and stripped.
    """
    stripped = clue.strip().upper()
    # Match <letters+optional-digits>-<digits> e.g. T07-1203 or B-408
    m = re.match(r"^([A-Z]+\d*)-(\d+)$", stripped)
    if m:
        return m.group(1), m.group(2)
    # Bare numeric / alphanumeric flat clue
    return None, stripped if stripped else None


@dataclass
class CandidateEvaluation:
    flat_id: UUID | None
    resident_id: UUID | None
    invoice_id: UUID | None
    existing_payment_id: UUID | None
    confidence_score: float
    confidence_tier: MatchConfidenceTier
    matching_level: MatchingLevel
    explanation: str
    evidence: dict[str, Any] = field(default_factory=dict)


class MatchingEngine:
    """Evaluates candidate matches for bank transactions."""

    def __init__(self, society_id: UUID) -> None:
        self.society_id = society_id

    def evaluate_transaction(
        self,
        transaction: BankTransaction,
        invoices: list[Invoice],
        payments: list[Payment],
        flats: list[Flat],
        memberships: list[FlatMembership],
        users: dict[UUID, User],
        upi_mappings: list[ResidentUPIMapping] | None = None,
    ) -> list[CandidateEvaluation]:
        """Evaluates a bank credit transaction against existing society records.

        Debits are ineligible for resident payment matching.
        Returns a list of candidate evaluations sorted by confidence_score descending.
        """
        # Invariant: Debits are not resident payments
        if transaction.credit_paise <= 0 or transaction.transaction_type.value == "DEBIT":
            return []

        candidates: list[CandidateEvaluation] = []

        # Extract and normalize UPI VPA if present
        txn_vpa = transaction.payer_vpa or extract_upi_vpa(transaction.description)
        norm_txn_vpa = normalize_vpa(txn_vpa) if txn_vpa else None

        vpa_matched_mapping: ResidentUPIMapping | None = None
        if norm_txn_vpa and upi_mappings:
            for mapping in upi_mappings:
                if mapping.is_verified and normalize_vpa(mapping.vpa) == norm_txn_vpa:
                    vpa_matched_mapping = mapping
                    break

        # Build lookup maps for rapid deterministic evaluation
        flat_by_id = {f.id: f for f in flats}

        # Two-level flat lookup for correct tower-flat resolution.
        #
        # ``tower_flat_index[(tower_upper, flat_upper)]`` → Flat
        #   Keyed on the EXACT tower_number+flat_number pair.  Used when the
        #   narration contains a tower-qualified clue such as "T07-1203".
        #
        # ``flat_only_index[flat_upper]`` → list[Flat]
        #   Flat-number-only lookup.  A single entry means unambiguous; multiple
        #   entries (same flat number in different towers) is ambiguous and must
        #   NOT be promoted to a confident match.
        tower_flat_index: dict[tuple[str, str], Flat] = {}
        flat_only_index: dict[str, list[Flat]] = {}

        for f in flats:
            flat_num = f.flat_number.upper().strip()
            numeric_only = "".join(filter(str.isdigit, flat_num))

            # Build flat-only index (may have collisions across towers — intentional)
            flat_only_index.setdefault(flat_num, []).append(f)
            if numeric_only and numeric_only != flat_num:
                flat_only_index.setdefault(numeric_only, []).append(f)

            # Build tower-flat composite index
            tower = getattr(f, "tower", None)
            if tower is not None:
                tnum = tower.tower_number.upper().strip()
                # Store under exact tower_number e.g. ("T07", "1203")
                tower_flat_index[(tnum, flat_num)] = f
                if numeric_only and numeric_only != flat_num:
                    tower_flat_index[(tnum, numeric_only)] = f
                # Also store without leading zero in tower number e.g. ("T7", "1203")
                tnum_compact = re.sub(r"^([A-Z]+)0+(\d)", r"\1\2", tnum)
                if tnum_compact != tnum:
                    tower_flat_index[(tnum_compact, flat_num)] = f
                    if numeric_only and numeric_only != flat_num:
                        tower_flat_index[(tnum_compact, numeric_only)] = f

        # Map active resident memberships per flat
        resident_by_flat: dict[UUID, UUID] = {}
        for m in memberships:
            if m.status == MembershipStatus.APPROVED and m.is_primary:
                resident_by_flat[m.flat_id] = m.user_id

        # Map allocations for payments
        payment_invoice_map: dict[UUID, UUID] = {}
        for p in payments:
            if p.allocations:
                payment_invoice_map[p.id] = p.allocations[0].invoice_id

        invoice_by_id = {inv.id: inv for inv in invoices}

        # ---------------------------------------------------------------------
        # Level 1: Exact UTR / Provider Reference Match (Weight 60)
        # ---------------------------------------------------------------------
        txn_utr = (transaction.utr_number or "").strip().upper()
        txn_ref = (transaction.reference_number or "").strip().upper()

        matched_payment_ids: set[UUID] = set()

        for payment in payments:
            pay_ref = payment.provider_reference.strip().upper()
            is_utr_match = bool(
                txn_utr and (txn_utr == pay_ref or txn_utr in pay_ref or pay_ref in txn_utr)
            )
            is_ref_match = bool(
                txn_ref and (txn_ref == pay_ref or txn_ref in pay_ref or pay_ref in txn_ref)
            )

            if is_utr_match or is_ref_match:
                matched_payment_ids.add(payment.id)
                # Calculate confidence score
                score = 60.0  # Base Level 1 weight
                evidence = {
                    "level_1_utr_match": 60.0,
                    "matched_provider_reference": payment.provider_reference,
                    "provider": payment.provider,
                }

                # Amount check
                if payment.amount_paise == transaction.credit_paise:
                    score += 20.0
                    evidence["level_2_exact_amount"] = 20.0
                elif (
                    abs(payment.amount_paise - transaction.credit_paise) <= 100
                ):  # within ₹1 rounding
                    score += 15.0
                    evidence["level_2_near_amount"] = 15.0

                # Date compatibility (within 7 days)
                pay_date = payment.created_at
                txn_date = transaction.transaction_date
                days_diff = abs((pay_date.date() - txn_date.date()).days)
                if days_diff <= 3:
                    score += 10.0
                    evidence["level_3_date_proximity_days"] = days_diff
                elif days_diff <= 14:
                    score += 5.0
                    evidence["level_3_date_proximity_days"] = days_diff

                # Identity check from payment flat
                flat = flat_by_id.get(payment.flat_id)
                if flat:
                    score += 10.0
                    evidence["level_3_flat_match"] = flat.flat_number

                # Normalize score to max 100
                final_score = min(score, 100.0)
                tier = (
                    MatchConfidenceTier.HIGH
                    if final_score >= 90
                    else MatchConfidenceTier.MEDIUM
                    if final_score >= 70
                    else MatchConfidenceTier.LOW
                )

                inv_id = payment_invoice_map.get(payment.id)
                inv = invoice_by_id.get(inv_id) if inv_id else None
                inv_text = f" (Invoice {inv.invoice_number})" if inv else ""

                explanation = (
                    f"Level 1 Exact Match: Bank UTR/reference '{txn_utr or txn_ref}' matches payment '{payment.provider_reference}' "
                    f"for flat {flat.flat_number if flat else 'unknown'}{inv_text}. "
                    f"Confidence: {int(final_score)}%."
                )

                candidates.append(
                    CandidateEvaluation(
                        flat_id=payment.flat_id,
                        resident_id=payment.initiated_by,
                        invoice_id=inv_id,
                        existing_payment_id=payment.id,
                        confidence_score=final_score,
                        confidence_tier=tier,
                        matching_level=MatchingLevel.LEVEL_1_UTR,
                        explanation=explanation,
                        evidence=evidence,
                    )
                )

        # If a high-confidence Level 1 match was found, return immediately
        high_level_1 = [c for c in candidates if c.confidence_score >= 90]
        if high_level_1:
            return sorted(candidates, key=lambda x: x.confidence_score, reverse=True)

        # ---------------------------------------------------------------------
        # Level 3 & Level 4: Narration clues & Outstanding Invoice balance
        # ---------------------------------------------------------------------
        unit_clues = extract_unit_clues(transaction.description)
        detected_flats: set[UUID] = set()

        for clue in unit_clues:
            tower_prefix, flat_part = _parse_tower_flat_clue(clue)

            if tower_prefix is not None and flat_part is not None:
                # Tower-qualified clue: resolve via composite index (exact match)
                matched_flat = tower_flat_index.get((tower_prefix, flat_part))
                if matched_flat is not None:
                    detected_flats.add(matched_flat.id)
                    continue  # Exact tower-flat hit; skip ambiguous flat-only lookup for this clue
                # Also try numeric-only flat part against same tower
                flat_numeric = "".join(filter(str.isdigit, flat_part))
                if flat_numeric and flat_numeric != flat_part:
                    matched_flat = tower_flat_index.get((tower_prefix, flat_numeric))
                    if matched_flat is not None:
                        detected_flats.add(matched_flat.id)
                        continue
            else:
                # Bare flat-number clue: unambiguous only if exactly one flat has this number
                candidates_for_flat = flat_only_index.get(flat_part or "", [])
                if len(candidates_for_flat) == 1:
                    detected_flats.add(candidates_for_flat[0].id)
                # len == 0: no match; len > 1: ambiguous — do NOT add, requires tower context

        # Also search resident names in description
        norm_desc = transaction.normalized_description
        for u_id, user in users.items():
            if user.full_name:
                name_tokens = [tok.upper() for tok in user.full_name.split() if len(tok) >= 3]
                for tok in name_tokens:
                    if tok in norm_desc:
                        # Find flats for this user
                        for m in memberships:
                            if m.user_id == u_id and m.status == MembershipStatus.APPROVED:
                                detected_flats.add(m.flat_id)

        # Evaluate candidate invoices
        unpaid_invoices = [
            inv
            for inv in invoices
            if inv.status
            in (InvoiceStatus.UNPAID, InvoiceStatus.PARTIALLY_PAID, InvoiceStatus.OVERDUE)
        ]

        for inv in unpaid_invoices:
            # If a verified payer VPA matched a specific flat, never match this transaction to other flats on amount alone
            if vpa_matched_mapping and inv.flat_id != vpa_matched_mapping.flat_id:
                continue

            flat = flat_by_id.get(inv.flat_id)
            flat_num = flat.flat_number if flat else "Unknown"
            score = 0.0
            evidence = {}
            level = MatchingLevel.LEVEL_4_INVOICE_AMOUNT

            # Calculate current outstanding balance
            valid_allocated = 0
            for alloc in inv.allocations:
                if alloc.payment and alloc.payment.status == PaymentStatus.SUCCESS:
                    valid_allocated += alloc.allocated_paise
            outstanding_paise = max(0, inv.total_paise - valid_allocated)

            # Check if this flat was detected from verified VPA
            is_vpa_match = bool(vpa_matched_mapping and inv.flat_id == vpa_matched_mapping.flat_id)
            if is_vpa_match and vpa_matched_mapping:
                score += 45.0
                evidence["level_1_vpa_match"] = norm_txn_vpa
                evidence["vpa_resident_id"] = str(vpa_matched_mapping.resident_id)
                level = MatchingLevel.LEVEL_3_NARRATION_RESIDENT

            # Check if this flat was detected from narration clues
            is_flat_clue = inv.flat_id in detected_flats
            if is_flat_clue and not is_vpa_match:
                score += 40.0
                evidence["narration_unit_clue"] = flat_num
                level = MatchingLevel.LEVEL_3_NARRATION_RESIDENT

            # Check exact amount match
            if transaction.credit_paise == outstanding_paise:
                score += 35.0
                evidence["exact_invoice_outstanding_match"] = outstanding_paise
            elif transaction.credit_paise == inv.total_paise:
                score += 30.0
                evidence["exact_invoice_total_match"] = inv.total_paise
            elif transaction.credit_paise < outstanding_paise:
                score += 15.0
                evidence["partial_payment_amount"] = transaction.credit_paise
            elif transaction.credit_paise > outstanding_paise:
                score += 10.0
                evidence["overpayment_amount"] = transaction.credit_paise - outstanding_paise

            # Date proximity (invoice due date vs transaction date)
            inv_date = inv.due_date
            days_from_due = abs((inv_date.date() - transaction.transaction_date.date()).days)
            if days_from_due <= 15:
                score += 10.0
                evidence["due_date_proximity_days"] = days_from_due
            elif days_from_due <= 45:
                score += 5.0
                evidence["due_date_proximity_days"] = days_from_due

            # Resident identity clue
            resident_id = (
                vpa_matched_mapping.resident_id
                if is_vpa_match and vpa_matched_mapping
                else resident_by_flat.get(inv.flat_id)
            )
            if resident_id and resident_id in users and not is_vpa_match:
                res_user = users[resident_id]
                if res_user.full_name and any(
                    part.upper() in norm_desc
                    for part in res_user.full_name.split()
                    if len(part) >= 3
                ):
                    score += 15.0
                    evidence["resident_name_match"] = res_user.full_name

            # Check reference overlap
            if txn_ref and txn_ref in inv.invoice_number.upper():
                score += 20.0
                evidence["invoice_number_reference_match"] = inv.invoice_number

            # Governance invariant: Never match on amount alone without unit or identity corroboration
            if (
                not is_vpa_match
                and not is_flat_clue
                and "resident_name_match" not in evidence
                and "invoice_number_reference_match" not in evidence
            ):
                evidence["amount_alone_warning"] = (
                    "Amount matched without unit or identity corroboration; manual review required."
                )
                score = min(score, 45.0)

            # Only suggest if score meets minimum heuristic threshold (at least 45)
            if score >= 45.0:
                final_score = min(score, 100.0)
                tier = (
                    MatchConfidenceTier.HIGH
                    if final_score >= 90
                    else MatchConfidenceTier.MEDIUM
                    if final_score >= 70
                    else MatchConfidenceTier.LOW
                )

                upi_text = f"verified payer VPA '{norm_txn_vpa}', " if is_vpa_match else ""
                unit_text = "unit narration clue, " if is_flat_clue and not is_vpa_match else ""
                bal_text = (
                    "exact balance match, " if "exact_invoice_outstanding_match" in evidence else ""
                )
                explanation = (
                    f"Suggested match for Flat {flat_num} (Invoice {inv.invoice_number}, "
                    f"Outstanding ₹{outstanding_paise / 100:,.2f}) based on "
                    f"{upi_text}{unit_text}{bal_text}"
                    f"confidence: {int(final_score)}%."
                )

                candidates.append(
                    CandidateEvaluation(
                        flat_id=inv.flat_id,
                        resident_id=resident_id,
                        invoice_id=inv.id,
                        existing_payment_id=None,
                        confidence_score=final_score,
                        confidence_tier=tier,
                        matching_level=level,
                        explanation=explanation,
                        evidence=evidence,
                    )
                )

        # Sort candidates descending by confidence score
        candidates.sort(key=lambda x: x.confidence_score, reverse=True)

        # Check for ambiguity: if top two candidates have scores within 5 points and both < 90
        if len(candidates) >= 2:
            top_1 = candidates[0]
            top_2 = candidates[1]
            if (
                abs(top_1.confidence_score - top_2.confidence_score) <= 5.0
                and top_1.confidence_score < 90.0
            ):
                # Mark ambiguity in evidence
                top_1.evidence["is_ambiguous"] = True
                top_1.explanation += (
                    " (Notice: Multiple plausible matching invoices found; review required)."
                )

        return candidates


# Alias for architectural documentation
DeterministicMatchingEngine = MatchingEngine
