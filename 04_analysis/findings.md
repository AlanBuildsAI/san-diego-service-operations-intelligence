# Findings

**San Diego Service Operations Intelligence** · data snapshot **2026-08-09**
Source: City of San Diego Open Data Portal — Get It Done service requests.

> **Independent portfolio case study** using public City of San Diego data. Not commissioned
> by, affiliated with, or endorsed by the City of San Diego. The stakeholder is hypothetical.
>
> **Data boundary.** Get It Done records represent submitted service requests and case
> statuses, not verified maintenance completion. A record reaching Closed or Referred
> status means it reached a terminal Get It Done status — not that a physical repair
> occurred. The dataset contains no work-order, staffing, capacity or satisfaction data, so
> it cannot establish why any pattern exists. Nothing below measures crew performance, and
> no relationship reported here is causal.

Every figure traces to a table in [`data/aggregates/`](../data/aggregates/) and is
re-verified against those tables by
[`scripts/verify_claims.py`](../scripts/verify_claims.py).

---

## The headline

**A recent submission cohort has a high terminal-status share; separately, the standing
active inventory is old and concentrated in four asset-maintenance categories.**

Those two statements describe different populations — a recent submission cohort and the
active inventory of all vintages at the snapshot. They should not be interpreted as the
same lifecycle measure. Neither statement explains *why* the older inventory persists; the
dataset does not carry the information needed to establish that.

| | |
|---|---|
| Requests submitted Jan–Jun 2026 | **209,411** |
| …in a terminal status at the snapshot | **91.2%** |
| …median recorded lifecycle *among those* | **2** days (P90 **29** days) |
| …still active | 8.8% |
| Active backlog, all vintages | **81,359** case records / **60,288** distinct issues |
| Median age of that backlog | **381** days (P90 **1,680** days) |
| Backlog aged 90+ days | **61,922** (**76.1%**) |
| Backlog aged 365+ days | **41,494** (**51.0%**) |

The recent cohort's status-at-snapshot and the standing inventory's age profile answer
different questions. The active inventory is old and concentrated in a few categories.

Note the right-censoring: the 2-day median is computed only over the 91.2% of the cohort
that had already reached a terminal status by the snapshot. Records still open are excluded
from that statistic by construction, so it describes terminal-status records, not the cohort
as a whole.

---

## Q1 · How large is the active request backlog?

**81,359 active case records**, which collapse to **60,288 distinct reported issues** once
duplicate children are attributed to their parent.

The queue's age distribution is the finding, not its size:

| Age bucket (days) | Records | % of backlog | Cumulative % |
|---|---:|---:|---:|
| 0–7 | 4,662 | 5.7% | 5.7% |
| 8–30 | 6,595 | 8.1% | 13.8% |
| 31–60 | 4,607 | 5.7% | 19.5% |
| 61–90 | 3,674 | 4.5% | 24.0% |
| 91–180 | 8,000 | 9.8% | 33.8% |
| 181–365 | 12,373 | 15.2% | 49.1% |
| 366–730 | 15,060 | 18.5% | 67.6% |
| 731+ | 26,388 | 32.4% | 100.0% |

**66.2%** of the active queue is older than 180 days, and the largest single bucket is the
oldest one. A queue in steady state does not look like this; a queue with a structural tail
does.

Median is used rather than mean throughout: the mean active age is **649.9** days against a
median of **381**, inflated by a tail reaching 3,731 days.
→ [`agg_backlog_aging_buckets`](../data/aggregates/agg_backlog_aging_buckets.csv),
[`agg_backlog_age_percentiles`](../data/aggregates/agg_backlog_age_percentiles.csv)

### A trap worth naming: closure-cohort bias

The tempting lifecycle summary — median recorded lifecycle of cases closed this year — is
**3 days**. That number is real but nearly useless on its own, because **88.1%** of this
year's closures were also *submitted* this year. Slower cases are missing from a closure
cohort by construction: they have not closed yet.

Decomposed by submission year, the same closures look very different:

