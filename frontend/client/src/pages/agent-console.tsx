import { useState, useMemo } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { Link } from "wouter";
import {
  Bot,
  Play,
  Search,
  Settings2,
  Clock,
  Zap,
  CheckCircle2,
  XCircle,
  Loader2,
  AlertCircle,
  ChevronRight,
  Activity,
  RefreshCw,
  ExternalLink,
  Plus,
} from "lucide-react";
import { PageLayout } from "@/components/layout/page-layout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { EmptyState } from "@/components/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import { fetchJson, apiRequest, queryClient } from "@/lib/queryClient";
import { apiV1 } from "@/lib/api";
import { useToast } from "@/hooks/use-toast";
import { formatDistanceToNow } from "date-fns";
import { cn } from "@/lib/utils";

// ─── Types ────────────────────────────────────────────────────────────────────

type Agent = {
  id: string;
  name: string;
  slug?: string;
  description?: string;
  enabled?: boolean;
  created_at?: string;
  updated_at?: string;
};

type AgentRun = {
  id: string;
  status?: "pending" | "running" | "success" | "failed" | "cancelled";
  trigger_source?: string;
  created_at?: string;
  updated_at?: string;
  usage?: {
    iterations?: number;
    llm_calls?: number;
    tool_calls?: number;
    tokens?: number;
  };
  error_data?: unknown;
};

// ─── Helpers ──────────────────────────────────────────────────────────────────

const ROBOTS_BASE = apiV1("/robots/");

function normalizeList<T>(data: unknown): T[] {
  if (!data) return [];
  if (Array.isArray(data)) return data as T[];
  if (typeof data === "object" && data !== null) {
    const r = data as Record<string, unknown>;
    for (const key of ["results", "items", "data", "robots", "runs"]) {
      if (Array.isArray(r[key])) return r[key] as T[];
    }
  }
  return [];
}

function runStatusIcon(status?: string) {
  switch (status) {
    case "success":
      return <CheckCircle2 className="h-4 w-4 text-green-500 dark:text-green-400 shrink-0" />;
    case "failed":
      return <XCircle className="h-4 w-4 text-destructive shrink-0" />;
    case "running":
      return <Loader2 className="h-4 w-4 text-primary animate-spin shrink-0" />;
    case "pending":
      return <Clock className="h-4 w-4 text-muted-foreground shrink-0" />;
    case "cancelled":
      return <AlertCircle className="h-4 w-4 text-muted-foreground shrink-0" />;
    default:
      return <AlertCircle className="h-4 w-4 text-muted-foreground shrink-0" />;
  }
}

function runStatusVariant(status?: string): "default" | "secondary" | "outline" | "destructive" {
  if (status === "success") return "default";
  if (status === "failed") return "destructive";
  if (status === "running" || status === "pending") return "secondary";
  return "outline";
}

function timeAgo(dateStr?: string) {
  if (!dateStr) return "—";
  try {
    return formatDistanceToNow(new Date(dateStr), { addSuffix: true });
  } catch {
    return "—";
  }
}

// ─── Agent List Item ──────────────────────────────────────────────────────────

function AgentListItem({
  agent,
  selected,
  onClick,
}: {
  agent: Agent;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "w-full text-left px-3 py-3 rounded-lg border transition-all duration-150 group",
        selected
          ? "bg-primary/10 border-primary/30 shadow-sm"
          : "bg-card/60 border-border hover:bg-card hover:border-border/80 hover:shadow-sm"
      )}
    >
      <div className="flex items-start gap-3">
        <div
          className={cn(
            "mt-0.5 flex h-8 w-8 items-center justify-center rounded-md shrink-0",
            selected ? "bg-primary/20" : "bg-muted group-hover:bg-muted/80"
          )}
        >
          <Bot className={cn("h-4 w-4", selected ? "text-primary" : "text-muted-foreground")} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium truncate">{agent.name}</span>
            {agent.enabled === false && (
              <Badge variant="outline" className="text-[10px] px-1.5 py-0 shrink-0">
                Disabled
              </Badge>
            )}
          </div>
          {agent.description && (
            <p className="text-xs text-muted-foreground truncate mt-0.5">{agent.description}</p>
          )}
        </div>
        <ChevronRight
          className={cn(
            "h-4 w-4 shrink-0 mt-1 transition-colors",
            selected ? "text-primary" : "text-muted-foreground/40 group-hover:text-muted-foreground"
          )}
        />
      </div>
    </button>
  );
}

// ─── Run History Row ──────────────────────────────────────────────────────────

