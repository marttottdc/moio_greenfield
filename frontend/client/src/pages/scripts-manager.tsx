import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { ArrowLeft, Search, FileCode, MoreVertical, Plus } from "lucide-react";
import { Link } from "wouter";
import { EmptyState } from "@/components/empty-state";
import { fetchJson } from "@/lib/queryClient";

interface Script {
  id: string;
  name?: string;
  description?: string;
  status?: string;
  language?: string;
  created_at?: string;
  updated_at?: string;
  latest_version?: {
    version: number;
    code: string;
  };
}

const SCRIPTS_PATH = "/api/v1/scripts/";

function normalizeScripts(data: unknown): Script[] {
  if (!data) return [];
  if (Array.isArray(data)) return data as Script[];
  if (typeof data === "object" && data !== null) {
    const record = data as Record<string, unknown>;
    if (Array.isArray(record.scripts)) return record.scripts as Script[];
    if (Array.isArray(record.results)) return record.results as Script[];
    if (Array.isArray(record.data)) return record.data as Script[];
  }
  return [];
}

export default function ScriptsManager() {
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedScriptId, setSelectedScriptId] = useState<string | null>(null);

  const scriptsQuery = useQuery<unknown>({
    queryKey: [SCRIPTS_PATH],
    queryFn: () => fetchJson<unknown>(SCRIPTS_PATH),
  });

  const scripts = normalizeScripts(scriptsQuery.data);

  const filteredScripts = searchQuery.trim().length > 0
    ? scripts.filter((script) =>
        (script.name ?? "").toLowerCase().includes(searchQuery.toLowerCase()) ||
        (script.description ?? "").toLowerCase().includes(searchQuery.toLowerCase())
      )
    : scripts;

  const selectedScript = filteredScripts.find((s) => s.id === selectedScriptId);

  return (
    <div className="h-full flex flex-col">
      <div className="mb-6">
        <div className="flex items-center gap-3 mb-4">
          <Link href="/workflows?tab=components">
            <Button variant="ghost" size="icon" data-testid="button-back">
              <ArrowLeft className="h-5 w-5" />
            </Button>
          </Link>
          <h1 className="text-3xl font-bold">Scripts</h1>
          <div className="flex-1" />
          <Link href="/scripts/new/edit">
            <Button data-testid="button-new-script">
              <Plus className="h-4 w-4 mr-2" />
              New Script
            </Button>
          </Link>
        </div>
      </div>
      <div className="flex h-full w-full">
        {/* Left Sidebar - Scripts List */}
        <div className="w-80 border-r border-border bg-background flex flex-col shrink-0">
          <div className="p-3 border-b border-border">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
              <Input
                placeholder="Search scripts..."
                className="pl-10"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                data-testid="input-search"
              />
            </div>
          </div>

          <div className="flex-1 overflow-y-auto">
            {scriptsQuery.isLoading ? (
              <div className="p-4">
                <p className="text-sm text-muted-foreground">Loading scripts...</p>
              </div>
            ) : filteredScripts.length === 0 ? (
              <div className="p-4">
                <EmptyState
                  title={searchQuery.trim() ? "No scripts match" : "No scripts yet"}
                  description={
                    searchQuery.trim()
                      ? "Try a different search term."
                      : "Create your first script to get started."
                  }
                />
              </div>
            ) : (
              filteredScripts.map((script) => (
                <div
                  key={script.id}
                  onClick={() => setSelectedScriptId(script.id)}
                  className={`p-3 border-b border-border cursor-pointer transition-colors ${
                    selectedScriptId === script.id ? "bg-accent" : "hover-elevate"
                  }`}
                  data-testid={`item-script-${script.id}`}
                >
                  <div className="flex items-start justify-between gap-2 mb-1">
                    <div className="flex-1 min-w-0">
                      <h3 className="font-semibold text-sm truncate" data-testid={`text-script-name-${script.id}`}>
                        {script.name || "Untitled Script"}
                      </h3>
                      <div className="flex items-center gap-2 mt-1">
                        {script.status && (
                          <Badge variant="outline" className="text-xs">
                            {script.status}
                          </Badge>
                        )}
                        {script.language && (
                          <Badge variant="secondary" className="text-xs">
                            {script.language}
                          </Badge>
                        )}
                      </div>
                    </div>
                  </div>
                  {script.description && (
                    <p className="text-xs text-muted-foreground line-clamp-2 mt-1">
                      {script.description}
                    </p>
                  )}
                </div>
              ))
            )}
          </div>
        </div>

        {/* Right Pane - Script Detail */}
        <div className="flex-1 flex flex-col bg-muted/20 backdrop-blur-sm">
          {!selectedScriptId ? (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center">
                <div className="inline-flex h-16 w-16 items-center justify-center rounded-full bg-muted mb-4">
                  <FileCode className="h-8 w-8 text-muted-foreground" />
                </div>
                <p className="text-sm text-muted-foreground">Select a script to view details</p>
              </div>
            </div>
          ) : selectedScript ? (
            <>
              {/* Detail Header */}
              <div className="p-4 border-b border-border bg-background">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1">
                    <h2 className="font-semibold text-lg">{selectedScript.name || "Untitled Script"}</h2>
                    {selectedScript.description && (
                      <p className="text-sm text-muted-foreground mt-1">{selectedScript.description}</p>
                    )}
                    <div className="flex items-center gap-2 mt-2">
                      {selectedScript.status && (
                        <Badge variant="outline">{selectedScript.status}</Badge>
                      )}
                      {selectedScript.language && (
                        <Badge variant="secondary">{selectedScript.language}</Badge>
                      )}
                      {selectedScript.latest_version && (
                        <Badge variant="secondary">v{selectedScript.latest_version.version}</Badge>
                      )}
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <Link href={`/scripts/${selectedScriptId}/edit`}>
                      <Button size="sm" variant="outline" data-testid="button-edit">
                        Edit
                      </Button>
                    </Link>
                    <Button size="icon" variant="ghost" data-testid="button-more">
                      <MoreVertical className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              </div>

              {/* Detail Content */}
              <div className="flex-1 overflow-y-auto p-4">
                <div className="space-y-4">
                  <div>
                    <h3 className="text-sm font-semibold mb-2">Metadata</h3>
                    <div className="grid grid-cols-2 gap-4 text-sm">
                      <div>
                        <span className="text-muted-foreground">Created:</span>
                        <p className="font-medium">
                          {selectedScript.created_at
                            ? new Date(selectedScript.created_at).toLocaleDateString()
                            : "N/A"}
                        </p>
                      </div>
                      <div>
                        <span className="text-muted-foreground">Updated:</span>
                        <p className="font-medium">
                          {selectedScript.updated_at
                            ? new Date(selectedScript.updated_at).toLocaleDateString()
                            : "N/A"}
                        </p>
                      </div>
                    </div>
                  </div>

                  {selectedScript.latest_version?.code && (
                    <div>
                      <h3 className="text-sm font-semibold mb-2">Code Preview</h3>
                      <pre className="bg-muted p-3 rounded-md text-xs overflow-x-auto">
                        <code>{selectedScript.latest_version.code.slice(0, 500)}...</code>
                      </pre>
                    </div>
                  )}
                </div>
              </div>
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
}
