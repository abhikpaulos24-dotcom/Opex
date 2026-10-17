"""Live plant: overview, machine detail, alerts, incidents."""

from datetime import timedelta
from uuid import uuid4

import numpy as np
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import agents, vision
from app.analytics.factory_report import all_machine_reports, factory_report
from app.analytics.machine_report import machine_report
from app.auth.deps import current_user, require
from app.db.models import Alert, AuditLog, Decision, Incident, User, now_utc
from app.db.session import get_db
from app.decisions import learning
from app.integrations import storage
from app.plant.factory import MACHINES_BY_ID
from app.plant.live import SIGNALS, S, get_plant
from app.services import alerts

router = APIRouter(prefix="/api", tags=["factory"])


def _check_machine(machine_id: str) -> str:
    machine_id = machine_id.upper()
    if machine_id not in MACHINES_BY_ID:
        raise HTTPException(404, f"No machine called {machine_id}.")
    return machine_id


@router.get("/overview")
def overview(user: User = Depends(current_user), db: Session = Depends(get_db)):
    data = factory_report()
    plant = get_plant()
    alerts.sync(db, all_machine_reports(), plant.minute, data["plant_time"])
    learning.check_outcomes(db)
    open_alerts = db.scalars(select(Alert).where(Alert.status == "open").order_by(Alert.created_at.desc())).all()
    return {**data, "alerts": [_alert_out(a) for a in open_alerts[:20]], "open_alert_count": len(open_alerts)}


@router.get("/machines/{machine_id}")
def machine(machine_id: str, _: User = Depends(current_user)):
    machine_id = _check_machine(machine_id)
    result = machine_report(machine_id)
    result["events"] = get_plant().recent_events(machine_id, 20)[::-1]
    return result


@router.get("/machines/{machine_id}/history")
def machine_history(machine_id: str, minutes: int = 180, _: User = Depends(current_user)):
    machine_id = _check_machine(machine_id)
    plant = get_plant()
    plant.advance()
    mins, data = plant.frame(min(max(minutes, 30), 720))
    i = plant.index[machine_id]
    start = plant.start
    times = [(start + timedelta(minutes=int(m))).strftime("%H:%M") for m in mins]
    series = {name: [None if np.isnan(v) else round(float(v), 3) for v in data[:, i, S[name]]] for name in SIGNALS}
    return {"times": times, "series": series}


PHOTO_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
MAX_PHOTO_BYTES = 5 * 1024 * 1024


@router.post("/machines/{machine_id}/photo-check")
async def photo_check(
    machine_id: str, language: str = "en", file: UploadFile = File(...), user: User = Depends(current_user)
):
    """Gemini looks at a photo of a part from this machine (visual quality inspection)."""
    machine_id = _check_machine(machine_id)
    if file.content_type not in PHOTO_TYPES:
        raise HTTPException(400, "Photos must be JPG, PNG or WEBP.")
    image = await file.read()
    if len(image) > MAX_PHOTO_BYTES:
        raise HTTPException(400, "Photos must be under 5 MB.")
    # Our own file name - never the uploaded one, which could contain "../".
    name = f"{get_plant().now:%Y%m%d-%H%M}-{uuid4().hex[:8]}.{PHOTO_TYPES[file.content_type]}"
    stored_at = storage.save(f"photos/{machine_id}/{name}", image, file.content_type)
    return {
        **vision.inspect_part(image, file.content_type, machine_report(machine_id), language),
        "stored_at": stored_at,
        "checked_by": user.email,
    }


def _alert_out(a: Alert) -> dict:
    return {
        "id": a.id,
        "machine_id": a.machine_id,
        "kind": a.kind,
        "severity": a.severity,
        "title": a.title,
        "message": a.message,
        "status": a.status,
        "plant_time": a.plant_time,
        "acknowledged_by": a.acknowledged_by,
    }


@router.get("/alerts")
def list_alerts(status: str = "open", _: User = Depends(current_user), db: Session = Depends(get_db)):
    query = select(Alert).order_by(Alert.created_at.desc()).limit(100)
    if status != "all":
        query = query.where(Alert.status == status)
    return [_alert_out(a) for a in db.scalars(query)]


@router.post("/alerts/{alert_id}/acknowledge")
def acknowledge(alert_id: str, user: User = Depends(require("acknowledge_alert")), db: Session = Depends(get_db)):
    alert = db.get(Alert, alert_id)
    if not alert:
        raise HTTPException(404, "Alert not found.")
    alert.status, alert.acknowledged_by, alert.acknowledged_at = "acknowledged", user.email, now_utc()
    db.add(
        AuditLog(
            user_email=user.email, action="alert.acknowledge", target=alert.machine_id, details={"kind": alert.kind}
        )
    )
    db.commit()
    return _alert_out(alert)


def _incident_out(i: Incident, with_snapshot: bool = False) -> dict:
    out = {
        "id": i.id,
        "machine_id": i.machine_id,
        "title": i.title,
        "status": i.status,
        "severity": i.severity,
        "component": i.component,
        "root_cause": i.root_cause,
        "started_plant_time": i.started_plant_time,
        "resolved_plant_time": i.resolved_plant_time,
        "has_report": bool(i.report),
    }
    if with_snapshot:
        out["snapshot"], out["report"] = i.snapshot, i.report
    return out


@router.get("/incidents")
def list_incidents(_: User = Depends(current_user), db: Session = Depends(get_db)):
    return [_incident_out(i) for i in db.scalars(select(Incident).order_by(Incident.opened_at.desc()).limit(50))]


@router.get("/incidents/{incident_id}")
def incident_detail(incident_id: str, _: User = Depends(current_user), db: Session = Depends(get_db)):
    incident = db.get(Incident, incident_id)
    if not incident:
        raise HTTPException(404, "Incident not found.")
    decisions = db.scalars(
        select(Decision).where(Decision.machine_id == incident.machine_id, Decision.decided_at >= incident.opened_at)
    ).all()
    return {**_incident_out(incident, True), "decisions": [_decision_brief(d) for d in decisions]}


@router.post("/incidents/{incident_id}/report")
def write_report(
    incident_id: str, language: str = "en", user: User = Depends(require("write_report")), db: Session = Depends(get_db)
):
    incident = db.get(Incident, incident_id)
    if not incident:
        raise HTTPException(404, "Incident not found.")
    decisions = db.scalars(
        select(Decision).where(Decision.machine_id == incident.machine_id, Decision.decided_at >= incident.opened_at)
    ).all()
    incident.report = agents.investigation_report(
        _incident_out(incident, True), [_decision_brief(d) for d in decisions], language
    )
    db.add(AuditLog(user_email=user.email, action="incident.report", target=incident.machine_id))
    db.commit()
    return {"report": incident.report}


def _decision_brief(d: Decision) -> dict:
    return {
        "action_key": d.action_key,
        "decision": d.decision,
        "decided_by": d.decided_by,
        "plant_time": d.plant_time,
        "outcome_status": d.outcome_status,
        "outcome": d.outcome,
        "note": d.note,
    }
