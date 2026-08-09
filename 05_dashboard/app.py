"""Streamlit dashboard for the San Diego service-operations analysis.

Reads only the generated aggregates in ``data/aggregates/`` — it never touches
raw data, so no suppressed field can reach the screen.

Run:
    make dashboard-app
    # or: streamlit run 05_dashboard/app.py

A static, self-contained version of the same content is built by
``src/build_dashboard.py`` to ``05_dashboard/dashboard.html``; that is the one to
open if Streamlit is not installed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src import claims as claims_mod, config  # noqa: E402

BOUNDARY_NOTE = (
    "**Data boundary.** Get It Done records represent submitted service requests and case "
    "statuses, not verified maintenance completion. A closed case records a case closure, "
    "not a completed repair. Nothing here measures crew performance, and no relationship "
    "shown is causal."
)

SERIES_1 = "#2a78d6"   # typical / recent / within threshold
SERIES_2 = "#eb6834"   # tail / aged / duplicated

st.set_page_config(
    page_title="San Diego Service Operations Intelligence",
    page_icon="🛠",
    layout="wide",
)


@st.cache_data
def load(name: str) -> pd.DataFrame:
    return claims_mod.agg(name)


@st.cache_data
def load_claims() -> dict:
    return {k: v.formatted for k, v in claims_mod.build_claims().items()}


def require_aggregates() -> bool:
    if not (config.AGGREGATES_DIR / "agg_executive_kpis.csv").exists():
        st.error(
            "Aggregates not found. Build them first:\n\n"
            "```\nmake install\nmake download\nmake analyze\n```"
        )
        return False
    return True


def main() -> None:
    if not require_aggregates():
        return

    c = load_claims()
    meta = json.loads(config.RUN_METADATA.read_text())
    snapshot = meta["snapshot_date"]

    st.title("San Diego Service Operations Intelligence")
    st.caption(
        f"Active request backlog, ageing and routing — City of San Diego Get It Done "
        f"programme · data snapshot {snapshot} · "
        f"source: City of San Diego Open Data Portal"
    )
    st.warning(BOUNDARY_NOTE)

    # ---- KPI row ------------------------------------------------------------
    cols = st.columns(6)
    cols[0].metric("Active backlog", c["active_backlog"],
                   help=f"{c['active_backlog_distinct_issues']} distinct issues once "
                        f"duplicate children are collapsed onto their parent")
    cols[1].metric("Aged 90+ days", c["active_aged_90_plus"],
                   delta=f"{c['active_aged_90_plus_pct']} of queue", delta_color="off")
    cols[2].metric("Aged 365+ days", c["active_aged_365_plus"],
                   delta=f"{c['active_aged_365_plus_pct']} of queue", delta_color="off")
    cols[3].metric("Median active age", f"{c['active_median_age_days']} days",
                   delta=f"P90 {c['active_p90_age_days']} days", delta_color="off")
    cols[4].metric("Duplicate rate, active", c["duplicate_rate_active_pct"],
                   delta=f"{c['duplicate_children_active']} child records", delta_color="off")
    cols[5].metric("Demand, Jan–Jul YoY", f"+{c['demand_yoy_change_pct']}",
                   delta=f"{c['demand_ytd_current']} vs {c['demand_ytd_prior']}",
                   delta_color="off")

    tabs = st.tabs([
        "Backlog & ageing", "Service categories", "Geography",
        "Duplicates", "Referrals", "Channels", "Trends", "Priority",
    ])

    # ---- Backlog & ageing ---------------------------------------------------
    with tabs[0]:
        st.subheader("Age profile of the active queue")
        st.caption("Q1 · How large is the active backlog, and how old is it?")
        buckets = load("agg_backlog_aging_buckets").sort_values("bucket_order")
        st.markdown(
            f"The queue is not short-lived inflow. **{c['active_aged_90_plus_pct']}** of "
            f"active requests are past 90 days and **{c['active_aged_365_plus_pct']}** past "
            f"a year. The single largest bucket is the oldest one."
        )
        st.bar_chart(buckets.set_index("age_bucket")["n_records"],
                     color=SERIES_2, height=340)
        st.dataframe(
            buckets[["age_bucket", "n_records", "n_distinct_issues", "median_age_days",
                     "pct_of_active_backlog", "cumulative_pct"]],
            hide_index=True, use_container_width=True)

        st.subheader("Percentile spine")
        st.caption("Median and P90 are reported with the mean so the skew is visible.")
        st.dataframe(load("agg_backlog_age_percentiles"), hide_index=True,
                     use_container_width=True)

    # ---- Service categories -------------------------------------------------
    with tabs[1]:
        st.subheader("Where the active workload sits")
        st.caption("Q2, Q3 & Q4 · Largest queues, oldest queues, longest tails.")
        service = load("agg_service_backlog")
        top_n = st.slider("Categories to show", 5, min(30, len(service)), 12, key="svc_n")
        top = service.nlargest(top_n, "active_records")
        st.markdown(
            f"The top four categories hold **{c['top4_share_pct']}** of the entire active "
            f"backlog: {c['top4_category_names'].replace(' / ', ', ')}."
        )
        st.bar_chart(top.set_index("service_name")["active_records"],
                     color=SERIES_1, height=420, horizontal=True)

        st.markdown("**Median vs P90 active age** — a wide gap means a long tail rather "
                    "than a uniformly slow queue.")
        tail = load("agg_service_tail_risk").nlargest(top_n, "p90_age_days")
        st.dataframe(
            tail[["service_name", "active_records", "median_age_days", "p90_age_days",
                  "p90_to_median_ratio", "p90_z_score", "tail_flag"]],
            hide_index=True, use_container_width=True)

        with st.expander("Full service-category table"):
            st.dataframe(service, hide_index=True, use_container_width=True)

    # ---- Geography ----------------------------------------------------------
    with tabs[2]:
        st.subheader("Geography: volume against aged concentration")
        st.caption("Q5 & Q6 · Which districts carry the most work, and is any queue unusually old?")
        st.info(
            "District counts are not comparable as service levels. This dataset carries no "
            "population, street-mileage or asset denominators, so a larger district with more "
            "streetlights will generate more streetlight reports for reasons unrelated to "
            "service quality."
        )
        district = load("agg_geography_district")
        left, right = st.columns(2)
        with left:
            st.markdown("**Active backlog by council district**")
            st.bar_chart(district.set_index("council_district")["active_records"],
                         color=SERIES_1, height=340, horizontal=True)
        with right:
            st.markdown("**Aged-concentration index** (1.000 = the aged share queue size implies)")
            index_df = load("agg_geography_aging_index")
            index_df = index_df[index_df["area_type"] == "Council district"]
            st.bar_chart(index_df.set_index("area")["aged_concentration_index"],
                         color=SERIES_2, height=340, horizontal=True)
        st.markdown(
            f"The index spans only **{c['aging_index_min']}** to **{c['aging_index_max']}** "
            f"across districts, so aged work is spread roughly in proportion to queue size "
            f"rather than concentrated in any one district."
        )
        st.dataframe(district, hide_index=True, use_container_width=True)

        with st.expander("Community planning areas (100+ active records)"):
            st.dataframe(load("agg_geography_community"), hide_index=True,
                         use_container_width=True)

    # ---- Duplicates ---------------------------------------------------------
    with tabs[3]:
        st.subheader("Repeat reporting")
        st.caption("Q7 & Q8 · How much of the queue is duplicates, and does removing them "
                   "change the answer?")
        st.markdown(
            f"**{c['duplicate_rate_active_pct']}** of active case records are duplicate "
            f"children ({c['duplicate_children_active']} records). Street Light Maintenance "
            f"contributes the most — **{c['streetlight_dup_children']}** child records, "
            f"{c['streetlight_dup_rate']} of its own queue. Collapsing duplicates moves "
            f"**{c['dup_ranks_moved']}** of the top 20 categories, never by more than "
            f"{c['dup_max_rank_shift']} positions."
        )
        st.dataframe(load("agg_duplicate_summary"), hide_index=True, use_container_width=True)
        st.markdown("**Does collapsing duplicates reorder the priority list?**")
        st.dataframe(load("agg_duplicate_rank_impact"), hide_index=True,
                     use_container_width=True)
        with st.expander("Duplicate rate by category and cluster sizes"):
            st.dataframe(load("agg_duplicate_by_service"), hide_index=True,
                         use_container_width=True)
            st.dataframe(load("agg_duplicate_cluster_size"), hide_index=True,
                         use_container_width=True)

    # ---- Referrals ----------------------------------------------------------
    with tabs[4]:
        st.subheader("Where referred requests go")
        st.caption("Q9 · What share of requests are referred, and where are they concentrated?")
        st.markdown(
            f"**{c['referred_rate_resolved_pct']}** of resolved case records were referred "
            f"rather than closed, and **{c['referred_external_pct']}** of those left the City. "
            f"Caltrans alone takes **{c['caltrans_pct']}** of all referrals "
            f"({c['caltrans_records']} records). A referral is a hand-off, not an outcome."
        )
        dest = load("agg_referral_destinations").nlargest(15, "referred_records")
        st.bar_chart(dest.set_index("referred_to")["referred_records"],
                     color=SERIES_2, height=440, horizontal=True)
        st.dataframe(load("agg_referral_by_service"), hide_index=True, use_container_width=True)
        with st.expander("Referral status consistency (audit check DQ-10)"):
            st.dataframe(load("agg_referral_status_consistency"), hide_index=True,
                         use_container_width=True)

    # ---- Channels -----------------------------------------------------------
    with tabs[5]:
        st.subheader("Submission channel")
        st.caption("Q10 · Do channels show different volume, status or ageing patterns?")
        st.info(
            "Channel is chosen by the reporter and is confounded with what is being reported: "
            "waste collection arrives mostly by web and phone, parking mostly by mobile. Any "
            "raw difference between channels is association, not effect. The controlled "
            "comparison below holds service category constant."
        )
        st.dataframe(load("agg_channel_summary"), hide_index=True, use_container_width=True)
        st.markdown("**Within a single service category, do resident channels differ?**")
        st.dataframe(load("agg_channel_controlled_comparison"), hide_index=True,
                     use_container_width=True)
        with st.expander("What each channel is used to report"):
            st.dataframe(load("agg_channel_mix_by_service"), hide_index=True,
                         use_container_width=True)

    # ---- Trends -------------------------------------------------------------
    with tabs[6]:
        st.subheader("Demand over time")
        st.caption("Q11 · How has demand changed where the source data allows a fair comparison?")
        monthly = load("agg_demand_monthly").copy()
        monthly["month_start"] = pd.to_datetime(monthly["month_start"])
        complete = monthly[monthly["coverage_status"] == "complete"]
        st.markdown(
            f"January–July submissions rose **{c['demand_yoy_change_pct']}** year over year "
            f"({c['demand_ytd_prior']} to {c['demand_ytd_current']}). Only complete months "
            f"are charted — months before January 2025 are not fully covered by the extracts "
            f"in scope and would show a false decline."
        )
        st.line_chart(complete.set_index("month_start")["submissions"],
                      color=SERIES_1, height=340)
        st.dataframe(load("agg_demand_yoy"), hide_index=True, use_container_width=True)

        st.markdown(
            f"**Category-level year-over-year carries a health warning.** "
            f"{c['yoy_flagged_categories']} categories are flagged as not comparable — most "
            f"visibly a confirmed relabelling between two Parking categories during autumn "
            f"2025. Filter to `comparable` before reading any category change."
        )
        yoy_service = load("agg_demand_yoy_by_service")
        only_comparable = st.checkbox("Show comparable categories only", value=True)
        view = (yoy_service[yoy_service["taxonomy_flag"] == "comparable"]
                if only_comparable else yoy_service)
        st.dataframe(view, hide_index=True, use_container_width=True)
        st.dataframe(load("agg_demand_yoy_by_record_type"), hide_index=True,
                     use_container_width=True)

    # ---- Priority -----------------------------------------------------------
    with tabs[7]:
        st.subheader("Investigation priority")
        st.caption("Q12 · Which operational areas should leadership look at first?")
        st.info(
            "A triage order, not a performance ranking. Score = 0.45 × share of the city's "
            "90+ day backlog + 0.35 × share of the category's own queue aged 90+ + 0.20 × "
            "median active age, each as a percentile rank across categories with 500+ active "
            "records. This dataset holds no staffing, budget or work-completion data, so "
            "nothing here indicates that any area is under-resourced or under-performing."
        )
        st.dataframe(load("agg_priority_table"), hide_index=True, use_container_width=True)
        st.markdown("**Service × council district cells with the most aged work**")
        st.dataframe(load("agg_priority_hotspots").head(40), hide_index=True,
                     use_container_width=True)

    st.divider()
    st.caption(
        "Source: City of San Diego Open Data Portal — Reports of non-emergency problems "
        "submitted by users of Get It Done. Method: 07_methodology/methodology.md · "
        "Data quality: 02_data_audit/data_quality_report.md"
    )


if __name__ == "__main__":
    main()
