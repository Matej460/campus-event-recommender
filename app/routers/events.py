"""`/events` endpoints."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app import crud
from app.database import get_db
from app.schemas import EventCreate, EventRead

router = APIRouter(prefix="/events", tags=["events"])


@router.get(
    "",
    response_model=list[EventRead],
    summary="List events with optional filters",
    description=(
        "Filters are combinable and applied with AND:\n\n"
        "- `GET /events?category=Technology`\n"
        "- `GET /events?date=2026-09-23`\n"
        "- `GET /events?free_only=true`\n"
        "- `GET /events?category=Technology&date=2026-09-23&free_only=true`"
    ),
)
def get_events(
    category: str | None = Query(None, description="Exact category, case-insensitive"),
    date_: date | None = Query(None, alias="date", description="Events starting on this day"),
    free_only: bool = Query(False, description="Only events with price = 0"),
    is_online: bool | None = Query(None, description="Filter online / on-site events"),
    search: str | None = Query(None, min_length=2, description="Text search in title/description"),
    upcoming_only: bool = Query(False, description="Hide events that already started"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> list[EventRead]:
    events = crud.list_events(
        db,
        category=category,
        event_date=date_,
        free_only=free_only,
        is_online=is_online,
        search=search,
        upcoming_only=upcoming_only,
        limit=limit,
        offset=offset,
    )
    return [EventRead.model_validate(e) for e in events]


@router.get("/categories", response_model=list[str], summary="Distinct event categories")
def get_categories(db: Session = Depends(get_db)) -> list[str]:
    """Used by the frontend to populate the category filter dropdown."""
    return crud.list_event_categories(db)


@router.get("/{event_id}", response_model=EventRead, summary="Get a single event")
def get_event(event_id: int, db: Session = Depends(get_db)) -> EventRead:
    event = crud.get_event(db, event_id)
    if event is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Event {event_id} not found")
    return EventRead.model_validate(event)


@router.post(
    "",
    response_model=EventRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create an event",
)
def post_event(payload: EventCreate, db: Session = Depends(get_db)) -> EventRead:
    if payload.registered_count > payload.capacity > 0:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="registered_count cannot exceed capacity",
        )
    event = crud.create_event(db, payload.model_dump())
    return EventRead.model_validate(event)
