import { apiV1 } from "@/lib/api";
import { fetchJson } from "@/lib/queryClient";

export interface WhatsappReportMessage {
  id: string;
  flow_execution_id: string;
  flow_id?: string;
  flow_name?: string;
  recipient: string;
  template_id?: string;
  template_name?: string;
  message_type?: string;
  status: string;
  message_id?: string;
  api_response?: any;
  error_message?: string;
  created_at: string;
}

function extractMessages(raw: any): { flow_id?: string; flow_name?: string; messages: any[] } {
  if (!raw) return { messages: [] };
  if (Array.isArray(raw)) return { messages: raw };
  if (Array.isArray(raw.messages)) return { flow_id: raw.flow_id, flow_name: raw.flow_name, messages: raw.messages };
  if (Array.isArray(raw.results)) return { messages: raw.results };
  if (Array.isArray(raw.data)) return { messages: raw.data };
  if (Array.isArray(raw.threads)) {
    const fromThreads: any[] = [];
    for (const t of raw.threads) {
      const threadPhone = t?.recipient_id ?? t?.user_number ?? t?.recipient ?? t?.to;
      const events = Array.isArray(t?.events) ? t.events : [];
      for (const e of events) {
        const phone = e?.recipient_id ?? e?.user_number ?? e?.recipient ?? e?.to ?? threadPhone;
        fromThreads.push({
          ...e,
          msg_id: e.msg_id ?? e.id,
          recipient: phone,
          recipient_id: phone ?? e.recipient_id ?? e.user_number,
          user_number: phone ?? e.user_number ?? e.recipient_id,
        });
      }
    }
    return { flow_id: raw.flow_id, flow_name: raw.flow_name, messages: fromThreads };
  }
  return { flow_id: raw.flow_id, flow_name: raw.flow_name, messages: [] };
}

function normalizeWhatsappMessage(raw: any, executionId: string, flowMeta?: { flow_id?: string; flow_name?: string }): WhatsappReportMessage {
  const createdAt =
    raw?.created ??
    raw?.created_at ??
    raw?.timestamp ??
    raw?.updated ??
    new Date().toISOString();

  return {
    id: String(raw?.id ?? raw?.msg_id ?? ""),
    flow_execution_id: String(raw?.flow_execution_id ?? raw?.execution_id ?? executionId ?? ""),
    flow_id: typeof raw?.flow_id === "string" ? raw.flow_id : flowMeta?.flow_id,
    flow_name: typeof raw?.flow_name === "string" ? raw.flow_name : flowMeta?.flow_name,
    recipient: String(
      raw?.user_number ??
      raw?.recipient ??
      raw?.recipient_id ??
      raw?.to ??
      raw?.destination ??
      raw?.phone_number ??
      (raw?.api_response && typeof raw.api_response === "object" && (raw.api_response as any)?.to) ??
      (raw?.api_response && typeof raw.api_response === "object" && (raw.api_response as any)?.recipient_id) ??
      ""
    ),
    template_id: (raw?.template_id ?? raw?.whatsapp_template_id) ? String(raw?.template_id ?? raw?.whatsapp_template_id) : undefined,
    template_name: typeof raw?.template_name === "string" ? raw.template_name : undefined,
    message_type: typeof raw?.type === "string" ? raw.type : (typeof raw?.message_type === "string" ? raw.message_type : undefined),
    status: String(raw?.status ?? "error"),
    message_id: typeof raw?.msg_id === "string" ? raw.msg_id : (typeof raw?.message_id === "string" ? raw.message_id : undefined),
    api_response: raw?.api_response ?? raw?.apiResponse,
    error_message: typeof raw?.error_message === "string" ? raw.error_message : (typeof raw?.errorMessage === "string" ? raw.errorMessage : undefined),
    created_at: String(createdAt),
  };
}

export async function fetchWhatsappMessagesForExecutionIds(executionIds: string[], opts?: { concurrency?: number }) {
  const concurrency = Math.max(1, Math.min(20, opts?.concurrency ?? 6));
  const results: WhatsappReportMessage[] = [];

  for (let i = 0; i < executionIds.length; i += concurrency) {
    const chunk = executionIds.slice(i, i + concurrency);
    const chunkRes = await Promise.all(
      chunk.map(async (id) => {
        try {
          const raw = await fetchJson<any>(apiV1(`/flows/executions/${id}/messages/`));
          const extracted = extractMessages(raw);
          const meta = { flow_id: extracted.flow_id, flow_name: extracted.flow_name };
          return extracted.messages.map((m) => normalizeWhatsappMessage(m, id, meta));
        } catch (e) {
          console.warn("[REPORTS] Failed to fetch messages for execution", id, e);
          return [] as WhatsappReportMessage[];
        }
      })
    );

    chunkRes.forEach((arr) => results.push(...arr));
  }

  return results;
}


