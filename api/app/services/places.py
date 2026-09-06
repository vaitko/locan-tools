"""Thin async client for Google Places API (New)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from ..errors import ApiError

BASE_URL = "https://places.googleapis.com"

DETAILS_FIELDS_FULL = (
    "id,displayName,formattedAddress,addressComponents,location,nationalPhoneNumber,"
    "internationalPhoneNumber,websiteUri,regularOpeningHours,primaryType,"
    "primaryTypeDisplayName,rating,userRatingCount,googleMapsUri"
)


@dataclass(frozen=True)
class Suggestion:
    place_id: str
    name: str
    address: str

    def to_dict(self) -> dict[str, str]:
        return {"placeId": self.place_id, "name": self.name, "address": self.address}


class PlacesClient:
    def __init__(self, api_key: str, http: httpx.AsyncClient):
        self._key = api_key
        self._http = http

    def _headers(self, field_mask: str | None = None) -> dict[str, str]:
        h = {"X-Goog-Api-Key": self._key, "Content-Type": "application/json"}
        if field_mask:
            h["X-Goog-FieldMask"] = field_mask
        return h

    async def _request(self, method: str, path: str, *, field_mask: str | None, json: Any = None, params: dict | None = None) -> dict:
        if not self._key:
            raise ApiError(503, "places_not_configured", "Business lookup is temporarily unavailable. Please try again later.")
        try:
            resp = await self._http.request(
                method, f"{BASE_URL}{path}", headers=self._headers(field_mask), json=json, params=params
            )
        except httpx.HTTPError as exc:
            raise ApiError(502, "places_upstream", f"Google Places request failed: {exc.__class__.__name__}") from exc
        if resp.status_code == 404:
            raise ApiError(404, "place_not_found", "We couldn't find that business on Google Maps.")
        if resp.status_code >= 400:
            raise ApiError(502, "places_upstream", f"Google Places returned HTTP {resp.status_code}.")
        return resp.json() if resp.content else {}

    async def autocomplete(
        self,
        q: str,
        session_token: str | None = None,
        language: str = "en",
        region: str | None = None,
    ) -> list[Suggestion]:
        body: dict[str, Any] = {"input": q, "includeQueryPredictions": False, "languageCode": language}
        if session_token:
            body["sessionToken"] = session_token
        if region:
            body["regionCode"] = region
        data = await self._request("POST", "/v1/places:autocomplete", field_mask=None, json=body)
        out: list[Suggestion] = []
        for item in data.get("suggestions", []):
            pred = item.get("placePrediction")
            if not pred or not pred.get("placeId"):
                continue
            fmt = pred.get("structuredFormat") or {}
            name = (fmt.get("mainText") or {}).get("text") or (pred.get("text") or {}).get("text") or ""
            address = (fmt.get("secondaryText") or {}).get("text") or ""
            out.append(Suggestion(pred["placeId"], name, address))
        return out

    async def details(self, place_id: str, fields: str, session_token: str | None = None) -> dict:
        resource = place_id if place_id.startswith("places/") else f"places/{place_id}"
        params = {"sessionToken": session_token} if session_token else None
        return await self._request("GET", f"/v1/{resource}", field_mask=fields, params=params)

    async def search_text(
        self,
        query: str,
        fields: str = "places.id",
        max_results: int = 20,
        location_bias: tuple[float, float, float] | None = None,
        language: str | None = None,
        region: str | None = None,
        page_token: str | None = None,
    ) -> dict:
        body: dict[str, Any] = {"textQuery": query, "pageSize": max(1, min(max_results, 20))}
        if location_bias:
            lat, lng, radius_m = location_bias
            body["locationBias"] = {"circle": {"center": {"latitude": lat, "longitude": lng}, "radius": float(radius_m)}}
        if language:
            body["languageCode"] = language
        if region:
            body["regionCode"] = region
        if page_token:
            body["pageToken"] = page_token
        return await self._request("POST", "/v1/places:searchText", field_mask=fields, json=body)

    async def search_text_first(self, query: str, fields: str = "places.id") -> dict | None:
        data = await self.search_text(query, fields=fields, max_results=1)
        places_ = data.get("places") or []
        return places_[0] if places_ else None


def normalize_details(p: dict) -> dict:
    """Map a Places (New) details payload to the public shape used by the site."""
    comps = {}
    for c in p.get("addressComponents", []) or []:
        for t in c.get("types", []):
            comps.setdefault(t, c.get("longText") or c.get("shortText") or "")
    street = " ".join(x for x in [comps.get("street_number"), comps.get("route")] if x)
    hours = []
    for period in (p.get("regularOpeningHours") or {}).get("periods", []) or []:
        o, c = period.get("open") or {}, period.get("close") or {}
        if "day" in o:
            hours.append(
                {
                    "day": o["day"],
                    "open": f"{o.get('hour', 0):02d}:{o.get('minute', 0):02d}",
                    "close": f"{c.get('hour', 0):02d}:{c.get('minute', 0):02d}" if c else None,
                }
            )
    loc = p.get("location") or {}
    return {
        "placeId": p.get("id"),
        "name": (p.get("displayName") or {}).get("text"),
        "address": p.get("formattedAddress"),
        "addressComponents": {
            "street": street or None,
            "locality": comps.get("locality") or comps.get("postal_town") or comps.get("sublocality") or None,
            "region": comps.get("administrative_area_level_1") or None,
            "postalCode": comps.get("postal_code") or None,
            "country": comps.get("country") or None,
        },
        "lat": loc.get("latitude"),
        "lng": loc.get("longitude"),
        "phone": p.get("nationalPhoneNumber"),
        "internationalPhone": p.get("internationalPhoneNumber"),
        "website": p.get("websiteUri"),
        "mapsUrl": p.get("googleMapsUri"),
        "primaryType": p.get("primaryType"),
        "primaryTypeLabel": (p.get("primaryTypeDisplayName") or {}).get("text"),
        "rating": p.get("rating"),
        "reviewCount": p.get("userRatingCount"),
        "openingHours": hours,
        "weekdayDescriptions": (p.get("regularOpeningHours") or {}).get("weekdayDescriptions", []) or [],
    }
