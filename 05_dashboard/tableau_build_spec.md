# Tableau Build Specification

**Status: MANUAL BUILD SPECIFICATION ONLY.** No `.twb`/`.twbx` file or Tableau Public URL is
included or claimed. Build and validate the workbook in Tableau Desktop or Tableau Public,
then publish it separately after completing the acceptance checks below. This specification
supports a manual build in roughly 60–90 minutes.

The equivalent analysis is already delivered two other ways:
[`dashboard.html`](dashboard.html) (self-contained, no install) and
[`app.py`](app.py) (Streamlit).

---

## 1. Data sources

Connect Tableau to the **generated aggregates**, not the raw CSVs. They are small, already
privacy-filtered, and contain no suppressed field.

| # | Connection | File | Rows | Used by sheets |
|---|---|---|---|---|
| A | Text file | `data/aggregates/agg_service_backlog.csv` | 40 | 2, 3, 9 |
| B | Text file | `data/aggregates/agg_backlog_aging_buckets.csv` | 8 | 1 |
| C | Text file | `data/aggregates/agg_geography_district.csv` | 10 | 4 |
| D | Text file | `data/aggregates/agg_geography_aging_index.csv` | 50 | 5 |
| E | Text file | `data/aggregates/agg_duplicate_by_service.csv` | 28 | 6 |
| F | Text file | `data/aggregates/agg_referral_destinations.csv` | 26 | 7 |
| G | Text file | `data/aggregates/agg_demand_monthly.csv` | 32 | 8 |
| H | Text file | `data/aggregates/agg_priority_table.csv` | 24 | 9 |
| I | Text file | `data/aggregates/agg_executive_kpis.csv` | 27 | KPI tiles |

These are **separate data sources**, not joins. Each sheet uses exactly one. Do not blend
A–H; they are pre-aggregated at different grains and blending them will produce wrong
totals.

If a record-level extract is wanted instead, use
`data/processed/fct_service_requests.parquet` (714,925 rows, 30 columns, already
privacy-filtered). That generated file is intentionally git-ignored and is not included in
this repository. Publish it as a `.hyper` extract, not a live connection.

**Refresh:** re-run `make all` to regenerate the aggregates, then refresh the extracts.

---

## 2. Calculated fields

Create these on the data source noted. Most analysis is already done in SQL — Tableau
should format and present, not recompute.

| Field | Source | Formula | Notes |
|---|---|---|---|
| `Aged 90+ (records)` | A | `[aged_90_plus]` | alias only |
| `Under 90 days` | A | `[active_records] - [aged_90_plus]` | second segment of the stacked bar |
| `Aged share label` | A | `STR(ROUND([pct_aged_90_plus],1)) + "%"` | direct label |
| `Bucket order` | B | `CASE [age_bucket] WHEN "0-7" THEN 1 WHEN "8-30" THEN 2 WHEN "31-60" THEN 3 WHEN "61-90" THEN 4 WHEN "91-180" THEN 5 WHEN "181-365" THEN 6 WHEN "366-730" THEN 7 ELSE 8 END` | **required** — alphabetical sort is wrong |
| `Bucket color` | B | `IF [Bucket order] <= 4 THEN "Under 90 days" ELSE "90+ days" END` | drives the two-color encoding |
| `District label` | C | `"District " + [council_district]` | |
| `Under 90 (district)` | C | `[active_records] - [aged_90_plus]` | |
| `Index vs baseline` | D | `[aged_concentration_index] - 1` | deviation from the city average |
| `Index above average` | D | `[aged_concentration_index] >= 1` | boolean, colors the lollipop |
| `Duplicate children` | E | `[active_records] - [active_distinct_issues]` | |
| `Is external referral` | F | `[referral_scope] = "External (non-City entity)"` | |
| `Month complete` | G | `[coverage_status] = "complete"` | |
| `Complete submissions` | G | `IF [Month complete] THEN [submissions] END` | solid line |
| `Incomplete submissions` | G | `IF NOT [Month complete] THEN [submissions] END` | dashed line — never plot as a drop |

---

## 3. Colour palette

Two colors carry meaning across every sheet. Do not add a third for decoration.

Create a custom categorical palette in `Preferences.tps`:

```xml
<workbook>
  <preferences>
    <color-palette name="SD Ops" type="regular">
      <color>#2a78d6</color>  <!-- typical / recent / within threshold -->
      <color>#eb6834</color>  <!-- tail / aged / duplicated -->
    </color-palette>
  </preferences>
</workbook>
```

