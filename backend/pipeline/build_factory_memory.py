"""Step 4 - build the factory's memory: maintenance log, past incidents, pilot decisions.

The maintenance log replays REAL event dates from Azure PdM machines 1-24 (re-dated by
+3,926 days so the history ends in Sept 2026) onto our machines M-01..M-24. Technician
notes are written in maintenance-work-order shorthand and tagged Item / Problem / Solution
the way NIST Nestor tags work orders (Nestor vocabulary + a CNC vocabulary).
"""

import logging
import re

import numpy as np
import pandas as pd

from app.plant.factory import COMPONENTS, MACHINES

from .common import PROCESSED_DIR, RAW_DIR, load_json, save_json

log = logging.getLogger("pipeline.memory")

DATE_SHIFT = pd.Timedelta(days=3926)  # 2015-01-01 -> 2025-10-01
AZURE_TO_CNC = {"comp4": "bearing", "comp2": "drive", "comp1": "electrical", "comp3": "coolant"}

NOTES = {
    ("bearing", "unplanned"): [
        "SPDL NOISY + HI VIB, FRONT BRG FAILED. REPL BRG SET + SEALS, RUNOUT 3um OK",
        "spindle seized in roughing, outer race pitting. replaced bearings, regreased",
        "VIB ALARM 9.2 mm/s, spindle hot. replaced spindle bearing pair, checked preload",
        "brg failure - grinding noise, chatter marks on parts. replaced brg, scrapped batch",
    ],
    ("bearing", "planned"): [
        "PLANNED: spindle brg replaced on vib trend, early spalling found on inner race",
        "PM spindle brg change, runout 2um after, lubrication checked",
    ],
    ("drive", "unplanned"): [
        "SPDL SPEED DROP, belt slipping. replaced drive belt + tensioner",
        "encoder alarm, spindle stopped. replaced spindle motor encoder, aligned",
        "rpm hunting under load, belt cracked. replaced belt, adjusted tension",
    ],
    ("drive", "planned"): [
        "PLANNED: drive belt replaced, glazing seen, tension reset",
        "PM spindle drive inspection, belt worn - replaced",
    ],
    ("electrical", "unplanned"): [
        "SERVO ALARM OVERVOLTAGE, X-axis stopped. replaced power module",
        "loose terminal on spindle amp, burnt lug. retightened + replaced contactor",
        "drive tripped repeatedly, voltage spikes. replaced servo amplifier",
    ],
    ("electrical", "planned"): [
        "PLANNED: thermography hot spot on panel, retightened terminals",
        "PM electrical cabinet, replaced aged contactor, cleaned filters",
    ],
    ("coolant", "unplanned"): [
        "COOLANT PRESSURE LOW, parts hot, size drift. pump impeller worn - replaced pump",
        "coolant filter clogged, tank dirty. cleaned tank, replaced filter",
        "through-spindle coolant lost, seal leak. replaced rotary union seal",
    ],
    ("coolant", "planned"): [
        "PLANNED: coolant pump replaced on pressure trend",
        "PM coolant system: filter change, concentration corrected",
    ],
}

ROOT_CAUSES = {
    "bearing": ["Spindle bearing degradation"] * 5 + ["Spindle misalignment", "Lubrication starvation"],
    "drive": ["Drive belt slip / wear"] * 4 + ["Spindle encoder fault"],
    "electrical": ["Servo power module fault"] * 3 + ["Loose power terminal"],
    "coolant": ["Coolant pump wear"] * 3 + ["Clogged coolant filter"],
}

CNC_VOCAB = {
    "I": [
        "spindle",
        "spdl",
        "brg",
        "bearing",
        "bearings",
        "seals",
        "seal",
        "belt",
        "tensioner",
        "encoder",
        "motor",
        "servo",
        "amplifier",
        "amp",
        "module",
        "contactor",
        "terminal",
        "lug",
        "coolant",
        "pump",
        "impeller",
        "filter",
        "tank",
        "union",
        "panel",
        "drive",
    ],
    "P": [
        "noisy",
        "vib",
        "seized",
        "pitting",
        "spalling",
        "slipping",
        "alarm",
        "overvoltage",
        "loose",
        "low",
        "clogged",
        "hot",
        "leak",
        "worn",
        "failed",
        "failure",
        "cracked",
        "hunting",
        "chatter",
        "drift",
        "tripped",
        "spikes",
        "burnt",
        "glazing",
        "dirty",
    ],
    "S": [
        "replaced",
        "repl",
        "regreased",
        "retightened",
        "cleaned",
        "adjusted",
        "checked",
        "aligned",
        "corrected",
        "scrapped",
        "reset",
    ],
}
ALIASES = {
    "spdl": "spindle",
    "brg": "bearing",
    "bearings": "bearing",
    "vib": "vibration",
    "repl": "replace",
    "replaced": "replace",
    "amp": "amplifier",
}


def load_vocabulary() -> dict[str, tuple[str, str]]:
    """token -> (class, alias). Nestor's excavator vocabulary covers generic maintenance words."""
    vocab = {}
    nestor = RAW_DIR / "nist_mwo" / "nestor_vocab_1gram.csv"
    if nestor.exists():
        for row in pd.read_csv(nestor).dropna(subset=["NE"]).itertuples():
            if row.NE in ("I", "P", "S"):
                vocab[str(row.tokens)] = (row.NE, str(row.alias))
    for cls, tokens in CNC_VOCAB.items():
        for token in tokens:
            vocab[token] = (cls, ALIASES.get(token, token))
    return vocab


