import WidgetCard from "@/components/WidgetCard";
import { LEVEL_BADGE, LEVEL_COLORS } from "@/lib/levels";
import { Badge } from "@/components/ui/badge";
import type { AnomalyOut, FleetOverview } from "@/lib/types";
import { cn } from "@/lib/utils";

interface FleetHealthSummaryProps {
  overview: FleetOverview | undefined;
  anomalies: AnomalyOut[];
  offline: boolean;
}

function StatCard({
  label,
  value,
  sub,
  testid,
  flashKey,
  valueClass,
}: {
  label: string;
  value: string;
  sub: string;
  testid: string;
  flashKey?: string | number;
  valueClass?: string;
}) {
  return (
    <div className="rounded-lg border border-[#1E2A44] bg-[#0D1424] p-4 transition-all duration-200 hover:border-[#2F426D] hover:shadow-[0_4px_20px_rgba(0,240,255,0.05)]">
      <p className="text-[11px] uppercase tracking-[0.15em] text-muted-foreground">{label}</p>
      <p
        key={flashKey}
        data-testid={testid}
        className={cn("flash-metric mt-2 font-mono text-2xl font-semibold tracking-tight", valueClass)}
      >
        {value}
      </p>
      <p className="mt-1 text-xs text-muted-foreground">{sub}</p>
    </div>
  );
}

export default function FleetHealthSummary({ overview, anomalies, offline }: FleetHealthSummaryProps) {
  const services = overview?.services ?? [];
  const healthy = services.filter((s) => s.status === "healthy").length;
  const regions = new Set(services.map((s) => s.region)).size;
  const worst = services.reduce(
    (acc, s) => (s.risk_score > acc.risk_score ? s : acc),
    services[0] ?? { risk_score: 0, risk_level: "LOW" as const, name: "" },
  );
  const incidentCount = services.filter((s) => s.status === "incident").length;

  return (
    <div className="grid h-full grid-cols-2 gap-3 sm:grid-cols-4">
      <StatCard
        label="Fleet status"
        value={offline ? "—" : `${healthy}/${services.length}`}
        sub={incidentCount > 0 ? `${incidentCount} service(s) with active incident` : offline ? "reconnecting…" : "all nominal"}
        testid="fleet-stat-health"
        flashKey={`${healthy}-${services.length}`}
      />
      <StatCard
        label="Monitored services"
        value={String(services.length)}
        sub={`${regions} region(s) · 5s tick`}
        testid="fleet-stat-services"
      />
      <StatCard
        label="Active anomalies"
        value={String(anomalies.length)}
        sub="ensemble detections, deduped/min"
        testid="fleet-stat-anomalies"
        flashKey={anomalies.length}
      />
      <StatCard
        label="Fleet risk"
        value={offline ? "—" : String(overview?.fleet_risk_score ?? 0)}
        sub={worst.name ? `worst: ${worst.name}` : "composite 0-100"}
        testid="fleet-stat-risk"
        flashKey={overview?.fleet_risk_score}
        valueClass={
          offline ? undefined : undefined
        }
      />
      {offline ? null : (
        <Badge className={cn("col-span-2 hidden sm:col-span-4 sm:w-fit", LEVEL_BADGE[worst.risk_level])} aria-live="polite">
          {`worst service risk ${worst.risk_score} · ${worst.risk_level}`}
        </Badge>
      )}
      <span className="hidden" style={{ color: LEVEL_COLORS[worst.risk_level] }} aria-hidden="true" />
    </div>
  );
}
