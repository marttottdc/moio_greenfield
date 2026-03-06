import { apiV1 } from "@/lib/api";
import { fetchJson } from "@/lib/queryClient";

export type WhatsappLogEvent = {
  status: string;
  timestamp: string;
  api_response?: unknown;
};

export type WhatsappLogMessage = {
  msg_id: string;
  channel?: string;
  recipient?: string;
  body?: string;
  events: WhatsappLogEvent[];
  first_status?: string;
  last_status?: string;
  created?: string;
  updated?: string;
};

export type WhatsappLogsResponseBase = {
  ok: boolean;
  message_count?: number;
  messages: WhatsappLogMessage[];
};

export type WhatsappLogsFlowResponse = WhatsappLogsResponseBase & {
  flow?: unknown;
};

export type WhatsappLogsCampaignResponse = WhatsappLogsResponseBase & {
  campaign?: unknown;
};

function normalizeEvent(raw: any): WhatsappLogEvent {
  return {
    status: String(raw?.status ?? ""),
    timestamp: String(raw?.timestamp ?? raw?.created ?? raw?.created_at ?? raw?.ts ?? ""),
    api_response: raw?.api_response ?? raw?.apiResponse,
  };
}

function normalizeMessage(raw: any): WhatsappLogMessage {
  const eventsRaw = Array.isArray(raw?.events) ? raw.events : [];
  const events = eventsRaw.map(normalizeEvent).filter((e) => e.status && e.timestamp);

  return {
    msg_id: String(raw?.msg_id ?? raw?.message_id ?? raw?.id ?? ""),
    channel: typeof raw?.channel === "string" ? raw.channel : "whatsapp",
    recipient: String(raw?.recipient ?? raw?.user_number ?? raw?.recipient_id ?? ""),
    body: typeof raw?.body === "string" ? raw.body : (typeof raw?.text === "string" ? raw.text : undefined),
    events,
    first_status: typeof raw?.first_status === "string" ? raw.first_status : events[0]?.status,
    last_status: typeof raw?.last_status === "string" ? raw.last_status : events[events.length - 1]?.status,
    created: typeof raw?.created === "string" ? raw.created : (typeof raw?.created_at === "string" ? raw.created_at : undefined),
    updated: typeof raw?.updated === "string" ? raw.updated : (typeof raw?.updated_at === "string" ? raw.updated_at : undefined),
  };
}

function normalizeResponse(raw: any): WhatsappLogsResponseBase & { flow?: unknown; campaign?: unknown } {
  const messagesRaw = Array.isArray(raw?.messages) ? raw.messages : [];
  return {
    ok: Boolean(raw?.ok ?? true),
    flow: raw?.flow,
    campaign: raw?.campaign,
    message_count: typeof raw?.message_count === "number" ? raw.message_count : messagesRaw.length,
    messages: messagesRaw.map(normalizeMessage).filter((m) => m.msg_id),
  };
}

export async function fetchWhatsappLogsForFlowExecution(executionId: string): Promise<WhatsappLogsFlowResponse> {
  const raw = await fetchJson<any>(apiV1("/flows/whatsapp-logs/"), { execution_id: executionId });
  return normalizeResponse(raw) as WhatsappLogsFlowResponse;
}

export async function fetchWhatsappLogsForCampaign(campaignId: string): Promise<WhatsappLogsCampaignResponse> {
  const raw = await fetchJson<any>(apiV1("/campaigns/audiences/whatsapp-logs/"), { campaign_id: campaignId });
  return normalizeResponse(raw) as WhatsappLogsCampaignResponse;
}


