// The legacy AnalysisWorkspace lives in workflows.tsx but isn't exported.
// We inline a lightweight proxy to render it by dynamic import to avoid circular export.
import React, { lazy, Suspense } from "react";
import type { Workflow } from "@/pages/workflows";

const AnalysisWorkspaceLazy = lazy(() =>
  import("@/pages/workflows").then((mod: any) => ({ default: mod.AnalysisWorkspace }))
);

// Wrap the existing AnalysisWorkspace visuals as a report
export function VisualAnalyticsReport({ workflows }: { workflows: Workflow[] }) {
  // For this embedded report, scripts/timeline/stat inputs can be empty; the component
  // will show visuals based on the props provided. We pass minimal safe defaults.
  return (
    <div className="space-y-2">
      <Suspense fallback={<div className="text-sm text-muted-foreground">Loading visuals…</div>}>
        <AnalysisWorkspaceLazy
          workflows={workflows as any}
          scripts={[] as any}
          automationStats={{
            totalFlows: workflows.length,
            activeFlows: workflows.length,
            draftFlows: 0,
            totalRuns: 0,
          } as any}
          scriptStats={{ totalScripts: 0, draftScripts: 0 } as any}
          timeline={[] as any}
        />
      </Suspense>
    </div>
  );
}


