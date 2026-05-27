import math
import datetime
from typing import Literal

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

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

# In-memory saved places (process-local, no auth)
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

PRICE_FILTERS = {"Free", "₽", "₽₽"}

# Overpass filter fragments per category
# {r} = radius in metres, {lat}/{lng} = centre
_OVP: dict[str, str] = {
    "all": (
        'node["name"]["amenity"~"restaurant|cafe|bar|pub|nightclub|fast_food|cinema|bowling_alley|theatre|arts_centre"](around:{r},{lat},{lng});'
        'node["name"]["tourism"="museum"](around:{r},{lat},{lng});'
        'node["name"]["leisure"~"park|garden|escape_game|amusement_arcade"](around:{r},{lat},{lng});'
        'way["name"]["amenity"~"restaurant|cafe|bar|pub|nightclub|fast_food|cinema|bowling_alley|theatre|arts_centre"](around:{r},{lat},{lng});'
        'way["name"]["tourism"="museum"](around:{r},{lat},{lng});'
        'way["name"]["leisure"~"park|garden"](around:{r},{lat},{lng});'
    ),
    "rest": (
        'node["name"]["amenity"~"restaurant|fast_food"](around:{r},{lat},{lng});'
        'way["name"]["amenity"~"restaurant|fast_food"](around:{r},{lat},{lng});'
    ),
    "cafe": (
        'node["name"]["amenity"="cafe"](around:{r},{lat},{lng});'
        'way["name"]["amenity"="cafe"](around:{r},{lat},{lng});'
    ),
    "bar": (
        'node["name"]["amenity"~"bar|pub|nightclub"](around:{r},{lat},{lng});'
        'way["name"]["amenity"~"bar|pub|nightclub"](around:{r},{lat},{lng});'
    ),
    "cult": (
        'node["name"]["tourism"="museum"](around:{r},{lat},{lng});'
        'node["name"]["amenity"~"theatre|arts_centre"](around:{r},{lat},{lng});'
        'way["name"]["tourism"="museum"](around:{r},{lat},{lng});'
        'way["name"]["amenity"~"theatre|arts_centre"](around:{r},{lat},{lng});'
    ),
    "cinema": (
        'node["name"]["amenity"="cinema"](around:{r},{lat},{lng});'
        'way["name"]["amenity"="cinema"](around:{r},{lat},{lng});'
    ),
    "fun": (
        'node["name"]["amenity"~"bowling_alley|casino"](around:{r},{lat},{lng});'
        'node["name"]["leisure"~"escape_game|amusement_arcade"](around:{r},{lat},{lng});'
        'way["name"]["amenity"~"bowling_alley|casino"](around:{r},{lat},{lng});'
    ),
    "park": (
        'node["name"]["leisure"~"park|garden"](around:{r},{lat},{lng});'
        'way["name"]["leisure"~"park|garden"](around:{r},{lat},{lng});'
    ),
}

# HTTP headers for Nominatim (required by their ToS)
_NOMINATIM_HEADERS = {"User-Agent": "Razvlekis/1.0 (hackathon demo)"}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> int:
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return int(2 * R * math.asin(math.sqrt(a)))


def _category_from_tags(tags: dict) -> tuple[str, str]:
    """Returns (category_id, category_label) from OSM element tags."""
    amenity = tags.get("amenity", "")
    tourism = tags.get("tourism", "")
    leisure = tags.get("leisure", "")

    if amenity == "restaurant":           return "rest",   "Ресторан"
    if amenity == "fast_food":            return "rest",   "Фастфуд"
    if amenity == "cafe":                 return "cafe",   "Кофейня"
    if amenity in ("bar", "pub"):         return "bar",    "Бар"
    if amenity == "nightclub":            return "bar",    "Ночной клуб"
    if amenity == "theatre":              return "cult",   "Театр"
    if amenity == "arts_centre":          return "cult",   "Культурный центр"
    if tourism == "museum":               return "cult",   "Музей"
    if amenity == "cinema":               return "cinema", "Кинотеатр"
    if amenity == "bowling_alley":        return "fun",    "Боулинг"
    if leisure in ("escape_game", "amusement_arcade"):
                                          return "fun",    "Развлечения"
    if amenity == "casino":               return "fun",    "Казино"
    if leisure in ("park", "garden"):     return "park",   "Парк"
    return "fun", "Место"


