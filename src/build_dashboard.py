"""Build the self-contained static dashboard from the generated aggregates.

Produces ``05_dashboard/dashboard.html`` — a single file with no external
requests, readable in light and dark mode, that a reviewer can open directly.

Every panel answers one of the twelve questions in the business brief. There are
no decorative charts: if a panel does not change what a reader would do, it is
not in the file.

Usage
-----
    python -m src.build_dashboard
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

try:
    from src import charts, claims as claims_mod, config
except ImportError:  # pragma: no cover
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from src import charts, claims as claims_mod, config

BOUNDARY_NOTE = (
    "Get It Done records represent submitted service requests and case statuses, "
    "not verified maintenance completion."
)
DISCLOSURE = (
    "Independent portfolio case study using public City of San Diego data. Not "
    "commissioned by, affiliated with, or endorsed by the City of San Diego."
)

STYLE = """
:root{
  color-scheme: light;
  --page:#f9f9f7; --surface-1:#fcfcfb;
  --text-primary:#0b0b0b; --text-secondary:#52514e; --muted:#898781;
  --grid:#e1e0d9; --axis:#c3c2b7; --border:rgba(11,11,11,0.10);
  --series-1:#2a78d6; --series-2:#eb6834;
  --critical:#d03b3b; --warning:#fab219; --good:#0ca30c;
  --chip:#f0efec;
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    color-scheme: dark;
    --page:#0d0d0d; --surface-1:#1a1a19;
    --text-primary:#ffffff; --text-secondary:#c3c2b7; --muted:#898781;
    --grid:#2c2c2a; --axis:#383835; --border:rgba(255,255,255,0.10);
    --series-1:#3987e5; --series-2:#d95926;
    --critical:#d03b3b; --warning:#fab219; --good:#0ca30c;
    --chip:#262624;
  }
}
:root[data-theme="dark"]{
  color-scheme: dark;
  --page:#0d0d0d; --surface-1:#1a1a19;
  --text-primary:#ffffff; --text-secondary:#c3c2b7; --muted:#898781;
  --grid:#2c2c2a; --axis:#383835; --border:rgba(255,255,255,0.10);
  --series-1:#3987e5; --series-2:#d95926;
  --chip:#262624;
}
*{box-sizing:border-box}
body{
  margin:0; background:var(--page); color:var(--text-primary);
  font-family:system-ui,-apple-system,"Segoe UI",sans-serif;
  font-size:15px; line-height:1.5;
}
.wrap{max-width:1180px;margin:0 auto;padding:28px 20px 64px}
header.top{margin-bottom:22px}
h1{font-size:26px;margin:0 0 6px;letter-spacing:-0.01em}
.sub{color:var(--text-secondary);font-size:14px;margin:0}
.meta{color:var(--muted);font-size:13px;margin-top:8px}
.disclosure{color:var(--muted);font-size:12.5px;margin:6px 0 0;font-style:italic}
.section{margin:34px 0 14px;display:flex;align-items:baseline;gap:12px;flex-wrap:wrap}
.section-n{font-size:12px;font-weight:700;color:var(--series-1);letter-spacing:.1em;
  border:1px solid var(--series-1);border-radius:4px;padding:2px 7px;flex:none}
.section-t{font-size:18px;margin:0;letter-spacing:-0.01em}
.section-s{flex-basis:100%;margin:2px 0 0;color:var(--text-secondary);font-size:13.5px}
.boundary{
  margin:18px 0 26px;padding:12px 14px;border-radius:8px;
  border:1px solid var(--border);border-left:3px solid var(--series-2);
  background:var(--surface-1);color:var(--text-secondary);font-size:13.5px;
}
.boundary strong{color:var(--text-primary)}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(178px,1fr));gap:12px;margin-bottom:26px}
.tile{background:var(--surface-1);border:1px solid var(--border);border-radius:10px;padding:14px 15px}
.tile .k{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.05em}
.tile .v{font-size:28px;font-weight:600;margin:6px 0 2px;letter-spacing:-0.02em}
.tile .n{font-size:12.5px;color:var(--text-secondary)}
section.panel{background:var(--surface-1);border:1px solid var(--border);border-radius:10px;
  padding:18px 20px 20px;margin-bottom:18px;overflow:hidden}
