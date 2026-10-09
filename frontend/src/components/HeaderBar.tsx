import { useState } from "react";
import { RotateCcw, Zap } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { cn } from "@/lib/utils";
import type { FleetOverview, IncidentKind } from "@/lib/types";

// Mirrors KIND_LABELS in backend/lib/telemetry.py — keep in sync.
const INCIDENT_KINDS: { value: IncidentKind; label: string }[] = [
  { value: "pod_oom", label: "Pod OOM (memory exhaustion)" },
  { value: "db_conn_leak", label: "DB connection leak" },
  { value: "latency_spike", label: "API latency spike" },
  { value: "traffic_surge", label: "Traffic surge" },
];

interface HeaderBarProps {
  overview: FleetOverview | undefined;
  offline: boolean;
  injecting: boolean;
  resetting: boolean;
  onInject: (serviceId: string, kind: IncidentKind) => void;
  onReset: () => void;
}

export default function HeaderBar({ overview, offline, injecting, resetting, onInject, onReset }: HeaderBarProps) {
  const services = overview?.services ?? [];
  const [serviceId, setServiceId] = useState<string>("");
  const [kind, setKind] = useState<IncidentKind>("pod_oom");
  const effectiveServiceId = serviceId || services[0]?.id || "";

  return (
    <header className="sticky top-0 z-40 border-b border-[#1E2A44] bg-[#060A14]/85 backdrop-blur-xl">
      <div className="mx-auto flex max-w-[1600px] flex-wrap items-center gap-x-3 gap-y-2 px-4 py-3 md:px-6">
        <span
          aria-hidden="true"
          className={cn(
            "radar-dot h-2.5 w-2.5 shrink-0 rounded-full",
            overview?.engine_alive ? "bg-emerald-400 text-emerald-400" : "bg-amber-400 text-amber-400",
          )}
        />
        <div className="mr-auto">
          <h1 className="font-heading text-lg font-bold tracking-tight text-glow-cyan">AstraOps AI</h1>
          <p className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground">
            Intelligent Cloud Operations
          </p>
        </div>

        <Badge
          className="border-[#123A52] bg-[#08283B] text-[#38BDF8]"
          title={overview?.simulation.note ?? "Telemetry comes from a deterministic simulator."}
        >
          SIMULATED FLEET
        </Badge>
        {offline && (
          <Badge variant="destructive" data-testid="engine-offline-badge">
            engine offline — reconnecting
          </Badge>
        )}

        <div className="flex flex-wrap items-center gap-2">
          <Select value={effectiveServiceId} onValueChange={setServiceId}>
            <SelectTrigger size="sm" className="w-[168px]" data-testid="inject-service-select">
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

          <Select value={kind} onValueChange={(v: string) => setKind(v as IncidentKind)}>
            <SelectTrigger size="sm" className="w-[208px]" data-testid="inject-kind-select">
              <SelectValue>{(v: string) => INCIDENT_KINDS.find((k) => k.value === v)?.label ?? "Failure mode"}</SelectValue>
            </SelectTrigger>
            <SelectContent>
              {INCIDENT_KINDS.map((k) => (
                <SelectItem key={k.value} value={k.value}>
                  {k.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Button
            size="sm"
            variant="outline"
            data-testid="inject-incident-btn"
            disabled={injecting || !effectiveServiceId}
            onClick={() => onInject(effectiveServiceId, kind)}
          >
            <Zap className="mr-1.5 h-3.5 w-3.5" />
            {injecting ? "Injecting…" : "Inject failure"}
          </Button>

          <Button size="sm" variant="ghost" data-testid="reset-fleet-btn" disabled={resetting} onClick={onReset}>
            <RotateCcw className="mr-1.5 h-3.5 w-3.5" />
            {resetting ? "Resetting…" : "Reset fleet"}
          </Button>
        </div>
      </div>
    </header>
  );
}
