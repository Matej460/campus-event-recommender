"""`/registrations` endpoints - optional extension beyond the required scope."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app import crud
from app.database import get_db
from app.schemas import RegistrationCreate, RegistrationRead

router = APIRouter(prefix="/registrations", tags=["registrations"])


@router.get("", response_model=list[RegistrationRead], summary="List registrations")
def get_registrations(
    student_id: int | None = Query(None), db: Session = Depends(get_db)
) -> list[RegistrationRead]:
    return [
        RegistrationRead.model_validate(r)
        for r in crud.list_registrations(db, student_id=student_id)
    ]


@router.post(
    "",
    response_model=RegistrationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register a student for an event",
)
def post_registration(
    payload: RegistrationCreate, db: Session = Depends(get_db)
) -> RegistrationRead:
    student = crud.get_student(db, payload.student_id)
    if student is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Student not found")

    event = crud.get_event(db, payload.event_id)
    if event is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Event not found")

    if event.capacity and event.available_places <= 0:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Event is fully booked")

    if crud.get_registration(db, payload.student_id, payload.event_id) is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="Student is already registered for this event"
        )

    registration = crud.create_registration(db, payload.student_id, payload.event_id)
    return RegistrationRead.model_validate(registration)
