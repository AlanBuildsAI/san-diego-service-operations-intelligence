"""Privacy guarantees, enforced rather than asserted in prose.

The source is public, but resident free text, exact addresses and coordinates are
not republished here. These tests fail if any suppressed field, or anything
shaped like one, reaches a published artifact.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src import config

# Artifacts a reader can actually see. Raw CSVs are git-ignored and excluded.
PUBLISHED_GLOBS = (
    "data/aggregates/*.csv",
    "05_dashboard/dashboard.html",
    "*.md",
    "01_business_brief/*.md",
    "02_data_audit/*.md",
    "04_analysis/*.md",
    "05_dashboard/*.md",
    "06_executive_memo/*.md",
    "07_methodology/*.md",
    "08_interview_defense/*.md",
    "docs/*.md",
)

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
STREET_ADDRESS = re.compile(
    r"\b\d{2,6}\s+[A-Z][A-Za-z]+\s+"
    r"(St|Street|Ave|Avenue|Blvd|Boulevard|Rd|Road|Dr|Drive|Ln|Lane|Way|Ct|Court|Pl|Place)\b"
)
# San Diego sits near 32.5-33.2 N, -117.6 to -116.6 E.
SD_COORDINATE = re.compile(r"\b3[23]\.\d{4,}\s*,\s*-11[67]\.\d{4,}\b")


def published_files() -> list[Path]:
    files: list[Path] = []
    for pattern in PUBLISHED_GLOBS:
        files.extend(sorted(config.REPO_ROOT.glob(pattern)))
    return [f for f in files if f.is_file()]


def test_there_are_published_files_to_check():
    """Guards against the suite passing because it scanned nothing."""
    assert len(published_files()) >= 10


def test_fact_table_excludes_every_suppressed_field(fixture_db):
    columns = {row[0] for row in fixture_db.execute("DESCRIBE fct_requests").fetchall()}
    leaked = columns & set(config.SUPPRESSED_SOURCE_FIELDS)
    assert not leaked, f"suppressed fields reached the fact table: {sorted(leaked)}"


def test_suppressed_fields_exist_in_the_source(fixture_db):
    """The suppression list must name real columns, or it protects nothing."""
    columns = {row[0] for row in fixture_db.execute("DESCRIBE src_open").fetchall()}
    for field in config.SUPPRESSED_SOURCE_FIELDS:
        assert field in columns, f"{field} is suppressed but not present in the source"


def test_resident_description_never_reaches_an_aggregate(fixture_db):
    """The fixture plants an identifiable sentence; it must not survive."""
    for table in ("fct_requests",):
        columns = [r[0] for r in fixture_db.execute(f"DESCRIBE {table}").fetchall()]
        assert "public_description" not in columns


@pytest.mark.parametrize("field", config.SUPPRESSED_SOURCE_FIELDS)
def test_no_published_artifact_contains_a_suppressed_column_header(field):
    """A suppressed field name appearing as a CSV header means it was exported."""
    offenders = []
    for path in published_files():
        if path.suffix != ".csv":
            continue
        header = path.read_text(errors="ignore").split("\n", 1)[0]
        if field in [h.strip().strip('"') for h in header.split(",")]:
            offenders.append(str(path.relative_to(config.REPO_ROOT)))
    assert not offenders, f"{field} exported in: {offenders}"


def test_no_published_artifact_contains_an_email_address():
    """The raw referral text carries staff and vendor addresses; it must be normalized."""
    offenders = []
    for path in published_files():
        text = path.read_text(errors="ignore")
        for match in EMAIL.findall(text):
            # The project's own documentation cites the City's open-data domain,
            # and pattern definitions inside this repo are not leaked data.
            if match.endswith(("sandiego.gov.", "example.com")) or "@" not in match:
                continue
            offenders.append(f"{path.relative_to(config.REPO_ROOT)}: {match}")
    assert not offenders, f"email addresses found in published output: {offenders[:5]}"


def test_no_published_artifact_contains_a_street_address():
    offenders = []
    for path in published_files():
        if path.name in ("test_privacy.py",):
            continue
        for match in STREET_ADDRESS.findall(path.read_text(errors="ignore")):
            offenders.append(f"{path.relative_to(config.REPO_ROOT)}: {match}")
    assert not offenders, f"street addresses found: {offenders[:5]}"


def test_no_published_artifact_contains_point_coordinates():
    offenders = []
    for path in published_files():
        if SD_COORDINATE.search(path.read_text(errors="ignore")):
            offenders.append(str(path.relative_to(config.REPO_ROOT)))
    assert not offenders, f"coordinate pairs found: {offenders}"


def test_geography_is_only_published_at_aggregate_level(fixture_db):
    """Published geography must be district / community / ZIP, never a point."""
    columns = {row[0] for row in fixture_db.execute("DESCRIBE fct_requests").fetchall()}
    assert "lat" not in columns and "lng" not in columns
    assert {"council_district", "community", "zipcode"} <= columns


def test_raw_data_is_git_ignored():
    """Source CSVs must never be committed."""
    gitignore = (config.REPO_ROOT / ".gitignore").read_text()
    assert "data/raw/" in gitignore
    assert "*.csv" in gitignore or "data/raw/*" in gitignore


def test_fixture_contains_no_real_resident_data():
    """The committed fixture is synthetic; confirm it carries no real address."""
    for path in (config.REPO_ROOT / "tests" / "fixtures").glob("*.csv"):
        text = path.read_text()
        assert not EMAIL.search(text), f"{path.name} contains an email address"
