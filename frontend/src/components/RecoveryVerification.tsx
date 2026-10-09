import { Badge } from "@/components/ui/badge";
import WidgetCard from "@/components/WidgetCard";
import { fmtTime } from "@/lib/levels";
import type { VerificationOut } from "@/lib/types";

interface RecoveryVerificationProps {
  verifications: VerificationOut[];
}

const VERDICT_BADGE: Record<string, string> = {
  RECOVERED: "bg-[#062E20] text-[#6EE7B7] border-[#0B4630]",
  NOT_YET: "bg-[#372406] text-[#FDE047] border-[#533B10]",
  FAILED: "bg-[#3A1016] text-[#FCA5A5] border-[#5C1A22]",
};

function Delta({ label, before, after, unit, invert }: { label: string; before: number; after: number; unit: string; invert?: boolean }) {
  const improved = invert ? after < before : after < before;
  return (
    <div className="flex items-center justify-between gap-3 font-mono text-[11px]">
      <span className="text-muted-foreground">{label}</span>
      <span className="flex items-center gap-2">
        <span className="text-muted-foreground">
          {before.toFixed(1)}
          {unit}
        </span>
        <span aria-hidden="true">→</span>
        <span className={(invert ? after <= before : after >= before) ? "text-emerald-400" : "text-red-400"}>
          {after.toFixed(1)}
          {unit}
        </span>
      </span>
    </div>
  );
}

export default function RecoveryVerification({ verifications }: RecoveryVerificationProps) {
  return (
    <WidgetCard
      title="Recovery verification"
      subtitle="VERIFY · verdicts come from fresh post-action telemetry"
      testid="recovery-verification"
      highlight={verifications.some((v) => v.verdict === "FAILED")}
    >
      {verifications.length === 0 ? (
        <div className="grid h-40 place-items-center">
          <p className="text-sm text-muted-foreground">No remediations verified yet.</p>
        </div>
      ) : (
        <div className="max-h-[300px] space-y-2.5 overflow-y-auto pr-1">
          {verifications.map((v) => (
            <div
              key={v.id}
              data-testid={`verification-item-${v.id}`}
              className="space-y-2 rounded-lg border border-[#1E2A44] bg-[#121C33] p-3"
            >
              <div className="flex flex-wrap items-center gap-2">
                <Badge className={VERDICT_BADGE[v.verdict]}>{v.verdict.replace(/_/g, " ")}</Badge>
                <span className="text-sm font-medium">{v.service_name}</span>
                <span className="ml-auto font-mono text-[11px] text-muted-foreground">{fmtTime(v.checked_at)}</span>
              </div>
              {v.before && v.after ? (
                <div className="space-y-1 rounded-md border border-[#1A263D] bg-[#0A101E] p-2">
                  <Delta label="error rate" before={v.before.error_rate} after={v.after.error_rate} unit="%" />
                  <Delta label="p99 latency" before={v.before.latency_p99} after={v.after.latency_p99} unit="ms" />
                  <Delta label="cpu" before={v.before.cpu} after={v.after.cpu} unit="%" />
                </div>
              ) : (
                <p className="text-[11px] text-muted-foreground">baseline snapshot unavailable</p>
              )}
            </div>
          ))}
        </div>
      )}
      <p className="mt-3 text-[11px] text-muted-foreground">
        A successful action execution is not proof of recovery — only fresh telemetry back within baseline
        produces RECOVERED.
      </p>
    </WidgetCard>
  );
}
