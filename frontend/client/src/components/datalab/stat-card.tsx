import type { ComponentType } from "react";
import { GlassPanel } from "@/components/radiant/glass-panel";

export function StatCard({
  label,
  value,
  helper,
  icon: Icon,
  accent,
  testId,
}: {
  label: string;
  value: string;
  helper?: string;
  icon: ComponentType<{ className?: string }>;
  accent: string;
  testId?: string;
}) {
  return (
    <GlassPanel className="p-4 flex flex-col gap-3" data-testid={testId}>
      <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${accent}`}>
        <Icon className="h-5 w-5" />
      </div>
      <div>
        <p className="text-xs uppercase tracking-wide text-muted-foreground">{label}</p>
        <p className="text-3xl font-bold tabular-nums">{value}</p>
        {helper && <p className="text-xs text-muted-foreground mt-1">{helper}</p>}
      </div>
    </GlassPanel>
  );
}

