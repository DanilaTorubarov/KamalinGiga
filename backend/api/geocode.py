from fastapi import APIRouter
from models.geocode import GeocodeIn, GeocodeOut
from services.geocode_service import geocode_address

router = APIRouter(prefix="/api")

@router.post("/geocode", response_model=GeocodeOut)
async def api_geocode(body: GeocodeIn):
    lat, lng = await geocode_address(body.address)
    return GeocodeOut(lat=lat, lng=lng)
