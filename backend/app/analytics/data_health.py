"""Factory data health: AI should not pretend to be certain when the data is bad.

Checks the last hour of readings for missing values, noise, drift that other sensors do not
confirm, staleness, calibration age and physically inconsistent measurements, then turns the
result into a confidence multiplier used by every prediction and recommendation.
"""

from dataclasses import dataclass, field

import numpy as np

from app.plant.physics import POWER_FACTOR, SQRT3

from .signals import SIGNAL_INFO

CORE_SIGNALS = ["vibration_mm_s", "process_temp_c", "rpm", "torque_nm", "current_a", "voltage_v", "coolant_bar"]
EXPECTED_STEP_NOISE = {
    "vibration_mm_s": 0.07,
    "process_temp_c": 0.3,
    "rpm": 0.01,
    "torque_nm": 0.05,
    "current_a": 0.035,
    "voltage_v": 0.008,
    "coolant_bar": 0.035,
}


@dataclass
class DataHealth:
    score: int
    confidence_factor: float
    issues: list[dict] = field(default_factory=list)
    completeness_pct: float = 100.0
    untrusted_signals: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def assess(
    values: dict[str, np.ndarray], ranges: dict, calibration_days: int, running: bool, valid: np.ndarray | None = None
) -> DataHealth:
    """`valid` marks the minutes a reading was expected (machine cutting); gaps elsewhere are not faults."""
    issues, penalty, untrusted = [], 0.0, []
    window = {k: v[-60:] for k, v in values.items()}
    expected = valid[-60:] if valid is not None else np.ones(len(window[CORE_SIGNALS[0]]), dtype=bool)

    completeness = []
    for signal in CORE_SIGNALS:
        missing = float(np.mean(np.isnan(window[signal][expected]))) if expected.any() else 0.0
        completeness.append(1 - missing)
        if missing > 0.1:
            penalty += min(25, missing * 60)
            untrusted.append(signal)
            issues.append(
                {
                    "type": "missing",
                    "signal": signal,
                    "text": f"{SIGNAL_INFO[signal].label} sensor is missing {missing:.0%} of readings",
                }
            )

    if running:
        for signal in CORE_SIGNALS:
            series = window[signal][~np.isnan(window[signal])]
            if len(series) < 20:
                continue
            steps = np.diff(series) / max(np.median(np.abs(series)), 1e-9)
            ratio = np.median(np.abs(steps)) / EXPECTED_STEP_NOISE[signal]
            if ratio > 3:
                penalty += 8
                issues.append(
                    {
                        "type": "noisy",
                        "signal": signal,
                        "text": f"{SIGNAL_INFO[signal].label} readings are {ratio:.0f}x noisier than usual",
                    }
                )

        # Drift: vibration far outside its band while heat and power - which a real bearing problem
        # would also move - stay normal.
        vib = np.nanmedian(window["vibration_mm_s"][-10:])
        heat_ok = np.nanmedian(window["process_temp_c"][-10:]) <= ranges["process_temp_c"][1]
        power_ok = np.nanmedian(window["power_kw"][-10:]) <= ranges["power_kw"][1]
        if vib > ranges["vibration_mm_s"][1] * 1.15 and heat_ok and power_ok:
            penalty += 20
            if "vibration_mm_s" not in untrusted:
                untrusted.append("vibration_mm_s")
            issues.append(
                {
                    "type": "drift",
                    "signal": "vibration_mm_s",
                    "text": "Vibration is rising but temperature and power are normal - sensor drift suspected",
                }
            )

        p = np.nanmedian(window["power_kw"][-10:])
        p_from_current = (
            SQRT3
            * np.nanmedian(window["voltage_v"][-10:])
            * np.nanmedian(window["current_a"][-10:])
            * POWER_FACTOR
            / 1000
        )
        if p > 0 and abs(p_from_current - p) / p > 0.12:
            penalty += 12
            issues.append(
                {
                    "type": "inconsistent",
                    "signal": "current_a",
                    "text": "Power and current readings disagree - check the meter wiring",
                }
            )

    if running and np.all(np.isnan(window["vibration_mm_s"][-5:])) and np.all(np.isnan(window["rpm"][-5:])):
        penalty += 30
        issues.append({"type": "stale", "signal": None, "text": "No fresh readings in the last 5 minutes"})

    if calibration_days > 365:
        penalty += 8
        issues.append(
            {
                "type": "calibration",
                "signal": None,
                "text": f"Sensors last calibrated {calibration_days} days ago (due every 365)",
            }
        )

    score = int(max(0, round(100 - penalty)))
    return DataHealth(
        score=score,
        confidence_factor=round(0.55 + 0.45 * score / 100, 3),
        issues=issues,
        completeness_pct=round(100 * float(np.mean(completeness)), 1),
        untrusted_signals=untrusted,
    )
