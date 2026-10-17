"""Plant-wide settings a manager can change from the UI (stored in app_settings)."""

from dataclasses import asdict, fields

from sqlalchemy.orm import Session

from app.db.models import AppSetting, now_utc
from app.decisions.ranking import WEIGHT_PRESETS
from app.plant.factory import Economics

EDITABLE_ECONOMICS = (
    "electricity_inr_per_kwh",
    "grid_tco2_per_mwh",
    "technician_inr_per_h",
    "overtime_multiplier",
    "sensor_kit_per_machine_inr",
    "implementation_inr",
    "annual_cloud_inr",
    "annual_support_inr",
)


def _get(db: Session, key: str) -> dict | None:
    row = db.get(AppSetting, key)
    return row.value if row else None


def _put(db: Session, key: str, value: dict, user_email: str | None) -> None:
    row = db.get(AppSetting, key) or AppSetting(key=key)
    row.value, row.updated_by, row.updated_at = value, user_email, now_utc()
    db.merge(row)
    db.commit()


def get_priorities(db: Session) -> dict:
    return _get(db, "priorities") or {"preset": "balanced", "weights": WEIGHT_PRESETS["balanced"]}


def set_priorities(db: Session, preset: str, weights: dict | None, user_email: str | None) -> dict:
    if preset != "custom":
        weights = WEIGHT_PRESETS[preset]
    total = sum(weights.values()) or 1
    value = {"preset": preset, "weights": {k: round(v / total, 3) for k, v in weights.items()}}
    _put(db, "priorities", value, user_email)
    return value


def get_economics(db: Session) -> Economics:
    overrides = _get(db, "economics") or {}
    valid = {f.name for f in fields(Economics)}
    return Economics(**{k: v for k, v in overrides.items() if k in valid})


def set_economics(db: Session, values: dict, user_email: str | None) -> dict:
    clean = {k: float(v) for k, v in values.items() if k in EDITABLE_ECONOMICS and v is not None and float(v) >= 0}
    _put(db, "economics", clean, user_email)
    return {k: asdict(get_economics(db))[k] for k in EDITABLE_ECONOMICS}
