import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Link } from "wouter";
import { ArrowLeft, Bot, Loader2, Search, Square, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/empty-state";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { fetchJson, apiRequest, queryClient } from "@/lib/queryClient";
import { apiV1 } from "@/lib/api";
import { useToast } from "@/hooks/use-toast";
import { useWebSocket, type WebSocketMessage } from "@/hooks/useWebSocket";

type Robot = {
  id: string;
  name: string;
  slug?: string;
  description?: string;
  enabled?: boolean;
  hard_timeout_seconds?: number;
  created_at?: string;
  updated_at?: string;
};

type RobotRun = {
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
    compactions_performed?: number;
  };
  error_data?: any;
};

type RobotSession = {
  id: string;
  session_key: string;
  run_id?: string | null;
  created_at?: string;
  updated_at?: string;
  metadata?: Record<string, any>;
};

type RobotEvent = {
  id?: string;
  event_type: string;
  payload?: any;
  created_at?: string;
  run_id?: string;
  session_id?: string;
};

/** Full payload supported by the API when creating a robot */
export type CreateRobotPayload = {
  name: string;
  slug?: string;
  description?: string;
  system_prompt?: string;
  bootstrap_context?: Record<string, unknown>;
  model_config?: Record<string, unknown>;
  tools_config?: Record<string, unknown>;
  targets?: Record<string, unknown>;
  operation_window?: { start?: string; end?: string; tz?: string };
  schedule?: { kind?: string; expr?: string; tz?: string };
  compaction_config?: { trigger_tokens?: number; keep_last_n?: number; max_entries_hard?: number };
  rate_limits?: { max_daily_runs?: number };
  enabled?: boolean;
  hard_timeout_seconds?: number;
};

const defaultCreateForm = (): CreateRobotFormState => ({
  name: "",
  slug: "",
  description: "",
  system_prompt: "You are a helpful sales assistant...",
  enabled: true,
  operation_window_start: "09:00",
  operation_window_end: "18:00",
  operation_window_tz: "America/Mexico_City",
  schedule_kind: "cron",
  schedule_expr: "0 9 * * 1-5",
  schedule_tz: "America/Mexico_City",
  max_iterations: 3,
  trigger_tokens: 8000,
  keep_last_n: 50,
  max_entries_hard: 2000,
  max_daily_runs: 100,
  hard_timeout_seconds: 3600,
  bootstrap_context_json: "{}",
  tools_config_json: "{}",
  targets_json: "{}",
});

type CreateRobotFormState = {
  name: string;
  slug: string;
  description: string;
  system_prompt: string;
  enabled: boolean;
  operation_window_start: string;
  operation_window_end: string;
  operation_window_tz: string;
  schedule_kind: string;
  schedule_expr: string;
  schedule_tz: string;
  max_iterations: number;
  trigger_tokens: number;
  keep_last_n: number;
  max_entries_hard: number;
  max_daily_runs: number;
  hard_timeout_seconds: number;
  bootstrap_context_json: string;
  tools_config_json: string;
  targets_json: string;
};

function buildCreatePayload(form: CreateRobotFormState): CreateRobotPayload {
  const slug = form.slug.trim() || form.name.trim().toLowerCase().replace(/\s+/g, "-");
  const payload: CreateRobotPayload = {
    name: form.name.trim(),
    slug: slug || undefined,
    description: form.description.trim() || undefined,
    system_prompt: form.system_prompt.trim() || undefined,
    enabled: form.enabled,
    operation_window:
      form.operation_window_start || form.operation_window_end || form.operation_window_tz
        ? {
            start: form.operation_window_start || undefined,
            end: form.operation_window_end || undefined,
            tz: form.operation_window_tz || undefined,
          }
        : undefined,
    schedule:
      form.schedule_kind || form.schedule_expr || form.schedule_tz
        ? {
            kind: form.schedule_kind || "cron",
            expr: form.schedule_expr || undefined,
            tz: form.schedule_tz || undefined,
          }
        : undefined,
    model_config: form.max_iterations != null ? { max_iterations: form.max_iterations } : undefined,
    compaction_config:
      form.trigger_tokens != null || form.keep_last_n != null || form.max_entries_hard != null
        ? {
            trigger_tokens: form.trigger_tokens,
            keep_last_n: form.keep_last_n,
            max_entries_hard: form.max_entries_hard,
          }
        : undefined,
    rate_limits:
      form.max_daily_runs != null && form.max_daily_runs > 0
        ? { max_daily_runs: form.max_daily_runs }
        : undefined,
    hard_timeout_seconds:
      form.hard_timeout_seconds != null && form.hard_timeout_seconds > 0
        ? form.hard_timeout_seconds
        : undefined,
  };
  try {
    const bc = form.bootstrap_context_json?.trim();
    if (bc && bc !== "{}") payload.bootstrap_context = JSON.parse(bc) as Record<string, unknown>;
  } catch {
    /* leave unset on parse error */
  }
  try {
    const tc = form.tools_config_json?.trim();
    if (tc && tc !== "{}") payload.tools_config = JSON.parse(tc) as Record<string, unknown>;
  } catch {
    /* leave unset */
  }
  try {
    const t = form.targets_json?.trim();
    if (t && t !== "{}") payload.targets = JSON.parse(t) as Record<string, unknown>;
  } catch {
    /* leave unset */
  }
  return payload;
}

