-- =============================================================================
-- 09_trends.sql
-- Purpose : Measure demand over time only where the three extracts in scope give
--           complete coverage of a submission month, and make the incomplete
--           months visibly incomplete rather than quietly wrong.
-- Depends : 01_clean_base.sql
-- Outputs : agg_demand_monthly, agg_demand_yoy, agg_demand_yoy_by_service,
--           agg_closure_monthly
--
-- Coverage logic — the single most important caveat on this file:
--   The scope is {open} + {closed in 2026} + {closed in 2025}. A request
--   submitted on or after 2025-01-01 must be either still open, or closed in
--   2025, or closed in 2026 — it cannot have closed before it was submitted. So
--   every submission month from January 2025 onward is fully covered.
--   Submission months before 2025 are NOT covered: a request submitted in 2024
--   and closed in 2024 is in none of the three files. Those months are flagged
--   and must not be read as a decline in demand.
-- =============================================================================

CREATE OR REPLACE TABLE agg_demand_monthly AS
WITH snap AS (
    SELECT snapshot_date FROM ref_snapshot
),
monthly AS (
    SELECT
        requested_month_start                       AS month_start,
        COUNT(*)                                    AS submissions,
        COUNT(DISTINCT issue_key)                   AS distinct_issues,
        COUNT(*) FILTER (WHERE is_duplicate_child)  AS duplicate_children,
        COUNT(*) FILTER (WHERE is_active)           AS still_active,
        -- Named referred_records rather than a bare `referred`: the source
        -- column called `referred` is free text this project suppresses, and
        -- reusing the bare name in an output would trip the privacy check for
        -- the wrong reason.
        COUNT(*) FILTER (WHERE status = 'Referred') AS referred_records
    FROM fct_requests
    GROUP BY 1
)
SELECT
    m.month_start,
    YEAR(m.month_start)  AS month_year,
    MONTH(m.month_start) AS month_number,
    m.submissions,
    m.distinct_issues,
    m.duplicate_children,
    m.still_active,
    m.referred_records,
    ROUND(100.0 * m.still_active / NULLIF(m.submissions, 0), 1) AS pct_still_active,
    CASE
        WHEN m.month_start < DATE '2025-01-01'
            THEN 'incomplete - closures before 2025 are out of scope'
        WHEN m.month_start >= DATE_TRUNC('month', (SELECT snapshot_date FROM snap))
            THEN 'incomplete - month still in progress at snapshot'
        ELSE 'complete'
    END AS coverage_status
FROM monthly AS m
WHERE m.month_start >= DATE '2024-01-01'
ORDER BY m.month_start;

-- -----------------------------------------------------------------------------
-- Year-over-year on like-for-like months only: January through the last month
-- that had fully elapsed at the snapshot date.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TABLE agg_demand_yoy AS
WITH snap AS (
    SELECT snapshot_date, MONTH(snapshot_date) - 1 AS last_complete_month
    FROM ref_snapshot
),
windowed AS (
    SELECT
        f.requested_year,
        f.requested_month,
        COUNT(*)                  AS submissions,
        COUNT(DISTINCT issue_key) AS distinct_issues
    FROM fct_requests AS f
    CROSS JOIN snap AS s
    WHERE f.requested_month <= s.last_complete_month
      AND f.requested_year IN (YEAR(s.snapshot_date), YEAR(s.snapshot_date) - 1)
    GROUP BY 1, 2
),
by_year AS (
    SELECT
        requested_year,
        SUM(submissions)     AS submissions,
        SUM(distinct_issues) AS distinct_issues
    FROM windowed
    GROUP BY 1
)
SELECT
    (SELECT 'Jan-' || MONTHNAME(MAKE_DATE(2000, last_complete_month, 1)) FROM snap) AS comparison_window,
    requested_year,
    submissions,
    distinct_issues,
    LAG(submissions)     OVER (ORDER BY requested_year) AS prior_year_submissions,
    submissions - LAG(submissions) OVER (ORDER BY requested_year) AS change_submissions,
    ROUND(100.0 * (submissions - LAG(submissions) OVER (ORDER BY requested_year))
          / NULLIF(LAG(submissions) OVER (ORDER BY requested_year), 0), 1) AS change_pct,
    ROUND(100.0 * (distinct_issues - LAG(distinct_issues) OVER (ORDER BY requested_year))
          / NULLIF(LAG(distinct_issues) OVER (ORDER BY requested_year), 0), 1) AS change_pct_distinct_issues
