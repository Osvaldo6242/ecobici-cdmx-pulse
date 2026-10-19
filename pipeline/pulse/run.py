"""Run the whole pipeline:  python -m pulse.run  [--skip-ingest]"""

from __future__ import annotations

import argparse
import json
import logging
import time
import warnings

from . import anomalies, config, export_web, forecast, ingest, riders, stations, warehouse

warnings.filterwarnings("ignore", message=".*encountered in matmul", category=RuntimeWarning)
log = logging.getLogger("pulse")


def main(argv=None) -> dict:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-ingest", action="store_true", help="reuse the Parquet lake")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    t0 = time.perf_counter()
    con = warehouse.connect()

    ingest_info = {} if args.skip_ingest else ingest.run(con)
    log.info("Building warehouse")
    timings = warehouse.build(con)

    dq = warehouse.table(con, "dq_summary")
    hourly = warehouse.table(con, "mart_hourly")
    log.info("Forecasting")
    fc = forecast.run(hourly)
    log.info("Anomaly detection")
    an = anomalies.detect(fc["features"])
    log.info("Station clustering / network / rebalancing")
    cl = stations.cluster_stations(warehouse.table(con, "mart_station_profile"))
    nw = stations.network(warehouse.table(con, "mart_od"))
    rb = stations.rebalancing_risk(warehouse.table(con, "mart_rebalancing"))
    rd = riders.summary(con)

    totals = con.execute("""SELECT count(*), count(DISTINCT trip_date), median(duration_min),
                                   sum(p.distance_km)
                            FROM int_trips JOIN int_station_pairs p USING (start_station, end_station)
                         """).fetchone()
    raw_total = int(dq["trips"].sum())
    meta = {
        "raw_trips": raw_total,
        "valid_trips": int(totals[0]),
        "pct_valid": round(totals[0] / raw_total * 100, 2),
        "days": int(totals[1]),
        "median_duration_min": round(float(totals[2]), 1),
        "total_km_straight_line": round(float(totals[3])),
        "stations": int(con.execute("SELECT count(*) FROM stg_stations").fetchone()[0]),
        "window": [warehouse.WINDOW_START, warehouse.WINDOW_END_EXCL],
        "dq": dq.to_dict("records"),
        "n_anomalies": int(an["is_anomaly"].sum()),
        "clusters_k": cl["k"],
        "communities": nw["n_communities"],
        "modularity": round(nw["modularity"], 3),
        "round_trip_share_pct": round(nw["round_trip_share"] * 100, 2),
        "pct_women": round(rd["pct_women"], 1),
        "median_age": rd["median_age"],
        "forecast_mae": round(fc["metrics"]["mae"], 1),
        "forecast_r2": round(fc["metrics"]["r2"], 3),
        "baseline_mae": round(fc["baseline_metrics"]["mae"], 1),
        "rain_drop_pct": round(fc["rain_effect"]["pct_drop_in_rainy_hours"], 1),
        "busiest_hour": int(hourly.groupby("hour_of_day")["trips"].mean().idxmax()),
        "sql_layer_seconds": timings,
    }
    files = export_web.export_all(con, {
        "clusters": cl, "network": nw, "rebalancing": rb, "forecast": fc,
        "anomalies": an, "riders": rd, "meta": meta,
    })
    meta["runtime_seconds"] = round(time.perf_counter() - t0, 1)
    config.REPORTS.mkdir(exist_ok=True)
    (config.REPORTS / "metrics.json").write_text(json.dumps(
        {**meta, "ingest": ingest_info, "site_files": files,
         "forecast_cv": fc["cv"].to_dict("records"),
         "top_anomalies": an[an["is_anomaly"]].assign(day=lambda d: d["day"].astype(str))
                          .sort_values("z").to_dict("records"),
         "top_rebalancing": rb.head(15).to_dict("records")},
        indent=2, default=str, ensure_ascii=False))
    log.info("Done in %.1fs", meta["runtime_seconds"])
    return meta


if __name__ == "__main__":
    main()
