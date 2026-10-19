"""Build the DuckDB warehouse by running the layered SQL models in order."""

from __future__ import annotations

import logging
import time

import duckdb
import pandas as pd

from . import config

log = logging.getLogger(__name__)

WINDOW_START = "2025-06-01"
WINDOW_END_EXCL = "2026-06-01"


def connect(path=config.WAREHOUSE) -> duckdb.DuckDBPyConnection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(path))
    con.execute("SET preserve_insertion_order = false")
    return con


def _params() -> dict:
    return {
        "lake": config.LAKE.as_posix(),
        "start": WINDOW_START, "end_excl": WINDOW_END_EXCL,
        "min_trip": config.MIN_TRIP_MIN, "max_trip": config.MAX_TRIP_MIN,
        "min_age": config.MIN_AGE, "max_age": config.MAX_AGE,
    }


def load_holidays(con: duckdb.DuckDBPyConnection) -> None:
    hol = pd.DataFrame(
        [(pd.Timestamp(d).date(), n) for d, n in config.HOLIDAYS.items()],
        columns=["holiday_date", "holiday_name"],
    )
    con.execute("CREATE OR REPLACE TABLE holidays AS SELECT * FROM hol")


def build(con: duckdb.DuckDBPyConnection) -> dict[str, float]:
    load_holidays(con)
    timings = {}
    for sql_file in sorted(config.SQL_DIR.glob("*.sql")):
        t0 = time.perf_counter()
        con.execute(sql_file.read_text().format(**_params()))
        timings[sql_file.stem] = round(time.perf_counter() - t0, 2)
        log.info("SQL layer %s built in %.2fs", sql_file.stem, timings[sql_file.stem])
    return timings


def table(con: duckdb.DuckDBPyConnection, name: str) -> pd.DataFrame:
    return con.execute(f"SELECT * FROM {name}").df()
