import { apiV1 } from "@/lib/api";
import { fetchJson } from "@/lib/queryClient";

export interface TaskExecution {
  id: string;
  scheduled_task_id?: string;
  scheduled_task_name?: string;
  task_name?: string;
  status?: string;
  started_at?: string;
  finished_at?: string;
  duration_ms?: number;
  celery_task_id?: string;
  input_data?: any;
  result_data?: any;
  error_message?: string;
  trigger_type?: string;
}

export interface TaskExecutionsListResponse {
  executions: TaskExecution[];
  count?: number;
  total?: number;
  limit: number;
  offset: number;
}

export interface TaskExecutionsStats {
  total?: number;
  by_status?: Record<string, number>;
  avg_duration_ms?: number | null;
  recent_failures_24h?: number;
}

function normalizeTaskExecution(raw: any): TaskExecution | null {
  if (!raw || typeof raw !== "object") return null;
  const id = raw.id ?? raw.execution_id;
  if (!id) return null;
  return {
    id: String(id),
    scheduled_task_id: raw.scheduled_task_id ? String(raw.scheduled_task_id) : undefined,
    scheduled_task_name: typeof raw.scheduled_task_name === "string" ? raw.scheduled_task_name : undefined,
    task_name: typeof raw.task_name === "string" ? raw.task_name : undefined,
    status: typeof raw.status === "string" ? raw.status : undefined,
    started_at: typeof raw.started_at === "string" ? raw.started_at : undefined,
    finished_at: typeof raw.finished_at === "string" ? raw.finished_at : undefined,
    duration_ms: typeof raw.duration_ms === "number" ? raw.duration_ms : undefined,
    celery_task_id: raw.celery_task_id ? String(raw.celery_task_id) : undefined,
    input_data: raw.input_data ?? raw.input,
    result_data: raw.result_data ?? raw.result,
    error_message: typeof raw.error_message === "string" ? raw.error_message : undefined,
    trigger_type: typeof raw.trigger_type === "string" ? raw.trigger_type : undefined,
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

export async function fetchTaskExecutions(params?: {
  limit?: number;
  offset?: number;
  status?: string;
  task_id?: string;
  task_name?: string;
  trigger_type?: string;
  from_date?: string;
  to_date?: string;
}) {
  const limit = Math.max(1, Math.min(200, params?.limit ?? 50));
  const offset = Math.max(0, params?.offset ?? 0);
  const query: Record<string, string> = { limit: String(limit), offset: String(offset) };
  if (params?.status) query.status = params.status;
  if (params?.task_id) query.task_id = params.task_id;
  if (params?.task_name) query.task_name = params.task_name;
  if (params?.trigger_type) query.trigger_type = params.trigger_type;
  if (params?.from_date) query.from_date = params.from_date;
  if (params?.to_date) query.to_date = params.to_date;

  const raw = await fetchJson<any>(apiV1("/flows/task-executions/"), query);
  const executions = extractExecutions(raw).map(normalizeTaskExecution).filter(Boolean) as TaskExecution[];
  return {
    executions,
    count: typeof raw?.count === "number" ? raw.count : executions.length,
    total: typeof raw?.total === "number" ? raw.total : undefined,
    limit,
    offset,
  } as TaskExecutionsListResponse;
}

export async function fetchTaskExecutionsStats(): Promise<TaskExecutionsStats> {
  const raw = await fetchJson<any>(apiV1("/flows/task-executions/stats/"));
  return {
    total: typeof raw?.total === "number" ? raw.total : undefined,
    by_status: typeof raw?.by_status === "object" ? raw.by_status : undefined,
    avg_duration_ms: typeof raw?.avg_duration_ms === "number" ? raw.avg_duration_ms : null,
    recent_failures_24h: typeof raw?.recent_failures_24h === "number" ? raw.recent_failures_24h : undefined,
  };
}


