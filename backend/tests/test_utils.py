from unittest.mock import patch

from utils.categories import CATEGORY_QUERY
from services.places_service import _price_label, _photo_url


def test_category_query_keys():
    expected = {"all", "rest", "cafe", "bar", "cult", "cinema", "fun", "park"}
    assert set(CATEGORY_QUERY.keys()) == expected


def test_category_query_values_non_empty():
    for key, value in CATEGORY_QUERY.items():
        assert isinstance(value, dict)
        assert "type" in value
        assert "keyword" in value
        assert "max_pages" in value
        assert value["max_pages"] >= 1


def test_category_all_no_restrictions():
    q = CATEGORY_QUERY["all"]
    assert q["type"] == "restaurant"
    assert q["keyword"] is None
    assert q["max_pages"] == 2


def test_category_rest_uses_type():
    q = CATEGORY_QUERY["rest"]
    assert q["type"] == "restaurant"
    assert q["max_pages"] == 2


def test_category_cafe_uses_type():
    q = CATEGORY_QUERY["cafe"]
    assert q["type"] == "cafe"


def test_category_cult_uses_keyword():
    q = CATEGORY_QUERY["cult"]
    assert q["keyword"] == "museum theater gallery"
    assert q["type"] is None


def test_category_max_pages_default():
    for key in ("cult", "cinema", "fun", "park"):
        assert CATEGORY_QUERY[key]["max_pages"] == 1


def test_price_label_levels():
    assert _price_label(0) == ""
    assert _price_label(1) == "$"
    assert _price_label(2) == "$$"
    assert _price_label(3) == "$$$"
    assert _price_label(4) == "$$$$"


def test_price_label_none():
    assert _price_label(None) is None


def test_price_label_negative():
    assert _price_label(-1) is None


def test_price_label_over_max():
    assert _price_label(5) == "$$$$"


@patch("services.places_service.GOOGLE_MAPS_API_KEY", "test_key")
def test_photo_url_with_reference():
    url = _photo_url("abc123", max_width=400)
    assert url is not None
    assert "maxwidth=400" in url
    assert "photo_reference=abc123" in url


def test_photo_url_none_reference():
    assert _photo_url(None) is None


@patch("services.places_service.GOOGLE_MAPS_API_KEY", "test_key")
def test_photo_url_default_maxwidth():
    url = _photo_url("ref456")
    assert url is not None
    assert "maxwidth=1200" in url
