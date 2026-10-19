"""Who rides? Gender and age patterns, published only as k-anonymous aggregates."""

from __future__ import annotations

import duckdb
import pandas as pd

K_MIN = 100  # minimum trips per published cell


def suppress_small_cells(df: pd.DataFrame, count_col: str = "trips", k: int = K_MIN) -> pd.DataFrame:
    return df[df[count_col] >= k].reset_index(drop=True)


def gender_by_hour(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return con.execute("""
        SELECT hour_of_day,
               count(*) FILTER (WHERE gender = 'F') * 100.0
                 / count(*) FILTER (WHERE gender IN ('M', 'F')) AS pct_women,
               count(*) AS trips
        FROM int_trips WHERE NOT is_non_working_day
        GROUP BY 1 ORDER BY 1
    """).df()


def summary(con: duckdb.DuckDBPyConnection) -> dict:
    riders = suppress_small_cells(con.execute("SELECT * FROM mart_riders").df())
    known = riders[riders["gender"].isin(["M", "F"])]
    pct_women = known.loc[known["gender"] == "F", "trips"].sum() / known["trips"].sum() * 100
    return {
        "table": riders,
        "by_hour": gender_by_hour(con),
        "pct_women": float(pct_women),
        "median_age": float(con.execute(
            "SELECT median(age) FROM int_trips WHERE age IS NOT NULL").fetchone()[0]),
    }
