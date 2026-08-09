# Methodology

How the analysis was built, what was decided along the way, and why. Written so that
another analyst can reproduce the result or disagree with a specific choice.

**Snapshot:** 2026-08-09 · **Engine:** DuckDB 1.5.5 · **Grain:** one row per
`service_request_id`

---

## 1. Pipeline

```
scripts/download_data.py     official CSVs -> data/raw/ (git-ignored) + manifest
      |
03_sql/00_sources.sql        typed views over the raw CSVs; snapshot date derived
03_sql/01_clean_base.sql     union -> deduplicate -> derive -> suppress -> fct_requests
      |
03_sql/02..10_*.sql          33 aggregate tables -> data/aggregates/*.csv
      |
src/audit.py                 13 reproducible checks -> data_quality_report.md
src/claims.py                canonical numbers for every written document
      |
src/build_dashboard.py       self-contained dashboard.html
src/build_excel.py           san_diego_ops_review.xlsx
scripts/verify_claims.py     every written figure re-checked against the aggregates
```

`src/pipeline.py` is only a runner. The analysis lives in the `.sql` files, which can be
executed directly:

```bash
duckdb data/processed/gid.duckdb -c ".read 03_sql/00_sources.sql"
```

## 2. Source selection

Three official extracts: the live open queue, closures during 2026, closures during 2025.
Closed-year files for 2016–2024 exist and the downloader supports them (`--all-closed`),
but they were excluded deliberately. Adding them would extend history without improving any
of the twelve business questions, and would **break the coverage argument** that makes the
year-over-year demand comparison valid (§6).

Only official City URLs were used. No third-party mirrors.

## 3. Deduplication across extracts

Nine `service_request_id` values appear in more than one extract, seven of them in both
closed-year files with a later closure date in 2026. Records are kept once, from the extract
with the lowest precedence number:

| Precedence | Extract | Rationale |
|---|---|---|
| 1 | open | the live queue is the most recently refreshed view of a case |
| 2 | closed_2026 | most recent closed-year archive |
| 3 | closed_2025 | older archive |

Two of the nine are genuinely contradictory (closed in the 2025 archive, still open in the
live queue). The rule resolves them toward the live extract. Nine records out of 714,925 is
not material, but the count is published rather than silently absorbed —
audit check DQ-02.

## 4. The `case_age_days` decision

**This was the most consequential finding of the audit and it changed the design.**

The official dictionary defines `case_age_days` as "the number of days, rounded to the
nearest whole day, between request submission and request closure."

Tested against the data:

| Population | Hypothesis tested | Agreement |
|---|---|---|
| Resolved records (633,566) | `case_age_days = date_closed − date_requested` | **99.88%** |
| Active records (81,359) | `case_age_days = date_closed − date_requested` | impossible — no close date exists |
| Active records (81,359) | `case_age_days = snapshot_date − date_requested` | **99.63%** |

The field carries **two different meanings** depending on status, and the dictionary
documents only one. It also let the snapshot date be recovered: the modal value of
`date_requested + case_age_days` across active records is 2026-08-09.

**Decision.** The published field is not used for any analysis. It is retained as
`case_age_days_published` solely so the comparison above stays reproducible. Two metrics
are computed from the dates instead:

- `active_age_days` = `snapshot_date − date_requested`, for active records only
- `lifecycle_days` = `date_closed − date_requested`, for resolved records only

The 0.37% of active records that disagree (298 records) are stale by up to 59 days,
consistent with rows not
refreshed on the latest publication run. That is a caveat on individual records, not on the
distribution.

## 5. Choice of statistics

| Choice | Reason |
|---|---|
| Median as the headline | Mean active age (649.9 days) is 70% above the median (381) because of a tail reaching 3,731 days. The mean is published alongside so the skew is visible rather than hidden. |
| P90 as the tail metric | Answers "how bad does it get for the worst tenth", which is what a service commitment is written against. |
| P90 ÷ own median, and P90 z-score across peers | Two different failure modes. A category can be uniformly slow, or mostly fine with a stranded minority. The two lists barely overlap. |
| Percentile ranks in the priority score | Combines measures on different units (counts, rates, days) without one dominating by scale. |
| Volume floors (250 / 500 records) | A p90 on 40 records is noise. Floors are stated in each SQL file and in the table headers. |
| A unit-free concentration index for geography | Raw district counts mostly measure district size. The index divides share-of-aged by share-of-total, so areas of different sizes compare directly. |

No significance testing is reported. The populations here are complete administrative
records rather than samples, so a p-value would answer a question nobody asked; the
relevant uncertainty is measurement bias, not sampling error, and that is handled in the
audit.

## 6. The coverage argument for demand trends

The year-over-year comparison rests on one claim: **every submission month from January 2025
is completely covered by the three extracts in scope.**

The argument: a request submitted on or after 2025-01-01 must be in one of exactly three
states — still open (in the `open` extract), closed during 2025 (in `closed_2025`), or
closed during 2026 (in `closed_2026`). It cannot have closed before it was submitted, and
no fourth state exists at this snapshot. Therefore no submission from that window is
missing.

