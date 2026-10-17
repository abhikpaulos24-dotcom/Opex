"""Rewind the factory: take one breakdown from the "without AI" history and replay that exact
degradation with OpEx watching. Because both worlds share every random draw, this is the
same bearing, the same life and the same luck - only the decision differs.

If OpEx would have missed it (sensor coverage, model miss, or the team not acting), we say so.
"""

from datetime import timedelta

from app.core.jsonsafe import clean
from app.plant.calibration import COMPONENT_KEYS
from app.plant.factory import COMPONENTS, MACHINES, lost_contribution_per_hour

from .engine import PRODUCTIVE_SHARE, START_DATE, FactorySimulation, SimulationParams

OP_HOURS_PER_PRODUCTION_DAY = 24 * PRODUCTIVE_SHARE * 0.82


def rewind_candidates(events: list[dict], limit: int = 6) -> list[dict]:
    failures = [e for e in events if e.get("world") == "without" and e["kind"] == "failure"]
    by_id = {m.id: m for m in MACHINES}

    def total(e: dict) -> float:
        return e["cost_inr"] + e["downtime_h"] * lost_contribution_per_hour(by_id[e["machine"]])

    ranked = sorted(failures, key=total, reverse=True)[:limit]
    return [{**e, "total_inr": round(total(e), -2)} for e in ranked]


def rewind(params: SimulationParams, event: dict) -> dict:
    sim = FactorySimulation(params)
    m = next(i for i, mach in enumerate(MACHINES) if mach.id == event["machine"])
    c = COMPONENT_KEYS.index(event["component"])
    k = event["life_index"]
    d, cal, spec, machine = sim.draws, sim.cal, COMPONENTS[event["component"]], MACHINES[m]

    life_h = float(d.lives[m, c, k])
    onset_days = (1 - cal.degradation_onset) * life_h / OP_HOURS_PER_PRODUCTION_DAY
    alert_op_h = spec.warning_lead_h / max(1 + float(d.rul_error[m, c, k]), 0.4)
    alert_days = alert_op_h / OP_HOURS_PER_PRODUCTION_DAY
    recall = cal.detection_recall[event["component"]] * params.sensor_coverage
    detected = float(d.detect_u[m, c, k]) < recall
    adopted = float(d.adopt_u[m, c, k]) < params.adoption_rate

    lost_per_h = lost_contribution_per_hour(machine)
    without_total = event["cost_inr"] + event["downtime_h"] * lost_per_h
    failure_day = START_DATE + timedelta(days=event["day"])

    def date(days_before: float) -> str:
        return (failure_day - timedelta(days=round(max(days_before, 0)))).isoformat()

    without = [
        {"when": date(onset_days), "text": f"{spec.name} starts to wear (no one can see it yet)"},
        {"when": date(alert_days), "text": f"Warning signs in the {spec.signal.replace('_', ' ')} data - unnoticed"},
        {"when": date(0), "text": f"Breakdown: {event['detail']}"},
        {"when": date(0), "text": f"{event['downtime_h']:.1f} h of lost production"},
        {"when": date(0), "text": f"₹{without_total:,.0f} total cost (repair ₹{event['cost_inr']:,.0f} + lost output)"},
    ]
    if not (detected and adopted):
        reason = (
            "the warning signs never reached a sensor or the model missed them"
            if not detected
            else "the warning was raised but nobody acted on it"
        )
        return clean(
            {
                "event": event,
                "caught": False,
                "reason": reason,
                "without": without,
                "with": without,
                "value_protected_inr": 0,
                "detection_odds": round(recall * params.adoption_rate, 3),
            }
        )

    alert_day = min(max(event["day"] - int(alert_days), 0), sim.days - 1)
    window_offset = int(sim.next_window[alert_day] - alert_day)
    window_op_h = window_offset * OP_HOURS_PER_PRODUCTION_DAY
    in_window = window_op_h <= 0.7 * spec.warning_lead_h
    disruption = 0.0 if in_window else spec.planned_repair_h
    with_total = spec.part_cost_inr + spec.planned_repair_h * sim.econ.technician_inr_per_h + disruption * lost_per_h
    with_steps = [
        {"when": date(onset_days), "text": f"{spec.name} starts to wear"},
        {"when": date(alert_days), "text": f"OpEx warns: about {alert_op_h:.0f} operating hours of life left"},
        {
            "when": date(alert_days),
            "text": "Recommended: planned replacement"
            + (" in the Sunday window" if in_window else " at the next shift change")
            + " - approved by the maintenance engineer",
        },
        {
            "when": date(alert_days - window_offset) if in_window else date(alert_days),
            "text": f"Planned swap, parts already on the shelf ({spec.planned_repair_h:.0f} h job)",
        },
        {"when": "", "text": f"{disruption:.1f} h of production disruption"},
        {"when": "", "text": f"₹{without_total - with_total:,.0f} value protected"},
    ]
    return clean(
        {
            "event": event,
            "caught": True,
            "without": without,
            "with": with_steps,
            "value_protected_inr": round(without_total - with_total, -2),
            "warning_days": round(alert_days, 1),
            "detection_odds": round(recall * params.adoption_rate, 3),
        }
    )
