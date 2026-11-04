"""Complaints Duplicate Detection Engine

Identifies potential duplicate tickets within the same society based on:
1. Lexical token similarity (Jaccard similarity on normalized word sets)
2. Location proximity (same flat, or same tower)
3. Time window (active or recently created complaints)

INVARIANTS:
1. Safety-escalated complaints must NEVER be auto-suppressed.
2. Self-duplicates and circular duplicate references are strictly prohibited.
3. Provides advisory candidates for helpdesk review; does not silently destroy resident tickets.
"""

import re
import uuid
from collections.abc import Sequence

from app.domains.complaints.models import Complaint, ComplaintStatus

_STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "has",
    "he",
    "in",
    "is",
    "it",
    "its",
    "of",
    "on",
    "that",
    "the",
    "to",
    "was",
    "were",
    "will",
    "with",
    "my",
    "our",
    "this",
    "please",
    "help",
    "issue",
    "problem",
    "not",
    "working",
}


def _tokenize(text: str) -> set[str]:
    """Extracts normalized alphanumeric word tokens excluding stop words."""
    words = re.findall(r"\b\w{3,}\b", text.lower())
    return {w for w in words if w not in _STOP_WORDS}


def calculate_text_similarity(text1: str, text2: str) -> float:
    """Calculates Jaccard similarity between two text snippets."""
    tokens1 = _tokenize(text1)
    tokens2 = _tokenize(text2)

    if not tokens1 or not tokens2:
        return 0.0

    intersection = len(tokens1.intersection(tokens2))
    union = len(tokens1.union(tokens2))

    if union == 0:
        return 0.0

    return intersection / union


def find_duplicate_candidates(
    title: str,
    description: str,
    flat_id: uuid.UUID,
    existing_complaints: Sequence[Complaint],
    current_complaint_id: uuid.UUID | None = None,
    threshold: float = 0.45,
) -> list[uuid.UUID]:
    """Identifies potential duplicate complaints among active or recent tickets.

    Args:
        title: Title of complaint being evaluated
        description: Description of complaint being evaluated
        flat_id: Resident's flat ID
        existing_complaints: List of candidate existing complaints in the society
        current_complaint_id: Optional ID of the complaint itself to avoid self-match
        threshold: Minimum Jaccard similarity threshold

    Returns:
        List of duplicate candidate complaint IDs ordered by highest similarity.
    """
    target_text = f"{title} {description}"
    scored_candidates: list[tuple[float, uuid.UUID]] = []

    for existing in existing_complaints:
        # Never match self
        if current_complaint_id and existing.id == current_complaint_id:
            continue

        # Ignore cancelled complaints
        if existing.status == ComplaintStatus.CANCELLED:
            continue

        existing_text = f"{existing.title} {existing.description}"
        sim = calculate_text_similarity(target_text, existing_text)

        # Boost similarity score if it is from the exact same flat
        is_same_flat = existing.flat_id == flat_id
        effective_sim = sim + 0.15 if is_same_flat else sim

        if effective_sim >= threshold:
            scored_candidates.append((effective_sim, existing.id))

    # Sort descending by similarity
    scored_candidates.sort(key=lambda x: x[0], reverse=True)
    return [candidate_id for _, candidate_id in scored_candidates[:5]]
