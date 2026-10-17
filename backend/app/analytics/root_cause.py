"""Root-cause analysis: connect several signals into one explanation.

Vibration up + temperature up + speed down + cycle time up + defects up is not five problems;
it is most likely one: bearing degradation. Each candidate cause has a fault signature
(direction and relative strength per signal). Directions for the four component faults come
from Azure PdM (the sensor that moved most in the 24 h before 761 real-labelled failures);
the secondary effects follow the physics model. The observed pattern is compared with every
signature (cosine similarity) and weighted by how often that cause was confirmed in this
plant's own incident history.
"""

import json
from collections import Counter
from functools import lru_cache

import numpy as np

from app.core.paths import PROCESSED_DIR

SIGNATURE_SIGNALS = [
    "vibration_mm_s",
    "process_temp_c",
    "rpm",
    "torque_nm",
    "power_kw",
    "coolant_bar",
    "voltage_v",
    "cycle_time_s",
    "defect_rate_pct",
    "energy_kwh_per_part",
]

CAUSES = {
    "bearing_degradation": {
        "name": "Spindle bearing degradation",
        "component": "bearing",
        "signature": [3.0, 1.0, -0.6, 0.3, 1.0, 0, 0, 1.0, 1.2, 1.0],
        "fixable_by_partial": False,
    },
    "lubrication_starvation": {
        "name": "Lubrication starvation (bearing)",
        "component": "bearing",
        "signature": [2.2, 1.8, -0.4, 0.2, 1.3, 0, 0, 0.6, 0.8, 1.2],
        "fixable_by_partial": True,
    },
    "drive_slip": {
        "name": "Drive belt slip / wear",
        "component": "drive",
        "signature": [0.5, 0.1, -2.5, 0, -0.3, 0, 0, 1.5, 0.4, 0.4],
        "fixable_by_partial": True,
    },
    "coolant_failure": {
        "name": "Coolant pump wear / clogged filter",
        "component": "coolant",
        "signature": [0, 1.5, 0, 0, 0.2, -2.5, 0, 0, 0.8, 0.2],
        "fixable_by_partial": True,
    },
    "power_module": {
        "name": "Servo power module fault",
        "component": "electrical",
        "signature": [0, 0, 0, 0, 0.3, 0, 2.5, 0, 0.1, 0.1],
        "fixable_by_partial": False,
    },
    "tool_overstrain": {
        "name": "Worn tool / overstrain",
        "component": None,
        "signature": [0.5, 0.2, 0, 2.5, 1.0, 0, 0, 0.1, 0.6, 0.6],
        "fixable_by_partial": True,
    },
}
CHAIN_WORDS = {
    "vibration_mm_s": "Vibration ↑",
    "process_temp_c": "Temperature ↑",
    "rpm": "Spindle speed ↓",
    "torque_nm": "Torque ↑",
    "current_a": "Current ↑",
    "power_kw": "Power ↑",
    "coolant_bar": "Coolant pressure ↓",
    "voltage_v": "Voltage spikes",
    "cycle_time_s": "Cycle time ↑",
    "defect_rate_pct": "Defects ↑",
    "energy_kwh_per_part": "Energy per part ↑",
    "tool_wear_min": "Tool wear ↑",
}
MEMORY_KEYS = {
    "vibration": "vibration_mm_s",
    "rpm": "rpm",
    "coolant_pressure": "coolant_bar",
    "voltage": "voltage_v",
    "process_temp": "process_temp_c",
    "cycle_time": "cycle_time_s",
}


def deviations(latest: dict, ranges: dict) -> dict[str, float]:
    """Signed distance from the middle of the healthy band, in half-band widths."""
    out = {}
    for signal in SIGNATURE_SIGNALS:
        value = latest.get(signal)
        if value is None or np.isnan(value):
            continue
        low, high = ranges[signal]
        half = max((high - low) / 2, 1e-9)
        out[signal] = float(np.clip((value - (low + high) / 2) / half, -8, 8))
    return out


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    return float(a @ b / (na * nb)) if na > 0 and nb > 0 else 0.0


@lru_cache
def incident_history() -> list[dict]:
    path = PROCESSED_DIR / "incident_history.json"
    return json.loads(path.read_text())["incidents"] if path.exists() else []