FROM by_year
ORDER BY requested_year;

-- -----------------------------------------------------------------------------
-- Which categories drove the year-over-year movement.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TABLE agg_demand_yoy_by_service AS
WITH snap AS (
    SELECT snapshot_date, MONTH(snapshot_date) - 1 AS last_complete_month FROM ref_snapshot
),
windowed AS (
    SELECT
        f.service_name,
        f.requested_year,
        COUNT(*) AS submissions
    FROM fct_requests AS f
    CROSS JOIN snap AS s
    WHERE f.requested_month <= s.last_complete_month
      AND f.requested_year IN (YEAR(s.snapshot_date), YEAR(s.snapshot_date) - 1)
    GROUP BY 1, 2
),
pivoted AS (
    SELECT
        service_name,
        SUM(CASE WHEN requested_year = (SELECT YEAR(snapshot_date) FROM snap)
                 THEN submissions ELSE 0 END) AS submissions_current,
        SUM(CASE WHEN requested_year = (SELECT YEAR(snapshot_date) - 1 FROM snap)
                 THEN submissions ELSE 0 END) AS submissions_prior
    FROM windowed
    GROUP BY service_name
),
-- Taxonomy-stability control. Between September and December 2025 the City
-- migrated volume between service names (most visibly Parking Violation ->
-- Parking - 72-Hours). A category whose share of *citywide* submissions moved
-- sharply between the two windows has been relabelled, and its year-over-year
-- change measures the relabelling rather than resident demand.
--
-- Share is taken against citywide volume rather than against the category's
-- case_record_type on purpose: audit check DQ-08 established that service_name
-- and case_record_type are a many-to-many pair, so "share of its own record
-- type" has no single well-defined denominator.
share_of_citywide AS (
    SELECT
        f.service_name,
        1.0 * COUNT(*) FILTER (WHERE f.requested_year = (SELECT YEAR(snapshot_date) - 1 FROM snap))
            / NULLIF(SUM(COUNT(*) FILTER (WHERE f.requested_year = (SELECT YEAR(snapshot_date) - 1 FROM snap)))
                     OVER (), 0) AS share_prior,
        1.0 * COUNT(*) FILTER (WHERE f.requested_year = (SELECT YEAR(snapshot_date) FROM snap))
            / NULLIF(SUM(COUNT(*) FILTER (WHERE f.requested_year = (SELECT YEAR(snapshot_date) FROM snap)))
                     OVER (), 0) AS share_current
    FROM fct_requests AS f
    CROSS JOIN snap AS s
    WHERE f.requested_month <= s.last_complete_month
      AND f.requested_year IN (YEAR(s.snapshot_date), YEAR(s.snapshot_date) - 1)
    GROUP BY f.service_name
)
SELECT
    p.service_name,
    p.submissions_prior,
    p.submissions_current,
    p.submissions_current - p.submissions_prior AS change_submissions,
    ROUND(100.0 * (p.submissions_current - p.submissions_prior)
          / NULLIF(p.submissions_prior, 0), 1) AS change_pct,
    ROUND(100.0 * (p.submissions_current - p.submissions_prior)
          / NULLIF(SUM(p.submissions_current - p.submissions_prior) OVER (), 0), 1)
        AS share_of_total_change_pct,
    ROUND(100.0 * COALESCE(w.share_prior, 0), 2)   AS pct_of_citywide_prior,
    ROUND(100.0 * COALESCE(w.share_current, 0), 2) AS pct_of_citywide_current,
    ROUND(100.0 * (COALESCE(w.share_current, 0) - COALESCE(w.share_prior, 0)), 2)
        AS share_shift_pp,
    -- Flag ladder, most specific first. Anything not marked "comparable" must
    -- not be quoted as a demand change without first checking the category
    -- against the City's service taxonomy. The flag says the number is not
    -- trustworthy on its own; it does not diagnose why.
    CASE
        WHEN p.submissions_current = 0 AND p.submissions_prior > 0
            THEN 'DISCONTINUED - no current-year records under this label'
        WHEN p.submissions_prior = 0
            THEN 'NEW CATEGORY - no prior-year baseline'
        WHEN p.submissions_prior < 100 AND p.submissions_current >= 500
            THEN 'NEWLY ADOPTED - negligible prior-year base'
        -- A structural break needs both tests. Share alone is not enough: when
        -- citywide demand grows, a category with flat volume loses share without
        -- anything having changed about the category itself.
        WHEN ABS(COALESCE(w.share_current, 0) - COALESCE(w.share_prior, 0)) >= 0.02
             AND ABS(100.0 * (p.submissions_current - p.submissions_prior)
                     / NULLIF(p.submissions_prior, 0)) >= 25
            THEN 'STRUCTURAL BREAK - share and volume both moved sharply'
        WHEN ABS(100.0 * (p.submissions_current - p.submissions_prior)
                 / NULLIF(p.submissions_prior, 0)) >= 200
            THEN 'VOLATILE - verify against service taxonomy before reporting'
        ELSE 'comparable'
    END AS taxonomy_flag,
    RANK() OVER (ORDER BY p.submissions_current - p.submissions_prior DESC) AS rank_by_absolute_growth
