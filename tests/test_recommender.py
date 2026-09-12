"""Unit tests for the deterministic scoring engine.

These tests use in-memory stub events, so they run without a database.
"""

from __future__ import annotations

from datetime import time, timedelta

import pytest

from app.recommender import (
    MAX_SCORE,
    StudentProfile,
    event_distance_km,
    haversine_km,
    is_eligible,
    recommend,
    score_audience,
    score_capacity,
    score_distance,
    score_event,
    score_interest,
    score_price,
    score_time,
)
from tests.conftest import make_event


# --------------------------------------------------------------------------- #
# Geo
# --------------------------------------------------------------------------- #
def test_haversine_zero_distance():
    assert haversine_km(41.9981, 21.4254, 41.9981, 21.4254) == pytest.approx(0.0, abs=1e-9)


def test_haversine_known_distance():
    # Skopje (41.9981, 21.4254) -> Tetovo (42.0100, 20.9714): ~37.6 km
    distance = haversine_km(41.9981, 21.4254, 42.0100, 20.9714)
    assert 37.0 < distance < 38.5


def test_haversine_is_symmetric():
    a = haversine_km(41.99, 21.42, 42.01, 21.44)
    b = haversine_km(42.01, 21.44, 41.99, 21.42)
    assert a == pytest.approx(b)


def test_online_event_has_no_distance(student):
    online = make_event(is_online=True)
    assert event_distance_km(student, online) is None


# --------------------------------------------------------------------------- #
# Hard filters
# --------------------------------------------------------------------------- #
def test_past_event_is_not_eligible(student, event, now):
    past = make_event(start_datetime=now - timedelta(days=1), end_datetime=now - timedelta(hours=22))
    eligible, reason = is_eligible(student, past, now)
    assert eligible is False
    assert "already started" in reason


def test_full_event_is_not_eligible(student, now):
    full = make_event(capacity=40, registered_count=40)
    full.available_places = 0
    eligible, reason = is_eligible(student, full, now)
    assert eligible is False
    assert "fully booked" in reason


def test_too_expensive_event_is_not_eligible(student, now):
    expensive = make_event(price=50)
    eligible, reason = is_eligible(student, expensive, now)
    assert eligible is False
    assert "price" in reason


def test_wrong_year_audience_is_not_eligible(student, now):
    # `student` is in year 2, so a first-year-only event must be dropped.
    freshman_only = make_event(target_audience="First Year Students")
    eligible, _ = is_eligible(student, freshman_only, now)
    assert eligible is False


def test_matching_year_audience_is_eligible(student, now):
    final_year = student._replace(year_of_study=4)
    event = make_event(target_audience="Final Year Students")
    eligible, _ = is_eligible(final_year, event, now)
    assert eligible is True


# --------------------------------------------------------------------------- #
# Interest component (0-35)
# --------------------------------------------------------------------------- #
def test_exact_category_gets_full_interest_points(student, event):
    points, note = score_interest(student, event)
    assert points == 35.0
    assert "Technology" in note


def test_related_category_gets_partial_points(student):
    # The student likes Technology; Science is mapped as related.
    science = make_event(category="Science", title="Physics Hour", description="demos")
    points, _ = score_interest(student, science)
    assert 0 < points < 35.0


def test_unrelated_category_scores_zero(student):
    sport = make_event(category="Sport", title="Volleyball", description="games on court")
    points, note = score_interest(student, sport)
    assert points == 0.0
    assert note == ""


def test_keyword_in_description_earns_partial_credit(student):
    # Category is unrelated, but "career" appears in the description text.
    event = make_event(category="Sport", title="Run", description="A career-focused charity run")
    points, _ = score_interest(student, event)
    assert points > 0


def test_student_without_interests_gets_neutral_points(event):
    blank = StudentProfile(interests=())
    points, _ = score_interest(blank, event)
    assert points == pytest.approx(17.5)


# --------------------------------------------------------------------------- #
# Time component (0-20)
# --------------------------------------------------------------------------- #
def test_event_fully_inside_window_gets_full_points(student, event):
    points, _ = score_time(student, event)  # 14:00-16:00 inside 13:00-18:00
    assert points == 20.0


def test_event_outside_window_scores_zero(student, now):
    early = make_event(
        start_datetime=now.replace(hour=8) + timedelta(days=5),
        end_datetime=now.replace(hour=10) + timedelta(days=5),
    )
    points, _ = score_time(student, early)
    assert points == 0.0


def test_partial_overlap_is_proportional(student, now):
    # 17:00-19:00 against a 13:00-18:00 window -> exactly half the event fits.
    partial = make_event(
        start_datetime=now.replace(hour=17) + timedelta(days=5),
        end_datetime=now.replace(hour=19) + timedelta(days=5),
    )
    points, note = score_time(student, partial)
    assert points == pytest.approx(10.0)
    assert "partly" in note


# --------------------------------------------------------------------------- #
# Audience component (0-15)
# --------------------------------------------------------------------------- #
def test_own_faculty_beats_all_students(student, event):
    own, _ = score_audience(student, event)  # target_audience = Computer Science
    general, _ = score_audience(student, make_event(target_audience="All Students"))
    other, _ = score_audience(student, make_event(target_audience="Philology"))
    assert own == 15.0
    assert own > general > other


# --------------------------------------------------------------------------- #
# Distance component (0-15)
# --------------------------------------------------------------------------- #
def test_very_close_event_gets_full_distance_points(student, event):
    distance = event_distance_km(student, event)
    points, _ = score_distance(student, distance, event)
    assert points == 15.0


