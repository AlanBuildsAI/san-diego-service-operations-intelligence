"""Shared configuration: paths, scope, and analytical constants.

Every module in this project imports its paths from here so that a change to the
project scope happens in exactly one place.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

RAW_DIR = REPO_ROOT / "data" / "raw"
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
AGGREGATES_DIR = REPO_ROOT / "data" / "aggregates"
SQL_DIR = REPO_ROOT / "03_sql"
AUDIT_DIR = REPO_ROOT / "02_data_audit"
DASHBOARD_DIR = REPO_ROOT / "05_dashboard"
ASSETS_DIR = DASHBOARD_DIR / "assets"
DOCS_DIR = REPO_ROOT / "docs"

DUCKDB_PATH = PROCESSED_DIR / "gid.duckdb"
FACT_PARQUET = PROCESSED_DIR / "fct_service_requests.parquet"
DOWNLOAD_MANIFEST = RAW_DIR / "_download_manifest.json"
RUN_METADATA = PROCESSED_DIR / "_run_metadata.json"
AUDIT_RESULTS = AUDIT_DIR / "audit_results.json"

# --- Project scope -----------------------------------------------------------
# The three official extracts that make up the analysis scope. `precedence`
# resolves the small number of service_request_ids that appear in more than one
# extract: lower number wins. The live "open" extract is the most recently
# refreshed view of a case, then the most recent closed-year archive.
SOURCE_EXTRACTS: dict[str, dict] = {
    "open": {
        "filename": "get_it_done_requests_open_datasd.csv",
        "precedence": 1,
        "description": "Requests not in a closed state as of the snapshot",
    },
    "closed_2026": {
        "filename": "get_it_done_requests_closed_2026_datasd.csv",
        "precedence": 2,
        "description": "Requests with a recorded closure during calendar 2026",
    },
    "closed_2025": {
        "filename": "get_it_done_requests_closed_2025_datasd.csv",
        "precedence": 3,
        "description": "Requests with a recorded closure during calendar 2025",
    },
}

DICTIONARY_FILE = RAW_DIR / "get_it_done_requests_dictionary_datasd.csv"

# --- Analytical constants ----------------------------------------------------
ACTIVE_STATUSES = ("New", "In Process")
CLOSED_STATUSES = ("Closed", "Referred")

# Aging buckets. The first six are the standard operational buckets. Because the
# active queue in this dataset is long-tailed (see 01_business_brief/
# metric_definitions.md), the "181+" bucket is additionally split so the tail is
# readable; "181+" remains recoverable by summing the last three.
AGE_BUCKETS = (
    ("0-7", 0, 7),
    ("8-30", 8, 30),
    ("31-60", 31, 60),
    ("61-90", 61, 90),
    ("91-180", 91, 180),
    ("181-365", 181, 365),
    ("366-730", 366, 730),
    ("731+", 731, None),
)

AGED_THRESHOLDS = (60, 90)

# Fields removed from every published output for privacy / need-to-know reasons.
# See docs/source_manifest.md and 07_methodology/methodology.md.
SUPPRESSED_SOURCE_FIELDS = (
    "public_description",   # resident free text
    "street_address",       # exact point address
    "lat",                  # exact coordinates
    "lng",
    "referred",             # canned text containing staff/vendor email addresses
    "iamfloc",              # internal asset identifiers, no analytical value here
    "floc",
    "sap_notification_number",
)

# Fair-comparison window for the year-over-year demand question. August of the
# snapshot year is partial, so only completed months are compared.
YOY_COMPLETE_MONTHS = 7  # January through July
YOY_CURRENT_YEAR = 2026
YOY_PRIOR_YEAR = 2025


def bucket_case_expression(column: str) -> str:
    """Return a SQL CASE expression assigning `column` to an aging bucket."""
    parts = []
    for label, low, high in AGE_BUCKETS:
        if high is None:
            parts.append(f"WHEN {column} >= {low} THEN '{label}'")
        else:
            parts.append(f"WHEN {column} <= {high} THEN '{label}'")
    return "CASE " + " ".join(parts) + " ELSE NULL END"


def bucket_order_expression(column: str) -> str:
    """Return a SQL CASE expression giving each bucket a stable sort order."""
    parts = [
        f"WHEN {column} = '{label}' THEN {i}"
        for i, (label, _, _) in enumerate(AGE_BUCKETS)
    ]
    return "CASE " + " ".join(parts) + " ELSE 99 END"
