import math
import os
import datetime
from typing import Literal

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Secrets — env vars first, keyring as local-dev fallback
# ---------------------------------------------------------------------------
try:
    import keyring as _kr

    def _get(name: str) -> str | None:
        v = os.environ.get(name)
        if v:
            return v
        try:
            return _kr.get_password("KamalinGiga", name)
        except Exception:
            return None

except ImportError:
    def _get(name: str) -> str | None:
        return os.environ.get(name)


YANDEX_SEARCH_KEY: str | None = _get("YANDEX_API_KEY")
YANDEX_GPT_KEY:    str | None = _get("YANDEX_GPT_KEY")
YANDEX_FOLDER_ID:  str | None = _get("YANDEX_FOLDER_ID")

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
# In-memory saved places (no auth — process-local)
# ---------------------------------------------------------------------------
_saved: set[str] = set()

# ---------------------------------------------------------------------------
# Category config
# ---------------------------------------------------------------------------
CATEGORY_TEXTS: dict[str, str] = {
    "all":    "кафе ресторан бар развлечения",
    "rest":   "ресторан",
    "cafe":   "кофейня кафе",
    "bar":    "бар",
    "cult":   "музей театр галерея",
    "cinema": "кинотеатр",
    "fun":    "развлечения боулинг квест",
    "park":   "парк",
}

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

# Yandex rubric `class` → our category_id
RUBRIC_TO_CAT: dict[str, str] = {
    "restaurant":     "rest",
    "cafe":           "cafe",
    "coffee_house":   "cafe",
    "bar":            "bar",
    "pub":            "bar",
    "night_club":     "bar",
    "museum":         "cult",
    "theatre":        "cult",
    "art_gallery":    "cult",
    "concert_hall":   "cult",
    "cinema":         "cinema",
    "bowling":        "fun",
    "billiards":      "fun",
    "amusement_park": "fun",
    "entertainment":  "fun",
    "park":           "park",
    "garden":         "park",
    "square":         "park",
}

PRICE_FILTERS = {"Free", "₽", "₽₽"}

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


def is_open_now(hours_data: dict | None) -> bool | None:
    """Parse Yandex CompanyMetaData.Hours → open / closed / unknown."""
    if not hours_data:
        return None
    avail = hours_data.get("Availability", {})
    if avail.get("TwentyFourHours"):
        return True

    now = datetime.datetime.now()
    day_keys = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    today_key = day_keys[now.weekday()]
    now_min = now.hour * 60 + now.minute

    for interval in avail.get("Intervals", []):
        if not (interval.get(today_key) or avail.get("Everyday")):
            continue
        try:
            fh, fm = map(int, interval["from"].split(":"))
            to_str = interval.get("to", "24:00")
            if to_str == "24:00":
                th, tm = 23, 59
            else:
                th, tm = map(int, to_str.split(":"))
            if fh * 60 + fm <= now_min <= th * 60 + tm:
                return True
        except (KeyError, ValueError, TypeError):
            continue
    return False


def _category_id_from_rubrics(categories: list) -> str:
    for cat in categories:
        cls = cat.get("class", "")
        if cls in RUBRIC_TO_CAT:
            return RUBRIC_TO_CAT[cls]
    return "fun"


def feature_to_place(feature: dict, user_lat: float, user_lng: float) -> dict:
    """Convert a Yandex Search API feature into a Place dict."""
    props  = feature.get("properties", {})
    meta   = props.get("CompanyMetaData", {})
    coords = feature["geometry"]["coordinates"]  # [lng, lat]

    place_id = str(meta.get("id") or abs(hash(meta.get("name", ""))))
    name     = meta.get("name") or props.get("name", "")
    address  = meta.get("address") or props.get("description", "")

    cats           = meta.get("Categories", [])
    category_id    = _category_id_from_rubrics(cats)
    category_label = cats[0].get("name", "Место") if cats else "Место"

    rating: float | None = None
    rating_data = meta.get("Ratings") or meta.get("rating")
    if isinstance(rating_data, dict):
        rating = rating_data.get("score")

    place_lng, place_lat = float(coords[0]), float(coords[1])
    distance_m = haversine(user_lat, user_lng, place_lat, place_lng)
    if distance_m < 1000:
        dist_label = f"{distance_m} м"
    else:
        dist_label = f"{distance_m / 1000:.1f} км"

    return {
        "id":             place_id,
        "name":           name,
        "category":       category_label,
        "category_id":    category_id,
        "rating":         rating,
        "price":          None,   # Yandex Search API doesn't expose price level
        "distance_m":     distance_m,
        "distance_label": dist_label,
        "image_url":      None,
        "is_open":        is_open_now(meta.get("Hours")),
        "saved":          place_id in _saved,
        "tags":           [],
        "address":        address,
        "lat":            place_lat,
        "lng":            place_lng,
    }


