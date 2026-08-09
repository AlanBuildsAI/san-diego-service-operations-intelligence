"""Shared pytest fixtures.

The `fixture_db` fixture runs the project's real SQL against the committed
synthetic CSVs in ``tests/fixtures/``. That means the tests exercise the same
statements the analysis uses — not a reimplementation of them — and can run in CI
without downloading ~245 MB of source data.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import duckdb
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src import config, pipeline  # noqa: E402

FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures"
FIXTURE_FILES = (
    "get_it_done_requests_open_datasd.csv",
    "get_it_done_requests_closed_2026_datasd.csv",
    "get_it_done_requests_closed_2025_datasd.csv",
    "get_it_done_requests_dictionary_datasd.csv",
)
FIXTURE_SNAPSHOT = "2026-08-09"


@pytest.fixture(scope="session")
def fixture_db(tmp_path_factory) -> duckdb.DuckDBPyConnection:
    """A DuckDB connection with the project SQL applied to the fixture data."""
    workdir = tmp_path_factory.mktemp("gid_fixture")
    raw = workdir / "data" / "raw"
    raw.mkdir(parents=True)
    for name in FIXTURE_FILES:
        shutil.copy(FIXTURE_DIR / name, raw / name)

    # The SQL files reference data/raw/... relative to the process working
    # directory, so the fixture must actually chdir. Reading the SQL files
    # themselves uses absolute paths, so they still resolve.
    sql = [(config.SQL_DIR / name).read_text()
           for name in pipeline.BASE_SQL + pipeline.ANALYSIS_SQL]

    previous = os.getcwd()
    os.chdir(workdir)
    try:
        con = duckdb.connect(str(workdir / "gid_test.duckdb"))
        for statement in sql:
            con.execute(statement)
        yield con
        con.close()
    finally:
        os.chdir(previous)


@pytest.fixture(scope="session")
def has_real_outputs() -> bool:
    """True when a full pipeline run against real data is present."""
    return (config.AGGREGATES_DIR / "agg_executive_kpis.csv").exists()
