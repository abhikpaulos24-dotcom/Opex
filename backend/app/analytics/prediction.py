"""Failure prediction: probability, remaining useful life, failure window, severity, confidence.

Two complementary estimators per component:
  * trend   - damage is mapped back to life fraction (NASA C-MAPSS curve), which grows linearly
              in time under constant stress, so a straight-line fit gives time-to-failure with
              an uncertainty band. Catches fast, accelerating faults.
  * model   - the C-MAPSS-trained gradient-boosting RUL model on health-index features + age.
              Catches slow wear that a 2-hour trend cannot see.
The shorter (more cautious) estimate wins. Operating-point risk (tool overstrain, power,
heat) comes from the AI4I failure-mode classifier.
"""

import logging
import math
from functools import lru_cache

import joblib
import numpy as np
import pandas as pd

from app.core.paths import MODELS_DIR
from app.plant import physics
from app.plant.calibration import COMPONENT_KEYS, get_calibration, mean_life_hours
from app.plant.factory import COMPONENTS, PRODUCTS, Machine, lost_contribution_per_hour

log = logging.getLogger(__name__)

AI4I_MODES = {
    "TWF": "Tool wear failure",
    "HDF": "Heat dissipation failure",
    "PWF": "Power failure",
    "OSF": "Overstrain failure",
}
Z90 = 1.2816
TREND_WINDOW = 240  # minutes of history used for the live damage trend


@lru_cache
def _models() -> dict:
    loaded = {}
    for name in ("failure_mode_model", "rul_model"):
        path = MODELS_DIR / f"{name}.joblib"
        if path.exists():
            loaded[name] = joblib.load(path)
        else:
            log.warning("model %s missing - run the pipeline; falling back to trend-only predictions", name)
    return loaded


def operating_point_risk(latest: dict) -> dict:
    return operating_point_risk_batch([latest])[0]


def operating_point_risk_batch(rows: list[dict]) -> list[dict]:
    """AI4I classifier on each machine's current operating point (one model call for all)."""
    model = _models().get("failure_mode_model")
    results = [{"probability": 0.0, "modes": {}} for _ in rows]
    usable = [
        i
        for i, r in enumerate(rows)
        if model is not None and not np.isnan(r.get("torque_nm", np.nan)) and r.get("rpm", 0) > 100
    ]
    if not usable:
        return results
    frame = pd.DataFrame(
        [
            {
                "air_temp_c": r["air_temp_c"],
                "process_temp_c": r["process_temp_c"],
                "temp_delta_c": r["process_temp_c"] - r["air_temp_c"],
                "rpm": r["rpm"],
                "torque_nm": r["torque_nm"],
                "tool_wear_min": r["tool_wear_min"],
                "power_kw": r["torque_nm"] * r["rpm"] * 2 * math.pi / 60 / 1000,
                "wear_x_torque": r["tool_wear_min"] * r["torque_nm"],
                "quality_level": 1,
            }
            for r in (rows[i] for i in usable)
        ]
    )[model["features"]]
    for i, proba_row in zip(usable, model["model"].predict_proba(frame), strict=False):
        proba = dict(zip(model["model"].classes_, proba_row, strict=False))
        results[i] = {
            "probability": float(1 - proba["none"]),
            "threshold": model["threshold"],
            "modes": {AI4I_MODES[k]: float(v) for k, v in proba.items() if k in AI4I_MODES and v >= 0.02},
        }
    return results


def _trend_rul(damage_series: np.ndarray, minutes: np.ndarray, b: float) -> dict | None:
    """Fit life fraction against time; returns hours to failure with a 10-90% band."""
    ok = ~np.isnan(damage_series)
    if ok.sum() < 60:
        return None
    # Only trust a trend that is both real damage and a clear rise, not sensor noise.
    early, late = np.nanmean(damage_series[:30]), np.nanmean(damage_series[-30:])
    if late < 0.3 or late - early < 0.06:
        return None
    u = physics.life_fraction_from_damage(damage_series[ok], b)
    hours = minutes[ok] / 60.0
    slope, intercept = np.polyfit(hours, u, 1)
    if slope <= 0:
        return None
    residual = u - (slope * hours + intercept)
    se = np.sqrt(np.sum(residual**2) / max(len(u) - 2, 1) / np.sum((hours - hours.mean()) ** 2))
    r2 = 1 - np.var(residual) / max(np.var(u), 1e-12)
    if slope / max(se, 1e-12) < 4 or r2 < 0.35:  # trend not clearly above noise
        return None
    u_now = slope * hours[-1] + intercept
    rul = max((1 - u_now) / slope, 0.05)
    sigma = math.sqrt((se / slope) ** 2 + get_calibration().rul_rel_error_sd ** 2)
    return {
        "rul_h": rul,
        "p10_h": rul * math.exp(-Z90 * sigma),
        "p90_h": rul * math.exp(Z90 * sigma),
        "sigma": sigma,
        "method": "trend",
        "fit_r2": float(max(r2, 0)),
        "u_slope_per_h": float(slope),
    }


