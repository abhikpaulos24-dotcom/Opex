"""Loads data/processed/calibration.json (written by the pipeline) into a typed object.

If the pipeline has never run, sensible defaults keep the app working; the Data page then
shows "calibration missing" so nobody mistakes defaults for measured values.
"""

import json
import logging
from dataclasses import dataclass, field
from functools import lru_cache

from app.core.paths import MODELS_DIR, PROCESSED_DIR
from app.plant.factory import planned_hours_per_year

log = logging.getLogger(__name__)

COMPONENT_KEYS = ("bearing", "drive", "electrical", "coolant")


@dataclass(frozen=True)
class Calibration:
    failures_per_year: dict[str, float]
    detection_recall: dict[str, float]
    false_alarms_per_year: dict[str, float]
    signatures: dict[str, dict[str, float]]
    weibull_shape: float
    degradation_b: float
    degradation_onset: float
    rul_rel_error_sd: float
    rul_rel_error_mean: float
    repair_log_sigma: float
    other_unplanned_share: float
    planned_stop_share: float
    base_performance: float
    base_quality: float
    is_measured: bool
    raw: dict = field(default_factory=dict, compare=False)


_DEFAULTS = Calibration(
    failures_per_year={"bearing": 1.8, "drive": 2.6, "electrical": 1.9, "coolant": 1.3},
    detection_recall={k: 0.9 for k in COMPONENT_KEYS},
    false_alarms_per_year={k: 2.0 for k in COMPONENT_KEYS},
    signatures={
        "bearing": {"vibration": 1.4},
        "drive": {"rotate": -1.1},
        "electrical": {"volt": 1.0},
        "coolant": {"pressure": 1.6},
    },
    weibull_shape=4.4,
    degradation_b=3.75,
    degradation_onset=0.46,
    rul_rel_error_sd=0.2,
    rul_rel_error_mean=0.0,
    repair_log_sigma=0.8,
    other_unplanned_share=0.089,
    planned_stop_share=0.086,
    base_performance=0.93,
    base_quality=0.983,
    is_measured=False,
)


def mean_life_hours(component: str) -> float:
    """Average operating hours between failures of one component (Azure PdM rate, our calendar)."""
    cal = get_calibration()
    operating = planned_hours_per_year() * (1 - cal.other_unplanned_share - cal.planned_stop_share)
    return operating / cal.failures_per_year[component]


@lru_cache
def get_calibration() -> Calibration:
    path = PROCESSED_DIR / "calibration.json"
    if not path.exists():
        log.warning("calibration.json missing - run `python -m pipeline.run_all`; using defaults")
        return _DEFAULTS

    raw = json.loads(path.read_text())
    comps = raw["components"]
    rul_metrics = json.loads((MODELS_DIR / "rul_metrics.json").read_text())
    value = lambda group, key: raw[group][key]["value"]  # noqa: E731
    return Calibration(
        failures_per_year={k: comps[k]["failures_per_year"]["value"] for k in COMPONENT_KEYS},
        detection_recall={k: comps[k]["detection_recall"]["value"] for k in COMPONENT_KEYS},
        false_alarms_per_year={k: comps[k]["false_alarms_per_year"]["value"] for k in COMPONENT_KEYS},
        signatures={k: comps[k]["signature_z"]["value"] for k in COMPONENT_KEYS},
        weibull_shape=value("degradation", "life_weibull_shape"),
        degradation_b=value("degradation", "degradation_b"),
        degradation_onset=value("degradation", "degradation_onset"),
        rul_rel_error_sd=value("degradation", "rul_relative_error_sd"),
        rul_rel_error_mean=rul_metrics.get("relative_error_mean_near_end", 0.0),
        repair_log_sigma=value("line", "repair_log_sigma"),
        other_unplanned_share=value("line", "other_unplanned_share"),
        planned_stop_share=value("line", "planned_stop_share"),
        base_performance=value("line", "base_performance"),
        base_quality=value("line", "base_quality"),
        is_measured=True,
        raw=raw,
    )
