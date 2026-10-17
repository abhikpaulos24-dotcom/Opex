"""Turns raw simulator output into the numbers people read: KPIs, savings, ROI and
the exact formulas used ("How we calculated this")."""

import numpy as np

from app.core.jsonsafe import clean
from app.plant.factory import MACHINES

from .engine import METRICS, START_DATE, FactorySimulation

COL = {m: i for i, m in enumerate(METRICS)}

# US Department of Energy, O&M Best Practices Guide (Release 3.0, 2010), section 5.4:
# predictive maintenance vs reactive. Used only as a sanity check for our results.
DOE_BENCHMARKS = {
    "breakdowns_reduction": (0.70, 0.75),
    "downtime_reduction": (0.35, 0.45),
    "maintenance_cost_reduction": (0.25, 0.30),
}


def _kpis(totals: np.ndarray, tariff: float, grid_factor: float) -> dict:
    t = {m: float(totals[COL[m]]) for m in METRICS}
    availability = t["run_h"] / t["planned_h"]
    performance = t["ideal_h"] / max(t["run_h"], 1e-9)
    quality = t["good"] / max(t["parts"], 1e-9)
    energy_mwh = t["energy_kwh"] / 1000
    return {
        "oee": availability * performance * quality,
        "availability": availability,
        "performance": performance,
        "quality": quality,
        "unplanned_downtime_h": t["unplanned_h"],
        "planned_stop_h": t["planned_stop_h"],
        "failures": t["failures"],
        "planned_repairs": t["planned_repairs"],
        "alerts": t["alerts"],
        "false_alarms": t["false_alarms"],
        "good_parts": t["good"],
        "defects": t["defects"],
        "defect_rate": t["defects"] / max(t["parts"], 1e-9),
        "energy_mwh": energy_mwh,
        "energy_kwh_per_part": t["energy_kwh"] / max(t["good"], 1e-9),
        "co2_t": energy_mwh * grid_factor,
        "maintenance_cost_inr": t["maint_cost"],
        "collateral_cost_inr": t["collateral_cost"],
        "energy_cost_inr": t["energy_kwh"] * tariff,
        "scrap_cost_inr": t["scrap_cost"],
        "contribution_inr": t["contribution"],
    }


def _monthly(daily: np.ndarray, metric: str) -> np.ndarray:
    months = np.arange(len(daily)) * 12 // 365
    return np.bincount(months, weights=daily[:, COL[metric]])


def _daily_oee(daily: np.ndarray) -> np.ndarray:
    planned = np.maximum(daily[:, COL["planned_h"]], 1e-9)
    parts = np.maximum(daily[:, COL["parts"]], 1e-9)
    oee = daily[:, COL["ideal_h"]] / planned * (daily[:, COL["good"]] / parts)
    return np.where(daily[:, COL["planned_h"]] > 0, oee, np.nan)


