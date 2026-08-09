# Hypothetical Executive Memo — Independent Portfolio Case Study

> **Simulated stakeholder deliverable.** Independent portfolio case study using public City
> of San Diego data. Not commissioned by, affiliated with, or endorsed by the City of San
> Diego. The audience below is hypothetical.

**To:** Hypothetical Service Operations Leadership
**From:** Alan Ibarra — Data Analyst Portfolio Case Study
**Date:** Data snapshot 2026-08-09
**Re:** Where the Get It Done active request inventory is concentrated, and what to examine first

---

### Decision context

We hold a large inventory of open non-emergency service requests. This memo answers one
question: **given limited analyst and management attention, where should we look first?**

It is a targeting exercise, not a diagnosis. The source data records service requests and
case statuses only — it contains no work-order, staffing, cost or completion information —
so it can show where aged records are concentrated but cannot show why.

### What the data shows

**1. The active inventory is large and old.** As of the snapshot, **81,359** requests are in
an active status (**60,288** distinct issues once duplicate child records are collapsed).
Median active age is **381** days; **61,922** records (**76.1%**) exceed 90 days and
**41,494** (**51.0%**) exceed a year.

**2. Recent submissions settle quickly.** Of the **209,411** requests submitted January–June
2026, **91.2%** had reached a terminal Get It Done status by the snapshot. Among records that
reached a terminal status, median recorded lifecycle was **2** days. Recent intake and the
standing inventory are two different populations.

**3. Four categories hold most of the aged work.** Sidewalk Repair Issue, Street Light
Maintenance, ROW Maintenance and Pavement Maintenance together account for **54.2%** of
active records. Sidewalk and Pavement alone hold **30.9%** of the citywide 90+ day active
inventory.

**4. Repeat reporting is concentrated.** **27.0%** of active records (**21,971**) are
duplicate child records of an already-open request. Street Light Maintenance carries
**6,189** of them — **45.3%** of its own active queue.

**5. Two patterns we might have expected are not visible in this data.** Council-district
variation in aged concentration is modest (index **0.826**–**1.085**), and after stratifying
by service category the median Mobile-vs-Web recorded-lifecycle difference is **2** days.
Neither rules out an effect; both suggest service category is the more informative axis to
investigate first.

### Recommended investigations

**1. Reconcile the sidewalk and pavement active queues against the capital maintenance
schedule.** These two categories hold **30.9%** of the citywide 90+ day active inventory.
Determine what share is already committed to a scheduled program. If a large share is, the
issue to address is status taxonomy and resident communication rather than field capacity —
but that has to be measured, not assumed.

**2. Review duplicate handling in Street Light Maintenance.** **6,189** active records are
repeat reports of already-open issues. Test whether the intake flow surfaces an existing open
case at the point of submission, and measure whether that changes repeat-report volume.

**3. Examine the Caltrans referral path.** **9,123** case records — **21.1%** of all
referrals — are routed to Caltrans for state right-of-way. Review whether the reporting
interface can identify state right-of-way before a City case is opened.

### Key limitations

- **A terminal status is not a verified repair.** These records represent submitted service
  requests and case statuses, not verified maintenance completion. Closed and Referred mean a
  record reached a terminal Get It Done status. The City states this data "should not be
  considered an official record of City maintenance work."
- **No causal claim is available.** No staffing, capacity, cost or work-order data exists
  here, and nothing in this analysis is a controlled comparison.
- **District counts are not service-level comparisons.** There are no population, street-mileage
  or asset denominators in this source.
- **The priority ranking is a heuristic sensitive to weighting.** Under five tested weightings
  the top two categories hold in all five, but the third position changes in one. Weights are
  a leadership judgment and should be set explicitly.
- **Two data-quality conditions were material** and are worked around explicitly: the
  published `case_age_days` field carries different meanings for active versus terminal
  records, and a service-category relabeling in autumn 2025 makes category-level
  year-over-year comparison invalid. Both are documented in
  [`02_data_audit/data_quality_report.md`](../02_data_audit/data_quality_report.md).

### Next measurement step

**Join a sample of the sidewalk and pavement active queues to the maintenance work-order
system.** A few thousand records is enough. That single join answers what this dataset cannot:
whether an old active record means work is outstanding, or that the record was never updated.
Until then, the inventory figures above should be read as counts of **open case records**,
not of outstanding physical work.

Second: adopt a fixed-window aging measure — the share of each month's submissions still
active at 30, 60 and 90 days — so inventory health can be tracked over time without the
censoring that makes closure-cohort medians look favorable.

---

*Full analysis: [`04_analysis/findings.md`](../04_analysis/findings.md) ·
Metric definitions: [`01_business_brief/metric_definitions.md`](../01_business_brief/metric_definitions.md) ·
Data quality: [`02_data_audit/data_quality_report.md`](../02_data_audit/data_quality_report.md) ·
Source: [City of San Diego Open Data Portal](https://data.sandiego.gov/datasets/get-it-done-reports/)*
