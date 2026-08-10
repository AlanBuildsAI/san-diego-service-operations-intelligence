-- =============================================================================
-- 10_priority_table.sql
-- Purpose : Produce a ranked investigation list for leadership, plus the
--           service-by-district cells where aged work is most concentrated.
-- Depends : 01_clean_base.sql
-- Outputs : agg_priority_table, agg_priority_hotspots
--
-- What this list is:    a triage order for where to look first.
-- What this list is not: a performance ranking of teams, or evidence that any
--                        area is under-resourced. This dataset contains no
--                        staffing, budget, cost or work-completion information,
--                        so no such inference is available from it.
--
-- Scoring: each component is converted to a percentile rank across categories
-- (0 = lowest, 1 = highest) so that measures on different units combine without
-- one dominating by scale. Weights are stated here and repeated in
-- 01_business_brief/metric_definitions.md.
--     0.45  share of the citywide 90+ day active backlog held  (how much aged work)
--     0.35  share of the category's own queue aged 90+ days  (how stuck it is)
--     0.20  median active age                                (how old typically)
-- =============================================================================

CREATE OR REPLACE TABLE agg_priority_table AS
-- Citywide totals, computed over EVERY active record with no volume floor.
-- These are the denominators for any column labeled "of city". The scored set
-- below applies a 500-record floor, and using that subset as the denominator for
-- a citywide-labeled metric would overstate each category's share.
WITH citywide AS (
    SELECT
        COUNT(*)                                      AS city_active_records,
        COUNT(*) FILTER (WHERE active_age_days >= 90) AS city_aged_90_plus
    FROM v_active
),
base AS (
    SELECT
        service_name,
        -- Modal, not arbitrary: audit check DQ-08 found service_name and
        -- case_record_type are many-to-many, so ANY_VALUE would pick a record
        -- type at random. MODE returns the one most records actually carry.
        MODE(case_record_type)                         AS most_common_record_type,
        COUNT(*)                                       AS active_records,
        COUNT(DISTINCT issue_key)                      AS active_distinct_issues,
        MEDIAN(active_age_days)                        AS median_age_days,
        QUANTILE_CONT(active_age_days, 0.90)           AS p90_age_days,
        COUNT(*) FILTER (WHERE active_age_days >= 90)  AS aged_90_plus,
        COUNT(*) FILTER (WHERE active_age_days >= 365) AS aged_365_plus,
        COUNT(*) FILTER (WHERE active_age_days <= 30)  AS aged_0_30,
        COUNT(*) FILTER (WHERE is_duplicate_child)     AS duplicate_children
    FROM v_active
    GROUP BY service_name
    HAVING COUNT(*) >= 500          -- volume floor: below this a percentile is noise
),
shares AS (
    SELECT
        b.*,
        c.city_active_records,
        c.city_aged_90_plus,
        -- The reported share, against the citywide 90+ day active inventory.
        1.0 * aged_90_plus / NULLIF(c.city_aged_90_plus, 0)           AS share_of_city_aged_90,
        1.0 * active_records / NULLIF(c.city_active_records, 0)       AS share_of_city_active,
        1.0 * aged_90_plus / NULLIF(active_records, 0)                AS own_queue_aged_90_rate,
        1.0 * duplicate_children / NULLIF(active_records, 0)          AS duplicate_rate
    FROM base AS b
    CROSS JOIN citywide AS c
),
scored AS (
    SELECT
        s.*,
        -- PERCENT_RANK is invariant to the choice of denominator here: both the
        -- citywide and the scored-subset share are aged_90_plus divided by a
        -- constant, so they induce the same ordering. Switching the denominator
        -- corrects the reported percentage without moving the score.
        PERCENT_RANK() OVER (ORDER BY share_of_city_aged_90)  AS pr_aged_volume,
        PERCENT_RANK() OVER (ORDER BY own_queue_aged_90_rate) AS pr_aged_rate,
        PERCENT_RANK() OVER (ORDER BY median_age_days)        AS pr_median_age
    FROM shares AS s
),
composite AS (
    SELECT
        sc.*,
        ROUND(100.0 * (0.45 * pr_aged_volume
                     + 0.35 * pr_aged_rate
                     + 0.20 * pr_median_age), 1) AS priority_score
    FROM scored AS sc
)
SELECT
    RANK() OVER (ORDER BY priority_score DESC) AS investigation_rank,
    service_name,
    most_common_record_type,
    active_records,
    active_distinct_issues,
    ROUND(100.0 * share_of_city_active, 1)                        AS pct_of_city_active_backlog,
    median_age_days,
    p90_age_days,
    aged_90_plus,
    ROUND(100.0 * own_queue_aged_90_rate, 1)                      AS pct_of_own_queue_aged_90,
    -- Denominator is every active record aged 90+ days citywide, with no volume
    -- floor applied, so this column means what its name says.
    ROUND(100.0 * share_of_city_aged_90, 1)                       AS pct_of_city_aged_90_backlog,
    aged_365_plus,
    aged_0_30,
    ROUND(100.0 * duplicate_rate, 1)                              AS duplicate_rate_pct,
    priority_score,
    -- A short, evidence-anchored reason, so the ranking is never presented as an
    -- unexplained score.
    CASE
        WHEN share_of_city_aged_90 >= 0.10 AND own_queue_aged_90_rate >= 0.80
            THEN 'Large share of the aged backlog and almost the entire queue is aged'
        WHEN share_of_city_aged_90 >= 0.10
            THEN 'Holds a large share of the 90+ day active backlog'
        WHEN own_queue_aged_90_rate >= 0.80
            THEN 'Nearly all active requests in this category are 90+ days old'
        WHEN median_age_days >= 365
            THEN 'Typical active request in this category is over a year old'
        WHEN own_queue_aged_90_rate <= 0.30
            THEN 'Most active records are under 90 days; lower priority under this heuristic'
        ELSE 'Mid-range on volume and aging'
    END AS why_flagged
