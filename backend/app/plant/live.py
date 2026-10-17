"""Live plant: a minute-by-minute digital twin of the 24 machines.

In a real deployment, readings arrive from the shop floor (Pub/Sub -> POST /api/ingest/readings)
and override the twin for that machine. For the demo, the twin generates readings from the same
physics the 5-year simulator uses, starting from a scripted morning:

  M-17  spindle bearing failing fast (lubrication starvation)       -> critical
  M-08  tool near end of life on a hard batch (overstrain risk)     -> high, short-lived
  M-11  coolant pump wearing, pressure falling                      -> medium
  M-03  drive belt wearing slowly, ~2-3 weeks left                  -> plan it
  M-05  idle for material, spindle + coolant left on                -> energy waste
  M-21  vibration sensor dropping readings and drifting             -> data-health warning

Plant time runs `live_plant_speed` times faster than real time (default 10x).
"""

import logging
import math
import threading
import time
from collections import deque
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np

from app.plant import physics
from app.plant.calibration import COMPONENT_KEYS, get_calibration, mean_life_hours
from app.plant.factory import COMPONENTS, MACHINES, PRODUCTS, type_arrays

log = logging.getLogger(__name__)

HISTORY_MINUTES = 720
WARMUP_MINUTES = 180
MAX_CATCH_UP = 720
SHIFT_STARTS = (6, 14, 22)
PLANT_TZ = ZoneInfo("Asia/Kolkata")

SIGNALS = [
    "air_temp_c",
    "process_temp_c",
    "rpm",
    "torque_nm",
    "tool_wear_min",
    "vibration_mm_s",
    "current_a",
    "power_kw",
    "voltage_v",
    "coolant_bar",
    "cycle_time_s",
    "defect_rate_pct",
    "energy_kwh_per_part",
]
COUNTERS = ["parts", "defects", "energy_kwh", "state", "ideal_s"]
S = {name: i for i, name in enumerate(SIGNALS + COUNTERS)}

RUNNING, IDLE, MAINTENANCE, DOWN, STOPPED = 0, 1, 2, 3, 4
STATE_NAMES = {RUNNING: "running", IDLE: "idle", MAINTENANCE: "maintenance", DOWN: "breakdown", STOPPED: "stopped"}
NOISE = {
    "air_temp_c": 0.15,
    "process_temp_c": 0.2,
    "rpm": 0.006,
    "torque_nm": 0.03,
    "vibration_mm_s": 0.045,
    "current_a": 0.02,
    "power_kw": 0.02,
    "voltage_v": 0.004,
    "coolant_bar": 0.02,
    "cycle_time_s": 0.01,
}
SCRIPTED = {"M-03", "M-05", "M-08", "M-11", "M-17", "M-21"}  # no random stops on the demo machines
MINOR_STOP_CHANCE = 1 / 80  # per running minute -> ~12% of time in short stops, like the Zenodo line
RELATIVE_NOISE = {
    "rpm",
    "torque_nm",
    "vibration_mm_s",
    "current_a",
    "power_kw",
    "voltage_v",
    "coolant_bar",
    "cycle_time_s",
}


@dataclass
class Job:
    """Work that stops a machine. `component` is renewed when the job ends (None = no part swap)."""

    reason: str
    start_minute: int
    duration_min: int
    component: str | None = None
    tool_change: bool = False


@dataclass
class SensorFault:
    signal: str
    missing_rate: float = 0.0
    drift_per_hour: float = 0.0
    started_minute: int = 0