def rank_causes(dev: dict[str, float], untrusted: list[str], tool_wear: float, idle_waste: bool) -> list[dict]:
    # Only deviations beyond the band edge count as evidence.
    observed = np.array([np.sign(dev.get(s, 0)) * max(abs(dev.get(s, 0)) - 1, 0) for s in SIGNATURE_SIGNALS])
    priors = Counter(i["root_cause"] for i in incident_history())
    total = sum(priors.values()) or 1
    ranked = []
    if np.linalg.norm(observed) > 0.3:
        for key, cause in CAUSES.items():
            score = max(_cosine(observed, np.array(cause["signature"], float)), 0)
            if key == "tool_overstrain":
                score *= 1.0 if tool_wear > 170 else 0.4
            prior = priors.get(cause["name"], 0) / total
            ranked.append(
                {
                    "key": key,
                    "name": cause["name"],
                    "component": cause["component"],
                    "match": round(0.85 * score + 0.15 * min(prior * 4, 1), 3),
                    "fixable_by_partial": cause["fixable_by_partial"],
                }
            )
    if "vibration_mm_s" in untrusted and dev.get("vibration_mm_s", 0) > 1:
        ranked.append(
            {
                "key": "sensor_drift",
                "name": "Vibration sensor drift (not a machine fault)",
                "component": None,
                "match": 0.9,
                "fixable_by_partial": True,
            }
        )
        for r in ranked:
            if r["component"] == "bearing":
                r["match"] = round(r["match"] * 0.4, 3)
    if idle_waste:
        ranked.append(
            {
                "key": "idle_waste",
                "name": "Spindle and coolant left running while idle",
                "component": None,
                "match": 0.95,
                "fixable_by_partial": True,
            }
        )
    ranked.sort(key=lambda r: -r["match"])
    total_match = sum(r["match"] for r in ranked[:3]) or 1
    for r in ranked:
        r["probability"] = round(r["match"] / total_match, 3) if r in ranked[:3] else 0.0
    return ranked[:4]


def chain_of_impact(anomalies: list) -> list[dict]:
    """Order the abnormal signals by when they started - the earliest is closest to the cause."""
    steps = sorted(anomalies, key=lambda a: -a.onset_minutes_ago)
    return [
        {
            "signal": a.signal,
            "text": CHAIN_WORDS.get(a.signal, a.label),
            "minutes_ago": a.onset_minutes_ago,
            "deviation_pct": round(a.deviation_pct, 1),
        }
        for a in steps
    ]


def similar_incidents(dev: dict[str, float], machine_type_ids: set[str], limit: int = 7) -> dict:
    """'Have we seen this before?' - compare today's sensor pattern with past incidents."""
    keys = list(MEMORY_KEYS)
    current = np.array([dev.get(MEMORY_KEYS[k], 0.0) for k in keys])
    if np.linalg.norm(current) < 1:
        return {"count": 0, "matches": [], "sentence": "No unusual pattern to compare with past incidents."}
    matches = []
    for incident in incident_history():
        past = np.array([incident["pattern_z"].get(k, 0.0) for k in keys])
        similarity = _cosine(current, past)
        if similarity >= 0.8:
            same_type = incident["machine_id"] in machine_type_ids
            matches.append({**incident, "similarity": round(similarity + (0.02 if same_type else 0), 3)})
    matches.sort(key=lambda m: -m["similarity"])
    top = matches[:limit]
    if not top:
        return {"count": 0, "matches": [], "sentence": "This pattern does not match any past incident."}
    causes = Counter(m["root_cause"] for m in top)
    cause, hits = causes.most_common(1)[0]
    return {
        "count": len(top),
        "total_similar": len(matches),
        "matches": top,
        "leading_cause": cause,
        "leading_cause_hits": hits,
        "sentence": f"This pattern is similar to {len(top)} previous incidents. "
        f"In {hits} cases, {cause.lower()} was confirmed.",
    }


def confidence_from_evidence(match: float, hits: int, count: int, data_factor: float) -> float:
    memory = (hits + 1) / (count + 2) if count else 0.5  # Laplace-smoothed agreement with history
    return round(min(0.97, (0.55 * match + 0.45 * memory)) * data_factor, 3)
