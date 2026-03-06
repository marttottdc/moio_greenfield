import { apiV1 } from "@/lib/api";
import { fetchJson } from "@/lib/queryClient";

export interface FlowVersionSummary {
  id: string;
  flow_id?: string;
  version?: number;
  major?: number;
  minor?: number;
  label?: string;
  status?: string;
  status_display?: string;
  is_published?: boolean;
  is_testing?: boolean;
  is_draft?: boolean;
  is_archived?: boolean;
  is_active?: boolean;
  is_editable?: boolean;
  preview_armed?: boolean;
  preview_armed_at?: string | null;
  notes?: string;
  created_at?: string;
  updated_at?: string;
  published_at?: string | null;
}

export interface FlowSummary {
  id: string;
  name?: string;
  description?: string;
  status?: string;
  is_enabled?: boolean;
  execution_count?: number;
  last_executed_at?: string;
  last_execution_status?: string;
  created_at?: string;
  updated_at?: string;
  created_by?: { id?: string; name?: string } | null;
  current_version_id?: string;
  latest_version?: FlowVersionSummary | null;
  published_version?: FlowVersionSummary | null;
}

export interface FlowsListResponse {
  ok?: boolean;
  flows: FlowSummary[];
  stats?: {
    total?: number;
    active?: number;
    published?: number;
    drafts?: number;
  };
  total?: number;
  count?: number;
  limit?: number;
  offset?: number;
}

function normalizeVersion(raw: any): FlowVersionSummary | null {
  if (!raw || typeof raw !== "object") return null;
  return {
    id: String(raw.id ?? ""),
    flow_id: raw.flow_id ? String(raw.flow_id) : undefined,
    version: typeof raw.version === "number" ? raw.version : undefined,
    major: typeof raw.major === "number" ? raw.major : undefined,
    minor: typeof raw.minor === "number" ? raw.minor : undefined,
    label: typeof raw.label === "string" ? raw.label : undefined,
    status: typeof raw.status === "string" ? raw.status : undefined,
    status_display: typeof raw.status_display === "string" ? raw.status_display : undefined,
    is_published: Boolean(raw.is_published),
    is_testing: Boolean(raw.is_testing),
    is_draft: Boolean(raw.is_draft),
    is_archived: Boolean(raw.is_archived),
    is_active: Boolean(raw.is_active),
    is_editable: Boolean(raw.is_editable),
    preview_armed: Boolean(raw.preview_armed),
    preview_armed_at: typeof raw.preview_armed_at === "string" ? raw.preview_armed_at : null,
    notes: typeof raw.notes === "string" ? raw.notes : undefined,
    created_at: typeof raw.created_at === "string" ? raw.created_at : undefined,
    updated_at: typeof raw.updated_at === "string" ? raw.updated_at : undefined,
    published_at: typeof raw.published_at === "string" ? raw.published_at : null,
  };
}

function normalizeFlow(raw: any): FlowSummary | null {
  if (!raw || typeof raw !== "object") return null;
  const id = raw.id ?? raw.flow_id ?? raw.uuid;
  if (!id) return null;

  return {
    id: String(id),
    name: typeof raw.name === "string" ? raw.name : undefined,
    description: typeof raw.description === "string" ? raw.description : undefined,
    status: typeof raw.status === "string" ? raw.status : undefined,
    is_enabled: typeof raw.is_enabled === "boolean" ? raw.is_enabled : undefined,
    execution_count: typeof raw.execution_count === "number" ? raw.execution_count : undefined,
    last_executed_at: typeof raw.last_executed_at === "string" ? raw.last_executed_at : undefined,
    last_execution_status: typeof raw.last_execution_status === "string" ? raw.last_execution_status : undefined,
    created_at: typeof raw.created_at === "string" ? raw.created_at : undefined,
    updated_at: typeof raw.updated_at === "string" ? raw.updated_at : undefined,
    created_by: raw.created_by && typeof raw.created_by === "object"
      ? {
          id: raw.created_by.id ? String(raw.created_by.id) : undefined,
          name: typeof raw.created_by.name === "string" ? raw.created_by.name : undefined,
        }
      : null,
    current_version_id: raw.current_version_id ? String(raw.current_version_id) : undefined,
    latest_version: normalizeVersion(raw.latest_version),
    published_version: normalizeVersion(raw.published_version),
  };
}

function extractFlows(raw: any): any[] {
  if (!raw) return [];
  if (Array.isArray(raw)) return raw;
  if (Array.isArray(raw.flows)) return raw.flows;
  if (Array.isArray(raw.results)) return raw.results;
  if (Array.isArray(raw.data)) return raw.data;
  return [];
}

export async function fetchFlowsOverview(params?: { limit?: number; offset?: number }) {
  const limit = Math.max(1, Math.min(200, params?.limit ?? 50));
  const offset = Math.max(0, params?.offset ?? 0);
  const raw = await fetchJson<any>(apiV1("/flows/"), { limit: String(limit), offset: String(offset) });
  const flows = extractFlows(raw).map(normalizeFlow).filter(Boolean) as FlowSummary[];

  const stats = raw?.stats && typeof raw.stats === "object" ? {
    total: typeof raw.stats.total === "number" ? raw.stats.total : undefined,
    active: typeof raw.stats.active === "number" ? raw.stats.active : undefined,
    published: typeof raw.stats.published === "number" ? raw.stats.published : undefined,
    drafts: typeof raw.stats.drafts === "number" ? raw.stats.drafts : undefined,
  } : undefined;

  return {
    ok: Boolean(raw?.ok ?? true),
    flows,
    stats,
    total: typeof raw?.total === "number" ? raw.total : undefined,
    count: typeof raw?.count === "number" ? raw.count : undefined,
    limit,
    offset,
  } as FlowsListResponse;
}


