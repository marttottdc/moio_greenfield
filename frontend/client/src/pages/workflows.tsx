import React, { useMemo, useState, useEffect, useCallback, type ComponentType } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { useLocation, Link } from "wouter";
import { Plus, Search, Zap, Layers, PlayCircle, BarChart3, FileCode, FileText, Activity, TrendingUp, Clock, Circle, Bot, Webhook, Radio, Database, Wrench, MessageSquare, Mail, Users, MoreVertical, Building2, Save, Trash2, Globe, FileSearch, Monitor, ArrowRightLeft, Plug, Braces, Rocket, FlaskConical, Eye, AlertTriangle, XCircle, CheckCircle, Copy, Link2, GitBranch, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tooltip as UITooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { GlassPanel } from "@/components/radiant/glass-panel";
import { EmptyState } from "@/components/empty-state";
import { ErrorDisplay } from "@/components/error-display";
import { fetchJson, apiRequest, queryClient } from "@/lib/queryClient";
import { apiV1 } from "@/lib/api";
import { useToast } from "@/hooks/use-toast";
import { useWhatsAppTemplates } from "@/hooks/useBuilderData";
import { CampaignWizardV2, ResumeCampaignData } from "@/components/campaign-wizard-v2";
import type { Campaign as CampaignRecord, CampaignStatus, CampaignChannel, AudienceRecord, CampaignDetail } from "@/lib/moio-types";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Checkbox } from "@/components/ui/checkbox";
import { 
  BarChart, 
  Bar, 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip as RechartTooltip, 
  ResponsiveContainer,
  Legend,
  Cell
} from "recharts";
import { ReportsHubWorkspace } from "@/pages/workflows/reports/ReportsHubWorkspace";

interface Workflow {
  id: string;
  name: string;
  description?: string | null;
  runs?: number;
  status?: string;
  created_at?: string;
  updated_at?: string;
  // Backend may provide explicit flags; we normalize into `status` for UI.
  is_active?: boolean;
  is_published?: boolean;
  is_enabled?: boolean;
}

interface Script {
  id: string;
  name: string;
  description?: string | null;
  language?: string;
  status?: "draft" | "pending_approval" | "approved" | "rejected";
  created_at?: string;
  updated_at?: string;
}

interface Agent {
  id: string;
  name: string;
  description?: string | null;
  status?: "active" | "inactive" | "draft";
  model?: string;
  system_prompt?: string;
  created_at?: string;
  updated_at?: string;
}

interface Tool {
  id: string;
  name: string;
  description?: string | null;
  type?: string;
  status?: "active" | "inactive";
  config?: Record<string, any>;
  created_at?: string;
  updated_at?: string;
}

interface WebhookComponent {
  id: string;
  name: string;
  description?: string | null;
  url?: string;
  method?: string;
  status?: "active" | "inactive";
  created_at?: string;
  updated_at?: string;
}

interface Signal {
  id: string;
  name: string;
  description?: string | null;
  event_type?: string;
  status?: "active" | "inactive";
  created_at?: string;
  updated_at?: string;
}

interface InternalModel {
  id: string;
  name: string;
  description?: string | null;
  schema?: Record<string, any>;
  status?: "active" | "inactive";
  created_at?: string;
  updated_at?: string;
}

interface WorkflowsResponse {
  flows?: Workflow[];
  results?: Workflow[];
  data?: Workflow[];
  count?: number;
}

interface ScriptsResponse {
  scripts?: Script[];
  results?: Script[];
  data?: Script[];
  count?: number;
}

interface AgentsResponse {
  agents?: Agent[];
  results?: Agent[];
  data?: Agent[];
  count?: number;
}

interface ToolsResponse {
  tools?: Tool[];
  results?: Tool[];
  data?: Tool[];
  count?: number;
}

interface WebhooksResponse {
  webhooks?: WebhookComponent[];
  results?: WebhookComponent[];
  data?: WebhookComponent[];
  count?: number;
}

interface SignalsResponse {
  signals?: Signal[];
  results?: Signal[];
  data?: Signal[];
  count?: number;
}

interface InternalModelsResponse {
  models?: InternalModel[];
  results?: InternalModel[];
  data?: InternalModel[];
  count?: number;
}

function normalizeCollection<T>(
  data: unknown,
  fallbackKey?: string,
): T[] {
  if (!data) return [];
  if (Array.isArray(data)) {
    return data as T[];
  }

  if (typeof data === "object" && data !== null) {
    const record = data as Record<string, unknown>;
    const fallbackValue = fallbackKey ? record[fallbackKey] : undefined;

    if (fallbackValue && Array.isArray(fallbackValue)) {
      return fallbackValue as T[];
    }

    if (Array.isArray(record.results)) {
      return record.results as T[];
    }

    if (Array.isArray(record.data)) {
      return record.data as T[];
    }

    if (Array.isArray(record.items)) {
      return record.items as T[];
    }
  }

  return [];
}

type TabType = "flows" | "campaigns" | "audiences" | "ai_agents" | "components" | "analysis" | "reports" | "task_monitor";

const FLOWS_PATH = apiV1("/flows/");
const SCRIPTS_PATH = apiV1("/scripts/");
const TOOLS_PATH = apiV1("/tools/");
const WEBHOOKS_PATH = apiV1("/resources/webhooks/");
const SIGNALS_PATH = apiV1("/signals/");
const MODELS_PATH = apiV1("/models/");

