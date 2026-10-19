"""Extract raw sources and land them as typed Parquet files in the data lake.

Sources
-------
* Ecobici monthly trip CSVs (official open data, ~1.5M trips/month)
* Ecobici station catalogue (GBFS feed)
* Hourly weather (Open-Meteo archive, ERA5)
* Hourly air quality (Open-Meteo air-quality, CAMS)
"""

from __future__ import annotations

import json
import logging
import urllib.request
from pathlib import Path

import duckdb
import pandas as pd

from . import config

log = logging.getLogger(__name__)

RAW_COLUMNS = ["gender", "age", "bike_id", "start_station", "start_date", "start_time",
               "end_station", "end_date", "end_time"]

# Every month should parse with one of these; the order is the preferred one.
_TS_FORMATS = ["%d/%m/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d/%m/%y %H:%M:%S",
               "%d/%m/%Y %H:%M", "%Y-%m-%d %H:%M"]


def _download(url: str, dest: Path) -> Path:
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    log.info("Downloading %s", url)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(url, timeout=600) as r, open(tmp, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    tmp.rename(dest)
    return dest


def download_trips() -> list[Path]:
    files = []
    for folder, name in config.MONTHS:
        dest = config.RAW_TRIPS / f"{name.removesuffix('-1')}.csv"
        files.append(_download(f"{config.ECOBICI_BASE}/{folder}/{name}.csv", dest))
    return files


def download_stations() -> Path:
    return _download(config.GBFS_STATIONS, config.RAW_EXT / "station_information.json")


def _open_meteo(api: str, variables: list[str], start: str, end: str, dest: Path) -> Path:
    url = (f"{api}?latitude={config.CDMX_LAT}&longitude={config.CDMX_LON}"
           f"&start_date={start}&end_date={end}&hourly={','.join(variables)}"
           f"&timezone={config.TZ.replace('/', '%2F')}")
    return _download(url, dest)


def download_environment(start: str, end: str) -> tuple[Path, Path]:
    weather = _open_meteo(config.WEATHER_API,
                          ["temperature_2m", "precipitation", "relative_humidity_2m",
                           "wind_speed_10m", "cloud_cover"],
                          start, end, config.RAW_EXT / f"weather_{start}_{end}.json")
    air = _open_meteo(config.AIR_API, ["pm2_5", "pm10", "ozone", "nitrogen_dioxide",
                                       "us_aqi"],
                      start, end, config.RAW_EXT / f"air_{start}_{end}.json")
    return weather, air


def _ts(date_col: str, time_col: str) -> str:
    parts = [f"try_strptime({date_col} || ' ' || {time_col}, '{fmt}')" for fmt in _TS_FORMATS]
    return f"coalesce({', '.join(parts)})"


def land_trips(con: duckdb.DuckDBPyConnection, files: list[Path]) -> int:
    """CSV -> typed Parquet, one file per month. Raw values are kept; cleaning is in SQL."""
    out_dir = config.LAKE / "trips"
    out_dir.mkdir(parents=True, exist_ok=True)
    total = 0
    for f in files:
        target = out_dir / f"{f.stem}.parquet"
        con.execute(f"""
            COPY (
              SELECT
                '{f.stem}'                                   AS source_month,
                nullif(trim(gender), '')                     AS gender,
                try_cast(age AS INTEGER)                     AS age,
                bike_id,
                trim(start_station)                          AS start_station,
                trim(end_station)                            AS end_station,
                {_ts('start_date', 'start_time')}            AS started_at,
                {_ts('end_date', 'end_time')}                AS ended_at
              FROM read_csv('{f}', header = true, all_varchar = true,
                            names = {RAW_COLUMNS}, ignore_errors = true)
            ) TO '{target}' (FORMAT parquet, COMPRESSION zstd)
        """)
        n = con.execute(f"SELECT count(*) FROM '{target}'").fetchone()[0]
        log.info("Landed %s: %s trips", f.stem, f"{n:,}")
        total += n
    return total


def land_stations(path: Path) -> pd.DataFrame:
    stations = pd.DataFrame(json.loads(path.read_text())["data"]["stations"])
    stations = stations.rename(columns={"short_name": "station_code"})[
        ["station_code", "name", "lat", "lon", "capacity"]]
    stations["name"] = stations["name"].str.replace(r"^[A-Z]{2,3}-\d+(-\d+)?\s+", "", regex=True)
    out = config.LAKE / "stations.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    stations.to_parquet(out, index=False)
    return stations


def land_environment(weather_path: Path, air_path: Path) -> pd.DataFrame:
    w = pd.DataFrame(json.loads(weather_path.read_text())["hourly"])
    a = pd.DataFrame(json.loads(air_path.read_text())["hourly"])
    env = w.merge(a, on="time", how="left")
    env["time"] = pd.to_datetime(env["time"])
    env = env.rename(columns={"time": "hour_ts", "temperature_2m": "temp_c",
                              "precipitation": "precip_mm", "relative_humidity_2m": "humidity",
                              "wind_speed_10m": "wind_kmh"})
    env.to_parquet(config.LAKE / "environment_hourly.parquet", index=False)
    return env


def run(con: duckdb.DuckDBPyConnection) -> dict:
    files = download_trips()
    n_trips = land_trips(con, files)
    stations = land_stations(download_stations())
    span = con.execute(
        f"SELECT min(started_at)::DATE, max(started_at)::DATE FROM '{config.LAKE}/trips/*.parquet'"
        " WHERE started_at BETWEEN '2025-06-01' AND '2026-06-01'"
    ).fetchone()
    env = land_environment(*download_environment(str(span[0]), str(span[1])))
    return {"raw_trips": n_trips, "stations": len(stations), "env_hours": len(env),
            "start": str(span[0]), "end": str(span[1])}
