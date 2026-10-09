import type { RiskLevel, WorkflowStage } from "./types";

export const LEVEL_COLORS: Record<RiskLevel, string> = {
  LOW: "#34D399",
  MEDIUM: "#FBBF24",
  HIGH: "#FB923C",
  CRITICAL: "#F87171",
};

export const LEVEL_BADGE: Record<RiskLevel, string> = {
  LOW: "bg-[#062E20] text-[#6EE7B7] border-[#0B4630]",
  MEDIUM: "bg-[#372406] text-[#FDE047] border-[#533B10]",
  HIGH: "bg-[#3A2310] text-[#FDBA74] border-[#5C3A17]",
  CRITICAL: "bg-[#3A1016] text-[#FCA5A5] border-[#5C1A22]",
};

export const STAGE_COLORS: Record<WorkflowStage, string> = {
  OBSERVE: "#38BDF8",
  DETECT: "#00F0FF",
  PREDICT: "#818CF8",
  DECIDE: "#FBBF24",
  ACT: "#FB923C",
  VERIFY: "#34D399",
  LEARN: "#A78BFA",
};

export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleTimeString([], { hour12: false });
}
