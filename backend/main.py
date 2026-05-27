"""
Razvlekis backend — Google Maps Platform + Google Gemini.

Required env vars:
  GOOGLE_MAPS_KEY  — Google Maps Platform key
                     (enable: Geocoding API, Places API)
  GOOGLE_AI_KEY    — Google AI Studio key for Gemini chat  (optional;
                     chat degrades gracefully when absent)
"""

import math
import os
from typing import Literal

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Secrets — set these as environment variables
# ---------------------------------------------------------------------------
GOOGLE_MAPS_KEY: str | None = os.environ.get("GOOGLE_MAPS_KEY")
GOOGLE_AI_KEY:   str | None = os.environ.get("GOOGLE_AI_KEY")

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="Razvlekis API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# In-memory saved places  (process-local; no auth)
# ---------------------------------------------------------------------------
_saved: set[str] = set()

# ---------------------------------------------------------------------------
# Category config
# ---------------------------------------------------------------------------
CATEGORY_LABELS: dict[str, str] = {
    "all":    "Все",
    "rest":   "Рестораны",
    "cafe":   "Кофейни",
    "bar":    "Бары",
    "cult":   "Культура",
    "cinema": "Кино",
    "fun":    "Развлечения",
    "park":   "Парки",
}

# Singular label shown inside each place card
CATEGORY_LABEL_SINGULAR: dict[str, str] = {
    "all":    "Место",
    "rest":   "Ресторан",
    "cafe":   "Кофейня",
    "bar":    "Бар",
    "cult":   "Культура",
    "cinema": "Кинотеатр",
    "fun":    "Развлечения",
    "park":   "Парк",
}

# Google place type → our category_id
GOOGLE_TYPE_TO_CAT: dict[str, str] = {
    "restaurant":              "rest",
    "food":                    "rest",
    "cafe":                    "cafe",
    "bakery":                  "cafe",
    "coffee_shop":             "cafe",
    "bar":                     "bar",
    "night_club":              "bar",
    "pub":                     "bar",
    "museum":                  "cult",
    "art_gallery":             "cult",
    "theater":                 "cult",
    "performing_arts_theater": "cult",
    "movie_theater":           "cinema",
    "amusement_park":          "fun",
    "bowling_alley":           "fun",
    "arcade":                  "fun",
    "tourist_attraction":      "fun",
    "park":                    "park",
    "natural_feature":         "park",
    "campground":              "park",
}

# our category_id → Google type (for nearbysearch ?type=)
CAT_TO_GOOGLE_TYPE: dict[str, str] = {
    "rest":   "restaurant",
    "cafe":   "cafe",
    "bar":    "bar",
    "cult":   "museum",
    "cinema": "movie_theater",
    "fun":    "amusement_park",
    "park":   "park",
}

# Google price_level (0-4) → display string
PRICE_MAP: dict[int, str] = {0: "Free", 1: "₽", 2: "₽₽", 3: "₽₽₽", 4: "₽₽₽₽"}
PRICE_FILTERS = {"Free", "₽", "₽₽"}

# ---------------------------------------------------------------------------
# Google API endpoints
# ---------------------------------------------------------------------------
_GEOCODE_URL    = "https://maps.googleapis.com/maps/api/geocode/json"
_NEARBY_URL     = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
_TEXTSEARCH_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"
_PHOTO_URL      = "https://maps.googleapis.com/maps/api/place/photo"
_GEMINI_URL     = (
    "https://generativelanguage.googleapis.com"
    "/v1beta/models/gemini-1.5-flash:generateContent"
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> int:
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lng2 - lng1)
    a = (math.sin(dphi / 2) ** 2
         + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2)
    return int(2 * R * math.asin(math.sqrt(a)))


def _photo_url(photo_reference: str) -> str | None:
    if not GOOGLE_MAPS_KEY or not photo_reference:
        return None
    return f"{_PHOTO_URL}?maxwidth=900&photo_reference={photo_reference}&key={GOOGLE_MAPS_KEY}"


def _category_from_types(types: list[str]) -> str:
    for t in types:
        if t in GOOGLE_TYPE_TO_CAT:
            return GOOGLE_TYPE_TO_CAT[t]
    return "fun"


