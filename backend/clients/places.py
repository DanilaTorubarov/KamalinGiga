import httpx
from fastapi import HTTPException

from core.config import GOOGLE_MAPS_API_KEY




async def google_nearby_search(lat, lng, keyword, radius=5000, language="ru"):
    api_key = GOOGLE_MAPS_API_KEY
    url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
    params = {
        "location": f"{lat},{lng}",
        "radius": radius,
        "keyword": keyword,
        "language": language,
        "key": api_key,
    }

    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(url, params=params)

    print(r.status_code)
    print(r.json())
    if r.status_code != 200:
        raise HTTPException(502, f"Google Places error {r.status_code}")

    data = r.json()
    status = data.get("status")
    if status not in ("OK", "ZERO_RESULTS"):
        message = data.get("error_message") or status or "Unknown error"
        raise HTTPException(502, f"Google Places error: {message}")

    return data.get("results", [])
