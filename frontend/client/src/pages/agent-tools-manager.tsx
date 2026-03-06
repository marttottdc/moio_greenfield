import { useState, useMemo, useEffect } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { ArrowLeft, Search, Wrench, RotateCcw, Save, Loader2 } from "lucide-react";
import { Link } from "wouter";
import { EmptyState } from "@/components/empty-state";
import { apiRequest, fetchJson, queryClient } from "@/lib/queryClient";
import { useToast } from "@/hooks/use-toast";
import { apiV1 } from "@/lib/api";

interface ToolDefault {
  name: string;
  display_name: string;
  description: string;
  category: string;
  type: string;
}

interface ParamProperty {
  type: string;
  title: string;
  default?: any;
  description?: string;
}

interface ParamSchema {
  type?: string;
  title?: string;
  required?: string[];
  properties?: Record<string, ParamProperty>;
}

interface AgentTool {
  tool_name: string;
  tool_type: string;
  enabled: boolean;
  custom_description: string;
  custom_display_name: string;
  default_params: ParamSchema;
  defaults: ToolDefault;
}

const AGENT_TOOLS_PATH = apiV1("/settings/agents/tools/");

// Helper to get display name with fallbacks
const getToolDisplayName = (tool: AgentTool) => {
  return tool.custom_display_name || tool.defaults?.display_name || tool.tool_name;
};

