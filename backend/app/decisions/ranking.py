"""Pick the best option by the plant's priorities, with one hard safety rule."""

from app.plant.factory import Machine

# fmt: off
WEIGHT_PRESETS = {
    "balanced":         {"cost": .3, "production": .2, "quality": .15, "energy": .1, "maintenance": .1, "risk": .15},
    "production_first": {"cost": .2, "production": .4, "quality": .1, "energy": .05, "maintenance": .1, "risk": .15},
    "quality_first":    {"cost": .15, "production": .15, "quality": .4, "energy": .05, "maintenance": .1, "risk": .15},
    "energy_saver":     {"cost": .2, "production": .15, "quality": .1, "energy": .35, "maintenance": .05, "risk": .15},
    "safety_first":     {"cost": .15, "production": .15, "quality": .1, "energy": .05, "maintenance": .1, "risk": .45},
}
# fmt: on
CRITERIA = {
    "cost": "total_inr",
    "production": "lost_parts",
    "quality": "extra_defects",
    "energy": "energy_cost_inr",
    "maintenance": "maintenance_cost_inr",
    "risk": "p_fail",
}
DO_NOTHING = ("continue_to_window", "continue_tool", "leave_idle_running", "ignore_sensor")


def rank(options: list[dict], weights: dict[str, float], severity: str) -> list[dict]:
    """Score = weighted sum of each criterion scaled 0 (best option) .. 1 (worst). Lower is better.

    Safety rule: when the risk is high or critical, an option that leaves a >= 60% chance of
    breakdown is pushed to the bottom, whatever it costs.
    """
    total_weight = sum(weights.values()) or 1
    for option in options:
        option["score_parts"] = {}
    for criterion, field in CRITERIA.items():
        values = [o[field] for o in options]
        lo, hi = min(values), max(values)
        for option, value in zip(options, values, strict=True):
            option["score_parts"][criterion] = 0.0 if hi == lo else (value - lo) / (hi - lo)
    for option in options:
        score = sum(weights.get(k, 0) * v for k, v in option["score_parts"].items()) / total_weight
        score -= 0.1 * option["confidence"]
        option["safety_blocked"] = severity in ("critical", "high") and option["p_fail"] >= 0.6
        option["score"] = round(score + (1.0 if option["safety_blocked"] else 0.0), 4)
    return sorted(options, key=lambda o: o["score"])


def recommendation(ranked: list[dict], machine: Machine, cause_name: str) -> dict:
    """The best option, compared with doing nothing, in plain sentences."""
    best = ranked[0]
    baseline = next((o for o in ranked if o["key"] in DO_NOTHING), None) or max(ranked, key=lambda o: o["total_inr"])
    changed = baseline is not best
    why = [f"Likely cause: {cause_name}."]
    if changed:
        why.append(f"Failure probability {baseline['p_fail']:.0%} → {best['p_fail']:.0%}.")
    why.append(
        f"Planned downtime {best['downtime_h']:.1f} h"
        + (f" instead of an expected {baseline['downtime_h']:.1f} h of breakdown." if changed else ".")
    )
    if best["learned"]["trials"]:
        why.append(
            f"This action worked in {best['learned']['successes']} of {best['learned']['trials']} similar cases here."
        )
    if any(o["safety_blocked"] for o in ranked):
        why.append("Options that leave a likely breakdown running were ruled out for safety.")
    return {
        "action_key": best["key"],
        "headline": f"{best['title']} on {machine.id}",
        "value_protected_inr": round(max(baseline["total_inr"] - best["total_inr"], 0), -2),
        "p_fail_before": baseline["p_fail"],
        "p_fail_after": best["p_fail"],
        "added_downtime_h": round(best["downtime_h"], 1),
        "confidence": best["confidence"],
        "why": why,
    }
