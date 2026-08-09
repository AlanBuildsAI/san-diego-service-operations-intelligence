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
and resolved records.

For resolved records it matches `date_closed − date_requested` 99.88% of the time — as
documented. For active records, which have no close date at all, it instead matches
`snapshot_date − date_requested` 99.63% of the time. **The field carries two different
meanings depending on status, and the dictionary documents only one.**

An analyst who took the dictionary at face value and filtered on `case_age_days` would be
mixing two different quantities in one column.

So I stopped using the published field and computed two metrics from the dates:
`active_age_days` for open records, `lifecycle_days` for resolved ones. The published value
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
relabelling, not demand.

So I built a detector, flagged 9 of 35 categories as not comparable, and moved the reported
year-over-year to citywide and record-type grain, which absorb a service-name relabelling.

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
is a hand-off, not a result. It sits in "resolved" for backlog arithmetic and is reported
separately from "closed" everywhere else. That distinction matters — referred cases have a
median lifecycle of 0 days, so folding them into closures would flatter every completion
metric.

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

No, and I tested it rather than assuming. Collapsing duplicates removes 25.9% of active
volume, but across the top 20 categories only 11 change rank at all and none moves more
than 2 positions. The four largest categories are the same four at either grain.

So the grain matters for *sizing* work and not for *targeting* it. The one place it really
matters is Street Light Maintenance, where 45.3% of the queue is duplicates — if the
question is "how many streetlights need attention", the case-record count overstates it by
about 6,000.

### 14. Walk me through your priority score.

Three components, each converted to a percentile rank across categories with 500+ active
records so measures on different units can combine: share of the aged backlog held (0.45),
share of the category's own queue that is aged 90+ (0.35), and median active age (0.20).
Volume carries the most weight because leadership attention is finite and should follow the
mass of the problem.

The weights are a judgement, not a derivation, and I'd say that in the room. What makes me
comfortable is that the top three lead on all three components, so they're stable under any
reasonable reweighting. Different weights would reshuffle the middle of the list.

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

Two facts sit side by side. Of requests submitted January–June 2026, 91.2% have already
resolved, typically in 2 days. Yet the standing backlog has a median age of 381 days. Both
are true because they describe different populations.

The most likely benign explanation is that sidewalk and pavement repair are multi-year
capital programmes, and a Get It Done case stays open until the asset is scheduled and
treated. If that's what's happening, this is a case-record hygiene and resident-expectation
problem, not a crew problem.

I can't distinguish those two worlds with this data, which is exactly why my
recommendations say "investigate" and my next measurement step is a join to the work-order
system.

### 19. You reported that closed cases have a 3-day median lifecycle. Is that a good number?

It's a real number and a misleading one, and I flagged it myself rather than quoting it.

88.1% of cases closed in 2026 were also submitted in 2026. A closure cohort is dominated by
fast cases by construction — slow cases haven't closed yet, so they're absent from the
denominator. Decomposed by submission year, the same closures show a median of 2 days for
2026 submissions, 93 days for 2025, and 627 days for 2024.

The unbiased version is a submission cohort: take everything submitted January–June 2026
and ask what became of it. 91.2% resolved, median 2 days, P90 29 days, 8.8% still active.
That's the number the recommendations rest on.

### 20. Do submission channels affect outcomes?

Not that this data can show, and I tested it properly rather than reporting the raw
comparison.

Raw channel medians differ, but channel is confounded with what's being reported: Missed
Collection arrives 32,872 times by web against 403 by mobile, while Parking Violation
arrives 60,033 times by mobile. Comparing channel medians without controlling compares
waste collection to parking enforcement.

Holding service category constant across 29 categories, the median absolute mobile-vs-web
difference is 2 days, and 26 of 29 differ by 20 days or less. Two exceptions point in
opposite directions, which argues against a general channel effect.

My conclusion: channel is not a lever this data supports pulling. That's a negative
finding and I report it as one.

### 21. Did you find geographic inequity?

No — and I think that's a more useful answer than a manufactured one.

The aged-concentration index spans only 0.826 to 1.085 across the nine council districts.
Every district holds close to the share of aged work its queue size implies. Ageing in this
dataset is a property of service category, not geography, so a district-targeted
intervention would be aimed at the wrong axis.

I'd add a caveat I can't resolve: this measures reports, not conditions. If some
communities report less for reasons of trust, language or app access, an equity problem
could exist and be invisible here. Answering that needs survey or asset-condition data.

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
will change its taxonomy without warning. And fixed-window ageing metrics replacing
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
contains staff and vendor **email addresses**, so I normalise it to a destination label and
drop the text.

Two mechanisms enforce it rather than relying on my discipline: the pipeline refuses to
export the fact table if a suppressed field is present, and a test fails if any suppressed
field name or address/email-like pattern appears in any published artefact. Raw CSVs are
git-ignored.

### 27. Why DuckDB rather than pandas or a warehouse?

The SQL is the deliverable. An analytics team reads and reviews SQL; they don't review a
chain of pandas transformations as easily. DuckDB runs that SQL against 715,000 rows in
seconds with no server, so the whole project is `git clone` plus `make all`.

Python does what SQL shouldn't: orchestration, the audit harness, rendering. `src/pipeline.py`
executes files and exports results — it holds no business logic. Anyone can run
`duckdb data/processed/gid.duckdb -c ".read 03_sql/04_service_analysis.sql"` and get the same
table without touching Python.

### 28. If I only had five minutes with your repo, what should I read?

`README.md` for the findings, then `02_data_audit/data_quality_report.md` — DQ-03 and DQ-08
are where the actual analytical work is. If you want to see how I write SQL,
`03_sql/09_trends.sql` has the coverage argument and the taxonomy detector, which are the
two places where getting the question right mattered more than getting the syntax right.
