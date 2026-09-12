"""Shared pytest fixtures."""

from __future__ import annotations

import sys
from datetime import datetime, time, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.recommender import StudentProfile  # noqa: E402

NOW = datetime(2026, 9, 12, 9, 0)


def make_event(**overrides) -> SimpleNamespace:
    """Build a lightweight stand-in for the Event ORM model.

    The recommender only reads attributes, so a SimpleNamespace keeps the unit
    tests fast and completely independent of the database.
    """
    defaults = dict(
        id=1,
        title="AI Workshop",
        description="Introductory workshop about AI tools",
        category="Technology",
        organizer="Computer Science Club",
        location_name="Faculty Lab 2",
        latitude=41.9981,
        longitude=21.4254,
        start_datetime=NOW + timedelta(days=5, hours=5),   # 14:00
        end_datetime=NOW + timedelta(days=5, hours=7),     # 16:00
        capacity=40,
        registered_count=12,
        target_audience="Computer Science",
        price=0,
        is_online=False,
    )
    defaults.update(overrides)
    event = SimpleNamespace(**defaults)
    event.available_places = max(event.capacity - event.registered_count, 0)
    return event


@pytest.fixture
def now() -> datetime:
    return NOW


@pytest.fixture
def event():
    return make_event()


@pytest.fixture
def student() -> StudentProfile:
    return StudentProfile(
        student_id=1,
        name="Ana Petrova",
        faculty="Computer Science",
        year_of_study=2,
        latitude=41.9980,
        longitude=21.4250,
        interests=("Technology", "Career", "Workshop"),
        available_from=time(13, 0),
        available_to=time(18, 0),
        max_price=10.0,
    )
