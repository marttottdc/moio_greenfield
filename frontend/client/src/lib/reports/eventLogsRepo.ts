import { apiV1 } from "@/lib/api";
import { fetchJson } from "@/lib/queryClient";

export interface EventLog {
  id: string;
  name?: string;
  tenant_id?: string;
  actor?: { type?: string; id?: string };
  entity?: { type?: string; id?: string };
  payload?: any;
  occurred_at?: string;
  created_at?: string;
  correlation_id?: string;
  source?: string;
  routed?: boolean;
  routed_at?: string;
  flow_executions?: string[];
}

export interface EventLogsListResponse {
  logs: EventLog[];
  count?: number;
  total?: number;
  limit: number;
  offset: number;
}

function normalizeLog(raw: any): EventLog | null {
  if (!raw || typeof raw !== "object") return null;
  const id = raw.id ?? raw.log_id;
  if (!id) return null;
  return {
    id: String(id),
    name: typeof raw.name === "string" ? raw.name : undefined,
    tenant_id: raw.tenant_id ? String(raw.tenant_id) : undefined,
    actor: raw.actor && typeof raw.actor === "object" ? { type: raw.actor.type, id: raw.actor.id ? String(raw.actor.id) : undefined } : undefined,
    entity: raw.entity && typeof raw.entity === "object" ? { type: raw.entity.type, id: raw.entity.id ? String(raw.entity.id) : undefined } : undefined,
    payload: raw.payload,
    occurred_at: typeof raw.occurred_at === "string" ? raw.occurred_at : undefined,
    created_at: typeof raw.created_at === "string" ? raw.created_at : undefined,
    correlation_id: raw.correlation_id ? String(raw.correlation_id) : undefined,
    source: typeof raw.source === "string" ? raw.source : undefined,
    routed: typeof raw.routed === "boolean" ? raw.routed : undefined,
    routed_at: typeof raw.routed_at === "string" ? raw.routed_at : undefined,
    flow_executions: Array.isArray(raw.flow_executions) ? raw.flow_executions.map((x: any) => String(x)) : [],
  };
}

function extractLogs(raw: any): any[] {
  if (!raw) return [];
  if (Array.isArray(raw)) return raw;
  if (Array.isArray(raw.logs)) return raw.logs;
  if (Array.isArray(raw.results)) return raw.results;
  if (Array.isArray(raw.data)) return raw.data;
  return [];
}

export async function fetchEventLogs(params?: {
  limit?: number;
  offset?: number;
  name?: string;
  entity_type?: string;
  entity_id?: string;
  routed?: boolean;
}) {
  const limit = Math.max(1, Math.min(200, params?.limit ?? 50));
  const offset = Math.max(0, params?.offset ?? 0);
  const query: Record<string, string> = { limit: String(limit), offset: String(offset) };
  if (params?.name) query.name = params.name;
  if (params?.entity_type) query.entity_type = params.entity_type;
  if (params?.entity_id) query.entity_id = params.entity_id;
  if (params?.routed !== undefined) query.routed = String(params.routed);

  const raw = await fetchJson<any>(apiV1("/flows/event-logs/"), query);
  const logs = extractLogs(raw).map(normalizeLog).filter(Boolean) as EventLog[];
  return {
    logs,
    count: typeof raw?.count === "number" ? raw.count : logs.length,
    total: typeof raw?.total === "number" ? raw.total : undefined,
    limit,
    offset,
  } as EventLogsListResponse;
}

export async function fetchEventLogDetail(id: string): Promise<EventLog | null> {
  const raw = await fetchJson<any>(apiV1(`/flows/event-logs/${id}/`));
  const log = normalizeLog(raw?.log ?? raw);
  return log;
}


