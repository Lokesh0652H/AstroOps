import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import WidgetCard from "@/components/WidgetCard";
import { fmtTime } from "@/lib/levels";
import type { PolicyState, RecommendationOut } from "@/lib/types";

interface RecommendationActuatorProps {
  recommendations: RecommendationOut[];
  policy: PolicyState | undefined;
  busyId: string | null;
  onApprove: (rec: RecommendationOut) => void;
  onExecute: (rec: RecommendationOut) => void;
  onDismiss: (rec: RecommendationOut) => void;
  onToggleAutoRemediate: (value: boolean) => void;
  policyPending: boolean;
}

const STATUS_BADGE: Record<string, string> = {
  open: "bg-[#08283B] text-[#38BDF8] border-[#123A52]",
  approved: "bg-[#372406] text-[#FDE047] border-[#533B10]",
  executed: "bg-[#062E20] text-[#6EE7B7] border-[#0B4630]",
  dismissed: "bg-[#121C33] text-[#8B9BB4] border-[#223559]",
};

// An action may execute when the operator approved it, or when it is low-risk + bounded
// and opened directly by policy (approval not required).
function canExecute(rec: RecommendationOut): boolean {
  return rec.status === "approved" || (rec.status === "open" && rec.auto_eligible && !rec.requires_approval);
}

export default function RecommendationActuator({
  recommendations,
  policy,
  busyId,
  onApprove,
  onExecute,
  onDismiss,
  onToggleAutoRemediate,
  policyPending,
}: RecommendationActuatorProps) {
  const visible = recommendations.filter((r) => r.status !== "dismissed").slice(0, 6);

  return (
    <WidgetCard
      title="Recommendations & bounded actions"
      subtitle="DECIDE → ACT · fixed action catalog, cooldowns, max_replicas caps"
      testid="recommendation-actuator"
      highlight={visible.some((r) => r.status === "open" && r.risk_of_action !== "low")}
    >
      <label className="mb-4 flex items-start gap-2.5 rounded-lg border border-[#1A263D] bg-[#0A101E] p-3 text-xs">
        <Checkbox
          checked={policy?.auto_remediate ?? false}
          onCheckedChange={(checked: boolean) => onToggleAutoRemediate(Boolean(checked))}
          disabled={policyPending}
          data-testid="auto-remediate-toggle"
          className="mt-0.5"
        />
        <span>
          <span className="font-medium text-foreground">Auto-remediate low-risk bounded actions</span>
          <span className="block text-muted-foreground">
            Scale-out and cache invalidation execute without approval when the engine decides; restart-class
            actions always require explicit approval. Default: off.
          </span>
        </span>
      </label>

      {visible.length === 0 ? (
        <div className="grid h-28 place-items-center">
          <p className="text-sm text-muted-foreground">
            No open recommendations — the engine recommends only on HIGH/CRITICAL risk.
          </p>
        </div>
      ) : (
        <div className="max-h-[380px] space-y-3 overflow-y-auto pr-1">
          {visible.map((rec) => (
            <div
              key={rec.id}
              data-testid={`recommendation-card-${rec.id}`}
              className="space-y-2 rounded-lg border border-[#1E2A44] bg-[#121C33] p-3"
            >
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="outline" className="font-mono text-[10px] uppercase">
                  {rec.action_type}
                </Badge>
                <Badge className={STATUS_BADGE[rec.status]}>{rec.status}</Badge>
                <span className="ml-auto font-mono text-[11px] text-muted-foreground">
                  {fmtTime(rec.created_at)} · confidence {(rec.confidence * 100).toFixed(0)}%
                </span>
              </div>

              <p className="text-sm font-medium">{rec.title}</p>
              <p className="text-xs text-muted-foreground">{rec.description}</p>

              <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px]">
                <span className="text-muted-foreground">
                  action risk:{" "}
                  <span className={rec.risk_of_action === "high" ? "text-red-400" : rec.risk_of_action === "medium" ? "text-amber-300" : "text-emerald-400"}>
                    {rec.risk_of_action}
                  </span>
                </span>
                <span className="text-muted-foreground">
                  approval: {rec.requires_approval ? <span className="text-amber-300">required</span> : <span className="text-muted-foreground">not required</span>}
                </span>
              </div>
              <p className="text-[11px] text-muted-foreground">impact: {rec.impact}</p>

              {rec.reasons.length > 0 && (
                <ul className="space-y-0.5 border-t border-[#1A263D] pt-1.5">
                  {rec.reasons.slice(0, 2).map((r, i) => (
                    <li key={i} className="font-mono text-[11px] leading-snug text-muted-foreground">
                      › {r}
                    </li>
                  ))}
                </ul>
              )}

              <div className="flex flex-wrap items-center gap-2 pt-1">
                {rec.status === "open" && rec.requires_approval && (
                  <Button
                    size="xs"
                    variant="outline"
                    data-testid={`approve-rec-btn-${rec.id}`}
                    disabled={busyId === rec.id}
                    onClick={() => onApprove(rec)}
                  >
                    Approve
                  </Button>
                )}
                {(rec.status === "approved" || rec.status === "open") && (
                  <Button
                    size="xs"
                    data-testid={`execute-rec-btn-${rec.id}`}
                    disabled={busyId === rec.id || !canExecute(rec)}
                    title={canExecute(rec) ? "Execute the bounded action" : "Requires operator approval first"}
                    onClick={() => onExecute(rec)}
                  >
                    {busyId === rec.id ? "Executing…" : "Execute"}
                  </Button>
                )}
                {(rec.status === "open" || rec.status === "approved") && (
                  <Button
                    size="xs"
                    variant="ghost"
                    data-testid={`dismiss-rec-btn-${rec.id}`}
                    disabled={busyId === rec.id}
                    onClick={() => onDismiss(rec)}
                  >
                    Dismiss
                  </Button>
                )}
                {rec.status === "executed" && (
                  <span className="font-mono text-[11px] text-emerald-400" data-testid={`rec-executed-note-${rec.id}`}>
                    executed by {rec.executed_by ?? "operator"} at {fmtTime(rec.executed_at)} — recovery verification in
                    progress
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      <p className="mt-3 text-[11px] text-muted-foreground">
        Executing an action is not treated as recovery — see the verifier panel for fresh-telemetry verdicts.
      </p>
    </WidgetCard>
  );
}
