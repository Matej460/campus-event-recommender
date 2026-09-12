#!/usr/bin/env python3
"""Live API smoke test - proof that every required endpoint works.

Start the API first, then run:

    uv run python scripts/api_smoke_test.py
    uv run python scripts/api_smoke_test.py --base-url http://127.0.0.1:8000

Every check prints PASS/FAIL with the request that was made, so the output can
be pasted straight into the technical documentation as test evidence.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import date

import requests

PASSED = 0
FAILED = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global PASSED, FAILED
    if condition:
        PASSED += 1
        print(f"  PASS  {label}")
    else:
        FAILED += 1
        print(f"  FAIL  {label}" + (f"  -> {detail}" if detail else ""))


def section(title: str) -> None:
    print()
    print(title)
    print("-" * len(title))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    print(f"Campus Event Recommendation System - API smoke test")
    print(f"Target: {base}")

    # ---------------------------------------------------------------- health
    section("GET /health")
    try:
        r = requests.get(f"{base}/health", timeout=10)
    except requests.RequestException as exc:
        print(f"  FAIL  cannot reach the API: {exc}")
        print("\nIs the server running?  uv run uvicorn app.main:app --reload")
        return 1
    check("status 200", r.status_code == 200, str(r.status_code))
    check("database reachable", r.json().get("database") == "reachable")

    # ---------------------------------------------------------------- events
    section("GET /events  (+ filters)")
    events = requests.get(f"{base}/events?limit=500").json()
    check("returns events", len(events) > 0, f"got {len(events)}")
    check("100+ events loaded", len(events) >= 100, f"got {len(events)}")

    tech = requests.get(f"{base}/events?category=Technology").json()
    check("?category=Technology", all(e["category"] == "Technology" for e in tech))

    sample_date = events[0]["start_datetime"][:10]
    by_date = requests.get(f"{base}/events?date={sample_date}").json()
    check(
        f"?date={sample_date}",
        all(e["start_datetime"].startswith(sample_date) for e in by_date),
    )

    free = requests.get(f"{base}/events?free_only=true").json()
    check("?free_only=true", all(float(e["price"]) == 0 for e in free))

    combo_url = f"{base}/events?category=Technology&date={sample_date}&free_only=true"
    combo = requests.get(combo_url).json()
    check(
        "combined category + date + free_only",
        all(
            e["category"] == "Technology"
            and e["start_datetime"].startswith(sample_date)
            and float(e["price"]) == 0
            for e in combo
        ),
        combo_url,
    )
    print(f"        -> {len(events)} total, {len(tech)} technology, "
          f"{len(free)} free, {len(combo)} combined")

    section("GET /events/{event_id}")
    one = requests.get(f"{base}/events/{events[0]['id']}")
    check("status 200", one.status_code == 200)
    check("correct event returned", one.json()["id"] == events[0]["id"])
    check("unknown id -> 404", requests.get(f"{base}/events/99999999").status_code == 404)

    # -------------------------------------------------------------- students
    section("GET /students")
    students = requests.get(f"{base}/students?limit=500").json()
    check("70-100 student profiles", 70 <= len(students) <= 200, f"got {len(students)}")
    check("interests are a list", isinstance(students[0]["interests"], list))
    check(
        "students have multiple interests",
        any(len(s["interests"]) >= 2 for s in students),
    )

    section("GET /students/{student_id}")
    one_student = requests.get(f"{base}/students/1")
    check("status 200", one_student.status_code == 200)
    check("unknown id -> 404", requests.get(f"{base}/students/99999999").status_code == 404)

    # ------------------------------------------------------------------ POST
    section("POST /students")
    new_student = {
        "name": "Smoke Test Student",
        "email": f"smoke.{uuid.uuid4().hex[:8]}@students.ukim.mk",
        "faculty": "Computer Science",
        "year_of_study": 2,
        "latitude": 41.998,
        "longitude": 21.425,
        "interests": ["Technology", "Career"],
        "available_from": "10:00",
        "available_to": "18:00",
        "max_price": 10,
    }
    created_student = requests.post(f"{base}/students", json=new_student)
    check("status 201", created_student.status_code == 201, created_student.text[:120])
    if created_student.status_code == 201:
        check(
            "multiple interests stored",
            created_student.json()["interests"] == ["Technology", "Career"],
        )

    section("POST /events")
    new_event = {
        "title": "Smoke Test Event",
        "description": "Created by scripts/api_smoke_test.py",
        "category": "Technology",
        "organizer": "QA",
        "location_name": "Faculty Lab 1",
        "latitude": 41.999,
        "longitude": 21.426,
        "start_datetime": f"{date.today().year}-12-20T14:00:00",
        "end_datetime": f"{date.today().year}-12-20T16:00:00",
        "capacity": 30,
        "registered_count": 0,
        "target_audience": "All Students",
        "price": 0,
        "is_online": False,
    }
    created_event = requests.post(f"{base}/events", json=new_event)
    check("status 201", created_event.status_code == 201, created_event.text[:120])
    if created_event.status_code == 201:
        check("available_places computed", created_event.json()["available_places"] == 30)

    # ------------------------------------------------------- recommendations
    section("GET /recommendations/{student_id}")
    reco = requests.get(f"{base}/recommendations/1?limit=10").json()
    items = reco["recommendations"]
    check("returns recommendations", len(items) > 0)
    check("student name present", bool(reco["student_name"]))

    required = {
        "event_id", "title", "category", "organizer", "location_name",
        "start_datetime", "end_datetime", "distance_km", "price",
        "available_places", "score", "reason",
    }
    check("response shape matches the brief", required <= set(items[0]))

    scores = [i["score"] for i in items]
    check("sorted by score descending", scores == sorted(scores, reverse=True), str(scores))
    check("scores within 0-100", all(0 <= s <= 100 for s in scores))
    check("every item has a reason", all(i["reason"] for i in items))
    check("no fully booked events", all(i["available_places"] > 0 for i in items))

    again = requests.get(f"{base}/recommendations/1?limit=10").json()["recommendations"]
    check(
        "deterministic (same request, same ranking)",
        [(i["event_id"], i["score"]) for i in items]
        == [(i["event_id"], i["score"]) for i in again],
    )

    check(
        "unknown student -> 404",
        requests.get(f"{base}/recommendations/99999999").status_code == 404,
    )

    section("GET /recommendations?lat=..&lon=..&interests=..")
    anon_url = (
        f"{base}/recommendations?lat=42.0038&lon=21.4092"
        f"&interests=Technology,Career&available_from=09:00&available_to=21:00&limit=5"
    )
    anon = requests.get(anon_url).json()
    check("status 200 + results", len(anon["recommendations"]) > 0, anon_url)
    check("student_id is null for an anonymous profile", anon["student_id"] is None)
    check(
        "top result matches the requested interests",
        anon["recommendations"][0]["category"] in {"Technology", "Career"},
        anon["recommendations"][0]["category"],
    )

    section("Example response (top recommendation for student 1)")
    print(json.dumps(items[0], indent=2, ensure_ascii=False))

    # --------------------------------------------------------------- summary
    print()
    print("=" * 60)
    print(f"  {PASSED} passed, {FAILED} failed")
    print("=" * 60)
    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
