import numpy as np
import pandas as pd

from pulse import anomalies, forecast, riders, stations, warehouse


def test_lag_features_do_not_leak(mini_warehouse):
    df = forecast.build_features(warehouse.table(mini_warehouse, "mart_hourly"))
    i = 200
    assert df.loc[i, "lag_24"] == df.loc[i - 24, "trips"]
    assert df.loc[i, "lag_168"] == df.loc[i - 168, "trips"]


def test_robust_z_flags_outlier():
    s = pd.Series([100, 102, 98, 101, 99, 100, 40])
    z = anomalies.robust_z(s)
    assert z.iloc[-1] < -3 and z.iloc[:-1].abs().max() < 3


def test_clustering_separates_homes_and_offices(mini_warehouse):
    res = stations.cluster_stations(warehouse.table(mini_warehouse, "mart_station_profile"),
                                    k_range=range(2, 4))
    a = res["assignments"].set_index("station_code")["cluster"]
    assert a["001"] == a["002"]
    assert a["003"] == a["004"]
    assert a["001"] != a["003"]


def test_cluster_naming_rules():
    hours = range(24)
    office = pd.Series({**{f"dep_{h}": 0.01 for h in hours}, **{f"arr_{h}": 0.01 for h in hours}})
    office[[f"arr_{h}" for h in (7, 8, 9)]] = 0.2
    office[[f"dep_{h}" for h in (17, 18, 19)]] = 0.2
    assert stations._name_cluster(office) == "Destino laboral"


def test_network_finds_communities(mini_warehouse):
    nw = stations.network(warehouse.table(mini_warehouse, "mart_od"), min_trips=1)
    assert nw["n_communities"] >= 1
    assert np.isclose(nw["nodes"]["pagerank"].sum(), 1.0)


def test_small_demographic_cells_are_suppressed():
    df = pd.DataFrame({"gender": ["F", "M"], "age_band": ["16-24", "16-24"], "trips": [50, 500]})
    out = riders.suppress_small_cells(df, k=100)
    assert len(out) == 1 and out.iloc[0]["trips"] == 500
