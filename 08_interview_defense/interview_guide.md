# Interview Defense Guide

Questions a hiring manager is likely to ask about this project, with answers grounded only
in work that was actually done. Where the honest answer is "I don't know" or "the data
can't say", that is the answer given — those are usually the questions that separate
candidates.

**Snapshot referenced throughout:** 2026-08-09.

---

## Framing

### 1. Why this problem?

Because it has the shape of real operational analytics: a genuine stakeholder question, a
large messy public dataset, and a hard boundary on what may be concluded. The City states
outright that Get It Done is not a record of maintenance work. That constraint is the
interesting part — it forces every claim to be about the request queue rather than about
service delivery, and most analyses of 311-style data quietly get that wrong.

### 2. Who is the stakeholder and what decision are they making?

Hypothetical City service-operations leadership deciding where to direct investigation
capacity. The deliverable is a triage order, not a diagnosis — the data cannot support a
diagnosis, and the memo says so.

### 3. What is the grain of your dataset?

One row per `service_request_id` — a case record. 714,925 of them in scope.

There is a second, coarser grain I carry alongside it: `issue_key`, defined as
`COALESCE(parent_request_id, service_request_id)`, which collapses a duplicate child onto
its parent. That gives 622,135 distinct reported issues. Both are reported wherever the
difference is material, because they answer different questions: case records measure how
many things are in the queue, distinct issues measure how many real-world problems exist.

### 4. Why those three source files and not the full ten years?

Two reasons. The twelve business questions are about the current backlog and a recent
demand comparison, and 2016–2020 closures add nothing to either. More importantly, the
scope of {open + closed 2026 + closed 2025} has a clean property: any request submitted on
or after 2025-01-01 must be in exactly one of those three files. That gives complete
coverage of every submission month from January 2025 and makes the year-over-year
comparison defensible. Adding partial older years would muddy that without buying anything.

---

## Data quality

### 5. How did you validate case age? What did you find?

This is the finding I'd lead with.

The official dictionary says `case_age_days` is "the number of days between request
submission and request closure." I didn't assume that; I tested it separately for active
and terminal-status records.

For terminal-status records it matches `date_closed − date_requested` 99.88% of the time — as
documented. For active records, which have no close date at all, it instead matches
`snapshot_date − date_requested` 99.63% of the time. **The field carries two different
meanings depending on status, and the dictionary documents only one.**

An analyst who took the dictionary at face value and filtered on `case_age_days` would be
mixing two different quantities in one column.

So I stopped using the published field and computed two metrics from the dates:
`active_age_days` for open records, `lifecycle_days` for terminal-status ones. The published value
is retained as `case_age_days_published` so the comparison stays reproducible.

A bonus fell out of it: because the field encodes age-to-extract-date for open records, I
could recover the snapshot date as the modal `date_requested + case_age_days`. The pipeline
now derives its own snapshot date instead of hard-coding one, so it re-dates itself
automatically on a fresh download.

### 6. What else did the audit find that changed the analysis?

The service taxonomy. Two problems.

First, `service_name` and `case_record_type` are many-to-many — 36 service names appear
under more than one record type. I had initially treated record type as the parent of
service name, which was wrong, and it broke a share calculation I'd built on it. I switched
those columns to a modal value with `MODE()` and renamed them `most_common_record_type`.

Second, and worse: between September and December 2025 the City moved volume between two
service names. Monthly Parking Violation reports fall from 8,417 to 2,111 while
Parking – 72-Hours rises from 514 to 3,977 — while the parent Parking record type grew only
17.3%. Taken at face value, Parking – 72-Hours "grew 3,914% year over year". That is a
relabeling, not demand.

So I built a detector, flagged 9 of 35 categories as not comparable, and moved the reported
year-over-year to citywide and record-type grain, which absorb a service-name relabeling.

### 7. Tell me about a check that gave you a false positive.

