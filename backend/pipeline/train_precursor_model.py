"""Step 2c - component precursor model on Azure PdM telemetry (100 machines, 1 year, hourly).

Question it answers: "which component is about to fail in the next 48 hours?"
We use it for two things:
  * the fault-signature library (how each component's failure shows up in the sensors),
  * realistic detection rates for the 5-year simulator (we never assume 100% detection).
"""

import logging

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

from .common import MODELS_DIR, RAW_DIR, save_json

log = logging.getLogger("pipeline.precursor_model")

SENSORS = ["volt", "rotate", "pressure", "vibration"]
HORIZON = pd.Timedelta(hours=48)
SPLIT_DATE = pd.Timestamp("2015-09-01")
THRESHOLD = 0.5
# Azure component -> the CNC component it stands in for (matched by failure signature)
COMPONENT_MAP = {"comp4": "bearing", "comp2": "drive", "comp1": "electrical", "comp3": "coolant"}


def build_features(folder) -> pd.DataFrame:
    tel = pd.read_csv(folder / "PdM_telemetry.csv", parse_dates=["datetime"])
    tel = tel.drop_duplicates(["machineID", "datetime"]).sort_values(["machineID", "datetime"])
    errors = pd.read_csv(folder / "PdM_errors.csv", parse_dates=["datetime"])
    machines = pd.read_csv(folder / "PdM_machines.csv")

    stats = tel.groupby("machineID")[SENSORS].agg(["mean", "std"])
    for s in SENSORS:
        tel[f"z_{s}"] = (tel[s] - tel["machineID"].map(stats[(s, "mean")])) / tel["machineID"].map(stats[(s, "std")])

    rolling = tel.groupby("machineID")[[f"z_{s}" for s in SENSORS]].rolling(24, min_periods=6)
    means = rolling.mean().reset_index(level=0, drop=True).add_suffix("_24h_mean")
    stds = rolling.std().reset_index(level=0, drop=True).add_suffix("_24h_std")
    tel = tel.join(means).join(stds)

    error_counts = errors.assign(n=1).pivot_table(
        index=["machineID", "datetime"], columns="errorID", values="n", aggfunc="sum", fill_value=0
    )
    tel = tel.merge(error_counts, left_on=["machineID", "datetime"], right_index=True, how="left")
    error_cols = sorted(c for c in tel.columns if str(c).startswith("error"))
    tel[error_cols] = tel[error_cols].fillna(0)
    for col in error_cols:
        tel[f"{col}_24h"] = tel.groupby("machineID")[col].transform(lambda s: s.rolling(24, min_periods=1).sum())

    tel = tel.merge(machines, on="machineID", how="left")
    tel["model_id"] = tel["model"].str.replace("model", "").astype(int)
    return tel


def add_labels(tel: pd.DataFrame, failures: pd.DataFrame) -> pd.DataFrame:
    upcoming = failures.rename(columns={"datetime": "failure_time"}).sort_values("failure_time")
    tel = tel.sort_values("datetime")
    tel = pd.merge_asof(tel, upcoming, left_on="datetime", right_on="failure_time", by="machineID", direction="forward")
    soon = (tel["failure_time"] - tel["datetime"]) <= HORIZON
    tel["label"] = np.where(soon, tel["failure"], "none")
    return tel.sort_values(["machineID", "datetime"]).reset_index(drop=True)


def evaluate_events(test: pd.DataFrame, proba: pd.DataFrame, failures: pd.DataFrame) -> dict:
    results = {}
    test = test.assign(**{f"p_{c}": proba[c].to_numpy() for c in proba.columns if c != "none"})
    test_failures = failures[failures["datetime"] >= SPLIT_DATE]
    hours_observed = test.groupby("machineID").size().sum()
    for comp, cnc_name in COMPONENT_MAP.items():
        caught, leads = 0, []
        events = test_failures[test_failures["failure"] == comp]
        for _, ev in events.iterrows():
            window = test[
                (test["machineID"] == ev.machineID)
                & (test["datetime"] > ev.datetime - HORIZON)
                & (test["datetime"] <= ev.datetime - pd.Timedelta(hours=2))
            ]
            hits = window[window[f"p_{comp}"] >= THRESHOLD]
            if len(hits):
                caught += 1
                leads.append((ev.datetime - hits["datetime"].min()).total_seconds() / 3600)
        # False alarms: alert episodes on machine-hours with no failure of this component ahead.
        quiet = test[test["label"] != comp]
        flags = (quiet[f"p_{comp}"] >= THRESHOLD).astype(int)
        episodes = int(((flags.diff() == 1) | ((flags == 1) & (quiet["machineID"].diff() != 0))).sum())
        results[cnc_name] = {
            "azure_component": comp,
            "test_failures": int(len(events)),
            "event_recall": caught / max(len(events), 1),
            "median_lead_h": float(np.median(leads)) if leads else 0.0,
            "false_alarms_per_machine_year": episodes / hours_observed * 8760,
        }
    return results


def main() -> dict | None:
    folder = RAW_DIR / "azure_pdm"
    if not (folder / "PdM_telemetry.csv").exists():
        log.warning("Azure telemetry not downloaded - keeping previous precursor results")
        return None

    failures = pd.read_csv(folder / "PdM_failures.csv", parse_dates=["datetime"])
    tel = add_labels(build_features(folder), failures)
    features = [c for c in tel.columns if c.endswith(("_24h_mean", "_24h_std", "_24h"))] + ["age", "model_id"]

    train = tel[tel["datetime"] < SPLIT_DATE - pd.Timedelta(days=2)]
    test = tel[tel["datetime"] >= SPLIT_DATE]
    negatives = train[train["label"] == "none"].sample(frac=0.08, random_state=42)
    fit_rows = pd.concat([train[train["label"] != "none"], negatives])

    model = HistGradientBoostingClassifier(max_iter=250, learning_rate=0.08, max_leaf_nodes=31, random_state=42)
    model.fit(fit_rows[features].fillna(0), fit_rows["label"])

    # Undo the negative down-sampling so probabilities reflect real class frequencies.
    raw = pd.DataFrame(model.predict_proba(test[features].fillna(0)), columns=model.classes_)
    raw["none"] = raw["none"] / 0.08
    proba = raw.div(raw.sum(axis=1), axis=0)

    signatures = {}
    for comp, cnc_name in COMPONENT_MAP.items():
        rows = tel[tel["label"] == comp]
        signatures[cnc_name] = {s: float(rows[f"z_{s}_24h_mean"].mean()) for s in SENSORS}

    metrics = {
        "model": "HistGradientBoostingClassifier (none / 4 components, 48 h horizon)",
        "dataset": f"Azure PdM telemetry: {len(tel):,} machine-hours, {len(failures)} labelled failures",
        "train_period": "2015-01-01 .. 2015-08-29",
        "test_period": "2015-09-01 .. 2015-12-31",
        "alert_threshold": THRESHOLD,
        "components": evaluate_events(test, proba, failures),
        "signatures_z_24h_before_failure": signatures,
        "failures_per_machine_year": {COMPONENT_MAP[c]: n / 100 for c, n in failures["failure"].value_counts().items()},
    }
    for name, m in metrics["components"].items():
        log.info(
            "precursor %-10s recall %.0f%%  lead %.0f h  false alarms %.1f/machine-yr",
            name,
            100 * m["event_recall"],
            m["median_lead_h"],
            m["false_alarms_per_machine_year"],
        )

    joblib.dump({"model": model, "features": features}, MODELS_DIR / "precursor_model.joblib")
    save_json(MODELS_DIR / "precursor_metrics.json", metrics)
    return metrics


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    main()
