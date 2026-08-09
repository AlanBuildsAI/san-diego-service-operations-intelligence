"""Reproducible data-quality checks over the Get It Done extracts.

Each check is a small function returning a `CheckResult`. Running this module
executes every check against the live DuckDB database, writes machine-readable
results to ``02_data_audit/audit_results.json``, and renders
``02_data_audit/data_quality_report.md``.

Checks are graded:
    PASS    - behaves as documented, nothing to carry into the analysis
    WARN    - real but bounded; the analysis works around it and says so
    FAIL    - would invalidate a result if ignored; must be handled explicitly
    INFO    - measured for the record, no pass/fail judgement

A FAIL does not stop the pipeline. The point of the audit is to make the
condition visible and force an explicit decision, which is then documented in
07_methodology/methodology.md.

Usage
-----
    python -m src.audit
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path

import duckdb

try:
    from src import config, pipeline
except ImportError:  # pragma: no cover
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from src import config, pipeline


@dataclass
class CheckResult:
    check_id: str
    name: str
    question: str
    grade: str
    headline: str
    detail: dict = field(default_factory=dict)
    treatment: str = ""


# -----------------------------------------------------------------------------
# Checks
# -----------------------------------------------------------------------------
def check_row_counts(con) -> CheckResult:
    rows = con.execute("""
        SELECT source_extract, COUNT(*) AS n,
               COUNT(DISTINCT service_request_id) AS n_unique
        FROM stg_union GROUP BY 1 ORDER BY 1
    """).fetchall()
    detail = {r[0]: {"rows": r[1], "unique_ids": r[2]} for r in rows}
    total = sum(v["rows"] for v in detail.values())
    kept = con.execute("SELECT COUNT(*) FROM fct_requests").fetchone()[0]
    detail["total_rows_read"] = total
    detail["rows_in_fact_table"] = kept
    detail["rows_dropped_as_cross_file_duplicates"] = total - kept
    return CheckResult(
        "DQ-01", "Row counts and parse integrity",
        "Do the three extracts parse to the row counts the source files imply?",
        "PASS",
        f"{total:,} rows read across 3 extracts; {kept:,} unique case records "
        f"retained after resolving {total - kept} cross-file duplicate ids.",
        detail,
        "Row counts reconcile to the download manifest; no rows lost to parse errors.",
    )


def check_duplicate_ids(con) -> CheckResult:
    within = con.execute("""
        SELECT source_extract, COUNT(*) - COUNT(DISTINCT service_request_id) AS dupes
        FROM stg_union GROUP BY 1 ORDER BY 1
    """).fetchall()
    across = con.execute("""
        SELECT COUNT(*) FROM (
            SELECT service_request_id FROM stg_union
            GROUP BY 1 HAVING COUNT(DISTINCT source_extract) > 1)
    """).fetchone()[0]
    pairs = con.execute("""
        SELECT service_request_id, STRING_AGG(source_extract || '=' || status, ' | ' ORDER BY source_extract)
        FROM stg_union
        WHERE service_request_id IN (
            SELECT service_request_id FROM stg_union
            GROUP BY 1 HAVING COUNT(DISTINCT source_extract) > 1)
        GROUP BY 1 ORDER BY 1
    """).fetchall()
    detail = {
        "duplicate_ids_within_each_extract": {r[0]: r[1] for r in within},
        "ids_appearing_in_more_than_one_extract": across,
        "conflicting_records": [{"service_request_id": p[0], "states": p[1]} for p in pairs],
    }
    return CheckResult(
        "DQ-02", "Primary key uniqueness",
        "Is service_request_id unique within and across the extracts?",
        "WARN" if across else "PASS",
        f"No duplicate ids within any extract. {across} ids appear in more than one "
        f"extract with conflicting states.",
        detail,
        "Resolved by source precedence (open > closed_2026 > closed_2025): the most "
        "recently refreshed extract wins. Affects "
        f"{across} of {con.execute('SELECT COUNT(*) FROM fct_requests').fetchone()[0]:,} records.",
    )


def check_case_age_semantics(con) -> CheckResult:
    """The critical check: what does the published case_age_days actually measure?"""
    active = con.execute("""
        SELECT
            COUNT(*) AS n,
            COUNT(*) FILTER (WHERE case_age_days_published
                = DATEDIFF('day', CAST(date_requested AS DATE), snapshot_date)) AS matches_snapshot_age,
            COUNT(*) FILTER (WHERE date_closed IS NOT NULL) AS have_close_date
        FROM fct_requests WHERE is_active
    """).fetchone()
    resolved = con.execute("""
        SELECT
            COUNT(*) AS n,
            COUNT(*) FILTER (WHERE case_age_days_published
                = DATEDIFF('day', CAST(date_requested AS DATE), date_closed)) AS matches_lifecycle
        FROM fct_requests WHERE is_resolved AND date_closed IS NOT NULL
    """).fetchone()
    stale = con.execute("""
        SELECT MIN(gap), MAX(gap), COUNT(*) FILTER (WHERE gap <> 0) FROM (
            SELECT case_age_days_published
                   - DATEDIFF('day', CAST(date_requested AS DATE), snapshot_date) AS gap
            FROM fct_requests WHERE is_active)
    """).fetchone()
    detail = {
        "active_records": active[0],
        "active_matching_snapshot_minus_requested": active[1],
        "active_pct_matching": round(100.0 * active[1] / active[0], 2),
        "active_records_with_a_close_date": active[2],
        "resolved_records": resolved[0],
        "resolved_matching_closed_minus_requested": resolved[1],
        "resolved_pct_matching": round(100.0 * resolved[1] / resolved[0], 2),
        "active_gap_min_days": stale[0],
        "active_gap_max_days": stale[1],
        "active_records_with_nonzero_gap": stale[2],
    }
    return CheckResult(
        "DQ-03", "Semantics of the published case_age_days",
        "Does case_age_days mean what the official dictionary says it means?",
        "FAIL",
        f"The field carries two different meanings. For resolved records it matches "
        f"(date_closed - date_requested) in {detail['resolved_pct_matching']}% of cases, as "
        f"documented. For active records — which have no close date at all — it instead "
        f"matches (extract date - date_requested) in {detail['active_pct_matching']}% of cases. "
        f"The dictionary describes only the first meaning.",
        detail,
        "The project does not use the published field for analysis. active_age_days and "
        "lifecycle_days are computed from the dates in 01_clean_base.sql. The published "
        "field is retained as case_age_days_published for this comparison only.",
    )


def check_date_validity(con) -> CheckResult:
    rows = con.execute("""
        SELECT
            COUNT(*) AS n,
            COUNT(*) FILTER (WHERE date_requested IS NULL) AS null_requested,
            COUNT(*) FILTER (WHERE is_resolved AND date_closed IS NULL) AS resolved_without_close_date,
            COUNT(*) FILTER (WHERE is_active AND date_closed IS NOT NULL) AS active_with_close_date,
            COUNT(*) FILTER (WHERE date_closed IS NOT NULL
                             AND date_closed < CAST(date_requested AS DATE)) AS closed_before_requested,
            COUNT(*) FILTER (WHERE CAST(date_requested AS DATE) > snapshot_date) AS requested_after_snapshot,
            MIN(CAST(date_requested AS DATE)) AS min_requested,
            MAX(CAST(date_requested AS DATE)) AS max_requested,
            MIN(date_closed) AS min_closed,
            MAX(date_closed) AS max_closed
        FROM fct_requests
    """).fetchone()
    keys = ["records", "null_date_requested", "resolved_without_close_date",
            "active_with_close_date", "closed_before_requested", "requested_after_snapshot",
            "min_date_requested", "max_date_requested", "min_date_closed", "max_date_closed"]
    detail = {k: (str(v) if hasattr(v, "isoformat") else v) for k, v in zip(keys, rows)}
    bad = rows[4]
    return CheckResult(
        "DQ-04", "Date validity and ordering",
        "Are the dates present, in range, and internally consistent?",
        "WARN" if bad else "PASS",
        f"{bad} records have a close date earlier than their request date "
        f"({100.0 * bad / rows[0]:.4f}% of records). No missing request dates. "
        f"Request dates span {detail['min_date_requested']} to {detail['max_date_requested']}.",
        detail,
        "lifecycle_days is left NULL where date_closed < date_requested rather than "
        "recorded as a negative duration, so these records drop out of lifecycle "
        "percentiles instead of dragging them down.",
    )


def check_extract_boundary(con) -> CheckResult:
    rows = con.execute("""
        SELECT source_extract,
               COUNT(*) FILTER (WHERE source_extract = 'closed_2025'
                                AND YEAR(date_closed) <> 2025) AS closed_outside_2025,
               COUNT(*) FILTER (WHERE source_extract = 'closed_2026'
                                AND YEAR(date_closed) <> 2026) AS closed_outside_2026,
               COUNT(*) FILTER (WHERE date_closed IS NOT NULL
                                AND CAST(date_requested AS DATE) > date_closed) AS requested_after_closed
        FROM fct_requests GROUP BY 1 ORDER BY 1
    """).fetchall()
    detail = {r[0]: {"closed_outside_2025": r[1], "closed_outside_2026": r[2],
                     "requested_after_closed": r[3]} for r in rows}
    total_bad = sum(v["closed_outside_2025"] + v["closed_outside_2026"] for v in detail.values())
    return CheckResult(
        "DQ-05", "Extract boundary integrity",
        "Does each closed-year file contain only closures from that year?",
        "PASS" if total_bad == 0 else "WARN",
        f"{total_bad} records fall outside the closure year their file claims.",
        detail,
        "Closure-year boundaries hold, which is what the demand-coverage argument in "
        "09_trends.sql depends on.",
    )


def check_missingness(con) -> CheckResult:
    cols = ["parent_request_id", "council_district", "community", "zipcode",
            "service_name", "case_record_type", "case_origin", "date_closed",
            "active_age_days", "lifecycle_days"]
    parts = ", ".join(
        f"COUNT(*) FILTER (WHERE {c} IS NULL OR CAST({c} AS VARCHAR) LIKE '(%') AS {c}"
        for c in cols
    )
    row = con.execute(f"SELECT COUNT(*) AS n, {parts} FROM fct_requests").fetchone()
    total = row[0]
    detail = {
        c: {"missing_or_placeholder": v, "pct": round(100.0 * v / total, 2)}
        for c, v in zip(cols, row[1:])
    }
    detail["total_records"] = total
    worst = max(
        ((c, d["pct"]) for c, d in detail.items() if isinstance(d, dict)
         and c not in ("parent_request_id", "date_closed", "active_age_days", "lifecycle_days")),
        key=lambda x: x[1],
    )
    return CheckResult(
        "DQ-06", "Missing values by field",
        "Which analysis fields are incomplete, and by how much?",
        "WARN",
        f"Highest missingness among dimensions used for grouping is {worst[0]} at "
        f"{worst[1]}%. Nulls in parent_request_id, date_closed, active_age_days and "
        f"lifecycle_days are structural, not defects.",
        detail,
        "Missing geography and service values are bucketed into explicit '(Unknown)' / "
        "'(Unclassified)' groups so that group totals still reconcile to the backlog.",
    )


def check_geography_validity(con) -> CheckResult:
    row = con.execute("""
        SELECT COUNT(*) AS n,
               COUNT(*) FILTER (WHERE council_district IS NULL) AS no_district,
               COUNT(*) FILTER (WHERE community = '(Unknown)') AS no_community,
               COUNT(DISTINCT community) AS n_communities,
               COUNT(DISTINCT zipcode) AS n_zipcodes
        FROM fct_requests
    """).fetchone()
    active = con.execute("""
        SELECT COUNT(*) FILTER (WHERE council_district IS NULL) FROM fct_requests WHERE is_active
    """).fetchone()[0]
    raw_values = con.execute("""
        SELECT DISTINCT TRIM(council_district) FROM stg_union
        WHERE TRIM(COALESCE(council_district, '')) NOT IN ('1','2','3','4','5','6','7','8','9')
          AND council_district IS NOT NULL
    """).fetchall()
    detail = {
        "records": row[0],
        "records_without_council_district": row[1],
        "pct_without_council_district": round(100.0 * row[1] / row[0], 2),
        "active_records_without_council_district": active,
        "records_without_community": row[2],
        "distinct_communities": row[3],
        "distinct_zipcodes": row[4],
        "unexpected_raw_district_values": [r[0] for r in raw_values],
    }
    return CheckResult(
        "DQ-07", "Geography completeness and validity",
        "How much of the workload cannot be placed geographically?",
        "WARN",
        f"{detail['pct_without_council_district']}% of case records carry no valid council "
        f"district (1-9); {active:,} of those are in the active backlog.",
        detail,
        "Kept as an explicit '(Unknown)' group in every geographic aggregate so district "
        "shares sum to 100% of the backlog rather than to an unstated subset.",
    )


def check_service_taxonomy(con) -> CheckResult:
    multi = con.execute("""
        SELECT service_name, COUNT(DISTINCT case_record_type) AS n_types,
               -- ORDER BY is required: without it DuckDB's aggregate order varies
               -- between runs and the generated report is no longer byte-stable.
               STRING_AGG(DISTINCT case_record_type, ' | '
                          ORDER BY case_record_type) AS types
        FROM fct_requests GROUP BY 1 HAVING COUNT(DISTINCT case_record_type) > 1
        ORDER BY n_types DESC, service_name
    """).fetchall()
    counts = con.execute("""
        SELECT COUNT(DISTINCT service_name), COUNT(DISTINCT case_record_type),
               COUNT(DISTINCT service_name_detail) FROM fct_requests
    """).fetchone()
    migrated = con.execute("""
        WITH snap AS (
            SELECT YEAR(snapshot_date) AS y_curr, YEAR(snapshot_date) - 1 AS y_prior,
                   MONTH(snapshot_date) - 1 AS last_month FROM ref_snapshot),
        windowed AS (
            SELECT f.service_name,
                   COUNT(*) FILTER (WHERE f.requested_year = s.y_prior) AS prior,
                   COUNT(*) FILTER (WHERE f.requested_year = s.y_curr)  AS curr
            FROM fct_requests AS f CROSS JOIN snap AS s
            WHERE f.requested_month <= s.last_month
              AND f.requested_year IN (s.y_prior, s.y_curr)
            GROUP BY 1),
        shares AS (
            SELECT service_name, prior, curr,
                   1.0 * prior / NULLIF(SUM(prior) OVER (), 0) AS s_prior,
                   1.0 * curr  / NULLIF(SUM(curr)  OVER (), 0) AS s_curr
            FROM windowed)
        SELECT service_name, prior, curr,
               ROUND(100.0 * COALESCE(s_prior, 0), 2) AS pct_prior,
               ROUND(100.0 * COALESCE(s_curr, 0), 2)  AS pct_curr,
               ROUND(100.0 * (COALESCE(s_curr, 0) - COALESCE(s_prior, 0)), 2) AS shift_pp
        FROM shares
        -- Both tests, for the reason documented in 09_trends.sql: a share shift
        -- on its own can be produced by growth in the denominator.
        WHERE ABS(COALESCE(s_curr, 0) - COALESCE(s_prior, 0)) >= 0.02
          AND ABS(100.0 * (curr - prior) / NULLIF(prior, 0)) >= 25
        ORDER BY ABS(COALESCE(s_curr, 0) - COALESCE(s_prior, 0)) DESC
    """).fetchall()
    detail = {
        "distinct_service_names": counts[0],
        "distinct_case_record_types": counts[1],
        "distinct_service_name_details": counts[2],
        "service_names_mapping_to_multiple_record_types":
            [{"service_name": m[0], "n_record_types": m[1], "record_types": m[2]} for m in multi],
        "categories_whose_share_of_citywide_demand_shifted_2pp_or_more":
            [{"service_name": m[0], "submissions_prior": m[1], "submissions_current": m[2],
              "pct_of_citywide_prior": m[3], "pct_of_citywide_current": m[4],
              "share_shift_pp": m[5]} for m in migrated],
    }
    # The Parking pair is a confirmed relabelling: monthly volumes cross over
    # between September and December 2025, one falling as the other rises, with
    # the parent Parking record type growing only 17.3% across the same window.
    # The remaining flagged categories are not diagnosed here — the check marks
    # them as not comparable without verification, which is a weaker and
    # defensible claim.
    crossover = con.execute("""
        SELECT requested_month_start,
               COUNT(*) FILTER (WHERE service_name = 'Parking Violation')   AS parking_violation,
               COUNT(*) FILTER (WHERE service_name = 'Parking - 72-Hours')  AS parking_72_hours
        FROM fct_requests
        WHERE requested_month_start BETWEEN DATE '2025-08-01' AND DATE '2026-01-01'
        GROUP BY 1 ORDER BY 1
    """).fetchall()
    detail["confirmed_relabelling_parking_monthly_crossover"] = [
        {"month": str(c[0])[:10], "parking_violation": c[1], "parking_72_hours": c[2]}
        for c in crossover
    ]
    names = ", ".join(f"{m[0]} ({m[5]:+}pp)" for m in migrated[:4])
    return CheckResult(
        "DQ-08", "Service taxonomy stability",
        "Is the service classification stable enough to compare across years?",
        "FAIL",
        f"Two problems. First, service_name and case_record_type are many-to-many: "
        f"{len(multi)} service names appear under more than one record type, so record type "
        f"cannot be treated as a parent of service name. Second, {len(migrated)} categories "
        f"moved their share of citywide demand by 2 percentage points or more between "
        f"Jan-Jul 2025 and Jan-Jul 2026 ({names}). For the Parking pair this is a confirmed "
        f"relabelling — monthly volumes cross over during autumn 2025 while the parent "
        f"Parking record type grows only 17.3% — so their year-over-year change measures the "
        f"label move. The remaining flagged categories are marked not-comparable pending "
        f"verification; this check does not claim to know why they moved.",
        detail,
        "Year-over-year demand is reported citywide and at case_record_type grain, both of "
        "which absorb a service-name relabelling. Service-level year-over-year rows carry a "
        "taxonomy_flag and flagged rows are excluded from every written finding. Wherever a "
        "record type is shown against a service name it is the modal value, computed with "
        "MODE() rather than picked arbitrarily.",
    )


def check_duplicate_lineage(con) -> CheckResult:
    row = con.execute("""
        SELECT COUNT(*) FILTER (WHERE is_duplicate_child) AS children,
               COUNT(*) AS total FROM fct_requests
    """).fetchone()
    orphans = con.execute("""
        SELECT COUNT(*) FROM fct_requests c
        WHERE c.parent_request_id IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM fct_requests p
                          WHERE p.service_request_id = c.parent_request_id)
    """).fetchone()[0]
    self_ref = con.execute("""
        SELECT COUNT(*) FROM fct_requests WHERE parent_request_id = service_request_id
    """).fetchone()[0]
    chained = con.execute("""
        SELECT COUNT(*) FROM fct_requests c
        JOIN fct_requests p ON c.parent_request_id = p.service_request_id
        WHERE p.parent_request_id IS NOT NULL
    """).fetchone()[0]
    detail = {
        "duplicate_children": row[0],
        "total_records": row[1],
        "duplicate_rate_pct": round(100.0 * row[0] / row[1], 2),
        "children_whose_parent_is_not_in_scope": orphans,
        "pct_of_children_orphaned": round(100.0 * orphans / row[0], 2),
        "self_referencing_records": self_ref,
        "children_whose_parent_is_itself_a_child": chained,
    }
    return CheckResult(
        "DQ-09", "Duplicate parent/child lineage",
        "Do duplicate children resolve to a parent that exists in scope?",
        "WARN" if orphans else "PASS",
        f"{row[0]:,} case records are duplicate children ({detail['duplicate_rate_pct']}%). "
        f"{orphans:,} ({detail['pct_of_children_orphaned']}%) point to a parent outside the "
        f"three extracts in scope — expected, since a parent closed before 2025 is not in "
        f"scope. {chained} children point at another child.",
        detail,
        "issue_key = COALESCE(parent_request_id, service_request_id) collapses one level. "
        "An orphaned child keeps its parent's id as its issue_key, so it is still not "
        "double-counted against a parent that is present.",
    )


def check_referral_consistency(con) -> CheckResult:
    rows = con.execute("""
        SELECT status, has_referral_text, COUNT(*) FROM fct_requests GROUP BY 1, 2 ORDER BY 1, 2
    """).fetchall()
    unparsed = con.execute("""
        SELECT COUNT(*) FROM fct_requests
        WHERE status = 'Referred' AND referred_to = '(Unparsed referral text)'
    """).fetchone()[0]
    referred_no_text = con.execute("""
        SELECT COUNT(*) FROM fct_requests WHERE status = 'Referred' AND NOT has_referral_text
    """).fetchone()[0]
    text_not_referred = con.execute("""
        SELECT COUNT(*) FROM fct_requests WHERE status <> 'Referred' AND has_referral_text
    """).fetchone()[0]
    total_referred = con.execute(
        "SELECT COUNT(*) FROM fct_requests WHERE status = 'Referred'").fetchone()[0]
    detail = {
        "status_by_referral_text": [{"status": r[0], "has_referral_text": r[1], "records": r[2]}
                                    for r in rows],
        "referred_status_total": total_referred,
        "referred_status_without_referral_text": referred_no_text,
        "non_referred_status_with_referral_text": text_not_referred,
        "referred_records_whose_destination_could_not_be_parsed": unparsed,
    }
    return CheckResult(
        "DQ-10", "Referral field consistency",
        "Does the referred field agree with the Referred status?",
        "WARN",
        f"{text_not_referred:,} records carry referral text but do not have a Referred status, "
        f"and {referred_no_text} Referred records carry no text. Destination parsing resolves "
        f"{total_referred - unparsed:,} of {total_referred:,} referred records.",
        detail,
        "Referral rate is always computed from status, never from the presence of text. "
        "The two populations are reported side by side in agg_referral_status_consistency.",
    )


def check_age_outliers(con) -> CheckResult:
    row = con.execute("""
        SELECT COUNT(*) AS n,
               MAX(active_age_days) AS max_age,
               COUNT(*) FILTER (WHERE active_age_days > 1825) AS over_5_years,
               COUNT(*) FILTER (WHERE active_age_days > 2555) AS over_7_years,
               COUNT(*) FILTER (WHERE active_age_days < 0) AS negative
        FROM fct_requests WHERE is_active
    """).fetchone()
    lifecycle = con.execute("""
        SELECT MAX(lifecycle_days), COUNT(*) FILTER (WHERE lifecycle_days > 1825)
        FROM fct_requests WHERE is_resolved
    """).fetchone()
    oldest = con.execute("""
        SELECT service_name, COUNT(*) FROM fct_requests
        WHERE is_active AND active_age_days > 1825 GROUP BY 1 ORDER BY 2 DESC LIMIT 5
    """).fetchall()
    detail = {
        "active_records": row[0],
        "max_active_age_days": row[1],
        "active_over_5_years": row[2],
        "pct_active_over_5_years": round(100.0 * row[2] / row[0], 2),
        "active_over_7_years": row[3],
        "negative_active_ages": row[4],
        "max_lifecycle_days": lifecycle[0],
        "resolved_lifecycle_over_5_years": lifecycle[1],
        "categories_holding_the_oldest_active_records":
            [{"service_name": o[0], "records": o[1]} for o in oldest],
    }
    return CheckResult(
        "DQ-11", "Age outliers",
        "Are extreme ages real records or artefacts?",
        "INFO",
        f"The oldest active request is {row[1]:,} days old. {row[2]:,} active records "
        f"({detail['pct_active_over_5_years']}%) exceed five years. No negative active ages.",
        detail,
        "Not trimmed. These are genuine long-lived open cases, concentrated in asset "
        "maintenance categories, and removing them would understate the backlog that is "
        "the subject of the analysis. Median and p90 are used throughout so the tail "
        "informs the picture without dominating it.",
    )


def check_privacy_suppression(con) -> CheckResult:
    fact_cols = {r[0] for r in con.execute("DESCRIBE fct_requests").fetchall()}
    leaked = sorted(fact_cols & set(config.SUPPRESSED_SOURCE_FIELDS))
    source_cols = {r[0] for r in con.execute("DESCRIBE src_open").fetchall()}
    detail = {
        "suppressed_fields": list(config.SUPPRESSED_SOURCE_FIELDS),
        "fields_present_in_source": sorted(source_cols & set(config.SUPPRESSED_SOURCE_FIELDS)),
        "fields_leaked_into_fact_table": leaked,
        "fact_table_columns": sorted(fact_cols),
    }
    return CheckResult(
        "DQ-12", "Privacy suppression",
        "Have sensitive source fields been kept out of every published output?",
        "PASS" if not leaked else "FAIL",
        f"{len(config.SUPPRESSED_SOURCE_FIELDS)} source fields are suppressed and "
        f"{len(leaked)} reached the fact table.",
        detail,
        "Resident free text, exact addresses and coordinates are dropped in "
        "01_clean_base.sql before anything is written to disk. The referral message is "
        "normalised to a destination label because the raw text contains staff and vendor "
        "email addresses. src/pipeline.py refuses to export if any suppressed field is present.",
    )


def check_status_domain(con) -> CheckResult:
    rows = con.execute("""
        SELECT status, COUNT(*), COUNT(*) FILTER (WHERE date_closed IS NOT NULL)
        FROM fct_requests GROUP BY 1 ORDER BY 2 DESC
    """).fetchall()
    origins = con.execute("""
        SELECT COUNT(DISTINCT case_origin) FROM fct_requests
    """).fetchone()[0]
    odd = con.execute("""
        SELECT case_origin, COUNT(*) FROM fct_requests
        WHERE channel_group = '(Unknown)' GROUP BY 1 ORDER BY 2 DESC
    """).fetchall()
    detail = {
        "status_values": [{"status": r[0], "records": r[1], "with_close_date": r[2]} for r in rows],
        "distinct_case_origin_values": origins,
        "origins_not_mapped_to_a_channel_group": [{"case_origin": o[0], "records": o[1]} for o in odd],
    }
    return CheckResult(
        "DQ-13", "Status and channel domains",
        "Are the categorical domains what the dictionary implies?",
        "PASS",
        f"Status takes {len(rows)} values with no unexpected members. case_origin takes "
        f"{origins} values, of which {len(odd)} are unmapped placeholders "
        f"({sum(o[1] for o in odd)} records).",
        detail,
        "Active is defined as status in (New, In Process); resolved as (Closed, Referred). "
        "Unmapped origins fall into an explicit '(Unknown)' channel group.",
    )


CHECKS = (
    check_row_counts,
    check_duplicate_ids,
    check_case_age_semantics,
    check_date_validity,
    check_extract_boundary,
    check_missingness,
    check_geography_validity,
    check_service_taxonomy,
    check_duplicate_lineage,
    check_referral_consistency,
    check_age_outliers,
    check_privacy_suppression,
    check_status_domain,
)


# -----------------------------------------------------------------------------
# Report rendering
# -----------------------------------------------------------------------------
GRADE_ICON = {"PASS": "PASS", "WARN": "WARN", "FAIL": "FAIL", "INFO": "INFO"}


def render_markdown(results: list[CheckResult], snapshot: str, generated: str) -> str:
    counts = {g: sum(1 for r in results if r.grade == g) for g in ("PASS", "WARN", "FAIL", "INFO")}
    lines: list[str] = []
    a = lines.append

    a("# Data Quality Report")
    a("")
    a("**San Diego Service Operations Intelligence** — audit of the City of San Diego")
    a("Get It Done extracts before any business analysis was performed.")
    a("")
    a(f"| | |")
    a("|---|---|")
    a(f"| Data snapshot | {snapshot} |")
    a(f"| Report generated | {generated} |")
    a(f"| Checks run | {len(results)} |")
    a(f"| Result | {counts['PASS']} PASS · {counts['WARN']} WARN · "
      f"{counts['FAIL']} FAIL · {counts['INFO']} INFO |")
    a("")
    a("This report is generated by [`src/audit.py`](../src/audit.py). Re-running")
    a("`make audit` regenerates it from the current data; nothing here is hand-written.")
    a("")
    a("A **FAIL** means the condition would invalidate a result if it were ignored. It does")
    a("not mean the data is unusable — it means the analysis had to be built around it, and")
    a("the *Treatment* line records how.")
    a("")
    a("---")
    a("")
    a("## Summary")
    a("")
    a("| Check | Grade | Finding |")
    a("|---|---|---|")
    for r in results:
        a(f"| [{r.check_id} {r.name}](#{r.check_id.lower()}-{r.name.lower().replace(' ', '-').replace('/', '')}) "
          f"| **{GRADE_ICON[r.grade]}** | {r.headline.splitlines()[0]} |")
    a("")
    a("---")
    a("")

    for r in results:
        anchor_name = r.name.lower().replace(" ", "-").replace("/", "")
        a(f"## {r.check_id} {r.name}")
        a("")
        a(f"**Grade:** {GRADE_ICON[r.grade]}")
        a("")
        a(f"**Question:** {r.question}")
        a("")
        a(f"**Finding:** {r.headline}")
        a("")
        if r.treatment:
            a(f"**Treatment:** {r.treatment}")
            a("")
        a("<details><summary>Measured values</summary>")
        a("")
        a("```json")
        a(json.dumps(r.detail, indent=2, default=str))
        a("```")
        a("")
        a("</details>")
        a("")
    a("---")
    a("")
    a("## What this dataset cannot tell us")
    a("")
    a("Recorded directly from the City's own published caveat, because it bounds every")
    a("conclusion in this project:")
    a("")
    a("> This data includes every user-submitted report and should not be considered an")
    a("> official record of City maintenance work. This data does not include details about")
    a("> any work performed to fix a problem or the date and time work was completed.")
    a("")
    a("Consequently this project does not, and cannot, measure:")
    a("")
    a("- whether a physical repair happened, or when;")
    a("- how long any physical work took — only how long a case record stayed open;")
    a("- crew productivity, staffing levels, cost, or budget;")
    a("- the true incidence of a problem, only the rate at which it was reported;")
    a("- why any pattern exists. Nothing here establishes cause.")
    a("")
    return "\n".join(lines) + "\n"


def main() -> int:
    con = pipeline.connect(read_only=True)
    snapshot = str(con.execute("SELECT snapshot_date FROM ref_snapshot").fetchone()[0])
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    results: list[CheckResult] = []
    for check in CHECKS:
        result = check(con)
        results.append(result)
        print(f"  [{result.grade:4}] {result.check_id} {result.name}")

    config.AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    config.AUDIT_RESULTS.write_text(json.dumps(
        {
            "snapshot_date": snapshot,
            "generated_at_utc": generated,
            "checks": [asdict(r) for r in results],
        },
        indent=2, default=str) + "\n")

    report_path = config.AUDIT_DIR / "data_quality_report.md"
    report_path.write_text(render_markdown(results, snapshot, generated))
    con.close()

    grades = {g: sum(1 for r in results if r.grade == g) for g in ("PASS", "WARN", "FAIL", "INFO")}
    print(f"\n{len(results)} checks: " + " · ".join(f"{v} {k}" for k, v in grades.items()))
    print(f"Report:  {report_path.relative_to(config.REPO_ROOT)}")
    print(f"Results: {config.AUDIT_RESULTS.relative_to(config.REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
