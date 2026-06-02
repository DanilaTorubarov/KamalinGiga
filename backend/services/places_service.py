from clients.places import google_nearby_search
from core.config import GOOGLE_MAPS_API_KEY
from utils.haversine import haversine

def _photo_url(photo_reference: str | None, max_width: int = 1200) -> str | None:
    if not photo_reference or not GOOGLE_MAPS_API_KEY:
        return None
    return (
        "https://maps.googleapis.com/maps/api/place/photo"
        f"?maxwidth={max_width}&photo_reference={photo_reference}&key={GOOGLE_MAPS_API_KEY}"
    )


def _price_label(level: int | None) -> str | None:
    if level is None:
        return None
    if level < 0:
        return None
    return "$" * min(level, 4)


def convert_google_place(item, user_lat, user_lng):
    location = (item.get("geometry") or {}).get("location") or {}
    lat = location.get("lat")
    lng = location.get("lng")
    if lat is None or lng is None:
        return None

    dist = haversine(user_lat, user_lng, lat, lng)
    photo_ref = None
    photos = item.get("photos") or []
    if photos:
        photo_ref = photos[0].get("photo_reference")

    types = item.get("types") or []
    category = types[0] if types else None

    return {
        "id": item.get("place_id"),
        "name": item.get("name"),
        "address": item.get("vicinity") or item.get("formatted_address"),
        "lat": lat,
        "lng": lng,
        "distance_m": dist,
        "distance_label": f"{dist} м" if dist < 1000 else f"{dist/1000:.1f} км",
        "rating": item.get("rating"),
        "price": _price_label(item.get("price_level")),
        "is_open": (item.get("opening_hours") or {}).get("open_now"),
        "category": category,
        "image_url": _photo_url(photo_ref),
    }
