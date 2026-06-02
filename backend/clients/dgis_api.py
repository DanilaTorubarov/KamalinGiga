import httpx
from fastapi import HTTPException
from core.config import DGIS_API_KEY

async def dgis_search(lat, lng, query, radius=5000):
    url = "https://catalog.api.2gis.com/3.0/items"
    params = {
        "key": DGIS_API_KEY,
        "q": query,
        "point": f"{lng},{lat}",
        "radius": radius,
        "sort": "distance",
        "fields": "items.point",
    }

    async with httpx.AsyncClient() as client:
        r = await client.get(url, params=params)

    if r.status_code != 200:
        raise HTTPException(502, f"2GIS error {r.status_code}")

    return r.json().get("result", {}).get("items", [])
