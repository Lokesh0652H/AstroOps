"""DECIDE / ACT / VERIFY / LEARN — policy-gated recommendations, remediation, recovery
verification, and outcome recording.

Bounded-automation rules this module enforces:
  - Actions are chosen from a fixed catalog, never free-form commands.
  - scale_up is capped by the service's max_replicas; restart-style actions always
    require explicit human approval.
  - Executing an action sets a per-service cooldown before further recommendations.
  - A successful action execution is NOT treated as recovery — recovery is only
    declared after fresh telemetry confirms the metrics returned to baseline.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from lib.db import db
from lib.telemetry import KIND_LABELS, aware

logger = logging.getLogger(__name__)

SCALE_STEP = 2
DEFAULT_POLICY = {
    "auto_remediate": False,
    "cooldown_seconds": 60,
    "verify_delay_seconds": 15,
    "verify_timeout_seconds": 240,
}


class PolicyError(Exception):
    """Raised when a requested action violates policy — routers map it to 409."""


ACTION_CATALOG: dict[str, dict[str, Any]] = {
    "pod_oom": {
        "action_type": "drain_restart",
        "title": "Drain & restart affected pods",
        "description": "Rolling restart of the degraded service's pods to clear leaked memory.",
        "requires_approval": True,
        "auto_eligible": False,
        "risk_of_action": "medium",
        "impact": "Brief rolling restart; reduced capacity for ~30s during the rollout.",
    },
    "db_conn_leak": {
        "action_type": "scale_up",
        "title": "Scale out +2 replicas (bounded)",
        "description": "Add replicas within the approved ceiling to absorb connection pressure.",
        "requires_approval": False,
        "auto_eligible": True,
        "risk_of_action": "low",
        "impact": "Capacity increase bounded by max_replicas; no data-plane change.",
    },
    "latency_spike": {
        "action_type": "invalidate_cache",
        "title": "Invalidate stale cache layer",
        "description": "Purge the suspected stale cache entries so latency can return to baseline.",
        "requires_approval": False,
        "auto_eligible": True,
        "risk_of_action": "low",
        "impact": "Transient cache-miss increase while the cache re-warms.",
    },
    "traffic_surge": {
        "action_type": "scale_up",
        "title": "Scale out +2 replicas (bounded)",
        "description": "Add replicas within the approved ceiling to absorb the load increase.",
        "requires_approval": False,
        "auto_eligible": True,
        "risk_of_action": "low",
        "impact": "Capacity increase bounded by max_replicas; no data-plane change.",
    },
}
NOTIFY_ACTION: dict[str, Any] = {
    "action_type": "notify_operator",
    "title": "Notify on-call operator",
    "description": "Elevated but unconfirmed risk — notify the on-call operator for review.",
    "requires_approval": False,
    "auto_eligible": False,
    "risk_of_action": "low",
    "impact": "No infrastructure change; notification only.",
}


async def get_policy() -> dict[str, Any]:
    doc = await db.settings.find_one({"key": "policy"})
    if not doc:
        return dict(DEFAULT_POLICY)
    return {**DEFAULT_POLICY, **{k: v for k, v in doc.items() if k in DEFAULT_POLICY}}


async def save_policy(patch: dict[str, Any]) -> dict[str, Any]:
    clean = {k: v for k, v in patch.items() if k in DEFAULT_POLICY}
    await db.settings.update_one({"key": "policy"}, {"$set": {"key": "policy", **clean}}, upsert=True)
    return await get_policy()


async def audit(stage: str, message: str, actor: str = "system", ref_type: str | None = None, ref_id: str | None = None) -> None:
    await db.audit_events.insert_one({
        "id": str(uuid.uuid4()),
        "ts": datetime.now(timezone.utc),
        "stage": stage,
        "actor": actor,
        "message": message,
        "ref_type": ref_type,
        "ref_id": ref_id,
    })


async def decide(
    service: dict[str, Any],
    detection: dict[str, Any],
    incident: dict[str, Any] | None,
    now: datetime,
    pol: dict[str, Any],
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Map a detection (+ incident context) to a recommendation, or None. DECIDE stage."""
    service_id = service["id"]

    # One live recommendation per service; cooldown after the last executed action.
    if await db.recommendations.find_one({"service_id": service_id, "status": {"$in": ["open", "approved"]}}):
        return None
    last_executed = await db.recommendations.find_one(
        {"service_id": service_id, "status": "executed"},
        sort=[("executed_at", -1)],
    )
    if last_executed and last_executed.get("executed_at"):
        cooldown_end = aware(last_executed["executed_at"]) + timedelta(seconds=pol["cooldown_seconds"])
        if now < cooldown_end:
            return None

    if incident and not incident.get("remediated_at") and detection["risk_level"] in ("HIGH", "CRITICAL"):
        spec = dict(ACTION_CATALOG[incident["kind"]])
    elif detection["risk_level"] == "MEDIUM":
        spec = dict(NOTIFY_ACTION)
    else:
        return None

    rec = {
        "id": str(uuid.uuid4()),
        "service_id": service_id,
        "service_name": service["name"],
        "incident_id": incident["id"] if incident else None,
        "action_type": spec["action_type"],
        "title": spec["title"],
        "description": spec["description"],
        "impact": spec["impact"],
        "confidence": detection["risk_score"] / 100.0,
        "risk_of_action": spec["risk_of_action"],
        "requires_approval": spec["requires_approval"],
        "auto_eligible": spec["auto_eligible"],
        "status": "open",
        "reasons": detection["reasons"],
        "evidence": {k: evidence[k] for k in ("ts", "cpu", "memory", "latency_p99", "error_rate")} if evidence else None,
        "created_at": now,
        "executed_at": None,
        "executed_by": None,
    }
    await db.recommendations.insert_one(rec)
    await audit(
        "DECIDE",
        f"Recommendation for {service['name']}: {spec['title']} "
        f"(risk {detection['risk_level']}, action risk {spec['risk_of_action']}, "
        f"approval {'required' if spec['requires_approval'] else 'not required'})",
        ref_type="recommendation",
        ref_id=rec["id"],
    )
    return rec


