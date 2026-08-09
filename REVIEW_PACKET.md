# Review Packet

Everything needed to check this project, generated from the actual run by
[`scripts/build_review_packet.py`](scripts/build_review_packet.py).

**Generated:** 2026-08-09 20:51 UTC  
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

Aggregate tables produced: **34**

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
| `agg_priority_weight_sensitivity` | 25 |
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
| Unit and integration tests | `make test` | **PASS** — ....................                                                     [100%] |
| Written-figure verification | `make verify` | **PASS** |
| Data-quality audit | `make audit` | 4 PASS · 6 WARN · 2 FAIL · 1 INFO |

The test suite runs the project's real SQL against a committed synthetic fixture,
so it needs no downloaded data and runs in CI on every push.

<details><summary>Claim verification output</summary>

```
Check 1 — registry: every declared claim appears in its documents
  PASS — 120 assertions across 75 claims

Check 2 — traceability: every number in prose exists in the aggregates
  PASS — every number traced to a value in data/aggregates/

RESULT: PASS
```

</details>

## 4. Main findings

1. **Recent submissions settle quickly; the standing inventory is old.** 91.2% of requests submitted Jan-Jun 2026 had reached a terminal status by the snapshot (median 2 days among those) - yet 81,359 requests are active with a median age of 381 days.
2. **76.1% of the active inventory is past 90 days** (61,922 records); 51.0% is past a year.
3. **Four categories hold 54.2% of active records.** TSW is the modal case_record_type for all four (64.0% of active records carry that label - a staff-group label, not a confirmed department owner).
4. **No strong district-level over-concentration is evident** - the descriptive aged-concentration index varies only 0.826 to 1.085 across the nine council districts. This does not prove geography is irrelevant.
5. **Duplicates are 27.0% of the active queue** (21,971 records). Collapsing them moves top-20 volume rankings by no more than 2 positions; the composite priority score was not re-derived on deduplicated inputs.
6. **Two metrics are traps and both are handled**: the 3-day closure median is a cohort artifact (88.1% of this year's closures were also submitted this year), and the apparent channel difference falls to 2 days once service category is held constant.
7. **The priority ranking is a heuristic sensitive to its weights.** Across 5 weighting schemes, Sidewalk and Pavement hold the top two in all 5, but Street Light Maintenance is top-three in only 4. An earlier 'stable top three' claim was tested, disproved and removed.

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
  of a confirmed service relabeling. Reported citywide and by record type instead.
- **One level of duplicate nesting is collapsed.** 428 children point at another
  child (0.06% of records).
- **Referral destination parsing is rule-based**; `City – Other department` is a
  residual bucket, not one department.
- **Priority-score weights (0.45 / 0.35 / 0.20) are a documented judgment**, not a
  derivation. Measured sensitivity: the top two hold across all five tested schemes;
  the third position does not.
- **The cohort lifecycle median is right-censored** - computed only over records that
  had reached a terminal status by the snapshot. The terminal-status share is not.
- **`case_record_type` is a staff-group label**, many-to-many with `service_name`, and
  not a confirmed mapping to a current City department.

## 6. Unverified or blocked items

Stated explicitly rather than glossed:

| Item | Status | Detail |
|---|---|---|
| Tableau workbook | **BLOCKED** | Tableau cannot be automated here. No `.twb` was fabricated; a full build spec is at [`05_dashboard/tableau_build_spec.md`](05_dashboard/tableau_build_spec.md). |
| Native Excel PivotTables | **BLOCKED** | openpyxl cannot author a PivotTable cache. The workbook uses native Excel Tables, charts, conditional formatting and live formulas, and states this on its first sheet. |
| Excel formula recalculation | **UNVERIFIED** | openpyxl writes formulas but does not evaluate them, and no spreadsheet engine was available in this environment. The formulas are written to compare against SQL-derived values and show MATCH/REVIEW when opened. |
| Streamlit app under load | **PARTIAL** | Verified to start and serve HTTP 200 with a healthy `/_stcore/health`; not click-tested page by page. |
| Reproducing the exact snapshot from the source URLs | **NOT POSSIBLE** | The City's files are rolling datasets refreshed daily; a later download returns current records. The committed aggregates, hashes, tests and claim registry are what make the published snapshot auditable. |
| Cause of the aging inventory | **UNRESOLVED BY DESIGN** | Requires the City's maintenance work-order system, which is not in this dataset. This is why the recommendations say *investigate*. |
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

*Claims registry: 75 figures, 120 document assertions.*
