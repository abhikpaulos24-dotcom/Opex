"""The demo factory: lines, machines, products and every money/time assumption.

All plant-specific assumptions live here so a plant manager can change them in one
file (or from Settings > Factory economics). Values that come from real datasets are
NOT hard-coded here - they are loaded from data/processed/calibration.json, which the
pipeline derives from AI4I 2020, NASA C-MAPSS, Azure PdM and the Zenodo OEE dataset.

The plant itself ("Sahyadri Precision Components, Unit 2") is fictional.
"""

from dataclasses import dataclass
from types import SimpleNamespace

import numpy as np


@dataclass(frozen=True)
class Product:
    key: str
    name: str
    ideal_cycle_s: float  # one part, healthy machine, 100% speed
    price_inr: float
    contribution_inr: float  # price minus variable cost = money lost per part not made
    scrap_cost_inr: float  # material + machining already spent on a scrapped part


@dataclass(frozen=True)
class ComponentSpec:
    key: str
    name: str
    signal: str  # the sensor that shows this failure first
    part_cost_inr: float
    planned_repair_h: float  # swap during a planned window, parts ready
    unplanned_repair_h: float  # median repair after a breakdown
    stockout_prob: float  # chance the part is not on the shelf after a surprise failure
    stockout_wait_h: float
    collateral_prob: float  # chance a breakdown also damages something else
    collateral_cost_inr: float
    warning_lead_h: float  # how early we want a warning (parts lead time + planning)


@dataclass(frozen=True)
class MachineType:
    key: str
    name: str
    rpm: float
    torque_nm: float
    vibration_mm_s: float
    coolant_bar: float
    cutting_kw: float
    idle_kw: float


@dataclass(frozen=True)
class Machine:
    id: str
    name: str
    line_id: str
    type_key: str
    product_key: str
    install_year: int
    criticality: float = 1.0  # >1 = bottleneck / single-source machine


@dataclass(frozen=True)
class Line:
    id: str
    name: str
    product_key: str


PRODUCTS = {
    "caliper": Product("caliper", "Brake caliper housing", 210, 1150, 330, 650),
    "shaft": Product("shaft", "Transmission shaft", 150, 640, 175, 380),
    "gear": Product("gear", "Helical gear (ground)", 180, 980, 290, 560),
    "housing": Product("housing", "Gearbox housing", 420, 2600, 760, 1450),
}

# Failure signals were measured, not guessed: in Azure PdM telemetry the 24 h before a
# comp4 failure shows vibration +1.84 sigma, comp2 rotation -1.49 sigma, comp3 pressure
# +2.17 sigma and comp1 voltage +1.30 sigma (see pipeline/train_precursor_model.py).
COMPONENTS = {
    "bearing": ComponentSpec("bearing", "Spindle bearing", "vibration", 85_000, 6, 14, 0.35, 36, 0.40, 220_000, 168),
    "drive": ComponentSpec("drive", "Spindle drive & belt", "rpm", 60_000, 4, 8, 0.30, 24, 0.20, 80_000, 96),
    "electrical": ComponentSpec(
        "electrical", "Servo power module", "voltage", 35_000, 2, 5, 0.20, 24, 0.10, 50_000, 72
    ),
    "coolant": ComponentSpec(
        "coolant", "Coolant pump & filter", "coolant_pressure", 18_000, 2, 4, 0.10, 12, 0.05, 30_000, 72
    ),
}

MACHINE_TYPES = {
    # Idle draw is ~40% of total running power: Terelak-Tymczyna et al. (Materials, 2024) measured
    # idle at 50-60% of cutting power on CNC lathes; Gutowski et al. (CIRP 2006) found cutting is
    # at most 14.8% of an automotive machining line's energy.
    "vmc": MachineType("vmc", "Vertical machining centre", 1650, 38, 1.9, 6.5, 8.0, 5.0),
    "lathe": MachineType("lathe", "CNC turning centre", 1500, 44, 2.1, 6.0, 6.0, 3.8),
    "grinder": MachineType("grinder", "CNC gear grinder", 1850, 30, 1.6, 7.0, 8.5, 5.5),
    "hmc": MachineType("hmc", "Horizontal machining centre", 1420, 50, 2.2, 7.5, 10.0, 6.5),
}