async def execute_recommendation(rec: dict[str, Any], policy_doc: dict[str, Any], actor: str) -> dict[str, Any]:
    """ACT stage — apply the bounded effect and mark the incident MITIGATING."""
    service = await db.services.find_one({"id": rec["service_id"]})
    if not service:
        raise PolicyError("service no longer exists")
    if rec["status"] not in ("open", "approved"):
        raise PolicyError(f"recommendation already {rec['status']}")
    if rec["requires_approval"] and rec["status"] != "approved":
        raise PolicyError("this action requires explicit approval before execution")

    now = datetime.now(timezone.utc)
    message = f"Executed {rec['action_type']} on {rec['service_name']}"

    if rec["action_type"] == "scale_up":
        new_replicas = min(service["replicas"] + SCALE_STEP, service["max_replicas"])
        if new_replicas == service["replicas"]:
            raise PolicyError(f"scale_up rejected: already at max_replicas ({service['max_replicas']})")
        await db.services.update_one({"id": service["id"]}, {"$set": {"replicas": new_replicas}})
        message += f", replicas {service['replicas']} -> {new_replicas} (bounded by max {service['max_replicas']})"

    await db.recommendations.update_one(
        {"id": rec["id"]},
        {"$set": {"status": "executed", "executed_at": now, "executed_by": actor}},
    )
    if rec.get("incident_id"):
        await db.incidents.update_one(
            {"id": rec["incident_id"], "status": {"$in": ["DETECTED", "MITIGATING"]}},
            {"$set": {"status": "MITIGATING", "remediated_at": now}},
        )
        message += "; recovery verification scheduled"

    await audit("ACT", message, actor=actor, ref_type="recommendation", ref_id=rec["id"])
    return {"executed_at": now, "message": message}


def check_recovery(incident: dict[str, Any], current: dict[str, Any], pol: dict[str, Any], now: datetime) -> str | None:
    """VERIFY stage — verdict from FRESH telemetry, never from execution success alone."""
    if not incident.get("remediated_at"):
        return None
    mitigated_at = aware(incident["remediated_at"])
    if (now - mitigated_at).total_seconds() < pol["verify_delay_seconds"]:
        return None

    baseline = incident.get("baseline") or {}
    recovered = (
        current["error_rate"] <= baseline.get("error_rate", 0.0) + 1.0
        and current["latency_p99"] <= baseline.get("latency_p99", 0.0) * 1.3 + 30.0
        and current["cpu"] <= baseline.get("cpu", 0.0) + 25.0
        and current["memory"] <= baseline.get("memory", 0.0) + 20.0
    )
    if recovered:
        return "RECOVERED"
    if (now - mitigated_at).total_seconds() > pol["verify_timeout_seconds"]:
        return "FAILED"
    return "NOT_YET"


async def record_outcome(incident: dict[str, Any], verdict: str) -> None:
    """LEARN stage — persist the labeled outcome (ground truth is known: the fleet is simulated)."""
    await db.outcomes.insert_one({
        "id": str(uuid.uuid4()),
        "incident_id": incident["id"],
        "kind": incident["kind"],
        "verdict": verdict,
        "ground_truth": "injected_degradation",
        "peak_risk": incident.get("peak_risk", 0.0),
        "ts": datetime.now(timezone.utc),
    })
    await audit(
        "LEARN",
        f"Outcome recorded for {incident['service_name']} {KIND_LABELS.get(incident['kind'], incident['kind'])}: "
        f"{verdict} (ground truth: degradation was injected by simulation)",
        ref_type="incident",
        ref_id=incident["id"],
    )
