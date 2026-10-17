"""How a CNC machine's sensors, output, quality and energy respond to wear.

One model, used by both the live plant and the 5-year simulator, so what you see on the
dashboard and what the simulator counts can never disagree.

`damage` is 0 for a new component and 1 at the moment it fails. Its shape over a
component's life comes from NASA C-MAPSS: flat for roughly the first half of life, then
accelerating (damage(u) = (e^(b u) - 1) / (e^b - 1), b fitted on 100 engines).

Response coefficients are engineering estimates chosen so that a bearing at the point of
failure vibrates about 4x its baseline (ISO 10816 zone D), cycle time grows ~10% and
the defect rate roughly triples - the behaviour described in machine-tool maintenance guides.
"""

from dataclasses import dataclass

import numpy as np

SQRT3 = np.sqrt(3)
NOMINAL_VOLTAGE = 415.0  # Indian 3-phase industrial supply
POWER_FACTOR = 0.85
TOOL_LIFE_REF_MIN = 240.0  # AI4I: tools fail between ~200 and 240 min of wear

# How strongly ageing speeds up with spindle speed (bearing life ~ 1/speed, plus load).
AGEING_SPEED_EXPONENT = {"bearing": 1.5, "drive": 1.0, "electrical": 0.0, "coolant": 0.0}


def damage_from_life_fraction(u, b: float):
    u = np.clip(u, 0.0, 1.0)
    return (np.exp(b * u) - 1.0) / (np.exp(b) - 1.0)


def life_fraction_from_damage(damage, b: float):
    damage = np.clip(damage, 0.0, 1.0)
    return np.log1p(damage * (np.exp(b) - 1.0)) / b


@dataclass
class Wear:
    """Damage per component (0..1) plus cutting-tool wear in minutes."""

    bearing: float | np.ndarray = 0.0
    drive: float | np.ndarray = 0.0
    electrical: float | np.ndarray = 0.0
    coolant: float | np.ndarray = 0.0
    tool_min: float | np.ndarray = 0.0


def sensor_means(wear: Wear, speed, base) -> dict:
    """Expected (noise-free) sensor values. `base` is a MachineType-like object."""
    tool = (np.asarray(wear.tool_min) / TOOL_LIFE_REF_MIN) ** 2
    rpm = base.rpm * speed * (1 - 0.05 * wear.drive**1.5 - 0.03 * wear.bearing**2)
    torque = base.torque_nm * (1 + 0.20 * tool) * (1 + 0.08 * wear.bearing)
    vibration = base.vibration_mm_s * (1 + 3.0 * wear.bearing**1.6 + 0.5 * wear.drive**2 + 0.25 * tool)
    temp_rise = 10.0 * (1 + 0.6 * wear.coolant**1.5 + 0.35 * wear.bearing**2)
    coolant = base.coolant_bar * (1 - 0.5 * wear.coolant**1.3)
    voltage = NOMINAL_VOLTAGE * (1 + 0.03 * wear.electrical**1.5)
    power_kw = base.idle_kw + base.cutting_kw * speed * (torque / base.torque_nm) * (
        1 + 0.15 * wear.bearing**1.5 + 0.06 * wear.coolant
    )
    current = power_kw * 1000 / (SQRT3 * voltage * POWER_FACTOR)
    return {
        "rpm": rpm,
        "torque_nm": torque,
        "vibration_mm_s": vibration,
        "temp_rise_c": temp_rise,
        "coolant_bar": coolant,
        "voltage_v": voltage,
        "power_kw": power_kw,
        "current_a": current,
    }


def cycle_time_s(ideal_cycle_s, wear: Wear, speed):
    return ideal_cycle_s / speed * (1 + 0.10 * wear.bearing**2 + 0.08 * wear.drive**1.5)


def defect_rate(base_defect, wear: Wear, speed):
    tool = (np.asarray(wear.tool_min) / TOOL_LIFE_REF_MIN) ** 4
    rate = (
        base_defect * (1 - 0.3 * (1 - speed))
        + 0.035 * wear.bearing**2
        + 0.025 * wear.coolant**2
        + 0.01 * wear.drive**2
        + 0.03 * tool
    )
    return np.clip(rate, 0.0, 0.5)


def cutting_power_kw(wear: Wear, speed, base):
    """Power while cutting (no tool-wear term - the simulator tracks averages)."""
    return base.idle_kw + base.cutting_kw * speed * (1 + 0.08 * wear.bearing) * (
        1 + 0.15 * wear.bearing**1.5 + 0.06 * wear.coolant
    )
