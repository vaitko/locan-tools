from __future__ import annotations

import math

EARTH_RADIUS_KM = 6371.0088


def offset(lat: float, lng: float, dx_km: float, dy_km: float) -> tuple[float, float]:
    """Move a coordinate east by dx_km and north by dy_km (flat-earth approximation, fine for < 50 km)."""
    dlat = dy_km / 111.32
    dlng = dx_km / (111.32 * max(math.cos(math.radians(lat)), 1e-6))
    return round(lat + dlat, 6), round(lng + dlng, 6)


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dl = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))
