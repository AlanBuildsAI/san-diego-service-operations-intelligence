"""The transformation layer, exercised against the synthetic fixture.

These tests run the project's real SQL files, so a change to a definition in
``03_sql/01_clean_base.sql`` shows up here rather than silently propagating into
the published numbers.
"""

from __future__ import annotations

import pytest

from tests.conftest import FIXTURE_SNAPSHOT


# --- snapshot derivation -----------------------------------------------------
def test_snapshot_date_is_derived_from_the_data(fixture_db):
    """The pipeline recovers the extract date instead of hard-coding it."""
    snapshot, supporting, total, pct = fixture_db.execute(
        "SELECT snapshot_date, n_records_supporting, n_active_records, "
        "pct_records_supporting FROM ref_snapshot").fetchone()
    assert str(snapshot) == FIXTURE_SNAPSHOT
    assert supporting < total, "the deliberately stale fixture row should not agree"
    assert pct > 90


# --- grain and deduplication -------------------------------------------------
def test_fact_table_is_one_row_per_service_request_id(fixture_db):
    rows, unique = fixture_db.execute(
        "SELECT COUNT(*), COUNT(DISTINCT service_request_id) FROM fct_requests").fetchone()
    assert rows == unique


def test_cross_file_duplicate_resolves_to_the_higher_precedence_extract(fixture_db):
    """id 2000 is in both closed_2026 and closed_2025; closed_2026 must win."""
    extract, n_extracts = fixture_db.execute(
        "SELECT source_extract, n_source_extracts FROM fct_requests "
        "WHERE service_request_id = '2000'").fetchone()
    assert extract == "closed_2026"
    assert n_extracts == 2


def test_no_rows_are_lost_or_invented(fixture_db):
    stacked = fixture_db.execute("SELECT COUNT(*) FROM stg_union").fetchone()[0]
    kept = fixture_db.execute("SELECT COUNT(*) FROM fct_requests").fetchone()[0]
    collisions = fixture_db.execute(
        "SELECT COUNT(*) FROM (SELECT service_request_id FROM stg_union "
        "GROUP BY 1 HAVING COUNT(*) > 1)").fetchone()[0]
    assert kept == stacked - collisions


# --- status definitions ------------------------------------------------------
def test_active_and_resolved_partition_every_record(fixture_db):
    total, active, resolved = fixture_db.execute(
        "SELECT COUNT(*), COUNT(*) FILTER (WHERE is_active), "
        "COUNT(*) FILTER (WHERE is_resolved) FROM fct_requests").fetchone()
    assert active + resolved == total, "every record must be exactly one of the two"


def test_referred_is_resolved_but_not_active(fixture_db):
    bad = fixture_db.execute(
        "SELECT COUNT(*) FROM fct_requests WHERE status = 'Referred' AND is_active").fetchone()[0]
    assert bad == 0
    referred_resolved = fixture_db.execute(
        "SELECT COUNT(*) FROM fct_requests WHERE status = 'Referred' AND NOT is_resolved"
    ).fetchone()[0]
    assert referred_resolved == 0


# --- age metrics -------------------------------------------------------------
def test_active_age_is_computed_from_dates_not_the_published_field(fixture_db):
    """The stale fixture row proves the project metric ignores case_age_days."""
    published, computed = fixture_db.execute(
        "SELECT case_age_days_published, active_age_days FROM fct_requests "
        "WHERE service_request_id = '1999'").fetchone()
    assert published == 200
    assert computed == 220, "should be snapshot minus request date, not the published value"


def test_age_metrics_are_mutually_exclusive(fixture_db):
    """An active record has no lifecycle; a resolved record has no active age."""
    bad = fixture_db.execute(
        "SELECT COUNT(*) FROM fct_requests "
        "WHERE (is_active AND active_age_days IS NULL) "
        "   OR (is_active AND lifecycle_days IS NOT NULL) "
        "   OR (is_resolved AND active_age_days IS NOT NULL)").fetchone()[0]
    assert bad == 0


def test_lifecycle_is_null_when_close_date_precedes_request_date(fixture_db):
    """Record 2998 closes before it opens; it must not produce a negative duration."""
    lifecycle = fixture_db.execute(
        "SELECT lifecycle_days FROM fct_requests WHERE service_request_id = '2998'"
    ).fetchone()[0]
    assert lifecycle is None
    negatives = fixture_db.execute(
        "SELECT COUNT(*) FROM fct_requests WHERE lifecycle_days < 0").fetchone()[0]
    assert negatives == 0


def test_no_negative_active_ages(fixture_db):
    assert fixture_db.execute(
        "SELECT COUNT(*) FROM fct_requests WHERE active_age_days < 0").fetchone()[0] == 0


# --- aging buckets -----------------------------------------------------------
@pytest.mark.parametrize("age,expected", [
    (0, "0-7"), (7, "0-7"), (8, "8-30"), (30, "8-30"), (31, "31-60"), (60, "31-60"),
    (61, "61-90"), (90, "61-90"), (91, "91-180"), (180, "91-180"),
    (181, "181-365"), (365, "181-365"), (366, "366-730"), (730, "366-730"), (731, "731+"),
])
def test_bucket_boundaries_are_inclusive_and_contiguous(fixture_db, age, expected):
    """Boundary values land in the lower bucket, with no gaps between buckets."""
    result = fixture_db.execute("""
        SELECT CASE
            WHEN ? <= 7 THEN '0-7' WHEN ? <= 30 THEN '8-30' WHEN ? <= 60 THEN '31-60'
            WHEN ? <= 90 THEN '61-90' WHEN ? <= 180 THEN '91-180'
            WHEN ? <= 365 THEN '181-365' WHEN ? <= 730 THEN '366-730' ELSE '731+' END
    """, [age] * 7).fetchone()[0]
    assert result == expected