function RunRow({ run }: { run: AgentRun }) {
  return (
    <div className="flex items-start gap-3 py-3 border-b last:border-0">
      {runStatusIcon(run.status)}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <Badge variant={runStatusVariant(run.status)} className="text-xs capitalize">
            {run.status ?? "unknown"}
          </Badge>
          {run.trigger_source && (
            <span className="text-xs text-muted-foreground">{run.trigger_source}</span>
          )}
        </div>
        {run.usage && (
          <div className="flex gap-3 mt-1.5 flex-wrap">
            {run.usage.iterations != null && (
              <span className="text-xs text-muted-foreground">
                <span className="font-medium text-foreground">{run.usage.iterations}</span> iter
              </span>
            )}
            {run.usage.tool_calls != null && (
              <span className="text-xs text-muted-foreground">
                <span className="font-medium text-foreground">{run.usage.tool_calls}</span> tool calls
              </span>
            )}
            {run.usage.tokens != null && (
              <span className="text-xs text-muted-foreground">
                <span className="font-medium text-foreground">{run.usage.tokens.toLocaleString()}</span> tokens
              </span>
            )}
          </div>
        )}
      </div>
      <span className="text-xs text-muted-foreground shrink-0">{timeAgo(run.created_at)}</span>
    </div>
  );
}

// ─── Agent Detail Panel ───────────────────────────────────────────────────────

function AgentDetail({ agent }: { agent: Agent }) {
  const { toast } = useToast();

  const runsPath = `${ROBOTS_BASE}${agent.id}/runs/`;

  const { data: runsData, isLoading: runsLoading, refetch: refetchRuns } = useQuery({
    queryKey: [runsPath],
    queryFn: () => fetchJson(runsPath),
    refetchInterval: 10_000,
  });

  const runs = useMemo(() => normalizeList<AgentRun>(runsData), [runsData]);

  const triggerMutation = useMutation({
    mutationFn: () =>
      apiRequest("POST", `${ROBOTS_BASE}${agent.id}/runs/`, {
        trigger_source: "manual",
      }),
    onSuccess: () => {
      toast({ title: "Agent triggered", description: `${agent.name} is starting a new run.` });
      queryClient.invalidateQueries({ queryKey: [runsPath] });
    },
    onError: () => {
      toast({
        title: "Could not trigger agent",
        description: "Check the agent configuration or try again.",
        variant: "destructive",
      });
    },
  });

  const lastRun = runs[0];
  const isRunning = lastRun?.status === "running" || lastRun?.status === "pending";

  return (
    <div className="flex flex-col h-full gap-4">
      {/* Agent Header Card */}
      <Card className="bg-card/70 backdrop-blur-sm border-border/60">
        <CardHeader className="pb-3">
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-start gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/15 shrink-0">
                <Bot className="h-5 w-5 text-primary" />
              </div>
              <div>
                <CardTitle className="text-base">{agent.name}</CardTitle>
                {agent.description && (
                  <CardDescription className="mt-0.5 text-sm">{agent.description}</CardDescription>
                )}
                {agent.slug && (
                  <span className="text-xs text-muted-foreground/70 font-mono mt-1 block">
                    {agent.slug}
                  </span>
                )}
              </div>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <Badge variant={agent.enabled === false ? "outline" : "default"} className="text-xs">
                {agent.enabled === false ? "Disabled" : "Active"}
              </Badge>
            </div>
          </div>
        </CardHeader>
        <CardContent className="pt-0">
          <div className="flex items-center gap-2 flex-wrap">
            <Button
              size="sm"
              onClick={() => triggerMutation.mutate()}
              disabled={triggerMutation.isPending || isRunning || agent.enabled === false}
              className="gap-1.5"
            >
              {triggerMutation.isPending || isRunning ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Play className="h-3.5 w-3.5" />
              )}
              {isRunning ? "Running…" : "Run now"}
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5"
              onClick={() => refetchRuns()}
            >
              <RefreshCw className="h-3.5 w-3.5" />
              Refresh
            </Button>
            <Link href={`/workflows`}>
              <Button variant="ghost" size="sm" className="gap-1.5 text-muted-foreground">
                <Settings2 className="h-3.5 w-3.5" />
                Configure
                <ExternalLink className="h-3 w-3 opacity-60" />
              </Button>
            </Link>
          </div>
        </CardContent>
      </Card>

      {/* Stats Strip */}
      {runs.length > 0 && (
        <div className="grid grid-cols-3 gap-3">
          {[
            {
              label: "Last run",
              value: timeAgo(lastRun?.created_at),
              icon: Clock,
            },
            {
              label: "Status",
              value: lastRun?.status ?? "—",
              icon: Activity,
              className: lastRun?.status === "success"
                ? "text-green-600 dark:text-green-400"
                : lastRun?.status === "failed"
                ? "text-destructive"
                : undefined,
            },
            {
              label: "Total runs",
              value: String(runs.length),
              icon: Zap,
            },
          ].map(({ label, value, icon: Icon, className }) => (
            <div key={label} className="bg-card/60 border border-border/60 rounded-lg p-3">
              <div className="flex items-center gap-1.5 text-xs text-muted-foreground mb-1">
                <Icon className="h-3.5 w-3.5" />
                {label}
              </div>
              <div className={cn("text-sm font-medium capitalize", className)}>{value}</div>
            </div>
          ))}
        </div>
      )}

      {/* Tabs: Run History */}
      <Tabs defaultValue="history" className="flex-1 flex flex-col min-h-0">
        <TabsList className="w-fit">
          <TabsTrigger value="history" className="gap-1.5 text-xs">
            <Activity className="h-3.5 w-3.5" />
            Run history
          </TabsTrigger>
        </TabsList>

        <TabsContent value="history" className="flex-1 mt-3 min-h-0">
          {runsLoading ? (
            <div className="space-y-3">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-16 w-full rounded-lg" />
              ))}
            </div>
          ) : runs.length === 0 ? (
            <EmptyState
              icon={Activity}
              title="No runs yet"
              description="Trigger this agent manually or wait for its scheduled run."
            />
          ) : (
            <ScrollArea className="h-full pr-2">
              <div className="space-y-0">
                {runs.map((run) => (
                  <RunRow key={run.id} run={run} />
                ))}
              </div>
            </ScrollArea>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}

