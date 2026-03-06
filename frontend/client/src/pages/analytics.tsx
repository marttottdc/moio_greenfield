import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useWorkflowsData } from "@/pages/workflows/hooks/useWorkflowsData";
import { ReportsHubWorkspace } from "@/pages/workflows/reports/ReportsHubWorkspace";
import { GlassPanel } from "@/components/radiant/glass-panel";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { fetchFlowsOverview } from "@/lib/reports/flowsRepo";
import { fetchExecutions, fetchFlowExecutions, fetchRunningExecutions, fetchFlowExecutionStats } from "@/lib/reports/executionsRepo";
import { fetchEventLogs, fetchEventLogDetail, type EventLog } from "@/lib/reports/eventLogsRepo";
import { fetchTaskExecutions, fetchTaskExecutionsStats } from "@/lib/reports/taskExecutionsRepo";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

export default function Analytics() {
  const { workflows, isLoading } = useWorkflowsData(1, 200);
  const [flowId, setFlowId] = useState<string | null>(null);

  const flowOptions = useMemo(
    () => workflows.map((w) => ({ id: w.id, name: w.name || w.id })),
    [workflows]
  );

  // Global or per-flow data
  const flowsOverviewQuery = useQuery({
    queryKey: ["analytics", "flows-overview"],
    queryFn: () => fetchFlowsOverview({ limit: 200 }),
    staleTime: 30_000,
  });

  const executionsQuery = useQuery({
    queryKey: ["analytics", "executions", flowId ?? "all"],
    queryFn: () =>
      flowId
        ? fetchFlowExecutions(flowId, { limit: 200, offset: 0 })
        : fetchExecutions({ limit: 200, offset: 0 }),
    enabled: true,
    staleTime: 15_000,
  });

  const runningQuery = useQuery({
    queryKey: ["analytics", "running", flowId ?? "all"],
    queryFn: () =>
      fetchRunningExecutions(flowId ? { flow_id: flowId } : undefined),
    staleTime: 10_000,
  });

  const flowStatsQuery = useQuery({
    queryKey: ["analytics", "flow-stats", flowId ?? "all"],
    queryFn: () => fetchFlowExecutionStats(flowId!, { days: 7 }),
    enabled: Boolean(flowId),
    staleTime: 30_000,
  });

  const flowRunsQuery = useQuery({
    queryKey: ["analytics", "flow-runs", flowId ?? "all"],
    queryFn: () => fetchFlowExecutions(flowId!, { limit: 20, offset: 0 }),
    enabled: Boolean(flowId),
    staleTime: 15_000,
  });

  const stats = flowsOverviewQuery.data?.stats;
  const selectedFlow = flowId ? flowOptions.find((f) => f.id === flowId) : null;
  const executions = executionsQuery.data?.executions ?? [];
  const runningCount = runningQuery.data?.count ?? 0;
  const monthlyStats = useMemo(() => groupExecutionsByMonth(executions), [executions]);

  const eventLogsQuery = useQuery({
    queryKey: ["analytics", "event-logs", flowId ?? "all"],
    queryFn: () => fetchEventLogs({ limit: 20, offset: 0 }),
    staleTime: 15_000,
  });

  const taskStatsQuery = useQuery({
    queryKey: ["analytics", "task-stats"],
    queryFn: () => fetchTaskExecutionsStats(),
    staleTime: 30_000,
  });

  const taskExecutionsQuery = useQuery({
    queryKey: ["analytics", "task-executions"],
    queryFn: () => fetchTaskExecutions({ limit: 20, offset: 0 }),
    staleTime: 15_000,
  });

  const [selectedLog, setSelectedLog] = useState<EventLog | null>(null);
  const [logDetail, setLogDetail] = useState<EventLog | null>(null);
  const logDetailQueryEnabled = selectedLog != null;

  useQuery({
    queryKey: ["analytics", "event-log-detail", selectedLog?.id],
    queryFn: () => fetchEventLogDetail(selectedLog!.id),
    enabled: logDetailQueryEnabled,
    onSuccess: (data) => setLogDetail(data),
  });

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <p className="text-xs uppercase tracking-wide text-muted-foreground">Analytics</p>
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-semibold">Analytics & Reports</h1>
          <Badge variant="outline" className="text-[11px]">Beta</Badge>
        </div>
        <p className="text-sm text-muted-foreground">
          Overview, reports, logs, and task monitors. Select a flow for per-flow analytics, or leave empty for all flows.
        </p>
      </div>

      <GlassPanel className="p-4 space-y-3">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="space-y-1">
            <Label className="text-xs">Flow scope (optional)</Label>
            {isLoading ? (
              <Skeleton className="h-9 w-60" />
            ) : (
              <Select
                value={flowId ?? "all"}
                onValueChange={(v) => setFlowId(v === "all" ? null : v)}
              >
                <SelectTrigger className="w-60">
                  <SelectValue placeholder="All flows" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All flows</SelectItem>
                  {flowOptions.map((f) => (
                    <SelectItem key={f.id} value={f.id}>
                      {f.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
            <p className="text-xs text-muted-foreground">
              This selector will be reused across reports to switch between global and per-flow mode.
            </p>
          </div>
        </div>
      </GlassPanel>

      <GlassPanel className="p-4 space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs uppercase tracking-wide text-muted-foreground">Overview</p>
            <h2 className="text-lg font-semibold">
              {selectedFlow ? `Flow: ${selectedFlow.name}` : "All flows"}
            </h2>
          </div>
          {executionsQuery.isFetching && <Badge variant="outline">Refreshing…</Badge>}
        </div>

        <div className="grid gap-3 md:grid-cols-4">
          <OverviewStat
            label="Flows"
            value={
              selectedFlow
                ? 1
                : stats?.total ??
                  (flowsOverviewQuery.data?.flows ? flowsOverviewQuery.data.flows.length : undefined)
            }
          />
          <OverviewStat label="Active" value={selectedFlow ? undefined : stats?.active} />
          <OverviewStat label="Published" value={selectedFlow ? undefined : stats?.published} />
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

        {monthlyStats.length > 0 && (
          <div className="space-y-2">
            <h3 className="font-semibold text-sm">Execution timeline (monthly)</h3>
            <ScrollArea className="rounded-md border max-h-[220px]">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Month</TableHead>
                    <TableHead>Total</TableHead>
                    <TableHead>Success</TableHead>
                    <TableHead>Failed</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {monthlyStats.map((m) => (
                    <TableRow key={m.month}>
                      <TableCell className="text-xs">{m.month}</TableCell>
                      <TableCell className="text-xs">{m.total}</TableCell>
                      <TableCell className="text-xs text-emerald-600">{m.success}</TableCell>
                      <TableCell className="text-xs text-destructive">{m.failed}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </ScrollArea>
          </div>
        )}
      </GlassPanel>

      <GlassPanel className="p-4 space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs uppercase tracking-wide text-muted-foreground">Flow analytics</p>
            <h2 className="text-lg font-semibold">Per-flow stats & runs</h2>
          </div>
          {!flowId && <Badge variant="outline">Select a flow</Badge>}
        </div>

        {!flowId ? (
          <GlassPanel className="p-4">
            <p className="text-sm text-muted-foreground">Select a flow above to view per-flow analytics.</p>
          </GlassPanel>
        ) : (
          <>
            <div className="grid gap-3 md:grid-cols-4">
              <OverviewStat label="Window total" value={flowStatsQuery.data?.total_window} />
              <OverviewStat
                label="Success rate (%)"
                value={
                  flowStatsQuery.data?.success_rate !== undefined && flowStatsQuery.data?.success_rate !== null
                    ? Math.round(flowStatsQuery.data!.success_rate! * 100)
                    : undefined
                }
              />
              <OverviewStat label="Avg duration (ms)" value={flowStatsQuery.data?.avg_duration_ms ?? undefined} />
              <OverviewStat label="Window days" value={flowStatsQuery.data?.window_days ?? 7} />
            </div>

            <div className="space-y-2">
              <h3 className="font-semibold text-sm">Runs (latest)</h3>
              <ScrollArea className="rounded-md border max-h-[360px]">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>ID</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Trigger</TableHead>
                      <TableHead>Started</TableHead>
                      <TableHead>Duration (ms)</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {(flowRunsQuery.data?.executions ?? []).map((exe) => (
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
                        <TableCell className="text-xs text-muted-foreground">
                          {exe.started_at ? new Date(exe.started_at).toLocaleString() : "—"}
                        </TableCell>
                        <TableCell className="text-xs text-muted-foreground">
                          {typeof exe.duration_ms === "number" ? exe.duration_ms : "—"}
                        </TableCell>
                      </TableRow>
                    ))}
                    {(flowRunsQuery.data?.executions ?? []).length === 0 && (
                      <TableRow>
                        <TableCell colSpan={5} className="text-center text-sm text-muted-foreground py-6">
                          No executions found for this flow.
                        </TableCell>
                      </TableRow>
                    )}
                  </TableBody>
                </Table>
              </ScrollArea>
            </div>
          </>
        )}
      </GlassPanel>

      <GlassPanel className="p-4 space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs uppercase tracking-wide text-muted-foreground">Event logs</p>
            <h3 className="text-lg font-semibold">Inbound events audit</h3>
            <p className="text-xs text-muted-foreground">Source events, routing status, correlation IDs.</p>
          </div>
          <Button variant="outline" size="sm" onClick={() => eventLogsQuery.refetch()} disabled={eventLogsQuery.isFetching}>
            {eventLogsQuery.isFetching ? "Refreshing…" : "Refresh"}
          </Button>
        </div>

        <ScrollArea className="rounded-md border max-h-[360px]">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>ID</TableHead>
                <TableHead>Name</TableHead>
                <TableHead>Entity</TableHead>
                <TableHead>Routed</TableHead>
                <TableHead>Occurred</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(eventLogsQuery.data?.logs ?? []).map((log) => (
                <TableRow
                  key={log.id}
                  className="cursor-pointer"
                  onClick={() => {
                    setSelectedLog(log);
                    setLogDetail(null);
                  }}
                >
                  <TableCell className="font-mono text-xs truncate max-w-[140px]" title={log.id}>
                    {log.id}
                  </TableCell>
                  <TableCell className="text-xs">{log.name || "—"}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {log.entity?.type ? `${log.entity.type}:${log.entity.id ?? "?"}` : "—"}
                  </TableCell>
                  <TableCell>
                    <Badge variant={log.routed ? "default" : "outline"} className="text-[11px]">
                      {log.routed ? "routed" : "pending"}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {log.occurred_at ? new Date(log.occurred_at).toLocaleString() : "—"}
                  </TableCell>
                </TableRow>
              ))}
              {(eventLogsQuery.data?.logs ?? []).length === 0 && (
                <TableRow>
                  <TableCell colSpan={5} className="text-center text-sm text-muted-foreground py-6">
                    No event logs found.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </ScrollArea>
      </GlassPanel>

      <GlassPanel className="p-4 space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs uppercase tracking-wide text-muted-foreground">Scheduled tasks</p>
            <h3 className="text-lg font-semibold">Task executions</h3>
            <p className="text-xs text-muted-foreground">Scheduled/triggered tasks, durations, and failures.</p>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              taskStatsQuery.refetch();
              taskExecutionsQuery.refetch();
            }}
            disabled={taskExecutionsQuery.isFetching}
          >
            {taskExecutionsQuery.isFetching ? "Refreshing…" : "Refresh"}
          </Button>
        </div>

        <div className="grid gap-3 md:grid-cols-4">
          <OverviewStat label="Total" value={taskStatsQuery.data?.total} />
          <OverviewStat
            label="Failed"
            value={
              taskStatsQuery.data?.by_status
                ? (taskStatsQuery.data.by_status.failed ?? 0)
                : undefined
            }
          />
          <OverviewStat
            label="Avg duration (ms)"
            value={taskStatsQuery.data?.avg_duration_ms ?? undefined}
          />
          <OverviewStat
            label="Recent failures (24h)"
            value={taskStatsQuery.data?.recent_failures_24h ?? undefined}
          />
        </div>

        <ScrollArea className="rounded-md border max-h-[360px]">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>ID</TableHead>
                <TableHead>Task</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Started</TableHead>
                <TableHead>Duration (ms)</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(taskExecutionsQuery.data?.executions ?? []).map((task) => (
                <TableRow key={task.id}>
                  <TableCell className="font-mono text-xs truncate max-w-[140px]" title={task.id}>
                    {task.id}
                  </TableCell>
                  <TableCell className="text-xs">
                    {task.task_name || task.scheduled_task_name || "—"}
                  </TableCell>
                  <TableCell>
                    <Badge variant={task.status === "failed" ? "destructive" : "outline"} className="text-[11px]">
                      {task.status || "unknown"}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {task.started_at ? new Date(task.started_at).toLocaleString() : "—"}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {typeof task.duration_ms === "number" ? task.duration_ms : "—"}
                  </TableCell>
                </TableRow>
              ))}
              {(taskExecutionsQuery.data?.executions ?? []).length === 0 && (
                <TableRow>
                  <TableCell colSpan={5} className="text-center text-sm text-muted-foreground py-6">
                    No task executions found.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </ScrollArea>
      </GlassPanel>

      <Dialog open={Boolean(selectedLog)} onOpenChange={(open) => !open && setSelectedLog(null)}>
        <DialogContent className="max-w-3xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="text-base flex items-center gap-2">
              Event log
              {selectedLog?.name && <Badge variant="outline">{selectedLog.name}</Badge>}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-2">
            <div className="text-xs text-muted-foreground">
              {selectedLog?.occurred_at ? new Date(selectedLog.occurred_at).toLocaleString() : "—"}
            </div>
            <pre className="text-xs bg-muted/50 p-3 rounded-md border overflow-x-auto">
              {(() => {
                try {
                  return JSON.stringify(logDetail ?? selectedLog, null, 2);
                } catch {
                  return String(logDetail ?? selectedLog);
                }
              })()}
            </pre>
          </div>
        </DialogContent>
      </Dialog>

      <ReportsHubWorkspace workflows={flowOptions} whatsappTemplates={[]} />
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

type MonthlyStat = {
  month: string;
  total: number;
  success: number;
  failed: number;
};

function groupExecutionsByMonth(executions: { status?: string; started_at?: string }[]): MonthlyStat[] {
  const bucket = new Map<string, { total: number; success: number; failed: number }>();
  for (const exe of executions) {
    if (!exe.started_at) continue;
    const d = new Date(exe.started_at);
    if (Number.isNaN(d.getTime())) continue;
    const monthKey = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
    const rec = bucket.get(monthKey) ?? { total: 0, success: 0, failed: 0 };
    rec.total += 1;
    const status = (exe.status || "").toLowerCase();
    if (status === "success") rec.success += 1;
    if (status === "failed" || status === "error") rec.failed += 1;
    bucket.set(monthKey, rec);
  }
  return Array.from(bucket.entries())
    .map(([month, rec]) => ({ month, ...rec }))
    .sort((a, b) => (a.month < b.month ? 1 : -1))
    .slice(0, 12);
}

