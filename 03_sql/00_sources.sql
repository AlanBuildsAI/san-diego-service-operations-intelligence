-- =============================================================================
-- 00_sources.sql
-- Purpose : Register the three official City of San Diego "Get It Done" extracts
--           as typed views, and derive the data snapshot date from the data
--           itself rather than from a hard-coded constant.
-- Engine  : DuckDB
-- Run from: repository root, e.g.
--             duckdb data/processed/gid.duckdb -c ".read 03_sql/00_sources.sql"
--           (paths below are relative to the repository root)
--
-- Source  : https://data.sandiego.gov/datasets/get-it-done-reports/
--           Files are downloaded by scripts/download_data.py into data/raw/.
--
-- Data boundary: these records are user-submitted service requests and case
-- statuses. They are not a record of maintenance work performed.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Raw views. Types are declared explicitly so that a change in the upstream file
-- (for example a council district arriving as text) fails loudly instead of
-- being silently coerced.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW src_open AS
SELECT *, 'open' AS source_extract, 1 AS source_precedence
FROM read_csv(
    'data/raw/get_it_done_requests_open_datasd.csv',
    header = true,
    sample_size = -1,
    columns = {
        'service_request_id': 'VARCHAR',
        'service_request_parent_id': 'VARCHAR',
        'sap_notification_number': 'VARCHAR',
        'date_requested': 'TIMESTAMP',
        'case_age_days': 'BIGINT',
        'case_record_type': 'VARCHAR',
        'service_name': 'VARCHAR',
        'service_name_detail': 'VARCHAR',
        'date_closed': 'DATE',
        'status': 'VARCHAR',
        'lat': 'DOUBLE',
        'lng': 'DOUBLE',
        'street_address': 'VARCHAR',
        'zipcode': 'VARCHAR',
        'council_district': 'VARCHAR',
        'comm_plan_code': 'VARCHAR',
        'comm_plan_name': 'VARCHAR',
        'park_name': 'VARCHAR',
        'case_origin': 'VARCHAR',
        'referred': 'VARCHAR',
        'iamfloc': 'VARCHAR',
        'floc': 'VARCHAR',
        'public_description': 'VARCHAR'
    }
);

CREATE OR REPLACE VIEW src_closed_2026 AS
SELECT *, 'closed_2026' AS source_extract, 2 AS source_precedence
FROM read_csv(
    'data/raw/get_it_done_requests_closed_2026_datasd.csv',
    header = true, sample_size = -1, all_varchar = false,
    types = {
        'service_request_id': 'VARCHAR',
        'service_request_parent_id': 'VARCHAR',
        'sap_notification_number': 'VARCHAR',
        'zipcode': 'VARCHAR',
        'council_district': 'VARCHAR',
        'comm_plan_code': 'VARCHAR',
        'date_requested': 'TIMESTAMP',
        'date_closed': 'DATE',
        'case_age_days': 'BIGINT'
    }
);

CREATE OR REPLACE VIEW src_closed_2025 AS
SELECT *, 'closed_2025' AS source_extract, 3 AS source_precedence
FROM read_csv(
    'data/raw/get_it_done_requests_closed_2025_datasd.csv',
    header = true, sample_size = -1, all_varchar = false,
    types = {
        'service_request_id': 'VARCHAR',
        'service_request_parent_id': 'VARCHAR',
        'sap_notification_number': 'VARCHAR',
        'zipcode': 'VARCHAR',
        'council_district': 'VARCHAR',
        'comm_plan_code': 'VARCHAR',
        'date_requested': 'TIMESTAMP',
        'date_closed': 'DATE',
        'case_age_days': 'BIGINT'
    }
);

-- -----------------------------------------------------------------------------
-- Snapshot date, derived from the data.
--
-- The published field `case_age_days` behaves differently for active records
-- than the official dictionary describes (see 02_data_audit/data_quality_report.md).
-- For active records it equals (extract date - date_requested), so the extract
-- date can be recovered as the modal value of date_requested + case_age_days.
-- Deriving it this way means the pipeline re-dates itself automatically when a
-- newer extract is downloaded, with no constant to forget to update.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TABLE ref_snapshot AS
WITH implied AS (
    SELECT
        CAST(CAST(date_requested AS DATE) + INTERVAL (case_age_days) DAY AS DATE) AS implied_date,
        COUNT(*) AS n_records
    FROM src_open
    WHERE case_age_days IS NOT NULL
      AND date_requested IS NOT NULL
    GROUP BY 1
),
ranked AS (
    SELECT
        implied_date,
        n_records,
        SUM(n_records) OVER () AS n_total,
        ROW_NUMBER() OVER (ORDER BY n_records DESC, implied_date DESC) AS rn
    FROM implied
)
SELECT
    implied_date                                   AS snapshot_date,
    n_records                                      AS n_records_supporting,
    n_total                                        AS n_active_records,
    ROUND(100.0 * n_records / NULLIF(n_total, 0), 2) AS pct_records_supporting
FROM ranked
WHERE rn = 1;

-- -----------------------------------------------------------------------------
-- Official field dictionary, kept alongside the data so field definitions can be
-- joined to audit output instead of being retyped by hand.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW src_dictionary AS
SELECT field, data_type, description
FROM read_csv_auto('data/raw/get_it_done_requests_dictionary_datasd.csv', header = true);
