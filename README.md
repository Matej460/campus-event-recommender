# Campus Event Recommendation System

A deterministic, explainable recommendation system that suggests campus events
to students. Built with **FastAPI**, **PostgreSQL**, **SQLAlchemy** and a
plain HTML/CSS/JS frontend. **No machine learning** — every score comes from
rules that can be read, explained and defended.

![Recommendations](docs/screenshots/01-recommendations-desktop.png)

---

## Contents

- [What it does](#what-it-does)
- [Quick start](#quick-start)
- [Project structure](#project-structure)
- [API reference](#api-reference)
- [Recommendation scoring](#recommendation-scoring)
- [Datasets](#datasets)
- [Testing](#testing)
- [Documentation](#documentation)

---

## What it does

Students miss campus events because the information is scattered across
emails, posters, social media and faculty websites. This system collects
events in one database and ranks them for each student using six factors:

| Factor | Weight | Question it answers |
|---|---:|---|
| Interest match | 35 | Does the category match what the student cares about? |
| Time availability | 20 | Does it fit the hours the student is free? |
| Audience / faculty | 15 | Is it meant for this student's faculty or year? |
| Distance | 15 | How far is it (Haversine), and is it online? |
| Price | 8 | Is it free, or affordable within the student's budget? |
| Capacity | 7 | Are there still places left? |
| **Total** | **100** | |

Each recommendation comes back with a **score**, a **per-component breakdown**
and a **plain-language reason** such as:

> *Matches your Technology interest, fits your available time and is very close to you (0.28 km).*

---

## Quick start

### Requirements

- Python 3.11+
- PostgreSQL 14+ running locally
- [uv](https://docs.astral.sh/uv/) (`pip install uv` if you do not have it)

### 1. Create the database

```bash
sudo -u postgres psql -c "CREATE USER campus WITH PASSWORD 'campus';"
sudo -u postgres psql -c "CREATE DATABASE campus_events OWNER campus;"
```

On Windows, use pgAdmin or the `psql` shell that ships with PostgreSQL and run
the same two statements.

### 2. Configure the connection

```bash
cp .env.example .env
```

Edit `.env` if your PostgreSQL user, password or port differ:

```ini
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=campus_events
POSTGRES_USER=campus
POSTGRES_PASSWORD=campus
```

> A single `DATABASE_URL=postgresql+psycopg2://user:pass@host:port/db` also
> works and overrides the individual variables.

### 3. Install dependencies

```bash
uv venv
uv pip install -e ".[dev]"
```

### 4. Load the data

```bash
uv run python scripts/generate_students.py    # writes data/students.csv (90 profiles)
uv run python scripts/seed_db.py --reset      # creates tables + loads 100 events and 90 students
```

Expected output:

```text
Events: 100 valid rows, 0 rejected (data/raw/campus_events_skopje.csv)
Students: 90 valid rows, 0 rejected (data/students.csv)
Done. students=90  events=100  registrations=0
```

### 5. Run the API

```bash
uv run uvicorn app.main:app --reload
```

| URL | What it is |
|---|---|
| <http://127.0.0.1:8000/app/index.html?student_id=1> | The frontend |
| <http://127.0.0.1:8000/docs> | Swagger UI (interactive API docs) |
| <http://127.0.0.1:8000/health> | Health check |

The frontend is served by the same FastAPI app, so there is nothing else to
start and no CORS configuration to worry about.

---

## Project structure

```text
campus-event-recommender/
├── app/
│   ├── config.py             # .env loading, database URL
│   ├── database.py           # SQLAlchemy engine, session, Base
│   ├── models.py             # students, events, event_registrations
│   ├── schemas.py            # Pydantic request/response models
│   ├── crud.py               # queries (all of them skip soft-deleted rows)
│   ├── recommender.py        # ← the scoring engine
│   ├── main.py               # FastAPI app, CORS, static frontend
│   └── routers/
│       ├── events.py
│       ├── students.py
│       ├── recommendations.py
│       └── registrations.py
├── data/
│   ├── raw/campus_events_skopje.csv
│   └── students.csv          # generated
├── scripts/
│   ├── generate_students.py  # synthetic student profiles
│   ├── seed_db.py            # clean + validate + load into PostgreSQL
│   └── api_smoke_test.py     # live end-to-end check of every endpoint
├── frontend/
│   ├── index.html
│   ├── styles.css
│   └── app.js
├── tests/
│   ├── test_recommender.py   # unit tests, no database needed
│   └── test_api.py           # integration tests against the API
└── docs/
    ├── technical_documentation.md
    ├── test-evidence.md
    └── screenshots/
```

---

## API reference

### Events

| Method | Path | Description |
|---|---|---|
| `GET` | `/events` | List events, with filters |
| `GET` | `/events/{event_id}` | One event |
| `GET` | `/events/categories` | Distinct categories (used by the frontend) |
| `POST` | `/events` | Create an event |

Filters on `GET /events` combine with AND:

```text
GET /events?category=Technology
GET /events?date=2026-09-23
GET /events?free_only=true
GET /events?category=Technology&date=2026-09-23&free_only=true
GET /events?search=python&is_online=false&upcoming_only=true&limit=20&offset=0
```

### Students

| Method | Path | Description |
|---|---|---|
| `GET` | `/students` | List profiles (`?faculty=`, `?year_of_study=`) |
| `GET` | `/students/{student_id}` | One profile |
| `POST` | `/students` | Create a profile |

### Recommendations

| Method | Path | Description |
|---|---|---|
| `GET` | `/recommendations/{student_id}` | Ranked events for a stored student |
| `GET` | `/recommendations?lat=&lon=&interests=` | Ranked events for an ad-hoc profile |

```text
GET /recommendations/1?limit=10&min_score=60&category=Technology&free_only=true
GET /recommendations?lat=42.0038&lon=21.4092&interests=Technology,Career&available_from=09:00&available_to=21:00
```

Response:

```json
{
  "student_id": 1,
  "student_name": "Marko Cvetkov",
  "generated_at": "2026-09-12T21:00:00",
  "total_candidates": 79,
  "returned": 1,
  "recommendations": [
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
  ]
}
```

### Registrations (optional extension)

| Method | Path | Description |
|---|---|---|
| `GET` | `/registrations?student_id=` | List registrations |
| `POST` | `/registrations` | Register a student (increments `registered_count`) |

---

## Recommendation scoring

Two stages, in this order:

**1. Hard filters** remove events the student *cannot* attend:

- the event has already started
- it is fully booked
- it costs more than the student's `max_price`
- it is restricted to a different year of study

**2. Weighted scoring** ranks whatever is left, out of 100 points. Ties break
on the earlier start time, then the lower event id — so the same request always
returns the same ranking.

The full reasoning behind each weight, threshold and special case is in
[`docs/technical_documentation.md`](docs/technical_documentation.md), and the
implementation lives in a single readable file:
[`app/recommender.py`](app/recommender.py).

---

## Datasets

| File | Rows | Source |
|---|---:|---|
| `data/raw/campus_events_skopje.csv` | 100 | Provided with the project brief |
| `data/students.csv` | 90 | Generated by `scripts/generate_students.py` |

The student generator is seeded (`RANDOM_SEED`, default `42`), so everyone who
runs it gets the same dataset. Each student has **2–4 interests**, weighted
toward their faculty with one cross-faculty wildcard.

`scripts/seed_db.py` cleans and validates every row before inserting:
whitespace and encoding are normalised, numbers/dates/booleans are parsed with
several accepted formats, coordinates are range-checked, `registered_count` is
clamped to `capacity`, and duplicate ids are skipped. Rejected rows are
reported with their line number instead of aborting the import.

```bash
uv run python scripts/seed_db.py --dry-run   # validate without writing
```

---

## Testing

```bash
uv run pytest                            # 69 tests
uv run python scripts/api_smoke_test.py  # 32 live endpoint checks
```

- `tests/test_recommender.py` — unit tests for the scoring engine (no database)
- `tests/test_api.py` — integration tests for every endpoint and filter
- `scripts/api_smoke_test.py` — end-to-end proof against a running server

Captured results and frontend screenshots:
[`docs/test-evidence.md`](docs/test-evidence.md).

---

## Documentation

- [`docs/technical_documentation.md`](docs/technical_documentation.md) — architecture, database design, scoring justification
- [`docs/test-evidence.md`](docs/test-evidence.md) — test output and screenshots

---

## Notes

- No authentication — the brief does not require it.
- The system runs entirely locally.
- Rows are **soft deleted** (`deleted_at`); every query filters them out.
