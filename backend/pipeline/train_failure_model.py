"""Step 2a - failure-mode classifier on AI4I 2020.

Given a machine's operating point (temperatures, speed, torque, tool wear) it returns the
probability of each failure mode: tool wear (TWF), heat dissipation (HDF), power (PWF),
overstrain (OSF). OpEx uses it for live operating-point risk and tool-change timing.
"""

import logging

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import average_precision_score, precision_recall_curve, roc_auc_score
from sklearn.model_selection import train_test_split

from .common import MODELS_DIR, PROCESSED_DIR, save_json

log = logging.getLogger("pipeline.failure_model")

FEATURES = [
    "air_temp_c",
    "process_temp_c",
    "temp_delta_c",
    "rpm",
    "torque_nm",
    "tool_wear_min",
    "power_kw",
    "wear_x_torque",
    "quality_level",
]
QUALITY_LEVEL = {"L": 0, "M": 1, "H": 2}


def main() -> dict:
    df = pd.read_csv(PROCESSED_DIR / "ai4i_clean.csv")
    df["quality_level"] = df["quality_type"].map(QUALITY_LEVEL)
    X, y = df[FEATURES], df["failure_mode"]

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, stratify=y, random_state=42)
    model = HistGradientBoostingClassifier(
        max_iter=300, learning_rate=0.06, max_leaf_nodes=15, l2_regularization=1.0, random_state=42
    )
    model.fit(X_train, y_train)

    proba = pd.DataFrame(model.predict_proba(X_test), columns=model.classes_, index=X_test.index)
    failure_score = 1 - proba["none"]
    is_failure = (y_test != "none").astype(int)

    precision, recall, thresholds = precision_recall_curve(is_failure, failure_score)
    f1 = 2 * precision * recall / np.clip(precision + recall, 1e-9, None)
    best = int(np.nanargmax(f1[:-1]))
    threshold = float(thresholds[best])

    predicted_mode = proba.drop(columns="none").idxmax(axis=1)
    failures = y_test != "none"
    per_mode = {}
    for mode in ["TWF", "HDF", "PWF", "OSF"]:
        mask = y_test == mode
        if mask.sum():
            caught = (failure_score[mask] >= threshold) & (predicted_mode[mask] == mode)
            per_mode[mode] = {"test_cases": int(mask.sum()), "recall": float(caught.mean())}

    metrics = {
        "model": "HistGradientBoostingClassifier (5 classes: none, TWF, HDF, PWF, OSF)",
        "dataset": "AI4I 2020, 10,000 rows, stratified 80/20 split",
        "test_rows": int(len(X_test)),
        "roc_auc_any_failure": float(roc_auc_score(is_failure, failure_score)),
        "pr_auc_any_failure": float(average_precision_score(is_failure, failure_score)),
        "alert_threshold": threshold,
        "precision_at_threshold": float(precision[best]),
        "recall_at_threshold": float(recall[best]),
        "mode_accuracy_on_failures": float((predicted_mode[failures] == y_test[failures]).mean()),
        "per_mode": per_mode,
    }
    log.info(
        "AI4I failure model: ROC AUC %.3f, PR AUC %.3f, P %.2f / R %.2f at %.2f",
        metrics["roc_auc_any_failure"],
        metrics["pr_auc_any_failure"],
        metrics["precision_at_threshold"],
        metrics["recall_at_threshold"],
        threshold,
    )

    model.fit(X, y)  # final model uses all rows; metrics above are from the held-out split
    MODELS_DIR.mkdir(exist_ok=True)
    joblib.dump(
        {"model": model, "features": FEATURES, "threshold": threshold}, MODELS_DIR / "failure_mode_model.joblib"
    )
    save_json(MODELS_DIR / "failure_mode_metrics.json", metrics)
    return metrics


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    main()
