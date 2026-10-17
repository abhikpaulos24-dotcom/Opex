"""Plant manager tools: demo controls, factory economics, audit log. Plus the sensor ingest
endpoint (for Pub/Sub push subscriptions or shop-floor gateways) and health/config."""

import base64
import json
from dataclasses import asdict

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import gemini
from app.auth.deps import current_user, require
from app.core.config import get_settings
from app.db.models import AuditLog, User
from app.db.seed import DEMO_USERS
from app.db.session import get_db
from app.integrations import bigquery
from app.plant.factory import LINES, MACHINE_TYPES, MACHINES, MACHINES_BY_ID, PRODUCTS
from app.plant.live import get_plant
from app.services import settings_store

router = APIRouter(prefix="/api", tags=["admin"])
FAULTS = ("bearing", "drive", "electrical", "coolant", "tool", "energy_waste", "sensor")


class InjectIn(BaseModel):
    machine_id: str
    fault: str


@router.post("/admin/demo/reset")
def reset_demo(user: User = Depends(require("demo_controls")), db: Session = Depends(get_db)):
    get_plant().reset()
    db.add(AuditLog(user_email=user.email, action="demo.reset"))
    db.commit()
    return {"ok": True, "plant_time": get_plant().now.isoformat(timespec="minutes")}


@router.post("/admin/demo/fast-forward")
def fast_forward(minutes: int = 60, user: User = Depends(require("demo_controls")), db: Session = Depends(get_db)):
    get_plant().fast_forward(max(1, min(minutes, 720)))
    db.add(AuditLog(user_email=user.email, action="demo.fast_forward", details={"minutes": minutes}))
    db.commit()
    return {"ok": True, "plant_time": get_plant().now.isoformat(timespec="minutes")}


@router.post("/admin/demo/inject")
def inject(body: InjectIn, user: User = Depends(require("demo_controls")), db: Session = Depends(get_db)):
    if body.fault not in FAULTS or body.machine_id.upper() not in MACHINES_BY_ID:
        raise HTTPException(400, "Unknown machine or fault.")
    message = get_plant().inject_fault(body.machine_id.upper(), body.fault)
    db.add(AuditLog(user_email=user.email, action="demo.inject", target=body.machine_id, details={"fault": body.fault}))
    db.commit()
    return {"message": message}


@router.get("/settings/economics")
def get_economics(_: User = Depends(current_user), db: Session = Depends(get_db)):
    return {k: v for k, v in asdict(settings_store.get_economics(db)).items() if k in settings_store.EDITABLE_ECONOMICS}


@router.put("/settings/economics")
def put_economics(values: dict, user: User = Depends(require("edit_settings")), db: Session = Depends(get_db)):
    result = settings_store.set_economics(db, values, user.email)
    db.add(AuditLog(user_email=user.email, action="settings.economics", details=result))
    db.commit()
    return result


@router.get("/audit")
def audit(_: User = Depends(require("manage_users")), db: Session = Depends(get_db)):
    rows = db.scalars(select(AuditLog).order_by(AuditLog.at.desc()).limit(200)).all()
    return [
        {"at": r.at, "user": r.user_email, "action": r.action, "target": r.target, "details": r.details} for r in rows
    ]


@router.get("/plant")
def plant_layout(_: User = Depends(current_user)):
    return {
        "lines": [{"id": ln.id, "name": ln.name, "product": PRODUCTS[ln.product_key].name} for ln in LINES],
        "machines": [
            {
                "id": m.id,
                "name": m.name,
                "line_id": m.line_id,
                "type": MACHINE_TYPES[m.type_key].name,
                "installed": m.install_year,
            }
            for m in MACHINES
        ],
        "faults": FAULTS,
    }


@router.post("/ingest/readings")
async def ingest(request: Request, x_api_key: str | None = Header(default=None)):
    """Accepts {"machine_id": "M-17", "readings": {"vibration_mm_s": 3.2, ...}} directly, or the same JSON
    wrapped in a Pub/Sub push message."""
    expected = get_settings().ingest_api_key
    if not expected or x_api_key != expected:
        raise HTTPException(403, "Ingest is disabled or the API key is wrong.")
    body = await request.json()
    if "message" in body:  # Pub/Sub push format
        body = json.loads(base64.b64decode(body["message"]["data"]))
    machine_id = str(body.get("machine_id", "")).upper()
    if machine_id not in MACHINES_BY_ID or not isinstance(body.get("readings"), dict):
        raise HTTPException(400, "Need machine_id and a readings object.")
    get_plant().ingest(machine_id, body["readings"])
    return {"ok": True}


@router.get("/health")
def health():
    return {"status": "ok", "plant_time": get_plant().now.isoformat(timespec="minutes")}


@router.get("/config")
def config():
    s = get_settings()
    return {
        "demo_mode": s.demo_mode,
        "allow_signup": s.allow_signup,
        "gemini": gemini.enabled(),
        "gemini_model": s.gemini_model if gemini.enabled() else None,
        "bigquery": bigquery.enabled(),
        "cloud_storage": bool(s.gcs_bucket),
        "pubsub": bool(s.pubsub_alerts_topic),
        "database": "supabase" if s.database_url else "local",
        "live_speed": s.live_plant_speed,
        "demo_accounts": [{"email": e, "role": r} for e, _, r in DEMO_USERS] if s.demo_mode else [],
        "demo_password": s.demo_password if s.demo_mode else None,
    }
