import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { GlassPanel } from "@/components/radiant/glass-panel";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { fetchFlowsOverview } from "@/lib/reports/flowsRepo";
import { fetchExecutions, fetchFlowExecutions, fetchRunningExecutions } from "@/lib/reports/executionsRepo";
import type { WorkflowRef } from "./reportRegistry";

export function OverviewReport({ flowId }: { flowId?: string }) {
  const flowsOverviewQuery = useQuery({
    queryKey: ["reports", "overview", "flows", flowId ?? "all"],
    queryFn: () => fetchFlowsOverview({ limit: 200 }),
    staleTime: 30_000,
  });

  const executionsQuery = useQuery({
    queryKey: ["reports", "overview", "executions", flowId ?? "all"],
    queryFn: () =>
      flowId
        ? fetchFlowExecutions(flowId, { limit: 50, offset: 0 })
        : fetchExecutions({ limit: 50, offset: 0 }),
    staleTime: 15_000,
  });

  const runningQuery = useQuery({
    queryKey: ["reports", "overview", "running", flowId ?? "all"],
    queryFn: () => fetchRunningExecutions(flowId ? { flow_id: flowId } : undefined),
    staleTime: 10_000,
  });

  const stats = flowsOverviewQuery.data?.stats;
  const executions = executionsQuery.data?.executions ?? [];
  const runningCount = runningQuery.data?.count ?? 0;

  return (
    <div className="space-y-4">
      <GlassPanel className="p-4 space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs uppercase tracking-wide text-muted-foreground">Overview</p>
            <h2 className="text-lg font-semibold">{flowId ? "Per-flow" : "All flows"}</h2>
          </div>
          {executionsQuery.isFetching && <Badge variant="outline">Refreshing…</Badge>}
        </div>

        <div className="grid gap-3 md:grid-cols-4">
          <OverviewStat
            label="Flows"
            value={
              flowId
                ? 1
                : stats?.total ??
                  (flowsOverviewQuery.data?.flows ? flowsOverviewQuery.data.flows.length : undefined)
            }
          />
          <OverviewStat label="Active" value={flowId ? undefined : stats?.active} />
          <OverviewStat label="Published" value={flowId ? undefined : stats?.published} />
          <OverviewStat label="Running now" value={runningCount} />
        </div>

        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="font-semibold text-sm">Recent executions</h3>
            <Badge variant="outline" className="text-[11px]">
              {executions.length} shown
            </Badge>
          </div>
          <ScrollArea className="rounded-md border max-h-[360px]">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>ID</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Trigger</TableHead>
                  <TableHead>Flow</TableHead>
                  <TableHead>Started</TableHead>
                  <TableHead>Duration (ms)</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {executions.map((exe) => (
                  <TableRow key={exe.id}>
                    <TableCell className="font-mono text-xs truncate max-w-[160px]" title={exe.id}>
                      {exe.id}
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline" className="text-[11px]">
                        {exe.status || "unknown"}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">{exe.trigger_source || "—"}</TableCell>
                    <TableCell className="text-xs">{exe.flow_name || exe.flow_id || "—"}</TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {exe.started_at ? new Date(exe.started_at).toLocaleString() : "—"}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {typeof exe.duration_ms === "number" ? exe.duration_ms : "—"}
                    </TableCell>
                  </TableRow>
                ))}
                {executions.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={6} className="text-center text-sm text-muted-foreground py-6">
                      No executions found for this scope.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </ScrollArea>
        </div>
      </GlassPanel>
    </div>
  );
}

function OverviewStat({ label, value }: { label: string; value?: number }) {
  return (
    <GlassPanel className="p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="text-2xl font-semibold mt-1">{value !== undefined ? value.toLocaleString() : "—"}</p>
    </GlassPanel>
  );
}


