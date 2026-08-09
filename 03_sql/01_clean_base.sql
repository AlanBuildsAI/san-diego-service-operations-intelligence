-- =============================================================================
-- 01_clean_base.sql
-- Purpose : Build the analysis fact table `fct_requests` at one row per
--           service_request_id, with project-defined age metrics, normalised
--           dimensions, and every sensitive source field suppressed.
-- Depends : 00_sources.sql
-- Engine  : DuckDB
--
-- Grain          : one row per service_request_id (case record).
-- Deduplication  : an id appearing in more than one official extract is kept
--                  once, from the extract with the lowest source_precedence
--                  (open > closed_2026 > closed_2025). Conflicts are counted in
--                  02_data_audit/data_quality_report.md.
-- Privacy        : public_description, street_address, lat, lng, the raw
--                  `referred` message (contains staff/vendor email addresses),
--                  asset floc identifiers and SAP numbers are never selected
--                  into fct_requests, so they cannot reach any published output.
--
-- Data boundary: user-submitted service requests and case statuses only. A
-- status of "Closed" records a case closure, not verified physical repair.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Step 1: stack the three extracts on a common, explicitly-named column set.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW stg_union AS
SELECT service_request_id, service_request_parent_id, date_requested, date_closed,
       case_age_days, status, case_record_type, service_name, service_name_detail,
       zipcode, council_district, comm_plan_code, comm_plan_name, park_name,
       case_origin, referred, source_extract, source_precedence
FROM src_open
UNION ALL
SELECT service_request_id, service_request_parent_id, date_requested, date_closed,
       case_age_days, status, case_record_type, service_name, service_name_detail,
       zipcode, council_district, comm_plan_code, comm_plan_name, park_name,
       case_origin, referred, source_extract, source_precedence
FROM src_closed_2026
UNION ALL
SELECT service_request_id, service_request_parent_id, date_requested, date_closed,
       case_age_days, status, case_record_type, service_name, service_name_detail,
       zipcode, council_district, comm_plan_code, comm_plan_name, park_name,
       case_origin, referred, source_extract, source_precedence
FROM src_closed_2025;

-- -----------------------------------------------------------------------------
-- Step 2: resolve ids that appear in more than one extract.
-- `n_source_extracts` is retained so the audit can quantify how often this
-- happens rather than silently absorbing it.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW stg_deduplicated AS
SELECT * EXCLUDE (rn)
FROM (
    SELECT
        u.*,
        COUNT(*)     OVER (PARTITION BY service_request_id) AS n_source_extracts,
        ROW_NUMBER() OVER (PARTITION BY service_request_id
                           ORDER BY source_precedence)      AS rn
    FROM stg_union AS u
)
WHERE rn = 1;