def test_distance_decays_with_kilometres(student, event):
    near, _ = score_distance(student, 1.0, event)
    mid, _ = score_distance(student, 3.0, event)
    far, _ = score_distance(student, 9.0, event)
    assert 15.0 > near > mid > far == 0.0


def test_online_event_gets_full_distance_points(student):
    online = make_event(is_online=True)
    points, note = score_distance(student, None, online)
    assert points == 15.0
    assert "online" in note.lower()


# --------------------------------------------------------------------------- #
# Price + capacity components
# --------------------------------------------------------------------------- #
def test_free_event_gets_full_price_points(student, event):
    points, note = score_price(student, event)
    assert points == 8.0
    assert "free" in note.lower()


def test_cheaper_event_scores_higher_than_expensive_one(student):
    cheap, _ = score_price(student, make_event(price=2))
    pricey, _ = score_price(student, make_event(price=9))
    assert cheap > pricey > 0


def test_capacity_points_drop_as_the_event_fills_up():
    empty = make_event(capacity=100, registered_count=0)
    empty.available_places = 100
    half = make_event(capacity=100, registered_count=70)
    half.available_places = 30
    nearly_full = make_event(capacity=100, registered_count=95)
    nearly_full.available_places = 5

    assert score_capacity(empty)[0] > score_capacity(half)[0] > score_capacity(nearly_full)[0]


# --------------------------------------------------------------------------- #
# Whole-event scoring
# --------------------------------------------------------------------------- #
def test_perfect_event_scores_100(student, now):
    perfect = make_event(
        category="Technology",           # exact interest -> 35
        target_audience="Computer Science",  # own faculty -> 15
        price=0,                         # free -> 8
        capacity=100,
        registered_count=0,              # plenty of room -> 7
        latitude=student.latitude,       # same spot -> 15
        longitude=student.longitude,
        start_datetime=now.replace(hour=14) + timedelta(days=5),  # inside window -> 20
        end_datetime=now.replace(hour=16) + timedelta(days=5),
    )
    perfect.available_places = 100
    scored = score_event(student, perfect, now)
    assert scored.score == 100
    assert MAX_SCORE == 100


def test_score_never_exceeds_bounds(student, now):
    for category in ("Technology", "Sport", "Culture"):
        for price in (0, 5, 10):
            scored = score_event(student, make_event(category=category, price=price), now)
            if scored is not None:
                assert 0 <= scored.score <= 100


def test_ineligible_event_returns_none(student, now):
    past = make_event(start_datetime=now - timedelta(days=2), end_datetime=now - timedelta(days=2))
    assert score_event(student, past, now) is None


def test_breakdown_sums_to_raw_score(student, event, now):
    scored = score_event(student, event, now)
    assert sum(scored.breakdown) == pytest.approx(scored.raw_score, abs=0.01)


def test_reason_is_a_sentence(student, event, now):
    scored = score_event(student, event, now)
    assert scored.reason.endswith(".")
    assert scored.reason[0].isupper()


# --------------------------------------------------------------------------- #
# Ranking
# --------------------------------------------------------------------------- #
def test_results_are_sorted_by_score_descending(student, now):
    events = [
        make_event(id=1, category="Sport", target_audience="Philology", price=5),
        make_event(id=2, category="Technology"),
        make_event(id=3, category="Science"),
    ]
    for e in events:
        e.available_places = max(e.capacity - e.registered_count, 0)

    ranked, candidates = recommend(student, events, now=now)
    scores = [r.score for r in ranked]

    assert scores == sorted(scores, reverse=True)
    assert ranked[0].event.id == 2  # exact interest match wins
    assert candidates == 3


def test_recommendation_is_deterministic(student, now):
    events = [make_event(id=i, category=c) for i, c in enumerate(["Technology", "Art", "Career"], 1)]
    for e in events:
        e.available_places = max(e.capacity - e.registered_count, 0)

    first, _ = recommend(student, events, now=now)
    second, _ = recommend(student, events, now=now)

    assert [(r.event.id, r.score) for r in first] == [(r.event.id, r.score) for r in second]


def test_limit_and_min_score_are_applied(student, now):
    events = [make_event(id=i, category="Technology") for i in range(1, 11)]
    for e in events:
        e.available_places = max(e.capacity - e.registered_count, 0)

    ranked, candidates = recommend(student, events, limit=3, now=now)
    assert len(ranked) == 3
    assert candidates == 10

    strict, _ = recommend(student, events, min_score=101, now=now)
    assert strict == []


def test_ties_break_on_earlier_start_then_id(student, now):
    later = make_event(id=5, start_datetime=now + timedelta(days=6, hours=5),
                       end_datetime=now + timedelta(days=6, hours=7))
    earlier = make_event(id=9, start_datetime=now + timedelta(days=3, hours=5),
                         end_datetime=now + timedelta(days=3, hours=7))
    for e in (later, earlier):
        e.available_places = max(e.capacity - e.registered_count, 0)

    ranked, _ = recommend(student, [later, earlier], now=now)
    assert [r.event.id for r in ranked] == [9, 5]


def test_anonymous_profile_still_produces_recommendations(now):
    visitor = StudentProfile(
        latitude=41.998, longitude=21.425,
        interests=("Technology",),
        available_from=time(9, 0), available_to=time(21, 0),
    )
    events = [make_event(id=1), make_event(id=2, category="Sport")]
    for e in events:
        e.available_places = max(e.capacity - e.registered_count, 0)

    ranked, candidates = recommend(visitor, events, now=now)
    assert candidates == 2
    assert ranked[0].event.id == 1