My first structural-break detector flagged a category whenever its share of citywide demand
moved by 2 points or more. That flagged Illegal Dumping — whose volume had only fallen
5.6%. Its share moved because the *denominator* grew 9.3%, not because anything happened to
the category.

I added a second condition: a break now requires a ≥ 2-point share shift **and** a ≥ 25%
volume change. Illegal Dumping correctly drops out. Separately, a discontinued category
(1,157 → 0 submissions) was passing as "comparable" because a −100% change fell below my
volatility threshold, so I added an explicit discontinued rule.

Both are in `03_sql/09_trends.sql` with the reasoning in the comments.

### 8. How clean is the data overall?

13 checks: 4 PASS, 6 WARN, 2 FAIL, 1 INFO. The FAILs are the `case_age_days` semantics and
the taxonomy instability — both handled, both documented.

The mechanical quality is good. Zero duplicate ids within any extract, zero missing request
dates, only 5 records with a close date before the request date, council district complete
for 99.0% of records. The problems are semantic, not structural, which is the harder kind
to find.

---

## Method

### 9. How did you define backlog?

`status IN ('New', 'In Process')` — 81,359 case records.

The decision that needed thought was `Referred`. I excluded it from active backlog: a
referred case has left the Get It Done queue, so counting it as open workload would
overstate the queue. But I also refuse to count it as a service outcome, because a referral
is a hand-off, not a result. It is terminal for backlog arithmetic and is reported
separately from Closed status everywhere else. That distinction matters — referred records
have a median recorded lifecycle of 0 days, so folding them into closures would flatter
every outcome metric.

### 10. Why median instead of mean?

The mean active age is 649.9 days; the median is 381. The mean is 70% higher because the
distribution has a tail reaching 3,731 days — 8.4% of active records exceed five years.

The mean describes neither the typical request nor the tail. The median describes the
typical request, and P90 describes the tail. I publish the mean alongside both so a reader
can see the skew rather than take my word for it.

### 11. What is P90 and why do you report it?

The value below which 90% of observations fall. Active P90 is 1,680 days.

I report it because a median alone hides the cases that generate complaints. More usefully,
the *relationship* between median and P90 identifies two different operational problems.
Pavement Maintenance has a median of 1,295.5 days and a P90 of 2,710 — that queue is old
throughout. Pothole has a median of 133.5 days and a P90 of 1,257, a ratio of 9.4 — that
queue mostly works but has a small population of cases stranded outside the process. Those
need different responses, and only the median would make them look similar.

### 12. How did you treat duplicate reports?

I used the City's own determination — the `service_request_parent_id` field, which the City
populates when it judges a report to describe an already-open issue. I did **not** attempt
fuzzy matching on address or description, because that would put an unmeasured error rate
into a headline metric. So my duplicate rate is a floor, not an exact figure, and I say so.

13.2% of all case records are duplicate children; 27.0% within the active backlog. The gap
is structural — a duplicate can only attach to a still-open parent, so long-lived cases
accumulate them.

### 13. Did removing duplicates change your conclusions?

I tested one specific thing, so let me be precise about what I can claim. Collapsing
duplicate child records removes 25.9% of active volume, and across the top 20 categories by
volume only 11 change rank at all, none by more than 2 positions.

That's a statement about **volume rankings**. I did not re-derive the full composite priority
score on deduplicated inputs, so I can't claim the priority table is unchanged by
deduplication — only that the volume ordering it draws on is stable.

The place the grain really matters is Street Light Maintenance, where 45.3% of the active
queue is duplicates. If the question is "how many streetlights need attention", the
case-record count overstates it by 6,189.

### 14. Walk me through your priority score.

Three components, each converted to a percentile rank across categories with 500+ active
records so measures on different units can combine: share of the aged backlog held (0.45),
share of the category's own queue that is aged 90+ (0.35), and median active age (0.20).
Volume carries the most weight because leadership attention is finite and should follow the
mass of the problem.

