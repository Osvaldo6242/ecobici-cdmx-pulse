"""Hourly system-demand forecasting with time-aware validation.

* Features: calendar, holidays, weather, air quality and autoregressive lags (t-24h, t-168h).
* Models: seasonal-naive baseline (same hour last week), Ridge, gradient boosting.
* Validation: rolling-origin (expanding window) over the last weeks of the year.
* Weather impact: counterfactual "what if it had not rained" on the hold-out period.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import RidgeCV
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from . import config

CALENDAR = ["hour_of_day", "iso_dow", "month", "is_non_working_day", "is_holiday"]
WEATHER = ["temp_c", "precip_mm", "precip_prev_3h", "humidity", "wind_kmh", "us_aqi"]
LAGS = ["lag_24", "lag_168", "rolling_168_mean"]
FEATURES = CALENDAR + WEATHER + LAGS
HOLDOUT_HOURS = 28 * 24


def build_features(hourly: pd.DataFrame) -> pd.DataFrame:
    df = hourly.sort_values("hour_ts").reset_index(drop=True).copy()
    df["is_holiday"] = df["holiday_name"].notna().astype(int)
    df["is_non_working_day"] = df["is_non_working_day"].astype(int)
    df["precip_prev_3h"] = df["precip_mm"].shift(1).rolling(3, min_periods=1).sum()
    df["lag_24"] = df["trips"].shift(24)
    df["lag_168"] = df["trips"].shift(168)
    df["rolling_168_mean"] = df["trips"].shift(24).rolling(168, min_periods=24).mean()
    for col in WEATHER:
        df[col] = df[col].interpolate(limit_direction="both")
    return df.dropna(subset=LAGS).reset_index(drop=True)


def _ridge() -> Pipeline:
    pre = ColumnTransformer([
        ("cal", OneHotEncoder(handle_unknown="ignore"), ["hour_of_day", "iso_dow", "month"]),
        ("num", StandardScaler(), ["is_non_working_day", "is_holiday"] + WEATHER + LAGS),
    ])
    return Pipeline([("pre", pre), ("model", RidgeCV(alphas=np.logspace(-2, 3, 12)))])


def _gbm() -> HistGradientBoostingRegressor:
    return HistGradientBoostingRegressor(
        loss="poisson", learning_rate=0.05, max_iter=600, max_leaf_nodes=48,
        min_samples_leaf=30, l2_regularization=1.0, random_state=config.RANDOM_STATE,
    )


def _metrics(y, p) -> dict:
    busy = y >= 50
    return {
        "mae": float(mean_absolute_error(y, p)),
        "r2": float(r2_score(y, p)),
        "mape_busy_hours": float(np.mean(np.abs(p[busy] - y[busy]) / y[busy]) * 100),
    }


def rolling_origin_cv(df: pd.DataFrame, folds: int = 4, horizon: int = 14 * 24) -> pd.DataFrame:
    """Expanding-window CV: each fold trains on everything before and tests the next 2 weeks."""
    rows = []
    end = len(df) - HOLDOUT_HOURS
    for k in range(folds, 0, -1):
        test_end = end - (k - 1) * horizon
        test_start = test_end - horizon
        train, test = df.iloc[:test_start], df.iloc[test_start:test_end]
        y = test["trips"].to_numpy()
        preds = {
            "Seasonal naive (t-168h)": test["lag_168"].to_numpy(),
            "Ridge regression": _ridge().fit(train[FEATURES], train["trips"]).predict(test[FEATURES]),
            "Gradient boosting (Poisson)": _gbm().fit(train[FEATURES], train["trips"]).predict(test[FEATURES]),
        }
        for name, p in preds.items():
            rows.append({"fold": folds - k + 1, "model": name, **_metrics(y, np.clip(p, 0, None))})
    res = pd.DataFrame(rows)
    return (res.groupby("model")[["mae", "r2", "mape_busy_hours"]].mean()
            .sort_values("mae").reset_index())


def holdout(df: pd.DataFrame) -> dict:
    train, test = df.iloc[:-HOLDOUT_HOURS], df.iloc[-HOLDOUT_HOURS:]
    model = _gbm().fit(train[FEATURES], train["trips"])
    pred = np.clip(model.predict(test[FEATURES]), 0, None)
    baseline = test["lag_168"].to_numpy()

    # Counterfactual: same hours with no rain.
    dry = test[FEATURES].copy()
    dry[["precip_mm", "precip_prev_3h"]] = 0.0
    pred_dry = np.clip(model.predict(dry), 0, None)
    rainy = test["precip_mm"].to_numpy() > 0.5

    out = test[["hour_ts", "trips", "precip_mm", "is_non_working_day", "holiday_name"]].copy()
    out["predicted"] = pred
    out["baseline"] = baseline
    out["predicted_no_rain"] = pred_dry
    return {
        "model": model,
        "frame": out.reset_index(drop=True),
        "metrics": _metrics(test["trips"].to_numpy(), pred),
        "baseline_metrics": _metrics(test["trips"].to_numpy(), baseline),
        "rain_effect": {
            "rainy_hours": int(rainy.sum()),
            "trips_lost_in_rainy_hours": float((pred_dry - pred)[rainy].sum()),
            "pct_drop_in_rainy_hours": float(((pred_dry - pred)[rainy].sum()
                                              / max(pred_dry[rainy].sum(), 1)) * 100),
        },
    }


def full_year_oof(df: pd.DataFrame, block_days: int = 7) -> pd.Series:
    """Out-of-fold predictions for every hour (blocked by week) — used for anomaly detection."""
    pred = pd.Series(np.nan, index=df.index)
    block = (df["hour_ts"] - df["hour_ts"].min()).dt.days // block_days
    for b in sorted(block.unique()):
        test = block == b
        # Leave a one-week gap on each side to avoid leakage through lags.
        train = (block < b - 1) | (block > b + 1)
        model = _gbm().set_params(max_iter=300).fit(df.loc[train, FEATURES], df.loc[train, "trips"])
        pred[test] = model.predict(df.loc[test, FEATURES])
    return pred.clip(lower=0)


def run(hourly: pd.DataFrame) -> dict:
    df = build_features(hourly)
    cv = rolling_origin_cv(df)
    ho = holdout(df)
    df["oof_pred"] = full_year_oof(df)
    return {"features": df, "cv": cv, **ho}