def build_report(sim: FactorySimulation, result: dict) -> dict:
    econ = sim.econ
    tariff, grid = econ.electricity_inr_per_kwh, econ.grid_tco2_per_mwh
    worlds = result["worlds"]
    kpi = {name: _kpis(w.daily.sum(axis=0), tariff, grid) for name, w in worlds.items()}
    base, opex = kpi["without"], kpi["with"]
    years = sim.params.years

    gains = {
        "production_protected_inr": opex["contribution_inr"] - base["contribution_inr"],
        "maintenance_savings_inr": base["maintenance_cost_inr"] - opex["maintenance_cost_inr"],
        "scrap_savings_inr": base["scrap_cost_inr"] - opex["scrap_cost_inr"],
        "energy_savings_inr": base["energy_cost_inr"] - opex["energy_cost_inr"],
    }
    benefit = sum(gains.values())
    one_time = econ.sensor_kit_per_machine_inr * len(MACHINES) + econ.implementation_inr
    yearly = econ.annual_cloud_inr + econ.annual_support_inr
    cost = one_time + yearly * years

    # Monthly cash view for the payback chart.
    def monthly_value(world) -> np.ndarray:
        d = world.daily
        return (
            _monthly(d, "contribution")
            - _monthly(d, "maint_cost")
            - _monthly(d, "scrap_cost")
            - _monthly(d, "energy_kwh") * tariff
        )

    monthly_gain = monthly_value(worlds["with"]) - monthly_value(worlds["without"])
    monthly_cost = np.full(len(monthly_gain), yearly / 12)
    monthly_cost[0] += one_time
    cumulative_net = np.cumsum(monthly_gain - monthly_cost)
    payback = next((i + 1 for i, v in enumerate(cumulative_net) if v >= 0), None)

    def reduction(key: str) -> float:
        return 1 - opex[key] / base[key] if base[key] else 0.0

    delta = {
        "downtime_avoided_h": base["unplanned_downtime_h"] - opex["unplanned_downtime_h"],
        "failures_avoided": base["failures"] - opex["failures"],
        "good_parts_gained": opex["good_parts"] - base["good_parts"],
        "defects_avoided": base["defects"] - opex["defects"],
        "energy_saved_mwh": base["energy_mwh"] - opex["energy_mwh"],
        "co2_avoided_t": base["co2_t"] - opex["co2_t"],
        "oee_points": 100 * (opex["oee"] - base["oee"]),
        **gains,
        "total_benefit_inr": benefit,
        "opex_cost_inr": cost,
        "net_benefit_inr": benefit - cost,
        "roi_multiple": (benefit - cost) / cost,
        "payback_months": payback,
        "breakdowns_reduction": reduction("failures"),
        "downtime_reduction": 1
        - (opex["unplanned_downtime_h"] + opex["planned_stop_h"])
        / (base["unplanned_downtime_h"] + base["planned_stop_h"]),
        "maintenance_cost_reduction": reduction("maintenance_cost_inr"),
    }

    return clean(
        {
            "kpis": kpi,
            "delta": delta,
            "benchmarks": {
                key: {"ours": delta[key], "doe_low": lo, "doe_high": hi} for key, (lo, hi) in DOE_BENCHMARKS.items()
            },
            "monthly": {
                "oee_without": _monthly_ratio(worlds["without"].daily),
                "oee_with": _monthly_ratio(worlds["with"].daily),
                "cumulative_net_inr": cumulative_net.round(-3).tolist(),
                "downtime_without": _monthly(worlds["without"].daily, "unplanned_h").round(1).tolist(),
                "downtime_with": _monthly(worlds["with"].daily, "unplanned_h").round(1).tolist(),
            },
            "yearly": _yearly(worlds, tariff),
            "machines": _per_machine(worlds),
            "costs": {
                "one_time_inr": one_time,
                "yearly_inr": yearly,
                "sensor_kits_inr": econ.sensor_kit_per_machine_inr * len(MACHINES),
                "implementation_inr": econ.implementation_inr,
                "cloud_per_year_inr": econ.annual_cloud_inr,
                "support_per_year_inr": econ.annual_support_inr,
            },
            "calculations": _calculations(sim, base, opex, delta, gains),
            "start_date": START_DATE.isoformat(),
        }
    )


def _monthly_ratio(daily: np.ndarray) -> list:
    ideal = _monthly(daily, "ideal_h")
    planned = np.maximum(_monthly(daily, "planned_h"), 1e-9)
    quality = _monthly(daily, "good") / np.maximum(_monthly(daily, "parts"), 1e-9)
    return (ideal / planned * quality).round(4).tolist()