Assign `#2a78d6` to "Under 90 days" / "Distinct issues" / "Routed within the City", and
`#eb6834` to "90+ days" / "Duplicate children" / "Routed outside the City" on every sheet.
This pair is validated for color-vision deficiency separation against both light and dark
backgrounds.

---

## 4. Sheets

### Sheet 1 — Age profile of the active queue *(source B)*
- **Marks:** Bar (vertical)
- **Columns:** `age_bucket`, sorted manually by `Bucket order`
- **Rows:** `SUM(n_records)`
- **Colour:** `Bucket color`
- **Label:** `SUM(n_records)`, above the bar
- **Tooltip:** bucket, records, `pct_of_active_backlog`, `cumulative_pct`
- **Title:** "Age profile of the active queue"
- **Caption:** "Q1 · How large is the active backlog, and how old is it?"

### Sheet 2 — Active workload by service category *(source A)*
- **Marks:** Bar (horizontal), stacked
- **Rows:** `service_name`, sorted descending by `SUM(active_records)`, Top 12 filter
- **Columns:** `SUM(Under 90 days)` and `SUM(Aged 90+ (records))` as measure values
- **Colour:** Measure Names, using the two-color palette
- **Label:** `SUM(active_records)` at the end of the bar
- **Title:** "Where the active workload sits"

### Sheet 3 — Median vs P90 age by category *(source A)*
- **Marks:** Circle, dual-axis with a Line to draw the connector
  1. `AVG(median_age_days)` on Columns → Circle, color `#2a78d6`
  2. `AVG(p90_age_days)` on Columns → Circle, color `#eb6834`
  3. Dual-axis, **Synchronise Axis** (mandatory — the two must share one scale)
- **Rows:** `service_name`, sorted descending by `AVG(p90_age_days)`
- **Filter:** `active_records >= 250`
- **Title:** "Typical age against tail age"
- **Note:** this is a dumbbell, not a dual-measure chart. Both marks are days on one axis.

### Sheet 4 — Backlog by council district *(source C)*
- **Marks:** Bar (horizontal), stacked
- **Rows:** `District label`, sorted descending by `SUM(active_records)`
- **Columns:** `SUM(Under 90 (district))`, `SUM(aged_90_plus)`
- **Tooltip:** must include `backlog_per_recent_submission` and `median_age_days`
- **Caption (required):** "District counts are not comparable as service levels — this
  dataset has no population or asset denominators."

### Sheet 5 — Aged-concentration index *(source D)*
- **Marks:** Circle
- **Rows:** `area`, filtered to `area_type = "Council district"`, sorted by index descending
- **Columns:** `AVG(aged_concentration_index)`
- **Colour:** `Index above average`
- **Reference line:** constant at **1.0**, dashed, labeled "City average"
- **Axis:** fixed 0.75 to 1.15 — do not let Tableau auto-scale, or a 0.826–1.085 spread
  will look dramatic
- **Title:** "Aged-concentration index by district"

### Sheet 6 — Repeat reporting *(source E)*
- **Marks:** Bar (horizontal), stacked
- **Rows:** `service_name`, sorted descending by **`SUM(active_records)`** — not by rate;
  bar length must encode workload
- **Columns:** `SUM(active_distinct_issues)`, `SUM(Duplicate children)`
- **Tooltip:** include `duplicate_rate_pct` and `records_per_issue`

### Sheet 7 — Referral destinations *(source F)*
- **Marks:** Bar (horizontal)
- **Rows:** `referred_to`, Top 10 by `SUM(referred_records)`
- **Columns:** `SUM(referred_records)`
- **Colour:** `Is external referral`
- **Title:** "Where referred requests go"

### Sheet 8 — Demand over time *(source G)*
- **Marks:** Line
- **Columns:** `month_start` (continuous, exact date)
- **Rows:** `SUM(Complete submissions)` and `SUM(Incomplete submissions)` on the same axis
- **Line style:** solid for complete, dashed at 55% opacity for incomplete
- **Filter:** `month_start >= 2025-01-01` — **mandatory.** Earlier months are not covered by
  the source scope and plotting them shows a false collapse in demand.

