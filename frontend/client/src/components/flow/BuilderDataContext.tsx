import { createContext, useContext, useEffect, useMemo } from "react";
import {
  CreateWebhookPayload,
  WebhookRecord,
  WhatsAppTemplateRecord,
  FlowEventType,
  useCreateWebhookMutation,
  useWebhookList,
  useWebhookDetails,
  useWhatsAppTemplates,
  useFlowEvents,
  useEventDetails,
  AgentRecord,
  useAgentList,
  AutomationScriptRecord,
  useAutomationScriptsList,
} from "@/hooks/useBuilderData";
import { useQueryClient } from "@tanstack/react-query";

interface WebhookDataContextValue {
  webhooks: WebhookRecord[];
  isLoading: boolean;
  isFetching: boolean;
  error?: string;
  refresh: () => void;
  createWebhook: (payload: CreateWebhookPayload) => Promise<WebhookRecord>;
  isCreating: boolean;
}

interface TemplateDataContextValue {
  templates: WhatsAppTemplateRecord[];
  isLoading: boolean;
  isFetching: boolean;
  error?: string;
  refresh: () => void;
}

interface FlowEventDataContextValue {
  events: FlowEventType[];
  categories: string[];
  entityTypes: string[];
  isLoading: boolean;
  isFetching: boolean;
  error?: string;
  refresh: () => void;
}

interface AgentDataContextValue {
  agents: AgentRecord[];
  isLoading: boolean;
  isFetching: boolean;
  error?: string;
  refresh: () => void;
}

interface ScriptDataContextValue {
  scripts: AutomationScriptRecord[];
  isLoading: boolean;
  isFetching: boolean;
  error?: string;
  refresh: () => void;
}

const WebhookDataContext = createContext<WebhookDataContextValue | undefined>(undefined);
const TemplateDataContext = createContext<TemplateDataContextValue | undefined>(undefined);
const FlowEventDataContext = createContext<FlowEventDataContextValue | undefined>(undefined);
const AgentDataContext = createContext<AgentDataContextValue | undefined>(undefined);
const ScriptDataContext = createContext<ScriptDataContextValue | undefined>(undefined);

export function useWebhookData() {
  const ctx = useContext(WebhookDataContext);
  if (!ctx) {
    return {
      webhooks: [],
      isLoading: false,
      isFetching: false,
      error: "WebhookDataContext is unavailable. Wrap components with BuilderDataProviders.",
      refresh: () => {},
      createWebhook: async () => {
        throw new Error("WebhookDataContext is unavailable. Wrap components with BuilderDataProviders.");
      },
      isCreating: false,
    };
  }
  return ctx;
}

export function useTemplateData() {
  const ctx = useContext(TemplateDataContext);
  if (!ctx) {
    return {
      templates: [],
      isLoading: false,
      isFetching: false,
      error: "TemplateDataContext is unavailable. Wrap components with BuilderDataProviders.",
      refresh: () => {},
    };
  }
  return ctx;
}

export function useFlowEventData() {
  const ctx = useContext(FlowEventDataContext);
  if (!ctx) {
    return {
      events: [],
      categories: [],
      entityTypes: [],
      isLoading: false,
      isFetching: false,
      error: "FlowEventDataContext is unavailable. Wrap components with BuilderDataProviders.",
      refresh: () => {},
    };
  }
  return ctx;
}

export function useAgentData() {
  const ctx = useContext(AgentDataContext);
  if (!ctx) {
    return {
      agents: [],
      isLoading: false,
      isFetching: false,
      error: "AgentDataContext is unavailable. Wrap components with BuilderDataProviders.",
      refresh: () => {},
    };
  }
  return ctx;
}

export function useScriptData() {
  const ctx = useContext(ScriptDataContext);
  if (!ctx) {
    return {
      scripts: [],
      isLoading: false,
      isFetching: false,
      error: "ScriptDataContext is unavailable. Wrap components with BuilderDataProviders.",
      refresh: () => {},
    };
  }
  return ctx;
}

