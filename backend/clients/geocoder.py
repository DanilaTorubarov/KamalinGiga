import httpx

from core.config import GOOGLE_MAPS_API_KEY



async def geocoder_request(address: str) -> httpx.Response:
    async with httpx.AsyncClient() as client:
        r = await client.get(
            "https://maps.googleapis.com/maps/api/geocode/json",
            params= {
                "address": address,
                "language": "ru",
                "region": "ru",
                "key": GOOGLE_MAPS_API_KEY
            }
        )
    return r