"""Idempotent seed: fleet registry + 10 minutes of baseline telemetry + policy defaults.

Run: cd /app/backend && python seed.py
Not imported by server.py. Gets env + client via lib.db (self-loads .env).
"""

import asyncio
from datetime import datetime, timedelta, timezone

from lib import policy as policy_lib
from lib.db import client, db, ensure_indexes
from lib.telemetry import DEFAULT_SERVICES, build_sample

BACKFILL_TICKS = 120  # 10 minutes at 5-second spacing


async def main() -> None:
    now = datetime.now(timezone.utc)

    # Fresh start: drop app collections (drops indexes too — ensure_indexes runs at the end).
    for name in ("telemetry_samples", "anomalies", "incidents", "recommendations",
                 "verifications", "outcomes", "audit_events", "services", "settings"):
        await db[name].drop_collection()

    await db.services.insert_many([dict(s) for s in DEFAULT_SERVICES])

    # Baseline history so the ensemble, the charts and the forecaster have data on first paint.
    for svc in DEFAULT_SERVICES:
        samples = [
            build_sample(svc, [], now - timedelta(seconds=5 * (BACKFILL_TICKS - i)))
            for i in range(BACKFILL_TICKS)
        ]
        await db.telemetry_samples.insert_many(samples, ordered=False)

    await db.settings.update_one(
        {"key": "policy"},
        {"$set": {"key": "policy", **policy_lib.DEFAULT_POLICY}},
        upsert=True,
    )
    await db.settings.update_one(
        {"key": "engine_heartbeat"},
        {"$set": {"key": "engine_heartbeat", "ts": now}},
        upsert=True,
    )
    await db.audit_events.insert_one({
        "id": "seed-event",
        "ts": now,
        "stage": "OBSERVE",
        "actor": "system",
        "message": "Fleet seeded: 6 services, 10 minutes of baseline telemetry. Simulation ground truth is labeled end to end.",
        "ref_type": None,
        "ref_id": None,
    })

    await ensure_indexes()
    print(f"Seeded {len(DEFAULT_SERVICES)} services x {BACKFILL_TICKS} baseline samples.")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
