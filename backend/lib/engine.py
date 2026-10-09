"""The AIOps engine loop — one cycle every TICK_SECONDS:

    OBSERVE (sample the fleet) -> DETECT (ensemble) -> DECIDE (policy recommendation)
    -> ACT (bounded, policy-gated) -> VERIFY (fresh telemetry) -> LEARN (outcome + audit)

PREDICT is served on demand by /api/intelligence/forecast from the same sample store.
Every stage transition lands in the audit trail. The loop never dies on a bad cycle:
failures are logged and the next tick retries.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone

from lib import detection, policy, telemetry
from lib.db import db
from lib.telemetry import ESCALATE_AFTER, TICK_SECONDS, build_sample, get_active_incidents, get_services

logger = logging.getLogger(__name__)

METRIC_KEYS = ("ts", "cpu", "memory", "latency_p99", "error_rate")


async def latest_history(service_id: str, limit: int = 120) -> list[dict]:
    docs = await db.telemetry_samples.find({"service_id": service_id}).sort("ts", -1).limit(limit).to_list(limit)
    return list(reversed(docs))


async def _maybe_store_anomaly(service: dict, det: dict, sample: dict, now: datetime) -> None:
    """DETECT stage persistence — deduped to one anomaly per service per minute."""
    recent = await db.anomalies.find_one(
        {"service_id": service["id"], "detected_at": {"$gte": now - timedelta(seconds=60)}}
    )
    if recent:
        return
    await db.anomalies.insert_one({
        "id": str(uuid.uuid4()),
        "service_id": service["id"],
        "service_name": service["name"],
        "detected_at": now,
        "risk_score": det["risk_score"],
        "risk_level": det["risk_level"],
        "score_z": det["score_z"],
        "score_forest": det["score_forest"],
        "score_spike": det["score_spike"],
        "reasons": det["reasons"],
        "evidence": {k: sample[k] for k in METRIC_KEYS},
    })
    await policy.audit(
        "DETECT",
        f"Anomaly on {service['name']}: risk {det['risk_score']} ({det['risk_level']}) — {'; '.join(det['reasons'][:2])}",
        ref_type="anomaly",
    )


async def _verify_incidents(pol: dict, now: datetime) -> None:
    for inc in await db.incidents.find({"status": "MITIGATING"}).to_list(100):
        service = await db.services.find_one({"id": inc["service_id"]})
        if not service:
            continue
        current = build_sample(service, [inc], now)
        verdict = policy.check_recovery(inc, current, pol, now)
        if verdict is None:
            continue
        await db.verifications.insert_one({
            "id": str(uuid.uuid4()),
            "incident_id": inc["id"],
            "service_id": inc["service_id"],
            "service_name": inc["service_name"],
            "verdict": verdict,
            "checked_at": now,
            "before": inc.get("baseline"),
            "after": {k: current[k] for k in METRIC_KEYS},
        })
        if verdict == "RECOVERED":
            await db.incidents.update_one({"id": inc["id"]}, {"$set": {"status": "RECOVERED", "resolved_at": now}})
            await policy.audit(
                "VERIFY",
                f"Recovery VERIFIED for {inc['service_name']}: fresh telemetry back within baseline "
                f"(error {current['error_rate']}%, p99 latency {current['latency_p99']}ms)",
                ref_type="incident",
                ref_id=inc["id"],
            )
            await policy.record_outcome(inc, "RECOVERED")
        elif verdict == "FAILED":
            await db.incidents.update_one({"id": inc["id"]}, {"$set": {"status": "FAILED", "resolved_at": now}})
            await policy.audit(
                "VERIFY",
                f"Recovery FAILED for {inc['service_name']}: metrics never returned to baseline within the timeout — escalated for human review",
                ref_type="incident",
                ref_id=inc["id"],
            )
            await policy.record_outcome(inc, "FAILED")
        else:
            await policy.audit(
                "VERIFY",
                f"Recovery not yet confirmed for {inc['service_name']} — action executed but telemetry still degraded",
                ref_type="incident",
                ref_id=inc["id"],
            )


async def _escalate_stale(now: datetime) -> None:
    cutoff = now - timedelta(seconds=ESCALATE_AFTER)
    result = await db.incidents.update_many(
        {"status": "DETECTED", "created_at": {"$lt": cutoff}},
        {"$set": {"status": "ESCALATED", "resolved_at": now}},
    )
    if result.modified_count:
        await policy.audit(
            "VERIFY",
            f"{result.modified_count} unremediated incident(s) auto-escalated after {ESCALATE_AFTER:.0f}s without remediation",
        )


async def run_cycle() -> None:
    now = datetime.now(timezone.utc)
    services = await get_services()
    incidents = await get_active_incidents()
    by_service = {i["service_id"]: i for i in incidents}

    # OBSERVE — sample every service against the incidents affecting it.
    samples: dict[str, dict] = {}
    to_insert: list[dict] = []
    for svc in services:
        active = [by_service[svc["id"]]] if svc["id"] in by_service else []
        sample = build_sample(svc, active, now)
        samples[svc["id"]] = sample
        to_insert.append(sample)
    await telemetry.record_samples(to_insert)
    await telemetry.heartbeat()

    pol = await policy.get_policy()

    # DETECT + DECIDE (+ bounded ACT when the policy allows it).
    for svc in services:
        history = await latest_history(svc["id"])
        det = detection.get_detector(svc["id"]).evaluate(history)
        if det["anomaly"]:
            await _maybe_store_anomaly(svc, det, samples[svc["id"]], now)

        incident = by_service.get(svc["id"])
        if incident and det["risk_score"] > incident.get("peak_risk", 0.0):
            await db.incidents.update_one({"id": incident["id"]}, {"$set": {"peak_risk": det["risk_score"]}})

        rec = await policy.decide(svc, det, incident, now, pol, evidence=samples[svc["id"]])
        if rec and pol["auto_remediate"] and rec["auto_eligible"] and not rec["requires_approval"]:
            try:
                await policy.execute_recommendation(rec, pol, actor="policy-engine (auto_remediate)")
            except policy.PolicyError as exc:
                logger.info("auto-remediation skipped: %s", exc)

    # VERIFY + LEARN.
    await _verify_incidents(pol, now)
    await _escalate_stale(now)
    await telemetry.prune_old_samples()


async def _loop() -> None:
    while True:
        try:
            await run_cycle()
        except Exception:
            logger.exception("engine cycle failed — retrying next tick")
        await asyncio.sleep(TICK_SECONDS)


def start() -> asyncio.Task:
    return asyncio.create_task(_loop(), name="astraops-engine-loop")


async def stop(task: asyncio.Task) -> None:
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
