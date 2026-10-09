"""AIOps loop tests — fleet overview, forecast, policy-gated remediation, recovery
verification, audit trail. The full-loop test drives a real injection end to end."""

import time
from datetime import datetime, timedelta, timezone


def test_overview_shape(client):
    resp = client.get("/fleet/overview")
    assert resp.status_code == 200
    body = resp.json()
    assert body["simulation"]["label"] == "SIMULATED FLEET"
    assert len(body["services"]) >= 6
    svc = body["services"][0]
    assert {"id", "name", "risk_score", "risk_level", "metrics"} <= set(svc)
    assert 0 <= svc["risk_score"] <= 100
    assert "T" in svc["metrics"]["ts"]  # ISO timestamp, parseable by JS


def test_metrics_history(client):
    resp = client.get("/fleet/services/order-api/metrics", params={"points": 30})
    assert resp.status_code == 200
    points = resp.json()["points"]
    assert len(points) >= 10
    assert {"ts", "cpu", "memory", "latency_p99", "error_rate"} <= set(points[0])


def test_inject_unknown_service_404(client):
    resp = client.post("/fleet/incidents/inject", json={"service_id": "nope", "kind": "pod_oom"})
    assert resp.status_code == 404


def test_inject_unknown_kind_422(client):
    resp = client.post("/fleet/incidents/inject", json={"service_id": "order-api", "kind": "flux_overload"})
    assert resp.status_code == 422


def test_inject_twice_conflicts_409(client):
    client.post("/fleet/reset")
    first = client.post("/fleet/incidents/inject", json={"service_id": "vector-index", "kind": "latency_spike"})
    assert first.status_code == 200
    second = client.post("/fleet/incidents/inject", json={"service_id": "vector-index", "kind": "pod_oom"})
    assert second.status_code == 409
    client.post("/fleet/reset")


def test_forecast_steps(client):
    resp = client.get("/intelligence/forecast/order-api", params={"metric": "cpu"})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["steps"]) == 5
    for step in body["steps"]:
        assert step["upper"] >= step["value"] >= step["lower"]


def test_check_recovery_unit():
    from lib.policy import check_recovery

    pol = {"verify_delay_seconds": 15, "verify_timeout_seconds": 240}
    baseline = {"cpu": 45.0, "memory": 55.0, "latency_p99": 120.0, "error_rate": 0.8}
    now = datetime.now(timezone.utc)
    healthy = {"ts": now, "cpu": 46.0, "memory": 56.0, "latency_p99": 125.0, "error_rate": 0.9}
    degraded = {"ts": now, "cpu": 95.0, "memory": 90.0, "latency_p99": 400.0, "error_rate": 5.0}

    inc = {"remediated_at": now - timedelta(seconds=60), "baseline": baseline}
    assert check_recovery(inc, healthy, pol, now) == "RECOVERED"
    assert check_recovery(inc, degraded, pol, now) == "NOT_YET"

    stale = {"remediated_at": now - timedelta(seconds=300), "baseline": baseline}
    assert check_recovery(stale, degraded, pol, now) == "FAILED"

    fresh = {"remediated_at": now, "baseline": baseline}
    assert check_recovery(fresh, degraded, pol, now) is None  # inside verify delay


def test_full_loop_inject_detect_execute_verify(client):
    """OBSERVE -> DETECT -> DECIDE -> ACT -> VERIFY -> LEARN against the live engine."""
    assert client.post("/fleet/reset").status_code == 200

    resp = client.post("/fleet/incidents/inject", json={"service_id": "order-api", "kind": "traffic_surge"})
    assert resp.status_code == 200

    rec = None
    for _ in range(30):  # up to ~2.5 min: ramp (20s) + detection + engine cycle (5s)
        recs = client.get("/intelligence/recommendations").json()
        matching = [r for r in recs if r["service_id"] == "order-api" and r["status"] in ("open", "approved")]
        if matching:
            rec = matching[0]
            break
        time.sleep(5)
    assert rec is not None, "engine never opened a recommendation after injection"
    assert rec["action_type"] == "scale_up"
    assert rec["requires_approval"] is False  # bounded scale-up is policy-approved

    resp = client.post(f"/intelligence/recommendations/{rec['id']}/execute")
    assert resp.status_code == 200

    verdicts: list[str] = []
    for _ in range(24):  # up to ~2 min: verify delay (15s) + decay (25s) + cycle (5s)
        verifs = client.get("/intelligence/verifications").json()
        verdicts = [v["verdict"] for v in verifs if v["incident_id"] == rec["incident_id"]]
        if "RECOVERED" in verdicts or "FAILED" in verdicts:
            break
        time.sleep(5)
    assert "RECOVERED" in verdicts, f"recovery never verified, saw {verdicts}"

    audit = client.get("/intelligence/audit").json()
    stages = {e["stage"] for e in audit}
    assert {"OBSERVE", "DETECT", "DECIDE", "ACT", "VERIFY", "LEARN"} <= stages


def test_model_status(client):
    resp = client.get("/intelligence/model-status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["samples_stored"] > 100
    assert "simulation" in body["note"].lower()
