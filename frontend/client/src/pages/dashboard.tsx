import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { PageLayout } from "@/components/layout/page-layout";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Settings2 } from "lucide-react";
import { fetchJson } from "@/lib/queryClient";
import { apiV1 } from "@/lib/api";
import { usePreferences, useKPIs, useWidgets } from "@/hooks/use-preferences";
import { WidgetSelector } from "@/components/dashboard/widget-selector";
import { KPISelector } from "@/components/dashboard/kpi-selector";
import { 
  KPIRibbonWidget,
  RecentCampaignsWidget,
  RecentAudiencesWidget,
  CRMAssistantWidget,
  FavoritesWidget,
  FrequentlyUsedWidget,
  ActivityChartWidget,
  QuickActionsWidget,
  PerformanceMetricsWidget,
  MyTasksWidget,
  GlobalTimelineWidget,
} from "@/components/dashboard/widgets";
import type { WidgetType, WidgetConfig, KPIType } from "@shared/schema";

interface DashboardMetricsBlock {
  total_campaigns?: number;
  total_audiences?: number;
  total_sent?: number;
  total_opened?: number;
  open_rate?: number;
}

interface DashboardBundle {
  dashboard_metrics?: DashboardMetricsBlock;
}

const DASHBOARD_PATH = apiV1("/campaigns/campaigns/dashboard/");

function WidgetRenderer({ widget }: { widget: WidgetConfig }) {
  switch (widget.type) {
    case "recent_campaigns":
      return <RecentCampaignsWidget />;
    case "recent_audiences":
      return <RecentAudiencesWidget />;
    case "crm_assistant":
      return <CRMAssistantWidget />;
    case "favorites":
      return <FavoritesWidget />;
    case "frequently_used":
      return <FrequentlyUsedWidget />;
    case "activity_chart":
      return <ActivityChartWidget />;
    case "quick_actions":
      return <QuickActionsWidget />;
    case "performance_metrics":
      return <PerformanceMetricsWidget />;
    case "my_tasks":
      return <MyTasksWidget />;
    case "global_timeline":
      return <GlobalTimelineWidget />;
    default:
      return null;
  }
}

function getWidgetGridClass(size: WidgetConfig["size"]): string {
  switch (size) {
    case "small":
      return "col-span-1";
    case "medium":
      return "col-span-1 lg:col-span-1";
    case "large":
      return "col-span-1 lg:col-span-2";
    case "full":
      return "col-span-1 lg:col-span-3";
    default:
      return "col-span-1";
  }
}

export default function Dashboard() {
  const [widgetSelectorOpen, setWidgetSelectorOpen] = useState(false);
  const [kpiSelectorOpen, setKPISelectorOpen] = useState(false);

  const { preferences, isLoading: prefsLoading, updatePreferences } = usePreferences();
  const { visibleKPIs, updateKPIs } = useKPIs();
  const { widgets, enabledWidgets, updateWidgets } = useWidgets();

  const { data: summary, isLoading: dataLoading } = useQuery<DashboardBundle>({
    queryKey: [DASHBOARD_PATH],
    queryFn: () => fetchJson<DashboardBundle>(DASHBOARD_PATH),
  });

  const handleSaveWidgets = async (newWidgets: WidgetConfig[]) => {
    await updateWidgets(newWidgets);
    setWidgetSelectorOpen(false);
  };

  const handleSaveKPIs = async (kpis: KPIType[]) => {
    await updateKPIs(kpis);
    setKPISelectorOpen(false);
  };

  const isLoading = prefsLoading || dataLoading;

  const kpiWidget = enabledWidgets.find((w) => w.type === "kpi_card");
  const otherWidgets = enabledWidgets.filter((w) => w.type !== "kpi_card");

  return (
    <PageLayout
      title="Dashboard"
      description="Your personalized command center"
      showSidebarTrigger={false}
      headerAction={
        <Button
          variant="outline"
          size="sm"
          onClick={() => setWidgetSelectorOpen(true)}
          data-testid="button-customize-dashboard"
        >
          <Settings2 className="h-4 w-4 mr-2" />
          Customize
        </Button>
      }
    >
      <div className="space-y-6">
        {isLoading ? (
          <div className="space-y-4">
            <div className="flex gap-4">
              {[1, 2, 3, 4].map((i) => (
                <Skeleton key={i} className="h-20 w-40" />
              ))}
            </div>
            <Skeleton className="h-[400px] w-full" />
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              <Skeleton className="h-64 lg:col-span-2" />
              <Skeleton className="h-64" />
            </div>
          </div>
        ) : (
          <>
            {kpiWidget && kpiWidget.enabled && (
              <KPIRibbonWidget
                visibleKPIs={visibleKPIs}
                onConfigureClick={() => setKPISelectorOpen(true)}
              />
            )}

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              {otherWidgets.map((widget) => (
                <div
                  key={widget.id}
                  className={getWidgetGridClass(widget.size)}
                  data-testid={`widget-container-${widget.type}`}
                >
                  <WidgetRenderer widget={widget} />
                </div>
              ))}
            </div>

            {enabledWidgets.length === 0 && (
              <div className="text-center py-12">
                <p className="text-muted-foreground mb-4">
                  No widgets enabled. Customize your dashboard to add widgets.
                </p>
                <Button onClick={() => setWidgetSelectorOpen(true)}>
                  <Settings2 className="h-4 w-4 mr-2" />
                  Add Widgets
                </Button>
              </div>
            )}
          </>
        )}
      </div>

      <WidgetSelector
        open={widgetSelectorOpen}
        onClose={() => setWidgetSelectorOpen(false)}
        widgets={widgets}
        onSave={handleSaveWidgets}
      />

      <KPISelector
        open={kpiSelectorOpen}
        onClose={() => setKPISelectorOpen(false)}
        selectedKPIs={visibleKPIs}
        onSave={handleSaveKPIs}
      />
    </PageLayout>
  );
}
