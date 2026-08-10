-- =============================================================================
-- 05_geography_analysis.sql
-- Purpose : Locate active workload and aged workload geographically, and
--           separate "large district" from "disproportionately aged district".
-- Depends : 01_clean_base.sql
-- Outputs : agg_geography_district, agg_geography_community,
--           agg_geography_aging_index
--
-- Caveat carried into every output: geography reflects where a problem was
-- reported, not where City resources were deployed. Districts differ in
-- population, street mileage and asset age; none of that is in this dataset, so
-- raw counts are not a like-for-like comparison of service levels.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Council district. Rows with no valid district (1-9) are kept as a labeled
-- group rather than dropped, so the totals still reconcile to the backlog.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TABLE agg_geography_district AS
WITH base AS (
    SELECT
        COALESCE(CAST(council_district AS VARCHAR), '(Unknown)') AS council_district,
        COUNT(*)                                                 AS active_records,
        COUNT(DISTINCT issue_key)                                AS active_distinct_issues,
        MEDIAN(active_age_days)                                  AS median_age_days,
        QUANTILE_CONT(active_age_days, 0.90)                     AS p90_age_days,
        COUNT(*) FILTER (WHERE active_age_days >= 60)            AS aged_60_plus,
        COUNT(*) FILTER (WHERE active_age_days >= 90)            AS aged_90_plus,
        COUNT(*) FILTER (WHERE active_age_days >= 365)           AS aged_365_plus,
        COUNT(*) FILTER (WHERE is_duplicate_child)               AS duplicate_children
    FROM v_active
    GROUP BY 1
),
demand AS (
    -- Submission volume over the last complete 12 months, for context on whether
    -- a large backlog simply reflects a large inflow.
    SELECT
        COALESCE(CAST(council_district AS VARCHAR), '(Unknown)') AS council_district,
        COUNT(*) AS submissions_last_12_months
    FROM fct_requests
    WHERE requested_date >= (SELECT snapshot_date - INTERVAL 12 MONTH FROM ref_snapshot)
    GROUP BY 1
)
SELECT
    b.council_district,
    b.active_records,
    b.active_distinct_issues,
    ROUND(100.0 * b.active_records / SUM(b.active_records) OVER (), 1) AS pct_of_active_backlog,
    COALESCE(d.submissions_last_12_months, 0)                          AS submissions_last_12_months,
    ROUND(100.0 * COALESCE(d.submissions_last_12_months, 0)
          / NULLIF(SUM(d.submissions_last_12_months) OVER (), 0), 1)   AS pct_of_recent_demand,
    -- Active records carried per unit of recent demand. A descriptive stock-to-
    -- recent-inflow ratio, NOT a clearance or throughput rate: numerator and
    -- denominator cover different populations over different time bases, and no
    -- exit rate is observable in this source. It distinguishes a district that
    -- simply receives many requests from one holding a large active inventory
    -- relative to its recent volume.
    ROUND(1.0 * b.active_records
          / NULLIF(d.submissions_last_12_months, 0), 3)                AS backlog_per_recent_submission,
    b.median_age_days,
    b.p90_age_days,
    b.aged_60_plus,
    b.aged_90_plus,
    b.aged_365_plus,
    ROUND(100.0 * b.aged_90_plus / NULLIF(b.active_records, 0), 1)     AS pct_aged_90_plus,
    ROUND(100.0 * b.aged_90_plus / SUM(b.aged_90_plus) OVER (), 1)     AS pct_of_aged_90_backlog,
    b.duplicate_children,
    ROUND(100.0 * b.duplicate_children / NULLIF(b.active_records, 0), 1) AS duplicate_rate_pct,
    RANK() OVER (ORDER BY b.active_records DESC)                       AS rank_by_backlog,
    RANK() OVER (ORDER BY b.median_age_days DESC)                      AS rank_by_median_age
FROM base AS b
LEFT JOIN demand AS d USING (council_district)
ORDER BY b.active_records DESC;