-- -----------------------------------------------------------------------------
-- Step 3: the fact table.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TABLE fct_requests AS
WITH snap AS (
    SELECT snapshot_date FROM ref_snapshot
),
typed AS (
    SELECT
        d.service_request_id,
        NULLIF(TRIM(d.service_request_parent_id), '')          AS parent_request_id,
        d.date_requested,
        d.date_closed,
        d.case_age_days                                        AS case_age_days_published,
        d.status,
        d.n_source_extracts,
        d.source_extract,

        -- Service taxonomy. Blank service names are labelled rather than dropped
        -- so that the ~0.1% of records with no classification stay countable.
        COALESCE(NULLIF(TRIM(d.case_record_type), ''), '(Unclassified)') AS case_record_type,
        COALESCE(NULLIF(TRIM(d.service_name), ''),     '(Unclassified)') AS service_name,
        COALESCE(NULLIF(TRIM(d.service_name_detail), ''), '(Unspecified)') AS service_name_detail,

        -- Geography. Council district arrives as text; only 1-9 are valid.
        CASE WHEN TRIM(COALESCE(d.council_district, '')) IN
                  ('1','2','3','4','5','6','7','8','9')
             THEN CAST(TRIM(d.council_district) AS INTEGER) END AS council_district,
        COALESCE(NULLIF(TRIM(d.comm_plan_name), ''), '(Unknown)') AS community,
        NULLIF(TRIM(d.zipcode), '')                            AS zipcode,
        NULLIF(TRIM(d.park_name), '')                          AS park_name,

        -- Submission channel, as published and grouped.
        COALESCE(NULLIF(TRIM(d.case_origin), ''), '(Unknown)') AS case_origin,

        d.referred                                             AS referred_raw,
        snap.snapshot_date
    FROM stg_deduplicated AS d
    CROSS JOIN snap
),
derived AS (
    SELECT
        t.* EXCLUDE (referred_raw),

        -- --- lifecycle state ------------------------------------------------
        t.status IN ('New', 'In Process')                      AS is_active,
        t.status IN ('Closed', 'Referred')                     AS is_resolved,
        t.parent_request_id IS NOT NULL                        AS is_duplicate_child,

        -- Issue key collapses a duplicate child onto its parent so that demand
        -- can be counted either per case record or per distinct reported issue.
        COALESCE(t.parent_request_id, t.service_request_id)    AS issue_key,

        -- --- project age metrics (computed, not taken from the source) ------
        CASE WHEN t.status IN ('New', 'In Process')
             THEN DATEDIFF('day', CAST(t.date_requested AS DATE), t.snapshot_date)
        END                                                    AS active_age_days,

        CASE WHEN t.status IN ('Closed', 'Referred')
              AND t.date_closed IS NOT NULL
              AND t.date_closed >= CAST(t.date_requested AS DATE)
             THEN DATEDIFF('day', CAST(t.date_requested AS DATE), t.date_closed)
        END                                                    AS lifecycle_days,

        -- --- channel grouping -----------------------------------------------
        -- Separates channels a resident can use from channels only City staff or
        -- automated systems can use. The two behave very differently and mixing
        -- them distorts any channel comparison.
        CASE
            WHEN t.case_origin IN ('Mobile', 'Web', 'Phone', 'Email', 'Walk-In', 'Letter')
                THEN 'Resident-submitted'
            WHEN t.case_origin IN ('Worker App', 'CC Self Generate', 'Crew/Self Generated',
                                   'Internal', 'System Generated', 'GID Field',
                                   'Self-Generated', 'Construction Patrol',
                                   'Residential Patrol', 'FO Self Generate',
                                   'Hauler List', 'Referral', 'Referral Notice')
                THEN 'Staff or system-generated'
            ELSE '(Unknown)'
        END                                                    AS channel_group,

        -- --- referral routing -------------------------------------------------
        -- The raw `referred` message is free text containing staff and vendor
        -- email addresses, so it is normalised to a routing destination here and
        -- never carried forward.
        CASE
            WHEN t.referred_raw IS NULL THEN NULL
            WHEN t.referred_raw ILIKE '%caltrans%'                       THEN 'Caltrans (State)'
            WHEN t.referred_raw ILIKE '%sdg&e%' OR t.referred_raw ILIKE '%sdge%'
                                                                          THEN 'SDG&E (utility)'
            WHEN t.referred_raw ILIKE '%at&t%' OR t.referred_raw ILIKE '%att.com%'
                                                                          THEN 'AT&T (utility)'
            WHEN t.referred_raw ILIKE '%retailsol%' OR t.referred_raw ILIKE '% RMS%'
                                                                          THEN 'RMS (cart retrieval)'
            WHEN t.referred_raw ILIKE '%cox%'                             THEN 'Cox (utility)'
            WHEN t.referred_raw ILIKE '%mts%'                             THEN 'MTS (transit)'
            WHEN t.referred_raw ILIKE '%usps%' OR t.referred_raw ILIKE '%postal%'
                                                                          THEN 'USPS (federal)'
            WHEN t.referred_raw ILIKE '%bnsf%' OR t.referred_raw ILIKE '%railroad%'
                                                                          THEN 'Railroad'
            WHEN t.referred_raw ILIKE '%sandi.net%' OR t.referred_raw ILIKE '%unified school%'
                                                                          THEN 'San Diego Unified School District'
            WHEN t.referred_raw ILIKE '%portofsandiego%' OR t.referred_raw ILIKE '%harbor police%'
                                                                          THEN 'Port of San Diego / Harbor Police'
            WHEN t.referred_raw ILIKE '%cleanharbors%' OR t.referred_raw ILIKE '%sanitiz%'
                 OR t.referred_raw ILIKE '%sanitation%'                   THEN 'Sanitation contractor'
            WHEN t.referred_raw ILIKE '%edco%' OR t.referred_raw ILIKE '%waste management%'
                                                                          THEN 'Private waste hauler'
            WHEN t.referred_raw ILIKE '%improvedtsd%' OR t.referred_raw ILIKE '%clean & safe%'
                                                                          THEN 'Downtown Clean & Safe'
            WHEN t.referred_raw ILIKE '%county of san diego%' OR t.referred_raw ILIKE '%sdcounty%'
                                                                          THEN 'County of San Diego'
            WHEN t.referred_raw ILIKE '%pd.sandiego.gov%' OR t.referred_raw ILIKE '%police%'
                                                                          THEN 'City - Police'
            WHEN t.referred_raw ILIKE '%sdfd%' OR t.referred_raw ILIKE '%fire%'
                                                                          THEN 'City - Fire-Rescue'
            WHEN t.referred_raw ILIKE '%storm water%' OR t.referred_raw ILIKE '%stormwater%'
                                                                          THEN 'City - Storm Water'
            WHEN t.referred_raw ILIKE '%code compliance%' OR t.referred_raw ILIKE '%code enforcement%'
                 OR t.referred_raw ILIKE '%t-row%'                        THEN 'City - Code Compliance'
            WHEN t.referred_raw ILIKE '%park%'                            THEN 'City - Parks & Recreation'
            WHEN t.referred_raw ILIKE '%street division%' OR t.referred_raw ILIKE '%street sweep%'
                                                                          THEN 'City - Streets'
            WHEN t.referred_raw ILIKE '%traffic engineering%'             THEN 'City - Traffic Engineering'
            WHEN t.referred_raw ILIKE '%field engineering%'               THEN 'City - Field Engineering'
            WHEN t.referred_raw ILIKE '%water%'                           THEN 'City - Public Utilities (Water)'
            WHEN t.referred_raw ILIKE '%librar%'                          THEN 'City - Library'
            WHEN t.referred_raw ILIKE '%facilit%'                         THEN 'City - Facilities Maintenance'
            WHEN t.referred_raw ILIKE '%golf%'                            THEN 'City - Golf'
            WHEN t.referred_raw ILIKE '%parking meter%'                   THEN 'City - Parking Meter Repair'
            WHEN t.referred_raw ILIKE '%esd %' OR t.referred_raw ILIKE '%environmental services%'
                                                                          THEN 'City - Environmental Services'
            -- Fallback tier: the long tail is a routing message ending in a
            -- contact address. A sandiego.gov address means the case stayed
            -- inside the City; any other domain means it left.
            WHEN t.referred_raw ILIKE '%@sandiego.gov%'                    THEN 'City - Other department'
            WHEN REGEXP_MATCHES(t.referred_raw, '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')
                                                                          THEN 'Other external entity'
            ELSE '(Unparsed referral text)'
        END                                                    AS referred_to,

        t.referred_raw IS NOT NULL                             AS has_referral_text,

        -- --- calendar helpers -------------------------------------------------
        CAST(t.date_requested AS DATE)                         AS requested_date,
        YEAR(t.date_requested)                                 AS requested_year,
        MONTH(t.date_requested)                                AS requested_month,
        DATE_TRUNC('month', CAST(t.date_requested AS DATE))    AS requested_month_start,
        YEAR(t.date_closed)                                    AS closed_year,
        DATE_TRUNC('month', t.date_closed)                     AS closed_month_start
    FROM typed AS t
)
SELECT
    d.*,
    CASE
        WHEN d.referred_to IS NULL THEN NULL
        WHEN d.referred_to LIKE 'City - %' THEN 'Internal (City department)'
        WHEN d.referred_to = '(Unparsed referral text)' THEN '(Unclassified)'
        ELSE 'External (non-City entity)'
    END                                                        AS referral_scope,
    CASE
        WHEN d.active_age_days IS NULL THEN NULL
        WHEN d.active_age_days <= 7   THEN '0-7'
        WHEN d.active_age_days <= 30  THEN '8-30'
        WHEN d.active_age_days <= 60  THEN '31-60'
        WHEN d.active_age_days <= 90  THEN '61-90'
        WHEN d.active_age_days <= 180 THEN '91-180'
        WHEN d.active_age_days <= 365 THEN '181-365'
        WHEN d.active_age_days <= 730 THEN '366-730'
        ELSE '731+'
    END                                                        AS age_bucket
FROM derived AS d;

-- -----------------------------------------------------------------------------
-- Step 4: convenience views used throughout the analysis layer.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_active AS
SELECT * FROM fct_requests WHERE is_active;

CREATE OR REPLACE VIEW v_resolved AS
SELECT * FROM fct_requests WHERE is_resolved;

-- One row per distinct reported issue: duplicate children collapse onto their
-- parent. Used to show how much of measured demand is repeat reporting.
CREATE OR REPLACE VIEW v_issues AS
SELECT
    issue_key,
    COUNT(*)                                          AS n_case_records,
    MIN(requested_date)                               AS first_requested_date,
    MAX(CASE WHEN is_active THEN 1 ELSE 0 END) = 1    AS has_active_record,
    MAX(active_age_days)                              AS max_active_age_days,
    ANY_VALUE(service_name)                           AS any_service_name,
    ANY_VALUE(council_district)                       AS any_council_district
FROM fct_requests
GROUP BY issue_key;