_rul_cache: dict[tuple, dict] = {}


def rul_key(component: str, damage_now: float, damage_slope_per_h: float | None, age_h: float) -> tuple:
    slope = None if damage_slope_per_h is None else round(damage_slope_per_h, 3)
    return component, round(damage_now, 2), slope, round(age_h, -1)


def prime_rul_cache(keys: list[tuple]) -> None:
    """Run the C-MAPSS RUL model once for every (component, damage, slope, age) not seen yet."""
    rul_model = _models().get("rul_model")
    missing = [k for k in dict.fromkeys(keys) if k not in _rul_cache]
    if rul_model is None or not missing:
        return
    b = get_calibration().degradation_b
    span = rul_model["hi_healthy"] - rul_model["hi_failed"]
    rows = []
    for component, damage, slope, age in missing:
        life_h = mean_life_hours(component)
        if slope is None:  # no visible trend: use the typical slope of the fleet at this damage level
            u = physics.life_fraction_from_damage(damage, b)
            slope_cycle = -span * b * math.exp(b * u) / (math.exp(b) - 1) / rul_model["mean_life"]
        else:
            slope_cycle = -slope * span * life_h / rul_model["mean_life"]
        rows.append(
            {
                "hi": rul_model["hi_healthy"] - damage * span,
                "slope_10": slope_cycle,
                "slope_30": slope_cycle,
                "age_frac": age / life_h,
            }
        )
    frame = pd.DataFrame(rows)[rul_model["features"]]
    point, low, high = (rul_model[k].predict(frame) for k in ("point", "low", "high"))
    for key, p, lo, hi in zip(missing, point, low, high, strict=False):
        life_h = mean_life_hours(key[0])
        rul = max(float(p) * life_h, 0.5)
        p10 = min(max(float(lo) * life_h, 0.25), rul)
        p90 = max(float(hi) * life_h, rul * 1.05)
        _rul_cache[key] = {
            "rul_h": rul,
            "p10_h": p10,
            "p90_h": p90,
            "sigma": max(math.log(p90 / max(p10, 1e-3)) / (2 * Z90), 0.1),
            "method": "model",
            "fit_r2": None,
        }
    if len(_rul_cache) > 20_000:
        _rul_cache.clear()


def outlook_inputs(damage: np.ndarray, minutes: np.ndarray) -> tuple[float, dict | None]:
    """Current damage and (if there is a real trend) the trend-based RUL."""
    recent = damage[~np.isnan(damage)]
    damage_now = float(np.median(recent[-10:])) if len(recent) else 0.0
    return damage_now, _trend_rul(damage[-TREND_WINDOW:], minutes[-TREND_WINDOW:], get_calibration().degradation_b)


def trend_damage_slope(trend: dict | None, damage_now: float) -> float | None:
    if trend is None:
        return None
    b = get_calibration().degradation_b
    u = physics.life_fraction_from_damage(damage_now, b)
    return trend["u_slope_per_h"] * b * math.exp(b * u) / (math.exp(b) - 1)


def prob_fail_within(rul: dict, horizon_h: float) -> float:
    z = (math.log(max(horizon_h, 1e-6)) - math.log(rul["rul_h"])) / rul["sigma"]
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


_sticky: dict[tuple, tuple[int, float, dict]] = {}
STICKY_MINUTES = 45


