"""What could we do about this problem, and what would each choice cost?

Every option is described by its Effect (how long the machine stops, how likely it still breaks
down, how long the worn part keeps cutting...). `price()` turns any Effect into rupees, over the
same horizon for every option (until the weekly maintenance window):

    total = maintenance + idle crew + lost production + extra scrap + extra energy

Failure probabilities come from the remaining-life estimate; the effect of speed on wear comes
from the shared physics model; "worked N of M times" comes from this plant's own decisions.
"""

from dataclasses import dataclass

from app.analytics.prediction import failure_cost, prob_fail_within
from app.plant import physics
from app.plant.calibration import get_calibration
from app.plant.factory import COMPONENTS, MACHINE_TYPES, PRODUCTS, Economics, Machine

OPERATOR_INR_PER_H = 120  # idle operator during a stop (₹19.4k/month, Indeed 2026, + overheads)
CUTTING_SHARE = 0.78  # share of calendar hours a machine actually cuts on a production day

ACTIONS = {
    "stop_now": ("Stop immediately", "Stop the machine now and repair it straight away."),
    "reduce_speed": ("Reduce speed 10%", "Run 10% slower to slow the wear, repair in the maintenance window."),
    "continue_to_window": ("Continue until scheduled maintenance", "Keep running normally, repair in the window."),
    "shift_production": ("Shift production to another machine", "Move half the work to sister machines on the line."),
    "partial_maintenance": (
        "Perform partial maintenance",
        "45 minutes: lubricate, clean, re-tension; full repair later.",
    ),
    "replace_component": ("Replace component at shift change", "Planned swap at the next shift change."),
    "increase_monitoring": ("Increase monitoring frequency", "Keep running, check every minute, stop at first sign."),
    "change_tool": ("Change the cutting tool now", "Six-minute tool change to remove overstrain risk."),
    "continue_tool": ("Keep cutting with this tool", "Continue until the operator's usual change point."),
    "standby": ("Switch to standby while idle", "Turn off spindle and coolant until material arrives."),
    "leave_idle_running": ("Leave it running", "Keep spindle and coolant on."),
    "recalibrate_sensor": ("Recalibrate the sensor", "15-minute sensor check; machine keeps running."),
    "ignore_sensor": ("Ignore the sensor for now", "Trust the other sensors until the next calibration."),
}


@dataclass
class Situation:
    """Everything the options depend on, taken from the machine report."""

    machine: Machine
    cause_key: str
    cause_name: str
    component: str | None
    cause_probability: float
    fixable_by_partial: bool
    rul: dict | None  # remaining-life outlook of the component (rul_h, sigma...)
    damage: dict  # current damage per component
    hours_to_shift: float
    hours_to_window: float
    op_risk: float  # AI4I operating-point failure probability
    confidence: float  # how sure we are about the diagnosis
    sister_capacity: bool  # other machines on the line could take extra work


@dataclass
class Effect:
    """What an action does between now and the maintenance window."""

    stop_h: float  # stop caused by the action itself
    p_fail: float  # chance of a breakdown before the problem is fixed
    run_h: float  # operating hours the worn part keeps cutting
    speed: float = 1.0
    slow_running_lost_parts: float = 0.0
    parts_cost: float = 0.0
    labour_h: float = 0.0
    energy_factor: float = 1.0
    breakdown_damage_factor: float = 1.0  # catching it early limits secondary damage
    breakdown_repair_factor: float = 1.0
    breakdown_is_tool: bool = False  # a broken tool, not a failed component
    confidence: float = 0.85


def build_options(s: Situation, econ: Economics, learned: dict[str, dict]) -> list[dict]:
    if s.cause_key == "idle_waste":
        return _idle_waste_options(s, econ)
    if s.cause_key == "sensor_drift":
        return _sensor_drift_options(s, econ)

    effects: dict[str, Effect] = {}
    if s.component:
        effects.update(_wear_effects(s, learned))
    if s.cause_key == "tool_overstrain" or s.op_risk > 0.2:
        effects.update(_tool_effects(s, econ, has_component=bool(s.component)))
    pricing = _Pricing(s, econ, learned)
    return [pricing.price(key, effect) for key, effect in effects.items()]


