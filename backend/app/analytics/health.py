"""Physics-informed health estimators: turn sensor readings back into component damage.

Each estimator inverts the sensor-response model in app/plant/physics.py for the sensor that
shows that component's wear first (the same pairing Azure PdM's failures revealed:
bearing <-> vibration, drive <-> speed, coolant <-> pressure, electrical <-> voltage).
On a real line these mappings are re-fitted per machine during commissioning.
"""

import numpy as np

from app.plant.factory import MACHINE_TYPES, Machine
from app.plant.physics import NOMINAL_VOLTAGE, TOOL_LIFE_REF_MIN


def _invert(excess, coefficient: float, power: float):
    return np.clip(np.clip(excess, 0, None) / coefficient, 0, 1) ** (1 / power)


def estimate_damage(
    values: dict[str, np.ndarray], machine: Machine, speed: float, vibration_trusted: bool = True
) -> dict[str, np.ndarray]:
    t = MACHINE_TYPES[machine.type_key]
    tool = (np.nan_to_num(values["tool_wear_min"], nan=100) / TOOL_LIFE_REF_MIN) ** 2

    bearing_vib = _invert(values["vibration_mm_s"] / t.vibration_mm_s - 1 - 0.25 * tool, 3.0, 1.6)
    temp_rise = values["process_temp_c"] - values["air_temp_c"]
    bearing_heat = _invert(temp_rise / 10.0 - 1, 0.35, 2.0)
    # Heat alone can also come from coolant trouble, so it only stands in when vibration is unreliable.
    bearing = bearing_vib if vibration_trusted else np.minimum(bearing_heat, 1) * 0.8

    drive = _invert(1 - values["rpm"] / (t.rpm * speed) - 0.03 * bearing**2, 0.05, 1.5)
    coolant = _invert(1 - values["coolant_bar"] / t.coolant_bar, 0.5, 1.3)
    electrical = _invert(values["voltage_v"] / NOMINAL_VOLTAGE - 1, 0.03, 1.5)
    return {"bearing": bearing, "drive": drive, "electrical": electrical, "coolant": coolant}
