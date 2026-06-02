import httpx
from fastapi import HTTPException

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
