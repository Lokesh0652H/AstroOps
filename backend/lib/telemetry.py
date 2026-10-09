"""OBSERVE — simulated fleet telemetry.

The fleet is a deterministic simulator, not live infrastructure: every metric is a pure
function of (service profile, timestamp, active incidents), so the same tick always
produces the same sample. The engine cycle samples every service every TICK_SECONDS and
persists samples to Mongo. Every surface in the app labels this data SIMULATED — no
chart on the dashboard pretends to be a production cluster.
"""

import hashlib
import math
import random
from datetime import datetime, timedelta, timezone
from typing import Any

from lib.db import db

TICK_SECONDS = 5
RAMP_SECONDS = 20.0      # an injected incident ramps 0 -> 1 over this window
DECAY_SECONDS = 25.0     # after remediation the degradation decays to 0 over this window
ESCALATE_AFTER = 600.0   # an unremediated incident escalates after this long
RETENTION = timedelta(minutes=45)

METRICS = ("cpu", "memory", "latency_p99", "error_rate")

# Absolute metric bumps at full incident strength, chosen per failure mode.
KIND_BUMPS: dict[str, dict[str, float]] = {
    "pod_oom": {"cpu": 30.0, "memory": 38.0, "latency_p99": 95.0, "error_rate": 2.2},
    "db_conn_leak": {"cpu": 18.0, "memory": 12.0, "latency_p99": 140.0, "error_rate": 4.5},
    "latency_spike": {"cpu": 14.0, "memory": 6.0, "latency_p99": 180.0, "error_rate": 1.2},
    "traffic_surge": {"cpu": 34.0, "memory": 16.0, "latency_p99": 70.0, "error_rate": 0.9},
}
KIND_LABELS: dict[str, str] = {
    "pod_oom": "Pod OOM (memory exhaustion)",
    "db_conn_leak": "DB connection leak",
    "latency_spike": "API latency spike",
    "traffic_surge": "Traffic surge",
}

DEFAULT_SERVICES: list[dict[str, Any]] = [
    {"id": "auth-gateway", "name": "Auth Gateway", "kind": "API Gateway", "region": "us-east-1",
     "replicas": 3, "min_replicas": 2, "max_replicas": 10,
     "base_cpu": 32, "base_memory": 48, "base_latency": 85, "base_error": 0.4,
     "amp_cpu": 4, "amp_memory": 3, "amp_latency": 10, "amp_error": 0.12},
    {"id": "order-api", "name": "Order API", "kind": "Core API", "region": "us-east-1",
     "replicas": 4, "min_replicas": 2, "max_replicas": 12,
     "base_cpu": 45, "base_memory": 55, "base_latency": 120, "base_error": 0.8,
     "amp_cpu": 5, "amp_memory": 4, "amp_latency": 14, "amp_error": 0.18},
    {"id": "payment-processor", "name": "Payment Processor", "kind": "Payments", "region": "eu-west-1",
     "replicas": 3, "min_replicas": 2, "max_replicas": 10,
     "base_cpu": 38, "base_memory": 52, "base_latency": 210, "base_error": 0.3,
     "amp_cpu": 4, "amp_memory": 3, "amp_latency": 18, "amp_error": 0.1},
    {"id": "inventory-db", "name": "Inventory DB", "kind": "Database", "region": "us-east-1",
     "replicas": 2, "min_replicas": 1, "max_replicas": 8,
     "base_cpu": 51, "base_memory": 68, "base_latency": 45, "base_error": 0.2,
     "amp_cpu": 5, "amp_memory": 4, "amp_latency": 8, "amp_error": 0.08},
    {"id": "notification-worker", "name": "Notification Worker", "kind": "Async Worker", "region": "ap-south-1",
     "replicas": 2, "min_replicas": 1, "max_replicas": 6,
     "base_cpu": 22, "base_memory": 35, "base_latency": 30, "base_error": 1.1,
     "amp_cpu": 3, "amp_memory": 2, "amp_latency": 6, "amp_error": 0.2},
    {"id": "vector-index", "name": "Vector Index", "kind": "Search / AI", "region": "us-west-2",
     "replicas": 4, "min_replicas": 2, "max_replicas": 12,
     "base_cpu": 58, "base_memory": 72, "base_latency": 160, "base_error": 0.6,
     "amp_cpu": 5, "amp_memory": 4, "amp_latency": 16, "amp_error": 0.14},
]