| Submitted | Closures in 2026 | % | Median lifecycle |
|---|---:|---:|---:|
| 2026 | 224,606 | 88.1% | 2 days |
| 2025 | 19,559 | 7.7% | **93** days |
| 2024 | 2,561 | 1.0% | 627 days |
| 2023 | 1,732 | 0.7% | 1,008 days |

The submission-cohort view in the headline table fixes the denominator at submission time,
which removes that particular distortion. It is not free of censoring — its lifecycle
median still covers only records that had reached a terminal status by the snapshot — but
its *terminal-status share* completely observes the cohort's status at the snapshot. It
should not be compared with the standing inventory as though both were the same lifecycle
measure.
→ [`agg_closure_cohort_bias`](../data/aggregates/agg_closure_cohort_bias.csv),
[`agg_submission_cohort`](../data/aggregates/agg_submission_cohort.csv)

---

## Q2 · Which service categories account for the largest share of active workload?

Four categories hold **54.2%** of the entire active backlog:

| Category | Active | % of backlog | Median age | P90 age | % aged 90+ |
|---|---:|---:|---:|---:|---:|
| Sidewalk Repair Issue | 14,614 | 18.0% | 1,090 | 2,617 | 94.7% |
| Street Light Maintenance | 13,665 | 16.8% | 467 | 1,359 | 90.2% |
| ROW Maintenance | 10,245 | 12.6% | 450 | 1,312 | 85.7% |
| Pavement Maintenance | 5,590 | 6.9% | 1,295.5 | 2,710 | 95.7% |

**TSW** is the modal `case_record_type` for each of these four categories, and records
carrying that label account for **52,063** active records — **64.0%** of the active
inventory. Treat that as a labeling concentration, not a confirmed org chart:
`case_record_type` is a higher-level staff-group label, audit check DQ-08 found it is
many-to-many with `service_name`, and this dataset does not establish which current City
department owns any queue. Concentration continues past the top four: ten categories account
for **78.8%** of the active inventory, out of 40 present.

For contrast, the fifth-largest category, Parking – 72-Hours, has 4,694 active records at a
median age of **21** days and only 14.6% aged 90+. Size of queue and age of queue are
different problems.
→ [`agg_service_backlog`](../data/aggregates/agg_service_backlog.csv),
[`agg_service_concentration`](../data/aggregates/agg_service_concentration.csv)

---

## Q3 · Which service categories have the oldest active requests?

By median active age, among categories with 250+ active records:

1. **Pavement Maintenance** — 1,295.5 days
2. **Traffic Sign Maintenance** — 1,146.5 days
3. **Sidewalk Repair Issue** — 1,090 days
4. **Stormwater** — 874 days

The first and third are also the first and fourth largest queues in the city. That overlap
is what makes them the top investigation priorities: they are simultaneously big and old.

---

## Q4 · Which categories have unusually high p90 aging?

"Unusually high" is measured two ways, because they identify different problems.

**Against peer categories** (z-score of P90 across categories with 250+ active records):

| Category | Median | P90 | P90 z-score | Flag |
|---|---:|---:|---:|---|
| Pavement Maintenance | 1,295.5 | 2,710 | 2.33 | p90 well above peers |
| Sidewalk Repair Issue | 1,090 | 2,617 | 2.21 | p90 well above peers |
| Development Services – Code Enforcement | 488 | 2,378 | 1.88 | p90 well above peers |
| Stormwater | 874 | 2,141 | 1.56 | p90 well above peers |

**Against their own median** (P90 ÷ median ≥ 5) — categories where most requests move but a
minority sit for years:

| Category | Median | P90 | Ratio |
|---|---:|---:|---:|
| Pothole | 133.5 | 1,257 | 9.42 |
| Traffic Engineering | 201 | 1,181 | 5.88 |
| Parks Issue | 203 | 1,133 | 5.58 |

