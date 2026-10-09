"""Shared Mongo handle — import `client`/`db` from here (server.py, routers, seed.py)."""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING, DESCENDING, IndexModel

load_dotenv(Path(__file__).parent.parent / ".env")

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

logger = logging.getLogger(__name__)

# One entry per collection: every field a route filters, sorts, or dedupes on. Applied by ensure_indexes() at startup.
INDEXES: dict[str, list[IndexModel]] = {
    "status_checks": [IndexModel([("timestamp", DESCENDING)], name="timestamp_desc")],
    "services": [IndexModel([("id", ASCENDING)], name="id_unique", unique=True)],
    "telemetry_samples": [IndexModel([("service_id", ASCENDING), ("ts", DESCENDING)], name="service_ts")],
    "anomalies": [IndexModel([("service_id", ASCENDING), ("detected_at", DESCENDING)], name="service_detected")],
    "incidents": [IndexModel([("status", ASCENDING), ("created_at", DESCENDING)], name="status_created")],
    "recommendations": [IndexModel([("service_id", ASCENDING), ("status", ASCENDING), ("created_at", DESCENDING)], name="svc_status_created")],
    "verifications": [IndexModel([("checked_at", DESCENDING)], name="checked_desc")],
    "outcomes": [IndexModel([("ts", DESCENDING)], name="ts_desc")],
    "audit_events": [IndexModel([("ts", DESCENDING)], name="ts_desc")],
    "settings": [IndexModel([("key", ASCENDING)], name="key_unique", unique=True)],
}


async def ensure_indexes() -> None:
    for collection, models in INDEXES.items():
        for model in models:  # one at a time so a bad spec skips only itself
            try:
                await db[collection].create_indexes([model])
            except Exception as exc:  # never block boot on an index; the log line names what to fix
                logger.error("ensure_indexes(%s.%s): %s", collection, model.document["name"], exc)
