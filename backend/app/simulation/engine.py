"""Five-year factory simulator: the same plant, the same luck, two ways of running it.

* "without"  - today's reactive plant: time-based PM on Sundays, components run to failure.
* "with"     - OpEx: precursor alerts, planned swaps in the Sunday window, speed reduction
               when the window is too far away, auto-standby for idle machines.

Both worlds share every random draw (component lives, repair times, stock-outs, minor stops),
so every difference in the results is caused by the policy and nothing else.

Detection is NOT assumed perfect. P(warning in time) = model recall (Azure PdM, held-out)
x sensor coverage x operator adoption; warning timing carries the RUL error measured on
NASA C-MAPSS; every false alarm costs a real inspection stop.
"""

import logging
import math
import time
from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np

from app.plant import physics
from app.plant.calibration import COMPONENT_KEYS, Calibration, get_calibration
from app.plant.factory import COMPONENTS, MACHINES, PRODUCTS, Economics, type_arrays

log = logging.getLogger(__name__)

START_DATE = date(2027, 1, 4)  # a Monday
PRODUCTIVE_SHARE = 7.5 / 8  # 30 min break per 8 h shift
SHIFT_STARTS = (6, 14, 22)
SUNDAY = 6
HOLIDAY_DAYS = (25, 59, 88, 104, 120, 226, 244, 274, 289, 304, 314, 358)  # day-of-year, 12 per year
MAX_LIVES = 80
INSPECTION_COST_HOURS = 2  # technician hours per false-alarm check
SPEED_REDUCED = 0.9

# Machine state codes sent to the UI (worst state seen that day wins)
OK, WEARING, AT_RISK, REDUCED, PLANNED, BROKEN = 0, 1, 2, 3, 4, 5
METRICS = (
    "planned_h",
    "run_h",
    "unplanned_h",
    "planned_stop_h",
    "parts",
    "good",
    "defects",
    "ideal_h",
    "energy_kwh",
    "failures",
    "planned_repairs",
    "alerts",
    "false_alarms",
    "maint_cost",
    "collateral_cost",
    "contribution",
    "scrap_cost",
)


@dataclass
class SimulationParams:
    years: int = 5
    adoption_rate: float = 0.85  # share of OpEx recommendations people actually approve
    sensor_coverage: float = 0.90  # share of failures whose warning signs reach our sensors
    seed: int = 2026
    electricity_inr_per_kwh: float | None = None


@dataclass
class Draws:
    """Every random number, drawn once and shared by both worlds."""

    lives: np.ndarray  # (M, C, K) operating hours per life
    initial_age_frac: np.ndarray  # (M, C)
    repair_mult: np.ndarray  # (M, C, K)
    stockout: np.ndarray  # (M, C, K) bool
    collateral: np.ndarray  # (M, C, K) bool
    detect_u: np.ndarray  # (M, C, K)
    adopt_u: np.ndarray  # (M, C, K)
    rul_error: np.ndarray  # (M, C, K) relative prediction error
    other_loss: np.ndarray  # (days, M) minor stops / materials / setups share
    false_alarm_gaps: np.ndarray  # (M, F) operating hours between false alarms
    false_alarm_adopt_u: np.ndarray  # (M, F)
    standby_u: np.ndarray  # (M,)


@dataclass
class World:
    name: str
    uses_opex: bool
    daily: np.ndarray
    states: np.ndarray
    events: list = field(default_factory=list)


