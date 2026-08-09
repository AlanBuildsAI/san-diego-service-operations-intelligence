"""Execute the SQL layer against DuckDB and export every aggregate.

The SQL files in ``03_sql/`` are the analysis. This module is only a runner: it
opens the DuckDB database, executes each file in order, exports every table
named ``agg_*`` to ``data/aggregates/`` as CSV, and writes run metadata.

Keeping the logic in .sql files means the same statements can be run by hand:

    duckdb data/processed/gid.duckdb -c ".read 03_sql/00_sources.sql"

Usage
-----
    python -m src.pipeline            # build base + run all analysis SQL
    python -m src.pipeline --base     # base tables only
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import duckdb

try:  # allow both `python -m src.pipeline` and `python src/pipeline.py`
    from src import config
except ImportError:  # pragma: no cover
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from src import config

BASE_SQL = ("00_sources.sql", "01_clean_base.sql")
ANALYSIS_SQL = (
    "02_executive_kpis.sql",
    "03_backlog_aging.sql",
    "04_service_analysis.sql",
    "05_geography_analysis.sql",
    "06_duplicates.sql",
    "07_referrals.sql",
    "08_channel_analysis.sql",
    "09_trends.sql",
    "10_priority_table.sql",
)


def connect(read_only: bool = False) -> duckdb.DuckDBPyConnection:
    """Open the project database, with the process working directory at the repo root.

    The SQL files reference ``data/raw/...`` as relative paths so that they can be
    run by hand in the DuckDB CLI. DuckDB resolves those against the *process*
    working directory — ``SET file_search_path`` does not cover ``read_csv``
    arguments — so the directory is changed here rather than assumed. Without
    this, running the pipeline from a subdirectory silently reads nothing, or
    worse, reads a different copy of the data.
    """
    config.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    os.chdir(config.REPO_ROOT)
    return duckdb.connect(str(config.DUCKDB_PATH), read_only=read_only)


def _run_file(con: duckdb.DuckDBPyConnection, name: str) -> list[str]:
    """Execute one SQL file; return the agg_* tables it left behind."""
    path = config.SQL_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"SQL file missing: {path}")

    before = _agg_tables(con)
    con.execute(path.read_text())
    after = _agg_tables(con)
    return sorted(after - before)


def _agg_tables(con: duckdb.DuckDBPyConnection) -> set[str]:
    rows = con.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'main' AND table_name LIKE 'agg_%'"
    ).fetchall()
    return {r[0] for r in rows}


def _require_raw_files() -> None:
    missing = [
        meta["filename"]
        for meta in config.SOURCE_EXTRACTS.values()
        if not (config.RAW_DIR / meta["filename"]).exists()
    ]
    if not config.DICTIONARY_FILE.exists():
        missing.append(config.DICTIONARY_FILE.name)
    if missing:
        raise SystemExit(
            "Source files are missing from data/raw/:\n  "
            + "\n  ".join(missing)
            + "\n\nRun:  make download   (or: python scripts/download_data.py)"
        )


def build_base(con: duckdb.DuckDBPyConnection) -> dict:
    """Create ref_snapshot and fct_requests, and export the privacy-safe fact."""
    for name in BASE_SQL:
        print(f"  [sql] {name}")
        _run_file(con, name)

    snapshot = con.execute("SELECT * FROM ref_snapshot").fetchone()
    n_rows = con.execute("SELECT COUNT(*) FROM fct_requests").fetchone()[0]

    columns = {r[0] for r in con.execute("DESCRIBE fct_requests").fetchall()}
    leaked = sorted(columns & set(config.SUPPRESSED_SOURCE_FIELDS))
    if leaked:
        raise SystemExit(
            "Refusing to export: suppressed source fields reached the fact table: "
            + ", ".join(leaked)
        )

    config.FACT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    con.execute(
        f"COPY fct_requests TO '{config.FACT_PARQUET}' (FORMAT PARQUET, COMPRESSION ZSTD)"
    )
    print(f"  [out] {config.FACT_PARQUET.relative_to(config.REPO_ROOT)} "
          f"({config.FACT_PARQUET.stat().st_size / 1e6:,.1f} MB, {n_rows:,} rows)")

    return {
        "snapshot_date": str(snapshot[0]),
        "snapshot_support_records": snapshot[1],
        "snapshot_support_pct": snapshot[3],
        "fact_rows": n_rows,
        "fact_columns": sorted(columns),
    }


def run_analysis(con: duckdb.DuckDBPyConnection) -> dict[str, list[str]]:
    """Execute the analysis SQL files and export their aggregates."""
    config.AGGREGATES_DIR.mkdir(parents=True, exist_ok=True)
    produced: dict[str, list[str]] = {}

    for name in ANALYSIS_SQL:
        tables = _run_file(con, name)
        produced[name] = tables
        for table in tables:
            out = config.AGGREGATES_DIR / f"{table}.csv"
            con.execute(f"COPY {table} TO '{out}' (HEADER, DELIMITER ',')")
        row_counts = {
            t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables
        }
        detail = ", ".join(f"{t} ({n:,})" for t, n in row_counts.items())
        print(f"  [sql] {name} -> {detail if detail else 'no new aggregates'}")

    return produced


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", action="store_true",
                        help="build base tables only, skip the analysis SQL")
    args = parser.parse_args(argv)

    _require_raw_files()
    started = datetime.now(timezone.utc)

    print("Building base tables")
    con = connect()
    base_meta = build_base(con)

    produced: dict[str, list[str]] = {}
    if not args.base:
        print("\nRunning analysis SQL")
        produced = run_analysis(con)

    metadata = {
        "generated_at_utc": started.isoformat(timespec="seconds"),
        "duckdb_version": duckdb.__version__,
        "snapshot_date": base_meta["snapshot_date"],
        "snapshot_support_records": base_meta["snapshot_support_records"],
        "snapshot_support_pct": base_meta["snapshot_support_pct"],
        "fact_rows": base_meta["fact_rows"],
        "fact_columns": base_meta["fact_columns"],
        "suppressed_source_fields": list(config.SUPPRESSED_SOURCE_FIELDS),
        "sql_files_executed": list(BASE_SQL) + ([] if args.base else list(ANALYSIS_SQL)),
        "aggregates_by_sql_file": produced,
    }
    config.RUN_METADATA.write_text(json.dumps(metadata, indent=2) + "\n")
    con.close()

    print(f"\nSnapshot date: {base_meta['snapshot_date']} "
          f"({base_meta['snapshot_support_pct']}% of active records agree)")
    print(f"Fact rows:     {base_meta['fact_rows']:,}")
    print(f"Aggregates:    {sum(len(v) for v in produced.values())} tables -> "
          f"{config.AGGREGATES_DIR.relative_to(config.REPO_ROOT)}/")
    print(f"Metadata:      {config.RUN_METADATA.relative_to(config.REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
