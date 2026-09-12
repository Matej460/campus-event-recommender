"""FastAPI application entry point.

Run with:
    uv run uvicorn app.main:app --reload
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.config import BASE_DIR, settings
from app.database import engine, init_db
from app.routers import events, recommendations, registrations, students


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables if they are missing. Seeding stays a separate, explicit
    # step (`scripts/seed_db.py`) so starting the API never rewrites data.
    init_db()
    yield
    engine.dispose()


app = FastAPI(
    title="Campus Event Recommendation System",
    description=(
        "Deterministic, rule-based recommender that ranks campus events for a "
        "student using interest match, time availability, faculty/audience fit, "
        "Haversine distance, price and remaining capacity. No machine learning."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(events.router)
app.include_router(students.router)
app.include_router(recommendations.router)
app.include_router(registrations.router)


@app.get("/health", tags=["meta"], summary="Liveness + database check")
def health() -> dict:
    from sqlalchemy import text

    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok", "database": "reachable"}


# --------------------------------------------------------------------------- #
# Serve the frontend from the same origin, so no CORS setup is needed in the
# common case: http://127.0.0.1:8000/app/index.html?student_id=1
# --------------------------------------------------------------------------- #
FRONTEND_DIR: Path = BASE_DIR / "frontend"
if FRONTEND_DIR.is_dir():
    app.mount("/app", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

    @app.get("/", include_in_schema=False, response_model=None)
    def root() -> RedirectResponse:
        return RedirectResponse(url="/app/index.html")

    @app.get("/favicon.ico", include_in_schema=False, response_model=None)
    def favicon():
        icon = FRONTEND_DIR / "favicon.svg"
        if icon.exists():
            return FileResponse(icon, media_type="image/svg+xml")
        return RedirectResponse(url="/app/index.html")
