# Executive Memo

**To:** Service Operations Leadership, City of San Diego
**From:** Alan Ibarra, Data Analyst
**Date:** 2026-08-09 (data snapshot 2026-08-09)
**Re:** Where the Get It Done active request backlog is concentrated, and what to look at first

---

### Executive question

Where is our open service-request workload concentrated, how old is it, and which two or
three areas should we examine first?

### What we found

**Intake is working. A specific part of the queue is not clearing.**

Of the **209,411** requests submitted January–June 2026, **91.2%** have already reached a
terminal state, typically within **2** days. That is not the problem.

The problem is what has accumulated behind it. **81,359** requests are currently active —
**60,288** distinct issues once duplicate reports are collapsed. Their median age is **381**
days. **61,922** of them — **76.1%** — are past 90 days, and
**41,494** (**51.0%**) are past a year. The largest single age bucket is the oldest
one.

That backlog is highly concentrated. Four categories — Sidewalk Repair Issue, Street Light
Maintenance, ROW Maintenance and Pavement Maintenance — hold **54.2%** of it, and all four
sit under one owning group, which carries **64.0%** of all active work.

Three further results are worth leadership's attention because they close off options that
would otherwise look attractive:

- **Ageing is not geographic.** Every council district holds almost exactly the share of
  aged work its queue size implies (concentration index 0.826–1.085). A district-targeted
  intervention would be aimed at the wrong axis.
- **Duplicates inflate the count but not the priorities.** **27.0%** of active records
  (**21,971**) are duplicate reports of an already-open issue, yet collapsing them shifts no
  category by more than two rank positions.
- **Submission channel is not a lever.** Once service category is held constant, the median
  difference between mobile and web is **2** days across 29 categories.
- **Demand is rising into that backlog.** January–July submissions grew **9.3%** year over
  year, from **225,628** to **246,572**. Intake is absorbing it, but the aged categories
  have no mechanism to shed volume.

### What matters

The backlog is not evidence of slow work. It is most likely evidence that **Get It Done
case records stay open across multi-year capital maintenance cycles** — a sidewalk report
remains an open case until the segment is scheduled and treated, which can be years.

If that is what is happening, the operational cost is not repair capacity. It is that
**41,494 case records have been open for more than a year with no expectation set**, and that
leadership's own backlog number cannot distinguish "waiting on a crew next week" from
"queued behind a capital programme". Both look identical in this data.

Confirming or ruling that out requires the City's maintenance work-order system, which is
not part of this dataset. That is why all three recommendations below are framed as
investigations, not corrective actions.

### Recommendations

**1. Reconcile the sidewalk and pavement queues against the capital maintenance schedule.**
Sidewalk Repair Issue (14,614 active, median **1,090** days) and Pavement Maintenance
(5,590 active, median **1,295.5** days) together hold **31.0%** of the city's 90+ day
backlog. Determine what share of these cases is already committed to a scheduled programme.
If most are, the fix is a status taxonomy that distinguishes "scheduled" from "unassigned",
not additional crew capacity. *Evidence:*
[`agg_priority_table`](../data/aggregates/agg_priority_table.csv),
[`agg_service_backlog`](../data/aggregates/agg_service_backlog.csv).

**2. Review duplicate handling in Street Light Maintenance.**
**45.3%** of that category's 13,665 active records are duplicate children — **6,189**
repeat reports of issues already logged. This is the largest single concentration of
repeat reporting in the system and points at residents receiving no visible status after
reporting. Review whether the intake flow surfaces existing open cases at the point of
submission. *Evidence:*
[`agg_duplicate_by_service`](../data/aggregates/agg_duplicate_by_service.csv).

**3. Examine the Caltrans referral path.**
**21.1%** of all referrals — 9,123 case records — are routed to Caltrans for state highway
right-of-way. This is intake handling work the City performs on reports it cannot action.
Assess whether the reporting interface can identify state right-of-way at submission and
redirect the resident before a City case is opened. *Evidence:*
[`agg_referral_destinations`](../data/aggregates/agg_referral_destinations.csv).

### Risks and limitations

- **This data records requests, not work.** The City states that Get It Done "should not be
  considered an official record of City maintenance work" and contains no work-completion
  detail. A closed case means a case was closed, not that a repair happened. Nothing here
  measures crew performance.
- **No causal claim is made or available.** Every relationship reported is an association
  in observational data with no controls.
- **Districts are not comparable as service levels.** There are no population, street-mileage
  or asset denominators in this source.
- **Two data-quality conditions were material and are worked around explicitly.** The
  published `case_age_days` field carries two different meanings depending on case status,
  so all ages here are computed from dates instead. A service-category relabelling in autumn
  2025 makes category-level year-over-year comparison invalid, so demand trends are reported
  citywide and by owning department. Both are documented in
  [`02_data_audit/data_quality_report.md`](../02_data_audit/data_quality_report.md).
- **Duplicate counts are a floor.** They are the City's own duplicate determinations; no
  additional matching was attempted.

### Next measurement step

**Join a sample of the sidewalk and pavement backlog to the maintenance work-order system.**
A few thousand cases is enough. That single join answers the question this dataset cannot:
whether an old open case means work is outstanding, or only that the case record was never
updated. Until it is answered, the backlog figure above should be read as a measure of
**open case records**, not of outstanding physical work.

Second priority: adopt a fixed-window ageing measure (share of each month's submissions
still open at 30/60/90 days) so that backlog health can be tracked over time without the
closure-cohort bias that makes headline closure speed look better than it is.

---

*Full analysis: [`04_analysis/findings.md`](../04_analysis/findings.md) ·
Metric definitions: [`01_business_brief/metric_definitions.md`](../01_business_brief/metric_definitions.md) ·
Data quality: [`02_data_audit/data_quality_report.md`](../02_data_audit/data_quality_report.md) ·
Source: [City of San Diego Open Data Portal](https://data.sandiego.gov/datasets/get-it-done-reports/)*
