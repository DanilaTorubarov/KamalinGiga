import httpx
from fastapi import HTTPException

from core.config import GOOGLE_MAPS_API_KEY



async def google_autocomplete(input_text: str, lat: float | None = None, lng: float | None = None, radius: int = 5000):
    url = "https://places.googleapis.com/v1/places:autocomplete"

    payload = {
        "input": input_text,
        "languageCode": "ru",
    }

    # Если есть координаты — добавляем bias (проверяем валидность)
    if lat is not None and lng is not None and -90 <= lat <= 90 and -180 <= lng <= 180:
        payload["locationBias"] = {
            "circle": {
                "center": {"latitude": lat, "longitude": lng},
                "radius": radius
            }
        }

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_MAPS_API_KEY,
        "X-Goog-FieldMask": "suggestions.placePrediction.placeId,suggestions.placePrediction.text"
    }

    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(url, json=payload, headers=headers)

    if r.status_code != 200:
        print(r.text)
        raise HTTPException(502, f"Google Autocomplete error {r.status_code}")

    data = r.json()
    return data.get("suggestions", [])
