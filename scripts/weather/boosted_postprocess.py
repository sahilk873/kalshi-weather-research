"""Optional gradient-boosted conditional-quantile postprocessor."""
from __future__ import annotations

import math
from datetime import date

from common import parse_utc_iso

Z90 = 1.2815515655446004
CITIES = {"austin": 0, "la": 1, "nyc": 2}
TYPES = {"high": 0, "low": 1}


def _features(row: dict) -> list[float]:
    target = date.fromisoformat(row["outcome_local_date"])
    mean = float(row.get("mean_f", "nan")); sigma = float(row.get("stddev_f", "nan") or "nan")
    lead = float(row.get("lead_hours", "0") or 0)
    return [mean, sigma if math.isfinite(sigma) else 0.0, lead,
            math.sin(2 * math.pi * target.timetuple().tm_yday / 365.25),
            math.cos(2 * math.pi * target.timetuple().tm_yday / 365.25),
            float(CITIES.get(row.get("city", ""), -1)), float(TYPES.get(row.get("temp_type", ""), -1))]


def _training(forecasts: list[dict], labels: list[dict], as_of=None):
    index = {}
    for label in labels:
        available = parse_utc_iso(label.get("label_available_ts"))
        try: observed = float(label.get("observed_f", ""))
        except (TypeError, ValueError): continue
        if available is not None and math.isfinite(observed): index[label.get("event_ticker", "")] = (available, observed)
    X, y = [], []
    for row in forecasts:
        label = index.get(row.get("event_ticker", "")); decision = parse_utc_iso(row.get("decision_time_utc"))
        if label is None or decision is None: continue
        gate = as_of or decision
        try: target = date.fromisoformat(row["outcome_local_date"]); features = _features(row)
        except (KeyError, TypeError, ValueError): continue
        if label[0] > gate or (as_of is not None and target >= gate.date()) or not all(math.isfinite(v) for v in features): continue
        X.append(features); y.append(label[1])
    return X, y


def fit_boosted(forecasts: list[dict], labels: list[dict], as_of=None, min_training: int = 30):
    """Fit three quantile regressors; raises a clear error if sklearn absent."""
    try:
        from sklearn.ensemble import HistGradientBoostingRegressor
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("boosted postprocessor requires scikit-learn") from exc
    X, y = _training(forecasts, labels, as_of)
    if len(y) < min_training: return None
    models = {}
    for quantile in (0.1, 0.5, 0.9):
        model = HistGradientBoostingRegressor(loss="quantile", quantile=quantile, max_iter=100, learning_rate=0.05, max_leaf_nodes=15, random_state=0)
        model.fit(X, y); models[quantile] = model
    return models, len(y)


def apply_boosted(forecasts: list[dict], fitted) -> list[dict]:
    output = []
    for row in forecasts:
        result = dict(row)
        if fitted is not None:
            models, count = fitted
            q10, q50, q90 = [float(models[q].predict([_features(row)])[0]) for q in (0.1, 0.5, 0.9)]
            q10, q90 = min(q10, q90), max(q10, q90)
            result["p10_f"] = f"{q10:.6f}"; result["p50_f"] = f"{q50:.6f}"; result["p90_f"] = f"{q90:.6f}"
            result["mean_f"] = result["p50_f"]; result["stddev_f"] = f"{max((q90 - q10) / (2 * Z90), 0.01):.6f}"; result["boosted_training_rows"] = str(count)
        else:
            result["boosted_training_rows"] = "0"
        result["model_version"] = f"{row.get('model_version', '')}+boosted_quantile_v1"
        output.append(result)
    return output