class FactorySimulation:
    def __init__(
        self, params: SimulationParams, calibration: Calibration | None = None, economics: Economics | None = None
    ):
        self.params = params
        self.cal = calibration or get_calibration()
        self.econ = economics or Economics()
        if params.electricity_inr_per_kwh:
            self.econ.electricity_inr_per_kwh = params.electricity_inr_per_kwh
        self.machines = MACHINES
        self.days = params.years * 365
        self.n_m, self.n_c = len(self.machines), len(COMPONENT_KEYS)

        products = [PRODUCTS[m.product_key] for m in self.machines]
        self.base = type_arrays(self.machines)
        self.ideal_cycle = np.array([p.ideal_cycle_s for p in products], dtype=float)
        self.contribution = np.array([p.contribution_inr for p in products], dtype=float)
        self.scrap_cost = np.array([p.scrap_cost_inr for p in products], dtype=float)
        self.base_defect = 1 - self.cal.base_quality
        self.specs = [COMPONENTS[k] for k in COMPONENT_KEYS]
        self.age_exp = np.array([physics.AGEING_SPEED_EXPONENT[k] for k in COMPONENT_KEYS])
        self.lead_h = np.array([s.warning_lead_h for s in self.specs])

        self.calendar = self._build_calendar()
        self.next_window = self._next_window_days()
        self.draws = self._draw_randomness()

    # ------------------------------------------------------------------ setup
    def _build_calendar(self) -> np.ndarray:
        """True for production days (Mon-Sat, not a holiday)."""
        production = np.zeros(self.days, dtype=bool)
        for d in range(self.days):
            day = START_DATE + timedelta(days=d)
            production[d] = day.weekday() != SUNDAY and day.timetuple().tm_yday - 1 not in HOLIDAY_DAYS
        return production

    def _next_window_days(self) -> np.ndarray:
        """For each day, the next day without production (Sunday or holiday) = maintenance window."""
        nxt = np.full(self.days, self.days + 7)
        upcoming = self.days + 7
        for d in range(self.days - 1, -1, -1):
            nxt[d] = upcoming
            if not self.calendar[d]:
                upcoming = d
        return nxt

    def _operating_hours_per_year(self) -> float:
        production_days = self.calendar.sum() / self.params.years
        return (
            production_days * 24 * PRODUCTIVE_SHARE * (1 - self.cal.other_unplanned_share - self.cal.planned_stop_share)
        )

    def _draw_randomness(self) -> Draws:
        rng = np.random.default_rng(self.params.seed)
        shape = (self.n_m, self.n_c, MAX_LIVES)
        k = self.cal.weibull_shape
        mean_life = np.array([self._operating_hours_per_year() / self.cal.failures_per_year[c] for c in COMPONENT_KEYS])
        scale = mean_life / math.gamma(1 + 1 / k)
        other_mean = self.cal.other_unplanned_share + self.cal.planned_stop_share
        concentration = 12.0
        fa_rate = sum(self.cal.false_alarms_per_year.values()) / self._operating_hours_per_year()
        return Draws(
            lives=rng.weibull(k, shape) * scale[None, :, None],
            initial_age_frac=rng.uniform(0, 0.9, (self.n_m, self.n_c)),
            repair_mult=rng.lognormal(0, self.cal.repair_log_sigma, shape),
            stockout=rng.random(shape) < np.array([s.stockout_prob for s in self.specs])[None, :, None],
            collateral=rng.random(shape) < np.array([s.collateral_prob for s in self.specs])[None, :, None],
            detect_u=rng.random(shape),
            adopt_u=rng.random(shape),
            rul_error=rng.normal(self.cal.rul_rel_error_mean, self.cal.rul_rel_error_sd, shape),
            other_loss=rng.beta(other_mean * concentration, (1 - other_mean) * concentration, (self.days, self.n_m)),
            false_alarm_gaps=rng.exponential(1 / fa_rate, (self.n_m, 400)),
            false_alarm_adopt_u=rng.random((self.n_m, 400)),
            standby_u=rng.random(self.n_m),
        )

    # ------------------------------------------------------------------ run
    def run(self) -> dict:
        started = time.perf_counter()
        worlds = [self._run_world("without", uses_opex=False), self._run_world("with", uses_opex=True)]
        log.info(
            "simulated %d years x %d machines x 2 worlds in %.1fs",
            self.params.years,
            self.n_m,
            time.perf_counter() - started,
        )
        return {"worlds": {w.name: w for w in worlds}, "calendar": self.calendar}

    def _run_world(self, name: str, uses_opex: bool) -> World:
        d = self.draws
        m_idx = np.arange(self.n_m)
        econ, cal, p = self.econ, self.cal, self.params
        world = World(name, uses_opex, np.zeros((self.days, len(METRICS))), np.zeros((self.days, self.n_m), np.int8))
        col = {metric: i for i, metric in enumerate(METRICS)}

        life_idx = np.zeros((self.n_m, self.n_c), dtype=int)
        life = d.lives[:, :, 0].copy()
        age = d.initial_age_frac * life
        busy_until = np.zeros(self.n_m)  # absolute hour the current stop ends
        busy_kind = np.zeros(self.n_m, dtype=int)  # 1 unplanned, 2 planned
        speed = np.ones(self.n_m)
        alerted = np.zeros((self.n_m, self.n_c), dtype=bool)
        staged = np.zeros((self.n_m, self.n_c), dtype=bool)  # parts on the shelf because we were warned
        planned_at = np.full((self.n_m, self.n_c), -1.0)  # absolute hour of a planned swap
        fa_clock = np.zeros(self.n_m)
        fa_index = np.zeros(self.n_m, dtype=int)
        pm_clock = np.zeros(self.n_m)
        standby = uses_opex & (d.standby_u < p.adoption_rate)
        idle_kw = self.base.idle_kw * np.where(standby, 1 - econ.standby_saving, 1.0)

        def renew(m: int, c: int) -> None:
            life_idx[m, c] = min(life_idx[m, c] + 1, MAX_LIVES - 1)
            life[m, c] = d.lives[m, c, life_idx[m, c]]
            age[m, c] = 0.0
            alerted[m, c] = staged[m, c] = False
            planned_at[m, c] = -1
            if not alerted[m].any():
                speed[m] = 1.0

        def planned_swap(m: int, c: int, hour: float, in_window: bool, row: np.ndarray) -> None:
            spec = self.specs[c]
            cost = spec.part_cost_inr + spec.planned_repair_h * econ.technician_inr_per_h
            row[col["maint_cost"]] += cost
            row[col["planned_repairs"]] += 1
            if not in_window:
                busy_until[m], busy_kind[m] = hour + math.ceil(spec.planned_repair_h), 2
            world.events.append(
                self._event(
                    hour,
                    m,
                    c,
                    "planned_repair",
                    spec.planned_repair_h if not in_window else 0,
                    cost,
                    "Sunday window" if in_window else "planned stop",
                )
            )
            renew(m, c)

        for day in range(self.days):
            row = world.daily[day]
            state = np.zeros(self.n_m, dtype=np.int8)
            if not self.calendar[day]:
                # Sunday / holiday: planned swaps happen here with zero lost production.
                for m, c in zip(*np.nonzero(planned_at >= 0), strict=False):
                    if planned_at[m, c] < (day + 1) * 24:
                        planned_swap(m, c, day * 24 + 6, True, row)
                        state[m] = max(state[m], PLANNED)
                pm_due = pm_clock >= econ.pm_every_operating_h
                row[col["maint_cost"]] += pm_due.sum() * econ.pm_cost_inr
                pm_clock[pm_due] = 0
                world.states[day] = state
                continue

            row[col["energy_kwh"]] += (idle_kw * econ.idle_hours_per_day).sum()
            for hour_of_day in range(24):
                t = day * 24 + hour_of_day
                # Planned swaps that fall inside production time (the Sunday window was too far away).
                if uses_opex:
                    for m, c in zip(*np.nonzero((planned_at >= 0) & (planned_at <= t)), strict=False):
                        if busy_until[m] <= t:
                            planned_swap(m, c, t, False, row)

                stopped = busy_until > t
                row[col["planned_h"]] += PRODUCTIVE_SHARE * self.n_m
                row[col["unplanned_h"]] += PRODUCTIVE_SHARE * np.sum(stopped & (busy_kind == 1))
                row[col["planned_stop_h"]] += PRODUCTIVE_SHARE * np.sum(stopped & (busy_kind == 2))
                state[stopped & (busy_kind == 1)] = BROKEN
                state[stopped & (busy_kind == 2)] = np.maximum(state[stopped & (busy_kind == 2)], PLANNED)

                running = ~stopped
                run_h = PRODUCTIVE_SHARE * (1 - d.other_loss[day]) * running
                damage = physics.damage_from_life_fraction(age / life, cal.degradation_b)
                wear = physics.Wear(*damage.T)
                cycle = physics.cycle_time_s(self.ideal_cycle, wear, speed)
                parts = run_h * 3600 / cycle * cal.base_performance
                defects = parts * physics.defect_rate(self.base_defect, wear, speed)
                power = physics.cutting_power_kw(wear, speed, self.base)

                row[col["run_h"]] += run_h.sum()
                row[col["parts"]] += parts.sum()
                row[col["good"]] += (parts - defects).sum()
                row[col["defects"]] += defects.sum()
                row[col["ideal_h"]] += (parts * self.ideal_cycle).sum() / 3600
                row[col["contribution"]] += ((parts - defects) * self.contribution).sum()
                row[col["scrap_cost"]] += (defects * self.scrap_cost).sum()
                row[col["energy_kwh"]] += (run_h * power + (PRODUCTIVE_SHARE * running - run_h) * idle_kw).sum()

                age += run_h[:, None] * speed[:, None] ** self.age_exp[None, :]
                pm_clock += run_h
                worst = damage.max(axis=1)
                state = np.maximum(
                    state, np.where(worst > 0.7, AT_RISK, np.where(worst > 0.3, WEARING, OK)).astype(np.int8)
                )

                # --- failures (both worlds) ---
                for m, c in zip(*np.nonzero(running[:, None] & (age >= life)), strict=False):
                    self._fail(world, row, col, m, c, t, life_idx, staged, busy_until, busy_kind)
                    state[m] = BROKEN
                    renew(m, c)

                if not uses_opex:
                    continue

                # --- OpEx: warnings ---
                rul = life - age
                k = life_idx
                threshold = self.lead_h[None, :] / np.clip(
                    1 + d.rul_error[m_idx[:, None], np.arange(self.n_c), k], 0.4, None
                )
                new = running[:, None] & ~alerted & (rul <= threshold)
                for m, c in zip(*np.nonzero(new), strict=False):
                    alerted[m, c] = True
                    detected = d.detect_u[m, c, k[m, c]] < cal.detection_recall[COMPONENT_KEYS[c]] * p.sensor_coverage
                    adopted = d.adopt_u[m, c, k[m, c]] < p.adoption_rate
                    if not detected:
                        continue
                    row[col["alerts"]] += 1
                    predicted = rul[m, c] * (1 + d.rul_error[m, c, k[m, c]])
                    world.events.append(
                        self._event(
                            t,
                            m,
                            c,
                            "alert",
                            0,
                            0,
                            f"approved - {predicted:.0f} h of life left"
                            if adopted
                            else "warning raised but not acted on",
                        )
                    )
                    if adopted:
                        staged[m, c] = True
                        self._schedule(m, c, t, day, predicted, planned_at, speed)
                state[speed < 1] = np.maximum(state[speed < 1], REDUCED)

                # --- OpEx: false alarms cost a real inspection stop ---
                fa_clock += run_h
                for m in np.nonzero(fa_clock >= d.false_alarm_gaps[m_idx, fa_index % 400])[0]:
                    fa_clock[m] = 0
                    row[col["false_alarms"]] += 1
                    if d.false_alarm_adopt_u[m, fa_index[m] % 400] < p.adoption_rate and busy_until[m] <= t:
                        busy_until[m], busy_kind[m] = t + 1 + econ.inspection_h, 2
                        row[col["maint_cost"]] += INSPECTION_COST_HOURS * econ.technician_inr_per_h
                    fa_index[m] += 1

            world.states[day] = state
        return world

    def _schedule(
        self, m: int, c: int, t: int, day: int, predicted_rul: float, planned_at: np.ndarray, speed: np.ndarray
    ) -> None:
        """Swap in the next Sunday window if the part will last; otherwise at the next shift change."""
        days_to_sunday = int(self.next_window[day] - day)
        production_hours = days_to_sunday * 24 - (t % 24)
        op_hours_until_window = production_hours * PRODUCTIVE_SHARE * 0.82
        if op_hours_until_window <= 0.7 * predicted_rul:
            planned_at[m, c] = (day + days_to_sunday) * 24 + 6
            if op_hours_until_window > 0.45 * predicted_rul:
                speed[m] = SPEED_REDUCED  # stretch the remaining life until Sunday
        else:
            next_shift = min((s for s in SHIFT_STARTS if s > t % 24), default=24 + SHIFT_STARTS[0])
            planned_at[m, c] = day * 24 + next_shift

    def _fail(self, world, row, col, m, c, t, life_idx, staged, busy_until, busy_kind) -> None:
        d, econ, spec = self.draws, self.econ, self.specs[c]
        k = life_idx[m, c]
        repair = spec.unplanned_repair_h * d.repair_mult[m, c, k]
        waited = d.stockout[m, c, k] and not staged[m, c]
        if waited:
            repair += spec.stockout_wait_h
        cost = spec.part_cost_inr + repair * econ.technician_inr_per_h * econ.overtime_multiplier
        collateral = spec.collateral_cost_inr if d.collateral[m, c, k] else 0.0
        busy_until[m], busy_kind[m] = t + 1 + math.ceil(repair), 1  # repair occupies the following hours
        row[col["failures"]] += 1
        row[col["maint_cost"]] += cost + collateral
        row[col["collateral_cost"]] += collateral
        detail = "waited for spare parts" if waited else ("secondary damage" if collateral else "breakdown")
        world.events.append(
            self._event(
                t, m, c, "failure", repair, cost + collateral, detail, life_index=int(k), parts_wait=bool(waited)
            )
        )

    def _event(
        self, hour: float, m: int, c: int, kind: str, downtime_h: float, cost: float, detail: str, **extra
    ) -> dict:
        return {
            "day": int(hour // 24),
            "hour": int(hour % 24),
            "machine": self.machines[int(m)].id,
            "component": COMPONENT_KEYS[int(c)],
            "kind": kind,
            "downtime_h": round(float(downtime_h), 1),
            "cost_inr": round(float(cost), -2),
            "detail": detail,
            **extra,
        }
