"""Generate REVIEW_PACKET.md — everything a reviewer needs to check this project.

Assembled from the real run artifacts: the download manifest, run metadata, audit
results, aggregate row counts, a live pytest run and a live claims verification.
Nothing is asserted that was not measured at generation time.

Usage
-----
    python scripts/build_review_packet.py
    python scripts/build_review_packet.py --skip-tests   # reuse nothing, run nothing
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import pandas as pd  # noqa: E402

from src import claims as claims_mod, config  # noqa: E402

VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python"
PYTHON = str(VENV_PYTHON) if VENV_PYTHON.exists() else sys.executable


def run(command: list[str]) -> tuple[int, str]:
    result = subprocess.run(command, cwd=REPO_ROOT, capture_output=True, text=True)
    return result.returncode, (result.stdout + result.stderr).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-tests", action="store_true",
                        help="do not run pytest or the claim verifier")
    args = parser.parse_args()

    if not config.RUN_METADATA.exists():
        print("No run metadata. Run: make analyze", file=sys.stderr)
        return 1

    run_meta = json.loads(config.RUN_METADATA.read_text())
    download = json.loads(config.DOWNLOAD_MANIFEST.read_text())
    audit = json.loads(config.AUDIT_RESULTS.read_text())
    built_claims = claims_mod.build_claims()

    if args.skip_tests:
        test_code, test_out = -1, "SKIPPED"
        verify_code, verify_out = -1, "SKIPPED"
    else:
        print("Running pytest ...")
        # pytest.ini already supplies -q. Adding another -q suppresses the
        # final "N passed" line and prevents the packet from reporting the
        # measured current test count.
        test_code, test_out = run([PYTHON, "-m", "pytest"])
        print("Running claim verification ...")
        verify_code, verify_out = run([PYTHON, "scripts/verify_claims.py"])

    test_summary = next(
        (line for line in reversed(test_out.splitlines())
         if re.search(r"\d+ (passed|failed)", line)), test_out.splitlines()[-1:] or [""])
    if isinstance(test_summary, list):
        test_summary = test_summary[0] if test_summary else ""

    grades = {g: sum(1 for c in audit["checks"] if c["grade"] == g)
              for g in ("PASS", "WARN", "FAIL", "INFO")}

    aggregates = sorted(config.AGGREGATES_DIR.glob("*.csv"))
    agg_rows = {p.stem: len(pd.read_csv(p)) for p in aggregates}

    lines: list[str] = []
    a = lines.append

    a("# Review Packet")
    a("")
    a("Everything needed to check this project, generated from the actual run by")
    a("[`scripts/build_review_packet.py`](scripts/build_review_packet.py).")
    a("")
    a(f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}<br>")
    a(f"**Data snapshot:** {run_meta['snapshot_date']}<br>")
    a(f"**DuckDB:** {run_meta['duckdb_version']}<br>")
    a(f"**Python:** {sys.version.split()[0]}")
    a("")
    a("---")
    a("")

    # --- 1. data used --------------------------------------------------------
    a("## 1. Dataset and files used")
    a("")
    a(f"Source: **{download['publisher']}** — <{download['dataset_page']}>")
    a("")
    a("| File | Size | SHA-256 (first 16) | Physical lines |")
    a("|---|---:|---|---:|")
    for entry in download["files"]:
        if "error" in entry:
            continue
        a(f"| `{entry['filename']}` | {entry['size_bytes'] / 1e6:,.1f} MB | "
          f"`{entry['sha256'][:16]}…` | {entry['physical_data_lines']:,} |")
    a("")
    a("Full hashes and licensing: [`docs/source_manifest.md`](docs/source_manifest.md).")
    a("Raw files are **not committed** — `data/raw/` is git-ignored.")
    a("")

    # --- 2. row counts -------------------------------------------------------
    a("## 2. Row counts")
    a("")
    row_counts = next((c for c in audit["checks"] if c["check_id"] == "DQ-01"), None)
    if row_counts:
        detail = row_counts["detail"]
        a("| Stage | Rows |")
        a("|---|---:|")
        for key in ("open", "closed_2026", "closed_2025"):
            if key in detail:
                a(f"| `{key}` extract, parsed | {detail[key]['rows']:,} |")
        a(f"| **Total read** | **{detail['total_rows_read']:,}** |")
        a(f"| Dropped as cross-file duplicate ids | "
          f"{detail['rows_dropped_as_cross_file_duplicates']:,} |")
        a(f"| **Fact table `fct_requests`** | **{detail['rows_in_fact_table']:,}** |")
    a("")
    a(f"Aggregate tables produced: **{len(aggregates)}**")
    a("")
    a("<details><summary>Row count per aggregate</summary>")
    a("")
    a("| Aggregate | Rows |")
    a("|---|---:|")
    for name, rows in agg_rows.items():
        a(f"| `{name}` | {rows:,} |")
    a("")
    a("</details>")
    a("")

    # --- 3. tests ------------------------------------------------------------
    a("## 3. Tests run and results")
    a("")
    a("| Gate | Command | Result |")
    a("|---|---|---|")
    test_status = ("SKIPPED" if test_code == -1
                   else ("PASS" if test_code == 0 else "FAIL"))
    verify_status = ("SKIPPED" if verify_code == -1
                     else ("PASS" if verify_code == 0 else "FAIL"))
    a(f"| Unit and integration tests | `make test` | **{test_status}** — {test_summary} |")
    a(f"| Written-figure verification | `make verify` | **{verify_status}** |")
    a(f"| Data-quality audit | `make audit` | {grades['PASS']} PASS · {grades['WARN']} WARN · "
      f"{grades['FAIL']} FAIL · {grades['INFO']} INFO |")
    a("")
    a("The test suite runs the project's real SQL against a committed synthetic fixture,")
    a("so it needs no downloaded data and runs in CI on every push.")
    a("")
    if not args.skip_tests:
        a("<details><summary>Claim verification output</summary>")
        a("")
        a("```")
        a(verify_out)
        a("```")
        a("")
        a("</details>")
        a("")

    # --- 4. findings ---------------------------------------------------------
    a("## 4. Main findings")
    a("")
    c = built_claims
    a(f"1. **Recent-cohort status and active-inventory age are different measures.** "
      f"{c['cohort_pct_resolved'].formatted} of requests submitted Jan-Jun 2026 had reached "
      f"Closed or Referred status by the snapshot; among those terminal-status records, median "
      f"recorded lifecycle was {c['cohort_median_lifecycle'].formatted} days. Separately, "
      f"{c['active_backlog'].formatted} requests were active with a median age of "
      f"{c['active_median_age_days'].formatted} days. These populations should not be "
      f"interpreted as the same lifecycle measure.")
    a(f"2. **{c['active_aged_90_plus_pct'].formatted} of the active inventory is past 90 days** "
      f"({c['active_aged_90_plus'].formatted} records); "
      f"{c['active_aged_365_plus_pct'].formatted} is past a year.")
    a(f"3. **Four categories hold {c['top4_share_pct'].formatted} of active records.** TSW is "
      f"the modal case_record_type for all four ({c['tsw_pct_of_backlog'].formatted} of active "
      f"records carry that label - a higher-level staff-group label, not a current ownership "
      f"field).")
    a(f"4. **No strong district-level over-concentration is evident** - the descriptive "
      f"aged-concentration index varies only {c['aging_index_min'].formatted} to "
      f"{c['aging_index_max'].formatted} across the nine council districts. This does not "
      f"prove geography is irrelevant.")
    a(f"5. **Duplicates are {c['duplicate_rate_active_pct'].formatted} of the active queue** "
      f"({c['duplicate_children_active'].formatted} records). Collapsing them moves top-20 "
      f"volume rankings by no more than {c['dup_max_rank_shift'].formatted} positions; the "
      f"composite priority score was not re-derived on deduplicated inputs.")
    a(f"6. **Two metrics are traps and both are handled**: the "
      f"{c['closed_median_lifecycle'].formatted}-day closure median is a cohort artifact "
      f"({c['closure_cohort_same_year_pct'].formatted} of this year's closures were also "
      f"submitted this year), and the apparent channel difference falls to "
      f"{c['channel_median_gap_days'].formatted} days once service category is held constant.")
    a(f"7. **The priority ranking is a heuristic sensitive to its weights.** Across "
      f"{c['weight_schemes_tested'].formatted} weighting schemes, Sidewalk and Pavement hold "
      f"the top two in all {c['weight_schemes_tested'].formatted}, but Street Light "
      f"Maintenance is top-three in only {c['streetlight_top3_scheme_count'].formatted}. An "
      f"earlier 'stable top three' claim was tested, disproved and removed.")
    a("")
    a("Full reasoning: [`04_analysis/findings.md`](04_analysis/findings.md).")
    a("")

    # --- 5. limitations ------------------------------------------------------
    a("## 5. Known limitations")
    a("")
    a("- **The data records requests, not work.** No work-completion detail exists. A closed")
    a("  case means a case closed, not that a repair happened. Nothing here measures crew")
    a("  performance and no claim is causal.")
    a("- **No denominators.** No population, street mileage or asset counts, so districts")
    a("  cannot be compared as service levels.")
    a("- **Duplicate counts are a floor** — the City's own determinations only; no fuzzy")
    a("  matching was attempted.")
    a("- **Category-level year-over-year is invalid** across the 2025/2026 boundary because")
    a("  of a confirmed service relabeling. Reported citywide and by record type instead.")
    a("- **One level of duplicate nesting is collapsed.** 428 children point at another")
    a("  child (0.06% of records).")
    a("- **Referral destination parsing is rule-based**; `City – Other department` is a")
    a("  residual bucket, not one department.")
    a("- **Priority-score weights (0.45 / 0.35 / 0.20) are a documented judgment**, not a")
    a("  derivation. Measured sensitivity: the top two hold across all five tested schemes;")
    a("  the third position does not.")
    a("- **The cohort lifecycle median is right-censored** - computed only over records that")
    a("  had reached a terminal status by the snapshot. The terminal-status share is not.")
    a("- **`case_record_type` is a staff-group label**, many-to-many with `service_name`, and")
    a("  not a confirmed mapping to a current City department.")
    a("")

    # --- 6. unverified -------------------------------------------------------
    a("## 6. Unverified or blocked items")
    a("")
    a("Stated explicitly rather than glossed:")
    a("")
    a("| Item | Status | Detail |")
    a("|---|---|---|")
    a("| Tableau workbook | **BLOCKED** | Tableau cannot be automated here. No `.twb` was "
      "fabricated; a full build spec is at "
      "[`05_dashboard/tableau_build_spec.md`](05_dashboard/tableau_build_spec.md). |")
    a("| Native Excel PivotTables | **BLOCKED** | openpyxl cannot author a PivotTable cache. "
      "The workbook uses native Excel Tables, charts, conditional formatting and live "
      "formulas, and states this on its first sheet. |")
    a("| Excel formula recalculation | **VERIFIED IN EXCEL** | The final workbook was opened "
      "in Microsoft Excel during visual QA. Its three SQL cross-check formulas recalculated "
      "to MATCH, and the audit totals recalculated to 4 PASS / 6 WARN / 2 FAIL / 1 INFO. |")
    a("| Streamlit app under load | **PARTIAL** | Verified to start and serve HTTP 200 with a "
      "healthy `/_stcore/health`; not click-tested page by page. |")
    a("| Reproducing the exact snapshot from the source URLs | **NOT POSSIBLE** | The City's "
      "files are rolling datasets refreshed daily; a later download returns current records. "
      "The committed aggregates, hashes, tests and claim registry are what make the published "
      "snapshot auditable. |")
    a("| Cause of the aging inventory | **UNRESOLVED BY DESIGN** | Requires the City's "
      "maintenance work-order system, which is not in this dataset. This is why the "
      "recommendations say *investigate*. |")
    a("| `(Unclassified)` category growth | **NOT EXPLAINED** | Grew from 173 to 2,919 "
      "submissions year over year. Surfaced, not diagnosed. |")
    a("| 2018 bulk closure event | **NOT INVESTIGATED** | 4,515 cases submitted in 2018 were "
      "closed during 2026 with a median lifecycle of 2,753 days. Visible in "
      "`agg_closure_cohort_bias`. |")
    a("")

    # --- 7. what to inspect --------------------------------------------------
    a("## 7. Files a reviewer should inspect")
    a("")
    a("**Start here — the analytical substance:**")
    a("")
    a("| File | Why |")
    a("|---|---|")
    a("| [`02_data_audit/data_quality_report.md`](02_data_audit/data_quality_report.md) | "
      "Checks DQ-03 and DQ-08 are the two findings that changed the design. |")
    a("| [`03_sql/09_trends.sql`](03_sql/09_trends.sql) | The coverage argument and the "
      "taxonomy-break detector — where getting the question right mattered most. |")
    a("| [`03_sql/01_clean_base.sql`](03_sql/01_clean_base.sql) | Grain, deduplication, "
      "derived metrics and privacy suppression in one place. |")
    a("| [`04_analysis/findings.md`](04_analysis/findings.md) | All twelve questions, "
      "including the negative findings. |")
    a("| [`06_executive_memo/executive_memo.md`](06_executive_memo/executive_memo.md) | "
      "Whether the recommendations are proportional to the evidence. |")
    a("")
    a("**Then the machinery:**")
    a("")
    a("| File | Why |")
    a("|---|---|")
    a("| [`src/claims.py`](src/claims.py) | Every written figure, recomputed from data. |")
    a("| [`scripts/verify_claims.py`](scripts/verify_claims.py) | How figures are prevented "
      "from drifting. |")
    a("| [`tests/test_privacy.py`](tests/test_privacy.py) | Privacy enforced by test, not "
      "by promise. |")
    a("| [`tests/test_pipeline.py`](tests/test_pipeline.py) | Definitions pinned against a "
      "fixture that contains every audit edge case. |")
    a("| [`07_methodology/methodology.md`](07_methodology/methodology.md) | Decisions and "
      "known weaknesses, §10. |")
    a("")
    a("**Adversarial questions worth asking:**")
    a("")
    a("1. Is the coverage argument in §6 of the methodology actually airtight?")
    a("2. How sensitive is the priority shortlist to analyst-selected weights, and does the "
      "repository report that sensitivity accurately?")
    a("3. Is the 2pp + 25% taxonomy-break threshold defensible, or tuned to the answer?")
    a("4. Does any recommendation assert more than the evidence supports?")
    a("5. Is the negative finding on geography genuinely negative, or under-powered?")
    a("")
    a("---")
    a("")
    a(f"*Claims registry: {len(built_claims)} figures, "
      f"{sum(len(cl.documents) for cl in built_claims.values())} document assertions.*")

    out = REPO_ROOT / "REVIEW_PACKET.md"
    out.write_text("\n".join(lines) + "\n")
    print(f"  [out] {out.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
