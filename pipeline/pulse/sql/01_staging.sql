-- STAGING: typed, normalised trips with a validity reason for every row.
CREATE OR REPLACE TABLE stg_stations AS
SELECT station_code, name, lat, lon, capacity
FROM read_parquet('{lake}/stations.parquet');

CREATE OR REPLACE TABLE stg_trips AS
WITH src AS (
    SELECT
        row_number() OVER ()                                   AS trip_id,
        source_month,
        CASE WHEN gender IN ('M', 'F') THEN gender ELSE 'O/ND' END AS gender,
        CASE WHEN age BETWEEN {min_age} AND {max_age} THEN age END  AS age,
        bike_id,
        start_station,
        end_station,
        started_at,
        ended_at,
        date_diff('second', started_at, ended_at) / 60.0       AS duration_min
    FROM read_parquet('{lake}/trips/*.parquet')
)
SELECT
    s.*,
    CASE
        WHEN started_at IS NULL OR ended_at IS NULL           THEN 'unparseable_timestamp'
        WHEN started_at < TIMESTAMP '{start}' OR started_at >= TIMESTAMP '{end_excl}'
                                                              THEN 'outside_window'
        WHEN duration_min < {min_trip}                        THEN 'too_short'
        WHEN duration_min > {max_trip}                        THEN 'too_long'
        WHEN st_a.station_code IS NULL OR st_b.station_code IS NULL
                                                              THEN 'unknown_station'
        ELSE 'valid'
    END AS validity
FROM src s
LEFT JOIN stg_stations st_a ON st_a.station_code = s.start_station
LEFT JOIN stg_stations st_b ON st_b.station_code = s.end_station;

CREATE OR REPLACE TABLE stg_environment AS
SELECT * FROM read_parquet('{lake}/environment_hourly.parquet');
