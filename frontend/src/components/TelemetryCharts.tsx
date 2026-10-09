import { useQuery } from "@tanstack/react-query";
import { format } from "date-fns";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import WidgetCard from "@/components/WidgetCard";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { apiGet } from "@/lib/api";
import type { MetricHistoryOut, ServiceRuntime } from "@/lib/types";

export const TELEMETRY_METRICS = [
  { key: "cpu", label: "CPU %", color: "#00F0FF", domain: [0, 100] as [number, number], unit: "%" },
  { key: "memory", label: "Memory %", color: "#38BDF8", domain: [0, 100] as [number, number], unit: "%" },
  { key: "latency_p99", label: "P99 latency (ms)", color: "#818CF8", unit: "ms" },
  { key: "error_rate", label: "Error rate (%)", color: "#F87171", unit: "%" },
] as const;

export type TelemetryMetricKey = (typeof TELEMETRY_METRICS)[number]["key"];

export type TooltipPayloadItem = {
  dataKey?: string | number;
  value?: number | string | Array<number | string>;
};

interface TelemetryChartsProps {
  serviceId?: string;
  services: ServiceRuntime[];
  onSelectService: (id: string) => void;
}

function TelemetryTooltip({
  active,
  payload,
  label,
  unit,
}: {
  active?: boolean;
  payload?: TooltipPayloadItem[];
  label?: number;
  unit?: string;
}) {
  if (!active || !payload?.length) return null;
  const raw = payload[0]?.value;
  const value = typeof raw === "number" ? raw : Number(raw ?? 0);
  return (
    <div className="rounded-md border border-[#223559] bg-[#0A101E] px-2.5 py-1.5 text-xs shadow-lg">
      <span className="font-mono text-muted-foreground">
        {typeof label === "number" ? format(new Date(label), "HH:mm:ss") : "—"}
      </span>
      <span className="ml-2 font-mono text-[#7DD3FC]">
        {value.toFixed(1)}
        {unit}
      </span>
    </div>
  );
}

export default function TelemetryCharts({ serviceId, services, onSelectService }: TelemetryChartsProps) {
  const historyQ = useQuery({
    queryKey: ["history", serviceId],
    queryFn: () => apiGet<MetricHistoryOut>(`/fleet/services/${serviceId}/metrics?points=90`),
    enabled: !!serviceId,
    refetchInterval: 5000,
  });

  const data = (historyQ.data?.points ?? []).map((p) => ({
    t: new Date(p.ts).getTime(),
    cpu: p.cpu,
    memory: p.memory,
    latency_p99: p.latency_p99,
    error_rate: p.error_rate,
  }));
  const hasData = data.length >= 2;

  return (
    <WidgetCard
      title="Live telemetry"
      subtitle="Rolling window · last ~7 minutes · 5s resolution"
      testid="telemetry-charts"
      accent={
        <Select value={serviceId ?? ""} onValueChange={onSelectService}>
          <SelectTrigger size="sm" className="w-[180px]" data-testid="telemetry-service-select">
            <SelectValue>{(v: string) => services.find((s) => s.id === v)?.name ?? "Service"}</SelectValue>
          </SelectTrigger>
          <SelectContent>
            {services.map((s) => (
              <SelectItem key={s.id} value={s.id}>
                {s.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      }
    >
      {!hasData ? (
        <div className="grid h-44 place-items-center">
          <p className="text-sm text-muted-foreground">
            {historyQ.isError
              ? "Telemetry unavailable — the engine will backfill on reconnect."
              : "Collecting telemetry…"}
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {TELEMETRY_METRICS.map((m) => (
            <div key={m.key} data-testid={`chart-${m.key}`} className="rounded-lg border border-[#1A263D] bg-[#0A101E] p-3">
              <div className="mb-1 flex items-center justify-between">
                <span className="text-[11px] uppercase tracking-[0.12em] text-muted-foreground">{m.label}</span>
                <span className="font-mono text-xs" style={{ color: m.color }}>
                  {data[data.length - 1][m.key].toFixed(1)}
                  {m.unit}
                </span>
              </div>
              <ResponsiveContainer width="100%" height={110}>
                <AreaChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
                  <defs>
                    <linearGradient id={`grad-${m.key}`} x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={m.color} stopOpacity={0.28} />
                      <stop offset="100%" stopColor={m.color} stopOpacity={0.02} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="#1A263D" vertical={false} />
                  <XAxis
                    dataKey="t"
                    tickFormatter={(t: number) => format(new Date(t), "HH:mm")}
                    tick={{ fill: "#8B9BB4", fontSize: 10 }}
                    axisLine={false}
                    tickLine={false}
                    minTickGap={48}
                  />
                  <YAxis
                    {...("domain" in m ? { domain: m.domain } : {})}
                    width={34}
                    tick={{ fill: "#8B9BB4", fontSize: 10 }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <Tooltip content={<TelemetryTooltip unit={m.unit} />} cursor={{ stroke: "#223559" }} />
                  <Area
                    type="monotone"
                    dataKey={m.key}
                    stroke={m.color}
                    strokeWidth={1.5}
                    fill={`url(#grad-${m.key})`}
                    isAnimationActive={false}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          ))}
        </div>
      )}
      <p className="mt-3 text-[11px] text-muted-foreground">
        Simulated fleet telemetry — deterministic and labeled; no production cluster is connected.
      </p>
    </WidgetCard>
  );
}
