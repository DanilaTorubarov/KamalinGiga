"""
Smoke/unit tests for the Razvlekis FastAPI backend.

All external HTTP calls (Yandex Geocoder, Yandex Search, YandexGPT) are
intercepted by unittest.mock so the suite runs offline without any API keys.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


# ─── Mock helpers ─────────────────────────────────────────────────────────────

def _make_http_mock(json_data: dict, status: int = 200) -> AsyncMock:
    """Return an AsyncMock that can stand in for httpx.AsyncClient.

    Usage::
        with patch("httpx.AsyncClient", return_value=_make_http_mock(data)):
            ...
    """
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = json_data
    resp.text = ""

    cm = AsyncMock()
    cm.get = AsyncMock(return_value=resp)
    cm.post = AsyncMock(return_value=resp)
    # Make the async-context-manager protocol return the mock itself as `client`.
    cm.__aenter__.return_value = cm
    return cm


# Sample Yandex Geocoder response
GEOCODE_RESP = {
    "response": {
        "GeoObjectCollection": {
            "featureMember": [
                {
                    "GeoObject": {
                        "Point": {"pos": "37.619900 55.756950"},
                        "metaDataProperty": {
                            "GeocoderMetaData": {
                                "text": "Москва, ул. Большая Никитская, 14"
                            }
                        },
                    }
                }
            ]
        }
    }
}

# Sample Yandex Search API (Places) response — a single café
PLACES_RESP = {
    "features": [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [37.617, 55.756]},
            "properties": {
                "CompanyMetaData": {
                    "id": "test_001",
                    "name": "Кафе Тест",
                    "address": "Москва, ул. Тестовая, 1",
                    "Categories": [{"class": "cafe", "name": "Кофейня"}],
                }
            },
        }
    ]
}


# ─── 0. Health ────────────────────────────────────────────────────────────────

def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


# ─── 1. Save / unsave (pure in-memory, no external calls) ─────────────────────

def test_save_place_returns_ok():
    r = client.post("/api/places/place_unit_test/save")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_unsave_place_returns_ok():
    # unsave an id that may or may not exist — should always be idempotent
    r = client.delete("/api/places/place_unit_test/save")
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
    assert data["label"] == "Москва, ул. Большая Никитская, 14"


def test_geocode_empty_result_returns_422():
    empty = {"response": {"GeoObjectCollection": {"featureMember": []}}}
    with patch("httpx.AsyncClient", return_value=_make_http_mock(empty)):
        r = client.post("/api/geocode", json={"address": "xyzzy_nowhere_special"})
    assert r.status_code == 422


def test_geocode_upstream_error_returns_422():
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
    assert place["name"] == "Кафе Тест"
    assert place["category_id"] == "cafe"
    assert place["distance_m"] == 0  # same coords as user


def test_places_category_filter_excludes_non_matching():
    with patch("httpx.AsyncClient", return_value=_make_http_mock(PLACES_RESP)):
        # The only place is a café; filtering for restaurants should yield zero
        r = client.get(
            "/api/places",
            params={"lat": 55.756, "lng": 37.617, "category": "rest"},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 0
    assert body["places"] == []


def test_places_empty_features():
    with patch("httpx.AsyncClient", return_value=_make_http_mock({"features": []})):
        r = client.get("/api/places", params={"lat": 55.756, "lng": 37.617})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 0
    assert body["places"] == []


def test_places_requires_coords_or_address():
    """Calling /api/places with no location params must return 422."""
    r = client.get("/api/places")
    assert r.status_code == 422


def test_places_upstream_error_returns_502():
    with patch("httpx.AsyncClient", return_value=_make_http_mock({}, status=500)):
        r = client.get("/api/places", params={"lat": 55.756, "lng": 37.617})
    assert r.status_code == 502


# ─── 4. Chat ───────────────────────────────────────────────────────────────────

def test_chat_without_api_keys_is_graceful():
    """Without YandexGPT credentials the endpoint must reply 200 with a notice."""
    with patch("main.YANDEX_GPT_KEY", None), patch("main.YANDEX_FOLDER_ID", None):
        r = client.post("/api/chat", json={"message": "Привет"})
    assert r.status_code == 200
    data = r.json()
    assert "reply" in data
    assert len(data["reply"]) > 10


def test_chat_accepts_history_and_context():
    """Schema validation: optional history + context fields must be accepted."""
    with patch("main.YANDEX_GPT_KEY", None), patch("main.YANDEX_FOLDER_ID", None):
        r = client.post(
            "/api/chat",
            json={
                "message": "Что посоветуешь?",
                "history": [{"role": "user", "content": "Привет"}],
                "context": {"address": "Москва", "category": "cafe", "filters": []},
            },
        )
    assert r.status_code == 200
    assert "reply" in r.json()
