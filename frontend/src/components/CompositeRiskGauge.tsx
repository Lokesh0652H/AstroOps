import WidgetCard from "@/components/WidgetCard";
import { Badge } from "@/components/ui/badge";
import { LEVEL_BADGE, LEVEL_COLORS } from "@/lib/levels";
import type { FleetOverview } from "@/lib/types";
import { cn } from "@/lib/utils";

interface CompositeRiskGaugeProps {
  overview: FleetOverview | undefined;
}

const R = 80;
const CX = 100;
const CY = 104;
const ARC_LEN = Math.PI * R;

// 0-100 semicircle gauge for the fleet composite risk + per-service breakdown bars.
export default function CompositeRiskGauge({ overview }: CompositeRiskGaugeProps) {
  const score = overview?.fleet_risk_score ?? 0;
  const level = overview?.fleet_risk_level ?? "LOW";
  const color = LEVEL_COLORS[level];
  const services = [...(overview?.services ?? [])].sort((a, b) => b.risk_score - a.risk_score);

  return (
    <WidgetCard
      title="Composite risk"
      subtitle="Weighted ensemble score · 0-100"
      testid="composite-risk-gauge"
      highlight={level === "CRITICAL"}
    >
      <div className="flex flex-col items-center">
        <svg
          viewBox="0 0 200 118"
          className="w-full max-w-[240px]"
          role="img"
          aria-label={`Fleet composite risk ${score} of 100, level ${level}`}
        >
          <path
            d={`M ${CX - R} ${CY} A ${R} ${R} 0 0 1 ${CX + R} ${CY}`}
            fill="none"
            stroke="#1E2A44"
            strokeWidth="14"
            strokeLinecap="round"
          />
          <path
            d={`M ${CX - R} ${CY} A ${R} ${R} 0 0 1 ${CX + R} ${CY}`}
            fill="none"
            stroke={color}
            strokeWidth="14"
            strokeLinecap="round"
            strokeDasharray={`${(Math.min(100, Math.max(0, score)) / 100) * ARC_LEN} ${ARC_LEN}`}
            style={{ transition: "stroke-dasharray 600ms ease-out" }}
          />
          <text
            x={CX}
            y={CY - 16}
            textAnchor="middle"
            fill="#F0F6FC"
            fontSize="34"
            fontFamily="'IBM Plex Mono', monospace"
            fontWeight="600"
            data-testid="risk-gauge-score"
          >
            {score}
          </text>
          <text x={CX} y={CY + 4} textAnchor="middle" fill="#8B9BB4" fontSize="9" letterSpacing="2">
            COMPOSITE RISK / 100
          </text>
        </svg>
        <Badge className={cn("mt-1", LEVEL_BADGE[level])} aria-live="polite">
          {level}
        </Badge>
      </div>

      <div className="mt-4 space-y-2" data-testid="service-risk-bars">
        {services.map((s) => (
          <div key={s.id} className="flex items-center gap-2">
            <span className="w-32 shrink-0 truncate text-xs text-muted-foreground">{s.name}</span>
            <div className="h-1.5 flex-1 rounded-full bg-[#1E2A44]">
              <div
                className="h-full rounded-full"
                style={{
                  width: `${s.risk_score}%`,
                  backgroundColor: LEVEL_COLORS[s.risk_level],
                  transition: "width 600ms ease-out",
                }}
              />
            </div>
            <span className="w-10 shrink-0 text-right font-mono text-[11px]">{s.risk_score}</span>
          </div>
        ))}
        {services.length === 0 && <div className="h-16 animate-pulse rounded bg-[#121C33]" />}
      </div>
    </WidgetCard>
  );
}
