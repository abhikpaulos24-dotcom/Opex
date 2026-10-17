"""OpEx - one FastAPI service that serves the API and the web app (one Cloud Run service)."""

import logging
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import actions, admin, auth, copilot, data, factory, simulation
from app.core.config import get_settings
from app.core.logging_setup import setup_logging
from app.core.paths import FRONTEND_DIST
from app.db.seed import seed
from app.db.session import SessionLocal, init_db

settings = get_settings()
setup_logging(settings.log_level, json_logs=settings.is_production)
log = logging.getLogger("opex")


def _warm_up() -> None:
    """Load models and compute the first overview so the first visitor doesn't wait."""
    from app.analytics.factory_report import factory_report

    started = time.perf_counter()
    factory_report()
    log.info("warm-up done in %.1fs", time.perf_counter() - started)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    with SessionLocal() as db:
        seed(db)
        data.refresh_index(db)
    from app.plant.live import get_plant

    get_plant()
    threading.Thread(target=_warm_up, daemon=True).start()
    log.info(
        "OpEx ready (Gemini: %s, database: %s)",
        "on" if settings.gemini_enabled else "off - rule-based fallback",
        "Supabase" if settings.database_url else "local SQLite",
    )
    yield


app = FastAPI(
    title="OpEx API", version="1.0.0", lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json"
)
app.add_middleware(GZipMiddleware, minimum_size=2000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for module in (auth, factory, actions, copilot, simulation, data, admin):
    app.include_router(module.router)
app.include_router(auth.users_router)


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception):
    log.exception("unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Something went wrong on our side. Please try again."})


# The built React app. Any non-API path returns index.html so client-side routes work on refresh.
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path == "api" or path.startswith("api/"):
            raise HTTPException(404, "No such API endpoint.")
        candidate = FRONTEND_DIST / path
        if path and candidate.is_file() and FRONTEND_DIST in candidate.resolve().parents:
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")
