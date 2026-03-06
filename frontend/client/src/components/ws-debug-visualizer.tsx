import { useState, useEffect, useRef } from "react";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ScrollArea } from "@/components/ui/scroll-area";
import { ChevronDown, X, Code2, ArrowUp, ArrowDown } from "lucide-react";
import { buildWebSocketUrl } from "@/hooks/useWebSocket";
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/resizable";

export interface EventLog {
  id: string;
  timestamp: number;
  eventType: string;
  payload: any;
  duration?: number;
  direction: "incoming" | "outgoing";
}

interface WSDebugVisualizerProps {
  eventType?: string;
  payload?: any;
  outgoingCommand?: {
    action: string;
    data: Record<string, unknown>;
    timestamp: number;
  } | null;
  subscriptionStatus?: {
    conversationId: string | null;
    subscribed: boolean;
    subscribedAt?: number;
  };
  isConnected?: boolean;
  persistedEvents?: EventLog[];
  onEventsChange?: (events: EventLog[]) => void;
  embeddedMode?: boolean;
}

const VALID_WS_ENDPOINTS = [
  { label: "WhatsApp", path: "/ws/whatsapp/" },
  { label: "Tickets", path: "/ws/tickets/" },
];

export function WSDebugVisualizer({
  eventType,
  payload,
  outgoingCommand,
  subscriptionStatus,
  isConnected = false,
  persistedEvents,
  onEventsChange,
  embeddedMode = false,
}: WSDebugVisualizerProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [internalEvents, setInternalEvents] = useState<EventLog[]>([]);
  const [expandedEvents, setExpandedEvents] = useState<Set<string>>(new Set());
  const [selectedEndpointPath, setSelectedEndpointPath] = useState(VALID_WS_ENDPOINTS[0].path);
  const scrollRef = useRef<HTMLDivElement>(null);
  const lastEventTimeRef = useRef<number>(0);
  
  // Use persisted events if provided, otherwise use internal state
  const events = persistedEvents ?? internalEvents;
  const setEvents = (updater: ((prev: EventLog[]) => EventLog[]) | EventLog[]) => {
    const newEvents = typeof updater === "function" ? updater(events) : updater;
    if (onEventsChange) {
      onEventsChange(newEvents);
    } else {
      setInternalEvents(newEvents);
    }
  };

  // Handle incoming events
  useEffect(() => {
    if (eventType && payload) {
      const now = Date.now();
      const duration = lastEventTimeRef.current ? now - lastEventTimeRef.current : 0;
      lastEventTimeRef.current = now;

      const newEvent: EventLog = {
        id: `${now}-${Math.random()}`,
        timestamp: now,
        eventType,
        payload,
        duration: duration > 0 ? duration : undefined,
        direction: "incoming",
      };

      setEvents([newEvent, ...events].slice(0, 50));

      setTimeout(() => {
        if (scrollRef.current) {
          scrollRef.current.scrollTop = 0;
        }
      }, 0);
    }
  }, [eventType, payload, setEvents]);

  // Handle outgoing commands
  useEffect(() => {
    if (outgoingCommand) {
      const now = outgoingCommand.timestamp;
      const duration = lastEventTimeRef.current ? now - lastEventTimeRef.current : 0;
      lastEventTimeRef.current = now;

      const newEvent: EventLog = {
        id: `out-${now}-${Math.random()}`,
        timestamp: now,
        eventType: outgoingCommand.action,
        payload: outgoingCommand.data,
        duration: duration > 0 ? duration : undefined,
        direction: "outgoing",
      };

      setEvents([newEvent, ...events].slice(0, 50));

      setTimeout(() => {
        if (scrollRef.current) {
          scrollRef.current.scrollTop = 0;
        }
      }, 0);
    }
  }, [outgoingCommand, setEvents]);

  const toggleExpanded = (id: string) => {
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

  const handleEndpointChange = (path: string) => {
    setSelectedEndpointPath(path);
  };

  const getSignedUrl = () => {
    return buildWebSocketUrl(selectedEndpointPath);
  };

  const EventsContent = (
    <div className="p-2 space-y-1 h-full">
      {events.length === 0 ? (
        <div className="text-xs text-muted-foreground p-2 text-center">
          Waiting for events...
        </div>
      ) : (
        events.map((event) => (
          <div
            key={event.id}
            className={`text-xs border rounded p-2 cursor-pointer transition-colors ${
              event.direction === "outgoing" 
                ? "bg-orange-50 dark:bg-orange-950/30 border-orange-200 dark:border-orange-800 hover:bg-orange-100 dark:hover:bg-orange-900/40" 
                : "bg-card hover:bg-muted/50"
            }`}
            onClick={() => toggleExpanded(event.id)}
            data-testid={`ws-event-${event.direction}-${event.eventType}`}
          >
            <div className="flex items-center gap-2 justify-between">
              <div className="flex items-center gap-2 flex-1">
                <ChevronDown
                  className={`w-3 h-3 transition-transform ${
                    expandedEvents.has(event.id) ? "rotate-180" : ""
                  }`}
                />
                {event.direction === "outgoing" ? (
                  <ArrowUp className="w-3 h-3 text-orange-600 dark:text-orange-400" />
                ) : (
                  <ArrowDown className="w-3 h-3 text-cyan-600 dark:text-cyan-400" />
                )}
                <code className={`font-mono font-semibold ${
                  event.direction === "outgoing" 
                    ? "text-orange-600 dark:text-orange-400" 
                    : "text-cyan-600 dark:text-cyan-400"
                }`}>
                  {event.eventType}
                </code>
              </div>
              <div className="flex items-center gap-2">
                {event.duration !== undefined && event.duration > 0 && (
                  <Badge variant="outline" className="text-xs">
                    +{event.duration}ms
                  </Badge>
                )}
                <span className="text-muted-foreground whitespace-nowrap text-xs">
                  {formatTime(event.timestamp)}
                </span>
              </div>
            </div>

            {expandedEvents.has(event.id) && (
              <div className="mt-2 p-2 bg-muted/50 rounded text-xs font-mono max-h-32 overflow-auto">
                <pre className="text-muted-foreground whitespace-pre-wrap break-words">
                  {JSON.stringify(event.payload, null, 2)}
                </pre>
              </div>
            )}
          </div>
        ))
      )}
    </div>
  );

  if (!embeddedMode && !isOpen) {
    return (
      <Button
        size="sm"
        variant="outline"
        onClick={() => setIsOpen(true)}
        className="fixed bottom-4 right-4 gap-2"
        data-testid="button-ws-debug-open"
      >
        <Code2 className="w-4 h-4" />
        WS Debug
        <Badge variant="secondary" className="ml-2">
          {events.length}
        </Badge>
      </Button>
    );
  }

  const debuggerCard = (
    <Card className={embeddedMode ? "h-full flex flex-col" : "fixed bottom-4 right-4 w-screen md:w-[900px] max-h-[80vh] shadow-lg flex flex-col z-50"}>
      {/* Header */}
      <div className="flex items-center justify-between p-3 border-b">
        <div className="flex items-center gap-2">
          <Code2 className="w-4 h-4" />
          <span className="font-semibold text-sm">WebSocket Debug</span>
          <Badge
            variant={isConnected ? "default" : "destructive"}
            className="text-xs"
          >
            {isConnected ? "Connected" : "Disconnected"}
          </Badge>
        </div>
        {!embeddedMode && (
          <Button
            size="icon"
            variant="ghost"
            onClick={() => setIsOpen(false)}
            data-testid="button-ws-debug-close"
          >
            <X className="w-4 h-4" />
          </Button>
        )}
      </div>

      {/* URL Selector Section */}
      <div className="px-3 py-3 border-b bg-muted/30 space-y-2">
        <div className="text-xs font-semibold text-muted-foreground">WebSocket Endpoint</div>
        <Select value={selectedEndpointPath} onValueChange={handleEndpointChange}>
          <SelectTrigger className="h-8 text-xs" data-testid="select-ws-endpoint">
            <SelectValue placeholder="Select endpoint..." />
          </SelectTrigger>
          <SelectContent>
            {VALID_WS_ENDPOINTS.map((endpoint) => (
              <SelectItem key={endpoint.path} value={endpoint.path}>
                {endpoint.label} — {endpoint.path}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <div className="text-xs text-muted-foreground font-mono break-all p-2 bg-background rounded border">
          {getSignedUrl().replace(/token=[^&]+/, "token=***")}
        </div>
      </div>

      {/* Subscription Status */}
      {subscriptionStatus && (
        <div className="px-3 py-2 bg-muted/50 text-xs border-b">
          <div className="flex items-center gap-1">
            <span>Conversation:</span>
            <code className="font-mono bg-background px-1 rounded">{subscriptionStatus.conversationId || "None"}</code>
          </div>
          <div className="flex items-center gap-1 mt-1">
            <span>Status:</span>
            <Badge
              variant={subscriptionStatus.subscribed ? "default" : "secondary"}
              className="text-xs"
            >
              {subscriptionStatus.subscribed ? "Subscribed" : "Unsubscribed"}
            </Badge>
          </div>
          {subscriptionStatus.subscribedAt && (
            <div className="text-xs text-muted-foreground mt-1">
              Since: {formatTime(subscriptionStatus.subscribedAt)}
            </div>
          )}
        </div>
      )}

      {/* Events List with Scroll */}
      {embeddedMode ? (
        <ScrollArea className="flex-1 overflow-hidden">
          {EventsContent}
        </ScrollArea>
      ) : (
        <div className="flex-1 overflow-y-auto">
          {EventsContent}
        </div>
      )}

      {/* Footer */}
      <div className="px-3 py-2 border-t bg-muted/30 text-xs text-muted-foreground">
        Total: {events.length} events | Last: {events.length > 0 ? formatTime(events[0].timestamp) : "none"}
      </div>
    </Card>
  );

  return debuggerCard;
}
