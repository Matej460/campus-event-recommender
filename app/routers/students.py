"""`/students` endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app import crud
from app.database import get_db
from app.schemas import StudentCreate, StudentRead

router = APIRouter(prefix="/students", tags=["students"])


@router.get("", response_model=list[StudentRead], summary="List student profiles")
def get_students(
    faculty: str | None = Query(None, description="Exact faculty, case-insensitive"),
    year_of_study: int | None = Query(None, ge=1, le=8),
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> list[StudentRead]:
    students = crud.list_students(
        db, faculty=faculty, year_of_study=year_of_study, limit=limit, offset=offset
    )
    return [StudentRead.model_validate(s) for s in students]


@router.get("/{student_id}", response_model=StudentRead, summary="Get a single student")
def get_student(student_id: int, db: Session = Depends(get_db)) -> StudentRead:
    student = crud.get_student(db, student_id)
    if student is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Student {student_id} not found")
    return StudentRead.model_validate(student)


@router.post(
    "",
    response_model=StudentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a student profile",
)
def post_student(payload: StudentCreate, db: Session = Depends(get_db)) -> StudentRead:
    if crud.get_student_by_email(db, payload.email) is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail=f"Student with email {payload.email} already exists"
        )
    if payload.available_to <= payload.available_from:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="available_to must be later than available_from",
        )

    data = payload.model_dump()
    # The DB stores interests as a normalised comma separated string.
    data["interests"] = ",".join(data.pop("interests"))
    data["email"] = str(data["email"])

    student = crud.create_student(db, data)
    return StudentRead.model_validate(student)
