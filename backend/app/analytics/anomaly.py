"""Anomaly detection with a sentence a person can act on.

Not "Temperature is high." but "Temperature is 18% above its normal operating range and
has increased continuously for 43 minutes."

Method: a robust 5-minute median smooths noise; a signal is anomalous when the smoothed
value leaves the machine's healthy band. Duration = minutes since it last sat inside the
band; "rising for N minutes" = length of the current monotonic run of the 10-minute trend.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .signals import SIGNAL_INFO, WORSE_WHEN_HIGH, fmt

WATCHED = [
    "vibration_mm_s",
    "process_temp_c",
    "rpm",
    "torque_nm",
    "current_a",
    "coolant_bar",
    "voltage_v",
    "cycle_time_s",
    "defect_rate_pct",
    "energy_kwh_per_part",
    "tool_wear_min",
]


@dataclass
class Anomaly:
    signal: str
    label: str
    value: float
    normal_low: float
    normal_high: float
    deviation_pct: float  # how far outside the band, % of the nearer edge (signed: + above, - below)
    minutes_outside: int
    trend_minutes: int  # minutes the signal has kept moving the wrong way
    severity: str  # "watch" | "warning" | "critical"
    sentence: str
    plain_sentence: str
    onset_minutes_ago: int

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def smooth(series: np.ndarray, window: int = 5) -> np.ndarray:
    """Rolling median that ignores missing readings."""
    return pd.Series(series).rolling(window, min_periods=1).median().to_numpy()


def _trend_run(smoothed: np.ndarray, rising: bool) -> int:
    """How many recent minutes the 20-minute trend has pointed the same way."""
    valid = smooth(smoothed[~np.isnan(smoothed)], 9)
    if len(valid) < 25:
        return 0
    slope = valid[20:] - valid[:-20]
    good = slope > 0 if rising else slope < 0
    run = 0
    for flag in good[::-1]:
        if not flag:
            break
        run += 1
    return int(run)


def detect(series_by_signal: dict[str, np.ndarray], ranges: dict[str, tuple[float, float]]) -> list[Anomaly]:
    found = []
    for signal in WATCHED:
        series = series_by_signal.get(signal)
        if series is None or np.all(np.isnan(series[-15:])):
            continue
        smoothed = smooth(series[-180:])
        value = smoothed[-1]
        if np.isnan(value):
            continue
        low, high = ranges[signal]
        if low <= value <= high:
            continue
        above = value > high
        if signal != "voltage_v" and above != (signal in WORSE_WHEN_HIGH):
            continue  # e.g. low vibration or high coolant pressure is not a problem
        edge = high if above else low
        deviation = 100 * (value - edge) / max(abs(edge), 1e-9)
        inside = (smoothed >= low) & (smoothed <= high)
        outside_for = int(len(smoothed) - 1 - np.max(np.nonzero(inside)[0])) if inside.any() else len(smoothed)
        trend = _trend_run(smoothed, rising=above)
        magnitude = abs(deviation)
        severity = "critical" if magnitude >= 25 else "warning" if magnitude >= 8 else "watch"

        info = SIGNAL_INFO[signal]
        direction = "above" if above else "below"
        verb = "increased" if above else "decreased"
        sentence = (
            f"{info.label} is {magnitude:.0f}% {direction} its normal operating range "
            f"({fmt(signal, low)} – {fmt(signal, high)})"
        )
        if trend >= 10:
            sentence += f" and has {verb} continuously for {trend} minutes."
        else:
            sentence += f" and has been outside it for {outside_for} minutes."
        plain = f"{info.plain} is {'higher' if above else 'lower'} than normal ({fmt(signal, value)})."
        found.append(
            Anomaly(
                signal,
                info.label,
                float(value),
                low,
                high,
                float(deviation),
                outside_for,
                trend,
                severity,
                sentence,
                plain,
                outside_for,
            )
        )
    order = {"critical": 0, "warning": 1, "watch": 2}
    return sorted(found, key=lambda a: (order[a.severity], -abs(a.deviation_pct)))
