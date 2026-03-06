import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { ArrowLeft, Search, Webhook, MoreVertical, Plus, Copy, Trash2, Edit2 } from "lucide-react";
import { Link } from "wouter";
import { EmptyState } from "@/components/empty-state";
import { apiRequest, queryClient } from "@/lib/queryClient";
import { useToast } from "@/hooks/use-toast";
import { useWebhookList } from "@/hooks/useBuilderData";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { WebhookFormFields } from "@/components/webhooks/WebhookFormFields";

interface WebhookItem {
  id: string;
  name: string;
  description?: string;
  url?: string;
  auth_type?: string;
  auth_config?: Record<string, any>;
  expected_content_type?: string;
  expected_schema?: string;
  handler_path?: string;
  locked?: boolean;
  status?: string;
  created_at?: string;
  updated_at?: string;
}

const WEBHOOKS_PATH = "/api/v1/resources/webhooks/";

interface WebhookFormData {
  name: string;
  description: string;
  auth_type: string;
  expected_content_type: string;
  handler_path?: string;
  auth_config?: Record<string, any>;
  locked?: boolean;
}

export default function WebhooksManager() {
  const { toast } = useToast();
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedWebhookId, setSelectedWebhookId] = useState<string | null>(null);
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [editingWebhook, setEditingWebhook] = useState<WebhookItem | null>(null);
  const [formData, setFormData] = useState<WebhookFormData>({
    name: "",
    description: "",
    auth_type: "none",
    expected_content_type: "application/json",
    handler_path: undefined,
    auth_config: {},
    locked: false,
  });

  const webhookListQuery = useWebhookList();
  const webhooksQuery = {
    ...webhookListQuery,
    isLoading: webhookListQuery.isLoading,
    isError: webhookListQuery.isError,
    data: webhookListQuery.data?.webhooks,
  };

  const createWebhookMutation = useMutation({
    mutationFn: (data: WebhookFormData) =>
      apiRequest("POST", WEBHOOKS_PATH, {
        data,
      }),
    onSuccess: () => {
      webhookListQuery.refetch();
      setIsDialogOpen(false);
      setFormData({
        name: "",
        description: "",
        auth_type: "none",
        expected_content_type: "application/json",
        handler_path: undefined,
        auth_config: {},
        locked: false,
      });
      toast({ title: "Webhook created successfully" });
    },
    onError: (error: any) => {
      toast({
        title: "Failed to create webhook",
        description: error.message || "Please try again.",
        variant: "destructive",
      });
    },
  });

  const updateWebhookMutation = useMutation({
    mutationFn: (data: WebhookFormData) =>
      apiRequest("PATCH", `${WEBHOOKS_PATH}${editingWebhook!.id}/`, {
        data,
      }),
    onSuccess: () => {
      webhookListQuery.refetch();
      setIsDialogOpen(false);
      setEditingWebhook(null);
      setFormData({
        name: "",
        description: "",
        auth_type: "none",
        expected_content_type: "application/json",
        handler_path: undefined,
        auth_config: {},
        locked: false,
      });
      toast({ title: "Webhook updated successfully" });
    },
    onError: (error: any) => {
      toast({
        title: "Failed to update webhook",
        description: error.message || "Please try again.",
        variant: "destructive",
      });
    },
  });

  const deleteWebhookMutation = useMutation({
    mutationFn: (id: string) =>
      apiRequest("DELETE", `${WEBHOOKS_PATH}${id}/`),
    onSuccess: () => {
      webhookListQuery.refetch();
      setSelectedWebhookId(null);
      toast({ title: "Webhook deleted successfully" });
    },
    onError: (error: any) => {
      toast({
        title: "Failed to delete webhook",
        description: error.message || "Please try again.",
        variant: "destructive",
      });
    },
  });

  const webhooks = webhooksQuery.data ?? [];

  const filteredWebhooks = searchQuery.trim().length > 0
    ? webhooks.filter(
        (webhook) =>
          webhook.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
          (webhook.description?.toLowerCase() || "").includes(
            searchQuery.toLowerCase()
          )
      )
    : webhooks;

  const selectedWebhook = webhooks.find((w) => w.id === selectedWebhookId);

  const handleOpenDialog = (webhook?: WebhookItem) => {
    if (webhook) {
      setEditingWebhook(webhook);
      setFormData({
        name: webhook.name,
        description: webhook.description || "",
        auth_type: webhook.auth_type || "none",
        expected_content_type: webhook.expected_content_type || "application/json",
        handler_path: webhook.handler_path || "",
        locked: webhook.locked || false,
      });
    } else {
      setEditingWebhook(null);
      setFormData({
        name: "",
        description: "",
        auth_type: "none",
        expected_content_type: "application/json",
        handler_path: undefined,
        auth_config: {},
        locked: false,
      });
    }
    setIsDialogOpen(true);
  };

  const handleSubmit = () => {
    if (!formData.name.trim()) {
      toast({
        title: "Validation error",
        description: "Webhook name is required.",
        variant: "destructive",
      });
      return;
    }

    if (editingWebhook) {
      updateWebhookMutation.mutate(formData);
    } else {
      createWebhookMutation.mutate(formData);
    }
  };

  const copyWebhookUrl = (url?: string) => {
    if (url) {
      navigator.clipboard.writeText(url);
      toast({ title: "Webhook URL copied to clipboard" });
    }
  };

  return (
    <div className="h-full flex flex-col">
      <div className="mb-6">
        <div className="flex items-center gap-3 mb-4">
          <Link href="/workflows?tab=components">
            <Button variant="ghost" size="icon" data-testid="button-back">
              <ArrowLeft className="h-5 w-5" />
            </Button>
          </Link>
          <h1 className="text-3xl font-bold">Webhooks</h1>
          <div className="flex-1" />
          <Button
            onClick={() => handleOpenDialog()}
            data-testid="button-new-webhook"
          >
            <Plus className="h-4 w-4 mr-2" />
            New Webhook
          </Button>
        </div>
      </div>
      <div className="flex h-full w-full">
        {/* Left Sidebar - Webhooks List */}
        <div className="w-80 border-r border-border bg-background flex flex-col shrink-0">
          <div className="p-3 border-b border-border">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
              <Input
                placeholder="Search webhooks..."
                className="pl-10"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                data-testid="input-search"
              />
            </div>
          </div>

          <div className="flex-1 overflow-y-auto">
            {webhooksQuery.isLoading ? (
              <div className="p-4">
                <p className="text-sm text-muted-foreground">Loading webhooks...</p>
              </div>
            ) : webhooksQuery.isError ? (
              <div className="p-4">
                <EmptyState
                  title="Error loading webhooks"
                  description="Failed to load webhooks. Please try again later."
                />
              </div>
            ) : filteredWebhooks.length === 0 ? (
              <div className="p-4">
                <EmptyState
                  title={searchQuery.trim() ? "No webhooks match" : "No webhooks yet"}
                  description={
                    searchQuery.trim()
                      ? "Try a different search term."
                      : "Create your first webhook to get started."
                  }
                />
              </div>
            ) : (
              filteredWebhooks.map((webhook) => (
                <div
                  key={webhook.id}
                  onClick={() => setSelectedWebhookId(webhook.id)}
                  className={`p-3 border-b border-border cursor-pointer transition-colors ${
                    selectedWebhookId === webhook.id ? "bg-accent" : "hover-elevate"
                  }`}
                  data-testid={`item-webhook-${webhook.id}`}
                >
                  <div className="flex items-center justify-between gap-2 mb-2">
                    <h3 className="font-semibold text-sm truncate flex-1" data-testid={`text-webhook-name-${webhook.id}`}>
                      {webhook.name}
                    </h3>
                    <div className="flex items-center gap-2 flex-shrink-0">
                      {webhook.auth_type && webhook.auth_type !== "none" && (
                        <Badge variant="secondary" className="text-xs whitespace-nowrap">
                          {webhook.auth_type}
                        </Badge>
                      )}
                      {webhook.locked && (
                        <div className="w-2 h-2 rounded-full bg-yellow-500" />
                      )}
                    </div>
                  </div>
                  {webhook.description && (
                    <p className="text-xs text-muted-foreground line-clamp-2">
                      {webhook.description}
                    </p>
                  )}
                  {webhook.url && (
                    <p className="text-xs text-muted-foreground mt-1 font-mono truncate">
                      {webhook.url}
                    </p>
                  )}
                </div>
              ))
            )}
          </div>
        </div>

        {/* Right Pane - Webhook Detail */}
        <div className="flex-1 flex flex-col bg-muted/20 backdrop-blur-sm">
          {!selectedWebhookId ? (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center">
                <div className="inline-flex h-16 w-16 items-center justify-center rounded-full bg-muted mb-4">
                  <Webhook className="h-8 w-8 text-muted-foreground" />
                </div>
                <p className="text-sm text-muted-foreground">Select a webhook to view details</p>
              </div>
            </div>
          ) : selectedWebhook ? (
            <>
              {/* Detail Header */}
              <div className="p-4 border-b border-border bg-background">
                <div className="flex items-start justify-between gap-3 mb-2">
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <h2 className="font-semibold text-lg">{selectedWebhook.name}</h2>
                      <div className="flex items-center gap-2">
                        {selectedWebhook.auth_type && selectedWebhook.auth_type !== "none" && (
                          <Badge variant="secondary" className="text-xs">
                            {selectedWebhook.auth_type}
                          </Badge>
                        )}
                        {selectedWebhook.locked && (
                          <Badge variant="outline" className="text-xs">
                            Locked
                          </Badge>
                        )}
                      </div>
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => handleOpenDialog(selectedWebhook)}
                      data-testid="button-edit"
                    >
                      <Edit2 className="h-4 w-4 mr-2" />
                      Edit
                    </Button>
                    <Button
                      size="sm"
                      variant="destructive"
                      onClick={() =>
                        deleteWebhookMutation.mutate(selectedWebhook.id)
                      }
                      data-testid="button-delete"
                      disabled={deleteWebhookMutation.isPending}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
                {selectedWebhook.description && (
                  <p className="text-sm text-muted-foreground">
                    {selectedWebhook.description}
                  </p>
                )}
              </div>

              {/* Detail Content */}
              <div className="flex-1 overflow-y-auto p-4">
                <div className="space-y-4">
                  {selectedWebhook.url && (
                    <div>
                      <h3 className="text-sm font-semibold mb-2">Webhook URL</h3>
                      <div className="flex items-center gap-2">
                        <div className="bg-muted p-3 rounded-md flex-1 overflow-hidden">
                          <code className="text-xs break-all font-mono">
                            {selectedWebhook.url}
                          </code>
                        </div>
                        <Button
                          size="icon"
                          variant="outline"
                          onClick={() => copyWebhookUrl(selectedWebhook.url)}
                          data-testid="button-copy-url"
                        >
                          <Copy className="h-4 w-4" />
                        </Button>
                      </div>
                    </div>
                  )}

                  {selectedWebhook.expected_content_type && (
                    <div>
                      <h3 className="text-sm font-semibold mb-2">
                        Expected Content Type
                      </h3>
                      <p className="text-sm text-muted-foreground">
                        {selectedWebhook.expected_content_type}
                      </p>
                    </div>
                  )}

                  {selectedWebhook.handler_path && (
                    <div>
                      <h3 className="text-sm font-semibold mb-2">Handler</h3>
                      <Badge variant="secondary" data-testid="text-handler-path">
                        {selectedWebhook.handler_path}
                      </Badge>
                    </div>
                  )}

                  {selectedWebhook.auth_type && selectedWebhook.auth_type !== "none" && (
                    <div>
                      <h3 className="text-sm font-semibold mb-2">Authentication</h3>
                      <div className="space-y-2">
                        <div className="flex items-center gap-2">
                          <span className="text-sm text-muted-foreground">Type:</span>
                          <Badge variant="outline">{selectedWebhook.auth_type}</Badge>
                        </div>
                        {selectedWebhook.auth_config && Object.keys(selectedWebhook.auth_config).length > 0 && (
                          <div className="bg-muted p-3 rounded-md">
                            <div className="flex items-center justify-between mb-2">
                              <span className="text-xs font-medium text-muted-foreground">Auth Config</span>
                              <Button
                                size="sm"
                                variant="ghost"
                                className="h-6 text-xs"
                                onClick={() => {
                                  navigator.clipboard.writeText(JSON.stringify(selectedWebhook.auth_config, null, 2));
                                  toast({ title: "Auth config copied to clipboard" });
                                }}
                                data-testid="button-copy-auth-config"
                              >
                                <Copy className="h-3 w-3 mr-1" />
                                Copy
                              </Button>
                            </div>
                            <div className="space-y-1">
                              {Object.entries(selectedWebhook.auth_config).map(([key, value]) => (
                                <div key={key} className="flex items-center gap-2 text-xs">
                                  <span className="text-muted-foreground">{key}:</span>
                                  <code className="font-mono bg-background px-1 py-0.5 rounded">
                                    {key.toLowerCase().includes('token') || key.toLowerCase().includes('password') || key.toLowerCase().includes('secret')
                                      ? '••••••••'
                                      : String(value)}
                                  </code>
                                  <Button
                                    size="icon"
                                    variant="ghost"
                                    className="h-5 w-5"
                                    onClick={() => {
                                      navigator.clipboard.writeText(String(value));
                                      toast({ title: `${key} copied to clipboard` });
                                    }}
                                    data-testid={`button-copy-${key}`}
                                  >
                                    <Copy className="h-3 w-3" />
                                  </Button>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  )}

                  {selectedWebhook.expected_schema && (
                    <div>
                      <h3 className="text-sm font-semibold mb-2">
                        Expected Schema
                      </h3>
                      <div className="bg-muted p-3 rounded-md overflow-auto max-h-64">
                        <code className="text-xs font-mono text-muted-foreground whitespace-pre break-words">
                          {(() => {
                            try {
                              const parsed = typeof selectedWebhook.expected_schema === 'string'
                                ? JSON.parse(selectedWebhook.expected_schema)
                                : selectedWebhook.expected_schema;
                              return JSON.stringify(parsed, null, 2);
                            } catch {
                              return selectedWebhook.expected_schema;
                            }
                          })()}
                        </code>
                      </div>
                    </div>
                  )}

                  <div>
                    <h3 className="text-sm font-semibold mb-2">Metadata</h3>
                    <div className="grid grid-cols-2 gap-4 text-sm">
                      <div>
                        <span className="text-muted-foreground">Created:</span>
                        <p className="font-medium">
                          {selectedWebhook.created_at
                            ? new Date(selectedWebhook.created_at).toLocaleDateString()
                            : "N/A"}
                        </p>
                      </div>
                      <div>
                        <span className="text-muted-foreground">Updated:</span>
                        <p className="font-medium">
                          {selectedWebhook.updated_at
                            ? new Date(selectedWebhook.updated_at).toLocaleDateString()
                            : "N/A"}
                        </p>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </>
          ) : null}
        </div>
      </div>

      {/* Webhook Dialog */}
      <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
        <DialogContent data-testid="dialog-webhook">
          <DialogHeader>
            <DialogTitle>
              {editingWebhook ? "Edit Webhook" : "Create Webhook"}
            </DialogTitle>
            <DialogDescription>
              {editingWebhook
                ? "Update the webhook configuration"
                : "Set up a new webhook to receive external data"}
            </DialogDescription>
          </DialogHeader>

          <WebhookFormFields
            formData={formData}
            onChange={setFormData}
            showLocked={true}
            showHandler={true}
          />

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setIsDialogOpen(false)}
              data-testid="button-cancel"
            >
              Cancel
            </Button>
            <Button
              onClick={handleSubmit}
              disabled={
                createWebhookMutation.isPending ||
                updateWebhookMutation.isPending
              }
              data-testid="button-save"
            >
              {editingWebhook ? "Update" : "Create"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