const ROBOTS_BASE = apiV1("/robots/");

function normalizeCollection<T>(data: unknown, fallbackKey?: string): T[] {
  if (!data) return [];
  if (Array.isArray(data)) return data as T[];
  if (typeof data === "object" && data !== null) {
    const record = data as Record<string, unknown>;
    if (fallbackKey && Array.isArray(record[fallbackKey])) return record[fallbackKey] as T[];
    if (Array.isArray(record.results)) return record.results as T[];
    if (Array.isArray(record.items)) return record.items as T[];
    if (Array.isArray(record.data)) return record.data as T[];
    if (Array.isArray(record.runs)) return record.runs as T[];
    if (Array.isArray(record.events)) return record.events as T[];
    if (Array.isArray(record.sessions)) return record.sessions as T[];
    if (Array.isArray(record.robots)) return record.robots as T[];
  }
  return [];
}

function getStatusVariant(status?: string): "default" | "secondary" | "outline" | "destructive" {
  const s = String(status || "").toLowerCase();
  if (s === "success") return "default";
  if (s === "failed") return "destructive";
  if (s === "running" || s === "pending") return "secondary";
  return "outline";
}

/** Modal for creating a new robot with full configuration. */
function RobotCreateModal(props: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  createMutation: { mutate: (payload: CreateRobotPayload) => void; isPending: boolean };
}) {
  const { open, onOpenChange, createMutation } = props;
  const [form, setForm] = useState<CreateRobotFormState>(() => defaultCreateForm());

  const handleOpenChange = (next: boolean) => {
    if (!next) setForm(defaultCreateForm());
    onOpenChange(next);
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange} modal>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-hidden flex flex-col" aria-describedby="robot-create-description">
        <DialogHeader>
          <DialogTitle>Create robot</DialogTitle>
          <DialogDescription id="robot-create-description">
            Configure all options for the new robot. Optional fields can be left empty.
          </DialogDescription>
        </DialogHeader>
        <Tabs defaultValue="basic" className="flex-1 min-h-0 flex flex-col">
          <TabsList className="grid grid-cols-4 w-full">
            <TabsTrigger value="basic">Basic</TabsTrigger>
            <TabsTrigger value="schedule">Schedule</TabsTrigger>
            <TabsTrigger value="model">Model & compaction</TabsTrigger>
            <TabsTrigger value="advanced">Advanced</TabsTrigger>
          </TabsList>
          <ScrollArea className="flex-1 mt-4 pr-4 -mr-4">
            <TabsContent value="basic" className="mt-0 space-y-4">
              <div className="space-y-2">
                <Label htmlFor="create-robot-name">Name *</Label>
                <Input
                  id="create-robot-name"
                  value={form.name}
                  onChange={(e) => {
                    const name = e.target.value;
                    setForm((f) => ({
                      ...f,
                      name,
                      slug: f.slug ? f.slug : name.toLowerCase().replace(/\s+/g, "-"),
                    }));
                  }}
                  placeholder="Outbound Sales Robot"
                  data-testid="input-create-robot-name"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="create-robot-slug">Slug</Label>
                <Input
                  id="create-robot-slug"
                  value={form.slug}
                  onChange={(e) => setForm((f) => ({ ...f, slug: e.target.value }))}
                  placeholder="outbound-sales"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="create-robot-description">Description</Label>
                <Input
                  id="create-robot-description"
                  value={form.description}
                  onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
                  placeholder="Qualifies inbound leads and drafts follow-ups"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="create-robot-system-prompt">System prompt</Label>
                <Textarea
                  id="create-robot-system-prompt"
                  value={form.system_prompt}
                  onChange={(e) => setForm((f) => ({ ...f, system_prompt: e.target.value }))}
                  placeholder="You are a helpful sales assistant..."
                  rows={4}
                />
              </div>
              <div className="flex items-center gap-2">
                <Switch
                  id="create-robot-enabled"
                  checked={form.enabled}
                  onCheckedChange={(v) => setForm((f) => ({ ...f, enabled: v }))}
                />
                <Label htmlFor="create-robot-enabled">Enabled</Label>
              </div>
            </TabsContent>
            <TabsContent value="schedule" className="mt-0 space-y-4">
              <div className="text-sm font-medium text-muted-foreground mb-2">Operation window</div>
              <div className="grid grid-cols-3 gap-2">
                <div className="space-y-1">
                  <Label>Start</Label>
                  <Input
                    value={form.operation_window_start}
                    onChange={(e) => setForm((f) => ({ ...f, operation_window_start: e.target.value }))}
                    placeholder="09:00"
                  />
                </div>
                <div className="space-y-1">
                  <Label>End</Label>
                  <Input
                    value={form.operation_window_end}
                    onChange={(e) => setForm((f) => ({ ...f, operation_window_end: e.target.value }))}
                    placeholder="18:00"
                  />
                </div>
                <div className="space-y-1">
                  <Label>Timezone</Label>
                  <Input
                    value={form.operation_window_tz}
                    onChange={(e) => setForm((f) => ({ ...f, operation_window_tz: e.target.value }))}
                    placeholder="America/Mexico_City"
                  />
                </div>
              </div>
              <div className="text-sm font-medium text-muted-foreground mb-2">Schedule (cron)</div>
              <div className="grid grid-cols-3 gap-2">
                <div className="space-y-1">
                  <Label>Kind</Label>
                  <Input
                    value={form.schedule_kind}
                    onChange={(e) => setForm((f) => ({ ...f, schedule_kind: e.target.value }))}
                    placeholder="cron"
                  />
                </div>
                <div className="space-y-1 col-span-2">
                  <Label>Expression</Label>
                  <Input
                    value={form.schedule_expr}
                    onChange={(e) => setForm((f) => ({ ...f, schedule_expr: e.target.value }))}
                    placeholder="0 9 * * 1-5"
                  />
                </div>
                <div className="space-y-1 col-span-3">
                  <Label>Schedule timezone</Label>
                  <Input
                    value={form.schedule_tz}
                    onChange={(e) => setForm((f) => ({ ...f, schedule_tz: e.target.value }))}
                    placeholder="America/Mexico_City"
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-1">
                  <Label>Max daily runs</Label>
                  <Input
                    type="number"
                    min={0}
                    value={form.max_daily_runs}
                    onChange={(e) => setForm((f) => ({ ...f, max_daily_runs: Number(e.target.value) || 0 }))}
                  />
                </div>
                <div className="space-y-1">
                  <Label>Hard timeout (seconds)</Label>
                  <Input
                    type="number"
                    min={0}
                    value={form.hard_timeout_seconds}
                    onChange={(e) => setForm((f) => ({ ...f, hard_timeout_seconds: Number(e.target.value) || 0 }))}
                  />
                </div>
              </div>
            </TabsContent>
            <TabsContent value="model" className="mt-0 space-y-4">
              <div className="text-sm font-medium text-muted-foreground mb-2">Model config</div>
              <div className="space-y-1">
                <Label>Max iterations</Label>
                <Input
                  type="number"
                  min={1}
                  value={form.max_iterations}
                  onChange={(e) => setForm((f) => ({ ...f, max_iterations: Number(e.target.value) || 1 }))}
                />
              </div>
              <div className="text-sm font-medium text-muted-foreground mb-2 mt-4">Compaction config</div>
              <div className="grid grid-cols-3 gap-2">
                <div className="space-y-1">
                  <Label>Trigger tokens</Label>
                  <Input
                    type="number"
                    min={0}
                    value={form.trigger_tokens}
                    onChange={(e) => setForm((f) => ({ ...f, trigger_tokens: Number(e.target.value) || 0 }))}
                  />
                </div>
                <div className="space-y-1">
                  <Label>Keep last N</Label>
                  <Input
                    type="number"
                    min={0}
                    value={form.keep_last_n}
                    onChange={(e) => setForm((f) => ({ ...f, keep_last_n: Number(e.target.value) || 0 }))}
                  />
                </div>
                <div className="space-y-1">
                  <Label>Max entries hard</Label>
                  <Input
                    type="number"
                    min={0}
                    value={form.max_entries_hard}
                    onChange={(e) => setForm((f) => ({ ...f, max_entries_hard: Number(e.target.value) || 0 }))}
                  />
                </div>
              </div>
            </TabsContent>
            <TabsContent value="advanced" className="mt-0 space-y-4">
              <div className="space-y-2">
                <Label htmlFor="create-robot-bootstrap">bootstrap_context (JSON)</Label>
                <Textarea
                  id="create-robot-bootstrap"
                  value={form.bootstrap_context_json}
                  onChange={(e) => setForm((f) => ({ ...f, bootstrap_context_json: e.target.value }))}
                  rows={3}
                  className="font-mono text-xs"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="create-robot-tools">tools_config (JSON)</Label>
                <Textarea
                  id="create-robot-tools"
                  value={form.tools_config_json}
                  onChange={(e) => setForm((f) => ({ ...f, tools_config_json: e.target.value }))}
                  rows={3}
                  className="font-mono text-xs"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="create-robot-targets">targets (JSON)</Label>
                <Textarea
                  id="create-robot-targets"
                  value={form.targets_json}
                  onChange={(e) => setForm((f) => ({ ...f, targets_json: e.target.value }))}
                  rows={3}
                  className="font-mono text-xs"
                />
              </div>
            </TabsContent>
          </ScrollArea>
        </Tabs>
        <DialogFooter className="mt-4 border-t pt-4">
          <Button variant="outline" onClick={() => handleOpenChange(false)}>
            Cancel
          </Button>
          <Button
            data-testid="button-create-robot-submit"
            disabled={!form.name.trim() || createMutation.isPending}
            onClick={() => createMutation.mutate(buildCreatePayload(form))}
          >
            {createMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
            Create robot
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default function RobotsManager() {
  const { toast } = useToast();
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedRobotId, setSelectedRobotId] = useState<string | null>(null);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [liveEvents, setLiveEvents] = useState<RobotEvent[]>([]);
  const startedRunRef = useRef<string | null>(null);

  const robotsQuery = useQuery({
    queryKey: [ROBOTS_BASE],
    queryFn: () => fetchJson<any>(ROBOTS_BASE),
  });

  const robots = useMemo(
    () => normalizeCollection<Robot>(robotsQuery.data, "robots").filter((r) => Boolean(r?.id)),
    [robotsQuery.data]
  );

  useEffect(() => {
    if (!selectedRobotId && robots.length > 0) {
      setSelectedRobotId(String(robots[0].id));
    }
  }, [robots, selectedRobotId]);

  const selectedRobot = useMemo(
    () => robots.find((r) => r.id === selectedRobotId),
    [robots, selectedRobotId]
  );

  const runsQuery = useQuery({
    queryKey: [ROBOTS_BASE, selectedRobotId, "runs"],
    enabled: Boolean(selectedRobotId),
    queryFn: () => fetchJson<any>(`${ROBOTS_BASE}${selectedRobotId}/runs/`),
  });

  const sessionsQuery = useQuery({
    queryKey: [ROBOTS_BASE, selectedRobotId, "sessions"],
    enabled: Boolean(selectedRobotId),
    queryFn: () => fetchJson<any>(`${ROBOTS_BASE}${selectedRobotId}/sessions/`),
  });

  const eventsQuery = useQuery({
    queryKey: [ROBOTS_BASE, selectedRobotId, "events"],
    enabled: Boolean(selectedRobotId),
    queryFn: () => fetchJson<any>(`${ROBOTS_BASE}${selectedRobotId}/events/`, { limit: "100", offset: "0" }),
  });

  const runs = useMemo(
    () => normalizeCollection<RobotRun>(runsQuery.data, "runs").filter((r) => Boolean(r?.id)),
    [runsQuery.data]
  );
  const sessions = useMemo(
    () => normalizeCollection<RobotSession>(sessionsQuery.data, "sessions").filter((s) => Boolean(s?.id)),
    [sessionsQuery.data]
  );
  const apiEvents = useMemo(
    () => normalizeCollection<RobotEvent>(eventsQuery.data, "events"),
    [eventsQuery.data]
  );

  const createRobotMutation = useMutation({
    mutationFn: async (payload: CreateRobotPayload) => {
      const res = await apiRequest("POST", ROBOTS_BASE, { data: payload });
      return await res.json();
    },
    onSuccess: async (data) => {
      await queryClient.invalidateQueries({ queryKey: [ROBOTS_BASE] });
      const createdId = String(data?.robot?.id ?? data?.id ?? "");
      if (createdId) setSelectedRobotId(createdId);
      setCreateModalOpen(false);
      toast({ title: "Robot created" });
    },
    onError: (err: any) => {
      toast({
        title: "Failed to create robot",
        description: err?.message || "Please try again.",
        variant: "destructive",
      });
    },
  });

  const cancelMutation = useMutation({
    mutationFn: async ({ robotId, runId }: { robotId: string; runId: string }) => {
      try {
        const res = await apiRequest("POST", `${ROBOTS_BASE}runs/${runId}/cancel/`, { data: {} });
        return await res.json();
      } catch {
        const res = await apiRequest("POST", `${ROBOTS_BASE}${robotId}/runs/${runId}/cancel/`, { data: {} });
        return await res.json();
      }
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: [ROBOTS_BASE, selectedRobotId, "runs"] }),
        queryClient.invalidateQueries({ queryKey: [ROBOTS_BASE, selectedRobotId, "events"] }),
      ]);
      toast({ title: "Cancel requested" });
    },
    onError: (err: any) => {
      toast({
        title: "Failed to cancel run",
        description: err?.message || "Please try again.",
        variant: "destructive",
      });
    },
  });

  const ws = useWebSocket({
    path: selectedRobotId ? `/ws/robots/${selectedRobotId}/runs/stream/` : "",
    enabled: Boolean(selectedRobotId),
    onMessage: (message: WebSocketMessage<any>) => {
      const evt: RobotEvent = {
        event_type: message.event_type,
        payload: message.payload,
        created_at: message.timestamp || new Date().toISOString(),
        run_id: (message.payload as any)?.run_id,
        session_id: (message.payload as any)?.session_id,
      };
      setLiveEvents((prev) => [evt, ...prev].slice(0, 200));
    },
  });

  useEffect(() => {
    if (!ws.isConnected || !activeRunId) return;
    if (startedRunRef.current === activeRunId) return;
    ws.send("start_stream", { run_id: activeRunId });
    startedRunRef.current = activeRunId;
  }, [ws.isConnected, activeRunId, ws]);

  const filteredRobots = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return robots;
    return robots.filter((r) =>
      (r.name || "").toLowerCase().includes(q) ||
      (r.slug || "").toLowerCase().includes(q) ||
      (r.description || "").toLowerCase().includes(q)
    );
  }, [robots, searchQuery]);

  const mergedEvents = useMemo(() => {
    return [...liveEvents, ...apiEvents].slice(0, 300);
  }, [liveEvents, apiEvents]);

  return (
    <div className="h-full flex flex-col">
      <RobotCreateModal
        open={createModalOpen}
        onOpenChange={setCreateModalOpen}
        createMutation={createRobotMutation}
      />

      <div className="mb-6">
        <div className="flex items-center gap-3 mb-4">
          <Link href="/workflows?tab=components">
            <Button variant="ghost" size="icon" data-testid="button-back">
              <ArrowLeft className="h-5 w-5" />
            </Button>
          </Link>
          <h1 className="text-3xl font-bold">Robot Studio</h1>
          <div className="flex-1" />
          <Badge variant="outline">Backend: /api/v1/robots</Badge>
        </div>
      </div>

      <div className="flex h-full w-full">
        <div className="w-80 border-r border-border bg-background flex flex-col shrink-0">
          <div className="p-3 border-b border-border space-y-2">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
              <Input
                placeholder="Search robots..."
                className="pl-10"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                data-testid="input-search-robots"
              />
            </div>
            <Button
              className="w-full justify-center"
              variant="secondary"
              onClick={() => setCreateDialogOpen(true)}
              data-testid="button-create-robot"
            >
              <Plus className="h-4 w-4 mr-2" />
              Create robot
            </Button>
          </div>

          <div className="flex-1 overflow-y-auto">
            {robotsQuery.isLoading ? (
              <div className="p-4 text-sm text-muted-foreground">Loading robots...</div>
            ) : filteredRobots.length === 0 ? (
              <div className="p-4">
                <EmptyState
                  title={searchQuery.trim() ? "No robots match" : "No robots yet"}
                  description={searchQuery.trim() ? "Try another search term." : "Create your first robot to get started."}
                />
              </div>
            ) : (
              filteredRobots.map((robot) => (
                <div
                  key={robot.id}
                  onClick={() => {
                    setSelectedRobotId(robot.id);
                    setActiveRunId(null);
                    setLiveEvents([]);
                    startedRunRef.current = null;
                  }}
                  className={`p-3 border-b border-border cursor-pointer transition-colors ${
                    selectedRobotId === robot.id ? "bg-accent" : "hover-elevate"
                  }`}
                  data-testid={`item-robot-${robot.id}`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="font-medium text-sm truncate">{robot.name}</div>
                    <Badge variant={robot.enabled === false ? "outline" : "secondary"} className="text-[10px]">
                      {robot.enabled === false ? "disabled" : "enabled"}
                    </Badge>
                  </div>
                  {robot.slug && <div className="text-xs text-muted-foreground truncate">{robot.slug}</div>}
                </div>
              ))
            )}
          </div>
        </div>

        <div className="flex-1 flex flex-col bg-muted/20 backdrop-blur-sm">
          {!selectedRobot ? (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center">
                <div className="inline-flex h-16 w-16 items-center justify-center rounded-full bg-muted mb-4">
                  <Bot className="h-8 w-8 text-muted-foreground" />
                </div>
                <p className="text-sm text-muted-foreground">Select a robot to view details</p>
              </div>
            </div>
          ) : (
            <>
              <div className="flex-1 overflow-hidden p-4">
                <Tabs defaultValue="runs" className="h-full flex flex-col">
                  <TabsList className="grid grid-cols-4 w-[520px]">
                    <TabsTrigger value="runs">Runs</TabsTrigger>
                    <TabsTrigger value="sessions">Sessions</TabsTrigger>
                    <TabsTrigger value="events">Events</TabsTrigger>
                    <TabsTrigger value="live">Live Stream</TabsTrigger>
                  </TabsList>

                  <TabsContent value="runs" className="flex-1 min-h-0 mt-3">
                    <ScrollArea className="h-full rounded-md border bg-background p-3">
                      {runs.length === 0 ? (
                        <EmptyState title="No runs yet" description="Trigger the robot to create a run." />
                      ) : (
                        <div className="space-y-2">
                          {runs.map((run) => (
                            <div key={run.id} className="rounded-md border p-3">
                              <div className="flex items-center justify-between gap-2">
                                <div className="min-w-0">
                                  <div className="font-mono text-xs truncate">Run {run.id}</div>
                                  <div className="text-xs text-muted-foreground">
                                    {run.trigger_source || "manual"} {run.created_at ? `· ${new Date(run.created_at).toLocaleString()}` : ""}
                                  </div>
                                </div>
                                <div className="flex items-center gap-2">
                                  <Badge variant={getStatusVariant(run.status)}>{run.status || "unknown"}</Badge>
                                  <Button
                                    size="sm"
                                    variant="outline"
                                    onClick={() => {
                                      setActiveRunId(run.id);
                                      setLiveEvents([]);
                                      startedRunRef.current = null;
                                    }}
                                    data-testid={`button-stream-run-${run.id}`}
                                  >
                                    Stream
                                  </Button>
                                  <Button
                                    size="sm"
                                    variant="destructive"
                                    onClick={() => cancelMutation.mutate({ robotId: selectedRobot.id, runId: run.id })}
                                    disabled={cancelMutation.isPending || run.status === "cancelled" || run.status === "success" || run.status === "failed"}
                                    data-testid={`button-cancel-run-${run.id}`}
                                  >
                                    <Square className="h-3.5 w-3.5 mr-1" />
                                    Cancel
                                  </Button>
                                </div>
                              </div>
                              {run.usage && (
                                <div className="grid grid-cols-5 gap-2 mt-2 text-[11px] text-muted-foreground">
                                  <div>iterations: {run.usage.iterations ?? 0}</div>
                                  <div>llm: {run.usage.llm_calls ?? 0}</div>
                                  <div>tools: {run.usage.tool_calls ?? 0}</div>
                                  <div>tokens: {run.usage.tokens ?? 0}</div>
                                  <div>compactions: {run.usage.compactions_performed ?? 0}</div>
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                    </ScrollArea>
                  </TabsContent>

                  <TabsContent value="sessions" className="flex-1 min-h-0 mt-3">
                    <ScrollArea className="h-full rounded-md border bg-background p-3">
                      {sessions.length === 0 ? (
                        <EmptyState title="No sessions" description="Sessions appear after runs are triggered." />
                      ) : (
                        <div className="space-y-2">
                          {sessions.map((session) => (
                            <div key={session.id} className="rounded-md border p-3">
                              <div className="font-mono text-xs">{session.session_key}</div>
                              <div className="text-xs text-muted-foreground mt-1">
                                session: {session.id} {session.run_id ? `· run: ${session.run_id}` : ""}
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </ScrollArea>
                  </TabsContent>

                  <TabsContent value="events" className="flex-1 min-h-0 mt-3">
                    <ScrollArea className="h-full rounded-md border bg-background p-3">
                      {apiEvents.length === 0 ? (
                        <EmptyState title="No events" description="Events are emitted as runs progress." />
                      ) : (
                        <div className="space-y-2">
                          {apiEvents.map((event, idx) => (
                            <div key={`${event.id || idx}-${event.created_at || ""}`} className="rounded-md border p-2">
                              <div className="flex items-center justify-between gap-2">
                                <Badge variant="outline">{event.event_type}</Badge>
                                <span className="text-[11px] text-muted-foreground">
                                  {event.created_at ? new Date(event.created_at).toLocaleTimeString() : ""}
                                </span>
                              </div>
                              {event.payload && (
                                <pre className="text-[11px] bg-muted/40 p-2 rounded mt-2 overflow-x-auto">
                                  {JSON.stringify(event.payload, null, 2)}
                                </pre>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                    </ScrollArea>
                  </TabsContent>

                  <TabsContent value="live" className="flex-1 min-h-0 mt-3">
                    <Card className="h-full flex flex-col">
                      <CardHeader className="pb-2">
                        <CardTitle className="text-sm">Live Run Stream</CardTitle>
                        <CardDescription>
                          WS: {ws.status} {activeRunId ? `· run ${activeRunId}` : "· select a run and click Stream"}
                        </CardDescription>
                      </CardHeader>
                      <CardContent className="flex-1 min-h-0">
                        <ScrollArea className="h-full rounded-md border bg-background p-3">
                          {mergedEvents.length === 0 ? (
                            <EmptyState title="No live events yet" description="Stream a run to receive real-time updates." />
                          ) : (
                            <div className="space-y-2">
                              {mergedEvents.map((event, idx) => (
                                <div key={`live-${idx}-${event.created_at || ""}`} className="rounded-md border p-2">
                                  <div className="flex items-center justify-between gap-2">
                                    <Badge variant="secondary">{event.event_type}</Badge>
                                    <span className="text-[11px] text-muted-foreground">
                                      {event.created_at ? new Date(event.created_at).toLocaleTimeString() : ""}
                                    </span>
                                  </div>
                                  {event.payload && (
                                    <pre className="text-[11px] bg-muted/40 p-2 rounded mt-2 overflow-x-auto">
                                      {JSON.stringify(event.payload, null, 2)}
                                    </pre>
                                  )}
                                </div>
                              ))}
                            </div>
                          )}
                        </ScrollArea>
                      </CardContent>
                    </Card>
                  </TabsContent>
                </Tabs>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