def result_to_place(result: dict, user_lat: float, user_lng: float) -> dict:
    """Convert one Google Places API result dict into a Place dict."""
    place_id = result.get("place_id", "")
    name     = result.get("name", "")
    address  = result.get("vicinity") or result.get("formatted_address") or ""

    loc       = result.get("geometry", {}).get("location", {})
    place_lat = float(loc.get("lat", 0))
    place_lng = float(loc.get("lng", 0))

    types       = result.get("types", [])
    category_id = _category_from_types(types)

    rating      = result.get("rating")        # float | None
    price_level = result.get("price_level")   # 0-4   | None
    price       = PRICE_MAP.get(price_level) if price_level is not None else None

    distance_m = haversine(user_lat, user_lng, place_lat, place_lng)
    dist_label = (
        f"{distance_m} м" if distance_m < 1000
        else f"{distance_m / 1000:.1f} км"
    )

    photos    = result.get("photos", [])
    image_url = None
    if photos:
        ref = photos[0].get("photo_reference")
        if ref:
            image_url = _photo_url(ref)

    opening = result.get("opening_hours") or {}
    is_open = opening.get("open_now")   # True | False | None

    return {
        "id":             place_id,
        "name":           name,
        "category":       CATEGORY_LABEL_SINGULAR.get(category_id, "Место"),
        "category_id":    category_id,
        "rating":         rating,
        "price":          price,
        "distance_m":     distance_m,
        "distance_label": dist_label,
        "image_url":      image_url,
        "is_open":        is_open,
        "saved":          place_id in _saved,
        "tags":           [],
        "address":        address,
        "lat":            place_lat,
        "lng":            place_lng,
    }


