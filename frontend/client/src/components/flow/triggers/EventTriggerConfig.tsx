import { useEffect, useMemo, useRef, useState } from "react";
import { Zap, AlertCircle, AlertTriangle, Plus, X, Filter, ChevronDown, ChevronUp, Lightbulb, RefreshCw } from "lucide-react";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { useFlowEventData } from "@/components/flow/BuilderDataContext";
import { useEventDetails } from "@/hooks/useBuilderData";
import type { EventTriggerConfig } from "./types";

interface EventTriggerConfigPanelProps {
  config: EventTriggerConfig;
  onChange: (config: EventTriggerConfig) => void;
}

export function EventTriggerConfigPanel({ config, onChange }: EventTriggerConfigPanelProps) {
  const { events, entityTypes, isLoading, error } = useFlowEventData();
  const [entityTypeFilter, setEntityTypeFilter] = useState<string>("all");
  const [showConditions, setShowConditions] = useState(
    Object.keys(config.conditions || {}).length > 0
  );
  const [newConditionKey, setNewConditionKey] = useState("");
  const [newConditionValue, setNewConditionValue] = useState("");
  const schemaHydratedRef = useRef(false);
  
  // Find selected event from list
  const selectedEventFromList = events.find((e) => e.name === config.event_name);
  const eventId = config.event_id || selectedEventFromList?.id;
  
  // Fetch detailed event information when an event is selected
  const eventDetailsQuery = useEventDetails(eventId);
  const eventDetails = eventDetailsQuery.data;
  const isFetchingDetails = eventDetailsQuery.isFetching;
  const eventDetailsError = eventDetailsQuery.error;
  
  // Use detailed event data if available, otherwise fall back to list data
  const selectedEvent = useMemo(() => {
    if (!config.event_name) return undefined;
    
    // Prioritize detailed data from individual endpoint
    if (eventDetails) {
      return eventDetails;
    }
    
    // Fallback to list data only if details query hasn't run yet or is loading
    // If there's an error, we don't use list data (per plan requirement)
    if (eventDetailsError) {
      return undefined; // Don't use list data when there's an error
    }
    
    return selectedEventFromList;
  }, [config.event_name, selectedEventFromList, eventDetails, eventDetailsError]);
  
  // Auto-hydrate schema from pre-loaded events when loading a flow with an event but no schema
  // IMPORTANT: Store ONLY payload_schema in event_schema (not the full event definition)
  useEffect(() => {
    if (schemaHydratedRef.current) return;
    if (isLoading || !events.length) return;
    if (!config.event_name || config.event_schema) return;
    
    const event = events.find((e) => e.name === config.event_name);
    if (!event) return;
    
    // Extract ONLY payload_schema - this defines what the event sends as input.body
    const payloadSchema = event.payload_schema || event.hints?.example_payload;
    if (payloadSchema) {
      schemaHydratedRef.current = true;
      onChange({
        ...config,
        event_id: event.id,
        event_schema: payloadSchema, // Only payload_schema, not full event definition
      });
    }
  }, [isLoading, events, config, onChange]);
  
  // Update config with payload_schema when event details are fetched
  // IMPORTANT: event_schema must contain ONLY payload_schema (the schema of what the event sends)
  // NOT the full event definition (id, name, label, etc.)
  useEffect(() => {
    if (eventDetails && config.event_id === eventDetails.id) {
      // Extract ONLY payload_schema - this is what the event sends as input.body
      // payload_schema defines the structure of the payload that will be available as input.body
      const payloadSchema = eventDetails.payload_schema || eventDetails.hints?.example_payload || null;
      
      // Only store payload_schema, not the full event definition
      if (payloadSchema) {
        const currentSchema = config.event_schema;
        // Deep comparison to avoid unnecessary updates
        const schemasEqual = JSON.stringify(currentSchema) === JSON.stringify(payloadSchema);
        
        if (!schemasEqual) {
          console.log(`[EventTrigger] Updating payload_schema for ${eventDetails.name}:`, {
            eventId: eventDetails.id,
            payloadSchema: payloadSchema,
          });
          
          // Store ONLY payload_schema in event_schema
          onChange({
            ...config,
            event_schema: payloadSchema, // Only payload_schema, not full event definition
          });
        }
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [eventDetails?.payload_schema, eventDetails?.hints?.example_payload, eventDetails?.id, config.event_id]);

  const filteredEvents = useMemo(() => {
    return events.filter((event) => {
      if (!event.active) return false;
      if (entityTypeFilter !== "all" && event.entity_type !== entityTypeFilter) return false;
      return true;
    });
  }, [events, entityTypeFilter]);

  const eventsByCategory = useMemo(() => {
    const grouped: Record<string, typeof filteredEvents> = {};
    filteredEvents.forEach((event) => {
      const category = event.category || "Other";
      if (!grouped[category]) {
        grouped[category] = [];
      }
      grouped[category].push(event);
    });
    return grouped;
  }, [filteredEvents]);

  const hasStaleSelection = !isLoading && config.event_name && events.length > 0 && !selectedEventFromList;

  const handleEventSelect = (eventName: string) => {
    const event = events.find((e) => e.name === eventName);
    if (!event) return;
    
    // Set event_name and event_id first - this will trigger useEventDetails to fetch full details
    // Clear event_schema to force reload from fresh details endpoint
    onChange({
      ...config,
      event_name: eventName,
      event_id: event.id,
      event_schema: undefined, // Clear to force reload from fresh details
    });
    
    // The useEventDetails hook will automatically refetch when eventId changes
    // This ensures we always get fresh data when an event is selected
  };
  
  const handleRefreshSchema = () => {
    if (eventId) {
      // Force refetch to get fresh event details from endpoint
      eventDetailsQuery.refetch();
    }
  };

  const handleAddCondition = () => {
    if (!newConditionKey.trim()) return;
    onChange({
      ...config,
      conditions: {
        ...config.conditions,
        [newConditionKey.trim()]: newConditionValue,
      },
    });
    setNewConditionKey("");
    setNewConditionValue("");
  };

  const handleRemoveCondition = (key: string) => {
    const newConditions = { ...config.conditions };
    delete newConditions[key];
    onChange({
      ...config,
      conditions: newConditions,
    });
  };

  const handleConditionValueChange = (key: string, value: string) => {
    onChange({
      ...config,
      conditions: {
        ...config.conditions,
        [key]: value,
      },
    });
  };

  const conditionEntries = Object.entries(config.conditions || {});

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2 pb-2">
        <div className="h-8 w-8 rounded-lg bg-gradient-to-br from-blue-500 to-cyan-600 flex items-center justify-center">
          <Zap className="h-4 w-4 text-white" />
        </div>
        <div>
          <h3 className="font-semibold text-sm">Event Trigger</h3>
          <p className="text-xs text-muted-foreground">React to system events</p>
        </div>
      </div>

      <Separator />

      {error && (
        <div className="p-3 rounded-lg border border-destructive/50 bg-destructive/5 flex gap-2">
          <AlertCircle className="h-4 w-4 text-destructive flex-shrink-0 mt-0.5" />
          <div className="text-xs text-destructive">{error}</div>
        </div>
      )}
      
      {hasStaleSelection && (
        <div className="p-3 rounded-lg border border-amber-500/50 bg-amber-500/5 flex gap-2">
          <AlertTriangle className="h-4 w-4 text-amber-500 flex-shrink-0 mt-0.5" />
          <div className="text-xs text-amber-700 dark:text-amber-400">
            Previously selected event "<span className="font-medium">{config.event_name}</span>" is no longer available. Please select a new event.
          </div>
        </div>
      )}

      <div className="space-y-4">
        {entityTypes.length > 0 && (
          <div className="space-y-1">
            <Label className="text-xs text-muted-foreground">Entity</Label>
            <Select value={entityTypeFilter} onValueChange={setEntityTypeFilter}>
              <SelectTrigger className="h-8 text-xs" data-testid="select-entity-filter">
                <SelectValue placeholder="All types" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All types</SelectItem>
                {entityTypes.map((type) => (
                  <SelectItem key={type} value={type}>
                    {type.charAt(0).toUpperCase() + type.slice(1)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}

        <div className="space-y-2">
          <Label className="text-xs font-medium flex items-center gap-1.5">
            <Zap className="h-3 w-3 text-amber-500" />
            Event Type
          </Label>
          {!isLoading && filteredEvents.length === 0 && !error ? (
            <div className="p-4 rounded-lg border border-dashed border-muted-foreground/30 bg-muted/20 text-center">
              <Zap className="h-6 w-6 text-muted-foreground/50 mx-auto mb-2" />
              <p className="text-xs text-muted-foreground">
                {events.length === 0 ? "No event types configured" : "No events match your filters"}
              </p>
              {events.length > 0 && (
                <Button 
                  variant="ghost" 
                  size="sm" 
                  className="mt-2 h-7 text-xs"
                  onClick={() => { setEntityTypeFilter("all"); }}
                >
                  Clear filters
                </Button>
              )}
            </div>
          ) : (
            <Select value={config.event_name} onValueChange={handleEventSelect} disabled={isLoading}>
              <SelectTrigger data-testid="select-event-type">
                <SelectValue placeholder={isLoading ? "Loading events..." : "Select an event..."} />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(eventsByCategory).map(([category, categoryEvents]) => (
                  <div key={category}>
                    <div className="px-2 py-1.5 text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                      {category}
                    </div>
                    {categoryEvents.map((event) => (
                      <SelectItem key={event.name} value={event.name}>
                        <div className="flex flex-col gap-0.5">
                          <div className="flex items-center gap-2">
                            <span>{event.label}</span>
                            <Badge variant="outline" className="text-[10px] h-4 px-1">
                              {event.entity_type}
                            </Badge>
                          </div>
                          {event.description && (
                            <span className="text-xs text-muted-foreground">{event.description}</span>
                          )}
                        </div>
                      </SelectItem>
                    ))}
                  </div>
                ))}
              </SelectContent>
            </Select>
          )}
        </div>

        {selectedEvent && (
          <div className="p-3 rounded-lg bg-muted/30 border text-xs space-y-1">
            <div className="flex items-center justify-between">
              <div className="font-medium">{selectedEvent.label}</div>
              {eventId && (
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-6 w-6"
                  onClick={handleRefreshSchema}
                  disabled={isFetchingDetails}
                  title="Refresh event schema"
                  data-testid="button-refresh-event-schema"
                >
                  <RefreshCw className={`h-3 w-3 ${isFetchingDetails ? "animate-spin" : ""}`} />
                </Button>
              )}
            </div>
            {selectedEvent.description && (
              <div className="text-muted-foreground">{selectedEvent.description}</div>
            )}
            {eventDetailsError && (
              <div className="text-xs text-destructive mt-1">
                Failed to load event schema. Using schema from list.
              </div>
            )}
            <div className="flex gap-2 mt-2">
              <Badge variant="secondary" className="text-[10px]">{selectedEvent.category}</Badge>
              <Badge variant="outline" className="text-[10px]">{selectedEvent.entity_type}</Badge>
              {config.event_schema && (
                <Badge variant="outline" className="text-[10px] bg-green-100 dark:bg-green-900 border-green-300 dark:border-green-700 text-green-800 dark:text-green-200">
                  Schema loaded
                </Badge>
              )}
            </div>
          </div>
        )}

        {selectedEvent?.hints && (
          ((selectedEvent.hints.use_cases && selectedEvent.hints.use_cases.length > 0) || 
           selectedEvent.hints.configuration_tips || 
           selectedEvent.hints.example_payload) && (
            <div className="space-y-3 p-3 rounded-lg bg-blue-50 dark:bg-blue-950/30 border border-blue-200 dark:border-blue-800">
              {selectedEvent.hints.use_cases && selectedEvent.hints.use_cases.length > 0 && (
                <div className="space-y-1">
                  <div className="flex items-center gap-1.5">
                    <Lightbulb className="h-3 w-3 text-blue-600 dark:text-blue-400" />
                    <span className="text-xs font-medium text-blue-900 dark:text-blue-300">Use Cases</span>
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {selectedEvent.hints.use_cases.map((useCase, idx) => (
                      <Badge key={idx} variant="outline" className="text-[10px] bg-blue-100 dark:bg-blue-900 border-blue-300 dark:border-blue-700">
                        {useCase}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}
              {selectedEvent.hints.configuration_tips && (
                <div className="space-y-1">
                  <div className="text-xs font-medium text-blue-900 dark:text-blue-300">Configuration Tips</div>
                  <div className="text-xs text-blue-800 dark:text-blue-300 leading-relaxed">{selectedEvent.hints.configuration_tips}</div>
                </div>
              )}
              {selectedEvent.hints.example_payload && (
                <Collapsible>
                  <CollapsibleTrigger asChild>
                    <Button variant="ghost" size="sm" className="text-xs h-6 px-2 -ml-2 text-blue-600 dark:text-blue-400">
                      View example payload
                    </Button>
                  </CollapsibleTrigger>
                  <CollapsibleContent>
                    <pre className="text-xs bg-white dark:bg-slate-950 p-2 rounded border border-blue-300 dark:border-blue-700 overflow-x-auto max-h-[200px] overflow-y-auto mt-2">
                      {JSON.stringify(selectedEvent.hints.example_payload, null, 2)}
                    </pre>
                  </CollapsibleContent>
                </Collapsible>
              )}
            </div>
          )
        )}

        <Separator />

        <Collapsible open={showConditions} onOpenChange={setShowConditions}>
          <CollapsibleTrigger asChild>
            <Button variant="ghost" size="sm" className="w-full justify-between h-8 text-xs">
              <span className="flex items-center gap-2">
                <Filter className="h-3 w-3" />
                Conditions
                {conditionEntries.length > 0 && (
                  <Badge variant="secondary" className="h-4 text-[10px]">
                    {conditionEntries.length}
                  </Badge>
                )}
              </span>
              {showConditions ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
            </Button>
          </CollapsibleTrigger>
          <CollapsibleContent className="space-y-3 pt-3">
            <p className="text-xs text-muted-foreground">
              Filter which events trigger this flow by matching payload fields.
            </p>

            {conditionEntries.map(([key, value]) => (
              <div key={key} className="flex items-center gap-2">
                <Input
                  value={key}
                  disabled
                  className="flex-1 h-8 text-xs bg-muted/50"
                  data-testid={`input-condition-key-${key}`}
                />
                <span className="text-muted-foreground">=</span>
                <Input
                  value={value}
                  onChange={(e) => handleConditionValueChange(key, e.target.value)}
                  className="flex-1 h-8 text-xs"
                  placeholder="Value"
                  data-testid={`input-condition-value-${key}`}
                />
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8 text-muted-foreground hover:text-destructive"
                  onClick={() => handleRemoveCondition(key)}
                  data-testid={`button-remove-condition-${key}`}
                >
                  <X className="h-3 w-3" />
                </Button>
              </div>
            ))}

            <div className="flex items-center gap-2">
              <Input
                value={newConditionKey}
                onChange={(e) => setNewConditionKey(e.target.value)}
                className="flex-1 h-8 text-xs"
                placeholder="Field name"
                data-testid="input-new-condition-key"
              />
              <span className="text-muted-foreground">=</span>
              <Input
                value={newConditionValue}
                onChange={(e) => setNewConditionValue(e.target.value)}
                className="flex-1 h-8 text-xs"
                placeholder="Expected value"
                data-testid="input-new-condition-value"
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    handleAddCondition();
                  }
                }}
              />
              <Button
                variant="outline"
                size="icon"
                className="h-8 w-8"
                onClick={handleAddCondition}
                disabled={!newConditionKey.trim()}
                data-testid="button-add-condition"
              >
                <Plus className="h-3 w-3" />
              </Button>
            </div>

            {selectedEvent?.payload_schema && (
              <Collapsible>
                <CollapsibleTrigger asChild>
                  <Button variant="ghost" size="sm" className="text-xs h-6 px-2">
                    View payload schema
                  </Button>
                </CollapsibleTrigger>
                <CollapsibleContent>
                  <pre className="text-xs bg-muted/50 p-2 rounded border overflow-x-auto max-h-[200px] overflow-y-auto mt-2">
                    {JSON.stringify(selectedEvent.payload_schema, null, 2)}
                  </pre>
                </CollapsibleContent>
              </Collapsible>
            )}
          </CollapsibleContent>
        </Collapsible>
      </div>
    </div>
  );
}

export function getEventTriggerSummary(config: EventTriggerConfig): string {
  if (!config.event_name) return "No event selected";
  const conditionCount = Object.keys(config.conditions || {}).length;
  if (conditionCount > 0) {
    return `On ${config.event_name} (${conditionCount} condition${conditionCount > 1 ? "s" : ""})`;
  }
  return `On ${config.event_name}`;
}