def _yearly(worlds: dict, tariff: float) -> list:
    rows = []
    for year in range(len(worlds["with"].daily) // 365):
        span = slice(year * 365, (year + 1) * 365)
        row = {"year": year + 1}
        for name, world in worlds.items():
            t = world.daily[span].sum(axis=0)
            row[name] = {
                "oee": float(t[COL["ideal_h"]] / t[COL["planned_h"]] * t[COL["good"]] / t[COL["parts"]]),
                "downtime_h": float(t[COL["unplanned_h"]]),
                "failures": int(t[COL["failures"]]),
                "maintenance_cost_inr": float(t[COL["maint_cost"]]),
                "energy_mwh": float(t[COL["energy_kwh"]] / 1000),
            }
        rows.append(row)
    return rows


def _per_machine(worlds: dict) -> list:
    rows = []
    for machine in MACHINES:
        row = {"machine": machine.id, "line": machine.line_id}
        for name, world in worlds.items():
            events = [e for e in world.events if e["machine"] == machine.id]
            row[name] = {
                "failures": sum(e["kind"] == "failure" for e in events),
                "planned_repairs": sum(e["kind"] == "planned_repair" for e in events),
                "downtime_h": round(sum(e["downtime_h"] for e in events if e["kind"] == "failure"), 1),
            }
        rows.append(row)
    return rows


def _calculations(sim, base: dict, opex: dict, delta: dict, gains: dict) -> list:
    econ, cal, p = sim.econ, sim.cal, sim.params
    inr = lambda v: f"₹{v / 1e5:,.1f} lakh"  # noqa: E731
    return [
        {
            "label": "Component lives",
            "formula": "Weibull(k from NASA C-MAPSS) with mean = operating hours per year"
            " / failures per year (Azure PdM)",
            "value": f"k = {cal.weibull_shape:.2f}; failures/machine-year: "
            + ", ".join(f"{k} {v:.2f}" for k, v in cal.failures_per_year.items()),
        },
        {
            "label": "Chance a failure is prevented",
            "formula": "model recall (Azure PdM, held-out months) x sensor coverage x people approving the advice",
            "value": f"bearing {cal.detection_recall['bearing']:.2f} x {p.sensor_coverage:.2f} x {p.adoption_rate:.2f} "
            f"= {cal.detection_recall['bearing'] * p.sensor_coverage * p.adoption_rate:.0%}",
        },
        {
            "label": "Warning timing",
            "formula": "alert when predicted life left <= parts lead time;"
            " prediction error ~ N(mean, sd) from NASA C-MAPSS",
            "value": f"relative error sd = {cal.rul_rel_error_sd:.2f}",
        },
        {
            "label": "OEE",
            "formula": "Availability (run h / planned h) x Performance (ideal h / run h) x Quality (good / made)",
            "value": f"{base['oee']:.1%} -> {opex['oee']:.1%}",
        },
        {
            "label": "Production protected",
            "formula": "extra good parts x contribution margin per part",
            "value": f"{delta['good_parts_gained']:,.0f} parts = {inr(gains['production_protected_inr'])}",
        },
        {
            "label": "Maintenance savings",
            "formula": "parts + technician hours (x1.5 overtime after a breakdown) + secondary damage + inspections",
            "value": inr(gains["maintenance_savings_inr"]),
        },
        {
            "label": "Energy",
            "formula": "kWh x tariff; CO2 = MWh x grid factor",
            "value": f"{delta['energy_saved_mwh']:,.0f} MWh x ₹{econ.electricity_inr_per_kwh}/kWh = "
            f"{inr(gains['energy_savings_inr'])}; "
            f"{delta['co2_avoided_t']:,.0f} t CO2 at {econ.grid_tco2_per_mwh} t/MWh",
        },
        {
            "label": "Cost of OpEx",
            "formula": "sensor kits + implementation + (cloud + support) x years",
            "value": inr(delta["opex_cost_inr"]),
        },
        {
            "label": "Return on investment",
            "formula": "(total benefit - cost of OpEx) / cost of OpEx",
            "value": f"{delta['roi_multiple']:.1f}x, payback in month {delta['payback_months']}",
        },
    ]


def player_payload(sim: FactorySimulation, result: dict) -> dict:
    """Compact day-by-day series the browser replays at the pace the user picks."""
    payload = {
        "days": sim.days,
        "start_date": START_DATE.isoformat(),
        "machines": [m.id for m in MACHINES],
        "production_day": result["calendar"].astype(int).tolist(),
        "worlds": {},
    }
    tariff = sim.econ.electricity_inr_per_kwh
    for name, world in result["worlds"].items():
        d = world.daily
        payload["worlds"][name] = {
            "oee": np.nan_to_num(_daily_oee(d), nan=-1).round(4).tolist(),
            "downtime_h": d[:, COL["unplanned_h"]].round(2).tolist(),
            "failures": d[:, COL["failures"]].astype(int).tolist(),
            "good": d[:, COL["good"]].round(0).tolist(),
            "defects": d[:, COL["defects"]].round(1).tolist(),
            "energy_kwh": d[:, COL["energy_kwh"]].round(0).tolist(),
            "cost_inr": (
                d[:, COL["maint_cost"]]
                + d[:, COL["scrap_cost"]]
                + d[:, COL["energy_kwh"]] * tariff
                - d[:, COL["contribution"]]
            )
            .round(0)
            .tolist(),
            "states": ["".join(map(str, row)) for row in world.states],
        }
    return clean(payload)