These two lists barely overlap, and they describe different shapes. A category in the first
list has an active queue that is old throughout. A category in the second has a much younger
typical record — Pothole's median active age is 133.5 days — alongside a small population of
very old ones.

One hypothesis worth testing is that the long tail in the second group reflects records that
stopped progressing rather than work that is genuinely slow. This dataset cannot distinguish
those, since it carries no work-order activity. The distinction matters operationally, and
it is invisible if only medians are reported.
→ [`agg_service_tail_risk`](../data/aggregates/agg_service_tail_risk.csv)

---

## Q5 · Which communities/council districts have the highest request volume?

| District | Active backlog | % of backlog | Submissions, last 12 mo | Backlog per recent submission | Median age |
|---|---:|---:|---:|---:|---:|
| 3 | 18,414 | 22.6% | 89,956 | 0.205 | 403 |
| 2 | 12,293 | 15.1% | 63,332 | 0.194 | 399 |
| 1 | 9,649 | 11.9% | 36,484 | 0.264 | 482 |
| 9 | 9,378 | 11.5% | 69,571 | 0.135 | 331 |
| 5 | 5,664 | 7.0% | 15,481 | **0.366** | **529** |
| 4 | 5,988 | 7.4% | 40,954 | **0.146** | **194** |

By community planning area, Downtown leads with 6,435 active records, followed by
Southeastern San Diego (4,551) and Clairemont Mesa (4,492).

**Raw district counts should not be read as a service-level comparison.** This dataset
contains no population, street-mileage, streetlight or sidewalk-asset counts. A district
with more streetlights will generate more streetlight reports for reasons that have nothing
to do with how it is served. The rightmost two columns are the closest available
like-for-like: District 5 carries the most backlog per unit of recent demand (0.366) and
the oldest median (529 days) despite having the *smallest* recent inflow of any numbered
district; District 4 sits at the opposite end on both.
→ [`agg_geography_district`](../data/aggregates/agg_geography_district.csv),
[`agg_geography_community`](../data/aggregates/agg_geography_community.csv)

---

## Q6 · Which areas have unusually high aged-backlog concentration?

**Council-district variation in the descriptive aged-concentration index is modest
(0.826–1.085); no strong district-level over-concentration is evident under this metric.**

The index divides a district's share of the citywide 90+ day active inventory by its share
of all active records. A value of 1.0 means the district holds exactly the aged share its
inventory size implies.

Across the nine council districts the index spans only **0.826** to **1.085** — aged records
sit close to proportional with inventory size everywhere.

**What this does not establish.** It does not prove geography is irrelevant. The index is a
single descriptive ratio at one snapshot, computed on reported requests rather than
conditions, with no population or asset denominators available. A geographic effect could
exist in reporting propensity, in asset condition, or at a finer level than a council
district, and none of those is observable here.

What it does support is a sequencing judgment: on this metric, service category
discriminates far more strongly than district does, so category is the more informative axis
to investigate first. The category-by-district hotspot table is consistent with that — the
top cells are the largest categories in the largest districts.
→ [`agg_geography_aging_index`](../data/aggregates/agg_geography_aging_index.csv),
[`agg_priority_hotspots`](../data/aggregates/agg_priority_hotspots.csv)

---

## Q7 · How many submissions are duplicate children of existing requests?

**94,687** case records across the full scope carry a parent id — a **13.2%** duplicate
rate. Within the active backlog the rate is **27.0%** (**21,971** records).

The gap is structural rather than surprising: a duplicate can only attach to a parent that
is still open, so long-lived open cases accumulate repeat reports. The categories with the
oldest queues are also the most duplicated.

| | Case records | Distinct issues | Duplicate rate |
|---|---:|---:|---:|
| All records in scope | 714,925 | 622,135 | 13.24% |
| Active backlog | 81,359 | 60,288 | 27.01% |
| Terminal status | 633,566 | 563,056 | 11.48% |

Repeat reporting is broad rather than driven by a few hotspots: 91.4% of issues have no
duplicate at all, and clusters of 11+ reports account for 0.07% of issues and 1.09% of case
records.

