# Test Evidence

Generated on the seeded database (90 students, 100 events).

## 1. Automated test suite (`pytest`)

```text
.....................................................................    [100%]
69 passed in 1.00s
```

## 2. Test list

```text
tests/test_api.py::test_health_reports_database_reachable
tests/test_api.py::test_openapi_schema_is_served
tests/test_api.py::test_get_events_returns_a_list
tests/test_api.py::test_filter_by_category
tests/test_api.py::test_category_filter_is_case_insensitive
tests/test_api.py::test_filter_by_date
tests/test_api.py::test_filter_free_only
tests/test_api.py::test_combined_filters_apply_together
tests/test_api.py::test_combined_filters_that_match_nothing_return_empty_list
tests/test_api.py::test_get_event_by_id
tests/test_api.py::test_get_unknown_event_returns_404
tests/test_api.py::test_categories_endpoint
tests/test_api.py::test_get_students
tests/test_api.py::test_students_support_multiple_interests
tests/test_api.py::test_get_student_by_id
tests/test_api.py::test_get_unknown_student_returns_404
tests/test_api.py::test_post_student_creates_a_profile
tests/test_api.py::test_post_student_rejects_a_duplicate_email
tests/test_api.py::test_post_student_rejects_an_invalid_time_window
tests/test_api.py::test_post_event_creates_an_event
tests/test_api.py::test_post_event_rejects_end_before_start
tests/test_api.py::test_recommendations_for_a_student
tests/test_api.py::test_recommendations_are_sorted_by_score
tests/test_api.py::test_recommendation_scores_stay_in_range
tests/test_api.py::test_recommendations_never_include_a_full_or_past_event
tests/test_api.py::test_recommendations_respect_the_student_budget
tests/test_api.py::test_recommendations_are_repeatable
tests/test_api.py::test_recommendations_limit_is_honoured
tests/test_api.py::test_recommendations_can_be_filtered_by_category
tests/test_api.py::test_recommendations_for_unknown_student_returns_404
tests/test_api.py::test_anonymous_recommendations_by_query_parameters
tests/test_api.py::test_anonymous_recommendations_reflect_the_interests_given
tests/test_api.py::test_score_breakdown_sums_to_the_total
tests/test_api.py::test_registration_flow
tests/test_api.py::test_registration_for_unknown_event_returns_404
tests/test_recommender.py::test_haversine_zero_distance
tests/test_recommender.py::test_haversine_known_distance
tests/test_recommender.py::test_haversine_is_symmetric
tests/test_recommender.py::test_online_event_has_no_distance
tests/test_recommender.py::test_past_event_is_not_eligible
tests/test_recommender.py::test_full_event_is_not_eligible
tests/test_recommender.py::test_too_expensive_event_is_not_eligible
tests/test_recommender.py::test_wrong_year_audience_is_not_eligible
tests/test_recommender.py::test_matching_year_audience_is_eligible
tests/test_recommender.py::test_exact_category_gets_full_interest_points
tests/test_recommender.py::test_related_category_gets_partial_points
tests/test_recommender.py::test_unrelated_category_scores_zero
tests/test_recommender.py::test_keyword_in_description_earns_partial_credit
tests/test_recommender.py::test_student_without_interests_gets_neutral_points
tests/test_recommender.py::test_event_fully_inside_window_gets_full_points
tests/test_recommender.py::test_event_outside_window_scores_zero
tests/test_recommender.py::test_partial_overlap_is_proportional
tests/test_recommender.py::test_own_faculty_beats_all_students
tests/test_recommender.py::test_very_close_event_gets_full_distance_points
tests/test_recommender.py::test_distance_decays_with_kilometres
tests/test_recommender.py::test_online_event_gets_full_distance_points
tests/test_recommender.py::test_free_event_gets_full_price_points
tests/test_recommender.py::test_cheaper_event_scores_higher_than_expensive_one
tests/test_recommender.py::test_capacity_points_drop_as_the_event_fills_up
tests/test_recommender.py::test_perfect_event_scores_100
tests/test_recommender.py::test_score_never_exceeds_bounds
tests/test_recommender.py::test_ineligible_event_returns_none
tests/test_recommender.py::test_breakdown_sums_to_raw_score
tests/test_recommender.py::test_reason_is_a_sentence
tests/test_recommender.py::test_results_are_sorted_by_score_descending
tests/test_recommender.py::test_recommendation_is_deterministic
tests/test_recommender.py::test_limit_and_min_score_are_applied
tests/test_recommender.py::test_ties_break_on_earlier_start_then_id
tests/test_recommender.py::test_anonymous_profile_still_produces_recommendations

69 tests collected in 0.54s
```

