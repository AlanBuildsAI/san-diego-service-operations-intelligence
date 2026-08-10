-- =============================================================================
-- 07_referrals.sql
-- Purpose : Size the referral stream, show where referred records go, and test
--           how referrals affect terminal-status lifecycle context.
-- Depends : 01_clean_base.sql
-- Outputs : agg_referral_summary, agg_referral_destinations,
--           agg_referral_by_service, agg_referral_by_district,
--           agg_referral_status_consistency
--
-- Treatment decision: a Referred case has left the Get It Done queue, so it is
-- treated as terminal for backlog purposes but is reported separately from
-- Closed throughout, because a referral records a hand-off, not an outcome.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Referral share of terminal-status records, and how the recorded lifecycle of a referral
-- compares with a closure.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TABLE agg_referral_summary AS
SELECT
    status,
    COUNT(*)                                                AS case_records,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1)      AS pct_of_resolved,
    MEDIAN(lifecycle_days)                                  AS median_lifecycle_days,
    QUANTILE_CONT(lifecycle_days, 0.90)                     AS p90_lifecycle_days,
    COUNT(*) FILTER (WHERE lifecycle_days <= 1)             AS resolved_within_1_day,
    ROUND(100.0 * COUNT(*) FILTER (WHERE lifecycle_days <= 1)
          / NULLIF(COUNT(*), 0), 1)                         AS pct_resolved_within_1_day
FROM v_resolved
GROUP BY status
ORDER BY case_records DESC, status;

-- -----------------------------------------------------------------------------
-- Where referred records are routed. The raw referral message is not exposed; it is
-- normalized to a destination in 01_clean_base.sql because it contains staff and
-- vendor email addresses.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TABLE agg_referral_destinations AS
SELECT
    COALESCE(referral_scope, '(No referral text recorded)') AS referral_scope,
    COALESCE(referred_to, '(No referral text recorded)')    AS referred_to,
    COUNT(*)                                                AS referred_records,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2)      AS pct_of_referrals,
    MEDIAN(lifecycle_days)                                  AS median_lifecycle_days
FROM fct_requests
WHERE status = 'Referred'
GROUP BY 1, 2
ORDER BY referred_records DESC, referral_scope, referred_to;

-- -----------------------------------------------------------------------------
-- Referral rate by service category. A high rate means a large share of what
-- residents report under that category is not the City's to action, which is a
-- routing and expectation-setting question rather than a capacity question.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TABLE agg_referral_by_service AS
SELECT
    service_name,
    COUNT(*)                                                    AS resolved_records,
    COUNT(*) FILTER (WHERE status = 'Referred')                 AS referred_records,
    ROUND(100.0 * COUNT(*) FILTER (WHERE status = 'Referred')
          / NULLIF(COUNT(*), 0), 1)                             AS referral_rate_pct,
    -- The status filter matters: ~3k Closed records also carry referral text, so
    -- filtering on referral_scope alone would overstate these two columns and
    -- break their reconciliation against referred_records.
    COUNT(*) FILTER (WHERE status = 'Referred'
                       AND referral_scope = 'External (non-City entity)') AS referred_external,
    COUNT(*) FILTER (WHERE status = 'Referred'
                       AND referral_scope = 'Internal (City department)') AS referred_internal,
    -- Referred cases carrying no routing text at all. Small, but included so
    -- external + internal + unclassified reconciles exactly to referred_records.
    COUNT(*) FILTER (WHERE status = 'Referred'
                       AND referral_scope IS NULL)                        AS referred_unclassified,
    ROUND(100.0 * COUNT(*) FILTER (WHERE status = 'Referred')
          / NULLIF(SUM(COUNT(*) FILTER (WHERE status = 'Referred')) OVER (), 0), 1)
                                                                AS pct_of_all_referrals,
    RANK() OVER (ORDER BY COUNT(*) FILTER (WHERE status = 'Referred') DESC) AS rank_by_referral_volume
FROM v_resolved
GROUP BY service_name
HAVING COUNT(*) >= 250
ORDER BY referral_rate_pct DESC, service_name;

-- -----------------------------------------------------------------------------
-- Geographic concentration of referrals.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TABLE agg_referral_by_district AS
SELECT
    COALESCE(CAST(council_district AS VARCHAR), '(Unknown)') AS council_district,
    COUNT(*)                                                 AS resolved_records,
    COUNT(*) FILTER (WHERE status = 'Referred')              AS referred_records,
    ROUND(100.0 * COUNT(*) FILTER (WHERE status = 'Referred')
          / NULLIF(COUNT(*), 0), 1)                          AS referral_rate_pct,
    ROUND(100.0 * COUNT(*) FILTER (WHERE status = 'Referred')
          / NULLIF(SUM(COUNT(*) FILTER (WHERE status = 'Referred')) OVER (), 0), 1)
                                                             AS pct_of_all_referrals,
    ROUND((1.0 * COUNT(*) FILTER (WHERE status = 'Referred')
             / NULLIF(SUM(COUNT(*) FILTER (WHERE status = 'Referred')) OVER (), 0))
          / NULLIF(1.0 * COUNT(*) / NULLIF(SUM(COUNT(*)) OVER (), 0), 0), 3)
                                                             AS referral_concentration_index
FROM v_resolved
GROUP BY 1
ORDER BY referred_records DESC, council_district;

-- -----------------------------------------------------------------------------
-- Consistency check surfaced from the audit: records carrying referral text
-- whose status is not Referred. Reported so that any referral rate computed off
-- the text field alone can be reconciled with one computed off status.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TABLE agg_referral_status_consistency AS
SELECT
    status,
    has_referral_text,
    COUNT(*) AS case_records,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS pct_of_all_records
FROM fct_requests
GROUP BY status, has_referral_text
ORDER BY status, has_referral_text;