FROM pivoted AS p
LEFT JOIN share_of_citywide AS w USING (service_name)
WHERE p.submissions_prior >= 500 OR p.submissions_current >= 500
ORDER BY change_submissions DESC;

-- -----------------------------------------------------------------------------
-- The same year-over-year comparison at case_record_type grain. Record type is
-- the department-level grouping and did not absorb the service-name migration,
-- so this is the comparison that can be reported without a caveat attached to
-- every row.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TABLE agg_demand_yoy_by_record_type AS
WITH snap AS (
    SELECT snapshot_date, MONTH(snapshot_date) - 1 AS last_complete_month FROM ref_snapshot
),
pivoted AS (
    SELECT
        f.case_record_type,
        COUNT(*) FILTER (WHERE f.requested_year = (SELECT YEAR(snapshot_date) - 1 FROM snap))
            AS submissions_prior,
        COUNT(*) FILTER (WHERE f.requested_year = (SELECT YEAR(snapshot_date) FROM snap))
            AS submissions_current
    FROM fct_requests AS f
    CROSS JOIN snap AS s
    WHERE f.requested_month <= s.last_complete_month
      AND f.requested_year IN (YEAR(s.snapshot_date), YEAR(s.snapshot_date) - 1)
    GROUP BY f.case_record_type
)
SELECT
    case_record_type,
    submissions_prior,
    submissions_current,
    submissions_current - submissions_prior AS change_submissions,
    ROUND(100.0 * (submissions_current - submissions_prior)
          / NULLIF(submissions_prior, 0), 1) AS change_pct,
    ROUND(100.0 * submissions_current / SUM(submissions_current) OVER (), 1)
        AS pct_of_current_demand,
    ROUND(100.0 * (submissions_current - submissions_prior)
          / NULLIF(SUM(submissions_current - submissions_prior) OVER (), 0), 1)
        AS share_of_total_change_pct,
    RANK() OVER (ORDER BY submissions_current - submissions_prior DESC) AS rank_by_absolute_growth
FROM pivoted
WHERE submissions_prior >= 250 OR submissions_current >= 250
ORDER BY change_submissions DESC;

