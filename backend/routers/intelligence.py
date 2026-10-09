"""Intelligence routes — anomalies, forecasts, recommendations (approve/execute), verifications,
audit trail, policy, and model status."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException

from lib import detection, forecaster, policy, telemetry
from lib.db import db
from lib.telemetry import TICK_SECONDS, metric_point
from models.intelligence import (
    AnomalyOut,
    AuditEventOut,
    ForecastMetric,
    ForecastResponse,
    ForecastStep,
    ModelStatusOut,
    PolicyPatch,
    PolicyState,
    RecommendationOut,
    VerificationOut,
)

router = APIRouter(prefix="/intelligence", tags=["intelligence"])


def _clean(doc: dict) -> dict:
    return {k: v for k, v in doc.items() if k != "_id"}


@router.get("/anomalies", response_model=list[AnomalyOut])
async def list_anomalies(limit: int = 20) -> list[AnomalyOut]:
    limit = max(1, min(limit, 50))
    docs = await db.anomalies.find().sort("detected_at", -1).limit(limit).to_list(limit)
    out = []
    for d in docs:
        if d.get("evidence"):
            d["evidence"] = metric_point(d["evidence"])
        out.append(AnomalyOut(**_clean(d)))
    return out


@router.get("/forecast/{service_id}", response_model=ForecastResponse)
async def forecast(service_id: str, metric: ForecastMetric = "cpu") -> ForecastResponse:
    svc = await db.services.find_one({"id": service_id})
    if not svc:
        raise HTTPException(status_code=404, detail="service not found")

    history = await engine_history(service_id, 60)
    values = [p[metric] for p in history]
    steps_raw = forecaster.holt_forecast(values)
    trend = forecaster.classify_trend(metric, values[-1] if values else 0.0, steps_raw)

    last_ts = history[-1]["ts"] if history else datetime.now(timezone.utc)
    if last_ts.tzinfo is None:
        last_ts = telemetry.aware(last_ts)
    steps = [
        ForecastStep(t=last_ts + timedelta(seconds=TICK_SECONDS * (i + 1)), **step)
        for i, step in enumerate(steps_raw)
    ]
    return ForecastResponse(
        service_id=svc["id"],
        service_name=svc["name"],
        metric=metric,
        trend=trend,
        trained_on=len(values),
        steps=steps,
        history=[metric_point(h) for h in history[-40:]],
    )


async def engine_history(service_id: str, limit: int) -> list[dict]:
    docs = await db.telemetry_samples.find({"service_id": service_id}).sort("ts", -1).limit(limit).to_list(limit)
    return list(reversed(docs))


@router.get("/recommendations", response_model=list[RecommendationOut])
async def list_recommendations(limit: int = 20) -> list[RecommendationOut]:
    limit = max(1, min(limit, 50))
    docs = await db.recommendations.find().sort("created_at", -1).limit(limit).to_list(limit)
    out = []
    for d in docs:
        if d.get("evidence"):
            d["evidence"] = metric_point(d["evidence"])
        out.append(RecommendationOut(**_clean(d)))
    return out


@router.post("/recommendations/{rec_id}/approve")
async def approve_recommendation(rec_id: str) -> dict:
    rec = await db.recommendations.find_one({"id": rec_id})
    if not rec:
        raise HTTPException(status_code=404, detail="recommendation not found")
    if rec["status"] != "open":
        raise HTTPException(status_code=409, detail=f"recommendation already {rec['status']}")
    await db.recommendations.update_one({"id": rec_id}, {"$set": {"status": "approved"}})
    await policy.audit(
        "DECIDE",
        f"Operator approved {rec['title']} on {rec['service_name']} — action may now be executed",
        actor="operator",
        ref_type="recommendation",
        ref_id=rec_id,
    )
    return {"ok": True, "status": "approved"}


@router.post("/recommendations/{rec_id}/execute")
async def execute_recommendation(rec_id: str) -> dict:
    rec = await db.recommendations.find_one({"id": rec_id})
    if not rec:
        raise HTTPException(status_code=404, detail="recommendation not found")
    pol = await policy.get_policy()
    try:
        result = await policy.execute_recommendation(rec, pol, actor="operator")
    except policy.PolicyError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"ok": True, "message": result["message"], "executed_at": result["executed_at"].isoformat()}


@router.post("/recommendations/{rec_id}/dismiss")
async def dismiss_recommendation(rec_id: str) -> dict:
    rec = await db.recommendations.find_one({"id": rec_id})
    if not rec:
        raise HTTPException(status_code=404, detail="recommendation not found")
    if rec["status"] not in ("open", "approved"):
        raise HTTPException(status_code=409, detail=f"recommendation already {rec['status']}")
    await db.recommendations.update_one({"id": rec_id}, {"$set": {"status": "dismissed"}})
    await policy.audit(
        "DECIDE",
        f"Operator dismissed recommendation {rec['title']} on {rec['service_name']}",
        actor="operator",
        ref_type="recommendation",
        ref_id=rec_id,
    )
    return {"ok": True, "status": "dismissed"}


@router.get("/verifications", response_model=list[VerificationOut])
async def list_verifications(limit: int = 12) -> list[VerificationOut]:
    limit = max(1, min(limit, 50))
    docs = await db.verifications.find().sort("checked_at", -1).limit(limit).to_list(limit)
    return [VerificationOut(**_clean(d)) for d in docs]


@router.get("/audit", response_model=list[AuditEventOut])
async def list_audit(limit: int = 40) -> list[AuditEventOut]:
    limit = max(1, min(limit, 100))
    docs = await db.audit_events.find().sort("ts", -1).limit(limit).to_list(limit)
    return [AuditEventOut(**_clean(d)) for d in docs]


@router.get("/policy", response_model=PolicyState)
async def get_policy() -> PolicyState:
    return PolicyState(**await policy.get_policy())


@router.put("/policy", response_model=PolicyState)
async def put_policy(patch: PolicyPatch) -> PolicyState:
    current = await policy.get_policy()
    updated = await policy.save_policy(patch.model_dump(exclude_none=True))
    if patch.auto_remediate is not None and patch.auto_remediate != current["auto_remediate"]:
        await policy.audit(
            "DECIDE",
            f"Operator turned auto-remediation {'ON — bounded auto-eligible actions now execute without approval' if patch.auto_remediate else 'OFF — every action requires operator approval'}",
            actor="operator",
        )
    return PolicyState(**updated)


@router.get("/model-status", response_model=ModelStatusOut)
async def model_status() -> ModelStatusOut:
    status = detection.model_status()
    samples_stored = await db.telemetry_samples.count_documents({})
    anomalies_total = await db.anomalies.count_documents({})
    return ModelStatusOut(
        **status,
        samples_stored=samples_stored,
        anomalies_total=anomalies_total,
        note=(
            "Ensemble state (Isolation Forest training counters) lives in the API process memory and "
            "rebuilds from the telemetry store on restart. Detection quality is evaluated only against "
            "simulation ground truth."
        ),
    )
