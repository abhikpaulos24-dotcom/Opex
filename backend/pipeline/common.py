import json
import logging
from pathlib import Path

import numpy as np

from app.core.paths import MODELS_DIR, PROCESSED_DIR, RAW_DIR  # noqa: F401  (re-exported)

log = logging.getLogger("pipeline")


def _to_builtin(value):
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return round(float(value), 6)
    if isinstance(value, np.ndarray):
        return [_to_builtin(v) for v in value.tolist()]
    if isinstance(value, dict):
        return {str(k): _to_builtin(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_builtin(v) for v in value]
    if isinstance(value, float):
        return round(value, 6)
    return value


def save_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_to_builtin(payload), indent=2))
    log.info("wrote %s", path.relative_to(path.parents[2]))


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())
