"""Step 2b - remaining-useful-life (RUL) model on NASA C-MAPSS FD001.

Turbofans are not CNC spindles, so we do not reuse raw jet-engine sensors. We reuse what
transfers: the SHAPE of degradation. Sensors are fused into one health index (HI, 1 = new,
0 = failed); the RUL model only sees HI-based features plus normalised age, so the same
model runs on any machine that can produce a health index.

Outputs: models/rul_model.joblib, models/rul_metrics.json (also used by the simulator:
degradation curve shape, life spread and prediction-error spread).
"""

import logging

import joblib
import numpy as np
import pandas as pd
from scipy.stats import weibull_min
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import GroupKFold
from sklearn.preprocessing import StandardScaler

from .common import MODELS_DIR, PROCESSED_DIR, save_json

log = logging.getLogger("pipeline.rul_model")

SENSORS = ["s2", "s3", "s4", "s7", "s8", "s9", "s11", "s12", "s13", "s14", "s15", "s17", "s20", "s21"]
RUL_CAP = 125  # standard piecewise-linear cap used in C-MAPSS literature
ALARM_CYCLES = 30
FEATURES = ["hi", "slope_10", "slope_30", "age_frac"]


def add_health_index(df: pd.DataFrame, scaler: StandardScaler, fuser: LinearRegression) -> pd.DataFrame:
    df = df.copy()
    raw = fuser.predict(scaler.transform(df[SENSORS]))
    df["hi_raw"] = raw
    df["hi"] = df.groupby("unit")["hi_raw"].transform(lambda s: s.ewm(span=15).mean()).clip(-0.2, 1.2)
    return df


def add_features(df: pd.DataFrame, mean_life: float) -> pd.DataFrame:
    df = df.copy()
    grouped = df.groupby("unit")["hi"]
    df["slope_10"] = (df["hi"] - grouped.shift(10)).fillna(0) / 10
    df["slope_30"] = (df["hi"] - grouped.shift(30)).fillna(0) / 30
    df["age_frac"] = df["cycle"] / mean_life
    return df


def fit_curve_shape(train: pd.DataFrame) -> dict:
    """Average HI against life fraction u, then fit HI(u) = h0 - (h0-h1)(e^{bu}-1)/(e^b-1)."""
    life = train.groupby("unit")["cycle"].transform("max")
    u = train["cycle"] / life
    bins = np.linspace(0, 1, 41)
    centers = (bins[:-1] + bins[1:]) / 2
    mean_hi = train.groupby(pd.cut(u, bins, include_lowest=True), observed=False)["hi"].mean().to_numpy()
    h0, h1 = mean_hi[:4].mean(), mean_hi[-1]
    normalized = (h0 - mean_hi) / (h0 - h1)  # 0 = healthy, 1 = failed

    best_b, best_err = 1.0, np.inf
    for b in np.linspace(0.5, 12, 231):
        err = np.mean(((np.exp(b * centers) - 1) / (np.exp(b) - 1) - normalized) ** 2)
        if err < best_err:
            best_b, best_err = b, err
    onset = float(centers[np.argmax(normalized > 0.1)])
    return {
        "b": float(best_b),
        "fit_mse": float(best_err),
        "onset_life_fraction": onset,
        "hi_healthy": float(h0),
        "hi_failed": float(h1),
        "curve_u": centers.tolist(),
        "curve_damage": normalized.tolist(),
    }


