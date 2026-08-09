"""Verify every numeric claim in the written documents against the generated data.

Two independent checks:

**1. Registry check.** Each claim in ``src/claims.py`` is recomputed from
``data/aggregates/`` and its formatted string must appear verbatim in the
documents that are supposed to carry it. This catches a figure that drifted after
a data refresh.

**2. Traceability sweep.** Every number-like token in README.md, the executive
memo and the findings write-up is extracted and matched against the full set of
values present in the aggregates (at several roundings). Anything that cannot be
traced is reported for review. This catches a number that was never in the data
at all — a typo, or a figure written from memory.

The sweep is deliberately noisy rather than silent: it lists untraceable tokens
so a human can confirm each one is a year, a threshold, a weight or a section
number. Only the registry check can fail the build.

Usage
-----
    python scripts/verify_claims.py            # both checks
    python scripts/verify_claims.py --strict   # sweep findings also fail the run
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import pandas as pd  # noqa: E402

from src import claims as claims_mod, config  # noqa: E402

DOCUMENTS = ("README.md", "06_executive_memo/executive_memo.md", "04_analysis/findings.md")

NUMBER_TOKEN = re.compile(r"\b\d[\d,]*\.?\d*%?")
ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")

# Values that legitimately appear in prose without coming from an aggregate:
# dates, thresholds that define metrics, scoring weights, structural counts.
ALLOWED_LITERALS = {
    # calendar and scope
    "2016", "2017", "2018", "2019", "2020", "2021", "2022", "2023", "2024",
    "2025", "2026", "2026-08-09", "1", "2", "3", "4", "5", "6", "7", "8", "9",
    "10", "11", "12", "15", "20", "25", "30", "40", "50", "60", "90", "100",
    # metric thresholds and bucket edges
    "0-7", "8-30", "31-60", "61-90", "91-180", "181-365", "366-730", "731",
    "180", "181", "250", "300", "365", "366", "500", "730", "731",
    # scoring weights and statistical constants
    "0.45", "0.35", "0.20", "0.90", "1.0", "0.9",
    # tool versions quoted in setup instructions
    "3.11", "3.13",
}


def load_documents() -> dict[str, str]:
    documents = {}
    for name in DOCUMENTS:
        path = REPO_ROOT / name
        if not path.exists():
            raise SystemExit(f"Missing document: {name}. Nothing to verify.")
        documents[name] = path.read_text()
    return documents


# -----------------------------------------------------------------------------
# Check 1: registry
# -----------------------------------------------------------------------------
def check_registry(documents: dict[str, str]) -> tuple[int, int, list[str]]:
    built = claims_mod.build_claims()
    checked = 0
    failures: list[str] = []

    for key, claim in built.items():
        for document in claim.documents:
            checked += 1
            if claim.formatted not in documents.get(document, ""):
                failures.append(
                    f"  {document}: claim '{key}' expects {claim.formatted!r} "
                    f"({claim.description}; source: {claim.source}) — not found")
    return len(built), checked, failures


# -----------------------------------------------------------------------------
# Check 2: traceability sweep
# -----------------------------------------------------------------------------
def aggregate_value_index() -> set[str]:
    """Every numeric value in every aggregate, in the formats prose might use."""
    index: set[str] = set()

    def add(value: float) -> None:
        if pd.isna(value):
            return
        # Prose writes a negative change as "-9.7%", and the token scanner reads
        # the sign as punctuation, so the magnitude is indexed as well.
        for value in {value, abs(value)}:
            _add_formats(value)

    def _add_formats(value: float) -> None:
        for text in (
            f"{value:,.0f}", f"{value:.0f}", f"{value:,.1f}", f"{value:.1f}",
            f"{value:,.2f}", f"{value:.2f}", f"{value:.3f}",
            f"{value:.1f}%", f"{value:.0f}%", f"{value:.2f}%",
        ):
            index.add(text)
            index.add(text.replace(",", ""))

    for path in sorted(config.AGGREGATES_DIR.glob("*.csv")):
        frame = pd.read_csv(path)
        for column in frame.columns:
            series = pd.to_numeric(frame[column], errors="coerce").dropna()
            for value in series.unique():
                add(float(value))
                # Sums and complements are frequently quoted (e.g. "top four hold
                # 54.2%"), so admit simple aggregates of each numeric column.
        numeric = frame.select_dtypes("number")
        for column in numeric.columns:
            add(float(numeric[column].sum()))
            add(float(numeric[column].max()))
            add(float(numeric[column].min()))

    # The audit report quotes measured values that live in audit_results.json
    # rather than in an aggregate CSV (row counts, conflict lists, the Parking
    # crossover). Those are generated numbers too, so they belong in the index.
    if config.AUDIT_RESULTS.exists():
        def walk(node) -> None:
            if isinstance(node, dict):
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for value in node:
                    walk(value)
            elif isinstance(node, (int, float)) and not isinstance(node, bool):
                add(float(node))
        walk(json.loads(config.AUDIT_RESULTS.read_text()))

    for claim in claims_mod.build_claims().values():
        index.add(claim.formatted)
        index.add(claim.formatted.replace(",", ""))
    return index


def check_traceability(documents: dict[str, str]) -> dict[str, list[str]]:
    index = aggregate_value_index()
    untraced: dict[str, list[str]] = {}

    for name, text in documents.items():
        # Skip fenced code blocks and link targets: they carry paths, not claims.
        body = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
        body = re.sub(r"\]\([^)]*\)", "]()", body)
        body = ISO_DATE.sub(" ", body)          # dates are not claims
        body = re.sub(r"`[^`]*`", " ", body)    # inline code: file paths, columns
        found: list[str] = []
        for token in NUMBER_TOKEN.findall(body):
            token = token.rstrip(".")
            if token in ALLOWED_LITERALS or token.replace(",", "") in ALLOWED_LITERALS:
                continue
            if token in index or token.replace(",", "") in index:
                continue
            found.append(token)
        if found:
            # Preserve order, drop repeats.
            untraced[name] = list(dict.fromkeys(found))
    return untraced


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true",
                        help="treat untraceable tokens as failures too")
    args = parser.parse_args(argv)

    if not (config.AGGREGATES_DIR / "agg_executive_kpis.csv").exists():
        print("Aggregates not found. Run: make analyze", file=sys.stderr)
        return 1

    documents = load_documents()

    print("Check 1 — registry: every declared claim appears in its documents")
    total, checked, failures = check_registry(documents)
    if failures:
        print(f"  FAIL — {len(failures)} of {checked} assertions failed\n")
        print("\n".join(failures))
    else:
        print(f"  PASS — {checked} assertions across {total} claims\n")

    print("Check 2 — traceability: every number in prose exists in the aggregates")
    untraced = check_traceability(documents)
    if untraced:
        count = sum(len(v) for v in untraced.values())
        print(f"  REVIEW — {count} token(s) not traced to an aggregate value:")
        for name, tokens in untraced.items():
            print(f"    {name}: {', '.join(tokens)}")
    else:
        print("  PASS — every number traced to a value in data/aggregates/")

    print()
    if failures:
        print("RESULT: FAIL (registry mismatch)")
        return 1
    if untraced and args.strict:
        print("RESULT: FAIL (untraced tokens, --strict)")
        return 1
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
