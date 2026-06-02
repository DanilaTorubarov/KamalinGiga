from pydantic import BaseModel

class GeocodeIn(BaseModel):
    address: str

class GeocodeOut(BaseModel):
    lat: float
    lng: float