## 3. Live API smoke test (`scripts/api_smoke_test.py`)

```text
Campus Event Recommendation System - API smoke test
Target: http://127.0.0.1:8000

GET /health
-----------
  PASS  status 200
  PASS  database reachable

GET /events  (+ filters)
------------------------
  PASS  returns events
  PASS  100+ events loaded
  PASS  ?category=Technology
  PASS  ?date=2026-09-21
  PASS  ?free_only=true
  PASS  combined category + date + free_only
        -> 102 total, 13 technology, 94 free, 0 combined

GET /events/{event_id}
----------------------
  PASS  status 200
  PASS  correct event returned
  PASS  unknown id -> 404

GET /students
-------------
  PASS  70-100 student profiles
  PASS  interests are a list
  PASS  students have multiple interests

GET /students/{student_id}
--------------------------
  PASS  status 200
  PASS  unknown id -> 404

POST /students
--------------
  PASS  status 201
  PASS  multiple interests stored

POST /events
------------
  PASS  status 201
  PASS  available_places computed

GET /recommendations/{student_id}
---------------------------------
  PASS  returns recommendations
  PASS  student name present
  PASS  response shape matches the brief
  PASS  sorted by score descending
  PASS  scores within 0-100
  PASS  every item has a reason
  PASS  no fully booked events
  PASS  deterministic (same request, same ranking)
  PASS  unknown student -> 404

GET /recommendations?lat=..&lon=..&interests=..
-----------------------------------------------
  PASS  status 200 + results
  PASS  student_id is null for an anonymous profile
  PASS  top result matches the requested interests

Example response (top recommendation for student 1)
---------------------------------------------------
{
  "event_id": 3,
  "title": "Cybersecurity Basics for Students",
  "category": "Technology",
  "organizer": "Skopje Tech Community",
  "location_name": "Public Room Skopje",
  "start_datetime": "2026-09-27T12:00:00",
  "end_datetime": "2026-09-27T13:00:00",
  "distance_km": 0.278,
  "price": 0.0,
  "available_places": 26,
  "is_online": false,
  "target_audience": "Computer Science",
  "score": 100,
  "reason": "Matches your Technology interest, fits your available time and is very close to you (0.28 km).",
  "score_breakdown": {
    "interest_match": 35.0,
    "time_availability": 20.0,
    "audience_match": 15.0,
    "distance": 15.0,
    "price": 8.0,
    "capacity": 7.0
  }
}

============================================================
  32 passed, 0 failed
============================================================
```

## 4. Frontend testing

The frontend was driven with a headless Chromium script (Playwright) against the running API.
Screenshots in `docs/screenshots/` are the captured output:

| File | What it shows |
|---|---|
| `01-recommendations-desktop.png` | Ranked recommendation cards, desktop width |
| `02-score-breakdown.png` | One card with the per-component score breakdown expanded |
| `03-events-filtered.png` | `All events` tab with `category=Technology` + `free_only=true` |
| `04-empty-state.png` | Empty state when the filter combination matches nothing |
| `05-recommendations-mobile.png` | Same page at 390 px (mobile) |
| `06-error-state.png` | Error state when the API cannot be reached |

Checks performed during that run:

- page loads with **0 console errors**
- student selector is populated from `GET /students` and `?student_id=1` is honoured
- category + free-only filters produced 12 events on the `All events` tab
- an impossible filter combination (`date=1999-01-01`) showed the empty state
- pointing the page at a dead API (`?api=http://127.0.0.1:9999`) showed the error state
