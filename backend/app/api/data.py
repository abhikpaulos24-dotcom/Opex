"""Data & models: where the data came from, what we did to it, how good the models are,
plus CSV upload (clean + check a sensor file) and the knowledge library."""

import io
import json
from uuid import uuid4

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics import anomaly, data_health
from app.analytics.signals import SIGNAL_INFO, normal_ranges
from app.auth.deps import current_user, require
from app.core.paths import MODELS_DIR, PROCESSED_DIR
from app.db.models import Alert, AuditLog, Decision, Incident, KnowledgeDocument, SimulationRun, User
from app.db.session import get_db
from app.integrations import bigquery, storage
from app.knowledge.search import get_index
from app.plant.calibration import get_calibration
from app.plant.factory import MACHINES_BY_ID

router = APIRouter(prefix="/api/data", tags=["data"])
DOWNLOADS = {
    "ai4i_clean.csv": PROCESSED_DIR / "ai4i_clean.csv",
    "maintenance_history.csv": PROCESSED_DIR / "maintenance_history.csv",
    "calibration.json": PROCESSED_DIR / "calibration.json",
    "data_quality_report.json": PROCESSED_DIR / "data_quality_report.json",
    "incident_history.json": PROCESSED_DIR / "incident_history.json",
}
MAX_UPLOAD = 15 * 1024 * 1024


def _read(path) -> dict:
    return json.loads(path.read_text()) if path.exists() else {}


@router.get("/overview")
def overview(_: User = Depends(current_user)):
    cal = get_calibration()
    return {
        "datasets": _read(PROCESSED_DIR / "data_quality_report.json").get("datasets", []),
        "models": {
            "failure_mode": _read(MODELS_DIR / "failure_mode_metrics.json"),
            "remaining_life": {
                k: v for k, v in _read(MODELS_DIR / "rul_metrics.json").items() if k != "degradation_curve"
            },
            "precursor": _read(MODELS_DIR / "precursor_metrics.json"),
        },
        "degradation_curve": _read(MODELS_DIR / "rul_metrics.json").get("degradation_curve", {}),
        "calibration": cal.raw,
        "calibration_measured": cal.is_measured,
        "downloads": [name for name, path in DOWNLOADS.items() if path.exists()],
    }


@router.get("/download/{name}")
def download(name: str, _: User = Depends(current_user)):
    path = DOWNLOADS.get(name)
    if not path or not path.exists():
        raise HTTPException(404, "File not available.")
    return FileResponse(path, filename=f"opex-{name}")


@router.get("/template.csv")
def template(_: User = Depends(current_user)):
    rows = [
        "timestamp,vibration_mm_s,process_temp_c,air_temp_c,rpm,torque_nm,current_a,power_kw,voltage_v,coolant_bar,tool_wear_min",
        "2026-10-16 08:00,1.9,37.1,27.2,1650,38.5,22.4,13.1,415,6.5,40",
        "2026-10-16 08:01,2.0,37.2,27.2,1648,38.9,22.6,13.2,416,6.5,41",
    ]
    return Response(
        "\n".join(rows) + "\n",
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="opex-sensor-template.csv"'},
    )


@router.post("/upload")
async def upload(machine_id: str, file: UploadFile = File(...), user: User = Depends(current_user)):
    """Clean an uploaded sensor CSV and report data health and anomalies against a machine's normal ranges."""
    machine = MACHINES_BY_ID.get(machine_id.upper())
    if machine is None:
        raise HTTPException(404, "Pick one of the plant's machines.")
    raw = await file.read()
    if len(raw) > MAX_UPLOAD:
        raise HTTPException(400, "Files must be under 15 MB.")
    try:
        df = pd.read_csv(io.BytesIO(raw))
    except Exception as err:
        raise HTTPException(400, "This does not look like a CSV file.") from err
    steps = []
    time_col = next((c for c in df.columns if c.lower() in ("timestamp", "time", "datetime")), None)
    if time_col is None:
        raise HTTPException(400, "The file needs a 'timestamp' column.")
    df[time_col] = pd.to_datetime(df[time_col], errors="coerce")
    bad_times = int(df[time_col].isna().sum())
    df = df.dropna(subset=[time_col]).sort_values(time_col).drop_duplicates(time_col)
    steps.append(f"Parsed timestamps ({bad_times} unreadable rows dropped), sorted, removed duplicates")
    known = [c for c in df.columns if c in SIGNAL_INFO or c == "air_temp_c"]
    if not known:
        raise HTTPException(400, "No recognised sensor columns. Download the template to see the names.")
    for col in known:
        df[col] = pd.to_numeric(df[col], errors="coerce")
        median, mad = df[col].median(), (df[col] - df[col].median()).abs().median()
        if mad > 0:
            spikes = (df[col] - median).abs() > 8 * 1.4826 * mad
            if spikes.any():
                df.loc[spikes, col] = np.nan
                steps.append(f"{col}: removed {int(spikes.sum())} impossible spikes (more than 8 robust SDs)")
    df = df.set_index(time_col).resample("1min").mean()
    steps.append(f"Resampled to 1-minute steps: {len(df)} rows")

    series = {
        name: (df[name].to_numpy() if name in df else np.full(len(df), np.nan))
        for name in list(SIGNAL_INFO) + ["air_temp_c", "power_kw"]
    }
    if np.all(np.isnan(series["air_temp_c"])):
        series["air_temp_c"] = np.full(len(df), 28.0)
    ranges = normal_ranges(machine, float(np.nanmedian(series["air_temp_c"])))
    health = data_health.assess(series, ranges, calibration_days=0, running=True)
    found = anomaly.detect(series, ranges)
    location = storage.save(f"uploads/{machine.id}/{uuid4().hex[:12]}.csv", raw, "text/csv")
    return {
        "rows": int(len(df)),
        "columns": known,
        "steps": steps,
        "stored_at": location,
        "data_health": health.to_dict(),
        "anomalies": [a.to_dict() for a in found],
        "uploaded_by": user.email,
    }


