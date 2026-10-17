"""Step 3 - turn dataset statistics into simulator parameters (data/processed/calibration.json).

Each parameter is stored with its value, the dataset it came from and how it was derived,
so the app can show "How we calculated this" next to every simulated number.
"""

import logging

import numpy as np
import pandas as pd

from .common import MODELS_DIR, PROCESSED_DIR, RAW_DIR, load_json, save_json

log = logging.getLogger("pipeline.calibrate")

AZURE_TO_CNC = {"comp4": "bearing", "comp2": "drive", "comp1": "electrical", "comp3": "coolant"}


def _param(value, unit: str, source: str, method: str) -> dict:
    return {"value": value, "unit": unit, "source": source, "method": method}


def zenodo_parameters() -> dict:
    oee = pd.read_csv(PROCESSED_DIR / "zenodo_oee_clean.csv", parse_dates=["shiftDate"])
    stops = pd.read_csv(PROCESSED_DIR / "zenodo_downtime_clean.csv", parse_dates=["StopStartTime"])
    stops["day"] = pd.to_datetime(stops["Date"], format="%m/%d/%y")
    stops = stops[stops["day"].isin(oee["shiftDate"])]
    planned_min = oee["Sumof plannedTime"].sum() / 60
    in_oee = stops[stops["StopType"] != "Planned - Not included in OEE"]

    failure = in_oee[in_oee["StopGroup"] == "FAILURE"]
    other_unplanned = in_oee[(in_oee["StopType"] == "Unplanned") & (in_oee["StopGroup"] != "FAILURE")]
    planned_in = in_oee[in_oee["StopType"] == "Planned - Included in OEE"]
    log_durations = np.log(failure["StopDuration(min)"])

    src = "Zenodo 17855209 (real serial line, 62 shifts, 635 stops)"
    before = pd.read_csv(RAW_DIR / "zenodo_oee" / "OEEdataset.csv", encoding="utf-8-sig")
    after = pd.read_csv(RAW_DIR / "zenodo_oee" / "OEEdataset_afterLSS.csv", encoding="utf-8-sig")
    return {
        "failure_stop_share": _param(
            failure["StopDuration(min)"].sum() / planned_min,
            "share of planned time",
            src,
            "sum of FAILURE stop minutes / planned minutes",
        ),
        "other_unplanned_share": _param(
            other_unplanned["StopDuration(min)"].sum() / planned_min,
            "share of planned time",
            src,
            "materials + operational + unplanned setup stops / planned minutes (AI does not fix these)",
        ),
        "planned_stop_share": _param(
            planned_in["StopDuration(min)"].sum() / planned_min,
            "share of planned time",
            src,
            "planned stops counted inside OEE (changeovers, cleaning) / planned minutes",
        ),
        "repair_log_sigma": _param(
            float(log_durations.std()),
            "log-minutes",
            src,
            "standard deviation of log(failure stop duration) - spread of repair times",
        ),
        "base_performance": _param(
            float(before["Performance"].mean()), "ratio", src, "mean shift performance before improvement"
        ),
        "base_quality": _param(
            float(before["Quality"].mean()), "ratio", src, "mean shift quality rate before improvement"
        ),
        "reference_oee_before": _param(
            float(before["OEE"].mean()), "ratio", src, "mean shift OEE before Lean Six Sigma"
        ),
        "reference_oee_after": _param(float(after["OEE"].mean()), "ratio", src, "mean shift OEE after Lean Six Sigma"),
    }


def azure_parameters() -> dict:
    failures = pd.read_csv(RAW_DIR / "azure_pdm" / "PdM_failures.csv")
    machines = failures["machineID"].nunique()
    precursor = load_json(MODELS_DIR / "precursor_metrics.json")
    src = "Azure PdM (100 machines x 8,760 h, 761 failures)"
    params = {}
    for azure_comp, cnc in AZURE_TO_CNC.items():
        rate = (failures["failure"] == azure_comp).sum() / max(machines, 100)
        comp = precursor["components"][cnc]
        params[cnc] = {
            "failures_per_year": _param(
                float(rate), "per machine-year", src, f"count of {azure_comp} failures / 100 machines / 1 year"
            ),
            "detection_recall": _param(
                comp["event_recall"],
                "share of failures",
                src + ", test months Sep-Dec",
                "failures with a >=50% precursor alert 2-48 h before (held-out months)",
            ),
            "false_alarms_per_year": _param(
                comp["false_alarms_per_machine_year"],
                "per machine-year",
                src,
                "alert episodes not followed by a failure, held-out months",
            ),
            "signature_z": _param(
                precursor["signatures_z_24h_before_failure"][cnc],
                "sigma",
                src,
                "mean 24 h z-score of each sensor before this component failed",
            ),
        }
    return params


def cmapss_parameters() -> dict:
    rul = load_json(MODELS_DIR / "rul_metrics.json")
    src = "NASA C-MAPSS FD001 (100 engines run to failure)"
    return {
        "life_weibull_shape": _param(rul["life_weibull_shape"], "k", src, "Weibull fit of normalised lifetimes"),
        "degradation_b": _param(
            rul["degradation_curve"]["b"],
            "-",
            src,
            "fit of mean health index: damage(u) = (e^(b u) - 1) / (e^b - 1), u = life fraction",
        ),
        "degradation_onset": _param(
            rul["degradation_curve"]["onset_life_fraction"],
            "life fraction",
            src,
            "life fraction where average damage passes 10% (first visible sign)",
        ),
        "rul_relative_error_sd": _param(
            rul["relative_error_sd_near_end"],
            "relative",
            src,
            "spread of (predicted - true)/true RUL when 10-60 cycles remain (out-of-fold)",
        ),
        "rul_test_rmse_cycles": _param(rul["test_rmse_cycles"], "cycles", src, "RMSE on NASA's 100 test engines"),
    }


def ai4i_parameters() -> dict:
    df = pd.read_csv(PROCESSED_DIR / "ai4i_clean.csv")
    twf = df[df["failure_mode"] == "TWF"]["tool_wear_min"]
    model = load_json(MODELS_DIR / "failure_mode_metrics.json")
    src = "AI4I 2020 (10,000 machining records)"
    return {
        "tool_failure_wear_mean": _param(float(twf.mean()), "min", src, "mean tool wear at tool-wear failures"),
        "tool_failure_wear_sd": _param(float(twf.std()), "min", src, "spread of tool wear at tool-wear failures"),
        "air_temp_c": _param(float(df["air_temp_c"].mean()), "°C", src, "mean air temperature"),
        "process_delta_c": _param(float(df["temp_delta_c"].mean()), "°C", src, "mean process - air temperature"),
        "failure_model_precision": _param(
            model["precision_at_threshold"], "ratio", src, "held-out precision at alert threshold"
        ),
        "failure_model_recall": _param(
            model["recall_at_threshold"], "ratio", src, "held-out recall at alert threshold"
        ),
    }


def main() -> dict:
    calibration = {
        "line": zenodo_parameters(),
        "components": azure_parameters(),
        "degradation": cmapss_parameters(),
        "machining": ai4i_parameters(),
    }
    line = calibration["line"]
    log.info(
        "Zenodo: failures %.1f%%, other unplanned %.1f%%, performance %.3f, quality %.3f of planned time",
        100 * line["failure_stop_share"]["value"],
        100 * line["other_unplanned_share"]["value"],
        line["base_performance"]["value"],
        line["base_quality"]["value"],
    )
    save_json(PROCESSED_DIR / "calibration.json", calibration)
    return calibration


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    main()
