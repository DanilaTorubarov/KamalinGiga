import asyncio

import httpx
from fastapi import HTTPException

from core.config import GOOGLE_MAPS_API_KEY


async def google_nearby_search(lat, lng, keyword=None, place_type=None, radius=5000, language="ru", max_pages=1):
    api_key = GOOGLE_MAPS_API_KEY
    url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"

    seen_ids = set()
    all_results = []
    next_page_token = None

    for page in range(max_pages):
        if next_page_token:
            await asyncio.sleep(2)
            params = {"key": api_key, "pagetoken": next_page_token}
        else:
            params = {
                "location": f"{lat},{lng}",
                "radius": radius,
                "language": language,
                "key": api_key,
            }
            if keyword:
                params["keyword"] = keyword
            if place_type:
                params["type"] = place_type

        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(url, params=params)

        if r.status_code != 200:
            raise HTTPException(502, f"Google Places error {r.status_code}")

        data = r.json()
        status = data.get("status")
        if status not in ("OK", "ZERO_RESULTS"):
            message = data.get("error_message") or status or "Unknown error"
            raise HTTPException(502, f"Google Places error: {message}")

        for item in data.get("results", []):
            pid = item.get("place_id")
            if pid and pid not in seen_ids:
                seen_ids.add(pid)
                all_results.append(item)

        next_page_token = data.get("next_page_token")
        if not next_page_token:
            break

    return all_results
