import { apiV1 } from "@/lib/api";
import { fetchJson } from "@/lib/queryClient";

export type ExecutionStatus =
  | "running"
  | "pending"
  | "success"
  | "failed"
  | "timeout"
  | "cancelled"
  | string;

export interface FlowExecution {
  id: string;
  flow_id?: string;
  flow_name?: string;
  status?: ExecutionStatus;
  status_display?: string;
  execution_mode?: string;
  trigger_source?: string;
  sandbox?: boolean;
  duration_ms?: number;
  started_at?: string;
  completed_at?: string;
  input?: any;
  output?: any;
  error?: any;
  context?: any;
  timeline?: any[];
  graph_version?: string | null;
  version_id?: string | null;
  version_status?: string | null;
  trace_id?: string | null;
  webhook_id?: string | null;
  webhook_name?: string | null;
}

export interface ExecutionsListResponse {
  ok?: boolean;
  total?: number;
  count?: number;
  limit: number;
  offset: number;
  executions: FlowExecution[];
}

function normalizeExecution(raw: any): FlowExecution | null {
  if (!raw || typeof raw !== "object") return null;
  const id = raw.id ?? raw.execution_id;
  if (!id) return null;
  return {
    id: String(id),
    flow_id: raw.flow_id ? String(raw.flow_id) : undefined,
    flow_name: typeof raw.flow_name === "string" ? raw.flow_name : undefined,
    status: typeof raw.status === "string" ? (raw.status as ExecutionStatus) : undefined,
    status_display: typeof raw.status_display === "string" ? raw.status_display : undefined,
    execution_mode: typeof raw.execution_mode === "string" ? raw.execution_mode : undefined,
    trigger_source: typeof raw.trigger_source === "string" ? raw.trigger_source : undefined,
    sandbox: typeof raw.sandbox === "boolean" ? raw.sandbox : undefined,
    duration_ms: typeof raw.duration_ms === "number" ? raw.duration_ms : undefined,
    started_at: typeof raw.started_at === "string" ? raw.started_at : undefined,
    completed_at: typeof raw.completed_at === "string" ? raw.completed_at : undefined,
    input: raw.input,
    output: raw.output,
    error: raw.error,
    context: raw.context,
    timeline: Array.isArray(raw.timeline) ? raw.timeline : [],
    graph_version: raw.graph_version ? String(raw.graph_version) : null,
    version_id: raw.version_id ? String(raw.version_id) : null,
    version_status: typeof raw.version_status === "string" ? raw.version_status : null,
    trace_id: raw.trace_id ? String(raw.trace_id) : null,
    webhook_id: raw.webhook_id ? String(raw.webhook_id) : null,
    webhook_name: typeof raw.webhook_name === "string" ? raw.webhook_name : null,
  };
}

function extractExecutions(raw: any): any[] {
  if (!raw) return [];
  if (Array.isArray(raw)) return raw;
  if (Array.isArray(raw.executions)) return raw.executions;
  if (Array.isArray(raw.results)) return raw.results;
  if (Array.isArray(raw.data)) return raw.data;
  return [];
}

export async function fetchExecutions(params?: {
  limit?: number;
  offset?: number;
  status?: string;
  trigger_source?: string;
  execution_mode?: string;
  flow_id?: string;
}) {
  const limit = Math.max(1, Math.min(100, params?.limit ?? 50));
  const offset = Math.max(0, params?.offset ?? 0);
  const query: Record<string, string> = { limit: String(limit), offset: String(offset) };
  if (params?.status) query.status = params.status;
  if (params?.trigger_source) query.trigger_source = params.trigger_source;
  if (params?.execution_mode) query.execution_mode = params.execution_mode;
  if (params?.flow_id) query.flow_id = params.flow_id;

  const raw = await fetchJson<any>(apiV1("/flows/executions/"), query);
  const executions = extractExecutions(raw).map(normalizeExecution).filter(Boolean) as FlowExecution[];
  return {
    ok: Boolean(raw?.ok ?? true),
    total: typeof raw?.total === "number" ? raw.total : undefined,
    count: typeof raw?.count === "number" ? raw.count : undefined,
    limit,
    offset,
    executions,
  } as ExecutionsListResponse;
}

export async function fetchRunningExecutions(params?: { execution_mode?: string; flow_id?: string }) {
  const query: Record<string, string> = {};
  if (params?.execution_mode) query.execution_mode = params.execution_mode;
  if (params?.flow_id) query.flow_id = params.flow_id;
  const raw = await fetchJson<any>(apiV1("/flows/executions/running/"), query);
  const executions = extractExecutions(raw).map(normalizeExecution).filter(Boolean) as FlowExecution[];
  return {
    ok: Boolean(raw?.ok ?? true),
    count: typeof raw?.count === "number" ? raw.count : executions.length,
    executions,
  };
}

export async function fetchFlowExecutions(flowId: string, params?: { limit?: number; offset?: number; status?: string; trigger_source?: string; execution_mode?: string }) {
  const limit = Math.max(1, Math.min(100, params?.limit ?? 50));
  const offset = Math.max(0, params?.offset ?? 0);
  const query: Record<string, string> = { limit: String(limit), offset: String(offset) };
  if (params?.status) query.status = params.status;
  if (params?.trigger_source) query.trigger_source = params.trigger_source;
  if (params?.execution_mode) query.execution_mode = params.execution_mode;

  const raw = await fetchJson<any>(apiV1(`/flows/${flowId}/executions/`), query);
  const executions = extractExecutions(raw).map(normalizeExecution).filter(Boolean) as FlowExecution[];
  return {
    ok: Boolean(raw?.ok ?? true),
    total: typeof raw?.total === "number" ? raw.total : undefined,
    count: typeof raw?.count === "number" ? raw.count : undefined,
    limit,
    offset,
    executions,
  } as ExecutionsListResponse;
}

export interface FlowExecutionStats {
  ok?: boolean;
  flow_id?: string;
  window_days?: number;
  total_all_time?: number;
  total_window?: number;
  by_status?: Record<string, number>;
  by_trigger_source?: Record<string, number>;
  avg_duration_ms?: number | null;
  success_rate?: number | null;
  latest_runs?: FlowExecution[];
}

export async function fetchFlowExecutionStats(flowId: string, params?: { days?: number }) {
  const days = Math.max(1, Math.min(365, params?.days ?? 7));
  const raw = await fetchJson<any>(apiV1(`/flows/${flowId}/executions/stats/`), { days: String(days) });
  const latest_runs = Array.isArray(raw?.latest_runs) ? raw.latest_runs.map(normalizeExecution).filter(Boolean) as FlowExecution[] : [];
  return {
    ok: Boolean(raw?.ok ?? true),
    flow_id: raw?.flow_id ? String(raw.flow_id) : flowId,
    window_days: typeof raw?.window_days === "number" ? raw.window_days : days,
    total_all_time: typeof raw?.total_all_time === "number" ? raw.total_all_time : undefined,
    total_window: typeof raw?.total_window === "number" ? raw.total_window : undefined,
    by_status: typeof raw?.by_status === "object" ? raw.by_status : undefined,
    by_trigger_source: typeof raw?.by_trigger_source === "object" ? raw.by_trigger_source : undefined,
    avg_duration_ms: typeof raw?.avg_duration_ms === "number" ? raw.avg_duration_ms : null,
    success_rate: typeof raw?.success_rate === "number" ? raw.success_rate : null,
    latest_runs,
  } as FlowExecutionStats;
}


