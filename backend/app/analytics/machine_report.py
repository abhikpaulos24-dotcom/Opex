"""Everything OpEx knows about one machine right now: Detect -> Diagnose -> Predict.

Reading order:
  read_machine()     sensors for the last 4 plant hours, data health, anomalies, damage per component
  machine_report()   adds remaining life, failure probability, root cause, severity, confidence,
                     quality/energy/₹ impact and the maintenance plan

This module only reads the live plant; it never changes it.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.core.jsonsafe import clean
from app.plant.calibration import COMPONENT_KEYS, get_calibration
from app.plant.factory import COMPONENTS, MACHINES, MACHINES_BY_ID, PRODUCTS, Machine, lost_contribution_per_hour
from app.plant.live import COUNTERS, DOWN, IDLE, RUNNING, SIGNALS, STATE_NAMES, S, get_plant

from . import anomaly, data_health, health, prediction, root_cause
from .data_health import DataHealth
from .minute_cache import cached_for_this_minute
from .signals import SIGNAL_INFO, normal_ranges

HISTORY_MINUTES = 240
NOT_WEAR = ("sensor_drift", "idle_waste")  # causes that are not a worn component
WHAT_TO_INSPECT = {
    "bearing": "spindle bearings, preload, lubrication",
    "drive": "belt tension and wear, encoder",
    "electrical": "servo power module, terminals (thermography)",
    "coolant": "pump impeller, filter, rotary union seal",
}
TECH_TIPS = {
    "bearing": (
        "Wireless triaxial vibration sensors with on-board FFT",
        "Bearing faults show weeks earlier in vibration spectra; retrofit kits cost about ₹25-40k per point.",
    ),
    "coolant": (
        "Coolant pressure + concentration monitoring",
        "A ₹15k inline sensor catches clogged filters before parts drift out of tolerance.",
    ),
    "drive": (
        "Spindle-load monitoring from the CNC controller",
        "Most modern controllers already expose spindle load over OPC UA / MTConnect - no new sensor needed.",
    ),
    "electrical": ("Panel thermography on a monthly route", "Loose terminals heat up long before a servo alarm."),
    "energy": (
        "Automatic standby on idle detection (ISO 50001 practice)",
        "Idle machines draw 40-60% of cutting power; standby rules pay back in weeks.",
    ),
    "tool": (
        "Tool-life management by cutting load, not part count",
        "Change tools when the load says so, not on a fixed count - fewer breakages and longer tool life.",
    ),
}


@dataclass
class Readings:
    minutes: np.ndarray
    series: dict  # sensor series; minutes when the machine was not cutting are blanked (NaN)
    raw: dict  # the same series without blanking
    state_code: int
    running: bool
    speed: float  # speed x load, 1.0 = normal
    latest: dict  # median of the last 5 minutes per signal
    ranges: dict  # healthy band per signal
    state: dict  # live-plant bookkeeping (jobs, idle waste, component ages...)
    data_health: DataHealth
    anomalies: list
    damage: dict  # damage series per component (0 = new, 1 = failed)


# ------------------------------------------------------------------ step 1: read the machine
def read_machine(machine_id: str) -> Readings:
    return cached_for_this_minute(("readings", machine_id), lambda: _read(machine_id))


def _read(machine_id: str) -> Readings:
    plant = get_plant()
    machine = MACHINES_BY_ID[machine_id]
    i = plant.index[machine_id]
    minutes, data = plant.frame(HISTORY_MINUTES)
    raw = {name: data[:, i, S[name]] for name in SIGNALS + COUNTERS}

    state_code = int(plant.state[i])
    running = state_code == RUNNING
    speed = float(plant.speed_factor[i] * plant.load[i])
    # Only minutes when the machine was cutting say anything about wear.
    cutting = raw["state"] == RUNNING
    keep_as_is = set(COUNTERS) | {"air_temp_c", "tool_wear_min"}
    series = {k: v if k in keep_as_is else np.where(cutting, v, np.nan) for k, v in raw.items()}

    # While a machine is briefly stopped (tool change, waiting for material) its parts are as worn as
    # when it last cut, so diagnosis keeps using the readings from its last cutting minutes.
    recent = {k: v[cutting] for k, v in raw.items()} if cutting.any() else raw
    latest = {k: _recent_median(v) for k, v in recent.items()}
    ranges = normal_ranges(machine, latest["air_temp_c"], speed)
    state = plant.machine_state(machine_id)
    dh = data_health.assess(series, ranges, state["calibration_days"], running, valid=cutting)
    smoothed = {k: pd.Series(v).rolling(15, min_periods=1).median().to_numpy() for k, v in series.items()}
    return Readings(
        minutes=minutes,
        series=series,
        raw=raw,
        state_code=state_code,
        running=running,
        speed=speed,
        latest=latest,
        ranges=ranges,
        state=state,
        data_health=dh,
        anomalies=anomaly.detect(series, ranges) if running else [],
        damage=health.estimate_damage(
            smoothed, machine, max(speed, 0.1), vibration_trusted="vibration_mm_s" not in dh.untrusted_signals
        ),
    )


def _recent_median(values: np.ndarray) -> float:
    values = values[~np.isnan(values)]
    return float(np.median(values[-5:])) if len(values) else float("nan")


# ------------------------------------------------------------------ step 2: the full report
def machine_report(machine_id: str, operating_risk: dict | None = None) -> dict:
    get_plant().advance()
    return cached_for_this_minute(("report", machine_id), lambda: _report(machine_id, operating_risk))


def _report(machine_id: str, operating_risk: dict | None) -> dict:
    plant = get_plant()
    machine = MACHINES_BY_ID[machine_id]
    r = read_machine(machine_id)

    # No forecast while it is broken down, or for a part that is being swapped right now.
    outlooks = {
        c: prediction.component_outlook(c, r.damage[c], r.minutes, r.state["component_age_h"][c], machine_id)
        for c in COMPONENT_KEYS
        if r.state_code != DOWN and c != r.state["replacing"]
    }
    op = operating_risk or (
        prediction.operating_point_risk(r.latest) if r.running else {"probability": 0.0, "modes": {}}
    )
    op_extra = max(op["probability"] - 0.03, 0)  # AI4I's background failure rate is ~3%

    wear_risk = max((o["p_fail_8h"] for o in outlooks.values()), default=0.0)
    causes = _root_causes(r, op_extra, wear_risk)
    top = causes[0] if causes else None
    memory = (
        root_cause.similar_incidents(root_cause.deviations(r.latest, r.ranges), _same_type(machine))
        if r.state_code != DOWN and not (top and top["key"] in NOT_WEAR)
        else {"count": 0, "matches": [], "sentence": "Not a machine-wear pattern - no incident comparison."}
    )

    focus = _focus_component(outlooks, top, op_extra)
    p8 = 1 - np.prod([1 - o["p_fail_8h"] for o in outlooks.values()] or [1]) * (1 - op_extra)
    cost = prediction.failure_cost(machine, focus["component"]) if focus else (25_000 if op_extra > 0.1 else 0)
    severity = _severity(r, top, float(p8), cost, machine)
    confidence_raw = _confidence(top, memory, focus)
    quality = _quality(r, outlooks, machine) if r.running else None

    return clean(
        {
            "machine": {
                "id": machine.id,
                "name": machine.name,
                "line_id": machine.line_id,
                "product": PRODUCTS[machine.product_key].name,
                "type": machine.type_key,
                "criticality": machine.criticality,
            },
            "plant_time": plant.now.isoformat(timespec="minutes"),
            "state": STATE_NAMES[r.state_code],
            "state_detail": r.state,
            "latest": {k: (None if np.isnan(v) else round(v, 3)) for k, v in r.latest.items() if k in SIGNAL_INFO},
            "ranges": {k: [round(lo, 3), round(hi, 3)] for k, (lo, hi) in r.ranges.items()},
            "anomalies": [a.to_dict() for a in r.anomalies],
            "data_health": r.data_health.to_dict(),
            "components": {
                c: {**o, "window": prediction.failure_window_text(o["p10_h"], o["p90_h"])} for c, o in outlooks.items()
            },
            "operating_risk": op,
            "prediction": {
                "p_fail_8h": round(float(p8), 3),
                "focus_component": focus["component"] if focus else None,
                "rul_h": round(focus["rul_h"], 1) if focus else None,
                "window": prediction.failure_window_text(focus["p10_h"], focus["p90_h"]) if focus else None,
                "method": focus["method"] if focus else None,
                "severity": severity,
                "failure_cost_inr": round(cost, -2),
                "confidence": round(confidence_raw * r.data_health.confidence_factor, 3),
                "confidence_before_data_check": round(confidence_raw, 3),
            },
            "root_cause": {
                "top": top,
                "candidates": causes,
                "chain": root_cause.chain_of_impact(r.anomalies),
                "memory": memory,
            },
            "quality": quality,
            "impact": _impact(r, machine, quality),
            "energy": _energy(r),
            "maintenance_plan": _maintenance_plan(outlooks, plant),
            "priority": round(_priority(r, top, focus, float(p8), cost, machine), 2),
            "tech_tip": _tech_tip(top, r.state),
        }
    )


# ------------------------------------------------------------------ the pieces
def _same_type(machine: Machine) -> set[str]:
    return {m.id for m in MACHINES if m.type_key == machine.type_key}


def _root_causes(r: Readings, op_extra: float, wear_risk: float) -> list[dict]:
    dev = root_cause.deviations(r.latest, r.ranges)
    causes = root_cause.rank_causes(
        dev, r.data_health.untrusted_signals, r.latest.get("tool_wear_min", 0), r.state["idle_waste"]
    )
    if op_extra >= 0.2 and op_extra >= wear_risk:
        # The AI4I model says the cutting conditions are the bigger danger than any worn part: act on that.
        tool = next((c for c in causes if c["key"] == "tool_overstrain"), None) or {
            "key": "tool_overstrain",
            "name": "Worn tool / overstrain",
            "component": None,
            "match": 0.8,
            "fixable_by_partial": True,
            "probability": 0.6,
        }
        causes = [tool] + [c for c in causes if c is not tool]
    return causes


def _focus_component(outlooks: dict, top: dict | None, op_extra: float) -> dict | None:
    """The component the warning is about (None when the risk is the cutting conditions, not wear)."""
    if not outlooks or op_extra > max(o["p_fail_8h"] for o in outlooks.values()):
        return None
    if top and top["component"] in outlooks:
        return outlooks[top["component"]]
    riskiest = max(outlooks.values(), key=lambda o: o["p_fail_8h"])
    return riskiest if riskiest["p_fail_8h"] > 0.01 else None


def _severity(r: Readings, top: dict | None, p8: float, cost: float, machine: Machine) -> str:
    if r.state_code == DOWN:
        return "critical"
    level = prediction.severity(p8, cost, machine.criticality)
    needs_a_look = any(a.severity != "watch" for a in r.anomalies) or (top and top["key"] in NOT_WEAR)
    return "medium" if level == "low" and needs_a_look else level


def _confidence(top: dict | None, memory: dict, focus: dict | None) -> float:
    """Half evidence (pattern match + agreement with past incidents), half model quality."""
    evidence = root_cause.confidence_from_evidence(
        top["match"] if top else 0.5, memory.get("leading_cause_hits", 0), memory.get("count", 0), 1.0
    )
    clear_trend = focus and focus["method"] == "trend" and (focus.get("fit_r2") or 0) > 0.6
    return min(0.97, 0.5 * evidence + 0.5 * (0.9 if clear_trend else 0.8))


def _quality(r: Readings, outlooks: dict, machine: Machine) -> dict:
    damage_now = {c: float(np.nanmedian(r.damage[c][-10:])) for c in COMPONENT_KEYS}
    slopes = {c: o.get("u_slope_per_h") or 0.0 for c, o in outlooks.items()}
    return prediction.quality_outlook(machine, damage_now, slopes, max(r.speed, 0.5))


def _impact(r: Readings, machine: Machine, quality: dict | None) -> dict:
    """What the problem costs per hour right now: missing parts + extra scrap (or the whole machine if down)."""
    product = PRODUCTS[machine.product_key]
    expected_parts_per_h = 3600 / product.ideal_cycle_s * get_calibration().base_performance
    made_last_hour = float(np.nansum(r.series["parts"][-60:]))
    energy_part = r.latest.get("energy_kwh_per_part", float("nan"))
    normal_energy = float(np.mean(r.ranges["energy_kwh_per_part"]))
    lost_parts = round(max(expected_parts_per_h - made_last_hour, 0), 1)
    extra_defects = round(quality["extra_scrap_per_h"], 2) if quality else 0.0
    per_hour = (
        lost_contribution_per_hour(machine)
        if r.state_code == DOWN
        else lost_parts * product.contribution_inr + extra_defects * product.scrap_cost_inr
    )
    return {
        "lost_parts_per_h": lost_parts,
        "extra_defects_per_h": extra_defects,
        "energy_per_part_change_pct": None
        if np.isnan(energy_part)
        else round(100 * (energy_part / normal_energy - 1), 1),
        "inr_per_hour": round(per_hour, -1),
    }


def _energy(r: Readings) -> dict:
    energy_part = r.latest.get("energy_kwh_per_part", float("nan"))
    idle_kw = float(np.nanmedian(r.raw["power_kw"][-10:])) if r.state_code == IDLE else 0.0
    return {
        "idle_power_kw": round(idle_kw, 2),
        "idle_waste": r.state["idle_waste"],
        "energy_per_part_kwh": None if np.isnan(energy_part) else round(energy_part, 3),
        "normal_energy_per_part_kwh": round(float(np.mean(r.ranges["energy_kwh_per_part"])), 3),
    }


def _priority(r: Readings, top: dict | None, focus: dict | None, p8: float, cost: float, machine: Machine) -> float:
    """Probability x impact x urgency (sooner failures rank higher)."""
    if r.state_code == DOWN:
        return 1e7
    urgency = 1 / max(focus["rul_h"], 0.5) ** 0.5 if focus else 0.05
    score = p8 * (cost or 5_000) * urgency * machine.criticality
    return max(score, 500.0) if top and top["key"] in NOT_WEAR else score


def _maintenance_plan(outlooks: dict, plant) -> list[dict]:
    window_h, shift_h = plant.minutes_to_window() / 60, plant.minutes_to_shift_change() / 60
    plan = []
    for c, o in outlooks.items():
        if o["p10_h"] > 21 * 18:  # nothing due in the next three weeks (~18 operating h/day)
            continue
        spec = COMPONENTS[c]
        emergency = o["p10_h"] < shift_h * 0.78
        when = (
            "now"
            if emergency
            else ("next shift change" if o["p10_h"] < window_h * 0.78 else "Sunday maintenance window")
        )
        plan.append(
            {
                "component": c,
                "component_name": spec.name,
                "when": when,
                "emergency": emergency,
                "inspect": WHAT_TO_INSPECT[c],
                "parts": [spec.name],
                "repair_h": spec.planned_repair_h,
                "part_cost_inr": spec.part_cost_inr,
                "needed_within": prediction.failure_window_text(o["p10_h"], o["p90_h"]),
                "p_fail_7d": round(o["p_fail_7d"], 3),
            }
        )
    return plan


def _tech_tip(top: dict | None, state: dict) -> dict | None:
    if state["idle_waste"]:
        key = "energy"
    elif top and top["key"] == "tool_overstrain":
        key = "tool"
    elif top and top["component"]:
        key = top["component"]
    else:
        return None
    title, text = TECH_TIPS[key]
    return {"title": title, "text": text}


def headline(report: dict) -> str:
    """One line for the factory floor tile and the ranked list."""
    p, top, state = report["prediction"], report["root_cause"]["top"], report["state"]
    if state == "breakdown":
        return "Broken down - repair in progress"
    if p["severity"] in ("critical", "high") and p["focus_component"] and p["window"]:
        cause = (
            top["name"]
            if top and top["component"] == p["focus_component"]
            else COMPONENTS[p["focus_component"]].name + " wear"
        )
        stopped = " (stopped for a routine job now)" if state == "maintenance" else ""
        return f"{cause}: failure expected in {p['window']} ({p['p_fail_8h']:.0%} within 8 h){stopped}"
    if state == "maintenance":
        return "In maintenance"
    if state == "idle" and not report["state_detail"]["idle_waste"]:
        return "Short stop (material, set-up or check)"
    modes = report["operating_risk"].get("modes") or {}
    if modes:
        mode, chance = max(modes.items(), key=lambda kv: kv[1])
        return f"{mode} risk {chance:.0%} - tool at {report['latest'].get('tool_wear_min') or 0:.0f} min"
    if report["anomalies"]:
        return report["anomalies"][0]["sentence"].split(" and ")[0]
    if top and top["key"] == "idle_waste":
        return "Idle with spindle and coolant on"
    if p["focus_component"] and p["severity"] != "low":
        return f"{COMPONENTS[p['focus_component']].name} wearing - {p['window']}"
    return "Running normally"
