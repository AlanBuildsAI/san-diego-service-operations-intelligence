-- =============================================================================
-- 02_executive_kpis.sql
-- Purpose : Single long-format table of headline operating metrics. Every number
--           quoted in the README, the executive memo and the dashboard traces
--           back to a row in agg_executive_kpis.
-- Depends : 01_clean_base.sql
-- Output  : agg_executive_kpis (metric_key, metric_label, value, unit, grouping)
--
-- Long format is deliberate: it keeps one authoritative value per metric key,
-- which is what scripts/verify_claims.py checks the written documents against.
-- =============================================================================

CREATE OR REPLACE TABLE agg_executive_kpis AS
WITH snap AS (
    SELECT snapshot_date FROM ref_snapshot
),
active AS (
    SELECT * FROM v_active
),
resolved_ytd AS (
    -- Cases with a recorded closure in the current snapshot year.
    SELECT *
    FROM v_resolved
    WHERE closed_year = (SELECT YEAR(snapshot_date) FROM snap)
),
demand_window AS (
    -- Completed-month demand for the current year and the same months last year.
    SELECT
        requested_year,
        COUNT(*) AS n_records,
        COUNT(DISTINCT issue_key) AS n_issues
    FROM fct_requests
    WHERE requested_month <= (SELECT MONTH(snapshot_date) - 1 FROM snap)
      AND requested_year IN (
            (SELECT YEAR(snapshot_date) FROM snap),
            (SELECT YEAR(snapshot_date) - 1 FROM snap))
    GROUP BY 1
),
yoy AS (
    SELECT
        MAX(CASE WHEN requested_year = (SELECT YEAR(snapshot_date) FROM snap)
                 THEN n_records END) AS curr_records,
        MAX(CASE WHEN requested_year = (SELECT YEAR(snapshot_date) - 1 FROM snap)
                 THEN n_records END) AS prior_records
    FROM demand_window
),
metrics AS (
    SELECT 'snapshot_date' AS metric_key,
           'Data snapshot date' AS metric_label,
           CAST(EPOCH(snapshot_date) AS DOUBLE) AS value,
           'epoch_seconds' AS unit,
           'context' AS grouping
    FROM snap

    UNION ALL SELECT 'total_case_records', 'Case records in scope (all statuses)',
           CAST(COUNT(*) AS DOUBLE), 'records', 'scope' FROM fct_requests

    UNION ALL SELECT 'total_distinct_issues', 'Distinct reported issues in scope (duplicates collapsed)',
           CAST(COUNT(DISTINCT issue_key) AS DOUBLE), 'issues', 'scope' FROM fct_requests

    UNION ALL SELECT 'active_backlog', 'Active request backlog (case records)',
           CAST(COUNT(*) AS DOUBLE), 'records', 'backlog' FROM active

    UNION ALL SELECT 'active_backlog_distinct_issues', 'Active backlog, duplicates collapsed',
           CAST(COUNT(DISTINCT issue_key) AS DOUBLE), 'issues', 'backlog' FROM active

    UNION ALL SELECT 'active_median_age_days', 'Median active request age',
           CAST(MEDIAN(active_age_days) AS DOUBLE), 'days', 'backlog' FROM active

    UNION ALL SELECT 'active_p90_age_days', 'P90 active request age',
           CAST(QUANTILE_CONT(active_age_days, 0.90) AS DOUBLE), 'days', 'backlog' FROM active

    UNION ALL SELECT 'active_mean_age_days', 'Mean active request age (reported for contrast only)',
           CAST(AVG(active_age_days) AS DOUBLE), 'days', 'backlog' FROM active

    UNION ALL SELECT 'active_aged_60_plus', 'Active requests aged 60+ days',
           CAST(COUNT(*) FILTER (WHERE active_age_days >= 60) AS DOUBLE), 'records', 'backlog' FROM active

    UNION ALL SELECT 'active_aged_60_plus_pct', 'Share of active backlog aged 60+ days',
           ROUND(100.0 * COUNT(*) FILTER (WHERE active_age_days >= 60) / NULLIF(COUNT(*), 0), 1),
           'percent', 'backlog' FROM active

    UNION ALL SELECT 'active_aged_90_plus', 'Active requests aged 90+ days',
           CAST(COUNT(*) FILTER (WHERE active_age_days >= 90) AS DOUBLE), 'records', 'backlog' FROM active

    UNION ALL SELECT 'active_aged_90_plus_pct', 'Share of active backlog aged 90+ days',
           ROUND(100.0 * COUNT(*) FILTER (WHERE active_age_days >= 90) / NULLIF(COUNT(*), 0), 1),
           'percent', 'backlog' FROM active

    UNION ALL SELECT 'active_aged_365_plus', 'Active requests aged 365+ days',
           CAST(COUNT(*) FILTER (WHERE active_age_days >= 365) AS DOUBLE), 'records', 'backlog' FROM active

    UNION ALL SELECT 'active_aged_365_plus_pct', 'Share of active backlog aged 365+ days',
           ROUND(100.0 * COUNT(*) FILTER (WHERE active_age_days >= 365) / NULLIF(COUNT(*), 0), 1),
           'percent', 'backlog' FROM active

    UNION ALL SELECT 'duplicate_children_total', 'Case records flagged as duplicate children (all statuses)',
           CAST(COUNT(*) FILTER (WHERE is_duplicate_child) AS DOUBLE), 'records', 'duplicates' FROM fct_requests

    UNION ALL SELECT 'duplicate_rate_total_pct', 'Duplicate-child rate, all case records',
           ROUND(100.0 * COUNT(*) FILTER (WHERE is_duplicate_child) / NULLIF(COUNT(*), 0), 1),
           'percent', 'duplicates' FROM fct_requests

    UNION ALL SELECT 'duplicate_children_active', 'Active case records flagged as duplicate children',
           CAST(COUNT(*) FILTER (WHERE is_duplicate_child) AS DOUBLE), 'records', 'duplicates' FROM active

    UNION ALL SELECT 'duplicate_rate_active_pct', 'Duplicate-child rate within the active backlog',
           ROUND(100.0 * COUNT(*) FILTER (WHERE is_duplicate_child) / NULLIF(COUNT(*), 0), 1),
           'percent', 'duplicates' FROM active

    UNION ALL SELECT 'referred_records_total', 'Case records with a Referred status',
           CAST(COUNT(*) FILTER (WHERE status = 'Referred') AS DOUBLE), 'records', 'referrals' FROM fct_requests

    UNION ALL SELECT 'referred_rate_resolved_pct', 'Referred share of resolved case records',
           ROUND(100.0 * COUNT(*) FILTER (WHERE status = 'Referred') / NULLIF(COUNT(*), 0), 1),
           'percent', 'referrals' FROM v_resolved

    UNION ALL SELECT 'referred_external_pct', 'Referred cases routed outside the City',
           ROUND(100.0 * COUNT(*) FILTER (WHERE referral_scope = 'External (non-City entity)')
                 / NULLIF(COUNT(*), 0), 1), 'percent', 'referrals'
           FROM fct_requests WHERE status = 'Referred'

    UNION ALL SELECT 'closed_current_year', 'Case records with a recorded closure this year',
           CAST(COUNT(*) AS DOUBLE), 'records', 'throughput' FROM resolved_ytd

    UNION ALL SELECT 'closed_current_year_median_lifecycle', 'Median recorded lifecycle of cases closed this year',
           CAST(MEDIAN(lifecycle_days) AS DOUBLE), 'days', 'throughput' FROM resolved_ytd

    UNION ALL SELECT 'closed_current_year_p90_lifecycle', 'P90 recorded lifecycle of cases closed this year',
           CAST(QUANTILE_CONT(lifecycle_days, 0.90) AS DOUBLE), 'days', 'throughput' FROM resolved_ytd

    UNION ALL SELECT 'demand_ytd_current', 'Submissions, January to last complete month, current year',
           CAST(curr_records AS DOUBLE), 'records', 'demand' FROM yoy

    UNION ALL SELECT 'demand_ytd_prior', 'Submissions, same months, prior year',
           CAST(prior_records AS DOUBLE), 'records', 'demand' FROM yoy

    UNION ALL SELECT 'demand_yoy_change_pct', 'Year-over-year change in submissions, like-for-like months',
           ROUND(100.0 * (curr_records - prior_records) / NULLIF(prior_records, 0), 1),
           'percent', 'demand' FROM yoy
)
SELECT
    metric_key,
    metric_label,
    ROUND(value, 4) AS value,
    unit,
    grouping
FROM metrics;
