"""Canonical numeric claims, computed from the generated aggregates.

Every number quoted in README.md, the executive memo and the findings write-up is
defined here once, recomputed from ``data/aggregates/`` on demand, and formatted
in exactly the form the documents must contain.

``scripts/verify_claims.py`` recomputes each claim and asserts that the formatted
string is present in the documents that are supposed to carry it. That makes it
impossible for a written figure to drift from the data without the check failing.

Usage
-----
    from src.claims import build_claims
    claims = build_claims()
    claims["active_backlog"].formatted   # '81,359'
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pandas as pd

try:
    from src import config
except ImportError:  # pragma: no cover
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from src import config


@dataclass(frozen=True)
class Claim:
    """One numeric assertion, its value, and where it must appear."""

    key: str
    description: str
    value: float
    formatted: str
    source: str
    documents: tuple[str, ...] = ()


@lru_cache(maxsize=None)
def agg(name: str) -> pd.DataFrame:
    """Load one aggregate CSV."""
    path = config.AGGREGATES_DIR / f"{name}.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"Aggregate {name} not found. Run: make analyze")
    return pd.read_csv(path)


def kpi(metric_key: str) -> float:
    """Look up one value from agg_executive_kpis."""
    df = agg("agg_executive_kpis")
    row = df.loc[df["metric_key"] == metric_key]
    if row.empty:
        raise KeyError(f"metric_key {metric_key!r} not in agg_executive_kpis")
    return float(row["value"].iloc[0])


def _int(value: float) -> str:
    return f"{int(round(value)):,}"


def _pct(value: float, decimals: int = 1) -> str:
    return f"{value:.{decimals}f}%"


README = "README.md"
MEMO = "06_executive_memo/executive_memo.md"
FINDINGS = "04_analysis/findings.md"


def build_claims() -> dict[str, Claim]:
    """Recompute every claim from the current aggregates."""
    service = agg("agg_service_backlog")
    buckets = agg("agg_backlog_aging_buckets")
    district = agg("agg_geography_district")
    dup_rank = agg("agg_duplicate_rank_impact")
    dup_service = agg("agg_duplicate_by_service")
    referral = agg("agg_referral_destinations")
    yoy = agg("agg_demand_yoy")
    yoy_service = agg("agg_demand_yoy_by_service")
    priority = agg("agg_priority_table")
    percentiles = agg("agg_backlog_age_percentiles")
    concentration = agg("agg_service_concentration")
    channel = agg("agg_channel_summary")

    def svc(name: str, column: str) -> float:
        return float(service.loc[service["service_name"] == name, column].iloc[0])

    def prio(name: str, column: str) -> float:
        return float(priority.loc[priority["service_name"] == name, column].iloc[0])

    top4 = service.nlargest(4, "active_records")
    top4_pct = float(top4["pct_of_active_backlog"].sum())
    top4_names = list(top4["service_name"])

    aged_365_share = float(
        buckets.loc[buckets["age_bucket"].isin(["181-365", "366-730", "731+"]),
                    "n_records"].sum())
    bucket_181_plus_pct = round(
        100.0 * aged_365_share / float(buckets["n_records"].sum()), 1)

    d3 = district.loc[district["council_district"] == "3"].iloc[0]
    d5 = district.loc[district["council_district"] == "5"].iloc[0]
    d4 = district.loc[district["council_district"] == "4"].iloc[0]

    ranks_moved = int((dup_rank["rank_status"] == "moved").sum())
    max_rank_shift = int(dup_rank["rank_shift"].abs().max())

    caltrans = referral.loc[referral["referred_to"] == "Caltrans (State)"].iloc[0]
    external_pct = float(
        referral.loc[referral["referral_scope"] == "External (non-City entity)",
                     "pct_of_referrals"].sum())

    yoy_current = yoy.loc[yoy["requested_year"] == yoy["requested_year"].max()].iloc[0]

    comparable = yoy_service[yoy_service["taxonomy_flag"] == "comparable"]
    top_growth = comparable.nlargest(1, "change_submissions").iloc[0]
    n_flagged = int((yoy_service["taxonomy_flag"] != "comparable").sum())

    all_active = percentiles.loc[
        percentiles["segment"] == "All active requests"].iloc[0]

    top3_priority = list(priority.nsmallest(3, "investigation_rank")["service_name"])

    def prio_share(name: str) -> float:
        return float(priority.loc[priority["service_name"] == name,
                                  "pct_of_city_aged_90_backlog"].iloc[0])

    mobile = channel.loc[channel["case_origin"] == "Mobile"].iloc[0]
    web = channel.loc[channel["case_origin"] == "Web"].iloc[0]

    aging_index = agg("agg_geography_aging_index")
    districts_only = aging_index[
        (aging_index["area_type"] == "Council district")
        & (aging_index["area"] != "(Unknown)")
    ]
    index_max = float(districts_only["aged_concentration_index"].max())
    index_min = float(districts_only["aged_concentration_index"].min())

    sidewalk_pavement_aged = round(
        prio_share("Sidewalk Repair Issue") + prio_share("Pavement Maintenance"), 1)

    sensitivity = agg("agg_priority_weight_sensitivity")
    n_schemes = sensitivity["scheme"].nunique()
    top3 = sensitivity[sensitivity["rank_in_scheme"] <= 3]
    top2 = sensitivity[sensitivity["rank_in_scheme"] <= 2]
    top2_schemes = int(
        top2.groupby("scheme")["service_name"]
        .apply(lambda s: set(s) == {"Sidewalk Repair Issue", "Pavement Maintenance"})
        .sum())
    streetlight_top3 = int(
        top3.groupby("scheme")["service_name"]
        .apply(lambda s: "Street Light Maintenance" in set(s))
        .sum())

    # month_start carries a time component, so compare as dates rather than
    # strings — "2025-12-01 00:00:00" > "2025-12-01" lexically.
    monthly = agg("agg_demand_monthly").copy()
    monthly["month_start"] = pd.to_datetime(monthly["month_start"])
    monthly_2025 = monthly[(monthly["month_start"].dt.year == 2025)
                           & (monthly["coverage_status"] == "complete")]
    assert len(monthly_2025) == 12, "2025 must contribute 12 complete months"
    submissions_2025 = float(monthly_2025["submissions"].sum())

    cohort_bias = agg("agg_closure_cohort_bias")
    cohort = agg("agg_submission_cohort").iloc[0]
    gap = agg("agg_channel_gap_summary").iloc[0]
    record_type = agg("agg_backlog_aging_by_record_type")
    tsw = record_type.loc[record_type["case_record_type"] == "TSW"].iloc[0]

    claims: list[Claim] = [
        # ---- scope -----------------------------------------------------------
        Claim("total_case_records", "Unique case records in scope",
              kpi("total_case_records"), _int(kpi("total_case_records")),
              "agg_executive_kpis.total_case_records", (README, FINDINGS)),
        Claim("total_distinct_issues", "Distinct reported issues in scope",
              kpi("total_distinct_issues"), _int(kpi("total_distinct_issues")),
              "agg_executive_kpis.total_distinct_issues", (FINDINGS,)),

        # ---- Q1 backlog size -------------------------------------------------
        Claim("active_backlog", "Active request backlog, case records",
              kpi("active_backlog"), _int(kpi("active_backlog")),
              "agg_executive_kpis.active_backlog", (README, MEMO, FINDINGS)),
        Claim("active_backlog_distinct_issues", "Active backlog, duplicates collapsed",
              kpi("active_backlog_distinct_issues"),
              _int(kpi("active_backlog_distinct_issues")),
              "agg_executive_kpis.active_backlog_distinct_issues", (README, MEMO, FINDINGS)),
        Claim("active_median_age_days", "Median active request age",
              kpi("active_median_age_days"), _int(kpi("active_median_age_days")),
              "agg_executive_kpis.active_median_age_days", (README, MEMO, FINDINGS)),
        Claim("active_p90_age_days", "P90 active request age",
              kpi("active_p90_age_days"), _int(kpi("active_p90_age_days")),
              "agg_executive_kpis.active_p90_age_days", (README, FINDINGS)),
        Claim("active_mean_age_days", "Mean active request age",
              float(all_active["mean_age_days"]), f"{all_active['mean_age_days']:,.1f}",
              "agg_backlog_age_percentiles.mean_age_days", (FINDINGS,)),
        Claim("active_aged_90_plus", "Active requests aged 90+ days",
              kpi("active_aged_90_plus"), _int(kpi("active_aged_90_plus")),
              "agg_executive_kpis.active_aged_90_plus", (README, MEMO, FINDINGS)),
        Claim("active_aged_90_plus_pct", "Share of active backlog aged 90+ days",
              kpi("active_aged_90_plus_pct"), _pct(kpi("active_aged_90_plus_pct")),
              "agg_executive_kpis.active_aged_90_plus_pct", (README, MEMO, FINDINGS)),
        Claim("active_aged_365_plus", "Active requests aged 365+ days",
              kpi("active_aged_365_plus"), _int(kpi("active_aged_365_plus")),
              "agg_executive_kpis.active_aged_365_plus", (MEMO, FINDINGS)),
        Claim("active_aged_365_plus_pct", "Share of active backlog aged 365+ days",
              kpi("active_aged_365_plus_pct"), _pct(kpi("active_aged_365_plus_pct")),
              "agg_executive_kpis.active_aged_365_plus_pct", (README, MEMO, FINDINGS)),
        Claim("bucket_181_plus_pct", "Share of active backlog older than 180 days",
              bucket_181_plus_pct, _pct(bucket_181_plus_pct),
              "agg_backlog_aging_buckets (181-365 + 366-730 + 731+)", (FINDINGS,)),

        # ---- recorded-lifecycle context -------------------------------------
        # Not quoted in prose on purpose: the closure-cohort total is misleading
        # without its decomposition, so the documents use the submission-cohort
        # figures instead. Retained for the dashboard and the Excel workbook.
        Claim("closed_current_year", "Case records with a recorded closure in 2026",
              kpi("closed_current_year"), _int(kpi("closed_current_year")),
              "agg_executive_kpis.closed_current_year", ()),
        Claim("closed_median_lifecycle", "Median recorded lifecycle, closed in 2026",
              kpi("closed_current_year_median_lifecycle"),
              _int(kpi("closed_current_year_median_lifecycle")),
              "agg_executive_kpis.closed_current_year_median_lifecycle",
              (README, MEMO, FINDINGS)),
        Claim("closed_p90_lifecycle", "P90 recorded lifecycle, closed in 2026",
              kpi("closed_current_year_p90_lifecycle"),
              _int(kpi("closed_current_year_p90_lifecycle")),
              "agg_executive_kpis.closed_current_year_p90_lifecycle", (FINDINGS,)),

        # ---- Q2/Q3 service ---------------------------------------------------
        Claim("top4_share_pct", "Share of active backlog held by the top 4 categories",
              top4_pct, _pct(top4_pct),
              "agg_service_backlog, top 4 by active_records", (README, MEMO, FINDINGS)),
        Claim("sidewalk_active", "Sidewalk Repair Issue active records",
              svc("Sidewalk Repair Issue", "active_records"),
              _int(svc("Sidewalk Repair Issue", "active_records")),
              "agg_service_backlog", (README, FINDINGS)),
        Claim("sidewalk_median_age", "Sidewalk Repair Issue median active age",
              svc("Sidewalk Repair Issue", "median_age_days"),
              _int(svc("Sidewalk Repair Issue", "median_age_days")),
              "agg_service_backlog", (README, FINDINGS)),
        Claim("sidewalk_pct_aged_90", "Sidewalk Repair Issue share aged 90+",
              svc("Sidewalk Repair Issue", "pct_aged_90_plus"),
              _pct(svc("Sidewalk Repair Issue", "pct_aged_90_plus")),
              "agg_service_backlog", (FINDINGS,)),
        # Formatted with one decimal because the median falls between two records
        # (5,590 is even) and rounding it to 1,296 would be a silent edit.
        Claim("pavement_median_age", "Pavement Maintenance median active age",
              svc("Pavement Maintenance", "median_age_days"),
              f'{svc("Pavement Maintenance", "median_age_days"):,.1f}',
              "agg_service_backlog", (README, FINDINGS)),
        Claim("sidewalk_pct_of_city_aged", "Sidewalk share of the citywide 90+ day backlog",
              prio("Sidewalk Repair Issue", "pct_of_city_aged_90_backlog"),
              _pct(prio("Sidewalk Repair Issue", "pct_of_city_aged_90_backlog")),
              "agg_priority_table.pct_of_city_aged_90_backlog", (FINDINGS,)),
        Claim("streetlight_pct_of_city_aged", "Street Light share of the citywide 90+ day backlog",
              prio("Street Light Maintenance", "pct_of_city_aged_90_backlog"),
              _pct(prio("Street Light Maintenance", "pct_of_city_aged_90_backlog")),
              "agg_priority_table.pct_of_city_aged_90_backlog", (FINDINGS,)),
        Claim("pavement_pct_of_city_aged", "Pavement share of the citywide 90+ day backlog",
              prio("Pavement Maintenance", "pct_of_city_aged_90_backlog"),
              _pct(prio("Pavement Maintenance", "pct_of_city_aged_90_backlog")),
              "agg_priority_table.pct_of_city_aged_90_backlog", (FINDINGS,)),
        Claim("sidewalk_pavement_combined_aged", "Sidewalk + Pavement share of citywide 90+ backlog",
              sidewalk_pavement_aged, _pct(sidewalk_pavement_aged),
              "agg_priority_table.pct_of_city_aged_90_backlog, summed", (MEMO, FINDINGS)),

        # ---- priority weight sensitivity (#7) --------------------------------
        Claim("weight_schemes_tested", "Weighting schemes tested",
              float(n_schemes), str(n_schemes),
              "agg_priority_weight_sensitivity", (FINDINGS,)),
        Claim("top2_stable_scheme_count", "Schemes where Sidewalk and Pavement are the top two",
              float(top2_schemes), str(top2_schemes),
              "agg_priority_weight_sensitivity", (FINDINGS,)),
        Claim("streetlight_top3_scheme_count", "Schemes where Street Light is top three",
              float(streetlight_top3), str(streetlight_top3),
              "agg_priority_weight_sensitivity", (FINDINGS,)),
        Claim("streetlight_active", "Street Light Maintenance active records",
              svc("Street Light Maintenance", "active_records"),
              _int(svc("Street Light Maintenance", "active_records")),
              "agg_service_backlog", (FINDINGS,)),
        Claim("streetlight_dup_rate", "Street Light Maintenance duplicate rate",
              svc("Street Light Maintenance", "duplicate_rate_pct"),
              _pct(svc("Street Light Maintenance", "duplicate_rate_pct")),
              "agg_service_backlog", (README, MEMO, FINDINGS)),
        Claim("streetlight_dup_children", "Street Light Maintenance duplicate child records",
              svc("Street Light Maintenance", "active_duplicate_children"),
              _int(svc("Street Light Maintenance", "active_duplicate_children")),
              "agg_service_backlog", (README, MEMO, FINDINGS)),
        Claim("pothole_dup_rate", "Pothole duplicate rate (highest of any scored category)",
              float(dup_service.loc[dup_service["service_name"] == "Pothole",
                                    "duplicate_rate_pct"].iloc[0]),
              _pct(float(dup_service.loc[dup_service["service_name"] == "Pothole",
                                         "duplicate_rate_pct"].iloc[0])),
              "agg_duplicate_by_service", (FINDINGS,)),
        Claim("pothole_active", "Pothole active records",
              svc("Pothole", "active_records"), _int(svc("Pothole", "active_records")),
              "agg_service_backlog", (FINDINGS,)),
        Claim("parking72_median_age", "Parking - 72-Hours median active age",
              svc("Parking - 72-Hours", "median_age_days"),
              _int(svc("Parking - 72-Hours", "median_age_days")),
              "agg_service_backlog", (FINDINGS,)),
        Claim("top10_cumulative_pct", "Share of backlog held by the top 10 categories",
              float(concentration.loc[concentration["n_categories"] == 10,
                                      "cumulative_pct_of_backlog"].iloc[0]),
              _pct(float(concentration.loc[concentration["n_categories"] == 10,
                                           "cumulative_pct_of_backlog"].iloc[0])),
              "agg_service_concentration", (FINDINGS,)),

        # ---- Q5/Q6 geography -------------------------------------------------
        Claim("d3_active", "District 3 active records",
              float(d3["active_records"]), _int(float(d3["active_records"])),
              "agg_geography_district", (README, FINDINGS)),
        Claim("d3_pct", "District 3 share of active backlog",
              float(d3["pct_of_active_backlog"]), _pct(float(d3["pct_of_active_backlog"])),
              "agg_geography_district", (README, FINDINGS)),
        Claim("d5_backlog_ratio", "District 5 backlog per recent submission",
              float(d5["backlog_per_recent_submission"]),
              f"{d5['backlog_per_recent_submission']:.3f}",
              "agg_geography_district", (FINDINGS,)),
        Claim("d4_backlog_ratio", "District 4 backlog per recent submission",
              float(d4["backlog_per_recent_submission"]),
              f"{d4['backlog_per_recent_submission']:.3f}",
              "agg_geography_district", (FINDINGS,)),
        Claim("d5_median_age", "District 5 median active age",
              float(d5["median_age_days"]), _int(float(d5["median_age_days"])),
              "agg_geography_district", (FINDINGS,)),
        Claim("aging_index_max", "Highest district aged-concentration index",
              index_max, f"{index_max:.3f}",
              "agg_geography_aging_index", (README, FINDINGS)),
        Claim("aging_index_min", "Lowest district aged-concentration index",
              index_min, f"{index_min:.3f}",
              "agg_geography_aging_index", (README, FINDINGS)),

        # ---- Q7/Q8 duplicates ------------------------------------------------
        Claim("duplicate_rate_total_pct", "Duplicate-child rate, all case records",
              kpi("duplicate_rate_total_pct"), _pct(kpi("duplicate_rate_total_pct")),
              "agg_executive_kpis.duplicate_rate_total_pct", (FINDINGS,)),
        Claim("duplicate_children_active", "Duplicate children in the active backlog",
              kpi("duplicate_children_active"), _int(kpi("duplicate_children_active")),
              "agg_executive_kpis.duplicate_children_active", (README, MEMO, FINDINGS)),
        Claim("duplicate_rate_active_pct", "Duplicate-child rate, active backlog",
              kpi("duplicate_rate_active_pct"), _pct(kpi("duplicate_rate_active_pct")),
              "agg_executive_kpis.duplicate_rate_active_pct", (README, MEMO, FINDINGS)),
        Claim("dup_ranks_moved", "Top-20 categories whose rank moved when duplicates collapse",
              ranks_moved, str(ranks_moved),
              "agg_duplicate_rank_impact", (README, FINDINGS)),
        Claim("dup_max_rank_shift", "Largest rank shift from collapsing duplicates",
              max_rank_shift, str(max_rank_shift),
              "agg_duplicate_rank_impact", (FINDINGS,)),

        # ---- Q9 referrals ----------------------------------------------------
        Claim("referred_rate_resolved_pct", "Referred share of terminal-status records",
              kpi("referred_rate_resolved_pct"), _pct(kpi("referred_rate_resolved_pct")),
              "agg_executive_kpis.referred_rate_resolved_pct", (README, FINDINGS)),
        Claim("referred_records_total", "Case records with a Referred status",
              kpi("referred_records_total"), _int(kpi("referred_records_total")),
              "agg_executive_kpis.referred_records_total", (FINDINGS,)),
        Claim("referred_external_pct", "Referrals routed outside the City",
              external_pct, _pct(external_pct),
              "agg_referral_destinations", (README, FINDINGS)),
        Claim("caltrans_pct", "Caltrans share of referrals",
              float(caltrans["pct_of_referrals"]), _pct(float(caltrans["pct_of_referrals"])),
              "agg_referral_destinations", (FINDINGS,)),
        Claim("caltrans_records", "Referrals routed to Caltrans",
              float(caltrans["referred_records"]), _int(float(caltrans["referred_records"])),
              "agg_referral_destinations", (FINDINGS,)),

        # ---- Q10 channel -----------------------------------------------------
        Claim("mobile_share_pct", "Mobile share of all case records",
              float(mobile["pct_of_all_records"]), _pct(float(mobile["pct_of_all_records"])),
              "agg_channel_summary", (FINDINGS,)),
        Claim("web_share_pct", "Web share of all case records",
              float(web["pct_of_all_records"]), _pct(float(web["pct_of_all_records"])),
              "agg_channel_summary", (FINDINGS,)),
        Claim("mobile_median_lifecycle", "Mobile median recorded lifecycle",
              float(mobile["median_lifecycle_days"]),
              _int(float(mobile["median_lifecycle_days"])),
              "agg_channel_summary", (FINDINGS,)),
        Claim("web_median_lifecycle", "Web median recorded lifecycle",
              float(web["median_lifecycle_days"]),
              _int(float(web["median_lifecycle_days"])),
              "agg_channel_summary", (FINDINGS,)),

        # ---- closure-cohort bias and the submission-cohort answer ------------
        Claim("closure_cohort_same_year_pct",
              "Share of this year's closures that were also submitted this year",
              float(cohort_bias.iloc[0]["pct_of_closures"]),
              _pct(float(cohort_bias.iloc[0]["pct_of_closures"])),
              "agg_closure_cohort_bias", (README, FINDINGS)),
        Claim("closure_cohort_prior_year_median",
              "Median lifecycle of prior-year submissions closed this year",
              float(cohort_bias.iloc[1]["median_lifecycle_days"]),
              _int(float(cohort_bias.iloc[1]["median_lifecycle_days"])),
              "agg_closure_cohort_bias", (FINDINGS,)),
        Claim("cohort_submissions", "Requests submitted Jan-Jun 2026",
              float(cohort["submissions"]), _int(float(cohort["submissions"])),
              "agg_submission_cohort", (FINDINGS,)),
        Claim("cohort_pct_resolved", "Share of the Jan-Jun 2026 cohort now resolved",
              float(cohort["pct_resolved"]), _pct(float(cohort["pct_resolved"])),
              "agg_submission_cohort", (README, MEMO, FINDINGS)),
        Claim("cohort_pct_still_active", "Share of the Jan-Jun 2026 cohort still active",
              float(cohort["pct_still_active"]), _pct(float(cohort["pct_still_active"])),
              "agg_submission_cohort", (FINDINGS,)),
        Claim("cohort_median_lifecycle", "Median lifecycle within the Jan-Jun 2026 cohort",
              float(cohort["median_lifecycle_days"]),
              _int(float(cohort["median_lifecycle_days"])),
              "agg_submission_cohort", (README, MEMO, FINDINGS)),
        Claim("cohort_p90_lifecycle", "P90 lifecycle within the Jan-Jun 2026 cohort",
              float(cohort["p90_lifecycle_days"]),
              _int(float(cohort["p90_lifecycle_days"])),
              "agg_submission_cohort", (FINDINGS,)),

        # ---- Q10 channel, controlled ----------------------------------------
        Claim("channel_cells_compared", "Service categories in the controlled channel comparison",
              float(gap["category_cells_compared"]), _int(float(gap["category_cells_compared"])),
              "agg_channel_gap_summary", (FINDINGS,)),
        Claim("channel_median_gap_days", "Median absolute mobile-vs-web gap, within category",
              float(gap["median_abs_gap_days"]), _int(float(gap["median_abs_gap_days"])),
              "agg_channel_gap_summary", (README, FINDINGS)),
        Claim("channel_cells_within_20", "Categories where the channel gap is 20 days or less",
              float(gap["cells_within_20_days"]), _int(float(gap["cells_within_20_days"])),
              "agg_channel_gap_summary", (FINDINGS,)),

        # ---- concentration by owning staff group ----------------------------
        Claim("tsw_pct_of_backlog", "Share of active records carrying the TSW case_record_type label",
              float(tsw["pct_of_active_backlog"]), _pct(float(tsw["pct_of_active_backlog"])),
              "agg_backlog_aging_by_record_type", (README, FINDINGS)),
        Claim("tsw_active_records", "Active records in the TSW record type",
              float(tsw["active_records"]), _int(float(tsw["active_records"])),
              "agg_backlog_aging_by_record_type", (FINDINGS,)),

        # ---- Q11 trends ------------------------------------------------------
        Claim("submissions_2025_full_year", "Submissions during calendar 2025 (12 complete months)",
              submissions_2025, _int(submissions_2025),
              "agg_demand_monthly, complete months of 2025", (README,)),
        Claim("demand_ytd_current", "Submissions Jan-Jul 2026",
              kpi("demand_ytd_current"), _int(kpi("demand_ytd_current")),
              "agg_executive_kpis.demand_ytd_current", (README, FINDINGS)),
        Claim("demand_ytd_prior", "Submissions Jan-Jul 2025",
              kpi("demand_ytd_prior"), _int(kpi("demand_ytd_prior")),
              "agg_executive_kpis.demand_ytd_prior", (README, FINDINGS)),
        Claim("demand_yoy_change_pct", "Year-over-year change in submissions",
              kpi("demand_yoy_change_pct"), _pct(kpi("demand_yoy_change_pct")),
              "agg_executive_kpis.demand_yoy_change_pct", (README, FINDINGS)),
        Claim("yoy_flagged_categories", "Service categories flagged as not comparable",
              n_flagged, str(n_flagged),
              "agg_demand_yoy_by_service.taxonomy_flag", (FINDINGS,)),
        Claim("top_growth_service", "Largest comparable category increase, records",
              float(top_growth["change_submissions"]),
              _int(float(top_growth["change_submissions"])),
              "agg_demand_yoy_by_service (comparable only)", (FINDINGS,)),
    ]

    # Names used in prose that must match the data, not numbers but still verified.
    claims.append(Claim(
        "top4_category_names", "The four largest active-backlog categories",
        float(len(top4_names)), " / ".join(top4_names),
        "agg_service_backlog, top 4 by active_records", ()))
    claims.append(Claim(
        "top3_priority_names", "Top three investigation priorities",
        float(len(top3_priority)), " / ".join(top3_priority),
        "agg_priority_table, investigation_rank 1-3", ()))

    return {c.key: c for c in claims}


if __name__ == "__main__":
    for key, claim in build_claims().items():
        print(f"{key:34} {claim.formatted:>28}   {claim.description}")
