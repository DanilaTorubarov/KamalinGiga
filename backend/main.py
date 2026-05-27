import asyncio
import math
import os
import time
import uuid
from pathlib import Path
from typing import Any, Literal

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# .env лежит в корне проекта (на уровень выше backend/)
load_dotenv(Path(__file__).parent.parent / ".env")

app = FastAPI(title="Places API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Категории
# ---------------------------------------------------------------------------

CATEGORY_QUERY = {
    "all":    "еда",
    "rest":   "ресторан",
    "cafe":   "кафе",
    "bar":    "бар",
    "cult":   "музей театр галерея",
    "cinema": "кинотеатр",
    "fun":    "развлечения",
    "park":   "парк сад",
}

# ---------------------------------------------------------------------------
# Утилиты
# ---------------------------------------------------------------------------

def haversine(lat1, lon1, lat2, lon2):
    R = 6371000
    from math import radians, sin, cos, asin, sqrt
    dphi = radians(lat2 - lat1)
    dlam = radians(lon2 - lon1)
    phi1, phi2 = radians(lat1), radians(lat2)
    a = sin(dphi/2)**2 + cos(phi1)*cos(phi2)*sin(dlam/2)**2
    return int(2 * R * asin(sqrt(a)))

async def geocode_address(address: str):
    async with httpx.AsyncClient(headers={"User-Agent": "PlacesApp/1.0"}) as client:
        r = await client.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": address, "format": "json", "limit": 1, "accept-language": "ru"}
        )
    if r.status_code != 200:
        raise HTTPException(422, "Ошибка геокодера")
    data = r.json()
    if not data:
        raise HTTPException(422, "Адрес не найден")
    return float(data[0]["lat"]), float(data[0]["lon"])

# ---------------------------------------------------------------------------
# 2GIS API
# ---------------------------------------------------------------------------

DGIS_API_KEY = os.getenv("DGIS_API_KEY")


async def dgis_search(lat: float, lng: float, query: str, radius: int = 5000):
    # Конечная точка без geosearch!
    url = "https://catalog.api.2gis.com/3.0/items"

    params = {
        "key": DGIS_API_KEY,
        "q": query,
        "point": f"{lng},{lat}",  # Сначала долгота, потом широта
        "radius": radius,
        "sort": "distance",
        "fields": "items.point",  # Запрашиваем координаты у API
    }

    async with httpx.AsyncClient() as client:
        r = await client.get(url, params=params)

    if r.status_code != 200:
        raise HTTPException(502, f"2GIS error {r.status_code}")

    return r.json().get("result", {}).get("items", [])

def convert_dgis_place(item, user_lat, user_lng):
    point = item.get("point", {})
    lat = point.get("lat")
    lon = point.get("lon") # Тут вы берете "lon" — это правильно для 2GIS!

    if lat is None or lon is None:
        return None

    dist = haversine(user_lat, user_lng, lat, lon)

    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "address": item.get("address_name"),
        "lat": lat,
        "lng": lon, # И здесь отдаете "lng" клиенту
        "distance_m": dist,
        "distance_label": f"{dist} м" if dist < 1000 else f"{dist/1000:.1f} км",
    }

# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

class GeocodeIn(BaseModel):
    address: str

class GeocodeOut(BaseModel):
    lat: float
    lng: float

@app.post("/api/geocode", response_model=GeocodeOut)
async def api_geocode(body: GeocodeIn):
    lat, lng = await geocode_address(body.address)
    return GeocodeOut(lat=lat, lng=lng)

@app.get("/api/places")
async def api_places(
    lat: float | None = None,
    lng: float | None = None,
    address: str | None = None,
    category: str = "all",
    limit: int = Query(50, ge=1, le=100)
):
    if lat is None or lng is None:
        if not address:
            raise HTTPException(422, "Нужен lat+lng или address")
        lat, lng = await geocode_address(address)

    query = CATEGORY_QUERY.get(category, "еда")
    raw_items = await dgis_search(lat, lng, query)
    places = []
    for item in raw_items:
        p = convert_dgis_place(item, lat, lng)

        if p:
            places.append(p)
    print(places)
    places.sort(key=lambda x: x["distance_m"])
    return {"total": len(places), "places": places[:limit]}

# ---------------------------------------------------------------------------
# GigaChat
# ---------------------------------------------------------------------------

GIGACHAT_AUTH_KEY = os.getenv("GIGACHAT_API")

_token: dict[str, Any] = {"access_token": None, "expires_at": 0}
_token_lock = asyncio.Lock()

GIGACHAT_SYSTEM_PROMPT = (
    "Ты — дружелюбный ассистент приложения «Развлекись». "
    "Помогаешь пользователю найти кафе, рестораны, бары и другие заведения рядом. "
    "Отвечай коротко, по-русски, без лишних формальностей."
)


async def _fetch_token() -> str:
    async with httpx.AsyncClient(verify=False) as client:
        r = await client.post(
            "https://ngw.devices.sberbank.ru:9443/api/v2/oauth",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
                "RqUID": str(uuid.uuid4()),
                "Authorization": f"Basic {GIGACHAT_AUTH_KEY}",
            },
            data={"scope": "GIGACHAT_API_PERS"},
            timeout=10,
        )
    r.raise_for_status()
    data = r.json()
    _token["access_token"] = data["access_token"]
    _token["expires_at"] = data["expires_at"]
    return _token["access_token"]


async def get_access_token() -> str:
    async with _token_lock:
        now_ms = int(time.time() * 1000)
        if _token["access_token"] and _token["expires_at"] > now_ms + 60_000:
            return _token["access_token"]
        return await _fetch_token()


async def gigachat_complete(messages: list[dict]) -> str:
    for attempt in range(2):
        token = await get_access_token()
        async with httpx.AsyncClient(verify=False) as client:
            r = await client.post(
                "https://gigachat.devices.sberbank.ru/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {token}"},
                json={"model": "GigaChat", "messages": messages},
                timeout=30,
            )
        if r.status_code == 401 and attempt == 0:
            async with _token_lock:
                _token["access_token"] = None
                _token["expires_at"] = 0
            continue
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    raise HTTPException(502, "GigaChat недоступен")


# ---------------------------------------------------------------------------
# Чат
# ---------------------------------------------------------------------------

class HistoryMessage(BaseModel):
    role: str
    content: str

class ChatIn(BaseModel):
    message: str
    history: list[HistoryMessage] = []

class ChatOut(BaseModel):
    reply: str

@app.post("/api/chat", response_model=ChatOut)
async def api_chat(body: ChatIn):
    messages = [{"role": "system", "content": GIGACHAT_SYSTEM_PROMPT}]
    for h in body.history:
        if h.role in ("user", "assistant"):
            messages.append({"role": h.role, "content": h.content})
    messages.append({"role": "user", "content": body.message})

    reply = await gigachat_complete(messages)
    return ChatOut(reply=reply)