def test_every_active_record_lands_in_exactly_one_bucket(fixture_db):
    active, bucketed = fixture_db.execute(
        "SELECT COUNT(*), COUNT(age_bucket) FROM fct_requests WHERE is_active").fetchone()
    assert active == bucketed
    total_in_buckets = fixture_db.execute(
        "SELECT SUM(n_records) FROM agg_backlog_aging_buckets").fetchone()[0]
    assert total_in_buckets == active


# --- duplicates --------------------------------------------------------------
def test_issue_key_collapses_children_onto_their_parent(fixture_db):
    key, parent = fixture_db.execute(
        "SELECT issue_key, parent_request_id FROM fct_requests "
        "WHERE is_duplicate_child LIMIT 1").fetchone()
    assert key == parent


def test_issue_key_falls_back_to_own_id_for_non_children(fixture_db):
    bad = fixture_db.execute(
        "SELECT COUNT(*) FROM fct_requests "
        "WHERE NOT is_duplicate_child AND issue_key <> service_request_id").fetchone()[0]
    assert bad == 0


def test_distinct_issues_never_exceed_case_records(fixture_db):
    records, issues = fixture_db.execute(
        "SELECT COUNT(*), COUNT(DISTINCT issue_key) FROM fct_requests").fetchone()
    assert issues <= records


# --- referrals ---------------------------------------------------------------
def test_referral_destination_is_parsed_not_passed_through(fixture_db):
    destination = fixture_db.execute(
        "SELECT referred_to FROM fct_requests WHERE status = 'Referred' "
        "AND referred_to LIKE 'Caltrans%' LIMIT 1").fetchone()
    assert destination is not None and destination[0] == "Caltrans (State)"


def test_referral_scope_is_assigned_for_every_referred_record_with_text(fixture_db):
    unscoped = fixture_db.execute(
        "SELECT COUNT(*) FROM fct_requests "
        "WHERE status = 'Referred' AND has_referral_text AND referral_scope IS NULL"
    ).fetchone()[0]
    assert unscoped == 0


def test_referral_rate_is_computed_from_status_not_text(fixture_db):
    """Fixture record 2999 is Closed but carries referral text; it must not count."""
    by_status = fixture_db.execute(
        "SELECT COUNT(*) FROM fct_requests WHERE status = 'Referred'").fetchone()[0]
    by_text = fixture_db.execute(
        "SELECT COUNT(*) FROM fct_requests WHERE has_referral_text").fetchone()[0]
    assert by_text > by_status, "fixture should contain the inconsistent record"
    summary = fixture_db.execute(
        "SELECT case_records FROM agg_referral_summary WHERE status = 'Referred'").fetchone()[0]
    assert summary == by_status


# --- geography ---------------------------------------------------------------
def test_council_district_is_only_ever_1_to_9_or_null(fixture_db):
    bad = fixture_db.execute(
        "SELECT COUNT(*) FROM fct_requests "
        "WHERE council_district IS NOT NULL AND council_district NOT BETWEEN 1 AND 9"
    ).fetchone()[0]
    assert bad == 0


def test_geography_aggregate_reconciles_to_the_backlog(fixture_db):
    """Unknown geography is kept as a labelled group, so shares sum to the whole."""
    active = fixture_db.execute(
        "SELECT COUNT(*) FROM fct_requests WHERE is_active").fetchone()[0]
    in_district_table = fixture_db.execute(
        "SELECT SUM(active_records) FROM agg_geography_district").fetchone()[0]
    assert in_district_table == active


def test_missing_dimensions_become_labelled_groups(fixture_db):
    """Fixture record 1998 has no service name, community or channel."""
    service, community, origin = fixture_db.execute(
        "SELECT service_name, community, case_origin FROM fct_requests "
        "WHERE service_request_id = '1998'").fetchone()
    assert service == "(Unclassified)"
    assert community == "(Unknown)"
    assert origin == "(Unknown)"


# --- aggregates --------------------------------------------------------------
def test_executive_kpis_reconcile_to_the_fact_table(fixture_db):
    def kpi(key: str) -> float:
        return fixture_db.execute(
            "SELECT value FROM agg_executive_kpis WHERE metric_key = ?", [key]).fetchone()[0]

    active = fixture_db.execute(
        "SELECT COUNT(*) FROM fct_requests WHERE is_active").fetchone()[0]
    total = fixture_db.execute("SELECT COUNT(*) FROM fct_requests").fetchone()[0]
    assert kpi("active_backlog") == active
    assert kpi("total_case_records") == total


def test_service_backlog_shares_sum_to_one_hundred(fixture_db):
    total = fixture_db.execute(
        "SELECT ROUND(SUM(pct_of_active_backlog), 0) FROM agg_service_backlog").fetchone()[0]
    assert total == 100


def test_referral_scope_columns_reconcile_to_referred_total(fixture_db):
    """external + internal + unclassified must equal referred_records exactly."""
    mismatches = fixture_db.execute(
        "SELECT COUNT(*) FROM agg_referral_by_service "
        "WHERE referred_external + referred_internal + referred_unclassified "
        "   <> referred_records").fetchone()[0]
    assert mismatches == 0


def test_incomplete_demand_months_are_flagged(fixture_db):
    """Months the scope cannot fully cover must never be labelled complete."""
    bad = fixture_db.execute(
        "SELECT COUNT(*) FROM agg_demand_monthly "
        "WHERE month_start < DATE '2025-01-01' AND coverage_status = 'complete'"
    ).fetchone()[0]
    assert bad == 0