def _price_from_tags(tags: dict) -> str | None:
    amenity = tags.get("amenity", "")
    if amenity == "fast_food":  return "₽"
    if amenity == "cafe":       return "₽₽"
    return None


def _rating_from_tags(tags: dict) -> float | None:
    for key in ("rating", "stars"):
        val = tags.get(key)
        if val:
            try:
                r = float(val)
                if 0 < r <= 5:   return round(r, 1)
                if 0 < r <= 10:  return round(r / 2, 1)
            except (ValueError, TypeError):
                pass
    return None


def _element_to_place(elem: dict, user_lat: float, user_lng: float) -> dict | None:
    tags = elem.get("tags", {})
    name = tags.get("name")
    if not name:
        return None

    if elem["type"] == "node":
        place_lat, place_lng = elem["lat"], elem["lon"]
    elif elem["type"] == "way" and "center" in elem:
        place_lat, place_lng = elem["center"]["lat"], elem["center"]["lon"]
    else:
        return None

    place_id = f"{elem['type']}:{elem['id']}"
    category_id, category_label = _category_from_tags(tags)
    distance_m = haversine(user_lat, user_lng, place_lat, place_lng)
    dist_label = f"{distance_m} м" if distance_m < 1000 else f"{distance_m / 1000:.1f} км"

    addr_parts = [tags.get("addr:street", ""), tags.get("addr:housenumber", "")]
    address = " ".join(p for p in addr_parts if p) or ""

    return {
        "id":             place_id,
        "name":           name,
        "category":       category_label,
        "category_id":    category_id,
        "rating":         _rating_from_tags(tags),
        "price":          _price_from_tags(tags),
        "distance_m":     distance_m,
        "distance_label": dist_label,
        "image_url":      None,
        "is_open":        None,   # OSM hours are complex to parse reliably
        "saved":          place_id in _saved,
        "tags":           [],
        "address":        address,
        "lat":            place_lat,
        "lng":            place_lng,
    }


async def _geocode(address: str) -> tuple[float, float, str]:
    """address → (lat, lng, display_name) via Nominatim (free, no key)."""
    async with httpx.AsyncClient(timeout=10.0, headers=_NOMINATIM_HEADERS) as client:
        r = await client.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": address, "format": "json", "limit": 1, "accept-language": "ru"},
        )
    if r.status_code != 200:
        raise HTTPException(422, f"Nominatim вернул {r.status_code}")
    results = r.json()
    if not results:
        raise HTTPException(422, "Адрес не найден")
    res = results[0]
    return float(res["lat"]), float(res["lon"]), res.get("display_name", address)


async def _overpass(category: str, lat: float, lng: float, radius: int = 2500) -> list[dict]:
    """Query Overpass API for OSM places near (lat, lng)."""
    fragment = _OVP.get(category, _OVP["all"]).format(r=radius, lat=lat, lng=lng)
    query = f"[out:json][timeout:25];(\n{fragment}\n);out center;"

    async with httpx.AsyncClient(timeout=35.0) as client:
        r = await client.post(
            "https://overpass-api.de/api/interpreter",
            data={"data": query},
        )
    if r.status_code != 200:
        raise HTTPException(502, f"Overpass API error: {r.status_code}")
    return r.json().get("elements", [])


# ===========================================================================
# 1. POST /api/geocode
# ===========================================================================

class GeocodeIn(BaseModel):
    address: str

class GeocodeOut(BaseModel):
    lat: float
    lng: float
    label: str | None = None


