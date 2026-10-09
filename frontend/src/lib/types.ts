// Hand-written mirrors of the backend Pydantic models (backend/models/*) — nothing infers
// across the HTTP boundary, so each interface here must be kept in sync in the same edit.

// --- backend/models/fleet.py ---

export interface MetricPoint {
  ts: string;
  cpu: number;
  memory: number;
  latency_p99: number;
  error_rate: number;
}

export type RiskLevel = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";

export type ServiceStatus = "healthy" | "elevated" | "degraded" | "critical" | "incident";

export interface ServiceRuntime {
  id: string;
  name: string;
  kind: string;
  region: string;
  replicas: number;
  min_replicas: number;
  max_replicas: number;
  status: ServiceStatus;
  risk_score: number;
  risk_level: RiskLevel;
  metrics: MetricPoint;
}

export interface FleetOverview {
  simulation: { label: string; note: string };
  fleet_risk_score: number;
  fleet_risk_level: RiskLevel;
  services: ServiceRuntime[];
  engine_alive: boolean;
  updated_at: string;
}

export interface MetricHistoryOut {
  service_id: string;
  service_name: string;
  points: MetricPoint[];
}

export type IncidentKind = "pod_oom" | "db_conn_leak" | "latency_spike" | "traffic_surge";

export interface IncidentOut {
  id: string;
  service_id: string;
  service_name: string;
  kind: string;
  kind_label: string;
  status: string;
  peak_risk: number;
  created_at: string;
  remediated_at: string | null;
  resolved_at: string | null;
  baseline: MetricPoint | null;
}

// --- backend/models/intelligence.py ---

export interface AnomalyOut {
  id: string;
  service_id: string;
  service_name: string;
  detected_at: string;
  risk_score: number;
  risk_level: RiskLevel;
  score_z: number;
  score_forest: number;
  score_spike: number;
  reasons: string[];
  evidence: MetricPoint | null;
}

export type RecommendationStatus = "open" | "approved" | "executed" | "dismissed";

export interface RecommendationOut {
  id: string;
  service_id: string;
  service_name: string;
  incident_id: string | null;
  action_type: string;
  title: string;
  description: string;
  impact: string;
  confidence: number;
  risk_of_action: string;
  requires_approval: boolean;
  auto_eligible: boolean;
  status: RecommendationStatus;
  reasons: string[];
  evidence: MetricPoint | null;
  created_at: string;
  executed_at: string | null;
  executed_by: string | null;
}

export type VerificationVerdict = "RECOVERED" | "NOT_YET" | "FAILED";

export interface VerificationOut {
  id: string;
  incident_id: string;
  service_id: string;
  service_name: string;
  verdict: VerificationVerdict;
  checked_at: string;
  before: MetricPoint | null;
  after: MetricPoint | null;
}

export type WorkflowStage = "OBSERVE" | "DETECT" | "PREDICT" | "DECIDE" | "ACT" | "VERIFY" | "LEARN";

export interface AuditEventOut {
  id: string;
  ts: string;
  stage: WorkflowStage;
  actor: string;
  message: string;
  ref_type: string | null;
  ref_id: string | null;
}

export interface PolicyState {
  auto_remediate: boolean;
  cooldown_seconds: number;
  verify_delay_seconds: number;
  verify_timeout_seconds: number;
}

export interface ForecastStep {
  t: string;
  value: number;
  upper: number;
  lower: number;
}

export interface ForecastResponse {
  service_id: string;
  service_name: string;
  metric: string;
  trend: string;
  trained_on: number;
  steps: ForecastStep[];
  history: MetricPoint[];
}

export interface ModelStatusOut {
  services_tracked: number;
  forest_trained: boolean;
  forest_min_points: number;
  retrain_every: number;
  total_evaluations: number;
  samples_stored: number;
  anomalies_total: number;
  note: string;
}

// --- backend/routers/export.py ---

export interface ExportScope {
  scope: string;
  label: string;
  available: boolean;
  filename: string;
}

export interface ExportScopesResponse {
  scopes: ExportScope[];
  policy: {
    excluded_directories: string[];
    excluded_file_names: string[];
    excluded_file_suffixes: string[];
    env_handling: string;
    max_file_bytes: number;
    max_total_bytes: number;
  };
}

export const WORKFLOW_STAGES: WorkflowStage[] = [
  "OBSERVE",
  "DETECT",
  "PREDICT",
  "DECIDE",
  "ACT",
  "VERIFY",
  "LEARN",
];
