"""Closed-loop learning: prediction -> recommendation -> human decision -> actual outcome.

Every live decision is checked again two plant hours later: did the machine break down anyway,
or is the risk still high? Success counts per (problem, action) feed back into the options
("this action worked in 9 of 11 similar cases here").
"""

import logging
import time
from datetime import UTC, datetime

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics.factory_report import shift_kpis
from app.analytics.machine_report import machine_report
from app.db.models import Decision
from app.plant.live import S, get_plant

log = logging.getLogger(__name__)
CHECK_AFTER_MINUTES = 120
_stats: tuple[float, dict] = (0.0, {})


def learned_stats(db: Session) -> dict[str, dict]:
    """{"cause:action": {"successes": n, "trials": m}} from checked, non-rejected decisions (cached 20 s)."""
    global _stats
    if time.monotonic() - _stats[0] < 20:
        return _stats[1]
    stats: dict[str, dict] = {}
    rows = db.execute(
        select(Decision.cause_key, Decision.action_key, Decision.outcome_status).where(
            Decision.outcome_status.in_(("success", "failure")), Decision.decision != "rejected"
        )
    )
    for cause, action, outcome in rows:
        entry = stats.setdefault(f"{cause}:{action}", {"successes": 0, "trials": 0})
        entry["trials"] += 1
        entry["successes"] += outcome == "success"
    _stats = (time.monotonic(), stats)
    return stats


def machine_snapshot(machine_id: str, minutes: int = 60) -> dict:
    """Before/after numbers for one machine over the last hour of plant time."""
    plant = get_plant()
    _, data = plant.frame(minutes)
    i = plant.index[machine_id]
    kpis = shift_kpis(data, [i])
    energy = float(np.nansum(data[:, i, S["energy_kwh"]]))
    vibration = data[-10:, i, S["vibration_mm_s"]]
    return {
        "oee": kpis["oee"],
        "parts": kpis["parts"],
        "defect_rate": kpis["defect_rate"] if kpis["parts"] else None,
        "energy_kwh_per_part": round(energy / kpis["good_parts"], 3) if kpis["good_parts"] else None,
        "downtime_min": kpis["downtime_min"] + kpis["maintenance_min"],
        "vibration_mm_s": None if np.all(np.isnan(vibration)) else round(float(np.nanmedian(vibration)), 2),
    }


def check_outcomes(db: Session) -> int:
    """Close the loop on live decisions whose check time has come."""
    plant = get_plant()
    due = db.scalars(
        select(Decision).where(
            Decision.outcome_status == "pending",
            Decision.source == "live",
            Decision.plant_minute <= plant.minute - CHECK_AFTER_MINUTES,
        )
    ).all()
    for decision in due:
        breakdowns = [
            e
            for e in plant.recent_events(decision.machine_id, 200)
            if e["kind"] == "breakdown" and e["minute"] >= decision.plant_minute
        ]
        risk_now = machine_report(decision.machine_id)["prediction"]["p_fail_8h"]
        failed = bool(breakdowns) or (decision.decision != "rejected" and risk_now >= 0.5)
        decision.outcome_status = "failure" if failed else "success"
        decision.after = machine_snapshot(decision.machine_id)
        decision.outcome = {
            "summary": f"Machine broke down: {breakdowns[0]['message']}"
            if breakdowns
            else f"No breakdown; chance of failure now {risk_now:.0%}",
            "risk_now": risk_now,
        }
        decision.evaluated_at = datetime.now(UTC)
    if due:
        db.commit()
        log.info("checked the outcome of %d decisions", len(due))
    return len(due)
