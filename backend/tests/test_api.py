"""
Integration tests for Развлекись API.
External HTTP calls (Google, GigaChat) are mocked so the suite
runs offline and in CI without real API keys.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient, ASGITransport, Response

from fastapi import HTTPException

from main import app


transport = ASGITransport(app=app)

GOOGLE_PLACES_RESPONSE = {
    "status": "OK",
    "results": [
        {
            "place_id": "ChIJcafe",
            "name": "Кафе Пушкин",
            "vicinity": "Тверской бульвар, 26а",
            "geometry": {"location": {"lat": 55.752, "lng": 37.619}},
            "rating": 4.5,
            "price_level": 2,
            "opening_hours": {"open_now": True},
            "types": ["cafe", "food"],
            "photos": [{"photo_reference": "photo_cafe"}],
        },
        {
            "place_id": "ChIJrest",
            "name": "Ресторан Белуга",
            "vicinity": "Никитская, 14",
            "geometry": {"location": {"lat": 55.754, "lng": 37.621}},
            "rating": 4.8,
            "price_level": 3,
            "opening_hours": {"open_now": False},
            "types": ["restaurant", "food"],
            "photos": [{"photo_reference": "photo_rest"}],
        },
    ],
}

GOOGLE_GEOCODE_RESPONSE = {
    "status": "OK",
    "results": [{
        "geometry": {"location": {"lat": 55.7596, "lng": 37.6184}},
        "formatted_address": "Большая Никитская улица, 14, Москва",
    }],
}

GIGACHAT_RESPONSE = {
    "choices": [{
        "message": {"role": "assistant", "content": "Попробуйте ресторан Белуга — отличная кухня!"}
    }],
}


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_nearby():
    with patch("clients.places.google_nearby_search", new_callable=AsyncMock) as m:
        m.return_value = GOOGLE_PLACES_RESPONSE["results"]
        yield m


@pytest.fixture
def mock_geocode():
    with patch("services.geocode_service.geocode_address", new_callable=AsyncMock) as m:
        m.return_value = (55.7596, 37.6184)
        yield m


@pytest.fixture
def mock_gigachat():
    with patch("clients.gigachat_client.gigachat_request", new_callable=AsyncMock) as m:
        m.return_value = GIGACHAT_RESPONSE
        yield m


# ===========================================================================
# 1. GET /api/places
# ===========================================================================

@pytest.mark.asyncio
async def test_places_by_coords(mock_nearby):
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/api/places", params={"lat": 55.75, "lng": 37.62})
    assert r.status_code == 200
    data = r.json()
    assert "places" in data
    assert "total" in data
    assert data["total"] == 2
    assert len(data["places"]) == 2


@pytest.mark.asyncio
async def test_places_by_address(mock_geocode, mock_nearby):
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/api/places", params={"address": "Москва, Тверская 10"})
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 2


@pytest.mark.asyncio
async def test_places_no_params():
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/api/places")
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_places_invalid_coords():
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/api/places", params={"lat": 91, "lng": 200})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_places_category_filter(mock_nearby):
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/api/places", params={"lat": 55.75, "lng": 37.62, "category": "cafe"})
    assert r.status_code == 200
    assert r.json()["total"] == 2


@pytest.mark.asyncio
async def test_places_limit(mock_nearby):
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/api/places", params={"lat": 55.75, "lng": 37.62, "limit": 1})
    assert r.status_code == 200
    assert len(r.json()["places"]) == 1


@pytest.mark.asyncio
async def test_places_sorted_by_distance(mock_nearby):
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/api/places", params={"lat": 55.75, "lng": 37.62})
    places = r.json()["places"]
    distances = [p["distance_m"] for p in places]
    assert distances == sorted(distances)


@pytest.mark.asyncio
async def test_places_google_error():
    with patch("clients.places.google_nearby_search", new_callable=AsyncMock) as m:
        m.side_effect = HTTPException(502, "Google Places error: REQUEST_DENIED")
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.get("/api/places", params={"lat": 55.75, "lng": 37.62})
    assert r.status_code == 502


@pytest.mark.asyncio
async def test_places_google_zero_results():
    with patch("clients.places.google_nearby_search", new_callable=AsyncMock) as m:
        m.return_value = []
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/api/places", params={"lat": 55.75, "lng": 37.62})
    assert r.status_code == 200
    assert r.json()["total"] == 0


# ===========================================================================
# 2. POST /api/geocode
# ===========================================================================

@pytest.mark.asyncio
async def test_geocode_ok(mock_geocode):
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/geocode", json={"address": "Москва, Красная площадь"})
    assert r.status_code == 200
    data = r.json()
    assert "lat" in data
    assert "lng" in data


@pytest.mark.asyncio
async def test_geocode_not_found():
    with patch("services.geocode_service.geocode_address", new_callable=AsyncMock) as m:
        m.side_effect = HTTPException(422, "Address not found")
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/geocode", json={"address": "nonexistent_xyz"})
    assert r.status_code == 422


# ===========================================================================
# 3. POST /api/chat
# ===========================================================================

@pytest.mark.asyncio
async def test_chat_ok(mock_gigachat):
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/chat", json={"message": "Где поужинать?"})
    assert r.status_code == 200
    assert "reply" in r.json()
    assert len(r.json()["reply"]) > 0


@pytest.mark.asyncio
async def test_chat_with_context(mock_gigachat):
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/chat", json={
            "message": "Что рядом?",
            "context": {
                "address": "Тверская 10",
                "places": [
                    {"name": "Кафе Пушкин", "category": "cafe", "distance_label": "200 м"},
                ]
            }
        })
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_chat_with_history(mock_gigachat):
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/chat", json={
            "message": "А что ещё?",
            "history": [
                {"role": "user", "content": "Где поужинать?"},
                {"role": "assistant", "content": "Попробуйте Белуга"},
            ]
        })
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_chat_gigachat_error():
    with patch("clients.gigachat_client.gigachat_request", new_callable=AsyncMock) as m:
        m.side_effect = HTTPException(502, "GigaChat error 500")
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/chat", json={"message": "test"})
    assert r.status_code == 502


@pytest.mark.asyncio
async def test_chat_gigachat_not_configured():
    with patch("clients.gigachat_client.GIGACHAT_API", new_callable=MagicMock) as m:
        m.__str__ = ""
        # Need to also mock the module-level import
        with patch("clients.gigachat_client.gigachat_request", new_callable=AsyncMock) as m2:
            m2.side_effect = HTTPException(503, "GIGACHAT_API is not configured")
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                r = await c.post("/api/chat", json={"message": "test"})
            assert r.status_code == 503


@pytest.mark.asyncio
async def test_chat_empty_message(mock_gigachat):
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/chat", json={"message": ""})
    # FastAPI validates Pydantic model — empty string is valid
    # but the endpoint should still work
    assert r.status_code in (200, 422)