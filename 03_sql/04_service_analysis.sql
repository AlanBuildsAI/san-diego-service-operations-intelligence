-- =============================================================================
-- 04_service_analysis.sql
-- Purpose : Answer where active workload sits by service category, which
--           categories hold the oldest requests, and which have a p90 that is
--           out of line with their own median (a long right tail rather than a
--           uniformly slow queue).
-- Depends : 01_clean_base.sql
-- Outputs : agg_service_backlog, agg_service_tail_risk, agg_service_concentration
-- =============================================================================

-- -----------------------------------------------------------------------------
-- One row per service category in the active queue. Categories are ranked on
-- volume and on age independently, because the largest queue and the oldest
-- queue are not the same thing and leadership needs both.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TABLE agg_service_backlog AS
WITH base AS (
    SELECT
        service_name,
        -- Modal, not arbitrary: audit check DQ-08 found service_name and
        -- case_record_type are many-to-many, so ANY_VALUE would pick a record
        -- type at random. MODE returns the one most records actually carry.
        MODE(case_record_type)                         AS most_common_record_type,
        COUNT(*)                                       AS active_records,
        COUNT(DISTINCT issue_key)                      AS active_distinct_issues,
        COUNT(*) FILTER (WHERE is_duplicate_child)     AS active_duplicate_children,
        MEDIAN(active_age_days)                        AS median_age_days,
        QUANTILE_CONT(active_age_days, 0.90)           AS p90_age_days,
        ROUND(AVG(active_age_days), 1)                 AS mean_age_days,
        MAX(active_age_days)                           AS max_age_days,
        COUNT(*) FILTER (WHERE active_age_days >= 60)  AS aged_60_plus,
        COUNT(*) FILTER (WHERE active_age_days >= 90)  AS aged_90_plus,
        COUNT(*) FILTER (WHERE active_age_days >= 365) AS aged_365_plus,
        COUNT(*) FILTER (WHERE active_age_days <= 30)  AS aged_0_30
    FROM v_active
    GROUP BY service_name
)
SELECT
    service_name,
    most_common_record_type,
    active_records,
    active_distinct_issues,
    active_duplicate_children,
    ROUND(100.0 * active_duplicate_children / NULLIF(active_records, 0), 1) AS duplicate_rate_pct,
    ROUND(100.0 * active_records / SUM(active_records) OVER (), 2)          AS pct_of_active_backlog,
    ROUND(100.0 * SUM(active_records) OVER (ORDER BY active_records DESC
                                            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
          / SUM(active_records) OVER (), 1)                                 AS cumulative_pct_of_backlog,
    median_age_days,
    p90_age_days,
    mean_age_days,
    max_age_days,
    aged_0_30,
    aged_60_plus,
    aged_90_plus,
    aged_365_plus,
    ROUND(100.0 * aged_90_plus / NULLIF(active_records, 0), 1)              AS pct_aged_90_plus,
    ROUND(100.0 * aged_90_plus / SUM(aged_90_plus) OVER (), 2)              AS pct_of_aged_90_backlog,
    RANK() OVER (ORDER BY active_records DESC)                              AS rank_by_volume,
    RANK() OVER (ORDER BY median_age_days DESC)                             AS rank_by_median_age,
    RANK() OVER (ORDER BY aged_90_plus DESC)                                AS rank_by_aged_90_volume
FROM base
ORDER BY active_records DESC;

-- -----------------------------------------------------------------------------
-- Tail risk: categories whose p90 is far above their own median. A high ratio
-- means most requests move but a minority sit for a very long time, which is a
-- different operational problem from a category that is uniformly slow.
-- Restricted to categories with enough volume for the percentiles to be stable.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TABLE agg_service_tail_risk AS
WITH sized AS (
    SELECT
        service_name,
        COUNT(*)                             AS active_records,
        MEDIAN(active_age_days)              AS median_age_days,
        QUANTILE_CONT(active_age_days, 0.90) AS p90_age_days
    FROM v_active
    GROUP BY service_name
    HAVING COUNT(*) >= 250          -- volume floor for a stable p90
),
scored AS (
    SELECT
        service_name,
        active_records,
        median_age_days,
        p90_age_days,
        ROUND(p90_age_days / NULLIF(median_age_days, 0), 2) AS p90_to_median_ratio,
        ROUND(AVG(p90_age_days) OVER (), 1)                 AS peer_mean_p90,
        ROUND(STDDEV_SAMP(p90_age_days) OVER (), 1)         AS peer_stddev_p90
    FROM sized
)
SELECT
    service_name,
    active_records,
    median_age_days,
    p90_age_days,
    p90_to_median_ratio,
    peer_mean_p90,
    ROUND((p90_age_days - peer_mean_p90) / NULLIF(peer_stddev_p90, 0), 2) AS p90_z_score,
    CASE
        WHEN (p90_age_days - peer_mean_p90) / NULLIF(peer_stddev_p90, 0) >= 1.0
             THEN 'p90 well above peer categories'
        WHEN p90_to_median_ratio >= 5
             THEN 'long tail relative to own median'
        ELSE 'within normal range'
    END AS tail_flag,
    RANK() OVER (ORDER BY p90_age_days DESC) AS rank_by_p90
FROM scored
ORDER BY p90_age_days DESC;

-- -----------------------------------------------------------------------------
-- How concentrated is the active queue? Answers "how few categories account for
-- most of the workload" without hand-picking a cut-off.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TABLE agg_service_concentration AS
WITH ranked AS (
    SELECT
        service_name,
        COUNT(*) AS active_records,
        ROW_NUMBER() OVER (ORDER BY COUNT(*) DESC) AS rn
    FROM v_active
    GROUP BY service_name
),
cumulative AS (
    SELECT
        rn,
        service_name,
        active_records,
        SUM(active_records) OVER (ORDER BY rn ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cum_records,
        SUM(active_records) OVER () AS total_records,
        COUNT(*) OVER () AS total_categories
    FROM ranked
)
SELECT
    'Top ' || rn || ' categories' AS threshold_label,
    rn                            AS n_categories,
    total_categories,
    cum_records,
    total_records,
    ROUND(100.0 * cum_records / total_records, 1) AS cumulative_pct_of_backlog
FROM cumulative
WHERE rn IN (1, 3, 5, 10, 15, 20)
ORDER BY rn;
