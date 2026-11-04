"""Deterministic Multilingual Safety Escalation Engine

Evaluates resident complaint titles and descriptions against high-risk safety keywords
and hazard patterns across English, Hindi, and Marathi.

SAFETY INVARIANTS:
1. Deterministic safety escalation executes BEFORE any AI classification.
2. If safety is triggered, priority MUST be forced to CRITICAL and cannot be downgraded by AI.
3. Operates completely offline with zero external network or model dependency.
4. Explains the exact hazard detected in safety_escalation_reason.
"""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class SafetyCheckResult:
    is_safety_escalated: bool
    reason: str | None


# Safety hazard patterns organized by hazard category and languages (English, Hindi, Marathi)
_HAZARD_PATTERNS: list[tuple[str, list[str]]] = [
    (
        "Fire or Smoke Hazard",
        [
            r"\bfire\b",
            r"\bsmoke\b",
            r"\bflames?\b",
            r"\bburning\b",
            r"\bexplosion\b",
            r"आग",
            r"धुआं",
            r"धुंआ",
            r"जल रहा",
            r"विस्फोट",
            r"धूर",
            r"आगीची",
            r"स्फोट",
        ],
    ),
    (
        "Gas Leak Hazard",
        [
            r"\bgas\s+leak\b",
            r"\blpg\s+leak\b",
            r"\bgas\s+smell\b",
            r"\bcylinder\s+leak\b",
            r"गैस\s+लीक",
            r"गैस\s+की\s+बदबू",
            r"सिलेंडर\s+लीक",
            r"गॅस\s+गळती",
            r"गॅसचा\ वास",
        ],
    ),
    (
        "Trapped in Lift / Elevator Hazard",
        [
            r"\btrapped\s+in\s+(?:the\s+)?(?:lift|elevator)\b",
            r"\b(?:lift|elevator)\s+stuck\b",
            r"\bperson\s+stuck\s+in\s+(?:lift|elevator)\b",
            r"\bkid\s+stuck\s+in\s+(?:lift|elevator)\b",
            r"\bchild\s+stuck\s+in\s+(?:lift|elevator)\b",
            r"लिफ्ट\s+में\s+फंसे?",
            r"लिफ्ट\s+अटक",
            r"लिफ्ट\s+बंद",
            r"लिफ्ट\s+अडकली",
            r"लिफ्टमध्ये\s+अडकले",
        ],
    ),
    (
        "Electrical Sparking / Short Circuit / Shock Hazard",
        [
            r"\bshort\s+circuit\b",
            r"\bsparking\b",
            r"\belectric\s+shock\b",
            r"\blive\s+wire\b",
            r"\bcable\s+on\s+fire\b",
            r"\bmeter\s+box\s+fire\b",
            r"शॉर्ट\s+सर्किट",
            r"स्पार्किंग",
            r"बिजली\s+का\s+झटका",
            r"करेंट",
            r"खुला\s+तार",
            r"विजेचा\s+धक्का",
            r"विजेची\s+तार",
            r"शॉक",
        ],
    ),
    (
        "Structural / Ceiling Collapse Hazard",
        [
            r"\bceiling\s+collapse\b",
            r"\broof\s+collapse\b",
            r"\bwall\s+collapse\b",
            r"\bbalcony\s+falling\b",
            r"\bdebris\s+falling\b",
            r"\bplaster\s+falling\b",
            r"छत\s+गिर",
            r"दीवार\s+गिर",
            r"मलबा\s+गिर",
            r"पडझड",
            r"छत\s+कौसळली",
            r"भिंत\s+पडली",
        ],
    ),
    (
        "Severe Flooding / Electrical Water Hazard",
        [
            r"\bsevere\s+flooding\b",
            r"\bwater\s+in\s+meter\s+room\b",
            r"\bwater\s+entering\s+lift\s+shaft\b",
            r"\belectricity\s+water\s+contact\b",
            r"मीटर\s+रूम\s+में\s+पानी",
            r"लिफ्ट\s+में\s+पानी",
            r"पाणी\s+मीटर\s+रूम",
        ],
    ),
]


def check_safety_escalation(title: str, description: str) -> SafetyCheckResult:
    """Evaluates complaint title and description for critical safety hazards.

    Args:
        title: Complaint subject / short title
        description: Full detailed complaint description

    Returns:
        SafetyCheckResult with boolean escalation flag and explanatory hazard reason.
    """
    text = f"{title}\n{description}".lower()

    for hazard_name, patterns in _HAZARD_PATTERNS:
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE | re.UNICODE):
                return SafetyCheckResult(
                    is_safety_escalated=True,
                    reason=f"Safety Hazard Detected: {hazard_name}",
                )

    return SafetyCheckResult(is_safety_escalated=False, reason=None)