The weights are a judgment, not a derivation — so I tested how much they matter rather than
asserting they don't. I ran the same components under five weightings: baseline, equal
thirds, volume-heavy, aged-rate-heavy and age-heavy.

The result made me weaken my own earlier claim. Sidewalk Repair Issue and Pavement
Maintenance hold the top two under all five, though their order swaps. But Street Light
Maintenance is top-three in only four of five — under aged-rate-heavy weighting it drops to
fifth and Development Services – Code Enforcement takes third.

So what I'd tell leadership is: the top two are robust, the third slot depends on whether you
care more about the volume of aged work or the proportion of a queue that's aged. That's your
call, not mine, and the score should be presented with the weights visible.

Every row also carries a `why_flagged` string, so the ranking is never presented as an
unexplained number.

### 15. What was the hardest query to write?

The geography aged-concentration index, for a mundane reason and an interesting one.

Mundane: DuckDB rejects a window function nested inside another window's `ORDER BY`, so
ranking by an index that was itself computed with `SUM() OVER ()` needed the shares
materialised in their own CTE first.

Interesting: getting the metric right took longer than writing it. Raw counts by district
mostly measure district size, which answers nothing. The index — an area's share of the 90+
day backlog divided by its share of all active work — is unit-free, so districts of
different sizes compare directly. Writing it was ten minutes; deciding it was the right
question took considerably longer.

### 16. Which chart on the dashboard did you get wrong first?

The duplicates panel. I originally sorted it by duplicate *rate* while the bar length
encoded absolute volume, so Pothole — 332 active records at a 57.8% rate — headed a chart
where its bar was invisible. The accompanying text also said Street Light Maintenance was
"the most duplicated category", which was wrong: it leads on absolute duplicate records
(6,189), while Pothole leads on rate.

I re-sorted by volume so bar length carries meaning, and rewrote the text to distinguish the
two claims. I caught it by rendering the dashboard and actually looking at it, which is why
screenshot review is a step in the build.

---

## Interpretation

### 17. What can this dataset NOT tell us?

The list matters more than any finding:

- **Whether anything was repaired.** No work-completion data exists. The City says so
  explicitly.
- **How long work takes.** Only how long a case record stays open.
- **Anything about staff or crew performance.** No staffing, cost or productivity data.
- **Why any pattern exists.** No causal claim is available from observational case data
  with no controls.
- **True problem incidence.** Only reporting rates, which vary with app adoption and civic
  engagement — neither observable here.
- **Whether districts are served equally.** No population or asset denominators.

### 18. Your backlog has a median age of 381 days. Isn't that damning?

That's the question I most want to be asked, because the honest answer is no — or at least,
not yet demonstrated.

Two facts sit side by side. Of requests submitted January–June 2026, 91.2% had reached
Closed or Referred status by the snapshot; among those terminal-status records, median
recorded lifecycle was 2 days. Separately, the standing active inventory had a median age
of 381 days. These are different populations and should not be interpreted as the same
lifecycle measure.

One benign hypothesis is that sidewalk and pavement repair are multi-year capital programs,
and a Get It Done case stays open until the asset is scheduled and treated. If that's what's
happening, this is a case-record hygiene and resident-expectation problem, not a crew problem.

I can't distinguish those two worlds with this data, which is exactly why my
recommendations say "investigate" and my next measurement step is a join to the work-order
system.

### 19. You reported a 3-day median for records closed in 2026. Is that a good lifecycle metric?

It's a real number and a misleading one, and I flagged it myself rather than quoting it.

88.1% of cases closed in 2026 were also submitted in 2026. A closure cohort is dominated by
fast cases by construction — slow cases haven't closed yet, so they're absent from the
denominator. Decomposed by submission year, the same closures show a median of 2 days for
2026 submissions, 93 days for 2025, and 627 days for 2024.

The fix is a submission cohort: fix the denominator at submission time and ask what became of
it. Of everything submitted January–June 2026, 91.2% had reached a terminal status by the
snapshot, and among those the median recorded lifecycle was 2 days (P90 29 days), with 8.8%
still active.

