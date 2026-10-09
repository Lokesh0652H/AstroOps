"""Pydantic v2 models for fleet state (mirrored by hand in frontend/src/lib/types.ts)."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

IncidentKind = Literal["pod_oom", "db_conn_leak", "latency_spike", "traffic_surge"]


class MetricPoint(BaseModel):
    ts: datetime
    cpu: float
    memory: float
    latency_p99: float
    error_rate: float


class ServiceRuntime(BaseModel):
    id: str
    name: str
    kind: str
    region: str
    replicas: int
    min_replicas: int
    max_replicas: int
    status: str
    risk_score: float
    risk_level: str
    metrics: MetricPoint


class FleetOverview(BaseModel):
    simulation: dict[str, str]
    fleet_risk_score: float
    fleet_risk_level: str
    services: list[ServiceRuntime]
    engine_alive: bool
    updated_at: datetime


class MetricHistoryOut(BaseModel):
    service_id: str
    service_name: str
    points: list[MetricPoint]


class InjectRequest(BaseModel):
    service_id: str
    kind: IncidentKind


class IncidentOut(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    service_id: str
    service_name: str
    kind: str
    kind_label: str
    status: str
    peak_risk: float
    created_at: datetime
    remediated_at: datetime | None = None
    resolved_at: datetime | None = None
    baseline: dict[str, Any] | None = None
