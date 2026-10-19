"""Paths, sources and constants for the Ecobici CDMX Pulse pipeline."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
RAW_TRIPS = DATA / "raw" / "trips"
RAW_EXT = DATA / "raw" / "external"
LAKE = DATA / "lake"                      # Parquet "data lake"
WAREHOUSE = DATA / "warehouse.duckdb"
SQL_DIR = Path(__file__).resolve().parent / "sql"
REPORTS = ROOT / "reports"
SITE_DATA = ROOT / "docs" / "data"        # GitHub Pages serves /docs

TZ = "America/Mexico_City"
CDMX_LAT, CDMX_LON = 19.42, -99.17
RANDOM_STATE = 42

ECOBICI_BASE = "https://ecobici.cdmx.gob.mx/wp-content/uploads"
# (upload folder, file name) for the 12 months analysed.
MONTHS = [
    ("2025/07", "2025-06"), ("2025/08", "2025-07"), ("2025/09", "2025-08"),
    ("2025/10", "2025-09"), ("2025/11", "2025-10-1"), ("2025/12", "2025-11"),
    ("2026/01", "2025-12"), ("2026/02", "2026-01"), ("2026/03", "2026-02"),
    ("2026/04", "2026-03"), ("2026/05", "2026-04"), ("2026/06", "2026-05"),
]
GBFS_STATIONS = "https://gbfs.mex.lyftbikes.com/gbfs/es/station_information.json"
WEATHER_API = "https://archive-api.open-meteo.com/v1/archive"
AIR_API = "https://air-quality-api.open-meteo.com/v1/air-quality"

# Trip-level validity rules.
MIN_TRIP_MIN, MAX_TRIP_MIN = 1, 180
MIN_AGE, MAX_AGE = 16, 85

# Mexican federal holidays + major CDMX observances within the study window.
HOLIDAYS = {
    "2025-09-16": "Día de la Independencia",
    "2025-11-02": "Día de Muertos",
    "2025-11-17": "Revolución (observado)",
    "2025-12-12": "Día de la Virgen de Guadalupe",
    "2025-12-24": "Nochebuena",
    "2025-12-25": "Navidad",
    "2025-12-31": "Fin de año",
    "2026-01-01": "Año Nuevo",
    "2026-02-02": "Constitución (observado)",
    "2026-03-16": "Natalicio de Benito Juárez (observado)",
    "2026-04-02": "Jueves Santo",
    "2026-04-03": "Viernes Santo",
    "2026-05-01": "Día del Trabajo",
}

# Multi-day periods used only to explain detected anomalies (not as model features).
SEASONS = [
    ("2025-09-15", "2025-09-15", "Víspera de Independencia (El Grito)"),
    ("2025-12-20", "2026-01-06", "Vacaciones de invierno"),
    ("2026-03-28", "2026-04-12", "Semana Santa y Pascua"),
]
