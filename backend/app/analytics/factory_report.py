"""The whole plant at a glance: shift KPIs, health scores, ranked risks, lines and the floor map."""

import numpy as np

from app.core.jsonsafe import clean
from app.plant.calibration import COMPONENT_KEYS
from app.plant.factory import LINES, MACHINES
from app.plant.live import DOWN, MAINTENANCE, RUNNING, S, get_plant

from . import prediction
from .machine_report import headline, machine_report, read_machine
from .minute_cache import cached_for_this_minute

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def all_machine_reports() -> list[dict]:
    """Every machine, with the slow model calls batched into one call per model."""
    get_plant().advance()
    readings = {m.id: read_machine(m.id) for m in MACHINES}
    rul_requests = []
    for r in readings.values():
        if r.state_code != DOWN:
            for c in COMPONENT_KEYS:
                damage_now, trend = prediction.outlook_inputs(r.damage[c], r.minutes)
                rul_requests.append(
                    prediction.rul_key(
                        c, damage_now, prediction.trend_damage_slope(trend, damage_now), r.state["component_age_h"][c]
                    )
                )
    prediction.prime_rul_cache(rul_requests)
    risks = prediction.operating_point_risk_batch([r.latest if r.running else {} for r in readings.values()])
    return [machine_report(machine_id, risk) for machine_id, risk in zip(readings, risks, strict=True)]


def factory_report() -> dict:
    get_plant().advance()
    return cached_for_this_minute(("factory",), _build)


def _build() -> dict:
    plant = get_plant()
    reports = all_machine_reports()
    _, data = plant.frame(_minutes_into_shift(plant.now))
    kpis = shift_kpis(data, range(len(MACHINES)))

    tiles = [
        {
            "id": a["machine"]["id"],
            "name": a["machine"]["name"],
            "line_id": a["machine"]["line_id"],
            "state": a["state"],
            "severity": a["prediction"]["severity"],
            "p_fail_8h": a["prediction"]["p_fail_8h"],
            "health_pct": min((c["health_pct"] for c in a["components"].values()), default=None),
            "headline": headline(a),
            "priority": a["priority"],
            "data_score": a["data_health"]["score"],
            "speed_pct": a["state_detail"]["speed_pct"],
        }
        for a in reports
    ]
    ranked = sorted(tiles, key=lambda t: (-t["priority"], SEVERITY_ORDER[t["severity"]]))
    risks = [t for t in ranked if t["severity"] != "low" or t["state"] == "breakdown"][:8]

    energy_kwh = float(np.nansum(data[:, :, S["energy_kwh"]]))
    good_parts = float(np.nansum(data[:, :, S["parts"]] - data[:, :, S["defects"]]))
    return clean(
        {
            "plant_time": plant.now.isoformat(timespec="minutes"),
            "shift": _shift_name(plant.now.hour),
            "kpis": {
                **kpis,
                "energy_kwh": round(energy_kwh, 1),
                "energy_kwh_per_part": round(energy_kwh / max(good_parts, 1), 3),
                "running": sum(t["state"] == "running" for t in tiles),
                "machines": len(MACHINES),
                "down_now": [t["id"] for t in tiles if t["state"] == "breakdown"],
                "anomalies": sum(len(a["anomalies"]) for a in reports),
            },
            "health": _health_scores(tiles, reports, kpis),
            "maintenance": {
                "planned_jobs": sum(len(a["state_detail"]["pending_jobs"]) for a in reports),
                "in_maintenance": [t["id"] for t in tiles if t["state"] == "maintenance"],
                "due_soon": [{"machine": a["machine"]["id"], **p} for a in reports for p in a["maintenance_plan"]][:6],
            },
            "risk_level": min((t["severity"] for t in tiles), key=SEVERITY_ORDER.get),
            "machines": tiles,
            "risks": risks,
            "lines": _lines(plant, data, tiles),
            "events": plant.recent_events(limit=12)[::-1],
            "window_in_h": round(plant.minutes_to_window() / 60, 1),
            "shift_change_in_h": round(plant.minutes_to_shift_change() / 60, 1),
        }
    )


def shift_kpis(data: np.ndarray, machine_indexes) -> dict:
    """OEE = availability x performance x quality over the minutes in `data`."""
    idx = list(machine_indexes)
    states = data[:, idx, S["state"]]
    running_minutes = np.sum(states == RUNNING)
    parts = float(np.nansum(data[:, idx, S["parts"]]))
    defects = float(np.nansum(data[:, idx, S["defects"]]))
    availability = running_minutes / max(states.size, 1)
    performance = min(float(np.nansum(data[:, idx, S["ideal_s"]])) / max(running_minutes * 60, 1), 1.0)
    quality = (parts - defects) / parts if parts else 1.0
    return {
        "oee": round(availability * performance * quality, 4),
        "availability": round(availability, 4),
        "performance": round(performance, 4),
        "quality": round(quality, 4),
        "parts": round(parts),
        "good_parts": round(parts - defects),
        "defect_rate": round(defects / max(parts, 1), 4),
        "downtime_min": int(np.sum(states == DOWN)),
        "maintenance_min": int(np.sum(states == MAINTENANCE)),
    }


def _health_scores(tiles: list[dict], reports: list[dict], kpis: dict) -> dict:
    """0-100 scores; 100 = as good as this part of the plant can be."""
    average_damage = np.mean([1 - (t["health_pct"] or 100) / 100 for t in tiles])
    energy_changes = [max(a["impact"]["energy_per_part_change_pct"] or 0, 0) for a in reports]
    idle_waste = sum(a["state_detail"]["idle_waste"] for a in reports)
    return {
        "machine": round(100 * (1 - average_damage)),
        "production": round(100 * min(kpis["availability"] * kpis["performance"] / 0.85, 1)),  # vs world-class 85%
        "quality": round(100 * max(0.0, 1 - max(1 - kpis["quality"] - 0.01, 0) / 0.04)),  # 1% scrap = 100, 5% = 0
        "energy": round(100 * max(0.0, 1 - idle_waste * 0.08 - np.mean(energy_changes) / 100)),
        "data": round(float(np.mean([a["data_health"]["score"] for a in reports]))),
    }


def _lines(plant, data: np.ndarray, tiles: list[dict]) -> list[dict]:
    lines = []
    for line in LINES:
        idx = [plant.index[m.id] for m in MACHINES if m.line_id == line.id]
        worst = min((t for t in tiles if t["line_id"] == line.id), key=lambda t: SEVERITY_ORDER[t["severity"]])
        lines.append(
            {
                "id": line.id,
                "name": line.name,
                **shift_kpis(data, idx),
                "worst_machine": worst["id"],
                "worst_severity": worst["severity"],
            }
        )
    return lines


def _minutes_into_shift(now) -> int:
    start = 22 if now.hour >= 22 or now.hour < 6 else (14 if now.hour >= 14 else 6)
    return max(min(((now.hour - start) % 24) * 60 + now.minute, 480), 30)


def _shift_name(hour: int) -> str:
    return "Night shift" if hour >= 22 or hour < 6 else ("Afternoon shift" if hour >= 14 else "Morning shift")
