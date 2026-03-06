import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { ArrowLeft, Search, Plug, Plus, Trash2, Edit2, ExternalLink, Shield, Check } from "lucide-react";
import { Link } from "wouter";
import { fetchJson, apiRequest, queryClient } from "@/lib/queryClient";
import { useToast } from "@/hooks/use-toast";
import { apiV1 } from "@/lib/api";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Checkbox } from "@/components/ui/checkbox";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

interface MCPConnection {
  id: string;
  name: string;
  server_label: string;
  description?: string;
  connection_type: "connector" | "url";
  connector_id?: string;
  server_url?: string;
  authorization?: string;
  allowed_tools: string[];
  require_approval: "always" | "never" | "on_first_use";
  is_active: boolean;
  created_at?: string;
  updated_at?: string;
}

interface MCPConnectionFormData {
  name: string;
  server_label: string;
  description: string;
  connection_type: "connector" | "url";
  connector_id: string;
  server_url: string;
  authorization: string;
  allowed_tools: string[];
  require_approval: "always" | "never" | "on_first_use";
  is_active: boolean;
}

interface AvailableMCPConnector {
  id: string;
  name: string;
  description: string;
  available_tools: string[];
}

const MCP_CONNECTIONS_PATH = apiV1("/settings/mcp_connections/");
const MCP_CONNECTORS_PATH = apiV1("/resources/mcp_connectors/");

const APPROVAL_OPTIONS = [
  { value: "always", label: "Always require approval" },
  { value: "never", label: "Never require approval" },
  { value: "on_first_use", label: "Require on first use" },
];

const COMMON_CONNECTORS: AvailableMCPConnector[] = [
  { 
    id: "connector_outlookemail", 
    name: "Outlook Email", 
    description: "Microsoft Outlook email integration",
    available_tools: ["fetch_message", "fetch_messages_batch", "get_profile", "get_recent_emails", "list_messages", "search_messages", "send_email", "reply_to_email"]
  },
  { 
    id: "connector_gmail", 
    name: "Gmail", 
    description: "Google Gmail integration",
    available_tools: ["list_emails", "get_email", "send_email", "search_emails", "get_labels", "create_draft"]
  },
  { 
    id: "connector_slack", 
    name: "Slack", 
    description: "Slack workspace integration",
    available_tools: ["list_channels", "send_message", "get_messages", "search_messages", "get_user_info"]
  },
  { 
    id: "connector_notion", 
    name: "Notion", 
    description: "Notion workspace integration",
    available_tools: ["search_pages", "get_page", "create_page", "update_page", "get_database", "query_database"]
  },
  { 
    id: "connector_github", 
    name: "GitHub", 
    description: "GitHub repository integration",
    available_tools: ["list_repos", "get_repo", "list_issues", "create_issue", "get_pull_requests", "search_code"]
  },
];

const DEFAULT_FORM_DATA: MCPConnectionFormData = {
  name: "",
  server_label: "",
  description: "",
  connection_type: "connector",
  connector_id: "",
  server_url: "",
  authorization: "",
  allowed_tools: [],
  require_approval: "always",
  is_active: true,
};

