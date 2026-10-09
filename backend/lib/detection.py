"""DETECT — three-model anomaly ensemble, ported from the Weltrix-AI reference engine.

Model 1: adaptive Z-score breach against a rolling window (per-metric std floors).
Model 2: scikit-learn Isolation Forest on [cpu, memory, latency_p99, error_rate].
Model 3: rate-of-change spike detection for sudden jumps.

The three signals combine into a weighted composite risk score (0-100). Honest
distinctions this module maintains:
  - `reasons` are measured evidence strings, not narratives.
  - `score_forest` is an unsupervised anomaly score, NOT a failure probability.
  - `risk_level` is a fixed-threshold band on the composite score, not a calibrated
    probability of failure.
"""

import logging
from typing import Any

import numpy as np
from sklearn.ensemble import IsolationForest

logger = logging.getLogger(__name__)

WINDOW = 24                 # rolling window for the z-score model (~2 min at 5s ticks)
FOREST_MIN_POINTS = 30      # Isolation Forest needs history before it says anything
FOREST_RETRAIN_EVERY = 25
FOREST_FEATURES = ["cpu", "memory", "latency_p99", "error_rate"]

# Minimum rolling-std for a z-breach to count — prevents false positives on flat metrics.
MIN_STD = {"cpu": 0.5, "memory": 0.5, "latency_p99": 5.0, "error_rate": 0.05}
# Spike detection floors: |delta| must exceed max(3x avg delta, floor) to count.
SPIKE_FLOOR = {"cpu": 5.0, "memory": 5.0, "latency_p99": 20.0, "error_rate": 0.5}

Z_WEIGHT, FOREST_WEIGHT, SPIKE_WEIGHT = 0.35, 0.40, 0.25
LEVELS = ((75.0, "CRITICAL"), (55.0, "HIGH"), (30.0, "MEDIUM"), (0.0, "LOW"))


def risk_level_for(score: float) -> str:
    for floor, level in LEVELS:
        if score >= floor:
            return level
    return "LOW"


class ServiceDetector:
    """Per-service ensemble state — trained models live in-process, samples in Mongo."""

    def __init__(self, service_id: str) -> None:
        self.service_id = service_id
        self.forest = IsolationForest(contamination=0.05, n_estimators=100, random_state=42)
        self.forest_trained = False
        self.train_count = 0
        self.total_points = 0

    def _train_forest(self, rows: list[dict[str, Any]]) -> bool:
        if len(rows) < FOREST_MIN_POINTS:
            return False
        X = [[r[m] for m in FOREST_FEATURES] for r in rows]
        try:
            self.forest.fit(X)
        except Exception:
            logger.exception("isolation forest training failed for %s", self.service_id)
            return False
        self.forest_trained = True
        self.train_count = len(rows)
        return True

    def evaluate(self, history: list[dict[str, Any]]) -> dict[str, Any]:
        """Score the newest sample against the ensemble. `history` is oldest -> newest."""
        self.total_points += 1
        if not history:
            return _result(0.0, 0.0, 0.0, 0.0, [], "no telemetry yet")
        self._train_forest(history[-120:])

        z_hits = _detect_zscore(history)
        spike_hits = _detect_spike(history)
        forest_score = 0.0
        if self.forest_trained:
            newest = [history[-1][m] for m in FOREST_FEATURES]
            try:
                raw = float(self.forest.decision_function([newest])[0])
                forest_score = float(np.clip(0.5 - raw, 0.0, 1.0))
            except Exception:
                logger.exception("isolation forest scoring failed for %s", self.service_id)

        z_flag = min(1.0, len(z_hits) / 2.0)
        spike_flag = 1.0 if spike_hits else 0.0
        score = 100.0 * (Z_WEIGHT * z_flag + FOREST_WEIGHT * forest_score + SPIKE_WEIGHT * spike_flag)
        score = round(min(100.0, score), 1)
        reasons = z_hits + spike_hits
        if forest_score >= 0.6:
            reasons.append(f"Isolation Forest flags this sample as outlying (score {forest_score:.2f}, 0=normal, 1=anomalous)")

        level = risk_level_for(score)
        return _result(score, level, z_flag, forest_score, spike_flag, reasons)


def _result(score: float, level: str, z: float, forest: float, spike: float, reasons: list[str]) -> dict[str, Any]:
    return {
        "risk_score": score,
        "risk_level": level,
        "score_z": round(z, 2),
        "score_forest": round(forest, 2),
        "score_spike": round(spike, 2),
        "reasons": reasons,
        "anomaly": level in ("HIGH", "CRITICAL"),
    }


def _detect_zscore(history: list[dict[str, Any]]) -> list[str]:
    if len(history) < WINDOW:
        return []
    window = history[-WINDOW:]
    reasons: list[str] = []
    for metric in ("cpu", "memory", "latency_p99", "error_rate"):
        values = [r[metric] for r in window]
        mean = float(np.mean(values))
        std = float(np.std(values))
        current = values[-1]
        threshold = mean + 2 * max(std, 0.01)
        if current > threshold and std > MIN_STD[metric]:
            unit = "%" if metric in ("cpu", "memory") else ("ms" if metric == "latency_p99" else "%")
            reasons.append(
                f"{metric} z-score breach: {current:g}{unit} above rolling mean {mean:.1f}{unit} "
                f"(threshold {threshold:.1f}{unit}, window {WINDOW})"
            )
    return reasons


def _detect_spike(history: list[dict[str, Any]]) -> list[str]:
    if len(history) < 3:
        return []
    prev, curr = history[-2], history[-1]
    reasons: list[str] = []
    for metric in ("cpu", "memory", "latency_p99", "error_rate"):
        delta = abs(curr[metric] - prev[metric])
        recent = history[-5:]
        avg_delta = float(np.mean([abs(recent[i][metric] - recent[i - 1][metric]) for i in range(1, len(recent))])) if len(recent) > 1 else delta
        if delta > max(3 * avg_delta, SPIKE_FLOOR[metric]):
            reasons.append(f"{metric} sudden change: +{delta:g} in one tick (typical tick delta {avg_delta:.1f})")
    return reasons


_DETECTORS: dict[str, ServiceDetector] = {}


def get_detector(service_id: str) -> ServiceDetector:
    if service_id not in _DETECTORS:
        _DETECTORS[service_id] = ServiceDetector(service_id)
    return _DETECTORS[service_id]


def model_status() -> dict[str, Any]:
    detectors = list(_DETECTORS.values())
    return {
        "services_tracked": len(detectors),
        "forest_trained": all(d.forest_trained for d in detectors) if detectors else False,
        "forest_min_points": FOREST_MIN_POINTS,
        "retrain_every": FOREST_RETRAIN_EVERY,
        "total_evaluations": sum(d.total_points for d in detectors),
    }