I'd flag one thing even about that: the 91.2% is a complete measure of the cohort, but the
2-day median is still right-censored — it only covers records that had reached a terminal status by the
snapshot, and the ones still open are by definition the slower ones. So I quote the
terminal-status share as the solid number and treat the lifecycle median as descriptive of
terminal-status records only.

### 20. Do submission channels affect outcomes?

Not that this data can show, and I tested it properly rather than reporting the raw
comparison.

Raw channel medians differ, but channel is confounded with what's being reported: Missed
Collection arrives 32,872 times by web against 403 by mobile, while Parking Violation
arrives 60,033 times by mobile. Comparing channel medians without controlling compares
waste collection to parking enforcement.

Holding service category constant across 29 categories, the median absolute mobile-vs-web
difference is 2 days, and 26 of 29 differ by 20 days or less. Two exceptions point in
opposite directions, which argues against a broad, consistent channel-associated pattern.

My conclusion, stated carefully: the data does not show a broad, consistent
channel-associated lifecycle difference after stratifying by service category. That is not
the same as "channel doesn't matter" — residents choose their own channel, so it's tangled up
with reporter and problem characteristics I can't observe. Nothing here separates channel
from those unobserved factors.

### 21. Did you find geographic inequity?

Not under the metric I used, and I'd be careful about how far that goes.

The aged-concentration index — a district's share of the citywide 90+ day inventory divided
by its share of all active records — varies only from 0.826 to 1.085 across the nine
districts. So no strong district-level over-concentration is evident.

What I would not say is "aging isn't geographic." That's one descriptive ratio, at one
snapshot, on reported requests rather than conditions, with no population or asset
denominators available. An effect could exist in reporting propensity, in asset age, or at a
finer level than a council district, and none of that is observable here.

What it does support is sequencing: service category discriminates far more strongly than
district does on this data, so category is the better axis to investigate first. And there's
an equity caveat I can't resolve — if some communities report less for reasons of trust,
language or app access, that would be invisible in a dataset made of reports.

### 21a. Why isn't Closed the same as a physical repair?

Because the City says so, and because the field simply isn't there. Get It Done records a
*case status*. There is no work-order id, no completion date, no crew, no cost. A record
moves to Closed when the case is closed in the system — which could mean the work was done,
or that it was a duplicate, or out of jurisdiction, or unverifiable, or administratively
closed.

So throughout the project I say "reached a terminal Get It Done status", never "completed" or
"repaired". It sounds pedantic until you realize the alternative is publishing a repair-time
metric that isn't a repair time.

### 21b. Why can't you infer backlog growth from one active snapshot?

Because I have a stock, not a flow. 81,359 active records is a photograph of one moment. To
say the backlog is growing I'd need at least two snapshots of the same measure, and the
open-requests extract is overwritten daily — there is no history of it in the source.

I can see submissions rising 9.3% year over year, and I can see the active inventory is old.
What I cannot do is subtract one from the other and call it growth, because I don't observe
the exit rate for the standing inventory separately from recent intake. That's why the next
measurement step in the memo is a daily snapshot table — it converts a stock into a
measurable flow.

I'll also flag the trap I avoided here: the monthly table shows the share of each month's
submissions still active rising from 4.3% to 21.2%. That looks like deterioration and is
mostly just recency — recent months have had less time to reach a terminal status.

### 21c. What additional data would you request from the stakeholder?

Four things, in priority order:

1. **The maintenance work-order feed.** Single highest value. It converts every "case age"
   statement in this project into a statement about service delivery.
2. **A daily or weekly snapshot of the open queue**, so backlog change becomes measurable.
3. **Denominators** — population, street mileage, streetlight and sidewalk asset counts by
   district — so geographic comparison becomes meaningful rather than a proxy for district
   size.
4. **The service taxonomy change log.** I detected the autumn 2025 relabeling from the data,
   but I had to infer it. A change log would have made it a lookup instead of an
   investigation.

