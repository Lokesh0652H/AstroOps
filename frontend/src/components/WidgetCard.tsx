import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

// Shared cockpit panel: tactical border, subtle hover glow, optional cyan accent bar
// used to flag cards in a critical state.
interface WidgetCardProps {
  title: string;
  subtitle?: string;
  testid: string;
  accent?: ReactNode;
  highlight?: boolean;
  className?: string;
  children: ReactNode;
}

export default function WidgetCard({ title, subtitle, testid, accent, highlight, className, children }: WidgetCardProps) {
  return (
    <section
      data-testid={testid}
      className={cn(
        "flex h-full flex-col rounded-lg border border-[#1E2A44] bg-[#0D1424] p-5 transition-all duration-200",
        "hover:border-[#2F426D] hover:shadow-[0_4px_20px_rgba(0,240,255,0.05)]",
        className,
      )}
    >
      {highlight && <div className="accent-bar-top mb-3" aria-hidden="true" />}
      <header className="mb-4 flex items-start justify-between gap-3">
        <div>
          <h2 className="font-heading text-sm font-semibold tracking-tight">{title}</h2>
          {subtitle && <p className="mt-0.5 text-xs text-muted-foreground">{subtitle}</p>}
        </div>
        {accent}
      </header>
      <div className="flex-1 overflow-hidden">{children}</div>
    </section>
  );
}
