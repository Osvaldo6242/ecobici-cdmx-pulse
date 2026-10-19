-- MARTS: analysis-ready tables consumed by models and the website.

-- 1. System demand per hour, joined with weather & air quality (gap-filled hours = 0 trips).
CREATE OR REPLACE TABLE mart_hourly AS
WITH hours AS (
    SELECT unnest(generate_series(TIMESTAMP '{start}', TIMESTAMP '{end_excl}' - INTERVAL 1 HOUR,
                                  INTERVAL 1 HOUR)) AS hour_ts
), demand AS (
    SELECT hour_ts, count(*) AS trips, avg(duration_min) AS avg_duration_min
    FROM int_trips GROUP BY hour_ts
)
SELECT
    h.hour_ts,
    coalesce(d.trips, 0)                         AS trips,
    d.avg_duration_min,
    hour(h.hour_ts)                              AS hour_of_day,
    isodow(h.hour_ts)                            AS iso_dow,
    month(h.hour_ts)                             AS month,
    (isodow(h.hour_ts) >= 6 OR hol.holiday_date IS NOT NULL) AS is_non_working_day,
    hol.holiday_name,
    e.temp_c, e.precip_mm, e.humidity, e.wind_kmh, e.cloud_cover,
    e.pm2_5, e.pm10, e.ozone, e.nitrogen_dioxide, e.us_aqi
FROM hours h
LEFT JOIN demand d USING (hour_ts)
LEFT JOIN stg_environment e USING (hour_ts)
LEFT JOIN holidays hol ON hol.holiday_date = CAST(h.hour_ts AS DATE)
ORDER BY h.hour_ts;

-- 2. Daily totals.
CREATE OR REPLACE TABLE mart_daily AS
SELECT
    CAST(hour_ts AS DATE)          AS day,
    sum(trips)                     AS trips,
    any_value(is_non_working_day)  AS is_non_working_day,
    any_value(holiday_name)        AS holiday_name,
    sum(precip_mm)                 AS precip_mm,
    avg(temp_c)                    AS temp_c,
    max(us_aqi)                    AS max_aqi
FROM mart_hourly
GROUP BY 1 ORDER BY 1;

-- 3. Average 24h departure/arrival profile per station (working vs non-working days).
CREATE OR REPLACE TABLE mart_station_profile AS
WITH days AS (
    SELECT is_non_working_day, count(DISTINCT trip_date) AS n_days FROM int_trips GROUP BY 1
), dep AS (
    SELECT start_station AS station_code, is_non_working_day, hour_of_day, count(*) AS n
    FROM int_trips GROUP BY ALL
), arr AS (
    SELECT end_station AS station_code, is_non_working_day, hour(ended_at) AS hour_of_day,
           count(*) AS n
    FROM int_trips GROUP BY ALL
)
SELECT
    s.station_code,
    d.is_non_working_day,
    hr.hour_of_day,
    coalesce(dep.n, 0) * 1.0 / d.n_days AS avg_departures,
    coalesce(arr.n, 0) * 1.0 / d.n_days AS avg_arrivals
FROM stg_stations s
CROSS JOIN days d
CROSS JOIN (SELECT unnest(range(24)) AS hour_of_day) hr
LEFT JOIN dep ON dep.station_code = s.station_code AND dep.is_non_working_day = d.is_non_working_day
             AND dep.hour_of_day = hr.hour_of_day
LEFT JOIN arr ON arr.station_code = s.station_code AND arr.is_non_working_day = d.is_non_working_day
             AND arr.hour_of_day = hr.hour_of_day;

-- 4. Origin-destination flows on working days with distance.
CREATE OR REPLACE TABLE mart_od AS
SELECT
    t.start_station, t.end_station,
    count(*)                                           AS trips,
    count(*) * 1.0 / (SELECT count(DISTINCT trip_date) FROM int_trips WHERE NOT is_non_working_day)
                                                       AS trips_per_day,
    median(t.duration_min)                             AS median_duration_min,
    any_value(p.distance_km)                           AS distance_km
FROM int_trips t
JOIN int_station_pairs p USING (start_station, end_station)
WHERE NOT t.is_non_working_day
GROUP BY ALL;

-- 5. Rebalancing pressure: cumulative net flow through a working day per station.
CREATE OR REPLACE TABLE mart_rebalancing AS
SELECT
    p.station_code,
    p.hour_of_day,
    p.avg_arrivals - p.avg_departures                                  AS net_flow,
    sum(p.avg_arrivals - p.avg_departures) OVER (
        PARTITION BY p.station_code ORDER BY p.hour_of_day)            AS cumulative_net,
    s.capacity
FROM mart_station_profile p
JOIN stg_stations s USING (station_code)
WHERE NOT p.is_non_working_day;

-- 6. Riders: gender x age band (aggregated; small cells suppressed downstream).
CREATE OR REPLACE TABLE mart_riders AS
SELECT
    gender,
    CASE WHEN age IS NULL THEN 'ND'
         WHEN age < 25 THEN '16-24' WHEN age < 35 THEN '25-34' WHEN age < 45 THEN '35-44'
         WHEN age < 55 THEN '45-54' ELSE '55+' END AS age_band,
    count(*)                                      AS trips,
    median(duration_min)                          AS median_duration_min,
    avg(CASE WHEN hour_of_day BETWEEN 6 AND 9 THEN 1.0 ELSE 0 END) AS share_morning_peak
FROM int_trips
GROUP BY ALL;

-- 7. Data-quality summary.
CREATE OR REPLACE TABLE dq_summary AS
SELECT validity, count(*) AS trips, round(count(*) * 100.0 / sum(count(*)) OVER (), 3) AS pct
FROM stg_trips GROUP BY validity ORDER BY trips DESC;