# ------------------------------------------------------------------ effects per kind of problem
def _wear_effects(s: Situation, learned: dict) -> dict[str, Effect]:
    spec = COMPONENTS[s.component]
    window_h, shift_h = s.hours_to_window * CUTTING_SHARE, s.hours_to_shift * CUTTING_SHARE
    parts_per_h = _parts_per_hour(s.machine)
    exponent = physics.AGEING_SPEED_EXPONENT[s.component]
    slower_wear_at_90pct = 0.9**-exponent if exponent else 1.0
    swap = {"parts_cost": spec.part_cost_inr, "labour_h": spec.planned_repair_h}
    expected_wait = spec.stockout_prob * spec.stockout_wait_h

    effects = {
        "continue_to_window": Effect(stop_h=0, p_fail=_p_fail(s, window_h), run_h=window_h, confidence=0.8, **swap),
        "stop_now": Effect(
            stop_h=spec.planned_repair_h + 1.5 + expected_wait,
            p_fail=0.0,
            run_h=0,
            confidence=0.95,
            parts_cost=spec.part_cost_inr,
            labour_h=spec.planned_repair_h + 1.5,
        ),
        "reduce_speed": Effect(
            stop_h=0,
            p_fail=_p_fail(s, window_h, slower_wear_at_90pct),
            run_h=window_h,
            speed=0.9,
            slow_running_lost_parts=0.1 * window_h * parts_per_h,
            **swap,
        ),
    }
    if shift_h < window_h:  # the shift change comes before the window
        effects["replace_component"] = Effect(
            stop_h=spec.planned_repair_h + expected_wait / 2,
            p_fail=_p_fail(s, shift_h),
            run_h=shift_h,
            confidence=0.9,
            **swap,
        )
    if s.sister_capacity:
        effects["shift_production"] = Effect(
            stop_h=0.5,
            p_fail=_p_fail(s, window_h, 0.5 ** -max(exponent, 0.5)),
            run_h=window_h / 2,
            energy_factor=1.03,
            confidence=0.8,
            parts_cost=spec.part_cost_inr,
            labour_h=spec.planned_repair_h + 0.5,
        )

    # Partial maintenance only helps if the cause is fixable (e.g. lubrication) - weighted by how often it worked here.
    history = learned.get(f"{s.cause_key}:partial_maintenance", {"successes": 4, "trials": 5})
    p_fix = (
        (s.cause_probability if s.fixable_by_partial else 0.1) * (history["successes"] + 1) / (history["trials"] + 2)
    )
    fixed = {**s.rul, "rul_h": max(s.rul["rul_h"] * 8, 200)} if s.rul else None
    p_after_fix = prob_fail_within(fixed, window_h) if fixed else 0.0
    effects["partial_maintenance"] = Effect(
        stop_h=0.75,
        p_fail=p_fix * p_after_fix + (1 - p_fix) * _p_fail(s, window_h),
        run_h=window_h,
        confidence=0.75,
        parts_cost=spec.part_cost_inr,
        labour_h=spec.planned_repair_h + 0.75,
    )
    effects["increase_monitoring"] = Effect(
        stop_h=0,
        p_fail=_p_fail(s, window_h),
        run_h=window_h,
        breakdown_damage_factor=0.5,
        breakdown_repair_factor=0.8,
        confidence=0.8,
        parts_cost=spec.part_cost_inr,
        labour_h=spec.planned_repair_h + window_h / 8 * 0.25,
    )
    return effects


def _tool_effects(s: Situation, econ: Economics, has_component: bool) -> dict[str, Effect]:
    effects = {
        "change_tool": Effect(
            stop_h=0.1, p_fail=0.01, run_h=0, labour_h=0.1, parts_cost=econ.tool_cost_inr, confidence=0.95
        )
    }
    if not has_component:
        effects["continue_tool"] = Effect(
            stop_h=0, p_fail=min(s.op_risk * 1.5, 0.95), run_h=1, breakdown_is_tool=True, confidence=0.8
        )
    return effects


def _idle_waste_options(s: Situation, econ: Economics) -> list[dict]:
    idle_kw = MACHINE_TYPES[s.machine.type_key].idle_kw
    wasted_next_2h = round(idle_kw * 0.7 * 2 * econ.electricity_inr_per_kwh, -1)
    per_year = round(idle_kw * 0.7 * econ.idle_hours_per_day * 300 * econ.electricity_inr_per_kwh, -2)
    standby = _flat_option("standby", total=0, confidence=0.92, energy_change_pct=-70.0)
    standby["description"] += f" As a habit: about ₹{per_year:,.0f} a year on this machine."
    leave = _flat_option("leave_idle_running", total=wasted_next_2h, confidence=0.9, energy_cost_inr=wasted_next_2h)
    return [standby, leave]


def _sensor_drift_options(s: Situation, econ: Economics) -> list[dict]:
    # Running on a bad sensor means a real bearing fault could go unseen until the next calibration.
    bearing_breakdown = failure_cost(s.machine, "bearing")
    recalibrate = round(0.25 * econ.technician_inr_per_h + 0.01 * bearing_breakdown, -2)
    ignore = round(0.05 * bearing_breakdown, -2)
    return [
        _flat_option(
            "recalibrate_sensor", total=recalibrate, confidence=0.92, p_fail=0.01, maintenance_cost_inr=recalibrate
        ),
        _flat_option("ignore_sensor", total=ignore, confidence=0.6, p_fail=0.05, maintenance_cost_inr=ignore),
    ]


