from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from lib import policy


@pytest.mark.asyncio
async def test_high_risk_incident_supersedes_open_notification(monkeypatch):
    notification = {
        "id": "notification-1",
        "service_id": "auth-gateway",
        "action_type": "notify_operator",
        "status": "open",
    }
    recommendations = SimpleNamespace(
        find_one=AsyncMock(side_effect=[notification, None]),
        update_one=AsyncMock(),
        insert_one=AsyncMock(),
    )
    audit_events = SimpleNamespace(insert_one=AsyncMock())
    monkeypatch.setattr(
        policy,
        "db",
        SimpleNamespace(recommendations=recommendations, audit_events=audit_events),
    )

    rec = await policy.decide(
        service={"id": "auth-gateway", "name": "Auth Gateway"},
        detection={"risk_level": "HIGH", "risk_score": 60.0, "reasons": ["memory high"]},
        incident={
            "id": "incident-1",
            "service_id": "auth-gateway",
            "kind": "pod_oom",
            "remediated_at": None,
        },
        now=datetime.now(timezone.utc),
        pol={"cooldown_seconds": 60},
    )

    assert rec is not None
    assert rec["action_type"] == "drain_restart"
    assert rec["requires_approval"] is True
    assert rec["incident_id"] == "incident-1"
    recommendations.update_one.assert_awaited_once_with(
        {"id": "notification-1"},
        {"$set": {"status": "dismissed"}},
    )
    recommendations.insert_one.assert_awaited_once_with(rec)
    assert audit_events.insert_one.await_count == 2