interface BuilderDataProvidersProps {
  children: React.ReactNode;
  flowId?: string;
  templateChannel?: string;
}

export function BuilderDataProviders({
  children,
  flowId,
  templateChannel = "WhatsApp",
}: BuilderDataProvidersProps) {
  const webhookQuery = useWebhookList();
  const createWebhook = useCreateWebhookMutation(flowId);
  const templatesQuery = useWhatsAppTemplates(templateChannel);
  const eventsQuery = useFlowEvents();
  const agentsQuery = useAgentList();
  const scriptsQuery = useAutomationScriptsList();

  // Ensure we refresh agents when opening Flow Builder (even if cached).
  useEffect(() => {
    agentsQuery.refetch();
  }, []);

  const webhookValue = useMemo<WebhookDataContextValue>(() => {
    const errorMessage = webhookQuery.data?.error ||
      (webhookQuery.error instanceof Error ? webhookQuery.error.message : undefined);

    return {
      webhooks: webhookQuery.data?.webhooks ?? [],
      isLoading: webhookQuery.isLoading,
      isFetching: webhookQuery.isFetching,
      error: errorMessage,
      refresh: () => webhookQuery.refetch(),
      createWebhook: async (payload) => {
        const created = await createWebhook.mutateAsync({ ...payload, flow_id: flowId });
        await webhookQuery.refetch();
        return created;
      },
      isCreating: createWebhook.isPending,
    };
  }, [createWebhook, flowId, webhookQuery]);

  const templateValue = useMemo<TemplateDataContextValue>(() => {
    const errorMessage = templatesQuery.data?.error ||
      (templatesQuery.error instanceof Error ? templatesQuery.error.message : undefined);

    return {
      templates: templatesQuery.data?.templates ?? [],
      isLoading: templatesQuery.isLoading,
      isFetching: templatesQuery.isFetching,
      error: errorMessage,
      refresh: () => templatesQuery.refetch(),
    };
  }, [templatesQuery]);

  const eventValue = useMemo<FlowEventDataContextValue>(() => {
    const errorMessage = eventsQuery.data?.error ||
      (eventsQuery.error instanceof Error ? eventsQuery.error.message : undefined);

    return {
      events: eventsQuery.data?.events ?? [],
      categories: eventsQuery.data?.categories ?? [],
      entityTypes: eventsQuery.data?.entity_types ?? [],
      isLoading: eventsQuery.isLoading,
      isFetching: eventsQuery.isFetching,
      error: errorMessage,
      refresh: () => eventsQuery.refetch(),
    };
  }, [eventsQuery]);

  const agentValue = useMemo<AgentDataContextValue>(() => {
    const errorMessage = agentsQuery.data?.error ||
      (agentsQuery.error instanceof Error ? agentsQuery.error.message : undefined);

    return {
      agents: agentsQuery.data?.agents ?? [],
      isLoading: agentsQuery.isLoading,
      isFetching: agentsQuery.isFetching,
      error: errorMessage,
      refresh: () => agentsQuery.refetch(),
    };
  }, [agentsQuery]);

  const scriptValue = useMemo<ScriptDataContextValue>(() => {
    const errorMessage = scriptsQuery.data?.error ||
      (scriptsQuery.error instanceof Error ? scriptsQuery.error.message : undefined);

    return {
      scripts: scriptsQuery.data?.scripts ?? [],
      isLoading: scriptsQuery.isLoading,
      isFetching: scriptsQuery.isFetching,
      error: errorMessage,
      refresh: () => scriptsQuery.refetch(),
    };
  }, [scriptsQuery]);

  return (
    <ScriptDataContext.Provider value={scriptValue}>
      <WebhookDataContext.Provider value={webhookValue}>
        <TemplateDataContext.Provider value={templateValue}>
          <FlowEventDataContext.Provider value={eventValue}>
            <AgentDataContext.Provider value={agentValue}>
              {children}
            </AgentDataContext.Provider>
          </FlowEventDataContext.Provider>
        </TemplateDataContext.Provider>
      </WebhookDataContext.Provider>
    </ScriptDataContext.Provider>
  );
}
