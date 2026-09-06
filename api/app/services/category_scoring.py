"""Pure logic for the GBP Category Optimizer (port of Podsite.AI GbpCategoryOptimizerService).

No I/O here: the router resolves places via PlacesClient and feeds raw Places (New) payloads in.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Generic Places types that are not real GBP categories.
SKIP_TYPES = frozenset({"point_of_interest", "establishment", "store", "food", "place_of_worship"})

_TOKEN_SPLIT = re.compile(r"[^a-z0-9]+")
_MIN_TOKEN_LEN = 3  # tokens must be longer than this ("and", "the", "bar" are noise)

FREQUENCY_POINTS = 40
KEYWORD_POINTS = 20
SERVICES_POINTS = 20
DESCRIPTION_POINTS = 10
REVIEWS_POINTS = 10
NO_EVIDENCE_PENALTY = 25
ADD_THRESHOLD = 60
CONSIDER_THRESHOLD = 35


@dataclass
class ClientSnapshot:
    place_id: str | None
    business_name: str | None
    primary_category: str | None
    all_categories: list[str]
    review_count: int
    combined_review_text: str | None


@dataclass
class CompetitorCategory:
    category: str
    count: int
    out_of: int
    source_keywords: list[str] = field(default_factory=list)


@dataclass
class Recommendation:
    category: str
    action: str  # add | keep | consider | avoid
    score: int  # 0-100
    reasons: list[str]


@dataclass
class Opportunity:
    missing_category_count: int
    estimated_keyword_match_gain: int
    estimated_service_search_gain: int
    estimated_local_pack_gaps_closed: int
    headline: str


def humanize_type(raw: str) -> str:
    """'water_heater_installation_service' -> 'Water Heater Installation Service'; generic types -> ''."""
    if not raw or not raw.strip() or raw.lower() in SKIP_TYPES:
        return ""
    parts = [p for p in raw.split("_") if p]
    return " ".join(p[0].upper() + p[1:] for p in parts)


def _localized_text(value: dict | None) -> str | None:
    text = (value or {}).get("text")
    return text if isinstance(text, str) and text.strip() else None


def extract_categories(place: dict) -> list[str]:
    """Primary display name first, then humanized `types`; de-duplicated case-insensitively."""
    out: list[str] = []
    seen: set[str] = set()

    def add(category: str | None) -> None:
        if not category or not category.strip():
            return
        key = category.lower()
        if key in seen:
            return
        seen.add(key)
        out.append(category)

    add(_localized_text(place.get("primaryTypeDisplayName")))
    for raw in place.get("types") or []:
        if isinstance(raw, str):
            add(humanize_type(raw))
    return out


def build_client_snapshot(place: dict) -> ClientSnapshot:
    reviews = place.get("reviews")
    combined: str | None = None
    if reviews is not None:
        texts = (_localized_text(r.get("text")) for r in reviews if isinstance(r, dict))
        combined = " \n ".join(t for t in texts if t)
    return ClientSnapshot(
        place_id=place.get("id"),
        business_name=_localized_text(place.get("displayName")),
        primary_category=_localized_text(place.get("primaryTypeDisplayName")),
        all_categories=extract_categories(place),
        review_count=int(place.get("userRatingCount") or 0),
        combined_review_text=combined,
    )


def term_overlap(category: str, text: str) -> bool:
    """True when any meaningful (>3 chars) token of `category` occurs in `text`."""
    if not category or not category.strip() or not text or not text.strip():
        return False
    tokens = {t for t in _TOKEN_SPLIT.split(category.lower()) if len(t) > _MIN_TOKEN_LEN}
    if not tokens:
        return False
    haystack = text.lower()
    return any(t in haystack for t in tokens)


def aggregate_competitor_categories(competitors_by_keyword: list[tuple[str, list[dict]]]) -> list[CompetitorCategory]:
    """Frequency of each category across all inspected competitor profiles, most common first.

    Case-insensitive on category; the first-seen casing is kept. `out_of` is the total number of
    competitor profiles inspected across all keywords (a profile ranking for two keywords counts twice,
    matching the original service).
    """
    freq: dict[str, CompetitorCategory] = {}
    total = 0
    for keyword, competitors in competitors_by_keyword:
        for competitor in competitors:
            total += 1
            for category in extract_categories(competitor):
                key = category.lower()
                entry = freq.get(key)
                if entry is None:
                    entry = CompetitorCategory(category=category, count=0, out_of=0)
                    freq[key] = entry
                entry.count += 1
                if keyword.lower() not in (k.lower() for k in entry.source_keywords):
                    entry.source_keywords.append(keyword)
    for entry in freq.values():
        entry.out_of = total
    return sorted(freq.values(), key=lambda e: e.count, reverse=True)


def score_recommendations(
    snapshot: ClientSnapshot,
    competitor_categories: list[CompetitorCategory],
    keywords: list[str],
    services_text: str | None,
    business_description: str | None,
) -> list[Recommendation]:
    client_categories = {c.lower() for c in snapshot.all_categories}
    services = (services_text or "").lower()
    description = (business_description or "").lower()
    reviews = (snapshot.combined_review_text or "").lower()
    keyword_blob = " ".join(keywords).lower()

    recs: list[Recommendation] = []
    if snapshot.primary_category and snapshot.primary_category.strip():
        recs.append(Recommendation(snapshot.primary_category, "keep", 100, ["Current primary category"]))

    for comp in competitor_categories:
        key = comp.category.lower()
        if key in client_categories:
            continue  # already on the profile
        if any(r.category.lower() == key for r in recs):
            continue

        reasons: list[str] = []
        score = 0

        ratio = comp.count / comp.out_of if comp.out_of > 0 else 0.0
        score += round(ratio * FREQUENCY_POINTS)  # banker's rounding, same as .NET Math.Round
        reasons.append(f"{comp.count} of {comp.out_of} competitors use it")

        if term_overlap(comp.category, keyword_blob):
            score += KEYWORD_POINTS
            reasons.append("Matches your target keywords")

        services_hit = bool(services.strip()) and term_overlap(comp.category, services)
        if services_hit:
            score += SERVICES_POINTS
            reasons.append("Listed in services you provide")

        if description.strip() and term_overlap(comp.category, description):
            score += DESCRIPTION_POINTS
            reasons.append("Mentioned in business description")

        reviews_hit = bool(reviews.strip()) and term_overlap(comp.category, reviews)
        if reviews_hit:
            score += REVIEWS_POINTS
            reasons.append("Customers mention this in reviews")

        if not services_hit and not reviews_hit and comp.count <= 1:
            score -= NO_EVIDENCE_PENALTY
            reasons.append("No evidence client offers this — verify before adding")

        score = max(0, min(100, score))
        action = "add" if score >= ADD_THRESHOLD else "consider" if score >= CONSIDER_THRESHOLD else "avoid"
        recs.append(Recommendation(comp.category, action, score, reasons))

    recs.sort(key=lambda r: r.score, reverse=True)  # stable: keeps competitor-frequency order among ties
    return recs


def build_opportunity(recs: list[Recommendation]) -> Opportunity:
    add = sum(1 for r in recs if r.action == "add")
    consider = sum(1 for r in recs if r.action == "consider")
    missing = add + consider
    if missing == 0:
        headline = "Your categories already match the top competitors in this market."
    else:
        noun = "category" if missing == 1 else "categories"
        headline = f"You are missing {missing} {noun} used by competitors ranking above you."
    return Opportunity(
        missing_category_count=missing,
        estimated_keyword_match_gain=add * 4 + consider * 2,
        estimated_service_search_gain=add * 2,
        estimated_local_pack_gaps_closed=min(add, 5),
        headline=headline,
    )
