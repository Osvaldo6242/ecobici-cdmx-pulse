def q(con, sql):
    return con.execute(sql).fetchall()


def test_dirty_rows_are_classified(mini_warehouse):
    dq = dict(q(mini_warehouse, "SELECT validity, trips FROM dq_summary"))
    assert dq["too_short"] == 1
    assert dq["unknown_station"] == 1
    assert dq["unparseable_timestamp"] == 1
    assert dq["valid"] > 1000


def test_only_valid_trips_reach_intermediate(mini_warehouse):
    bad = q(mini_warehouse, """SELECT count(*) FROM int_trips
                               WHERE duration_min < 1 OR start_station = '999'""")[0][0]
    assert bad == 0


def test_double_station_codes_join(mini_warehouse):
    n = q(mini_warehouse, "SELECT count(*) FROM int_trips WHERE end_station = '271-272'")[0][0]
    assert n > 0


def test_hourly_mart_has_every_hour(mini_warehouse):
    n, zero_hours = q(mini_warehouse, "SELECT count(*), count(*) FILTER (WHERE trips = 0) FROM mart_hourly")[0]
    assert n == 21 * 24
    assert zero_hours > 0          # night hours are gap-filled with zeros, not dropped


def test_haversine_distance_is_sane(mini_warehouse):
    km = q(mini_warehouse, """SELECT distance_km FROM int_station_pairs
                              WHERE start_station = '001' AND end_station = '003'""")[0][0]
    assert 3 < km < 6               # ~4.5 km between the two synthetic points


def test_rebalancing_cumulates_net_flow(mini_warehouse):
    rows = q(mini_warehouse, """SELECT hour_of_day, net_flow, cumulative_net FROM mart_rebalancing
                                WHERE station_code = '001' ORDER BY hour_of_day""")
    running = 0
    for _, net, cum in rows:
        running += net
        assert abs(running - cum) < 1e-9
    # Homes empty out in the morning.
    assert min(c for _, _, c in rows) < 0