-- -----------------------------------------------------------------------------
-- Closure-cohort bias.
--
-- "Median lifecycle of cases closed this year" is the obvious throughput metric
-- and it is misleading on its own: a closure cohort is dominated by cases that
-- closed quickly, because slow cases are still open and therefore absent. This
-- table decomposes the current year's closures by the year they were submitted
-- so the size of that bias is visible rather than assumed.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TABLE agg_closure_cohort_bias AS
SELECT
    requested_year                                          AS submitted_year,
    COUNT(*)                                                AS closures_recorded,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1)      AS pct_of_closures,
    MEDIAN(lifecycle_days)                                  AS median_lifecycle_days,
    QUANTILE_CONT(lifecycle_days, 0.90)                     AS p90_lifecycle_days
FROM v_resolved
WHERE closed_year = (SELECT YEAR(snapshot_date) FROM ref_snapshot)
GROUP BY requested_year
ORDER BY submitted_year DESC;

-- -----------------------------------------------------------------------------
-- Submission-cohort view — the unbiased complement to the table above.
--
-- Takes every request submitted in a given period and asks what has become of
-- it. Because the denominator is fixed at submission time, this cannot be
-- flattered by slow cases being absent. The cohort is cut off before the
-- snapshot month so that every request in it has had comparable time to resolve.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TABLE agg_submission_cohort AS
WITH snap AS (
    SELECT snapshot_date, MONTH(snapshot_date) - 2 AS cohort_last_month FROM ref_snapshot
),
cohort AS (
    SELECT f.*
    FROM fct_requests AS f
    CROSS JOIN snap AS s
    WHERE f.requested_year = YEAR(s.snapshot_date)
      AND f.requested_month <= s.cohort_last_month
)
SELECT
    (SELECT 'Submitted Jan-' || MONTHNAME(MAKE_DATE(2000, cohort_last_month, 1))
            || ' ' || YEAR(snapshot_date) FROM snap)        AS cohort,
    COUNT(*)                                                AS submissions,
    COUNT(*) FILTER (WHERE status = 'Closed')               AS now_closed,
    COUNT(*) FILTER (WHERE status = 'Referred')             AS now_referred,
    COUNT(*) FILTER (WHERE is_active)                       AS still_active,
    ROUND(100.0 * COUNT(*) FILTER (WHERE is_resolved) / NULLIF(COUNT(*), 0), 1)
                                                            AS pct_resolved,
    ROUND(100.0 * COUNT(*) FILTER (WHERE is_active) / NULLIF(COUNT(*), 0), 1)
                                                            AS pct_still_active,
    MEDIAN(lifecycle_days) FILTER (WHERE is_resolved)       AS median_lifecycle_days,
    QUANTILE_CONT(lifecycle_days, 0.90) FILTER (WHERE is_resolved)
                                                            AS p90_lifecycle_days
FROM cohort;

-- -----------------------------------------------------------------------------
-- Recorded closures by month. Coverage here is the mirror image of demand: the
-- scope covers closures in 2025 and 2026 completely and nothing before.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TABLE agg_closure_monthly AS
SELECT
    closed_month_start AS month_start,
    COUNT(*)                                     AS closures_recorded,
    COUNT(*) FILTER (WHERE status = 'Closed')    AS closed_status,
    COUNT(*) FILTER (WHERE status = 'Referred')  AS referred_status,
    MEDIAN(lifecycle_days)                       AS median_lifecycle_days,
    QUANTILE_CONT(lifecycle_days, 0.90)          AS p90_lifecycle_days,
    CASE
        WHEN closed_month_start >= DATE_TRUNC('month', (SELECT snapshot_date FROM ref_snapshot))
            THEN 'incomplete - month still in progress at snapshot'
        ELSE 'complete'
    END AS coverage_status
FROM v_resolved
WHERE closed_month_start IS NOT NULL
GROUP BY closed_month_start
ORDER BY month_start;
