-- INTERMEDIATE: valid trips enriched with calendar attributes.
CREATE OR REPLACE TABLE int_trips AS
SELECT
    t.trip_id,
    t.gender,
    t.age,
    t.start_station,
    t.end_station,
    t.started_at,
    t.ended_at,
    t.duration_min,
    date_trunc('hour', t.started_at)                          AS hour_ts,
    CAST(t.started_at AS DATE)                                AS trip_date,
    hour(t.started_at)                                        AS hour_of_day,
    isodow(t.started_at)                                      AS iso_dow,
    (isodow(t.started_at) >= 6 OR h.holiday_date IS NOT NULL) AS is_non_working_day,
    h.holiday_name
FROM stg_trips t
LEFT JOIN holidays h ON h.holiday_date = CAST(t.started_at AS DATE)
WHERE t.validity = 'valid';

-- Great-circle distance between stations (haversine, km) for every observed pair.
CREATE OR REPLACE TABLE int_station_pairs AS
SELECT
    a.station_code AS start_station,
    b.station_code AS end_station,
    2 * 6371 * asin(sqrt(
        pow(sin(radians(b.lat - a.lat) / 2), 2)
        + cos(radians(a.lat)) * cos(radians(b.lat)) * pow(sin(radians(b.lon - a.lon) / 2), 2)
    )) AS distance_km
FROM (SELECT DISTINCT start_station, end_station FROM int_trips) p
JOIN stg_stations a ON a.station_code = p.start_station
JOIN stg_stations b ON b.station_code = p.end_station;