section.panel.emphasis{border-left:4px solid var(--series-1);
  box-shadow:0 1px 3px rgba(0,0,0,0.06)}
section.panel.emphasis h2{font-size:18px}
.panel h2{font-size:16px;margin:0 0 3px;letter-spacing:-0.005em}
.panel .q{font-size:13px;color:var(--muted);margin:0 0 4px}
.panel .read{font-size:13.5px;color:var(--text-secondary);margin:8px 0 12px}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:18px}
@media (max-width:880px){.grid2{grid-template-columns:1fr}}
.chart-scroll{overflow-x:auto}
svg.chart{display:block;width:100%;height:auto;min-width:520px}
.legend{display:flex;gap:16px;flex-wrap:wrap;margin:2px 0 12px}
.lg-item{display:inline-flex;align-items:center;gap:6px;font-size:12.5px;color:var(--text-secondary)}
.lg-swatch{width:11px;height:11px;border-radius:3px;display:inline-block}
text.ax-label{fill:var(--text-secondary);font-size:12px;font-family:inherit}
text.ax-value{fill:var(--text-primary);font-size:12px;font-family:inherit;font-variant-numeric:tabular-nums}
text.ax-tick{fill:var(--muted);font-size:11px;font-family:inherit;font-variant-numeric:tabular-nums}
text.ax-caption{fill:var(--muted);font-size:11.5px;font-family:inherit}
line.grid{stroke:var(--grid);stroke-width:1}
line.axis{stroke:var(--axis);stroke-width:1}
line.connector{stroke:var(--axis);stroke-width:2}
table{width:100%;border-collapse:collapse;font-size:13.5px}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--border)}
th{color:var(--muted);font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.04em}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
tbody tr:last-child td{border-bottom:none}
.tag{display:inline-block;padding:1px 8px;border-radius:20px;font-size:11.5px;
  background:var(--chip);color:var(--text-secondary);white-space:nowrap}
.table-scroll{overflow-x:auto}
footer{margin-top:30px;padding-top:18px;border-top:1px solid var(--border);
  color:var(--muted);font-size:12.5px}