export default function AgentToolsManager() {
  const { toast } = useToast();
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedToolName, setSelectedToolName] = useState<string | null>(null);
  const [formData, setFormData] = useState<Partial<AgentTool> | null>(null);
  const [initialFormData, setInitialFormData] = useState<Partial<AgentTool> | null>(null);

  const toolsListQuery = useQuery({
    queryKey: [AGENT_TOOLS_PATH],
    queryFn: async () => {
      const result = await fetchJson<AgentTool[] | { results: AgentTool[] }>(AGENT_TOOLS_PATH);
      // Handle both raw array and paginated response formats
      return Array.isArray(result) ? result : (result.results || []);
    },
  });

  const toolDetailsQuery = useQuery({
    queryKey: [AGENT_TOOLS_PATH, selectedToolName],
    queryFn: async () => {
      if (!selectedToolName) return null;
      const result = await fetchJson<AgentTool>(`${AGENT_TOOLS_PATH}${selectedToolName}/`);
      return result;
    },
    enabled: !!selectedToolName,
  });

  const saveMutation = useMutation({
    mutationFn: async (data: Partial<AgentTool>) => {
      if (!selectedToolName) return;
      return await apiRequest("PATCH", `${AGENT_TOOLS_PATH}${selectedToolName}/`, {
        data: {
          enabled: data.enabled,
          custom_description: data.custom_description,
          custom_display_name: data.custom_display_name,
          default_params: data.default_params,
        },
      });
    },
    onSuccess: () => {
      toolsListQuery.refetch();
      toast({ title: "Tool settings saved successfully" });
    },
    onError: (error: any) => {
      toast({
        title: "Failed to save tool settings",
        description: error.message || "Please try again.",
        variant: "destructive",
      });
    },
  });

  const resetMutation = useMutation({
    mutationFn: async () => {
      if (!selectedToolName) return;
      return await apiRequest("PATCH", `${AGENT_TOOLS_PATH}${selectedToolName}/`, {
        data: {
          enabled: true,
          custom_description: "",
          custom_display_name: "",
          default_params: {},
        },
      });
    },
    onSuccess: () => {
      toolDetailsQuery.refetch();
      toolsListQuery.refetch();
      toast({ title: "Tool settings reset to defaults" });
      if (formData) {
        setFormData({ ...formData, custom_description: "", custom_display_name: "" });
        setInitialFormData({ ...formData, custom_description: "", custom_display_name: "" });
      }
    },
    onError: (error: any) => {
      toast({
        title: "Failed to reset tool settings",
        description: error.message || "Please try again.",
        variant: "destructive",
      });
    },
  });

  const tools = toolsListQuery.data ?? [];
  const selectedTool = toolDetailsQuery.data;

  const filteredTools = useMemo(() => {
    return tools
      .filter((tool) => tool.tool_type !== "builtin")
      .filter((tool) => {
        const displayName = getToolDisplayName(tool);
        return tool.tool_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
          displayName.toLowerCase().includes(searchQuery.toLowerCase());
      });
  }, [tools, searchQuery]);

  const handleSelectTool = (toolName: string) => {
    setSelectedToolName(toolName);
    setFormData(null);
    setInitialFormData(null);
  };

  const handleFormChange = (field: string, value: any) => {
    if (!formData) return;
    const updated = { ...formData, [field]: value };
    setFormData(updated);
  };

  const handleParamDefaultChange = (paramName: string, defaultValue: any) => {
    if (!formData?.default_params?.properties) return;
    const updated = {
      ...formData,
      default_params: {
        ...formData.default_params,
        properties: {
          ...formData.default_params.properties,
          [paramName]: {
            ...formData.default_params.properties[paramName],
            default: defaultValue,
          },
        },
      },
    };
    setFormData(updated);
  };

  const handleSave = () => {
    if (formData) {
      saveMutation.mutate(formData);
    }
  };

  const hasChanges = JSON.stringify(formData) !== JSON.stringify(initialFormData);

  // Initialize form when tool details load
  useEffect(() => {
    if (selectedTool && !formData) {
      const data = {
        enabled: selectedTool.enabled,
        custom_description: selectedTool.custom_description,
        custom_display_name: selectedTool.custom_display_name,
        default_params: selectedTool.default_params,
      };
      setFormData(data);
      setInitialFormData(data);
    }
  }, [selectedTool]);

  return (
    <div className="h-full flex flex-col">
      <div className="mb-6">
        <div className="flex items-center gap-3 mb-4">
          <Link href="/workflows?tab=components">
            <Button variant="ghost" size="icon" data-testid="button-back">
              <ArrowLeft className="h-5 w-5" />
            </Button>
          </Link>
          <h1 className="text-3xl font-bold">Agent Tools</h1>
        </div>
      </div>

      <div className="flex h-full w-full gap-4">
        {/* Left Sidebar - Tools List */}
        <div className="w-80 border-r border-border bg-background flex flex-col shrink-0">
          <div className="p-3 border-b border-border">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
              <Input
                placeholder="Search tools..."
                className="pl-10"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                data-testid="input-search"
              />
            </div>
          </div>

          <div className="flex-1 overflow-y-auto">
            {toolsListQuery.isLoading ? (
              <div className="p-4">
                <p className="text-sm text-muted-foreground">Loading tools...</p>
              </div>
            ) : toolsListQuery.isError ? (
              <div className="p-4">
                <EmptyState
                  title="Error loading tools"
                  description="Failed to load agent tools. Please try again later."
                />
              </div>
            ) : filteredTools.length === 0 ? (
              <div className="p-4">
                <EmptyState
                  title={searchQuery.trim() ? "No tools match" : "No tools found"}
                  description={searchQuery.trim() ? "Try a different search term." : "No agent tools available."}
                />
              </div>
            ) : (
              filteredTools.map((tool) => (
                <div
                  key={tool.tool_name}
                  onClick={() => handleSelectTool(tool.tool_name)}
                  className={`p-3 border-b border-border cursor-pointer transition-colors ${
                    selectedToolName === tool.tool_name ? "bg-accent" : "hover-elevate"
                  }`}
                  data-testid={`item-tool-${tool.tool_name}`}
                >
                  <div className="flex items-center justify-between gap-2 mb-2">
                    <h3 className="font-semibold text-sm truncate flex-1">
                      {getToolDisplayName(tool)}
                    </h3>
                    {tool.enabled ? (
                      <Badge variant="default" className="text-xs">Active</Badge>
                    ) : (
                      <Badge variant="secondary" className="text-xs">Inactive</Badge>
                    )}
                  </div>
                  <p className="text-xs text-muted-foreground">{tool.tool_name}</p>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Right Pane - Tool Detail */}
        <div className="flex-1 flex flex-col bg-muted/20 backdrop-blur-sm">
          {!selectedToolName ? (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center">
                <div className="inline-flex h-16 w-16 items-center justify-center rounded-full bg-muted mb-4">
                  <Wrench className="h-8 w-8 text-muted-foreground" />
                </div>
                <p className="text-sm text-muted-foreground">Select a tool to configure settings</p>
              </div>
            </div>
          ) : toolDetailsQuery.isLoading ? (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center">
                <Loader2 className="h-8 w-8 animate-spin mx-auto mb-2 text-muted-foreground" />
                <p className="text-sm text-muted-foreground">Loading tool details...</p>
              </div>
            </div>
          ) : selectedTool && formData ? (
            <>
              {/* Detail Header */}
              <div className="p-4 border-b border-border bg-background">
                <div className="flex items-start justify-between gap-3 mb-2">
                  <div className="flex-1">
                    <h2 className="font-semibold text-lg">{getToolDisplayName(selectedTool)}</h2>
                    <p className="text-sm text-muted-foreground font-mono">{selectedTool.tool_name}</p>
                  </div>
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => resetMutation.mutate()}
                      disabled={resetMutation.isPending || saveMutation.isPending}
                      data-testid="button-reset"
                    >
                      <RotateCcw className="h-4 w-4 mr-2" />
                      Reset
                    </Button>
                    <Button
                      size="sm"
                      onClick={handleSave}
                      disabled={!hasChanges || saveMutation.isPending}
                      data-testid="button-save"
                    >
                      <Save className="h-4 w-4 mr-2" />
                      Save
                    </Button>
                  </div>
                </div>
              </div>

              {/* Detail Content */}
              <div className="flex-1 overflow-y-auto p-4">
                <div className="space-y-6 max-w-2xl">
                  {/* Enabled Toggle */}
                  <div className="space-y-2">
                    <Label htmlFor="enabled" className="font-semibold">Status</Label>
                    <div className="flex items-center gap-3">
                      <Switch
                        id="enabled"
                        checked={formData.enabled ?? false}
                        onCheckedChange={(value) => handleFormChange("enabled", value)}
                        data-testid="switch-enabled"
                      />
                      <span className="text-sm text-muted-foreground">
                        {formData.enabled ? "Enabled" : "Disabled"}
                      </span>
                    </div>
                  </div>

                  {/* Display Name */}
                  <div className="space-y-2">
                    <Label htmlFor="custom_display_name">Display Name</Label>
                    <Input
                      id="custom_display_name"
                      placeholder={selectedTool.defaults?.display_name || selectedTool.tool_name}
                      value={formData.custom_display_name || ""}
                      onChange={(e) => handleFormChange("custom_display_name", e.target.value)}
                      data-testid="input-display-name"
                    />
                    {!formData.custom_display_name && selectedTool.defaults?.display_name && (
                      <p className="text-xs text-muted-foreground">
                        Default: {selectedTool.defaults.display_name}
                      </p>
                    )}
                  </div>

                  {/* Description */}
                  <div className="space-y-2">
                    <Label htmlFor="custom_description">Description</Label>
                    <Textarea
                      id="custom_description"
                      placeholder={selectedTool.defaults?.description || "Enter description..."}
                      value={formData.custom_description || ""}
                      onChange={(e) => handleFormChange("custom_description", e.target.value)}
                      className="min-h-24"
                      data-testid="textarea-description"
                    />
                    {!formData.custom_description && selectedTool.defaults?.description && (
                      <p className="text-xs text-muted-foreground">
                        Default: {selectedTool.defaults.description}
                      </p>
                    )}
                  </div>

                  {/* Default Parameters */}
                  {formData.default_params?.properties && Object.keys(formData.default_params.properties).length > 0 && (
                    <div className="space-y-3">
                      <h3 className="font-semibold text-sm">Parameter Defaults</h3>
                      <p className="text-xs text-muted-foreground">Set default values for each parameter</p>
                      <div className="space-y-4 bg-muted/30 p-4 rounded-md">
                        {Object.entries(formData.default_params.properties).map(([paramName, prop]) => {
                          const isRequired = formData.default_params?.required?.includes(paramName);
                          const paramType = prop.type;
                          const currentDefault = prop.default;
                          
                          return (
                            <div key={paramName} className="space-y-2 pb-3 border-b border-border last:border-0 last:pb-0">
                              <div className="flex items-center gap-2">
                                <Label htmlFor={`param-${paramName}`} className="text-sm font-medium">
                                  {prop.title || paramName}
                                </Label>
                                {isRequired && (
                                  <Badge variant="outline" className="text-xs">Required</Badge>
                                )}
                                <Badge variant="secondary" className="text-xs">{paramType}</Badge>
                              </div>
                              {prop.description && (
                                <p className="text-xs text-muted-foreground">{prop.description}</p>
                              )}
                              <div className="flex items-center gap-2">
                                <span className="text-xs text-muted-foreground w-16">Default:</span>
                                {paramType === "boolean" ? (
                                  <Switch
                                    id={`param-${paramName}`}
                                    checked={currentDefault === true}
                                    onCheckedChange={(v) => handleParamDefaultChange(paramName, v)}
                                    data-testid={`switch-param-${paramName}`}
                                  />
                                ) : paramType === "integer" || paramType === "number" ? (
                                  <Input
                                    id={`param-${paramName}`}
                                    type="number"
                                    className="flex-1"
                                    value={currentDefault !== undefined && currentDefault !== null ? currentDefault : ""}
                                    onChange={(e) => handleParamDefaultChange(paramName, paramType === "integer" ? parseInt(e.target.value) || 0 : parseFloat(e.target.value) || 0)}
                                    data-testid={`input-param-${paramName}`}
                                  />
                                ) : (
                                  <Input
                                    id={`param-${paramName}`}
                                    className="flex-1"
                                    value={currentDefault !== undefined && currentDefault !== null ? String(currentDefault) : ""}
                                    onChange={(e) => handleParamDefaultChange(paramName, e.target.value)}
                                    data-testid={`input-param-${paramName}`}
                                  />
                                )}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}

                  {/* Tool Info */}
                  <div className="pt-4 border-t border-border space-y-2">
                    <h3 className="font-semibold text-sm">Tool Info</h3>
                    <div className="grid grid-cols-2 gap-4 text-sm">
                      <div>
                        <span className="text-muted-foreground">Type:</span>
                        <p className="font-medium">{selectedTool.tool_type}</p>
                      </div>
                      <div>
                        <span className="text-muted-foreground">Name:</span>
                        <p className="font-medium font-mono text-xs">{selectedTool.tool_name}</p>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
}
