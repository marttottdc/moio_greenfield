import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { CheckCircle, Clock, PlayCircle, TrendingUp } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { GlassPanel } from "@/components/radiant/glass-panel";
import { EmptyState } from "@/components/empty-state";
import { StatCard } from "@/pages/workflows/components/StatCard";
import { apiV1 } from "@/lib/api";
import { fetchJson } from "@/lib/queryClient";
import { fetchFlowExecutionsForReports } from "@/lib/reports/flowExecutionsRepo";

type WorkflowRef = { id: string; name: string };

type FlowStats = {
  total_all_time: number;
  total_window: number;
  by_status: Record<string, number>;
  by_trigger_source: Record<string, number>;
  avg_duration_ms: number | null;
  success_rate: number | null;
  latest_runs: Array<{
    id: string;
    status: string;
    trigger_source?: string;
    duration_ms?: number | null;
    started_at?: string;
    completed_at?: string;
  }>;
};

export function FlowExecutionsReport({ workflows }: { workflows: WorkflowRef[] }) {
  const [flowId, setFlowId] = useState<string>("");
  const [days, setDays] = useState<number>(7);
  const [fromDate, setFromDate] = useState<string>("");
  const [toDate, setToDate] = useState<string>("");
  const [runNonce, setRunNonce] = useState<number>(0);

  const runParams = useMemo(() => {
    if (!runNonce) return null;
    return {
      flowId: flowId || undefined,
      days: Math.max(1, Math.min(365, Number.isFinite(days) ? days : 7)),
      fromDate: fromDate || undefined,
      toDate: toDate || undefined,
      nonce: runNonce,
    };
  }, [flowId, days, fromDate, toDate, runNonce]);

  const selectedFlow = useMemo(() => workflows.find((w) => w.id === flowId) ?? null, [workflows, flowId]);

  // If a flow is selected, use backend stats endpoint (best fidelity).
  const statsQuery = useQuery({
    queryKey: ["reports", "flow-executions", "stats", runParams?.flowId, runParams?.days, runParams?.nonce],
    enabled: !!runParams?.nonce && !!runParams?.flowId,
    queryFn: () => fetchJson<FlowStats>(apiV1(`/flows/${runParams!.flowId}/executions/stats/`), { days: String(runParams!.days) }),
    staleTime: 0,
  });

  // Always fetch a list of executions we can show (even tenant-wide).
  const executionsQuery = useQuery({
    queryKey: ["reports", "flow-executions", "list", runParams],
    enabled: !!runParams?.nonce,
    queryFn: async () => {
      const res = await fetchFlowExecutionsForReports({ flowId: runParams?.flowId, limit: 200, offset: 0 });
      return res.items;
    },
    staleTime: 0,
  });

  const executions = useMemo(() => {
    const list = executionsQuery.data ?? [];
    const fromTs = runParams?.fromDate ? new Date(runParams.fromDate).getTime() : undefined;
    const toTs = runParams?.toDate ? new Date(runParams.toDate).getTime() : undefined;
    return list
      .filter((e) => {
        const ts = e.started_at ? new Date(e.started_at).getTime() : 0;
        if (fromTs && ts && ts < fromTs) return false;
        if (toTs && ts && ts > toTs) return false;
        return true;
      })
      .sort((a, b) => new Date(b.started_at ?? 0 as any).getTime() - new Date(a.started_at ?? 0 as any).getTime());
  }, [executionsQuery.data, runParams]);

  const derivedStats = useMemo(() => {
    const by_status: Record<string, number> = {};
    const by_trigger_source: Record<string, number> = {};
    let durationSum = 0;
    let durationCount = 0;

    for (const e of executions) {
      const s = String(e.status ?? "unknown").toLowerCase();
      by_status[s] = (by_status[s] ?? 0) + 1;
      const t = String(e.trigger_source ?? "unknown").toLowerCase();
      by_trigger_source[t] = (by_trigger_source[t] ?? 0) + 1;
      if (typeof e.duration_ms === "number" && e.duration_ms > 0) {
        durationSum += e.duration_ms;
        durationCount += 1;
      }
    }

    const total_window = executions.length;
    const success = (by_status.success ?? 0) + (by_status.succeeded ?? 0) + (by_status.ok ?? 0) + (by_status.completed ?? 0);
    const success_rate = total_window > 0 ? success / total_window : null;
    const avg_duration_ms = durationCount > 0 ? durationSum / durationCount : null;

    return { total_window, by_status, by_trigger_source, success_rate, avg_duration_ms };
  }, [executions]);

  const effectiveStats: FlowStats | null = useMemo(() => {
    if (statsQuery.data) return statsQuery.data;
    if (!runParams?.nonce) return null;
    return {
      total_all_time: 0,
      total_window: derivedStats.total_window,
      by_status: derivedStats.by_status,
      by_trigger_source: derivedStats.by_trigger_source,
      avg_duration_ms: derivedStats.avg_duration_ms,
      success_rate: derivedStats.success_rate,
      latest_runs: executions.slice(0, 20).map((e) => ({
        id: e.id,
        status: String(e.status ?? "unknown"),
        trigger_source: e.trigger_source,
        duration_ms: e.duration_ms ?? null,
        started_at: e.started_at,
        completed_at: e.completed_at,
      })),
    };
  }, [statsQuery.data, runParams, derivedStats, executions]);

  const isRunning = executionsQuery.isLoading || statsQuery.isLoading;

  const formatDuration = (ms?: number | null) => {
    if (!ms) return "-";
    if (ms < 1000) return `${Math.round(ms)}ms`;
    if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
    return `${(ms / 60000).toFixed(1)}m`;
  };

  return (
    <div className="space-y-6">
      <GlassPanel className="p-4 space-y-4" data-testid="flow-exec-report-filters">
        <div className="grid gap-3 lg:grid-cols-6">
          <div className="lg:col-span-2">
            <Label className="text-xs">Flow (optional)</Label>
            <select
              className="mt-1 w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
              value={flowId}
              onChange={(e) => setFlowId(e.target.value)}
              data-testid="select-flow-exec-report-flow"
            >
              <option value="">All flows</option>
              {workflows
                .slice()
                .sort((a, b) => a.name.localeCompare(b.name))
                .map((w) => (
                  <option key={w.id} value={w.id}>
                    {w.name}
                  </option>
                ))}
            </select>
          </div>

          <div>
            <Label className="text-xs">From</Label>
            <Input type="date" value={fromDate} onChange={(e) => setFromDate(e.target.value)} className="mt-1 h-9" />
          </div>
          <div>
            <Label className="text-xs">To</Label>
            <Input type="date" value={toDate} onChange={(e) => setToDate(e.target.value)} className="mt-1 h-9" />
          </div>

          <div>
            <Label className="text-xs">Days (stats)</Label>
            <Input
              type="number"
              min={1}
              max={365}
              value={String(days)}
              onChange={(e) => {
                const n = Number(e.target.value);
                if (!Number.isFinite(n)) return;
                setDays(Math.max(1, Math.min(365, n)));
              }}
              className="mt-1 h-9"
            />
          </div>

          <div className="flex items-end justify-end">
            <Button
              onClick={() => setRunNonce(Date.now())}
              disabled={isRunning}
              className="h-9 w-full"
              data-testid="button-flow-exec-report-generate"
            >
              {isRunning ? "Generating..." : "Generate"}
            </Button>
          </div>
        </div>

        {runParams?.nonce && (
          <div className="text-xs text-muted-foreground">
            Using <span className="font-medium text-foreground">{selectedFlow?.name ?? "All flows"}</span> ·{" "}
            {executions.length} executions scanned
            {!runParams.flowId && <span> · Stats are approximate (based on last 200 executions)</span>}
          </div>
        )}
      </GlassPanel>

      {isRunning ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <Skeleton className="h-24" />
          <Skeleton className="h-24" />
          <Skeleton className="h-24" />
          <Skeleton className="h-24" />
        </div>
      ) : effectiveStats ? (
        <>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <StatCard
              label="Runs (window)"
              value={String(effectiveStats.total_window ?? 0)}
              helper={runParams?.flowId ? `Last ${runParams?.days ?? 7}d` : "Based on scanned executions"}
              icon={PlayCircle}
              accent="bg-primary/10 text-primary"
            />
            <StatCard
              label="Success rate"
              value={
                effectiveStats.success_rate === null || effectiveStats.success_rate === undefined
                  ? "-"
                  : `${Math.round(effectiveStats.success_rate * 100)}%`
              }
              helper="Windowed"
              icon={CheckCircle}
              accent="bg-emerald-100 text-emerald-600 dark:bg-emerald-900/30"
            />
            <StatCard
              label="Avg duration"
              value={
                effectiveStats.avg_duration_ms === null || effectiveStats.avg_duration_ms === undefined
                  ? "-"
                  : formatDuration(effectiveStats.avg_duration_ms)
              }
              helper="Windowed"
              icon={Clock}
              accent="bg-indigo-100 text-indigo-600 dark:bg-indigo-900/30"
            />
            <StatCard
              label="Triggers"
              value={String(Object.keys(effectiveStats.by_trigger_source ?? {}).length)}
              helper="Distinct trigger sources"
              icon={TrendingUp}
              accent="bg-muted text-muted-foreground"
            />
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <GlassPanel className="p-4">
              <div className="flex items-center justify-between mb-3">
                <h3 className="font-semibold text-sm">By status (window)</h3>
              </div>
              <div className="grid grid-cols-2 gap-2 text-sm">
                {Object.entries(effectiveStats.by_status ?? {})
                  .sort((a, b) => b[1] - a[1])
                  .map(([k, v]) => (
                    <div key={k} className="flex items-center justify-between border rounded-md px-3 py-2">
                      <span className="capitalize">{k.replaceAll("_", " ")}</span>
                      <Badge variant="outline">{v}</Badge>
                    </div>
                  ))}
                {Object.keys(effectiveStats.by_status ?? {}).length === 0 && (
                  <div className="text-sm text-muted-foreground">No runs in window.</div>
                )}
              </div>
            </GlassPanel>

            <GlassPanel className="p-4">
              <div className="flex items-center justify-between mb-3">
                <h3 className="font-semibold text-sm">By trigger source (window)</h3>
              </div>
              <div className="grid grid-cols-2 gap-2 text-sm">
                {Object.entries(effectiveStats.by_trigger_source ?? {})
                  .sort((a, b) => b[1] - a[1])
                  .map(([k, v]) => (
                    <div key={k} className="flex items-center justify-between border rounded-md px-3 py-2">
                      <span className="capitalize">{k.replaceAll("_", " ")}</span>
                      <Badge variant="outline">{v}</Badge>
                    </div>
                  ))}
                {Object.keys(effectiveStats.by_trigger_source ?? {}).length === 0 && (
                  <div className="text-sm text-muted-foreground">No runs in window.</div>
                )}
              </div>
            </GlassPanel>
          </div>

          <GlassPanel className="p-4">
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-semibold text-sm">Latest runs</h3>
              <Badge variant="outline" className="text-[10px]">{effectiveStats.latest_runs?.length ?? 0} shown</Badge>
            </div>
            {(effectiveStats.latest_runs?.length ?? 0) === 0 ? (
              <EmptyState title="No runs" description="No executions found for the selected filters." />
            ) : (
              <div className="space-y-2">
                {effectiveStats.latest_runs.slice(0, 20).map((r) => (
                  <div key={r.id} className="flex items-center justify-between border rounded-md px-3 py-2 text-sm">
                    <div className="min-w-0">
                      <div className="font-medium truncate">{r.id.slice(0, 8)}…</div>
                      <div className="text-xs text-muted-foreground truncate">
                        {r.started_at ? new Date(r.started_at).toLocaleString() : "-"} · {r.trigger_source ?? "unknown"}
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge variant="outline" className="capitalize">
                        {String(r.status ?? "unknown").toLowerCase()}
                      </Badge>
                      <Badge variant="secondary" className="text-[10px]">
                        {r.duration_ms ? formatDuration(r.duration_ms) : "-"}
                      </Badge>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </GlassPanel>
        </>
      ) : (
        <GlassPanel className="p-6">
          <EmptyState title="Generate a report" description="Pick optional filters and click Generate." />
        </GlassPanel>
      )}
    </div>
  );
}