Street Light Maintenance contributes the most duplicate records in absolute terms —
**6,189**, or **45.3%** of its own active queue. The highest *rate* belongs to Pothole at
**57.8%**, but on only **332** active records, so it is a small effect on a small base.

**Important limitation.** These are the City's own duplicate determinations, recorded in
`service_request_parent_id`. No attempt was made to find additional duplicates by address
or description similarity — that would introduce an unmeasured error rate into a headline
metric. The true duplicate rate is therefore *at least* this, not exactly this.
→ [`agg_duplicate_summary`](../data/aggregates/agg_duplicate_summary.csv),
[`agg_duplicate_cluster_size`](../data/aggregates/agg_duplicate_cluster_size.csv)

---

## Q8 · How materially do duplicates change rankings or volume metrics?

**Collapsing duplicate child records changes top-20 service-category volume rankings by no
more than two positions.**

That is the specific test that was run, and it is the specific claim being made. Collapsing
duplicates removes 25.9% of active case-record volume. Across the top 20 categories by
volume, **11** change rank at all, and none moves by more than **2** positions. The four
largest categories remain the four largest at either grain:

| Category | Rank (case records) | Rank (distinct issues) | Shift |
|---|---:|---:|---:|
| Sidewalk Repair Issue | 1 | 1 | 0 |
| Street Light Maintenance | 2 | 3 | −1 |
| ROW Maintenance | 3 | 2 | +1 |
| Pavement Maintenance | 4 | 4 | 0 |

So the choice of grain materially changes volume totals but barely reorders the volume
ranking. Both grains are reported throughout.

**Scope of this test.** It compares *volume rankings only*. A full sensitivity analysis
re-deriving the composite priority score on deduplicated inputs was not run, so this does
not establish that the priority table is unchanged by deduplication — only that the volume
ordering it draws on is stable.

The one place the choice genuinely matters is Street Light Maintenance, where 45.3% of the
queue is duplicates — it is the second-largest queue by case record and the third-largest
by distinct issue. If the question is "how many streetlights need attention", the case-record
count overstates it by 6,189.
→ [`agg_duplicate_rank_impact`](../data/aggregates/agg_duplicate_rank_impact.csv)

---

## Q9 · What share of requests are referred and where are referrals concentrated?

**6.8%** of terminal-status records (**43,306**) were referred rather than closed, and
**61.8%** of those were routed outside the City entirely.

| Destination | Referrals | % of referrals | Scope |
|---|---:|---:|---|
| Caltrans (State) | 9,123 | 21.1% | External |
| City – Other department | 8,282 | 19.1% | Internal |
| City – Police | 6,902 | 15.9% | Internal |
| SDG&E (utility) | 5,280 | 12.2% | External |
| AT&T (utility) | 2,303 | 5.3% | External |

Referred records have a short recorded lifecycle in the case system — median **0** days, and
66.4% within one day — because a referral records a routing decision, not work. They are
terminal for backlog arithmetic and reported separately from Closed status everywhere in
this project, since treating a hand-off as an outcome would flatter any outcome metric.

By category, referral rates are high where jurisdiction is ambiguous: "Other" at 66.4%,
Graffiti – Code Enforcement at 29.0%, Building and Land Use Enforcement at 26.4%. Roughly
one in five referrals goes to Caltrans, which points at state highway right-of-way being a
recurring source of misdirected reports.

**Caveat.** Referral destination is parsed from free text by a rule set in
[`01_clean_base.sql`](../03_sql/01_clean_base.sql); the raw text is never published because
it contains staff and vendor email addresses. The parser resolves every referred record to
a destination, but grouped labels such as "City – Other department" (19.1%) are a residual
bucket, not a single department.
→ [`agg_referral_destinations`](../data/aggregates/agg_referral_destinations.csv),
[`agg_referral_by_service`](../data/aggregates/agg_referral_by_service.csv)

---

## Q10 · Do submission channels show different volume/status/aging patterns?