class DocumentIn(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    kind: str = "sop"
    body: str = Field(min_length=20, max_length=50_000)


@router.get("/knowledge")
def list_documents(_: User = Depends(current_user), db: Session = Depends(get_db)):
    index = get_index()
    files = sorted({(c.doc_id, c.title, c.kind) for c in index.chunks if c.kind in ("sop", "manual")})
    uploaded = db.scalars(select(KnowledgeDocument).order_by(KnowledgeDocument.created_at.desc())).all()
    return {
        "documents": [
            {"id": d, "title": t, "kind": k, "source": "library"}
            for d, t, k in files
            if not any(u.id == d for u in uploaded)
        ]
        + [{"id": u.id, "title": u.title, "kind": u.kind, "source": f"added by {u.created_by}"} for u in uploaded],
        "chunks": len(index.chunks),
    }


@router.post("/knowledge")
def add_document(body: DocumentIn, user: User = Depends(require("manage_knowledge")), db: Session = Depends(get_db)):
    doc = KnowledgeDocument(kind=body.kind, title=body.title, body=body.body, created_by=user.email)
    db.add(doc)
    db.add(AuditLog(user_email=user.email, action="knowledge.add", target=body.title))
    db.commit()
    refresh_index(db)
    return {"id": doc.id, "title": doc.title}


@router.get("/knowledge/search")
def search(q: str, _: User = Depends(current_user)):
    return get_index().search(q, limit=8)


@router.post("/export-bigquery")
def export_to_bigquery(user: User = Depends(require("edit_settings")), db: Session = Depends(get_db)):
    """Copy decisions, incidents, alerts and the latest simulation into BigQuery (free sandbox works)."""
    if not bigquery.enabled():
        raise HTTPException(
            400, "BigQuery is not set up. Add GOOGLE_CLOUD_PROJECT and BIGQUERY_DATASET (AUDIT.md, step 5)."
        )
    decisions = [
        {
            "machine_id": d.machine_id,
            "cause": d.cause_key,
            "ai_suggested": d.recommended_action,
            "action": d.action_key,
            "decision": d.decision,
            "decided_by": d.decided_by,
            "decided_at": d.decided_at.isoformat(),
            "outcome": d.outcome_status,
            "source": d.source,
        }
        for d in db.scalars(select(Decision))
    ]
    incidents = [
        {
            "machine_id": i.machine_id,
            "title": i.title,
            "status": i.status,
            "severity": i.severity,
            "component": i.component,
            "root_cause": i.root_cause,
            "started": i.started_plant_time,
            "resolved": i.resolved_plant_time,
        }
        for i in db.scalars(select(Incident))
    ]
    alerts = [
        {
            "machine_id": a.machine_id,
            "kind": a.kind,
            "severity": a.severity,
            "title": a.title,
            "status": a.status,
            "plant_time": a.plant_time,
        }
        for a in db.scalars(select(Alert))
    ]
    latest = db.scalars(select(SimulationRun).order_by(SimulationRun.created_at.desc()).limit(1)).first()
    simulation = (
        [{"metric": k, "value": v} for k, v in latest.summary["delta"].items() if isinstance(v, int | float)]
        if latest
        else []
    )
    try:
        written = bigquery.replace_tables(
            {"decisions": decisions, "incidents": incidents, "alerts": alerts, "latest_simulation": simulation}
        )
    except Exception as err:
        raise HTTPException(502, f"BigQuery refused the upload: {err}") from err
    db.add(AuditLog(user_email=user.email, action="data.export_bigquery", details=written))
    db.commit()
    return {"tables": written, "open_in_console": bigquery.console_url()}


def refresh_index(db: Session) -> None:
    docs = db.scalars(select(KnowledgeDocument)).all()
    get_index().set_extra_documents([(d.id, d.kind, d.title, d.body) for d in docs])