FROM composite
ORDER BY priority_score DESC;

-- -----------------------------------------------------------------------------
-- Hotspots: service category by council district. Uses the same concentration
-- index idea as 05_geography_analysis.sql — observed share of aged work against
-- the share the cell's size would imply — so that big cells do not automatically
-- top the list.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TABLE agg_priority_hotspots AS
WITH cells AS (
    SELECT
        service_name,
        COALESCE(CAST(council_district AS VARCHAR), '(Unknown)') AS council_district,
        COUNT(*)                                                 AS active_records,
        COUNT(*) FILTER (WHERE active_age_days >= 90)            AS aged_90_plus,
        MEDIAN(active_age_days)                                  AS median_age_days,
        QUANTILE_CONT(active_age_days, 0.90)                     AS p90_age_days
    FROM v_active
    GROUP BY 1, 2
    HAVING COUNT(*) >= 200
),
indexed AS (
    SELECT
        c.*,
        SUM(active_records) OVER () AS total_scored_active,
        SUM(aged_90_plus)   OVER () AS total_scored_aged_90,
        ROUND((1.0 * aged_90_plus / NULLIF(SUM(aged_90_plus) OVER (), 0))
              / NULLIF(1.0 * active_records / NULLIF(SUM(active_records) OVER (), 0), 0), 3)
            AS aged_concentration_index
    FROM cells AS c
)
SELECT
    RANK() OVER (ORDER BY aged_90_plus DESC) AS rank_by_aged_volume,
    service_name,
    council_district,
    active_records,
    aged_90_plus,
    ROUND(100.0 * aged_90_plus / NULLIF(active_records, 0), 1) AS pct_aged_90_plus,
    median_age_days,
    p90_age_days,
    aged_concentration_index,
    ROUND(100.0 * aged_90_plus / NULLIF(total_scored_aged_90, 0), 2) AS pct_of_scored_aged_90
FROM indexed
ORDER BY aged_90_plus DESC, service_name, council_district;

-- =============================================================================
-- Weight sensitivity.
--
-- The 0.45 / 0.35 / 0.20 weighting is an analyst judgment, not a derivation.
-- Any claim that the leading categories survive a different weighting has to be
-- tested rather than asserted, so the same three percentile-rank components are
-- recombined under five schemes and the resulting top ranks compared.
--
-- Components (identical in every scheme, only the weights change):
--     pr_aged_volume  share of the citywide 90+ day active backlog held
--     pr_aged_rate    share of the category's own active queue aged 90+ days
--     pr_median_age   median active age
-- =============================================================================
CREATE OR REPLACE TABLE agg_priority_weight_sensitivity AS
WITH citywide AS (
    SELECT COUNT(*) FILTER (WHERE active_age_days >= 90) AS city_aged_90_plus
    FROM v_active
),
base AS (
    SELECT
        service_name,
        COUNT(*)                                      AS active_records,
        MEDIAN(active_age_days)                       AS median_age_days,
        COUNT(*) FILTER (WHERE active_age_days >= 90) AS aged_90_plus
    FROM v_active
    GROUP BY service_name
    HAVING COUNT(*) >= 500
),
components AS (
    SELECT
        b.service_name,
        PERCENT_RANK() OVER (ORDER BY 1.0 * b.aged_90_plus / c.city_aged_90_plus) AS pr_aged_volume,
        PERCENT_RANK() OVER (ORDER BY 1.0 * b.aged_90_plus / b.active_records)    AS pr_aged_rate,
        PERCENT_RANK() OVER (ORDER BY b.median_age_days)                          AS pr_median_age
    FROM base AS b CROSS JOIN citywide AS c
),
schemes(scheme, w_volume, w_rate, w_age) AS (
    VALUES
        ('baseline 0.45 / 0.35 / 0.20',    0.45, 0.35, 0.20),
        ('equal 1/3 each',                 0.3333, 0.3333, 0.3334),
        ('volume-heavy 0.60 / 0.25 / 0.15', 0.60, 0.25, 0.15),
        ('aged-rate-heavy 0.25 / 0.60 / 0.15', 0.25, 0.60, 0.15),
        ('age-heavy 0.25 / 0.25 / 0.50',   0.25, 0.25, 0.50)
),
scored AS (
    SELECT
        s.scheme,
        c.service_name,
        ROUND(100.0 * (s.w_volume * c.pr_aged_volume
                     + s.w_rate   * c.pr_aged_rate
                     + s.w_age    * c.pr_median_age), 1) AS score,
        RANK() OVER (PARTITION BY s.scheme
                     ORDER BY s.w_volume * c.pr_aged_volume
                            + s.w_rate   * c.pr_aged_rate
                            + s.w_age    * c.pr_median_age DESC) AS rank_in_scheme
    FROM components AS c
    CROSS JOIN schemes AS s
)
SELECT
    scheme,
    rank_in_scheme,
    service_name,
    score,
    -- Flags whether this category is in the baseline top three, so a reader can
    -- see membership churn directly rather than inferring it from rank numbers.
    service_name IN (
        SELECT service_name FROM scored
        WHERE scheme = 'baseline 0.45 / 0.35 / 0.20' AND rank_in_scheme <= 3
    ) AS in_baseline_top_3
FROM scored
WHERE rank_in_scheme <= 5
ORDER BY scheme, rank_in_scheme;
