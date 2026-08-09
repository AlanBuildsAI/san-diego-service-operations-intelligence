# Business Brief

**Project:** San Diego Service Operations Intelligence
**Analyst:** Alan Ibarra
**Stakeholder:** Hypothetical City of San Diego service-operations leadership
**Data snapshot:** 2026-08-09

> **Independent portfolio case study** using public City of San Diego data. Not commissioned
> by, affiliated with, or endorsed by the City of San Diego. The stakeholder and the
> engagement are simulated for the purposes of this case study.

---

## 1. Situation

The City of San Diego receives non-emergency service requests from residents through the
Get It Done program — a mobile app, a web portal and a telephone line. Over the ten years
since launch the program has accumulated a large volume of reports across street repair,
lighting, parking, waste, code enforcement, parks and stormwater.

Leadership can see the raw feed. What they cannot see from the feed is where work is
piling up, which parts of the queue are aging, and which of those patterns are real
rather than artifacts of how the data is recorded.

## 2. The question leadership is actually asking

> *Where is our open service-request workload concentrated, how old is it, and which
> two or three areas should we look at first?*

That decomposes into twelve questions, answered in
[`04_analysis/findings.md`](../04_analysis/findings.md):

| # | Question | Where answered |
|---|---|---|
| 1 | How large is the active request inventory? | [`agg_executive_kpis`](../data/aggregates/agg_executive_kpis.csv) |
| 2 | Which service categories hold the largest share of active workload? | [`agg_service_backlog`](../data/aggregates/agg_service_backlog.csv) |
| 3 | Which categories have the oldest active requests? | [`agg_service_backlog`](../data/aggregates/agg_service_backlog.csv) |
| 4 | Which categories have unusually high p90 aging? | [`agg_service_tail_risk`](../data/aggregates/agg_service_tail_risk.csv) |
| 5 | Which communities and districts have the highest volume? | [`agg_geography_district`](../data/aggregates/agg_geography_district.csv) |
| 6 | Which areas have unusually high aged-record concentration? | [`agg_geography_aging_index`](../data/aggregates/agg_geography_aging_index.csv) |
| 7 | How many submissions are duplicate children? | [`agg_duplicate_summary`](../data/aggregates/agg_duplicate_summary.csv) |
| 8 | How materially do duplicates change the rankings? | [`agg_duplicate_rank_impact`](../data/aggregates/agg_duplicate_rank_impact.csv) |
| 9 | What share of requests are referred, and where to? | [`agg_referral_destinations`](../data/aggregates/agg_referral_destinations.csv) |
| 10 | Do submission channels show different patterns? | [`agg_channel_controlled_comparison`](../data/aggregates/agg_channel_controlled_comparison.csv) |
| 11 | How has demand changed over time? | [`agg_demand_yoy`](../data/aggregates/agg_demand_yoy.csv) |
| 12 | Which three areas should leadership investigate first? | [`agg_priority_table`](../data/aggregates/agg_priority_table.csv) |

## 3. Scope

**In scope.** Three official extracts from the City of San Diego Open Data Portal:
the live open-request queue, requests closed during 2026, and requests closed during 2025.
714,925 unique case records after resolving cross-file duplicates.

**Out of scope.** Closed-year files for 2016–2024. They are available and the downloader
supports them (`--all-closed`), but including them would extend history without improving
the answer to any of the twelve questions, and would break the clean coverage argument
that makes the year-over-year comparison defensible (see
[`03_sql/09_trends.sql`](../03_sql/09_trends.sql)).

## 4. The boundary on every conclusion

The City states plainly:

> This data includes every user-submitted report and should not be considered an official
> record of City maintenance work. This data does not include details about any work
> performed to fix a problem or the date and time work was completed.

This is not boilerplate — it determines what may be said. A closed case means *a case record
reached a terminal Get It Done status*. It does not mean a pothole was filled. Throughout
this project:

- **Used:** request lifecycle, case status, terminal status, reported workload, active
  request age, recorded case closure, active inventory, operational queue.
- **Not used:** repair time, resolution time, completion, productivity, performance, fixed.

Nothing in this dataset supports a causal claim. Where a relationship appears, it is
reported as an association and the confounder is named.

## 5. Deliverables

| Deliverable | Audience | Location |
|---|---|---|
| Metric definitions | Analysts | [`metric_definitions.md`](metric_definitions.md) |
| Data quality report | Analysts, data owners | [`02_data_audit/data_quality_report.md`](../02_data_audit/data_quality_report.md) |
| SQL analysis layer | Analysts | [`03_sql/`](../03_sql/) |
| Written findings | Managers | [`04_analysis/findings.md`](../04_analysis/findings.md) |
| Interactive dashboard | Managers | [`05_dashboard/`](../05_dashboard/) |
| Excel review workbook | Operations staff | [`05_dashboard/san_diego_ops_review.xlsx`](../05_dashboard/san_diego_ops_review.xlsx) |
| Executive memo | Leadership | [`06_executive_memo/executive_memo.md`](../06_executive_memo/executive_memo.md) |

## 6. What would make this analysis materially better

The single highest-value addition would be a **work-order feed** — the City's maintenance
management system records what was actually done. Joining Get It Done case records to work
orders would convert every "case age" statement in this project into a statement about
actual service delivery. Without it, this analysis describes a request queue, and says so.

Second would be **denominators**: population, street mileage, streetlight and sidewalk asset
counts by district. Request volume by district is currently uninterpretable as a service-level
comparison because a district with more streetlights will generate more streetlight reports.
