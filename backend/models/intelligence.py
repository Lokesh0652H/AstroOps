"""Pydantic v2 models for the intelligence layer (mirrored by hand in frontend/src/lib/types.ts)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from models.fleet import MetricPoint

ForecastMetric = Literal["cpu", "memory", "latency_p99", "error_rate"]


class AnomalyOut(BaseModel):
    id: str
    service_id: str
    service_name: str
    detected_at: datetime
    risk_score: float
    risk_level: str
    score_z: float
    score_forest: float
    score_spike: float
    reasons: list[str]
    evidence: MetricPoint | None = None


class RecommendationOut(BaseModel):
    id: str
    service_id: str
    service_name: str
    incident_id: str | None = None
    action_type: str
    title: str
    description: str
    impact: str
    confidence: float
    risk_of_action: str
    requires_approval: bool
    auto_eligible: bool
    status: str
    reasons: list[str]
    evidence: MetricPoint | None = None
    created_at: datetime
    executed_at: datetime | None = None
    executed_by: str | None = None


class VerificationOut(BaseModel):
    id: str
    incident_id: str
    service_id: str
    service_name: str
    verdict: str
    checked_at: datetime
    before: dict | None = None
    after: dict | None = None


class AuditEventOut(BaseModel):
    id: str
    ts: datetime
    stage: str
    actor: str
    message: str
    ref_type: str | None = None
    ref_id: str | None = None


class PolicyState(BaseModel):
    auto_remediate: bool
    cooldown_seconds: int
    verify_delay_seconds: int
    verify_timeout_seconds: int


class PolicyPatch(BaseModel):
    auto_remediate: bool | None = None
    cooldown_seconds: int | None = None
    verify_delay_seconds: int | None = None
    verify_timeout_seconds: int | None = None


class ForecastStep(BaseModel):
    t: datetime
    value: float
    upper: float
    lower: float


class ForecastResponse(BaseModel):
    service_id: str
    service_name: str
    metric: str
    trend: str
    trained_on: int
    steps: list[ForecastStep]
    history: list[MetricPoint]


class ModelStatusOut(BaseModel):
    services_tracked: int
    forest_trained: bool
    forest_min_points: int
    retrain_every: int
    total_evaluations: int
    samples_stored: int
    anomalies_total: int
    note: str
