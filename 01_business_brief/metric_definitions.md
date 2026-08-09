# Metric Definitions

Every metric used anywhere in this project is defined here once. Each definition states
its grain, its exact SQL, where it is implemented, and — where it matters — why the
obvious alternative was rejected.

**Data snapshot:** 2026-08-09 (derived from the data; see [Snapshot date](#snapshot-date))

---

## Grain

| Level | Key | Row count in scope |
|---|---|---|
| Case record | `service_request_id` | 714,925 |
| Reported issue | `issue_key` = `COALESCE(parent_request_id, service_request_id)` | 622,135 |

**The fact table is one row per case record.** A resident submitting a second report about
a streetlight that is already logged creates a second case record, which the City may then
link to the first as a duplicate child. Both grains are legitimate; they answer different
questions, and the project reports both wherever the difference is material.

- Use **case records** when the question is *how many things are in the queue* — a
  duplicate still occupies a slot and still represents a resident waiting for an answer.
- Use **reported issues** when the question is *how many distinct problems exist* — for
  sizing physical work.

Implemented in [`03_sql/01_clean_base.sql`](../03_sql/01_clean_base.sql).

---

## Snapshot date

**Definition.** The date the source extracts were generated: **2026-08-09**.

**Not hard-coded.** It is recovered from the data as the modal value of
`date_requested + case_age_days` across active records, which agrees for 99.63% of them.
The pipeline therefore re-dates itself when a newer extract is downloaded.

```sql
-- 03_sql/00_sources.sql
CAST(CAST(date_requested AS DATE) + INTERVAL (case_age_days) DAY AS DATE) AS implied_date
-- modal value across active records = snapshot date
```

---

## Volume metrics

### Raw submissions
Count of case records, no filter. `COUNT(*)` over `fct_requests`. **714,925.**

### Unique service requests (reported issues)
`COUNT(DISTINCT issue_key)`. **622,135** — 12.98% lower than raw submissions.

### Demand volume
Case records grouped by `requested_month_start`. Only submission months from
**January 2025 onward** are complete under this scope, because a request submitted on or
after 2025-01-01 must be either still open, closed in 2025, or closed in 2026 — all three
of which are in scope. Earlier months are labelled `incomplete` in
[`agg_demand_monthly`](../data/aggregates/agg_demand_monthly.csv) and must not be read as
a demand decline.

---

## Status metrics

### Active / open backlog
```sql
status IN ('New', 'In Process')
```
**81,359 case records; 60,288 distinct issues.**

`Referred` is deliberately **not** active: the case has left the Get It Done queue. It is
also not counted as a service outcome — it is reported separately from `Closed` everywhere,
because a referral records a hand-off, not a result.

### Resolved
```sql
status IN ('Closed', 'Referred')
```
Note the word: *resolved* refers to the case record reaching a terminal state. It carries
no claim that a physical problem was corrected.

---

## Age metrics

Both age metrics are **computed from dates in this project**, not taken from the published
`case_age_days` field. Audit check
[DQ-03](../02_data_audit/data_quality_report.md#dq-03-semantics-of-the-published-case_age_days)
established that the published field carries two different meanings depending on status,
only one of which the official dictionary documents.

### Active request age
```sql
CASE WHEN status IN ('New','In Process')
     THEN DATEDIFF('day', CAST(date_requested AS DATE), snapshot_date) END
```
Days a request has been in an open state as of the snapshot. **Not** a measure of how long
work took — no work-completion data exists in this source.

### Lifecycle age (closed and referred records)
```sql
CASE WHEN status IN ('Closed','Referred')
      AND date_closed IS NOT NULL
      AND date_closed >= CAST(date_requested AS DATE)
     THEN DATEDIFF('day', CAST(date_requested AS DATE), date_closed) END
```
Days between submission and the recorded terminal state. Left `NULL` for the 5 records
where `date_closed < date_requested`, so they drop out of percentiles rather than
contributing a negative duration.

### Median active age — and why not the mean
**Median: 381 days. Mean: 649.9 days.** The mean is 70% higher because the queue has a
long right tail — 8.44% of active records exceed five years. The median describes the
typical request; the mean describes neither the typical request nor the tail. Both are
published in [`agg_backlog_age_percentiles`](../data/aggregates/agg_backlog_age_percentiles.csv)
so the skew is visible rather than asserted.

### P90 active age
`QUANTILE_CONT(active_age_days, 0.90)` = **1,680 days**. Nine in ten active requests are
younger than this. P90 is the tail metric: it answers "how bad does it get for the worst
tenth", which is the question a service commitment is written against. Reported alongside
the median because the two together describe the distribution's shape, and a category
where they diverge sharply
([`agg_service_tail_risk`](../data/aggregates/agg_service_tail_risk.csv)) has a different
operational problem from one where they do not.

### Aging buckets — **modified from the original specification**

The brief proposed `0-7, 8-30, 31-60, 61-90, 91-180, 181+`. Applied to this data, the
final bucket absorbs **66.2%** of the active backlog, so the chart would carry almost no
information.

The first five buckets are kept unchanged for comparability. `181+` is split into
`181-365`, `366-730`, `731+`. Summing the last three recovers the original `181+` exactly.

| Bucket | Records | % of active backlog |
|---|---:|---:|
| 0-7 | 4,662 | 5.7% |
| 8-30 | 6,595 | 8.1% |
| 31-60 | 4,607 | 5.7% |
| 61-90 | 3,674 | 4.5% |
| 91-180 | 8,000 | 9.8% |
| 181-365 | 12,373 | 15.2% |
| 366-730 | 15,060 | 18.5% |
| 731+ | 26,388 | 32.4% |

### Aged backlog thresholds
`aged_60_plus` and `aged_90_plus` are counts of active records at or beyond those ages.
`aged_365_plus` was added because at this snapshot **51.0%** of the active backlog is
already past a year, which makes 60 and 90 days too weak a discriminator on their own.

---

## Duplicate metrics

### Duplicate child request
A case record with a populated `service_request_parent_id`. The City sets this field when
a report is judged to describe an issue that is already reported and still open. **This is
the City's determination, recorded in the source — not a fuzzy-matching judgement made by
this analysis.** No attempt is made here to detect additional duplicates by address or
description similarity; that would be a different project with its own error rate.

### Duplicate rate
`duplicate_children / case_records`:

| Population | Rate |
|---|---:|
| All case records | 13.24% |
| Active backlog | 27.01% |
| Resolved records | 11.48% |

The active rate is more than double the resolved rate — expected, since a duplicate can
only attach to a parent that is still open, so long-lived open cases accumulate them.

---

## Referral metrics

### Referred rate
`records with status = 'Referred' / resolved records` = **6.8%**.

Always computed from **status**, never from the presence of referral text: audit check
[DQ-10](../02_data_audit/data_quality_report.md#dq-10-referral-field-consistency) found
4,204 records that carry referral text without a Referred status.

### Referral destination and scope
The raw `referred` field is free text containing staff and vendor email addresses. It is
normalised in [`03_sql/01_clean_base.sql`](../03_sql/01_clean_base.sql) to a destination
label and a scope of `External (non-City entity)` / `Internal (City department)`, and the
raw text is never written to any output. **61.8%** of referrals route outside the City.

---

## Concentration metrics

### Service-category concentration
Cumulative share of the active backlog held by the top *N* categories, ranked by volume.
Reported at N = 1, 3, 5, 10, 15, 20 rather than at a single hand-picked cut-off.

### Geographic concentration and the aged-concentration index

Raw counts by district answer "where is there most work", which is largely a question
about district size. The index answers "where is work *unusually* old":

```
aged_concentration_index = (area's share of the city's 90+ day active backlog)
                         / (area's share of all active backlog)
```

- **1.0** — the area holds exactly the aged share its queue size implies.
- **> 1.0** — its queue skews older than the city average.

Unit-free, so districts of different sizes compare directly.

### Backlog per recent submission
`active_records / submissions in the last 12 months`. Separates "large district" from
"district whose queue is not clearing".

---

## Investigation priority score

A **triage order**, not a performance ranking. Applied to service categories with at least
500 active records. Each component is converted to a percentile rank across categories so
that measures on different units combine without one dominating by scale:

| Weight | Component | Question it answers |
|---:|---|---|
| 0.45 | Share of the city's 90+ day active backlog | How much aged work sits here? |
| 0.35 | Share of the category's own queue aged 90+ | How stuck is this queue? |
| 0.20 | Median active age | How old is a typical request here? |

Volume carries the largest weight because leadership attention is a fixed resource and
should follow the mass of the problem. Every row carries a `why_flagged` string so the
score is never presented without its reason.

**What this score cannot do:** it contains no staffing, budget, cost or work-completion
data, so it cannot indicate that any area is under-resourced or under-performing. It
indicates only where the aged queue is.

---

## Rejected definitions

| Considered | Rejected because |
|---|---|
| Using the published `case_age_days` directly | Means two different things depending on status (DQ-03). |
| `Referred` counted as active backlog | The case has left the queue; counting it would overstate open workload by 6.8% of resolved volume. |
| `Referred` counted as a service outcome | A referral is a hand-off, not a result. Reported separately throughout. |
| Mean age as the headline | 70% above the median here; describes neither the typical case nor the tail. |
| A single `181+` bucket | Absorbs 66.2% of the backlog — no information content. |
| Trimming ages above five years as outliers | They are genuine long-lived open cases and are the subject of the analysis. Median and p90 handle the skew without discarding data. |
| Year-over-year demand at service-category grain | A confirmed relabelling between two Parking categories in autumn 2025 makes category-level comparison invalid (DQ-08). Reported citywide and at record-type grain instead. |
| Fuzzy-matching to find additional duplicates | Would introduce an unmeasured error rate into a headline metric. The City's own parent/child flag is used instead. |
