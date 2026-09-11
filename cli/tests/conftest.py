from __future__ import annotations

import json

import httpx
import pytest

BASE_URL = "https://api.test/api"

SUGGESTIONS = {
    "suggestions": [
        {"placeId": "PLACE1", "name": "Smile Dental", "address": "Laisves al. 1, Kaunas"},
        {"placeId": "PLACE2", "name": "Bright Teeth", "address": "Vilniaus g. 9, Kaunas"},
    ]
}

DETAILS = {
    "placeId": "PLACE1",
    "name": "Smile Dental",
    "address": "Laisves al. 1, Kaunas, Lithuania",
    "addressComponents": {
        "street": "Laisves al. 1",
        "locality": "Kaunas",
        "region": "Kauno apskritis",
        "postalCode": "44001",
        "country": "LT",
    },
    "lat": 54.8985,
    "lng": 23.9036,
    "phone": "(8 600) 00000",
    "internationalPhone": "+370 600 00000",
    "website": "https://smile.example",
    "mapsUrl": "https://maps.google.com/?cid=1",
    "primaryType": "dentist",
    "primaryTypeLabel": "Dentist",
    "rating": 4.8,
    "reviewCount": 120,
    "openingHours": [
        {"day": 1, "open": "09:00", "close": "18:00"},
        {"day": 2, "open": "09:00", "close": "18:00"},
        {"day": 3, "open": "10:00", "close": "16:00"},
        {"day": 6, "open": "00:00", "close": None},
    ],
    "weekdayDescriptions": ["Monday: 9 AM–6 PM"],
}

GBP_AUDIT = {
    "score": 72.0,
    "grade": "Good",
    "summary": "We analyzed your public Google Business Profile for key visibility factors.",
    "checks": [{"name": "Website", "pass": True, "detail": "Linked"}],
    "recommendations": ["Add more photos"],
    "place": {"name": "Smile Dental", "address": "Laisves al. 1, Kaunas", "rating": 4.8, "reviews": 120},
    "ai": {"optimizedDescription": "Family dentistry in Kaunas.", "longTailKeywords": ["dentist near me kaunas"]},
}

CATEGORIES = {
    "client": {
        "placeId": "PLACE1",
        "businessName": "Smile Dental",
        "primaryCategory": "Dentist",
        "allCategories": ["Dentist"],
        "reviewCount": 120,
    },
    "competitorCategories": [{"category": "Dental Clinic", "count": 4, "outOf": 5, "sourceKeywords": ["dentist kaunas"]}],
    "recommendations": [{"category": "Dental Clinic", "action": "add", "score": 88, "reasons": ["4 of 5 competitors use it"]}],
    "opportunity": {
        "missingCategoryCount": 1,
        "estimatedKeywordMatchGain": 12,
        "estimatedServiceSearchGain": 8,
        "estimatedLocalPackGapsClosed": 2,
        "headline": "One missing category",
    },
}

RANK_GRID = {
    "business": {"placeId": "PLACE1", "name": "Smile Dental", "address": "Laisves al. 1", "lat": 54.8985, "lng": 23.9036},
    "keyword": "dentist",
    "grid": {
        "size": 3,
        "spacingKm": 1.0,
        "points": [{"row": 0, "col": 0, "lat": 54.9, "lng": 23.9, "rank": 3, "error": False}],
    },
    "summary": {
        "averageRank": 3.0,
        "bestRank": 1,
        "worstRank": 9,
        "visibleShare": 0.8,
        "top3Share": 0.4,
        "pointsChecked": 9,
    },
    "competitors": [{"placeId": "PLACE2", "name": "Bright Teeth", "appearances": 7, "averageRank": 2.1}],
}

AI_VISIBILITY = {
    "score": 41,
    "scoreLabel": "Emerging",
    "totalMentions": 5,
    "totalQueries": 12,
    "failedQueries": 0,
    "visibilityRate": 41,
    "category": "dentist",
    "engines": {"chatgpt": {"mentions": 2, "queries": 3, "confidence": "medium", "avgPosition": 2}},
    "queries": [{"text": "best dentist in Kaunas", "mentioned": True, "engine": "chatgpt", "failed": False}],
    "competitors": [{"name": "Bright Teeth", "score": 70, "reasons": ["Named first"]}],
    "missing": ["Emergency dentist"],
    "actions": [{"title": "Publish an FAQ", "desc": "Answer the questions buyers ask."}],
}

REVIEW_REPLY = {
    "responses": [
        {"tone": "Professional", "text": "Thank you for the kind words about our team."},
        {"tone": "Professional · short", "text": "Thanks for visiting us."},
    ],
    "tips": ["Reply within 24 hours"],
}

QUOTA_ERROR = {
    "error": "You've reached today's free limit for this tool. Please try again tomorrow.",
    "code": "quota_exceeded",
}

UPSTREAM_ERROR = {"error": "Google Places returned HTTP 500.", "code": "places_upstream"}

DETAILS_VALIDATION_ERROR = {"error": "Invalid place id", "code": "validation_error"}


class Recorder:
    def __init__(self, payload: object, status: int = 200, raise_connect_error: bool = False) -> None:
        self.payload = payload
        self.status = status
        self.raise_connect_error = raise_connect_error
        self.requests: list[httpx.Request] = []

    @property
    def request(self) -> httpx.Request:
        assert self.requests, "no request was made"
        return self.requests[-1]

    @property
    def body(self) -> dict:
        return json.loads(self.request.content)

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.raise_connect_error:
            raise httpx.ConnectError("connection refused", request=request)
        return httpx.Response(self.status, json=self.payload, request=request)

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)


@pytest.fixture
def recorder():
    def make(payload: object = None, status: int = 200, raise_connect_error: bool = False) -> Recorder:
        return Recorder(payload, status, raise_connect_error)

    return make


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    monkeypatch.delenv("LOCAN_API_URL", raising=False)