### Sheet 9 — Investigation priority *(source H)*
- **Marks:** Text table
- **Rows:** `investigation_rank`, `service_name`, `why_flagged`
- **Measures:** `active_records`, `median_age_days`, `aged_90_plus`,
  `pct_of_own_queue_aged_90`, `pct_of_city_aged_90_backlog`, `priority_score`
- **Colour:** highlight table on `priority_score`, white → `#eb6834`
- **Caption (required):** "A triage order, not a performance ranking. No staffing, budget or
  work-completion data exists in this source."

---

## 5. Dashboard layout

**Size:** 1280 × 2400, Fixed size, top-left aligned.

```
┌────────────────────────────────────────────────────────────────┐
│ TITLE  San Diego Service Operations Intelligence               │
│ SUBTITLE  Active backlog, aging and routing · snapshot        │
├────────────────────────────────────────────────────────────────┤
│ DATA BOUNDARY BANNER  (text object, orange left border, 60px)  │
├──────────┬──────────┬──────────┬──────────┬──────────┬─────────┤
│ Active   │ Aged 90+ │ Aged     │ Median   │ Duplicate│ Demand  │
│ backlog  │          │ 365+     │ age      │ rate     │ YoY     │
│ 81,359   │ 61,922   │ 41,494   │ 381 d    │ 27.0%    │ +9.3%   │
├──────────┴──────────┴──────────┴──────────┴──────────┴─────────┤
│ Sheet 1 — Age profile of the active queue          (full, 320) │
├────────────────────────────────────────────────────────────────┤
│ Sheet 2 — Active workload by service category      (full, 420) │
├────────────────────────────────────────────────────────────────┤
│ Sheet 3 — Median vs P90 age by category            (full, 420) │
├───────────────────────────────┬────────────────────────────────┤
│ Sheet 4 — District backlog    │ Sheet 5 — Aged index    (380)  │
├───────────────────────────────┴────────────────────────────────┤
│ Sheet 6 — Repeat reporting                         (full, 360) │
├───────────────────────────────┬────────────────────────────────┤
│ Sheet 7 — Referral destinations│ Sheet 8 — Demand trend  (340)  │
├───────────────────────────────┴────────────────────────────────┤
│ Sheet 9 — Investigation priority table             (full, 420) │
├────────────────────────────────────────────────────────────────┤
│ FOOTER  source, generation date, links to method & audit       │
└────────────────────────────────────────────────────────────────┘
```

**KPI tiles:** build each as a one-mark Text sheet against source I, filtered to a single
`metric_key`, showing `SUM(value)` with the `metric_label` as caption. Do not type the
numbers as static text — they must refresh with the data.

**Boundary banner text (verbatim, required):**

> **Data boundary.** Get It Done records represent submitted service requests and case
> statuses, not verified maintenance completion. A record reaching Closed or Referred status
> means it reached a terminal Get It Done status, not that a repair occurred. This source
> carries no work-order, staffing or capacity data, so nothing here measures crew performance
> and no relationship shown is causal.

---

## 6. Filters

Because the sheets use separate pre-aggregated sources, global filter actions will not
propagate cleanly. Keep filtering local and minimal:

| Filter | Sheets | Type |
|---|---|---|
| Top N categories | 2, 3, 6 | parameter, 5–30, default 12 |
| `area_type` | 5 | fixed to "Council district" |
| Month range | 8 | fixed ≥ 2025-01-01, **not** user-adjustable below that floor |

The fixed area type and month floor are guard rails, not conveniences. Exposing them invites
a reader to produce a figure the data does not support.

---

## 7. Acceptance checks

Before considering the workbook done, confirm each of these against
[`data/aggregates/`](../data/aggregates/):

- [ ] Sheet 1 bars sum to **81,359**
- [ ] Sheet 1 buckets are in age order, not alphabetical
- [ ] Sheet 2 top four categories sum to **54.2%** of the backlog
- [ ] Sheet 3 dual axes are **synchronised**
- [ ] Sheet 5 reference line is at 1.0 and the axis is fixed
- [ ] Sheet 6 is sorted by volume, not by duplicate rate
- [ ] Sheet 8 shows no data before January 2025
- [ ] KPI tiles are live measures, not typed text
- [ ] The boundary banner appears above the fold
- [ ] No sheet exposes `public_description`, `street_address`, `lat`, `lng` or raw
      `referred` text — none of these exist in the aggregate sources, so this should be
      automatic; confirm it anyway
