-- =============================================================================
-- 06_duplicates.sql
-- Purpose : Quantify repeat reporting, and test whether collapsing duplicate
--           children onto their parent changes the conclusions leadership would
--           draw. If it does not, the simpler case-record count can be used.
-- Depends : 01_clean_base.sql
-- Outputs : agg_duplicate_summary, agg_duplicate_by_service,
--           agg_duplicate_rank_impact, agg_duplicate_cluster_size
--
-- Definition: a duplicate child is a case record whose service_request_parent_id
-- is populated. The City sets this when a report is judged to describe an issue
-- already reported and still open. It is the City's determination, not one made
-- in this analysis.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Headline duplicate volumes, all records and active only.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TABLE agg_duplicate_summary AS
SELECT
    'All case records in scope' AS population,
    COUNT(*)                                                    AS case_records,
    COUNT(DISTINCT issue_key)                                   AS distinct_issues,
    COUNT(*) FILTER (WHERE is_duplicate_child)                  AS duplicate_children,
    ROUND(100.0 * COUNT(*) FILTER (WHERE is_duplicate_child)
          / NULLIF(COUNT(*), 0), 2)                             AS duplicate_rate_pct,
    ROUND(100.0 * (COUNT(*) - COUNT(DISTINCT issue_key))
          / NULLIF(COUNT(*), 0), 2)                             AS pct_volume_removed_by_collapsing
FROM fct_requests

UNION ALL

SELECT
    'Active backlog only',
    COUNT(*),
    COUNT(DISTINCT issue_key),
    COUNT(*) FILTER (WHERE is_duplicate_child),
    ROUND(100.0 * COUNT(*) FILTER (WHERE is_duplicate_child) / NULLIF(COUNT(*), 0), 2),
    ROUND(100.0 * (COUNT(*) - COUNT(DISTINCT issue_key)) / NULLIF(COUNT(*), 0), 2)
FROM v_active

UNION ALL

SELECT
    'Resolved case records',
    COUNT(*),
    COUNT(DISTINCT issue_key),
    COUNT(*) FILTER (WHERE is_duplicate_child),
    ROUND(100.0 * COUNT(*) FILTER (WHERE is_duplicate_child) / NULLIF(COUNT(*), 0), 2),
    ROUND(100.0 * (COUNT(*) - COUNT(DISTINCT issue_key)) / NULLIF(COUNT(*), 0), 2)
FROM v_resolved;

-- -----------------------------------------------------------------------------
-- Which service categories attract repeat reports. A high duplicate rate is a
-- signal about visibility and resident frustration, not about the work itself:
-- highly visible problems on busy streets get reported many times.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TABLE agg_duplicate_by_service AS
SELECT
    service_name,
    COUNT(*)                                                     AS active_records,
    COUNT(DISTINCT issue_key)                                    AS active_distinct_issues,
    COUNT(*) FILTER (WHERE is_duplicate_child)                   AS duplicate_children,
    ROUND(100.0 * COUNT(*) FILTER (WHERE is_duplicate_child)
          / NULLIF(COUNT(*), 0), 1)                              AS duplicate_rate_pct,
    ROUND(1.0 * COUNT(*) / NULLIF(COUNT(DISTINCT issue_key), 0), 2) AS records_per_issue,
    MEDIAN(active_age_days)                                      AS median_age_days
FROM v_active
GROUP BY service_name
HAVING COUNT(*) >= 250
ORDER BY duplicate_rate_pct DESC;

-- -----------------------------------------------------------------------------
-- Materiality test for question 8: does collapsing duplicates reorder the
-- category ranking leadership would act on? Compares rank on case records with
-- rank on distinct issues.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TABLE agg_duplicate_rank_impact AS
WITH by_service AS (
    SELECT
        service_name,
        COUNT(*)                  AS active_records,
        COUNT(DISTINCT issue_key) AS active_distinct_issues
    FROM v_active
    GROUP BY service_name
),
ranked AS (
    SELECT
        service_name,
        active_records,
        active_distinct_issues,
        RANK() OVER (ORDER BY active_records DESC)          AS rank_case_records,
        RANK() OVER (ORDER BY active_distinct_issues DESC)  AS rank_distinct_issues
    FROM by_service
)
SELECT
    service_name,
    active_records,
    active_distinct_issues,
    active_records - active_distinct_issues AS records_removed_by_collapsing,
    rank_case_records,
    rank_distinct_issues,
    rank_case_records - rank_distinct_issues AS rank_shift,
    CASE WHEN rank_case_records = rank_distinct_issues THEN 'unchanged' ELSE 'moved' END AS rank_status
FROM ranked
WHERE rank_case_records <= 20 OR rank_distinct_issues <= 20
ORDER BY rank_case_records;

-- -----------------------------------------------------------------------------
-- Cluster size: how many case records attach to a single reported issue. Shows
-- whether repeat reporting is broad and shallow or driven by a few hotspots.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TABLE agg_duplicate_cluster_size AS
WITH clusters AS (
    SELECT issue_key, COUNT(*) AS n_case_records
    FROM fct_requests
    GROUP BY issue_key
),
binned AS (
    SELECT
        CASE
            WHEN n_case_records = 1 THEN '1 (no duplicate)'
            WHEN n_case_records = 2 THEN '2'
            WHEN n_case_records BETWEEN 3 AND 5 THEN '3-5'
            WHEN n_case_records BETWEEN 6 AND 10 THEN '6-10'
            ELSE '11+'
        END AS cluster_size_band,
        MIN(n_case_records) AS band_min,
        COUNT(*)            AS n_issues,
        SUM(n_case_records) AS n_case_records
    FROM clusters
    GROUP BY 1
)
SELECT
    cluster_size_band,
    n_issues,
    n_case_records,
    ROUND(100.0 * n_issues / SUM(n_issues) OVER (), 2)             AS pct_of_issues,
    ROUND(100.0 * n_case_records / SUM(n_case_records) OVER (), 2) AS pct_of_case_records
FROM binned
ORDER BY band_min;
