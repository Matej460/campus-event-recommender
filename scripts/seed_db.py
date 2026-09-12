#!/usr/bin/env python3
"""ETL: read the CSV files, clean + validate every row, load into PostgreSQL.

Usage:
    uv run python scripts/seed_db.py             # create tables and load data
    uv run python scripts/seed_db.py --reset     # drop and recreate first
    uv run python scripts/seed_db.py --dry-run   # validate only, touch nothing

Rows that fail validation are reported with their line number and skipped, so a
single broken record never aborts the whole import.
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime, time
from pathlib import Path
from typing import Any, Iterator

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from app.config import settings  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.models import Event, EventRegistration, Student  # noqa: E402

DATETIME_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M")
TIME_FORMATS = ("%H:%M:%S", "%H:%M")

TRUE_VALUES = {"true", "1", "yes", "y", "t"}
FALSE_VALUES = {"false", "0", "no", "n", "f", ""}


class RowError(ValueError):
    """Raised when a CSV row cannot be cleaned into a valid record."""


# --------------------------------------------------------------------------- #
# Field-level cleaning helpers
# --------------------------------------------------------------------------- #
def clean_text(value: Any, *, field: str, required: bool = True, default: str = "") -> str:
    text_value = (value or "").strip()
    # Collapse repeated whitespace introduced by copy-paste / line breaks.
    text_value = " ".join(text_value.split())
    if not text_value:
        if required:
            raise RowError(f"'{field}' is empty")
        return default
    return text_value


def clean_int(value: Any, *, field: str, minimum: int | None = None, default: int | None = None) -> int:
    raw = (str(value) if value is not None else "").strip()
    if not raw:
        if default is not None:
            return default
        raise RowError(f"'{field}' is empty")
    try:
        parsed = int(float(raw))
    except ValueError as exc:
        raise RowError(f"'{field}' is not a number: {raw!r}") from exc
    if minimum is not None and parsed < minimum:
        raise RowError(f"'{field}' must be >= {minimum}, got {parsed}")
    return parsed


def clean_float(
    value: Any,
    *,
    field: str,
    minimum: float | None = None,
    maximum: float | None = None,
    default: float | None = None,
) -> float:
    raw = (str(value) if value is not None else "").strip().replace(",", ".")
    if not raw:
        if default is not None:
            return default
        raise RowError(f"'{field}' is empty")
    try:
        parsed = float(raw)
    except ValueError as exc:
        raise RowError(f"'{field}' is not a number: {raw!r}") from exc
    if minimum is not None and parsed < minimum:
        raise RowError(f"'{field}' must be >= {minimum}, got {parsed}")
    if maximum is not None and parsed > maximum:
        raise RowError(f"'{field}' must be <= {maximum}, got {parsed}")
    return parsed


def clean_bool(value: Any, *, field: str) -> bool:
    raw = (str(value) if value is not None else "").strip().lower()
    if raw in TRUE_VALUES:
        return True
    if raw in FALSE_VALUES:
        return False
    raise RowError(f"'{field}' is not a boolean: {value!r}")


def clean_datetime(value: Any, *, field: str) -> datetime:
    raw = (value or "").strip()
    if not raw:
        raise RowError(f"'{field}' is empty")
    for fmt in DATETIME_FORMATS:
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    raise RowError(f"'{field}' has an unsupported datetime format: {raw!r}")


def clean_time(value: Any, *, field: str) -> time:
    raw = (value or "").strip()
    if not raw:
        raise RowError(f"'{field}' is empty")
    for fmt in TIME_FORMATS:
        try:
            return datetime.strptime(raw, fmt).time()
        except ValueError:
            continue
    raise RowError(f"'{field}' has an unsupported time format: {raw!r}")


def clean_interests(value: Any) -> str:
    """Normalise 'technology, career ,Workshop' -> 'Technology,Career,Workshop'."""
    parts = [p.strip() for p in (value or "").split(",")]
    cleaned = [p.title() if p.islower() else p for p in parts if p]
    # dict.fromkeys removes duplicates while preserving the original order.
    return ",".join(dict.fromkeys(cleaned))


# --------------------------------------------------------------------------- #
# Row-level validation
# --------------------------------------------------------------------------- #
def parse_event_row(row: dict) -> dict:
    start = clean_datetime(row.get("start_datetime"), field="start_datetime")
    end = clean_datetime(row.get("end_datetime"), field="end_datetime")
    if end < start:
        raise RowError("end_datetime is earlier than start_datetime")

    is_online = clean_bool(row.get("is_online"), field="is_online")

    capacity = clean_int(row.get("capacity"), field="capacity", minimum=0, default=0)
    registered = clean_int(row.get("registered_count"), field="registered_count", minimum=0, default=0)
    if capacity and registered > capacity:
        # Clamp instead of rejecting: an over-booked count is a data quality
        # issue, not a reason to lose the event.
        registered = capacity

    latitude = longitude = None
    if not is_online:
        latitude = clean_float(row.get("latitude"), field="latitude", minimum=-90, maximum=90)
        longitude = clean_float(row.get("longitude"), field="longitude", minimum=-180, maximum=180)
    else:
        raw_lat = (row.get("latitude") or "").strip()
        raw_lon = (row.get("longitude") or "").strip()
        if raw_lat and raw_lon:
            latitude = clean_float(raw_lat, field="latitude", minimum=-90, maximum=90)
            longitude = clean_float(raw_lon, field="longitude", minimum=-180, maximum=180)

    return {
        "id": clean_int(row.get("event_id"), field="event_id", minimum=1),
        "title": clean_text(row.get("title"), field="title"),
        "description": clean_text(row.get("description"), field="description", required=False),
        "category": clean_text(row.get("category"), field="category"),
        "organizer": clean_text(row.get("organizer"), field="organizer"),
        "location_name": clean_text(row.get("location_name"), field="location_name"),
        "latitude": latitude,
        "longitude": longitude,
        "start_datetime": start,
        "end_datetime": end,
        "capacity": capacity,
        "registered_count": registered,
        "target_audience": clean_text(
            row.get("target_audience"), field="target_audience", required=False,
            default="All Students",
        ),
        "price": clean_float(row.get("price"), field="price", minimum=0, default=0.0),
        "is_online": is_online,
    }


def parse_student_row(row: dict) -> dict:
    available_from = clean_time(row.get("available_from"), field="available_from")
    available_to = clean_time(row.get("available_to"), field="available_to")
    if available_to <= available_from:
        raise RowError("available_to must be later than available_from")

    email = clean_text(row.get("email"), field="email").lower()
    if "@" not in email or "." not in email.split("@")[-1]:
        raise RowError(f"'email' looks invalid: {email!r}")

    interests = clean_interests(row.get("interests"))
    if not interests:
        raise RowError("'interests' is empty - at least one interest is required")

    return {
        "id": clean_int(row.get("student_id"), field="student_id", minimum=1),
        "name": clean_text(row.get("name"), field="name"),
        "email": email,
        "faculty": clean_text(row.get("faculty"), field="faculty"),
        "year_of_study": clean_int(row.get("year_of_study"), field="year_of_study", minimum=1),
        "latitude": clean_float(row.get("latitude"), field="latitude", minimum=-90, maximum=90),
        "longitude": clean_float(row.get("longitude"), field="longitude", minimum=-180, maximum=180),
        "interests": interests,
        "available_from": available_from,
        "available_to": available_to,
        "max_price": clean_float(row.get("max_price"), field="max_price", minimum=0, default=0.0),
    }


# --------------------------------------------------------------------------- #
# CSV / TSV reading
# --------------------------------------------------------------------------- #
def read_rows(path: Path) -> Iterator[tuple[int, dict]]:
    """Yield (line_number, row). Auto-detects comma vs tab delimiter."""
    if not path.exists():
        raise SystemExit(f"ERROR: data file not found: {path}")

    delimiter = "\t" if path.suffix.lower() in {".tsv", ".tab"} else ","
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh, delimiter=delimiter)
        for line_number, row in enumerate(reader, start=2):  # line 1 is the header
            yield line_number, row


def load_file(path: Path, parser, label: str) -> tuple[list[dict], list[str]]:
    records: list[dict] = []
    problems: list[str] = []
    seen_ids: set[int] = set()

    for line_number, row in read_rows(path):
        if not any((value or "").strip() for value in row.values()):
            continue  # skip blank lines
        try:
            record = parser(row)
        except RowError as exc:
            problems.append(f"  line {line_number}: {exc}")
            continue

        if record["id"] in seen_ids:
            problems.append(f"  line {line_number}: duplicate id {record['id']} - skipped")
            continue

        seen_ids.add(record["id"])
        records.append(record)

    print(f"{label}: {len(records)} valid rows, {len(problems)} rejected ({path})")
    for problem in problems[:20]:
        print(problem)
    if len(problems) > 20:
        print(f"  ... and {len(problems) - 20} more")

    return records, problems


# --------------------------------------------------------------------------- #
# Database loading
# --------------------------------------------------------------------------- #
def reset_schema() -> None:
    print("Dropping and recreating all tables ...")
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def sync_sequences() -> None:
    """Realign the identity sequences after inserting explicit ids.

    Without this, the first POST /events would try to reuse id 1 and fail on a
    primary-key conflict.
    """
    with engine.begin() as conn:
        for table in ("students", "events", "event_registrations"):
            conn.execute(
                text(
                    f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                    f"COALESCE((SELECT MAX(id) FROM {table}), 0) + 1, false)"
                )
            )
    print("Primary-key sequences realigned.")


def insert_records(model, records: list[dict], label: str) -> None:
    if not records:
        print(f"{label}: nothing to insert")
        return

    with SessionLocal() as session:
        existing = {row[0] for row in session.query(model.id).all()}
        fresh = [r for r in records if r["id"] not in existing]
        skipped = len(records) - len(fresh)

        session.bulk_insert_mappings(model, fresh)
        session.commit()

    message = f"{label}: inserted {len(fresh)} row(s)"
    if skipped:
        message += f", skipped {skipped} already present"
    print(message)


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed PostgreSQL from the CSV datasets")
    parser.add_argument("--reset", action="store_true", help="Drop and recreate all tables first")
    parser.add_argument("--dry-run", action="store_true", help="Validate only, do not write")
    parser.add_argument("--events", type=Path, default=settings.events_csv)
    parser.add_argument("--students", type=Path, default=settings.students_csv)
    args = parser.parse_args()

    print(f"Database: {settings.safe_database_url}")
    print("-" * 70)

    events, event_problems = load_file(args.events, parse_event_row, "Events")
    students, student_problems = load_file(args.students, parse_student_row, "Students")
    print("-" * 70)

    if args.dry_run:
        total_problems = len(event_problems) + len(student_problems)
        print(f"Dry run complete. {total_problems} problem row(s) found. Nothing was written.")
        return

    if args.reset:
        reset_schema()
    else:
        Base.metadata.create_all(bind=engine)

    insert_records(Student, students, "Students")
    insert_records(Event, events, "Events")
    sync_sequences()

    with SessionLocal() as session:
        n_students = session.query(Student).count()
        n_events = session.query(Event).count()
        n_registrations = session.query(EventRegistration).count()

    print("-" * 70)
    print(f"Done. students={n_students}  events={n_events}  registrations={n_registrations}")


if __name__ == "__main__":
    main()
