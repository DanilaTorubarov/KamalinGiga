"""
Integration tests for Razvlekis API.
External HTTP calls (Nominatim, Overpass) are mocked so the suite
runs offline and in sandboxed CI environments.
"""
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient, ASGITransport, Response

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from main import app

# ---------------------------------------------------------------------------
# Fixtures — fake external responses
# ---------------------------------------------------------------------------

NOMINATIM_RESPONSE = json.dumps([{
    "lat": "55.7512",
    "lon": "37.6184",
    "display_name": "Большая Никитская улица, 14, Москва"
}]).encode()

OVERPASS_RESPONSE = json.dumps({
    "elements": [
        {
            "type": "node", "id": 111,
            "lat": 55.752, "lon": 37.619,
            "tags": {
                "name": "Кафе Пушкин",
                "amenity": "cafe",
                "addr:street": "Тверской бульвар",
                "addr:housenumber": "26а",
            },
        },
        {
            "type": "node", "id": 222,
            "lat": 55.753, "lon": 37.620,
            "tags": {
                "name": "Ресторан Белуга",
                "amenity": "restaurant",
            },
        },
        {
            "type": "node", "id": 333,
            "lat": 55.754, "lon": 37.621,
            "tags": {
                "name": "Парк Эрмитаж",
                "leisure": "park",
            },
        },
        {
            "type": "node", "id": 444,
            "lat": 55.755, "lon": 37.622,
            "tags": {
                "name": "Бар Нора",
                "amenity": "bar",
            },
        },
        {
            "type": "way", "id": 555,
            "center": {"lat": 55.756, "lon": 37.623},
            "tags": {
                "name": "Театр Современник",
                "amenity": "theatre",
            },
        },
        # element without a name — должен быть отфильтрован
        {
            "type": "node", "id": 666,
            "lat": 55.757, "lon": 37.624,
            "tags": {"amenity": "cafe"},
        },
    ]
}).encode()


def _mock_nominatim(status=200, body=NOMINATIM_RESPONSE):
    return Response(status_code=status, content=body,
                    headers={"content-type": "application/json"})

def _mock_overpass(status=200, body=OVERPASS_RESPONSE):
    return Response(status_code=status, content=body,
                    headers={"content-type": "application/json"})


def make_transport():
    return ASGITransport(app=app)


# ---------------------------------------------------------------------------
# Helper context manager — patches both external httpx calls
# ---------------------------------------------------------------------------
from contextlib import asynccontextmanager

@asynccontextmanager
async def both_mocked(nom_resp=None, ovp_resp=None):
    nom_resp = nom_resp or _mock_nominatim()
    ovp_resp = ovp_resp or _mock_overpass()

    async def fake_get(*args, **kwargs):
        return nom_resp

    async def fake_post(*args, **kwargs):
        return ovp_resp

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(side_effect=fake_get)
    mock_client.post = AsyncMock(side_effect=fake_post)

    with patch("main.httpx.AsyncClient", return_value=mock_client):
        yield mock_client


# ===========================================================================
# 1. POST /api/geocode
# ===========================================================================

@pytest.mark.asyncio
async def test_geocode_ok():
    async with both_mocked():
        async with AsyncClient(transport=make_transport(), base_url="http://test") as c:
            r = await c.post("/api/geocode", json={"address": "Большая Никитская, 14"})
    assert r.status_code == 200
    data = r.json()
    assert data["lat"] == pytest.approx(55.7512, abs=0.001)
    assert data["lng"] == pytest.approx(37.6184, abs=0.001)
    assert "Никитская" in data["label"]
    print(f"  geocode → lat={data['lat']}, lng={data['lng']}")


@pytest.mark.asyncio
async def test_geocode_not_found():
    empty = Response(200, content=b"[]", headers={"content-type": "application/json"})
    async with both_mocked(nom_resp=empty):
        async with AsyncClient(transport=make_transport(), base_url="http://test") as c:
            r = await c.post("/api/geocode", json={"address": "xyzzy_nonexistent"})
    assert r.status_code == 422
    print(f"  geocode 404 → {r.json()['detail']}")


