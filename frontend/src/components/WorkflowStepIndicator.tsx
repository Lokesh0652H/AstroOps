import { ChevronRight } from "lucide-react";
import { STAGE_COLORS } from "@/lib/levels";
import { WORKFLOW_STAGES } from "@/lib/types";
import type {
  AnomalyOut,
  AuditEventOut,
  FleetOverview,
  IncidentOut,
  RecommendationOut,
  VerificationOut,
  WorkflowStage,
} from "@/lib/types";
import { cn } from "@/lib/utils";

interface WorkflowStepIndicatorProps {
  overview: FleetOverview | undefined;
  anomalies: AnomalyOut[];
  recommendations: RecommendationOut[];
  verifications: VerificationOut[];
  incidents: IncidentOut[];
  auditEvents: AuditEventOut[];
}

// Stage activity is derived from persisted pipeline records, not a timer.
function stageActivity(
  overview: FleetOverview | undefined,
  anomalies: AnomalyOut[],
  recommendations: RecommendationOut[],
  verifications: VerificationOut[],
  incidents: IncidentOut[],
  auditEvents: AuditEventOut[],
): Record<WorkflowStage, { active: boolean; count?: number }> {
  return {
    OBSERVE: { active: !!overview?.engine_alive },
    DETECT: { active: anomalies.length > 0, count: anomalies.length },
    PREDICT: { active: (overview?.services.length ?? 0) > 0 },
    DECIDE: {
      active: recommendations.some((r) => r.status === "open" || r.status === "approved"),
      count: recommendations.filter((r) => r.status === "open" || r.status === "approved").length,
    },
    ACT: { active: recommendations.some((r) => r.status === "approved" || r.status === "executed") },
    VERIFY: {
      active: incidents.some((i) => i.status === "MITIGATING") || verifications.length > 0,
      count: verifications.length,
    },
    LEARN: {
      active: auditEvents.some((event) => event.stage === "LEARN"),
      count: auditEvents.filter((event) => event.stage === "LEARN").length,
    },
  };
}

export default function WorkflowStepIndicator({
  overview,
  anomalies,
  recommendations,
  verifications,
  incidents,
  auditEvents,
}: WorkflowStepIndicatorProps) {
  const activity = stageActivity(overview, anomalies, recommendations, verifications, incidents, auditEvents);

  return (
    <div
      data-testid="workflow-pipeline"
      className="flex flex-wrap items-center gap-x-1 gap-y-2 rounded-lg border border-[#1A263D] bg-[#0A101E] px-4 py-3"
    >
      {WORKFLOW_STAGES.map((stage, i) => {
        const { active, count } = activity[stage];
        return (
          <div key={stage} className="flex items-center gap-1">
            {i > 0 && <ChevronRight className="h-3.5 w-3.5 text-[#33405C]" aria-hidden="true" />}
            <div
              data-testid={`workflow-stage-${stage.toLowerCase()}`}
              className={cn(
                "flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-[11px] font-medium uppercase tracking-[0.12em] transition-colors duration-150",
                active ? "border-[#223559] bg-[#121C33]" : "border-transparent text-muted-foreground/60",
              )}
            >
              <span
                aria-hidden="true"
                className="h-1.5 w-1.5 rounded-full transition-opacity duration-150"
                style={{
                  backgroundColor: STAGE_COLORS[stage],
                  opacity: active ? 1 : 0.25,
                  boxShadow: active ? `0 0 8px ${STAGE_COLORS[stage]}` : "none",
                }}
              />
              <span style={{ color: active ? STAGE_COLORS[stage] : undefined }}>{stage}</span>
              {count !== undefined && count > 0 && (
                <span className="font-mono text-[10px] text-muted-foreground" aria-live="polite">
                  {count}
                </span>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