def main() -> dict:
    train = pd.read_csv(PROCESSED_DIR / "cmapss_fd001_train.csv")
    test = pd.read_csv(PROCESSED_DIR / "cmapss_fd001_test.csv")
    lives = train.groupby("unit")["cycle"].max()
    mean_life = float(lives.mean())

    # 1. Health index: healthy rows (first 30 cycles) -> 1, failing rows (last 15) -> 0.
    scaler = StandardScaler().fit(train[SENSORS])
    anchors = train[(train["cycle"] <= 30) | (train["rul"] <= 15)]
    target = (anchors["cycle"] <= 30).astype(float)
    fuser = LinearRegression().fit(scaler.transform(anchors[SENSORS]), target)
    train = add_features(add_health_index(train, scaler, fuser), mean_life)
    test = add_features(add_health_index(test, scaler, fuser), mean_life)

    shape = fit_curve_shape(train)
    weibull_shape, _, weibull_scale = weibull_min.fit(lives / mean_life, floc=0)

    # 2. RUL regressors (point + 10th/90th percentile) on HI features.
    y = train["rul"].clip(upper=RUL_CAP) / mean_life
    params = dict(max_iter=300, learning_rate=0.05, max_leaf_nodes=20, random_state=42)
    point = HistGradientBoostingRegressor(**params)

    # Out-of-fold predictions on full run-to-failure histories -> honest warning statistics.
    oof = np.zeros(len(train))
    for fit_idx, val_idx in GroupKFold(n_splits=5).split(train, y, train["unit"]):
        fold_model = HistGradientBoostingRegressor(**params).fit(train.iloc[fit_idx][FEATURES], y.iloc[fit_idx])
        oof[val_idx] = fold_model.predict(train.iloc[val_idx][FEATURES])
    train["pred_rul"] = oof * mean_life

    point.fit(train[FEATURES], y)
    low = HistGradientBoostingRegressor(loss="quantile", quantile=0.1, **params).fit(train[FEATURES], y)
    high = HistGradientBoostingRegressor(loss="quantile", quantile=0.9, **params).fit(train[FEATURES], y)

    last = test.groupby("unit").tail(1)
    pred = point.predict(last[FEATURES]) * mean_life
    truth = last["rul"].clip(upper=RUL_CAP).to_numpy()
    err = pred - truth
    nasa_score = float(np.sum(np.where(err < 0, np.exp(-err / 13) - 1, np.exp(err / 10) - 1)))
    p10 = low.predict(last[FEATURES]) * mean_life
    p90 = high.predict(last[FEATURES]) * mean_life

    # Warning behaviour: first cycle at which the model says "<= 30 cycles left".
    leads = []
    for _, unit in train.groupby("unit"):
        alarm = unit[unit["pred_rul"] <= ALARM_CYCLES]
        leads.append(float(alarm["rul"].iloc[0]) if len(alarm) else 0.0)
    leads = np.array(leads)
    near_end = train[(train["rul"] >= 10) & (train["rul"] <= 60)]
    rel_err = (near_end["pred_rul"] - near_end["rul"]) / near_end["rul"]

    metrics = {
        "model": "HistGradientBoostingRegressor on health-index features (+ P10/P90 quantile models)",
        "dataset": "NASA C-MAPSS FD001: 100 training engines run to failure, 100 test engines",
        "mean_life_cycles": mean_life,
        "test_rmse_cycles": float(np.sqrt(np.mean(err**2))),
        "test_mae_cycles": float(np.mean(np.abs(err))),
        "nasa_score": nasa_score,
        "p10_p90_coverage": float(np.mean((truth >= p10) & (truth <= p90))),
        "warning_recall": float(np.mean(leads >= 10)),
        "median_warning_lead_cycles": float(np.median(leads)),
        "premature_warning_share": float(np.mean(leads > 2 * ALARM_CYCLES)),
        "relative_error_sd_near_end": float(rel_err.std()),
        "relative_error_mean_near_end": float(rel_err.mean()),
        "life_weibull_shape": float(weibull_shape),
        "life_weibull_scale_normalised": float(weibull_scale),
        "life_cv": float(lives.std() / mean_life),
        "degradation_curve": shape,
    }
    log.info(
        "C-MAPSS RUL: test RMSE %.1f cycles, warning recall %.0f%%, curve b=%.2f, Weibull k=%.2f",
        metrics["test_rmse_cycles"],
        100 * metrics["warning_recall"],
        shape["b"],
        weibull_shape,
    )

    joblib.dump(
        {
            "point": point,
            "low": low,
            "high": high,
            "features": FEATURES,
            "mean_life": mean_life,
            "hi_healthy": shape["hi_healthy"],
            "hi_failed": shape["hi_failed"],
            "cap": RUL_CAP,
            "scaler": scaler,
            "fuser": fuser,
            "sensors": SENSORS,
        },
        MODELS_DIR / "rul_model.joblib",
    )
    save_json(MODELS_DIR / "rul_metrics.json", metrics)
    return metrics


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    main()
