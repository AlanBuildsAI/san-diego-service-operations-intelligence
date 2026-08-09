"""Repository-level guarantees: SQL inventory, chart helpers, claims, and links."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src import charts, config, pipeline

EXPECTED_SQL = (
    "00_sources.sql", "01_clean_base.sql", "02_executive_kpis.sql",
    "03_backlog_aging.sql", "04_service_analysis.sql", "05_geography_analysis.sql",
    "06_duplicates.sql", "07_referrals.sql", "08_channel_analysis.sql",
    "09_trends.sql", "10_priority_table.sql",
)


# --- SQL layer ---------------------------------------------------------------
@pytest.mark.parametrize("name", EXPECTED_SQL)
def test_every_expected_sql_file_exists_and_is_documented(name):
    path = config.SQL_DIR / name
    assert path.exists(), f"missing {name}"
    head = path.read_text()[:1200]
    assert "-- Purpose" in head, f"{name} has no Purpose header"


def test_pipeline_runs_every_sql_file_in_the_directory():
    """A new .sql file must be wired into the runner, not left orphaned."""
    on_disk = {p.name for p in config.SQL_DIR.glob("*.sql")}
    wired = set(pipeline.BASE_SQL) | set(pipeline.ANALYSIS_SQL)
    assert on_disk == wired, f"unwired SQL files: {sorted(on_disk - wired)}"


def test_no_sql_file_selects_a_suppressed_field_into_an_aggregate():
    """Suppressed fields may only appear in 01_clean_base.sql, where they are dropped."""
    for path in config.SQL_DIR.glob("*.sql"):
        if path.name in ("00_sources.sql", "01_clean_base.sql"):
            continue
        text = path.read_text()
        for field in ("public_description", "street_address", "lat", "lng"):
            assert not re.search(rf"\b{field}\b", text), f"{path.name} references {field}"


# --- chart helpers -----------------------------------------------------------
@pytest.mark.parametrize("value,expected_last", [
    (26388, 25000), (100, 100), (8, 8), (1.0, 1.0), (378675, 350000),
])
def test_nice_ticks_are_round_and_within_range(value, expected_last):
    ticks = charts.nice_ticks(value)
    assert ticks[-1] <= value * 1.0001
    assert ticks[-1] == pytest.approx(expected_last, rel=0.35)
    assert all(b > a for a, b in zip(ticks, ticks[1:])), "ticks must ascend"


def test_nice_ticks_handles_zero():
    assert charts.nice_ticks(0) == [0.0]


def test_labels_are_truncated_but_the_full_value_is_kept():
    clipped = charts._clip("Development Services - Code Enforcement", 20)
    assert len(clipped) == 20 and clipped.endswith("…")
    assert charts._clip("Pothole", 20) == "Pothole"


def test_svg_escapes_markup_in_labels():
    svg = charts.horizontal_bars(["<script>x</script>"], [1.0])
    assert "<script>" not in svg
    assert "&lt;script&gt;" in svg


def test_charts_emit_valid_single_root_svg():
    svg = charts.vertical_bars(["a", "b"], [1.0, 2.0],
                               ["var(--series-1)", "var(--series-2)"])
    assert svg.startswith("<svg") and svg.endswith("</svg>")
    assert svg.count("<svg") == 1


def test_charts_use_theme_tokens_not_hard_coded_colors():
    """Hard-coded hex would break dark mode."""
    svg = charts.dumbbell(["a"], [1.0], [10.0])
    assert "var(--series-" in svg
    assert not re.search(r"#[0-9a-fA-F]{6}", svg)


# --- documentation links -----------------------------------------------------
MARKDOWN_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


def markdown_files() -> list[Path]:
    return [p for p in config.REPO_ROOT.rglob("*.md")
            if ".venv" not in p.parts and ".git" not in p.parts]


def test_every_relative_markdown_link_resolves():
    broken: list[str] = []
    for path in markdown_files():
        for target in MARKDOWN_LINK.findall(path.read_text()):
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            resolved = (path.parent / target.split("#")[0]).resolve()
            if not resolved.exists():
                broken.append(f"{path.relative_to(config.REPO_ROOT)} -> {target}")
    assert not broken, "broken relative links:\n" + "\n".join(broken)


RECRUITER_FACING = (
    "README.md",
    "04_analysis/findings.md",
    "06_executive_memo/executive_memo.md",
    "05_dashboard/dashboard.html",
)


def normalized_prose(relative_path: str) -> str:
    """Document text with wrapping and emphasis removed.

    These assertions are about content, not typography — a phrase broken across a
    line or wrapped in bold is still present for the reader.
    """
    text = (config.REPO_ROOT / relative_path).read_text()
    text = re.sub(r"[*_`>]", " ", text)
    return re.sub(r"\s+", " ", text).lower()


@pytest.mark.parametrize("relative_path", RECRUITER_FACING)
def test_recruiter_facing_artifacts_carry_the_data_boundary(relative_path):
    """A reader must not be able to reach a finding without the boundary note."""
    assert "not verified maintenance completion" in normalized_prose(relative_path), \
        relative_path


@pytest.mark.parametrize("relative_path", RECRUITER_FACING)
def test_recruiter_facing_artifacts_disclose_portfolio_status(relative_path):
    """This work was not commissioned by the City; every public surface says so."""
    prose = normalized_prose(relative_path)
    assert "independent portfolio case study" in prose, relative_path
    assert "not commissioned by" in prose, relative_path


def test_no_artifact_claims_a_city_engagement():
    """Guard against wording that would imply real City employment or contracting."""
    banned = [
        r"\bcommissioned by the city\b(?!,| ,)",
        r"\bon behalf of the city\b",
        r"\bmy client\b",
        r"\bwhile (?:working|employed) (?:at|for) the city\b",
        r"\bcontracted (?:by|to) the city\b",
    ]
    offenders = []
    for path in markdown_files():
        text = path.read_text()
        for pattern in banned:
            for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                context = text[max(0, match.start() - 60):match.end() + 20]
                if "not commissioned by" in context.lower():
                    continue
                offenders.append(f"{path.relative_to(config.REPO_ROOT)}: {match.group(0)!r}")
    assert not offenders, f"implied City engagement: {offenders}"


def test_no_document_claims_an_unsupported_outcome():
    """Guard against causal or completion language creeping into the findings.

    The words are legitimate in some contexts (quoting the City, describing a
    code fix), so only unqualified operational claims are rejected.
    """
    banned = [
        r"\bwe (?:fixed|repaired|resolved) \d",
        r"\bcaused by the (?:backlog|duplicate|channel)",
        r"\bsaved \$?\d",
        r"\breduced the backlog by\b",
        r"\bimproved (?:response|repair) times?\b",
        r"\bproves that\b",
    ]
    offenders: list[str] = []
    for path in markdown_files():
        text = path.read_text()
        for pattern in banned:
            for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                offenders.append(
                    f"{path.relative_to(config.REPO_ROOT)}: {match.group(0)!r}")
    assert not offenders, f"unsupported claims: {offenders}"


# --- claims registry ---------------------------------------------------------
@pytest.mark.needs_real_data
def test_claims_build_from_real_aggregates(has_real_outputs):
    if not has_real_outputs:
        pytest.skip("no real pipeline run present")
    from src import claims as claims_mod
    built = claims_mod.build_claims()
    assert len(built) >= 40
    for key, claim in built.items():
        assert claim.formatted, f"{key} formatted empty"
        assert claim.source, f"{key} has no stated source"