export default function MCPConnectionsManager() {
  const { toast } = useToast();
  const [searchQuery, setSearchQuery] = useState("");
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [editingConnection, setEditingConnection] = useState<MCPConnection | null>(null);
  const [formData, setFormData] = useState<MCPConnectionFormData>(DEFAULT_FORM_DATA);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [connectionToDelete, setConnectionToDelete] = useState<MCPConnection | null>(null);
  const [showAuthToken, setShowAuthToken] = useState(false);

  const connectionsQuery = useQuery<{ connections: MCPConnection[] }>({
    queryKey: [MCP_CONNECTIONS_PATH],
    queryFn: () => fetchJson<{ connections: MCPConnection[] }>(MCP_CONNECTIONS_PATH),
  });

  const connectorsQuery = useQuery<{ connectors: AvailableMCPConnector[] }>({
    queryKey: [MCP_CONNECTORS_PATH],
    queryFn: () => fetchJson<{ connectors: AvailableMCPConnector[] }>(MCP_CONNECTORS_PATH),
  });

  const connections = connectionsQuery.data?.connections ?? [];
  const availableConnectors = connectorsQuery.data?.connectors ?? COMMON_CONNECTORS;

  const filteredConnections = connections.filter((conn) =>
    conn.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    conn.server_label.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const selectedConnector = availableConnectors.find(
    (c) => c.id === formData.connector_id
  );

  const createMutation = useMutation({
    mutationFn: (data: MCPConnectionFormData) =>
      apiRequest("POST", MCP_CONNECTIONS_PATH, { data }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [MCP_CONNECTIONS_PATH] });
      setIsDialogOpen(false);
      setFormData(DEFAULT_FORM_DATA);
      toast({ title: "MCP connection created successfully" });
    },
    onError: (error: any) => {
      toast({
        title: "Failed to create MCP connection",
        description: error.message || "Please try again.",
        variant: "destructive",
      });
    },
  });

  const updateMutation = useMutation({
    mutationFn: (data: MCPConnectionFormData) =>
      apiRequest("PATCH", `${MCP_CONNECTIONS_PATH}${editingConnection!.id}/`, { data }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [MCP_CONNECTIONS_PATH] });
      setIsDialogOpen(false);
      setEditingConnection(null);
      setFormData(DEFAULT_FORM_DATA);
      toast({ title: "MCP connection updated successfully" });
    },
    onError: (error: any) => {
      toast({
        title: "Failed to update MCP connection",
        description: error.message || "Please try again.",
        variant: "destructive",
      });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) =>
      apiRequest("DELETE", `${MCP_CONNECTIONS_PATH}${id}/`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [MCP_CONNECTIONS_PATH] });
      setDeleteDialogOpen(false);
      setConnectionToDelete(null);
      toast({ title: "MCP connection deleted successfully" });
    },
    onError: (error: any) => {
      toast({
        title: "Failed to delete MCP connection",
        description: error.message || "Please try again.",
        variant: "destructive",
      });
    },
  });

  const handleCreate = () => {
    setEditingConnection(null);
    setFormData(DEFAULT_FORM_DATA);
    setShowAuthToken(false);
    setIsDialogOpen(true);
  };

  const handleEdit = (connection: MCPConnection) => {
    setEditingConnection(connection);
    setFormData({
      name: connection.name,
      server_label: connection.server_label,
      description: connection.description || "",
      connection_type: connection.connection_type,
      connector_id: connection.connector_id || "",
      server_url: connection.server_url || "",
      authorization: connection.authorization || "",
      allowed_tools: connection.allowed_tools || [],
      require_approval: connection.require_approval,
      is_active: connection.is_active,
    });
    setShowAuthToken(false);
    setIsDialogOpen(true);
  };

  const handleDelete = (connection: MCPConnection) => {
    setConnectionToDelete(connection);
    setDeleteDialogOpen(true);
  };

  const handleSubmit = () => {
    if (editingConnection) {
      updateMutation.mutate(formData);
    } else {
      createMutation.mutate(formData);
    }
  };

  const toggleTool = (tool: string) => {
    setFormData((prev) => ({
      ...prev,
      allowed_tools: prev.allowed_tools.includes(tool)
        ? prev.allowed_tools.filter((t) => t !== tool)
        : [...prev.allowed_tools, tool],
    }));
  };

  const selectAllTools = () => {
    if (selectedConnector) {
      setFormData((prev) => ({
        ...prev,
        allowed_tools: [...selectedConnector.available_tools],
      }));
    }
  };

  const clearAllTools = () => {
    setFormData((prev) => ({
      ...prev,
      allowed_tools: [],
    }));
  };

  const isFormValid = formData.name.trim() !== "" && 
    formData.server_label.trim() !== "" &&
    (formData.connection_type === "connector" ? formData.connector_id !== "" : formData.server_url !== "");

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Button variant="ghost" size="icon" asChild>
          <Link href="/workflows?tab=components" data-testid="button-back-components">
            <ArrowLeft className="h-4 w-4" />
          </Link>
        </Button>
        <div className="flex-1">
          <h1 className="text-xl font-semibold" data-testid="text-page-title">MCP Connections</h1>
          <p className="text-sm text-muted-foreground">
            Manage external service connectors for AI agents
          </p>
        </div>
        <Button onClick={handleCreate} data-testid="button-create-mcp">
          <Plus className="h-4 w-4 mr-2" />
          New Connection
        </Button>
      </div>

      <div className="flex items-center gap-2">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search connections..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9"
            data-testid="input-search-mcp"
          />
        </div>
      </div>

      {connectionsQuery.isLoading ? (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-40 bg-muted animate-pulse rounded-lg" />
          ))}
        </div>
      ) : filteredConnections.length === 0 ? (
        <div className="flex flex-col items-center justify-center text-center border border-dashed border-muted-foreground/40 rounded-lg p-8 bg-white/60 dark:bg-slate-900/60">
          <Plug className="h-10 w-10 text-muted-foreground mb-4" />
          <h3 className="text-lg font-semibold text-foreground">
            {searchQuery ? "No connections found" : "No MCP connections yet"}
          </h3>
          <p className="mt-2 text-sm text-muted-foreground max-w-sm">
            {searchQuery
              ? "Try adjusting your search query"
              : "Create your first MCP connection to enable AI agents to interact with external services"}
          </p>
          {!searchQuery && (
            <Button onClick={handleCreate} className="mt-4" data-testid="button-create-first-mcp">
              <Plus className="h-4 w-4 mr-2" />
              Create Connection
            </Button>
          )}
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {filteredConnections.map((connection) => (
            <div
              key={connection.id}
              className="group relative p-4 border rounded-lg bg-card hover-elevate"
              data-testid={`card-mcp-${connection.id}`}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-lg bg-cyan-50 flex items-center justify-center shrink-0">
                    <Plug className="h-5 w-5 text-cyan-600" />
                  </div>
                  <div className="min-w-0">
                    <h3 className="font-medium truncate" data-testid={`text-mcp-name-${connection.id}`}>
                      {connection.name}
                    </h3>
                    <p className="text-xs text-muted-foreground truncate">
                      {connection.server_label}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-1">
                  <Badge variant={connection.is_active ? "default" : "secondary"}>
                    {connection.is_active ? "Active" : "Inactive"}
                  </Badge>
                </div>
              </div>

              {connection.description && (
                <p className="mt-3 text-sm text-muted-foreground line-clamp-2">
                  {connection.description}
                </p>
              )}

              <div className="mt-3 flex items-center gap-2 flex-wrap">
                <Badge variant="outline" className="text-xs">
                  <Shield className="h-3 w-3 mr-1" />
                  {connection.require_approval === "always" ? "Always approve" : 
                   connection.require_approval === "never" ? "Auto-approve" : "First use"}
                </Badge>
                <Badge variant="outline" className="text-xs">
                  {connection.allowed_tools.length} tools
                </Badge>
              </div>

              <div className="mt-4 flex items-center justify-end gap-2">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => handleEdit(connection)}
                  data-testid={`button-edit-mcp-${connection.id}`}
                >
                  <Edit2 className="h-4 w-4" />
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => handleDelete(connection)}
                  className="text-destructive hover:text-destructive"
                  data-testid={`button-delete-mcp-${connection.id}`}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}

      <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-hidden flex flex-col">
          <DialogHeader>
            <DialogTitle>
              {editingConnection ? "Edit MCP Connection" : "Create MCP Connection"}
            </DialogTitle>
            <DialogDescription>
              Configure an external service connector for your AI agents
            </DialogDescription>
          </DialogHeader>

          <ScrollArea className="flex-1 pr-4">
            <div className="space-y-6 py-4">
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="mcp-name">Connection Name *</Label>
                  <Input
                    id="mcp-name"
                    value={formData.name}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                    placeholder="My Outlook Connection"
                    data-testid="input-mcp-name"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="mcp-label">Server Label *</Label>
                  <Input
                    id="mcp-label"
                    value={formData.server_label}
                    onChange={(e) => setFormData({ ...formData, server_label: e.target.value })}
                    placeholder="outlookemail"
                    data-testid="input-mcp-label"
                  />
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="mcp-description">Description</Label>
                <Textarea
                  id="mcp-description"
                  value={formData.description}
                  onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                  placeholder="Describe what this connection is used for..."
                  rows={2}
                  data-testid="input-mcp-description"
                />
              </div>

              <div className="space-y-2">
                <Label>Connection Type *</Label>
                <Select
                  value={formData.connection_type}
                  onValueChange={(val) => setFormData({ 
                    ...formData, 
                    connection_type: val as "connector" | "url",
                    connector_id: "",
                    server_url: "",
                    allowed_tools: [],
                  })}
                >
                  <SelectTrigger data-testid="select-mcp-connection-type">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="connector">OpenAI Hosted Connector</SelectItem>
                    <SelectItem value="url">Custom Server URL</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {formData.connection_type === "connector" ? (
                <div className="space-y-2">
                  <Label>Select Connector *</Label>
                  <Select
                    value={formData.connector_id}
                    onValueChange={(val) => {
                      const connector = availableConnectors.find((c) => c.id === val);
                      setFormData({ 
                        ...formData, 
                        connector_id: val,
                        allowed_tools: connector?.available_tools ?? [],
                      });
                    }}
                  >
                    <SelectTrigger data-testid="select-mcp-connector">
                      <SelectValue placeholder="Select a connector..." />
                    </SelectTrigger>
                    <SelectContent>
                      {availableConnectors.map((connector) => (
                        <SelectItem key={connector.id} value={connector.id}>
                          <div className="flex flex-col">
                            <span>{connector.name}</span>
                            <span className="text-xs text-muted-foreground">{connector.description}</span>
                          </div>
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              ) : (
                <div className="space-y-2">
                  <Label htmlFor="mcp-server-url">Server URL *</Label>
                  <Input
                    id="mcp-server-url"
                    value={formData.server_url}
                    onChange={(e) => setFormData({ ...formData, server_url: e.target.value })}
                    placeholder="https://mcp.example.com/sse"
                    data-testid="input-mcp-server-url"
                  />
                </div>
              )}

              <div className="space-y-2">
                <Label htmlFor="mcp-auth">Authorization Token</Label>
                <div className="relative">
                  <Input
                    id="mcp-auth"
                    type={showAuthToken ? "text" : "password"}
                    value={formData.authorization}
                    onChange={(e) => setFormData({ ...formData, authorization: e.target.value })}
                    placeholder="Bearer token or API key"
                    className="pr-20"
                    data-testid="input-mcp-auth"
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="absolute right-1 top-1/2 -translate-y-1/2 h-7"
                    onClick={() => setShowAuthToken(!showAuthToken)}
                  >
                    {showAuthToken ? "Hide" : "Show"}
                  </Button>
                </div>
              </div>

              <div className="space-y-2">
                <Label>Require Approval</Label>
                <Select
                  value={formData.require_approval}
                  onValueChange={(val) => setFormData({ 
                    ...formData, 
                    require_approval: val as "always" | "never" | "on_first_use" 
                  })}
                >
                  <SelectTrigger data-testid="select-mcp-approval">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {APPROVAL_OPTIONS.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {(selectedConnector || formData.connection_type === "url") && (
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <Label>Allowed Tools</Label>
                    {selectedConnector && (
                      <div className="flex items-center gap-2">
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={selectAllTools}
                        >
                          Select All
                        </Button>
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={clearAllTools}
                        >
                          Clear
                        </Button>
                      </div>
                    )}
                  </div>
                  
                  {selectedConnector ? (
                    <div className="border rounded-md p-3 max-h-48 overflow-y-auto">
                      <div className="grid gap-2 sm:grid-cols-2">
                        {selectedConnector.available_tools.map((tool) => (
                          <div key={tool} className="flex items-center space-x-2">
                            <Checkbox
                              id={`tool-${tool}`}
                              checked={formData.allowed_tools.includes(tool)}
                              onCheckedChange={() => toggleTool(tool)}
                              data-testid={`checkbox-mcp-tool-${tool}`}
                            />
                            <label
                              htmlFor={`tool-${tool}`}
                              className="text-sm cursor-pointer"
                            >
                              {tool}
                            </label>
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : (
                    <Textarea
                      placeholder="Enter tool names, one per line..."
                      value={formData.allowed_tools.join("\n")}
                      onChange={(e) => setFormData({
                        ...formData,
                        allowed_tools: e.target.value.split("\n").filter((t) => t.trim()),
                      })}
                      rows={4}
                      data-testid="input-mcp-tools-list"
                    />
                  )}
                </div>
              )}

              <div className="flex items-center justify-between">
                <div className="space-y-0.5">
                  <Label>Active</Label>
                  <p className="text-xs text-muted-foreground">
                    Enable this connection for use by agents
                  </p>
                </div>
                <Switch
                  checked={formData.is_active}
                  onCheckedChange={(checked) => setFormData({ ...formData, is_active: checked })}
                  data-testid="switch-mcp-active"
                />
              </div>
            </div>
          </ScrollArea>

          <DialogFooter>
            <Button variant="outline" onClick={() => setIsDialogOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleSubmit}
              disabled={!isFormValid || createMutation.isPending || updateMutation.isPending}
              data-testid="button-save-mcp"
            >
              {createMutation.isPending || updateMutation.isPending ? "Saving..." : "Save Connection"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete MCP Connection</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete "{connectionToDelete?.name}"? This action cannot be undone.
              Any agents using this connection will no longer be able to access it.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => connectionToDelete && deleteMutation.mutate(connectionToDelete.id)}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {deleteMutation.isPending ? "Deleting..." : "Delete"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
