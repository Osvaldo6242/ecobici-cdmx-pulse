"""Synthetic miniature Ecobici system so the full SQL + model stack runs in seconds."""

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
warnings.filterwarnings("ignore", message=".*encountered in matmul", category=RuntimeWarning)

from pulse import config, ingest, warehouse  # noqa: E402

STATIONS = pd.DataFrame({
    "station_code": ["001", "002", "003", "004", "005", "271-272"],
    "name": ["Casa A", "Casa B", "Oficina A", "Oficina B", "Parque", "Doble"],
    "lat": [19.40, 19.41, 19.43, 19.44, 19.42, 19.425],
    "lon": [-99.16, -99.17, -99.19, -99.20, -99.18, -99.175],
    "capacity": [20, 20, 30, 30, 25, 60],
})


def _synthetic_trips(days: int = 21, seed: int = 0) -> pd.DataFrame:
    """Homes (001/002) send riders to offices (003/004) at 8h and receive them back at 18h."""
    rng = np.random.default_rng(seed)
    rows = []
    start = pd.Timestamp("2025-06-01")
    for d in range(days):
        day = start + pd.Timedelta(days=d)
        weekday = day.dayofweek < 5
        for hour in range(6, 23):
            base = 30 if hour in (8, 18) and weekday else 6
            for _ in range(rng.poisson(base)):
                if hour < 12:
                    o, dest = rng.choice(["001", "002"]), rng.choice(["003", "004"])
                else:
                    o, dest = rng.choice(["003", "004", "005"]), rng.choice(["001", "002", "271-272"])
                t0 = day + pd.Timedelta(hours=hour, minutes=int(rng.integers(0, 60)))
                t1 = t0 + pd.Timedelta(minutes=int(rng.integers(5, 40)))
                rows.append([rng.choice(["M", "F", "?"], p=[.65, .3, .05]), int(rng.integers(18, 70)),
                             str(rng.integers(1e6, 9e6)), o, t0.strftime("%d/%m/%Y"), t0.strftime("%H:%M:%S"),
                             dest, t1.strftime("%d/%m/%Y"), t1.strftime("%H:%M:%S")])
    # Dirty rows the pipeline must reject.
    rows.append(["M", "30", "1", "001", "05/06/2025", "10:00:00", "003", "05/06/2025", "10:00:20"])  # too short
    rows.append(["F", "30", "2", "999", "05/06/2025", "10:00:00", "003", "05/06/2025", "10:20:00"])  # unknown
    rows.append(["F", "abc", "3", "001", "bad-date", "10:00:00", "003", "05/06/2025", "10:20:00"])   # unparseable
    cols = ["Genero_Usuario", "Edad_Usuario", "Bici", "Ciclo_Estacion_Retiro", "Fecha_Retiro",
            "Hora_Retiro", "Ciclo_EstacionArribo", "Fecha_Arribo", "Hora_Arribo"]
    return pd.DataFrame(rows, columns=cols)


@pytest.fixture(scope="session")
def mini_warehouse(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("pulse")
    config.LAKE = tmp / "lake"
    config.SITE_DATA = tmp / "site"
    raw = tmp / "trips.csv"
    _synthetic_trips().to_csv(raw, index=False)

    (config.LAKE).mkdir(parents=True)
    STATIONS.to_parquet(config.LAKE / "stations.parquet", index=False)
    hours = pd.date_range("2025-06-01", "2025-06-22", freq="h", inclusive="left")
    rng = np.random.default_rng(1)
    pd.DataFrame({
        "hour_ts": hours, "temp_c": 18 + 5 * np.sin(np.arange(len(hours)) / 24 * 2 * np.pi),
        "precip_mm": rng.choice([0, 0, 0, 0, 2.5], len(hours)), "humidity": 60.0,
        "wind_kmh": 8.0, "cloud_cover": 40.0, "pm2_5": 20.0, "pm10": 35.0, "ozone": 60.0,
        "nitrogen_dioxide": 25.0, "us_aqi": rng.integers(30, 160, len(hours)).astype(float),
    }).to_parquet(config.LAKE / "environment_hourly.parquet", index=False)

    warehouse.WINDOW_START, warehouse.WINDOW_END_EXCL = "2025-06-01", "2025-06-22"
    con = warehouse.connect(tmp / "test.duckdb")
    ingest.land_trips(con, [raw])
    warehouse.build(con)
    yield con
    con.close()