footer a{color:var(--text-secondary)}
"""


def tile(key: str, value: str, note: str) -> str:
    return (f'<div class="tile"><div class="k">{charts.esc(key)}</div>'
            f'<div class="v">{charts.esc(value)}</div>'
            f'<div class="n">{charts.esc(note)}</div></div>')


def panel(title: str, question: str, reading: str, body: str,
          emphasis: bool = False) -> str:
    """One analysis panel. `emphasis` marks the decision-relevant panels so the
    layout is not visually flat — the reader's eye should land on the findings
    that change what leadership would do."""
    css = "panel emphasis" if emphasis else "panel"
    return (f'<section class="{css}"><h2>{charts.esc(title)}</h2>'
            f'<p class="q">{charts.esc(question)}</p>'
            f'<p class="read">{reading}</p>{body}</section>')


def section(number: str, title: str, standfirst: str) -> str:
    """A tier heading, so the dashboard reads as an argument rather than a pile
    of charts."""
    return (f'<div class="section"><span class="section-n">{charts.esc(number)}</span>'
            f'<h2 class="section-t">{charts.esc(title)}</h2>'
            f'<p class="section-s">{charts.esc(standfirst)}</p></div>')


def build_html() -> str:
    c = claims_mod.build_claims()
    agg = claims_mod.agg

    snapshot = json.loads(config.RUN_METADATA.read_text())["snapshot_date"]
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    parts: list[str] = []
    parts.append('<div class="wrap">')
    parts.append(
        '<header class="top">'
        '<h1>San Diego Service Operations Intelligence</h1>'
        '<p class="sub">Active request inventory, aging and routing — '
        'City of San Diego Get It Done program</p>'
        f'<p class="meta">Data snapshot {charts.esc(snapshot)} · '
        f'built {charts.esc(generated)} · source: City of San Diego Open Data Portal</p>'
        f'<p class="disclosure">{charts.esc(DISCLOSURE)}</p>'
        '</header>'
    )
    parts.append(
        f'<div class="boundary"><strong>Data boundary.</strong> {charts.esc(BOUNDARY_NOTE)} '
        'A record reaching Closed or Referred status means it reached a terminal Get It Done '
        'status, not that a repair occurred. This source carries no work-order, staffing or '
        'capacity data, so nothing here measures crew performance and no relationship shown '
        'is causal.</div>'
    )

    # ---- KPI tiles ----------------------------------------------------------
    parts.append('<div class="tiles">')
    parts.append(tile("Active backlog", c["active_backlog"].formatted,
                      f'{c["active_backlog_distinct_issues"].formatted} distinct issues'))
    parts.append(tile("Aged 90+ days", c["active_aged_90_plus"].formatted,
                      f'{c["active_aged_90_plus_pct"].formatted} of the active queue'))
    parts.append(tile("Aged 365+ days", c["active_aged_365_plus"].formatted,
                      f'{c["active_aged_365_plus_pct"].formatted} of the active queue'))
    parts.append(tile("Median active age", f'{c["active_median_age_days"].formatted} days',
                      f'P90 {c["active_p90_age_days"].formatted} days'))
    parts.append(tile("Duplicate rate, active", c["duplicate_rate_active_pct"].formatted,
                      f'{c["duplicate_children_active"].formatted} child records'))
    parts.append(tile("Demand, Jan–Jul", f'+{c["demand_yoy_change_pct"].formatted}',
                      f'{c["demand_ytd_current"].formatted} vs '
                      f'{c["demand_ytd_prior"].formatted} in 2025'))
    parts.append('</div>')

    two_series = charts.legend([("Under 90 days", "var(--series-1)"),
                                ("90+ days", "var(--series-2)")])

    parts.append(section(
        "01", "How large is the active inventory, and how old is it?",
        "The starting position: volume and age of everything in an active status at "
        "the snapshot, across all vintages."))

    # ---- Q1 aging profile --------------------------------------------------
    buckets = agg("agg_backlog_aging_buckets").sort_values("bucket_order")
    colors = ["var(--series-1)" if b in ("0-7", "8-30", "31-60", "61-90")
              else "var(--series-2)" for b in buckets["age_bucket"]]
    parts.append(panel(
        "Age profile of the active inventory",
        "Q1 · How large is the active inventory, and how old is it?",
        f'As of the snapshot, <strong>{c["active_aged_90_plus_pct"].formatted}</strong> of '
        f'active requests are past 90 days and '
        f'<strong>{c["active_aged_365_plus_pct"].formatted}</strong> past a year. The single '
        f'largest age bucket is the oldest one. Separately, '
        f'<strong>{c["cohort_pct_resolved"].formatted}</strong> of requests submitted '
        f'Jan–Jun 2026 had reached Closed or Referred status by the snapshot. These are '
        f'different populations and should not be interpreted as the same lifecycle measure.',
        two_series + '<div class="chart-scroll">'
        + charts.vertical_bars(list(buckets["age_bucket"]),
                               [float(v) for v in buckets["n_records"]], colors)
        + '</div>',
        emphasis=True,
    ))

    parts.append(section(
        "02", "Where is it concentrated?",
        "Which service categories hold the workload, which hold the oldest records, and "
        "which have a long tail rather than a uniformly slow queue."))

    # ---- Q2/Q3 service backlog ---------------------------------------------
    service = agg("agg_service_backlog").nlargest(12, "active_records")
    under90 = [float(r.active_records - r.aged_90_plus) for r in service.itertuples()]
    aged90 = [float(r.aged_90_plus) for r in service.itertuples()]
    parts.append(panel(
        "Where the active workload sits",
        "Q2 · Which service categories account for the largest share of active workload?",
        f'The top four categories — {charts.esc(c["top4_category_names"].formatted)} — hold '
        f'<strong>{c["top4_share_pct"].formatted}</strong> of all active records, and in each '
        f'the aged segment dominates. TSW is the modal case_record_type for all four; '
        f'case_record_type is a higher-level staff-group label, not a current ownership field.',
        two_series + '<div class="chart-scroll">'
        + charts.horizontal_bars(list(service["service_name"]), under90, aged90,
                                 primary_label="Under 90 days",
                                 secondary_label="Aged 90+ days")
        + '</div>',
        emphasis=True,
    ))

    # ---- Q3/Q4 aging by category ------------------------------------------
    tail = agg("agg_service_tail_risk").nlargest(12, "p90_age_days")
    parts.append(panel(
        "Typical age against tail age, by category",
        "Q3 & Q4 · Which categories hold the oldest requests, and which have an unusually long tail?",
        'Each row spans that category\'s median (blue) to its P90 (orange). A long span means '
        'most requests move while a minority sit for years — a different problem from a queue '
        'that is uniformly slow. Categories with at least 250 active records only.',
        charts.legend([("Median age", "var(--series-1)"), ("P90 age", "var(--series-2)")])
        + '<div class="chart-scroll">'
        + charts.dumbbell(list(tail["service_name"]),
                          [float(v) for v in tail["median_age_days"]],
                          [float(v) for v in tail["p90_age_days"]])
        + '</div>',
    ))

    parts.append(section(
        "03", "What materially affects how these numbers should be read?",
        "Four factors that change the interpretation before any conclusion is drawn: "
        "geography, duplicate reporting, referrals out of the queue, and demand coverage."))

    # ---- Q5/Q6 geography ----------------------------------------------------
    district = agg("agg_geography_district")
    district = district[district["council_district"] != "(Unknown)"].copy()
    district["cd_num"] = district["council_district"].astype(int)
    district = district.sort_values("active_records", ascending=False)
    d_under = [float(r.active_records - r.aged_90_plus) for r in district.itertuples()]
    d_aged = [float(r.aged_90_plus) for r in district.itertuples()]

    index_df = agg("agg_geography_aging_index")
    index_df = index_df[(index_df["area_type"] == "Council district")
                        & (index_df["area"] != "(Unknown)")]
    index_df = index_df.sort_values("aged_concentration_index", ascending=False)

    parts.append(panel(
        "Geography: volume against aged concentration",
        "Q5 & Q6 · Which districts carry the most work, and is any district's queue unusually old?",
        f'District 3 holds the largest active inventory at '
        f'<strong>{c["d3_active"].formatted}</strong> records ({c["d3_pct"].formatted}). The '
        f'index on the right divides each district\'s share of the citywide 90+ day inventory '
        f'by its share of all active records. It varies only from '
        f'<strong>{c["aging_index_min"].formatted}</strong> to '
        f'<strong>{c["aging_index_max"].formatted}</strong> — no strong district-level '
        f'over-concentration is evident under this metric. That does not prove geography is '
        f'irrelevant: district counts carry no population or asset denominator, and an effect '
        f'could exist in reporting propensity or at a finer level than a district.',
        two_series + '<div class="grid2">'
        + '<div class="chart-scroll">'
        + charts.horizontal_bars(["District " + str(d) for d in district["council_district"]],
                                 d_under, d_aged, primary_label="Under 90 days",
                                 secondary_label="Aged 90+ days", width=560, label_width=96)
        + '</div><div class="chart-scroll">'
        + charts.index_lollipop(["District " + str(a) for a in index_df["area"]],
                                [float(v) for v in index_df["aged_concentration_index"]])
        + '</div></div>',
    ))

    # ---- Q7/Q8 duplicates ---------------------------------------------------
    # Sorted by active volume, not by rate: bar length encodes workload, so a
    # 332-record category with a high rate must not head the chart.
    dup = agg("agg_duplicate_by_service").nlargest(10, "active_records")
    dup_unique = [float(r.active_distinct_issues) for r in dup.itertuples()]
    dup_children = [float(r.active_records - r.active_distinct_issues) for r in dup.itertuples()]
    parts.append(panel(
        "Repeat reporting",
        "Q7 & Q8 · How much of the queue is duplicate reports, and does removing them change the answer?",
        f'<strong>{c["duplicate_rate_active_pct"].formatted}</strong> of active case records are '
        f'duplicate children ({c["duplicate_children_active"].formatted} records). Street Light '
        f'Maintenance contributes the most of them — '
        f'<strong>{c["streetlight_dup_children"].formatted}</strong> child records, '
        f'{c["streetlight_dup_rate"].formatted} of its own active queue. The highest rate belongs '
        f'to Pothole at {c["pothole_dup_rate"].formatted}, but on only '
        f'{c["pothole_active"].formatted} active records. Collapsing duplicates onto their parent '
        f'moves <strong>{c["dup_ranks_moved"].formatted}</strong> of the top 20 categories, never '
        f'by more than {c["dup_max_rank_shift"].formatted} positions. This tests volume rankings '
        f'only; the composite priority score was not re-derived on deduplicated inputs.',
        charts.legend([("Distinct issues", "var(--series-1)"),
                       ("Duplicate child records", "var(--series-2)")])
        + '<div class="chart-scroll">'
        + charts.horizontal_bars(list(dup["service_name"]), dup_unique, dup_children,
                                 primary_label="Distinct issues",
                                 secondary_label="Duplicate children")
        + '</div>',
    ))

    # ---- Q9 referrals -------------------------------------------------------
    ref = agg("agg_referral_destinations").nlargest(10, "referred_records")
    ref_ext = [float(r.referred_records) if r.referral_scope == "External (non-City entity)"
               else 0.0 for r in ref.itertuples()]
    ref_int = [float(r.referred_records) if r.referral_scope != "External (non-City entity)"
               else 0.0 for r in ref.itertuples()]
    parts.append(panel(
        "Where referred requests go",
        "Q9 · What share of requests are referred, and where are referrals concentrated?",
        f'<strong>{c["referred_rate_resolved_pct"].formatted}</strong> of terminal-status records '
        f'were referred rather than closed, and <strong>{c["referred_external_pct"].formatted}</strong> '
        f'of those left the City entirely. Caltrans alone takes '
        f'<strong>{c["caltrans_pct"].formatted}</strong> of all referrals '
        f'({c["caltrans_records"].formatted} records). A referral is a hand-off, not an outcome.',
        charts.legend([("Routed within the City", "var(--series-1)"),
                       ("Routed outside the City", "var(--series-2)")])
        + '<div class="chart-scroll">'
        + charts.horizontal_bars(list(ref["referred_to"]), ref_int, ref_ext,
                                 primary_label="Internal", secondary_label="External",
                                 label_width=250)
        + '</div>',
    ))

    # ---- Q11 demand trend ---------------------------------------------------
    # Complete months only. A partial month plotted at its partial value draws a
    # cliff that looks like a collapse in demand, which is the exact misreading
    # the coverage logic exists to prevent.
    monthly = agg("agg_demand_monthly")
    monthly = monthly[(monthly["month_start"] >= "2025-01-01")
                      & (monthly["coverage_status"] == "complete")].copy()
    labels = [str(m)[:7] for m in monthly["month_start"]]
    complete = [True] * len(monthly)
    parts.append(panel(
        "Demand over time",
        "Q11 · How has demand changed where the source data allows a fair comparison?",
        f'Submissions for January–July rose <strong>{c["demand_yoy_change_pct"].formatted}</strong> '
        f'year over year ({c["demand_ytd_prior"].formatted} to '
        f'{c["demand_ytd_current"].formatted}). Only months from January 2025 are shown: earlier '
        f'months are not fully covered by the three extracts in scope, and plotting them would '
        f'show a decline that is an artifact of coverage. Category-level year-over-year is not '
        f'comparable across the 2025/26 boundary — see the taxonomy check in the audit.',
        '<div class="chart-scroll">'
        + charts.line_chart(labels, [float(v) for v in monthly["submissions"]], complete)
        + '</div>',
    ))

    parts.append(section(
        "04", "What should a stakeholder investigate first?",
        "A triage order with the reason for each entry, plus how sensitive that order is "
        "to the weights an analyst chose."))

    # ---- Q12 priority table -------------------------------------------------
    prio = agg("agg_priority_table").nsmallest(10, "investigation_rank")
    rows = []
    for r in prio.itertuples():
        rows.append(
            "<tr>"
            f'<td class="num">{r.investigation_rank}</td>'
            f"<td>{charts.esc(r.service_name)}</td>"
            f'<td class="num">{r.active_records:,}</td>'
            f'<td class="num">{r.median_age_days:,.9g}</td>'
            f'<td class="num">{r.aged_90_plus:,}</td>'
            f'<td class="num">{r.pct_of_own_queue_aged_90:.1f}%</td>'
            f'<td class="num">{r.pct_of_city_aged_90_backlog:.1f}%</td>'
            f'<td class="num">{r.priority_score:.1f}</td>'
            f'<td><span class="tag">{charts.esc(r.why_flagged)}</span></td>'
            "</tr>"
        )
    table = (
        '<div class="table-scroll"><table><thead><tr>'
        '<th class="num">#</th><th>Service category</th><th class="num">Active</th>'
        '<th class="num">Median age</th><th class="num">Aged 90+</th>'
        '<th class="num">% of own queue aged 90+</th>'
        '<th class="num">% of citywide 90+ inventory</th>'
        '<th class="num">Score</th><th>Why flagged</th>'
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>"
    )
    parts.append(panel(
        "Investigation priority",
        "Q12 · Which operational areas should a stakeholder look at first?",
        'A triage order, not a performance ranking. The score is a prioritization heuristic: '
        'percentile ranks of share of the citywide 90+ day inventory (0.45), share of the '
        'category\'s own active queue aged 90+ (0.35) and median active age (0.20), across '
        'categories with 500+ active records. This dataset contains no staffing, budget or '
        'work-completion data, so nothing here indicates that any area is under-resourced or '
        'under-performing.',
        table,
        emphasis=True,
    ))

    # ---- weight sensitivity -------------------------------------------------
    sens = agg("agg_priority_weight_sensitivity")
    top3 = sens[sens["rank_in_scheme"] <= 3].copy()
    # Baseline first; the alternatives are what it is being compared against.
    top3["_order"] = (~top3["scheme"].str.startswith("baseline")).astype(int)
    top3 = top3.sort_values(["_order", "scheme", "rank_in_scheme"])
    rows = []
    for scheme, group in top3.groupby("scheme", sort=False):
        ordered = group.sort_values("rank_in_scheme")
        names = " → ".join(ordered["service_name"])
        is_baseline = scheme.startswith("baseline")
        rows.append(
            "<tr>"
            f'<td>{charts.esc(scheme)}{" <span class=\"tag\">baseline</span>" if is_baseline else ""}</td>'
            f"<td>{charts.esc(names)}</td>"
            "</tr>")
    sens_table = (
        '<div class="table-scroll"><table><thead><tr>'
        '<th>Weighting scheme (volume / aged rate / median age)</th>'
        '<th>Top three, in order</th>'
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>")

    parts.append(panel(
        "How sensitive is that order to the weights?",
        "Q12b · Would a different analyst, weighting differently, reach the same shortlist?",
        f'Tested rather than assumed. Sidewalk Repair Issue and Pavement Maintenance hold the '
        f'top two positions under all <strong>{c["weight_schemes_tested"].formatted}</strong> '
        f'schemes, though their order swaps. Street Light Maintenance is top-three in '
        f'<strong>{c["streetlight_top3_scheme_count"].formatted}</strong> of '
        f'{c["weight_schemes_tested"].formatted} — under aged-rate-heavy weighting it falls to '
        f'fifth and Development Services – Code Enforcement enters at third. The third position '
        f'is a stakeholder judgment about whether volume of aged work or proportion of a queue '
        f'matters more, not an analytical result.',
        sens_table,
    ))

    parts.append(
        '<footer>'
        'Source: City of San Diego Open Data Portal — '
        'Reports of non-emergency problems submitted by users of Get It Done '
        '(data.sandiego.gov/datasets/get-it-done-reports). '
        'Generated by <code>src/build_dashboard.py</code> from the aggregates in '
        '<code>data/aggregates/</code>. Method: <code>07_methodology/methodology.md</code>. '
        'Data quality: <code>02_data_audit/data_quality_report.md</code>.'
        '</footer>'
    )
    parts.append("</div>")

    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<title>San Diego Service Operations Intelligence</title>"
        f"<style>{STYLE}</style></head><body>{''.join(parts)}</body></html>"
    )


def main() -> int:
    config.DASHBOARD_DIR.mkdir(parents=True, exist_ok=True)
    out = config.DASHBOARD_DIR / "dashboard.html"
    out.write_text(build_html())
    print(f"  [out] {out.relative_to(config.REPO_ROOT)} "
          f"({out.stat().st_size / 1024:,.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
