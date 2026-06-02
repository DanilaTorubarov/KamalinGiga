from clients.dgis_api import dgis_search
from utils.haversine import haversine

def convert_dgis_place(item, user_lat, user_lng):
    point = item.get("point", {})
    lat = point.get("lat")
    lon = point.get("lon")
    if lat is None or lon is None:
        return None

    dist = haversine(user_lat, user_lng, lat, lon)

    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "address": item.get("address_name"),
        "lat": lat,
        "lng": lon,
        "distance_m": dist,
        "distance_label": f"{dist} м" if dist < 1000 else f"{dist/1000:.1f} км",
    }
