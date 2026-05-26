from fastapi import FastAPI, Query
import httpx
import os
import keyring
from typing import List

app = FastAPI()

YANDEX_API_KEY = keyring.get_password("KamalinGiga", "YANDEX_API_KEY")

CATEGORIES = {
    "restaurant": "restaurant",
    "bar": "bar",
    "cafe": "cafe",
    "gym": "fitness",
    "pharmacy": "pharmacy",
    "supermarket": "supermarket",
    "hotel": "hotel",
    "cinema": "cinema",
    "bank": "bank",
    "beauty": "beauty_salon",
}

@app.get("/places")
async def get_places(
    category: str = Query(...),
    lat: float = Query(...),
    lon: float = Query(...),
    radius: int = 1000,
    limit: int = 10
):
    if category not in CATEGORIES:
        return {
            "error": "Unknown category",
            "available": list(CATEGORIES.keys())
        }

    url = "https://search-maps.yandex.ru/v1/"

    params = {
        "apikey": YANDEX_API_KEY,
        "text": CATEGORIES[category],
        "ll": f"{lon},{lat}",
        "spn": "0.02,0.02",
        "type": "biz",
        "results": limit,
        "lang": "ru_RU"
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params)

    # Проверяем статус
    if response.status_code != 200:
        return {
            "error": "Yandex API error",
            "status": response.status_code,
            "text": response.text[:500]  # покажем первые 500 символов
        }

    # Пробуем распарсить JSON
    try:
        data = response.json()
    except Exception:
        return {
            "error": "Invalid JSON from Yandex",
            "raw": response.text[:500]
        }

    results = []
    for feature in data.get("features", []):
        props = feature["properties"]
        coords = feature["geometry"]["coordinates"]

        results.append({
            "name": props.get("name"),
            "address": props.get("description"),
            "lat": coords[1],
            "lon": coords[0],
            "category": category,
        })

    return {"count": len(results), "results": results}
