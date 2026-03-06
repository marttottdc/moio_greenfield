import { useQuery } from "@tanstack/react-query";
import { GlassPanel } from "@/components/radiant/glass-panel";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { Settings2 } from "lucide-react";
import { fetchJson } from "@/lib/queryClient";
import { apiV1 } from "@/lib/api";
import type { KPIType } from "@shared/schema";

interface DashboardMetricsBlock {
  total_campaigns?: number;
  total_audiences?: number;
  total_sent?: number;
  total_opened?: number;
  open_rate?: number;
  click_rate?: number;
  total_contacts?: number;
  active_deals?: number;
  conversion_rate?: number;
  response_rate?: number;
}

interface DashboardBundle {
  dashboard_metrics?: DashboardMetricsBlock;
}

const KPI_LABELS: Record<KPIType, string> = {
  total_campaigns: "Campaigns",
  total_audiences: "Audiences",
  total_sent: "Sent",
  total_opened: "Opened",
  open_rate: "Open Rate",
  click_rate: "Click Rate",
  total_contacts: "Contacts",
  active_deals: "Active Deals",
  conversion_rate: "Conversion",
  response_rate: "Response Rate",
};

function formatValue(key: KPIType, value?: number | null): string {
  if (value === undefined || value === null) return "—";
  if (key.includes("rate")) return `${value.toFixed(1)}%`;
  return value.toLocaleString();
}

interface KPIRibbonWidgetProps {
  visibleKPIs: KPIType[];
  onConfigureClick?: () => void;
}

export function KPIRibbonWidget({ visibleKPIs, onConfigureClick }: KPIRibbonWidgetProps) {
  const { data, isLoading } = useQuery<DashboardBundle>({
    queryKey: [apiV1("/campaigns/campaigns/dashboard/")],
    queryFn: () => fetchJson<DashboardBundle>(apiV1("/campaigns/campaigns/dashboard/")),
  });

  const metrics = data?.dashboard_metrics;

  if (isLoading) {
    return (
      <div className="flex gap-4 overflow-x-auto pb-2">
        {[1, 2, 3, 4].map((i) => (
          <Skeleton key={i} className="h-20 w-40 shrink-0" />
        ))}
      </div>
    );
  }

  const displayKPIs = visibleKPIs.filter((kpi) => kpi in (metrics || {}));

  return (
    <div className="relative">
      <div className="flex gap-4 overflow-x-auto pb-2">
        {displayKPIs.length > 0 ? (
          displayKPIs.map((kpi) => (
            <GlassPanel 
              key={kpi} 
              className="p-4 min-w-[140px] shrink-0"
              data-testid={`kpi-card-${kpi}`}
            >
              <p className="text-xs text-muted-foreground mb-1">{KPI_LABELS[kpi]}</p>
              <p className="text-2xl font-bold">
                {formatValue(kpi, metrics?.[kpi as keyof DashboardMetricsBlock] as number | undefined)}
              </p>
            </GlassPanel>
          ))
        ) : (
          <GlassPanel className="p-4 w-full text-center">
            <p className="text-sm text-muted-foreground">
              No KPIs selected. Click configure to add metrics.
            </p>
          </GlassPanel>
        )}
      </div>
      {onConfigureClick && (
        <Button
          variant="ghost"
          size="icon"
          className="absolute -top-2 -right-2"
          onClick={onConfigureClick}
          data-testid="button-configure-kpis"
        >
          <Settings2 className="h-4 w-4" />
        </Button>
      )}
    </div>
  );
}
