import { useMemo, useState } from "react";
import { FileText } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { GlassPanel } from "@/components/radiant/glass-panel";
import { reportRegistry, type ReportContextProps, type ReportId, type WorkflowRef, type TemplateRef } from "./reportRegistry";

export function ReportsHubWorkspace({
  workflows,
  whatsappTemplates,
  flowId,
}: {
  workflows: WorkflowRef[];
  whatsappTemplates: TemplateRef[];
  flowId?: string;
}) {
  const [activeReport, setActiveReport] = useState<ReportId | null>(null);

  const cards = useMemo(() => reportRegistry, []);

  const ActiveIcon = FileText;

  const ctx: ReportContextProps = useMemo(
    () => ({
      workflows,
      whatsappTemplates,
      flowId,
    }),
    [workflows, whatsappTemplates, flowId]
  );

  return (
    <div className="space-y-6">
      <div>
        <p className="text-xs uppercase tracking-wide text-muted-foreground">Reporting</p>
        <h2 className="text-2xl font-semibold">Reports</h2>
        <p className="text-sm text-muted-foreground mt-1">
          Choose a report. Each report can have its own filters and features.
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {cards.map((card) => {
              const Icon = card.icon;
          return (
            <GlassPanel
              key={card.id}
              className="p-6 space-y-4 hover-elevate cursor-pointer"
              onClick={() => setActiveReport(card.id)}
              data-testid={`report-card-${card.id}`}
            >
              <div className="flex items-start justify-between gap-4">
                <div className={`w-12 h-12 rounded-lg ${card.bgClass} flex items-center justify-center shrink-0`}>
                  <Icon className={`h-6 w-6 ${card.iconClass}`} />
                </div>
              </div>

              <div className="space-y-1">
                <h3 className="font-semibold">{card.label}</h3>
                <p className="text-sm text-muted-foreground line-clamp-3">{card.description}</p>
              </div>

              <div className="flex justify-end">
                <Button variant="outline" size="sm" onClick={() => setActiveReport(card.id)}>
                  Open
                </Button>
              </div>
            </GlassPanel>
          );
        })}
      </div>

      <Dialog open={!!activeReport} onOpenChange={(open) => !open && setActiveReport(null)}>
        <DialogContent className="max-w-5xl max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <ActiveIcon className="h-5 w-5 text-muted-foreground" />
              {activeReport === "whatsapp_templates"
                ? "WhatsApp Templates Report"
                : activeReport === "flow_executions"
                  ? "Flow Executions Report"
                  : activeReport === "whatsapp_logs"
                    ? "WhatsApp Logs"
                  : "Report"}
            </DialogTitle>
          </DialogHeader>

          {(() => {
            const def = cards.find((c) => c.id === activeReport);
            if (!def) return null;
            return def.render(ctx);
          })()}
        </DialogContent>
      </Dialog>
    </div>
  );
}