@pytest.mark.asyncio
async def test_geocode_upstream_error():
    err_resp = Response(503, content=b"Service Unavailable")
    async with both_mocked(nom_resp=err_resp):
        async with AsyncClient(transport=make_transport(), base_url="http://test") as c:
            r = await c.post("/api/geocode", json={"address": "Москва"})
    assert r.status_code == 422
    print(f"  geocode 503 → {r.json()['detail']}")


# ===========================================================================
# 2. GET /api/places
# ===========================================================================

@pytest.mark.asyncio
async def test_places_by_coords():
    async with both_mocked():
        async with AsyncClient(transport=make_transport(), base_url="http://test") as c:
            r = await c.get("/api/places", params={"lat": 55.7512, "lng": 37.6184})
    assert r.status_code == 200
    data = r.json()
    assert "places" in data and "total" in data and "categories" in data
    places = data["places"]
    # Элемент без name должен быть отфильтрован → ровно 5 мест
    assert len(places) == 5
    print(f"  places by coords → {data['total']} мест, примеры: {[p['name'] for p in places[:3]]}")


@pytest.mark.asyncio
async def test_places_by_address():
    """Когда coords не переданы — должен вызвать geocode, потом overpass."""
    async with both_mocked():
        async with AsyncClient(transport=make_transport(), base_url="http://test") as c:
            r = await c.get("/api/places", params={"address": "Большая Никитская, 14"})
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 5
    print(f"  places by address → OK, total={data['total']}")


@pytest.mark.asyncio
async def test_places_no_params():
    async with both_mocked():
        async with AsyncClient(transport=make_transport(), base_url="http://test") as c:
            r = await c.get("/api/places")
    assert r.status_code == 422
    print(f"  places no params → 422 as expected")


@pytest.mark.asyncio
async def test_places_category_rest():
    async with both_mocked():
        async with AsyncClient(transport=make_transport(), base_url="http://test") as c:
            r = await c.get("/api/places", params={"lat": 55.75, "lng": 37.62, "category": "rest"})
    assert r.status_code == 200
    places = r.json()["places"]
    assert all(p["category_id"] == "rest" for p in places)
    print(f"  category=rest → {[p['name'] for p in places]}")


@pytest.mark.asyncio
async def test_places_sort_distance():
    async with both_mocked():
        async with AsyncClient(transport=make_transport(), base_url="http://test") as c:
            r = await c.get("/api/places", params={"lat": 55.7512, "lng": 37.6184, "sort": "near"})
    places = r.json()["places"]
    distances = [p["distance_m"] for p in places]
    assert distances == sorted(distances)
    print(f"  sort=near → distances ascending: {distances}")


@pytest.mark.asyncio
async def test_places_text_search():
    async with both_mocked():
        async with AsyncClient(transport=make_transport(), base_url="http://test") as c:
            r = await c.get("/api/places", params={"lat": 55.75, "lng": 37.62, "q": "Пушкин"})
    places = r.json()["places"]
    assert len(places) == 1
    assert "Пушкин" in places[0]["name"]
    print(f"  q=Пушкин → {[p['name'] for p in places]}")


@pytest.mark.asyncio
async def test_places_filter_walk():
    """Фильтр walk=1км: все результаты ≤ 1000 м. Все наши моки далеко → 0 результатов."""
    async with both_mocked():
        async with AsyncClient(transport=make_transport(), base_url="http://test") as c:
            # Берём очень далёкие координаты от мок-данных
            r = await c.get("/api/places", params={"lat": 0.0, "lng": 0.0, "filters": "walk"})
    places = r.json()["places"]
    assert all(p["distance_m"] <= 1000 for p in places)
    print(f"  filter=walk (far origin) → {len(places)} мест ≤ 1км (ожидаем 0)")


@pytest.mark.asyncio
async def test_places_tab_counts():
    """categories должны содержать все 8 вкладок с корректными count."""
    async with both_mocked():
        async with AsyncClient(transport=make_transport(), base_url="http://test") as c:
            r = await c.get("/api/places", params={"lat": 55.75, "lng": 37.62})
    cats = {c["id"]: c["count"] for c in r.json()["categories"]}
    expected_ids = {"all", "rest", "cafe", "bar", "cult", "cinema", "fun", "park"}
    assert expected_ids == set(cats.keys())
    assert cats["all"] == 5
    assert cats["rest"] == 1
    assert cats["cafe"] == 1
    assert cats["bar"] == 1
    assert cats["park"] == 1
    assert cats["cult"] == 1
    print(f"  tab counts → {cats}")


