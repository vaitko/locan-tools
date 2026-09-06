"""Pure scoring for the GBP Optimizer — a port of the .NET GoogleBusinessProfileOptimizer checks."""

from __future__ import annotations

from dataclasses import dataclass

GENERIC_RECOMMENDATIONS = [
    "Use local keywords in your description (e.g., “barbershop in Austin”).",
    "Publish weekly Posts to keep your profile fresh.",
    "Ensure NAP (name, address, phone) matches your website and other listings.",
]


@dataclass
class ScoringResult:
    checks: list[dict]  # {"name": str, "pass": bool, "detail": str}
    score: float
    grade: str
    recommendations: list[str]


def _text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def phone_of(p: dict) -> str | None:
    return _text(p.get("nationalPhoneNumber")) or _text(p.get("internationalPhoneNumber"))


def grade_for(score: float) -> str:
    if score >= 90:
        return "A"
    if score >= 80:
        return "B+"
    if score >= 70:
        return "B"
    if score >= 60:
        return "C"
    return "Needs work"


def score_place(p: dict) -> ScoringResult:
    """Score a Places (New) details payload: six weighted checks totalling 100 points."""
    checks: list[dict] = []
    recommendations: list[str] = []
    score = 0.0

    def check(name: str, passed: bool, ok: str, fix: str, weight: int, recommendation: str) -> None:
        nonlocal score
        checks.append({"name": name, "pass": passed, "detail": ok if passed else fix})
        if passed:
            score += weight
        else:
            recommendations.append(recommendation)

    photo_count = len(p.get("photos") or [])
    review_count = int(p.get("userRatingCount") or 0)
    has_hours = bool((p.get("regularOpeningHours") or {}).get("weekdayDescriptions"))

    check(
        "Website",
        _text(p.get("websiteUri")) is not None,
        "Website present",
        "Add your website URL",
        15,
        "Add your website URL to your profile.",
    )
    check(
        "Opening hours",
        has_hours,
        "Hours set",
        "Add accurate opening hours",
        15,
        "Set accurate opening hours (incl. holidays).",
    )
    check(
        "Phone number",
        phone_of(p) is not None,
        "Phone present",
        "Add a phone number",
        10,
        "Add a visible phone number customers can call.",
    )
    check(
        "Photos",
        photo_count >= 5,
        f"{photo_count} photos",
        "Upload at least 5 quality photos",
        20,
        "Upload 5–10 high-quality photos (exterior, interior, team, products).",
    )
    check(
        "Reviews",
        review_count >= 10,
        f"{review_count} reviews",
        "Aim for 10+ recent reviews",
        25,
        "Request new reviews via SMS/email and reply to each review.",
    )
    check(
        "Relevant category",
        bool(p.get("types")),
        "Primary category set",
        "Pick the most accurate primary category",
        15,
        "Choose the best primary category; add 2–3 relevant secondary categories.",
    )

    return ScoringResult(checks, score, grade_for(score), recommendations + GENERIC_RECOMMENDATIONS)
