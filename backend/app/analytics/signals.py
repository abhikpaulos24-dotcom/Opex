"""What each signal means and what "normal" looks like for a given machine."""

from dataclasses import dataclass

from app.plant.factory import MACHINE_TYPES, PRODUCTS, Machine


@dataclass(frozen=True)
class SignalInfo:
    key: str
    label: str
    plain: str  # wording for "simple language" mode
    unit: str
    decimals: int = 1


SIGNAL_INFO = {
    s.key: s
    for s in [
        SignalInfo("vibration_mm_s", "Vibration", "Shaking", "mm/s", 2),
        SignalInfo("process_temp_c", "Temperature", "Heat", "°C"),
        SignalInfo("rpm", "Spindle speed", "Spin speed", "rpm", 0),
        SignalInfo("torque_nm", "Torque", "Cutting force", "Nm"),
        SignalInfo("current_a", "Current", "Electric current", "A"),
        SignalInfo("power_kw", "Power", "Power use", "kW"),
        SignalInfo("voltage_v", "Voltage", "Supply voltage", "V", 0),
        SignalInfo("coolant_bar", "Coolant pressure", "Coolant flow", "bar", 2),
        SignalInfo("cycle_time_s", "Cycle time", "Time per part", "s", 0),
        SignalInfo("defect_rate_pct", "Defect rate", "Bad parts", "%", 2),
        SignalInfo("energy_kwh_per_part", "Energy per part", "Energy per part", "kWh", 3),
        SignalInfo("tool_wear_min", "Tool wear", "Tool use", "min", 0),
    ]
}

# Signals that point "up" when things get worse (others point down).
WORSE_WHEN_HIGH = {
    "vibration_mm_s",
    "process_temp_c",
    "torque_nm",
    "current_a",
    "power_kw",
    "cycle_time_s",
    "defect_rate_pct",
    "energy_kwh_per_part",
    "tool_wear_min",
    "voltage_v",
}


def normal_ranges(machine: Machine, air_temp_c: float, speed: float = 1.0) -> dict[str, tuple[float, float]]:
    """Healthy operating band for each signal (machine type baseline, new components)."""
    t = MACHINE_TYPES[machine.type_key]
    ideal = PRODUCTS[machine.product_key].ideal_cycle_s
    power = t.idle_kw + t.cutting_kw * speed
    current = power * 1000 / (1.732 * 415 * 0.85)
    energy = power * ideal / speed / 3600
    return {
        "vibration_mm_s": (0.75 * t.vibration_mm_s, 1.3 * t.vibration_mm_s),
        "process_temp_c": (air_temp_c + 8.5, air_temp_c + 11.5),
        "rpm": (0.97 * t.rpm * speed, 1.03 * t.rpm * speed),
        "torque_nm": (0.85 * t.torque_nm, 1.25 * t.torque_nm),
        "current_a": (0.85 * current, 1.18 * current),
        "power_kw": (0.85 * power, 1.18 * power),
        "voltage_v": (400.0, 430.0),
        "coolant_bar": (0.9 * t.coolant_bar, 1.12 * t.coolant_bar),
        "cycle_time_s": (0.97 * ideal / speed, 1.04 * ideal / speed),
        "defect_rate_pct": (0.0, 3.0),
        "energy_kwh_per_part": (0.85 * energy, 1.15 * energy),
        "tool_wear_min": (0.0, 200.0),
    }


def fmt(signal: str, value: float) -> str:
    info = SIGNAL_INFO[signal]
    return f"{value:,.{info.decimals}f} {info.unit}"
