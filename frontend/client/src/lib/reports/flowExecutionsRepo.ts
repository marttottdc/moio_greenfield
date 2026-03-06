import { apiV1 } from "@/lib/api";
import { fetchJson } from "@/lib/queryClient";

export interface FlowExecutionReportItem {
  id: string;
  flow_id: string;
  flow_name?: string;
  status?: string;
  status_display?: string;
  execution_mode?: string;
  trigger_source?: string;
  duration_ms?: number;
  started_at?: string;
  completed_at?: string;
  trace_id?: string;
  context?: any;
}

interface FlowExecutionsListResponse {
  ok?: boolean;
  total?: number;
  limit?: number;
  offset?: number;
  executions?: any[];
  results?: any[];
  data?: any[];
}

function extractList(raw: FlowExecutionsListResponse | any): any[] {
  if (!raw) return [];
  if (Array.isArray(raw)) return raw;
  if (Array.isArray(raw.executions)) return raw.executions;
  if (Array.isArray(raw.results)) return raw.results;
  if (Array.isArray(raw.data)) return raw.data;
  return [];
}

export function normalizeFlowExecutionReportItem(raw: any): FlowExecutionReportItem {
  return {
    id: String(raw?.id ?? ""),
    flow_id: String(raw?.flow_id ?? raw?.flow__id ?? ""),
    flow_name: typeof raw?.flow_name === "string" ? raw.flow_name : (typeof raw?.flow__name === "string" ? raw.flow__name : undefined),
    status: typeof raw?.status === "string" ? raw.status : undefined,
    status_display: typeof raw?.status_display === "string" ? raw.status_display : undefined,
    execution_mode: typeof raw?.execution_mode === "string" ? raw.execution_mode : (typeof raw?.context?.execution_mode === "string" ? raw.context.execution_mode : undefined),
    trigger_source: typeof raw?.trigger_source === "string" ? raw.trigger_source : undefined,
    duration_ms: typeof raw?.duration_ms === "number" ? raw.duration_ms : undefined,
    started_at: typeof raw?.started_at === "string" ? raw.started_at : (typeof raw?.created_at === "string" ? raw.created_at : undefined),
    completed_at: typeof raw?.completed_at === "string" ? raw.completed_at : (typeof raw?.finished_at === "string" ? raw.finished_at : undefined),
    trace_id: typeof raw?.trace_id === "string" ? raw.trace_id : undefined,
    context: raw?.context,
  };
}

export async function fetchFlowExecutionsForReports(params: {
  flowId?: string;
  limit?: number;
  offset?: number;
  status?: string;
  trigger_source?: string;
  execution_mode?: string;
}) {
  const limit = Math.max(1, Math.min(1000, params.limit ?? 200));
  const offset = Math.max(0, params.offset ?? 0);

  const query: Record<string, any> = { limit, offset };
  if (params.flowId) query.flow_id = params.flowId;
  if (params.status) query.status = params.status;
  if (params.trigger_source) query.trigger_source = params.trigger_source;
  if (params.execution_mode) query.execution_mode = params.execution_mode;

  const raw = await fetchJson<FlowExecutionsListResponse>(apiV1("/flows/executions/"), query);
  const list = extractList(raw).map(normalizeFlowExecutionReportItem).filter((e) => e.id);

  return {
    items: list,
    total: typeof (raw as any)?.total === "number" ? (raw as any).total : undefined,
    limit: typeof (raw as any)?.limit === "number" ? (raw as any).limit : limit,
    offset: typeof (raw as any)?.offset === "number" ? (raw as any).offset : offset,
  };
}