def tag_note(note: str, vocab: dict) -> dict[str, list[str]]:
    tags = {"item": [], "problem": [], "solution": []}
    names = {"I": "item", "P": "problem", "S": "solution"}
    for token in re.findall(r"[a-z]+", note.lower()):
        if token in vocab:
            cls, alias = vocab[token]
            if alias not in tags[names[cls]]:
                tags[names[cls]].append(alias)
    return tags


def build_maintenance_log(rng: np.random.Generator, vocab: dict, repair_sigma: float) -> pd.DataFrame:
    folder = RAW_DIR / "azure_pdm"
    maint = pd.read_csv(folder / "PdM_maint.csv", parse_dates=["datetime"])
    failures = pd.read_csv(folder / "PdM_failures.csv", parse_dates=["datetime"])
    failure_keys = set(zip(failures["datetime"], failures["machineID"], failures["failure"], strict=False))

    rows = []
    for rec in maint[maint["machineID"] <= len(MACHINES)].itertuples():
        component = AZURE_TO_CNC[rec.comp]
        spec = COMPONENTS[component]
        unplanned = (rec.datetime, rec.machineID, rec.comp) in failure_keys
        if unplanned:
            hours = spec.unplanned_repair_h * rng.lognormal(0, repair_sigma)
            if rng.random() < spec.stockout_prob:
                hours += spec.stockout_wait_h * rng.uniform(0.5, 1.2)
            cost = spec.part_cost_inr + hours * 300 * 1.5
            if rng.random() < spec.collateral_prob:
                cost += spec.collateral_cost_inr
        else:
            hours = spec.planned_repair_h * rng.lognormal(0, 0.25)
            cost = spec.part_cost_inr + hours * 300
        work_type = "unplanned" if unplanned else "planned"
        note = str(rng.choice(NOTES[(component, work_type)]))
        tags = tag_note(note, vocab)
        rows.append(
            {
                "date": (rec.datetime + DATE_SHIFT).strftime("%Y-%m-%d %H:%M"),
                "machine_id": MACHINES[rec.machineID - 1].id,
                "component": component,
                "work_type": work_type,
                "duration_h": round(hours, 1),
                "cost_inr": round(cost, -2),
                "parts": spec.name,
                "technician_note": note,
                "tags_item": ";".join(tags["item"]),
                "tags_problem": ";".join(tags["problem"]),
                "tags_solution": ";".join(tags["solution"]),
                "source": f"Azure PdM machine {rec.machineID} ({rec.comp}), re-dated",
            }
        )
    return pd.DataFrame(rows).sort_values("date").reset_index(drop=True)


def build_incidents(log_df: pd.DataFrame, signatures: dict, rng: np.random.Generator) -> list[dict]:
    """Every unplanned job becomes a past incident with the sensor pattern seen before it."""
    incidents = []
    for i, row in enumerate(log_df[log_df["work_type"] == "unplanned"].itertuples(), start=1):
        base = signatures[row.component]
        pattern = {
            "vibration": base["vibration"] + rng.normal(0, 0.3),
            "rpm": base["rotate"] + rng.normal(0, 0.3),
            "coolant_pressure": -base["pressure"] + rng.normal(0, 0.3),  # our pump failure = pressure falls
            "voltage": base["volt"] + rng.normal(0, 0.3),
            "process_temp": (0.9 if row.component in ("bearing", "coolant") else 0.1) + rng.normal(0, 0.3),
            "cycle_time": (0.8 if row.component in ("bearing", "drive") else 0.1) + rng.normal(0, 0.3),
        }
        cause = str(rng.choice(ROOT_CAUSES[row.component]))
        incidents.append(
            {
                "id": f"INC-{2025000 + i}",
                "date": row.date,
                "machine_id": row.machine_id,
                "component": row.component,
                "root_cause": cause,
                "confirmed": cause == ROOT_CAUSES[row.component][0],
                "downtime_h": row.duration_h,
                "cost_inr": row.cost_inr,
                "technician_note": row.technician_note,
                "pattern_z": {k: round(float(v), 2) for k, v in pattern.items()},
            }
        )
    return incidents


def main() -> dict:
    rng = np.random.default_rng(7)
    calibration = load_json(PROCESSED_DIR / "calibration.json")
    repair_sigma = calibration["line"]["repair_log_sigma"]["value"]
    signatures = {c: p["signature_z"]["value"] for c, p in calibration["components"].items()}

    vocab = load_vocabulary()
    log_df = build_maintenance_log(rng, vocab, repair_sigma)
    incidents = build_incidents(log_df, signatures, rng)

    log_df.to_csv(PROCESSED_DIR / "maintenance_history.csv", index=False)
    save_json(PROCESSED_DIR / "incident_history.json", {"incidents": incidents})
    summary = {
        "maintenance_records": len(log_df),
        "incidents": len(incidents),
        "unplanned_share": float((log_df["work_type"] == "unplanned").mean()),
        "vocabulary_terms": len(vocab),
    }
    log.info(
        "factory memory: %(maintenance_records)s jobs, %(incidents)s incidents, %(vocabulary_terms)s vocab terms",
        summary,
    )
    return summary


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    main()
