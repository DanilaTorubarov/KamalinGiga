"""
Smoke/unit tests for the Razvlekis FastAPI backend (Google APIs).

All external HTTP calls (Google Geocoding, Google Places, Gemini) are
intercepted by unittest.mock so the suite runs offline without any API keys.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


# ─── Mock helpers ─────────────────────────────────────────────────────────────

def _make_http_mock(json_data: dict, status: int = 200) -> AsyncMock:
    """Return an AsyncMock that stands in for httpx.AsyncClient.

    Usage::
        with patch("httpx.AsyncClient", return_value=_make_http_mock(data)):
            ...
    """
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = json_data
    resp.text = str(json_data)

    cm = AsyncMock()
    cm.get  = AsyncMock(return_value=resp)
    cm.post = AsyncMock(return_value=resp)
    # async-context-manager protocol: __aenter__ returns the mock itself
    cm.__aenter__.return_value = cm
    return cm


# ─── Sample Google API responses ──────────────────────────────────────────────

# Google Geocoding API — one result
GEOCODE_RESP = {
    "status": "OK",
    "results": [
        {
            "formatted_address": "Большая Никитская ул., 14, Москва, Россия, 125009",
            "geometry": {
                "location": {"lat": 55.756950, "lng": 37.619900},
            },
            "place_id": "ChIJtest_geocode",
        }
    ],
}

# Google Places Nearby Search — one café result
PLACES_RESP = {
    "status": "OK",
    "results": [
        {
            "place_id":  "ChIJtest001",
            "name":      "Кафе Тест",
            "vicinity":  "ул. Тестовая, 1, Москва",
            "geometry":  {"location": {"lat": 55.756, "lng": 37.617}},
            "types":     ["cafe", "food", "establishment"],
            "rating":    4.5,
            "price_level": 2,
            "opening_hours": {"open_now": True},
        }
    ],
}

# Gemini API — minimal successful response
GEMINI_RESP = {
    "candidates": [
        {
            "content": {
                "parts": [{"text": "Рекомендую попробовать Кафе Тест!"}],
                "role": "model",
            }
        }
    ]
}


# ─── 0. Health ────────────────────────────────────────────────────────────────

def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


# ─── 1. Save / Unsave (pure in-memory, no external calls) ─────────────────────

def test_save_place_returns_ok():
    r = client.post("/api/places/ChIJunit_test/save")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_unsave_place_is_idempotent():
    r = client.delete("/api/places/ChIJunit_test/save")
    assert r.status_code == 200
    assert r.json()["ok"] is True


# ─── 2. Geocode ────────────────────────────────────────────────────────────────

def test_geocode_returns_lat_lng_and_label():
    with patch("httpx.AsyncClient", return_value=_make_http_mock(GEOCODE_RESP)):
        r = client.post("/api/geocode", json={"address": "Большая Никитская, 14"})
    assert r.status_code == 200
    data = r.json()
    assert abs(data["lat"] - 55.75695) < 0.001
    assert abs(data["lng"] - 37.61990) < 0.001
    assert "Никитская" in data["label"]


def test_geocode_zero_results_returns_422():
    empty = {"status": "ZERO_RESULTS", "results": []}
    with patch("httpx.AsyncClient", return_value=_make_http_mock(empty)):
        r = client.post("/api/geocode", json={"address": "xyzzy_nowhere_special"})
    assert r.status_code == 422


def test_geocode_upstream_http_error_returns_422():
    with patch("httpx.AsyncClient", return_value=_make_http_mock({}, status=403)):
        r = client.post("/api/geocode", json={"address": "Москва"})
    assert r.status_code == 422


# ─── 3. Places ─────────────────────────────────────────────────────────────────

def test_places_with_lat_lng():
    with patch("httpx.AsyncClient", return_value=_make_http_mock(PLACES_RESP)):
        r = client.get("/api/places", params={"lat": 55.756, "lng": 37.617})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert "categories" in body

    place = body["places"][0]
    assert place["name"]        == "Кафе Тест"
    assert place["category_id"] == "cafe"
    assert place["rating"]      == 4.5
    assert place["price"]       == "₽₽"
    assert place["is_open"]     is True
    assert place["distance_m"]  == 0      # same coords as user


def test_places_category_filter_excludes_non_matching():
    # The mock returns a café; filtering for restaurants must yield 0 results.
    with patch("httpx.AsyncClient", return_value=_make_http_mock(PLACES_RESP)):
        r = client.get(
            "/api/places",
            params={"lat": 55.756, "lng": 37.617, "category": "rest"},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["total"]  == 0
    assert body["places"] == []


def test_places_zero_results_is_ok():
    zero = {"status": "ZERO_RESULTS", "results": []}
    with patch("httpx.AsyncClient", return_value=_make_http_mock(zero)):
        r = client.get("/api/places", params={"lat": 55.756, "lng": 37.617})
    assert r.status_code == 200
    assert r.json()["total"]  == 0
    assert r.json()["places"] == []


def test_places_requires_coords_or_address():
    r = client.get("/api/places")
    assert r.status_code == 422


def test_places_upstream_http_error_returns_502():
    with patch("httpx.AsyncClient", return_value=_make_http_mock({}, status=500)):
        r = client.get("/api/places", params={"lat": 55.756, "lng": 37.617})
    assert r.status_code == 502


def test_places_api_status_error_returns_502():
    # Google returns HTTP 200 but with an error status in the body
    denied = {"status": "REQUEST_DENIED", "results": []}
    with patch("httpx.AsyncClient", return_value=_make_http_mock(denied)):
        r = client.get("/api/places", params={"lat": 55.756, "lng": 37.617})
    assert r.status_code == 502


# ─── 4. Chat ───────────────────────────────────────────────────────────────────

def test_chat_without_api_key_returns_graceful_message():
    """Without GOOGLE_AI_KEY the endpoint must reply 200 with a notice."""
    with patch("main.GOOGLE_AI_KEY", None):
        r = client.post("/api/chat", json={"message": "Привет"})
    assert r.status_code == 200
    data = r.json()
    assert "reply" in data
    assert len(data["reply"]) > 10


def test_chat_with_gemini_response():
    """With a key present, the Gemini reply is passed through."""
    with patch("main.GOOGLE_AI_KEY", "fake-key"), \
         patch("httpx.AsyncClient", return_value=_make_http_mock(GEMINI_RESP)):
        r = client.post("/api/chat", json={"message": "Что посоветуешь?"})
    assert r.status_code == 200
    assert "Кафе Тест" in r.json()["reply"]


def test_chat_accepts_history_and_context():
    """Full schema — optional history + context fields — must be accepted."""
    with patch("main.GOOGLE_AI_KEY", None):
        r = client.post(
            "/api/chat",
            json={
                "message": "Продолжи",
                "history": [{"role": "user", "content": "Привет"}],
                "context": {
                    "address":  "Москва",
                    "category": "cafe",
                    "filters":  [],
                },
            },
        )
    assert r.status_code == 200
    assert "reply" in r.json()
