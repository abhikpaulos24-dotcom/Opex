import logging
from collections.abc import Iterator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.paths import ROOT

from .models import Base

log = logging.getLogger(__name__)
settings = get_settings()

_is_sqlite = settings.sqlalchemy_url.startswith("sqlite")
engine = create_engine(
    settings.sqlalchemy_url,
    pool_pre_ping=True,
    # SQLite: allow use from FastAPI's thread pool. Supabase pooler: disable prepared statements.
    connect_args={"check_same_thread": False} if _is_sqlite else {"prepare_threshold": None},
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create tables. On Postgres/Supabase we run the same SQL scripts you can run by hand."""
    if _is_sqlite:
        Base.metadata.create_all(engine)
        log.info("database: local SQLite file (set DATABASE_URL to use Supabase)")
        return
    if inspect(engine).has_table("app_users"):
        log.info("database: Supabase/Postgres connected, tables present")
        return
    log.info("database: tables missing - running database/01_schema.sql and 02_security.sql")
    with engine.begin() as conn:
        for name in ("01_schema.sql", "02_security.sql"):
            conn.execute(text((ROOT / "database" / name).read_text()))
