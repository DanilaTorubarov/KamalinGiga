import httpx
from fastapi import HTTPException
from clients.geocoder import geocoder_request


def _parse_geocode_response(data) -> tuple[float, float]:
    if not isinstance(data, dict):
        raise HTTPException(422, "Ошибка геокодера")

    status = data.get("status")
    if status != "OK":
        raise HTTPException(422, "Адрес не найден")

    results = data.get("results") or []
    if not results:
        raise HTTPException(422, "Адрес не найден")

    location = (results[0].get("geometry") or {}).get("location") or {}
    if "lat" not in location or "lng" not in location:
        raise HTTPException(422, "Ошибка геокодера")

    return float(location["lat"]), float(location["lng"])


async def geocode_address(address: str) -> tuple[float, float]:
    r = await geocoder_request(address)
    if r.status_code != 200:
        raise HTTPException(422, "Ошибка геокодера")

    data = r.json()
    return _parse_geocode_response(data)
