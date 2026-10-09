import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { format } from "date-fns";
import { Area, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import WidgetCard from "@/components/WidgetCard";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { apiGet } from "@/lib/api";
import type { ForecastResponse, MetricPoint } from "@/lib/types";
import type { TooltipPayloadItem } from "@/components/TelemetryCharts";

type MetricKey = Exclude<keyof MetricPoint, "ts">;

const METRIC_OPTIONS: { value: MetricKey; label: string }[] = [
  { value: "cpu", label: "CPU %" },
  { value: "memory", label: "Memory %" },
  { value: "latency_p99", label: "P99 latency (ms)" },
  { value: "error_rate", label: "Error rate (%)" },
];

const TREND_BADGE: Record<string, string> = {
  STABLE: "bg-[#062E20] text-[#6EE7B7] border-[#0B4630]",
  RISING: "bg-[#372406] text-[#FDE047] border-[#533B10]",
  SPIKE_EXPECTED: "bg-[#3A1016] text-[#FCA5A5] border-[#5C1A22]",
  INSUFFICIENT_DATA: "bg-[#121C33] text-[#8B9BB4] border-[#223559]",
};

type Row = { t: number; actual: number | null; forecast: number | null; range: [number, number] | null };

function ForecastTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: TooltipPayloadItem[];
  label?: number;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-md border border-[#223559] bg-[#0A101E] px-2.5 py-2 text-xs shadow-lg">
      <p className="mb-1 font-mono text-muted-foreground">
        {typeof label === "number" ? format(new Date(label), "HH:mm:ss") : "—"}
      </p>
      {payload.map((p, i) => (
        <div key={i} className="flex justify-between gap-4">
          <span className="text-muted-foreground">{String(p.dataKey)}</span>
          <span className="font-mono text-[#7DD3FC]">
            {Array.isArray(p.value)
              ? `${Number(p.value[0] ?? 0).toFixed(1)} – ${Number(p.value[1] ?? 0).toFixed(1)}`
              : Number(p.value ?? 0).toFixed(1)}
          </span>
        </div>
      ))}
    </div>
  );
}

export default function ForecastConfidenceView({ serviceId }: { serviceId?: string }) {
  const [metric, setMetric] = useState<MetricKey>("cpu");

  const forecastQ = useQuery({
    queryKey: ["forecast", serviceId, metric],
    queryFn: () => apiGet<ForecastResponse>(`/intelligence/forecast/${serviceId}?metric=${metric}`),
    enabled: !!serviceId,
    refetchInterval: 10000,
  });

  const data: Row[] = (forecastQ.data?.history ?? []).map((p) => ({
    t: new Date(p.ts).getTime(),
    actual: p[metric],
    forecast: null,
    range: null,
  }));
  for (const s of forecastQ.data?.steps ?? []) {
    data.push({ t: new Date(s.t).getTime(), actual: null, forecast: s.value, range: [s.lower, s.upper] });
  }

  const trend = forecastQ.data?.trend ?? "INSUFFICIENT_DATA";

  return (
    <WidgetCard
      title="Degradation forecast"
      subtitle="Holt double-exponential smoothing · 5 steps ahead"
      testid="forecast-view"
      highlight={trend === "SPIKE_EXPECTED"}
      accent={
        <Select value={metric} onValueChange={(v: string) => setMetric(v as MetricKey)}>
          <SelectTrigger size="sm" className="w-[160px]" data-testid="forecast-metric-select">
            <SelectValue>{(v: string) => METRIC_OPTIONS.find((m) => m.value === v)?.label ?? "Metric"}</SelectValue>
          </SelectTrigger>
          <SelectContent>
            {METRIC_OPTIONS.map((m) => (
              <SelectItem key={m.value} value={m.value}>
                {m.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      }
    >
      <div className="mb-3 flex items-center gap-2">
        <Badge data-testid="forecast-trend-badge" className={TREND_BADGE[trend] ?? TREND_BADGE.INSUFFICIENT_DATA}>
          {trend.replace(/_/g, " ")}
        </Badge>
        <span className="font-mono text-[11px] text-muted-foreground">
          trained on {forecastQ.data?.trained_on ?? 0} samples
        </span>
      </div>

      {data.length < 2 ? (
        <div className="grid h-44 place-items-center">
          <p className="text-sm text-muted-foreground">
            {forecastQ.isError ? "Forecast unavailable — resumes on reconnect." : "Collecting history…"}
          </p>
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={200}>
          <ComposedChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="#1A263D" vertical={false} />
            <XAxis
              dataKey="t"
              tickFormatter={(t: number) => format(new Date(t), "HH:mm")}
              tick={{ fill: "#8B9BB4", fontSize: 10 }}
              axisLine={false}
              tickLine={false}
              minTickGap={40}
            />
            <YAxis width={36} tick={{ fill: "#8B9BB4", fontSize: 10 }} axisLine={false} tickLine={false} />
            <Tooltip content={<ForecastTooltip />} cursor={{ stroke: "#223559" }} />
            <Area dataKey="range" stroke="none" fill="#38BDF8" fillOpacity={0.15} isAnimationActive={false} connectNulls={false} />
            <Line dataKey="actual" stroke="#00F0FF" strokeWidth={1.5} dot={false} isAnimationActive={false} />
            <Line dataKey="forecast" stroke="#38BDF8" strokeWidth={1.5} strokeDasharray="5 3" dot={false} isAnimationActive={false} />
          </ComposedChart>
        </ResponsiveContainer>
      )}

      <p className="mt-2 text-[11px] text-muted-foreground">
        A statistical extrapolation of recent telemetry with widening uncertainty — an estimate, not a
        calibrated probability of failure.
      </p>
    </WidgetCard>
  );
}
