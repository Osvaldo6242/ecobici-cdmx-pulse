"""Daily anomaly detection on forecast residuals with a robust (median/MAD) z-score."""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import config


def robust_z(x: pd.Series) -> pd.Series:
    med = x.median()
    mad = (x - med).abs().median() * 1.4826
    return (x - med) / (mad if mad > 0 else 1.0)


def detect(features: pd.DataFrame, threshold: float = 3.0) -> pd.DataFrame:
    daily = (features.assign(day=features["hour_ts"].dt.date)
             .groupby("day")
             .agg(actual=("trips", "sum"), expected=("oof_pred", "sum"),
                  precip_mm=("precip_mm", "sum"), holiday_name=("holiday_name", "first"),
                  non_working=("is_non_working_day", "max"))
             .reset_index())
    daily["residual_pct"] = (daily["actual"] - daily["expected"]) / daily["expected"] * 100
    daily["z"] = robust_z(daily["residual_pct"])
    daily["is_anomaly"] = daily["z"].abs() >= threshold
    daily["direction"] = np.where(daily["residual_pct"] < 0, "below", "above")

    seasons = [(pd.Timestamp(a).date(), pd.Timestamp(b).date(), n) for a, b, n in config.SEASONS]

    def explain(r) -> str:
        if not r.is_anomaly:
            return ""
        if isinstance(r.holiday_name, str):
            return f"Festivo: {r.holiday_name}"
        if r.precip_mm >= 10 and r.direction == "below":
            return f"Lluvia intensa ({r.precip_mm:.0f} mm)"
        for a, b, name in seasons:
            if a <= r.day <= b:
                return name
        return "Sin explicación en calendario ni clima (posible evento o marcha)"

    daily["explanation"] = daily.apply(explain, axis=1)
    return daily
