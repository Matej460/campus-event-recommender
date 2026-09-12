"""Pydantic request/response schemas."""

from __future__ import annotations

from datetime import datetime, time

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


# --------------------------------------------------------------------------- #
# Events
# --------------------------------------------------------------------------- #
class EventBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str = ""
    category: str = Field(..., min_length=1, max_length=60)
    organizer: str = Field(..., min_length=1, max_length=160)
    location_name: str = Field(..., min_length=1, max_length=200)
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)
    start_datetime: datetime
    end_datetime: datetime
    capacity: int = Field(0, ge=0)
    registered_count: int = Field(0, ge=0)
    target_audience: str = "All Students"
    price: float = Field(0, ge=0)
    is_online: bool = False

    @field_validator("end_datetime")
    @classmethod
    def end_after_start(cls, v: datetime, info) -> datetime:
        start = info.data.get("start_datetime")
        if start and v < start:
            raise ValueError("end_datetime must not be earlier than start_datetime")
        return v


class EventCreate(EventBase):
    """Payload for POST /events."""


class EventRead(EventBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    available_places: int
    created_at: datetime
    updated_at: datetime


# --------------------------------------------------------------------------- #
# Students
# --------------------------------------------------------------------------- #
class StudentBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    email: EmailStr
    faculty: str = Field(..., min_length=1, max_length=120)
    year_of_study: int = Field(..., ge=1, le=8)
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    interests: list[str] = Field(default_factory=list)
    available_from: time
    available_to: time
    max_price: float = Field(0, ge=0)

    @field_validator("interests", mode="before")
    @classmethod
    def split_interests(cls, v):
        """Accept either a list or the comma separated string used in the DB."""
        if v is None:
            return []
        if isinstance(v, str):
            return [part.strip() for part in v.split(",") if part.strip()]
        return [str(part).strip() for part in v if str(part).strip()]


class StudentCreate(StudentBase):
    """Payload for POST /students."""


class StudentRead(StudentBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


# --------------------------------------------------------------------------- #
# Recommendations
# --------------------------------------------------------------------------- #
class ScoreBreakdown(BaseModel):
    """Per-component points, so the score is fully explainable."""

    interest_match: float
    time_availability: float
    audience_match: float
    distance: float
    price: float
    capacity: float


class RecommendationItem(BaseModel):
    event_id: int
    title: str
    category: str
    organizer: str
    location_name: str
    start_datetime: datetime
    end_datetime: datetime
    distance_km: float | None
    price: float
    available_places: int
    is_online: bool
    target_audience: str
    score: int
    reason: str
    score_breakdown: ScoreBreakdown


class RecommendationResponse(BaseModel):
    student_id: int | None
    student_name: str | None
    generated_at: datetime
    total_candidates: int
    returned: int
    recommendations: list[RecommendationItem]


# --------------------------------------------------------------------------- #
# Registrations (optional extension)
# --------------------------------------------------------------------------- #
class RegistrationCreate(BaseModel):
    student_id: int
    event_id: int


class RegistrationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    student_id: int
    event_id: int
    registration_datetime: datetime
    status: str
