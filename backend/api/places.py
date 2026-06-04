from fastapi import APIRouter, HTTPException, Query
from services.geocode_service import geocode_address
from services.places_service import convert_google_place
from clients.places import google_nearby_search
from utils.categories import CATEGORY_QUERY

router = APIRouter(prefix="/api")


def _validate_coords(lat: float, lng: float) -> None:
    if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
        raise HTTPException(422, "Некорректные координаты")


@router.get("/places")
async def api_places(lat: float | None = None,
                     lng: float | None = None,
                     address: str | None = None,
                     category: str = "all",
                     radius: int = 5000,
                     limit: int = Query(50, ge=1, le=100)):

    if lat is None or lng is None:
        if not address:
            raise HTTPException(422, "Нужен lat+lng или address")
        lat, lng = await geocode_address(address)

    _validate_coords(lat, lng)

    query = CATEGORY_QUERY.get(category, {"type": "restaurant", "keyword": None, "max_pages": 1})
    raw_items = await google_nearby_search(
        lat, lng,
        keyword=query["keyword"],
        place_type=query["type"],
        radius=radius,
        max_pages=query.get("max_pages", 1),
    )

    places = [p for item in raw_items if (p := convert_google_place(item, lat, lng))]
    places.sort(key=lambda x: x["distance_m"])

    return {"total": len(places), "places": places[:limit]}
