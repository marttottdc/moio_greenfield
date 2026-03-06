import { useState, useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { 
  ChevronDown, 
  X, 
  Activity, 
  ArrowDown, 
  Maximize2,
  Minimize2,
  Trash2,
  RefreshCw,
  Radio,
  Rocket,
  FlaskConical,
  Eye
} from "lucide-react";
import { useFlowExecutionStream, type FlowExecutionEvent } from "@/hooks/useWebSocket";
import { apiV1 } from "@/lib/api";

export interface WSEvent {
  id: string;
  timestamp: number;
  eventType: string;
  payload: any;
  duration?: number;
  direction: "incoming" | "outgoing";
}

type ExecutionMode = "production" | "testing" | "preview";

interface RunningExecution {
  id: string;
  flow_id: string;
  flow_name: string;
  version_id?: string;
  trigger_source: string;
  execution_mode?: ExecutionMode;
  created_at: string;
}

const MODE_ICON_MAP: Record<ExecutionMode, typeof Rocket> = {
  production: Rocket,
  testing: FlaskConical,
  preview: Eye,
};

const MODE_COLORS: Record<ExecutionMode, string> = {
  production: "text-green-600 dark:text-green-400",
  testing: "text-amber-600 dark:text-amber-400",
  preview: "text-blue-600 dark:text-blue-400",
};

interface MiniWSDebuggerProps {
  isConnected?: boolean;
  events?: WSEvent[];
  onEventsChange?: (events: WSEvent[]) => void;
  latestEvent?: { eventType: string; payload: any } | null;
  isOpen?: boolean;
  onOpenChange?: (open: boolean) => void;
  flowId?: string | null;
  versionId?: string | null;
}

export function MiniWSDebugger({
  isConnected = false,
  events: externalEvents,
  onEventsChange,
  latestEvent,
  isOpen: controlledIsOpen,
  onOpenChange,
  flowId,
  versionId,
}: MiniWSDebuggerProps) {
  const [internalIsOpen, setInternalIsOpen] = useState(false);
  const isOpen = controlledIsOpen ?? internalIsOpen;
  const setIsOpen = (open: boolean) => {
    if (onOpenChange) {
      onOpenChange(open);
    } else {
      setInternalIsOpen(open);
    }
  };
  const [isExpanded, setIsExpanded] = useState(false);
  const [height, setHeight] = useState(280);
  const [internalEvents, setInternalEvents] = useState<WSEvent[]>([]);
  const [expandedEvents, setExpandedEvents] = useState<Set<string>>(new Set());
  const [selectedExecutionId, setSelectedExecutionId] = useState<string | null>(null);
  const [executionModeFilter, setExecutionModeFilter] = useState<ExecutionMode | "all">("all");
  const lastEventTimeRef = useRef<number>(0);
  const resizeRef = useRef<{ startY: number; startHeight: number } | null>(null);

  const events = externalEvents ?? internalEvents;
  
  // Use a ref to track the latest external events for the callback
  const externalEventsRef = useRef(externalEvents);
  externalEventsRef.current = externalEvents;
  
  const setEvents = (updater: ((prev: WSEvent[]) => WSEvent[]) | WSEvent[]) => {
    if (onEventsChange) {
      // For controlled mode, resolve updater against external events ref
      const currentEvents = externalEventsRef.current ?? [];
      const newEvents = typeof updater === "function" ? updater(currentEvents) : updater;
      onEventsChange(newEvents);
    } else {
      // For uncontrolled mode, use proper functional update to avoid stale state
      if (typeof updater === "function") {
        setInternalEvents(updater);
      } else {
        setInternalEvents(updater);
      }
    }
  };

  // Fetch running executions - filter by flowId, versionId, and execution_mode if provided
  const runningExecutionsQuery = useQuery({
    queryKey: ["flows", "executions", "running", flowId, versionId, executionModeFilter],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (flowId) params.append("flow_id", flowId);
      if (versionId) params.append("version_id", versionId);
      if (executionModeFilter !== "all") params.append("execution_mode", executionModeFilter);
      
      const queryString = params.toString();
      const url = queryString 
        ? apiV1(`/flows/api/executions/running/?${queryString}`)
        : apiV1("/flows/api/executions/running/");
      const response = await fetch(url, {
        credentials: "include",
      });
      if (!response.ok) {
        throw new Error("Failed to fetch running executions");
      }
      const data = await response.json() as RunningExecution[];
      // Client-side filter as backup if API doesn't support flow_id/version_id params
      let filtered = data;
      if (flowId) {
        filtered = filtered.filter(exec => exec.flow_id === flowId);
      }
      if (versionId) {
        filtered = filtered.filter(exec => !exec.version_id || exec.version_id === versionId);
      }
      if (executionModeFilter !== "all") {
        filtered = filtered.filter(exec => exec.execution_mode === executionModeFilter);
      }
      return filtered;
    },
    refetchInterval: 5000, // Refresh every 5 seconds
    enabled: isOpen,
  });

  // Get running executions data (needed for version isolation guard)
  const runningExecutions = runningExecutionsQuery.data ?? [];
  
  // Check if selected execution matches the current version (version isolation guard)
  const selectedExecution = runningExecutions.find(e => e.id === selectedExecutionId);
  const isVersionMismatch = versionId && selectedExecution?.version_id && selectedExecution.version_id !== versionId;
  
  // Subscribe to selected execution's WebSocket channel (disabled on version mismatch)
  const executionStream = useFlowExecutionStream({
    executionId: isVersionMismatch ? null : selectedExecutionId,
    enabled: Boolean(selectedExecutionId) && !isVersionMismatch,
    onEvent: (eventType: string, payload: FlowExecutionEvent) => {
      const now = Date.now();
      const duration = lastEventTimeRef.current ? now - lastEventTimeRef.current : 0;
      lastEventTimeRef.current = now;

      const newEvent: WSEvent = {
        id: `${now}-${Math.random()}`,
        timestamp: now,
        eventType,
        payload,
        duration: duration > 0 ? duration : undefined,
        direction: "incoming",
      };

      setEvents((prev) => [newEvent, ...prev].slice(0, 100));
    },
  });

  // Handle incoming events from parent (preview mode)
  useEffect(() => {
    if (latestEvent?.eventType && latestEvent?.payload) {
      const now = Date.now();
      const duration = lastEventTimeRef.current ? now - lastEventTimeRef.current : 0;
      lastEventTimeRef.current = now;

      const newEvent: WSEvent = {
        id: `${now}-${Math.random()}`,
        timestamp: now,
        eventType: latestEvent.eventType,
        payload: latestEvent.payload,
        duration: duration > 0 ? duration : undefined,
        direction: "incoming",
      };

      setEvents((prev) => [newEvent, ...prev].slice(0, 100));
    }
  }, [latestEvent?.eventType, latestEvent?.payload]);

  // Auto-select first execution for current flow/version when provided
  useEffect(() => {
    if (flowId && runningExecutions.length > 0 && !selectedExecutionId) {
      // Prefer execution matching both flowId and versionId
      let firstMatchingExecution = runningExecutions.find(exec => 
        exec.flow_id === flowId && (!versionId || exec.version_id === versionId)
      );
      // Fall back to flow-only match if no version match
      if (!firstMatchingExecution) {
        firstMatchingExecution = runningExecutions.find(exec => exec.flow_id === flowId);
      }
      if (firstMatchingExecution) {
        setSelectedExecutionId(firstMatchingExecution.id);
      }
    }
  }, [flowId, versionId, runningExecutions, selectedExecutionId]);

  // Clear selection when flow or version changes
  useEffect(() => {
    setSelectedExecutionId(null);
  }, [flowId, versionId]);

  const toggleEventExpanded = (id: string) => {
    const newExpanded = new Set(expandedEvents);
    if (newExpanded.has(id)) {
      newExpanded.delete(id);
    } else {
      newExpanded.add(id);
    }
    setExpandedEvents(newExpanded);
  };

  const formatTime = (timestamp: number) => {
    const date = new Date(timestamp);
    return date.toLocaleTimeString("en-US", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      fractionalSecondDigits: 3,
    });
  };

  const handleMouseDown = (e: React.MouseEvent<HTMLDivElement>) => {
    e.preventDefault();
    resizeRef.current = { startY: e.clientY, startHeight: height };
    
    const handleMouseMove = (e: globalThis.MouseEvent) => {
      if (!resizeRef.current) return;
      const delta = resizeRef.current.startY - e.clientY;
      const newHeight = Math.max(200, Math.min(600, resizeRef.current.startHeight + delta));
      setHeight(newHeight);
    };

    const handleMouseUp = () => {
      resizeRef.current = null;
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
    };
    
    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);
  };

  const clearEvents = () => {
    setEvents([]);
  };

  const isLive = isConnected || executionStream.isConnected;

  if (!isOpen) {
    return (
      <Button
        size="sm"
        variant="outline"
        onClick={() => setIsOpen(true)}
        // Keep the floating button above the app footer.
        className="fixed bottom-16 left-4 gap-2 z-50 shadow-md"
        data-testid="button-event-monitor-open"
      >
        <Activity className="w-4 h-4" />
        <span className="text-xs">Event Monitor</span>
        {events.length > 0 && (
          <Badge variant="secondary" className="ml-1 h-5 px-1.5">
            {events.length}
          </Badge>
        )}
      </Button>
    );
  }

  const panelHeight = isExpanded ? 500 : height;

  return (
    <div
      // Keep the floating panel above the app footer.
      className="fixed bottom-16 left-4 z-50 bg-background border rounded-lg shadow-lg flex flex-col overflow-hidden"
      style={{ width: isExpanded ? 420 : 340, height: panelHeight }}
      data-testid="panel-event-monitor"
    >
      {/* Resize Handle */}
      <div
        className="h-1.5 cursor-ns-resize bg-muted hover:bg-muted-foreground/20 transition-colors flex-shrink-0"
        onMouseDown={handleMouseDown}
      />

      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b bg-muted/30 flex-shrink-0">
        <div className="flex items-center gap-2">
          <Activity className="w-3.5 h-3.5" />
          <span className="font-medium text-xs">Event Monitor</span>
          <Badge
            variant={isLive ? "default" : "secondary"}
            className="text-[10px] h-4 px-1"
          >
            {isLive ? (
              <span className="flex items-center gap-1">
                <Radio className="w-2 h-2 animate-pulse" />
                Live
              </span>
            ) : "Off"}
          </Badge>
        </div>
        <div className="flex items-center gap-1">
          <Button
            size="icon"
            variant="ghost"
            className="h-6 w-6"
            onClick={clearEvents}
            title="Clear events"
            data-testid="button-clear-events"
          >
            <Trash2 className="w-3 h-3" />
          </Button>
          <Button
            size="icon"
            variant="ghost"
            className="h-6 w-6"
            onClick={() => setIsExpanded(!isExpanded)}
            title={isExpanded ? "Collapse" : "Expand"}
            data-testid="button-expand"
          >
            {isExpanded ? <Minimize2 className="w-3 h-3" /> : <Maximize2 className="w-3 h-3" />}
          </Button>
          <Button
            size="icon"
            variant="ghost"
            className="h-6 w-6"
            onClick={() => setIsOpen(false)}
            data-testid="button-event-monitor-close"
          >
            <X className="w-3 h-3" />
          </Button>
        </div>
      </div>

      {/* Mode Filter & Execution Selector */}
      <div className="px-3 py-2 border-b bg-muted/20 flex flex-col gap-2 flex-shrink-0">
        {/* Mode Filter */}
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-muted-foreground">Mode:</span>
          <Select
            value={executionModeFilter}
            onValueChange={(value) => setExecutionModeFilter(value as ExecutionMode | "all")}
          >
            <SelectTrigger className="h-6 text-[10px] w-24" data-testid="select-execution-mode">
              <SelectValue placeholder="All modes" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">
                <span>All modes</span>
              </SelectItem>
              <SelectItem value="production">
                <div className="flex items-center gap-1.5">
                  <Rocket className="w-3 h-3 text-green-600 dark:text-green-400" />
                  <span>Production</span>
                </div>
              </SelectItem>
              <SelectItem value="testing">
                <div className="flex items-center gap-1.5">
                  <FlaskConical className="w-3 h-3 text-amber-600 dark:text-amber-400" />
                  <span>Testing</span>
                </div>
              </SelectItem>
              <SelectItem value="preview">
                <div className="flex items-center gap-1.5">
                  <Eye className="w-3 h-3 text-blue-600 dark:text-blue-400" />
                  <span>Preview</span>
                </div>
              </SelectItem>
            </SelectContent>
          </Select>
        </div>
        
        {/* Execution Selector */}
        <div className="flex items-center gap-2">
          <Select
            value={selectedExecutionId || "none"}
            onValueChange={(value) => setSelectedExecutionId(value === "none" ? null : value)}
          >
            <SelectTrigger className="h-7 text-xs flex-1" data-testid="select-execution">
              <SelectValue placeholder="Select running flow..." />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="none">
                <span className="text-muted-foreground">No subscription</span>
              </SelectItem>
              {runningExecutions.map((exec) => {
                const ModeIcon = exec.execution_mode ? MODE_ICON_MAP[exec.execution_mode] : Radio;
                const modeColor = exec.execution_mode ? MODE_COLORS[exec.execution_mode] : "text-green-500";
                return (
                  <SelectItem key={exec.id} value={exec.id}>
                    <div className="flex items-center gap-2">
                      <ModeIcon className={`w-2.5 h-2.5 ${modeColor} ${!exec.execution_mode ? "animate-pulse" : ""}`} />
                      <span className="truncate">{exec.flow_name}</span>
                      {exec.execution_mode && (
                        <Badge variant="outline" className="h-4 text-[9px] px-1">
                          {exec.execution_mode}
                        </Badge>
                      )}
                      <span className="text-muted-foreground text-[10px]">
                        {exec.trigger_source}
                      </span>
                    </div>
                  </SelectItem>
                );
              })}
              {runningExecutions.length === 0 && (
                <SelectItem value="empty" disabled>
                  <span className="text-muted-foreground">No running executions</span>
                </SelectItem>
              )}
            </SelectContent>
          </Select>
          <Button
            size="icon"
            variant="ghost"
            className="h-7 w-7"
            onClick={() => runningExecutionsQuery.refetch()}
            disabled={runningExecutionsQuery.isFetching}
            title="Refresh executions"
            data-testid="button-refresh-executions"
          >
            <RefreshCw className={`w-3 h-3 ${runningExecutionsQuery.isFetching ? "animate-spin" : ""}`} />
          </Button>
        </div>
      </div>

      {/* Events List */}
      <ScrollArea className="flex-1 overflow-hidden">
        <div className="p-2 space-y-1">
          {events.length === 0 ? (
            <div className="text-xs text-muted-foreground p-4 text-center space-y-2">
              <Activity className="w-8 h-8 mx-auto opacity-30" />
              <p>Waiting for events...</p>
              <p className="text-[10px]">
                {selectedExecutionId 
                  ? "Subscribed to flow execution" 
                  : "Select a running flow or trigger a preview"}
              </p>
            </div>
          ) : (
            events.map((event) => (
              <div
                key={event.id}
                className={`text-xs border rounded p-2 cursor-pointer transition-colors ${
                  event.eventType.includes("error")
                    ? "bg-red-50 dark:bg-red-950/30 border-red-200 dark:border-red-800 hover:bg-red-100 dark:hover:bg-red-900/40"
                    : event.eventType.includes("completed")
                    ? "bg-green-50 dark:bg-green-950/30 border-green-200 dark:border-green-800 hover:bg-green-100 dark:hover:bg-green-900/40"
                    : event.eventType.includes("started")
                    ? "bg-blue-50 dark:bg-blue-950/30 border-blue-200 dark:border-blue-800 hover:bg-blue-100 dark:hover:bg-blue-900/40"
                    : "bg-card hover:bg-muted/50"
                }`}
                onClick={() => toggleEventExpanded(event.id)}
                data-testid={`event-${event.eventType}`}
              >
                <div className="flex items-center gap-1.5 justify-between">
                  <div className="flex items-center gap-1.5 flex-1 min-w-0">
                    <ChevronDown
                      className={`w-3 h-3 flex-shrink-0 transition-transform ${
                        expandedEvents.has(event.id) ? "rotate-180" : ""
                      }`}
                    />
                    <ArrowDown className="w-3 h-3 flex-shrink-0 text-cyan-600 dark:text-cyan-400" />
                    <code className="font-mono text-[11px] font-semibold truncate">
                      {event.eventType}
                    </code>
                  </div>
                  <div className="flex items-center gap-1.5 flex-shrink-0">
                    {event.duration !== undefined && event.duration > 0 && (
                      <span className="text-[10px] text-muted-foreground">
                        +{event.duration}ms
                      </span>
                    )}
                    <span className="text-muted-foreground text-[10px]">
                      {formatTime(event.timestamp)}
                    </span>
                  </div>
                </div>

                {expandedEvents.has(event.id) && (
                  <div className="mt-2 p-2 bg-muted/50 rounded text-[10px] font-mono max-h-32 overflow-auto">
                    <pre className="text-muted-foreground whitespace-pre-wrap break-words">
                      {JSON.stringify(event.payload, null, 2)}
                    </pre>
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      </ScrollArea>

      {/* Footer */}
      <div className="px-3 py-1.5 border-t bg-muted/30 text-[10px] text-muted-foreground flex-shrink-0 flex items-center justify-between">
        <span>{events.length} events</span>
        {selectedExecutionId && (
          <span className="truncate max-w-[150px]">
            Watching: {runningExecutions.find(e => e.id === selectedExecutionId)?.flow_name || selectedExecutionId.slice(0, 8)}
          </span>
        )}
      </div>
    </div>
  );
}
