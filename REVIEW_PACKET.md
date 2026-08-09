# Review Packet

Everything needed to check this project, generated from the actual run by
[`scripts/build_review_packet.py`](scripts/build_review_packet.py).

**Generated:** 2026-08-09 19:12 UTC  
**Data snapshot:** 2026-08-09  
**DuckDB:** 1.5.5  
**Python:** 3.13.5

---

## 1. Dataset and files used

Source: **City of San Diego, Performance & Analytics Department** — <https://data.sandiego.gov/datasets/get-it-done-reports/>

| File | Size | SHA-256 (first 16) | Physical lines |
|---|---:|---|---:|
| `get_it_done_requests_dictionary_datasd.csv` | 0.0 MB | `6703a0fbc9600a52…` | 23 |
| `get_it_done_requests_open_datasd.csv` | 29.7 MB | `37278b5b467543a7…` | 88,658 |
| `get_it_done_requests_closed_2026_datasd.csv` | 86.2 MB | `c156ae3a57cfec60…` | 257,368 |
| `get_it_done_requests_closed_2025_datasd.csv` | 128.2 MB | `2659650f008bca0e…` | 378,675 |

Full hashes and licensing: [`docs/source_manifest.md`](docs/source_manifest.md).
Raw files are **not committed** — `data/raw/` is git-ignored.

## 2. Row counts

| Stage | Rows |
|---|---:|
| `open` extract, parsed | 81,359 |
| `closed_2026` extract, parsed | 254,906 |
| `closed_2025` extract, parsed | 378,669 |
| **Total read** | **714,934** |
| Dropped as cross-file duplicate ids | 9 |
| **Fact table `fct_requests`** | **714,925** |

Aggregate tables produced: **33**

<details><summary>Row count per aggregate</summary>

| Aggregate | Rows |
|---|---:|
| `agg_backlog_age_percentiles` | 4 |
| `agg_backlog_aging_buckets` | 8 |
| `agg_backlog_aging_by_record_type` | 9 |
| `agg_channel_controlled_comparison` | 29 |
| `agg_channel_gap_summary` | 1 |
| `agg_channel_mix_by_service` | 44 |
| `agg_channel_status_mix` | 11 |
| `agg_channel_summary` | 27 |
| `agg_closure_cohort_bias` | 11 |
| `agg_closure_monthly` | 20 |
| `agg_demand_monthly` | 32 |
| `agg_demand_yoy` | 2 |
| `agg_demand_yoy_by_record_type` | 9 |
| `agg_demand_yoy_by_service` | 35 |
| `agg_duplicate_by_service` | 28 |
| `agg_duplicate_cluster_size` | 5 |
| `agg_duplicate_rank_impact` | 20 |
| `agg_duplicate_summary` | 3 |
| `agg_executive_kpis` | 27 |
| `agg_geography_aging_index` | 50 |
| `agg_geography_community` | 49 |
| `agg_geography_district` | 10 |
| `agg_priority_hotspots` | 94 |
| `agg_priority_table` | 24 |
| `agg_referral_by_district` | 10 |
| `agg_referral_by_service` | 35 |
| `agg_referral_destinations` | 26 |
| `agg_referral_status_consistency` | 8 |
| `agg_referral_summary` | 2 |
| `agg_service_backlog` | 40 |
| `agg_service_concentration` | 6 |
| `agg_service_tail_risk` | 28 |
| `agg_submission_cohort` | 1 |

</details>

## 3. Tests run and results

| Gate | Command | Result |
|---|---|---|
| Unit and integration tests | `make test` | **PASS** — ............                                                             [100%] |
| Written-figure verification | `make verify` | **PASS** |
| Data-quality audit | `make audit` | 4 PASS · 6 WARN · 2 FAIL · 1 INFO |

The test suite runs the project's real SQL against a committed synthetic fixture,
so it needs no downloaded data and runs in CI on every push.

<details><summary>Claim verification output</summary>

```
Check 1 — registry: every declared claim appears in its documents
  PASS — 117 assertions across 69 claims

Check 2 — traceability: every number in prose exists in the aggregates
  PASS — every number traced to a value in data/aggregates/

RESULT: PASS
```

</details>

## 4. Main findings

