import pytest
from fastapi import HTTPException

from services.geocode_service import _parse_geocode_response


def test_parse_success():
    data = {
        "status": "OK",
        "results": [{
            "geometry": {"location": {"lat": 55.75, "lng": 37.62}},
        }],
    }
    lat, lng = _parse_geocode_response(data)
    assert lat == 55.75
    assert lng == 37.62


def test_parse_not_dict():
    with pytest.raises(HTTPException) as exc:
        _parse_geocode_response("not a dict")
    assert exc.value.status_code == 422
    assert "Ошибка геокодера" in exc.value.detail


def test_parse_status_not_ok():
    data = {"status": "ZERO_RESULTS", "results": []}
    with pytest.raises(HTTPException) as exc:
        _parse_geocode_response(data)
    assert exc.value.status_code == 422
    assert "Адрес не найден" in exc.value.detail


def test_parse_no_results():
    data = {"status": "OK", "results": []}
    with pytest.raises(HTTPException) as exc:
        _parse_geocode_response(data)
    assert exc.value.status_code == 422
    assert "Адрес не найден" in exc.value.detail


def test_parse_results_none():
    data = {"status": "OK", "results": None}
    with pytest.raises(HTTPException) as exc:
        _parse_geocode_response(data)
    assert exc.value.status_code == 422
    assert "Адрес не найден" in exc.value.detail


def test_parse_no_geometry():
    data = {
        "status": "OK",
        "results": [{"geometry": None}],
    }
    with pytest.raises(HTTPException) as exc:
        _parse_geocode_response(data)
    assert exc.value.status_code == 422
    assert "Ошибка геокодера" in exc.value.detail


def test_parse_no_location():
    data = {
        "status": "OK",
        "results": [{"geometry": {"location": None}}],
    }
    with pytest.raises(HTTPException) as exc:
        _parse_geocode_response(data)
    assert exc.value.status_code == 422
    assert "Ошибка геокодера" in exc.value.detail


def test_parse_missing_lat():
    data = {
        "status": "OK",
        "results": [{"geometry": {"location": {"lng": 37.62}}}],
    }
    with pytest.raises(HTTPException) as exc:
        _parse_geocode_response(data)
    assert exc.value.status_code == 422
    assert "Ошибка геокодера" in exc.value.detail


def test_parse_missing_lng():
    data = {
        "status": "OK",
        "results": [{"geometry": {"location": {"lat": 55.75}}}],
    }
    with pytest.raises(HTTPException) as exc:
        _parse_geocode_response(data)
    assert exc.value.status_code == 422
    assert "Ошибка геокодера" in exc.value.detail


def test_parse_empty_results_list():
    data = {"status": "OK", "results": [{}]}
    with pytest.raises(HTTPException) as exc:
        _parse_geocode_response(data)
    assert exc.value.status_code == 422
    assert "Ошибка геокодера" in exc.value.detail
