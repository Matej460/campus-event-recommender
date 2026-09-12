"""`/recommendations` endpoints - the core of the system."""

from __future__ import annotations

from datetime import datetime, time

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app import crud
from app.database import get_db
from app.recommender import ScoredEvent, StudentProfile, recommend
from app.schemas import (
    RecommendationItem,
    RecommendationResponse,
    ScoreBreakdown,
)

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


def _to_item(scored: ScoredEvent) -> RecommendationItem:
    event = scored.event
    return RecommendationItem(
        event_id=event.id,
        title=event.title,
        category=event.category,
        organizer=event.organizer,
        location_name=event.location_name,
        start_datetime=event.start_datetime,
        end_datetime=event.end_datetime,
        distance_km=scored.distance_km,
        price=float(event.price or 0),
        available_places=event.available_places,
        is_online=event.is_online,
        target_audience=event.target_audience,
        score=scored.score,
        reason=scored.reason,
        score_breakdown=ScoreBreakdown(**scored.breakdown._asdict()),
    )


@router.get(
    "",
    response_model=RecommendationResponse,
    summary="Recommendations for an ad-hoc profile (no stored student needed)",
    description=(
        "Builds a temporary student profile from query parameters, which makes "
        "the recommender usable from a widget where the visitor is not logged in.\n\n"
        "`GET /recommendations?lat=42.0038&lon=21.4092&interests=Technology,Career`"
    ),
)
def get_recommendations_by_profile(
    lat: float | None = Query(None, ge=-90, le=90, description="Visitor latitude"),
    lon: float | None = Query(None, ge=-180, le=180, description="Visitor longitude"),
    interests: str | None = Query(None, description="Comma separated interests"),
    faculty: str | None = Query(None),
    year_of_study: int | None = Query(None, ge=1, le=8),
    available_from: time | None = Query(None, description="HH:MM"),
    available_to: time | None = Query(None, description="HH:MM"),
    max_price: float | None = Query(None, ge=0),
    limit: int = Query(20, ge=1, le=100),
    min_score: float = Query(0, ge=0, le=100),
    db: Session = Depends(get_db),
) -> RecommendationResponse:
    interest_tuple = tuple(
        part.strip() for part in (interests or "").split(",") if part.strip()
    )

    profile = StudentProfile(
        student_id=None,
        name=None,
        faculty=faculty,
        year_of_study=year_of_study,
        latitude=lat,
        longitude=lon,
        interests=interest_tuple,
        available_from=available_from,
        available_to=available_to,
        max_price=max_price,
    )

    events = crud.list_events(db, limit=500)
    scored, candidates = recommend(profile, events, limit=limit, min_score=min_score)

    return RecommendationResponse(
        student_id=None,
        student_name=None,
        generated_at=datetime.now(),
        total_candidates=candidates,
        returned=len(scored),
        recommendations=[_to_item(s) for s in scored],
    )


@router.get(
    "/{student_id}",
    response_model=RecommendationResponse,
    summary="Ranked recommendations for a stored student",
)
def get_recommendations_for_student(
    student_id: int,
    limit: int = Query(20, ge=1, le=100),
    min_score: float = Query(0, ge=0, le=100),
    category: str | None = Query(None, description="Restrict to one category"),
    free_only: bool = Query(False, description="Only free events"),
    db: Session = Depends(get_db),
) -> RecommendationResponse:
    student = crud.get_student(db, student_id)
    if student is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Student {student_id} not found")

    profile = StudentProfile.from_model(student)
    events = crud.list_events(db, category=category, free_only=free_only, limit=500)
    scored, candidates = recommend(profile, events, limit=limit, min_score=min_score)

    return RecommendationResponse(
        student_id=student.id,
        student_name=student.name,
        generated_at=datetime.now(),
        total_candidates=candidates,
        returned=len(scored),
        recommendations=[_to_item(s) for s in scored],
    )
