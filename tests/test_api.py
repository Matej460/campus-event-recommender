"""Integration tests for the REST API.

These tests run against the seeded PostgreSQL database. Run the seed script
first:

    uv run python scripts/generate_students.py
    uv run python scripts/seed_db.py --reset
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


# --------------------------------------------------------------------------- #
# Meta
# --------------------------------------------------------------------------- #
def test_health_reports_database_reachable():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["database"] == "reachable"


def test_openapi_schema_is_served():
    assert client.get("/openapi.json").status_code == 200


# --------------------------------------------------------------------------- #
# GET /events
# --------------------------------------------------------------------------- #
def test_get_events_returns_a_list():
    response = client.get("/events")
    assert response.status_code == 200
    events = response.json()
    assert len(events) > 0
    assert {"id", "title", "category", "available_places"} <= set(events[0])


def test_filter_by_category():
    events = client.get("/events?category=Technology").json()
    assert events
    assert all(e["category"] == "Technology" for e in events)


def test_category_filter_is_case_insensitive():
    lower = client.get("/events?category=technology").json()
    upper = client.get("/events?category=Technology").json()
    assert [e["id"] for e in lower] == [e["id"] for e in upper]


def test_filter_by_date():
    all_events = client.get("/events?limit=500").json()
    target_date = all_events[0]["start_datetime"][:10]

    filtered = client.get(f"/events?date={target_date}").json()
    assert filtered
    assert all(e["start_datetime"].startswith(target_date) for e in filtered)


def test_filter_free_only():
    events = client.get("/events?free_only=true").json()
    assert events
    assert all(float(e["price"]) == 0 for e in events)


def test_combined_filters_apply_together():
    all_tech = client.get("/events?category=Technology&limit=500").json()
    target_date = all_tech[0]["start_datetime"][:10]

    combined = client.get(
        f"/events?category=Technology&date={target_date}&free_only=true"
    ).json()

    for event in combined:
        assert event["category"] == "Technology"
        assert event["start_datetime"].startswith(target_date)
        assert float(event["price"]) == 0

    # The combined result can never be larger than any single filter's result.
    assert len(combined) <= len(all_tech)


def test_combined_filters_that_match_nothing_return_empty_list():
    response = client.get("/events?category=Technology&date=1999-01-01")
    assert response.status_code == 200
    assert response.json() == []


def test_get_event_by_id():
    first = client.get("/events?limit=1").json()[0]
    response = client.get(f"/events/{first['id']}")
    assert response.status_code == 200
    assert response.json()["id"] == first["id"]


def test_get_unknown_event_returns_404():
    assert client.get("/events/99999999").status_code == 404


def test_categories_endpoint():
    categories = client.get("/events/categories").json()
    assert "Technology" in categories
    assert categories == sorted(categories)


# --------------------------------------------------------------------------- #
# GET /students
# --------------------------------------------------------------------------- #
def test_get_students():
    students = client.get("/students").json()
    assert len(students) >= 70  # the brief asks for 70-100 profiles
    assert isinstance(students[0]["interests"], list)


def test_students_support_multiple_interests():
    students = client.get("/students?limit=500").json()
    assert any(len(s["interests"]) >= 2 for s in students)


def test_get_student_by_id():
    response = client.get("/students/1")
    assert response.status_code == 200
    assert response.json()["id"] == 1


def test_get_unknown_student_returns_404():
    assert client.get("/students/99999999").status_code == 404


# --------------------------------------------------------------------------- #
# POST endpoints
# --------------------------------------------------------------------------- #
def test_post_student_creates_a_profile():
    payload = {
        "name": "Test Student",
        "email": f"test.{uuid.uuid4().hex[:8]}@students.ukim.mk",
        "faculty": "Computer Science",
        "year_of_study": 2,
        "latitude": 41.998,
        "longitude": 21.425,
        "interests": ["Technology", "Career"],
        "available_from": "10:00",
        "available_to": "18:00",
        "max_price": 10,
    }
    response = client.post("/students", json=payload)
    assert response.status_code == 201

    created = response.json()
    assert created["interests"] == ["Technology", "Career"]
    assert client.get(f"/students/{created['id']}").status_code == 200


def test_post_student_rejects_a_duplicate_email():
    existing = client.get("/students/1").json()
    payload = {
        "name": "Duplicate",
        "email": existing["email"],
        "faculty": "Computer Science",
        "year_of_study": 1,
        "latitude": 41.998,
        "longitude": 21.425,
        "interests": ["Technology"],
        "available_from": "10:00",
        "available_to": "18:00",
        "max_price": 0,
    }
    assert client.post("/students", json=payload).status_code == 409


def test_post_student_rejects_an_invalid_time_window():
    payload = {
        "name": "Backwards Window",
        "email": f"backwards.{uuid.uuid4().hex[:8]}@students.ukim.mk",
        "faculty": "Design",
        "year_of_study": 1,
        "latitude": 41.998,
        "longitude": 21.425,
        "interests": ["Art"],
        "available_from": "18:00",
        "available_to": "10:00",
        "max_price": 0,
    }
    assert client.post("/students", json=payload).status_code == 422


def test_post_event_creates_an_event():
    payload = {
        "title": "Test Event",
        "description": "Created by the integration test suite",
        "category": "Technology",
        "organizer": "QA Team",
        "location_name": "Faculty Lab 1",
        "latitude": 41.999,
        "longitude": 21.426,
        "start_datetime": "2026-12-20T14:00:00",
        "end_datetime": "2026-12-20T16:00:00",
        "capacity": 30,
        "registered_count": 0,
        "target_audience": "All Students",
        "price": 0,
        "is_online": False,
    }
    response = client.post("/events", json=payload)
    assert response.status_code == 201

    created = response.json()
    assert created["available_places"] == 30
    assert client.get(f"/events/{created['id']}").status_code == 200


def test_post_event_rejects_end_before_start():
    payload = {
        "title": "Broken Event",
        "description": "",
        "category": "Technology",
        "organizer": "QA Team",
        "location_name": "Faculty Lab 1",
        "latitude": 41.999,
        "longitude": 21.426,
        "start_datetime": "2026-12-20T16:00:00",
        "end_datetime": "2026-12-20T14:00:00",
        "capacity": 10,
        "registered_count": 0,
        "target_audience": "All Students",
        "price": 0,
        "is_online": False,
    }
    assert client.post("/events", json=payload).status_code == 422


# --------------------------------------------------------------------------- #
# GET /recommendations
# --------------------------------------------------------------------------- #
def test_recommendations_for_a_student():
    response = client.get("/recommendations/1")
    assert response.status_code == 200

    body = response.json()
    assert body["student_id"] == 1
    assert body["student_name"]
    assert body["recommendations"]

    first = body["recommendations"][0]
    expected = {
        "event_id", "title", "category", "organizer", "location_name",
        "start_datetime", "end_datetime", "distance_km", "price",
        "available_places", "score", "reason", "score_breakdown",
    }
    assert expected <= set(first)


def test_recommendations_are_sorted_by_score():
    body = client.get("/recommendations/1?limit=25").json()
    scores = [r["score"] for r in body["recommendations"]]
    assert scores == sorted(scores, reverse=True)


def test_recommendation_scores_stay_in_range():
    body = client.get("/recommendations/3?limit=50").json()
    assert all(0 <= r["score"] <= 100 for r in body["recommendations"])


def test_recommendations_never_include_a_full_or_past_event():
    body = client.get("/recommendations/5?limit=50").json()
    for item in body["recommendations"]:
        assert item["available_places"] > 0
        assert item["start_datetime"] > "2026-09-12"


def test_recommendations_respect_the_student_budget():
    student = client.get("/students/2").json()
    body = client.get("/recommendations/2?limit=50").json()
    for item in body["recommendations"]:
        assert float(item["price"]) <= float(student["max_price"])


def test_recommendations_are_repeatable():
    first = client.get("/recommendations/4?limit=10").json()["recommendations"]
    second = client.get("/recommendations/4?limit=10").json()["recommendations"]
    assert [(r["event_id"], r["score"]) for r in first] == [
        (r["event_id"], r["score"]) for r in second
    ]


def test_recommendations_limit_is_honoured():
    body = client.get("/recommendations/1?limit=5").json()
    assert len(body["recommendations"]) <= 5
    assert body["returned"] == len(body["recommendations"])


def test_recommendations_can_be_filtered_by_category():
    body = client.get("/recommendations/1?category=Technology&limit=50").json()
    assert all(r["category"] == "Technology" for r in body["recommendations"])


def test_recommendations_for_unknown_student_returns_404():
    assert client.get("/recommendations/99999999").status_code == 404


def test_anonymous_recommendations_by_query_parameters():
    response = client.get(
        "/recommendations"
        "?lat=42.0038&lon=21.4092&interests=Technology,Career"
        "&available_from=09:00&available_to=21:00&limit=5"
    )
    assert response.status_code == 200

    body = response.json()
    assert body["student_id"] is None
    assert body["recommendations"]
    assert all(0 <= r["score"] <= 100 for r in body["recommendations"])


def test_anonymous_recommendations_reflect_the_interests_given():
    tech = client.get("/recommendations?lat=42.0038&lon=21.4092&interests=Technology&limit=5").json()
    art = client.get("/recommendations?lat=42.0038&lon=21.4092&interests=Art&limit=5").json()
    assert tech["recommendations"][0]["category"] == "Technology"
    assert art["recommendations"][0]["category"] == "Art"


def test_score_breakdown_sums_to_the_total():
    body = client.get("/recommendations/1?limit=10").json()
    for item in body["recommendations"]:
        total = sum(item["score_breakdown"].values())
        assert item["score"] == pytest.approx(total, abs=0.5)


# --------------------------------------------------------------------------- #
# Registrations (optional extension)
# --------------------------------------------------------------------------- #
def test_registration_flow():
    event_payload = {
        "title": "Registration Test Event",
        "description": "",
        "category": "Workshop",
        "organizer": "QA Team",
        "location_name": "Library",
        "latitude": 41.999,
        "longitude": 21.426,
        "start_datetime": "2026-12-22T10:00:00",
        "end_datetime": "2026-12-22T12:00:00",
        "capacity": 2,
        "registered_count": 0,
        "target_audience": "All Students",
        "price": 0,
        "is_online": False,
    }
    event_id = client.post("/events", json=event_payload).json()["id"]

    created = client.post("/registrations", json={"student_id": 1, "event_id": event_id})
    assert created.status_code == 201
    assert created.json()["status"] == "registered"

    # The seat count must have gone down.
    assert client.get(f"/events/{event_id}").json()["available_places"] == 1

    # Registering twice is a conflict.
    duplicate = client.post("/registrations", json={"student_id": 1, "event_id": event_id})
    assert duplicate.status_code == 409


def test_registration_for_unknown_event_returns_404():
    response = client.post("/registrations", json={"student_id": 1, "event_id": 99999999})
    assert response.status_code == 404
