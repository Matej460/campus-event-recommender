"""Deterministic, explainable recommendation engine.

No machine learning is involved. Every event is scored with a fixed set of
rules; running the same input twice always produces the same output.

FINAL SCORE = 100 points, split across six weighted components:

    Interest match .......... 35   (the strongest signal of relevance)
    Time availability ....... 20   (an event you cannot attend is useless)
    Audience / faculty ...... 15
    Distance ................ 15
    Price / affordability ....  8
    Capacity / availability ..  7
    -----------------------------
    TOTAL ................... 100

Before scoring, four HARD FILTERS remove events the student simply cannot
attend (see `is_eligible`). Filtering first keeps the score honest: a 0 in a
component means "weak match", never "impossible".

The weights are explained and justified in docs/technical_documentation.md.
"""

from __future__ import annotations

from datetime import datetime, time
from math import asin, cos, radians, sin, sqrt
from typing import Iterable, NamedTuple

# --------------------------------------------------------------------------- #
# Tunable constants - single source of truth for the whole scoring model.
# --------------------------------------------------------------------------- #
W_INTEREST = 35.0
W_TIME = 20.0
W_AUDIENCE = 15.0
W_DISTANCE = 15.0
W_PRICE = 8.0
W_CAPACITY = 7.0

MAX_SCORE = W_INTEREST + W_TIME + W_AUDIENCE + W_DISTANCE + W_PRICE + W_CAPACITY  # = 100

# Distance model: full marks inside NEAR_KM, linear decay to zero at FAR_KM.
NEAR_KM = 0.5
FAR_KM = 5.0

EARTH_RADIUS_KM = 6371.0088

# Categories that are close enough to each other to earn partial interest
# credit. The map is symmetric and is applied in both directions.
RELATED_CATEGORIES: dict[str, set[str]] = {
    "Technology": {"Science", "Workshop", "Competition"},
    "Science": {"Technology", "Workshop"},
    "Career": {"Networking", "Business", "Workshop"},
    "Business": {"Career", "Networking", "Competition"},
    "Networking": {"Career", "Business", "Student Club"},
    "Art": {"Culture", "Music"},
    "Culture": {"Art", "Music", "Language"},
    "Music": {"Art", "Culture"},
    "Language": {"Culture", "Workshop"},
    "Sport": {"Health"},
    "Health": {"Sport", "Volunteering"},
    "Volunteering": {"Student Club", "Health"},
    "Student Club": {"Networking", "Volunteering"},
    "Workshop": {"Technology", "Career", "Science", "Language"},
    "Competition": {"Technology", "Business", "Sport"},
}

# Audiences that target a specific year of study rather than a faculty.
YEAR_AUDIENCES = {
    "First Year Students": lambda year: year == 1,
    "Final Year Students": lambda year: year >= 4,
}

GENERAL_AUDIENCES = {"All Students", "All", "Everyone"}


# --------------------------------------------------------------------------- #
# Small value objects
# --------------------------------------------------------------------------- #
class Breakdown(NamedTuple):
    interest_match: float
    time_availability: float
    audience_match: float
    distance: float
    price: float
    capacity: float

    @property
    def total(self) -> float:
        return sum(self)


class ScoredEvent(NamedTuple):
    event: object
    score: int
    raw_score: float
    distance_km: float | None
    breakdown: Breakdown
    reason: str


class StudentProfile(NamedTuple):
    """Everything the engine needs about a student.

    Using a lightweight profile (instead of the ORM object) lets the same
    engine serve both `GET /recommendations/{student_id}` and the anonymous
    `GET /recommendations?lat=..&lon=..&interests=..` endpoint.
    """

    student_id: int | None = None
    name: str | None = None
    faculty: str | None = None
    year_of_study: int | None = None
    latitude: float | None = None
    longitude: float | None = None
    interests: tuple[str, ...] = ()
    available_from: time | None = None
    available_to: time | None = None
    max_price: float | None = None

    @classmethod
    def from_model(cls, student) -> "StudentProfile":
        return cls(
            student_id=student.id,
            name=student.name,
            faculty=student.faculty,
            year_of_study=student.year_of_study,
            latitude=student.latitude,
            longitude=student.longitude,
            interests=tuple(student.interest_list),
            available_from=student.available_from,
            available_to=student.available_to,
            max_price=float(student.max_price) if student.max_price is not None else None,
        )


