"""Settings come from environment variables (or the .env file at the repo root).

Everything optional has a safe default so the app runs on a laptop with zero keys.
See AUDIT.md for what each value is and where to get it.
"""

import logging
import os
import secrets
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from .paths import DATA_DIR, ROOT

log = logging.getLogger(__name__)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    # --- App ---
    env: str = "development"  # "production" on Cloud Run
    log_level: str = "INFO"
    secret_key: str = ""  # signs login sessions
    cors_origins: str = "http://localhost:5173"

    # --- Database (Supabase Postgres). Empty = local SQLite file. ---
    database_url: str = ""

    # --- Demo behaviour ---
    demo_mode: bool = True  # seed demo users + show demo controls
    demo_password: str = "OpEx-demo-2026"
    allow_signup: bool = True
    live_plant_speed: float = 10.0  # plant minutes per real minute

    # --- Gemini (Vertex AI or Gemini API key) ---
    google_genai_use_vertexai: bool = False
    google_cloud_project: str = ""
    google_cloud_location: str = "global"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash-lite"  # the free tier allows far more calls than 3.8-flash
    gemini_fast_model: str = "gemini-3.5-flash-lite"
    gemini_embedding_model: str = "gemini-embedding-001"
    google_application_credentials: str = ""  # service-account JSON path (local runs only)

    # --- Optional Google Cloud services ---
    bigquery_dataset: str = ""
    bigquery_location: str = "asia-south1"
    gcs_bucket: str = ""
    pubsub_alerts_topic: str = ""
    ingest_api_key: str = ""  # protects POST /api/ingest/readings

    @property
    def is_production(self) -> bool:
        return self.env.lower() == "production"

    @property
    def sqlalchemy_url(self) -> str:
        if not self.database_url:
            return f"sqlite:///{DATA_DIR / 'opex.db'}"
        # Supabase gives "postgresql://..."; SQLAlchemy needs the psycopg 3 driver name.
        url = self.database_url
        for prefix in ("postgres://", "postgresql://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url[len(prefix) :]
        return url

    @property
    def gemini_enabled(self) -> bool:
        if self.google_genai_use_vertexai:
            return bool(self.google_cloud_project)
        return bool(self.gemini_api_key)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    if settings.google_application_credentials:  # Google client libraries read this from the environment
        os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", settings.google_application_credentials)
    if not settings.secret_key:
        if settings.is_production:
            raise RuntimeError("SECRET_KEY must be set in production (see AUDIT.md, step 1).")
        settings.secret_key = secrets.token_urlsafe(32)
        log.warning("SECRET_KEY not set - using a temporary key; everyone is logged out on restart.")
    return settings
