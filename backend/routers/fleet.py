"""Fleet routes — overview, metric history, incident injection (simulation controls)."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from lib import detection, engine, telemetry
from lib.db import db
from lib.detection import risk_level_for
from lib.policy import audit
from lib.telemetry import KIND_LABELS, metric_point
from models.fleet import FleetOverview, IncidentOut, InjectRequest, MetricHistoryOut, ServiceRuntime

router = APIRouter(prefix="/fleet", tags=["fleet"])

SIMULATION_LABEL = {
    "label": "SIMULATED FLEET",
    "note": (
        "All telemetry on this dashboard comes from a deterministic in-process simulator. "
        "No production infrastructure is connected."
    ),
}

_STATUS_BY_LEVEL = {"LOW": "healthy", "MEDIUM": "elevated", "HIGH": "degraded", "CRITICAL": "critical"}


def _service_status(risk_level: str, has_incident: bool) -> str:
    if has_incident and risk_level in ("HIGH", "CRITICAL"):
        return "incident"
    return _STATUS_BY_LEVEL.get(risk_level, "healthy")


@router.get("/overview", response_model=FleetOverview)
async def fleet_overview() -> FleetOverview:
    services = await telemetry.get_services()
    incidents = await telemetry.get_active_incidents()
    incident_by_service = {i["service_id"]: i for i in incidents}

    runtime: list[ServiceRuntime] = []
    worst_score = 0.0
    for svc in services:
        history = await engine.latest_history(svc["id"])
        det = detection.get_detector(svc["id"]).evaluate(history)
        latest = history[-1] if history else None
        metrics = metric_point(latest) if latest else {
            "ts": datetime.now(timezone.utc), "cpu": 0.0, "memory": 0.0, "latency_p99": 0.0, "error_rate": 0.0,
        }
        runtime.append(ServiceRuntime(
            id=svc["id"], name=svc["name"], kind=svc["kind"], region=svc["region"],
            replicas=svc["replicas"], min_replicas=svc["min_replicas"], max_replicas=svc["max_replicas"],
            status=_service_status(det["risk_level"], svc["id"] in incident_by_service),
            risk_score=det["risk_score"], risk_level=det["risk_level"],
            metrics=metrics,
        ))
        worst_score = max(worst_score, det["risk_score"])

    age = await telemetry.heartbeat_age_seconds()
    return FleetOverview(
        simulation=SIMULATION_LABEL,
        fleet_risk_score=worst_score,
        fleet_risk_level=risk_level_for(worst_score),
        services=runtime,
        engine_alive=age is not None and age < 15,
        updated_at=datetime.now(timezone.utc),
    )


@router.get("/services/{service_id}/metrics", response_model=MetricHistoryOut)
async def service_metrics(service_id: str, points: int = 90) -> MetricHistoryOut:
    svc = await db.services.find_one({"id": service_id})
    if not svc:
        raise HTTPException(status_code=404, detail="service not found")
    points = max(10, min(points, 240))
    docs = await db.telemetry_samples.find({"service_id": service_id}).sort("ts", -1).limit(points).to_list(points)
    docs.reverse()
    return MetricHistoryOut(
        service_id=svc["id"],
        service_name=svc["name"],
        points=[metric_point(d) for d in docs],
    )


@router.post("/incidents/inject", response_model=IncidentOut)
async def inject_incident(req: InjectRequest) -> IncidentOut:
    """Simulation control: inject a degradation into the fleet. Ground truth is labeled."""
    svc = await db.services.find_one({"id": req.service_id})
    if not svc:
        raise HTTPException(status_code=404, detail="service not found")
    active = await db.incidents.find_one(
        {"service_id": req.service_id, "status": {"$in": ["DETECTED", "MITIGATING"]}}
    )
    if active:
        raise HTTPException(status_code=409, detail="service already has an active incident — remediate or reset first")

    now = datetime.now(timezone.utc)
    latest = await db.telemetry_samples.find_one({"service_id": req.service_id}, sort=[("ts", -1)])
    baseline = metric_point(latest) if latest else None
    inc = {
        "id": str(uuid.uuid4()),
        "service_id": svc["id"],
        "service_name": svc["name"],
        "kind": req.kind,
        "kind_label": KIND_LABELS[req.kind],
        "status": "DETECTED",
        "peak_risk": 0.0,
        "created_at": now,
        "remediated_at": None,
        "resolved_at": None,
        "baseline": baseline,
    }
    await db.incidents.insert_one(inc)
    await audit(
        "OBSERVE",
        f"Simulation control: injected {KIND_LABELS[req.kind]} on {svc['name']} — degradation ramps in over ~20s",
        actor="operator",
        ref_type="incident",
        ref_id=inc["id"],
    )
    return IncidentOut(**inc)


@router.get("/incidents", response_model=list[IncidentOut])
async def list_incidents() -> list[IncidentOut]:
    docs = await db.incidents.find().sort("created_at", -1).limit(20).to_list(20)
    return [IncidentOut(**{k: v for k, v in d.items() if k != "_id"}) for d in docs]


@router.post("/reset")
async def reset_fleet() -> dict:
    """Resolve active incidents and clear the anomaly feed; audit history is kept."""
    now = datetime.now(timezone.utc)
    resolved = await db.incidents.update_many(
        {"status": {"$in": ["DETECTED", "MITIGATING"]}},
        {"$set": {"status": "RESOLVED", "resolved_at": now}},
    )
    await db.recommendations.update_many(
        {"status": {"$in": ["open", "approved"]}},
        {"$set": {"status": "dismissed"}},
    )
    await db.anomalies.delete_many({})
    await audit("OBSERVE", f"Fleet reset by operator — {resolved.modified_count} incident(s) resolved, anomaly feed cleared", actor="operator")
    return {"ok": True, "resolved_incidents": resolved.modified_count}
