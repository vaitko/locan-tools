from __future__ import annotations

import os
from typing import Any
from urllib.parse import quote

import httpx

from . import __version__

DEFAULT_BASE_URL = "https://api.locan.ai/api"
REVIEW_LINK = "https://search.google.com/local/writereview?placeid={place_id}"

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
GOOGLE_DAYS = {0: "Sunday", 1: "Monday", 2: "Tuesday", 3: "Wednesday", 4: "Thursday", 5: "Friday", 6: "Saturday"}

SCHEMA_TYPES = {
    "plumber": "Plumber",
    "electrician": "Electrician",
    "dentist": "Dentist",
    "doctor": "Physician",
    "restaurant": "Restaurant",
    "cafe": "CafeOrCoffeeShop",
    "bakery": "Bakery",
    "bar": "BarOrPub",
    "hair_salon": "HairSalon",
    "hair_care": "HairSalon",
    "beauty_salon": "BeautySalon",
    "nail_salon": "NailSalon",
    "spa": "DaySpa",
    "lawyer": "Attorney",
    "accounting": "AccountingService",
    "insurance_agency": "InsuranceAgency",
    "real_estate_agency": "RealEstateAgent",
    "travel_agency": "TravelAgency",
    "hotel": "Hotel",
    "lodging": "Hotel",
    "pet_store": "PetStore",
    "veterinary_care": "VeterinaryCare",
    "gym": "ExerciseGym",
    "fitness_center": "ExerciseGym",
    "car_repair": "AutoRepair",
    "car_dealer": "AutoDealer",
    "car_wash": "AutoWash",
    "locksmith": "Locksmith",
    "moving_company": "MovingCompany",
    "roofing_contractor": "RoofingContractor",
    "general_contractor": "GeneralContractor",
    "florist": "Florist",
    "furniture_store": "FurnitureStore",
    "hardware_store": "HardwareStore",
    "jewelry_store": "JewelryStore",
    "clothing_store": "ClothingStore",
    "store": "Store",
    "school": "School",
    "child_care": "ChildCare",
    "physiotherapist": "Physiotherapy",
    "pharmacy": "Pharmacy",
}


class LocanApiError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def _clean(values: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value is not None}


def _error_from(response: httpx.Response) -> LocanApiError:
    try:
        data = response.json()
    except ValueError:
        data = None
    message = f"HTTP {response.status_code} from the Locan API"
    code = f"http_{response.status_code}"
    if isinstance(data, dict):
        if isinstance(data.get("error"), str) and data["error"]:
            message = data["error"]
        elif data.get("detail") is not None:
            message = _detail_message(data["detail"])
        if isinstance(data.get("code"), str) and data["code"]:
            code = data["code"]
    return LocanApiError(response.status_code, code, message)


def _detail_message(detail: Any) -> str:
    if isinstance(detail, str):
        return detail
    if isinstance(detail, list):
        parts = []
        for item in detail:
            if isinstance(item, dict):
                location = ".".join(str(p) for p in item.get("loc", []) if p != "body")
                text = str(item.get("msg", "invalid request"))
                parts.append(f"{location}: {text}" if location else text)
            else:
                parts.append(str(item))
        if parts:
            return "; ".join(parts)
    return str(detail)


