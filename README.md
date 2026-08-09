# San Diego Service Operations Intelligence

**Where is the City of San Diego's open service-request workload concentrated, how old is
it, and which areas should leadership investigate first?**

An end-to-end analytics case study on **714,925 real service requests** from the City of San
Diego's Get It Done programme — from source retrieval and data audit through SQL analysis,
reporting and a decision memo.

| | |
|---|---|
| **Stakeholder** | City of San Diego service-operations leadership *(hypothetical engagement)* |
| **Data source** | [City of San Diego Open Data Portal — Get It Done reports](https://data.sandiego.gov/datasets/get-it-done-reports/) (official, daily-refreshed) |
| **Scope** | Open request queue + closures during 2025 and 2026 · **714,925** unique case records · snapshot **2026-08-09** |
| **Stack** | Python · DuckDB · SQL · pandas · openpyxl · Streamlit · pytest · GitHub Actions |
| **Deliverables** | [Executive memo](06_executive_memo/executive_memo.md) · [Full findings](04_analysis/findings.md) · [Dashboard](05_dashboard/dashboard.html) · [Excel workbook](05_dashboard/san_diego_ops_review.xlsx) · [SQL](03_sql/) · [Data quality report](02_data_audit/data_quality_report.md) |

> **Data boundary.** Get It Done records represent submitted service requests and case
> statuses, **not verified maintenance completion**. A closed case records a case closure,
> not a completed repair. Nothing in this project measures crew performance, and no
> relationship reported is causal.

![Dashboard](05_dashboard/assets/dashboard_overview.png)

---

## Findings

Every number below is recomputed from the generated data by
[`scripts/verify_claims.py`](scripts/verify_claims.py) and fails CI if it drifts.

**1 — Intake is fast; a specific part of the queue is not clearing.**
Of requests submitted January–June 2026, **91.2%** have already reached a terminal state,
typically in **2** days. Yet **81,359** requests are currently active — **60,288** distinct
issues once duplicates collapse — with a median age of **381** days. Both are true because they describe different populations.

**2 — Three quarters of the active backlog is already past 90 days.**
**61,922** active requests (**76.1%**) exceed 90 days and **51.0%** exceed a year; the P90 is
**1,680** days. The largest single age bucket is the oldest one.

**3 — Four categories hold over half the backlog, all under one owning group.**
Sidewalk Repair Issue (**14,614** active, median **1,090** days), Street Light Maintenance,
ROW Maintenance and Pavement Maintenance (median **1,295.5** days) together hold **54.2%**
of the active queue. All four sit under the TSW record type, which carries **64.0%** of all
active work.

**4 — Ageing is not geographic. This is a negative finding, reported as one.**
Every council district holds close to the share of aged work its queue size implies — the
aged-concentration index spans only **0.826** to **1.085**. A district-targeted intervention
would be aimed at the wrong axis. District 3 has the largest backlog (**18,414**, **22.6%**)
simply because it is the largest district by demand.

**5 — Duplicates inflate volume but do not change priorities.**
**21,971** active records (**27.0%**) are duplicate reports of an already-open issue.
Collapsing them shifts **11** of the top 20 categories by at most two rank positions. Street
Light Maintenance is the worst affected: **45.3%** of its queue — **6,189** records — is
repeat reporting.

**6 — Two reported metrics are traps, and both are handled.**
The headline "median closure time of **3** days" is a closure-cohort artefact: **88.1%** of
this year's closures were also submitted this year, so slow cases are absent by
construction. And submission channel looks influential until service category is held
constant, after which the median mobile-vs-web difference is **2** days.

**Supporting context:** **6.8%** of resolved records were referred rather than closed, with
**61.8%** routed outside the City. Citywide demand for January–July rose **9.3%** year over
year (**225,628** → **246,572**), though category-level trends are invalid across the
2025/2026 boundary because of a service relabelling.

## Recommendations

1. **Reconcile the sidewalk and pavement queues against the capital maintenance schedule.**
   They hold 31.0% of the city's 90+ day backlog. If most are already committed to a
   scheduled programme, the answer is a status taxonomy that separates "scheduled" from
   "unassigned" — not more crew capacity.
2. **Review duplicate handling in Street Light Maintenance.** 6,189 repeat reports suggests
   residents get no visible status after reporting. Check whether intake surfaces existing
   open cases at submission.
3. **Examine the Caltrans referral path.** 9,123 case records (21.1% of all referrals) are
   routed to the State. That is intake work the City performs on reports it cannot action.

All three are framed as investigations because this dataset cannot establish cause — see
[the memo](06_executive_memo/executive_memo.md) for the reasoning.

## Limitations

This analysis **cannot** tell you whether anything was repaired, how long work takes,
anything about staff performance, why any pattern exists, true problem incidence (only
reporting rates), or whether districts are served equally (no population or asset
denominators). Two data-quality conditions were material and are worked around explicitly —
see below.

---

## What this project demonstrates

**The audit changed the analysis.** Two findings in
[`02_data_audit/data_quality_report.md`](02_data_audit/data_quality_report.md) forced design
decisions:

- **`case_age_days` means two different things.** The official dictionary defines it as days
  between submission and closure. That holds for resolved records (99.88% agreement) — but
  active records have no closure date, and for them the field matches
  *snapshot date − request date* instead (99.63%). An analyst trusting the dictionary would
  mix two quantities in one column. The project computes its own age metrics from the dates,
  and recovers the snapshot date from the field's behaviour so the pipeline re-dates itself
  on each refresh.
- **The service taxonomy is unstable.** Between September and December 2025 the City moved
  volume between two Parking categories — monthly volumes cross over while the parent record
  type grew only 17.3%. Taken at face value one category "grew 3,914% year over year". A
  detector flags 9 of 35 categories as not comparable, and demand trends are reported at
  grains that absorb a relabelling.

**Numbers cannot drift.** [`src/claims.py`](src/claims.py) recomputes every figure quoted in
the README, memo and findings from the generated aggregates.
[`scripts/verify_claims.py`](scripts/verify_claims.py) asserts each appears verbatim, then
sweeps every number-like token in those documents and traces it back to a value in
`data/aggregates/`. Both run in CI.

**Privacy is enforced, not promised.** Eight source fields — resident free text, exact
addresses, coordinates, the raw referral message (it contains staff email addresses) and
internal identifiers — never reach any output. The pipeline refuses to export if one is
present, and [`tests/test_privacy.py`](tests/test_privacy.py) fails if any suppressed field
name or address/email-shaped string appears in a published artefact.

---

## Repository

| Path | Contents |
|---|---|
| [`01_business_brief/`](01_business_brief/) | [Business brief](01_business_brief/business_brief.md) · [metric definitions](01_business_brief/metric_definitions.md) — every metric, its SQL, and the definitions that were rejected |
| [`02_data_audit/`](02_data_audit/) | [Data quality report](02_data_audit/data_quality_report.md) — 13 generated checks (4 PASS · 6 WARN · 2 FAIL · 1 INFO) |
| [`03_sql/`](03_sql/) | 11 documented SQL files — the analysis itself, runnable in the DuckDB CLI |
| [`04_analysis/`](04_analysis/) | [Findings](04_analysis/findings.md) — all twelve business questions answered |
| [`05_dashboard/`](05_dashboard/) | [Static dashboard](05_dashboard/dashboard.html) · [Streamlit app](05_dashboard/app.py) · [Excel workbook](05_dashboard/san_diego_ops_review.xlsx) · [Tableau build spec](05_dashboard/tableau_build_spec.md) |
| [`06_executive_memo/`](06_executive_memo/) | [One-page memo](06_executive_memo/executive_memo.md) for leadership |
| [`07_methodology/`](07_methodology/) | [Methodology](07_methodology/methodology.md) — decisions, trade-offs and known weaknesses |
| [`08_interview_defense/`](08_interview_defense/) | [Interview guide](08_interview_defense/interview_guide.md) — 28 questions with grounded answers |
| [`src/`](src/) · [`scripts/`](scripts/) | Pipeline runner, audit harness, claim registry, output builders |
| [`tests/`](tests/) | 60+ tests over a synthetic fixture, plus privacy and link checks |
| [`docs/`](docs/) | [Source manifest](docs/source_manifest.md) — files, hashes, row counts, licensing |

### SQL layer

| File | Answers |
|---|---|
| [`00_sources.sql`](03_sql/00_sources.sql) | Typed views over the official CSVs; derives the snapshot date from the data |
| [`01_clean_base.sql`](03_sql/01_clean_base.sql) | Union → deduplicate → derive metrics → suppress sensitive fields |
| [`02_executive_kpis.sql`](03_sql/02_executive_kpis.sql) | Headline metrics, long format |
| [`03_backlog_aging.sql`](03_sql/03_backlog_aging.sql) | Q1 — queue size and age profile |
| [`04_service_analysis.sql`](03_sql/04_service_analysis.sql) | Q2–Q4 — workload, oldest queues, tail risk |
| [`05_geography_analysis.sql`](03_sql/05_geography_analysis.sql) | Q5–Q6 — volume and the aged-concentration index |
| [`06_duplicates.sql`](03_sql/06_duplicates.sql) | Q7–Q8 — repeat reporting and its effect on rankings |
| [`07_referrals.sql`](03_sql/07_referrals.sql) | Q9 — referral volume, destinations and consistency |
| [`08_channel_analysis.sql`](03_sql/08_channel_analysis.sql) | Q10 — channel comparison, controlled for service category |
| [`09_trends.sql`](03_sql/09_trends.sql) | Q11 — demand over time, coverage argument, taxonomy detector |
| [`10_priority_table.sql`](03_sql/10_priority_table.sql) | Q12 — investigation priority and hotspots |

---

## Reproducing

Requires Python 3.11+. The full run downloads ~245 MB from the City's portal and takes
about three minutes.

```bash
make install     # create .venv and install pinned dependencies
make download    # retrieve the official extracts into data/raw/ (git-ignored)
make audit       # build base tables and run 13 data-quality checks
make analyze     # execute the SQL layer -> data/aggregates/
make dashboard   # build dashboard.html, the Excel workbook and screenshots
make test        # run the test suite against the committed fixture
make verify      # re-check every written figure against the generated data
make all         # everything above, in order
```

The test suite needs **no** downloaded data — it runs the project's real SQL against a
committed synthetic fixture, which is what CI does on every push.

```bash
make dashboard-app     # optional: streamlit run 05_dashboard/app.py
```

---

## Notes and honest caveats

- **No Tableau workbook is included.** Tableau cannot be automated in this environment, so
  rather than fabricate a `.twb` there is a complete
  [build specification](05_dashboard/tableau_build_spec.md) — data sources, calculated
  fields, nine sheets, layout and acceptance checks.
- **The Excel workbook contains no native PivotTables.** openpyxl cannot author a PivotTable
  cache. It contains native Excel Tables with filters, charts, conditional formatting and
  live cross-check formulas instead, and says so on its first sheet.
- **Duplicate counts are a floor**, not an exact figure — they are the City's own
  determinations, and no additional matching was attempted.
- **Raw data is never committed.** `data/raw/` is git-ignored;
  [`docs/source_manifest.md`](docs/source_manifest.md) records the exact files, SHA-256
  hashes, row counts and retrieval date.

---

*Data source: City of San Diego Open Data Portal, published by the Performance & Analytics
Department. This is an independent portfolio analysis and is not affiliated with or endorsed
by the City of San Diego.*