class LivePlant:
    def __init__(self, speed: float = 10.0, seed: int = 17):
        self.speed = speed
        self.seed = seed
        self.lock = threading.RLock()
        self.warming_up = False
        self.cal = get_calibration()
        self.base = type_arrays(MACHINES)
        self.ideal_cycle = np.array([PRODUCTS[m.product_key].ideal_cycle_s for m in MACHINES])
        self.index = {m.id: i for i, m in enumerate(MACHINES)}
        self.scripted = np.array([m.id in SCRIPTED for m in MACHINES])
        self.reset()

    # ------------------------------------------------------------------ lifecycle
    def reset(self) -> None:
        with self.lock:
            self.rng = np.random.default_rng(self.seed)
            n = len(MACHINES)
            mean_life = np.array([mean_life_hours(c) for c in COMPONENT_KEYS])
            k = self.cal.weibull_shape
            self.lives = self.rng.weibull(k, (n, 4)) * (mean_life / math.gamma(1 + 1 / k))
            self.ages = self.lives * self.rng.uniform(0.05, 0.55, (n, 4))
            self.stress = np.ones((n, 4))
            self.speed_factor = np.ones(n)
            self.load = np.ones(n)
            self.state = np.full(n, RUNNING)
            self.state_until = np.zeros(n, dtype=int)
            self.tool_wear = self.rng.uniform(10, 150, n)
            self.tool_change_at = self.rng.normal(200, 8, n)
            self.torque_factor = np.ones(n)
            self.idle_waste = np.zeros(n, dtype=bool)
            self.monitoring = np.zeros(n, dtype=bool)
            self.calibration_days = self.rng.integers(30, 200, n)
            self.sensor_faults: dict[int, SensorFault] = {}
            self.jobs: dict[int, list[Job]] = {i: [] for i in range(n)}
            self.renew_after: dict[int, str | None] = {}
            self.external_until = np.full(n, -1)
            self.external_values: dict[int, dict] = {}
            self.events: deque = deque(maxlen=500)
            self.history: deque = deque(maxlen=HISTORY_MINUTES)
            self.minute = 0
            now = datetime.now(PLANT_TZ).replace(second=0, microsecond=0, tzinfo=None)
            self.start = now - timedelta(minutes=WARMUP_MINUTES)
            self._script_morning()
            self.warming_up = True
            for _ in range(WARMUP_MINUTES):
                self._step()
            self.warming_up = False
            self.anchor_wall = time.monotonic()
            self.anchor_minute = self.minute
            log.info("live plant ready: %d machines, plant clock %s, speed x%.0f", n, self.now, self.speed)

    def _script_morning(self) -> None:
        def set_damage(machine_id: str, component: str, damage: float, hours_left: float):
            m, c = self.index[machine_id], COMPONENT_KEYS.index(component)
            u = physics.life_fraction_from_damage(damage, self.cal.degradation_b)
            self.ages[m, c] = u * self.lives[m, c]
            self.stress[m, c] = (1 - u) * self.lives[m, c] / hours_left

        set_damage("M-17", "bearing", 0.74, hours_left=9.0)  # ~6 h left when the demo opens
        set_damage("M-11", "coolant", 0.6, hours_left=90)
        set_damage("M-03", "drive", 0.55, hours_left=420)
        m8 = self.index["M-08"]
        self.tool_wear[m8], self.tool_change_at[m8], self.torque_factor[m8] = 6, 236, 1.10  # ~186 min at demo start
        m5 = self.index["M-05"]
        self.state[m5], self.state_until[m5], self.idle_waste[m5] = IDLE, WARMUP_MINUTES + 150, True
        m21 = self.index["M-21"]
        self.sensor_faults[m21] = SensorFault("vibration_mm_s", missing_rate=0.3, drift_per_hour=0.35)
        self.calibration_days[m21] = 420

    @property
    def now(self) -> datetime:
        return self.start + timedelta(minutes=self.minute)

    def advance(self) -> None:
        """Bring the twin up to the current plant time. Called before every read."""
        with self.lock:
            target = self.anchor_minute + int((time.monotonic() - self.anchor_wall) * self.speed / 60)
            behind = target - self.minute
            if behind > MAX_CATCH_UP:  # e.g. the server slept: skip the gap, keep going
                self.anchor_minute += behind - MAX_CATCH_UP
                behind = MAX_CATCH_UP
            for _ in range(max(behind, 0)):
                self._step()

    def fast_forward(self, minutes: int) -> None:
        with self.lock:
            self.advance()
            for _ in range(min(minutes, 24 * 60)):
                self._step()
            self.anchor_minute = self.minute
            self.anchor_wall = time.monotonic()

    # ------------------------------------------------------------------ one plant minute
    def _step(self) -> None:
        self.minute += 1
        t = self.minute
        self._run_jobs(t)
        running = self.state == RUNNING

        exp = np.array([physics.AGEING_SPEED_EXPONENT[c] for c in COMPONENT_KEYS])
        effective_speed = self.speed_factor * self.load
        self.ages += running[:, None] * (1 / 60) * effective_speed[:, None] ** exp[None, :] * self.stress
        self.tool_wear += running * self.speed_factor

        for m in np.nonzero(running & (self.tool_wear >= self.tool_change_at))[0]:
            self._start_job(m, Job("routine tool change", t, 6, tool_change=True))
        for m, c in zip(*np.nonzero(running[:, None] & (self.ages >= self.lives)), strict=False):
            self._breakdown(m, c, t)

        # Short everyday stops: waiting for material, set-ups, first-off checks (not equipment faults).
        minor = running & ~self.scripted & (self.rng.random(len(MACHINES)) < MINOR_STOP_CHANCE)
        for m in np.nonzero(minor & (self.state == RUNNING))[0]:
            self.state[m], self.state_until[m] = IDLE, t + max(3, int(self.rng.lognormal(np.log(11), 0.6)))

        self._maybe_new_fault(t)
        self.history.append(self._readings(t))

    def _readings(self, t: int) -> np.ndarray:
        n = len(MACHINES)
        out = np.full((n, len(S)), np.nan)
        damage = physics.damage_from_life_fraction(self.ages / self.lives, self.cal.degradation_b)
        wear = physics.Wear(*damage.T, tool_min=self.tool_wear)
        effective_speed = self.speed_factor * self.load
        means = physics.sensor_means(wear, effective_speed, self.base)
        means["torque_nm"] = means["torque_nm"] * self.torque_factor
        hour = self.now.hour + self.now.minute / 60
        air = 28.5 + 2.5 * math.sin((hour - 9) / 24 * 2 * math.pi)  # warm Indian shop floor
        cycle = physics.cycle_time_s(self.ideal_cycle, wear, effective_speed)
        defects = physics.defect_rate(1 - self.cal.base_quality, wear, self.speed_factor)
        running = self.state == RUNNING
        idle = self.state == IDLE

        values = {
            "air_temp_c": np.full(n, air),
            "process_temp_c": air + np.where(running, means["temp_rise_c"], 2.0),
            "rpm": np.where(running, means["rpm"], np.where(idle & self.idle_waste, self.base.rpm * 0.3, 0)),
            "torque_nm": np.where(running, means["torque_nm"], 0),
            "tool_wear_min": self.tool_wear.copy(),
            "vibration_mm_s": np.where(running, means["vibration_mm_s"], 0.25),
            "voltage_v": means["voltage_v"],
            "coolant_bar": np.where(running | (idle & self.idle_waste), means["coolant_bar"], 0.3),
            "cycle_time_s": np.where(running, cycle, np.nan),
        }
        power = np.where(
            running,
            means["power_kw"],
            np.where(idle & self.idle_waste, self.base.idle_kw, np.where(idle, self.base.idle_kw * 0.25, 0.4)),
        )
        values["power_kw"] = power
        values["current_a"] = power * 1000 / (physics.SQRT3 * values["voltage_v"] * physics.POWER_FACTOR)

        for name, value in values.items():
            sd = NOISE.get(name, 0)
            scale = np.abs(value) if name in RELATIVE_NOISE else 1.0
            noise = self.rng.normal(0, sd, n) * scale
            if name == "voltage_v":  # electrical wear shows up as spiky voltage (Azure PdM signature)
                noise *= 1 + 6 * damage[:, COMPONENT_KEYS.index("electrical")]
            out[:, S[name]] = value + noise

        parts = np.where(running, 60 / cycle * self.cal.base_performance * self.load, 0)
        out[:, S["parts"]] = parts
        out[:, S["defects"]] = parts * defects
        out[:, S["defect_rate_pct"]] = np.where(running, defects * 100, np.nan)
        out[:, S["energy_kwh"]] = power / 60
        out[:, S["energy_kwh_per_part"]] = np.where(parts > 0, power / 60 / np.maximum(parts, 1e-9), np.nan)
        out[:, S["state"]] = self.state
        out[:, S["ideal_s"]] = parts * self.ideal_cycle

        for m, fault in self.sensor_faults.items():
            col = S[fault.signal]
            out[m, col] += fault.drift_per_hour * (t - fault.started_minute) / 60
            if self.rng.random() < fault.missing_rate:
                out[m, col] = np.nan
        for m, values_in in self.external_values.items():
            if self.external_until[m] >= t:
                for name, value in values_in.items():
                    if name in S:
                        out[m, S[name]] = value
        return np.concatenate([[t], out.ravel()])

    # ------------------------------------------------------------------ jobs and breakdowns
    def _start_job(self, m: int, job: Job) -> None:
        self.state[m] = MAINTENANCE
        self.state_until[m] = job.start_minute + job.duration_min
        self.renew_after[m] = job.component
        if job.tool_change:
            self.tool_wear[m] = 0
            self.tool_change_at[m] = self.rng.normal(200, 8)
            self.torque_factor[m] = 1.0
        else:  # routine tool changes are too frequent to log
            self._log(m, "maintenance_started", job.reason, component=job.component)

    def _run_jobs(self, t: int) -> None:
        for m in range(len(MACHINES)):
            stop_over = self.state[m] in (MAINTENANCE, DOWN, IDLE) and 0 < self.state_until[m] <= t
            if stop_over:
                component = self.renew_after.pop(m, None)
                if component:
                    self._renew(m, COMPONENT_KEYS.index(component))
                    self._log(m, "back_in_service", f"{COMPONENTS[component].name} replaced", component=component)
                if self.state[m] == IDLE:
                    self.idle_waste[m] = False
                self.state[m], self.state_until[m] = RUNNING, 0
            for job in list(self.jobs[m]):
                if job.start_minute <= t and self.state[m] == RUNNING:
                    self.jobs[m].remove(job)
                    self._start_job(m, replace(job, start_minute=t))

    def _breakdown(self, m: int, c: int, t: int) -> None:
        spec = COMPONENTS[COMPONENT_KEYS[c]]
        hours = spec.unplanned_repair_h * self.rng.lognormal(0, 0.3)
        self.state[m], self.state_until[m] = DOWN, t + int(hours * 60)
        self.renew_after[m] = COMPONENT_KEYS[c]
        self.jobs[m] = [j for j in self.jobs[m] if j.component != COMPONENT_KEYS[c]]
        self._log(
            m,
            "breakdown",
            f"{spec.name} failed - repair about {hours:.1f} h",
            component=COMPONENT_KEYS[c],
            repair_h=round(hours, 1),
        )

    def _renew(self, m: int, c: int) -> None:
        k = self.cal.weibull_shape
        self.lives[m, c] = self.rng.weibull(k) * mean_life_hours(COMPONENT_KEYS[c]) / math.gamma(1 + 1 / k)
        self.ages[m, c] = 0.0
        self.stress[m, c] = 1.0
        if not any(j.component for j in self.jobs[m]):
            self.speed_factor[m], self.load[m] = 1.0, 1.0

    def _maybe_new_fault(self, t: int) -> None:
        """Roughly every 6 plant hours a new problem starts somewhere, so the plant stays alive."""
        if self.warming_up or self.rng.random() > 1 / 360:
            return
        damage = physics.damage_from_life_fraction(self.ages / self.lives, self.cal.degradation_b)
        healthy = [m for m in range(len(MACHINES)) if damage[m].max() < 0.3 and self.state[m] == RUNNING]
        if healthy:
            m = int(self.rng.choice(healthy))
            c = int(self.rng.integers(0, 4))
            u = physics.life_fraction_from_damage(self.rng.uniform(0.45, 0.6), self.cal.degradation_b)
            self.ages[m, c] = u * self.lives[m, c]
            self.stress[m, c] = (1 - u) * self.lives[m, c] / self.rng.uniform(14, 40)

    def _log(self, m: int, kind: str, message: str, **extra) -> None:
        self.events.append(
            {
                "minute": self.minute,
                "time": self.now.isoformat(timespec="minutes"),
                "machine_id": MACHINES[m].id,
                "kind": kind,
                "message": message,
                **extra,
            }
        )

    # ------------------------------------------------------------------ actions (after human approval)
    def apply_action(self, machine_id: str, action: str, component: str | None = None) -> str:
        """Carry out an approved decision on the twin. Returns a sentence for the person who approved it."""
        with self.lock:
            self.advance()
            m, now = self.index[machine_id], self.minute
            spec = COMPONENTS.get(component) if component else None
            window, shift = self.minutes_to_window(), self.minutes_to_shift_change()

            def book_swap(in_minutes: int) -> None:
                if spec:
                    self.jobs[m].append(
                        Job("planned replacement", now + in_minutes, int(spec.planned_repair_h * 60), component)
                    )

            if action == "stop_now":
                repair_h = (spec.planned_repair_h if spec else 1) + 1.5
                self._start_job(m, Job("stopped for repair", now, int(repair_h * 60), component))
                result = "Machine stopped and handed to maintenance"
            elif action == "replace_component":
                book_swap(shift)
                result = f"Replacement booked at the next shift change (in {shift / 60:.1f} h)"
            elif action == "continue_to_window":
                book_swap(window)
                result = f"Running normally; replacement booked in the maintenance window (in {window / 60:.0f} h)"
            elif action == "reduce_speed":
                self.speed_factor[m] = 0.9
                book_swap(window)
                result = "Speed reduced 10%" + (", replacement booked in the maintenance window" if spec else "")
            elif action == "shift_production":
                self.load[m] = 0.5
                book_swap(window)
                result = "Half of this machine's work moved to sister machines on the line"
            elif action == "partial_maintenance":
                self._start_job(m, Job("partial maintenance (lubricate, clean, re-tension)", now, 45))
                if component:
                    self.stress[m, COMPONENT_KEYS.index(component)] = 1.0
                result = "45-minute partial maintenance started"
            elif action == "increase_monitoring":
                self.monitoring[m] = True
                result = "Monitoring every minute with a tighter alarm limit"
            elif action == "change_tool":
                self._start_job(m, Job("tool change (OpEx advice)", now, 6, tool_change=True))
                result = "Tool change started (about 6 minutes)"
            elif action == "standby":
                self.idle_waste[m] = False
                result = "Spindle and coolant switched to standby while idle"
            elif action == "recalibrate_sensor":
                self.sensor_faults.pop(m, None)
                self.calibration_days[m] = 0
                result = "Sensor recalibrated"
            else:
                result = "No change to the machine (decision recorded)"
            self._log(m, "action", result, action=action)
            return result

    def inject_fault(self, machine_id: str, kind: str) -> str:
        with self.lock:
            self.advance()
            m = self.index[machine_id]
            if kind in COMPONENT_KEYS:
                c = COMPONENT_KEYS.index(kind)
                u = physics.life_fraction_from_damage(0.7, self.cal.degradation_b)
                self.ages[m, c] = u * self.lives[m, c]
                self.stress[m, c] = (1 - u) * self.lives[m, c] / 6
            elif kind == "tool":
                self.tool_wear[m], self.tool_change_at[m], self.torque_factor[m] = 185, 240, 1.3
            elif kind == "energy_waste":
                self.state[m], self.state_until[m], self.idle_waste[m] = IDLE, self.minute + 120, True
            elif kind == "sensor":
                self.sensor_faults[m] = SensorFault("vibration_mm_s", 0.35, 0.5, self.minute)
            self._log(m, "scenario", f"Demo scenario injected: {kind}")
            return f"Injected '{kind}' on {machine_id}"

    def ingest(self, machine_id: str, values: dict, hold_minutes: int = 10) -> None:
        """Real readings from the shop floor replace the twin's values for a few minutes."""
        with self.lock:
            m = self.index[machine_id]
            self.external_values[m] = {k: float(v) for k, v in values.items() if k in S}
            self.external_until[m] = self.minute + hold_minutes

    # ------------------------------------------------------------------ reads
    def minutes_to_shift_change(self) -> int:
        now = self.now
        for start in SHIFT_STARTS + (SHIFT_STARTS[0] + 24,):
            boundary = now.replace(hour=0, minute=0) + timedelta(hours=start)
            if boundary > now:
                return int((boundary - now).total_seconds() // 60)
        return 480

    def minutes_to_window(self) -> int:
        """Weekly planned maintenance window: Sunday 06:00."""
        now = self.now
        days = (6 - now.weekday()) % 7
        window = (now + timedelta(days=days)).replace(hour=6, minute=0)
        if window <= now:
            window += timedelta(days=7)
        return int((window - now).total_seconds() // 60)

    def frame(self, minutes: int | None = None) -> tuple[np.ndarray, np.ndarray]:
        """(minutes array, values array [T, machines, fields]) for the last `minutes`."""
        with self.lock:
            rows = list(self.history)[-minutes:] if minutes else list(self.history)
        data = np.array(rows)
        return data[:, 0].astype(int), data[:, 1:].reshape(len(rows), len(MACHINES), len(S))

    def machine_state(self, machine_id: str) -> dict:
        m = self.index[machine_id]
        with self.lock:
            return {
                "state": STATE_NAMES[int(self.state[m])],
                "speed_pct": round(100 * self.speed_factor[m] * self.load[m]),
                "monitoring": bool(self.monitoring[m]),
                "calibration_days": int(self.calibration_days[m]),
                "pending_jobs": [
                    {"component": j.component, "in_minutes": j.start_minute - self.minute, "reason": j.reason}
                    for j in self.jobs[m]
                ],
                "idle_waste": bool(self.idle_waste[m]),
                "replacing": self.renew_after.get(m) if self.state[m] == MAINTENANCE else None,
                "external_feed": bool(self.external_until[m] >= self.minute),
                "component_age_h": {c: round(float(self.ages[m, i]), 1) for i, c in enumerate(COMPONENT_KEYS)},
            }

    def recent_events(self, machine_id: str | None = None, limit: int = 50) -> list[dict]:
        with self.lock:
            events = [e for e in self.events if machine_id is None or e["machine_id"] == machine_id]
        return events[-limit:]


_plant: LivePlant | None = None


def get_plant() -> LivePlant:
    global _plant
    if _plant is None:
        from app.core.config import get_settings

        _plant = LivePlant(speed=get_settings().live_plant_speed)
    return _plant