class LocanClient:
    def __init__(
        self,
        base_url: str | None = None,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 120.0,
    ) -> None:
        self.base_url = (base_url or os.environ.get("LOCAN_API_URL") or DEFAULT_BASE_URL).rstrip("/")
        self._http = httpx.Client(
            base_url=self.base_url,
            transport=transport,
            timeout=timeout,
            headers={"User-Agent": f"locan-tools/{__version__}", "Accept": "application/json"},
        )

    def __enter__(self) -> LocanClient:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return self._result(self._http.get(path, params=_clean(params or {})))

    def _post(self, path: str, body: dict[str, Any]) -> Any:
        return self._result(self._http.post(path, json=_clean(body)))

    def _result(self, response: httpx.Response) -> Any:
        if not response.is_success:
            raise _error_from(response)
        try:
            data = response.json()
        except ValueError:
            raise LocanApiError(response.status_code, "bad_response", "API returned a non-JSON response")
        if isinstance(data, dict) and isinstance(data.get("error"), str) and data["error"]:
            if isinstance(data.get("code"), str) and data["code"]:
                raise LocanApiError(response.status_code, data["code"], data["error"])
            raise LocanApiError(response.status_code, "error", data["error"])
        return data

    def find_business(
        self,
        query: str,
        session: str | None = None,
        lang: str | None = None,
        region: str | None = None,
    ) -> list[dict[str, Any]]:
        data = self._get("/places/autocomplete", {"q": query, "session": session, "lang": lang, "region": region})
        return list(data.get("suggestions", []))

    def place_details(self, place_id: str, session: str | None = None) -> dict[str, Any]:
        return self._get(f"/places/details/{quote(place_id, safe='')}", {"session": session})

    def gbp_audit(
        self,
        place_id: str | None = None,
        business_name: str | None = None,
        city: str | None = None,
        gbp_url: str | None = None,
    ) -> dict[str, Any]:
        return self._post(
            "/tools/gbp-optimizer",
            {"placeId": place_id, "businessName": business_name, "city": city, "gbpUrl": gbp_url},
        )

    def gbp_categories(
        self,
        keywords: list[str],
        place_id: str | None = None,
        business_name: str | None = None,
        city: str | None = None,
        region_code: str | None = None,
        language_code: str | None = None,
        services_text: str | None = None,
    ) -> dict[str, Any]:
        return self._post(
            "/tools/category-optimizer",
            {
                "placeId": place_id,
                "businessName": business_name,
                "city": city,
                "keywords": list(keywords),
                "regionCode": region_code,
                "languageCode": language_code,
                "servicesText": services_text,
            },
        )

    def rank_grid(
        self,
        place_id: str,
        keyword: str,
        grid_size: int | None = None,
        spacing_km: float | None = None,
        language_code: str | None = None,
        region_code: str | None = None,
    ) -> dict[str, Any]:
        return self._post(
            "/tools/rank-checker",
            {
                "placeId": place_id,
                "keyword": keyword,
                "gridSize": grid_size,
                "spacingKm": spacing_km,
                "languageCode": language_code,
                "regionCode": region_code,
            },
        )

    def ai_visibility(self, business_name: str, city: str, category: str | None = None) -> dict[str, Any]:
        return self._post(
            "/tools/ai-visibility",
            {"businessName": business_name, "city": city, "category": category},
        )

    def review_reply(
        self,
        business_name: str,
        review_text: str,
        rating: int,
        reviewer_name: str | None = None,
        tone: str | None = None,
        language: str | None = None,
        sign_off: str | None = None,
        business_type: str | None = None,
    ) -> dict[str, Any]:
        return self._post(
            "/tools/review-response",
            {
                "businessName": business_name,
                "reviewText": review_text,
                "rating": rating,
                "reviewerName": reviewer_name,
                "tone": tone,
                "language": language,
                "signOff": sign_off,
                "businessType": business_type,
            },
        )

    def review_link(self, place_id: str) -> dict[str, str]:
        return {"placeId": place_id, "reviewLink": REVIEW_LINK.format(place_id=quote(place_id, safe=""))}

    def schema_jsonld(self, details: dict[str, Any]) -> dict[str, Any]:
        return build_jsonld(details)


def build_jsonld(details: dict[str, Any]) -> dict[str, Any]:
    components = details.get("addressComponents") or {}
    website = details.get("website")
    data: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": SCHEMA_TYPES.get(details.get("primaryType") or "", "LocalBusiness"),
    }
    if website:
        data["@id"] = f"{website}#localbusiness"
    _put(data, "name", details.get("name"))
    _put(data, "url", website)
    _put(data, "telephone", details.get("internationalPhone") or details.get("phone"))

    address = {"@type": "PostalAddress"}
    _put(address, "streetAddress", components.get("street"))
    _put(address, "addressLocality", components.get("locality"))
    _put(address, "addressRegion", components.get("region"))
    _put(address, "postalCode", components.get("postalCode"))
    _put(address, "addressCountry", _country_code(components.get("country")))
    if len(address) > 1:
        data["address"] = address

    lat, lng = details.get("lat"), details.get("lng")
    if isinstance(lat, (int, float)) and isinstance(lng, (int, float)):
        data["geo"] = {"@type": "GeoCoordinates", "latitude": lat, "longitude": lng}

    hours = _opening_hours(details.get("openingHours") or [])
    if hours:
        data["openingHoursSpecification"] = hours
    _put(data, "hasMap", details.get("mapsUrl"))
    return data


def _put(target: dict[str, Any], key: str, value: Any) -> None:
    if value:
        target[key] = value


def _country_code(country: Any) -> str | None:
    if not isinstance(country, str) or not country:
        return None
    return country.upper() if len(country) == 2 and country.isalpha() else country


def _opening_hours(periods: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_day: dict[str, tuple[str, str]] = {}
    for period in periods:
        day = GOOGLE_DAYS.get(period.get("day"))
        opens = period.get("open")
        if not day or not opens:
            continue
        closes = period.get("close")
        if not closes:
            opens, closes = "00:00", "23:59"
        current = by_day.get(day)
        if current:
            opens, closes = min(opens, current[0]), max(closes, current[1])
        by_day[day] = (opens, closes)

    groups: list[dict[str, Any]] = []
    previous_index = -2
    for index, day in enumerate(DAYS):
        hours = by_day.get(day)
        if not hours:
            continue
        opens, closes = hours
        last = groups[-1] if groups else None
        if last and index == previous_index + 1 and (last["opens"], last["closes"]) == (opens, closes):
            last["dayOfWeek"].append(day)
        else:
            groups.append(
                {"@type": "OpeningHoursSpecification", "dayOfWeek": [day], "opens": opens, "closes": closes}
            )
        previous_index = index
    return groups


def make_client() -> LocanClient:
    return LocanClient()
