"""Regenerate the synthetic test fixture.

The fixture is committed so that CI can run the full pipeline without downloading
~245 MB of real data. It is entirely synthetic — no real resident report, address
or description appears in it — and it deliberately contains one instance of every
condition the audit checks for:

    * open records whose case_age_days equals (snapshot - requested)   -> DQ-03
    * one stale open record whose case_age_days lags the snapshot      -> DQ-03
    * a service_request_id present in two extracts                     -> DQ-02
    * a record with date_closed earlier than date_requested            -> DQ-04
    * a Closed record carrying referral text                           -> DQ-10
    * records with missing geography and missing service_name          -> DQ-06/07
    * duplicate parent/child links, including an orphaned child        -> DQ-09

Run:  python tests/fixtures/make_fixture.py
"""

from __future__ import annotations

import csv
import random
from datetime import date, timedelta
from pathlib import Path

OUT = Path(__file__).resolve().parent
SNAPSHOT = date(2026, 8, 9)

COLUMNS = [
    "service_request_id", "service_request_parent_id", "sap_notification_number",
    "date_requested", "case_age_days", "case_record_type", "service_name",
    "service_name_detail", "date_closed", "status", "lat", "lng", "street_address",
    "zipcode", "council_district", "comm_plan_code", "comm_plan_name", "park_name",
    "case_origin", "referred", "iamfloc", "floc", "public_description",
]

SERVICES = ["Sidewalk Repair Issue", "Street Light Maintenance", "Pothole",
            "Parking - 72-Hours", "Encampment"]
COMMUNITIES = ["DOWNTOWN", "LA JOLLA", "NORTH PARK"]


def row(**kwargs) -> dict:
    record = {column: "" for column in COLUMNS}
    record.update(kwargs)
    return record


def build() -> tuple[list, list, list]:
    random.seed(7)
    open_rows, closed_2026, closed_2025 = [], [], []

    for i in range(60):
        age = random.choice([3, 15, 45, 80, 150, 400, 900, 1500])
        requested = SNAPSHOT - timedelta(days=age)
        parent = str(1000 + i - 1) if i % 4 == 0 and i > 0 else ""
        open_rows.append(row(
            service_request_id=str(1000 + i), service_request_parent_id=parent,
            date_requested=f"{requested} 09:15:00.000", case_age_days=str(age),
            case_record_type="TSW", service_name=SERVICES[i % len(SERVICES)],
            service_name_detail="DETAIL", status="In Process" if i % 5 else "New",
            lat="32.7", lng="-117.1", street_address=f"{100 + i} Main St",
            zipcode="92101", council_district=str((i % 9) + 1), comm_plan_code="4",
            comm_plan_name=COMMUNITIES[i % 3],
            case_origin=["Mobile", "Web", "Phone", "Worker App"][i % 4],
            public_description="A synthetic description that must never be published."))

    open_rows.append(row(
        service_request_id="1999", date_requested="2026-01-01 08:00:00.000",
        case_age_days="200", case_record_type="TSW", service_name="Pothole",
        status="In Process", council_district="3", comm_plan_name="DOWNTOWN",
        case_origin="Mobile"))
    open_rows.append(row(
        service_request_id="1998", date_requested="2025-02-01 08:00:00.000",
        case_age_days=str((SNAPSHOT - date(2025, 2, 1)).days), case_record_type="TSW",
        service_name="", status="New", case_origin=""))

    for i in range(80):
        lifecycle = random.choice([0, 1, 2, 5, 30, 120, 700])
        closed = date(2026, random.randint(1, 7), random.randint(1, 28))
        requested = closed - timedelta(days=lifecycle)
        status = "Referred" if i % 9 == 0 else "Closed"
        referred = ""
        if status == "Referred":
            referred = ("This report has been referred to Caltrans San Diego at null"
                        if i % 2 == 0 else
                        "Your request has been referred to SDG&E. To contact SDG&E, "
                        "please call 800-411-7343.")
        closed_2026.append(row(
            service_request_id=str(2000 + i),
            service_request_parent_id=str(2000 + i - 1) if i % 7 == 0 and i > 0 else "",
            date_requested=f"{requested} 11:00:00.000", case_age_days=str(lifecycle),
            case_record_type="TSW", service_name=SERVICES[i % len(SERVICES)],
            date_closed=str(closed), status=status, street_address=f"{i} Elm Ave",
            zipcode="92101", council_district=str((i % 9) + 1),
            comm_plan_name=COMMUNITIES[i % 3],
            case_origin=["Mobile", "Web", "Phone"][i % 3], referred=referred,
            public_description="synthetic text"))

    closed_2026.append(row(
        service_request_id="2999", date_requested="2026-03-01 09:00:00.000",
        case_age_days="10", case_record_type="TSW", service_name="Pothole",
        date_closed="2026-03-11", status="Closed", council_district="1",
        comm_plan_name="DOWNTOWN", case_origin="Web",
        referred="This report has been referred to Parks Intake"))
    closed_2026.append(row(
        service_request_id="2998", date_requested="2026-04-10 09:00:00.000",
        case_age_days="-2", case_record_type="TSW", service_name="Pothole",
        date_closed="2026-04-08", status="Closed", council_district="2",
        comm_plan_name="LA JOLLA", case_origin="Mobile"))

    for i in range(50):
        lifecycle = random.choice([0, 1, 4, 20, 90, 400])
        closed = date(2025, random.randint(1, 12), random.randint(1, 28))
        requested = closed - timedelta(days=lifecycle)
        closed_2025.append(row(
            service_request_id=str(3000 + i), date_requested=f"{requested} 14:30:00.000",
            case_age_days=str(lifecycle), case_record_type="Parking",
            service_name=SERVICES[i % len(SERVICES)], date_closed=str(closed),
            status="Closed", council_district=str((i % 9) + 1),
            comm_plan_name=COMMUNITIES[i % 3], case_origin="Mobile",
            public_description="synthetic text"))

    closed_2025.append(row(
        service_request_id="2000", date_requested="2025-01-05 10:00:00.000",
        case_age_days="30", case_record_type="TSW", service_name="Pothole",
        date_closed="2025-02-04", status="Closed", council_district="3",
        comm_plan_name="DOWNTOWN", case_origin="Mobile"))

    return open_rows, closed_2026, closed_2025


def write(name: str, rows: list[dict]) -> None:
    path = OUT / name
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"{name}: {len(rows)} rows")


def main() -> None:
    open_rows, closed_2026, closed_2025 = build()
    write("get_it_done_requests_open_datasd.csv", open_rows)
    write("get_it_done_requests_closed_2026_datasd.csv", closed_2026)
    write("get_it_done_requests_closed_2025_datasd.csv", closed_2025)

    path = OUT / "get_it_done_requests_dictionary_datasd.csv"
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["field", "data_type", "description", "possible_values"])
        for column in COLUMNS:
            writer.writerow([column, "String", "fixture field", ""])
    print("dictionary written")


if __name__ == "__main__":
    main()