1. **Intake is fast; a specific queue is not clearing.** 91.2% of requests submitted Jan–Jun 2026 are already resolved, median 2 days — yet 81,359 requests are active with a median age of 381 days.
2. **76.1% of the active backlog is past 90 days** (61,922 records); 51.0% is past a year.
3. **Four categories hold 54.2% of the backlog**, all under the TSW record type (64.0% of active work).
4. **Ageing is not geographic** — the aged-concentration index spans only 0.826 to 1.085 across the nine council districts. Reported as a negative finding.
5. **Duplicates are 27.0% of the active queue** (21,971 records) but move no category more than 2 rank positions.
6. **Two metrics are traps and both are handled**: the 3-day closure median is a cohort artefact (88.1% of this year's closures were also submitted this year), and the apparent channel effect collapses to 2 days once service category is held constant.

Full reasoning: [`04_analysis/findings.md`](04_analysis/findings.md).

## 5. Known limitations

- **The data records requests, not work.** No work-completion detail exists. A closed
  case means a case closed, not that a repair happened. Nothing here measures crew
  performance and no claim is causal.
- **No denominators.** No population, street mileage or asset counts, so districts
  cannot be compared as service levels.
- **Duplicate counts are a floor** — the City's own determinations only; no fuzzy
  matching was attempted.
- **Category-level year-over-year is invalid** across the 2025/2026 boundary because
  of a confirmed service relabelling. Reported citywide and by record type instead.
- **One level of duplicate nesting is collapsed.** 428 children point at another
  child (0.06% of records).
- **Referral destination parsing is rule-based**; `City – Other department` is a
  residual bucket, not one department.
- **Priority-score weights (0.45 / 0.35 / 0.20) are a documented judgement**, not a
  derivation. The top three are stable under reweighting; the middle of the list is not.

## 6. Unverified or blocked items

Stated explicitly rather than glossed:

| Item | Status | Detail |
|---|---|---|
| Tableau workbook | **BLOCKED** | Tableau cannot be automated here. No `.twb` was fabricated; a full build spec is at [`05_dashboard/tableau_build_spec.md`](05_dashboard/tableau_build_spec.md). |
| Native Excel PivotTables | **BLOCKED** | openpyxl cannot author a PivotTable cache. The workbook uses native Excel Tables, charts, conditional formatting and live formulas, and states this on its first sheet. |
| Excel formula recalculation | **UNVERIFIED** | openpyxl writes formulas but does not evaluate them, and no spreadsheet engine was available in this environment. The formulas are written to compare against SQL-derived values and show MATCH/REVIEW when opened. |
| Streamlit app under load | **PARTIAL** | Verified to start and serve HTTP 200 with a healthy `/_stcore/health`; not click-tested page by page. |
| Cause of the ageing backlog | **UNRESOLVED BY DESIGN** | Requires the City's maintenance work-order system, which is not in this dataset. This is why the recommendations say *investigate*. |
| `(Unclassified)` category growth | **NOT EXPLAINED** | Grew from 173 to 2,919 submissions year over year. Surfaced, not diagnosed. |
| 2018 bulk closure event | **NOT INVESTIGATED** | 4,515 cases submitted in 2018 were closed during 2026 with a median lifecycle of 2,753 days. Visible in `agg_closure_cohort_bias`. |

## 7. Files a reviewer should inspect

**Start here — the analytical substance:**

| File | Why |
|---|---|
| [`02_data_audit/data_quality_report.md`](02_data_audit/data_quality_report.md) | Checks DQ-03 and DQ-08 are the two findings that changed the design. |
| [`03_sql/09_trends.sql`](03_sql/09_trends.sql) | The coverage argument and the taxonomy-break detector — where getting the question right mattered most. |
| [`03_sql/01_clean_base.sql`](03_sql/01_clean_base.sql) | Grain, deduplication, derived metrics and privacy suppression in one place. |
| [`04_analysis/findings.md`](04_analysis/findings.md) | All twelve questions, including the negative findings. |
| [`06_executive_memo/executive_memo.md`](06_executive_memo/executive_memo.md) | Whether the recommendations are proportional to the evidence. |

**Then the machinery:**

| File | Why |
|---|---|
| [`src/claims.py`](src/claims.py) | Every written figure, recomputed from data. |
| [`scripts/verify_claims.py`](scripts/verify_claims.py) | How figures are prevented from drifting. |
| [`tests/test_privacy.py`](tests/test_privacy.py) | Privacy enforced by test, not by promise. |
| [`tests/test_pipeline.py`](tests/test_pipeline.py) | Definitions pinned against a fixture that contains every audit edge case. |
| [`07_methodology/methodology.md`](07_methodology/methodology.md) | Decisions and known weaknesses, §10. |

**Adversarial questions worth asking:**

1. Is the coverage argument in §6 of the methodology actually airtight?
2. Does the priority score's weighting change the top three? (It should not.)
3. Is the 2pp + 25% taxonomy-break threshold defensible, or tuned to the answer?
4. Does any recommendation assert more than the evidence supports?
5. Is the negative finding on geography genuinely negative, or under-powered?

---

*Claims registry: 69 figures, 117 document assertions.*
