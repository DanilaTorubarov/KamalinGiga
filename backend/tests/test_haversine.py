from utils.haversine import haversine


def test_zero_distance():
    assert haversine(55.75, 37.62, 55.75, 37.62) == 0


def test_known_distance_moscow():
    # Красная площадь (~55.7539, 37.6208) → Тверская 10 (~55.7608, 37.6188) ~780 м
    dist = haversine(55.7539, 37.6208, 55.7608, 37.6188)
    assert 700 < dist < 900


def test_long_distance():
    # Москва (~55.75, 37.62) → Санкт-Петербург (~59.93, 30.32) ~630 км
    dist = haversine(55.75, 37.62, 59.93, 30.32)
    assert 600_000 < dist < 700_000


def test_antipodal():
    # Противоположные точки на Земле — ~20 000 км (половина окружности)
    dist = haversine(0, 0, 0, 180)
    assert 19_900_000 < dist < 20_100_000


def test_negative_coords():
    # Нью-Йорк (40.71, -74.01) → Лондон (51.51, -0.13) ~5 570 км
    dist = haversine(40.71, -74.01, 51.51, -0.13)
    assert 5_500_000 < dist < 5_700_000


def test_returns_int():
    result = haversine(55.75, 37.62, 55.76, 37.63)
    assert isinstance(result, int)
