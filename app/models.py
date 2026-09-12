"""SQLAlchemy ORM models.

Every table carries the audit columns required by the brief:
`created_at`, `updated_at` and `deleted_at` (soft delete).
"""

from __future__ import annotations

from datetime import datetime, time

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class TimestampMixin:
    """Audit columns shared by every table."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    # NULL  -> the row is active.
    # value -> the row is soft deleted and must be excluded from every query.
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False), nullable=True, default=None
    )


class Student(TimestampMixin, Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    faculty: Mapped[str] = mapped_column(String(120), nullable=False)
    year_of_study: Mapped[int] = mapped_column(Integer, nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)

    # Multiple interests per student, stored as a normalised comma separated
    # string ("Technology,Career,Workshop"). See docs for why this simple
    # representation was chosen over a join table.
    interests: Mapped[str] = mapped_column(Text, nullable=False, default="")

    available_from: Mapped[time] = mapped_column(Time, nullable=False)
    available_to: Mapped[time] = mapped_column(Time, nullable=False)
    max_price: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False, default=0)

    registrations: Mapped[list["EventRegistration"]] = relationship(
        back_populates="student", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_students_deleted_at", "deleted_at"),)

    @property
    def interest_list(self) -> list[str]:
        """Interests as a clean list, e.g. ['Technology', 'Career']."""
        return [part.strip() for part in (self.interests or "").split(",") if part.strip()]

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<Student id={self.id} name={self.name!r} faculty={self.faculty!r}>"


class Event(TimestampMixin, Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    category: Mapped[str] = mapped_column(String(60), nullable=False)
    organizer: Mapped[str] = mapped_column(String(160), nullable=False)
    location_name: Mapped[str] = mapped_column(String(200), nullable=False)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    start_datetime: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    end_datetime: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    registered_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    target_audience: Mapped[str] = mapped_column(String(120), nullable=False, default="All Students")
    price: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False, default=0)
    is_online: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    registrations: Mapped[list["EventRegistration"]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_events_category", "category"),
        Index("ix_events_start_datetime", "start_datetime"),
        Index("ix_events_deleted_at", "deleted_at"),
    )

    @property
    def available_places(self) -> int:
        """Remaining seats, never negative."""
        return max(self.capacity - self.registered_count, 0)

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<Event id={self.id} title={self.title!r} category={self.category!r}>"


class EventRegistration(TimestampMixin, Base):
    """Optional extension: keeps track of who signed up for what."""

    __tablename__ = "event_registrations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"), nullable=False
    )
    event_id: Mapped[int] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    registration_datetime: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), server_default=func.now(), nullable=False
    )
    # registered | cancelled | attended
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="registered")

    student: Mapped["Student"] = relationship(back_populates="registrations")
    event: Mapped["Event"] = relationship(back_populates="registrations")

    __table_args__ = (
        UniqueConstraint("student_id", "event_id", name="uq_registration_student_event"),
        Index("ix_event_registrations_deleted_at", "deleted_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return (
            f"<EventRegistration student_id={self.student_id} "
            f"event_id={self.event_id} status={self.status!r}>"
        )
