"""PREDICT — Holt double-exponential smoothing forecast, ported from the Weltrix-AI
reference predictor.

Produces `steps` future points with widening confidence bands and a coarse trend class.
This is a statistical extrapolation of recent telemetry, not a calibrated probability —
the dashboard labels it accordingly.
"""

from typing import Any

import numpy as np

ALPHA = 0.4
BETA = 0.3
STEPS = 5

# How far above the current value the mean forecast must sit before the trend is "RISING".
_RISING_RULES = {
    "cpu": lambda cur: max(cur * 0.10, 3.0),
    "memory": lambda cur: max(cur * 0.10, 3.0),
    "latency_p99": lambda cur: max(cur * 0.20, 8.0),
    "error_rate": lambda cur: max(cur * 0.20, 0.15),
}


def holt_forecast(values: list[float], steps: int = STEPS, alpha: float = ALPHA, beta: float = BETA) -> list[dict[str, float]]:
    if len(values) < 3:
        last = round(values[-1], 2) if values else 0.0
        return [{"value": last, "upper": last + 5, "lower": max(0.0, last - 5)} for _ in range(steps)]

    level = values[0]
    trend = values[1] - values[0]
    for val in values[1:]:
        prev_level = level
        level = alpha * val + (1 - alpha) * (level + trend)
        trend = beta * (level - prev_level) + (1 - beta) * trend

    recent = values[-10:] if len(values) >= 10 else values
    volatility = float(np.std(recent)) if len(recent) > 1 else 1.0

    predictions = []
    for step in range(1, steps + 1):
        forecast = level + trend * step
        margin = volatility * (1 + 0.5 * step)
        predictions.append({
            "value": round(max(0.0, forecast), 2),
            "upper": round(max(0.0, forecast + margin), 2),
            "lower": round(max(0.0, forecast - margin), 2),
        })
    return predictions


def classify_trend(metric: str, current: float, forecast: list[dict[str, float]]) -> str:
    if not forecast:
        return "INSUFFICIENT_DATA"
    mean_predicted = float(np.mean([p["value"] for p in forecast]))
    rule = _RISING_RULES.get(metric, lambda cur: max(cur * 0.1, 3.0))
    if mean_predicted > current + rule(current):
        return "SPIKE_EXPECTED" if mean_predicted > current + 2 * rule(current) else "RISING"
    return "STABLE"