# --------------------------------------------------------------------------- #
# Geo helpers
# --------------------------------------------------------------------------- #
def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points in kilometres."""
    p1, p2 = radians(lat1), radians(lat2)
    d_lat = p2 - p1
    d_lon = radians(lon2 - lon1)
    a = sin(d_lat / 2) ** 2 + cos(p1) * cos(p2) * sin(d_lon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * asin(sqrt(a))


def event_distance_km(student: StudentProfile, event) -> float | None:
    """Distance student -> event, or None when it cannot be computed.

    Online events have no physical distance, so they return None and are
    treated separately by the distance component.
    """
    if getattr(event, "is_online", False):
        return None
    if student.latitude is None or student.longitude is None:
        return None
    if event.latitude is None or event.longitude is None:
        return None
    return round(haversine_km(student.latitude, student.longitude, event.latitude, event.longitude), 3)


# --------------------------------------------------------------------------- #
# Hard filters - "can this student attend at all?"
# --------------------------------------------------------------------------- #
def is_eligible(student: StudentProfile, event, now: datetime) -> tuple[bool, str]:
    """Return (eligible, reason_if_not).

    An event is dropped entirely when:
      1. it has already started (you cannot attend the past),
      2. it is sold out (no free places left),
      3. it costs more than the student is willing to pay,
      4. it is targeted at a year of study that is not the student's.
    """
    if event.start_datetime <= now:
        return False, "event already started"

    if event.capacity > 0 and event.available_places <= 0:
        return False, "event is fully booked"

    price = float(event.price or 0)
    if student.max_price is not None and price > float(student.max_price):
        return False, "price above the student's maximum"

    audience = (event.target_audience or "").strip()
    if audience in YEAR_AUDIENCES and student.year_of_study is not None:
        if not YEAR_AUDIENCES[audience](student.year_of_study):
            return False, "event restricted to a different year of study"

    return True, ""


# --------------------------------------------------------------------------- #
# Scoring components
# --------------------------------------------------------------------------- #
def score_interest(student: StudentProfile, event) -> tuple[float, str]:
    """0-35 points.

    Exact category hit is worth full marks. A related category, or an interest
    keyword found in the title/description, earns partial credit so a student
    with narrow interests still receives useful suggestions.
    """
    interests = {i.strip().lower() for i in student.interests if i.strip()}
    if not interests:
        # No stated interests -> neutral, mid-range credit for everything.
        return W_INTEREST * 0.5, "is part of a balanced mix (no interests on file)"

    category = (event.category or "").strip()
    category_lc = category.lower()

    if category_lc in interests:
        return W_INTEREST, f"matches your {category} interest"

    related = {c.lower() for c in RELATED_CATEGORIES.get(category, set())}
    if related & interests:
        hit = sorted(related & interests)[0].title()
        return W_INTEREST * 0.55, f"is a {category} event, close to your {hit} interest"

    haystack = f"{event.title} {event.description}".lower()
    keyword_hits = [i for i in interests if len(i) > 3 and i in haystack]
    if keyword_hits:
        return W_INTEREST * 0.30, f"mentions {keyword_hits[0].title()} in its description"

    return 0.0, ""


def _to_minutes(t: time) -> int:
    return t.hour * 60 + t.minute


def score_time(student: StudentProfile, event) -> tuple[float, str]:
    """0-20 points, based on how much of the event fits the free time window.

    Fully inside the window -> 20. Partial overlap is scored proportionally to
    the share of the event the student could actually attend.
    """
    if student.available_from is None or student.available_to is None:
        return W_TIME * 0.5, ""

    win_start = _to_minutes(student.available_from)
    win_end = _to_minutes(student.available_to)
    if win_end <= win_start:  # window crossing midnight -> clamp to end of day
        win_end = 24 * 60

    ev_start = event.start_datetime.hour * 60 + event.start_datetime.minute
    ev_end = event.end_datetime.hour * 60 + event.end_datetime.minute
    if ev_end <= ev_start:  # event crossing midnight -> clamp to end of day
        ev_end = 24 * 60

    duration = max(ev_end - ev_start, 1)
    overlap = max(0, min(win_end, ev_end) - max(win_start, ev_start))

    if overlap == 0:
        return 0.0, ""

    ratio = overlap / duration
    if ratio >= 0.999:
        return W_TIME, "fits your available time"
    return round(W_TIME * ratio, 2), f"partly fits your available time ({int(ratio * 100)}%)"


def score_audience(student: StudentProfile, event) -> tuple[float, str]:
    """0-15 points for faculty / audience relevance."""
    audience = (event.target_audience or "").strip()

    if audience in YEAR_AUDIENCES:
        # Year mismatches were already removed by the hard filter, so reaching
        # this branch means the student is in the targeted year.
        return W_AUDIENCE, f"is aimed at {audience.lower()}"

    if student.faculty and audience.lower() == student.faculty.strip().lower():
        return W_AUDIENCE, f"is intended for {student.faculty} students"

    if audience in GENERAL_AUDIENCES:
        return W_AUDIENCE * 0.8, "is open to all students"

    if not audience:
        return W_AUDIENCE * 0.5, ""

    # Targeted at another faculty: still attendable, but clearly less relevant.
    return W_AUDIENCE * 0.2, ""


def score_distance(student: StudentProfile, distance_km: float | None, event) -> tuple[float, str]:
    """0-15 points. Online events get full marks - there is nothing to travel to."""
    if getattr(event, "is_online", False):
        return W_DISTANCE, "is online, so there is no travel"

    if distance_km is None:
        return W_DISTANCE * 0.5, ""

    if distance_km <= NEAR_KM:
        return W_DISTANCE, f"is very close to you ({distance_km:.2f} km)"

    if distance_km >= FAR_KM:
        return 0.0, ""

    factor = 1 - (distance_km - NEAR_KM) / (FAR_KM - NEAR_KM)
    points = round(W_DISTANCE * factor, 2)
    label = "is nearby" if factor >= 0.5 else "is still reachable"
    return points, f"{label} ({distance_km:.2f} km away)"


def score_price(student: StudentProfile, event) -> tuple[float, str]:
    """0-8 points. Free is best; paid events are scored against the budget."""
    price = float(event.price or 0)
    if price == 0:
        return W_PRICE, "is free to attend"

    budget = float(student.max_price) if student.max_price is not None else None
    if not budget:  # budget is 0 or unknown -> paid events were filtered out already
        return 0.0, ""

    # Half the points for being affordable, half scaled by how cheap it is.
    factor = 1 - (price / budget)
    return round(W_PRICE * (0.5 + 0.5 * factor), 2), f"is within your budget ({price:.0f} MKD)"


def score_capacity(event) -> tuple[float, str]:
    """0-7 points, based on the share of seats still available."""
    if not event.capacity:
        return W_CAPACITY * 0.5, ""

    free_ratio = event.available_places / event.capacity
    if free_ratio >= 0.5:
        return W_CAPACITY, "still has plenty of places"
    if free_ratio >= 0.2:
        return W_CAPACITY * 0.7, "still has places available"
    return W_CAPACITY * 0.4, f"is filling up fast ({event.available_places} places left)"


# --------------------------------------------------------------------------- #
# Reason text
# --------------------------------------------------------------------------- #
def build_reason(notes: Iterable[tuple[float, str]], score: int) -> str:
    """Compose a short human sentence from the strongest scoring components."""
    ranked = sorted(((pts, text) for pts, text in notes if text), key=lambda x: -x[0])
    parts = [text for _, text in ranked[:3]]
    if not parts:
        return f"Scored {score}/100 on the standard criteria."
    if len(parts) == 1:
        sentence = parts[0]
    else:
        sentence = ", ".join(parts[:-1]) + " and " + parts[-1]
    return sentence[0].upper() + sentence[1:] + "."


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #
def score_event(student: StudentProfile, event, now: datetime | None = None) -> ScoredEvent | None:
    """Score a single event, or return None when the student cannot attend it."""
    now = now or datetime.now()

    eligible, _ = is_eligible(student, event, now)
    if not eligible:
        return None

    distance_km = event_distance_km(student, event)

    interest_pts, interest_note = score_interest(student, event)
    time_pts, time_note = score_time(student, event)
    audience_pts, audience_note = score_audience(student, event)
    distance_pts, distance_note = score_distance(student, distance_km, event)
    price_pts, price_note = score_price(student, event)
    capacity_pts, capacity_note = score_capacity(event)

    breakdown = Breakdown(
        interest_match=round(interest_pts, 2),
        time_availability=round(time_pts, 2),
        audience_match=round(audience_pts, 2),
        distance=round(distance_pts, 2),
        price=round(price_pts, 2),
        capacity=round(capacity_pts, 2),
    )
    raw = breakdown.total
    score = int(round(raw))

    reason = build_reason(
        [
            (interest_pts, interest_note),
            (time_pts, time_note),
            (distance_pts, distance_note),
            (audience_pts, audience_note),
            (price_pts, price_note),
            (capacity_pts, capacity_note),
        ],
        score,
    )

    return ScoredEvent(
        event=event,
        score=score,
        raw_score=round(raw, 2),
        distance_km=distance_km,
        breakdown=breakdown,
        reason=reason,
    )


def recommend(
    student: StudentProfile,
    events: Iterable,
    *,
    limit: int | None = 20,
    min_score: float = 0.0,
    now: datetime | None = None,
) -> tuple[list[ScoredEvent], int]:
    """Score and rank every event for one student.

    Returns `(ranked_results, total_candidates)` where `total_candidates` is
    the number of events that passed the hard filters, before `limit` is
    applied.

    Ordering is fully deterministic: score desc, then the event that starts
    soonest, then the lowest event id as a final tie-breaker.
    """
    now = now or datetime.now()

    scored = [s for s in (score_event(student, e, now) for e in events) if s is not None]
    candidates = len(scored)

    scored = [s for s in scored if s.score >= min_score]
    scored.sort(key=lambda s: (-s.raw_score, s.event.start_datetime, s.event.id))

    if limit is not None:
        scored = scored[:limit]

    return scored, candidates
