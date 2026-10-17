"""Turn a machine report into priced options, record the human decision, act on the plant."""

import logging

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.analytics.machine_report import machine_report
from app.auth.security import can, permission_to_approve
from app.core.jsonsafe import clean
from app.db.models import AuditLog, Decision, Recommendation, User
from app.plant.calibration import COMPONENT_KEYS
from app.plant.factory import MACHINES, MACHINES_BY_ID
from app.plant.live import get_plant
from app.services import settings_store

from . import learning
from .options import Situation, build_options
from .ranking import WEIGHT_PRESETS, rank, recommendation

log = logging.getLogger(__name__)
CAUSE_OF_WORN = {
    "bearing": "bearing_degradation",
    "drive": "drive_slip",
    "coolant": "coolant_failure",
    "electrical": "power_module",
}
NO_PART_SWAP = ("idle_waste", "sensor_drift", "tool_overstrain")


def situation_for(report: dict) -> Situation | None:
    """None when nothing on this machine needs a decision."""
    plant = get_plant()
    machine = MACHINES_BY_ID[report["machine"]["id"]]
    top = report["root_cause"]["top"]
    focus = report["prediction"]["focus_component"]
    if top is None and focus is None and not report["operating_risk"].get("modes"):
        return None
    if top is None:
        top = {
            "key": CAUSE_OF_WORN.get(focus, "tool_overstrain"),
            "name": "Component wear",
            "component": focus,
            "probability": 0.6,
            "fixable_by_partial": False,
        }
    component = top["component"] or (focus if top["key"] not in NO_PART_SWAP else None)
    sisters = [m for m in MACHINES if m.line_id == machine.line_id and m.id != machine.id]
    healthy_sisters = sum(machine_report(m.id)["prediction"]["severity"] in ("low", "medium") for m in sisters)
    return Situation(
        machine=machine,
        cause_key=top["key"],
        cause_name=top["name"],
        component=component,
        cause_probability=top.get("probability") or 0.6,
        fixable_by_partial=top.get("fixable_by_partial", False),
        rul=report["components"].get(component) if component else None,
        damage={c: report["components"][c]["damage"] if c in report["components"] else 0.0 for c in COMPONENT_KEYS},
        hours_to_shift=plant.minutes_to_shift_change() / 60,
        hours_to_window=plant.minutes_to_window() / 60,
        op_risk=report["operating_risk"]["probability"],
        confidence=report["prediction"]["confidence"],
        sister_capacity=healthy_sisters >= 3,
    )


def build_recommendation(
    db: Session, machine_id: str, preset: str | None = None, weights: dict | None = None, save: bool = True
) -> dict:
    report = machine_report(machine_id)
    situation = situation_for(report)
    if situation is None:
        return {
            "machine_id": machine_id,
            "needed": False,
            "message": "Nothing needs a decision on this machine right now.",
            "report": report,
        }

    saved = settings_store.get_priorities(db)
    preset = preset or saved["preset"]
    weights = weights or (
        saved["weights"] if preset == "custom" else WEIGHT_PRESETS.get(preset, WEIGHT_PRESETS["balanced"])
    )
    options = build_options(situation, settings_store.get_economics(db), learning.learned_stats(db))
    ranked = clean(rank(options, weights, report["prediction"]["severity"]))
    for option in ranked:
        option["permission"] = permission_to_approve(option["key"])
    summary = clean(recommendation(ranked, situation.machine, situation.cause_name))

    result = {
        "machine_id": machine_id,
        "needed": True,
        "preset": preset,
        "weights": weights,
        "cause": {"key": situation.cause_key, "name": situation.cause_name, "component": situation.component},
        "options": ranked,
        "recommendation": summary,
        "report": report,
        "hours_to_window": round(situation.hours_to_window, 1),
        "hours_to_shift": round(situation.hours_to_shift, 1),
    }
    if save:
        row = Recommendation(
            machine_id=machine_id,
            plant_time=report["plant_time"],
            cause_key=situation.cause_key,
            cause_name=situation.cause_name,
            component=situation.component,
            preset=preset,
            weights=weights,
            options=ranked,
            recommended_action=summary["action_key"],
            summary=summary,
            confidence=summary["confidence"],
        )
        db.add(row)
        db.commit()
        result["id"] = row.id
    return result


def decide(
    db: Session, user: User, recommendation_id: str, decision: str, action_key: str | None, note: str | None
) -> dict:
    rec = db.get(Recommendation, recommendation_id)
    if rec is None:
        raise HTTPException(404, "That recommendation no longer exists.")
    if decision not in ("approved", "rejected", "modified"):
        raise HTTPException(400, "Decision must be approved, rejected or modified.")
    chosen = action_key if decision == "modified" and action_key else rec.recommended_action
    if decision == "modified" and chosen not in {o["key"] for o in rec.options}:
        raise HTTPException(400, "Pick one of the listed options.")
    if decision == "rejected":
        allowed = can(user.role, "decide_minor")
    else:
        allowed = can(user.role, permission_to_approve(chosen))
    if not allowed:
        raise HTTPException(403, "This action needs a maintenance engineer or plant manager to approve it.")

    plant = get_plant()
    option = next((o for o in rec.options if o["key"] == chosen), {})
    before = learning.machine_snapshot(rec.machine_id)
    result = (
        "No change made to the machine."
        if decision == "rejected"
        else plant.apply_action(rec.machine_id, chosen, rec.component)
    )
    row = Decision(
        recommendation_id=rec.id,
        machine_id=rec.machine_id,
        cause_key=rec.cause_key,
        recommended_action=rec.recommended_action,
        action_key=chosen,
        decision=decision,
        note=note,
        decided_by=user.email,
        plant_minute=plant.minute,
        plant_time=plant.now.isoformat(timespec="minutes"),
        predicted={
            "p_fail_after": option.get("p_fail"),
            "total_inr": option.get("total_inr"),
            "value_protected_inr": rec.summary.get("value_protected_inr"),
        },
        before=before,
    )
    db.add(row)
    db.add(
        AuditLog(
            user_email=user.email,
            action=f"decision.{decision}",
            target=rec.machine_id,
            details={"action": chosen, "recommended": rec.recommended_action, "note": note},
        )
    )
    db.commit()
    log.info("%s %s %s on %s", user.email, decision, chosen, rec.machine_id)
    return {
        "decision_id": row.id,
        "result": result,
        "action": chosen,
        "decision": decision,
        "check_in_plant_minutes": learning.CHECK_AFTER_MINUTES,
    }
