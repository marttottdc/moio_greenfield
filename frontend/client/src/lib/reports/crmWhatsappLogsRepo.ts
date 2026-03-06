import { apiV1 } from "@/lib/api";
import { fetchJson } from "@/lib/queryClient";

/** Single status entry in a message's timeline. */
export interface WaLogStatus {
  status: string;
  occurred_at?: string;
  timestamp?: string;
  date?: string;
  time?: string;
  type?: string;
  api_response?: unknown;
}

/** One message from GET /api/v1/crm/communications/whatsapp-logs/. */
export interface WaMessageLog {
  msg_id: string;
  recipient: string;
  body?: string;
  flow_execution_id?: string | null;
  contact_phone?: string;
  contact_name?: string;
  contact?: { id?: string | null; name?: string; phone?: string; email?: string };
  created?: string;
  updated?: string;
  first_status?: string;
  last_status?: string;
  latest_status?: string;
  statuses?: WaLogStatus[];
  events?: WaLogStatus[];
}

export interface CrmWhatsappLogsPagination {
  current_page: number;
  total_pages: number;
  total_items: number;
}

export interface CrmWhatsappLogsResponse {
  ok: boolean;
  message_count: number;
  messages: WaMessageLog[];
  pagination?: CrmWhatsappLogsPagination;
}

export interface CrmWhatsappLogsParams {
  page?: number;
  page_size?: number;
  flow_id?: string;
  flow_execution_id?: string;
  recipient?: string;
  from_date?: string;
  to_date?: string;
}

/**
 * GET /api/v1/crm/communications/whatsapp-logs/
 * Tenant-scoped; returns messages with full status timeline.
 */
export async function fetchCrmWhatsappLogs(
  params?: CrmWhatsappLogsParams
): Promise<CrmWhatsappLogsResponse> {
  const query: Record<string, string> = {};
  if (params?.page != null) query.page = String(params.page);
  if (params?.page_size != null) query.page_size = String(params.page_size);
  if (params?.flow_id) query.flow_id = params.flow_id;
  if (params?.flow_execution_id) query.flow_execution_id = params.flow_execution_id;
  if (params?.recipient) query.recipient = params.recipient;
  if (params?.from_date) query.from_date = params.from_date;
  if (params?.to_date) query.to_date = params.to_date;

  const raw = await fetchJson<CrmWhatsappLogsResponse>(
    apiV1("/crm/communications/whatsapp-logs/"),
    query
  );

  const messages = Array.isArray(raw?.messages) ? raw.messages : [];
  return {
    ok: Boolean(raw?.ok ?? true),
    message_count: typeof raw?.message_count === "number" ? raw.message_count : messages.length,
    messages,
    pagination: raw?.pagination,
  };
}

/**
 * Flatten CRM log messages into one record per status (for report UIs that expect event-level rows).
 * Preserves msg_id, recipient, contact info, and maps each status to a row with created_at from status timestamp.
 */
export function flattenCrmLogsToEvents(messages: WaMessageLog[]): Array<{
  id: string;
  message_id: string;
  flow_execution_id: string;
  recipient: string;
  contact_name?: string;
  contact_phone?: string;
  body?: string;
  status: string;
  created_at: string;
  error_message?: string;
}> {
  const out: Array<{
    id: string;
    message_id: string;
    flow_execution_id: string;
    recipient: string;
    contact_name?: string;
    contact_phone?: string;
    body?: string;
    status: string;
    created_at: string;
    error_message?: string;
  }> = [];
  for (const m of messages) {
    const recipient = m.recipient ?? m.contact_phone ?? m.contact?.phone ?? "";
    const statuses = m.statuses ?? m.events ?? [];
    if (statuses.length === 0) {
      out.push({
        id: m.msg_id,
        message_id: m.msg_id,
        flow_execution_id: m.flow_execution_id ?? "",
        recipient,
        contact_name: m.contact_name ?? m.contact?.name,
        contact_phone: m.contact_phone ?? m.contact?.phone,
        body: m.body,
        status: m.latest_status ?? m.last_status ?? m.first_status ?? "unknown",
        created_at: m.updated ?? m.created ?? "",
      });
      continue;
    }
    for (let i = 0; i < statuses.length; i++) {
      const s = statuses[i]!;
      const ts = s.occurred_at ?? s.timestamp ?? "";
      out.push({
        id: `${m.msg_id}-${i}`,
        message_id: m.msg_id,
        flow_execution_id: m.flow_execution_id ?? "",
        recipient,
        contact_name: m.contact_name ?? m.contact?.name,
        contact_phone: m.contact_phone ?? m.contact?.phone,
        body: m.body,
        status: s.status ?? "unknown",
        created_at: ts,
        error_message:
          s.api_response && typeof s.api_response === "object" && (s.api_response as any)?.error
            ? String((s.api_response as any).error)
            : undefined,
      });
    }
  }
  return out;
}
