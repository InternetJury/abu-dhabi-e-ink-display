from datetime import timedelta

from ribbon.fixtures import load_fixture_snapshot
from ribbon.preview import snapshot_with_uniform_delay


def test_uniform_delay_preview_does_not_mutate_canonical_weekday_fixture():
    snapshot = load_fixture_snapshot("weekday_commute_now")
    original_due = snapshot.primary_stop.departures[0].due_minutes

    preview = snapshot_with_uniform_delay(snapshot, delay_minutes=4)

    assert snapshot.primary_stop.departures[0].due_minutes == original_due
    assert preview.primary_stop.departures[0].due_minutes == original_due + 4
    assert preview.primary_stop.departures[0].delay_minutes == 4
    assert preview.primary_stop.departures[0].expected_at == snapshot.primary_stop.departures[0].scheduled_at + timedelta(minutes=4)
    assert preview.primary_stop.hero.irregularity_flag == "Delay +4m"
    assert preview.primary_stop.hero.due_label == "08 min"


def test_uniform_delay_preview_updates_weekend_departures_without_changing_stop_order():
    snapshot = load_fixture_snapshot("weekend_multi_stop")
    preview = snapshot_with_uniform_delay(snapshot, delay_minutes=4)

    assert [stop.stop_id for stop in preview.multi_stop.stops] == [stop.stop_id for stop in snapshot.multi_stop.stops]
    assert preview.multi_stop.stops[0].departures[0].due_minutes == snapshot.multi_stop.stops[0].departures[0].due_minutes + 4
    assert preview.multi_stop.stops[0].departures[0].expected_at == snapshot.multi_stop.stops[0].departures[0].scheduled_at + timedelta(minutes=4)
    assert all(departure.delay_minutes == 4 for stop in preview.multi_stop.stops for departure in stop.departures)