def component_outlook(
    component: str, damage: np.ndarray, minutes: np.ndarray, age_h: float, machine_id: str = ""
) -> dict:
    damage_now, trend = outlook_inputs(damage, minutes)
    # Alarm hygiene (ISA-18.2): a trend warning stays up for a while instead of chattering on and off.
    key_sticky, minute = (machine_id, component), int(minutes[-1]) if len(minutes) else 0
    if trend is not None:
        _sticky[key_sticky] = (minute, damage_now, trend)
    elif key_sticky in _sticky:
        seen_at, seen_damage, old = _sticky[key_sticky]
        elapsed_h = (minute - seen_at) / 60
        if 0 <= minute - seen_at <= STICKY_MINUTES and damage_now >= seen_damage - 0.02:
            trend = {
                **old,
                "rul_h": max(old["rul_h"] - elapsed_h, 0.05),
                "p10_h": max(old["p10_h"] - elapsed_h, 0.05),
                "p90_h": max(old["p90_h"] - elapsed_h, 0.1),
            }
        else:
            _sticky.pop(key_sticky, None)
    key = rul_key(component, damage_now, trend_damage_slope(trend, damage_now), age_h)
    prime_rul_cache([key])
    candidates = [r for r in (trend, _rul_cache.get(key)) if r]
    if not candidates:
        best = {"rul_h": 5000.0, "p10_h": 2000.0, "p90_h": 9000.0, "sigma": 0.6, "method": "prior", "fit_r2": None}
    else:
        best = min(candidates, key=lambda r: r["rul_h"])
    best = {
        **best,
        "component": component,
        "component_name": COMPONENTS[component].name,
        "damage": round(damage_now, 3),
        "health_pct": round(100 * (1 - damage_now)),
    }
    best["p_fail_8h"] = prob_fail_within(best, 8)
    best["p_fail_24h"] = prob_fail_within(best, 24)
    best["p_fail_7d"] = prob_fail_within(best, 7 * 18)  # ~18 operating hours per calendar day
    return best


def failure_window_text(p10: float, p90: float) -> str:
    def h(x: float) -> str:
        if x < 1:
            return f"{max(x * 60, 5):.0f} min"
        if x < 48:
            return f"{x:.0f} h"
        return f"{x / 18:.0f} days"

    return f"{h(p10)} – {h(p90)}"


def failure_cost(machine: Machine, component: str) -> float:
    """Expected cost if this component breaks down instead of being swapped on plan."""
    spec = COMPONENTS[component]
    hours = spec.unplanned_repair_h * 1.4 + spec.stockout_prob * spec.stockout_wait_h
    return (
        spec.part_cost_inr
        + hours * 300 * 1.5
        + spec.collateral_prob * spec.collateral_cost_inr
        + hours * lost_contribution_per_hour(machine)
    )


def severity(p8: float, cost: float, criticality: float) -> str:
    exposure = p8 * cost * criticality
    if p8 >= 0.5 or exposure >= 150_000:
        return "critical"
    if p8 >= 0.2 or exposure >= 40_000:
        return "high"
    if p8 >= 0.05 or exposure >= 8_000:
        return "medium"
    return "low"


def quality_outlook(
    machine: Machine, damage_now: dict, trend_slopes: dict, speed: float, hours_ahead: float = 3
) -> dict:
    cal = get_calibration()
    base = 1 - cal.base_quality

    def rate(damages: dict) -> float:
        return float(physics.defect_rate(base, physics.Wear(**damages), speed))

    future = {}
    for c in COMPONENT_KEYS:
        u = physics.life_fraction_from_damage(damage_now[c], cal.degradation_b) + trend_slopes.get(c, 0) * hours_ahead
        future[c] = float(physics.damage_from_life_fraction(u, cal.degradation_b))
    now, later = rate(damage_now), rate(future)
    parts_per_h = 3600 / PRODUCTS[machine.product_key].ideal_cycle_s
    return {
        "defect_rate_now": now,
        "defect_rate_later": later,
        "hours_ahead": hours_ahead,
        "extra_scrap_per_h": max(now - base, 0) * parts_per_h,
        "sentence": f"At current machine conditions, defect probability is expected to "
        f"{'increase' if later > now + 0.001 else 'stay near'} {now:.1%}"
        + (f" → {later:.1%} within {hours_ahead:.0f} hours." if later > now + 0.001 else "."),
    }
