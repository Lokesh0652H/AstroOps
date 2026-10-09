# AstraOps AI — Architecture

Intelligent cloud operations platform implementing the full AIOps loop:

```
OBSERVE -> DETECT -> PREDICT -> DECIDE -> ACT -> VERIFY -> LEARN
```

> **Implementation truth:** the telemetry source is a deterministic in-process fleet
> simulator (6 services), labeled `SIMULATED FLEET` on every surface. Detection, risk
> scoring, forecasting, policy enforcement, remediation, verification, and audit are
> real code paths running against that simulator. No production cloud is connected.

## Modules

| Layer | Path | Responsibility |
|---|---|---|
| OBSERVE | `backend/lib/telemetry.py` | Deterministic fleet simulator (per-service baselines + load wave + seeded noise + incident ramps/decays), 5s tick, sample persistence + retention |
| DETECT | `backend/lib/detection.py` | 3-model ensemble: adaptive Z-score, Isolation Forest (scikit-learn), rate-of-change spike detector; weighted composite risk 0-100 |
| PREDICT | `backend/lib/forecaster.py` | Holt double-exponential smoothing, 5-step forecast, widening confidence bands, trend classification |
| DECIDE | `backend/lib/policy.py` | Fixed action catalog, approval requirements, per-service cooldowns, bounded scale-up (max_replicas cap) |
| ACT | `backend/lib/policy.py` | Executed effects (scale_up / drain_restart / invalidate_cache / notify_operator); auto-remediation only for auto-eligible low-risk actions when the operator enables it |
| VERIFY | `backend/lib/policy.py` + `engine.py` | Recovery verdict from FRESH telemetry (RECOVERED / NOT_YET / FAILED); execution success is never treated as recovery |
| LEARN | `backend/lib/policy.py` + `engine.py` | Labeled outcomes (ground truth known: degradations are injected), full audit trail |
| Engine loop | `backend/lib/engine.py` | One cycle per tick; every stage transition lands in `audit_events` |
| Fleet API | `backend/routers/fleet.py` | Overview, history, incident injection (simulation controls), reset |
| Intelligence API | `backend/routers/intelligence.py` | Anomalies, forecast, recommendations + approve/execute/dismiss, verifications, audit, policy, model status |
| Export | `backend/routers/export.py` | `GET /api/export/source?scope=astraops|weltrix` — sanitized source ZIP (see `docs/SETUP.md`) |

## Data model (MongoDB, database `app`)

- `services` — fleet registry with per-service metric baselines and replica bounds
- `telemetry_samples` — one row per service per 5s tick (45-minute retention)
- `anomalies` — HIGH/CRITICAL ensemble detections with evidence snapshots
- `incidents` — injected degradation lifecycle: `DETECTED -> MITIGATING -> RECOVERED | FAILED | ESCALATED | RESOLVED`
- `recommendations` — policy decisions: `open -> approved -> executed` (or `dismissed`)
- `verifications` — per-check recovery verdicts with before/after evidence
- `outcomes` — LEARN records labeled with simulation ground truth
- `audit_events` — append-only trail across all seven stages
- `settings` — policy document (`auto_remediate`, cooldowns, verify windows) + engine heartbeat

## Honesty rules baked into the product

- Every page carries the `SIMULATED FLEET` badge; no chart claims live production data.
- Anomaly reasons are measured evidence strings (z-score breach, spike delta, forest score).
- The forecast is labeled a statistical extrapolation, not a calibrated probability.
- Approval is required for restart-class actions; `auto_remediate` defaults OFF.
- A recommendation executed message never claims recovery — only `VERIFY` does.
