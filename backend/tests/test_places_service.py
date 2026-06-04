from unittest.mock import patch

from services.places_service import convert_google_place


USER_LAT = 55.7539
USER_LNG = 37.6208


def _google_item(**overrides):
    base = {
        "place_id": "ChIJ123",
        "name": "Кафе Пушкин",
        "vicinity": "Тверской бульвар, 26а",
        "geometry": {"location": {"lat": 55.752, "lng": 37.619}},
        "rating": 4.5,
        "price_level": 2,
        "opening_hours": {"open_now": True},
        "types": ["cafe", "food", "establishment"],
        "photos": [{"photo_reference": "photo_ref_abc"}],
    }
    base.update(overrides)
    return base


@patch("services.places_service.GOOGLE_MAPS_API_KEY", "test_key")
def test_convert_full_item():
    p = convert_google_place(_google_item(), USER_LAT, USER_LNG)
    assert p is not None
    assert p["id"] == "ChIJ123"
    assert p["name"] == "Кафе Пушкин"
    assert p["address"] == "Тверской бульвар, 26а"
    assert p["rating"] == 4.5
    assert p["price"] == "$$"
    assert p["is_open"] is True
    assert p["category"] == "cafe"
    assert p["distance_m"] > 0
    assert "м" in p["distance_label"]
    assert p["image_url"] is not None


def test_convert_no_location_returns_none():
    item = _google_item(geometry={"location": {}})
    assert convert_google_place(item, USER_LAT, USER_LNG) is None


def test_convert_no_geometry_returns_none():
    item = _google_item(geometry=None)
    assert convert_google_place(item, USER_LAT, USER_LNG) is None


def test_convert_partial_lat_only():
    item = _google_item(geometry={"location": {"lat": 55.75}})
    assert convert_google_place(item, USER_LAT, USER_LNG) is None


def test_convert_no_photos():
    item = _google_item(photos=[])
    p = convert_google_place(item, USER_LAT, USER_LNG)
    assert p is not None
    assert p["image_url"] is None


def test_convert_no_photos_key():
    p = convert_google_place(_google_item(photos=None), USER_LAT, USER_LNG)
    assert p is not None
    assert p["image_url"] is None


def test_convert_no_rating():
    p = convert_google_place(_google_item(rating=None), USER_LAT, USER_LNG)
    assert p is not None
    assert p["rating"] is None


def test_convert_no_price_level():
    p = convert_google_place(_google_item(price_level=None), USER_LAT, USER_LNG)
    assert p is not None
    assert p["price"] is None


def test_convert_no_opening_hours():
    p = convert_google_place(_google_item(opening_hours=None), USER_LAT, USER_LNG)
    assert p is not None
    assert p["is_open"] is None


def test_convert_no_types():
    p = convert_google_place(_google_item(types=[]), USER_LAT, USER_LNG)
    assert p is not None
    assert p["category"] is None


def test_convert_no_types_key():
    p = convert_google_place(_google_item(types=None), USER_LAT, USER_LNG)
    assert p is not None
    assert p["category"] is None


def test_convert_formatted_address_fallback():
    item = _google_item(vicinity=None, formatted_address="Москва, Тверская 1")
    p = convert_google_place(item, USER_LAT, USER_LNG)
    assert p is not None
    assert p["address"] == "Москва, Тверская 1"


def test_distance_label_meters():
    # <1000 м — метры
    p = convert_google_place(
        _google_item(geometry={"location": {"lat": USER_LAT + 0.001, "lng": USER_LNG}}),
        USER_LAT, USER_LNG
    )
    assert p is not None
    assert " м" in p["distance_label"]


def test_distance_label_kilometers():
    # >1000 м — километры
    p = convert_google_place(
        _google_item(geometry={"location": {"lat": USER_LAT + 0.05, "lng": USER_LNG}}),
        USER_LAT, USER_LNG
    )
    assert p is not None
    assert " км" in p["distance_label"]