async def _geocode_address(address: str) -> tuple[float, float]:
    """address string → (lat, lng) via Yandex Geocoder."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(
            "https://geocode-maps.yandex.ru/1.x/",
            params={
                "apikey":  YANDEX_SEARCH_KEY,
                "geocode": address,
                "format":  "json",
                "results": 1,
                "lang":    "ru_RU",
            },
        )
    if r.status_code != 200:
        raise HTTPException(422, f"Yandex Geocoder вернул {r.status_code}")
    members = (
        r.json()
        .get("response", {})
        .get("GeoObjectCollection", {})
        .get("featureMember", [])
    )
    if not members:
        raise HTTPException(422, "Адрес не найден")
    lng_s, lat_s = members[0]["GeoObject"]["Point"]["pos"].split()
    return float(lat_s), float(lng_s)


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
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(
            "https://geocode-maps.yandex.ru/1.x/",
            params={
                "apikey":  YANDEX_SEARCH_KEY,
                "geocode": body.address,
                "format":  "json",
                "results": 1,
                "lang":    "ru_RU",
            },
        )
    if r.status_code != 200:
        raise HTTPException(422, f"Yandex Geocoder вернул {r.status_code}")

    members = (
        r.json()
        .get("response", {})
        .get("GeoObjectCollection", {})
        .get("featureMember", [])
    )
    if not members:
        raise HTTPException(422, "Адрес не найден")

    geo    = members[0]["GeoObject"]
    lng_s, lat_s = geo["Point"]["pos"].split()
    label  = (
        geo.get("metaDataProperty", {})
           .get("GeocoderMetaData", {})
           .get("text")
    )
    return GeocodeOut(lat=float(lat_s), lng=float(lng_s), label=label)


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
    # Resolve coordinates when only address is given
    if lat is None or lng is None:
        if not address:
            raise HTTPException(422, "Нужен lat+lng или address")
        lat, lng = await _geocode_address(address)

    search_text = q or CATEGORY_TEXTS.get(category, CATEGORY_TEXTS["all"])

    async with httpx.AsyncClient(timeout=20.0) as client:
        sr = await client.get(
            "https://search-maps.yandex.ru/v1/",
            params={
                "apikey":  YANDEX_SEARCH_KEY,
                "text":    search_text,
                "ll":      f"{lng},{lat}",
                "spn":     "0.15,0.15",
                "type":    "biz",
                "results": 500,
                "lang":    "ru_RU",
            },
        )
    if sr.status_code != 200:
        raise HTTPException(502, f"Yandex Search API error: {sr.status_code}")

    features   = sr.json().get("features", [])
    all_places = [feature_to_place(f, lat, lng) for f in features]

    # ── Non-category filters (also used for tab-strip counts) ───────────────
    active  = set(filters.split(",")) if filters else set()
    trimmed = list(all_places)

    if "open" in active:
        trimmed = [p for p in trimmed if p["is_open"] is True]
    if "walk" in active:
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
# 5. POST /api/chat
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
    if not YANDEX_GPT_KEY or not YANDEX_FOLDER_ID:
        return ChatOut(
            reply=(
                "Чат-ассистент не настроен. "
                "Задайте переменные окружения YANDEX_GPT_KEY и YANDEX_FOLDER_ID."
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

    messages = [{"role": "system", "text": " ".join(system_parts)}]
    for m in body.history:
        messages.append({"role": m.role, "text": m.content})
    messages.append({"role": "user", "text": body.message})

    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(
            "https://llm.api.cloud.yandex.net/foundationModels/v1/completion",
            headers={"Authorization": f"Api-Key {YANDEX_GPT_KEY}"},
            json={
                "modelUri": f"gpt://{YANDEX_FOLDER_ID}/yandexgpt-lite",
                "completionOptions": {
                    "stream":      False,
                    "temperature": 0.6,
                    "maxTokens":   "800",
                },
                "messages": messages,
            },
        )
    if r.status_code != 200:
        raise HTTPException(502, f"YandexGPT error: {r.text[:300]}")

    reply = r.json()["result"]["alternatives"][0]["message"]["text"]
    return ChatOut(reply=reply)
