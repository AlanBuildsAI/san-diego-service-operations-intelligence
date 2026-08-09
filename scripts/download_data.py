"""Retrieve official City of San Diego "Get It Done" source files.

Source of record
----------------
City of San Diego Open Data Portal (DataSD), dataset:
"Reports of non-emergency problems submitted by users of Get It Done"
    https://data.sandiego.gov/datasets/get-it-done-reports/

Files are served from the City's public object store (seshat.datasd.org) and are
refreshed daily by the City. Only official City URLs are used; no third-party
mirrors or scraped copies are involved.

This script downloads the files into ``data/raw/`` (git-ignored), records the
retrieval date, byte size, SHA-256 hash and row count of every file, and writes
a machine-readable manifest to ``data/raw/_download_manifest.json``.

Usage
-----
    python scripts/download_data.py                # default project scope
    python scripts/download_data.py --all-closed   # every closed-year file
    python scripts/download_data.py --check-only   # HEAD requests, no download
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE_URL = "https://seshat.datasd.org/get_it_done_reports"
DATASET_PAGE = "https://data.sandiego.gov/datasets/get-it-done-reports/"

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = REPO_ROOT / "data" / "raw"
MANIFEST_PATH = RAW_DIR / "_download_manifest.json"

CHUNK_BYTES = 1 << 20  # 1 MiB


@dataclass(frozen=True)
class SourceFile:
    """One official file in the Get It Done dataset."""

    key: str
    filename: str
    role: str
    in_default_scope: bool

    @property
    def url(self) -> str:
        return f"{BASE_URL}/{self.filename}"

    @property
    def local_path(self) -> Path:
        return RAW_DIR / self.filename


# Registry of the official files this project knows about. The three flagged
# ``in_default_scope`` are the project scope: the live open queue plus the two
# most recent closed-year files, which is what the backlog and the year-over-year
# demand comparison require.
SOURCE_FILES: tuple[SourceFile, ...] = (
    SourceFile("dictionary", "get_it_done_requests_dictionary_datasd.csv",
               "Official field dictionary", True),
    SourceFile("open", "get_it_done_requests_open_datasd.csv",
               "All requests not in a closed state (live queue)", True),
    SourceFile("closed_2026", "get_it_done_requests_closed_2026_datasd.csv",
               "Requests closed during calendar 2026", True),
    SourceFile("closed_2025", "get_it_done_requests_closed_2025_datasd.csv",
               "Requests closed during calendar 2025", True),
    SourceFile("closed_2024", "get_it_done_requests_closed_2024_datasd.csv",
               "Requests closed during calendar 2024", False),
    SourceFile("closed_2023", "get_it_done_requests_closed_2023_datasd.csv",
               "Requests closed during calendar 2023", False),
    SourceFile("closed_2022", "get_it_done_requests_closed_2022_datasd.csv",
               "Requests closed during calendar 2022", False),
    SourceFile("closed_2021", "get_it_done_requests_closed_2021_datasd.csv",
               "Requests closed during calendar 2021", False),
    SourceFile("closed_2020", "get_it_done_requests_closed_2020_datasd.csv",
               "Requests closed during calendar 2020", False),
    SourceFile("closed_2019", "get_it_done_requests_closed_2019_datasd.csv",
               "Requests closed during calendar 2019", False),
    SourceFile("closed_2018", "get_it_done_requests_closed_2018_datasd.csv",
               "Requests closed during calendar 2018", False),
    SourceFile("closed_2017", "get_it_done_requests_closed_2017_datasd.csv",
               "Requests closed during calendar 2017", False),
    SourceFile("closed_2016", "get_it_done_requests_closed_2016_datasd.csv",
               "Requests closed during calendar 2016 (program launch May 2016)", False),
)


def head(source: SourceFile) -> dict:
    """Fetch server metadata without downloading the body."""
    response = requests.head(source.url, timeout=60, allow_redirects=True)
    response.raise_for_status()
    return {
        "http_status": response.status_code,
        "content_length_bytes": int(response.headers.get("content-length", 0)) or None,
        "last_modified_header": response.headers.get("last-modified"),
        "etag": response.headers.get("etag", "").strip('"') or None,
    }


def download(source: SourceFile, force: bool = False) -> None:
    """Stream one file to ``data/raw/``, skipping unchanged local copies."""
    if source.local_path.exists() and not force:
        print(f"  [skip] {source.filename} already present "
              f"({source.local_path.stat().st_size / 1e6:,.1f} MB)")
        return

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    tmp_path = source.local_path.with_suffix(".partial")
    with requests.get(source.url, stream=True, timeout=600) as response:
        response.raise_for_status()
        with tmp_path.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=CHUNK_BYTES):
                handle.write(chunk)
    tmp_path.replace(source.local_path)
    print(f"  [ok]   {source.filename} "
          f"({source.local_path.stat().st_size / 1e6:,.1f} MB)")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def count_data_rows(path: Path) -> int:
    """Count newline-delimited data rows, excluding the header.

    Get It Done free-text fields can contain embedded newlines, so this is a
    physical line count and is reported as such. The authoritative logical row
    count is produced by the parser in ``src/build_base.py`` and recorded in the
    audit; the two are compared there.
    """
    with path.open("rb") as handle:
        physical_lines = sum(buffer.count(b"\n") for buffer in iter(
            lambda: handle.read(CHUNK_BYTES), b""))
    return max(physical_lines - 1, 0)


def profile(source: SourceFile, server_meta: dict) -> dict:
    path = source.local_path
    return {
        "key": source.key,
        "filename": source.filename,
        "role": source.role,
        "url": source.url,
        "dataset_page": DATASET_PAGE,
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "size_bytes": path.stat().st_size,
        "sha256": sha256(path),
        "physical_data_lines": count_data_rows(path),
        **server_meta,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all-closed", action="store_true",
                        help="also retrieve closed-year files from 2016-2024")
    parser.add_argument("--check-only", action="store_true",
                        help="HEAD each URL and print metadata; download nothing")
    parser.add_argument("--force", action="store_true",
                        help="re-download files that already exist locally")
    args = parser.parse_args(argv)

    selected = [s for s in SOURCE_FILES if s.in_default_scope or args.all_closed]

    print(f"Official dataset page: {DATASET_PAGE}")
    print(f"Files selected: {len(selected)}\n")

    entries: list[dict] = []
    for source in selected:
        print(f"- {source.key}: {source.role}")
        try:
            server_meta = head(source)
        except requests.RequestException as exc:
            print(f"  [FAIL] HEAD {source.url}: {exc}", file=sys.stderr)
            entries.append({"key": source.key, "filename": source.filename,
                            "url": source.url, "error": str(exc)})
            continue

        if args.check_only:
            print(f"  [head] {server_meta}")
            entries.append({"key": source.key, "filename": source.filename,
                            "url": source.url, **server_meta})
            continue

        try:
            download(source, force=args.force)
        except requests.RequestException as exc:
            print(f"  [FAIL] GET {source.url}: {exc}", file=sys.stderr)
            entries.append({"key": source.key, "filename": source.filename,
                            "url": source.url, "error": str(exc)})
            continue

        entries.append(profile(source, server_meta))

    if not args.check_only:
        MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
        MANIFEST_PATH.write_text(json.dumps(
            {
                "dataset": "Get It Done service requests",
                "publisher": "City of San Diego, Performance & Analytics Department",
                "dataset_page": DATASET_PAGE,
                "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "files": entries,
            },
            indent=2,
        ) + "\n")
        print(f"\nManifest written to {MANIFEST_PATH.relative_to(REPO_ROOT)}")

    failures = [e for e in entries if "error" in e]
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
