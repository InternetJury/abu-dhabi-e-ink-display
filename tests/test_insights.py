from ribbon.fixtures import load_fixture_snapshot


def test_weekday_fixture_contains_next_bus_hero_and_density():
    snapshot = load_fixture_snapshot("weekday_commute_now")
    assert snapshot.primary_stop is not None
    assert snapshot.primary_stop.hero is not None
    assert snapshot.primary_stop.hero.route_number == "24"
    assert snapshot.primary_stop.density_window is not None
    assert snapshot.primary_stop.density_window.bins == [2, 1, 1, 0]


def test_degraded_fixture_keeps_city_summary():
    snapshot = load_fixture_snapshot("degraded_bus_data")
    assert snapshot.primary_stop is not None
    assert snapshot.primary_stop.hero is None
    assert snapshot.city_summary is not None
    assert "quiet or unavailable" in snapshot.city_summary.summary_line.lower()

