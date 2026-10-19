"""Export compact JSON files consumed by the interactive website in /docs."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from . import config

log = logging.getLogger(__name__)


def _r(x, nd=1):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), nd)


def _write(name: str, obj) -> Path:
    config.SITE_DATA.mkdir(parents=True, exist_ok=True)
    path = config.SITE_DATA / f"{name}.json"
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")))
    log.info("site data %-14s %7.1f KB", name, path.stat().st_size / 1024)
    return path


def representative_day(con: duckdb.DuckDBPyConnection) -> str:
    """A non-holiday Wednesday, preferably dry, whose volume is closest to the median Wednesday."""
    return str(con.execute("""
        WITH w AS (SELECT * FROM mart_daily WHERE isodow(day) = 3 AND NOT is_non_working_day)
        SELECT day FROM w
        ORDER BY precip_mm >= 1, abs(trips - (SELECT median(trips) FROM w)) LIMIT 1
    """).fetchone()[0])


def trips_animation(con: duckdb.DuckDBPyConnection, day: str, n: int = 22000) -> dict:
    df = con.execute(f"""
        WITH day_trips AS (
            SELECT a.lon AS x0, a.lat AS y0, b.lon AS x1, b.lat AS y1,
                   epoch(t.started_at) - epoch(CAST(t.started_at AS DATE)) AS t0,
                   epoch(t.ended_at)   - epoch(CAST(t.started_at AS DATE)) AS t1,
                   CASE t.gender WHEN 'F' THEN 1 WHEN 'M' THEN 0 ELSE 2 END AS g
            FROM int_trips t
            JOIN stg_stations a ON a.station_code = t.start_station
            JOIN stg_stations b ON b.station_code = t.end_station
            WHERE t.trip_date = DATE '{day}' AND t.start_station <> t.end_station
        )
        SELECT * FROM day_trips
        USING SAMPLE reservoir({n} ROWS) REPEATABLE ({config.RANDOM_STATE})
    """).df().sort_values("t0")
    flat = []
    for r in df.itertuples(index=False):
        flat += [round(r.x0, 5), round(r.y0, 5), round(r.x1, 5), round(r.y1, 5),
                 int(r.t0), int(r.t1), int(r.g)]
    total = con.execute(f"SELECT count(*) FROM int_trips WHERE trip_date = DATE '{day}'").fetchone()[0]
    return {"day": day, "total_trips_that_day": int(total), "sampled": len(df),
            "fields": ["x0", "y0", "x1", "y1", "t0", "t1", "g"], "data": flat}


def export_all(con: duckdb.DuckDBPyConnection, ctx: dict) -> list[str]:
    paths = []
    stations = con.execute("SELECT * FROM stg_stations").df()
    st = (stations
          .merge(ctx["clusters"]["assignments"], on="station_code", how="left")
          .merge(ctx["network"]["nodes"], on="station_code", how="left")
          .merge(ctx["rebalancing"][["station_code", "risk", "risk_type", "hour_of_peak_deficit",
                                     "hour_of_peak_surplus"]], on="station_code", how="left"))
    prof = con.execute("""SELECT station_code, hour_of_day, avg_departures, avg_arrivals
                          FROM mart_station_profile WHERE NOT is_non_working_day
                          ORDER BY station_code, hour_of_day""").df()
    dep = prof.pivot(index="station_code", columns="hour_of_day", values="avg_departures")
    arr = prof.pivot(index="station_code", columns="hour_of_day", values="avg_arrivals")
    paths.append(_write("stations", [{
        "id": r.station_code, "n": r.name, "lon": round(r.lon, 5), "lat": round(r.lat, 5),
        "cap": int(r.capacity), "cl": None if pd.isna(r.cluster) else int(r.cluster),
        "pr": _r(r.pagerank * 1000, 3) if not pd.isna(r.pagerank) else None,
        "cm": None if pd.isna(r.community) else int(r.community),
        "risk": _r(r.risk, 2), "rt": r.risk_type if isinstance(r.risk_type, str) else None,
        "dep": [round(v, 2) for v in dep.loc[r.station_code]] if r.station_code in dep.index else [],
        "arr": [round(v, 2) for v in arr.loc[r.station_code]] if r.station_code in arr.index else [],
    } for r in st.itertuples(index=False)]))

    day = representative_day(con)
    paths.append(_write("trips", trips_animation(con, day)))

    coords = stations.set_index("station_code")[["lon", "lat"]]
    od = con.execute("""SELECT * FROM mart_od WHERE start_station <> end_station
                        ORDER BY trips DESC LIMIT 450""").df()
    comm = ctx["network"]["nodes"].set_index("station_code")["community"]
    paths.append(_write("flows", [{
        "s": [round(coords.at[r.start_station, "lon"], 5), round(coords.at[r.start_station, "lat"], 5)],
        "t": [round(coords.at[r.end_station, "lon"], 5), round(coords.at[r.end_station, "lat"], 5)],
        "v": _r(r.trips_per_day, 1), "km": _r(r.distance_km, 2),
        "cm": int(comm.get(r.start_station, -1)),
    } for r in od.itertuples(index=False)]))

    f = ctx["forecast"]["frame"]
    paths.append(_write("forecast", {
        "t": f["hour_ts"].dt.strftime("%Y-%m-%dT%H").tolist(),
        "actual": f["trips"].astype(int).tolist(),
        "pred": [round(v) for v in f["predicted"]],
        "base": [round(v) for v in f["baseline"]],
        "dry": [round(v) for v in f["predicted_no_rain"]],
        "rain": [round(v, 1) for v in f["precip_mm"].fillna(0)],
        "cv": ctx["forecast"]["cv"].round(3).to_dict("records"),
        "metrics": {k: round(v, 3) for k, v in ctx["forecast"]["metrics"].items()},
        "baseline_metrics": {k: round(v, 3) for k, v in ctx["forecast"]["baseline_metrics"].items()},
        "rain_effect": {k: round(v, 1) for k, v in ctx["forecast"]["rain_effect"].items()},
    }))

    d = ctx["anomalies"]
    paths.append(_write("daily", [{
        "d": str(r.day), "a": int(r.actual), "e": int(round(r.expected)), "p": _r(r.precip_mm),
        "z": _r(r.z, 2), "an": bool(r.is_anomaly), "x": r.explanation,
        "nw": bool(r.non_working),
    } for r in d.itertuples(index=False)]))

    hm = con.execute("""SELECT iso_dow, hour_of_day, avg(trips) AS v FROM mart_hourly
                        GROUP BY ALL ORDER BY ALL""").df()
    paths.append(_write("heatmap", hm.round(1).values.tolist()))

    # Each hour vs. the median of *dry* hours with the same hour, weekday and month.
    env = con.execute("""
        WITH dry AS (
            SELECT hour_of_day, iso_dow, month, median(trips) AS typical
            FROM mart_hourly WHERE precip_mm = 0 AND holiday_name IS NULL
            GROUP BY ALL
        )
        SELECT
          CASE WHEN h.precip_mm = 0 THEN '0' WHEN h.precip_mm < 1 THEN '<1' WHEN h.precip_mm < 3 THEN '1-3'
               WHEN h.precip_mm < 6 THEN '3-6' ELSE '6+' END AS rain_bin,
          median(h.trips / d.typical) AS ratio_vs_dry, count(*) AS hours
        FROM mart_hourly h JOIN dry d USING (hour_of_day, iso_dow, month)
        WHERE h.hour_of_day BETWEEN 7 AND 21 AND d.typical > 30 AND h.holiday_name IS NULL
        GROUP BY 1
    """).df()
    # Controls for time of day: each hour is compared with the average of the same hour slot,
    # because pollution and cycling both peak at busy hours (a naive average is confounded).
    aqi = con.execute("""
        WITH typical AS (
            SELECT hour_of_day, is_non_working_day, avg(trips) AS typical
            FROM mart_hourly GROUP BY ALL
        )
        SELECT CASE WHEN us_aqi < 50 THEN 'Buena' WHEN us_aqi < 100 THEN 'Aceptable'
                    WHEN us_aqi < 150 THEN 'Mala (sensibles)' ELSE 'Mala' END AS aqi_bin,
               avg(h.trips / t.typical) AS ratio_vs_typical, count(*) AS hours
        FROM mart_hourly h JOIN typical t USING (hour_of_day, is_non_working_day)
        WHERE h.hour_of_day BETWEEN 7 AND 21 AND t.typical > 30 AND h.us_aqi IS NOT NULL
        GROUP BY 1 HAVING count(*) >= 24
    """).df()
    paths.append(_write("environment", {"rain": env.round(3).to_dict("records"),
                                        "aqi": aqi.round(3).to_dict("records")}))

    c = ctx["clusters"]
    paths.append(_write("clusters", {
        "k": c["k"], "silhouette": {str(k): round(v, 3) for k, v in c["silhouette"].items()},
        "names": c["names"],
        "sizes": c["assignments"]["cluster"].value_counts().sort_index().tolist(),
        "centroids": [[round(v, 4) for v in row] for row in c["centroids"].values],
    }))

    r = ctx["riders"]
    paths.append(_write("riders", {
        "pct_women": round(r["pct_women"], 1), "median_age": r["median_age"],
        "table": r["table"].round(3).to_dict("records"),
        "by_hour": r["by_hour"].round(2).to_dict("records"),
    }))

    paths.append(_write("meta", ctx["meta"]))
    return [p.name for p in paths]
