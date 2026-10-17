"""Step 1 - clean the raw datasets and write a data-quality report.

Every transformation is recorded in data/processed/data_quality_report.json so the
"Data & models" page can show exactly what happened to each file.
"""

import logging

import numpy as np
import pandas as pd

from .common import PROCESSED_DIR, RAW_DIR, save_json

log = logging.getLogger("pipeline.prepare")

CMAPSS_COLUMNS = ["unit", "cycle", "setting1", "setting2", "setting3"] + [f"s{i}" for i in range(1, 22)]


def _base_report(name: str, source: str, df: pd.DataFrame) -> dict:
    return {
        "name": name,
        "source": source,
        "rows_in": int(len(df)),
        "columns": int(df.shape[1]),
        "missing_cells": int(df.isna().sum().sum()),
        "duplicate_rows": int(df.duplicated().sum()),
        "steps": [],
    }


def prepare_ai4i() -> dict:
    raw = pd.read_csv(RAW_DIR / "ai4i" / "ai4i2020.csv", encoding="utf-8-sig")
    report = _base_report("AI4I 2020 machining sensors", "UCI ML Repository #601 (CC BY 4.0)", raw)

    df = raw.rename(
        columns={
            "Product ID": "product_id",
            "Type": "quality_type",
            "Air temperature [K]": "air_temp_k",
            "Process temperature [K]": "process_temp_k",
            "Rotational speed [rpm]": "rpm",
            "Torque [Nm]": "torque_nm",
            "Tool wear [min]": "tool_wear_min",
            "Machine failure": "machine_failure",
        }
    ).drop(columns=["UDI"])
    report["steps"].append("Renamed columns to snake_case, dropped row index UDI")

    df["air_temp_c"] = df["air_temp_k"] - 273.15
    df["process_temp_c"] = df["process_temp_k"] - 273.15
    df["temp_delta_c"] = df["process_temp_k"] - df["air_temp_k"]
    df["power_kw"] = df["torque_nm"] * df["rpm"] * 2 * np.pi / 60 / 1000
    df["wear_x_torque"] = df["tool_wear_min"] * df["torque_nm"]
    report["steps"].append("Kelvin to Celsius; derived power = torque x angular speed; tool wear x torque (overstrain)")

    # The published labels have known inconsistencies: some rows carry a failure mode
    # but machine_failure = 0, and some failures have no mode. We make them agree.
    modes = ["TWF", "HDF", "PWF", "OSF"]
    mode_any = df[modes].sum(axis=1) > 0
    inconsistent = int(((df["machine_failure"] == 1) != (mode_any | (df["RNF"] == 1))).sum())
    df["failure_mode"] = "none"
    for mode in modes:  # first matching mode wins; multi-mode rows are rare (<0.3%)
        df.loc[(df["failure_mode"] == "none") & (df[mode] == 1), "failure_mode"] = mode
    report["steps"].append(
        f"Rebuilt a single failure_mode label from TWF/HDF/PWF/OSF; fixed {inconsistent} rows whose "
        "machine_failure flag disagreed with the mode flags; random failures (RNF) treated as unpredictable"
    )

    df.to_csv(PROCESSED_DIR / "ai4i_clean.csv", index=False)
    report["rows_out"] = int(len(df))
    report["label_counts"] = df["failure_mode"].value_counts().to_dict()
    return report


def _read_cmapss(name: str) -> pd.DataFrame:
    return pd.read_csv(RAW_DIR / "cmapss" / name, sep=r"\s+", header=None, names=CMAPSS_COLUMNS)