**Volume: yes, substantially.** Mobile is **54.0%** of all case records, Web **23.9%**,
Phone 6.7%. A further 15.1% are staff or system-generated.

**Recorded lifecycle: no consistent difference once service category is held constant.**

The raw comparison is confounded, because channel is associated with problem type. Missed
Collection arrives 32,872 times by web and 17,946 by phone against only 403 by mobile;
Parking Violation arrives 60,033 times by mobile. Comparing channel medians without
controlling compares waste collection against parking enforcement.

Among terminal-status records, after stratifying by service category across **29** categories with
enough volume in both channels, the median absolute Mobile-vs-Web recorded-lifecycle
difference is **2** days, and **26** of 29 categories differ by 20 days or less.

Two exceptions are worth a look rather than a conclusion:

- **Development Services – Code Enforcement**: mobile 682 days vs web 163.5 days (n = 1,945 / 522)
- **Pavement Maintenance**: mobile 199 days vs web 360 days (n = 1,242 / 414)

They point in opposite directions, which is not the pattern a general channel-associated
difference would produce, and is more consistent with something specific to how those two
categories are intaken. Neither is established by this data.

**Conclusion: the data does not show a broad, consistent channel-associated lifecycle
difference after stratifying by service category.**

That is a statement about what was measured, not about causation. Residents choose their own
channel, so channel is associated with reporter characteristics and problem types that are
not observable in this dataset. Nothing here separates channel from those unobserved factors,
and the absence of a consistent difference is not evidence that channel could never matter
operationally.
→ [`agg_channel_controlled_comparison`](../data/aggregates/agg_channel_controlled_comparison.csv),
[`agg_channel_mix_by_service`](../data/aggregates/agg_channel_mix_by_service.csv)

---

## Q11 · How has demand changed over time?

**Citywide, January–July submissions rose 9.3% year over year** — from **225,628** in 2025
to **246,572** in 2026. Collapsing duplicates, the same comparison is +7.6%.

This comparison is fair for a specific, checkable reason. The scope is {open} + {closed
2026} + {closed 2025}. A request submitted on or after 2025-01-01 must be still open, or
closed in 2025, or closed in 2026 — it cannot have closed before it was submitted. So every
submission month from January 2025 is completely covered. Months before that are **not**,
and are flagged `incomplete` rather than charted; plotting them would show a fabricated
collapse in demand.

By `case_record_type` (higher-level staff-group label), which is the stable grain:

| Record type | Jan–Jul 2025 | Jan–Jul 2026 | Change |
|---|---:|---:|---:|
| ESD Complaint/Report | 71,794 | 84,627 | +17.9% |
| Parking | 46,108 | 54,088 | +17.3% |
| Neighborhood Policing | 20,592 | 27,255 | +32.4% |
| TSW | 64,797 | 58,527 | −9.7% |
| TSW ROW | 9,091 | 6,882 | −24.3% |

**Category-level year-over-year cannot be read directly.** Between September and December
2025 the City migrated volume between service names: monthly Parking Violation reports fall
from 8,417 to 2,111 while Parking – 72-Hours rises from 514 to 3,977, with the parent
Parking record type growing only 17.3% overall. That is a rerelabeling, not a demand shift.
**9** of 35 categories are flagged as not comparable in
[`agg_demand_yoy_by_service`](../data/aggregates/agg_demand_yoy_by_service.csv); anyone
quoting a category change should filter to `taxonomy_flag = 'comparable'` first.

Among comparable categories, the largest increase is Encampment at **+4,081** submissions
(+17.4%), followed by Missed Collection (+3,745, +22.1%).

Note also the aging pressure visible in the monthly table: the share of each month's
submissions still active rises from 4.3% (January 2025) to 21.2% (July 2026). Most of that
is simply recency — recent months have had less time to resolve — so it should not be read
as deterioration without a fixed-window follow-up.
→ [`agg_demand_yoy`](../data/aggregates/agg_demand_yoy.csv),
[`agg_demand_monthly`](../data/aggregates/agg_demand_monthly.csv)

