import WidgetCard from "@/components/WidgetCard";
import { Badge } from "@/components/ui/badge";
import { LEVEL_BADGE } from "@/lib/levels";
import { fmtTime } from "@/lib/levels";
import type { AnomalyOut } from "@/lib/types";
import { cn } from "@/lib/utils";

interface AnomalyFeedProps {
  anomalies: AnomalyOut[];
}

export default function AnomalyFeed({ anomalies }: AnomalyFeedProps) {
  return (
    <WidgetCard
      title="Anomaly feed"
      subtitle="Ensemble detections with measured evidence"
      testid="anomaly-feed"
      highlight={anomalies.some((a) => a.risk_level === "CRITICAL")}
    >
      {anomalies.length === 0 ? (
        <div className="grid h-40 place-items-center">
          <p className="text-sm text-muted-foreground">No anomalies in the current window — fleet nominal.</p>
        </div>
      ) : (
        <div className="max-h-[360px] space-y-2.5 overflow-y-auto pr-1" aria-live="polite">
          {anomalies.map((a) => (
            <div
              key={a.id}
              data-testid={`anomaly-item-${a.id}`}
              className="space-y-1.5 rounded-lg border border-[#1E2A44] bg-[#121C33] p-3"
            >
              <div className="flex flex-wrap items-center gap-2">
                <Badge className={cn(LEVEL_BADGE[a.risk_level])}>{a.risk_level}</Badge>
                <span className="text-sm font-medium">{a.service_name}</span>
                <span className="ml-auto font-mono text-[11px] text-muted-foreground">
                  {fmtTime(a.detected_at)} · risk {a.risk_score}
                </span>
              </div>
              <ul className="space-y-0.5">
                {a.reasons.slice(0, 3).map((r, i) => (
                  <li key={i} className="font-mono text-[11px] leading-snug text-muted-foreground">
                    › {r}
                  </li>
                ))}
              </ul>
              {a.evidence && (
                <div className="flex flex-wrap gap-x-4 gap-y-0.5 border-t border-[#1A263D] pt-1.5 font-mono text-[11px] text-muted-foreground">
                  <span>cpu {a.evidence.cpu}%</span>
                  <span>mem {a.evidence.memory}%</span>
                  <span>p99 {a.evidence.latency_p99}ms</span>
                  <span>err {a.evidence.error_rate}%</span>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </WidgetCard>
  );
}
