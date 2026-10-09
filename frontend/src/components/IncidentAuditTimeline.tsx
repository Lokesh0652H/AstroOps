import WidgetCard from "@/components/WidgetCard";
import { STAGE_COLORS, fmtTime } from "@/lib/levels";
import type { AuditEventOut } from "@/lib/types";

interface IncidentAuditTimelineProps {
  events: AuditEventOut[];
}

export default function IncidentAuditTimeline({ events }: IncidentAuditTimelineProps) {
  return (
    <WidgetCard
      title="Incident & audit timeline"
      subtitle="LEARN · every stage transition, append-only"
      testid="incident-audit-timeline"
    >
      {events.length === 0 ? (
        <div className="grid h-40 place-items-center">
          <p className="text-sm text-muted-foreground">No audit events yet.</p>
        </div>
      ) : (
        <div className="max-h-[360px] space-y-0 overflow-y-auto pr-1" data-testid="audit-timeline">
          {events.map((e, idx) => (
            <div key={e.id} className="flex gap-3" data-testid={`audit-event-${e.id}`}>
              <div className="flex flex-col items-center">
                <span
                  className="mt-1.5 h-2 w-2 shrink-0 rounded-full"
                  style={{ backgroundColor: STAGE_COLORS[e.stage] ?? "#38BDF8" }}
                />
                {idx < events.length - 1 && <span className="w-px flex-1 bg-[#1E2A44]" />}
              </div>
              <div className="pb-4">
                <div className="flex flex-wrap items-center gap-2 text-[11px]">
                  <span
                    className="font-mono uppercase tracking-[0.12em]"
                    style={{ color: STAGE_COLORS[e.stage] ?? "#38BDF8" }}
                  >
                    {e.stage}
                  </span>
                  <span className="font-mono text-muted-foreground">{fmtTime(e.ts)}</span>
                  <span className="text-muted-foreground">· {e.actor}</span>
                </div>
                <p className="mt-0.5 text-[13px] leading-snug text-foreground/90">{e.message}</p>
              </div>
            </div>
          ))}
        </div>
      )}
    </WidgetCard>
  );
}
