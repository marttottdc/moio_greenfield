import { apiV1 } from "@/lib/api";
import { fetchJson } from "@/lib/queryClient";

export interface ExecutionMessage {
  id: string;
  msg_id?: string;
  type?: string;
  status?: string;
  user_number?: string;
  recipient_id?: string;
  body?: string;
  api_response?: any;
  created?: string;
  updated?: string;
  timestamp?: string;
}

/** Event within a threaded execution-messages response (GET .../executions/<id>/messages/). */
export interface ExecutionThreadEvent {
  id: string;
  msg_id?: string | null;
  type?: string | null;
  status?: string | null;
  user_number?: string | null;
  recipient_id?: string | null;
  body?: string | null;
  api_response?: unknown;
  created?: string | null;
  updated?: string | null;
  timestamp?: string | null;
}

/** Thread keyed by msg_id from GET .../executions/<id>/messages/. */
export interface ExecutionThread {
  msg_id: string;
  first_seen_at?: string | null;
  last_seen_at?: string | null;
  latest_status?: string | null;
  events: ExecutionThreadEvent[];
}

export interface ExecutionMessagesResponse {
  ok?: boolean;
  execution_id?: string;
  flow_id?: string;
  flow_name?: string;
  seed_msg_ids_count?: number;
  /** Threads from backend (threads[]). */
  threads: ExecutionThread[];
  /** Flattened list for backward compatibility (one entry per thread event). */
  messages: ExecutionMessage[];
}

function normalizeMessage(raw: any): ExecutionMessage | null {
  if (!raw || typeof raw !== "object") return null;
  const id = raw.id ?? raw.msg_id ?? raw.message_id;
  if (!id) return null;
  return {
    id: String(id),
    msg_id: typeof raw.msg_id === "string" ? raw.msg_id : undefined,
    type: typeof raw.type === "string" ? raw.type : (typeof raw.message_type === "string" ? raw.message_type : undefined),
    status: typeof raw.status === "string" ? raw.status : undefined,
    user_number: typeof raw.user_number === "string" ? raw.user_number : undefined,
    recipient_id: typeof raw.recipient_id === "string" ? raw.recipient_id : undefined,
    body: typeof raw.body === "string" ? raw.body : undefined,
    api_response: raw.api_response ?? raw.apiResponse,
    created: typeof raw.created === "string" ? raw.created : (typeof raw.created_at === "string" ? raw.created_at : undefined),
    updated: typeof raw.updated === "string" ? raw.updated : (typeof raw.updated_at === "string" ? raw.updated_at : undefined),
    timestamp: typeof raw.timestamp === "string" ? raw.timestamp : undefined,
  };
}

function extractMessages(raw: any): any[] {
  if (!raw) return [];
  if (Array.isArray(raw)) return raw;
  if (Array.isArray(raw.messages)) return raw.messages;
  if (Array.isArray(raw.results)) return raw.results;
  if (Array.isArray(raw.data)) return raw.data;
  return [];
}

function normalizeThreadEvent(raw: any): ExecutionThreadEvent | null {
  if (!raw || typeof raw !== "object") return null;
  const id = raw.id ?? raw.msg_id ?? raw.message_id;
  if (id == null) return null;
  return {
    id: String(id),
    msg_id: raw.msg_id ?? null,
    type: raw.type ?? raw.message_type ?? null,
    status: raw.status ?? null,
    user_number: raw.user_number ?? null,
    recipient_id: raw.recipient_id ?? null,
    body: raw.body ?? null,
    api_response: raw.api_response ?? raw.apiResponse,
    created: raw.created ?? raw.created_at ?? null,
    updated: raw.updated ?? raw.updated_at ?? null,
    timestamp: raw.timestamp ?? null,
  };
}

function normalizeThread(raw: any): ExecutionThread | null {
  if (!raw || typeof raw !== "object") return null;
  const msgId = raw.msg_id;
  if (msgId == null || typeof msgId !== "string") return null;
  const rawEvents = Array.isArray(raw.events) ? raw.events : [];
  const events = rawEvents.map(normalizeThreadEvent).filter(Boolean) as ExecutionThreadEvent[];
  return {
    msg_id: msgId,
    first_seen_at: raw.first_seen_at ?? null,
    last_seen_at: raw.last_seen_at ?? null,
    latest_status: raw.latest_status ?? null,
    events,
  };
}

function extractThreads(raw: any): ExecutionThread[] {
  if (!raw || !Array.isArray(raw.threads)) return [];
  return raw.threads.map(normalizeThread).filter(Boolean) as ExecutionThread[];
}

export async function fetchExecutionMessages(executionId: string): Promise<ExecutionMessagesResponse> {
  const raw = await fetchJson<any>(apiV1(`/flows/executions/${executionId}/messages/`));
  const threads = extractThreads(raw);
  const legacyMessages = extractMessages(raw).map(normalizeMessage).filter(Boolean) as ExecutionMessage[];
  const flattenedFromThreads: ExecutionMessage[] = [];
  for (const t of threads) {
    for (const e of t.events) {
      const m = normalizeMessage(e);
      if (m) flattenedFromThreads.push(m);
    }
  }
  const messages =
    flattenedFromThreads.length > 0 ? flattenedFromThreads : legacyMessages;
  return {
    ok: Boolean(raw?.ok ?? true),
    execution_id: raw?.execution_id ? String(raw.execution_id) : executionId,
    flow_id: raw?.flow_id ? String(raw.flow_id) : undefined,
    flow_name: typeof raw?.flow_name === "string" ? raw.flow_name : undefined,
    seed_msg_ids_count:
      typeof raw?.seed_msg_ids_count === "number" ? raw.seed_msg_ids_count : undefined,
    threads,
    message_count: typeof raw?.message_count === "number" ? raw.message_count : messages.length,
    messages,
  };
}


