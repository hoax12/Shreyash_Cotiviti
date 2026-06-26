"""Deterministic claim audit against extracted NCCI bundling rules.

No LLM calls — plain dict comparisons and boolean logic only.

Claim dict schema
-----------------
{
    "date_of_service": "YYYY-MM-DD",   # single DOS for the claim
    "lines": [
        {
            "cpt_code": "28230",       # CPT/HCPCS code on this line
            "modifiers": ["59"],       # list of modifier strings (may be empty)
            "anatomical_location": "toe",  # optional; used for same-location checks
        },
        ...
    ],
    # Optional quantitative fields (checked when present on rule or claim):
    "visit_count": 3,
    "duration_days": 14,
}

Rule dict fields (from extractor)
---------------------------------
- column1_code, column2_code: code pair
- modifier_allowed: bool — if True, a valid NCCI modifier on Column 2 bypasses the edit
- Optional: max_visits, min_duration_days — enforced when present on the rule
"""

from __future__ import annotations

from extractor import SIMULATION_RULES

# NCCI-associated modifiers that indicate a distinct encounter or structure.
VALID_NCCI_MODIFIERS = frozenset({"59", "XE", "XS", "XP", "XU"})


def normalize_code(code) -> str:
    """Normalize CPT codes for comparison."""
    if code is None:
        return ""
    text = str(code).strip()
    if text.isdigit():
        return str(int(text))
    return text


def _normalize_modifier(modifier: str) -> str:
    return str(modifier).strip().upper()


def _line_has_valid_modifier(line: dict) -> bool:
    modifiers = line.get("modifiers") or []
    return any(_normalize_modifier(m) in VALID_NCCI_MODIFIERS for m in modifiers)


def _same_anatomical_location(line1: dict, line2: dict) -> bool:
    """True when both lines share a location, or location is unspecified (conservative)."""
    loc1 = (line1.get("anatomical_location") or "").strip().lower()
    loc2 = (line2.get("anatomical_location") or "").strip().lower()
    if not loc1 or not loc2:
        return True
    return loc1 == loc2


def _check_quantitative_constraints(
    rule: dict, claim: dict
) -> str | None:
    """Return a failure reason if a quantitative constraint is violated, else None."""
    max_visits = rule.get("max_visits")
    if max_visits is not None:
        visit_count = claim.get("visit_count")
        if visit_count is not None and visit_count > max_visits:
            return (
                f"visit_count {visit_count} exceeds rule max_visits {max_visits} "
                f"for pair {rule.get('column1_code')}/{rule.get('column2_code')}"
            )

    min_duration = rule.get("min_duration_days")
    if min_duration is not None:
        duration_days = claim.get("duration_days")
        if duration_days is not None and duration_days < min_duration:
            return (
                f"duration_days {duration_days} is below rule min_duration_days "
                f"{min_duration} for pair {rule.get('column1_code')}/{rule.get('column2_code')}"
            )

    return None


def _check_rule_pair(rule: dict, claim: dict) -> str | None:
    """Return a failure reason if this rule is violated by the claim, else None."""
    column1 = normalize_code(rule.get("column1_code"))
    column2 = normalize_code(rule.get("column2_code"))
    if not column1 or not column2:
        return None

    qty_reason = _check_quantitative_constraints(rule, claim)
    if qty_reason:
        return qty_reason

    lines = claim.get("lines") or []
    col1_lines = [ln for ln in lines if normalize_code(ln.get("cpt_code")) == column1]
    col2_lines = [ln for ln in lines if normalize_code(ln.get("cpt_code")) == column2]

    if not col1_lines or not col2_lines:
        return None

    modifier_allowed = bool(rule.get("modifier_allowed", False))
    claim_dos = claim.get("date_of_service", "unspecified")

    for line1 in col1_lines:
        for line2 in col2_lines:
            if not _same_anatomical_location(line1, line2):
                continue

            if modifier_allowed and _line_has_valid_modifier(line2):
                continue

            location = line1.get("anatomical_location") or line2.get("anatomical_location")
            location_note = f" at {location}" if location else ""
            if modifier_allowed:
                return (
                    f"Column 2 code {column2} is bundled with Column 1 code {column1} "
                    f"on date of service {claim_dos}{location_note}: both codes are present "
                    f"for the same anatomical location without a valid NCCI modifier "
                    f"(59, XE, XS, XP, or XU) on the Column 2 line."
                )
            return (
                f"Column 2 code {column2} may not be reported with Column 1 code "
                f"{column1} on date of service {claim_dos}{location_note}: "
                f"modifier bypass is not allowed for this edit."
            )

    return None


def audit_claim(extracted_rules: list[dict], claim: dict) -> dict:
    """Audit a claim against extracted bundling rules.

    Returns {"verdict": "pass" | "fail", "reason": "<human-readable explanation>"}.
    """
    if not extracted_rules:
        return {
            "verdict": "pass",
            "reason": "No bundling rules to apply.",
        }

    for rule in extracted_rules:
        violation = _check_rule_pair(rule, claim)
        if violation:
            return {"verdict": "fail", "reason": violation}

    return {
        "verdict": "pass",
        "reason": "No NCCI bundling violations detected for the extracted rule set.",
    }


# Illustrative test inputs constructed for the POC — NOT real claims data.
# No dollar amounts or fabricated claims counts are included.
EXAMPLE_CLAIMS = {
    "pass": {
        "date_of_service": "2024-01-15",
        "lines": [
            {"cpt_code": "28230", "modifiers": [], "anatomical_location": "toe"},
            {
                "cpt_code": "64450",
                "modifiers": ["59"],
                "anatomical_location": "toe",
            },
        ],
    },
    "fail": {
        "date_of_service": "2024-01-15",
        "lines": [
            {"cpt_code": "28230", "modifiers": [], "anatomical_location": "toe"},
            {"cpt_code": "64450", "modifiers": [], "anatomical_location": "toe"},
        ],
    },
}


if __name__ == "__main__":
    rules = SIMULATION_RULES
    for label, example_claim in EXAMPLE_CLAIMS.items():
        result = audit_claim(rules, example_claim)
        print(f"{label.upper()} example: verdict={result['verdict']}")
        print(f"  reason: {result['reason']}")
        print()
