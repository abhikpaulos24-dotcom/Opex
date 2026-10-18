import logging
from collections.abc import Iterator
from urllib.parse import urlsplit

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.paths import ROOT

from .models import Base

log = logging.getLogger(__name__)
settings = get_settings()


def _make_engine(url: str):
    sqlite = url.startswith("sqlite")
    return create_engine(
        url,
        pool_pre_ping=True,
        # SQLite: allow use from FastAPI's thread pool. Supabase pooler: no prepared statements, don't hang forever.
        connect_args={"check_same_thread": False} if sqlite else {"prepare_threshold": None, "connect_timeout": 8},
    )


def _unreachable_message(url: str, err: OperationalError) -> str:
    host = urlsplit(url).hostname
    reason = str(err.orig).strip().splitlines()[0] if err.orig else "unknown reason"
    return (
        f"Cannot reach the database at {host} ({reason}). In Supabase open your project, click Connect and copy the "
        "'Session pooler' address into DATABASE_URL (it works on every network). If the project is paused, restore it "
        "from the Supabase dashboard. See AUDIT.md, step 2."
    )


engine = _make_engine(settings.sqlalchemy_url)
if not settings.sqlalchemy_url.startswith("sqlite"):
    try:
        with engine.connect():
            pass
    except OperationalError as err:
        message = _unreachable_message(settings.sqlalchemy_url, err)
        if settings.is_production:
            raise RuntimeError(message) from err
        # Working on your own computer: keep going with the local file rather than failing to start.
        log.error("%s Using the local SQLite file for this run instead (changes will not reach Supabase).", message)
        engine = _make_engine(settings.local_database_url)
_is_sqlite = engine.dialect.name == "sqlite"
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
