"""AI-Assisted Complaint Classifier & Triage Provider

Provides automated categorization, priority recommendation, and concise summarization.

SAFETY & DESIGN INVARIANTS:
1. AI decisions are advisory only. They are stored in distinct `ai_suggested_*` columns.
2. AI suggestions NEVER overwrite or downgrade deterministic safety escalations.
3. Completely deterministic offline fallback provider ensuring 100% test reliability and zero paid API requirement.
4. Resilient to unexpected inputs; never causes complaint creation failure.
"""

import abc
import logging
from dataclasses import dataclass

from app.domains.complaints.models import ComplaintCategory, ComplaintPriority

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AITriageResult:
    suggested_category: ComplaintCategory
    suggested_priority: ComplaintPriority
    confidence_score: float
    summary: str
    urgency_reason: str


class AIClassifierProvider(abc.ABC):
    @abc.abstractmethod
    def classify(
        self, title: str, description: str, selected_category: ComplaintCategory
    ) -> AITriageResult:
        """Analyzes complaint text and returns classification recommendations."""
        ...


class DeterministicAIClassifierProvider(AIClassifierProvider):
    """Deterministic, rule-based AI classifier provider with zero external dependencies."""

    _CATEGORY_KEYWORDS: dict[ComplaintCategory, list[str]] = {
        ComplaintCategory.PLUMBING: [
            "leak",
            "pipe",
            "tap",
            "faucet",
            "flush",
            "drain",
            "sink",
            "toilet",
            "bathroom",
            "sewage",
            "clog",
            "overflow",
            "washroom",
            "plumber",
        ],
        ComplaintCategory.ELECTRICAL: [
            "light",
            "bulb",
            "fan",
            "switch",
            "socket",
            "power",
            "mcb",
            "tripping",
            "wiring",
            "geyser",
            "fuse",
            "voltage",
            "electrician",
            "plug",
        ],
        ComplaintCategory.LIFT: [
            "lift",
            "elevator",
            "lift door",
            "lift button",
            "lift display",
            "lift jerky",
            "elevator maintenance",
        ],
        ComplaintCategory.HOUSEKEEPING: [
            "cleaning",
            "garbage",
            "trash",
            "dustbin",
            "dirty",
            "corridor",
            "staircase",
            "sweeping",
            "mopping",
            "spill",
            "smell",
            "pest",
        ],
        ComplaintCategory.SECURITY: [
            "security",
            "guard",
            "gate",
            "boom barrier",
            "cctv",
            "camera",
            "visitor",
            "parking issue",
            "stranger",
            "trespass",
            "theft",
            "lock",
        ],
        ComplaintCategory.WATER_SUPPLY: [
            "no water",
            "water pressure",
            "tanker",
            "dirty water",
            "muddy water",
            "drinking water",
            "overhead tank",
            "water shortage",
        ],
        ComplaintCategory.WASTE_MANAGEMENT: [
            "waste chute",
            "segregation",
            "compost",
            "waste disposal",
            "dumpster",
            "overflowing bin",
        ],
        ComplaintCategory.STRUCTURAL: [
            "crack",
            "seepage",
            "dampness",
            "plaster",
            "balcony",
            "pillar",
            "beam",
            "roof",
            "waterproofing",
        ],
        ComplaintCategory.COMMON_AREA: [
            "gym",
            "clubhouse",
            "swimming pool",
            "garden",
            "park",
            "play area",
            "tennis court",
            "intercom",
            "street light",
        ],
    }

    _HIGH_PRIORITY_KEYWORDS: list[str] = [
        "urgent",
        "emergency",
        "immediately",
        "severe",
        "entire flat",
        "flooding",
        "blackout",
        "no water",
        "stuck",
        "hazardous",
        "unsafe",
    ]

    _LOW_PRIORITY_KEYWORDS: list[str] = [
        "minor",
        "cosmetic",
        "slight",
        "whenever possible",
        "not urgent",
        "noise",
        "squeak",
        "loose",
        "aesthetic",
    ]

    def classify(
        self, title: str, description: str, selected_category: ComplaintCategory
    ) -> AITriageResult:
        try:
            combined = f"{title} {description}".lower()

            # 1. Determine best category match based on keyword frequency
            best_category = selected_category
            max_matches = 0

            for cat, keywords in self._CATEGORY_KEYWORDS.items():
                matches = sum(1 for kw in keywords if kw in combined)
                if matches > max_matches:
                    max_matches = matches
                    best_category = cat

            # 2. Confidence score based on matches
            if max_matches >= 3:
                confidence = 0.95
            elif max_matches >= 1:
                confidence = 0.82
            elif selected_category != ComplaintCategory.OTHER:
                confidence = 0.70
                best_category = selected_category
            else:
                confidence = 0.50
                best_category = ComplaintCategory.OTHER

            # 3. Determine priority recommendation
            high_count = sum(1 for kw in self._HIGH_PRIORITY_KEYWORDS if kw in combined)
            low_count = sum(1 for kw in self._LOW_PRIORITY_KEYWORDS if kw in combined)

            if high_count > 0:
                priority = ComplaintPriority.HIGH
                urgency_reason = "Urgency keywords detected indicating operational impact"
            elif low_count > 0:
                priority = ComplaintPriority.LOW
                urgency_reason = "Minor or non-urgent keywords detected"
            else:
                priority = ComplaintPriority.MEDIUM
                urgency_reason = "Standard township maintenance timeline recommended"

            # 4. Summary generation (short first sentence or truncated title)
            clean_title = title.strip()
            summary = clean_title if len(clean_title) <= 120 else f"{clean_title[:117]}..."

            return AITriageResult(
                suggested_category=best_category,
                suggested_priority=priority,
                confidence_score=confidence,
                summary=summary,
                urgency_reason=urgency_reason,
            )
        except Exception as e:
            logger.warning("Deterministic AI triage fallback triggered due to error: %s", e)
            return AITriageResult(
                suggested_category=selected_category,
                suggested_priority=ComplaintPriority.MEDIUM,
                confidence_score=0.5,
                summary=title[:120],
                urgency_reason="Default triage assignment",
            )


# Alias for default injection
MockAIClassifierProvider = DeterministicAIClassifierProvider
