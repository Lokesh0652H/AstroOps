import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import AnomalyFeed from "@/components/AnomalyFeed";
import CompositeRiskGauge from "@/components/CompositeRiskGauge";
import FleetHealthSummary from "@/components/FleetHealthSummary";
import ForecastConfidenceView from "@/components/ForecastConfidenceView";
import HeaderBar from "@/components/HeaderBar";
import IncidentAuditTimeline from "@/components/IncidentAuditTimeline";
import RecommendationActuator from "@/components/RecommendationActuator";
import RecoveryVerification from "@/components/RecoveryVerification";
import TelemetryCharts from "@/components/TelemetryCharts";
import WorkflowStepIndicator from "@/components/WorkflowStepIndicator";
import { apiErrorMessage, apiGet, apiPost, apiPut } from "@/lib/api";
import type {
  AnomalyOut,
  AuditEventOut,
  FleetOverview,
  IncidentKind,
  IncidentOut,
  PolicyState,
  RecommendationOut,
  VerificationOut,
} from "@/lib/types";

// The cockpit polls the engine every 5s; a failed poll degrades to the shell + an
// offline chip — the page never blanks (it is also served as a static preview).
export default function Home() {
  const qc = useQueryClient();
  const overviewQ = useQuery({
    queryKey: ["overview"],
    queryFn: () => apiGet<FleetOverview>("/fleet/overview"),
    refetchInterval: 5000,
  });
  const anomaliesQ = useQuery({
    queryKey: ["anomalies"],
    queryFn: () => apiGet<AnomalyOut[]>("/intelligence/anomalies?limit=12"),
    refetchInterval: 5000,
  });
  const recsQ = useQuery({
    queryKey: ["recommendations"],
    queryFn: () => apiGet<RecommendationOut[]>("/intelligence/recommendations"),
    refetchInterval: 5000,
  });
  const verifsQ = useQuery({
    queryKey: ["verifications"],
    queryFn: () => apiGet<VerificationOut[]>("/intelligence/verifications?limit=10"),
    refetchInterval: 5000,
  });
  const auditQ = useQuery({
    queryKey: ["audit"],
    queryFn: () => apiGet<AuditEventOut[]>("/intelligence/audit?limit=40"),
    refetchInterval: 10000,
  });
  const incidentsQ = useQuery({
    queryKey: ["incidents"],
    queryFn: () => apiGet<IncidentOut[]>("/fleet/incidents"),
    refetchInterval: 5000,
  });
  const policyQ = useQuery({
    queryKey: ["policy"],
    queryFn: () => apiGet<PolicyState>("/intelligence/policy"),
    refetchInterval: 30000,
  });

  const offline = overviewQ.isError;

  const [selectedServiceId, setSelectedServiceId] = useState<string | null>(null);
  const serviceId = selectedServiceId ?? overviewQ.data?.services[0]?.id;

  const invalidate = (...keys: string[]) => keys.forEach((k) => qc.invalidateQueries({ queryKey: [k] }));

  const injectMutation = useMutation({
    mutationFn: (req: { service_id: string; kind: IncidentKind }) => apiPost("/fleet/incidents/inject", req),
    onSuccess: () => {
      toast.success("Degradation injected — the engine should detect and recommend within ~40s");
      invalidate("overview", "anomalies", "incidents", "audit", "recommendations");
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  });
  const resetMutation = useMutation({
    mutationFn: () => apiPost<{ ok: boolean; resolved_incidents: number }>("/fleet/reset"),
    onSuccess: (data) => {
      toast.success(`Fleet reset — ${data.resolved_incidents} incident(s) resolved`);
      invalidate("overview", "anomalies", "incidents", "audit", "recommendations", "verifications");
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  });
  const approveMutation = useMutation({
    mutationFn: (id: string) => apiPost(`/intelligence/recommendations/${id}/approve`),
    onSuccess: () => {
      toast.success("Action approved — ready to execute");
      invalidate("recommendations", "audit");
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  });
  const executeMutation = useMutation({
    mutationFn: (id: string) => apiPost<{ ok: boolean; message: string }>(`/intelligence/recommendations/${id}/execute`),
    onSuccess: (data) => {
      toast.success(data.message);
      invalidate("recommendations", "verifications", "incidents", "overview", "audit");
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  });
  const dismissMutation = useMutation({
    mutationFn: (id: string) => apiPost(`/intelligence/recommendations/${id}/dismiss`),
    onSuccess: () => {
      toast("Recommendation dismissed");
      invalidate("recommendations", "audit");
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  });
  const policyMutation = useMutation({
    mutationFn: (value: boolean) => apiPut<PolicyState>("/intelligence/policy", { auto_remediate: value }),
    onSuccess: (policy) => {
      toast.success(policy.auto_remediate ? "Auto-remediation enabled for low-risk bounded actions" : "Auto-remediation disabled — all actions need approval");
      invalidate("policy", "audit");
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  });

  // Busy id derived from in-flight mutations — disables the matching card's buttons.
  const busyId =
    approveMutation.isPending
      ? (approveMutation.variables ?? null)
      : executeMutation.isPending
        ? (executeMutation.variables ?? null)
        : dismissMutation.isPending
          ? (dismissMutation.variables ?? null)
          : null;

  return (
    <div className="min-h-svh">
      <HeaderBar
        overview={overviewQ.data}
        offline={offline}
        injecting={injectMutation.isPending}
        resetting={resetMutation.isPending}
        onInject={(sid, kind) => injectMutation.mutate({ service_id: sid, kind })}
        onReset={() => resetMutation.mutate()}
      />

      <main className="mx-auto max-w-[1600px] space-y-4 px-4 py-5 md:px-6">
        <WorkflowStepIndicator
          overview={overviewQ.data}
          anomalies={anomaliesQ.data ?? []}
          recommendations={recsQ.data ?? []}
          verifications={verifsQ.data ?? []}
          incidents={incidentsQ.data ?? []}
        />

        <div className="grid grid-cols-1 gap-4 md:grid-cols-12 md:gap-5">
          <div className="md:col-span-12 lg:col-span-8">
            <FleetHealthSummary overview={overviewQ.data} anomalies={anomaliesQ.data ?? []} offline={offline} />
          </div>
          <div className="md:col-span-12 lg:col-span-4">
            <CompositeRiskGauge overview={overviewQ.data} />
          </div>
          <div className="md:col-span-12 lg:col-span-8">
            <TelemetryCharts
              serviceId={serviceId}
              services={overviewQ.data?.services ?? []}
              onSelectService={setSelectedServiceId}
            />
          </div>
          <div className="md:col-span-12 lg:col-span-4">
            <ForecastConfidenceView serviceId={serviceId} />
          </div>
          <div className="md:col-span-12 lg:col-span-6">
            <AnomalyFeed anomalies={anomaliesQ.data ?? []} />
          </div>
          <div className="md:col-span-12 lg:col-span-6">
            <RecommendationActuator
              recommendations={recsQ.data ?? []}
              policy={policyQ.data}
              busyId={busyId}
              onApprove={(rec) => approveMutation.mutate(rec.id)}
              onExecute={(rec) => executeMutation.mutate(rec.id)}
              onDismiss={(rec) => dismissMutation.mutate(rec.id)}
              onToggleAutoRemediate={(value) => policyMutation.mutate(value)}
              policyPending={policyMutation.isPending}
            />
          </div>
          <div className="md:col-span-12 lg:col-span-6">
            <RecoveryVerification verifications={verifsQ.data ?? []} />
          </div>
          <div className="md:col-span-12 lg:col-span-6">
            <IncidentAuditTimeline events={auditQ.data ?? []} />
          </div>
        </div>

        <footer className="pb-6 pt-2 text-center text-[11px] text-muted-foreground">
          AstraOps AI · OBSERVE → DETECT → PREDICT → DECIDE → ACT → VERIFY → LEARN · every stage transition is
          recorded in the audit trail · telemetry is simulated and labeled
        </footer>
      </main>
    </div>
  );
}