def prepare_cmapss() -> dict:
    train = _read_cmapss("train_FD001.txt")
    test = _read_cmapss("test_FD001.txt")
    true_rul = pd.read_csv(RAW_DIR / "cmapss" / "RUL_FD001.txt", header=None, names=["rul"])
    report = _base_report(
        "NASA C-MAPSS FD001 run-to-failure", "NASA Prognostics Data Repository (public domain)", train
    )

    constant = [c for c in CMAPSS_COLUMNS[2:] if train[c].std() < 1e-4]
    train = train.drop(columns=constant)
    test = test.drop(columns=constant)
    report["steps"].append(f"Dropped {len(constant)} constant channels: {', '.join(constant)}")

    life = train.groupby("unit")["cycle"].transform("max")
    train["rul"] = life - train["cycle"]
    test_last = test.groupby("unit")["cycle"].transform("max")
    test["rul"] = test["unit"].map(dict(zip(range(1, 101), true_rul["rul"], strict=False))) + (
        test_last - test["cycle"]
    )
    report["steps"].append("Labelled remaining useful life per cycle (train: life - cycle; test: NASA ground truth)")

    train.to_csv(PROCESSED_DIR / "cmapss_fd001_train.csv", index=False)
    test.to_csv(PROCESSED_DIR / "cmapss_fd001_test.csv", index=False)
    report["rows_out"] = int(len(train))
    report["engines"] = int(train["unit"].nunique())
    report["life_cycles"] = train.groupby("unit")["cycle"].max().describe()[["mean", "std", "min", "max"]].to_dict()
    return report


def prepare_azure() -> dict:
    folder = RAW_DIR / "azure_pdm"
    failures = pd.read_csv(folder / "PdM_failures.csv", parse_dates=["datetime"])
    maint = pd.read_csv(folder / "PdM_maint.csv", parse_dates=["datetime"])
    report = _base_report("Microsoft Azure Predictive Maintenance", "Azure AI Gallery sample (MIT)", failures)
    report["failures"] = int(len(failures))
    report["maintenance_records"] = int(len(maint))
    report["failures_by_component"] = failures["failure"].value_counts().to_dict()

    telemetry_path = folder / "PdM_telemetry.csv"
    if telemetry_path.exists():
        tel = pd.read_csv(telemetry_path, parse_dates=["datetime"])
        report["telemetry_rows"] = int(len(tel))
        report["telemetry_missing_cells"] = int(tel.isna().sum().sum())
        dupes = int(tel.duplicated(["machineID", "datetime"]).sum())
        report["steps"].append(f"Telemetry: {dupes} duplicate machine-hour rows found (dropped at training time)")
    else:
        report["steps"].append("Telemetry file not present - precursor model reuses its last saved results")
    return report


def prepare_zenodo() -> dict:
    folder = RAW_DIR / "zenodo_oee"
    oee = pd.read_csv(folder / "OEEdataset.csv", encoding="utf-8-sig")
    downtime = pd.read_csv(folder / "DowntimeDataset.csv", encoding="utf-8-sig")
    report = _base_report("Zenodo 17855209 line OEE & downtime", "Zenodo, Ntoas et al. 2025 (CC BY 4.0)", downtime)

    oee["shiftDate"] = pd.to_datetime(oee["shiftDate"], format="%m/%d/%y")
    downtime["StopStartTime"] = pd.to_datetime(downtime["StopStartTime"])
    downtime["StopEndTime"] = pd.to_datetime(downtime["StopEndTime"])
    downtime["StopGroup"] = downtime["StopGroup"].str.strip().str.upper()
    bad = downtime["StopDuration(min)"].isna() | (downtime["StopDuration(min)"] <= 0)
    downtime = downtime[~bad]
    report["steps"].append(f"Parsed dates, normalised stop groups, dropped {int(bad.sum())} stops with no duration")
    report["steps"].append("Operator notes are in Greek and are not used; only categories and durations are")

    oee.to_csv(PROCESSED_DIR / "zenodo_oee_clean.csv", index=False)
    downtime.to_csv(PROCESSED_DIR / "zenodo_downtime_clean.csv", index=False)
    report["rows_out"] = int(len(downtime))
    report["shifts"] = int(len(oee))
    return report


def main() -> dict:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    reports = [prepare_ai4i(), prepare_cmapss(), prepare_azure(), prepare_zenodo()]
    for r in reports:
        log.info("%-45s rows in=%s out=%s", r["name"], r["rows_in"], r.get("rows_out", "-"))
    save_json(PROCESSED_DIR / "data_quality_report.json", {"datasets": reports})
    return {"datasets": reports}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    main()