### 22. What conclusion are you least confident in?

The Caltrans referral recommendation.

The count is solid — 9,123 referrals, 21.1% of all referrals. What I'm less sure of is the
implied fix. I inferred "residents can't tell state right-of-way from City right-of-way"
from the volume and destination, but I have no data on where those reports were filed from,
and I deliberately excluded lat/lng from published outputs on privacy grounds. So I can't
demonstrate they cluster on state highways.

It's phrased as "examine" rather than "fix" for that reason. If pressed, I'd rank it third
of three and say the first two rest on much stronger evidence.

### 23. What would you do differently with more time?

Recursive duplicate chains — I collapse one parent level, and 428 children point at another
child. It's 0.06% of records so it doesn't move anything, but it's a known simplification.

I'd also want to explain the `(Unclassified)` service group growing from 173 to 2,919
submissions year over year. That's a data-quality signal in the source that I surfaced but
didn't chase.

And I'd build a daily snapshot table. Right now I have one point in time, so I can measure
the backlog but not whether it's growing. Backlog *change* is the metric leadership actually
needs, and one snapshot can't produce it.

### 24. What would change in production?

Incremental loads against the daily refresh instead of a full rebuild. A daily snapshot
table so backlog change becomes measurable. Schema contract tests that fail loudly when a
column type or status domain changes upstream — this dataset has already demonstrated it
will change its taxonomy without warning. And fixed-window aging metrics replacing
closure-cohort medians as the headline, for the reason in question 19.

The single highest-value change isn't technical: it's getting the maintenance work-order
feed, which would convert every case-age statement here into a statement about service
delivery.

### 25. How do you know the numbers in your README are right?

They're not typed by hand. `src/claims.py` recomputes every quoted figure from the generated
aggregates and formats it exactly as the documents must contain it;
`scripts/verify_claims.py` then asserts each string appears in the documents that should
carry it, and separately extracts every number-like token from the README, memo and findings
and checks it can be traced to a value in the aggregates.

If a number drifts because the data was refreshed, the check fails. `make verify` runs it,
and it runs in CI.

I built it after catching myself writing "Street Light Maintenance is the most duplicated
category" when the data said Pothole led on rate. One wrong sentence I wrote myself was
enough to justify the automation.

### 26. How did you handle privacy on a public dataset?

Public doesn't mean everything needs republishing. Eight source fields never reach any
output: resident free text, exact street address, lat/lng, the raw referral message,
internal asset identifiers and SAP numbers.

The referral field is the one worth mentioning — it's a canned routing message, but it
contains staff and vendor **email addresses**, so I normalize it to a destination label and
drop the text.

Two mechanisms enforce it rather than relying on my discipline: the pipeline refuses to
export the fact table if a suppressed field is present, and a test fails if any suppressed
field name or address/email-like pattern appears in any published artifact. Raw CSVs are
git-ignored.

### 27. Why DuckDB rather than pandas or a warehouse?

The SQL is the deliverable. An analytics team reads and reviews SQL; they don't review a
chain of pandas transformations as easily. DuckDB runs that SQL against 715,000 rows in
seconds with no server. A reviewer can validate the published snapshot with the committed
aggregates, automated test suite, claim verification and source hashes; `make all` instead
downloads the City's rolling extracts and refreshes the outputs with current data.

Python does what SQL shouldn't: orchestration, the audit harness, rendering. `src/pipeline.py`
executes files and exports results — it holds no business logic. Anyone can run
`duckdb data/processed/gid.duckdb -c ".read 03_sql/04_service_analysis.sql"` and get the same
table without touching Python.

### 28. If I only had five minutes with your repo, what should I read?

`README.md` for the findings, then `02_data_audit/data_quality_report.md` — DQ-03 and DQ-08
are where the actual analytical work is. If you want to see how I write SQL,
`03_sql/09_trends.sql` has the coverage argument and the taxonomy detector, which are the
two places where getting the question right mattered more than getting the syntax right.
