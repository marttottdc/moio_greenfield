import { useState, useMemo, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { ArrowLeft, Search, Zap, Loader2, Code } from "lucide-react";
import { Link } from "wouter";
import { EmptyState } from "@/components/empty-state";
import { fetchJson } from "@/lib/queryClient";
import { apiV1 } from "@/lib/api";
import { ScrollArea } from "@/components/ui/scroll-area";

interface EventPayloadSchema {
  type: string;
  required?: string[];
  properties?: Record<string, any>;
}

interface EventHints {
  use_cases?: string[];
  example_payload?: Record<string, any>;
  configuration_tips?: string;
  expression_examples?: Array<{ description: string; example: string }>;
}

interface FlowEvent {
  id: string;
  name: string;
  label: string;
  description: string;
  entity_type: string;
  category: string;
  payload_schema: EventPayloadSchema;
  hints?: EventHints;
  active: boolean;
  created_at: string;
  updated_at: string;
}

const EVENTS_PATH = apiV1("/flows/events");

export default function EventsBrowser() {
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);
  const [showPayload, setShowPayload] = useState(false);

  const eventsQuery = useQuery({
    queryKey: [EVENTS_PATH],
    queryFn: async () => {
      const result = await fetchJson<{ events: FlowEvent[] }>(EVENTS_PATH);
      return result.events || [];
    },
  });

  const events = eventsQuery.data ?? [];
  const selectedEvent = events.find((e) => e.id === selectedEventId);

  const filteredEvents = useMemo(() => {
    return events.filter(
      (event) =>
        event.label.toLowerCase().includes(searchQuery.toLowerCase()) ||
        event.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        event.description.toLowerCase().includes(searchQuery.toLowerCase()) ||
        event.category.toLowerCase().includes(searchQuery.toLowerCase())
    );
  }, [events, searchQuery]);

  const eventsByCategory = useMemo(() => {
    const grouped: Record<string, FlowEvent[]> = {};
    filteredEvents.forEach((event) => {
      if (!grouped[event.category]) {
        grouped[event.category] = [];
      }
      grouped[event.category].push(event);
    });
    return grouped;
  }, [filteredEvents]);

  // Auto-select first event
  useEffect(() => {
    if (!selectedEventId && filteredEvents.length > 0) {
      setSelectedEventId(filteredEvents[0].id);
    }
  }, [filteredEvents, selectedEventId]);

  return (
    <div className="h-full flex flex-col">
      <div className="mb-6">
        <div className="flex items-center gap-3 mb-4">
          <Link href="/workflows?tab=components">
            <Button variant="ghost" size="icon" data-testid="button-back">
              <ArrowLeft className="h-5 w-5" />
            </Button>
          </Link>
          <h1 className="text-3xl font-bold">Event Definitions</h1>
        </div>
        <p className="text-sm text-muted-foreground ml-12">
          Browse all available events you can trigger flows from
        </p>
      </div>

      <div className="flex h-full w-full gap-4">
        {/* Left Sidebar - Events List */}
        <div className="w-80 border-r border-border bg-background flex flex-col shrink-0">
          <div className="p-3 border-b border-border">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
              <Input
                placeholder="Search events..."
                className="pl-10"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                data-testid="input-search"
              />
            </div>
          </div>

          <ScrollArea className="flex-1">
            {eventsQuery.isLoading ? (
              <div className="p-4">
                <p className="text-sm text-muted-foreground">Loading events...</p>
              </div>
            ) : eventsQuery.isError ? (
              <div className="p-4">
                <EmptyState
                  title="Error loading events"
                  description="Failed to load flow events. Please try again later."
                />
              </div>
            ) : filteredEvents.length === 0 ? (
              <div className="p-4">
                <EmptyState
                  title={searchQuery.trim() ? "No events match" : "No events found"}
                  description={
                    searchQuery.trim()
                      ? "Try a different search term."
                      : "No events available."
                  }
                />
              </div>
            ) : (
              <div className="p-3 space-y-6">
                {Object.entries(eventsByCategory).map(([category, categoryEvents]) => (
                  <div key={category}>
                    <h3 className="text-xs font-semibold text-muted-foreground uppercase mb-2 px-2">
                      {category}
                    </h3>
                    <div className="space-y-1">
                      {categoryEvents.map((event) => (
                        <button
                          key={event.id}
                          onClick={() => setSelectedEventId(event.id)}
                          className={`w-full text-left p-3 rounded-md transition-colors ${
                            selectedEventId === event.id
                              ? "bg-accent text-accent-foreground"
                              : "hover-elevate text-foreground"
                          }`}
                          data-testid={`item-event-${event.id}`}
                        >
                          <div className="flex items-start justify-between gap-2 mb-1">
                            <div className="flex-1 min-w-0">
                              <p className="text-sm font-semibold truncate">{event.label}</p>
                              <p className="text-xs text-muted-foreground font-mono truncate">
                                {event.name}
                              </p>
                            </div>
                            {event.active && (
                              <div className="flex-shrink-0 w-2 h-2 rounded-full bg-green-500 mt-1" />
                            )}
                          </div>
                        </button>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </ScrollArea>
        </div>

        {/* Right Pane - Event Detail */}
        <div className="flex-1 flex flex-col bg-muted/20 backdrop-blur-sm">
          {!selectedEventId ? (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center">
                <div className="inline-flex h-16 w-16 items-center justify-center rounded-full bg-muted mb-4">
                  <Zap className="h-8 w-8 text-muted-foreground" />
                </div>
                <p className="text-sm text-muted-foreground">Select an event to view details</p>
              </div>
            </div>
          ) : eventsQuery.isLoading ? (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center">
                <Loader2 className="h-8 w-8 animate-spin mx-auto mb-2 text-muted-foreground" />
                <p className="text-sm text-muted-foreground">Loading...</p>
              </div>
            </div>
          ) : selectedEvent ? (
            <>
              {/* Detail Header */}
              <div className="p-6 border-b border-border bg-background">
                <div className="flex items-start justify-between gap-3 mb-4">
                  <div className="flex-1">
                    <div className="flex items-center gap-3 mb-2">
                      <h2 className="font-semibold text-2xl">{selectedEvent.label}</h2>
                      <Badge variant={selectedEvent.active ? "default" : "secondary"}>
                        {selectedEvent.active ? "Active" : "Inactive"}
                      </Badge>
                    </div>
                    <p className="text-sm text-muted-foreground font-mono mb-3">
                      {selectedEvent.name}
                    </p>
                    <p className="text-sm text-foreground">{selectedEvent.description}</p>
                  </div>
                </div>
              </div>

              {/* Detail Content */}
              <ScrollArea className="flex-1">
                <div className="p-6 space-y-6 max-w-3xl">
                  {/* Category & Entity Type */}
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <h3 className="text-xs font-semibold text-muted-foreground mb-1">
                        Category
                      </h3>
                      <Badge variant="outline" className="capitalize">
                        {selectedEvent.category}
                      </Badge>
                    </div>
                    <div>
                      <h3 className="text-xs font-semibold text-muted-foreground mb-1">
                        Entity Type
                      </h3>
                      <Badge variant="outline" className="capitalize">
                        {selectedEvent.entity_type}
                      </Badge>
                    </div>
                  </div>

                  {/* Use Cases */}
                  {selectedEvent.hints?.use_cases && selectedEvent.hints.use_cases.length > 0 && (
                    <div>
                      <h3 className="text-sm font-semibold mb-3">Use Cases</h3>
                      <ul className="space-y-2">
                        {selectedEvent.hints.use_cases.map((useCase, idx) => (
                          <li key={idx} className="text-sm text-foreground flex gap-2">
                            <span className="text-primary mt-1">•</span>
                            {useCase}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Configuration Tips */}
                  {selectedEvent.hints?.configuration_tips && (
                    <div>
                      <h3 className="text-sm font-semibold mb-3">Configuration Tips</h3>
                      <div className="bg-muted/50 border border-border p-3 rounded-md">
                        <p className="text-sm text-foreground">
                          {selectedEvent.hints.configuration_tips}
                        </p>
                      </div>
                    </div>
                  )}

                  {/* Payload Schema */}
                  <div>
                    <div className="flex items-center gap-2 mb-3">
                      <h3 className="text-sm font-semibold">Payload Schema</h3>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => setShowPayload(!showPayload)}
                        data-testid="button-toggle-payload"
                      >
                        <Code className="h-4 w-4" />
                      </Button>
                    </div>
                    {showPayload ? (
                      <div className="bg-muted p-4 rounded-md overflow-auto max-h-96">
                        <code className="text-xs font-mono text-muted-foreground whitespace-pre break-words">
                          {JSON.stringify(selectedEvent.payload_schema, null, 2)}
                        </code>
                      </div>
                    ) : (
                      <div className="space-y-3">
                        {selectedEvent.payload_schema.required && (
                          <div>
                            <p className="text-xs font-semibold text-muted-foreground mb-2">
                              Required Fields:
                            </p>
                            <div className="flex flex-wrap gap-2">
                              {selectedEvent.payload_schema.required.map((field) => (
                                <Badge key={field} variant="secondary" className="font-mono text-xs">
                                  {field}
                                </Badge>
                              ))}
                            </div>
                          </div>
                        )}
                        {selectedEvent.payload_schema.properties && (
                          <div>
                            <p className="text-xs font-semibold text-muted-foreground mb-2">
                              Properties:
                            </p>
                            <div className="space-y-2">
                              {Object.entries(selectedEvent.payload_schema.properties).map(
                                ([key, prop]: [string, any]) => (
                                  <div
                                    key={key}
                                    className="bg-muted/30 p-3 rounded-md border border-border/50"
                                  >
                                    <div className="flex items-center gap-2 mb-1">
                                      <code className="text-xs font-mono font-semibold">
                                        {key}
                                      </code>
                                      <Badge variant="outline" className="text-xs">
                                        {prop.type}
                                      </Badge>
                                    </div>
                                    {prop.description && (
                                      <p className="text-xs text-muted-foreground">
                                        {prop.description}
                                      </p>
                                    )}
                                    {prop.enum && (
                                      <div className="text-xs text-muted-foreground mt-1">
                                        Enum: {prop.enum.join(", ")}
                                      </div>
                                    )}
                                  </div>
                                )
                              )}
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </div>

                  {/* Example Payload */}
                  {selectedEvent.hints?.example_payload && (
                    <div>
                      <h3 className="text-sm font-semibold mb-3">Example Payload</h3>
                      <div className="bg-muted p-4 rounded-md overflow-auto max-h-64">
                        <code className="text-xs font-mono text-muted-foreground whitespace-pre break-words">
                          {JSON.stringify(selectedEvent.hints.example_payload, null, 2)}
                        </code>
                      </div>
                    </div>
                  )}

                  {/* Metadata */}
                  <div className="pt-4 border-t border-border">
                    <h3 className="text-sm font-semibold mb-3">Metadata</h3>
                    <div className="grid grid-cols-2 gap-4 text-sm">
                      <div>
                        <span className="text-muted-foreground">Created:</span>
                        <p className="font-medium">
                          {new Date(selectedEvent.created_at).toLocaleDateString()}
                        </p>
                      </div>
                      <div>
                        <span className="text-muted-foreground">Updated:</span>
                        <p className="font-medium">
                          {new Date(selectedEvent.updated_at).toLocaleDateString()}
                        </p>
                      </div>
                    </div>
                  </div>
                </div>
              </ScrollArea>
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
}