-- -----------------------------------------------------------------------------
-- Community planning area. Finer than a council district and closer to how
-- residents describe where they live. Limited to areas with enough active
-- records for the percentiles to mean anything.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TABLE agg_geography_community AS
SELECT
    community,
    -- A community can cross district boundaries. Report its modal district and
    -- resolve exact frequency ties by the label so repeat builds are stable.
    MODE(COALESCE(CAST(council_district AS VARCHAR), '(Unknown)')
         ORDER BY COALESCE(CAST(council_district AS VARCHAR), '(Unknown)')) AS example_council_district,
    COUNT(*)                                                      AS active_records,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2)            AS pct_of_active_backlog,
    MEDIAN(active_age_days)                                       AS median_age_days,
    QUANTILE_CONT(active_age_days, 0.90)                          AS p90_age_days,
    COUNT(*) FILTER (WHERE active_age_days >= 90)                 AS aged_90_plus,
    ROUND(100.0 * COUNT(*) FILTER (WHERE active_age_days >= 90)
          / NULLIF(COUNT(*), 0), 1)                               AS pct_aged_90_plus,
    RANK() OVER (ORDER BY COUNT(*) DESC)                          AS rank_by_backlog
FROM v_active
GROUP BY community
HAVING COUNT(*) >= 100
ORDER BY active_records DESC, community;

-- -----------------------------------------------------------------------------
-- Aged-backlog concentration index.
--
--   index = (area's share of aged 90+ backlog) / (area's share of all active
--            backlog)
--
-- An index of 1.0 means the area holds exactly the share of aged work its total
-- queue size would imply. Above 1.0 means its queue skews older than the city
-- average. This is the metric that answers "unusually aged", as opposed to
-- simply "large", and it is unit-free so districts of different sizes compare.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TABLE agg_geography_aging_index AS
WITH district AS (
    SELECT
        COALESCE(CAST(council_district AS VARCHAR), '(Unknown)') AS area,
        'Council district' AS area_type,
        COUNT(*) AS active_records,
        COUNT(*) FILTER (WHERE active_age_days >= 90) AS aged_90_plus,
        MEDIAN(active_age_days) AS median_age_days
    FROM v_active
    GROUP BY 1
),
community AS (
    SELECT
        community AS area,
        'Community planning area' AS area_type,
        COUNT(*) AS active_records,
        COUNT(*) FILTER (WHERE active_age_days >= 90) AS aged_90_plus,
        MEDIAN(active_age_days) AS median_age_days
    FROM v_active
    GROUP BY 1
    HAVING COUNT(*) >= 500
),
stacked AS (
    SELECT * FROM district
    UNION ALL
    SELECT * FROM community
),
-- Shares are materialised in their own step because a window function cannot be
-- nested inside another window's ORDER BY.
shared AS (
    SELECT
        s.*,
        1.0 * active_records / NULLIF(SUM(active_records) OVER (PARTITION BY area_type), 0) AS share_of_backlog,
        1.0 * aged_90_plus   / NULLIF(SUM(aged_90_plus)   OVER (PARTITION BY area_type), 0) AS share_of_aged_90
    FROM stacked AS s
),
indexed AS (
    SELECT
        sh.*,
        share_of_aged_90 / NULLIF(share_of_backlog, 0) AS aged_concentration_index
    FROM shared AS sh
)
SELECT
    area_type,
    area,
    active_records,
    aged_90_plus,
    median_age_days,
    ROUND(100.0 * share_of_backlog, 2)   AS pct_of_backlog,
    ROUND(100.0 * share_of_aged_90, 2)   AS pct_of_aged_90,
    ROUND(aged_concentration_index, 3)   AS aged_concentration_index,
    RANK() OVER (PARTITION BY area_type ORDER BY aged_concentration_index DESC) AS rank_by_index
FROM indexed
ORDER BY area_type, aged_concentration_index DESC, area;