// ─── Agent Console Page ───────────────────────────────────────────────────────

export default function AgentConsole() {
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const { data: agentsData, isLoading } = useQuery({
    queryKey: [ROBOTS_BASE],
    queryFn: () => fetchJson(ROBOTS_BASE),
  });

  const agents = useMemo(() => normalizeList<Agent>(agentsData), [agentsData]);

  const filtered = useMemo(() => {
    const q = search.toLowerCase().trim();
    if (!q) return agents;
    return agents.filter(
      (a) =>
        a.name.toLowerCase().includes(q) ||
        a.description?.toLowerCase().includes(q) ||
        a.slug?.toLowerCase().includes(q)
    );
  }, [agents, search]);

  const selectedAgent = useMemo(
    () => agents.find((a) => a.id === selectedId) ?? null,
    [agents, selectedId]
  );

  // Auto-select first agent when list loads
  const handleLoad = (list: Agent[]) => {
    if (!selectedId && list.length > 0) setSelectedId(list[0].id);
  };
  if (agents.length > 0 && !selectedId) {
    handleLoad(agents);
  }

  return (
    <PageLayout
      title="Agent Console"
      description="Monitor and trigger your AI agents operating on behalf of your organization."
      ctaLabel="New agent"
      ctaIcon={Plus}
      onCtaClick={() => {
        window.location.href = "/workflows";
      }}
    >
      <div className="flex gap-4 h-full" style={{ minHeight: "calc(100vh - 200px)" }}>
        {/* ── Left Panel: Agent List ── */}
        <div className="w-72 shrink-0 flex flex-col gap-3">
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search agents…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-8 h-9 text-sm bg-background"
            />
          </div>

          <ScrollArea className="flex-1">
            {isLoading ? (
              <div className="space-y-2">
                {Array.from({ length: 5 }).map((_, i) => (
                  <Skeleton key={i} className="h-16 w-full rounded-lg" />
                ))}
              </div>
            ) : filtered.length === 0 ? (
              search ? (
                <p className="text-xs text-muted-foreground text-center py-8">
                  No agents match "{search}"
                </p>
              ) : (
                <div className="flex flex-col items-center justify-center py-12 gap-3">
                  <Bot className="h-10 w-10 text-muted-foreground/40" />
                  <p className="text-sm text-muted-foreground text-center">No agents yet</p>
                  <Link href="/workflows">
                    <Button variant="outline" size="sm" className="gap-1.5 text-xs">
                      <Plus className="h-3.5 w-3.5" />
                      Create your first agent
                    </Button>
                  </Link>
                </div>
              )
            ) : (
              <div className="space-y-1.5 pr-1">
                {filtered.map((agent) => (
                  <AgentListItem
                    key={agent.id}
                    agent={agent}
                    selected={agent.id === selectedId}
                    onClick={() => setSelectedId(agent.id)}
                  />
                ))}
              </div>
            )}
          </ScrollArea>
        </div>

        {/* ── Right Panel: Agent Detail ── */}
        <div className="flex-1 min-w-0">
          {selectedAgent ? (
            <AgentDetail agent={selectedAgent} />
          ) : !isLoading ? (
            <div className="flex flex-col items-center justify-center h-full gap-3 text-center">
              <div className="flex h-14 w-14 items-center justify-center rounded-xl bg-muted">
                <Bot className="h-7 w-7 text-muted-foreground" />
              </div>
              <p className="text-sm text-muted-foreground max-w-xs">
                Select an agent from the list to view its status and run history.
              </p>
            </div>
          ) : null}
        </div>
      </div>
    </PageLayout>
  );
}