@pytest.mark.asyncio
async def test_places_overpass_error():
    err = Response(504, content=b"Gateway Timeout")
    async with both_mocked(ovp_resp=err):
        async with AsyncClient(transport=make_transport(), base_url="http://test") as c:
            r = await c.get("/api/places", params={"lat": 55.75, "lng": 37.62})
    assert r.status_code == 502
    print(f"  overpass 504 → backend 502: {r.json()['detail']}")


@pytest.mark.asyncio
async def test_places_pagination():
    async with both_mocked():
        async with AsyncClient(transport=make_transport(), base_url="http://test") as c:
            r = await c.get("/api/places", params={"lat": 55.75, "lng": 37.62, "limit": 2, "offset": 0})
    data = r.json()
    assert len(data["places"]) == 2
    assert data["total"] == 5

    async with both_mocked():
        async with AsyncClient(transport=make_transport(), base_url="http://test") as c:
            r2 = await c.get("/api/places", params={"lat": 55.75, "lng": 37.62, "limit": 2, "offset": 2})
    data2 = r2.json()
    assert len(data2["places"]) == 2

    # page 1 и page 2 — разные места
    ids1 = {p["id"] for p in data["places"]}
    ids2 = {p["id"] for p in data2["places"]}
    assert not ids1 & ids2
    # IDs should use colon separator (safe in URL paths)
    assert all(":" in pid for pid in ids1 | ids2)
    print(f"  pagination → page1={ids1}, page2={ids2}")


# ===========================================================================
# 3 & 4. Save / Unsave
# ===========================================================================

@pytest.mark.asyncio
async def test_save_and_unsave():
    async with AsyncClient(transport=make_transport(), base_url="http://test") as c:
        r = await c.post("/api/places/node:111/save")
        assert r.status_code == 200
        assert r.json() == {"ok": True}
        print("  save → ok")

        r = await c.delete("/api/places/node:111/save")
        assert r.status_code == 200
        assert r.json() == {"ok": True}
        print("  unsave → ok")

        # Double unsave should not crash
        r = await c.delete("/api/places/node:111/save")
        assert r.status_code == 200
        print("  double unsave → ok (idempotent)")


# ===========================================================================
# 5. POST /api/chat
# ===========================================================================

@pytest.mark.asyncio
async def test_chat_restaurant():
    async with AsyncClient(transport=make_transport(), base_url="http://test") as c:
        r = await c.post("/api/chat", json={"message": "Хочу поужинать"})
    assert r.status_code == 200
    reply = r.json()["reply"]
    assert len(reply) > 10
    print(f"  chat 'поужинать' → {reply[:80]}")


@pytest.mark.asyncio
async def test_chat_park():
    async with AsyncClient(transport=make_transport(), base_url="http://test") as c:
        r = await c.post("/api/chat", json={"message": "Хочу прогуляться в парке"})
    reply = r.json()["reply"]
    assert "парк" in reply.lower() or "прогулк" in reply.lower()
    print(f"  chat 'парк' → {reply[:80]}")


@pytest.mark.asyncio
async def test_chat_route():
    async with AsyncClient(transport=make_transport(), base_url="http://test") as c:
        r = await c.post("/api/chat", json={
            "message": "Составь маршрут на вечер",
            "context": {"address": "Тверская, 1"}
        })
    reply = r.json()["reply"]
    assert len(reply) > 20
    print(f"  chat 'маршрут' → {reply[:80]}")


@pytest.mark.asyncio
async def test_chat_unknown():
    async with AsyncClient(transport=make_transport(), base_url="http://test") as c:
        r = await c.post("/api/chat", json={"message": "хорошая погода сегодня"})
    assert r.status_code == 200
    reply = r.json()["reply"]
    assert len(reply) > 5
    print(f"  chat unknown → {reply[:80]}")


@pytest.mark.asyncio
async def test_chat_empty_history():
    async with AsyncClient(transport=make_transport(), base_url="http://test") as c:
        r = await c.post("/api/chat", json={"message": "Где выпить кофе?", "history": []})
    assert r.status_code == 200
    print(f"  chat empty history → ok")
