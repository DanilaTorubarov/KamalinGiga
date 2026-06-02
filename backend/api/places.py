from fastapi import APIRouter, HTTPException, Query
from services.geocode_service import geocode_address
from services.places_service import convert_dgis_place
from clients.dgis_api import dgis_search
from utils.categories import CATEGORY_QUERY

router = APIRouter(prefix="/api")

@router.get("/places")
async def api_places(lat: float | None = None,
                     lng: float | None = None,
                     address: str | None = None,
                     category: str = "all",
                     limit: int = Query(50, ge=1, le=100)):

    if lat is None or lng is None:
        if not address:
            raise HTTPException(422, "Нужен lat+lng или address")
        lat, lng = await geocode_address(address)

    query = CATEGORY_QUERY.get(category, "еда")
    raw_items = await dgis_search(lat, lng, query)

    places = [p for item in raw_items if (p := convert_dgis_place(item, lat, lng))]
    places.sort(key=lambda x: x["distance_m"])

    return {"total": len(places), "places": places[:limit]}
