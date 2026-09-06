"""Pure grid geometry and ranking maths for the Local Rank Checker (no I/O)."""

from __future__ import annotations

from collections import defaultdict
from statistics import mean

from .geo import offset


def build_grid(lat: float, lng: float, size: int, spacing_km: float) -> list[dict]:
    """Row 0 is the northern-most row, col 0 the western-most; the centre cell is the business itself."""
    centre = size // 2
    points: list[dict] = []
    for row in range(size):
        for col in range(size):
            if row == centre and col == centre:
                p_lat, p_lng = lat, lng
            else:
                p_lat, p_lng = offset(lat, lng, (col - centre) * spacing_km, (centre - row) * spacing_km)
            points.append({"row": row, "col": col, "lat": p_lat, "lng": p_lng})
    return points


def rank_of(place_id: str, places: list[dict]) -> int | None:
    """1-based position of `place_id` in a Places search result list, or None when it is not listed."""
    for index, place in enumerate(places):
        if place.get("id") == place_id:
            return index + 1
    return None


def summarize(ranks: list[int | None]) -> dict:
    ranked = [r for r in ranks if r is not None]
    total = len(ranks)
    return {
        "averageRank": round(mean(ranked), 1) if ranked else None,
        "bestRank": min(ranked) if ranked else None,
        "worstRank": max(ranked) if ranked else None,
        "visibleShare": round(len(ranked) / total, 2) if total else 0.0,
        "top3Share": round(sum(1 for r in ranked if r <= 3) / total, 2) if total else 0.0,
        "pointsChecked": total,
    }


def aggregate_competitors(per_point_ids: list[list[str]], exclude_id: str) -> list[dict]:
    """Every other place seen across the grid, most frequent (then best average position) first."""
    positions: dict[str, list[int]] = defaultdict(list)
    for ids in per_point_ids:
        for position, pid in enumerate(ids, start=1):
            if pid and pid != exclude_id:
                positions[pid].append(position)
    out = [
        {"placeId": pid, "appearances": len(seen), "averageRank": round(mean(seen), 1)}
        for pid, seen in positions.items()
    ]
    out.sort(key=lambda c: (-c["appearances"], c["averageRank"]))
    return out
