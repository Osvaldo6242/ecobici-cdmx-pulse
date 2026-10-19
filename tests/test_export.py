from pulse import export_web


def test_representative_day_is_a_working_wednesday(mini_warehouse):
    day = export_web.representative_day(mini_warehouse)
    assert mini_warehouse.execute(f"SELECT isodow(DATE '{day}')").fetchone()[0] == 3


def test_trip_animation_payload(mini_warehouse):
    day = export_web.representative_day(mini_warehouse)
    payload = export_web.trips_animation(mini_warehouse, day, n=50)
    k = len(payload["fields"])
    assert payload["sampled"] <= 50
    assert len(payload["data"]) == payload["sampled"] * k
    rows = [payload["data"][i:i + k] for i in range(0, len(payload["data"]), k)]
    assert all(r[5] > r[4] for r in rows)                              # ends after it starts
    assert all(-100 < r[0] < -98 and 19 < r[1] < 20 for r in rows)     # inside CDMX
    assert [r[4] for r in rows] == sorted(r[4] for r in rows)          # sorted for animation
