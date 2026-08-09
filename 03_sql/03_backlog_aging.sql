-- =============================================================================
-- 03_backlog_aging.sql
-- Purpose : Describe the shape of the active queue by age, and show how much of
--           it is recent inflow versus a long-standing tail.
-- Depends : 01_clean_base.sql
-- Outputs : agg_backlog_aging_buckets, agg_backlog_aging_by_record_type,
--           agg_backlog_age_percentiles
--
-- Note on age: active_age_days is computed as (snapshot_date - date_requested).
-- It measures how long a request has been in an open state, not how long any
-- physical work has taken.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Aging profile of the whole active queue, with a running share so a reader can
-- answer "what fraction of the queue is older than X" directly off the table.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TABLE agg_backlog_aging_buckets AS
WITH bucketed AS (
    SELECT
        age_bucket,
        MIN(active_age_days) AS bucket_min_days,
        MAX(active_age_days) AS bucket_max_days,
        COUNT(*)             AS n_records,
        COUNT(DISTINCT issue_key) AS n_distinct_issues,
        MEDIAN(active_age_days)   AS median_age_days
    FROM v_active
    GROUP BY age_bucket
),
ordered AS (
    SELECT
        b.*,
        CASE age_bucket
            WHEN '0-7' THEN 1 WHEN '8-30' THEN 2 WHEN '31-60' THEN 3
            WHEN '61-90' THEN 4 WHEN '91-180' THEN 5 WHEN '181-365' THEN 6
            WHEN '366-730' THEN 7 WHEN '731+' THEN 8 ELSE 99
        END AS bucket_order
    FROM bucketed AS b
)
SELECT
    bucket_order,
    age_bucket,
    bucket_min_days,
    bucket_max_days,
    n_records,
    n_distinct_issues,
    median_age_days,
    ROUND(100.0 * n_records / SUM(n_records) OVER (), 1) AS pct_of_active_backlog,
    SUM(n_records) OVER (ORDER BY bucket_order
                         ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cumulative_records,
    ROUND(100.0 * SUM(n_records) OVER (ORDER BY bucket_order
                                       ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
          / SUM(n_records) OVER (), 1) AS cumulative_pct
FROM ordered
ORDER BY bucket_order;

-- -----------------------------------------------------------------------------
-- Same profile split by the City staff group that owns the request type. This is
-- what separates "genuine aging queue" from "asset program backlog".
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TABLE agg_backlog_aging_by_record_type AS
SELECT
    case_record_type,
    COUNT(*)                                                        AS active_records,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1)              AS pct_of_active_backlog,
    MEDIAN(active_age_days)                                         AS median_age_days,
    QUANTILE_CONT(active_age_days, 0.90)                            AS p90_age_days,
    COUNT(*) FILTER (WHERE active_age_days <= 30)                   AS aged_0_30,
    COUNT(*) FILTER (WHERE active_age_days >= 60)                   AS aged_60_plus,
    COUNT(*) FILTER (WHERE active_age_days >= 90)                   AS aged_90_plus,
    COUNT(*) FILTER (WHERE active_age_days >= 365)                  AS aged_365_plus,
    ROUND(100.0 * COUNT(*) FILTER (WHERE active_age_days >= 90)
          / NULLIF(COUNT(*), 0), 1)                                 AS pct_aged_90_plus
FROM v_active
GROUP BY case_record_type
ORDER BY active_records DESC;

-- -----------------------------------------------------------------------------
-- Percentile spine for the active queue overall and for the two channel groups.
-- Median and p90 are reported together with the mean so the skew is visible
-- rather than asserted.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TABLE agg_backlog_age_percentiles AS
SELECT
    'All active requests' AS segment,
    COUNT(*)                              AS active_records,
    ROUND(AVG(active_age_days), 1)        AS mean_age_days,
    QUANTILE_CONT(active_age_days, 0.25)  AS p25_age_days,
    MEDIAN(active_age_days)               AS median_age_days,
    QUANTILE_CONT(active_age_days, 0.75)  AS p75_age_days,
    QUANTILE_CONT(active_age_days, 0.90)  AS p90_age_days,
    QUANTILE_CONT(active_age_days, 0.95)  AS p95_age_days,
    MAX(active_age_days)                  AS max_age_days
FROM v_active

UNION ALL

SELECT
    'Channel group: ' || channel_group,
    COUNT(*),
    ROUND(AVG(active_age_days), 1),
    QUANTILE_CONT(active_age_days, 0.25),
    MEDIAN(active_age_days),
    QUANTILE_CONT(active_age_days, 0.75),
    QUANTILE_CONT(active_age_days, 0.90),
    QUANTILE_CONT(active_age_days, 0.95),
    MAX(active_age_days)
FROM v_active
GROUP BY channel_group

ORDER BY active_records DESC;