LINES = [
    Line("L1", "Line 1 · Brake calipers", "caliper"),
    Line("L2", "Line 2 · Transmission shafts", "shaft"),
    Line("L3", "Line 3 · Gears", "gear"),
    Line("L4", "Line 4 · Gearbox housings", "housing"),
]

_LINE_TYPES = {"L1": "vmc", "L2": "lathe", "L3": "grinder", "L4": "hmc"}
_INSTALL_YEARS = [2016, 2018, 2019, 2021, 2022, 2024]


def _build_machines() -> list[Machine]:
    machines = []
    number = 1
    for line in LINES:
        type_key = _LINE_TYPES[line.id]
        for i in range(6):
            machines.append(
                Machine(
                    id=f"M-{number:02d}",
                    name=f"{MACHINE_TYPES[type_key].name} {number:02d}",
                    line_id=line.id,
                    type_key=type_key,
                    product_key=line.product_key,
                    install_year=_INSTALL_YEARS[i],
                    criticality=1.3 if i == 0 else 1.0,  # first machine of each line feeds the others
                )
            )
            number += 1
    return machines


MACHINES = _build_machines()
MACHINES_BY_ID = {m.id: m for m in MACHINES}


@dataclass
class Economics:
    """Money and calendar assumptions. Sources are listed in README > Assumptions."""

    shifts_per_day: int = 3
    productive_hours_per_shift: float = 7.5  # 8 h minus a 30 min break
    working_days_per_week: int = 6  # Sunday = planned maintenance window
    holidays_per_year: int = 12
    electricity_inr_per_kwh: float = 9.25  # MSEDCL HT-I(A) FY27 energy + wheeling (MERC, Mar 2026)
    grid_tco2_per_mwh: float = 0.675  # CEA CO2 Baseline Database v22, FY2025-26 weighted avg
    technician_inr_per_h: float = 300  # blend: in-house tech (~₹19k/month, Indeed 2026) + OEM service visits
    overtime_multiplier: float = 1.5  # breakdowns are often fixed on overtime
    inspection_h: float = 1.0  # cost of checking a (false) alarm
    tool_cost_inr: float = 2400  # one tool/insert set
    tool_break_downtime_h: float = 0.5
    tool_break_scrap_parts: int = 3
    pm_every_operating_h: float = 500  # time-based PM on Sundays, same in both worlds
    pm_cost_inr: float = 5000
    idle_hours_per_day: float = 1.5  # breaks + shift handover with machines powered
    standby_saving: float = 0.6  # share of idle power cut by auto-standby

    # Cost of running OpEx itself (used for ROI)
    sensor_kit_per_machine_inr: float = 45_000  # vibration + current + temp retrofit, gateway share
    implementation_inr: float = 600_000  # integration, training, commissioning
    annual_cloud_inr: float = 240_000  # Cloud Run + BigQuery + Gemini at this scale
    annual_support_inr: float = 600_000  # licence / support / model upkeep


def planned_hours_per_year(econ: Economics | None = None) -> float:
    """3 shifts x 7.5 h x 300 working days = 6,750 h with the default calendar."""
    e = econ or Economics()
    days = e.working_days_per_week * 52 - e.holidays_per_year
    return days * e.shifts_per_day * e.productive_hours_per_shift


def type_arrays(machines: list[Machine]) -> SimpleNamespace:
    """Machine-type baselines as numpy arrays (one value per machine) for vectorised physics."""
    types = [MACHINE_TYPES[m.type_key] for m in machines]
    return SimpleNamespace(
        **{
            attr: np.array([getattr(t, attr) for t in types], dtype=float)
            for attr in ("rpm", "torque_nm", "vibration_mm_s", "coolant_bar", "cutting_kw", "idle_kw")
        }
    )


def lost_contribution_per_hour(machine: Machine) -> float:
    """Money a machine earns per productive hour = parts/hour x contribution per part."""
    product = PRODUCTS[machine.product_key]
    return 3600 / product.ideal_cycle_s * product.contribution_inr
