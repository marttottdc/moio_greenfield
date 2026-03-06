
import * as React from "react";
import { useState, useEffect, useRef } from "react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Drawer,
  DrawerClose,
  DrawerContent,
  DrawerDescription,
  DrawerFooter,
  DrawerHeader,
  DrawerTitle,
} from "@/components/ui/drawer";
import { CheckCircle, XCircle, Clock, Play, Wifi, WifiOff, Code2, ChevronDown, ArrowDown } from "lucide-react";
import type { PreviewExecution, PreviewTimelineEntry } from "./types";

export interface WSDebugEvent {
  id: string;
  timestamp: number;
  eventType: string;
  payload: any;
  duration?: number;
  direction: "incoming";
}

interface PreviewDrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  execution: PreviewExecution | null;
  onClear: () => void;
  isConnected: boolean;
  isArmed?: boolean;
  wsEvents?: WSDebugEvent[];
  onWsEventsChange?: (events: WSDebugEvent[]) => void;
  latestWsEvent?: { eventType: string; payload: any } | null;
}

export function PreviewDrawer({ 
  open, 
  onOpenChange, 
  execution, 
  onClear,
  isConnected,
  isArmed,
  wsEvents = [],
  onWsEventsChange,
  latestWsEvent
}: PreviewDrawerProps) {
  const [activeTab, setActiveTab] = useState("timeline");
  const [internalWsEvents, setInternalWsEvents] = useState<WSDebugEvent[]>([]);
  const [expandedEvents, setExpandedEvents] = useState<Set<string>>(new Set());
  const lastEventTimeRef = useRef<number>(0);
  
  // Use external events if provided, otherwise internal
  const events = wsEvents.length > 0 ? wsEvents : internalWsEvents;
  const setEvents = (updater: ((prev: WSDebugEvent[]) => WSDebugEvent[]) | WSDebugEvent[]) => {
    const newEvents = typeof updater === "function" ? updater(events) : updater;
    if (onWsEventsChange) {
      onWsEventsChange(newEvents);
    } else {
      setInternalWsEvents(newEvents);
    }
  };
  
  // Handle incoming WebSocket events
  useEffect(() => {
    if (latestWsEvent?.eventType && latestWsEvent?.payload) {
      const now = Date.now();
      const duration = lastEventTimeRef.current ? now - lastEventTimeRef.current : 0;
      lastEventTimeRef.current = now;

      const newEvent: WSDebugEvent = {
        id: `${now}-${Math.random()}`,
        timestamp: now,
        eventType: latestWsEvent.eventType,
        payload: latestWsEvent.payload,
        duration: duration > 0 ? duration : undefined,
        direction: "incoming",
      };

      setEvents([newEvent, ...events].slice(0, 100));
    }
  }, [latestWsEvent?.eventType, latestWsEvent?.payload]);
  
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

  const getStatusIcon = () => {
    if (!execution) return <Clock className="h-4 w-4 text-gray-500" />;

    switch (execution.status) {
      case "success":
        return <CheckCircle className="h-4 w-4 text-green-500" />;
      case "error":
      case "failed":
        return <XCircle className="h-4 w-4 text-red-500" />;
      case "running":
        return <Play className="h-4 w-4 text-blue-500 animate-pulse" />;
      default:
        return <Clock className="h-4 w-4 text-gray-500" />;
    }
  };

  const getStatusBadgeVariant = () => {
    if (!execution) return "outline";
    return execution.status === "success" ? "secondary" : "outline";
  };

  return (
    <Drawer open={open} onOpenChange={onOpenChange}>
      <DrawerContent className="h-[85vh]">
        <DrawerHeader className="border-b">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <DrawerTitle className="flex items-center gap-2">
                Flow Preview Log
                {getStatusIcon()}
              </DrawerTitle>
            </div>
            {execution?.id && (
              <Badge
                variant={isArmed ? "default" : isConnected ? "secondary" : "outline"}
                className={`flex items-center gap-1.5 text-[10px] px-2 py-0.5 ${
                  isArmed ? "animate-pulse" : ""
                }`}
              >
                {isArmed ? (
                  <>
                    <div className="h-2 w-2 rounded-full bg-current animate-pulse" />
                    <span>Armed & Live</span>
                  </>
                ) : isConnected ? (
                  <>
                    <Wifi className="h-3 w-3 animate-pulse" />
                    <span>Live</span>
                  </>
                ) : (
                  <>
                    <WifiOff className="h-3 w-3" />
                    <span>Disconnected</span>
                  </>
                )}
              </Badge>
            )}
          </div>
          <DrawerDescription>
            Track server-sent events for sandbox executions.
          </DrawerDescription>

          {/* Status bar */}
          <div className="flex items-center gap-2 text-xs text-muted-foreground flex-wrap pt-2">
            <span>Run ID:</span>
            <code className="text-[10px] bg-muted px-1 rounded">
              {execution?.id || "—"}
            </code>
            <span className="ml-2">Status:</span>
            <Badge variant={getStatusBadgeVariant()}>
              {execution?.status || "idle"}
            </Badge>
            <Button
              size="sm"
              variant="ghost"
              onClick={onClear}
              className="ml-auto h-7 text-xs"
            >
              Clear
            </Button>
          </div>
        </DrawerHeader>

        <Tabs value={activeTab} onValueChange={setActiveTab} className="flex-1 flex flex-col overflow-hidden">
          <div className="px-4 border-b">
            <TabsList className="h-9">
              <TabsTrigger value="timeline" className="text-xs" data-testid="tab-preview-timeline">
                <Play className="h-3 w-3 mr-1.5" />
                Timeline
                {execution?.entries && execution.entries.length > 0 && (
                  <Badge variant="secondary" className="ml-1.5 text-[10px] px-1.5">
                    {execution.entries.length}
                  </Badge>
                )}
              </TabsTrigger>
              <TabsTrigger value="ws-debug" className="text-xs" data-testid="tab-preview-ws-debug">
                <Code2 className="h-3 w-3 mr-1.5" />
                WS Debug
                {events.length > 0 && (
                  <Badge variant="secondary" className="ml-1.5 text-[10px] px-1.5">
                    {events.length}
                  </Badge>
                )}
              </TabsTrigger>
            </TabsList>
          </div>
          
          <TabsContent value="timeline" className="flex-1 m-0 overflow-hidden">
            <ScrollArea className="h-full p-4">
              <div className="space-y-3">
                {!execution ? (
                  <div className="flex items-center justify-center py-12">
                    <div className="text-center space-y-2">
                      <Play className="h-8 w-8 text-muted-foreground/50 mx-auto" />
                      <p className="text-sm text-muted-foreground">No preview running</p>
                      <p className="text-xs text-muted-foreground">
                        Click Preview to start a flow execution
                      </p>
                    </div>
                  </div>
                ) : execution.entries && execution.entries.length > 0 ? (
                  execution.entries.map((entry, index) => (
                    <TimelineEntryCard key={entry.id || `entry-${index}`} entry={entry} />
                  ))
                ) : (
                  <div className="flex flex-col items-center justify-center py-12 text-center">
                    <Clock className="h-12 w-12 text-muted-foreground/50 mb-3" />
                    <p className="text-sm text-muted-foreground">Waiting for events...</p>
                    <p className="text-xs text-muted-foreground mt-1">
                      Timeline entries will appear here as they occur.
                    </p>
                  </div>
                )}

                {execution?.summaryHtml && (
                  <>
                    <Separator className="my-4" />
                    <div className="rounded-lg border bg-card p-4 shadow-sm">
                      <h4 className="text-sm font-semibold mb-2 flex items-center gap-2">
                        <CheckCircle className="h-4 w-4 text-green-500" />
                        Execution Summary
                      </h4>
                      <div
                        className="prose prose-sm max-w-none dark:prose-invert"
                        dangerouslySetInnerHTML={{ __html: execution.summaryHtml }}
                      />
                    </div>
                  </>
                )}
              </div>
            </ScrollArea>
          </TabsContent>
          
          <TabsContent value="ws-debug" className="flex-1 m-0 overflow-hidden">
            <div className="flex flex-col h-full">
              {/* WS Debug Header */}
              <div className="px-4 py-2 border-b bg-muted/30 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Code2 className="h-4 w-4" />
                  <span className="text-sm font-medium">WebSocket Messages</span>
                  <Badge variant={isConnected ? "default" : "outline"} className="text-[10px]">
                    {isConnected ? "Connected" : "Disconnected"}
                  </Badge>
                </div>
                <Button 
                  variant="ghost" 
                  size="sm" 
                  className="h-7 text-xs"
                  onClick={() => setEvents([])}
                  data-testid="button-clear-ws-events"
                >
                  Clear
                </Button>
              </div>
              
              {/* WS Events List */}
              <ScrollArea className="flex-1">
                <div className="p-3 space-y-2">
                  {events.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-12 text-center">
                      <Code2 className="h-8 w-8 text-muted-foreground/50 mb-3" />
                      <p className="text-sm text-muted-foreground">Waiting for WebSocket messages...</p>
                      <p className="text-xs text-muted-foreground mt-1">
                        Messages will appear here as they are received.
                      </p>
                    </div>
                  ) : (
                    events.map((event) => (
                      <div
                        key={event.id}
                        className="text-xs border rounded p-2 cursor-pointer transition-colors bg-card hover:bg-muted/50"
                        onClick={() => toggleEventExpanded(event.id)}
                        data-testid={`ws-event-${event.eventType}`}
                      >
                        <div className="flex items-center gap-2 justify-between">
                          <div className="flex items-center gap-2 flex-1">
                            <ChevronDown
                              className={`w-3 h-3 transition-transform ${
                                expandedEvents.has(event.id) ? "rotate-180" : ""
                              }`}
                            />
                            <ArrowDown className="w-3 h-3 text-cyan-600 dark:text-cyan-400" />
                            <code className="font-mono font-semibold text-cyan-600 dark:text-cyan-400">
                              {event.eventType}
                            </code>
                          </div>
                          <div className="flex items-center gap-2">
                            {event.duration !== undefined && event.duration > 0 && (
                              <Badge variant="outline" className="text-[10px]">
                                +{event.duration}ms
                              </Badge>
                            )}
                            <span className="text-muted-foreground whitespace-nowrap text-[10px]">
                              {formatTime(event.timestamp)}
                            </span>
                          </div>
                        </div>

                        {expandedEvents.has(event.id) && (
                          <div className="mt-2 p-2 bg-muted/50 rounded text-xs font-mono max-h-48 overflow-auto">
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
              
              {/* WS Debug Footer */}
              <div className="px-4 py-2 border-t bg-muted/30 text-xs text-muted-foreground">
                Total: {events.length} messages | Last: {events.length > 0 ? formatTime(events[0].timestamp) : "none"}
              </div>
            </div>
          </TabsContent>
        </Tabs>

        <DrawerFooter className="border-t">
          <DrawerClose asChild>
            <Button variant="outline">Close</Button>
          </DrawerClose>
        </DrawerFooter>
      </DrawerContent>
    </Drawer>
  );
}

/**
 * Safely extracts a string message from entry.message
 * Handles cases where message might be a string, object, or other type
 */
function getMessage(message: any): string | null {
  if (!message) return null;
  if (typeof message === 'string') return message;
  if (typeof message === 'object') {
    // Try common message field names
    if (message.message && typeof message.message === 'string') {
      return message.message;
    }
    // Try to extract meaningful fields for objects like {steps_count, status}
    const parts: string[] = [];
    if (message.steps_count !== undefined) {
      parts.push(`${message.steps_count} steps`);
    }
    if (message.status) {
      parts.push(`Status: ${message.status}`);
    }
    if (parts.length > 0) {
      return parts.join(' • ');
    }
    // Fallback: stringify the object
    try {
      return JSON.stringify(message);
    } catch {
      return null;
    }
  }
  return null;
}

function TimelineEntryCard({ entry }: { entry: PreviewTimelineEntry }) {
  const getStatusColor = () => {
    switch (entry.status) {
      case "success":
        return "border-green-500/50 bg-green-50 dark:bg-green-950/20";
      case "error":
      case "failed":
        return "border-red-500/50 bg-red-50 dark:bg-red-950/20";
      case "running":
        return "border-blue-500/50 bg-blue-50 dark:bg-blue-950/20";
      default:
        return "border-border bg-card";
    }
  };

  const getBadgeVariant = () => {
    return entry.status === "success" ? "secondary" : "outline";
  };

  const messageText = getMessage(entry.message);

  // Get additional fields not in the standard schema
  const standardFields = new Set(['id', 'status', 'timestamp', 'message', 'payload', 'nodeId', 'nodeType', 'action', 'htmlSnippet']);
  const additionalFields = Object.entries(entry)
    .filter(([key]) => !standardFields.has(key as keyof PreviewTimelineEntry))
    .reduce((acc, [key, value]) => ({ ...acc, [key]: value }), {});
  const hasAdditionalFields = Object.keys(additionalFields).length > 0;

  return (
    <div className={`rounded-lg border p-3 shadow-sm transition-colors ${getStatusColor()}`}>
      <div className="flex items-center justify-between text-xs text-muted-foreground mb-2">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-mono">
            {new Date(entry.timestamp).toLocaleTimeString()}
          </span>
          {entry.nodeId && (
            <Badge variant="outline" className="text-[10px] font-mono bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300">
              Node: {entry.nodeId}
            </Badge>
          )}
          {entry.nodeType && (
            <Badge variant="outline" className="text-[10px] font-mono">
              {entry.nodeType}
            </Badge>
          )}
        </div>
        <Badge variant={getBadgeVariant()} className="uppercase text-[10px]">
          {entry.status}
        </Badge>
      </div>

      {entry.action && (
        <p className="text-xs text-muted-foreground mb-2">
          <span className="font-semibold">Action:</span> {entry.action}
        </p>
      )}

      {messageText && (
        <p className="text-sm mb-2">{messageText}</p>
      )}

      {entry.htmlSnippet && (
        <div
          className="text-sm prose prose-sm max-w-none dark:prose-invert mb-2"
          dangerouslySetInnerHTML={{ __html: entry.htmlSnippet }}
        />
      )}

      {entry.payload && (
        <details className="mt-2">
          <summary className="text-xs text-muted-foreground cursor-pointer hover:text-foreground">
            View payload
          </summary>
          <pre className="mt-2 max-h-48 overflow-auto rounded bg-muted p-2 text-xs">
            {JSON.stringify(entry.payload, null, 2)}
          </pre>
        </details>
      )}

      {hasAdditionalFields && (
        <details className="mt-2">
          <summary className="text-xs text-muted-foreground cursor-pointer hover:text-foreground">
            Additional fields ({Object.keys(additionalFields).length})
          </summary>
          <pre className="mt-2 max-h-48 overflow-auto rounded bg-muted p-2 text-xs">
            {JSON.stringify(additionalFields, null, 2)}
          </pre>
        </details>
      )}

      <details className="mt-2">
        <summary className="text-xs text-muted-foreground cursor-pointer hover:text-foreground">
          Raw data
        </summary>
        <pre className="mt-2 max-h-48 overflow-auto rounded bg-muted p-2 text-xs">
          {JSON.stringify(entry, null, 2)}
        </pre>
      </details>
    </div>
  );
}
