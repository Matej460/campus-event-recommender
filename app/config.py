"""Application configuration loaded from environment variables / .env file."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

# Project root = one level above the `app` package.
BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env from the project root. Values already present in the real
# environment win over the file, which is what we want in CI / Docker.
load_dotenv(BASE_DIR / ".env", override=False)


class Settings:
    """Plain settings object - no external settings library required."""

    def __init__(self) -> None:
        self.postgres_host: str = os.getenv("POSTGRES_HOST", "localhost")
        self.postgres_port: str = os.getenv("POSTGRES_PORT", "5432")
        self.postgres_db: str = os.getenv("POSTGRES_DB", "campus_events")
        self.postgres_user: str = os.getenv("POSTGRES_USER", "campus")
        self.postgres_password: str = os.getenv("POSTGRES_PASSWORD", "campus")

        self.app_host: str = os.getenv("APP_HOST", "127.0.0.1")
        self.app_port: int = int(os.getenv("APP_PORT", "8000"))

        raw_origins = os.getenv("CORS_ORIGINS", "*")
        self.cors_origins: list[str] = [
            origin.strip() for origin in raw_origins.split(",") if origin.strip()
        ] or ["*"]

        self.events_csv: Path = BASE_DIR / os.getenv(
            "EVENTS_CSV", "data/raw/campus_events_skopje.csv"
        )
        self.students_csv: Path = BASE_DIR / os.getenv(
            "STUDENTS_CSV", "data/students.csv"
        )
        self.random_seed: int = int(os.getenv("RANDOM_SEED", "42"))

    @property
    def database_url(self) -> str:
        """Full SQLAlchemy connection string.

        `DATABASE_URL` takes precedence so the app can be pointed at any
        PostgreSQL instance (local install, Docker, or a managed service)
        without touching the individual variables.
        """
        explicit = os.getenv("DATABASE_URL")
        if explicit:
            return explicit
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def safe_database_url(self) -> str:
        """Connection string with the password masked, safe for logging."""
        url = self.database_url
        if "://" not in url or "@" not in url:
            return url
        scheme, rest = url.split("://", 1)
        credentials, host_part = rest.rsplit("@", 1)
        user = credentials.split(":", 1)[0]
        return f"{scheme}://{user}:***@{host_part}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
