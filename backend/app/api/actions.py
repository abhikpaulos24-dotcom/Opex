"""Diagnose -> options -> AI incident room -> human decision -> learning log."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai import agents
from app.analytics.factory_report import factory_report
from app.auth.deps import current_user, require
from app.db.models import AuditLog, Decision, Recommendation, User
from app.db.session import get_db
from app.decisions import learning
from app.decisions.ranking import WEIGHT_PRESETS
from app.decisions.service import build_recommendation
from app.decisions.service import decide as record_decision
from app.services import settings_store

router = APIRouter(prefix="/api", tags=["actions"])


class RecommendIn(BaseModel):
    preset: str | None = None
    weights: dict[str, float] | None = None


class DecisionIn(BaseModel):
    decision: str
    action_key: str | None = None
    note: str | None = None


class PrioritiesIn(BaseModel):
    preset: str
    weights: dict[str, float] | None = None


@router.get("/actions")
def action_queue(_: User = Depends(current_user)):
    """What should I worry about first? Ranked by probability x impact x urgency."""
    overview = factory_report()
    return {
        "risks": overview["risks"],
        "maintenance_due": overview["maintenance"]["due_soon"],
        "plant_time": overview["plant_time"],
        "window_in_h": overview["window_in_h"],
        "shift_change_in_h": overview["shift_change_in_h"],
    }


@router.post("/machines/{machine_id}/recommendation")
def recommend(machine_id: str, body: RecommendIn, _: User = Depends(current_user), db: Session = Depends(get_db)):
    if body.preset and body.preset not in WEIGHT_PRESETS and body.preset != "custom":
        raise HTTPException(400, "Unknown priority preset.")
    result = build_recommendation(db, machine_id.upper(), body.preset, body.weights)
    result.pop("report", None)
    return result


@router.post("/recommendations/{recommendation_id}/agents")
def incident_room(
    recommendation_id: str,
    language: str = "en",
    simple: bool = False,
    _: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    rec = db.get(Recommendation, recommendation_id)
    if not rec:
        raise HTTPException(404, "Recommendation not found.")
    if rec.agent_trace and language == "en" and not simple:
        return {"agents": rec.agent_trace}
    full = build_recommendation(db, rec.machine_id, rec.preset, rec.weights, save=False)
    if not full["needed"]:
        return {"agents": []}
    full["options"], full["recommendation"] = rec.options, rec.summary
    trace = agents.incident_room(full["report"], full, language, simple)
    if language == "en" and not simple:
        rec.agent_trace = trace
        db.commit()
    return {"agents": trace}


@router.post("/recommendations/{recommendation_id}/decision")
def decide(recommendation_id: str, body: DecisionIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return record_decision(db, user, recommendation_id, body.decision, body.action_key, body.note)


@router.get("/decisions")
def decision_log(user: User = Depends(current_user), db: Session = Depends(get_db)):
    learning.check_outcomes(db)
    rows = db.scalars(select(Decision).order_by(Decision.decided_at.desc()).limit(60)).all()
    stats = learning.learned_stats(db)
    totals = dict(db.execute(select(Decision.outcome_status, func.count()).group_by(Decision.outcome_status)).all())
    live = [d for d in rows if d.source == "live"]
    return {
        "decisions": [
            {
                "id": d.id,
                "machine_id": d.machine_id,
                "cause_key": d.cause_key,
                "action_key": d.action_key,
                "recommended_action": d.recommended_action,
                "decision": d.decision,
                "note": d.note,
                "decided_by": d.decided_by,
                "decided_at": d.decided_at,
                "plant_time": d.plant_time,
                "predicted": d.predicted,
                "before": d.before,
                "after": d.after,
                "outcome_status": d.outcome_status,
                "outcome": d.outcome,
                "source": d.source,
            }
            for d in rows
        ],
        "learned": [
            {
                "cause": k.split(":")[0],
                "action": k.split(":")[1],
                **v,
                "success_rate": round(v["successes"] / v["trials"], 3),
            }
            for k, v in sorted(stats.items())
        ],
        "totals": totals,
        "agreement": {
            "live_decisions": len(live),
            "followed_ai": sum(d.action_key == d.recommended_action and d.decision != "rejected" for d in live),
        },
    }


@router.get("/settings/priorities")
def get_priorities(_: User = Depends(current_user), db: Session = Depends(get_db)):
    return {**settings_store.get_priorities(db), "presets": WEIGHT_PRESETS}


@router.put("/settings/priorities")
def put_priorities(body: PrioritiesIn, user: User = Depends(require("edit_settings")), db: Session = Depends(get_db)):
    if body.preset not in WEIGHT_PRESETS and body.preset != "custom":
        raise HTTPException(400, "Unknown preset.")
    if body.preset == "custom" and not body.weights:
        raise HTTPException(400, "Custom priorities need weights.")
    value = settings_store.set_priorities(db, body.preset, body.weights, user.email)
    db.add(AuditLog(user_email=user.email, action="settings.priorities", details=value))
    db.commit()
    return value