@app.post("/api/geocode", response_model=GeocodeOut)
async def geocode(body: GeocodeIn):
    lat, lng, label = await _geocode(body.address)
    return GeocodeOut(lat=lat, lng=lng, label=label)


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
    filters:  str   | None = None,          # comma-separated codes
    limit:    int          = Query(default=60, ge=1, le=100),
    offset:   int          = Query(default=0, ge=0),
):
    # Resolve coordinates
    if lat is None or lng is None:
        if not address:
            raise HTTPException(422, "Нужен lat+lng или address")
        lat, lng, _ = await _geocode(address)

    # Fetch from Overpass
    elements = await _overpass(category, lat, lng)

    # Convert to place dicts (deduplicate by ID)
    seen: set[str] = set()
    all_places: list[dict] = []
    for elem in elements:
        p = _element_to_place(elem, lat, lng)
        if p and p["id"] not in seen:
            seen.add(p["id"])
            all_places.append(p)

    # Text search
    if q:
        ql = q.lower()
        all_places = [p for p in all_places if ql in p["name"].lower() or ql in p["category"].lower()]

    # Non-category filters
    active = set(filters.split(",")) if filters else set()
    trimmed = list(all_places)

    if "open"   in active: trimmed = [p for p in trimmed if p["is_open"] is True]
    if "walk"   in active: trimmed = [p for p in trimmed if p["distance_m"] <= 1000]
    if "budget" in active: trimmed = [p for p in trimmed if p.get("price") in PRICE_FILTERS]
    for tag in ("terrace", "wifi", "pet"):
        if tag in active:
            trimmed = [p for p in trimmed if tag in p["tags"]]

    # Tab-strip counts (before category filter)
    cat_counts: dict[str, int] = {k: 0 for k in CATEGORY_LABELS}
    cat_counts["all"] = len(trimmed)
    for p in trimmed:
        cid = p["category_id"]
        if cid in cat_counts:
            cat_counts[cid] += 1

    # Category filter
    if category != "all":
        trimmed = [p for p in trimmed if p["category_id"] == category]

    # Sort
    if sort == "rating":
        trimmed.sort(key=lambda p: p["rating"] or 0.0, reverse=True)
    elif sort == "price":
        _po = {"Free": 0, "₽": 1, "₽₽": 2, "₽₽₽": 3, "₽₽₽₽": 4, None: 99}
        trimmed.sort(key=lambda p: _po.get(p["price"], 99))
    else:
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
# 5. POST /api/chat  — simple rule-based assistant (no external LLM needed)
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


_CHAT_RULES: list[tuple[list[str], str]] = [
    (["ужин", "поужинать", "обед", "поесть", "кушать", "голод"],
     "Переключитесь на вкладку «Рестораны» — там все ближайшие места для еды, отсортированные по расстоянию!"),
    (["кофе", "кофейн", "капучин", "латте"],
     "Загляните во вкладку «Кофейни» — найдёте ближайшие места для кофе."),
    (["бар", "выпить", "коктейл", "пиво", "вино"],
     "Открывайте вкладку «Бары» — выберем что-то атмосферное для вечера!"),
    (["кино", "фильм", "кинотеатр"],
     "Смотрите вкладку «Кино» — там все ближайшие кинотеатры."),
    (["музей", "театр", "галерея", "культур", "выставк"],
     "Культурный вечер — отличный выбор! Вкладка «Культура» к вашим услугам."),
    (["парк", "прогулк", "свежий", "природ"],
     "Для прогулки — откройте вкладку «Парки». Найдём ближайший зелёный уголок!"),
    (["маршрут", "программ", "вечер", "что делать", "куда пойти"],
     "Классический маршрут: кофейня → ужин → бар или парк. "
     "Включите фильтр «Рядом — до 1 км» и смотрите по вкладкам — всё будет рядом!"),
    (["дёшев", "дешев", "бюджет", "недорог", "бесплатн"],
     "Включите фильтр «Бюджетно» — покажем места с доступными ценами!"),
    (["рядом", "близко", "поблизости", "пешком"],
     "Включите фильтр «Рядом — до 1 км» — останутся только места в пешей доступности!"),
]


@app.post("/api/chat", response_model=ChatOut)
async def chat(body: ChatIn):
    q = body.message.lower()
    for keywords, reply in _CHAT_RULES:
        if any(kw in q for kw in keywords):
            return ChatOut(reply=reply)
    return ChatOut(
        reply="Помогу найти интересные места рядом! Спросите про еду, кофе, бары, кино, парки — или просто попросите маршрут на вечер."
    )
