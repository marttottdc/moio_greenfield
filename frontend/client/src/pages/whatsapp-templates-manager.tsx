import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { ArrowLeft, Search, MessageSquare, MoreVertical, Plus } from "lucide-react";
import { Link } from "wouter";
import { EmptyState } from "@/components/empty-state";
import { fetchJson, apiRequest, queryClient } from "@/lib/queryClient";
import { WhatsAppTemplatePreview } from "@/components/whatsapp-template-preview";
import { useToast } from "@/hooks/use-toast";

interface WhatsAppTemplate {
  id: string;
  name: string;
  language: string;
  status: string;
  category: string;
  components?: Array<{
    type: "HEADER" | "BODY" | "FOOTER" | "BUTTONS";
    format?: "IMAGE" | "DOCUMENT" | "TEXT";
    text?: string;
    example?: {
      header_handle?: string[];
      body_text?: string[];
      body_text_named_params?: Record<string, string>;
    };
    buttons?: Array<{
      text: string;
      type?: string;
    }>;
  }>;
}

const TEMPLATES_PATH = "/api/v1/resources/whatsapp-templates/";

export default function WhatsAppTemplatesManager() {
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedTemplateId, setSelectedTemplateId] = useState<string | null>(null);

  const templatesQuery = useQuery<{ templates: WhatsAppTemplate[] }>({
    queryKey: [TEMPLATES_PATH, { channel: "WhatsApp" }],
    queryFn: () => fetchJson<{ templates: WhatsAppTemplate[] }>(`${TEMPLATES_PATH}?channel=WhatsApp`),
  });

  const templates = templatesQuery.data?.templates ?? [];

  const filteredTemplates = searchQuery.trim().length > 0
    ? templates.filter((template) =>
        (template.name ?? "").toLowerCase().includes(searchQuery.toLowerCase()) ||
        (template.category ?? "").toLowerCase().includes(searchQuery.toLowerCase())
      )
    : templates;

  const selectedTemplate = filteredTemplates.find((t) => t.id === selectedTemplateId);

  return (
    <div className="h-full flex flex-col">
      <div className="mb-6">
        <div className="flex items-center gap-3 mb-4">
          <Link href="/workflows?tab=components">
            <Button variant="ghost" size="icon" data-testid="button-back">
              <ArrowLeft className="h-5 w-5" />
            </Button>
          </Link>
          <h1 className="text-3xl font-bold">WhatsApp Templates</h1>
          <div className="flex-1" />
          <Button data-testid="button-new-template">
            <Plus className="h-4 w-4 mr-2" />
            New Template
          </Button>
        </div>
      </div>
      <div className="flex h-full w-full">
        {/* Left Sidebar - Templates List */}
        <div className="w-80 border-r border-border bg-background flex flex-col shrink-0">
          <div className="p-3 border-b border-border">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
              <Input
                placeholder="Search templates..."
                className="pl-10"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                data-testid="input-search"
              />
            </div>
          </div>

          <div className="flex-1 overflow-y-auto">
            {templatesQuery.isLoading ? (
              <div className="p-4">
                <p className="text-sm text-muted-foreground">Loading templates...</p>
              </div>
            ) : filteredTemplates.length === 0 ? (
              <div className="p-4">
                <EmptyState
                  title={searchQuery.trim() ? "No templates match" : "No templates yet"}
                  description={
                    searchQuery.trim()
                      ? "Try a different search term."
                      : "Create your first WhatsApp template to get started."
                  }
                />
              </div>
            ) : (
              filteredTemplates.map((template) => (
                <div
                  key={template.id}
                  onClick={() => setSelectedTemplateId(template.id)}
                  className={`p-3 border-b border-border cursor-pointer transition-colors ${
                    selectedTemplateId === template.id ? "bg-accent" : "hover-elevate"
                  }`}
                  data-testid={`item-template-${template.id}`}
                >
                  <div className="flex items-center justify-between gap-2 mb-2">
                    <h3 className="font-semibold text-sm truncate flex-1" data-testid={`text-template-name-${template.id}`}>
                      {template.name}
                    </h3>
                    <div className="flex items-center gap-2 flex-shrink-0">
                      {template.category && (
                        <Badge variant="secondary" className="text-xs whitespace-nowrap">
                          {template.category}
                        </Badge>
                      )}
                      {template.status?.toLowerCase() === "approved" && (
                        <div className="w-2 h-2 rounded-full bg-green-500" />
                      )}
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Right Pane - Template Detail */}
        <div className="flex-1 flex flex-col bg-muted/20 backdrop-blur-sm">
          {!selectedTemplateId ? (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center">
                <div className="inline-flex h-16 w-16 items-center justify-center rounded-full bg-muted mb-4">
                  <MessageSquare className="h-8 w-8 text-muted-foreground" />
                </div>
                <p className="text-sm text-muted-foreground">Select a template to view details</p>
              </div>
            </div>
          ) : selectedTemplate ? (
            <>
              {/* Detail Header */}
              <div className="p-4 border-b border-border bg-background">
                <div className="flex items-start justify-between gap-3 mb-2">
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <h2 className="font-semibold text-lg">{selectedTemplate.name}</h2>
                      <div className="flex items-center gap-2">
                        {selectedTemplate.category && (
                          <Badge variant="secondary" className="text-xs">
                            {selectedTemplate.category}
                          </Badge>
                        )}
                        {selectedTemplate.status?.toLowerCase() === "approved" && (
                          <div className="w-2 h-2 rounded-full bg-green-500" />
                        )}
                      </div>
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <Button size="sm" variant="outline" data-testid="button-edit">
                      Edit
                    </Button>
                    <Button size="icon" variant="ghost" data-testid="button-more">
                      <MoreVertical className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
                {selectedTemplate.language && (
                  <p className="text-xs text-muted-foreground">
                    {selectedTemplate.language}
                  </p>
                )}
              </div>

              {/* Detail Content - Phone Preview */}
              <div className="flex-1 overflow-y-auto bg-gradient-to-br from-slate-50 to-slate-100">
                {selectedTemplate.components && selectedTemplate.components.length > 0 ? (
                  <WhatsAppTemplatePreview template={selectedTemplate} />
                ) : (
                  <div className="h-full flex items-center justify-center">
                    <div className="text-center text-muted-foreground">
                      <p className="text-sm">No components in this template</p>
                    </div>
                  </div>
                )}
              </div>
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
}