# ------------------------------------------------------------------ turning an effect into rupees
class _Pricing:
    def __init__(self, s: Situation, econ: Economics, learned: dict):
        self.s, self.econ, self.learned = s, econ, learned
        self.product = PRODUCTS[s.machine.product_key]
        self.spec = COMPONENTS.get(s.component) if s.component else None
        self.parts_per_h = _parts_per_hour(s.machine)
        self.healthy_defect_rate = 1 - get_calibration().base_quality
        self.normal_energy = self._energy_per_part(1.0)

    def price(self, key: str, e: Effect) -> dict:
        econ, product = self.econ, self.product
        breakdown_h, breakdown_cost = self._breakdown(e)
        downtime = e.stop_h + e.p_fail * breakdown_h
        lost_parts = downtime * self.parts_per_h + e.slow_running_lost_parts
        defect_rate = float(physics.defect_rate(self.healthy_defect_rate, physics.Wear(**self.s.damage), e.speed))
        extra_defects = max(defect_rate - self.healthy_defect_rate, 0) * e.run_h * self.parts_per_h * min(e.speed, 1)
        energy_part = self._energy_per_part(e.speed) * e.energy_factor
        extra_kwh = max((energy_part - self.normal_energy * 0.95) * e.run_h * self.parts_per_h, 0)
        costs = {
            "maintenance_cost_inr": e.parts_cost * (1 - e.p_fail)
            + e.labour_h * econ.technician_inr_per_h
            + breakdown_cost,
            "downtime_cost_inr": downtime * OPERATOR_INR_PER_H,
            "production_loss_inr": lost_parts * product.contribution_inr,
            "scrap_cost_inr": extra_defects * product.scrap_cost_inr,
            "energy_cost_inr": extra_kwh * econ.electricity_inr_per_kwh,
        }
        history = self.learned.get(f"{self.s.cause_key}:{key}", {"successes": 0, "trials": 0})
        success = (history["successes"] + 1) / (history["trials"] + 2)  # Laplace: 0 of 0 = 50%
        title, description = ACTIONS[key]
        return {
            "key": key,
            "title": title,
            "description": description,
            "downtime_h": round(downtime, 2),
            "lost_parts": round(lost_parts),
            "p_fail": round(e.p_fail, 3),
            "defect_rate": round(defect_rate, 4),
            "extra_defects": round(extra_defects, 1),
            "energy_per_part_kwh": round(energy_part, 3),
            "energy_change_pct": round(100 * (energy_part / self.normal_energy - 1), 1),
            **{k: round(v, -2) for k, v in costs.items()},
            "total_inr": round(sum(costs.values()), -2),
            "confidence": round(min(0.97, e.confidence * self.s.confidence * (0.6 + 0.4 * success)), 3),
            "learned": {**history, "success_rate": round(success, 3)},
        }

    def _breakdown(self, e: Effect) -> tuple[float, float]:
        """Expected extra hours and rupees if the machine breaks down anyway (already x p_fail for cost)."""
        econ = self.econ
        if e.breakdown_is_tool:  # broken tool: new tool, scrapped parts, sometimes a damaged fixture
            cost = econ.tool_cost_inr + econ.tool_break_scrap_parts * self.product.scrap_cost_inr + 0.1 * 25_000
            return econ.tool_break_downtime_h, e.p_fail * cost
        if not self.spec:
            return 0.0, 0.0
        spec = self.spec
        hours = spec.unplanned_repair_h * 1.4 * e.breakdown_repair_factor + spec.stockout_prob * spec.stockout_wait_h
        cost = (
            spec.part_cost_inr
            + hours * econ.technician_inr_per_h * econ.overtime_multiplier
            + spec.collateral_prob * e.breakdown_damage_factor * spec.collateral_cost_inr
        )
        return hours, e.p_fail * cost

    def _energy_per_part(self, speed: float) -> float:
        wear = physics.Wear(**self.s.damage)
        power = float(physics.cutting_power_kw(wear, speed, MACHINE_TYPES[self.s.machine.type_key]))
        cycle = float(physics.cycle_time_s(self.product.ideal_cycle_s, wear, speed))
        return power * cycle / 3600


# ------------------------------------------------------------------ small helpers
def _parts_per_hour(machine: Machine) -> float:
    return 3600 / PRODUCTS[machine.product_key].ideal_cycle_s * get_calibration().base_performance


def _p_fail(s: Situation, hours: float, slower_wear: float = 1.0) -> float:
    if s.rul is None:
        return min(s.op_risk, 0.95)
    return prob_fail_within({**s.rul, "rul_h": s.rul["rul_h"] * slower_wear}, max(hours, 0.01))


def _flat_option(key: str, total: float, confidence: float, **fields) -> dict:
    """An option with no production or scrap effect (standby, sensor checks)."""
    title, description = ACTIONS[key]
    option = {
        "key": key,
        "title": title,
        "description": description,
        "downtime_h": 0.0,
        "lost_parts": 0,
        "p_fail": 0.0,
        "defect_rate": None,
        "extra_defects": 0,
        "energy_per_part_kwh": None,
        "energy_change_pct": 0.0,
        "maintenance_cost_inr": 0,
        "downtime_cost_inr": 0,
        "production_loss_inr": 0,
        "scrap_cost_inr": 0,
        "energy_cost_inr": 0,
        "total_inr": total,
        "confidence": confidence,
        "learned": {"successes": 0, "trials": 0, "success_rate": 0.5},
    }
    option.update(fields)
    return option
