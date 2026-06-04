"""
Integration tests for Развлекись API.
External HTTP calls (Google, GigaChat) are mocked so the suite
runs offline and in CI without real API keys.
"""

import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport

from fastapi import HTTPException

from main import app


transport = ASGITransport(app=app)

GOOGLE_PLACES_RESPONSE = [
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
]

GIGACHAT_RESPONSE = {
    "choices": [{
        "message": {"role": "assistant", "content": "Попробуйте ресторан Белуга — отличная кухня!"}
    }],
}

GOOGLE_AUTOCOMPLETE_RESPONSE = {
    "suggestions": [
        {
            "placePrediction": {
                "placeId": "ChIJabc",
                "text": {"text": "Тверская улица, Москва", "secondaryText": "Россия"},
            }
        },
        {
            "placePrediction": {
                "placeId": "ChIJdef",
                "text": {"text": "Тверская улица, 10", "secondaryText": "Москва"},
            }
        },
    ],
}


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_nearby():
    with patch("api.places.google_nearby_search", new_callable=AsyncMock) as m:
        m.return_value = GOOGLE_PLACES_RESPONSE
        yield m


@pytest.fixture
def mock_geocode():
    with patch("services.geocode_service.geocode_address", new_callable=AsyncMock) as m:
        m.return_value = (55.7596, 37.6184)
        yield m


@pytest.fixture
def mock_gigachat():
    with patch("services.chat_service.gigachat_request", new_callable=AsyncMock) as m:
        m.return_value = GIGACHAT_RESPONSE
        yield m


@pytest.fixture
def mock_autocomplete():
    with patch("api.suggestions.google_autocomplete", new_callable=AsyncMock) as m:
        m.return_value = GOOGLE_AUTOCOMPLETE_RESPONSE["suggestions"]
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
    with patch("api.places.google_nearby_search", new_callable=AsyncMock) as m:
        m.side_effect = HTTPException(502, "Google Places error: REQUEST_DENIED")
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.get("/api/places", params={"lat": 55.75, "lng": 37.62})
    assert r.status_code == 502


@pytest.mark.asyncio
async def test_places_google_zero_results():
    with patch("api.places.google_nearby_search", new_callable=AsyncMock) as m:
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
        m.side_effect = HTTPException(422, "Адрес не найден")
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.post("/api/geocode", json={"address": "nonexistent_xyz"})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_geocode_empty_body():
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/geocode", json={})
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
    with patch("services.chat_service.gigachat_request", new_callable=AsyncMock) as m:
        m.side_effect = HTTPException(502, "GigaChat error 500")
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.post("/api/chat", json={"message": "test"})
    assert r.status_code == 502


# ===========================================================================
# 4. GET /api/suggestions
# ===========================================================================

@pytest.mark.asyncio
async def test_suggestions_ok(mock_autocomplete):
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/api/suggestions", params={"q": "Тверская"})
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) == 2
    assert "Тверская улица, Москва, Россия" in data


@pytest.mark.asyncio
async def test_suggestions_with_coords(mock_autocomplete):
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/api/suggestions", params={"q": "Тверская", "lat": 55.75, "lng": 37.62})
    assert r.status_code == 200
    assert len(r.json()) == 2


@pytest.mark.asyncio
async def test_suggestions_empty_q():
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/api/suggestions", params={"q": ""})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_suggestions_missing_q():
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/api/suggestions")
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_suggestions_upstream_error():
    with patch("api.suggestions.google_autocomplete", new_callable=AsyncMock) as m:
        m.side_effect = HTTPException(502, "Google Autocomplete error 403")
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.get("/api/suggestions", params={"q": "Тверская"})
    assert r.status_code == 502