// Custom hook to manage query parameters with wouter
function useQueryParams() {
  const [search, setSearch] = useState(window.location.search);

  useEffect(() => {
    // Listen to popstate events (browser back/forward)
    const handlePopState = () => {
      setSearch(window.location.search);
    };
    
    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  return useMemo(() => new URLSearchParams(search), [search]);
}

export default function Workflows() {
  const [location, navigate] = useLocation();
  const queryParams = useQueryParams();

  const activeTab: TabType = useMemo(() => {
    const tab = queryParams.get("tab");
    if (tab && ["flows", "campaigns", "audiences", "ai_agents", "components", "analysis", "reports", "task_monitor"].includes(tab)) {
      return tab as TabType;
    }
    return "flows";
  }, [queryParams]);

  const setActiveTab = (tab: TabType) => {
    if (tab !== activeTab) {
      const newUrl = `/workflows?tab=${tab}`;
      window.history.pushState({ tab }, '', newUrl);
      window.dispatchEvent(new PopStateEvent('popstate'));
    }
  };

  const [flowsPage, setFlowsPage] = useState(1);
  const [flowsPageSize] = useState(20);
  
  const flowsQuery = useQuery<WorkflowsResponse>({
    queryKey: [FLOWS_PATH, { page: flowsPage, page_size: flowsPageSize }],
    queryFn: () => fetchJson<WorkflowsResponse>(FLOWS_PATH, { 
      page: flowsPage.toString(), 
      page_size: flowsPageSize.toString() 
    }),
    enabled: activeTab === "flows" || activeTab === "analysis",
  });

  const scriptsQuery = useQuery<ScriptsResponse>({
    queryKey: [SCRIPTS_PATH],
    queryFn: () => fetchJson<ScriptsResponse>(SCRIPTS_PATH),
    enabled: activeTab === "components" || activeTab === "analysis",
  });

  const whatsappTemplatesQuery = useWhatsAppTemplates("WhatsApp");

  const workflows = useMemo(() => {
    const rawList = normalizeCollection<any>(flowsQuery.data, "flows").filter((flow) => Boolean(flow?.id));

    const normalizeWorkflow = (raw: any): Workflow => {
      const is_enabled = typeof raw?.is_enabled === "boolean" ? raw.is_enabled : undefined;
      const is_active = typeof raw?.is_active === "boolean" ? raw.is_active : undefined;
      const is_published = typeof raw?.is_published === "boolean" ? raw.is_published : undefined;

      // Runs count can come under different keys depending on API version.
      const runs =
        typeof raw?.runs === "number" ? raw.runs :
        typeof raw?.execution_count === "number" ? raw.execution_count :
        typeof raw?.runs_count === "number" ? raw.runs_count :
        typeof raw?.executions_count === "number" ? raw.executions_count :
        typeof raw?.execution_count === "number" ? raw.execution_count :
        typeof raw?.total_runs === "number" ? raw.total_runs :
        typeof raw?.stats?.runs === "number" ? raw.stats.runs :
        undefined;

      const rawStatus = typeof raw?.status === "string" ? raw.status : undefined;
      const statusLower = (rawStatus ?? "").toLowerCase();

      // Derive status with precedence:
      // 1) is_enabled flag (authoritative in /flows list)
      // 2) is_active flag (authoritative in some backends)
      // 2) explicit status string (if present)
      // 3) is_published (published but not active => inactive)
      // 4) fallback draft
      let status: string | undefined = rawStatus;
      if (is_enabled === true) status = "active";
      else if (is_enabled === false) status = "inactive";
      else if (is_active === true) status = "active";
      else if (is_active === false) status = is_published ? "inactive" : (statusLower || "draft");
      else if (statusLower) status = statusLower;
      else if (is_published) status = "inactive";
      else status = "draft";

      return {
        id: String(raw?.id ?? ""),
        name: String(raw?.name ?? ""),
        description: raw?.description ?? undefined,
        created_at: typeof raw?.created_at === "string" ? raw.created_at : undefined,
        updated_at: typeof raw?.updated_at === "string" ? raw.updated_at : undefined,
        runs,
        status,
        is_active: typeof is_active === "boolean" ? is_active : is_enabled,
        is_published,
        is_enabled,
      };
    };

    const list = rawList.map(normalizeWorkflow).filter((flow) => Boolean(flow?.id));
    const parseTs = (v?: string) => {
      if (!v) return 0;
      const t = new Date(v).getTime();
      return Number.isFinite(t) ? t : 0;
    };
    return list
      .slice()
      .sort((a, b) => {
        const aTs = parseTs(a.updated_at) || parseTs(a.created_at);
        const bTs = parseTs(b.updated_at) || parseTs(b.created_at);
        return bTs - aTs;
      });
  }, [flowsQuery.data]);

  const scripts = useMemo(
    () => normalizeCollection<Script>(scriptsQuery.data, "scripts").filter((script) => Boolean(script?.id)),
    [scriptsQuery.data],
  );

  const whatsappTemplatesCount = useMemo(
    () => whatsappTemplatesQuery.data?.templates?.length ?? 0,
    [whatsappTemplatesQuery.data]
  );


  const automationStats = useMemo(() => computeAutomationStats(workflows), [workflows]);

  const scriptStats = useMemo(() => computeScriptStats(scripts), [scripts]);

  const timeline = useMemo(() => workflows.slice(0, 6), [workflows]);

  const { toast } = useToast();

  // Dialog state for creating new flow
  const [showNewFlowDialog, setShowNewFlowDialog] = useState(false);
  const [newFlowName, setNewFlowName] = useState("");
  const [flowNameError, setFlowNameError] = useState("");

  // Dialog state for creating new script
  const [showNewScriptDialog, setShowNewScriptDialog] = useState(false);
  const [newScriptName, setNewScriptName] = useState("");
  const [scriptNameError, setScriptNameError] = useState("");

  // Create draft flow mutation
  const createFlowMutation = useMutation({
    mutationFn: async (flowName: string) => {
      const payload = {
        name: flowName,
        description: "",
        definition: {
          nodes: [],
          edges: [],
        },
      };
      const res = await apiRequest("POST", apiV1("/flows/"), { data: payload });
      return await res.json();
    },
    onSuccess: (data) => {
      if (data.id) {
        setShowNewFlowDialog(false);
        setNewFlowName("");
        setFlowNameError("");
        navigate(`/flows/${data.id}/edit`);
      }
    },
    onError: (error) => {
      toast({
        title: "Failed to create flow",
        description: error instanceof Error ? error.message : "An error occurred",
        variant: "destructive",
      });
    },
  });

  // Create draft script mutation
  const createScriptMutation = useMutation({
    mutationFn: async (scriptName: string) => {
      const payload = {
        name: scriptName,
        description: "",
        code: "",
        language: "python",
      };
      const res = await apiRequest("POST", apiV1("/scripts/"), { data: payload });
      return await res.json();
    },
    onSuccess: (data) => {
      if (data.id) {
        setShowNewScriptDialog(false);
        setNewScriptName("");
        setScriptNameError("");
        navigate(`/scripts/${data.id}/edit`);
      }
    },
    onError: (error) => {
      toast({
        title: "Failed to create script",
        description: error instanceof Error ? error.message : "An error occurred",
        variant: "destructive",
      });
    },
  });

  // Create agent mutation (for sidebar button)
  const createAgentMutation = useMutation({
    mutationFn: async (agentName: string) => {
      const payload = {
        name: agentName,
        enabled: true,
        model: "gpt-4o",
        instructions: "You are a helpful AI assistant.",
        channel: null,
        channel_id: null,
        tools: null,
      };
      const res = await apiRequest("POST", apiV1("/settings/agents/"), { data: payload });
      return await res.json();
    },
    onSuccess: () => {
      setShowNewAgentDialog(false);
      setNewAgentName("");
      setAgentNameError("");
      queryClient.invalidateQueries({ queryKey: [apiV1("/settings/agents/")] });
      toast({
        title: "Agent created",
        description: "Your AI agent has been created successfully.",
      });
    },
    onError: (error) => {
      toast({
        title: "Failed to create agent",
        description: error instanceof Error ? error.message : "An error occurred",
        variant: "destructive",
      });
    },
  });

  const handleCreateAgent = () => {
    const trimmedName = newAgentName.trim();
    if (!trimmedName) {
      setAgentNameError("Agent name is required");
      return;
    }
    createAgentMutation.mutate(trimmedName);
  };

  const handleNewFlow = () => {
    setNewFlowName("");
    setFlowNameError("");
    setShowNewFlowDialog(true);
  };

  const handleCreateFlow = () => {
    const trimmedName = newFlowName.trim();
    
    // Validate name is not empty
    if (!trimmedName) {
      setFlowNameError("Flow name is required");
      return;
    }

    // Check for duplicate names (case-insensitive)
    const isDuplicate = workflows.some(
      (flow) => flow.name.toLowerCase() === trimmedName.toLowerCase()
    );

    if (isDuplicate) {
      setFlowNameError("A flow with this name already exists");
      return;
    }

    // Create the flow
    createFlowMutation.mutate(trimmedName);
  };
  
  const handleNewScript = () => {
    setNewScriptName("");
    setScriptNameError("");
    setShowNewScriptDialog(true);
  };

  const handleCreateScript = () => {
    const trimmedName = newScriptName.trim();
    
    // Validate name is not empty
    if (!trimmedName) {
      setScriptNameError("Script name is required");
      return;
    }

    // Check for duplicate names (case-insensitive)
    const isDuplicate = scripts.some(
      (script) => script.name.toLowerCase() === trimmedName.toLowerCase()
    );

    if (isDuplicate) {
      setScriptNameError("A script with this name already exists");
      return;
    }

    // Create the script
    createScriptMutation.mutate(trimmedName);
  };

  const tabItems = [
    { id: "flows" as TabType, label: "Flows", icon: Layers },
    { id: "campaigns" as TabType, label: "Campaigns", icon: Building2 },
    { id: "audiences" as TabType, label: "Audiences", icon: Users },
    { id: "ai_agents" as TabType, label: "AI Agents", icon: Bot },
    { id: "components" as TabType, label: "Components", icon: Wrench },
    { id: "analysis" as TabType, label: "Analysis", icon: BarChart3 },
    { id: "reports" as TabType, label: "Reports", icon: FileText },
    { id: "task_monitor" as TabType, label: "Task Monitor", icon: Activity },
  ];

  const [showNewAgentDialog, setShowNewAgentDialog] = useState(false);
  const [newAgentName, setNewAgentName] = useState("");
  const [agentNameError, setAgentNameError] = useState("");

  const workflowRefs = useMemo(
    () => workflows.map((w) => ({ id: w.id, name: w.name || w.id })),
    [workflows]
  );

  return (
    <div className="h-full flex">
      <div className="w-64 border-r border-border bg-background flex flex-col shrink-0">
        <div className="p-3 border-b border-border">
          <h2 className="font-semibold text-sm">Automation Studio</h2>
          <p className="text-xs text-muted-foreground mt-0.5">Design & orchestrate</p>
        </div>

        <div className="p-2 space-y-1 border-b border-border">
          {tabItems.map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => setActiveTab(tab.id)}
              className={`w-full flex items-center gap-2 px-3 py-2 text-sm rounded-md transition-colors ${
                activeTab === tab.id
                  ? "bg-accent text-accent-foreground"
                  : "text-muted-foreground hover-elevate"
              }`}
              data-testid={`tab-${tab.id}`}
            >
              <tab.icon className="h-4 w-4" />
              {tab.label}
            </button>
          ))}
          <button
            type="button"
            onClick={() => navigate("/agent-console")}
            className="w-full flex items-center gap-2 px-3 py-2 text-sm rounded-md transition-colors text-muted-foreground hover-elevate"
            data-testid="button-open-robot-studio"
          >
            <Bot className="h-4 w-4" />
            Robot Studio
          </button>
        </div>
      </div>

      <div className="flex-1 flex flex-col bg-muted/20 overflow-hidden">
        {activeTab === "ai_agents" ? (
          <AIAgentsWorkspace />
        ) : (
          <ScrollArea className="flex-1">
            <div className="pl-2 pr-4 py-4">
              {activeTab === "flows" && (
                <FlowsWorkspace
                  workflows={workflows}
                  automationStats={automationStats}
                  isLoading={flowsQuery.isLoading}
                  isError={flowsQuery.isError}
                  error={flowsQuery.error as Error | null}
                  onNewFlow={handleNewFlow}
                  navigateTo={navigate}
                  timeline={timeline}
                />
              )}

              {activeTab === "campaigns" && <CampaignsWorkspace />}

              {activeTab === "audiences" && <AudiencesWorkspace />}

              {activeTab === "components" && (
                <ComponentsWorkspace 
                  scriptsCount={scripts.length}
                  whatsappTemplatesCount={whatsappTemplatesCount}
                />
              )}

              {activeTab === "analysis" && (
                <AnalysisWorkspace
                  workflows={workflows}
                  scripts={scripts}
                  automationStats={automationStats}
                  scriptStats={scriptStats}
                  timeline={timeline}
                />
              )}

              {activeTab === "reports" && (
                <div className="space-y-4">
                  <GlassPanel className="p-4 grid grid-cols-2 md:grid-cols-4 gap-4">
                    <ScorecardItem label="Total Flows" value={`${automationStats.totalFlows}`} helper="Defined flows" />
                    <ScorecardItem label="Active Flows" value={`${automationStats.activeFlows}`} helper="Enabled/live" />
                    <ScorecardItem label="Draft Flows" value={`${automationStats.draftFlows}`} helper="In progress" />
                    <ScorecardItem label="Total Runs" value={`${automationStats.totalRuns}`} helper="All-time executions" />
                  </GlassPanel>
                  <ReportsHubWorkspace
                    workflows={workflowRefs}
                    whatsappTemplates={(whatsappTemplatesQuery.data as any)?.templates ?? []}
                  />
                </div>
              )}

              {activeTab === "task_monitor" && <TaskMonitorWorkspace />}
            </div>
          </ScrollArea>
        )}
      </div>

      <Dialog open={showNewFlowDialog} onOpenChange={setShowNewFlowDialog}>
        <DialogContent data-testid="dialog-new-flow">
          <DialogHeader>
            <DialogTitle>Create New Flow</DialogTitle>
            <DialogDescription>
              Enter a unique name for your new workflow.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="flow-name">Flow Name</Label>
              <Input
                id="flow-name"
                data-testid="input-flow-name"
                placeholder="e.g., Customer Onboarding Flow"
                value={newFlowName}
                onChange={(e) => {
                  setNewFlowName(e.target.value);
                  setFlowNameError("");
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !createFlowMutation.isPending) {
                    handleCreateFlow();
                  }
                }}
                className={flowNameError ? "border-destructive" : ""}
                autoFocus
              />
              {flowNameError && (
                <p className="text-sm text-destructive" data-testid="error-flow-name">
                  {flowNameError}
                </p>
              )}
            </div>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setShowNewFlowDialog(false)}
              disabled={createFlowMutation.isPending}
              data-testid="button-cancel-flow"
            >
              Cancel
            </Button>
            <Button
              onClick={handleCreateFlow}
              disabled={createFlowMutation.isPending}
              data-testid="button-create-flow"
            >
              {createFlowMutation.isPending ? "Creating..." : "Create Flow"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={showNewScriptDialog} onOpenChange={setShowNewScriptDialog}>
        <DialogContent data-testid="dialog-new-script">
          <DialogHeader>
            <DialogTitle>Create New Script</DialogTitle>
            <DialogDescription>
              Enter a unique name for your new script.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="script-name">Script Name</Label>
              <Input
                id="script-name"
                data-testid="input-script-name"
                placeholder="e.g., Data Validation Script"
                value={newScriptName}
                onChange={(e) => {
                  setNewScriptName(e.target.value);
                  setScriptNameError("");
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !createScriptMutation.isPending) {
                    handleCreateScript();
                  }
                }}
                className={scriptNameError ? "border-destructive" : ""}
                autoFocus
              />
              {scriptNameError && (
                <p className="text-sm text-destructive" data-testid="error-script-name">
                  {scriptNameError}
                </p>
              )}
            </div>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setShowNewScriptDialog(false)}
              disabled={createScriptMutation.isPending}
              data-testid="button-cancel-script"
            >
              Cancel
            </Button>
            <Button
              onClick={handleCreateScript}
              disabled={createScriptMutation.isPending}
              data-testid="button-create-script"
            >
              {createScriptMutation.isPending ? "Creating..." : "Create Script"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* New Agent Dialog */}
      <Dialog open={showNewAgentDialog} onOpenChange={setShowNewAgentDialog}>
        <DialogContent data-testid="dialog-new-agent">
          <DialogHeader>
            <DialogTitle>Create New AI Agent</DialogTitle>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <label htmlFor="agent-name" className="text-sm font-medium">
                Agent Name
              </label>
              <Input
                id="agent-name"
                placeholder="Enter agent name..."
                value={newAgentName}
                onChange={(e) => {
                  setNewAgentName(e.target.value);
                  setAgentNameError("");
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !createAgentMutation.isPending) {
                    handleCreateAgent();
                  }
                }}
                className={agentNameError ? "border-destructive" : ""}
                autoFocus
                data-testid="input-agent-name"
              />
              {agentNameError && (
                <p className="text-sm text-destructive" data-testid="error-agent-name">
                  {agentNameError}
                </p>
              )}
            </div>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setShowNewAgentDialog(false)}
              disabled={createAgentMutation.isPending}
              data-testid="button-cancel-agent"
            >
              Cancel
            </Button>
            <Button
              onClick={handleCreateAgent}
              disabled={createAgentMutation.isPending}
              data-testid="button-create-agent"
            >
              {createAgentMutation.isPending ? "Creating..." : "Create Agent"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

interface FlowsWorkspaceProps {
  workflows: Workflow[];
  automationStats: ReturnType<typeof computeAutomationStats>;
  isLoading: boolean;
  isError: boolean;
  error: Error | null;
  onNewFlow: () => void;
  navigateTo: (path: string) => void;
  timeline: Workflow[];
}

type AutomationStats = ReturnType<typeof computeAutomationStats>;

function computeAutomationStats(workflows: Workflow[]) {
  const totalFlows = workflows.length;
  const activeFlows = workflows.filter((w) => (w.status ?? "").toLowerCase() === "active").length;
  const draftFlows = workflows.filter((w) => !w.status || w.status?.toLowerCase() === "draft").length;
  const totalRuns = workflows.reduce((acc, flow) => acc + (flow.runs ?? 0), 0);
  return { totalFlows, activeFlows, draftFlows, totalRuns };
}

interface StatCardProps {
  label: string;
  value: string;
  helper?: string;
  icon: ComponentType<{ className?: string }>;
  accent: string;
}

const StatCard = ({ label, value, helper, icon: Icon, accent }: StatCardProps) => (
  <GlassPanel className="p-4 flex flex-col gap-3" data-testid={`stat-${label.toLowerCase().replace(/\s+/g, "-")}`}>
    <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${accent}`}>
      <Icon className="h-5 w-5" />
    </div>
    <div>
      <p className="text-xs uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="text-3xl font-bold tabular-nums">{value}</p>
      {helper && <p className="text-xs text-muted-foreground mt-1">{helper}</p>}
    </div>
  </GlassPanel>
);

const LoadingList = () => (
  <div className="space-y-3">
    {[...Array(3)].map((_, idx) => (
      <GlassPanel key={idx} className="p-4">
        <div className="space-y-2">
          <Skeleton className="h-4 w-1/3" />
          <Skeleton className="h-3 w-2/3" />
        </div>
      </GlassPanel>
    ))}
  </div>
);

const formatTimestamp = (value?: string | null) => {
  if (!value) return "Never";
  const date = new Date(value);
  return `${date.toLocaleDateString()} • ${date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;
};

function FlowsWorkspace({
  workflows,
  automationStats,
  isLoading,
  isError,
  error,
  onNewFlow,
  navigateTo,
  timeline,
}: FlowsWorkspaceProps) {
  const hasWorkflows = workflows.length > 0;

  return (
    <div className="space-y-8">
      <div className="grid gap-3 grid-cols-4">
        <StatCard
          label="Total flows"
          value={automationStats.totalFlows.toString()}
          helper="All automation blueprints"
          icon={Layers}
          accent="bg-primary/10 text-primary"
        />
        <StatCard
          label="Active"
          value={automationStats.activeFlows.toString()}
          helper="Live & processing events"
          icon={Zap}
          accent="bg-emerald-100 text-emerald-600"
        />
        <StatCard
          label="Drafts"
          value={automationStats.draftFlows.toString()}
          helper="Need review before launch"
          icon={Clock}
          accent="bg-amber-100 text-amber-600"
        />
        <StatCard
          label="Runs"
          value={automationStats.totalRuns.toString()}
          helper="Total executions tracked"
          icon={PlayCircle}
          accent="bg-indigo-100 text-indigo-600"
        />
      </div>

      <div className="grid gap-6 xl:grid-cols-3">
        <GlassPanel className="p-6 xl:col-span-2 space-y-5">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <p className="text-xs uppercase tracking-wide text-muted-foreground">Automation library</p>
              <h2 className="text-xl font-semibold">Flows</h2>
            </div>
            <Button size="sm" onClick={onNewFlow} data-testid="button-create-first-flow">
              <Plus className="h-4 w-4 mr-2" />
              Create flow
            </Button>
          </div>
          {isLoading ? (
            <LoadingList />
          ) : isError ? (
            <ErrorDisplay error={error ?? new Error("Unable to load flows") } endpoint="api/v1/flows" />
          ) : workflows.length === 0 ? (
            <EmptyState
              title="No flows match"
              description={hasWorkflows ? "Try a different search" : "Create your first automation to get started."}
            />
          ) : (
            <div className="space-y-3">
              {workflows.map((workflow) => (
                (() => {
                  const meta = getWorkflowStatusMeta(workflow.status);
                  return (
                <GlassPanel
                  key={workflow.id}
                  className="p-4 hover-elevate cursor-pointer"
                  onClick={() => navigateTo(`/flows/${workflow.id}/edit`)}
                  data-testid={`card-workflow-${workflow.id}`}
                >
                  <div className="flex items-start justify-between">
                    <div>
                      <div className="flex items-center gap-3">
                        <h3 className="font-semibold" data-testid={`text-workflow-name-${workflow.id}`}>
                          {workflow.name}
                        </h3>
                        <Badge
                          variant={meta.variant}
                          className={meta.className}
                          data-testid={`badge-status-${workflow.id}`}
                        >
                          {meta.label}
                        </Badge>
                      </div>
                      <p className="text-sm text-muted-foreground mt-2">
                        {workflow.description ?? "No description provided"}
                      </p>
                      <div className="flex flex-wrap items-center gap-4 mt-3 text-xs text-muted-foreground">
                        <div className="flex items-center gap-1">
                          <PlayCircle className="h-3.5 w-3.5" />
                          {workflow.runs ?? 0} runs
                        </div>
                        <div className="flex items-center gap-1">
                          <Clock className="h-3.5 w-3.5" />
                          Updated {workflow.updated_at ? formatTimestamp(workflow.updated_at) : "never"}
                        </div>
                      </div>
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="gap-1"
                      onClick={(event) => {
                        event.stopPropagation();
                        navigateTo(`/flows/${workflow.id}/edit`);
                      }}
                      data-testid={`button-edit-${workflow.id}`}
                    >
                      Edit
                    </Button>
                  </div>
                </GlassPanel>
                  );
                })()
              ))}
            </div>
          )}
        </GlassPanel>

        <GlassPanel className="p-6 space-y-4">
          <div>
            <p className="text-xs uppercase tracking-wide text-muted-foreground">Latest activity</p>
            <h2 className="text-xl font-semibold">Timeline</h2>
          </div>
          {timeline.length === 0 ? (
            <EmptyState
              title="No activity"
              description="Publish or edit a flow to populate the timeline."
            />
          ) : (
            <div className="space-y-4">
              {timeline.map((flow) => (
                <div key={flow.id} className="flex items-start gap-3">
                  <div className="mt-1">
                    <Circle className={`h-3 w-3 ${getStatusColor(flow.status)}`} />
                  </div>
                  <div className="flex-1">
                    <p className="font-medium text-sm">{flow.name}</p>
                    <p className="text-xs text-muted-foreground">{flow.status ?? "draft"} • {formatTimestamp(flow.updated_at)}</p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </GlassPanel>
      </div>

      <GlassPanel className="p-6">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-wide text-muted-foreground">Need inspiration?</p>
            <h2 className="text-xl font-semibold">Automation starter kits</h2>
          </div>
          <Button variant="outline" size="sm" onClick={onNewFlow}>
            <Plus className="h-4 w-4 mr-2" />
            New automation
          </Button>
        </div>
        <div className="grid gap-4 mt-6 md:grid-cols-3">
          {starterKits.map((kit) => (
            <div key={kit.title} className="rounded-2xl border border-border/50 p-4 bg-gradient-to-br from-background via-background to-muted/30">
              <kit.icon className="h-6 w-6 mb-3 text-primary" />
              <p className="font-semibold">{kit.title}</p>
              <p className="text-sm text-muted-foreground mt-1">{kit.description}</p>
              <Button variant="ghost" className="px-0 mt-2 text-primary" onClick={onNewFlow}>
                Use template
              </Button>
            </div>
          ))}
        </div>
      </GlassPanel>
    </div>
  );
}

const starterKits: Array<{ title: string; description: string; icon: ComponentType<{ className?: string }> }> = [
  {
    title: "Lead enrichment",
    description: "Trigger enrichment scripts as soon as a new lead arrives.",
    icon: Zap,
  },
  {
    title: "Sales follow-up",
    description: "Branch conversations across WhatsApp and Email.",
    icon: Layers,
  },
  {
    title: "Onboarding concierge",
    description: "Automate onboarding tasks with conditional logic.",
    icon: Activity,
  },
];

const statusColorMap: Record<string, string> = {
  active: "text-emerald-500",
  live: "text-emerald-500",
  draft: "text-amber-500",
  paused: "text-amber-500",
  error: "text-red-500",
};

const getStatusColor = (status?: string) => {
  if (!status) return "text-foreground/40";
  return statusColorMap[status.toLowerCase()] || "text-foreground/40";
};

const getWorkflowStatusMeta = (status?: string) => {
  const normalized = (status ?? "draft").toLowerCase();
  if (normalized === "active") {
    return { label: "Active", variant: "default" as const, className: "bg-emerald-600 hover:bg-emerald-700 text-white" };
  }
  if (normalized === "inactive" || normalized === "paused") {
    return { label: "Inactive", variant: "secondary" as const, className: "" };
  }
  if (normalized === "error" || normalized === "failed") {
    return { label: "Error", variant: "destructive" as const, className: "" };
  }
  return { label: "Draft", variant: "outline" as const, className: "" };
};

interface ScriptsWorkspaceProps {
  scripts: Script[];
  originalScripts: Script[];
  scriptStats: ReturnType<typeof computeScriptStats>;
  isLoading: boolean;
  isError: boolean;
  error: Error | null;
  onNewScript: () => void;
  navigateTo: (path: string) => void;
}

function computeScriptStats(scripts: Script[]) {
  const total = scripts.length;
  const approved = scripts.filter((s) => s.status === "approved").length;
  const pending = scripts.filter((s) => s.status === "pending_approval").length;
  const draft = scripts.filter((s) => s.status === "draft" || !s.status).length;
  return { total, approved, pending, draft };
}

function ScriptsWorkspace({
  scripts,
  originalScripts,
  scriptStats,
  isLoading,
  isError,
  error,
  onNewScript,
  navigateTo,
}: ScriptsWorkspaceProps) {
  return (
    <div className="space-y-8">
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Scripts" value={scriptStats.total.toString()} helper="All automation scripts" icon={FileCode} accent="bg-primary/10 text-primary" />
        <StatCard label="Approved" value={scriptStats.approved.toString()} helper="Ready for flows" icon={TrendingUp} accent="bg-emerald-100 text-emerald-600" />
        <StatCard label="Pending" value={scriptStats.pending.toString()} helper="Awaiting review" icon={Clock} accent="bg-amber-100 text-amber-600" />
        <StatCard label="Drafts" value={scriptStats.draft.toString()} helper="Still being crafted" icon={Layers} accent="bg-indigo-100 text-indigo-600" />
      </div>

      <GlassPanel className="p-6">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-wide text-muted-foreground">Script library</p>
            <h2 className="text-xl font-semibold">Reusable automations</h2>
          </div>
          <Button onClick={onNewScript} size="sm" data-testid="button-new-script">
            <Plus className="h-4 w-4 mr-2" />
            New script
          </Button>
        </div>

        {isLoading ? (
          <LoadingList />
        ) : isError ? (
          <ErrorDisplay error={error ?? new Error("Unable to load scripts")} endpoint={SCRIPTS_PATH} />
        ) : scripts.length === 0 ? (
          <EmptyState
            title={originalScripts.length === 0 ? "No scripts yet" : "No scripts match"}
            description={originalScripts.length === 0 ? "Create your first script to use inside flows." : "Try a different search."}
          />
        ) : (
          <div className="grid gap-4 mt-6 sm:grid-cols-2 lg:grid-cols-3">
            {scripts.map((script) => (
              <GlassPanel
                key={script.id}
                className="p-4 space-y-3 hover-elevate cursor-pointer"
                onClick={() => navigateTo(`/scripts/${script.id}/edit`)}
                data-testid={`card-script-${script.id}`}
              >
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="font-semibold text-base">{script.name}</p>
                    {getScriptStatusBadge(script.status)}
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="gap-1"
                    onClick={(event) => {
                      event.stopPropagation();
                      navigateTo(`/scripts/${script.id}/edit`);
                    }}
                    data-testid={`button-edit-script-${script.id}`}
                  >
                    Edit
                  </Button>
                </div>
                <p className="text-sm text-muted-foreground">
                  {script.description ?? "No description provided"}
                </p>
                <div className="text-xs text-muted-foreground">
                  Updated {formatTimestamp(script.updated_at)}
                </div>
              </GlassPanel>
            ))}
          </div>
        )}
      </GlassPanel>
    </div>
  );
}

const getScriptStatusBadge = (status?: string) => {
  const config = {
    draft: { variant: "outline" as const, label: "Draft" },
    pending_approval: { variant: "secondary" as const, label: "Pending" },
    approved: { variant: "default" as const, label: "Approved" },
    rejected: { variant: "destructive" as const, label: "Rejected" },
  };
  const meta = config[(status as keyof typeof config) ?? "draft"] ?? config.draft;
  return <Badge variant={meta.variant}>{meta.label}</Badge>;
};

interface AnalysisWorkspaceProps {
  workflows: Workflow[];
  scripts: Script[];
  automationStats: AutomationStats;
  scriptStats: ReturnType<typeof computeScriptStats>;
  timeline: Workflow[];
}

type AnalysisExecutionMode = "production" | "testing" | "preview";

interface ExecutionTimelineStep {
  step_index: number;
  node_id: string;
  node_name: string;
  node_type: string;
  status: "pending" | "running" | "completed" | "failed" | "skipped";
  started_at?: string;
  completed_at?: string;
  duration_ms?: number;
  input?: any;
  output?: any;
  error?: string;
}

interface AnalysisExecution {
  id: string;
  flow_id: string;
  flow_name?: string;
  status: "pending" | "running" | "completed" | "failed" | "cancelled";
  started_at?: string;
  completed_at?: string;
  execution_mode?: AnalysisExecutionMode;
  duration_ms?: number;
  error_message?: string;
  timeline?: ExecutionTimelineStep[];
  output?: {
    steps?: ExecutionTimelineStep[];
    context?: any;
  };
  context?: any;
}

interface AnalysisExecutionsResponse {
  results?: AnalysisExecution[];
  executions?: AnalysisExecution[];
  data?: AnalysisExecution[];
  pagination?: {
    total_items: number;
    current_page: number;
    total_pages: number;
  };
}

const ANALYSIS_MODE_ICON_MAP: Record<AnalysisExecutionMode, typeof Rocket> = {
  production: Rocket,
  testing: FlaskConical,
  preview: Eye,
};

const ANALYSIS_MODE_COLORS: Record<AnalysisExecutionMode, string> = {
  production: "text-green-600 dark:text-green-400",
  testing: "text-amber-600 dark:text-amber-400",
  preview: "text-blue-600 dark:text-blue-400",
};

const ANALYSIS_MODE_BG_COLORS: Record<AnalysisExecutionMode, string> = {
  production: "bg-green-100 dark:bg-green-900/30",
  testing: "bg-amber-100 dark:bg-amber-900/30",
  preview: "bg-blue-100 dark:bg-blue-900/30",
};

const EXECUTIONS_PATH = apiV1("/flows/executions/");

const STEP_STATUS_COLORS: Record<string, { bg: string; text: string; icon: typeof CheckCircle }> = {
  completed: { bg: "bg-green-100 dark:bg-green-900", text: "text-green-600 dark:text-green-400", icon: CheckCircle },
  failed: { bg: "bg-red-100 dark:bg-red-900", text: "text-red-600 dark:text-red-400", icon: XCircle },
  running: { bg: "bg-blue-100 dark:bg-blue-900", text: "text-blue-600 dark:text-blue-400", icon: Activity },
  pending: { bg: "bg-slate-100 dark:bg-slate-800", text: "text-slate-600 dark:text-slate-400", icon: Clock },
  skipped: { bg: "bg-gray-100 dark:bg-gray-800", text: "text-gray-500 dark:text-gray-400", icon: Circle },
};

function AnalysisWorkspace({ workflows, scripts, automationStats, scriptStats, timeline }: AnalysisWorkspaceProps) {
  const [selectedExecution, setSelectedExecution] = useState<AnalysisExecution | null>(null);
  const { toast } = useToast();

  // Fetch detailed execution when one is selected
  const executionDetailQuery = useQuery<AnalysisExecution>({
    queryKey: [EXECUTIONS_PATH, selectedExecution?.id],
    queryFn: async () => {
      const raw = await fetchJson<any>(apiV1(`/flows/executions/${selectedExecution!.id}/`));
      // Backends vary: sometimes returns the execution directly, other times wraps it.
      const exec = raw?.execution ?? raw?.result ?? raw?.data ?? raw;
      return exec as AnalysisExecution;
    },
    enabled: !!selectedExecution?.id,
    staleTime: 30000,
  });

  // Transform execution data to extract timeline steps
  const executionTimeline = useMemo(() => {
    const detail = executionDetailQuery.data;
    if (!detail) return [];
    const normalizeStatus = (v: any): ExecutionTimelineStep["status"] => {
      const s = String(v ?? "").toLowerCase();
      if (s === "success" || s === "succeeded" || s === "ok" || s === "completed") return "completed";
      if (s === "fail" || s === "failed" || s === "error") return "failed";
      if (s === "running") return "running";
      if (s === "skipped") return "skipped";
      return "pending";
    };

    const fromLogs = (logs: any[]): ExecutionTimelineStep[] => {
      return logs.map((l, idx) => {
        const nodeId = String(l?.node_id ?? l?.action_id ?? l?.id ?? idx + 1);
        const nodeType = String(l?.node_type ?? l?.action_type ?? l?.type ?? "step");
        const nodeName = String(l?.node_name ?? l?.action_id ?? l?.name ?? nodeType);
        const ts = l?.timestamp ?? l?.started_at ?? l?.completed_at;
        return {
          step_index: typeof l?.step_index === "number" ? l.step_index : idx + 1,
          node_id: nodeId,
          node_name: nodeName,
          node_type: nodeType,
          status: normalizeStatus(l?.status),
          started_at: typeof l?.started_at === "string" ? l.started_at : typeof ts === "string" ? ts : undefined,
          completed_at: typeof l?.completed_at === "string" ? l.completed_at : undefined,
          duration_ms: typeof l?.duration_ms === "number" ? l.duration_ms : undefined,
          input: l?.input ?? l?.data?.input,
          output: l?.output ?? l?.data?.output ?? (l?.data && typeof l.data === "object" ? l.data : undefined),
          error: typeof l?.error === "string" ? l.error : typeof l?.message === "string" ? l.message : undefined,
        };
      });
    };

    const normalizeStepsArray = (steps: any[]): ExecutionTimelineStep[] => {
      return steps.map((s, idx) => ({
        step_index: typeof s?.step_index === "number" ? s.step_index : idx + 1,
        node_id: String(s?.node_id ?? s?.nodeId ?? s?.id ?? idx + 1),
        node_name: String(s?.node_name ?? s?.nodeName ?? s?.name ?? s?.node_id ?? s?.nodeId ?? "Step"),
        node_type: String(s?.node_type ?? s?.nodeType ?? s?.type ?? "step"),
        status: normalizeStatus(s?.status),
        started_at: typeof s?.started_at === "string" ? s.started_at : undefined,
        completed_at: typeof s?.completed_at === "string" ? s.completed_at : undefined,
        duration_ms: typeof s?.duration_ms === "number" ? s.duration_ms : undefined,
        input: s?.input,
        output: s?.output,
        error: typeof s?.error === "string" ? s.error : undefined,
      }));
    };

    // API returns steps at several possible paths depending on backend version:
    const maybeLogs = (detail as any)?.logs;
    if (Array.isArray(maybeLogs) && maybeLogs.length > 0) return fromLogs(maybeLogs);

    const steps =
      (detail as any).timeline ??
      (detail as any).steps ??
      (detail as any).execution_steps ??
      (detail as any).output?.steps ??
      (detail as any).output?.timeline ??
      [];

    if (Array.isArray(steps)) return normalizeStepsArray(steps);
    return [];
  }, [executionDetailQuery.data]);

  const executionsQuery = useQuery<AnalysisExecutionsResponse>({
    queryKey: [EXECUTIONS_PATH, { page: 1, page_size: 500 }],
    queryFn: () => fetchJson<AnalysisExecutionsResponse>(EXECUTIONS_PATH, { 
      page: "1", 
      page_size: "500" 
    }),
    refetchInterval: 30000,
  });

  const executions = useMemo(() => {
    const data = executionsQuery.data;
    if (!data) return [];
    if (Array.isArray(data)) return data as AnalysisExecution[];
    return (data.results ?? data.executions ?? data.data ?? []) as AnalysisExecution[];
  }, [executionsQuery.data]);

  const executionStats = useMemo(() => {
    const total = executions.length;
    const completed = executions.filter(e => e.status === "completed").length;
    const failed = executions.filter(e => e.status === "failed").length;
    const running = executions.filter(e => e.status === "running").length;
    const successRate = total > 0 ? Math.round((completed / total) * 100) : 0;
    
    const durations = executions
      .filter(e => e.duration_ms !== undefined && e.duration_ms > 0)
      .map(e => e.duration_ms!);
    const avgDuration = durations.length > 0 
      ? Math.round(durations.reduce((a, b) => a + b, 0) / durations.length)
      : 0;

    const byMode: Record<AnalysisExecutionMode, { total: number; completed: number; failed: number }> = {
      production: { total: 0, completed: 0, failed: 0 },
      testing: { total: 0, completed: 0, failed: 0 },
      preview: { total: 0, completed: 0, failed: 0 },
    };

    executions.forEach(e => {
      const rawMode = e.execution_mode ?? "production";
      const mode: AnalysisExecutionMode = (rawMode === "production" || rawMode === "testing" || rawMode === "preview") ? rawMode : "production";
      byMode[mode].total++;
      if (e.status === "completed") byMode[mode].completed++;
      if (e.status === "failed") byMode[mode].failed++;
    });

    return { total, completed, failed, running, successRate, avgDuration, byMode };
  }, [executions]);

  const recentFailures = useMemo(() => {
    return executions
      .filter(e => e.status === "failed")
      .slice(0, 5);
  }, [executions]);

  const flowSuccessRate = useMemo(() => {
    if (automationStats.totalRuns === 0) return 0;
    const active = workflows.filter((w) => (w.status ?? "").toLowerCase() === "active").length;
    return Math.min(100, Math.round((active / (automationStats.totalFlows || 1)) * 100));
  }, [workflows, automationStats.totalFlows, automationStats.totalRuns]);

  const formatDuration = (ms?: number) => {
    if (!ms) return "-";
    if (ms < 1000) return `${ms}ms`;
    if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
    return `${(ms / 60000).toFixed(1)}m`;
  };

  const timelineChartData = useMemo(() => {
    // Aggregate by hour-of-day over the last 30 days
    const cutoff = Date.now() - 30 * 24 * 60 * 60 * 1000;
    const buckets: { hour: string; completed: number; failed: number; running: number }[] = Array.from(
      { length: 24 },
      (_, h) => ({
        hour: `${String(h).padStart(2, "0")}:00`,
        completed: 0,
        failed: 0,
        running: 0,
      })
    );

    executions.forEach((e) => {
      if (!e.started_at) return;
      const ts = new Date(e.started_at).getTime();
      if (Number.isNaN(ts) || ts < cutoff) return;
      const d = new Date(ts);
      const h = d.getHours();
      if (e.status === "completed") buckets[h].completed += 1;
      else if (e.status === "failed") buckets[h].failed += 1;
      else if (e.status === "running" || e.status === "pending") buckets[h].running += 1;
    });

    return buckets;
  }, [executions]);

  return (
    <div className="space-y-8">
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <StatCard 
          label="Total Executions" 
          value={executionsQuery.isLoading ? "..." : executionStats.total.toString()} 
          helper="Flow runs in last 50" 
          icon={PlayCircle} 
          accent="bg-primary/10 text-primary" 
        />
        <StatCard 
          label="Success Rate" 
          value={executionsQuery.isLoading ? "..." : `${executionStats.successRate}%`} 
          helper="Completed vs total" 
          icon={CheckCircle} 
          accent="bg-emerald-100 text-emerald-600 dark:bg-emerald-900/30" 
        />
        <StatCard 
          label="Avg Duration" 
          value={executionsQuery.isLoading ? "..." : formatDuration(executionStats.avgDuration)} 
          helper="Mean execution time" 
          icon={Clock} 
          accent="bg-indigo-100 text-indigo-600 dark:bg-indigo-900/30" 
        />
        <StatCard 
          label="Failed" 
          value={executionsQuery.isLoading ? "..." : executionStats.failed.toString()} 
          helper="Errors to investigate" 
          icon={XCircle} 
          accent="bg-red-100 text-red-600 dark:bg-red-900/30" 
        />
      </div>

      <GlassPanel className="p-6" data-testid="panel-execution-chart">
        <div className="flex items-center justify-between mb-4">
          <div>
            <p className="text-xs uppercase tracking-wide text-muted-foreground">Execution timeline</p>
            <h2 className="text-xl font-semibold">Runs by Hour</h2>
          </div>
          <Badge variant="outline">Last 30 days</Badge>
        </div>
        {executionsQuery.isLoading ? (
          <Skeleton className="h-[200px]" />
        ) : timelineChartData.length === 0 ? (
          <EmptyState title="No execution data" description="Run some flows to see the timeline chart." />
        ) : (
          <div className="h-[200px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={timelineChartData} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                <XAxis dataKey="hour" className="text-xs" tick={{ fontSize: 11 }} />
                <YAxis className="text-xs" tick={{ fontSize: 11 }} allowDecimals={false} />
                <RechartTooltip 
                  contentStyle={{ 
                    backgroundColor: 'hsl(var(--background))', 
                    border: '1px solid hsl(var(--border))',
                    borderRadius: '8px',
                  }} 
                />
                <Legend />
                <Bar dataKey="completed" name="Completed" fill="#22c55e" radius={[4, 4, 0, 0]} />
                <Bar dataKey="failed" name="Failed" fill="#ef4444" radius={[4, 4, 0, 0]} />
                <Bar dataKey="running" name="Running" fill="#3b82f6" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </GlassPanel>

      <div className="grid gap-6 lg:grid-cols-3">
        <GlassPanel className="p-6" data-testid="panel-mode-breakdown">
          <div className="mb-4">
            <p className="text-xs uppercase tracking-wide text-muted-foreground">Execution breakdown</p>
            <h2 className="text-xl font-semibold">By Mode</h2>
          </div>
          {executionsQuery.isLoading ? (
            <div className="space-y-3">
              <Skeleton className="h-16" />
              <Skeleton className="h-16" />
              <Skeleton className="h-16" />
            </div>
          ) : (
            <div className="space-y-3">
              {(["production", "testing", "preview"] as AnalysisExecutionMode[]).map((mode) => {
                const ModeIcon = ANALYSIS_MODE_ICON_MAP[mode];
                const stats = executionStats.byMode[mode];
                const modeSuccessRate = stats.total > 0 ? Math.round((stats.completed / stats.total) * 100) : 0;
                return (
                  <div 
                    key={mode} 
                    className={`flex items-center gap-4 rounded-xl p-4 ${ANALYSIS_MODE_BG_COLORS[mode]}`}
                    data-testid={`mode-stat-${mode}`}
                  >
                    <div className={`w-10 h-10 rounded-full flex items-center justify-center bg-background/60`}>
                      <ModeIcon className={`h-5 w-5 ${ANALYSIS_MODE_COLORS[mode]}`} />
                    </div>
                    <div className="flex-1">
                      <p className="font-semibold capitalize">{mode}</p>
                      <p className="text-xs text-muted-foreground">
                        {stats.total} runs, {modeSuccessRate}% success
                      </p>
                    </div>
                    <div className="text-right">
                      <p className="text-lg font-bold">{stats.total}</p>
                      <p className="text-xs text-muted-foreground">
                        {stats.failed > 0 && <span className="text-red-500">{stats.failed} failed</span>}
                      </p>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </GlassPanel>

        <GlassPanel className="p-6" data-testid="panel-recent-failures">
          <div className="flex items-center justify-between mb-4">
            <div>
              <p className="text-xs uppercase tracking-wide text-muted-foreground">Attention needed</p>
              <h2 className="text-xl font-semibold">Recent Failures</h2>
            </div>
            <Badge variant="destructive">{recentFailures.length}</Badge>
          </div>
          {executionsQuery.isLoading ? (
            <div className="space-y-3">
              <Skeleton className="h-14" />
              <Skeleton className="h-14" />
              <Skeleton className="h-14" />
            </div>
          ) : recentFailures.length === 0 ? (
            <EmptyState 
              title="No failures" 
              description="All recent executions completed successfully." 
              icon={CheckCircle}
            />
          ) : (
            <div className="space-y-3">
              {recentFailures.map((execution) => {
                const mode = execution.execution_mode;
                const validMode = mode === "production" || mode === "testing" || mode === "preview";
                const ModeIcon = validMode ? ANALYSIS_MODE_ICON_MAP[mode] : Rocket;
                const modeColor = validMode ? ANALYSIS_MODE_COLORS[mode] : "";
                return (
                  <div 
                    key={execution.id} 
                    className="flex items-start gap-3 rounded-lg border border-red-200 dark:border-red-900/50 bg-red-50 dark:bg-red-900/20 p-3"
                    data-testid={`failure-${execution.id}`}
                  >
                    <AlertTriangle className="h-4 w-4 text-red-500 mt-0.5 shrink-0" />
                    <div className="flex-1 min-w-0">
                      <p className="font-medium text-sm truncate">{execution.flow_name ?? `Flow ${execution.flow_id}`}</p>
                      <p className="text-xs text-muted-foreground truncate">
                        {execution.error_message ?? "Unknown error"}
                      </p>
                      <div className="flex items-center gap-2 mt-1">
                        <Badge variant="outline" className="text-[10px] h-5">
                          <ModeIcon className={`h-2.5 w-2.5 mr-1 ${modeColor}`} />
                          {execution.execution_mode ?? "production"}
                        </Badge>
                        <span className="text-[10px] text-muted-foreground">
                          {formatTimestamp(execution.started_at)}
                        </span>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </GlassPanel>

        <GlassPanel className="p-6 space-y-4" data-testid="panel-scorecard">
          <div>
            <p className="text-xs uppercase tracking-wide text-muted-foreground">Health snapshot</p>
            <h2 className="text-xl font-semibold">Automation Scorecard</h2>
          </div>
          <ScorecardItem label="Total Flows" value={`${automationStats.totalFlows} blueprints`} helper="Flows defined across all stages" />
          <ScorecardItem label="Active Flows" value={`${automationStats.activeFlows} live`} helper="Ready for traffic" />
          <ScorecardItem label="Flow Health" value={`${flowSuccessRate}%`} helper="Active vs total flows" />
          <ScorecardItem label="Scripts" value={`${scriptStats.total} total`} helper="Reusable automation logic" />
          <ScorecardItem label="Review Queue" value={`${scriptStats.pending} pending`} helper="Scripts awaiting approval" />
        </GlassPanel>
      </div>

      <GlassPanel className="p-6" data-testid="panel-execution-timeline">
        <div className="flex items-center justify-between mb-4">
          <div>
            <p className="text-xs uppercase tracking-wide text-muted-foreground">Flow velocity</p>
            <h2 className="text-xl font-semibold">Latest Executions</h2>
          </div>
          <Badge variant="outline">Updated live</Badge>
        </div>
        {executionsQuery.isLoading ? (
          <div className="space-y-4">
            <Skeleton className="h-16" />
            <Skeleton className="h-16" />
            <Skeleton className="h-16" />
          </div>
        ) : executions.length === 0 ? (
          <EmptyState title="No recent executions" description="Preview or run a flow to populate analytics." />
        ) : (
          <div className="space-y-3">
            {executions.slice(0, 10).map((execution) => {
              const mode = execution.execution_mode;
              const validMode = mode === "production" || mode === "testing" || mode === "preview";
              const ModeIcon = validMode ? ANALYSIS_MODE_ICON_MAP[mode] : Rocket;
              const modeColor = validMode ? ANALYSIS_MODE_COLORS[mode] : "";
              const statusColors: Record<string, string> = {
                completed: "bg-emerald-100 text-emerald-600 dark:bg-emerald-900/30",
                failed: "bg-red-100 text-red-600 dark:bg-red-900/30",
                running: "bg-blue-100 text-blue-600 dark:bg-blue-900/30",
                pending: "bg-gray-100 text-gray-600 dark:bg-gray-800",
                cancelled: "bg-gray-100 text-gray-500 dark:bg-gray-800",
              };
              const StatusIcon = execution.status === "completed" ? CheckCircle 
                : execution.status === "failed" ? XCircle 
                : execution.status === "running" ? Activity 
                : Circle;
              return (
                <div 
                  key={execution.id} 
                  className="flex items-center gap-4 rounded-xl border border-border/50 p-4 hover-elevate cursor-pointer"
                  onClick={() => setSelectedExecution(execution)}
                  data-testid={`execution-${execution.id}`}
                >
                  <div className={`w-10 h-10 rounded-full flex items-center justify-center ${statusColors[execution.status] ?? statusColors.pending}`}>
                    <StatusIcon className="h-5 w-5" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="font-semibold truncate">{execution.flow_name ?? `Flow ${execution.flow_id}`}</p>
                    <div className="flex items-center gap-2 mt-1">
                      <Badge variant="outline" className="text-[10px] h-5">
                        <ModeIcon className={`h-2.5 w-2.5 mr-1 ${modeColor}`} />
                        {execution.execution_mode ?? "production"}
                      </Badge>
                      {execution.duration_ms && (
                        <span className="text-xs text-muted-foreground">
                          {formatDuration(execution.duration_ms)}
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="text-right text-xs text-muted-foreground">
                    <div className="capitalize">{execution.status}</div>
                    <div>{formatTimestamp(execution.started_at)}</div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </GlassPanel>

      {/* Execution Detail Dialog */}
      {selectedExecution && (
        <Dialog open={!!selectedExecution} onOpenChange={(open) => !open && setSelectedExecution(null)}>
          <DialogContent className="max-w-3xl max-h-[85vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                {(() => {
                  const statusColors: Record<string, string> = {
                    completed: "bg-emerald-100 text-emerald-600 dark:bg-emerald-900/30",
                    failed: "bg-red-100 text-red-600 dark:bg-red-900/30",
                    running: "bg-blue-100 text-blue-600 dark:bg-blue-900/30",
                    pending: "bg-gray-100 text-gray-600 dark:bg-gray-800",
                    cancelled: "bg-gray-100 text-gray-500 dark:bg-gray-800",
                  };
                  const StatusIcon = selectedExecution.status === "completed" ? CheckCircle 
                    : selectedExecution.status === "failed" ? XCircle 
                    : selectedExecution.status === "running" ? Activity 
                    : Circle;
                  return (
                    <>
                      <div className={`w-8 h-8 rounded-full flex items-center justify-center ${statusColors[selectedExecution.status] ?? statusColors.pending}`}>
                        <StatusIcon className="h-4 w-4" />
                      </div>
                      <span className="truncate">{selectedExecution.flow_name ?? `Flow ${selectedExecution.flow_id}`}</span>
                    </>
                  );
                })()}
              </DialogTitle>
              <DialogDescription>
                Execution ID: {selectedExecution.id}
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-4 py-2">
              {/* Execution Summary */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                <div>
                  <p className="text-xs text-muted-foreground mb-1">Status</p>
                  <Badge className={selectedExecution.status === "completed" ? "bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300" : selectedExecution.status === "failed" ? "bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300" : ""}>
                    {selectedExecution.status}
                  </Badge>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground mb-1">Mode</p>
                  <Badge variant="outline">{selectedExecution.execution_mode ?? "production"}</Badge>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground mb-1">Started</p>
                  <p>{selectedExecution.started_at ? new Date(selectedExecution.started_at).toLocaleString() : "-"}</p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground mb-1">Duration</p>
                  <p>{formatDuration(selectedExecution.duration_ms)}</p>
                </div>
              </div>

              {/* Error Message */}
              {selectedExecution.error_message && (
                <div className="bg-destructive/10 text-destructive text-sm p-3 rounded-md">
                  {selectedExecution.error_message}
                </div>
              )}

              {/* Step-by-Step Execution Log */}
              <div className="border rounded-lg p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 text-sm font-medium">
                    <Layers className="h-4 w-4 text-primary" />
                    Execution Steps
                  </div>
                  {executionDetailQuery.isLoading && (
                    <div className="text-xs text-muted-foreground">Loading details...</div>
                  )}
                </div>

                {executionDetailQuery.isLoading ? (
                  <div className="space-y-2">
                    <Skeleton className="h-12" />
                    <Skeleton className="h-12" />
                    <Skeleton className="h-12" />
                  </div>
                ) : executionTimeline.length > 0 ? (
                  <div className="space-y-2">
                    {executionTimeline.map((step, idx) => {
                      const stepStatus = step.status ?? "completed";
                      const stepStyle = STEP_STATUS_COLORS[stepStatus] ?? STEP_STATUS_COLORS.pending;
                      const StepIcon = stepStyle.icon;
                      return (
                        <div 
                          key={step.node_id || idx}
                          className="border rounded-md p-3 space-y-2"
                        >
                          <div className="flex items-center gap-3">
                            <div className="flex items-center gap-2 text-xs text-muted-foreground w-6">
                              #{step.step_index ?? idx + 1}
                            </div>
                            <div className={`w-6 h-6 rounded-full ${stepStyle.bg} flex items-center justify-center shrink-0`}>
                              <StepIcon className={`h-3.5 w-3.5 ${stepStyle.text}`} />
                            </div>
                            <div className="flex-1 min-w-0">
                              <p className="font-medium text-sm truncate">
                                {step.node_name || step.node_id}
                              </p>
                              <p className="text-xs text-muted-foreground">
                                {step.node_type}
                              </p>
                            </div>
                            <div className="text-xs text-muted-foreground">
                              {step.duration_ms ? `${step.duration_ms}ms` : "-"}
                            </div>
                          </div>

                          {/* Step Error */}
                          {step.error && (
                            <div className="ml-8 text-xs text-destructive bg-destructive/10 px-2 py-1 rounded">
                              {step.error}
                            </div>
                          )}

                          {/* Step Input/Output */}
                          {(step.input || step.output) && (
                            <div className="ml-8 grid grid-cols-2 gap-2 text-xs">
                              {step.input && Object.keys(step.input).length > 0 && (
                                <details>
                                  <summary className="text-muted-foreground cursor-pointer hover:text-foreground">
                                    Input
                                  </summary>
                                  <pre className="mt-1 p-2 bg-muted rounded text-[10px] overflow-x-auto max-h-32">
                                    {JSON.stringify(step.input, null, 2)}
                                  </pre>
                                </details>
                              )}
                              {step.output && Object.keys(step.output).length > 0 && (
                                <details>
                                  <summary className="text-muted-foreground cursor-pointer hover:text-foreground">
                                    Output
                                  </summary>
                                  <pre className="mt-1 p-2 bg-muted rounded text-[10px] overflow-x-auto max-h-32">
                                    {JSON.stringify(step.output, null, 2)}
                                  </pre>
                                </details>
                              )}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <div className="text-sm text-muted-foreground text-center py-4">
                    No step details available for this execution
                  </div>
                )}
              </div>

              {/* Context/Variables */}
              {executionDetailQuery.data?.context && Object.keys(executionDetailQuery.data.context).length > 0 && (
                <details className="border rounded-lg p-4">
                  <summary className="flex items-center gap-2 text-sm font-medium cursor-pointer">
                    <Database className="h-4 w-4 text-muted-foreground" />
                    Execution Context
                  </summary>
                  <ScrollArea className="h-40 mt-3">
                    <pre className="text-xs">
                      {JSON.stringify(executionDetailQuery.data.context, null, 2)}
                    </pre>
                  </ScrollArea>
                </details>
              )}
            </div>

            <DialogFooter>
              <Button variant="outline" onClick={() => setSelectedExecution(null)}>Close</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
}

// AI Agents Workspace

interface HostedTools {
  web_search: boolean;
  file_search: boolean;
  computer: boolean;
}

interface AgentTools {
  hosted: HostedTools;
  agent_tools: string[];
  mcp_connections: string[];
}

interface MCPConnectionRef {
  id: string;
  name: string;
  server_label: string;
  is_active: boolean;
}

interface JsonSchemaRef {
  id: string;
  name: string;
  version: string;
  is_active: boolean;
}

/** Model settings for OpenAI Responses API; persisted in POST/PATCH agent payload */
interface ModelSettings {
  temperature?: number | null;
  top_p?: number | null;
  frequency_penalty?: number | null;
  presence_penalty?: number | null;
  tool_choice?: "none" | "auto" | "required" | null;
  parallel_tool_calls?: boolean | null;
  truncation?: "auto" | "disabled" | null;
  max_tokens?: number | null;
  verbosity?: "low" | "medium" | "high" | null;
  prompt_cache_retention?: "in_memory" | "24h" | null;
  metadata?: Record<string, string> | null;
}

interface AgentConfig {
  id: string;
  enabled: boolean;
  name: string | null;
  model: string;
  instructions: string | null;
  channel: string | null;
  channel_id: string | null;
  tools: AgentTools | null;
  handoffs: string[];
  tool_use_behavior: string;
  handoff_description: string | null;
  output_type: string | null;
  reasoning_effort: string | null;
  model_settings?: ModelSettings | null;
  default?: boolean;
  created_at: string;
  updated_at: string;
}

const REASONING_MODELS = ["o1", "o1-mini", "o1-preview", "o3", "o3-mini", "o4-mini", "gpt-5"];

function createDefaultHostedTools(): HostedTools {
  return {
    web_search: false,
    file_search: false,
    computer: false,
  };
}

function createDefaultAgentTools(): AgentTools {
  return {
    hosted: createDefaultHostedTools(),
    agent_tools: [],
    mcp_connections: [],
  };
}

function hydrateAgentTools(tools: any): AgentTools {
  if (!tools) {
    return createDefaultAgentTools();
  }
  
  // Handle legacy format: array of tool names
  if (Array.isArray(tools)) {
    return {
      hosted: createDefaultHostedTools(),
      agent_tools: tools,
      mcp_connections: [],
    };
  }
  
  // Handle new format: object with hosted, agent_tools, mcp_connections
  if (typeof tools === "object" && Object.keys(tools).length === 0) {
    return createDefaultAgentTools();
  }
  
  return {
    hosted: {
      web_search: tools.hosted?.web_search ?? false,
      file_search: tools.hosted?.file_search ?? false,
      computer: tools.hosted?.computer ?? false,
    },
    agent_tools: Array.isArray(tools.agent_tools) ? [...tools.agent_tools] : [],
    mcp_connections: Array.isArray(tools.mcp_connections) ? [...tools.mcp_connections] : [],
  };
}

function hydrateReasoningEffort(model: string, reasoningEffort: any): string | null {
  if (REASONING_MODELS.includes(model)) {
    return reasoningEffort ?? "medium";
  }
  return null;
}

function hydrateHandoffs(raw: any): string[] {
  if (!raw) return [];

  // Most common: array of IDs
  if (Array.isArray(raw)) {
    return raw
      .map((v) => {
        if (typeof v === "string") return v;
        if (typeof v === "object" && v && typeof (v as any).id === "string") return (v as any).id as string;
        return null;
      })
      .filter((id): id is string => typeof id === "string" && id.trim().length > 0);
  }

  // Sometimes: serialized JSON array or comma-separated string
  if (typeof raw === "string") {
    const trimmed = raw.trim();
    if (!trimmed) return [];

    // JSON array string
    if (trimmed.startsWith("[") && trimmed.endsWith("]")) {
      try {
        const parsed = JSON.parse(trimmed);
        return hydrateHandoffs(parsed);
      } catch {
        // fall through to comma-split
      }
    }

    return trimmed
      .split(",")
      .map((p) => p.trim())
      .filter((p) => p.length > 0);
  }

  // Sometimes: object wrapper
  if (typeof raw === "object") {
    const obj: any = raw;
    return hydrateHandoffs(obj.handoffs ?? obj.ids ?? obj.items ?? obj.results);
  }

  return [];
}

function hydrateModelSettings(raw: any): ModelSettings | null {
  if (!raw || typeof raw !== "object") return null;
  const ms = raw as Record<string, unknown>;
  const out: ModelSettings = {};
  if (typeof ms.temperature === "number" && ms.temperature >= 0 && ms.temperature <= 2) out.temperature = ms.temperature;
  if (typeof ms.top_p === "number" && ms.top_p >= 0 && ms.top_p <= 1) out.top_p = ms.top_p;
  if (typeof ms.frequency_penalty === "number") out.frequency_penalty = ms.frequency_penalty;
  if (typeof ms.presence_penalty === "number") out.presence_penalty = ms.presence_penalty;
  if (ms.tool_choice === "none" || ms.tool_choice === "auto" || ms.tool_choice === "required") out.tool_choice = ms.tool_choice;
  if (typeof ms.parallel_tool_calls === "boolean") out.parallel_tool_calls = ms.parallel_tool_calls;
  if (ms.truncation === "auto" || ms.truncation === "disabled") out.truncation = ms.truncation;
  if (typeof ms.max_tokens === "number" && ms.max_tokens >= 0) out.max_tokens = ms.max_tokens;
  if (ms.verbosity === "low" || ms.verbosity === "medium" || ms.verbosity === "high") out.verbosity = ms.verbosity;
  const pcr = ms.prompt_cache_retention;
  if (pcr === "in_memory" || pcr === "24h") out.prompt_cache_retention = pcr;
  if (pcr === "in-memory") out.prompt_cache_retention = "in_memory";
  if (ms.metadata && typeof ms.metadata === "object" && !Array.isArray(ms.metadata)) {
    out.metadata = Object.fromEntries(
      Object.entries(ms.metadata).filter(([, v]) => typeof v === "string") as [string, string][]
    );
  }
  return Object.keys(out).length > 0 ? out : null;
}

interface MoioAgentTool {
  tool_name: string;
  tool_type: "custom" | "builtin";
  enabled: boolean;
  custom_display_name: string;
  custom_description: string;
  default_params: Record<string, any>;
  defaults: {
    name: string;
    display_name: string;
    description: string;
    category: string;
    type: string;
  };
  created_at?: string;
  updated_at?: string;
}

interface AgentToolsResponse {
  tools?: MoioAgentTool[];
}

interface ChannelOption {
  value: string;
  label: string;
}

const AGENTS_PATH = apiV1("/settings/agents/");
const AGENT_TOOLS_PATH = apiV1("/settings/agents/tools/");
const AGENT_CHANNELS_PATH = apiV1("/settings/agents/channels/");
const MCP_CONNECTIONS_PATH = apiV1("/settings/mcp_connections/");
const JSON_SCHEMAS_PATH = apiV1("/settings/json_schemas/");
const OPENAI_INTEGRATION_PATH = apiV1("/integrations/openai/");

interface OpenAIModel {
  id: string;
  created: number;
}

interface OpenAIIntegration {
  openai_integration_enabled: boolean;
  openai_api_key?: string;
  openai_max_retries?: number;
  openai_default_model?: string;
  openai_embedding_model?: string;
  available_models?: OpenAIModel[];
}

function AIAgentsWorkspace() {
  const { toast } = useToast();
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [editedAgent, setEditedAgent] = useState<AgentConfig | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [modelSettingsOpen, setModelSettingsOpen] = useState(false);

  const agentsQuery = useQuery<AgentConfig[] | { results?: AgentConfig[]; agents?: AgentConfig[]; items?: AgentConfig[] }>({
    queryKey: [AGENTS_PATH],
    queryFn: () => fetchJson<AgentConfig[] | { results?: AgentConfig[]; agents?: AgentConfig[]; items?: AgentConfig[] }>(AGENTS_PATH, { page_size: 200 }),
    staleTime: 1000 * 60 * 5,
    gcTime: 1000 * 60 * 10,
  });

  const agentToolsQuery = useQuery<MoioAgentTool[]>({
    queryKey: [AGENT_TOOLS_PATH],
    queryFn: async () => {
      const data = await fetchJson<MoioAgentTool[] | { tools?: MoioAgentTool[] }>(AGENT_TOOLS_PATH);
      if (Array.isArray(data)) {
        return data;
      }
      return data?.tools ?? [];
    },
    staleTime: 1000 * 60 * 5,
    gcTime: 1000 * 60 * 10,
    refetchOnWindowFocus: false,
    refetchOnMount: false,
    refetchOnReconnect: false,
  });

  const mcpConnectionsQuery = useQuery<{ connections: MCPConnectionRef[] }>({
    queryKey: [MCP_CONNECTIONS_PATH],
    queryFn: () => fetchJson<{ connections: MCPConnectionRef[] }>(MCP_CONNECTIONS_PATH),
    staleTime: 1000 * 60 * 5,
    gcTime: 1000 * 60 * 10,
  });

  const jsonSchemasQuery = useQuery<{ schemas: JsonSchemaRef[] }>({
    queryKey: [JSON_SCHEMAS_PATH],
    queryFn: () => fetchJson<{ schemas: JsonSchemaRef[] }>(JSON_SCHEMAS_PATH),
    staleTime: 1000 * 60 * 5,
    gcTime: 1000 * 60 * 10,
  });

  const openaiIntegrationQuery = useQuery<OpenAIIntegration>({
    queryKey: [OPENAI_INTEGRATION_PATH],
    queryFn: async () => {
      const data = await fetchJson<any>(OPENAI_INTEGRATION_PATH);
      if (Array.isArray(data)) {
        const integration = data[0];
        return {
          ...integration?.config,
          available_models: integration?.available_models || [],
        };
      }
      return data || {};
    },
    staleTime: 1000 * 60 * 5,
    gcTime: 1000 * 60 * 10,
  });

  const channelsQuery = useQuery<ChannelOption[]>({
    queryKey: [AGENT_CHANNELS_PATH],
    queryFn: async () => {
      const data = await fetchJson<ChannelOption[] | { channels: ChannelOption[] }>(AGENT_CHANNELS_PATH);
      if (Array.isArray(data)) {
        return data;
      }
      return data?.channels ?? [];
    },
    staleTime: 1000 * 60 * 5,
    gcTime: 1000 * 60 * 10,
  });

  const agents = (() => {
    const data = agentsQuery.data;
    if (Array.isArray(data)) return data;
    return data?.results ?? data?.agents ?? data?.items ?? [];
  })();
  const availableModels = openaiIntegrationQuery.data?.available_models ?? [];
  const openaiIntegrationError = openaiIntegrationQuery.isError;
  const availableChannels = channelsQuery.data ?? [
    { value: "whatsapp", label: "WhatsApp" },
    { value: "telegram", label: "Telegram" },
    { value: "webchat", label: "Web Chat" },
  ];
  const mcpConnections = (
    Array.isArray(mcpConnectionsQuery.data) 
      ? mcpConnectionsQuery.data 
      : mcpConnectionsQuery.data?.connections ?? []
  ).filter((c) => c.is_active);
  const jsonSchemas = (
    Array.isArray(jsonSchemasQuery.data) 
      ? jsonSchemasQuery.data 
      : jsonSchemasQuery.data?.schemas ?? []
  ).filter((s) => s.is_active);

  const filteredAgents = agents.filter((agent) =>
    (agent.name || "").toLowerCase().includes(searchQuery.toLowerCase())
  );

  // Stable reference for availableTools to prevent unnecessary re-renders
  const availableTools = useMemo(() => {
    if (!agentToolsQuery.data) return [];
    const tools = Array.isArray(agentToolsQuery.data) 
      ? agentToolsQuery.data 
      : [];
    const filtered = tools.filter((tool: MoioAgentTool) => tool.tool_type !== "builtin" && tool.enabled);
    // Create stable object references - only recreate if tool data actually changes
    return filtered.map((tool: MoioAgentTool) => ({
      tool_name: tool.tool_name,
      tool_type: tool.tool_type,
      enabled: tool.enabled,
      custom_display_name: tool.custom_display_name,
      custom_description: tool.custom_description,
      display_name: tool.custom_display_name || tool.defaults?.display_name || tool.tool_name,
      defaults: tool.defaults,
      default_params: tool.default_params,
    }));
  }, [agentToolsQuery.data]);

  const handleToolToggle = useCallback((toolName: string, checked: boolean) => {
    // Use requestAnimationFrame to batch the update and prevent visual jitter
    requestAnimationFrame(() => {
      setEditedAgent((prev) => {
        if (!prev) return prev;
        const current = prev.tools?.agent_tools ?? [];
        const alreadyChecked = current.includes(toolName);
        
        // If state is already what we want, don't update
        if (checked === alreadyChecked) {
          return prev;
        }
        
        // Update the tools array
        const updated = checked
          ? [...current, toolName]
          : current.filter((name) => name !== toolName);
        
        // Preserve all other properties to minimize re-renders
        const newTools = {
          ...(prev.tools ?? createDefaultAgentTools()),
          agent_tools: updated,
        };
        
        // Only create new object if tools actually changed
        return {
          ...prev,
          tools: newTools,
        };
      });
    });
  }, []);


  useEffect(() => {
    if (selectedAgentId) {
      const agent = agents.find((a) => a.id === selectedAgentId);
      if (agent) {
        // Handoffs may arrive as array, json-string, comma-string, or objects depending on serializer.
        const handoffs = hydrateHandoffs(
          (agent as any).handoffs ??
            (agent as any).handoffs_json ??
            (agent as any).handoff_ids ??
            (agent as any).handoff_agents
        );
        
        setEditedAgent({
          ...agent,
          tools: hydrateAgentTools(agent.tools),
          handoffs: handoffs,
          tool_use_behavior: agent.tool_use_behavior ?? "run_llm_again",
          handoff_description: agent.handoff_description ?? null,
          output_type: agent.output_type ?? null,
          reasoning_effort: hydrateReasoningEffort(agent.model, (agent as any).reasoning_effort),
          model_settings: hydrateModelSettings((agent as any).model_settings),
        });
      }
    } else if (isCreating) {
      setEditedAgent({
        id: "",
        name: "",
        enabled: true,
        model: "gpt-4o",
        instructions: "You are a helpful AI assistant.",
        channel: null,
        channel_id: null,
        tools: createDefaultAgentTools(),
        handoffs: [],
        tool_use_behavior: "run_llm_again",
        handoff_description: null,
        output_type: null,
        reasoning_effort: null,
        model_settings: {
          temperature: 0.2,
          top_p: 1.0,
          parallel_tool_calls: true,
          truncation: "auto",
          max_tokens: 800,
          verbosity: "low",
          prompt_cache_retention: "24h",
        },
        created_at: "",
        updated_at: "",
      });
    } else {
      setEditedAgent(null);
    }
  }, [selectedAgentId, isCreating, agents]);

  const handleCreateNew = () => {
    setSelectedAgentId(null);
    setIsCreating(true);
  };

  const handleSave = async () => {
    if (!editedAgent || !editedAgent.name?.trim()) {
      toast({ title: "Error", description: "Agent name is required", variant: "destructive" });
      return;
    }

    setIsSaving(true);
    try {
      // Ensure handoffs is always an array, never null or undefined
      const handoffs = Array.isArray(editedAgent.handoffs) ? editedAgent.handoffs : [];
      
      const payload: Record<string, unknown> = {
        name: editedAgent.name,
        enabled: editedAgent.enabled,
        model: editedAgent.model,
        instructions: editedAgent.instructions,
        channel: editedAgent.channel,
        channel_id: editedAgent.channel_id,
        tools: editedAgent.tools,
        // Backend: `handoffs` is read-only in responses; use `handoff_ids` to persist.
        handoff_ids: handoffs,
        tool_use_behavior: editedAgent.tool_use_behavior,
        handoff_description: editedAgent.handoff_description || null,
        output_type: editedAgent.output_type || null,
        reasoning_effort: editedAgent.reasoning_effort || null,
      };
      // Persist model_settings; omit undefined/null values so backend uses provider defaults
      if (editedAgent.model_settings) {
        const ms: Record<string, unknown> = {};
        for (const [k, v] of Object.entries(editedAgent.model_settings)) {
          if (v !== undefined && v !== null) ms[k] = v;
        }
        if (Object.keys(ms).length > 0) payload.model_settings = ms;
      }

      if (isCreating) {
        const res = await apiRequest("POST", AGENTS_PATH, { data: payload });
        const newAgent = await res.json();
        toast({ title: "Created", description: "Agent created successfully." });
        setIsCreating(false);
        // Wait for refetch to complete before setting selected agent to ensure data is fresh
        await agentsQuery.refetch();
        setSelectedAgentId(newAgent.id);
      } else {
        const res = await apiRequest("PATCH", `${AGENTS_PATH}${selectedAgentId}/`, { data: payload });
        const updatedAgent = await res.json();
        toast({ title: "Saved", description: "Agent updated successfully." });
        // Update editedAgent with the response to ensure handoffs are properly synced
        if (updatedAgent) {
          setEditedAgent({
            ...updatedAgent,
            tools: hydrateAgentTools(updatedAgent.tools),
            handoffs: hydrateHandoffs(
              (updatedAgent as any).handoffs ??
                (updatedAgent as any).handoffs_json ??
                (updatedAgent as any).handoff_ids ??
                (updatedAgent as any).handoff_agents
            ),
            tool_use_behavior: updatedAgent.tool_use_behavior ?? "run_llm_again",
            handoff_description: updatedAgent.handoff_description ?? null,
            output_type: updatedAgent.output_type ?? null,
            reasoning_effort: hydrateReasoningEffort(updatedAgent.model, (updatedAgent as any).reasoning_effort),
            model_settings: hydrateModelSettings((updatedAgent as any).model_settings),
          });
        }
        // Also invalidate and refetch to keep the list in sync
        queryClient.invalidateQueries({ queryKey: [AGENTS_PATH] });
        await agentsQuery.refetch();
      }
    } catch (error) {
      toast({
        title: "Error",
        description: error instanceof Error ? error.message : "Failed to save",
        variant: "destructive",
      });
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!selectedAgentId) return;
    
    try {
      await apiRequest("DELETE", `${AGENTS_PATH}${selectedAgentId}/`);
      toast({ title: "Deleted", description: "Agent deleted successfully." });
      setSelectedAgentId(null);
      setEditedAgent(null);
      queryClient.invalidateQueries({ queryKey: [AGENTS_PATH] });
      agentsQuery.refetch();
    } catch (error) {
      toast({
        title: "Error",
        description: error instanceof Error ? error.message : "Failed to delete",
        variant: "destructive",
      });
    }
  };

  return (
    <div className="w-full h-full flex overflow-hidden">
      <div className="w-96 border-r border-border bg-background flex flex-col shrink-0">
        <div className="p-3 border-b border-border flex items-center gap-2 flex-shrink-0">
          <Button onClick={handleCreateNew} size="sm" data-testid="button-new-agent">
            <Plus className="h-4 w-4 mr-2" />
            New Agent
          </Button>
        </div>
        <div className="p-3 border-b border-border flex-shrink-0">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
            <Input
              placeholder="Search agents..."
              className="pl-10"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              data-testid="input-search-agents"
            />
          </div>
        </div>

        <ScrollArea className="flex-1 min-h-0 overflow-hidden">
          {agentsQuery.isLoading ? (
            <div className="p-4 space-y-3">
              {[...Array(5)].map((_, i) => (
                <Skeleton key={i} className="h-16 w-full" />
              ))}
            </div>
          ) : agentsQuery.isError ? (
            <div className="p-4">
              <ErrorDisplay error={agentsQuery.error as Error} endpoint={AGENTS_PATH} />
            </div>
          ) : filteredAgents.length === 0 ? (
            <div className="p-4">
              <EmptyState
                title={searchQuery.trim() ? "No agents match" : "No agents yet"}
                description={searchQuery.trim() ? "Try a different search." : "Create your first AI agent."}
              />
            </div>
          ) : (
            filteredAgents.map((agent) => (
              <div
                key={agent.id}
                onClick={() => { setSelectedAgentId(agent.id); setIsCreating(false); }}
                className={`p-3 border-b border-border cursor-pointer transition-colors ${
                  selectedAgentId === agent.id ? "bg-accent" : "hover-elevate"
                }`}
                data-testid={`item-agent-${agent.id}`}
              >
                <div className="flex items-center justify-between gap-2 mb-1">
                  <div className="flex items-center gap-2">
                    <Bot className="h-4 w-4 text-primary" />
                    <h3 className="font-semibold text-sm truncate">{agent.name || "Untitled Agent"}</h3>
                  </div>
                  <Badge variant={agent.enabled ? "default" : "outline"} className="text-xs">
                    {agent.enabled ? "Active" : "Inactive"}
                  </Badge>
                </div>
                <p className="text-xs text-muted-foreground line-clamp-2">
                  {agent.instructions || "No instructions provided"}
                </p>
                <div className="flex items-center gap-2 mt-1 text-xs text-muted-foreground">
                  <Zap className="h-3 w-3" />
                  {agent.model}
                </div>
              </div>
            ))
          )}
        </ScrollArea>
      </div>

      <div className="flex-1 flex flex-col bg-muted/20 overflow-hidden">
        {agentsQuery.isLoading ? (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto mb-4" />
              <p className="text-sm text-muted-foreground">Loading agents...</p>
            </div>
          </div>
        ) : agentsQuery.isError ? (
          <div className="flex-1 flex items-center justify-center p-6">
            <ErrorDisplay error={agentsQuery.error as Error} endpoint={AGENTS_PATH} />
          </div>
        ) : !selectedAgentId && !isCreating ? (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center">
              <div className="inline-flex h-16 w-16 items-center justify-center rounded-full bg-muted mb-4">
                <Bot className="h-8 w-8 text-muted-foreground" />
              </div>
              <p className="text-sm text-muted-foreground">Select an agent to configure or create a new one</p>
            </div>
          </div>
        ) : editedAgent ? (
          <ScrollArea className="flex-1 min-h-0">
            <div className="p-6 space-y-6">
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 space-y-4">
                  <div>
                    <Label htmlFor="agent-name">Agent Name</Label>
                    <Input
                      id="agent-name"
                      value={editedAgent.name || ""}
                      onChange={(e) => setEditedAgent({ ...editedAgent, name: e.target.value })}
                      className="mt-1"
                      data-testid="input-agent-name"
                    />
                  </div>
                  <div>
                    <Label htmlFor="agent-instructions">Instructions</Label>
                    <Textarea
                      id="agent-instructions"
                      value={editedAgent.instructions || ""}
                      onChange={(e) => setEditedAgent({ ...editedAgent, instructions: e.target.value })}
                      className="mt-1"
                      rows={4}
                      placeholder="Describe how the agent should behave..."
                      data-testid="input-agent-instructions"
                    />
                  </div>
                </div>
                <div className="flex flex-col gap-2">
                  <Button onClick={handleSave} disabled={isSaving || !editedAgent.name?.trim()} data-testid="button-save-agent">
                    <Save className="h-4 w-4 mr-2" />
                    {isSaving ? (isCreating ? "Creating..." : "Saving...") : (isCreating ? "Create" : "Save")}
                  </Button>
                  {isCreating && (
                    <Button variant="outline" onClick={() => { setIsCreating(false); setEditedAgent(null); }} data-testid="button-cancel-create">
                      Cancel
                    </Button>
                  )}
                </div>
              </div>

              <div className="flex items-center gap-6 flex-wrap">
                <div className="flex items-center gap-4">
                  <Label>Status</Label>
                  <Switch
                    checked={editedAgent.enabled}
                    onCheckedChange={(checked) => setEditedAgent({ ...editedAgent, enabled: checked })}
                    data-testid="switch-agent-enabled"
                  />
                  <span className="text-sm text-muted-foreground">
                    {editedAgent.enabled ? "Active" : "Inactive"}
                  </span>
                </div>
                <div className="flex items-center gap-4">
                  <Label>Model</Label>
                  <Select
                    value={editedAgent.model}
                    onValueChange={(val) => setEditedAgent({ 
                      ...editedAgent, 
                      model: val,
                      reasoning_effort: REASONING_MODELS.includes(val) ? (editedAgent.reasoning_effort ?? "medium") : null
                    })}
                  >
                    <SelectTrigger className="w-48" data-testid="select-agent-model">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {availableModels.length > 0 ? (
                        availableModels.map((model) => (
                          <SelectItem key={model.id} value={model.id} data-testid={`select-model-${model.id}`}>
                            {model.id}
                          </SelectItem>
                        ))
                      ) : (
                        <>
                          <SelectItem value="gpt-4o" data-testid="select-model-gpt-4o">gpt-4o</SelectItem>
                          <SelectItem value="gpt-4o-mini" data-testid="select-model-gpt-4o-mini">gpt-4o-mini</SelectItem>
                          <SelectItem value="gpt-4-turbo" data-testid="select-model-gpt-4-turbo">gpt-4-turbo</SelectItem>
                          <SelectItem value="gpt-3.5-turbo" data-testid="select-model-gpt-3.5-turbo">gpt-3.5-turbo</SelectItem>
                        </>
                      )}
                    </SelectContent>
                  </Select>
                  {openaiIntegrationError && (
                    <span className="text-xs text-muted-foreground">(using defaults)</span>
                  )}
                </div>
                {REASONING_MODELS.includes(editedAgent.model) && (
                  <div className="flex items-center gap-4">
                    <Label>Reasoning Effort</Label>
                    <Select
                      value={editedAgent.reasoning_effort || "medium"}
                      onValueChange={(val) => setEditedAgent({ ...editedAgent, reasoning_effort: val })}
                    >
                      <SelectTrigger className="w-32" data-testid="select-reasoning-effort">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="low">Low</SelectItem>
                        <SelectItem value="medium">Medium</SelectItem>
                        <SelectItem value="high">High</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                )}
              </div>

              <GlassPanel className="p-4">
                <Collapsible open={modelSettingsOpen} onOpenChange={setModelSettingsOpen}>
                  <CollapsibleTrigger asChild>
                    <button
                      type="button"
                      className="flex items-center gap-2 w-full text-left"
                      data-testid="collapsible-model-settings"
                    >
                      <ChevronRight
                        className={`h-4 w-4 text-muted-foreground transition-transform ${modelSettingsOpen ? "rotate-90" : ""}`}
                      />
                      <Zap className="h-4 w-4 text-muted-foreground" />
                      <h3 className="font-semibold text-sm">Model Settings</h3>
                      <span className="text-xs text-muted-foreground">(temperature, max_tokens, etc.)</span>
                    </button>
                  </CollapsibleTrigger>
                  <CollapsibleContent className="pt-4 space-y-4">
                    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                      <div>
                        <Label htmlFor="ms-temperature" className="text-xs">Temperature (0–2)</Label>
                        <Input
                          id="ms-temperature"
                          type="number"
                          min={0}
                          max={2}
                          step={0.1}
                          value={editedAgent.model_settings?.temperature ?? ""}
                          onChange={(e) => {
                            const v = e.target.value === "" ? undefined : parseFloat(e.target.value);
                            setEditedAgent({
                              ...editedAgent,
                              model_settings: {
                                ...(editedAgent.model_settings ?? {}),
                                temperature: v != null && !isNaN(v) ? Math.min(2, Math.max(0, v)) : undefined,
                              },
                            });
                          }}
                          placeholder="Default"
                          className="h-9 mt-1"
                          data-testid="input-model-settings-temperature"
                        />
                      </div>
                      <div>
                        <Label htmlFor="ms-top-p" className="text-xs">Top P (0–1)</Label>
                        <Input
                          id="ms-top-p"
                          type="number"
                          min={0}
                          max={1}
                          step={0.1}
                          value={editedAgent.model_settings?.top_p ?? ""}
                          onChange={(e) => {
                            const v = e.target.value === "" ? undefined : parseFloat(e.target.value);
                            setEditedAgent({
                              ...editedAgent,
                              model_settings: {
                                ...(editedAgent.model_settings ?? {}),
                                top_p: v != null && !isNaN(v) ? Math.min(1, Math.max(0, v)) : undefined,
                              },
                            });
                          }}
                          placeholder="Default"
                          className="h-9 mt-1"
                          data-testid="input-model-settings-top-p"
                        />
                      </div>
                      <div>
                        <Label htmlFor="ms-max-tokens" className="text-xs">Max Tokens</Label>
                        <Input
                          id="ms-max-tokens"
                          type="number"
                          min={1}
                          value={editedAgent.model_settings?.max_tokens ?? ""}
                          onChange={(e) => {
                            const v = e.target.value === "" ? undefined : parseInt(e.target.value, 10);
                            setEditedAgent({
                              ...editedAgent,
                              model_settings: {
                                ...(editedAgent.model_settings ?? {}),
                                max_tokens: v != null && !isNaN(v) && v > 0 ? v : undefined,
                              },
                            });
                          }}
                          placeholder="Default"
                          className="h-9 mt-1"
                          data-testid="input-model-settings-max-tokens"
                        />
                      </div>
                      <div>
                        <Label htmlFor="ms-frequency-penalty" className="text-xs">Frequency Penalty</Label>
                        <Input
                          id="ms-frequency-penalty"
                          type="number"
                          step={0.1}
                          value={editedAgent.model_settings?.frequency_penalty ?? ""}
                          onChange={(e) => {
                            const v = e.target.value === "" ? undefined : parseFloat(e.target.value);
                            setEditedAgent({
                              ...editedAgent,
                              model_settings: {
                                ...(editedAgent.model_settings ?? {}),
                                frequency_penalty: v != null && !isNaN(v) ? v : undefined,
                              },
                            });
                          }}
                          placeholder="Default"
                          className="h-9 mt-1"
                          data-testid="input-model-settings-frequency-penalty"
                        />
                      </div>
                      <div>
                        <Label htmlFor="ms-presence-penalty" className="text-xs">Presence Penalty</Label>
                        <Input
                          id="ms-presence-penalty"
                          type="number"
                          step={0.1}
                          value={editedAgent.model_settings?.presence_penalty ?? ""}
                          onChange={(e) => {
                            const v = e.target.value === "" ? undefined : parseFloat(e.target.value);
                            setEditedAgent({
                              ...editedAgent,
                              model_settings: {
                                ...(editedAgent.model_settings ?? {}),
                                presence_penalty: v != null && !isNaN(v) ? v : undefined,
                              },
                            });
                          }}
                          placeholder="Default"
                          className="h-9 mt-1"
                          data-testid="input-model-settings-presence-penalty"
                        />
                      </div>
                      <div>
                        <Label className="text-xs">Tool Choice</Label>
                        <Select
                          value={editedAgent.model_settings?.tool_choice ?? "default"}
                          onValueChange={(val) =>
                            setEditedAgent({
                              ...editedAgent,
                              model_settings: {
                                ...(editedAgent.model_settings ?? {}),
                                tool_choice: val === "default" ? undefined : (val as "none" | "auto" | "required"),
                              },
                            })
                          }
                        >
                          <SelectTrigger className="h-9 mt-1" data-testid="select-model-settings-tool-choice">
                            <SelectValue placeholder="Default" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="default">Default</SelectItem>
                            <SelectItem value="none">None</SelectItem>
                            <SelectItem value="auto">Auto</SelectItem>
                            <SelectItem value="required">Required</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                      <div>
                        <Label className="text-xs">Truncation</Label>
                        <Select
                          value={editedAgent.model_settings?.truncation ?? "default"}
                          onValueChange={(val) =>
                            setEditedAgent({
                              ...editedAgent,
                              model_settings: {
                                ...(editedAgent.model_settings ?? {}),
                                truncation: val === "default" ? undefined : (val as "auto" | "disabled"),
                              },
                            })
                          }
                        >
                          <SelectTrigger className="h-9 mt-1" data-testid="select-model-settings-truncation">
                            <SelectValue placeholder="Default" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="default">Default</SelectItem>
                            <SelectItem value="auto">Auto</SelectItem>
                            <SelectItem value="disabled">Disabled</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                      <div>
                        <Label className="text-xs">Verbosity</Label>
                        <Select
                          value={editedAgent.model_settings?.verbosity ?? "default"}
                          onValueChange={(val) =>
                            setEditedAgent({
                              ...editedAgent,
                              model_settings: {
                                ...(editedAgent.model_settings ?? {}),
                                verbosity: val === "default" ? undefined : (val as "low" | "medium" | "high"),
                              },
                            })
                          }
                        >
                          <SelectTrigger className="h-9 mt-1" data-testid="select-model-settings-verbosity">
                            <SelectValue placeholder="Default" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="default">Default</SelectItem>
                            <SelectItem value="low">Low</SelectItem>
                            <SelectItem value="medium">Medium</SelectItem>
                            <SelectItem value="high">High</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                      <div>
                        <Label className="text-xs">Prompt Cache Retention</Label>
                        <Select
                          value={editedAgent.model_settings?.prompt_cache_retention ?? "default"}
                          onValueChange={(val) =>
                            setEditedAgent({
                              ...editedAgent,
                              model_settings: {
                                ...(editedAgent.model_settings ?? {}),
                                prompt_cache_retention: val === "default" ? undefined : (val as "in_memory" | "24h"),
                              },
                            })
                          }
                        >
                          <SelectTrigger className="h-9 mt-1" data-testid="select-model-settings-prompt-cache">
                            <SelectValue placeholder="Default" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="default">Default</SelectItem>
                            <SelectItem value="in_memory">In memory</SelectItem>
                            <SelectItem value="24h">24h</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                      <div className="flex items-center gap-2 pt-6">
                        <Switch
                          id="ms-parallel-tool-calls"
                          checked={editedAgent.model_settings?.parallel_tool_calls ?? true}
                          onCheckedChange={(checked) =>
                            setEditedAgent({
                              ...editedAgent,
                              model_settings: {
                                ...(editedAgent.model_settings ?? {}),
                                parallel_tool_calls: checked,
                              },
                            })
                          }
                          data-testid="switch-model-settings-parallel-tool-calls"
                        />
                        <Label htmlFor="ms-parallel-tool-calls" className="text-xs cursor-pointer">
                          Parallel tool calls
                        </Label>
                      </div>
                    </div>
                    <div>
                      <Label htmlFor="ms-metadata" className="text-xs">Metadata (JSON, e.g. {`{"app":"moio"}`})</Label>
                      <Input
                        id="ms-metadata"
                        value={
                          editedAgent.model_settings?.metadata
                            ? JSON.stringify(editedAgent.model_settings.metadata)
                            : ""
                        }
                        onChange={(e) => {
                          const raw = e.target.value.trim();
                          if (!raw) {
                            setEditedAgent({
                              ...editedAgent,
                              model_settings: {
                                ...(editedAgent.model_settings ?? {}),
                                metadata: undefined,
                              },
                            });
                            return;
                          }
                          try {
                            const parsed = JSON.parse(raw);
                            if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
                              const meta: Record<string, string> = {};
                              for (const [k, v] of Object.entries(parsed)) {
                                if (typeof k === "string" && typeof v === "string") meta[k] = v;
                              }
                              setEditedAgent({
                                ...editedAgent,
                                model_settings: {
                                  ...(editedAgent.model_settings ?? {}),
                                  metadata: Object.keys(meta).length > 0 ? meta : undefined,
                                },
                              });
                            }
                          } catch {
                            // Invalid JSON, ignore
                          }
                        }}
                        placeholder='{"app":"moio"}'
                        className="mt-1 font-mono text-xs"
                        data-testid="input-model-settings-metadata"
                      />
                    </div>
                  </CollapsibleContent>
                </Collapsible>
              </GlassPanel>

              <GlassPanel className="p-4">
                <div className="flex items-center gap-2 mb-3">
                  <MessageSquare className="h-4 w-4 text-muted-foreground" />
                  <h3 className="font-semibold text-sm">Channel Configuration</h3>
                </div>
                <div className="grid gap-4 sm:grid-cols-2">
                  <div>
                    <Label htmlFor="agent-channel">Channel Type</Label>
                    <Select
                      value={editedAgent.channel || "none"}
                      onValueChange={(val) => setEditedAgent({ ...editedAgent, channel: val === "none" ? null : val })}
                    >
                      <SelectTrigger className="mt-1" data-testid="select-agent-channel">
                        <SelectValue placeholder="Select channel" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="none">No channel</SelectItem>
                        {availableChannels.map((ch) => (
                          <SelectItem key={ch.value} value={ch.value}>
                            {ch.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <Label htmlFor="agent-channel-id">Channel ID</Label>
                    <Input
                      id="agent-channel-id"
                      value={editedAgent.channel_id || ""}
                      onChange={(e) => setEditedAgent({ ...editedAgent, channel_id: e.target.value || null })}
                      className="mt-1"
                      placeholder="Optional channel identifier"
                      data-testid="input-agent-channel-id"
                    />
                  </div>
                </div>
              </GlassPanel>

              <GlassPanel className="p-4">
                <div className="flex items-center gap-2 mb-4">
                  <Wrench className="h-4 w-4 text-muted-foreground" />
                  <h3 className="font-semibold text-sm">Tools Configuration</h3>
                </div>

                <div className="mb-4 p-3 bg-background/50 rounded-md border border-border/50 min-h-[3rem]">
                  {(editedAgent.tools?.hosted && Object.values(editedAgent.tools.hosted).some(Boolean)) ||
                  (editedAgent.tools?.agent_tools && editedAgent.tools.agent_tools.length > 0) ||
                  (editedAgent.tools?.mcp_connections && editedAgent.tools.mcp_connections.length > 0) ? (
                    <>
                      <p className="text-xs font-semibold text-muted-foreground mb-2">Configured Tools:</p>
                      <div className="flex flex-wrap gap-1.5">
                        {editedAgent.tools?.hosted?.web_search && (
                          <Badge variant="secondary" className="text-xs">Web Search</Badge>
                        )}
                        {editedAgent.tools?.hosted?.file_search && (
                          <Badge variant="secondary" className="text-xs">File Search</Badge>
                        )}
                        {editedAgent.tools?.hosted?.computer && (
                          <Badge variant="secondary" className="text-xs">Computer</Badge>
                        )}
                        {editedAgent.tools?.agent_tools?.map((toolName) => {
                          const tool = availableTools.find((t) => t.tool_name === toolName);
                          return (
                            <Badge key={toolName} variant="secondary" className="text-xs" title={tool?.custom_description}>
                              {tool?.display_name || toolName}
                            </Badge>
                          );
                        })}
                        {editedAgent.tools?.mcp_connections?.map((connId) => {
                          const conn = mcpConnections.find((c) => c.id === connId);
                          return (
                            <Badge key={connId} variant="secondary" className="text-xs">
                              {conn?.name || `MCP: ${connId}`}
                            </Badge>
                          );
                        })}
                      </div>
                    </>
                  ) : (
                    <p className="text-xs text-muted-foreground">No tools configured yet</p>
                  )}
                </div>

                <div className="space-y-4">
                  <div>
                    <Label className="text-xs text-muted-foreground mb-2 block">Hosted Tools (OpenAI)</Label>
                    <div className="grid grid-cols-3 gap-3">
                      <div className="flex items-center space-x-2 p-3 border rounded-md bg-background">
                        <Checkbox
                          id="tool-web-search"
                          checked={editedAgent.tools?.hosted?.web_search ?? false}
                          onCheckedChange={(checked) =>
                            setEditedAgent({
                              ...editedAgent,
                              tools: {
                                ...editedAgent.tools ?? createDefaultAgentTools(),
                                hosted: {
                                  ...editedAgent.tools?.hosted ?? createDefaultHostedTools(),
                                  web_search: !!checked,
                                },
                              },
                            })
                          }
                          data-testid="checkbox-tool-web-search"
                        />
                        <label htmlFor="tool-web-search" className="flex items-center gap-2 text-sm cursor-pointer">
                          <Globe className="h-4 w-4 text-blue-500" />
                          Web Search
                        </label>
                      </div>
                      <div className="flex items-center space-x-2 p-3 border rounded-md bg-background">
                        <Checkbox
                          id="tool-file-search"
                          checked={editedAgent.tools?.hosted?.file_search ?? false}
                          onCheckedChange={(checked) =>
                            setEditedAgent({
                              ...editedAgent,
                              tools: {
                                ...editedAgent.tools ?? createDefaultAgentTools(),
                                hosted: {
                                  ...editedAgent.tools?.hosted ?? createDefaultHostedTools(),
                                  file_search: !!checked,
                                },
                              },
                            })
                          }
                          data-testid="checkbox-tool-file-search"
                        />
                        <label htmlFor="tool-file-search" className="flex items-center gap-2 text-sm cursor-pointer">
                          <FileSearch className="h-4 w-4 text-green-500" />
                          File Search
                        </label>
                      </div>
                      <div className="flex items-center space-x-2 p-3 border rounded-md bg-background">
                        <Checkbox
                          id="tool-computer"
                          checked={editedAgent.tools?.hosted?.computer ?? false}
                          onCheckedChange={(checked) =>
                            setEditedAgent({
                              ...editedAgent,
                              tools: {
                                ...editedAgent.tools ?? createDefaultAgentTools(),
                                hosted: {
                                  ...editedAgent.tools?.hosted ?? createDefaultHostedTools(),
                                  computer: !!checked,
                                },
                              },
                            })
                          }
                          data-testid="checkbox-tool-computer"
                        />
                        <label htmlFor="tool-computer" className="flex items-center gap-2 text-sm cursor-pointer">
                          <Monitor className="h-4 w-4 text-purple-500" />
                          Computer
                        </label>
                      </div>
                    </div>
                  </div>

                  <div>
                    <Label className="text-xs text-muted-foreground mb-2 block">Moio Agent Tools</Label>
                    {agentToolsQuery.isLoading ? (
                      <div className="flex items-center gap-2 text-sm text-muted-foreground">
                        <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-primary" />
                        Loading tools...
                      </div>
                    ) : agentToolsQuery.isError ? (
                      <p className="text-sm text-destructive">Failed to load tools</p>
                    ) : availableTools.length === 0 ? (
                      <p className="text-sm text-muted-foreground">No agent tools available</p>
                    ) : (
                      <div className="grid grid-cols-2 gap-2 max-h-40 overflow-y-auto p-2 border rounded-md bg-background">
                        {availableTools.map((tool) => {
                          const isChecked = editedAgent?.tools?.agent_tools?.includes(tool.tool_name) ?? false;
                          const handleChange = (checked: boolean | string) => {
                            handleToolToggle(tool.tool_name, !!checked);
                          };
                          return (
                            <div key={tool.tool_name} className="flex items-center space-x-2">
                              <Checkbox
                                id={`agent-tool-${tool.tool_name}`}
                                checked={isChecked}
                                onCheckedChange={handleChange}
                                data-testid={`checkbox-agent-tool-${tool.tool_name}`}
                              />
                              <label 
                                htmlFor={`agent-tool-${tool.tool_name}`}
                                onClick={(e) => {
                                  // Prevent default to avoid double-trigger
                                  e.preventDefault();
                                  handleChange(!isChecked);
                                }}
                                className="text-sm cursor-pointer truncate" 
                                title={tool.custom_description}
                              >
                                {tool.display_name}
                              </label>
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>

                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <Label className="text-xs text-muted-foreground">MCP Connections</Label>
                      <Link href="/workflows/mcp-connections" className="text-xs text-primary hover:underline">
                        Manage
                      </Link>
                    </div>
                    {mcpConnectionsQuery.isLoading ? (
                      <div className="flex items-center gap-2 text-sm text-muted-foreground">
                        <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-primary" />
                        Loading...
                      </div>
                    ) : mcpConnections.length === 0 ? (
                      <p className="text-sm text-muted-foreground">No MCP connections configured</p>
                    ) : (
                      <div className="grid grid-cols-2 gap-2 max-h-32 overflow-y-auto p-2 border rounded-md bg-background">
                        {mcpConnections.map((conn) => (
                          <div key={conn.id} className="flex items-center space-x-2">
                            <Checkbox
                              id={`mcp-${conn.id}`}
                              checked={editedAgent.tools?.mcp_connections?.includes(conn.id) ?? false}
                              onCheckedChange={(checked) => {
                                const current = editedAgent.tools?.mcp_connections ?? [];
                                const updated = checked
                                  ? [...current, conn.id]
                                  : current.filter((id) => id !== conn.id);
                                setEditedAgent({
                                  ...editedAgent,
                                  tools: {
                                    ...editedAgent.tools ?? createDefaultAgentTools(),
                                    mcp_connections: updated,
                                  },
                                });
                              }}
                              data-testid={`checkbox-mcp-${conn.id}`}
                            />
                            <label htmlFor={`mcp-${conn.id}`} className="text-sm cursor-pointer truncate flex items-center gap-1.5" title={conn.server_label}>
                              <Plug className="h-3 w-3 text-cyan-500" />
                              {conn.name}
                            </label>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  <div className="flex items-center gap-4">
                    <Label>Tool Use Behavior</Label>
                    <Select
                      value={editedAgent.tool_use_behavior || "run_llm_again"}
                      onValueChange={(val) => setEditedAgent({ ...editedAgent, tool_use_behavior: val })}
                    >
                      <SelectTrigger className="w-48" data-testid="select-tool-use-behavior">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="run_llm_again">Run LLM Again</SelectItem>
                        <SelectItem value="stop_on_first_tool">Stop on First Tool</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>
              </GlassPanel>

              <GlassPanel className="p-4">
                <div className="flex items-center gap-2 mb-4">
                  <ArrowRightLeft className="h-4 w-4 text-muted-foreground" />
                  <h3 className="font-semibold text-sm">Handoffs</h3>
                </div>

                <div className="space-y-4">
                  <div>
                    <Label htmlFor="handoff-description">Handoff Description</Label>
                    <Textarea
                      id="handoff-description"
                      value={editedAgent.handoff_description || ""}
                      onChange={(e) => setEditedAgent({ ...editedAgent, handoff_description: e.target.value || null })}
                      className="mt-1"
                      rows={2}
                      placeholder="Describe when other agents should delegate to this agent..."
                      data-testid="input-handoff-description"
                    />
                  </div>

                  <div>
                    <Label className="text-xs text-muted-foreground mb-2 block">Delegate To Agents</Label>
                    {agents.length <= 1 ? (
                      <p className="text-sm text-muted-foreground">Create more agents to enable handoffs</p>
                    ) : (
                      <div className="grid grid-cols-2 gap-2 max-h-32 overflow-y-auto p-2 border rounded-md bg-background">
                        {agents
                          .filter((a) => a.id !== editedAgent.id)
                          .map((agent) => (
                            <div key={agent.id} className="flex items-center space-x-2">
                              <Checkbox
                                id={`handoff-${agent.id}`}
                                checked={editedAgent.handoffs?.includes(agent.id) ?? false}
                                onCheckedChange={(checked) => {
                                  const currentHandoffs = editedAgent.handoffs ?? [];
                                  const newHandoffs = checked
                                    ? [...currentHandoffs, agent.id]
                                    : currentHandoffs.filter((id) => id !== agent.id);
                                  setEditedAgent({ ...editedAgent, handoffs: newHandoffs });
                                }}
                                data-testid={`checkbox-handoff-${agent.id}`}
                              />
                              <label htmlFor={`handoff-${agent.id}`} className="text-sm cursor-pointer truncate">
                                {agent.name || "Untitled"}
                              </label>
                            </div>
                          ))}
                      </div>
                    )}
                  </div>
                </div>
              </GlassPanel>

              <GlassPanel className="p-4">
                <div className="flex items-center gap-2 mb-4">
                  <Braces className="h-4 w-4 text-muted-foreground" />
                  <h3 className="font-semibold text-sm">Output Configuration</h3>
                </div>

                <div className="space-y-4">
                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <Label htmlFor="output-schema">Output Schema</Label>
                      <Link href="/workflows/json-schemas" className="text-xs text-primary hover:underline">
                        Manage
                      </Link>
                    </div>
                    <Select
                      value={editedAgent.output_type || "none"}
                      onValueChange={(val) => setEditedAgent({ ...editedAgent, output_type: val === "none" ? null : val })}
                    >
                      <SelectTrigger data-testid="select-output-schema">
                        <SelectValue placeholder="Select output schema" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="none">No structured output</SelectItem>
                        <SelectItem value="json">JSON (freeform)</SelectItem>
                        {jsonSchemas.map((schema) => (
                          <SelectItem key={schema.id} value={schema.id}>
                            {schema.name} (v{schema.version})
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <p className="text-xs text-muted-foreground mt-1">
                      Define a structured schema for agent responses
                    </p>
                  </div>
                </div>
              </GlassPanel>
            </div>
          </ScrollArea>
        ) : null}
      </div>
    </div>
  );
}

// Helper functions for campaigns
const statusColors: Record<CampaignStatus, "default" | "secondary" | "outline" | "destructive"> = {
  draft: "outline",
  ready: "default",
  scheduled: "secondary",
  active: "default",
  ended: "secondary",
  archived: "outline",
};

const channelFilterOptions: Array<{ label: string; value: "all" | CampaignChannel }> = [
  { label: "All Channels", value: "all" },
  { label: "Email", value: "email" },
  { label: "WhatsApp", value: "whatsapp" },
  { label: "Telegram", value: "telegram" },
  { label: "SMS", value: "sms" },
];

const statusFilterOptions: Array<{ label: string; value: "all" | CampaignStatus }> = [
  { label: "All Statuses", value: "all" },
  { label: "Draft", value: "draft" },
  { label: "Ready", value: "ready" },
  { label: "Scheduled", value: "scheduled" },
  { label: "Active", value: "active" },
  { label: "Ended", value: "ended" },
  { label: "Archived", value: "archived" },
];

function formatLabel(value?: string | null) {
  if (!value) return "—";
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

// Campaigns Workspace
function CampaignsWorkspace() {
  const [statusFilter, setStatusFilter] = useState<"all" | CampaignStatus>("all");
  const [channelFilter, setChannelFilter] = useState<"all" | CampaignChannel>("all");
  const [wizardOpen, setWizardOpen] = useState(false);
  const [resumeCampaign, setResumeCampaign] = useState<ResumeCampaignData | null>(null);
  const [isLoadingResume, setIsLoadingResume] = useState<string | null>(null);
  const { toast } = useToast();

  const CAMPAIGNS_PATH = apiV1("/campaigns/campaigns/");

  const handleResumeCampaign = async (campaignId: string) => {
    setIsLoadingResume(campaignId);
    try {
      const detail = await fetchJson<CampaignDetail>(`${CAMPAIGNS_PATH}${campaignId}/`);
      const supportedChannels = ["whatsapp", "email", "sms"] as const;
      const channel = supportedChannels.includes(detail.channel as typeof supportedChannels[number])
        ? (detail.channel as "whatsapp" | "email" | "sms")
        : "whatsapp";
      
      const mappings = detail.config?.message?.map?.map((m) => ({
        source: String(m.source ?? ""),
        target: String(m.target ?? ""),
      }));
      
      const messageConfig = detail.config?.message as Record<string, unknown> | undefined;
      const templateId = messageConfig?.whatsapp_template_id as string | undefined 
        || messageConfig?.template_id as string | undefined 
        || "";
      const templateName = messageConfig?.whatsapp_template_name as string | undefined 
        || messageConfig?.template_name as string | undefined 
        || "";
      
      setResumeCampaign({
        id: detail.id,
        name: detail.name,
        description: detail.description,
        channel,
        kind: detail.kind,
        config: {
          message: detail.config?.message ? {
            template_id: templateId,
            template_name: templateName,
            map: mappings,
          } : undefined,
          schedule: detail.config?.schedule,
        },
        configuration_state: detail.configuration_state,
      });
      setWizardOpen(true);
    } catch (error) {
      console.error("Failed to load campaign details:", error);
      toast({
        variant: "destructive",
        title: "Error loading campaign",
        description: "Could not load campaign details. Please try again.",
      });
    } finally {
      setIsLoadingResume(null);
    }
  };

  const handleWizardClose = (open: boolean) => {
    setWizardOpen(open);
    if (!open) {
      setResumeCampaign(null);
    }
  };

  const campaignsQuery = useQuery<CampaignRecord[]>({
    queryKey: [CAMPAIGNS_PATH, { status: statusFilter, channel: channelFilter }],
    queryFn: async () => {
      const params: Record<string, string> = {};
      if (statusFilter && statusFilter !== "all") {
        params.status = statusFilter;
      }
      if (channelFilter && channelFilter !== "all") {
        params.channel = channelFilter;
      }
      return await fetchJson<CampaignRecord[]>(CAMPAIGNS_PATH, params);
    },
  });

  const deleteCampaignMutation = useMutation({
    mutationFn: async (campaignId: string) => {
      await apiRequest("DELETE", `${CAMPAIGNS_PATH}${campaignId}/`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [CAMPAIGNS_PATH] });
      toast({
        title: "Campaign deleted",
        description: "The campaign has been deleted successfully.",
      });
    },
    onError: (error) => {
      toast({
        variant: "destructive",
        title: "Delete failed",
        description: error instanceof Error ? error.message : "Could not delete campaign.",
      });
    },
  });

  const handleDeleteCampaign = (campaignId: string, e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (confirm("Are you sure you want to delete this campaign?")) {
      deleteCampaignMutation.mutate(campaignId);
    }
  };

  const campaigns = campaignsQuery.data ?? [];

  return (
    <>
      <CampaignWizardV2 open={wizardOpen} onOpenChange={handleWizardClose} resumeCampaign={resumeCampaign} />
      
      <div className="space-y-6">
        {/* Filters */}
        <div className="flex items-center gap-3 flex-wrap">
          <Select value={statusFilter} onValueChange={(value) => setStatusFilter(value as "all" | CampaignStatus)}>
            <SelectTrigger className="w-48" data-testid="select-status">
              <SelectValue placeholder="All Statuses" />
            </SelectTrigger>
            <SelectContent>
              {statusFilterOptions.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Select value={channelFilter} onValueChange={(value) => setChannelFilter(value as "all" | CampaignChannel)}>
            <SelectTrigger className="w-48" data-testid="select-channel">
              <SelectValue placeholder="All Channels" />
            </SelectTrigger>
            <SelectContent>
              {channelFilterOptions.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <div className="flex-1" />
          
          <Button onClick={() => setWizardOpen(true)} data-testid="button-new-campaign">
            <Plus className="h-4 w-4 mr-2" />
            New Campaign
          </Button>
        </div>

        {/* Campaign List */}
        {campaignsQuery.isLoading ? (
          <EmptyState
            title="Loading campaigns"
            description="Fetching campaigns from the backend..."
            isLoading
          />
        ) : campaignsQuery.isError ? (
          <ErrorDisplay
            error={campaignsQuery.error}
            endpoint="api/v1/campaigns/campaigns/"
          />
        ) : campaigns.length === 0 ? (
          <EmptyState
            title="No campaigns found"
            description={statusFilter !== "all" || channelFilter !== "all" ? "Try adjusting your filters." : "Create your first campaign to get started."}
          />
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {campaigns.map((campaign) => (
              <Link key={campaign.id} href={`/campaigns/${campaign.id}`}>
                <div
                  className="p-4 rounded-lg border border-border bg-card hover-elevate active-elevate-2 cursor-pointer transition-all"
                  data-testid={`card-campaign-${campaign.id}`}
                >
                  {/* Header */}
                  <div className="flex items-start justify-between gap-2 mb-3">
                    <div className="flex-1 min-w-0">
                      <h3 className="font-semibold text-sm mb-1 line-clamp-1" data-testid={`text-campaign-name-${campaign.id}`}>
                        {campaign.name}
                      </h3>
                      <p className="text-xs text-muted-foreground">{formatLabel(campaign.kind)}</p>
                    </div>
                    <div className="flex items-center gap-1.5 shrink-0">
                      <Badge variant={statusColors[campaign.status] || "secondary"} className="text-xs h-5 px-1.5 capitalize">
                        {formatLabel(campaign.status)}
                      </Badge>
                      {campaign.ready_to_launch && (
                        <Badge variant="secondary" className="text-[10px] h-5 px-2">
                          Ready to launch
                        </Badge>
                      )}
                      {campaign.status === "draft" && (
                        <Button
                          size="icon"
                          variant="ghost"
                          disabled={isLoadingResume === campaign.id}
                          onClick={(e) => {
                            e.preventDefault();
                            e.stopPropagation();
                            handleResumeCampaign(campaign.id);
                          }}
                          data-testid={`button-continue-${campaign.id}`}
                        >
                          <PlayCircle className="h-3.5 w-3.5" />
                        </Button>
                      )}
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button
                            size="icon"
                            variant="ghost"
                            onClick={(e) => {
                              e.preventDefault();
                              e.stopPropagation();
                            }}
                            data-testid={`button-more-${campaign.id}`}
                          >
                            <MoreVertical className="h-3.5 w-3.5" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end" onClick={(e) => e.stopPropagation()}>
                          {campaign.status === "draft" && (
                            <DropdownMenuItem
                              onClick={(e) => {
                                e.preventDefault();
                                handleResumeCampaign(campaign.id);
                              }}
                              data-testid={`menu-continue-${campaign.id}`}
                            >
                              <PlayCircle className="h-4 w-4 mr-2" />
                              Continue setup
                            </DropdownMenuItem>
                          )}
                          <DropdownMenuItem data-testid={`menu-view-${campaign.id}`}>
                            View details
                          </DropdownMenuItem>
                          {campaign.status === "draft" && (
                            <DropdownMenuItem
                              onClick={(e) => handleDeleteCampaign(campaign.id, e)}
                              className="text-destructive focus:text-destructive"
                              data-testid={`menu-delete-${campaign.id}`}
                            >
                              <Trash2 className="h-4 w-4 mr-2" />
                              Delete
                            </DropdownMenuItem>
                          )}
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </div>
                  </div>

                  {/* Description */}
                  <p className="text-xs text-muted-foreground line-clamp-2 mb-3 min-h-[32px]">
                    {campaign.description || "No description provided"}
                  </p>

                  {/* Channel and Recipients */}
                  <div className="flex items-center justify-between mb-3 text-xs">
                    <div className="flex items-center gap-1.5">
                      <MessageSquare className="h-3.5 w-3.5 text-green-500" />
                      <span className="text-muted-foreground">{formatLabel(campaign.channel)}</span>
                    </div>
                    {(campaign.audience_size ?? 0) > 0 && (
                      <div className="flex items-center gap-1.5">
                        <Users className="h-3.5 w-3.5 text-muted-foreground" />
                        <span className="text-muted-foreground">
                          {campaign.audience_size?.toLocaleString()}{" "}
                          recipients
                        </span>
                      </div>
                    )}
                  </div>

                  {/* Metrics */}
                  <div className="grid grid-cols-3 gap-3 mb-3 py-3 border-y border-border/50">
                    <div className="text-center">
                      <div className="text-lg font-bold text-blue-500" data-testid={`text-sent-${campaign.id}`}>
                        {campaign.sent ?? 0}
                      </div>
                      <div className="text-xs text-muted-foreground">sent</div>
                    </div>
                    <div className="text-center">
                      <div className="text-lg font-bold text-green-500" data-testid={`text-opened-${campaign.id}`}>
                        {campaign.opened ?? 0}
                      </div>
                      <div className="text-xs text-muted-foreground">opened</div>
                    </div>
                    <div className="text-center">
                      <div className="text-lg font-bold" data-testid={`text-rate-${campaign.id}`}>
                        {campaign.open_rate !== undefined && campaign.open_rate !== null
                          ? `${campaign.open_rate.toFixed(1)}%`
                          : "—"}
                      </div>
                      <div className="text-xs text-muted-foreground">open rate</div>
                    </div>
                  </div>

                  {/* Date */}
                  {campaign.created && (
                    <div className="text-xs text-muted-foreground">
                      {new Date(campaign.created).toLocaleDateString('en-US', { 
                        month: 'short', 
                        day: 'numeric', 
                        year: 'numeric' 
                      })}
                    </div>
                  )}
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </>
  );
}

// Audiences Workspace
const audienceKindColors: Record<string, "default" | "secondary" | "outline"> = {
  dynamic: "default",
  static: "secondary",
};

function AudiencesWorkspace() {
  const [kindFilter, setKindFilter] = useState<"all" | "dynamic" | "static">("all");

  const AUDIENCES_PATH = apiV1("/campaigns/audiences/");

  const audiencesQuery = useQuery<AudienceRecord[]>({
    queryKey: [AUDIENCES_PATH, { kind: kindFilter }],
    queryFn: async () => {
      const params: Record<string, string> = {};
      if (kindFilter && kindFilter !== "all") {
        params.kind = kindFilter;
      }
      return await fetchJson<AudienceRecord[]>(AUDIENCES_PATH, params);
    },
  });

  const audiences = audiencesQuery.data ?? [];

  return (
    <div className="space-y-6">
      {/* Filters */}
      <div className="flex items-center gap-3 flex-wrap">
        <Select value={kindFilter} onValueChange={(value) => setKindFilter(value as "all" | "dynamic" | "static")}>
          <SelectTrigger className="w-48" data-testid="select-audience-kind">
            <SelectValue placeholder="All Types" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Types</SelectItem>
            <SelectItem value="dynamic">Dynamic</SelectItem>
            <SelectItem value="static">Static</SelectItem>
          </SelectContent>
        </Select>

        <div className="flex-1" />
        
        <Button data-testid="button-new-audience">
          <Plus className="h-4 w-4 mr-2" />
          New Audience
        </Button>
      </div>

      {/* Audience List */}
      {audiencesQuery.isLoading ? (
        <EmptyState
          title="Loading audiences"
          description="Fetching audiences from the backend..."
          isLoading
        />
      ) : audiencesQuery.isError ? (
        <ErrorDisplay
          error={audiencesQuery.error}
          endpoint="api/v1/campaigns/audiences/"
        />
      ) : audiences.length === 0 ? (
        <EmptyState
          title="No audiences found"
          description={kindFilter !== "all" ? "Try adjusting your filter." : "Create your first audience to get started."}
        />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {audiences.map((audience) => (
            <div
              key={audience.id}
              className="p-4 rounded-lg border border-border bg-card hover-elevate active-elevate-2 cursor-pointer transition-all"
              data-testid={`card-audience-${audience.id}`}
            >
              {/* Header */}
              <div className="flex items-start justify-between gap-2 mb-3">
                <div className="flex-1 min-w-0">
                  <h3 className="font-semibold text-sm mb-1 line-clamp-1" data-testid={`text-audience-name-${audience.id}`}>
                    {audience.name}
                  </h3>
                  <p className="text-xs text-muted-foreground capitalize">{audience.kind} audience</p>
                </div>
                <div className="flex items-center gap-1.5 shrink-0">
                  <Badge variant={audienceKindColors[audience.kind] || "secondary"} className="text-xs h-5 px-1.5 capitalize">
                    {audience.kind}
                  </Badge>
                  {audience.is_draft && (
                    <Badge variant="outline" className="text-[10px] h-5 px-2">
                      Draft
                    </Badge>
                  )}
                  <Button
                    size="icon"
                    variant="ghost"
                    className="h-6 w-6"
                    onClick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                    }}
                    data-testid={`button-more-${audience.id}`}
                  >
                    <MoreVertical className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </div>

              {/* Description */}
              <p className="text-xs text-muted-foreground line-clamp-2 mb-3 min-h-[32px]">
                {audience.description || "No description provided"}
              </p>

              {/* Stats */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5">
                  <Users className="h-3.5 w-3.5 text-muted-foreground" />
                  <span className="text-sm font-medium">{audience.size.toLocaleString()}</span>
                  <span className="text-xs text-muted-foreground">contacts</span>
                </div>
                
                {/* Date */}
                {audience.created && (
                  <div className="text-xs text-muted-foreground">
                    {new Date(audience.created).toLocaleDateString('en-US', { 
                      month: 'short', 
                      day: 'numeric', 
                      year: 'numeric' 
                    })}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// Components Workspace
type AutomationComponentType = "scripts" | "whatsapp_templates" | "email_templates" | "webhooks" | "agent_tools" | "events" | "mcp_connections" | "json_schemas" | "robots";

interface ComponentsWorkspaceProps {
  scriptsCount?: number;
  whatsappTemplatesCount?: number;
}

function ComponentsWorkspace({ scriptsCount = 0, whatsappTemplatesCount = 0 }: ComponentsWorkspaceProps) {
  const [, navigate] = useLocation();
  const componentTypes = [
    { 
      id: "scripts" as AutomationComponentType, 
      label: "Scripts", 
      description: "Python scripts for automation logic with approval workflow",
      icon: FileCode,
      count: scriptsCount,
      bgClass: "bg-indigo-50",
      iconClass: "text-indigo-600"
    },
    {
      id: "robots" as AutomationComponentType,
      label: "Robot Studio",
      description: "Manage autonomous robots, runs, sessions, and live event timelines.",
      icon: Bot,
      count: 0,
      bgClass: "bg-purple-50",
      iconClass: "text-purple-600"
    },
    { 
      id: "whatsapp_templates" as AutomationComponentType, 
      label: "WhatsApp Templates", 
      description: "Message templates approved by WhatsApp for business communication",
      icon: MessageSquare,
      count: whatsappTemplatesCount,
      bgClass: "bg-green-50",
      iconClass: "text-green-600"
    },
    { 
      id: "email_templates" as AutomationComponentType, 
      label: "Email Templates", 
      description: "Reusable email templates for campaigns and notifications",
      icon: Mail,
      count: 0,
      bgClass: "bg-red-50",
      iconClass: "text-red-600"
    },
    { 
      id: "webhooks" as AutomationComponentType, 
      label: "Webhooks", 
      description: "HTTP endpoints that trigger flows from external services",
      icon: Webhook,
      count: 0,
      bgClass: "bg-blue-50",
      iconClass: "text-blue-600"
    },
    { 
      id: "agent_tools" as AutomationComponentType, 
      label: "Agent Tools", 
      description: "Configure default parameters and settings for AI agent tools",
      icon: Wrench,
      count: 0,
      bgClass: "bg-slate-50",
      iconClass: "text-slate-600"
    },
    { 
      id: "events" as AutomationComponentType, 
      label: "Event Definitions", 
      description: "Browse all available events you can trigger flows from",
      icon: Zap,
      count: 0,
      bgClass: "bg-yellow-50",
      iconClass: "text-yellow-600"
    },
    { 
      id: "mcp_connections" as AutomationComponentType, 
      label: "MCP Connections", 
      description: "External service connectors for AI agents (Outlook, PayPal, etc.)",
      icon: Plug,
      count: 0,
      bgClass: "bg-cyan-50",
      iconClass: "text-cyan-600"
    },
    { 
      id: "json_schemas" as AutomationComponentType, 
      label: "JSON Schemas", 
      description: "Reusable output schemas for structured AI agent responses",
      icon: Braces,
      count: 0,
      bgClass: "bg-orange-50",
      iconClass: "text-orange-600"
    },
  ];
  
  const handleManageComponent = (componentType: AutomationComponentType) => {
    switch (componentType) {
      case "scripts":
        navigate("/workflows/scripts");
        break;
      case "whatsapp_templates":
        navigate("/workflows/whatsapp-templates");
        break;
      case "webhooks":
        navigate("/workflows/webhooks");
        break;
      case "agent_tools":
        navigate("/workflows/agent-tools");
        break;
      case "events":
        navigate("/workflows/events");
        break;
      case "mcp_connections":
        navigate("/workflows/mcp-connections");
        break;
      case "json_schemas":
        navigate("/workflows/json-schemas");
        break;
      case "robots":
        navigate("/agent-console");
        break;
      default:
        // Other component types not yet implemented
        break;
    }
  };
  
  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3" data-testid="component-types-grid">
        {componentTypes.map((type) => (
          <ComponentTypeCard 
            key={type.id} 
            type={type} 
            onManage={() => handleManageComponent(type.id)}
          />
        ))}
      </div>
    </div>
  );
}

// Component Type Card
interface ComponentTypeCardProps {
  type: {
    id: AutomationComponentType;
    label: string;
    description: string;
    icon: any;
    count: number;
    bgClass: string;
    iconClass: string;
  };
  onManage?: () => void;
}

function ComponentTypeCard({ type, onManage }: ComponentTypeCardProps) {
  const Icon = type.icon;
  
  return (
    <GlassPanel 
      className="p-6 space-y-4 hover-elevate cursor-pointer" 
      data-testid={`card-component-type-${type.id}`}
    >
      <div className="flex items-start justify-between gap-4">
        <div 
          className={`w-12 h-12 rounded-lg ${type.bgClass} flex items-center justify-center shrink-0`}
          data-testid={`icon-${type.id}`}
        >
          <Icon className={`h-6 w-6 ${type.iconClass}`} />
        </div>
        {type.count > 0 && (
          <Badge 
            variant="outline"
            data-testid={`count-${type.id}`}
          >
            {type.count}
          </Badge>
        )}
      </div>

      <div className="space-y-1">
        <h3 className="font-semibold" data-testid={`text-name-${type.id}`}>
          {type.label}
        </h3>
        <p className="text-sm text-muted-foreground line-clamp-2" data-testid={`text-description-${type.id}`}>
          {type.description}
        </p>
      </div>

      <div className="flex justify-end">
        <Button 
          variant="outline" 
          size="sm"
          onClick={onManage}
          data-testid={`button-manage-${type.id}`}
        >
          Manage
        </Button>
      </div>
    </GlassPanel>
  );
}

const getStatusAccent = (status?: string) => {
  if (!status) return "bg-muted text-muted-foreground";
  const normalized = status.toLowerCase();
  if (normalized === "active") return "bg-emerald-50 text-emerald-600";
  if (normalized === "draft") return "bg-amber-50 text-amber-600";
  if (normalized === "error") return "bg-red-50 text-red-600";
  return "bg-muted text-muted-foreground";
};

const ScorecardItem = ({ label, value, helper }: { label: string; value: string; helper: string }) => (
  <div>
    <p className="text-xs uppercase tracking-wide text-muted-foreground">{label}</p>
    <p className="text-lg font-semibold">{value}</p>
    <p className="text-xs text-muted-foreground">{helper}</p>
  </div>
);

type ReportsView = "wa_ops" | "wa_business" | "executions";

type ExecutionStatsStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed"
  | "cancelled"
  | "success"
  | "error";

interface FlowExecutionStatsResponse {
  total_all_time: number;
  total_window: number;
  by_status: Record<string, number>;
  by_trigger_source: Record<string, number>;
  avg_duration_ms: number | null;
  success_rate: number | null;
  latest_runs: Array<{
    id: string;
    status: ExecutionStatsStatus | string;
    started_at?: string;
    completed_at?: string;
    duration_ms?: number | null;
    execution_mode?: string;
    trigger_source?: string;
    version_label?: string;
    version_id?: string;
    error_message?: string | null;
  }>;
}

function ReportsWorkspace({
  workflows,
  whatsappTemplates,
}: {
  workflows: Workflow[];
  whatsappTemplates: Array<{ id?: string; name?: string }>;
}) {
  const { toast } = useToast();
  const [view, setView] = useState<ReportsView>("wa_ops");

  const [flowId, setFlowId] = useState<string>("");
  const [templateId, setTemplateId] = useState<string>("all");
  const [days, setDays] = useState<number>(7);
  const [fromDate, setFromDate] = useState<string>("");
  const [toDate, setToDate] = useState<string>("");
  const [runParams, setRunParams] = useState<{
    flowId: string;
    templateId?: string;
    fromDate?: string;
    toDate?: string;
    days: number;
    nonce: number;
  } | null>(null);

  const selectedFlow = useMemo(() => workflows.find((w) => w.id === flowId) ?? null, [workflows, flowId]);

  const runReport = () => {
    if (!flowId) {
      toast({ title: "Select a flow", description: "Choose a flow to generate the report.", variant: "destructive" });
      return;
    }
    setRunParams({
      flowId,
      templateId: templateId !== "all" ? templateId : undefined,
      fromDate: fromDate || undefined,
      toDate: toDate || undefined,
      days: Math.max(1, Math.min(365, Number.isFinite(days) ? days : 7)),
      nonce: Date.now(),
    });
  };

  const executionStatsQuery = useQuery<FlowExecutionStatsResponse>({
    queryKey: ["reports", "executions-stats", runParams?.flowId, runParams?.days, runParams?.nonce],
    enabled: !!runParams?.flowId,
    queryFn: () => fetchJson<FlowExecutionStatsResponse>(apiV1(`/flows/${runParams!.flowId}/executions/stats/`), { days: String(runParams!.days) }),
    staleTime: 0,
  });

  const executionsForReportQuery = useQuery<AnalysisExecutionsResponse>({
    queryKey: ["reports", "wa", "executions", runParams],
    enabled: !!runParams?.flowId,
    queryFn: async () => {
      const params: Record<string, string> = { page: "1", page_size: "200" };
      if (runParams?.flowId) params.flow_id = runParams.flowId;
      if (runParams?.fromDate) params.from_date = runParams.fromDate;
      if (runParams?.toDate) params.to_date = runParams.toDate;
      return fetchJson<AnalysisExecutionsResponse>(EXECUTIONS_PATH, params);
    },
    staleTime: 0,
  });

  const executionsForReport = useMemo(() => {
    const data = executionsForReportQuery.data;
    if (!data) return [] as AnalysisExecution[];
    const list = (Array.isArray(data) ? (data as any) : (data.results ?? data.executions ?? data.data ?? [])) as AnalysisExecution[];

    const flowFiltered = runParams?.flowId ? list.filter((e) => e.flow_id === runParams.flowId) : list;
    const fromTs = runParams?.fromDate ? new Date(runParams.fromDate).getTime() : undefined;
    const toTs = runParams?.toDate ? new Date(runParams.toDate).getTime() : undefined;
    const dateFiltered = flowFiltered.filter((e) => {
      const ts = e.started_at ? new Date(e.started_at).getTime() : 0;
      if (fromTs && ts && ts < fromTs) return false;
      if (toTs && ts && ts > toTs) return false;
      return true;
    });

    return dateFiltered.sort((a, b) => {
      const ta = a.started_at ? new Date(a.started_at).getTime() : 0;
      const tb = b.started_at ? new Date(b.started_at).getTime() : 0;
      return tb - ta;
    });
  }, [executionsForReportQuery.data, runParams]);

  const fetchMessagesForExecutionIds = async (executionIds: string[]) => {
    const concurrency = 6;
    const results: WaMessageLog[] = [];
    for (let i = 0; i < executionIds.length; i += concurrency) {
      const chunk = executionIds.slice(i, i + concurrency);
      const chunkRes = await Promise.all(
        chunk.map(async (id) => {
          try {
            return await fetchJson<WaMessageLog[]>(apiV1(`/flows/executions/${id}/messages/`));
          } catch (e) {
            console.warn("[REPORTS] Failed to fetch messages for execution", id, e);
            return [] as WaMessageLog[];
          }
        })
      );
      chunkRes.forEach((arr) => results.push(...arr));
    }
    return results;
  };

  const messagesQuery = useQuery<WaMessageLog[]>({
    queryKey: ["reports", "wa", "messages", runParams, executionsForReport.map((e) => e.id)],
    enabled: !!runParams?.flowId && executionsForReport.length > 0,
    queryFn: () => fetchMessagesForExecutionIds(executionsForReport.map((e) => e.id)),
    staleTime: 0,
  });

  const normalizedMessages = useMemo(() => {
    const list = messagesQuery.data ?? [];

    const inferTemplateId = (msg: WaMessageLog): string | undefined => {
      const direct = (msg as any).template_id ?? (msg as any).whatsapp_template_id;
      if (typeof direct === "string" && direct.trim()) return direct;
      const api = (msg as any).api_response;
      const candidates = [
        api?.template_id,
        api?.template?.id,
        api?.template?.template_id,
        api?.message?.template_id,
        api?.data?.template_id,
      ];
      for (const c of candidates) {
        if (typeof c === "string" && c.trim()) return c;
      }
      return undefined;
    };

    const withTemplate = list.map((m) => ({
      ...m,
      template_id: m.template_id ?? inferTemplateId(m),
    }));

    if (!runParams?.templateId) return withTemplate;
    return withTemplate.filter((m) => m.template_id === runParams.templateId);
  }, [messagesQuery.data, runParams]);

  const summary = useMemo(() => {
    const byStatus: Record<string, number> = {};
    for (const m of normalizedMessages) {
      const k = String(m.status ?? "unknown");
      byStatus[k] = (byStatus[k] ?? 0) + 1;
    }
    const total = normalizedMessages.length;
    const delivered = (byStatus.delivered ?? 0) + (byStatus.read ?? 0);
    const failed = (byStatus.failed ?? 0) + (byStatus.error ?? 0);
    const deliveryRate = total > 0 ? Math.round((delivered / total) * 100) : 0;
    const failRate = total > 0 ? Math.round((failed / total) * 100) : 0;
    return { total, delivered, failed, deliveryRate, failRate, byStatus };
  }, [normalizedMessages]);

  const errorsTop = useMemo(() => {
    const counts = new Map<string, number>();
    for (const m of normalizedMessages) {
      const s = (m.error_message ?? "").trim();
      if (!s) continue;
      counts.set(s, (counts.get(s) ?? 0) + 1);
    }
    return Array.from(counts.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 10)
      .map(([error, count]) => ({ error, count }));
  }, [normalizedMessages]);

  const byTemplate = useMemo(() => {
    const map = new Map<string, { template_id?: string; template_name?: string; total: number; delivered: number; read: number; failed: number }>();
    for (const m of normalizedMessages) {
      const key = m.template_id || m.template_name || "(unknown template)";
      const cur = map.get(key) ?? { template_id: m.template_id, template_name: m.template_name, total: 0, delivered: 0, read: 0, failed: 0 };
      cur.total += 1;
      if (m.status === "delivered") cur.delivered += 1;
      if (m.status === "read") cur.read += 1;
      if (m.status === "failed" || m.status === "error") cur.failed += 1;
      map.set(key, cur);
    }
    return Array.from(map.values()).sort((a, b) => b.total - a.total);
  }, [normalizedMessages]);

  const byDay = useMemo(() => {
    const map = new Map<string, { day: string; total: number; delivered: number; failed: number; read: number }>();
    for (const m of normalizedMessages) {
      const day = new Date(m.created_at).toISOString().slice(0, 10);
      const cur = map.get(day) ?? { day, total: 0, delivered: 0, failed: 0, read: 0 };
      cur.total += 1;
      if (m.status === "delivered") cur.delivered += 1;
      if (m.status === "read") cur.read += 1;
      if (m.status === "failed" || m.status === "error") cur.failed += 1;
      map.set(day, cur);
    }
    return Array.from(map.values()).sort((a, b) => a.day.localeCompare(b.day)).slice(-30);
  }, [normalizedMessages]);

  const templateOptions = useMemo(() => {
    const fromCatalog = (whatsappTemplates ?? [])
      .map((t) => ({ id: String(t.id ?? ""), name: String(t.name ?? "") }))
      .filter((t) => t.id && t.name);

    const fromLogs = byTemplate
      .map((t) => ({ id: t.template_id ?? "", name: t.template_name ?? "" }))
      .filter((t) => t.id && t.name);

    const seen = new Set<string>();
    const merged: Array<{ id: string; name: string }> = [];
    for (const t of [...fromCatalog, ...fromLogs]) {
      const k = `${t.id}:${t.name}`;
      if (seen.has(k)) continue;
      seen.add(k);
      merged.push(t);
    }
    return merged.sort((a, b) => a.name.localeCompare(b.name));
  }, [whatsappTemplates, byTemplate]);

  const isRunning = executionsForReportQuery.isLoading || messagesQuery.isLoading;

  return (
    <div className="space-y-6">
      <div>
        <p className="text-xs uppercase tracking-wide text-muted-foreground">Reporting</p>
        <h2 className="text-2xl font-semibold">Reports</h2>
        <p className="text-sm text-muted-foreground mt-1">
          WhatsApp delivery and template performance reporting (flow-scoped).
        </p>
      </div>

      <GlassPanel className="p-4 space-y-4" data-testid="panel-reports-filters">
        <div className="flex flex-col lg:flex-row gap-3 lg:items-end">
          <div className="flex-1 min-w-[240px]">
            <Label className="text-xs">Flow</Label>
            <select
              className="mt-1 w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
              value={flowId}
              onChange={(e) => setFlowId(e.target.value)}
              data-testid="select-report-flow"
            >
              <option value="">Select flow...</option>
              {workflows
                .slice()
                .sort((a, b) => a.name.localeCompare(b.name))
                .map((w) => (
                  <option key={w.id} value={w.id}>
                    {w.name}
                  </option>
                ))}
            </select>
          </div>

          <div className="flex-1 min-w-[240px]">
            <Label className="text-xs">Template</Label>
            <select
              className="mt-1 w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
              value={templateId}
              onChange={(e) => setTemplateId(e.target.value)}
              data-testid="select-report-template"
            >
              <option value="all">All templates</option>
              {templateOptions.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name} ({t.id.slice(0, 8)}…)
                </option>
              ))}
            </select>
          </div>

          <div className="w-[180px]">
            <Label className="text-xs">From</Label>
            <Input
              type="date"
              value={fromDate}
              onChange={(e) => setFromDate(e.target.value)}
              className="mt-1 h-9"
              data-testid="input-report-from"
            />
          </div>

          <div className="w-[180px]">
            <Label className="text-xs">To</Label>
            <Input
              type="date"
              value={toDate}
              onChange={(e) => setToDate(e.target.value)}
              className="mt-1 h-9"
              data-testid="input-report-to"
            />
          </div>

          <div className="w-[140px]">
            <Label className="text-xs">Days (stats)</Label>
            <Input
              type="number"
              min={1}
              max={365}
              value={String(days)}
              onChange={(e) => {
                const n = Number(e.target.value);
                if (!Number.isFinite(n)) return;
                setDays(Math.max(1, Math.min(365, n)));
              }}
              className="mt-1 h-9"
              data-testid="input-report-days"
            />
          </div>

          <Button
            onClick={runReport}
            disabled={!flowId || isRunning}
            className="h-9"
            data-testid="button-run-report"
          >
            <FileSearch className="h-4 w-4 mr-2" />
            {isRunning ? "Generating..." : "Generate"}
          </Button>
        </div>

        {selectedFlow && runParams?.flowId === selectedFlow.id && (
          <div className="text-xs text-muted-foreground">
            Using <span className="font-medium text-foreground">{selectedFlow.name}</span> ·{" "}
            {executionsForReport.length} executions scanned · {normalizedMessages.length} message logs
          </div>
        )}
      </GlassPanel>

      <Tabs value={view} onValueChange={(v: string) => setView(v as ReportsView)}>
        <TabsList>
          <TabsTrigger value="wa_ops" data-testid="tab-report-ops">WhatsApp Ops</TabsTrigger>
          <TabsTrigger value="wa_business" data-testid="tab-report-business">WhatsApp Business</TabsTrigger>
          <TabsTrigger value="executions" data-testid="tab-report-executions">Executions</TabsTrigger>
        </TabsList>

        <TabsContent value="wa_ops" className="mt-4 space-y-4">
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <StatCard label="Messages" value={summary.total.toString()} helper="Total logs" icon={MessageSquare} accent="bg-primary/10 text-primary" />
            <StatCard label="Delivered" value={summary.delivered.toString()} helper={`Delivery rate ${summary.deliveryRate}%`} icon={CheckCircle} accent="bg-blue-100 text-blue-600 dark:bg-blue-900/30" />
            <StatCard label="Failed" value={summary.failed.toString()} helper={`Fail rate ${summary.failRate}%`} icon={XCircle} accent="bg-red-100 text-red-600 dark:bg-red-900/30" />
            <StatCard label="Read" value={(summary.byStatus.read ?? 0).toString()} helper="Read receipts" icon={Eye} accent="bg-purple-100 text-purple-600 dark:bg-purple-900/30" />
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <GlassPanel className="p-4">
              <div className="flex items-center justify-between mb-3">
                <h3 className="font-semibold text-sm">Top failure reasons</h3>
                <Badge variant="outline" className="text-[10px]">{errorsTop.length} shown</Badge>
              </div>
              {errorsTop.length === 0 ? (
                <div className="text-sm text-muted-foreground">No errors found for the selected filters.</div>
              ) : (
                <div className="space-y-2">
                  {errorsTop.map((e) => (
                    <div key={e.error} className="flex items-start justify-between gap-3 border rounded-md p-2">
                      <div className="text-xs text-muted-foreground break-words flex-1">{e.error}</div>
                      <Badge variant="secondary" className="shrink-0">{e.count}</Badge>
                    </div>
                  ))}
                </div>
              )}
            </GlassPanel>

            <GlassPanel className="p-4">
              <div className="flex items-center justify-between mb-3">
                <h3 className="font-semibold text-sm">Status breakdown</h3>
              </div>
              <div className="grid grid-cols-2 gap-2 text-sm">
                {Object.entries(summary.byStatus).sort((a, b) => b[1] - a[1]).map(([k, v]) => (
                  <div key={k} className="flex items-center justify-between border rounded-md px-3 py-2">
                    <span className="capitalize">{k.replaceAll("_", " ")}</span>
                    <Badge variant="outline">{v}</Badge>
                  </div>
                ))}
              </div>
            </GlassPanel>
          </div>
        </TabsContent>

        <TabsContent value="wa_business" className="mt-4 space-y-4">
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <StatCard label="Messages" value={summary.total.toString()} helper="Total logs" icon={MessageSquare} accent="bg-primary/10 text-primary" />
            <StatCard label="Templates" value={byTemplate.length.toString()} helper="Distinct templates in logs" icon={FileText} accent="bg-muted text-muted-foreground" />
            <StatCard label="Delivered" value={summary.delivered.toString()} helper={`Delivery rate ${summary.deliveryRate}%`} icon={CheckCircle} accent="bg-blue-100 text-blue-600 dark:bg-blue-900/30" />
            <StatCard label="Failed" value={summary.failed.toString()} helper={`Fail rate ${summary.failRate}%`} icon={XCircle} accent="bg-red-100 text-red-600 dark:bg-red-900/30" />
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <GlassPanel className="p-4">
              <div className="flex items-center justify-between mb-3">
                <h3 className="font-semibold text-sm">Volume by template</h3>
                <Badge variant="outline" className="text-[10px]">{byTemplate.length} total</Badge>
              </div>
              {byTemplate.length === 0 ? (
                <div className="text-sm text-muted-foreground">No messages found for the selected filters.</div>
              ) : (
                <div className="space-y-2">
                  {byTemplate.slice(0, 12).map((t) => (
                    <div key={t.template_id ?? t.template_name ?? "(unknown)"} className="border rounded-md p-3">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="font-medium text-sm truncate">
                            {t.template_name && t.template_id
                              ? `${t.template_name} (${t.template_id})`
                              : t.template_name ?? t.template_id ?? "(unknown template)"}
                          </div>
                        </div>
                        <Badge variant="secondary">{t.total}</Badge>
                      </div>
                      <div className="mt-2 flex flex-wrap gap-2 text-xs text-muted-foreground">
                        <span>Delivered: {t.delivered + t.read}</span>
                        <span>Read: {t.read}</span>
                        <span>Failed: {t.failed}</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </GlassPanel>

            <GlassPanel className="p-4">
              <div className="flex items-center justify-between mb-3">
                <h3 className="font-semibold text-sm">Last 30 days</h3>
              </div>
              {byDay.length === 0 ? (
                <div className="text-sm text-muted-foreground">No messages found for the selected filters.</div>
              ) : (
                <div className="space-y-2">
                  {byDay.map((d) => (
                    <div key={d.day} className="flex items-center justify-between border rounded-md px-3 py-2 text-sm">
                      <div className="text-xs text-muted-foreground">{d.day}</div>
                      <div className="flex items-center gap-3 text-xs">
                        <span>Total <Badge variant="outline">{d.total}</Badge></span>
                        <span>Delivered <Badge variant="outline">{d.delivered + d.read}</Badge></span>
                        <span>Failed <Badge variant="outline">{d.failed}</Badge></span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </GlassPanel>
          </div>
        </TabsContent>

        <TabsContent value="executions" className="mt-4 space-y-4">
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <StatCard
              label="Runs (all time)"
              value={String(executionStatsQuery.data?.total_all_time ?? 0)}
              helper="Total executions ever"
              icon={PlayCircle}
              accent="bg-primary/10 text-primary"
            />
            <StatCard
              label={`Runs (last ${runParams?.days ?? 7}d)`}
              value={String(executionStatsQuery.data?.total_window ?? 0)}
              helper="Windowed count"
              icon={TrendingUp}
              accent="bg-muted text-muted-foreground"
            />
            <StatCard
              label="Success rate"
              value={
                executionStatsQuery.data?.success_rate === null || executionStatsQuery.data?.success_rate === undefined
                  ? "-"
                  : `${Math.round(executionStatsQuery.data.success_rate * 100)}%`
              }
              helper="Windowed"
              icon={CheckCircle}
              accent="bg-emerald-100 text-emerald-600 dark:bg-emerald-900/30"
            />
            <StatCard
              label="Avg duration"
              value={
                executionStatsQuery.data?.avg_duration_ms === null || executionStatsQuery.data?.avg_duration_ms === undefined
                  ? "-"
                  : `${Math.round(executionStatsQuery.data.avg_duration_ms)}ms`
              }
              helper="Windowed"
              icon={Clock}
              accent="bg-indigo-100 text-indigo-600 dark:bg-indigo-900/30"
            />
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <GlassPanel className="p-4">
              <div className="flex items-center justify-between mb-3">
                <h3 className="font-semibold text-sm">By status (window)</h3>
              </div>
              {executionStatsQuery.isLoading ? (
                <Skeleton className="h-20" />
              ) : (
                <div className="grid grid-cols-2 gap-2 text-sm">
                  {Object.entries(executionStatsQuery.data?.by_status ?? {})
                    .sort((a, b) => b[1] - a[1])
                    .map(([k, v]) => (
                      <div key={k} className="flex items-center justify-between border rounded-md px-3 py-2">
                        <span className="capitalize">{k.replaceAll("_", " ")}</span>
                        <Badge variant="outline">{v}</Badge>
                      </div>
                    ))}
                  {Object.keys(executionStatsQuery.data?.by_status ?? {}).length === 0 && (
                    <div className="text-sm text-muted-foreground">No runs in window.</div>
                  )}
                </div>
              )}
            </GlassPanel>

            <GlassPanel className="p-4">
              <div className="flex items-center justify-between mb-3">
                <h3 className="font-semibold text-sm">By trigger source (window)</h3>
              </div>
              {executionStatsQuery.isLoading ? (
                <Skeleton className="h-20" />
              ) : (
                <div className="grid grid-cols-2 gap-2 text-sm">
                  {Object.entries(executionStatsQuery.data?.by_trigger_source ?? {})
                    .sort((a, b) => b[1] - a[1])
                    .map(([k, v]) => (
                      <div key={k} className="flex items-center justify-between border rounded-md px-3 py-2">
                        <span className="capitalize">{k.replaceAll("_", " ")}</span>
                        <Badge variant="outline">{v}</Badge>
                      </div>
                    ))}
                  {Object.keys(executionStatsQuery.data?.by_trigger_source ?? {}).length === 0 && (
                    <div className="text-sm text-muted-foreground">No runs in window.</div>
                  )}
                </div>
              )}
            </GlassPanel>
          </div>

          <GlassPanel className="p-4">
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-semibold text-sm">Latest runs (window)</h3>
              <Badge variant="outline" className="text-[10px]">
                {executionStatsQuery.data?.latest_runs?.length ?? 0} shown
              </Badge>
            </div>

            {executionStatsQuery.isLoading ? (
              <div className="space-y-2">
                <Skeleton className="h-10" />
                <Skeleton className="h-10" />
              </div>
            ) : (executionStatsQuery.data?.latest_runs?.length ?? 0) > 0 ? (
              <div className="space-y-2">
                {executionStatsQuery.data!.latest_runs.map((r) => (
                  <div key={r.id} className="flex items-center justify-between border rounded-md px-3 py-2 text-sm">
                    <div className="min-w-0">
                      <div className="font-medium truncate">{r.id.slice(0, 8)}…</div>
                      <div className="text-xs text-muted-foreground truncate">
                        {r.started_at ? new Date(r.started_at).toLocaleString() : "-"} ·{" "}
                        {r.trigger_source ?? "unknown trigger"}
                        {r.version_label ? ` · ${r.version_label}` : ""}
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge variant="outline" className="capitalize">
                        {String(r.status ?? "unknown").toLowerCase()}
                      </Badge>
                      <Badge variant="secondary" className="text-[10px]">
                        {r.duration_ms ? `${Math.round(r.duration_ms)}ms` : "-"}
                      </Badge>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-sm text-muted-foreground">No runs in window.</div>
            )}
          </GlassPanel>
        </TabsContent>
      </Tabs>
    </div>
  );
}

// Task Monitor Types
type TaskExecutionStatus = "pending" | "running" | "success" | "failed" | "timeout" | "cancelled";
type TaskTriggerType = "scheduled" | "manual" | "api";

interface TaskExecution {
  id: string;
  task_id?: string;
  task_name: string;
  status: TaskExecutionStatus;
  trigger_type: TaskTriggerType;
  started_at: string;
  finished_at?: string | null;
  duration_ms?: number;
  result?: any;
  error?: string | null;
  celery_task_id?: string;
  args?: any[];
  kwargs?: Record<string, any>;
  trace_id?: string;
  version_id?: string;
  version_status?: string;
  webhook_id?: string;
  webhook_name?: string;
}

type WaMessageStatus = "sent" | "sent_pending_id" | "failed" | "error" | "delivered" | "read";

interface WaMessageLog {
  id: string;
  flow_execution_id: string;
  recipient: string;
  template_id?: string;
  template_name?: string;
  message_type?: string;
  status: WaMessageStatus;
  message_id?: string;
  api_response?: any;
  error_message?: string;
  created_at: string;
}

const MESSAGE_STATUS_COLORS: Record<WaMessageStatus, { bg: string; text: string; icon: typeof CheckCircle }> = {
  sent: { bg: "bg-green-100 dark:bg-green-900", text: "text-green-600 dark:text-green-400", icon: CheckCircle },
  sent_pending_id: { bg: "bg-yellow-100 dark:bg-yellow-900", text: "text-yellow-600 dark:text-yellow-400", icon: Clock },
  delivered: { bg: "bg-blue-100 dark:bg-blue-900", text: "text-blue-600 dark:text-blue-400", icon: CheckCircle },
  read: { bg: "bg-purple-100 dark:bg-purple-900", text: "text-purple-600 dark:text-purple-400", icon: Eye },
  failed: { bg: "bg-red-100 dark:bg-red-900", text: "text-red-600 dark:text-red-400", icon: XCircle },
  error: { bg: "bg-red-100 dark:bg-red-900", text: "text-red-600 dark:text-red-400", icon: AlertTriangle },
};

interface TaskExecutionStats {
  total: number;
  pending: number;
  running: number;
  success: number;
  failed: number;
  timeout: number;
  cancelled: number;
  success_rate: number;
  avg_duration_ms: number;
}

interface TaskExecutionsResponse {
  results?: TaskExecution[];
  executions?: TaskExecution[];
  data?: TaskExecution[];
  count?: number;
  pagination?: {
    total_items: number;
    current_page: number;
    total_pages: number;
    page_size: number;
  };
}

const TASK_EXECUTIONS_PATH = apiV1("/flows/task-executions/");
const TASK_EXECUTIONS_STATS_PATH = apiV1("/flows/task-executions/stats/");
const TASK_EXECUTIONS_RUNNING_PATH = apiV1("/flows/task-executions/running/");

const STATUS_COLORS: Record<TaskExecutionStatus, { bg: string; text: string; icon: typeof CheckCircle }> = {
  pending: { bg: "bg-slate-100 dark:bg-slate-800", text: "text-slate-600 dark:text-slate-400", icon: Clock },
  running: { bg: "bg-blue-100 dark:bg-blue-900", text: "text-blue-600 dark:text-blue-400", icon: Activity },
  success: { bg: "bg-green-100 dark:bg-green-900", text: "text-green-600 dark:text-green-400", icon: CheckCircle },
  failed: { bg: "bg-red-100 dark:bg-red-900", text: "text-red-600 dark:text-red-400", icon: XCircle },
  timeout: { bg: "bg-amber-100 dark:bg-amber-900", text: "text-amber-600 dark:text-amber-400", icon: AlertTriangle },
  cancelled: { bg: "bg-gray-100 dark:bg-gray-800", text: "text-gray-600 dark:text-gray-400", icon: XCircle },
};

function TaskMonitorWorkspace() {
  const [statusFilter, setStatusFilter] = useState<"all" | TaskExecutionStatus>("all");
  const [triggerFilter, setTriggerFilter] = useState<"all" | TaskTriggerType>("all");
  const [taskNameSearch, setTaskNameSearch] = useState("");
  const [traceIdSearch, setTraceIdSearch] = useState("");
  const [fromDate, setFromDate] = useState<string>("");
  const [toDate, setToDate] = useState<string>("");
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);
  const [selectedExecution, setSelectedExecution] = useState<TaskExecution | null>(null);
  const { toast } = useToast();

  const hasActiveFilters = statusFilter !== "all" || triggerFilter !== "all" || taskNameSearch || traceIdSearch || fromDate || toDate;

  const clearFilters = () => {
    setStatusFilter("all");
    setTriggerFilter("all");
    setTaskNameSearch("");
    setTraceIdSearch("");
    setFromDate("");
    setToDate("");
    setPage(1);
  };

  const copyTraceId = (traceId: string) => {
    navigator.clipboard.writeText(traceId);
    toast({
      title: "Copied",
      description: `Trace ID ${traceId} copied to clipboard`,
    });
  };

  // Stats query
  const statsQuery = useQuery<TaskExecutionStats>({
    queryKey: [TASK_EXECUTIONS_STATS_PATH],
    queryFn: () => fetchJson<TaskExecutionStats>(TASK_EXECUTIONS_STATS_PATH),
    refetchInterval: 30000,
  });

  // Running executions query
  const runningQuery = useQuery<TaskExecutionsResponse>({
    queryKey: [TASK_EXECUTIONS_RUNNING_PATH],
    queryFn: () => fetchJson<TaskExecutionsResponse>(TASK_EXECUTIONS_RUNNING_PATH),
    refetchInterval: 5000,
  });

  // All executions query with filters
  const executionsQuery = useQuery<TaskExecutionsResponse>({
    queryKey: [
      TASK_EXECUTIONS_PATH,
      { 
        status: statusFilter !== "all" ? statusFilter : undefined,
        trigger_type: triggerFilter !== "all" ? triggerFilter : undefined,
        task_name: taskNameSearch || undefined,
        trace_id: traceIdSearch || undefined,
        from_date: fromDate || undefined,
        to_date: toDate || undefined,
        limit: pageSize,
        offset: (page - 1) * pageSize,
      }
    ],
    queryFn: () => {
      const params: Record<string, string> = {
        limit: pageSize.toString(),
        offset: ((page - 1) * pageSize).toString(),
      };
      if (statusFilter !== "all") params.status = statusFilter;
      if (triggerFilter !== "all") params.trigger_type = triggerFilter;
      if (taskNameSearch) params.task_name = taskNameSearch;
      if (traceIdSearch) params.trace_id = traceIdSearch;
      if (fromDate) params.from_date = fromDate;
      if (toDate) params.to_date = toDate;
      return fetchJson<TaskExecutionsResponse>(TASK_EXECUTIONS_PATH, params);
    },
    refetchInterval: 15000,
  });

  // Messages for selected execution
  const messagesQuery = useQuery<WaMessageLog[]>({
    queryKey: ["/api/v1/flows/executions", selectedExecution?.id, "messages"],
    queryFn: () => fetchJson<WaMessageLog[]>(apiV1(`/flows/executions/${selectedExecution!.id}/messages/`)),
    enabled: !!selectedExecution?.id,
    staleTime: 30000,
  });

  const stats = statsQuery.data ?? {
    total: 0,
    pending: 0,
    running: 0,
    success: 0,
    failed: 0,
    timeout: 0,
    cancelled: 0,
    success_rate: 0,
    avg_duration_ms: 0,
  };

  const runningExecutions = useMemo(() => {
    const data = runningQuery.data;
    if (!data) return [];
    if (Array.isArray(data)) return data as TaskExecution[];
    return (data.results ?? data.executions ?? data.data ?? []) as TaskExecution[];
  }, [runningQuery.data]);

  const executions = useMemo(() => {
    const data = executionsQuery.data;
    if (!data) return [];
    // Handle various response formats from API
    if (Array.isArray(data)) return data as TaskExecution[];
    return (data.results ?? data.executions ?? data.data ?? []) as TaskExecution[];
  }, [executionsQuery.data]);

  const totalPages = useMemo(() => {
    const data = executionsQuery.data;
    if (!data) return 1;
    if (data.pagination) return data.pagination.total_pages;
    if (data.count) return Math.ceil(data.count / pageSize);
    return 1;
  }, [executionsQuery.data, pageSize]);

  const formatDuration = (ms?: number) => {
    if (!ms) return "-";
    if (ms < 1000) return `${ms}ms`;
    if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
    return `${(ms / 60000).toFixed(1)}m`;
  };

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  return (
    <div className="space-y-6">
      {/* Stats Cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <GlassPanel className="p-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-blue-100 dark:bg-blue-900 flex items-center justify-center">
              <Activity className="h-5 w-5 text-blue-600 dark:text-blue-400" />
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Running</p>
              <p className="text-2xl font-bold" data-testid="stat-running">{stats.running}</p>
            </div>
          </div>
        </GlassPanel>

        <GlassPanel className="p-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-green-100 dark:bg-green-900 flex items-center justify-center">
              <CheckCircle className="h-5 w-5 text-green-600 dark:text-green-400" />
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Success Rate</p>
              <p className="text-2xl font-bold" data-testid="stat-success-rate">{stats.success_rate?.toFixed(1) ?? 0}%</p>
            </div>
          </div>
        </GlassPanel>

        <GlassPanel className="p-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-red-100 dark:bg-red-900 flex items-center justify-center">
              <XCircle className="h-5 w-5 text-red-600 dark:text-red-400" />
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Failed</p>
              <p className="text-2xl font-bold" data-testid="stat-failed">{stats.failed}</p>
            </div>
          </div>
        </GlassPanel>

        <GlassPanel className="p-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-slate-100 dark:bg-slate-800 flex items-center justify-center">
              <Clock className="h-5 w-5 text-slate-600 dark:text-slate-400" />
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Avg Duration</p>
              <p className="text-2xl font-bold" data-testid="stat-avg-duration">{formatDuration(stats.avg_duration_ms)}</p>
            </div>
          </div>
        </GlassPanel>
      </div>

      {/* Running Executions */}
      {runningExecutions.length > 0 && (
        <GlassPanel className="p-4">
          <div className="flex items-center gap-2 mb-3">
            <div className="w-2 h-2 rounded-full bg-blue-500 animate-pulse" />
            <h3 className="font-semibold text-sm">Live Executions ({runningExecutions.length})</h3>
          </div>
          <div className="space-y-2">
            {runningExecutions.slice(0, 5).map((exec) => {
              const StatusIcon = STATUS_COLORS[exec.status]?.icon ?? Activity;
              return (
                <div 
                  key={exec.id}
                  className="flex items-center justify-between p-2 rounded-lg bg-muted/50 hover-elevate cursor-pointer"
                  onClick={() => setSelectedExecution(exec)}
                  data-testid={`running-execution-${exec.id}`}
                >
                  <div className="flex items-center gap-2">
                    <StatusIcon className={`h-4 w-4 ${STATUS_COLORS[exec.status]?.text ?? "text-muted-foreground"}`} />
                    <span className="text-sm font-medium truncate max-w-[200px]">{exec.task_name}</span>
                    <Badge variant="outline" className="text-xs">{exec.trigger_type}</Badge>
                  </div>
                  <span className="text-xs text-muted-foreground">{formatDate(exec.started_at)}</span>
                </div>
              );
            })}
          </div>
        </GlassPanel>
      )}

      {/* Filters */}
      <div className="flex items-center gap-3 flex-wrap">
        <Select value={statusFilter} onValueChange={(v) => { setStatusFilter(v as "all" | TaskExecutionStatus); setPage(1); }}>
          <SelectTrigger className="w-40" data-testid="select-status-filter">
            <SelectValue placeholder="All Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Status</SelectItem>
            <SelectItem value="pending">Pending</SelectItem>
            <SelectItem value="running">Running</SelectItem>
            <SelectItem value="success">Success</SelectItem>
            <SelectItem value="failed">Failed</SelectItem>
            <SelectItem value="timeout">Timeout</SelectItem>
            <SelectItem value="cancelled">Cancelled</SelectItem>
          </SelectContent>
        </Select>

        <Select value={triggerFilter} onValueChange={(v) => { setTriggerFilter(v as "all" | TaskTriggerType); setPage(1); }}>
          <SelectTrigger className="w-40" data-testid="select-trigger-filter">
            <SelectValue placeholder="All Triggers" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Triggers</SelectItem>
            <SelectItem value="scheduled">Scheduled</SelectItem>
            <SelectItem value="manual">Manual</SelectItem>
            <SelectItem value="api">API</SelectItem>
          </SelectContent>
        </Select>

        <div className="relative flex-1 max-w-[180px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Task name..."
            value={taskNameSearch}
            onChange={(e) => { setTaskNameSearch(e.target.value); setPage(1); }}
            className="pl-9"
            data-testid="input-task-name-search"
          />
        </div>

        <div className="relative w-36">
          <GitBranch className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Trace ID..."
            value={traceIdSearch}
            onChange={(e) => { setTraceIdSearch(e.target.value); setPage(1); }}
            className="pl-9 font-mono text-xs"
            data-testid="input-trace-id-search"
          />
        </div>

        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1">
            <span className="text-xs text-muted-foreground">From:</span>
            <Input
              type="date"
              value={fromDate}
              onChange={(e) => { setFromDate(e.target.value); setPage(1); }}
              className="w-36 h-9"
              data-testid="input-from-date"
            />
          </div>
          <div className="flex items-center gap-1">
            <span className="text-xs text-muted-foreground">To:</span>
            <Input
              type="date"
              value={toDate}
              onChange={(e) => { setToDate(e.target.value); setPage(1); }}
              className="w-36 h-9"
              data-testid="input-to-date"
            />
          </div>
        </div>

        {hasActiveFilters && (
          <Button 
            variant="ghost" 
            size="sm"
            onClick={clearFilters}
            data-testid="button-clear-filters"
          >
            <XCircle className="h-4 w-4 mr-1" />
            Clear
          </Button>
        )}

        <div className="flex-1" />

        <Button 
          variant="outline" 
          size="sm"
          onClick={() => { 
            executionsQuery.refetch(); 
            statsQuery.refetch(); 
            runningQuery.refetch(); 
          }}
          data-testid="button-refresh"
        >
          <Activity className="h-4 w-4 mr-2" />
          Refresh
        </Button>
      </div>

      {/* Executions Table */}
      <GlassPanel className="p-0 overflow-hidden">
        {executionsQuery.isLoading ? (
          <div className="p-8 text-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto" />
            <p className="text-sm text-muted-foreground mt-2">Loading executions...</p>
          </div>
        ) : executionsQuery.isError ? (
          <div className="p-8">
            <ErrorDisplay error={executionsQuery.error} endpoint={TASK_EXECUTIONS_PATH} />
          </div>
        ) : executions.length === 0 ? (
          <div className="p-8">
            <EmptyState
              title="No executions found"
              description={hasActiveFilters
                ? "Try adjusting your filters." 
                : "Task executions will appear here once tasks are run."}
            />
          </div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="bg-muted/50 border-b">
                  <tr>
                    <th className="text-left text-xs font-medium text-muted-foreground p-3">Status</th>
                    <th className="text-left text-xs font-medium text-muted-foreground p-3">Trace ID</th>
                    <th className="text-left text-xs font-medium text-muted-foreground p-3">Task Name</th>
                    <th className="text-left text-xs font-medium text-muted-foreground p-3">Source</th>
                    <th className="text-left text-xs font-medium text-muted-foreground p-3">Started</th>
                    <th className="text-left text-xs font-medium text-muted-foreground p-3">Duration</th>
                    <th className="text-left text-xs font-medium text-muted-foreground p-3"></th>
                  </tr>
                </thead>
                <tbody>
                  {executions.map((exec, idx) => {
                    const StatusIcon = STATUS_COLORS[exec.status]?.icon ?? Circle;
                    const statusColor = STATUS_COLORS[exec.status];
                    return (
                      <tr 
                        key={exec.id}
                        className={`border-b last:border-0 hover:bg-muted/30 cursor-pointer ${idx % 2 === 0 ? "" : "bg-muted/10"}`}
                        onClick={() => setSelectedExecution(exec)}
                        data-testid={`row-execution-${exec.id}`}
                      >
                        <td className="p-3">
                          <div className="flex items-center gap-2">
                            <div className={`w-6 h-6 rounded-full ${statusColor?.bg ?? "bg-muted"} flex items-center justify-center`}>
                              <StatusIcon className={`h-3.5 w-3.5 ${statusColor?.text ?? "text-muted-foreground"}`} />
                            </div>
                            <span className={`text-xs font-medium ${statusColor?.text ?? "text-muted-foreground"}`}>
                              {exec.status}
                            </span>
                          </div>
                        </td>
                        <td className="p-3">
                          {exec.trace_id ? (
                            <div className="flex items-center gap-1">
                              <code className="text-xs font-mono bg-muted px-1.5 py-0.5 rounded text-primary">
                                {exec.trace_id}
                              </code>
                              <Button 
                                variant="ghost" 
                                size="icon" 
                                className="h-5 w-5"
                                onClick={(e) => { e.stopPropagation(); copyTraceId(exec.trace_id!); }}
                                data-testid={`button-copy-trace-${exec.id}`}
                              >
                                <Copy className="h-3 w-3" />
                              </Button>
                            </div>
                          ) : (
                            <span className="text-xs text-muted-foreground">-</span>
                          )}
                        </td>
                        <td className="p-3">
                          <span className="text-sm font-medium truncate max-w-[200px] block">{exec.task_name}</span>
                        </td>
                        <td className="p-3">
                          <div className="flex flex-col gap-0.5">
                            <Badge variant="outline" className="text-xs w-fit">{exec.trigger_type}</Badge>
                            {exec.webhook_name && (
                              <span className="text-[10px] text-muted-foreground flex items-center gap-1">
                                <Webhook className="h-2.5 w-2.5" />
                                {exec.webhook_name}
                              </span>
                            )}
                          </div>
                        </td>
                        <td className="p-3 text-sm text-muted-foreground">{formatDate(exec.started_at)}</td>
                        <td className="p-3 text-sm text-muted-foreground">{formatDuration(exec.duration_ms)}</td>
                        <td className="p-3">
                          <Button variant="ghost" size="icon" className="h-7 w-7">
                            <MoreVertical className="h-4 w-4" />
                          </Button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="flex items-center justify-between p-3 border-t">
                <span className="text-xs text-muted-foreground">
                  Page {page} of {totalPages}
                </span>
                <div className="flex gap-1">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setPage(p => Math.max(1, p - 1))}
                    disabled={page <= 1}
                    data-testid="button-prev-page"
                  >
                    Previous
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                    disabled={page >= totalPages}
                    data-testid="button-next-page"
                  >
                    Next
                  </Button>
                </div>
              </div>
            )}
          </>
        )}
      </GlassPanel>

      {/* Execution Detail Sheet */}
      {selectedExecution && (
        <Dialog open={!!selectedExecution} onOpenChange={(open) => !open && setSelectedExecution(null)}>
          <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                {(() => {
                  const StatusIcon = STATUS_COLORS[selectedExecution.status]?.icon ?? Circle;
                  const statusColor = STATUS_COLORS[selectedExecution.status];
                  return (
                    <>
                      <div className={`w-8 h-8 rounded-full ${statusColor?.bg ?? "bg-muted"} flex items-center justify-center`}>
                        <StatusIcon className={`h-4 w-4 ${statusColor?.text ?? "text-muted-foreground"}`} />
                      </div>
                      <span className="truncate">{selectedExecution.task_name}</span>
                    </>
                  );
                })()}
              </DialogTitle>
              <DialogDescription className="flex items-center gap-2">
                <span>Execution ID: {selectedExecution.id}</span>
                {selectedExecution.trace_id && (
                  <>
                    <span className="text-muted-foreground">|</span>
                    <span className="flex items-center gap-1">
                      Trace: 
                      <code className="font-mono bg-primary/10 text-primary px-1.5 py-0.5 rounded text-xs">
                        {selectedExecution.trace_id}
                      </code>
                      <Button 
                        variant="ghost" 
                        size="icon" 
                        className="h-5 w-5"
                        onClick={() => copyTraceId(selectedExecution.trace_id!)}
                        data-testid="button-copy-trace-detail"
                      >
                        <Copy className="h-3 w-3" />
                      </Button>
                    </span>
                  </>
                )}
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-4 py-2">
              {/* Status & Info Grid */}
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <p className="text-xs text-muted-foreground mb-1">Status</p>
                  <Badge className={`${STATUS_COLORS[selectedExecution.status]?.bg ?? ""} ${STATUS_COLORS[selectedExecution.status]?.text ?? ""}`}>
                    {selectedExecution.status}
                  </Badge>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground mb-1">Trigger Type</p>
                  <Badge variant="outline">{selectedExecution.trigger_type}</Badge>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground mb-1">Started</p>
                  <p>{new Date(selectedExecution.started_at).toLocaleString()}</p>
                </div>
                {selectedExecution.finished_at && (
                  <div>
                    <p className="text-xs text-muted-foreground mb-1">Finished</p>
                    <p>{new Date(selectedExecution.finished_at).toLocaleString()}</p>
                  </div>
                )}
                <div>
                  <p className="text-xs text-muted-foreground mb-1">Duration</p>
                  <p>{formatDuration(selectedExecution.duration_ms)}</p>
                </div>
                {selectedExecution.celery_task_id && (
                  <div>
                    <p className="text-xs text-muted-foreground mb-1">Celery Task ID</p>
                    <code className="text-xs bg-muted px-1 py-0.5 rounded">{selectedExecution.celery_task_id}</code>
                  </div>
                )}
              </div>

              {/* Trace & Version Info */}
              {(selectedExecution.trace_id || selectedExecution.version_id || selectedExecution.webhook_name) && (
                <div className="border rounded-lg p-4 space-y-3">
                  <div className="flex items-center gap-2 text-sm font-medium">
                    <GitBranch className="h-4 w-4 text-primary" />
                    Trace Information
                  </div>
                  <div className="grid grid-cols-2 gap-4 text-sm">
                    {selectedExecution.trace_id && (
                      <div>
                        <p className="text-xs text-muted-foreground mb-1">Trace ID</p>
                        <div className="flex items-center gap-1">
                          <code className="text-xs font-mono bg-primary/10 text-primary px-1.5 py-0.5 rounded">
                            {selectedExecution.trace_id}
                          </code>
                          <Button 
                            variant="ghost" 
                            size="icon" 
                            className="h-5 w-5"
                            onClick={() => copyTraceId(selectedExecution.trace_id!)}
                          >
                            <Copy className="h-3 w-3" />
                          </Button>
                        </div>
                        <p className="text-[10px] text-muted-foreground mt-1">
                          Search logs: [FLOW_TRACE:{selectedExecution.trace_id}]
                        </p>
                      </div>
                    )}
                    {selectedExecution.version_id && (
                      <div>
                        <p className="text-xs text-muted-foreground mb-1">Version</p>
                        <div className="flex items-center gap-2">
                          <code className="text-xs font-mono bg-muted px-1.5 py-0.5 rounded">
                            {selectedExecution.version_id.slice(0, 8)}...
                          </code>
                          {selectedExecution.version_status && (
                            <Badge variant="outline" className="text-[10px] h-5">
                              {selectedExecution.version_status}
                            </Badge>
                          )}
                        </div>
                      </div>
                    )}
                    {selectedExecution.webhook_name && (
                      <div>
                        <p className="text-xs text-muted-foreground mb-1">Webhook</p>
                        <div className="flex items-center gap-2">
                          <Webhook className="h-3.5 w-3.5 text-muted-foreground" />
                          <span className="text-sm">{selectedExecution.webhook_name}</span>
                        </div>
                        {selectedExecution.webhook_id && (
                          <code className="text-[10px] text-muted-foreground font-mono mt-0.5 block">
                            ID: {selectedExecution.webhook_id}
                          </code>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Error */}
              {selectedExecution.error && (
                <div>
                  <p className="text-xs text-muted-foreground mb-1">Error</p>
                  <div className="bg-destructive/10 text-destructive text-sm p-3 rounded-md">
                    {selectedExecution.error}
                  </div>
                </div>
              )}

              {/* Args */}
              {selectedExecution.args && selectedExecution.args.length > 0 && (
                <div>
                  <p className="text-xs text-muted-foreground mb-1">Arguments</p>
                  <ScrollArea className="h-24 border rounded p-2">
                    <pre className="text-xs">{JSON.stringify(selectedExecution.args, null, 2)}</pre>
                  </ScrollArea>
                </div>
              )}

              {/* Kwargs */}
              {selectedExecution.kwargs && Object.keys(selectedExecution.kwargs).length > 0 && (
                <div>
                  <p className="text-xs text-muted-foreground mb-1">Keyword Arguments</p>
                  <ScrollArea className="h-24 border rounded p-2">
                    <pre className="text-xs">{JSON.stringify(selectedExecution.kwargs, null, 2)}</pre>
                  </ScrollArea>
                </div>
              )}

              {/* Result */}
              {selectedExecution.result && (
                <div>
                  <p className="text-xs text-muted-foreground mb-1">Result</p>
                  <ScrollArea className="h-32 border rounded p-2">
                    <pre className="text-xs">{JSON.stringify(selectedExecution.result, null, 2)}</pre>
                  </ScrollArea>
                </div>
              )}

              {/* WhatsApp Messages */}
              <div className="border rounded-lg p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 text-sm font-medium">
                    <MessageSquare className="h-4 w-4 text-green-600" />
                    WhatsApp Messages
                  </div>
                  {messagesQuery.isLoading && (
                    <div className="text-xs text-muted-foreground">Loading...</div>
                  )}
                </div>
                
                {messagesQuery.data && messagesQuery.data.length > 0 ? (
                  <div className="space-y-2">
                    {messagesQuery.data.map((msg) => {
                      const statusInfo = MESSAGE_STATUS_COLORS[msg.status] || MESSAGE_STATUS_COLORS.error;
                      const StatusIcon = statusInfo.icon;
                      return (
                        <div 
                          key={msg.id} 
                          className="flex items-start gap-3 p-2 border rounded-md bg-muted/30"
                        >
                          <div className={`w-6 h-6 rounded-full ${statusInfo.bg} flex items-center justify-center shrink-0 mt-0.5`}>
                            <StatusIcon className={`h-3.5 w-3.5 ${statusInfo.text}`} />
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 flex-wrap">
                              <span className="text-sm font-medium">{msg.recipient}</span>
                              <Badge className={`text-[10px] ${statusInfo.bg} ${statusInfo.text}`}>
                                {msg.status.replace("_", " ")}
                              </Badge>
                            </div>
                            <div className="flex items-center gap-3 text-xs text-muted-foreground mt-1">
                              {msg.template_name && (
                                <span>Template: {msg.template_name}</span>
                              )}
                              {msg.message_type && (
                                <span>Type: {msg.message_type}</span>
                              )}
                              <span>{new Date(msg.created_at).toLocaleTimeString()}</span>
                            </div>
                            {msg.message_id && (
                              <div className="flex items-center gap-1 mt-1">
                                <code className="text-[10px] font-mono text-muted-foreground bg-muted px-1 rounded">
                                  msg_id: {msg.message_id}
                                </code>
                              </div>
                            )}
                            {msg.error_message && (
                              <div className="mt-1 text-xs text-destructive bg-destructive/10 px-2 py-1 rounded">
                                {msg.error_message}
                              </div>
                            )}
                            {msg.api_response && (
                              <details className="mt-1">
                                <summary className="text-[10px] text-muted-foreground cursor-pointer hover:text-foreground">
                                  View API Response
                                </summary>
                                <pre className="text-[10px] mt-1 p-2 bg-muted rounded overflow-x-auto">
                                  {JSON.stringify(msg.api_response, null, 2)}
                                </pre>
                              </details>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                ) : !messagesQuery.isLoading ? (
                  <div className="text-sm text-muted-foreground text-center py-4">
                    No WhatsApp messages sent in this execution
                  </div>
                ) : null}
              </div>
            </div>

            <DialogFooter>
              <Button variant="outline" onClick={() => setSelectedExecution(null)}>Close</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
}