---

## Q12 · Which 3 operational areas would you recommend leadership investigate first?

The ranked list is in
[`agg_priority_table`](../data/aggregates/agg_priority_table.csv). The score is a
**prioritization heuristic**, not a measurement: it combines three percentile-ranked
components using analyst-selected weights (0.45 share of the citywide 90+ day active
inventory, 0.35 share of the category's own active queue aged 90+, 0.20 median active age).

Under the baseline weighting the top three are:

### 1. Sidewalk Repair Issue — score 93.7
14,614 active records (18.0% of the active inventory), median active age 1,090 days, 94.7%
aged 90+, holding **22.3%** of the citywide 90+ day active inventory. Largest active queue
in the city and among the oldest.

### 2. Pavement Maintenance — score 91.1
5,590 active records, median active age **1,295.5 days** — the highest median active age
among categories eligible for the 500+ record priority score — with 95.7% aged 90+ and a P90
of 2,710 days, holding **8.6%** of the citywide 90+ day active inventory.

### 3. Street Light Maintenance — score 86.1
13,665 active records (16.8%), median active age 467 days, 90.2% aged 90+, holding **19.9%**
of the citywide 90+ day active inventory. Also the most duplicated active queue at 45.3% —
6,189 of its records are repeat reports of issues already logged.

### How sensitive is this to the weights?

Tested rather than assumed. The same three components were recombined under **5** weighting
schemes — baseline, equal thirds, volume-heavy, aged-rate-heavy and age-heavy — in
[`agg_priority_weight_sensitivity`](../data/aggregates/agg_priority_weight_sensitivity.csv).

**The result does not fully support a "stable top three" claim, so that claim is not made.**

| What was observed | Across the 5 schemes |
|---|---|
| Sidewalk Repair Issue and Pavement Maintenance occupy the top two positions | **5** of **5** (their relative order swaps) |
| Street Light Maintenance is in the top three | **4** of **5** |
| Top-three membership identical to baseline | 3 of 5 |

Under the aged-rate-heavy weighting (0.25 / 0.60 / 0.15) Street Light Maintenance falls to
fifth and Development Services – Code Enforcement enters at third. Under age-heavy and equal
weighting, Pavement overtakes Sidewalk for first place.

**What this means for a reader.** The two leading categories are robust to how the score is
weighted. The third position is not — it depends on whether leadership cares more about the
volume of aged work or the proportion of a queue that is aged. That is a stakeholder
judgment, not an analytical one, and the score should be presented to leadership with the
weights visible and adjustable rather than as a final ranking.

### What the evidence supports, and what it does not

**Supported.** These categories are where aged active records are concentrated. Sidewalk and
Pavement together account for **30.9%** of the citywide 90+ day active inventory.

**Not supported.** Nothing here shows that these categories are under-resourced, mismanaged
or failing. This dataset contains no staffing, budget, cost, work-order or completion data.

**A hypothesis worth testing, not a conclusion.** Sidewalk and pavement repair are commonly
delivered through multi-year capital programs, and a service-request record may remain in an
active status until the asset is scheduled and treated. If that is what is happening here,
the finding would be about record-keeping and resident expectation rather than about field
capacity. This dataset cannot distinguish that from any other explanation — testing it
requires the City's maintenance work-order system. That is why every recommendation is
framed as an investigation.

---

## What this analysis cannot tell you

- **Whether anything was repaired.** No work-completion data exists in this source.
- **How long work takes.** Only how long a case record stays open.
- **Anything about staff or crew performance.** No staffing, cost or productivity data.
- **Why any pattern exists.** No causal claim is available from observational case data
  with no controls.
- **True problem incidence.** Only reporting rates, which vary with resident awareness,
  app adoption and civic engagement — none of which is observable here.
- **Fair comparison between districts.** No population or asset denominators.
- **Category-level demand trends across the 2025/2026 boundary**, for the reason in Q11.
