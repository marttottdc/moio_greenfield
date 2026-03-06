import { useMutation, useQuery } from "@tanstack/react-query";
import { apiRequest, fetchJson, ApiError } from "@/lib/queryClient";
import { apiV1, desktopAgentApi } from "@/lib/api";

export interface WebhookRecord {
  id: string;
  name: string;
  description?: string;
  url?: string;
  handler_path?: string;
  expected_content_type?: string;
  expected_schema?: string;
  auth_type?: string;
  auth_config?: Record<string, any>;
  locked?: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface WebhookListResponse {
  webhooks?: WebhookRecord[] | null;
  error?: string;
}

export interface CreateWebhookPayload {
  name: string;
  url?: string;
  description?: string;
  handler_path?: string;
  secret?: string;
  events?: string[];
  flow_id?: string;
}

export interface AgentRecord {
  id: string;
  name: string;
  description?: string;
  status?: "active" | "inactive" | "draft";
  model?: string;
  system_prompt?: string;
  channel?: string;
  tools?: string[];
  created_at?: string;
  updated_at?: string;
}

export interface AgentListResponse {
  agents?: AgentRecord[] | null;
  error?: string;
}

// ============================================================================
// Automation Scripts (Flow Builder Script node)
// ============================================================================

export interface AutomationScriptRecord {
  id: string;
  name?: string;
  description?: string;
  status?: string;
  language?: string;
  // Backend may expose specs/schemas depending on version
  params_schema?: Record<string, any>;
  params_schema_json?: Record<string, any>;
  input_spec?: Record<string, any>;
  input_spec_json?: Record<string, any>;
  output_spec?: Record<string, any>;
  output_spec_json?: Record<string, any>;
  created_at?: string;
  updated_at?: string;
}

export interface AutomationScriptListResponse {
  scripts?: AutomationScriptRecord[] | null;
  error?: string;
}

function normalizeAutomationScript(entry?: Partial<AutomationScriptRecord> | null): AutomationScriptRecord {
  if (!entry) {
    return { id: "", name: "", description: "" };
  }
  const parseMaybeJsonObject = (v: any): Record<string, any> | undefined => {
    if (!v) return undefined;
    if (typeof v === "object") return v as Record<string, any>;
    if (typeof v === "string") {
      try {
        const parsed = JSON.parse(v);
        return parsed && typeof parsed === "object" ? (parsed as Record<string, any>) : undefined;
      } catch {
        return undefined;
      }
    }
    return undefined;
  };

  const paramsSchema =
    // Canonical backend shape (v2): params stored on latest_version + script.params_text
    parseMaybeJsonObject((entry as any)?.latest_version?.parameters) ??
    parseMaybeJsonObject((entry as any)?.latest_version?.parameters_text) ??
    parseMaybeJsonObject((entry as any)?.params_text) ??
    parseMaybeJsonObject((entry as any).params_schema_json) ??
    parseMaybeJsonObject((entry as any).params_schema);
  const inputSpec =
    parseMaybeJsonObject((entry as any).input_spec_json) ??
    parseMaybeJsonObject((entry as any).input_spec);
  const outputSpec =
    parseMaybeJsonObject((entry as any).output_spec_json) ??
    parseMaybeJsonObject((entry as any).output_spec);

  return {
    id: entry.id ? String(entry.id) : "",
    name: typeof entry.name === "string" ? entry.name : entry.name ? String(entry.name) : "",
    description: typeof entry.description === "string" ? entry.description : entry.description ? String(entry.description) : "",
    status: typeof entry.status === "string" ? entry.status : entry.status ? String(entry.status) : undefined,
    language: typeof entry.language === "string" ? entry.language : entry.language ? String(entry.language) : undefined,
    params_schema: paramsSchema,
    params_schema_json: paramsSchema,
    input_spec: inputSpec,
    input_spec_json: inputSpec,
    output_spec: outputSpec,
    output_spec_json: outputSpec,
    created_at: (entry as any).created_at,
    updated_at: (entry as any).updated_at,
  };
}

function normalizeAutomationScriptsList(data: any): AutomationScriptRecord[] {
  if (!data) return [];
  const list = Array.isArray(data)
    ? data
    : Array.isArray(data?.scripts)
      ? data.scripts
      : Array.isArray(data?.results)
        ? data.results
        : Array.isArray(data?.data)
          ? data.data
          : [];

  return (list as any[])
    .map((entry) => normalizeAutomationScript(entry))
    .filter((s) => Boolean(s.id));
}

// Desktop Agent runtime configs (for Flow Builder Agent node)
export interface DesktopAgentRecord {
  id: string;
  name: string;
  model?: string;
  is_default?: boolean;
}

export interface DesktopAgentListResponse {
  agents?: DesktopAgentRecord[] | null;
  error?: string;
}

export interface WhatsAppTemplateComponent {
  type?: string;
  text?: string;
  parameters?: Array<{ type?: string; text?: string; parameter_name?: string }>;
}

export interface WhatsAppTemplateRecord {
  id: string;
  name: string;
  language?: string;
  category?: string;
  status?: string;
  components?: WhatsAppTemplateComponent[];
  placeholders?: string[];
  requirements?: string[];
}

interface WhatsAppTemplateResponse {
  templates?: WhatsAppTemplateRecord[];
  error?: string;
}

export function normalizeWebhook(entry?: Partial<WebhookRecord> | null): WebhookRecord {
  if (!entry) {
    return {
      id: "",
      name: "",
      description: "",
      url: "",
      handler_path: "",
      expected_content_type: "",
      expected_schema: "",
      auth_type: "",
      auth_config: {},
      locked: false,
    };
  }

  return {
    id: entry.id ? String(entry.id) : "",
    name: entry.name ?? "",
    description: entry.description ?? "",
    url: entry.url ?? "",
    handler_path: entry.handler_path ?? "",
    expected_content_type: entry.expected_content_type ?? "",
    expected_schema: entry.expected_schema ?? "",
    auth_type: entry.auth_type ?? "",
    auth_config: entry.auth_config ?? {},
    locked: entry.locked ?? false,
    created_at: entry.created_at,
    updated_at: entry.updated_at,
  };
}

export function normalizeAgent(entry?: Partial<AgentRecord> | null): AgentRecord {
  if (!entry) {
    return {
      id: "",
      name: "",
      description: "",
      status: "draft",
      model: "",
      system_prompt: "",
      channel: "",
      tools: [],
    };
  }

  return {
    id: entry.id ? String(entry.id) : "",
    name: entry.name ?? "",
    description: entry.description ?? "",
    status: entry.status ?? "draft",
    model: entry.model ?? "",
    system_prompt: entry.system_prompt ?? "",
    channel: entry.channel ?? "",
    tools: Array.isArray(entry.tools) ? entry.tools : [],
    created_at: entry.created_at,
    updated_at: entry.updated_at,
  };
}

export function normalizeTemplate(entry?: Partial<WhatsAppTemplateRecord> | null): WhatsAppTemplateRecord {
  if (!entry) {
    return {
      id: "",
      name: "",
      components: [],
      placeholders: [],
      requirements: [],
    };
  }

  return {
    id: entry.id ? String(entry.id) : entry.name ?? "",
    name: entry.name ?? entry.id ?? "",
    language: entry.language ?? "",
    category: entry.category ?? "",
    status: entry.status ?? "",
    components: Array.isArray(entry.components) ? entry.components : [],
    placeholders: Array.isArray(entry.placeholders) ? entry.placeholders : [],
    requirements: Array.isArray(entry.requirements) ? entry.requirements : [],
  };
}

const WEBHOOKS_PATH = apiV1("/resources/webhooks/");
const AGENTS_PATH = apiV1("/settings/agents/");
const AUTOMATION_SCRIPTS_PATH = apiV1("/scripts/");

async function fetchWebhookList(flowId?: string) {
  return await fetchJson<WebhookListResponse>(WEBHOOKS_PATH, flowId ? { flow_id: flowId } : undefined);
}

async function fetchWebhookDetails(webhookId: string): Promise<WebhookRecord> {
  const res = await apiRequest("GET", `${WEBHOOKS_PATH}${webhookId}/`, {});
  const json = await res.json();
  const webhook = (json?.webhook ?? json) as Partial<WebhookRecord> | undefined;
  if (!webhook) {
    throw new ApiError(500, "Webhook details response missing payload");
  }
  return normalizeWebhook(webhook);
}

export function useWebhookList(flowId?: string) {
  return useQuery<WebhookListResponse>({
    queryKey: [WEBHOOKS_PATH, { flowId }],
    queryFn: async () => {
      const data = await fetchWebhookList(flowId);
      // API returns array directly, not wrapped in webhooks property
      const webhooksList = Array.isArray(data) ? data : (data.webhooks ?? []);
      return {
        error: data.error || undefined,
        webhooks: webhooksList.map((entry) => normalizeWebhook(entry)),
      };
    },
  });
}

export function useWebhookDetails(webhookId: string | undefined) {
  return useQuery<WebhookRecord>({
    queryKey: [WEBHOOKS_PATH, webhookId, "details"],
    queryFn: () => {
      if (!webhookId) {
        throw new Error("webhookId is required");
      }
      return fetchWebhookDetails(webhookId);
    },
    enabled: !!webhookId,
    staleTime: 30000, // Consider data fresh for 30 seconds
  });
}

async function postWebhook(payload: CreateWebhookPayload, flowId?: string) {
  const res = await apiRequest("POST", WEBHOOKS_PATH, {
    data: flowId ? { ...payload, flow_id: flowId } : payload,
  });
  const json = await res.json();
  const webhook = (json?.webhook ?? json) as Partial<WebhookRecord> | undefined;
  if (!webhook) {
    throw new ApiError(500, "Webhook creation response missing payload");
  }
  return normalizeWebhook(webhook);
}

export function useCreateWebhookMutation(flowId?: string) {
  return useMutation({
    mutationFn: async (payload: CreateWebhookPayload) => postWebhook(payload, flowId),
  });
}

const WHATSAPP_TEMPLATES_PATH = apiV1("/resources/whatsapp-templates/");

export function useWhatsAppTemplates(channel = "WhatsApp") {
  return useQuery<WhatsAppTemplateResponse>({
    queryKey: [WHATSAPP_TEMPLATES_PATH, { channel }],
    queryFn: async () => {
      const res = await apiRequest("GET", WHATSAPP_TEMPLATES_PATH, {
        params: { channel },
      });
      const json = (await res.json()) as WhatsAppTemplateResponse;
      return {
        error: json.error,
        templates: (json.templates ?? []).map((template) => normalizeTemplate(template)),
      };
    },
  });
}

// Flow Event Types API
export interface FlowEventType {
  id: string;
  name: string;                        // e.g., "ticket.created", "deal.won"
  label: string;                       // Human-readable name
  description?: string;
  entity_type: string;                 // e.g., ticket, deal, contact
  category: string;                    // e.g., crm, chatbot, recruiter
  payload_schema?: Record<string, any>; // JSON Schema for expected payload
  hints?: {
    use_cases?: string[];              // Example use cases for this event
    example_payload?: Record<string, any>; // Example payload data
    configuration_tips?: string;       // Tips for configuring this event
  };
  active: boolean;                     // Can be used as trigger
  created_at?: string;
  updated_at?: string;
}

export interface FlowEventsResponse {
  events: FlowEventType[];
  count: number;
  categories: string[];                // Available categories for filtering
  entity_types: string[];              // Available entity types for filtering
  error?: string;
}

const FLOW_EVENTS_PATH = apiV1("/flows/events/");

async function fetchEventDetails(eventId: string): Promise<FlowEventType> {
  const res = await apiRequest("GET", `${FLOW_EVENTS_PATH}${eventId}/`, {});
  const json = await res.json();
  const event = (json?.event ?? json) as Partial<FlowEventType> | undefined;
  if (!event) {
    throw new ApiError(500, "Event details response missing payload");
  }
  return event as FlowEventType;
}

export function useFlowEvents() {
  return useQuery<FlowEventsResponse>({
    queryKey: [FLOW_EVENTS_PATH],
    queryFn: async () => {
      const data = await fetchJson<FlowEventsResponse>(FLOW_EVENTS_PATH);
      return {
        events: data.events ?? [],
        count: data.count ?? 0,
        categories: data.categories ?? [],
        entity_types: data.entity_types ?? [],
        error: data.error,
      };
    },
    staleTime: 0, // Disabled cache for development - always fetch fresh data
  });
}

export function useEventDetails(eventId: string | undefined) {
  return useQuery<FlowEventType>({
    queryKey: [FLOW_EVENTS_PATH, eventId, "details"],
    queryFn: () => {
      if (!eventId) {
        throw new Error("eventId is required");
      }
      return fetchEventDetails(eventId);
    },
    enabled: !!eventId,
    staleTime: 0, // Always fetch fresh data when eventId changes (no cache)
    refetchOnMount: true, // Refetch when component mounts to ensure fresh data
  });
}

async function fetchAgentList() {
  return await fetchJson<AgentListResponse>(AGENTS_PATH);
}

export function useAgentList() {
  return useQuery<AgentListResponse>({
    queryKey: [AGENTS_PATH],
    queryFn: async () => {
      const data = await fetchAgentList();
      const agentsList = Array.isArray(data) ? data : (data.agents ?? []);
      return {
        error: data.error || undefined,
        agents: agentsList.map((entry) => normalizeAgent(entry)),
      };
    },
    // Ensure fresh list when opening pages that depend on it (Flow Builder agent picker)
    staleTime: 0,
    refetchOnMount: "always",
  });
}

async function fetchAutomationScriptsList() {
  return await fetchJson<any>(AUTOMATION_SCRIPTS_PATH);
}

async function fetchAutomationScriptDetails(scriptId: string): Promise<AutomationScriptRecord> {
  const res = await apiRequest("GET", `${AUTOMATION_SCRIPTS_PATH}${scriptId}/`, {});
  const json = await res.json();
  const payload = (json?.script ?? json) as Partial<AutomationScriptRecord> | undefined;
  if (!payload) {
    throw new ApiError(500, "Script details response missing payload");
  }
  return normalizeAutomationScript(payload);
}

export function useAutomationScriptsList() {
  return useQuery<AutomationScriptListResponse>({
    queryKey: [AUTOMATION_SCRIPTS_PATH],
    queryFn: async () => {
      const data = await fetchAutomationScriptsList();
      return {
        error: typeof data?.error === "string" ? data.error : undefined,
        scripts: normalizeAutomationScriptsList(data),
      };
    },
    staleTime: 0,
    refetchOnMount: "always",
  });
}

export function useAutomationScriptDetails(scriptId: string | undefined) {
  return useQuery<AutomationScriptRecord>({
    queryKey: [AUTOMATION_SCRIPTS_PATH, scriptId, "details"],
    queryFn: () => {
      if (!scriptId) throw new Error("scriptId is required");
      return fetchAutomationScriptDetails(scriptId);
    },
    enabled: Boolean(scriptId),
    staleTime: 30_000,
  });
}

async function fetchDesktopAgentList() {
  const path = desktopAgentApi.getAgents();
  return await fetchJson<DesktopAgentListResponse | DesktopAgentRecord[]>(path);
}

export function useDesktopAgentList() {
  const path = desktopAgentApi.getAgents();
  return useQuery<DesktopAgentListResponse>({
    queryKey: [path],
    queryFn: async () => {
      const data = await fetchDesktopAgentList();
      const list = Array.isArray(data) ? data : (data.agents ?? []);
      return {
        error: (data as any)?.error || undefined,
        agents: list.map((a: any) => ({
          id: String(a?.id ?? ""),
          name: String(a?.name ?? a?.id ?? ""),
          model: typeof a?.model === "string" ? a.model : undefined,
          is_default: Boolean(a?.is_default),
        })).filter((a: DesktopAgentRecord) => Boolean(a.id)),
      };
    },
    staleTime: 30_000,
  });
}

// ============================================================================
// CRM CRUD (tool_crm_crud)
// ============================================================================

export interface CrmModelSummary {
  slug: string;
  label: string;
  description?: string;
  enabled_operations?: string[];
}

export interface CrmOperationSchemas {
  input_schema?: unknown;
  output_schema?: unknown;
  description?: string;
}

export interface CrmResourceDetails {
  slug: string;
  label: string;
  description?: string;
  operations?: Record<string, CrmOperationSchemas>;
}

const CRM_MODELS_PATH = apiV1("/flows/crm/models/");
const crmResourcePath = (slug: string) => apiV1(`/flows/crm/${slug}/`);

export function useCrmModels() {
  return useQuery<{ models: CrmModelSummary[]; error?: string }>({
    queryKey: [CRM_MODELS_PATH],
    queryFn: async () => {
      const data = await fetchJson<any>(CRM_MODELS_PATH);
      const list = Array.isArray(data)
        ? data
        : Array.isArray(data?.models)
          ? data.models
          : Array.isArray(data?.items)
            ? data.items
            : [];

      const models: CrmModelSummary[] = list
        .map((m: any) => ({
          slug: String(m.slug ?? ""),
          label: String(m.label ?? m.slug ?? ""),
          description: typeof m.description === "string" ? m.description : undefined,
          enabled_operations: Array.isArray(m.enabled_operations) ? m.enabled_operations.map(String) : undefined,
        }))
        .filter((m: CrmModelSummary) => Boolean(m.slug));

      return { models, error: typeof data?.error === "string" ? data.error : undefined };
    },
    staleTime: 30_000,
  });
}

export function useCrmResourceDetails(slug: string | undefined) {
  return useQuery<CrmResourceDetails>({
    queryKey: [CRM_MODELS_PATH, slug, "details"],
    queryFn: async () => {
      if (!slug) throw new Error("slug is required");
      const data = await fetchJson<any>(crmResourcePath(slug));
      // Backend may return { model: {...} } or { resource: {...} } depending on version
      const payload = data?.model ?? data?.resource ?? data?.data?.model ?? data?.data?.resource ?? data;
      const opsCandidate =
        payload?.operations ??
        payload?.model?.operations ??
        data?.operations ??
        data?.model?.operations ??
        data?.resource?.operations;

      return {
        slug: String(payload?.slug ?? slug),
        label: String(payload?.label ?? payload?.slug ?? slug),
        description: typeof payload?.description === "string" ? payload.description : undefined,
        operations: typeof opsCandidate === "object" && opsCandidate ? opsCandidate : {},
      } as CrmResourceDetails;
    },
    enabled: Boolean(slug),
    staleTime: 30_000,
  });
}
