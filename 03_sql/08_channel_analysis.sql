-- =============================================================================
-- 08_channel_analysis.sql
-- Purpose : Test whether submission channel is associated with different volume,
--           status mix or aging — and, critically, whether any apparent channel
--           effect survives controlling for what is being reported.
-- Depends : 01_clean_base.sql
-- Outputs : agg_channel_summary, agg_channel_status_mix, agg_channel_mix_by_service,
--           agg_channel_controlled_comparison
--
-- Interpretation warning built into the design: channel is chosen by the
-- reporter and is confounded with the type of problem being reported. Any raw
-- difference between channels is therefore association, not effect. The
-- controlled comparison below is the honest version of the question.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Volume and aging by published channel.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TABLE agg_channel_summary AS
SELECT
    case_origin,
    ANY_VALUE(channel_group)                                     AS channel_group,
    COUNT(*)                                                     AS case_records,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2)           AS pct_of_all_records,
    COUNT(*) FILTER (WHERE is_active)                            AS active_records,
    ROUND(100.0 * COUNT(*) FILTER (WHERE is_active)
          / NULLIF(COUNT(*), 0), 1)                              AS pct_still_active,
    COUNT(*) FILTER (WHERE is_duplicate_child)                   AS duplicate_children,
    ROUND(100.0 * COUNT(*) FILTER (WHERE is_duplicate_child)
          / NULLIF(COUNT(*), 0), 1)                              AS duplicate_rate_pct,
    MEDIAN(active_age_days)                                      AS median_active_age_days,
    QUANTILE_CONT(active_age_days, 0.90)                         AS p90_active_age_days,
    MEDIAN(lifecycle_days)                                       AS median_lifecycle_days,
    QUANTILE_CONT(lifecycle_days, 0.90)                          AS p90_lifecycle_days
FROM fct_requests
GROUP BY case_origin
ORDER BY case_records DESC;

-- -----------------------------------------------------------------------------
-- Status mix by channel group.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TABLE agg_channel_status_mix AS
SELECT
    channel_group,
    status,
    COUNT(*) AS case_records,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY channel_group), 1)
        AS pct_within_channel_group
FROM fct_requests
GROUP BY channel_group, status
ORDER BY channel_group, case_records DESC;

-- -----------------------------------------------------------------------------
-- What each channel is actually used to report. This is the confounder, made
-- explicit: if Mobile is dominated by street lights and Phone by waste
-- collection, comparing their aging compares service types, not channels.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TABLE agg_channel_mix_by_service AS
WITH top_channels AS (
    SELECT case_origin
    FROM fct_requests
    GROUP BY case_origin
    HAVING COUNT(*) >= 5000
),
top_services AS (
    SELECT service_name
    FROM fct_requests
    GROUP BY service_name
    ORDER BY COUNT(*) DESC
    LIMIT 10
)
SELECT
    f.case_origin,
    f.service_name,
    COUNT(*) AS case_records,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY f.case_origin), 1)
        AS pct_of_channel_volume
FROM fct_requests AS f
JOIN top_channels  AS c ON f.case_origin = c.case_origin
JOIN top_services  AS s ON f.service_name = s.service_name
GROUP BY f.case_origin, f.service_name
ORDER BY f.case_origin, case_records DESC;

-- -----------------------------------------------------------------------------
-- Controlled comparison: within a single service category, do the two main
-- resident channels differ in recorded lifecycle? Holding service category
-- constant removes the largest confounder. Restricted to cells with enough
-- records for the medians to be stable, and to resident channels, since staff
-- and system-generated records are created under different rules.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TABLE agg_channel_controlled_comparison AS
WITH cells AS (
    SELECT
        service_name,
        case_origin,
        COUNT(*)                             AS resolved_records,
        MEDIAN(lifecycle_days)               AS median_lifecycle_days,
        QUANTILE_CONT(lifecycle_days, 0.90)  AS p90_lifecycle_days
    FROM v_resolved
    WHERE case_origin IN ('Mobile', 'Web', 'Phone')
    GROUP BY service_name, case_origin
    HAVING COUNT(*) >= 300
),
pivoted AS (
    SELECT
        service_name,
        MAX(CASE WHEN case_origin = 'Mobile' THEN resolved_records END)      AS mobile_records,
        MAX(CASE WHEN case_origin = 'Mobile' THEN median_lifecycle_days END) AS mobile_median_days,
        MAX(CASE WHEN case_origin = 'Web'    THEN resolved_records END)      AS web_records,
        MAX(CASE WHEN case_origin = 'Web'    THEN median_lifecycle_days END) AS web_median_days,
        MAX(CASE WHEN case_origin = 'Phone'  THEN resolved_records END)      AS phone_records,
        MAX(CASE WHEN case_origin = 'Phone'  THEN median_lifecycle_days END) AS phone_median_days
    FROM cells
    GROUP BY service_name
)
SELECT
    service_name,
    mobile_records, mobile_median_days,
    web_records,    web_median_days,
    phone_records,  phone_median_days,
    mobile_median_days - web_median_days AS mobile_minus_web_days,
    GREATEST(COALESCE(mobile_median_days, 0), COALESCE(web_median_days, 0), COALESCE(phone_median_days, 0))
      - LEAST(COALESCE(mobile_median_days, 1e9), COALESCE(web_median_days, 1e9), COALESCE(phone_median_days, 1e9))
        AS max_channel_gap_days
FROM pivoted
WHERE mobile_records IS NOT NULL AND web_records IS NOT NULL
ORDER BY ABS(mobile_median_days - web_median_days) DESC;

-- -----------------------------------------------------------------------------
-- Summary of the controlled comparison: how large is the channel gap once
-- service category is held constant? Reported as one row so the answer to
-- question 10 is a measured statement rather than an impression formed by
-- scanning a table.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TABLE agg_channel_gap_summary AS
SELECT
    COUNT(*)                                                        AS category_cells_compared,
    MEDIAN(ABS(mobile_minus_web_days))                              AS median_abs_gap_days,
    QUANTILE_CONT(ABS(mobile_minus_web_days), 0.90)                 AS p90_abs_gap_days,
    MAX(ABS(mobile_minus_web_days))                                 AS max_abs_gap_days,
    COUNT(*) FILTER (WHERE ABS(mobile_minus_web_days) <= 20)        AS cells_within_20_days,
    ROUND(100.0 * COUNT(*) FILTER (WHERE ABS(mobile_minus_web_days) <= 20)
          / NULLIF(COUNT(*), 0), 1)                                 AS pct_cells_within_20_days
FROM agg_channel_controlled_comparison;
