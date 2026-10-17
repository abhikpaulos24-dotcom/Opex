"""First-run data: demo accounts (one per role) and the pilot decision history that
closed-loop learning starts from. Runs only when the tables are empty."""

import logging
from datetime import timedelta

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.security import hash_password
from app.core.config import get_settings

from .models import Decision, User, now_utc

log = logging.getLogger(__name__)

DEMO_USERS = [
    ("manager@opex.demo", "Priya Deshmukh", "manager"),
    ("engineer@opex.demo", "Arjun Nair", "engineer"),
    ("operator@opex.demo", "Ravi Kumar", "operator"),
    ("viewer@opex.demo", "Guest Viewer", "viewer"),
]

# (cause, action): (successes, trials) observed during the 90-day pilot (Jul-Oct 2026, demo data)
PILOT_OUTCOMES = {
    ("bearing_degradation", "replace_component"): (9, 10),
    ("bearing_degradation", "reduce_speed"): (9, 11),
    ("bearing_degradation", "stop_now"): (6, 6),
    ("bearing_degradation", "continue_to_window"): (2, 5),
    ("bearing_degradation", "partial_maintenance"): (1, 4),
    ("bearing_degradation", "increase_monitoring"): (3, 5),
    ("lubrication_starvation", "partial_maintenance"): (7, 8),
    ("lubrication_starvation", "reduce_speed"): (5, 6),
    ("coolant_failure", "partial_maintenance"): (6, 7),
    ("coolant_failure", "replace_component"): (5, 5),
    ("coolant_failure", "continue_to_window"): (3, 5),
    ("drive_slip", "partial_maintenance"): (5, 7),
    ("drive_slip", "replace_component"): (4, 4),
    ("power_module", "replace_component"): (3, 3),
    ("tool_overstrain", "change_tool"): (12, 12),
    ("tool_overstrain", "continue_tool"): (3, 7),
    ("idle_waste", "standby"): (15, 15),
    ("sensor_drift", "recalibrate_sensor"): (4, 4),
}


def seed(db: Session) -> None:
    settings = get_settings()
    if settings.demo_mode and not db.scalar(select(func.count()).select_from(User)):
        for email, name, role in DEMO_USERS:
            db.add(
                User(
                    email=email,
                    full_name=name,
                    role=role,
                    password_hash=hash_password(settings.demo_password),
                    preferences={},
                )
            )
        log.info("seeded %d demo accounts", len(DEMO_USERS))

    if not db.scalar(select(func.count()).select_from(Decision)):
        rng = np.random.default_rng(11)
        machines = [f"M-{i:02d}" for i in range(1, 25)]
        start = now_utc() - timedelta(days=90)
        count = 0
        for (cause, action), (wins, trials) in PILOT_OUTCOMES.items():
            outcomes = [True] * wins + [False] * (trials - wins)
            rng.shuffle(outcomes)
            for worked in outcomes:
                db.add(
                    Decision(
                        machine_id=str(rng.choice(machines)),
                        cause_key=cause,
                        recommended_action=action,
                        action_key=action,
                        decision="approved",
                        decided_by="pilot history",
                        decided_at=start + timedelta(hours=float(rng.uniform(0, 90 * 24))),
                        outcome_status="success" if worked else "failure",
                        outcome={
                            "summary": "Machine ran to the planned window without a breakdown"
                            if worked
                            else "Problem came back or the machine broke down before the fix"
                        },
                        source="pilot_history",
                    )
                )
                count += 1
        log.info("seeded %d pilot decisions for closed-loop learning", count)
    db.commit()
