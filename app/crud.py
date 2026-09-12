"""Database query helpers.

Every read helper filters out soft-deleted rows (`deleted_at IS NULL`) so the
rest of the application never has to remember to do it.
"""

from __future__ import annotations

from datetime import date, datetime, time

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.models import Event, EventRegistration, Student


# --------------------------------------------------------------------------- #
# Events
# --------------------------------------------------------------------------- #
def _active_events() -> Select:
    return select(Event).where(Event.deleted_at.is_(None))


def list_events(
    db: Session,
    *,
    category: str | None = None,
    event_date: date | None = None,
    free_only: bool = False,
    is_online: bool | None = None,
    search: str | None = None,
    upcoming_only: bool = False,
    limit: int = 100,
    offset: int = 0,
) -> list[Event]:
    """Return events matching every supplied filter (filters combine with AND)."""
    stmt = _active_events()

    if category:
        # Case-insensitive so ?category=technology also works.
        stmt = stmt.where(Event.category.ilike(category))

    if event_date is not None:
        day_start = datetime.combine(event_date, time.min)
        day_end = datetime.combine(event_date, time.max)
        stmt = stmt.where(Event.start_datetime.between(day_start, day_end))

    if free_only:
        stmt = stmt.where(Event.price == 0)

    if is_online is not None:
        stmt = stmt.where(Event.is_online.is_(is_online))

    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(Event.title.ilike(pattern) | Event.description.ilike(pattern))

    if upcoming_only:
        stmt = stmt.where(Event.start_datetime > datetime.now())

    stmt = stmt.order_by(Event.start_datetime.asc(), Event.id.asc()).limit(limit).offset(offset)
    return list(db.execute(stmt).scalars())


def get_event(db: Session, event_id: int) -> Event | None:
    stmt = _active_events().where(Event.id == event_id)
    return db.execute(stmt).scalar_one_or_none()


def count_events(db: Session) -> int:
    from sqlalchemy import func

    return db.execute(
        select(func.count(Event.id)).where(Event.deleted_at.is_(None))
    ).scalar_one()


def create_event(db: Session, data: dict) -> Event:
    event = Event(**data)
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def list_event_categories(db: Session) -> list[str]:
    stmt = (
        select(Event.category)
        .where(Event.deleted_at.is_(None))
        .distinct()
        .order_by(Event.category.asc())
    )
    return list(db.execute(stmt).scalars())


# --------------------------------------------------------------------------- #
# Students
# --------------------------------------------------------------------------- #
def _active_students() -> Select:
    return select(Student).where(Student.deleted_at.is_(None))


def list_students(
    db: Session,
    *,
    faculty: str | None = None,
    year_of_study: int | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[Student]:
    stmt = _active_students()
    if faculty:
        stmt = stmt.where(Student.faculty.ilike(faculty))
    if year_of_study is not None:
        stmt = stmt.where(Student.year_of_study == year_of_study)
    stmt = stmt.order_by(Student.id.asc()).limit(limit).offset(offset)
    return list(db.execute(stmt).scalars())


def get_student(db: Session, student_id: int) -> Student | None:
    stmt = _active_students().where(Student.id == student_id)
    return db.execute(stmt).scalar_one_or_none()


def get_student_by_email(db: Session, email: str) -> Student | None:
    stmt = _active_students().where(Student.email == email)
    return db.execute(stmt).scalar_one_or_none()


def create_student(db: Session, data: dict) -> Student:
    student = Student(**data)
    db.add(student)
    db.commit()
    db.refresh(student)
    return student


# --------------------------------------------------------------------------- #
# Registrations (optional extension)
# --------------------------------------------------------------------------- #
def get_registration(db: Session, student_id: int, event_id: int) -> EventRegistration | None:
    stmt = select(EventRegistration).where(
        EventRegistration.student_id == student_id,
        EventRegistration.event_id == event_id,
        EventRegistration.deleted_at.is_(None),
    )
    return db.execute(stmt).scalar_one_or_none()


def create_registration(db: Session, student_id: int, event_id: int) -> EventRegistration:
    registration = EventRegistration(
        student_id=student_id, event_id=event_id, status="registered"
    )
    db.add(registration)

    event = get_event(db, event_id)
    if event is not None:
        event.registered_count += 1

    db.commit()
    db.refresh(registration)
    return registration


def list_registrations(db: Session, *, student_id: int | None = None) -> list[EventRegistration]:
    stmt = select(EventRegistration).where(EventRegistration.deleted_at.is_(None))
    if student_id is not None:
        stmt = stmt.where(EventRegistration.student_id == student_id)
    return list(db.execute(stmt.order_by(EventRegistration.id.asc())).scalars())