async def _geocode_address(address: str) -> tuple[float, float]:
    """Address string → (lat, lng) via Google Geocoding API."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(
            _GEOCODE_URL,
            params={"address": address, "key": GOOGLE_MAPS_KEY, "language": "ru"},
        )
    if r.status_code != 200:
        raise HTTPException(422, f"Google Geocoder вернул {r.status_code}")
    data = r.json()
    if data.get("status") != "OK" or not data.get("results"):
        raise HTTPException(422, "Адрес не найден")
    loc = data["results"][0]["geometry"]["location"]
    return loc["lat"], loc["lng"]


# ===========================================================================
# 0. GET /api/health
# ===========================================================================

@app.get("/api/health")
def health():
    return {"status": "ok"}


# ===========================================================================
# 1. POST /api/geocode
# ===========================================================================

class GeocodeIn(BaseModel):
    address: str

class GeocodeOut(BaseModel):
    lat:   float
    lng:   float
    label: str | None = None


@app.post("/api/geocode", response_model=GeocodeOut)
async def geocode(body: GeocodeIn):
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(
            _GEOCODE_URL,
            params={"address": body.address, "key": GOOGLE_MAPS_KEY, "language": "ru"},
        )
    if r.status_code != 200:
        raise HTTPException(422, f"Google Geocoder вернул {r.status_code}")
    data = r.json()
    if data.get("status") != "OK" or not data.get("results"):
        raise HTTPException(422, "Адрес не найден")
    result = data["results"][0]
    loc    = result["geometry"]["location"]
    label  = result.get("formatted_address")
    return GeocodeOut(lat=loc["lat"], lng=loc["lng"], label=label)


# ===========================================================================
# 2. GET /api/places
# ===========================================================================

@app.get("/api/places")
async def list_places(
    lat:      float | None = None,
    lng:      float | None = None,
    address:  str   | None = None,
    q:        str   | None = None,
    category: str          = "all",
    sort:     Literal["near", "rating", "price"] = "near",
    filters:  str   | None = None,          # comma-separated: open,walk,wifi,…
    limit:    int          = Query(default=60, ge=1, le=100),
    offset:   int          = Query(default=0, ge=0),
):
    # ── Resolve coordinates ─────────────────────────────────────────────────
    if lat is None or lng is None:
        if not address:
            raise HTTPException(422, "Нужен lat+lng или address")
        lat, lng = await _geocode_address(address)

    # ── Build Google Places request ─────────────────────────────────────────
    base_params: dict = {
        "key":      GOOGLE_MAPS_KEY,
        "language": "ru",
        "radius":   5000,
        "location": f"{lat},{lng}",
    }

    if q:
        # Free-text search
        url = _TEXTSEARCH_URL
        base_params["query"] = q
    elif category in CAT_TO_GOOGLE_TYPE:
        # Category-filtered nearby search
        url = _NEARBY_URL
        base_params["type"] = CAT_TO_GOOGLE_TYPE[category]
    else:
        # "all" — broad keyword nearby search
        url = _NEARBY_URL
        base_params["keyword"] = "кафе ресторан бар театр парк"

    async with httpx.AsyncClient(timeout=20.0) as http_client:
        sr = await http_client.get(url, params=base_params)

    if sr.status_code != 200:
        raise HTTPException(502, f"Google Places API error: {sr.status_code}")

    gdata      = sr.json()
    api_status = gdata.get("status", "")
    if api_status not in ("OK", "ZERO_RESULTS"):
        raise HTTPException(502, f"Google Places API: {api_status}")

    results    = gdata.get("results", [])
    all_places = [result_to_place(item, lat, lng) for item in results]

    # ── Non-category filters ────────────────────────────────────────────────
    active  = set(filters.split(",")) if filters else set()
    trimmed = list(all_places)

    if "open"   in active:
        trimmed = [p for p in trimmed if p["is_open"] is True]
    if "walk"   in active:
        trimmed = [p for p in trimmed if p["distance_m"] <= 1000]
    if "budget" in active:
        trimmed = [p for p in trimmed if p.get("price") in PRICE_FILTERS]
    for tag in ("terrace", "wifi", "pet"):
        if tag in active:
            trimmed = [p for p in trimmed if tag in p["tags"]]

    # ── Tab-strip counts (before category filter) ───────────────────────────
    cat_counts: dict[str, int] = {k: 0 for k in CATEGORY_LABELS}
    cat_counts["all"] = len(trimmed)
    for p in trimmed:
        cid = p["category_id"]
        if cid in cat_counts:
            cat_counts[cid] += 1

    # ── Category filter ─────────────────────────────────────────────────────
    if category != "all":
        trimmed = [p for p in trimmed if p["category_id"] == category]

    # ── Sort ────────────────────────────────────────────────────────────────
    if sort == "rating":
        trimmed.sort(key=lambda p: p["rating"] or 0.0, reverse=True)
    elif sort == "price":
        _po = {"Free": 0, "₽": 1, "₽₽": 2, "₽₽₽": 3, "₽₽₽₽": 4, None: 99}
        trimmed.sort(key=lambda p: _po.get(p["price"], 99))
    else:  # "near"
        trimmed.sort(key=lambda p: p["distance_m"])

    total = len(trimmed)
    page  = trimmed[offset: offset + limit]

    categories_out = [
        {"id": k, "label": CATEGORY_LABELS[k], "count": cat_counts[k]}
        for k in CATEGORY_LABELS
    ]
    return {"places": page, "total": total, "categories": categories_out}


# ===========================================================================
# 3 & 4. POST / DELETE /api/places/{place_id}/save
# ===========================================================================

@app.post("/api/places/{place_id}/save")
def save_place(place_id: str):
    _saved.add(place_id)
    return {"ok": True}


@app.delete("/api/places/{place_id}/save")
def unsave_place(place_id: str):
    _saved.discard(place_id)
    return {"ok": True}


# ===========================================================================
# 5. POST /api/chat  (Google Gemini)
# ===========================================================================

class ChatMsg(BaseModel):
    role:    Literal["user", "assistant"]
    content: str

class ChatIn(BaseModel):
    message: str
    history: list[ChatMsg] = []
    context: dict | None   = None

class ChatOut(BaseModel):
    reply:     str
    place_ids: list[str] | None = None


@app.post("/api/chat", response_model=ChatOut)
async def chat(body: ChatIn):
    if not GOOGLE_AI_KEY:
        return ChatOut(
            reply=(
                "Чат-ассистент не настроен. "
                "Задайте переменную окружения GOOGLE_AI_KEY."
            )
        )

    ctx = body.context or {}
    system_parts = [
        "Ты помощник приложения Razvlekis — сервис поиска мест для отдыха и развлечений.",
        "Отвечай кратко и по-русски. Предлагай конкретные места с учётом контекста поиска.",
    ]
    if ctx.get("address"):
        system_parts.append(f"Район поиска: {ctx['address']}.")
    if ctx.get("category") and ctx["category"] != "all":
        system_parts.append(f"Выбрана категория: {ctx['category']}.")
    if ctx.get("filters"):
        system_parts.append(f"Активные фильтры: {ctx['filters']}.")

    # Gemini uses "model" for the assistant role
    contents = []
    for m in body.history:
        role = "model" if m.role == "assistant" else "user"
        contents.append({"role": role, "parts": [{"text": m.content}]})
    contents.append({"role": "user", "parts": [{"text": body.message}]})

    async with httpx.AsyncClient(timeout=30.0) as http_client:
        r = await http_client.post(
            _GEMINI_URL,
            params={"key": GOOGLE_AI_KEY},
            json={
                "system_instruction": {"parts": [{"text": " ".join(system_parts)}]},
                "contents": contents,
                "generationConfig": {
                    "temperature":     0.7,
                    "maxOutputTokens": 800,
                },
            },
        )
    if r.status_code != 200:
        raise HTTPException(502, f"Gemini API error: {r.text[:300]}")

    reply_text = (
        r.json()
        .get("candidates", [{}])[0]
        .get("content", {})
        .get("parts", [{}])[0]
        .get("text", "")
    )
    return ChatOut(reply=reply_text or "…")