def aware(dt: datetime) -> datetime:
    """Motor hands naive UTC datetimes back; normalise so JS Date() parses them."""
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def metric_point(doc: dict[str, Any]) -> dict[str, Any]:
    """Normalized metric dict from a stored sample (aware UTC timestamp)."""
    return {
        "ts": aware(doc["ts"]),
        "cpu": doc["cpu"],
        "memory": doc["memory"],
        "latency_p99": doc["latency_p99"],
        "error_rate": doc["error_rate"],
    }


def _noise(seed: str) -> float:
    """Deterministic pseudo-random in [-1, 1] seeded by (service, tick) — reproducible samples."""
    digest = hashlib.md5(seed.encode()).hexdigest()
    return random.Random(digest).uniform(-1.0, 1.0)


def incident_multiplier(incident: dict[str, Any], now: datetime) -> float:
    """0..1 strength of an incident's degradation at time `now` (ramp up, decay after fix)."""
    created = aware(incident["created_at"])
    if incident.get("remediated_at"):
        elapsed = (now - aware(incident["remediated_at"])).total_seconds()
        return max(0.0, 1.0 - elapsed / DECAY_SECONDS)
    elapsed = (now - created).total_seconds()
    return min(1.0, elapsed / RAMP_SECONDS)


def build_sample(service: dict[str, Any], incidents: list[dict[str, Any]], t: datetime) -> dict[str, Any]:
    """One telemetry sample for one service at time `t` — pure function, no side effects."""
    bucket = int(t.timestamp() // TICK_SECONDS)
    bump = {"cpu": 0.0, "memory": 0.0, "latency_p99": 0.0, "error_rate": 0.0}
    for inc in incidents:
        strength = incident_multiplier(inc, t)
        if strength <= 0:
            continue
        for metric, amount in KIND_BUMPS.get(inc["kind"], {}).items():
            bump[metric] += amount * strength

    wave = math.sin(2 * math.pi * (t.timestamp() % 900) / 900.0)  # 15-minute load wave
    cpu = service["base_cpu"] + service["amp_cpu"] * wave + 2.5 * _noise(f"{service['id']}:cpu:{bucket}") + bump["cpu"]
    memory = service["base_memory"] + service["amp_memory"] * wave + 2.0 * _noise(f"{service['id']}:mem:{bucket}") + bump["memory"]
    latency = service["base_latency"] + service["amp_latency"] * wave + 4.0 * _noise(f"{service['id']}:lat:{bucket}") + bump["latency_p99"]
    error = max(0.0, service["base_error"] + service["amp_error"] * wave + 0.06 * _noise(f"{service['id']}:err:{bucket}") + bump["error_rate"])

    return {
        "service_id": service["id"],
        "service_name": service["name"],
        "ts": t,
        "cpu": round(min(99.0, max(1.0, cpu)), 1),
        "memory": round(min(99.0, max(1.0, memory)), 1),
        "latency_p99": round(max(5.0, latency), 1),
        "error_rate": round(min(99.0, error), 2),
    }


async def get_services() -> list[dict[str, Any]]:
    services = await db.services.find().sort("id", 1).to_list(100)
    if not services:  # lazy registry bootstrap so a fresh DB still serves the cockpit
        await db.services.insert_many([dict(s) for s in DEFAULT_SERVICES])
        services = await db.services.find().sort("id", 1).to_list(100)
    return services


async def get_active_incidents() -> list[dict[str, Any]]:
    return await db.incidents.find({"status": {"$in": ["DETECTED", "MITIGATING"]}}).to_list(100)


async def record_samples(samples: list[dict[str, Any]]) -> None:
    if samples:
        await db.telemetry_samples.insert_many(samples, ordered=False)


async def prune_old_samples() -> None:
    await db.telemetry_samples.delete_many({"ts": {"$lt": datetime.now(timezone.utc) - RETENTION}})


async def heartbeat() -> None:
    """Engine liveness marker — the dashboard's radar dot reads this, not a client timer."""
    now = datetime.now(timezone.utc)
    await db.settings.update_one({"key": "engine_heartbeat"}, {"$set": {"key": "engine_heartbeat", "ts": now}}, upsert=True)


async def heartbeat_age_seconds() -> float | None:
    doc = await db.settings.find_one({"key": "engine_heartbeat"})
    if not doc or "ts" not in doc:
        return None
    return (datetime.now(timezone.utc) - aware(doc["ts"])).total_seconds()