The same argument fails for 2024: a request submitted and closed in 2024 appears in none of
the three files. Those months are flagged `incomplete` and excluded from every chart and
every stated figure. The monthly table shows January 2024 at 1,648 submissions against
January 2025 at 33,626 — that twentyfold gap is the coverage boundary, not a demand
collapse, and it is labelled as such.

The comparison window is January–July, the months fully elapsed at the snapshot. August
2026 is partial and excluded.

## 7. The service taxonomy problem

Two structural issues in the classification, both found by audit check DQ-08:

**`service_name` and `case_record_type` are many-to-many.** 36 service names appear under
more than one record type — "Sidewalk Repair Issue" appears under six. Record type cannot
be treated as a parent of service name. Wherever the two are shown together, the record type
is the **modal** value computed with `MODE()`, not an arbitrary pick, and the column is
named `most_common_record_type` to say so.

**Volume moved between labels in autumn 2025.** Monthly Parking Violation reports fall from
8,417 (Aug 2025) to 2,111 (Dec 2025) while Parking – 72-Hours rises from 514 to 3,977, with
the parent Parking record type growing only 17.3% across the comparison window. That is a
relabelling.

**Detection.** A category is flagged when its share of citywide demand moves ≥ 2 percentage
points **and** its volume changes ≥ 25%. Both tests are required: a share shift alone is
produced whenever citywide demand grows, which initially flagged Illegal Dumping (−5.6% in
volume) as a break. Additional flags cover new, discontinued, newly-adopted and volatile
categories. 9 of 35 categories are flagged.

**Treatment.** Year-over-year demand is reported citywide and by record type, both of which
absorb a service-name relabelling. No flagged category appears in any written finding. The
flag asserts "not comparable without verification" — only the Parking pair is claimed as a
confirmed relabelling, on the crossover evidence above.

## 8. Duplicate treatment

`issue_key = COALESCE(parent_request_id, service_request_id)` collapses one level of the
parent/child relationship. Both grains are reported everywhere it matters.

Three details worth stating:

- **3,421 children (3.6%) point at a parent outside the scope** — expected, since a parent
  closed before 2025 is not in these files. Such a child keeps its parent's id as its
  `issue_key`, so it is still not double-counted against a parent that *is* present.
- **428 children point at another child.** Only one level is collapsed. Deeper chains would
  need a recursive CTE; at 0.06% of records the added complexity was not justified, and the
  count is published.
- **No fuzzy matching was attempted.** Detecting further duplicates by address or
  description similarity would introduce an unmeasured error rate into a headline metric.
  The reported duplicate rate is therefore a **floor**.

## 9. Privacy

Eight source fields never reach any output, dropped in `01_clean_base.sql` before anything
is written to disk:

`public_description`, `street_address`, `lat`, `lng`, `referred` (raw text),
`iamfloc`, `floc`, `sap_notification_number`

The first four are resident free text and exact locations. The raw `referred` message is
excluded because it contains staff and vendor **email addresses** — it is normalised to a
destination label and a scope instead. The last three are internal identifiers with no
analytical value here.

Two mechanisms enforce this rather than relying on discipline:

1. `src/pipeline.py` refuses to export the fact table if any suppressed field is present.
2. `tests/test_privacy.py` fails if any suppressed field name appears in any published
   artefact, and scans the processed dataset and every aggregate for address-like and
   email-like patterns.

Geography is published at council district, community planning area and ZIP level only.

## 10. Known weaknesses

Stated plainly, because a reviewer will find them anyway:

- **The `(Unclassified)` service group is growing** — 173 submissions in Jan–Jul 2025 against
  2,919 in the same window of 2026. That is a data-quality signal in the source that this
  project surfaces but does not explain.
- **Referral destination parsing is rule-based.** Every referred record resolves to a label,
  but "City – Other department" (19.1% of referrals) is a residual bucket, not one
  department.
- **The priority score's weights are a judgement.** 0.45 / 0.35 / 0.20 is defensible and
  documented, not derived. Different weights would reorder the middle of the list; the top
  three are stable under any reasonable weighting because they lead on all three components.
- **A bulk closure event sits in the closure data** — 4,515 cases submitted in 2018 were
  closed during 2026 with a median lifecycle of 2,753 days. This is visible in
  `agg_closure_cohort_bias` and is not investigated further here.
- **Excel formula results are not machine-verified.** openpyxl writes formulas but does not
  evaluate them, and no spreadsheet engine was available in this environment to recalculate
  the workbook. The formulas are written to compare themselves against SQL-derived values
  and display MATCH or REVIEW when opened.

## 11. What would change in production

- Incremental loading against the daily refresh instead of a full rebuild.
- A snapshot table capturing backlog by category and age bucket each day, so backlog *change*
  becomes measurable — currently only one point in time exists.
- Schema contract tests against the source, failing loudly when a column type or a status
  domain changes.
- A join to the maintenance work-order system, which is the single change that would convert
  every "case age" statement here into a statement about service delivery.
- Fixed-window ageing metrics (share of a submission cohort still open at 30/60/90 days) to
  replace closure-cohort medians as the headline throughput measure.
