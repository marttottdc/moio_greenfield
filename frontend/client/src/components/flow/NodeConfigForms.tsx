import { useMemo, useState, useEffect, useRef, useCallback } from "react";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useWebhookData, useTemplateData, useAgentData, useScriptData } from "@/components/flow/BuilderDataContext";
import { useAutomationScriptDetails, useCrmModels, useCrmResourceDetails, useWebhookDetails } from "@/hooks/useBuilderData";
import { deriveBranchOutputs, normalizeBranchConfig } from "@/components/flow/branchUtils";
import { SchemaFieldSelector, FieldReferenceBuilder } from "@/components/flow/SchemaFieldSelector";
import { DataVisualizer } from "@/components/flow/DataVisualizer";
import { useToast } from "@/hooks/use-toast";
import { AvailableDataField } from "@/components/flow/types";
import { ChevronsUpDown, Loader2, Plus, RefreshCw, AlertCircle, Trash2, Check, Copy, ChevronDown, Lightbulb, Code, HelpCircle, Zap } from "lucide-react";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";
import { apiV1 } from "@/lib/api";
import { apiRequest } from "@/lib/queryClient";
import { EventTriggerConfigPanel } from "@/components/flow/triggers/EventTriggerConfig";
import { ScheduleTriggerConfigPanel } from "@/components/flow/triggers/ScheduleTriggerConfig";
import { DEFAULT_EVENT_CONFIG, DEFAULT_SCHEDULE_CONFIG } from "@/components/flow/triggers/types";
import type { EventTriggerConfig, ScheduleConfig } from "@/components/flow/triggers/types";
import { useWebhookHandlers } from "@/hooks/useWebhookHandlers";
import ReactQuill from "react-quill";
import "react-quill/dist/quill.snow.css";
import { validateCtxPath, validateNormalizeSourcePath, validateSandboxedExpression } from "@/components/flow/sandboxedExpressions";
import { emailApi } from "@/lib/integrations/emailApi";
import { calendarApi } from "@/lib/integrations/calendarApi";
import type { EmailAccount, CalendarAccount } from "@/lib/integrations/types";
import { useDataLabImportProcesses, useDataLabImportProcess } from "@/hooks/use-datalab";
import type { ImportProcess } from "@/lib/moio-types";
import { FormulaAwareStringInput } from "@/components/flow/FormulaAwareStringInput";

interface NodeHints {
  description?: string;
  example_config?: Record<string, any>;
  use_cases?: string[];
  expression_examples?: Array<{
    expr: string;
    description: string;
  }>;
  tips?: string;
}

interface NodeConfigFormProps {
  config: Record<string, any>;
  onConfigChange: (updates: Record<string, any>) => void;
  availableData?: AvailableDataField[];
  dataNodes?: any[];
  hints?: NodeHints;
  scope?: {
    canSeeInput: boolean;
    canSeeCtx: boolean;
    schemaAvailable?: boolean;
  };
}

function AccountPickerForm({
  config,
  onConfigChange,
  kind,
}: NodeConfigFormProps & { kind: "email" | "calendar" }) {
  const { toast } = useToast();
  const { data, isLoading, error, refetch } = useQuery<EmailAccount[] | CalendarAccount[]>({
    queryKey: [kind, "flow", "accounts", "tenant"],
    queryFn: () => (kind === "email" ? emailApi.flowAccounts("tenant") : calendarApi.flowAccounts("tenant")),
    retry: false,
  });

  const accountId = config.account_id as string | undefined;

  const handleSelect = (value: string) => {
    onConfigChange({ account_id: value });
  };

  if (isLoading) {
    return <Skeleton className="h-10 w-full" />;
  }

  if (error) {
    return (
      <ErrorDisplay
        error={error}
        action={{ label: "Retry", onClick: () => refetch() }}
        endpoint={kind === "email" ? "/api/v1/integrations/email/flow/accounts" : "/api/v1/integrations/calendar/flow/accounts"}
      />
    );
  }

  const accounts = data ?? [];

  if (accounts.length === 0) {
    return <Alert className="bg-muted/50"><AlertDescription>No tenant {kind} accounts available. Connect one in Settings.</AlertDescription></Alert>;
  }

  return (
    <div className="space-y-2">
      <Label>Select tenant {kind} account</Label>
      <Select value={accountId} onValueChange={handleSelect}>
        <SelectTrigger>
          <SelectValue placeholder="Choose account" />
        </SelectTrigger>
        <SelectContent>
          {accounts.map((acc) => (
            <SelectItem key={acc.id} value={acc.id}>
              {acc.external_account.email_address} ({acc.external_account.provider})
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

// HTTP Request Form
function HttpRequestForm({ config, onConfigChange, availableData = [], dataNodes = [] }: NodeConfigFormProps) {
  const [selectedField, setSelectedField] = useState<string>("");
  const { toast } = useToast();
  const [runner, setRunner] = useState<"auto" | "backend" | "browser">("auto");
  const [isRunning, setIsRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [lastResult, setLastResult] = useState<{
    runnerUsed: "backend" | "browser";
    ok: boolean;
    status: number;
    statusText?: string;
    elapsedMs: number;
    contentType?: string;
    headers?: Record<string, string>;
    bodyText?: string;
    bodyJson?: any;
  } | null>(null);

  // Convert availableData to SchemaField format
  const schemaFields = useMemo(() => {
    return availableData.map(d => ({
      path: d.key,
      type: d.type,
      description: d.description,
      source: d.source,
    }));
  }, [availableData]);

  const parseJsonText = (raw: any): { ok: true; value: any } | { ok: false; error: string } => {
    const text = String(raw ?? "").trim();
    if (!text) return { ok: true, value: undefined };
    try {
      return { ok: true, value: JSON.parse(text) };
    } catch (e) {
      return { ok: false, error: e instanceof Error ? e.message : "Invalid JSON" };
    }
  };

  const inferSchemaNodeFromExample = (value: any): any => {
    if (value === null || value === undefined) return { kind: "unknown" };
    if (Array.isArray(value)) {
      const firstNonNull = value.find((v) => v !== null && v !== undefined);
      return {
        kind: "array",
        items: firstNonNull === undefined ? { kind: "unknown" } : inferSchemaNodeFromExample(firstNonNull),
      };
    }
    if (typeof value === "object") {
      const properties: Record<string, any> = {};
      for (const [k, v] of Object.entries(value)) {
        // Keep paths safe for Normalize / dot-path access; skip weird keys
        if (!/^[A-Za-z0-9_-]+$/.test(k)) continue;
        properties[k] = inferSchemaNodeFromExample(v);
      }
      return { kind: "object", properties };
    }
    const t = typeof value;
    if (t === "string" || t === "number" || t === "boolean") {
      return { kind: "primitive", type: t };
    }
    return { kind: "unknown" };
  };

  const runBrowser = async (payload: { url: string; method: string; headers: Record<string, string>; body?: any }) => {
    const start = performance.now();
    const res = await fetch(payload.url, {
      method: payload.method,
      headers: payload.headers,
      body: payload.method.toUpperCase() === "GET" || payload.method.toUpperCase() === "HEAD"
        ? undefined
        : payload.body !== undefined
          ? JSON.stringify(payload.body)
          : undefined,
    });

    const elapsedMs = Math.round(performance.now() - start);
    const contentType = res.headers.get("content-type") ?? undefined;

    const headersOut: Record<string, string> = {};
    // Return a small, useful subset
    ["content-type", "content-length", "date", "etag", "x-request-id"].forEach((h) => {
      const v = res.headers.get(h);
      if (v) headersOut[h] = v;
    });

    let bodyText = "";
    let bodyJson: any = undefined;
    try {
      bodyText = await res.text();
      if (contentType?.includes("application/json")) {
        try {
          bodyJson = JSON.parse(bodyText);
        } catch {
          bodyJson = undefined;
        }
      }
    } catch {
      bodyText = "";
    }

    return {
      runnerUsed: "browser" as const,
      ok: res.ok,
      status: res.status,
      statusText: res.statusText,
      elapsedMs,
      contentType,
      headers: headersOut,
      bodyText,
      bodyJson,
    };
  };

  const runBackend = async (payload: { url: string; method: string; headers: Record<string, string>; body?: any }) => {
    const start = performance.now();
    const res = await apiRequest("POST", apiV1("/flows/http-test/"), {
      data: {
        url: payload.url,
        method: payload.method,
        headers: payload.headers,
        body: payload.body,
        timeout_ms: 15000,
      },
    });
    const elapsedMs = Math.round(performance.now() - start);
    const json = await res.json();
    return {
      runnerUsed: "backend" as const,
      ok: Boolean(json?.ok),
      status: Number(json?.status ?? 0),
      statusText: String(json?.statusText ?? ""),
      elapsedMs: Number(json?.elapsedMs ?? elapsedMs),
      contentType: json?.contentType ? String(json.contentType) : undefined,
      headers: (json?.headers && typeof json.headers === "object") ? (json.headers as Record<string, string>) : undefined,
      bodyText: typeof json?.bodyText === "string" ? json.bodyText : undefined,
      bodyJson: json?.bodyJson,
    };
  };

  const handleRun = async () => {
    setRunError(null);
    setIsRunning(true);
    try {
      const url = String(config.url ?? "").trim();
      if (!url) {
        setRunError("URL is required.");
        return;
      }

      const method = String(config.method ?? "GET").toUpperCase();

      const headersParsed = parseJsonText(config.headers);
      if (!headersParsed.ok) {
        setRunError(`Headers JSON is invalid: ${headersParsed.error}`);
        return;
      }
      const headersObj = headersParsed.value && typeof headersParsed.value === "object" && !Array.isArray(headersParsed.value)
        ? (headersParsed.value as Record<string, any>)
        : {};
      const headers: Record<string, string> = {};
      for (const [k, v] of Object.entries(headersObj)) {
        if (!k) continue;
        if (v === null || v === undefined) continue;
        headers[String(k)] = String(v);
      }

      const bodyParsed = parseJsonText(config.body);
      if (!bodyParsed.ok) {
        setRunError(`Body JSON is invalid: ${bodyParsed.error}`);
        return;
      }
      const body = bodyParsed.value;

      // Default Content-Type when sending JSON body
      if (body !== undefined && !Object.keys(headers).some((h) => h.toLowerCase() === "content-type")) {
        headers["Content-Type"] = "application/json";
      }

      const request = { url, method, headers, body };

      let result: any = null;
      if (runner === "browser") {
        result = await runBrowser(request);
      } else if (runner === "backend") {
        result = await runBackend(request);
      } else {
        try {
          result = await runBackend(request);
        } catch (e) {
          // Fallback for deployments that don't implement the backend test route
          result = await runBrowser(request);
          toast({
            title: "Used browser runner",
            description: "Backend HTTP tester endpoint was unavailable; ran in-browser (CORS may apply).",
          });
        }
      }

      setLastResult(result);
      if (result.ok) {
        toast({ title: "Request succeeded", description: `HTTP ${result.status} (${result.elapsedMs}ms)` });
      } else {
        toast({ title: "Request failed", description: `HTTP ${result.status} ${result.statusText || ""}`.trim(), variant: "destructive" });
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setRunError(msg);
      toast({ title: "Preview error", description: msg, variant: "destructive" });
    } finally {
      setIsRunning(false);
    }
  };

  const outputSchemaText = useMemo(() => {
    if (!config.output_schema) return "";
    try {
      return JSON.stringify(config.output_schema, null, 2);
    } catch {
      return String(config.output_schema);
    }
  }, [config.output_schema]);

  return (
    <div className="space-y-3">
      {dataNodes.length > 0 && (
        <DataVisualizer 
          data={dataNodes} 
          title="Flow Data Available Here"
          compact={true}
          maxHeight="250px"
        />
      )}
      <div>
        <Label htmlFor="http-url" className="text-xs">URL</Label>
        <Input
          id="http-url"
          value={config.url || ""}
          onChange={(e) => onConfigChange({ ...config, url: e.target.value })}
          placeholder="https://api.example.com/endpoint"
          className="text-sm"
          data-testid="input-http-url"
        />
      </div>
      {schemaFields.length > 0 && (
        <ScrollArea className="h-48 border rounded-md p-2">
          <div>
            <SchemaFieldSelector
              value={selectedField}
              onChange={setSelectedField}
              availableFields={schemaFields}
              label="Map field for URL (optional)"
              placeholder="Select field to use in URL..."
            />
            <FieldReferenceBuilder selectedField={selectedField} />
          </div>
        </ScrollArea>
      )}
      <div>
        <Label htmlFor="http-method" className="text-xs">Method</Label>
        <Select
          value={config.method || "GET"}
          onValueChange={(value) => onConfigChange({ ...config, method: value })}
        >
          <SelectTrigger id="http-method" className="text-sm" data-testid="select-http-method">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="GET">GET</SelectItem>
            <SelectItem value="POST">POST</SelectItem>
            <SelectItem value="PUT">PUT</SelectItem>
            <SelectItem value="PATCH">PATCH</SelectItem>
            <SelectItem value="DELETE">DELETE</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <div>
        <Label htmlFor="http-headers" className="text-xs">Headers (JSON)</Label>
        <Textarea
          id="http-headers"
          value={config.headers || ""}
          onChange={(e) => onConfigChange({ ...config, headers: e.target.value })}
          placeholder='{"Content-Type": "application/json"}'
          rows={3}
          className="text-sm font-mono"
          data-testid="textarea-http-headers"
        />
      </div>
      <div>
        <Label htmlFor="http-body" className="text-xs">Body (JSON)</Label>
        <Textarea
          id="http-body"
          value={config.body || ""}
          onChange={(e) => onConfigChange({ ...config, body: e.target.value })}
          placeholder='{"key": "value"}'
          rows={4}
          className="text-sm font-mono"
          data-testid="textarea-http-body"
        />
      </div>

      <div className="rounded-md border bg-muted/20 p-3">
        <div className="flex items-center justify-between gap-2">
          <div className="min-w-0">
            <div className="text-sm font-medium">Test / Preview</div>
            <div className="text-xs text-muted-foreground">
              Run the request and infer an output schema from the JSON response.
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Select value={runner} onValueChange={(v) => setRunner(v as any)}>
              <SelectTrigger className="h-8 w-[160px] text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="auto">Auto (backend → browser)</SelectItem>
                <SelectItem value="backend">Backend runner</SelectItem>
                <SelectItem value="browser">Browser runner</SelectItem>
              </SelectContent>
            </Select>
            <Button
              size="sm"
              className="h-8"
              onClick={handleRun}
              disabled={isRunning || !String(config.url ?? "").trim()}
              data-testid="button-http-run-test"
            >
              {isRunning ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Zap className="h-4 w-4 mr-2" />}
              Run
            </Button>
          </div>
        </div>

        {String(config.method ?? "GET").toUpperCase() !== "GET" && (
          <Alert className="mt-3">
            <AlertCircle className="h-4 w-4" />
            <AlertTitle>Heads up</AlertTitle>
            <AlertDescription>
              Non-GET methods may create real side effects on the target API.
            </AlertDescription>
          </Alert>
        )}

        {runError && (
          <Alert variant="destructive" className="mt-3">
            <AlertCircle className="h-4 w-4" />
            <AlertTitle>Preview error</AlertTitle>
            <AlertDescription>{runError}</AlertDescription>
          </Alert>
        )}

        {lastResult && (
          <div className="mt-3 space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant={lastResult.ok ? "secondary" : "destructive"}>
                HTTP {lastResult.status}
              </Badge>
              <Badge variant="outline">{lastResult.runnerUsed}</Badge>
              <Badge variant="outline">{lastResult.elapsedMs}ms</Badge>
              {lastResult.contentType && <Badge variant="outline">{lastResult.contentType}</Badge>}
            </div>

            <div className="flex flex-wrap gap-2">
              <Button
                variant="secondary"
                size="sm"
                className="h-8"
                disabled={!lastResult.bodyJson || typeof lastResult.bodyJson !== "object"}
                onClick={() => {
                  const responseDataSchema = inferSchemaNodeFromExample(lastResult.bodyJson);
                  // IMPORTANT: Persist ONLY the response-body schema here.
                  // The backend wraps this under `response_data` when exposing node outputs.
                  // If we wrap here too, you end up with response_data.response_data.*.
                  const schema = responseDataSchema;
                  onConfigChange({
                    ...config,
                    output_schema: schema,
                    output_example: lastResult.bodyJson,
                  });
                  toast({ title: "Output schema saved", description: "Downstream nodes can now use nodes.<id>.output.*" });
                }}
                data-testid="button-http-use-as-output-schema"
              >
                Use response as output schema
              </Button>

              <Button
                variant="ghost"
                size="sm"
                className="h-8"
                disabled={!config.output_schema}
                onClick={() => onConfigChange({ ...config, output_schema: undefined, output_example: undefined })}
                data-testid="button-http-clear-output-schema"
              >
                <Trash2 className="h-4 w-4 mr-2" />
                Clear schema
              </Button>

              <Button
                variant="ghost"
                size="sm"
                className="h-8"
                disabled={!lastResult.bodyText}
                onClick={() => {
                  navigator.clipboard.writeText(String(lastResult.bodyText ?? ""));
                  toast({ title: "Response copied" });
                }}
                data-testid="button-http-copy-response"
              >
                <Copy className="h-4 w-4 mr-2" />
                Copy response
              </Button>
            </div>

            <Collapsible>
              <CollapsibleTrigger className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
                <ChevronDown className="h-3 w-3" />
                View response
              </CollapsibleTrigger>
              <CollapsibleContent className="pt-2">
                <pre className="text-xs bg-muted/50 p-2 rounded border overflow-x-auto max-h-[260px] overflow-y-auto">
                  {lastResult.bodyJson !== undefined
                    ? JSON.stringify(lastResult.bodyJson, null, 2)
                    : (lastResult.bodyText || "")}
                </pre>
              </CollapsibleContent>
            </Collapsible>
          </div>
        )}
      </div>

      {config.output_schema && (
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <Label className="text-xs">Output (output_schema)</Label>
            <Button
              variant="ghost"
              size="sm"
              className="h-7 px-2 text-xs text-muted-foreground"
              onClick={() => {
                navigator.clipboard.writeText(outputSchemaText);
                toast({ title: "Output schema copied" });
              }}
              data-testid="button-http-copy-output-schema"
            >
              <Copy className="h-3.5 w-3.5 mr-1" />
              Copy
            </Button>
          </div>

          <Collapsible>
            <CollapsibleTrigger className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
              <ChevronDown className="h-3 w-3" />
              View output schema
            </CollapsibleTrigger>
            <CollapsibleContent className="pt-2">
              <pre className="text-xs bg-muted/50 p-2 rounded border overflow-x-auto max-h-[260px] overflow-y-auto">
                {outputSchemaText}
              </pre>
              <p className="text-[11px] text-muted-foreground mt-2">
                Output is available to downstream nodes as <code>nodes.&lt;nodeId&gt;.output.*</code>.
              </p>
            </CollapsibleContent>
          </Collapsible>
        </div>
      )}
    </div>
  );
}

// Email Form
function EmailForm({ config, onConfigChange, dataNodes = [], availableData = [] }: NodeConfigFormProps) {
  const [isFieldPickerOpen, setIsFieldPickerOpen] = useState(false);
  const quillRef = useRef<ReactQuill>(null);
  const htmlBodyRef = useRef<HTMLTextAreaElement | null>(null);
  const [bodyMode, setBodyMode] = useState<"editor" | "html">("editor");
  const isInternalUpdateRef = useRef(false);
  const lastValueRef = useRef<string>("");

  // For sandboxed control-flow, autocomplete must offer ONLY ctx.* (from ctx_schema).
  const flatAvailableData = useMemo(() => {
    return (availableData || []).filter((f) => (f.key || "").startsWith("ctx."));
  }, [availableData]);

  const handleInsertField = (fieldKey: string) => {
    // If user is editing raw HTML, insert into the textarea.
    if (bodyMode === "html") {
      const el = htmlBodyRef.current;
      const currentText = String(config.body || "");
      const token = `{{ ${fieldKey} }}`;
      if (!el) {
        onConfigChange({ ...config, body: currentText + token });
        setIsFieldPickerOpen(false);
        return;
      }
      const start = el.selectionStart ?? currentText.length;
      const end = el.selectionEnd ?? currentText.length;
      const next = currentText.slice(0, start) + token + currentText.slice(end);
      onConfigChange({ ...config, body: next });
      setIsFieldPickerOpen(false);
      // Restore cursor after render
      setTimeout(() => {
        el.focus();
        const nextPos = start + token.length;
        el.setSelectionRange(nextPos, nextPos);
      }, 0);
      return;
    }

    const quill = quillRef.current?.getEditor();
    if (!quill) return;

    // Get current selection
    const range = quill.getSelection(true);
    if (!range) {
      // If no selection, insert at the end
      const length = quill.getLength();
      quill.setSelection(length - 1, 0);
    }

    // Wrap field in template syntax: {{ fieldKey }}
    const fieldReference = `{{ ${fieldKey} }}`;
    
    // Insert at current cursor position
    quill.insertText(range?.index || 0, fieldReference, 'user');
    
    // Move cursor after inserted text
    const newIndex = (range?.index || 0) + fieldReference.length;
    quill.setSelection(newIndex, 0);
    
    setIsFieldPickerOpen(false);
  };

  // Use useCallback to stabilize the function reference
  const handleEditorChange = useCallback((value: string) => {
    // Skip if this is an internal update (from useEffect)
    if (isInternalUpdateRef.current) {
      isInternalUpdateRef.current = false;
      return;
    }
    
    // Only update if the value actually changed to prevent infinite loops
    if (value === lastValueRef.current) {
      return;
    }
    
    lastValueRef.current = value;
    onConfigChange({ ...config, body: value });
  }, [config, onConfigChange]);

  // Sync external config changes to editor (when config.body changes from outside)
  useEffect(() => {
    const quill = quillRef.current?.getEditor();
    if (!quill) return;
    
    const currentContent = quill.root.innerHTML;
    const newContent = config.body || "";
    
    // Only update if content actually changed
    if (currentContent !== newContent) {
      isInternalUpdateRef.current = true;
      const selection = quill.getSelection();
      quill.root.innerHTML = newContent;
      lastValueRef.current = newContent;
      // Restore selection if it existed
      if (selection) {
        setTimeout(() => quill.setSelection(selection), 0);
      }
    }
  }, [config.body]);

  // Quill modules configuration
  const quillModules = useMemo(() => ({
    toolbar: [
      [{ 'header': [1, 2, 3, false] }],
      ['bold', 'italic', 'underline', 'strike'],
      [{ 'list': 'ordered'}, { 'list': 'bullet' }],
      [{ 'color': [] }, { 'background': [] }],
      [{ 'align': [] }],
      ['link', 'image'],
      ['clean']
    ],
  }), []);

  const quillFormats = [
    'header',
    'bold', 'italic', 'underline', 'strike',
    'list', 'bullet',
    'color', 'background',
    'align',
    'link', 'image'
  ];

  const parseEmailList = (raw: string): string[] => {
    const parts = raw
      .split(/[,;\n]+/g)
      .map((s) => s.trim())
      .filter(Boolean);
    // de-dupe, preserve order
    const seen = new Set<string>();
    const out: string[] = [];
    for (const p of parts) {
      const k = p.toLowerCase();
      if (seen.has(k)) continue;
      seen.add(k);
      out.push(p);
    }
    return out;
  };

  const toDisplay = useMemo(() => {
    const v: any = (config as any).to;
    if (Array.isArray(v)) return v.join("\n");
    return typeof v === "string" ? v : "";
  }, [config]);

  const toCount = useMemo(() => parseEmailList(toDisplay).length, [toDisplay]);

  return (
    <div className="space-y-3">
      {dataNodes.length > 0 && (
        <DataVisualizer 
          data={dataNodes} 
          title="Flow Data Available Here"
          compact={true}
          maxHeight="250px"
        />
      )}
      <div>
        <div className="flex items-center justify-between gap-2">
          <Label htmlFor="email-to" className="text-xs">To</Label>
          <Badge variant="outline" className="text-[10px]">{toCount} recipient{toCount === 1 ? "" : "s"}</Badge>
        </div>
        <Textarea
          id="email-to"
          value={toDisplay}
          onChange={(e) => onConfigChange({ ...config, to: parseEmailList(e.target.value) })}
          placeholder={"one@example.com\nanother@example.com\n(also supports commas/semicolons)"}
          rows={3}
          className="text-sm font-mono"
          data-testid="input-email-to"
        />
        <p className="text-[11px] text-muted-foreground mt-1">
          Enter one email per line (or separated by commas/semicolons). Saved as an array in <code>config.to</code>.
        </p>
      </div>
      <div>
        <Label htmlFor="email-subject" className="text-xs">Subject</Label>
        <Input
          id="email-subject"
          value={config.subject || ""}
          onChange={(e) => onConfigChange({ ...config, subject: e.target.value })}
          placeholder="Email subject"
          className="text-sm"
          data-testid="input-email-subject"
        />
      </div>
      <div>
        <div className="flex items-center justify-between mb-1">
          <Label htmlFor="email-body" className="text-xs">Body</Label>
          <Tabs value={bodyMode} onValueChange={(v) => setBodyMode(v as any)} className="w-auto">
            <TabsList className="h-7">
              <TabsTrigger value="editor" className="text-xs px-2">Editor</TabsTrigger>
              <TabsTrigger value="html" className="text-xs px-2">HTML</TabsTrigger>
            </TabsList>
          </Tabs>
          {flatAvailableData.length > 0 && (
            <Popover open={isFieldPickerOpen} onOpenChange={setIsFieldPickerOpen}>
              <PopoverTrigger asChild>
                <Button
                  variant="outline"
                  size="sm"
                  className="h-7 text-xs"
                  data-testid="button-insert-field"
                >
                  <Zap className="h-3 w-3 mr-1" />
                  Insert Field
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-80 p-0" side="bottom" align="end">
                <Command>
                  <CommandInput placeholder="Search fields..." className="text-sm" />
                  <CommandList 
                    className="max-h-[300px] overflow-y-auto"
                    onWheel={(e) => {
                      // Ensure wheel events scroll the list
                      const target = e.currentTarget;
                      if (target.scrollHeight > target.clientHeight) {
                        target.scrollTop += e.deltaY;
                        e.preventDefault();
                      }
                    }}
                    style={{ 
                      overscrollBehavior: 'contain',
                      WebkitOverflowScrolling: 'touch'
                    }}
                  >
                    <CommandEmpty className="text-sm p-2">No fields found.</CommandEmpty>
                    <CommandGroup>
                      {flatAvailableData.map((field) => (
                        <CommandItem
                          key={field.key}
                          value={field.key}
                          onSelect={() => handleInsertField(field.key)}
                          className="flex flex-col items-start gap-0.5"
                        >
                          <div className="flex w-full items-center justify-between gap-2">
                            <code className="text-sm font-mono">{field.key}</code>
                            <Badge variant="secondary" className="text-xs">
                              {field.type}
                            </Badge>
                          </div>
                          {field.description && (
                            <p className="text-xs text-muted-foreground">{field.description}</p>
                          )}
                        </CommandItem>
                      ))}
                    </CommandGroup>
                  </CommandList>
                </Command>
              </PopoverContent>
            </Popover>
          )}
        </div>
        {bodyMode === "editor" ? (
          <div className="border rounded-md overflow-hidden bg-background">
            <style>{`
              .email-editor .ql-container {
                height: 250px;
                font-size: 14px;
              }
              .email-editor .ql-editor {
                min-height: 250px;
              }
              .email-editor .ql-toolbar {
                border-top: none;
                border-left: none;
                border-right: none;
                border-bottom: 1px solid hsl(var(--border));
                background: hsl(var(--background));
              }
              .email-editor .ql-container {
                border-bottom: none;
                border-left: none;
                border-right: none;
                border-top: none;
              }
              .email-editor .ql-editor.ql-blank::before {
                color: hsl(var(--muted-foreground));
                font-style: normal;
              }
            `}</style>
            <ReactQuill
              ref={quillRef}
              theme="snow"
              value={config.body || ""}
              onChange={handleEditorChange}
              modules={quillModules}
              formats={quillFormats}
              placeholder="Write your email content here..."
              className="email-editor"
            />
          </div>
        ) : (
          <Textarea
            ref={htmlBodyRef}
            value={config.body || ""}
            onChange={(e) => onConfigChange({ ...config, body: e.target.value })}
            placeholder={"<p>Hello {{ ctx.user.name }}</p>"}
            rows={12}
            className="text-sm font-mono"
            data-testid="textarea-email-body-html"
          />
        )}
        <p className="text-xs text-muted-foreground mt-1">
          Use <code className="text-xs bg-muted px-1 py-0.5 rounded">{"{{ field.key }}"}</code> to insert dynamic fields
        </p>
      </div>
    </div>
  );
}

// Script/Code Form
function ScriptForm({ config, onConfigChange, availableData = [], dataNodes = [] }: NodeConfigFormProps) {
  const { scripts, isLoading, isFetching, error, refresh } = useScriptData();
  const { toast } = useToast();
  const [isSelectorOpen, setIsSelectorOpen] = useState(false);
  const [isInputPickerOpen, setIsInputPickerOpen] = useState<string | null>(null);
  const [isOutputPickerOpen, setIsOutputPickerOpen] = useState<string | null>(null);
  const [isParamPickerOpen, setIsParamPickerOpen] = useState<string | null>(null);
  const paramInputRefs = useRef<Record<string, HTMLInputElement | null>>({});
  const dataInputRefs = useRef<Record<string, HTMLInputElement | null>>({});

  const legacyInlineLanguage = typeof config?.language === "string" ? config.language : undefined;
  const legacyInlineCode = typeof config?.code === "string" ? config.code : undefined;
  const hasLegacyInlineConfig = Boolean(legacyInlineLanguage || legacyInlineCode);

  const inputMapping: Record<string, string> =
    config?.inputs && typeof config.inputs === "object" && !Array.isArray(config.inputs)
      ? (config.inputs as Record<string, string>)
      : {};

  const paramMapping: Record<string, string> =
    (config as any)?.params && typeof (config as any).params === "object" && !Array.isArray((config as any).params)
      ? ((config as any).params as Record<string, string>)
      : {};

  const outputToCtxMapping: Record<string, string> =
    (config as any)?.output_to_ctx && typeof (config as any).output_to_ctx === "object" && !Array.isArray((config as any).output_to_ctx)
      ? ((config as any).output_to_ctx as Record<string, string>)
      : {};

  const selectedFromList = useMemo(() => {
    const id = String(config?.script_id || "").trim();
    if (!id) return undefined;
    return scripts.find((s) => s.id === id);
  }, [config?.script_id, scripts]);

  const scriptDetailsQuery = useAutomationScriptDetails(
    typeof config?.script_id === "string" && config.script_id.trim() ? config.script_id : undefined
  );
  const scriptDetails = scriptDetailsQuery.data;
  const scriptDetailsError = scriptDetailsQuery.error;
  const isFetchingDetails = scriptDetailsQuery.isFetching;

  const selectedScript = scriptDetails ?? selectedFromList;

  const scriptParams = useMemo(() => {
    const s: any = selectedScript;
    if (!s) return [] as Array<{ name: string; type?: string; required?: boolean; default?: any; description?: string }>;

    // ScriptBuilder-style params_schema: { param: { type, required, default? } }
    if (s.params_schema && typeof s.params_schema === "object" && !Array.isArray(s.params_schema)) {
      return Object.entries(s.params_schema as Record<string, any>)
        .map(([name, def]) => ({
          name: String(name),
          type: typeof def?.type === "string" ? def.type : undefined,
          required: def?.required !== false,
          default: def?.default,
          description: typeof def?.description === "string" ? def.description : undefined,
        }))
        .filter((x) => Boolean(x.name));
    }

    return [];
  }, [selectedScript]);

  const scriptDataInputs = useMemo(() => {
    const s: any = selectedScript;
    if (!s) return [] as Array<{ name: string; type?: string; required?: boolean; description?: string }>;

    // Spec-style input_spec: { inputName: { name, type, required } }
    if (s.input_spec && typeof s.input_spec === "object" && !Array.isArray(s.input_spec)) {
      return Object.entries(s.input_spec as Record<string, any>)
        .map(([key, def]) => ({
          name: String(def?.name ?? key),
          type: typeof def?.type === "string" ? def.type : undefined,
          required: Boolean(def?.required),
          description: typeof def?.description === "string" ? def.description : undefined,
        }))
        .filter((x) => Boolean(x.name));
    }

    return [];
  }, [selectedScript]);

  const scriptOutputs = useMemo(() => {
    const s: any = selectedScript;
    if (!s) return [] as Array<{ name: string; type?: string; description?: string }>;

    // Spec-style output_spec: { outputName: { name, type } }
    if (s.output_spec && typeof s.output_spec === "object" && !Array.isArray(s.output_spec)) {
      return Object.entries(s.output_spec as Record<string, any>)
        .map(([key, def]) => ({
          name: String(def?.name ?? key),
          type: typeof def?.type === "string" ? def.type : undefined,
          description: typeof def?.description === "string" ? def.description : undefined,
        }))
        .filter((x) => Boolean(x.name));
    }

    return [];
  }, [selectedScript]);

  const handleSelectScript = (scriptId: string) => {
    const entry = scripts.find((s) => s.id === scriptId);
    if (!entry) return;
    setIsSelectorOpen(false);

    const next: Record<string, any> = {
      ...config,
      script_id: entry.id,
      script_name: entry.name,
      script_description: entry.description,
      script_language: entry.language,
    };
    // Remove legacy inline fields to avoid ambiguous runtime behavior
    delete next.code;
    delete next.language;
    onConfigChange(next);
  };

  const handleRefreshDetails = async () => {
    if (!config?.script_id) return;
    try {
      await scriptDetailsQuery.refetch();
      await refresh();
      toast({ description: "Script details refreshed." });
    } catch (err) {
      toast({
        variant: "destructive",
        description: err instanceof Error ? err.message : "Failed to refresh script details",
      });
    }
  };

  const outputSpecForPreview = useMemo(() => {
    const s: any = selectedScript;
    return s?.output_spec;
  }, [selectedScript]);

  const outputSpecTextForPreview = useMemo(() => {
    if (!outputSpecForPreview) return "";
    try {
      return typeof outputSpecForPreview === "string"
        ? outputSpecForPreview
        : JSON.stringify(outputSpecForPreview, null, 2);
    } catch {
      return String(outputSpecForPreview);
    }
  }, [outputSpecForPreview]);

  const ctxFields = useMemo(() => {
    return (availableData || []).filter((f) => String(f?.key || "").startsWith("ctx."));
  }, []);

  const pickableTemplateFields = useMemo(() => {
    const list = Array.isArray(availableData) ? availableData : [];
    return list.filter((f) => {
      const k = String(f?.key ?? "");
      if (!k) return false;
      return k.startsWith("ctx.") || k === "input.body" || k.startsWith("input.body.") || k.startsWith("nodes.");
    });
  }, [availableData]);

  const isTemplateString = useCallback((v: any): boolean => {
    if (typeof v !== "string") return false;
    const s = v.trim();
    return s.startsWith("{{") && s.endsWith("}}") && s.length >= 4;
  }, []);

  const getTemplateInner = useCallback((v: string): string => v.trim().slice(2, -2).trim(), []);

  const lintTemplateNamespace = useCallback((inner: string): string | null => {
    // Allowed namespaces:
    // - ctx.*
    // - input.body.*
    // - nodes.<id>.output.*
    if (inner === "ctx" || inner.startsWith("ctx.")) return null;
    if (inner === "input.body" || inner.startsWith("input.body.")) return null;
    if (inner.startsWith("nodes.")) {
      const parts = inner.split(".").filter(Boolean);
      if (parts.length >= 3 && parts[2] === "output") return null;
      return "Invalid nodes template. Expected {{nodes.<id>.output.*}}";
    }
    return "Unsupported template namespace. Allowed: {{ctx.*}}, {{input.body.*}}, {{nodes.<id>.output.*}}";
  }, []);

  const validateTemplateExpression = useCallback((v: string): { ok: true } | { ok: false; error: string } => {
    if (!isTemplateString(v)) return { ok: true };
    const inner = getTemplateInner(v);
    const err = lintTemplateNamespace(inner);
    if (err) return { ok: false, error: err };
    return { ok: true };
  }, [getTemplateInner, isTemplateString, lintTemplateNamespace]);

  const insertTokenAtCursor = useCallback((el: HTMLInputElement | null, current: string, token: string) => {
    if (!el) {
      return current ? `${current}${token}` : token;
    }
    const start = el.selectionStart ?? current.length;
    const end = el.selectionEnd ?? current.length;
    const before = current.slice(0, start);
    const after = current.slice(end);
    const next = before + token + after;
    const nextCursor = start + token.length;
    // restore cursor after state update
    setTimeout(() => {
      try {
        el.focus();
        el.setSelectionRange(nextCursor, nextCursor);
      } catch {
        // ignore
      }
    }, 0);
    return next;
  }, []);

  const handleSetInputMapping = (inputName: string, value: string) => {
    onConfigChange({
      ...config,
      inputs: {
        ...inputMapping,
        [inputName]: value,
      },
    });
  };

  const handleClearInputMapping = (inputName: string) => {
    const next = { ...inputMapping };
    delete next[inputName];
    onConfigChange({ ...config, inputs: next });
  };

  const handleSetParamMapping = (paramName: string, value: string) => {
    // Migration helper: if old flows stored params in `inputs` and this param isn't a declared data input,
    // remove it from inputs when setting params to avoid ambiguity.
    const shouldDeleteFromInputs = scriptDataInputs.every((x) => x.name !== paramName);
    const nextInputs = shouldDeleteFromInputs ? (() => {
      const n = { ...inputMapping };
      delete n[paramName];
      return n;
    })() : inputMapping;

    onConfigChange({
      ...config,
      params: {
        ...paramMapping,
        [paramName]: value,
      },
      ...(shouldDeleteFromInputs ? { inputs: nextInputs } : {}),
    });
  };

  const handleClearParamMapping = (paramName: string) => {
    const next = { ...paramMapping };
    delete next[paramName];
    onConfigChange({ ...config, params: next });
  };

  const handleSetOutputToCtxMapping = (outputName: string, ctxPath: string) => {
    onConfigChange({
      ...config,
      output_to_ctx: {
        ...outputToCtxMapping,
        [outputName]: ctxPath,
      },
    });
  };

  const handleClearOutputToCtxMapping = (outputName: string) => {
    const next = { ...outputToCtxMapping };
    delete next[outputName];
    onConfigChange({ ...config, output_to_ctx: next });
  };

  return (
    <div className="space-y-4">
      {dataNodes.length > 0 && (
        <DataVisualizer 
          data={dataNodes} 
          title="Flow Data Available Here"
          compact={true}
          maxHeight="250px"
        />
      )}
      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between gap-2">
          <div>
            <Label className="text-xs">Script</Label>
            <p className="text-xs text-muted-foreground">
              Select an existing script. Create/edit scripts in{" "}
              <a href="/workflows/scripts" target="_blank" rel="noreferrer" className="text-primary hover:underline">
                Scripts
              </a>
              .
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="icon"
              className="h-8 w-8"
              onClick={() => refresh()}
              disabled={isFetching}
              data-testid="button-refresh-scripts"
              title="Refresh scripts"
            >
              {isFetching ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
              <span className="sr-only">Refresh scripts</span>
            </Button>
          </div>
        </div>

        <Popover open={isSelectorOpen} onOpenChange={setIsSelectorOpen}>
          <PopoverTrigger asChild>
            <Button
              variant="outline"
              role="combobox"
              aria-expanded={isSelectorOpen}
              className="w-full justify-between"
              data-testid="button-select-script"
            >
              <span className="truncate text-left text-sm">
                {selectedScript?.name || config.script_id || "Select script"}
              </span>
              <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-[360px] p-0" align="start">
            <Command>
              <CommandInput placeholder="Search scripts..." />
              <CommandList className="max-h-[300px] overflow-y-auto">
                <CommandEmpty>
                  {isLoading ? "Loading scripts..." : "No scripts available."}
                </CommandEmpty>
                <CommandGroup>
                  {scripts.map((script) => {
                    const searchValue = `${script.id} ${script.name || ""} ${script.description || ""} ${script.language || ""}`.toLowerCase();
                    return (
                      <CommandItem
                        key={script.id}
                        value={searchValue}
                        onSelect={() => handleSelectScript(script.id)}
                        className="flex flex-col items-start gap-0.5"
                        data-testid={`option-script-${script.id}`}
                      >
                        <div className="flex w-full items-center justify-between gap-2">
                          <span className="text-sm font-medium truncate">{script.name || script.id}</span>
                          <div className="flex items-center gap-1">
                            {script.language && (
                              <Badge variant="secondary" className="text-[10px] uppercase tracking-wide">
                                {script.language}
                              </Badge>
                            )}
                            {script.status && (
                              <Badge variant="outline" className="text-[10px] capitalize">
                                {script.status}
                              </Badge>
                            )}
                          </div>
                        </div>
                        {script.description && (
                          <div className="text-xs text-muted-foreground line-clamp-2">
                            {script.description}
                          </div>
                        )}
                      </CommandItem>
                    );
                  })}
                </CommandGroup>
              </CommandList>
            </Command>
          </PopoverContent>
        </Popover>
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>Script service error</AlertTitle>
          <AlertDescription className="text-xs">{error}</AlertDescription>
        </Alert>
      )}

      {hasLegacyInlineConfig && !config?.script_id && (
        <Alert>
          <AlertTitle>Legacy inline script config detected</AlertTitle>
          <AlertDescription className="text-xs">
            This node no longer edits code inline. Select an existing Script above. The legacy values are shown read-only below for migration.
          </AlertDescription>
        </Alert>
      )}

      {config?.script_id ? (
        <>
          {scriptDetailsError ? (
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertTitle>Failed to load script details</AlertTitle>
              <AlertDescription className="text-xs">
                {scriptDetailsError instanceof Error ? scriptDetailsError.message : "Could not fetch script details."}
              </AlertDescription>
            </Alert>
          ) : selectedScript ? (
            <div className="rounded-md border bg-muted/40 p-3 text-xs space-y-2">
              <div className="flex items-start justify-between gap-2">
                <div className="flex-1 flex flex-wrap items-center gap-2 text-xs font-medium">
                  <span>{selectedScript.name || selectedScript.id}</span>
                  {selectedScript.language && (
                    <Badge variant="secondary" className="text-[10px] uppercase tracking-wide">
                      {selectedScript.language}
                    </Badge>
                  )}
                  {(selectedScript as any).status && (
                    <Badge variant="outline" className="text-[10px] capitalize">
                      {(selectedScript as any).status}
                    </Badge>
                  )}
                  {scriptParams.length > 0 && (
                    <Badge variant="default" className="text-[10px]">
                      Params: {scriptParams.length}
                    </Badge>
                  )}
                  {outputSpecForPreview && (
                    <Badge variant="default" className="text-[10px]">
                      Output spec
                    </Badge>
                  )}
                </div>
                <div className="flex items-center gap-1">
                  <Button
                    size="icon"
                    variant="ghost"
                    className="h-6 w-6 flex-shrink-0"
                    onClick={handleRefreshDetails}
                    disabled={isFetchingDetails}
                    title="Refresh script details"
                    data-testid="button-refresh-script-details"
                  >
                    {isFetchingDetails ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <RefreshCw className="h-3.5 w-3.5" />
                    )}
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-6 px-2 text-[11px]"
                    onClick={() => window.open(`/scripts/${selectedScript.id}/edit`, "_blank")}
                    data-testid="button-open-script-editor"
                  >
                    Open
                  </Button>
                </div>
              </div>

              {selectedScript.description && (
                <p className="text-muted-foreground">{selectedScript.description}</p>
              )}
              <p className="font-mono text-[11px] break-all">ID: {selectedScript.id}</p>

              {outputSpecForPreview && (
                <Collapsible>
                  <CollapsibleTrigger asChild>
                    <Button variant="ghost" size="sm" className="h-7 px-2 text-xs -ml-2">
                      View output spec
                    </Button>
                  </CollapsibleTrigger>
                  <CollapsibleContent className="pt-2">
                    <div className="flex items-center justify-between gap-2 mb-2">
                      <p className="text-[11px] text-muted-foreground">Read-only preview</p>
                      <Button
                        size="icon"
                        variant="ghost"
                        className="h-6 w-6"
                        onClick={() => {
                          navigator.clipboard.writeText(outputSpecTextForPreview);
                          toast({ title: "Output spec copied" });
                        }}
                        disabled={!outputSpecTextForPreview}
                        title="Copy output spec"
                        data-testid="button-copy-script-output-spec"
                      >
                        <Copy className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                    <pre className="text-xs bg-muted/50 p-2 rounded border overflow-x-auto max-h-[240px] overflow-y-auto">
                      {outputSpecTextForPreview}
                    </pre>
                  </CollapsibleContent>
                </Collapsible>
              )}

              {isFetchingDetails && !scriptDetails && (
                <div className="flex items-center gap-2 text-muted-foreground">
                  <Loader2 className="h-3 w-3 animate-spin" />
                  <span>Loading script details...</span>
                </div>
              )}
            </div>
          ) : (
            <p className="text-xs text-muted-foreground">Choose a script to see connection details.</p>
          )}
        </>
      ) : (
        <p className="text-xs text-muted-foreground">Choose a script to see connection details.</p>
      )}

      {selectedScript && scriptParams.length > 0 && (
        <div className="rounded-md border p-3 space-y-3">
          <div>
            <div className="text-sm font-medium">Parameter mapping</div>
            <p className="text-xs text-muted-foreground">
              Map script parameters to flow data. Use template expressions like <code>{"{{ctx.*}}"}</code>,{" "}
              <code>{"{{input.body.*}}"}</code>, or <code>{"{{nodes.<id>.output.*}}"}</code>.
            </p>
          </div>

          <div className="space-y-2">
            {scriptParams.map((p) => {
              // Backward-compat: if params aren't set but old config stored them in inputs, show those.
              const current = paramMapping[p.name] ?? (paramMapping[p.name] === undefined ? (inputMapping[p.name] ?? "") : "");
              const required = p.required !== false;
              const check = current.trim() ? validateTemplateExpression(current) : { ok: true as const };
              const tokenHelp = <code>{"{{ctx.*}}"}</code>;

              return (
                <div key={p.name} className="rounded-md border bg-muted/20 p-2 space-y-2">
                  <div className="flex items-center justify-between gap-2">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <code className="text-xs font-mono">{p.name}</code>
                        {required && <Badge variant="outline" className="text-[10px]">required</Badge>}
                        {p.type && <Badge variant="secondary" className="text-[10px]">{p.type}</Badge>}
                      </div>
                      {p.description && (
                        <div className="text-xs text-muted-foreground mt-1">{p.description}</div>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-7 px-2 text-xs text-muted-foreground"
                        onClick={() => handleClearParamMapping(p.name)}
                        disabled={!current}
                        data-testid={`button-script-param-clear-${p.name}`}
                      >
                        Clear
                      </Button>
                    </div>
                  </div>

                  <FormulaAwareStringInput
                    value={current}
                    onChange={(v) => handleSetParamMapping(p.name, v)}
                    availableData={pickableTemplateFields}
                    singleLine
                    placeholderTemplate={p.default !== undefined ? String(p.default) : "{{ctx.some_value}}"}
                    placeholderFormula={'coalesce(ctx.some_value, "default")'}
                    error={current.trim() && !check.ok ? (check as { error?: string }).error : undefined}
                    data-testid={`input-script-param-mapping-${p.name}`}
                  />
                  {p.default !== undefined && !current && (
                    <div className="text-[11px] text-muted-foreground">
                      Default: <code className="font-mono">{String(p.default)}</code>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {selectedScript && scriptDataInputs.length > 0 && (
        <div className="rounded-md border p-3 space-y-3">
          <div>
            <div className="text-sm font-medium">Input mapping</div>
            <p className="text-xs text-muted-foreground">
              Map script data inputs to upstream outputs (often a dataframe/resultset reference).
            </p>
          </div>

          <div className="space-y-2">
            {scriptDataInputs.map((inp) => {
              const current = inputMapping[inp.name] ?? "";
              const required = inp.required === true;
              const check = current.trim() ? validateTemplateExpression(current) : { ok: true as const };

              return (
                <div key={inp.name} className="rounded-md border bg-muted/20 p-2 space-y-2">
                  <div className="flex items-center justify-between gap-2">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <code className="text-xs font-mono">{inp.name}</code>
                        {required && <Badge variant="outline" className="text-[10px]">required</Badge>}
                        {inp.type && <Badge variant="secondary" className="text-[10px]">{inp.type}</Badge>}
                      </div>
                      {inp.description && (
                        <div className="text-xs text-muted-foreground mt-1">{inp.description}</div>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-7 px-2 text-xs text-muted-foreground"
                        onClick={() => handleClearInputMapping(inp.name)}
                        disabled={!current}
                        data-testid={`button-script-input-clear-${inp.name}`}
                      >
                        Clear
                      </Button>
                    </div>
                  </div>

                  <FormulaAwareStringInput
                    value={current}
                    onChange={(v) => handleSetInputMapping(inp.name, v)}
                    availableData={pickableTemplateFields}
                    singleLine
                    placeholderTemplate="{{nodes.some_node.output.resultset_id}}"
                    placeholderFormula={'path(input.body, "resultset_id")'}
                    error={current.trim() && !check.ok ? (check as { error?: string }).error : undefined}
                    data-testid={`input-script-input-mapping-${inp.name}`}
                  />
                </div>
              );
            })}
          </div>
        </div>
      )}

      {selectedScript && scriptOutputs.length > 0 && (
        <div className="rounded-md border p-3 space-y-2">
          <div>
            <div className="text-sm font-medium">Outputs</div>
            <p className="text-xs text-muted-foreground">
              Declared outputs for this script (used for downstream mapping/autocomplete when available).
            </p>
          </div>
          <div className="space-y-1">
            {scriptOutputs.map((o) => (
              <div key={o.name} className="flex items-center justify-between gap-2 rounded border bg-muted/20 px-2 py-1">
                <div className="min-w-0">
                  <code className="text-xs font-mono">{o.name}</code>
                  {o.description && (
                    <div className="text-[11px] text-muted-foreground truncate">{o.description}</div>
                  )}
                </div>
                <div className="flex items-center gap-1">
                  {o.type && (
                    <Badge variant="secondary" className="text-[10px]">
                      {o.type}
                    </Badge>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {selectedScript && scriptOutputs.length > 0 && (
        <div className="rounded-md border p-3 space-y-3">
          <div>
            <div className="text-sm font-medium">Output mapping</div>
            <p className="text-xs text-muted-foreground">
              Optionally promote specific script outputs into <code>ctx.*</code> paths (for easier reuse).
              Downstream nodes can always reference this node’s output via <code>nodes.&lt;id&gt;.output.*</code>.
            </p>
          </div>

          <div className="space-y-2">
            {scriptOutputs.map((out) => {
              const current = outputToCtxMapping[out.name] ?? "";
              const ctxCheck = validateCtxPath(current);

              return (
                <div key={out.name} className="rounded-md border bg-muted/20 p-2 space-y-2">
                  <div className="flex items-center justify-between gap-2">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <code className="text-xs font-mono">{out.name}</code>
                        {out.type && <Badge variant="secondary" className="text-[10px]">{out.type}</Badge>}
                      </div>
                      {out.description && (
                        <div className="text-xs text-muted-foreground mt-1">{out.description}</div>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      {Array.isArray(availableData) && ctxFields.length > 0 && (
                        <Popover
                          open={isOutputPickerOpen === out.name}
                          onOpenChange={(open) => setIsOutputPickerOpen(open ? out.name : null)}
                        >
                          <PopoverTrigger asChild>
                            <Button
                              size="sm"
                              variant="outline"
                              className="h-7 px-2 text-xs"
                              data-testid={`button-script-output-pick-${out.name}`}
                            >
                              Pick ctx
                            </Button>
                          </PopoverTrigger>
                          <PopoverContent className="w-[360px] p-0" align="end">
                            <Command>
                              <CommandInput placeholder="Search ctx fields..." className="text-sm" />
                              <CommandList className="max-h-[280px] overflow-y-auto">
                                <CommandEmpty className="text-sm p-2">No ctx fields found.</CommandEmpty>
                                <CommandGroup>
                                  {ctxFields.map((field) => (
                                    <CommandItem
                                      key={field.key}
                                      value={`${field.key} ${field.description || ""}`.toLowerCase()}
                                      onSelect={() => {
                                        handleSetOutputToCtxMapping(out.name, field.key);
                                        setIsOutputPickerOpen(null);
                                      }}
                                      className="flex flex-col items-start gap-0.5"
                                      data-testid={`item-script-output-ctx-${out.name}-${field.key}`}
                                    >
                                      <div className="flex w-full items-center justify-between gap-2">
                                        <code className="text-xs font-mono break-all">{field.key}</code>
                                        <Badge variant="outline" className="text-[10px]">{field.type}</Badge>
                                      </div>
                                      {field.description && (
                                        <div className="text-xs text-muted-foreground">{field.description}</div>
                                      )}
                                    </CommandItem>
                                  ))}
                                </CommandGroup>
                              </CommandList>
                            </Command>
                          </PopoverContent>
                        </Popover>
                      )}
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-7 px-2 text-xs text-muted-foreground"
                        onClick={() => handleClearOutputToCtxMapping(out.name)}
                        disabled={!current}
                        data-testid={`button-script-output-clear-${out.name}`}
                      >
                        Clear
                      </Button>
                    </div>
                  </div>

                  <Input
                    value={current}
                    onChange={(e) => handleSetOutputToCtxMapping(out.name, e.target.value)}
                    placeholder="ctx.some.path"
                    className={cn("text-sm font-mono", current && !ctxCheck.ok ? "border-destructive" : "")}
                    data-testid={`input-script-output-to-ctx-${out.name}`}
                  />
                  {current && !ctxCheck.ok && (
                    <div className="text-xs text-destructive">{ctxCheck.error}</div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {hasLegacyInlineConfig && !config?.script_id && (
        <div className="space-y-2">
          {legacyInlineLanguage && (
            <div className="space-y-1">
              <Label className="text-[11px] uppercase tracking-wide">Legacy language</Label>
              <Input value={legacyInlineLanguage} readOnly className="text-sm" />
            </div>
          )}
          {legacyInlineCode && (
            <div className="space-y-1">
              <div className="flex items-center justify-between gap-2">
                <Label className="text-[11px] uppercase tracking-wide">Legacy code (read-only)</Label>
                <Button
                  size="sm"
                  variant="outline"
                  className="h-7 px-2 text-xs"
                  onClick={() => {
                    navigator.clipboard.writeText(legacyInlineCode);
                    toast({ title: "Legacy code copied" });
                  }}
                >
                  <Copy className="h-3.5 w-3.5 mr-2" />
                  Copy
                </Button>
              </div>
              <Textarea value={legacyInlineCode} readOnly rows={8} className="text-xs font-mono" />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// AI Agent Selector Form
function AgentForm({ config, onConfigChange, dataNodes = [], availableData = [] }: NodeConfigFormProps) {
  const { agents, isLoading, isFetching, error, refresh } = useAgentData();
  const [isSelectorOpen, setIsSelectorOpen] = useState(false);
  const [isFieldPickerOpen, setIsFieldPickerOpen] = useState(false);
  const promptRef = useRef<HTMLTextAreaElement | null>(null);
  const promptCursorRef = useRef<{ start: number; end: number }>({ start: 0, end: 0 });

  const selectedAgent = useMemo(() => {
    if (!config?.agent_id) return undefined;
    return agents.find((agent) => agent.id === config.agent_id);
  }, [config?.agent_id, agents]);

  const handleSelectAgent = (agentId: string) => {
    const agent = agents.find((entry) => entry.id === agentId);
    if (!agent) return;
    setIsSelectorOpen(false);
    onConfigChange({
      ...config,
      agent_id: agent.id,
      agent_name: agent.name,
      agent_model: agent.model,
    });
  };

  const availableAgents = useMemo(() => {
    // /api/v1/settings/agents/ returns AgentConfiguration-ish objects (with status).
    // In the Flow Builder we allow active + draft.
    const list = Array.isArray(agents) ? agents : [];
    return list.filter((a: any) => {
      const statusOk = a.status === "active" || a.status === "draft" || !a.status;
      // Only Flow-channel agents should appear in the Flow Builder Agent node
      const channel = String(a.channel || "").toLowerCase().trim();
      const channelOk = channel === "flows";
      return statusOk && channelOk;
    });
  }, [agents]);

  // Backend expects `input_message`; we also keep `prompt_template` synchronized for backward compatibility.
  const inputMessage =
    (config?.input_message as string | undefined) ||
    (config?.prompt_template as string | undefined) ||
    "";

  // Allowed placeholders for Agent input_message: only {{ctx.*}}
  // Always allow ctx.workflow.input_as_text (raw incoming message), even if not in ctx_schema.
  const agentPlaceholderFields = useMemo(() => {
    const base = (availableData || []).filter((f) => String(f?.key || "").startsWith("ctx."));
    const extras: AvailableDataField[] = [
      {
        key: "ctx.workflow.input_as_text",
        type: "string",
        source: "Workflow",
        description: "Raw incoming message as text",
      },
    ];
    const seen = new Set<string>();
    const out: AvailableDataField[] = [];
    for (const f of [...extras, ...base]) {
      const k = String(f?.key || "");
      if (!k || seen.has(k)) continue;
      seen.add(k);
      out.push(f);
    }
    return out;
  }, [availableData]);

  const handleInsertFieldIntoPrompt = (fieldKey: string) => {
    const currentText = inputMessage;
    const { start, end } = promptCursorRef.current || { start: currentText.length, end: currentText.length };
    const token = `{{ ${fieldKey} }}`;
    const before = currentText.slice(0, start);
    const after = currentText.slice(end);
    const next = before + token + after;
    const nextCursor = start + token.length;

    onConfigChange({ ...config, input_message: next, prompt_template: next });
    setIsFieldPickerOpen(false);

    // restore cursor after react updates
    setTimeout(() => {
      const el = promptRef.current;
      if (!el) return;
      el.focus();
      el.setSelectionRange(nextCursor, nextCursor);
    }, 0);
  };

  const toggleFieldPicker = (open: boolean) => {
    if (open) {
      const el = promptRef.current;
      if (el) {
        promptCursorRef.current = {
          start: el.selectionStart ?? inputMessage.length,
          end: el.selectionEnd ?? inputMessage.length,
        };
      }
    }
    setIsFieldPickerOpen(open);
  };

  return (
    <div className="space-y-4">
      {dataNodes.length > 0 && (
        <DataVisualizer 
          data={dataNodes} 
          title="Flow Data Available Here"
          compact={true}
          maxHeight="250px"
        />
      )}
      
      <div className="space-y-2">
        <div className="flex items-center justify-between gap-2">
          <div>
            <Label className="text-xs">Input message</Label>
            <p className="text-xs text-muted-foreground">
              Use Template <code>{"{{ ctx.* }}"}</code> or Formula (Zap). For the raw incoming message use{" "}
              <code>{"{{ ctx.workflow.input_as_text }}"}</code>.
            </p>
          </div>
        </div>
        <FormulaAwareStringInput
          value={inputMessage}
          onChange={(v) => onConfigChange({ ...config, input_message: v, prompt_template: v })}
          availableData={agentPlaceholderFields}
          singleLine={false}
          placeholderTemplate="Type the message you want to send to the agent..."
          placeholderFormula={'coalesce(ctx.workflow.input_as_text, "Hello")'}
          data-testid="textarea-agent-prompt-template"
        />
      </div>

      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between gap-2">
          <div>
            <Label className="text-xs">Agent</Label>
            <p className="text-xs text-muted-foreground">Select a configured agent to use in this step.</p>
          </div>
          <Button
            variant="outline"
            size="icon"
            className="h-8 w-8"
            onClick={() => refresh()}
            disabled={isFetching}
            data-testid="button-refresh-agents"
          >
            {isFetching ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
            <span className="sr-only">Refresh agents</span>
          </Button>
        </div>
        <Popover open={isSelectorOpen} onOpenChange={setIsSelectorOpen}>
          <PopoverTrigger asChild>
            <Button
              variant="outline"
              role="combobox"
              aria-expanded={isSelectorOpen}
              className="w-full justify-between"
              data-testid="button-select-agent"
            >
              <span className="truncate text-left text-sm">
                {selectedAgent?.name || config.agent_id || "Select agent"}
              </span>
              <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-[320px] p-0" align="start">
            <Command>
              <CommandInput placeholder="Search agents..." />
              <CommandList>
                <CommandEmpty>
                  {isLoading ? "Loading agents..." : "No agents available."}
                </CommandEmpty>
                <CommandGroup>
                  <ScrollArea className="max-h-64">
                    {availableAgents.map((agent) => (
                      <CommandItem
                        key={agent.id}
                        value={agent.id}
                        onSelect={(value) => handleSelectAgent(value)}
                        className="flex flex-col items-start gap-0.5"
                        data-testid={`option-agent-${agent.id}`}
                      >
                        <span className="text-sm font-medium">{agent.name}</span>
                        {agent.model && (
                          <span className="text-xs text-muted-foreground">{agent.model}</span>
                        )}
                      </CommandItem>
                    ))}
                  </ScrollArea>
                </CommandGroup>
              </CommandList>
            </Command>
          </PopoverContent>
        </Popover>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-md border bg-background/50 p-2">
          <div className="flex items-center justify-between gap-2">
            <Label className="text-xs">Reuse session</Label>
            <Switch
              checked={config.use_flow_session !== false}
              onCheckedChange={(checked) => onConfigChange({ ...config, use_flow_session: checked })}
              data-testid="switch-agent-use-flow-session"
            />
          </div>
          <p className="text-[11px] text-muted-foreground mt-1">
            When enabled, the agent session is persisted per FlowExecution.
          </p>
        </div>

        <div className="rounded-md border bg-background/50 p-2">
          <div className="flex items-center justify-between gap-2">
            <Label className="text-xs">Include chat history</Label>
            <Switch
              checked={config.include_chat_history !== false}
              onCheckedChange={(checked) => onConfigChange({ ...config, include_chat_history: checked })}
              data-testid="switch-agent-include-chat-history"
            />
          </div>
          <p className="text-[11px] text-muted-foreground mt-1">
            When enabled, previous turns in the session are sent to the agent.
          </p>
        </div>
      </div>

      <div className="space-y-2">
        <Label className="text-xs">Input role</Label>
        <Select
          value={String(config.input_role || "user")}
          onValueChange={(value) => onConfigChange({ ...config, input_role: value })}
        >
          <SelectTrigger className="text-sm">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="user">user</SelectItem>
            <SelectItem value="system">system</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>Agent service error</AlertTitle>
          <AlertDescription className="text-xs">{error}</AlertDescription>
        </Alert>
      )}

      {selectedAgent ? (
        <div className="rounded-md border bg-muted/40 p-3 text-xs space-y-2">
          <div className="flex flex-wrap items-center gap-2 text-xs font-medium">
            <span>{selectedAgent.name}</span>
            {selectedAgent.model && (
              <Badge variant="secondary" className="text-[10px] uppercase tracking-wide">
                {selectedAgent.model}
              </Badge>
            )}
            {selectedAgent.status && (
              <Badge variant="outline" className="text-[10px] capitalize">
                {selectedAgent.status}
              </Badge>
            )}
          </div>
          {selectedAgent.description && (
            <p className="text-muted-foreground">{selectedAgent.description}</p>
          )}
          {selectedAgent.tools && selectedAgent.tools.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {selectedAgent.tools.map((tool) => (
                <Badge key={tool} variant="secondary" className="text-[10px]">
                  {tool}
                </Badge>
              ))}
            </div>
          )}
        </div>
      ) : (
        <p className="text-xs text-muted-foreground">Choose an agent to see its configuration.</p>
      )}
    </div>
  );
}

// Webhook Form
function WebhookForm({ config, onConfigChange, dataNodes = [] }: NodeConfigFormProps) {
  const { webhooks, isLoading, isFetching, error, refresh } = useWebhookData();
  const { data: handlers = [] } = useWebhookHandlers();
  const { toast } = useToast();
  const [isSelectorOpen, setIsSelectorOpen] = useState(false);

  // Get the flow webhook handler path from handlers API
  const flowHandlerPath = useMemo(() => {
    const flowHandler = handlers.find(h => h.name.includes("execute_flow_webhook"));
    // Use the full path from API
    return flowHandler?.path || flowHandler?.name || "";
  }, [handlers]);

  // Filter webhooks to show only flow-compatible ones:
  // - No handler_path (generic webhooks)
  // - Or handler_path contains "execute_flow_webhook"
  // - Or handler_path matches the flowHandlerPath (for newly created webhooks)
  // - Or if flowHandlerPath is empty, show all webhooks (fallback)
  const flowWebhooks = useMemo(() => {
    // If flowHandlerPath is not available yet, show all webhooks
    if (!flowHandlerPath || flowHandlerPath === "") {
      return webhooks;
    }
    
    const filtered = webhooks.filter((webhook) => {
      const handlerPath = webhook.handler_path?.trim() || "";
      
      // Include if no handler_path (generic webhooks or newly created)
      if (!handlerPath || handlerPath === "") return true;
      
      // Include if handler_path contains "execute_flow_webhook"
      if (handlerPath.includes("execute_flow_webhook")) return true;
      
      // Include if handler_path matches the current flowHandlerPath (for newly created)
      if (handlerPath === flowHandlerPath) return true;
      
      // Also check if handler_path matches handler name (some APIs return name instead of path)
      const handlerName = handlers.find(h => h.path === flowHandlerPath || h.name === flowHandlerPath)?.name;
      if (handlerName && handlerPath.includes(handlerName)) return true;
      
      return false;
    });
    
    // Debug logging - show detailed information in expandable format
    if (webhooks.length > 0) {
      const excluded = webhooks.filter(w => !filtered.some(f => f.id === w.id));
      console.group(`[WebhookForm] Webhook Filtering (${webhooks.length} total, ${filtered.length} included, ${excluded.length} excluded)`);
      console.log('flowHandlerPath:', flowHandlerPath || '(empty - showing all)');
      console.log('Handlers available:', handlers.length);
      if (handlers.length > 0) {
        console.log('Handler details:', handlers.map(h => `${h.name} -> ${h.path || 'no path'}`));
      }
      if (filtered.length > 0) {
        console.log('✅ INCLUDED webhooks:', filtered.map(w => `${w.name} (handler_path: ${w.handler_path || 'empty'})`));
      }
      if (excluded.length > 0) {
        console.log('❌ EXCLUDED webhooks:', excluded.map(w => `${w.name} (handler_path: ${w.handler_path || 'empty'})`));
        excluded.forEach(w => {
          const handlerPath = w.handler_path?.trim() || "";
          let reason = 'unknown';
          if (!handlerPath) {
            reason = 'no handler_path (should be included - this is a bug!)';
          } else if (flowHandlerPath && handlerPath === flowHandlerPath) {
            reason = 'matches flowHandlerPath (should be included - this is a bug!)';
          } else if (handlerPath.includes("execute_flow_webhook")) {
            reason = 'contains execute_flow_webhook (should be included - this is a bug!)';
          } else {
            reason = `handler_path "${handlerPath}" does not match flowHandlerPath "${flowHandlerPath}"`;
          }
          console.log(`  - ${w.name}: ${reason}`);
        });
      }
      console.groupEnd();
    }
    
    return filtered;
  }, [webhooks, flowHandlerPath, handlers]);

  // Fetch detailed webhook information when a webhook is selected
  const webhookDetailsQuery = useWebhookDetails(config?.webhook_id);
  const webhookDetails = webhookDetailsQuery.data;
  const isFetchingDetails = webhookDetailsQuery.isFetching;
  const webhookDetailsError = webhookDetailsQuery.error;

  // Use detailed webhook data if available, otherwise fall back to list data
  const selectedWebhook = useMemo(() => {
    if (!config?.webhook_id) return undefined;
    
    // Prioritize detailed data from individual endpoint
    if (webhookDetails) {
      return webhookDetails;
    }
    
    // Fallback to list data only if details query hasn't run yet or is loading
    // If there's an error, we don't use list data (per plan requirement)
    if (webhookDetailsError) {
      return undefined; // Don't use list data when there's an error
    }
    
    return flowWebhooks.find((webhook) => webhook.id === config.webhook_id);
  }, [config?.webhook_id, flowWebhooks, webhookDetails, webhookDetailsError]);

  const handleSelectWebhook = (webhookId: string) => {
    const webhook = flowWebhooks.find((entry) => entry.id === webhookId);
    if (!webhook) return;
    setIsSelectorOpen(false);
    // Set webhook_id first - this will trigger useWebhookDetails to fetch full details
    // The useEffect below will update config with expected_schema when details arrive
    onConfigChange({
      ...config,
      webhook_id: webhook.id,
      webhook_name: webhook.name,
      webhook_description: webhook.description,
      webhook_url: webhook.url,
      handler_path: flowHandlerPath,
      expected_content_type: webhook.expected_content_type,
      // Don't set expected_schema here - wait for details query
    });
  };

  // Update config with expected_schema when webhook details are fetched
  useEffect(() => {
    if (webhookDetails && config?.webhook_id === webhookDetails.id) {
      // Only update if expected_schema is different to avoid unnecessary updates
      const currentSchema = config.expected_schema;
      const newSchema = webhookDetails.expected_schema;
      if (currentSchema !== newSchema) {
        onConfigChange({
          ...config,
          expected_schema: newSchema,
        });
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [webhookDetails?.expected_schema, webhookDetails?.id, config?.webhook_id]);

  // Handle refresh on-demand
  const handleRefreshWebhookDetails = async () => {
    if (!config?.webhook_id) return;
    try {
      await webhookDetailsQuery.refetch();
      // Also refresh the webhooks list to keep it in sync
      refresh();
      toast({
        title: "Webhook updated",
        description: "Webhook details have been refreshed.",
      });
    } catch (err) {
      toast({
        title: "Refresh failed",
        description: err instanceof Error ? err.message : "Failed to refresh webhook details",
        variant: "destructive",
      });
    }
  };

  const expectedSchemaForPreview = useMemo(() => {
    const schema = (selectedWebhook as any)?.expected_schema ?? (config as any)?.expected_schema ?? null;
    if (!schema) return null;
    if (typeof schema === "string") {
      try {
        return JSON.parse(schema);
      } catch {
        return schema;
      }
    }
    return schema;
  }, [config, selectedWebhook]);

  const expectedSchemaTextForPreview = useMemo(() => {
    if (!expectedSchemaForPreview) return "";
    if (typeof expectedSchemaForPreview === "string") return expectedSchemaForPreview;
    try {
      return JSON.stringify(expectedSchemaForPreview, null, 2);
    } catch {
      return String(expectedSchemaForPreview);
    }
  }, [expectedSchemaForPreview]);

  return (
    <div className="space-y-4">
      {dataNodes.length > 0 && (
        <DataVisualizer 
          data={dataNodes} 
          title="Flow Data Available Here"
          compact={true}
          maxHeight="250px"
        />
      )}
      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between gap-2">
          <div>
            <Label className="text-xs">Webhook</Label>
            <p className="text-xs text-muted-foreground">
              Select an existing webhook. Manage webhooks in{" "}
              <a href="/workflows/webhooks" target="_blank" rel="noreferrer" className="text-primary hover:underline">
                Webhooks
              </a>
              .
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="icon"
              className="h-8 w-8"
              onClick={() => refresh()}
              disabled={isFetching}
            >
              {isFetching ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
              <span className="sr-only">Refresh webhooks</span>
            </Button>
          </div>
        </div>
        <Popover open={isSelectorOpen} onOpenChange={setIsSelectorOpen}>
          <PopoverTrigger asChild>
            <Button
              variant="outline"
              role="combobox"
              aria-expanded={isSelectorOpen}
              className="w-full justify-between"
            >
              <span className="truncate text-left text-sm">
                {selectedWebhook?.name || config.webhook_id || "Select webhook"}
              </span>
              <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-[320px] p-0" align="start">
            <Command>
              <CommandInput placeholder="Search webhooks..." />
              <CommandList 
                className="max-h-[300px] overflow-y-auto"
                onWheel={(e) => {
                  // Ensure wheel events scroll the list
                  const target = e.currentTarget;
                  if (target.scrollHeight > target.clientHeight) {
                    target.scrollTop += e.deltaY;
                    e.preventDefault();
                  }
                }}
                style={{ 
                  overscrollBehavior: 'contain',
                  WebkitOverflowScrolling: 'touch'
                }}
              >
                <CommandEmpty>
                  {isLoading ? "Loading webhooks..." : "No flow-compatible webhooks available."}
                </CommandEmpty>
                <CommandGroup>
                  {flowWebhooks.map((webhook) => {
                    // Include both ID and name in value for better search/filtering
                    const searchValue = `${webhook.id} ${webhook.name || ''} ${webhook.url || ''}`.toLowerCase();
                    return (
                      <CommandItem
                        key={webhook.id}
                        value={searchValue}
                        onSelect={() => handleSelectWebhook(webhook.id)}
                        className="flex flex-col items-start gap-0.5"
                      >
                        <span className="text-sm font-medium">{webhook.name || webhook.id}</span>
                        {webhook.url && (
                          <span className="text-xs text-muted-foreground truncate w-full">{webhook.url}</span>
                        )}
                      </CommandItem>
                    );
                  })}
                </CommandGroup>
              </CommandList>
            </Command>
          </PopoverContent>
        </Popover>
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>Webhook service error</AlertTitle>
          <AlertDescription className="text-xs">{error}</AlertDescription>
        </Alert>
      )}

      {config?.webhook_id ? (
        <>
          {webhookDetailsError ? (
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertTitle>Failed to load webhook details</AlertTitle>
              <AlertDescription className="text-xs">
                {webhookDetailsError instanceof Error 
                  ? webhookDetailsError.message 
                  : "Could not fetch webhook details. Please try refreshing."}
              </AlertDescription>
            </Alert>
          ) : selectedWebhook ? (
        <div className="rounded-md border bg-muted/40 p-3 text-xs space-y-2">
              <div className="flex items-start justify-between gap-2">
                <div className="flex-1 flex flex-wrap items-center gap-2 text-xs font-medium">
            <span>{selectedWebhook.name}</span>
            {selectedWebhook.expected_content_type && (
              <Badge variant="secondary" className="text-[10px] uppercase tracking-wide">
                {selectedWebhook.expected_content_type}
              </Badge>
            )}
            {selectedWebhook.handler_path && (
              <Badge variant="outline" className="text-[10px]">
                {selectedWebhook.handler_path}
              </Badge>
            )}
                  {selectedWebhook.expected_schema && (
                    <Badge variant="default" className="text-[10px]">
                      Schema defined
              </Badge>
            )}
          </div>
                <div className="flex items-center gap-1">
                  <Button
                    size="icon"
                    variant="ghost"
                    className="h-6 w-6 flex-shrink-0"
                    onClick={handleRefreshWebhookDetails}
                    disabled={isFetchingDetails}
                    title="Refresh webhook details"
                    data-testid="button-refresh-webhook-details"
                  >
                    {isFetchingDetails ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <RefreshCw className="h-3.5 w-3.5" />
                    )}
                  </Button>
          {selectedWebhook.url && (
              <Button
                size="icon"
                variant="ghost"
                className="h-6 w-6 flex-shrink-0"
                onClick={() => {
                  navigator.clipboard.writeText(selectedWebhook.url || "");
                  toast({ title: "Webhook URL copied" });
                }}
                data-testid="button-copy-webhook-url"
              >
                <Copy className="h-3.5 w-3.5" />
              </Button>
                  )}
            </div>
              </div>
              {selectedWebhook.description && (
                <p className="text-muted-foreground">{selectedWebhook.description}</p>
              )}
              {selectedWebhook.url && (
                <p className="font-mono text-[11px] break-all">{selectedWebhook.url}</p>
              )}
              {expectedSchemaForPreview && (
                <Collapsible>
                  <CollapsibleTrigger asChild>
                    <Button variant="ghost" size="sm" className="h-7 px-2 text-xs -ml-2">
                      View expected schema
                    </Button>
                  </CollapsibleTrigger>
                  <CollapsibleContent className="pt-2">
                    <div className="flex items-center justify-between gap-2 mb-2">
                      <p className="text-[11px] text-muted-foreground">
                        Read-only preview (not exposed as available data on Trigger nodes).
                      </p>
                      <Button
                        size="icon"
                        variant="ghost"
                        className="h-6 w-6"
                        onClick={() => {
                          navigator.clipboard.writeText(expectedSchemaTextForPreview);
                          toast({ title: "Schema copied" });
                        }}
                        disabled={!expectedSchemaTextForPreview}
                        title="Copy schema"
                        data-testid="button-copy-webhook-expected-schema"
                      >
                        <Copy className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                    <pre className="text-xs bg-muted/50 p-2 rounded border overflow-x-auto max-h-[240px] overflow-y-auto">
                      {expectedSchemaTextForPreview}
                    </pre>
                  </CollapsibleContent>
                </Collapsible>
              )}
              {isFetchingDetails && !webhookDetails && (
                <div className="flex items-center gap-2 text-muted-foreground">
                  <Loader2 className="h-3 w-3 animate-spin" />
                  <span>Loading webhook details...</span>
                </div>
          )}
        </div>
          ) : (
            <div className="rounded-md border bg-muted/40 p-3 text-xs">
              <div className="flex items-center gap-2 text-muted-foreground">
                {isFetchingDetails ? (
                  <>
                    <Loader2 className="h-3 w-3 animate-spin" />
                    <span>Loading webhook details...</span>
                  </>
                ) : (
                  <span>Webhook selected but details not available.</span>
                )}
              </div>
            </div>
          )}
        </>
      ) : (
        <p className="text-xs text-muted-foreground">Choose a webhook to see connection details.</p>
      )}
    </div>
  );
}

// Normalize Form (logic_normalize) - defines internal ctx contract
function NormalizeForm({ config, onConfigChange, availableData = [] }: NodeConfigFormProps) {
  const mappings: Array<{
    ctx_path?: string;
    source_path?: string;
    type?: string;
    required?: boolean;
    default?: any;
  }> = Array.isArray((config as any).mappings) ? (config as any).mappings : [];

  const failOnMissingRequired = (config as any).fail_on_missing_required ?? true;

  const allowedTypeOptions = ["string", "number", "integer", "boolean", "object", "array"] as const;

  const sourceOptions = useMemo(() => {
    // Only allow: input.body.*, nodes.<id>.output.*, config.*
    return (availableData || []).filter((f) => {
      const key = f.key || "";
      if (key.includes("[") || key.includes("]") || key.includes("[]")) return false;
      return key.startsWith("input.body.") || key === "input.body" || key.startsWith("nodes.") || key.startsWith("config.");
    });
  }, [availableData]);

  const updateMapping = (idx: number, patch: Record<string, any>) => {
    const next = mappings.map((m, i) => (i === idx ? { ...m, ...patch } : m));
    onConfigChange({ ...config, mappings: next });
  };

  const addMapping = () => {
    const next = [
      ...mappings,
      {
        ctx_path: "",
        source_path: "",
        type: "string",
        required: true,
        default: null,
      },
    ];
    onConfigChange({ ...config, mappings: next });
  };

  const removeMapping = (idx: number) => {
    const next = mappings.filter((_, i) => i !== idx);
    onConfigChange({ ...config, mappings: next });
  };

  return (
    <div className="space-y-4">
      <Alert>
        <AlertTitle>Normalize (obligatorio)</AlertTitle>
        <AlertDescription className="text-xs">
          Este nodo define el contrato interno del flow (<code>ctx.*</code>). Mapea desde{" "}
          <code>input.body.*</code>, <code>nodes.&lt;id&gt;.output.*</code> o <code>config.*</code> hacia{" "}
          <code>ctx.*</code>.
        </AlertDescription>
      </Alert>

      <div className="flex items-center gap-2 p-2 bg-muted rounded-md">
        <Switch
          checked={Boolean(failOnMissingRequired)}
          onCheckedChange={(checked) => onConfigChange({ ...config, fail_on_missing_required: checked })}
        />
        <div className="flex-1">
          <Label className="text-xs font-medium cursor-pointer">Fail on missing required fields</Label>
          <p className="text-xs text-muted-foreground">
            Si una key marcada como <code>required</code> falta en el runtime, el flow falla.
          </p>
        </div>
      </div>

      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <div>
            <Label className="text-xs">Mappings</Label>
            <p className="text-xs text-muted-foreground">
              <code>ctx_path</code> debe ser <code>ctx.&lt;seg&gt;.&lt;seg&gt;...</code> (segmentos: <code>[A-Za-z0-9_-]</code>).
            </p>
          </div>
          <Button size="sm" variant="outline" onClick={addMapping} data-testid="button-normalize-add-mapping">
            <Plus className="h-4 w-4 mr-2" /> Add mapping
          </Button>
        </div>

        {mappings.length === 0 ? (
          <div className="rounded-md border bg-muted/30 p-3 text-xs text-muted-foreground">
            No mappings configured yet. Add at least one mapping to define <code>ctx.*</code>.
          </div>
        ) : (
          <div className="space-y-2">
            {mappings.map((m, idx) => {
              const ctxPath = (m.ctx_path ?? "").toString();
              const sourcePath = (m.source_path ?? "").toString();

              const ctxCheck = validateCtxPath(ctxPath);
              const sourceCheck = validateNormalizeSourcePath(sourcePath);

              const type = (m.type ?? "string").toString();
              const required = m.required ?? true;

              return (
                <div key={idx} className="rounded-md border p-3 space-y-3">
                  <div className="flex items-start justify-between gap-2">
                    <div className="text-xs font-medium">Mapping #{idx + 1}</div>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8 text-muted-foreground"
                      onClick={() => removeMapping(idx)}
                      title="Remove mapping"
                      data-testid={`button-normalize-remove-mapping-${idx}`}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-1">
                      <Label className="text-[11px] uppercase tracking-wide">ctx_path</Label>
                      <Input
                        value={ctxPath}
                        onChange={(e) => updateMapping(idx, { ctx_path: e.target.value })}
                        placeholder="ctx.event.tipo_nombre"
                        className={cn("text-sm font-mono", !ctxCheck.ok && ctxPath.trim() ? "border-destructive" : "")}
                        data-testid={`input-normalize-ctx-path-${idx}`}
                      />
                      {!ctxCheck.ok && ctxPath.trim() && (
                        <p className="text-xs text-destructive">{ctxCheck.reason}</p>
                      )}
                    </div>

                    <div className="space-y-1">
                      <div className="flex items-center justify-between gap-2">
                        <Label className="text-[11px] uppercase tracking-wide">source_path</Label>
                        {sourceOptions.length > 0 && (
                          <Popover>
                            <PopoverTrigger asChild>
                              <Button
                                variant="ghost"
                                size="sm"
                                className="h-6 px-2 text-xs text-muted-foreground"
                                data-testid={`button-normalize-pick-source-${idx}`}
                              >
                                <Plus className="h-3 w-3 mr-1" />
                                Pick
                              </Button>
                            </PopoverTrigger>
                            <PopoverContent className="w-[360px] p-0" align="end">
                              <Command>
                                <CommandInput placeholder="Search source paths..." className="text-sm" />
                                <CommandList className="max-h-[300px] overflow-y-auto">
                                  <CommandEmpty className="text-sm p-2">No fields found.</CommandEmpty>
                                  <CommandGroup>
                                    {sourceOptions.map((field) => (
                                      <CommandItem
                                        key={field.key}
                                        value={field.key}
                                        onSelect={() => updateMapping(idx, { source_path: field.key })}
                                        className="flex flex-col items-start gap-0.5"
                                      >
                                        <div className="flex w-full items-center justify-between gap-2">
                                          <code className="text-sm font-mono">{field.key}</code>
                                          <Badge variant="outline" className="text-[10px]">
                                            {field.type}
                                          </Badge>
                                        </div>
                                        {field.description && (
                                          <p className="text-xs text-muted-foreground">{field.description}</p>
                                        )}
                                      </CommandItem>
                                    ))}
                                  </CommandGroup>
                                </CommandList>
                              </Command>
                            </PopoverContent>
                          </Popover>
                        )}
                      </div>
                      <Input
                        value={sourcePath}
                        onChange={(e) => updateMapping(idx, { source_path: e.target.value })}
                        placeholder="input.body.values.tipo_nombre"
                        className={cn("text-sm font-mono", !sourceCheck.ok && sourcePath.trim() ? "border-destructive" : "")}
                        data-testid={`input-normalize-source-path-${idx}`}
                      />
                      {!sourceCheck.ok && sourcePath.trim() && (
                        <p className="text-xs text-destructive">{sourceCheck.reason}</p>
                      )}
                    </div>
                  </div>

                  <div className="grid grid-cols-3 gap-3 items-end">
                    <div className="space-y-1">
                      <Label className="text-[11px] uppercase tracking-wide">type</Label>
                      <Select
                        value={allowedTypeOptions.includes(type as any) ? type : "string"}
                        onValueChange={(value) => updateMapping(idx, { type: value })}
                      >
                        <SelectTrigger className="text-sm" data-testid={`select-normalize-type-${idx}`}>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {allowedTypeOptions.map((opt) => (
                            <SelectItem key={opt} value={opt}>
                              {opt}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>

                    <div className="space-y-1">
                      <Label className="text-[11px] uppercase tracking-wide">required</Label>
                      <div className="flex items-center gap-2">
                        <Switch
                          checked={Boolean(required)}
                          onCheckedChange={(checked) => updateMapping(idx, { required: checked })}
                          data-testid={`switch-normalize-required-${idx}`}
                        />
                        <span className="text-xs text-muted-foreground">{required ? "true" : "false"}</span>
                      </div>
                    </div>

                    <div className="space-y-1">
                      <Label className="text-[11px] uppercase tracking-wide">default</Label>
                      <FormulaAwareStringInput
                        value={m.default === null || m.default === undefined ? "" : String(m.default)}
                        onChange={(v) => updateMapping(idx, { default: v === "" ? null : v })}
                        availableData={availableData}
                        singleLine
                        placeholderTemplate="{{ctx.some_field}}"
                        placeholderFormula={'coalesce(ctx.some_field, "default")'}
                        className="text-sm font-mono"
                        data-testid={`input-normalize-default-${idx}`}
                      />
                      <p className="text-[11px] text-muted-foreground">Empty → null. Template or formula (Zap) supported.</p>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

// Condition/Branch Form
function BranchForm({ config, onConfigChange, availableData = [], hints, scope }: NodeConfigFormProps) {
  const normalizedConfig = useMemo(() => normalizeBranchConfig(config), [config]);
  const [hintsOpen, setHintsOpen] = useState(true);
  const [openFieldPickers, setOpenFieldPickers] = useState<Record<number, boolean>>({});
  const textareaRefs = useMemo<Record<number, HTMLTextAreaElement | null>>(() => ({}), []);
  const cursorPositions = useMemo<Record<number, { start: number; end: number }>>(() => ({}), []);

  const sanitizeOutputName = useCallback((raw: string) => {
    // Output names become ReactFlow handle IDs. Keep them selector-safe.
    const trimmed = String(raw ?? "").trim();
    const underscored = trimmed.replace(/\s+/g, "_");
    const cleaned = underscored.replace(/[^A-Za-z0-9_-]/g, "");
    return cleaned;
  }, []);

  const ensureUniqueOutputName = useCallback(
    (desired: string, taken: Set<string>) => {
      const base = desired || "rule";
      if (!taken.has(base)) return base;
      let i = 2;
      while (taken.has(`${base}_${i}`)) i++;
      return `${base}_${i}`;
    },
    []
  );

  const handleRuleChange = (index: number, key: "name" | "expr", value: string) => {
    // For output names, enforce safe + unique names so edge creation keeps working.
    let nextValue = value;
    if (key === "name") {
      const taken = new Set<string>();
      normalizedConfig.rules.forEach((r, idx) => {
        if (idx === index) return;
        const nm = sanitizeOutputName(r?.name ?? "");
        if (nm) taken.add(nm);
      });
      // Also prevent collision with else output name
      taken.add("else");

      const sanitized = sanitizeOutputName(value);
      const withFallback = sanitized || `rule_${index + 1}`;
      nextValue = ensureUniqueOutputName(withFallback, taken);
    }

    const nextRules = normalizedConfig.rules.map((rule, idx) => {
      if (idx === index) {
        // v2 spec: Ensure id field exists and preserve it
        const ruleId = rule.id || `rule_${idx + 1}_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
        return { 
          ...rule, 
          id: ruleId,
          [key]: nextValue 
        };
      }
      return rule;
    });
    // Only update if the value actually changed
    const currentValue = normalizedConfig.rules[index]?.[key];
    if (currentValue !== nextValue) {
    onConfigChange({ ...normalizedConfig, rules: nextRules });
    }
  };

  const handleAddRule = () => {
    const nextIndex = normalizedConfig.rules.length + 1;
    const ruleId = `rule_${nextIndex}_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    const nextRules = [
      ...normalizedConfig.rules,
      { id: ruleId, name: `rule_${nextIndex}`, expr: "True" },
    ];
    onConfigChange({ ...normalizedConfig, rules: nextRules });
  };

  const handleRemoveRule = (index: number) => {
    if (normalizedConfig.rules.length <= 1) return;
    const nextRules = normalizedConfig.rules.filter((_, idx) => idx !== index);
    onConfigChange({ ...normalizedConfig, rules: nextRules });
  };

  const handleModeChange = (mode: "first" | "all") => {
    onConfigChange({ ...normalizedConfig, mode });
  };
  
  const derivedOutputs = useMemo(() => deriveBranchOutputs(normalizedConfig), [normalizedConfig]);

  const handleInsertField = (index: number, fieldKey: string) => {
    const currentExpr = normalizedConfig.rules[index]?.expr || "";
    const { start, end } = cursorPositions[index] || { start: currentExpr.length, end: currentExpr.length };
    
    // Insert at cursor position
    const before = currentExpr.slice(0, start);
    const after = currentExpr.slice(end);
    const newExpr = before + fieldKey + after;
    const newCursorPos = start + fieldKey.length;
    
    handleRuleChange(index, "expr", newExpr);
    setOpenFieldPickers((prev) => ({ ...prev, [index]: false }));
    
    // Restore focus and set cursor position after state update
    setTimeout(() => {
      const textarea = textareaRefs[index];
      if (textarea) {
        textarea.focus();
        textarea.setSelectionRange(newCursorPos, newCursorPos);
      }
    }, 0);
  };

  const toggleFieldPicker = (index: number, open: boolean) => {
    if (open) {
      // Save cursor position when opening picker
      const textarea = textareaRefs[index];
      if (textarea) {
        cursorPositions[index] = {
          start: textarea.selectionStart ?? 0,
          end: textarea.selectionEnd ?? 0,
        };
      }
    }
    setOpenFieldPickers((prev) => ({ ...prev, [index]: open }));
  };

  // For sandboxed control-flow, autocomplete must offer ONLY ctx.* (from ctx_schema).
  const flatAvailableData = useMemo(() => {
    return (availableData || []).filter((f) => (f.key || "").startsWith("ctx."));
  }, [availableData]);

  // Check if hints have content
  const hasHints = hints && (
    hints.tips ||
    (hints.expression_examples && hints.expression_examples.length > 0) ||
    (hints.use_cases && hints.use_cases.length > 0)
  );

  return (
    <div className="space-y-4">
      {/* Hints Section */}
      {hasHints && (
        <Collapsible open={hintsOpen} onOpenChange={setHintsOpen}>
          <CollapsibleTrigger asChild>
            <Button variant="ghost" size="sm" className="w-full justify-between p-2 h-auto">
              <div className="flex items-center gap-2">
                <Lightbulb className="h-4 w-4 text-amber-500" />
                <span className="text-xs font-medium">Expressions (sandboxed)</span>
              </div>
              <ChevronDown className={cn("h-4 w-4 transition-transform", hintsOpen && "rotate-180")} />
            </Button>
          </CollapsibleTrigger>
          <CollapsibleContent>
            <div className="rounded-md border bg-amber-50/50 dark:bg-amber-950/20 p-3 space-y-3 mt-2">
              {/* Tips */}
              {hints.tips && (
                <div className="space-y-1">
                  <div className="flex items-center gap-1.5 text-xs font-medium text-amber-800 dark:text-amber-300">
                    <HelpCircle className="h-3.5 w-3.5" />
                    Tips
                  </div>
                  <p className="text-xs text-amber-700 dark:text-amber-400">{hints.tips}</p>
                </div>
              )}

              {/* Expression Examples */}
              {hints.expression_examples && hints.expression_examples.length > 0 && (
                <div className="space-y-2">
                  <div className="flex items-center gap-1.5 text-xs font-medium text-amber-800 dark:text-amber-300">
                    <Code className="h-3.5 w-3.5" />
                    Examples
                  </div>
                  <div className="space-y-1.5">
                    {hints.expression_examples.map((example, idx) => (
                      <div key={idx} className="rounded bg-white/60 dark:bg-black/20 p-2">
                        <code className="text-xs font-mono text-amber-900 dark:text-amber-200 block">{example.expr}</code>
                        <p className="text-[11px] text-amber-600 dark:text-amber-400 mt-1">{example.description}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Use Cases */}
              {hints.use_cases && hints.use_cases.length > 0 && (
                <div className="space-y-1">
                  <div className="text-xs font-medium text-amber-800 dark:text-amber-300">Common Use Cases</div>
                  <ul className="text-xs text-amber-700 dark:text-amber-400 list-disc list-inside space-y-0.5">
                    {hints.use_cases.map((useCase, idx) => (
                      <li key={idx}>{useCase}</li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Quick Reference */}
              <div className="border-t border-amber-200 dark:border-amber-800 pt-2">
                <div className="text-xs font-medium text-amber-800 dark:text-amber-300 mb-1">Quick Reference</div>
                <div className="grid grid-cols-2 gap-1 text-[11px]">
                  <div className="text-amber-700 dark:text-amber-400"><code>==</code> equals</div>
                  <div className="text-amber-700 dark:text-amber-400"><code>!=</code> not equals</div>
                  <div className="text-amber-700 dark:text-amber-400"><code>&gt;</code> <code>&lt;</code> compare</div>
                  <div className="text-amber-700 dark:text-amber-400"><code>and</code> <code>or</code> logic</div>
                  <div className="text-amber-700 dark:text-amber-400"><code>"text"</code> strings need quotes</div>
                  <div className="text-amber-700 dark:text-amber-400"><code>True</code> <code>False</code> booleans</div>
                </div>
              </div>
            </div>
          </CollapsibleContent>
        </Collapsible>
      )}

      {/* Quick Reference when no API hints */}
      {!hasHints && (
        <div className="rounded-md border bg-muted/40 p-3">
          <div className="text-xs font-medium mb-2">Expressions (sandboxed)</div>
          <div className="grid grid-cols-2 gap-1 text-[11px] text-muted-foreground">
            <div><code>ctx.event.tipo_nombre == "AVISO_FECHA_LIMITE"</code></div>
            <div><code>ctx.event.amount &gt; 1000 and ctx.event.status == "active"</code></div>
            <div><code>ctx.event.email is not None</code></div>
            <div><code>True</code> (always match)</div>
          </div>
          <p className="text-[11px] text-muted-foreground mt-2">
            Las expresiones solo pueden leer <code>ctx.*</code> (no <code>payload</code> ni <code>input</code>).
          </p>
        </div>
      )}

      {!scope?.canSeeCtx ? (
        <Alert variant="destructive">
          <AlertTitle>This flow has no contract yet.</AlertTitle>
          <AlertDescription className="text-xs">
            No contract defined. Add a <code>Normalize</code> node upstream to define <code>ctx</code>.
          </AlertDescription>
        </Alert>
      ) : (
        <Alert>
          <AlertTitle>Expressions (sandboxed)</AlertTitle>
          <AlertDescription className="text-xs">
            Las expresiones solo pueden leer <code>ctx.*</code> (no <code>payload</code> ni <code>input</code>).
            {scope?.schemaAvailable === false && (
              <>
                {" "}
                <span className="text-muted-foreground">(schema no disponible)</span>
              </>
            )}
          </AlertDescription>
        </Alert>
      )}

      <div>
        <Label className="text-xs">Branch rules</Label>
        <p className="text-xs text-muted-foreground">
          Evaluate each expression in order. The first rule that resolves to true wins. (ctx-only sandbox)
        </p>
        <p className="text-[11px] text-muted-foreground mt-1">
          Output names become connection handles. Use only <code>A–Z</code>, <code>0–9</code>, <code>_</code>, <code>-</code> (spaces/symbols are auto-cleaned).
        </p>
      </div>

      <div className="space-y-2">
        {normalizedConfig.rules.map((rule, index) => (
          <div key={rule.id || `rule-${index}`} className="rounded-md border p-3 space-y-2">
            <div className="flex items-start gap-2">
              <div className="flex-1">
                <Label className="text-[11px] uppercase tracking-wide">Label</Label>
                <Input
                  value={rule.name}
                  onChange={(e) => handleRuleChange(index, "name", e.target.value)}
                  placeholder={`rule_${index + 1}`}
                  className="text-sm"
                  data-testid={`input-branch-rule-name-${index}`}
                />
              </div>
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 text-muted-foreground"
                onClick={() => handleRemoveRule(index)}
                disabled={normalizedConfig.rules.length <= 1}
                title="Remove rule"
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            </div>
            <div>
              <div className="flex items-center justify-between mb-1">
                <Label className="text-[11px] uppercase tracking-wide">Expression</Label>
                {flatAvailableData.length > 0 && (
                  <Popover
                    open={openFieldPickers[index] || false}
                    onOpenChange={(open) => toggleFieldPicker(index, open)}
                  >
                    <PopoverTrigger asChild>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-6 px-2 text-xs text-muted-foreground"
                        data-testid={`button-insert-field-${index}`}
                      >
                        <Plus className="h-3 w-3 mr-1" />
                        Insert field
                      </Button>
                    </PopoverTrigger>
                    <PopoverContent className="w-[300px] p-0" align="end">
                      <Command>
                        <CommandInput placeholder="Search fields..." className="text-sm" />
                        <CommandList 
                          className="max-h-[300px] overflow-y-auto"
                          onWheel={(e) => {
                            // Ensure wheel events scroll the list
                            const target = e.currentTarget;
                            if (target.scrollHeight > target.clientHeight) {
                              target.scrollTop += e.deltaY;
                              e.preventDefault();
                            }
                          }}
                          style={{ 
                            overscrollBehavior: 'contain',
                            WebkitOverflowScrolling: 'touch'
                          }}
                        >
                          <CommandEmpty className="text-sm p-2">No fields found.</CommandEmpty>
                          <CommandGroup>
                              {flatAvailableData.map((field) => (
                                <CommandItem
                                  key={field.key}
                                  value={field.key}
                                  onSelect={() => handleInsertField(index, field.key)}
                                  className="flex flex-col items-start gap-0.5"
                                >
                                  <div className="flex w-full items-center justify-between gap-2">
                                    <code className="text-sm font-mono">{field.key}</code>
                                    <div className="flex items-center gap-1">
                                      {field.effects?.map((effect, idx) => (
                                        <Badge 
                                          key={idx} 
                                          variant="secondary" 
                                          className={cn(
                                            "text-[9px] px-1",
                                            effect.type === 'validated' && "bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300",
                                            effect.type === 'transformed' && "bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300",
                                            effect.type === 'computed' && "bg-purple-100 text-purple-700 dark:bg-purple-900 dark:text-purple-300"
                                          )}
                                          title={effect.description || `${effect.type} by ${effect.appliedBy}`}
                                        >
                                          {effect.type === 'validated' ? '✓' : effect.type === 'transformed' ? '↻' : effect.type === 'computed' ? '+' : ''}
                                        </Badge>
                                      ))}
                                    </div>
                                  </div>
                                  <div className="flex items-center gap-2 text-xs flex-wrap">
                                    <Badge variant="outline" className="text-[10px]">{field.type}</Badge>
                                    {field.effects && field.effects.length > 0 && (
                                      <span className="text-muted-foreground text-[10px]">
                                        via {field.effects.map(e => e.appliedBy).join(' → ')}
                                      </span>
                                    )}
                                    {field.source && !field.effects?.length && (
                                      <span className="text-muted-foreground">from {field.source}</span>
                                    )}
                                  </div>
                                </CommandItem>
                              ))}
                          </CommandGroup>
                        </CommandList>
                      </Command>
                    </PopoverContent>
                  </Popover>
                )}
              </div>
              <Textarea
                ref={(el) => { textareaRefs[index] = el; }}
                value={rule.expr || ""}
                onChange={(e) => handleRuleChange(index, "expr", e.target.value)}
                placeholder='ctx.event.amount > 1000 and ctx.event.status == "active"'
                rows={2}
                className={cn(
                  "text-sm font-mono",
                  rule.expr && !validateSandboxedExpression(rule.expr).ok ? "border-destructive" : ""
                )}
                data-testid={`textarea-branch-rule-expr-${index}`}
              />
              {rule.expr && !validateSandboxedExpression(rule.expr).ok && (
                <p className="text-xs text-destructive mt-1">
                  {validateSandboxedExpression(rule.expr).errors[0]?.message || "Invalid sandboxed expression"}
                </p>
              )}
            </div>
          </div>
        ))}

        {/* Default output is always present and evaluated last */}
        <div className="rounded-md border border-dashed p-3 bg-muted/30">
          <div className="flex items-center justify-between">
            <div>
              <Label className="text-[11px] uppercase tracking-wide">Default output</Label>
              <p className="text-[11px] text-muted-foreground">
                When no rule matches, flow goes through <code>default</code>.
              </p>
            </div>
            <Badge variant="outline" className="text-[10px]">always on</Badge>
          </div>
        </div>
      </div>

      <Button variant="outline" size="sm" onClick={handleAddRule} className="w-full" data-testid="button-branch-add-rule">
        <Plus className="mr-2 h-4 w-4" /> Add condition
      </Button>

      {/* v2 spec: Mode selector */}
      <div className="space-y-2 rounded-md border p-3">
        <Label className="text-xs">Branch Mode</Label>
        <p className="text-xs text-muted-foreground mb-2">
          How to handle multiple matching rules: "first" stops at first match, "all" evaluates all rules.
        </p>
        <div className="flex gap-2">
          <Button
            variant={normalizedConfig.mode === "first" ? "default" : "outline"}
            size="sm"
            onClick={() => handleModeChange("first")}
            className="flex-1"
            data-testid="button-branch-mode-first"
          >
            First Match
          </Button>
          <Button
            variant={normalizedConfig.mode === "all" ? "default" : "outline"}
            size="sm"
            onClick={() => handleModeChange("all")}
            className="flex-1"
            data-testid="button-branch-mode-all"
          >
            All Matches
          </Button>
        </div>
      </div>

      <div className="space-y-2 rounded-md border p-3">
        <div className="flex items-center justify-between gap-2">
          <div>
            <Label className="text-xs">Else path</Label>
            <p className="text-xs text-muted-foreground">
              Optional fallback output when no rule matches. Enable it to get an <code>else</code> output handle you can connect.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Switch
              checked={normalizedConfig.else === "else"}
              onCheckedChange={(enabled) =>
                onConfigChange({
                  ...normalizedConfig,
                  else: enabled ? "else" : undefined,
                })
              }
              data-testid="switch-branch-else-enabled"
            />
            <span className="text-xs text-muted-foreground">Enable</span>
          </div>
        </div>

        {normalizedConfig.else === "else" && (
          <p className="text-[11px] text-muted-foreground">
            Tip: connect the else path by dragging an edge from the <code>else</code> output handle.
          </p>
        )}
      </div>

      <div className="rounded-md border bg-muted/30 p-3">
        <div className="text-xs font-medium mb-2">Outputs you can connect</div>
        <div className="flex flex-wrap gap-1">
          {derivedOutputs.map((o) => (
            <Badge key={o} variant="outline" className="text-[10px] font-mono">
              {o}
            </Badge>
          ))}
        </div>
      </div>
    </div>
  );
}

// Condition Form (logic_condition) - single sandboxed expression
function ConditionForm({ config, onConfigChange, availableData = [], scope }: NodeConfigFormProps) {
  const [isPickerOpen, setIsPickerOpen] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);
  const cursorRef = useRef<{ start: number; end: number }>({ start: 0, end: 0 });

  const expr = (config as any).expr ?? "";
  const exprStr = typeof expr === "string" ? expr : String(expr ?? "");
  const validation = useMemo(() => validateSandboxedExpression(exprStr), [exprStr]);

  const ctxFields = useMemo(() => (availableData || []).filter((f) => (f.key || "").startsWith("ctx.")), [availableData]);

  const handleInsert = (fieldKey: string) => {
    const current = exprStr;
    const { start, end } = cursorRef.current || { start: current.length, end: current.length };
    const next = current.slice(0, start) + fieldKey + current.slice(end);
    onConfigChange({ ...config, expr: next });
    setIsPickerOpen(false);
    const nextCursor = start + fieldKey.length;
    setTimeout(() => {
      const el = inputRef.current;
      if (!el) return;
      el.focus();
      el.setSelectionRange(nextCursor, nextCursor);
    }, 0);
  };

  return (
    <div className="space-y-3">
      {!scope?.canSeeCtx ? (
        <Alert variant="destructive">
          <AlertTitle>This flow has no contract yet.</AlertTitle>
          <AlertDescription className="text-xs">
            No contract defined. Add a <code>Normalize</code> node upstream to define <code>ctx</code>.
          </AlertDescription>
        </Alert>
      ) : (
        <Alert>
          <AlertTitle>Expressions (sandboxed)</AlertTitle>
          <AlertDescription className="text-xs">
            Las expresiones solo pueden leer <code>ctx.*</code> (no <code>payload</code> ni <code>input</code>).
            {scope?.schemaAvailable === false && (
              <>
                {" "}
                <span className="text-muted-foreground">(schema no disponible)</span>
              </>
            )}
          </AlertDescription>
        </Alert>
      )}

      <div className="space-y-1">
        <div className="flex items-center justify-between mb-1">
          <Label className="text-xs">Expression</Label>
          {ctxFields.length > 0 && (
            <Popover
              open={isPickerOpen}
              onOpenChange={(open) => {
                if (open) {
                  const el = inputRef.current;
                  if (el) {
                    cursorRef.current = {
                      start: el.selectionStart ?? exprStr.length,
                      end: el.selectionEnd ?? exprStr.length,
                    };
                  }
                }
                setIsPickerOpen(open);
              }}
            >
              <PopoverTrigger asChild>
                <Button variant="ghost" size="sm" className="h-6 px-2 text-xs text-muted-foreground">
                  <Plus className="h-3 w-3 mr-1" />
                  Insert field
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-[320px] p-0" align="end">
                <Command>
                  <CommandInput placeholder="Search ctx fields..." className="text-sm" />
                  <CommandList className="max-h-[300px] overflow-y-auto">
                    <CommandEmpty className="text-sm p-2">No fields found.</CommandEmpty>
                    <CommandGroup>
                      {ctxFields.map((field) => (
                        <CommandItem key={field.key} value={field.key} onSelect={() => handleInsert(field.key)}>
                          <div className="flex w-full items-center justify-between gap-2">
                            <code className="text-sm font-mono">{field.key}</code>
                            <Badge variant="outline" className="text-[10px]">
                              {field.type}
                            </Badge>
                          </div>
                        </CommandItem>
                      ))}
                    </CommandGroup>
                  </CommandList>
                </Command>
              </PopoverContent>
            </Popover>
          )}
        </div>

        <Textarea
          ref={inputRef}
          value={exprStr}
          onChange={(e) => onConfigChange({ ...config, expr: e.target.value })}
          placeholder='ctx.event.status == "active"'
          rows={2}
          className={cn("text-sm font-mono", exprStr.trim() && !validation.ok ? "border-destructive" : "")}
          data-testid="textarea-condition-expr"
        />

        {exprStr.trim() && !validation.ok && (
          <p className="text-xs text-destructive">{validation.errors[0]?.message || "Invalid sandboxed expression"}</p>
        )}
      </div>
    </div>
  );
}

// While Loop Form (logic_while) - sandboxed expression
function WhileForm({ config, onConfigChange, availableData = [], scope }: NodeConfigFormProps) {
  const [isPickerOpen, setIsPickerOpen] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);
  const cursorRef = useRef<{ start: number; end: number }>({ start: 0, end: 0 });

  const expr = (config as any).expr ?? (config as any).condition ?? "";
  const exprStr = typeof expr === "string" ? expr : String(expr ?? "");
  const validation = useMemo(() => validateSandboxedExpression(exprStr), [exprStr]);

  const ctxFields = useMemo(() => (availableData || []).filter((f) => (f.key || "").startsWith("ctx.")), [availableData]);

  const handleInsert = (fieldKey: string) => {
    const current = exprStr;
    const { start, end } = cursorRef.current || { start: current.length, end: current.length };
    const next = current.slice(0, start) + fieldKey + current.slice(end);
    onConfigChange({ ...config, expr: next });
    setIsPickerOpen(false);
    const nextCursor = start + fieldKey.length;
    setTimeout(() => {
      const el = inputRef.current;
      if (!el) return;
      el.focus();
      el.setSelectionRange(nextCursor, nextCursor);
    }, 0);
  };

  return (
    <div className="space-y-3">
      {!scope?.canSeeCtx ? (
        <Alert variant="destructive">
          <AlertTitle>This flow has no contract yet.</AlertTitle>
          <AlertDescription className="text-xs">
            No contract defined. Add a <code>Normalize</code> node upstream to define <code>ctx</code>.
          </AlertDescription>
        </Alert>
      ) : (
        <Alert>
          <AlertTitle>Expressions (sandboxed)</AlertTitle>
          <AlertDescription className="text-xs">
            Las expresiones solo pueden leer <code>ctx.*</code> (no <code>payload</code> ni <code>input</code>).
            {scope?.schemaAvailable === false && (
              <>
                {" "}
                <span className="text-muted-foreground">(schema no disponible)</span>
              </>
            )}
          </AlertDescription>
        </Alert>
      )}

      <div className="space-y-1">
        <div className="flex items-center justify-between mb-1">
          <Label className="text-xs">Loop condition</Label>
          {ctxFields.length > 0 && (
            <Popover
              open={isPickerOpen}
              onOpenChange={(open) => {
                if (open) {
                  const el = inputRef.current;
                  if (el) {
                    cursorRef.current = {
                      start: el.selectionStart ?? exprStr.length,
                      end: el.selectionEnd ?? exprStr.length,
                    };
                  }
                }
                setIsPickerOpen(open);
              }}
            >
              <PopoverTrigger asChild>
                <Button variant="ghost" size="sm" className="h-6 px-2 text-xs text-muted-foreground">
                  <Plus className="h-3 w-3 mr-1" />
                  Insert field
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-[320px] p-0" align="end">
                <Command>
                  <CommandInput placeholder="Search ctx fields..." className="text-sm" />
                  <CommandList className="max-h-[300px] overflow-y-auto">
                    <CommandEmpty className="text-sm p-2">No fields found.</CommandEmpty>
                    <CommandGroup>
                      {ctxFields.map((field) => (
                        <CommandItem key={field.key} value={field.key} onSelect={() => handleInsert(field.key)}>
                          <div className="flex w-full items-center justify-between gap-2">
                            <code className="text-sm font-mono">{field.key}</code>
                            <Badge variant="outline" className="text-[10px]">
                              {field.type}
                            </Badge>
                          </div>
                        </CommandItem>
                      ))}
                    </CommandGroup>
                  </CommandList>
                </Command>
              </PopoverContent>
            </Popover>
          )}
        </div>

        <Textarea
          ref={inputRef}
          value={exprStr}
          onChange={(e) => onConfigChange({ ...config, expr: e.target.value })}
          placeholder="ctx.loop.should_continue == True"
          rows={2}
          className={cn("text-sm font-mono", exprStr.trim() && !validation.ok ? "border-destructive" : "")}
          data-testid="input-while-condition"
        />

        {exprStr.trim() && !validation.ok && (
          <p className="text-xs text-destructive">{validation.errors[0]?.message || "Invalid sandboxed expression"}</p>
        )}
      </div>

      <div>
        <Label htmlFor="while-max-iterations" className="text-xs">Max Iterations</Label>
        <Input
          id="while-max-iterations"
          type="number"
          min="1"
          value={(config as any).max_iterations || 100}
          onChange={(e) => onConfigChange({ ...config, max_iterations: parseInt(e.target.value) })}
          className="text-sm"
          data-testid="input-while-max-iterations"
        />
      </div>
    </div>
  );
}

// Helper to extract placeholders from template components
function extractPlaceholders(components: any[]): string[] {
  const placeholderSet = new Set<string>();
  const regex = /\{\{(\w+)\}\}/g;

  if (components && Array.isArray(components)) {
    components.forEach((component) => {
      if (component.text) {
        let match;
        while ((match = regex.exec(component.text)) !== null) {
          placeholderSet.add(match[1]);
        }
      }
    });
  }

  // Always include phone_number as the first implicit placeholder
  const result = ["phone_number"];
  // Add extracted placeholders (excluding phone_number if it was in the text)
  placeholderSet.forEach(p => {
    if (p !== "phone_number") {
      result.push(p);
    }
  });

  return result;
}

// WhatsApp Template Form
function WhatsAppTemplateForm({ config, onConfigChange, availableData = [], dataNodes = [] }: NodeConfigFormProps) {
  const { templates, isLoading, isFetching, error, refresh } = useTemplateData();
  const { toast } = useToast();
  const [isSelectorOpen, setIsSelectorOpen] = useState(false);
  const handleCopyTemplateId = () => {
    if (config.template_id) {
      navigator.clipboard.writeText(config.template_id);
      toast({
        description: "Template ID copied to clipboard",
        duration: 2000,
      });
    }
  };

  const selectedTemplate = useMemo(() => {
    if (!templates.length) return undefined;
    return templates.find((template) => template.id === config.template_id) ||
      templates.find((template) => template.name === config.template_name);
  }, [config.template_id, config.template_name, templates]);

  const mapping: Record<string, string> = useMemo(() => {
    return typeof config.mapping === "object" && config.mapping !== null ? config.mapping : {};
  }, [config.mapping]);

  const handleTemplateSelect = (templateId: string) => {
    const template = templates.find((entry) => entry.id === templateId);
    if (!template) return;
    setIsSelectorOpen(false);
    
    // Extract placeholders from template components
    const extractedPlaceholders = extractPlaceholders(template.components || []);
    const nextMapping = extractedPlaceholders.reduce<Record<string, string>>((acc, key) => {
      acc[key] = mapping[key] ?? "";
      return acc;
    }, {});

    onConfigChange({
      ...config,
      template_id: template.id,
      template_name: template.name,
      language: template.language || config.language || "en",
      mapping: nextMapping,
    });
  };

  // Extract placeholders from selected template components
  const placeholders = useMemo(() => {
    return extractPlaceholders(selectedTemplate?.components || []);
  }, [selectedTemplate?.components]);

  const handleMappingChange = (key: string, value: string) => {
    onConfigChange({
      ...config,
      mapping: {
        ...mapping,
        [key]: value,
      },
    });
  };

  return (
    <div className="space-y-4">
      {dataNodes.length > 0 && (
        <DataVisualizer 
          data={dataNodes} 
          title="Flow Data Available Here"
          compact={true}
          maxHeight="250px"
        />
      )}
      <div className="flex items-center justify-between gap-2">
        <div>
          <Label className="text-xs">WhatsApp Template</Label>
          <p className="text-xs text-muted-foreground">Select an approved template from your workspace.</p>
        </div>
        <Button
          variant="outline"
          size="icon"
          className="h-8 w-8"
          onClick={() => refresh()}
          disabled={isFetching}
        >
          {isFetching ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
          <span className="sr-only">Refresh templates</span>
        </Button>
      </div>

      <Popover open={isSelectorOpen} onOpenChange={setIsSelectorOpen}>
        <PopoverTrigger asChild>
          <Button variant="outline" role="combobox" aria-expanded={isSelectorOpen} className="w-full justify-between">
            <span className="truncate text-left text-sm">
              {selectedTemplate?.name || config.template_name || "Select template"}
            </span>
            <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-[340px] p-0" align="start">
          <Command>
            <CommandInput placeholder="Search templates..." />
            <CommandList>
              <CommandEmpty>
                {isLoading ? "Loading templates..." : "No templates available."}
              </CommandEmpty>
              <CommandGroup>
                <ScrollArea className="max-h-72">
                  {templates.map((template) => (
                    <CommandItem
                      key={template.id}
                      value={template.id}
                      onSelect={(value) => handleTemplateSelect(value)}
                      className="flex flex-col items-start gap-1"
                    >
                      <div className="flex w-full items-center justify-between gap-2">
                        <span className="text-sm font-medium">{template.name}</span>
                        <div className="flex items-center gap-1">
                          {template.language && <Badge variant="outline">{template.language}</Badge>}
                          {template.status && (
                            <Badge variant="secondary" className="text-[10px] uppercase">
                              {template.status}
                            </Badge>
                          )}
                        </div>
                      </div>
                      {template.category && (
                        <span className="text-xs text-muted-foreground">{template.category}</span>
                      )}
                    </CommandItem>
                  ))}
                </ScrollArea>
              </CommandGroup>
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>

      {config.template_id && (
        <div className="rounded-md border bg-muted/40 p-3">
          <div className="grid grid-cols-2 gap-4">
            <div className="flex flex-col gap-1">
              <Label className="text-xs text-muted-foreground">Template name (id)</Label>
              <div className="flex items-center gap-2">
                <code className="text-sm font-mono break-all flex-1">
                  {selectedTemplate?.name ? `${selectedTemplate.name} (${config.template_id})` : config.template_id}
                </code>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={handleCopyTemplateId}
                  className="h-8 w-8 flex-shrink-0"
                  data-testid="button-copy-template-id"
                >
                  <Copy className="h-4 w-4" />
                  <span className="sr-only">Copy template ID</span>
                </Button>
              </div>
            </div>
            {(config.language || selectedTemplate?.language) && (
              <div className="flex flex-col gap-1">
                <Label className="text-xs text-muted-foreground">Language Code</Label>
                <code className="text-sm font-mono">{config.language || selectedTemplate?.language}</code>
              </div>
            )}
          </div>
        </div>
      )}

      {error && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>Template service error</AlertTitle>
          <AlertDescription className="text-xs">{error}</AlertDescription>
        </Alert>
      )}

      {selectedTemplate ? (
        <div className="space-y-3">
          <div>
            <Label className="text-xs">Preview</Label>
            <div className="rounded-md border bg-muted/40 p-3 text-xs space-y-2">
              {selectedTemplate.components && selectedTemplate.components.length > 0 ? (
                selectedTemplate.components
                  .filter((component) => component.type !== "footer")
                  .map((component, index) => (
                    <div key={`${component.type}-${index}`}>
                      <p className="font-medium capitalize">{component.type}</p>
                      {component.text && (
                        <p className="text-muted-foreground whitespace-pre-wrap">{component.text}</p>
                      )}
                    </div>
                  ))
              ) : (
                <p className="text-muted-foreground">No preview available for this template.</p>
              )}
            </div>
          </div>

          <div className="space-y-2">
            <Label className="text-xs">Placeholder mapping</Label>
            {placeholders.length > 0 ? (
              <div className="space-y-3">
                {placeholders.map((key) => (
                  <div key={key} className="space-y-1">
                    <Label className="text-[11px] uppercase text-muted-foreground">{key}</Label>
                    <FormulaAwareStringInput
                      value={mapping[key] ?? ""}
                      onChange={(v) => handleMappingChange(key, v)}
                      availableData={availableData}
                      singleLine
                      placeholderTemplate="{{ctx.contact.first_name}}"
                      placeholderFormula={'coalesce(ctx.contact.first_name, "friend")'}
                      data-testid={`input-placeholder-${key}`}
                    />
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs text-muted-foreground">This template has no placeholders.</p>
            )}
          </div>
        </div>
      ) : (
        <p className="text-xs text-muted-foreground">Select a template to configure mappings and preview content.</p>
      )}
    </div>
  );
}

// Event Trigger Form - wraps EventTriggerConfigPanel for registry compatibility
function EventTriggerForm({ config, onConfigChange }: NodeConfigFormProps) {
  const eventConfig: EventTriggerConfig = {
    event_name: config.event_name ?? DEFAULT_EVENT_CONFIG.event_name,
    conditions: config.conditions ?? DEFAULT_EVENT_CONFIG.conditions,
    event_schema: config.event_schema ?? null,
  };

  const handleChange = (newConfig: EventTriggerConfig) => {
    onConfigChange({ ...config, ...newConfig });
  };

  return (
    <EventTriggerConfigPanel config={eventConfig} onChange={handleChange} />
  );
}

// Schedule Trigger Form - wraps ScheduleTriggerConfigPanel for registry compatibility
function ScheduleTriggerForm({ config, onConfigChange }: NodeConfigFormProps) {
  const scheduleConfig: ScheduleConfig = {
    schedule_type: config.schedule_type ?? DEFAULT_SCHEDULE_CONFIG.schedule_type,
    cron_expression: config.cron_expression ?? DEFAULT_SCHEDULE_CONFIG.cron_expression,
    interval_seconds: config.interval_seconds ?? DEFAULT_SCHEDULE_CONFIG.interval_seconds,
    run_at: config.run_at ?? DEFAULT_SCHEDULE_CONFIG.run_at,
    timezone: config.timezone ?? DEFAULT_SCHEDULE_CONFIG.timezone,
  };

  const handleChange = (newConfig: ScheduleConfig) => {
    onConfigChange({ ...config, ...newConfig });
  };

  return (
    <ScheduleTriggerConfigPanel config={scheduleConfig} onChange={handleChange} />
  );
}

// Set Values Form - allows creating key-value pairs
function SetValuesForm({ config, onConfigChange, availableData = [] }: NodeConfigFormProps) {
  const [newKey, setNewKey] = useState("");
  const [newValue, setNewValue] = useState("");
  const [keyError, setKeyError] = useState<string | null>(null);
  const [renameErrors, setRenameErrors] = useState<Record<string, string>>({});

  // Support both array and object formats - convert to array for processing
  const valuesList = Array.isArray(config.values) ? config.values : 
    (config.values && typeof config.values === 'object' ? 
      Object.entries(config.values).map(([key, value]) => ({ key, value })) : 
      []);

  const handleAddPair = () => {
    if (!newKey.trim()) return;
    const trimmedKey = newKey.trim();
    // Check for duplicate key
    if (valuesList.some(pair => pair.key === trimmedKey)) {
      setKeyError(`Key "${trimmedKey}" already exists`);
      return;
    }
    setKeyError(null);
    const updatedValues = [...valuesList, { key: trimmedKey, value: newValue }];
    onConfigChange({ ...config, values: updatedValues });
    setNewKey("");
    setNewValue("");
  };

  const handleUpdateValue = (oldKey: string, newVal: string) => {
    const updatedValues = valuesList.map(pair => 
      pair.key === oldKey ? { ...pair, value: newVal } : pair
    );
    onConfigChange({ ...config, values: updatedValues });
  };

  const handleRemovePair = (keyToRemove: string) => {
    const updatedValues = valuesList.filter(pair => pair.key !== keyToRemove);
    // Clear any rename error for this key
    const newErrors = { ...renameErrors };
    delete newErrors[keyToRemove];
    setRenameErrors(newErrors);
    onConfigChange({ ...config, values: updatedValues });
  };

  const handleKeyRename = (oldKey: string, newKeyName: string) => {
    // Clear error for this key when typing
    if (renameErrors[oldKey]) {
      const newErrors = { ...renameErrors };
      delete newErrors[oldKey];
      setRenameErrors(newErrors);
    }
    
    if (!newKeyName.trim() || newKeyName === oldKey) return;
    const trimmedNewKey = newKeyName.trim();
    
    // Check for collision with existing key (other than the one being renamed)
    if (valuesList.some(pair => pair.key === trimmedNewKey && pair.key !== oldKey)) {
      setRenameErrors({ ...renameErrors, [oldKey]: `Key "${trimmedNewKey}" already exists` });
      return;
    }
    
    const updatedValues = valuesList.map(pair =>
      pair.key === oldKey ? { ...pair, key: trimmedNewKey } : pair
    );
    onConfigChange({ ...config, values: updatedValues });
  };

  return (
    <div className="space-y-4">
      <div>
        <div className="flex items-center justify-between mb-3">
          <div>
            <Label className="text-xs font-medium">Key-Value Pairs</Label>
            <p className="text-xs text-muted-foreground mt-1">
              Each key you add becomes a new field available to downstream nodes. Use {"{{field}}"} syntax to reference existing data.
            </p>
          </div>
        </div>
        
        <div className="flex items-center gap-2 p-2 bg-muted rounded-md">
          <Switch
            checked={config.merge_with_input ?? true}
            onCheckedChange={(checked) => onConfigChange({ ...config, merge_with_input: checked })}
            data-testid="switch-merge-with-input"
          />
          <div className="flex-1">
            <Label className="text-xs font-medium cursor-pointer">Merge with incoming data</Label>
            <p className="text-xs text-muted-foreground">
              {config.merge_with_input 
                ? "Output includes incoming data + new values (new values override existing keys)"
                : "Output is ONLY the values you define (incoming data is discarded)"}
            </p>
          </div>
        </div>
      </div>

      {valuesList.length > 0 && (
        <div className="space-y-2">
          {valuesList.map((pair, index) => (
            <div key={index} className="space-y-1">
              <div className="flex items-center gap-2">
                <Input
                  value={pair.key}
                  onChange={(e) => handleKeyRename(pair.key, e.target.value)}
                  placeholder="Key"
                  className={cn("text-sm flex-1", renameErrors[pair.key] && "border-destructive")}
                  data-testid={`input-set-values-key-${index}`}
                />
                <span className="text-muted-foreground">=</span>
                <FormulaAwareStringInput
                  value={String(pair.value)}
                  onChange={(v) => handleUpdateValue(pair.key, v)}
                  availableData={availableData}
                  singleLine
                  placeholderTemplate="{{ctx.some_field}}"
                  placeholderFormula={'coalesce(ctx.some_field, "default")'}
                  className="flex-1"
                  data-testid={`input-set-values-value-${index}`}
                />
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  onClick={() => handleRemovePair(pair.key)}
                  className="text-destructive hover:text-destructive"
                  data-testid={`button-remove-value-${index}`}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
              {renameErrors[pair.key] && (
                <p className="text-xs text-destructive pl-1" data-testid={`text-rename-error-${index}`}>
                  {renameErrors[pair.key]}
                </p>
              )}
            </div>
          ))}
        </div>
      )}

      <div className="space-y-2 pt-2 border-t">
        <div className="flex items-center gap-2">
          <Input
            value={newKey}
            onChange={(e) => {
              setNewKey(e.target.value);
              setKeyError(null);
            }}
            placeholder="New key"
            className={cn("text-sm flex-1", keyError && "border-destructive")}
            data-testid="input-new-key"
          />
          <span className="text-muted-foreground">=</span>
          <div
            className="flex-1 min-w-0"
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                handleAddPair();
              }
            }}
          >
            <FormulaAwareStringInput
              value={newValue}
              onChange={setNewValue}
              availableData={availableData}
              singleLine
              placeholderTemplate="{{ctx.some_field}}"
              placeholderFormula={'coalesce(ctx.some_field, "default")'}
              data-testid="input-new-value"
            />
          </div>
          <Button
            type="button"
            variant="outline"
            size="icon"
            onClick={handleAddPair}
            disabled={!newKey.trim()}
            data-testid="button-add-value"
          >
            <Plus className="h-4 w-4" />
          </Button>
        </div>
        {keyError && (
          <p className="text-xs text-destructive" data-testid="text-key-error">{keyError}</p>
        )}
      </div>

      {availableData.length > 0 && (
        <div className="pt-2">
          <Collapsible>
            <CollapsibleTrigger className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
              <ChevronDown className="h-3 w-3" />
              Available fields to reference
            </CollapsibleTrigger>
            <CollapsibleContent className="pt-2">
              <div className="flex flex-wrap gap-1">
                {availableData.slice(0, 10).map((field, idx) => (
                  <Badge
                    key={idx}
                    variant="outline"
                    className="text-xs cursor-pointer"
                    onClick={() => setNewValue(`{{${field.key}}}`)}
                    data-testid={`badge-field-${idx}`}
                  >
                    {field.key}
                  </Badge>
                ))}
                {availableData.length > 10 && (
                  <Badge variant="secondary" className="text-xs">
                    +{availableData.length - 10} more
                  </Badge>
                )}
              </div>
            </CollapsibleContent>
          </Collapsible>
        </div>
      )}
    </div>
  );
}

// CRM CRUD Form (tool_crm_crud) - unified CRM model operations
function CrmCrudForm({ config, onConfigChange, availableData = [] }: NodeConfigFormProps) {
  const { toast } = useToast();

  const resourceSlug = (config.resource_slug ?? "").toString();
  const operation = (config.operation ?? "").toString();
  const rawInput: any = (config as any).input;
  const inputObj: Record<string, any> =
    typeof rawInput === "object" && rawInput !== null && !Array.isArray(rawInput) ? rawInput : {};
  const [rawInputText, setRawInputText] = useState<string>(() => {
    try {
      return JSON.stringify(inputObj ?? {}, null, 2);
    } catch {
      return "{}";
    }
  });
  const [rawInputError, setRawInputError] = useState<string | null>(null);

  // Track which fields are in template or formula mode
  const [templateModeFields, setTemplateModeFields] = useState<Set<string>>(new Set());
  const [formulaModeFields, setFormulaModeFields] = useState<Set<string>>(new Set());
  const [templateDrafts, setTemplateDrafts] = useState<Record<string, string>>({});
  const [templateFieldErrors, setTemplateFieldErrors] = useState<Record<string, string>>({});
  const [templateFieldWarnings, setTemplateFieldWarnings] = useState<Record<string, string>>({});

  const modelsQuery = useCrmModels();
  const resourceDetailsQuery = useCrmResourceDetails(resourceSlug || undefined);
  const resourceDetails = resourceDetailsQuery.data;

  const ctxFields = useMemo(() => {
    return (availableData || []).filter((f) => (f.key || "").startsWith("ctx."));
  }, [availableData]);

  const parseJsonMaybe = useCallback((v: unknown): unknown => {
    if (typeof v === "string") {
      try {
        return JSON.parse(v);
      } catch {
        return v;
      }
    }
    return v;
  }, []);

  const normalizeJsonSchemaType = useCallback((t: any): string | undefined => {
    if (typeof t === "string") return t;
    if (Array.isArray(t)) {
      const firstNonNull = t.find((x) => typeof x === "string" && x !== "null");
      return (firstNonNull ?? t.find((x) => typeof x === "string")) as string | undefined;
    }
    return undefined;
  }, []);

  const normalizeSchemaLike = useCallback(
    (schema: any): any => {
      if (!schema || typeof schema !== "object") return schema;
      // Unwrap common wrappers returned by some backends
      if (schema.schema && typeof schema.schema === "object") return normalizeSchemaLike(schema.schema);
      if (schema.data && typeof schema.data === "object" && !schema.type && !schema.properties) {
        // Treat as { data: <schema> } wrapper
        return normalizeSchemaLike(schema.data);
      }
      return schema;
    },
    []
  );

  const isTemplateString = useCallback((v: any): boolean => {
    if (typeof v !== "string") return false;
    const s = v.trim();
    return s.startsWith("{{") && s.endsWith("}}") && s.length >= 4;
  }, []);

  const getTemplateInner = useCallback((v: string): string => v.trim().slice(2, -2).trim(), []);

  const lintTemplateNamespace = useCallback(
    (inner: string): string | null => {
      // Allowed namespaces:
      // - ctx.*
      // - input.body.*
      // - nodes.<id>.output.*
      if (inner === "ctx" || inner.startsWith("ctx.")) return null;
      if (inner === "input.body" || inner.startsWith("input.body.")) return null;
      if (inner.startsWith("nodes.")) {
        const parts = inner.split(".").filter(Boolean);
        // nodes.<id>.output or nodes.<id>.output.<path...>
        if (parts.length >= 3 && parts[2] === "output") return null;
        return "Invalid nodes template. Expected {{nodes.<id>.output.*}}";
      }
      return "Unsupported template namespace. Allowed: {{ctx.*}}, {{input.body.*}}, {{nodes.<id>.output.*}}";
    },
    []
  );

  const isAllowedTemplateExpression = useCallback(
    (v: any): { ok: true; inner?: string } | { ok: false; error: string; inner?: string } => {
      if (!isTemplateString(v)) return { ok: true };
      const inner = getTemplateInner(String(v));
      const err = lintTemplateNamespace(inner);
      if (err) return { ok: false, error: err, inner };
      return { ok: true, inner };
    },
    [getTemplateInner, isTemplateString, lintTemplateNamespace]
  );

  const ctxTypeByPath = useMemo(() => {
    const m = new Map<string, string>();
    for (const f of ctxFields) {
      if (typeof f?.key === "string" && f.key.startsWith("ctx.")) {
        m.set(f.key, String((f as any).type ?? ""));
      }
    }
    return m;
  }, [ctxFields]);

  const isCompositeType = useCallback((t: string): boolean => {
    const s = (t || "").toLowerCase();
    return s === "object" || s === "dict" || s === "map" || s === "record" || s === "json" || s.includes("object") || s.includes("dict");
  }, []);

  const isArrayType = useCallback((t: string): boolean => {
    const s = (t || "").toLowerCase();
    return s === "array" || s === "list" || s.includes("array") || s.includes("list");
  }, []);

  const getDeep = useCallback((obj: any, path: string) => {
    const parts = path.split(".").filter(Boolean);
    let cur: any = obj;
    for (const p of parts) {
      if (!cur || typeof cur !== "object") return undefined;
      cur = cur[p];
    }
    return cur;
  }, []);

  const isFieldInFormulaMode = useCallback((fieldPath: string): boolean => {
    if (formulaModeFields.has(fieldPath)) return true;
    const v = String(getDeep(inputObj, fieldPath) ?? "").trim();
    return v.startsWith("=") && !v.startsWith("==");
  }, [formulaModeFields, inputObj, getDeep]);

  const isFieldInTemplateMode = useCallback((fieldPath: string): boolean => {
    if (isFieldInFormulaMode(fieldPath)) return false;
    return templateModeFields.has(fieldPath) || isTemplateString(getDeep(inputObj, fieldPath));
  }, [templateModeFields, inputObj, getDeep, isTemplateString, isFieldInFormulaMode]);

  const setFieldMode = useCallback((fieldPath: string, mode: "literal" | "template" | "formula") => {
    if (mode === "literal") {
      setTemplateModeFields((prev) => { const next = new Set(prev); next.delete(fieldPath); return next; });
      setFormulaModeFields((prev) => { const next = new Set(prev); next.delete(fieldPath); return next; });
    } else if (mode === "template") {
      setTemplateModeFields((prev) => new Set(prev).add(fieldPath));
      setFormulaModeFields((prev) => { const next = new Set(prev); next.delete(fieldPath); return next; });
    } else {
      setFormulaModeFields((prev) => new Set(prev).add(fieldPath));
      setTemplateModeFields((prev) => { const next = new Set(prev); next.delete(fieldPath); return next; });
    }
  }, []);

  const toggleFieldMode = useCallback((fieldPath: string) => {
    setTemplateModeFields(prev => {
      const next = new Set(prev);
      if (next.has(fieldPath)) next.delete(fieldPath);
      else next.add(fieldPath);
      return next;
    });
    setFormulaModeFields(prev => { const next = new Set(prev); next.delete(fieldPath); return next; });
  }, []);

  const validateInputAgainstSchema = useCallback(
    (
      value: any,
      schema: any,
      path: string = "input",
      isTemplateMode: boolean = false
    ): { ok: true } | { ok: false; error: string } => {
      const s = normalizeSchemaLike(schema);
      if (!s || typeof s !== "object") return { ok: true };

      // In template mode, allow template strings regardless of schema
      if (isTemplateMode && isTemplateString(value)) {
        const lint = isAllowedTemplateExpression(value);
        if (!lint.ok) return { ok: false, error: `${path}: ${lint.error}` };
        return { ok: true };
      }

      // SchemaNode v2
      if (typeof s.kind === "string") {
        if (s.kind === "unknown") return { ok: true };
        if (s.kind === "primitive") {
          if (isTemplateString(value)) {
            const lint = isAllowedTemplateExpression(value);
            if (!lint.ok) return { ok: false, error: `${path}: ${lint.error}` };
            return { ok: true };
          }
          const t = String(s.type ?? "");
          if (t === "string") return typeof value === "string" ? { ok: true } : { ok: false, error: `${path} must be string` };
          if (t === "number" || t === "integer") return typeof value === "number" ? { ok: true } : { ok: false, error: `${path} must be number` };
          if (t === "boolean") return typeof value === "boolean" ? { ok: true } : { ok: false, error: `${path} must be boolean` };
          return { ok: true };
        }
        if (s.kind === "array") {
          if (isTemplateString(value)) {
            const lint = isAllowedTemplateExpression(value);
            if (!lint.ok) return { ok: false, error: `${path}: ${lint.error}` };
            return { ok: true };
          }
          if (!Array.isArray(value)) return { ok: false, error: `${path} must be array` };
          return { ok: true }; // keep shallow; array item editors are not supported yet
        }
        if (s.kind === "object") {
          if (isTemplateString(value)) {
            const lint = isAllowedTemplateExpression(value);
            if (!lint.ok) return { ok: false, error: `${path}: ${lint.error}` };
            return { ok: true };
          }
          if (!value || typeof value !== "object" || Array.isArray(value)) {
            return { ok: false, error: `${path} must be object` };
          }
          const props = s.properties && typeof s.properties === "object" ? s.properties : {};
          const keys = Object.keys(value);
          for (const k of keys) {
            if (!(k in props)) {
              return { ok: false, error: `${path} has unknown key "${k}"` };
            }
            const child = validateInputAgainstSchema(value[k], props[k], `${path}.${k}`, isTemplateMode);
            if (!child.ok) return child;
          }
          return { ok: true };
        }
        return { ok: true };
      }

      // JSON Schema-ish
      const schemaType = normalizeJsonSchemaType(s.type);
      const props = s.properties && typeof s.properties === "object" ? s.properties : undefined;

      if (props) {
        if (isTemplateString(value)) {
          const lint = isAllowedTemplateExpression(value);
          if (!lint.ok) return { ok: false, error: `${path}: ${lint.error}` };
          return { ok: true };
        }
        if (!value || typeof value !== "object" || Array.isArray(value)) {
          return { ok: false, error: `${path} must be object` };
        }

        const allowAdditional = s.additionalProperties !== false;
        const keys = Object.keys(value);
        if (!allowAdditional) {
          for (const k of keys) {
            if (!(k in props)) {
              return { ok: false, error: `${path} has unknown key "${k}"` };
            }
          }
        }

        const required = new Set<string>(Array.isArray(s.required) ? s.required.map(String) : []);
        for (const reqKey of required) {
          if (value[reqKey] === undefined) {
            return { ok: false, error: `${path}.${reqKey} is required` };
          }
        }

        for (const [k, childSchema] of Object.entries(props)) {
          if (value[k] === undefined) continue;
          const child = validateInputAgainstSchema(value[k], childSchema, `${path}.${k}`, isTemplateMode);
          if (!child.ok) return child;
        }
        return { ok: true };
      }

      if (schemaType === "array" || s.items) {
        if (isTemplateString(value)) {
          const lint = isAllowedTemplateExpression(value);
          if (!lint.ok) return { ok: false, error: `${path}: ${lint.error}` };
          return { ok: true };
        }
        if (!Array.isArray(value)) return { ok: false, error: `${path} must be array` };
        return { ok: true };
      }

      if (schemaType && schemaType !== "object") {
        if (isTemplateString(value)) {
          const lint = isAllowedTemplateExpression(value);
          if (!lint.ok) return { ok: false, error: `${path}: ${lint.error}` };
          return { ok: true };
        }
        if (schemaType === "string") return typeof value === "string" ? { ok: true } : { ok: false, error: `${path} must be string` };
        if (schemaType === "number" || schemaType === "integer") return typeof value === "number" ? { ok: true } : { ok: false, error: `${path} must be number` };
        if (schemaType === "boolean") return typeof value === "boolean" ? { ok: true } : { ok: false, error: `${path} must be boolean` };
      }

      return { ok: true };
    },
    [isAllowedTemplateExpression, isTemplateString, normalizeJsonSchemaType, normalizeSchemaLike]
  );

  type FieldDesc = {
    path: string;
    title?: string;
    description?: string;
    type?: string;
    required: boolean;
    isLeaf: boolean;
  };

  const collectFieldsFromSchema = useCallback(
    (schema: any, prefix: string, requiredFromParent: Set<string>): FieldDesc[] => {
      const s = normalizeSchemaLike(schema);
      if (!s || typeof s !== "object") return [];

      // If JSON Schema uses `properties`, treat it as object-like regardless of `type` shape.
      const schemaType = normalizeJsonSchemaType((s as any).type) ?? (typeof (s as any).kind === "string" ? (s as any).kind : undefined);
      const props = (s as any).properties && typeof (s as any).properties === "object" ? (s as any).properties : undefined;
      if (!props) {
        // Leaf schema (primitive / array / unknown): render as a single field if we have a prefix.
        if (!prefix) return [];
        return [
          {
            path: prefix,
            title: (s as any).title,
            description: (s as any).description,
            type:
              (schemaType === "primitive" ? (s as any).type : schemaType) ??
              ((s as any).items ? "array" : undefined),
            required: requiredFromParent.has(prefix.split(".").slice(-1)[0] || ""),
            isLeaf: true,
          },
        ];
      }

      const requiredSet = new Set<string>(Array.isArray((s as any).required) ? (s as any).required.map(String) : []);
      const out: FieldDesc[] = [];

      for (const [k, v] of Object.entries(props)) {
        const key = String(k);
        const nextPath = prefix ? `${prefix}.${key}` : key;
        const child = v as any;
        const normalizedChild = normalizeSchemaLike(child);
        const childProps = normalizedChild && typeof normalizedChild === "object" ? normalizedChild.properties : undefined;
        const childIsObject = Boolean(childProps && typeof childProps === "object");
        const childType =
          normalizeJsonSchemaType(normalizedChild?.type) ??
          (typeof normalizedChild?.kind === "string" ? normalizedChild.kind : undefined);
        const childIsArray =
          childType === "array" ||
          Boolean(normalizedChild?.items) ||
          normalizedChild?.kind === "array";

        // Object-like: recurse; also include a non-leaf header entry (for readability)
        if (childIsObject) {
          out.push({
            path: nextPath,
            title: normalizedChild?.title,
            description: normalizedChild?.description,
            type: "object",
            required: requiredSet.has(key),
            isLeaf: false,
          });
          out.push(...collectFieldsFromSchema(normalizedChild, nextPath, requiredSet));
          continue;
        }

        // Array-like: treat as leaf (we can't build item forms safely without full schema support)
        if (childIsArray) {
          out.push({
            path: nextPath,
            title: normalizedChild?.title,
            description: normalizedChild?.description,
            type: "array",
            required: requiredSet.has(key),
            isLeaf: true,
          });
          continue;
        }

        // Primitive/unknown leaf
        out.push({
          path: nextPath,
          title: normalizedChild?.title,
          description: normalizedChild?.description,
          type: childType === "primitive" ? normalizedChild?.type : childType,
          required: requiredSet.has(key),
          isLeaf: true,
        });
      }

      return out;
    },
    [normalizeJsonSchemaType, normalizeSchemaLike]
  );

  const selectedOperationSchemas = useMemo(() => {
    const ops = resourceDetails?.operations || {};
    const raw = (ops as any)[operation];
    if (!raw) return undefined;
    return {
      input_schema: parseJsonMaybe(raw.input_schema),
      output_schema: parseJsonMaybe(raw.output_schema),
      description: typeof raw.description === "string" ? raw.description : undefined,
    };
  }, [operation, parseJsonMaybe, resourceDetails?.operations]);

  const inputSchema = normalizeSchemaLike(selectedOperationSchemas?.input_schema as any);
  const outputSchema = selectedOperationSchemas?.output_schema as any;

  const inputSchemaFields = useMemo(() => {
    const schema = inputSchema;
    if (!schema || typeof schema !== "object") return [];

    // Root is expected to be an object schema with properties.
    const rootRequired = new Set<string>(Array.isArray(schema.required) ? schema.required.map(String) : []);
    return collectFieldsFromSchema(schema, "", rootRequired);
  }, [collectFieldsFromSchema, inputSchema]);

  // Default to Template mode for all leaf fields once the schema loads
  useEffect(() => {
    if (!inputSchemaFields || inputSchemaFields.length === 0) return;
    const leafPaths = inputSchemaFields.filter((f) => f.isLeaf).map((f) => f.path).filter(Boolean);
    setTemplateModeFields(new Set(leafPaths));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resourceSlug, operation, inputSchemaFields.length]);

  const rootInputEditor = useMemo(() => {
    const s = normalizeSchemaLike(inputSchema);
    if (!s || typeof s !== "object") return null;

    const hasProps = Boolean((s as any).properties && typeof (s as any).properties === "object");
    if (hasProps) return null; // regular schema form will render

    const kind = typeof (s as any).kind === "string" ? (s as any).kind : undefined;
    const t = normalizeJsonSchemaType((s as any).type) ?? kind;

    return { type: t };
  }, [inputSchema, normalizeJsonSchemaType, normalizeSchemaLike]);

  const [rootInputText, setRootInputText] = useState<string>(() => {
    if (rawInput === undefined || rawInput === null) return "";
    if (typeof rawInput === "string") return rawInput;
    if (typeof rawInput === "number" || typeof rawInput === "boolean") return String(rawInput);
    try {
      return JSON.stringify(rawInput, null, 2);
    } catch {
      return String(rawInput);
    }
  });
  const [rootInputError, setRootInputError] = useState<string | null>(null);

  const coerceRootValue = useCallback(
    (text: string, schemaType?: string): { ok: true; value: any } | { ok: false; error: string } => {
      const trimmed = text;
      if (schemaType === "primitive") schemaType = undefined;

      // Always allow templates as raw strings (backend resolves).
      if (isTemplateString(trimmed)) {
        const lint = isAllowedTemplateExpression(trimmed);
        if (!lint.ok) return { ok: false, error: lint.error };
        return { ok: true, value: trimmed };
      }

      const t = (schemaType ?? "").toLowerCase();
      if (!t || t === "unknown") return { ok: true, value: trimmed };
      if (t === "string") return { ok: true, value: trimmed };
      if (t === "number" || t === "integer") {
        if (trimmed.trim().length === 0) return { ok: true, value: null };
        const n = Number(trimmed);
        if (Number.isNaN(n)) return { ok: false, error: "Must be a number (or a {{ctx.*}} template)." };
        return { ok: true, value: n };
      }
      if (t === "boolean") {
        const v = trimmed.trim().toLowerCase();
        if (v === "true") return { ok: true, value: true };
        if (v === "false") return { ok: true, value: false };
        return { ok: false, error: "Must be true/false (or a {{ctx.*}} template)." };
      }
      if (t === "array" || t === "object") {
        if (trimmed.trim().length === 0) return { ok: true, value: t === "array" ? [] : {} };
        try {
          const parsed = JSON.parse(trimmed);
          if (t === "array" && !Array.isArray(parsed)) return { ok: false, error: "Must be a JSON array." };
          if (t === "object" && (typeof parsed !== "object" || parsed === null || Array.isArray(parsed))) {
            return { ok: false, error: "Must be a JSON object." };
          }
          return { ok: true, value: parsed };
        } catch (e) {
          return { ok: false, error: e instanceof Error ? e.message : "Invalid JSON" };
        }
      }
      return { ok: true, value: trimmed };
    },
    [isAllowedTemplateExpression, isTemplateString]
  );

  const coerceFieldValue = useCallback(
    (text: string, field: FieldDesc, isTemplateMode: boolean): { ok: true; value: any } | { ok: false; error: string } => {
      const trimmed = text;

      // In template mode, always treat as string (backend resolves templates)
      if (isTemplateMode) {
        return { ok: true, value: trimmed };
      }

      // In literal mode, coerce based on schema type
      const schemaType = field.type?.toLowerCase();
      if (!schemaType || schemaType === "unknown") return { ok: true, value: trimmed };

      if (schemaType === "string") return { ok: true, value: trimmed };
      if (schemaType === "number" || schemaType === "integer") {
        if (trimmed.trim().length === 0) return { ok: true, value: null };
        const n = Number(trimmed);
        if (Number.isNaN(n)) return { ok: false, error: "Must be a number." };
        return { ok: true, value: n };
      }
      if (schemaType === "boolean") {
        const v = trimmed.trim().toLowerCase();
        if (v === "true") return { ok: true, value: true };
        if (v === "false") return { ok: true, value: false };
        return { ok: false, error: "Must be true or false." };
      }
      if (schemaType === "array") {
        if (trimmed.trim().length === 0) return { ok: true, value: [] };
        try {
          const parsed = JSON.parse(trimmed);
          if (!Array.isArray(parsed)) return { ok: false, error: "Must be a JSON array." };
          return { ok: true, value: parsed };
        } catch (e) {
          return { ok: false, error: e instanceof Error ? e.message : "Invalid JSON array" };
        }
      }
      if (schemaType === "object") {
        if (trimmed.trim().length === 0) return { ok: true, value: {} };
        try {
          const parsed = JSON.parse(trimmed);
          if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
            return { ok: false, error: "Must be a JSON object." };
          }
          return { ok: true, value: parsed };
        } catch (e) {
          return { ok: false, error: e instanceof Error ? e.message : "Invalid JSON object" };
        }
      }

      return { ok: true, value: trimmed };
    },
    []
  );

  // Keep raw JSON editor in sync when config.input changes externally (e.g. op switch)
  // Also reset template mode fields when operation changes
  useEffect(() => {
    try {
      setRawInputText(JSON.stringify(inputObj ?? {}, null, 2));
      setRawInputError(null);
    } catch {
      // ignore
    }
    try {
      const next =
        rawInput === undefined || rawInput === null
          ? ""
          : typeof rawInput === "string"
            ? rawInput
            : typeof rawInput === "number" || typeof rawInput === "boolean"
              ? String(rawInput)
              : JSON.stringify(rawInput, null, 2);
      setRootInputText(next);
      setRootInputError(null);
    } catch {
      // ignore
    }

    // Reset template mode fields when operation changes
    setTemplateModeFields(new Set());
    setTemplateDrafts({});
    setTemplateFieldErrors({});
    setTemplateFieldWarnings({});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resourceSlug, operation]);

  const setDeep = useCallback((obj: any, path: string, value: any) => {
    const parts = path.split(".").filter(Boolean);
    if (parts.length === 0) return obj;
    const out = { ...(obj || {}) };
    let cur: any = out;
    for (let i = 0; i < parts.length; i++) {
      const p = parts[i];
      if (i === parts.length - 1) {
        cur[p] = value;
      } else {
        const next = cur[p];
        cur[p] = typeof next === "object" && next !== null && !Array.isArray(next) ? { ...next } : {};
        cur = cur[p];
      }
    }
    return out;
  }, []);

  const clearDeep = useCallback((obj: any, path: string) => {
    const parts = path.split(".").filter(Boolean);
    if (parts.length === 0) return obj;
    const out = { ...(obj || {}) };
    const stack: any[] = [out];
    for (let i = 0; i < parts.length - 1; i++) {
      const p = parts[i];
      const cur = stack[stack.length - 1];
      if (!cur[p] || typeof cur[p] !== "object") return out;
      cur[p] = { ...cur[p] };
      stack.push(cur[p]);
    }
    const lastParent = stack[stack.length - 1];
    delete lastParent[parts[parts.length - 1]];
    return out;
  }, []);

  const handlePickCtx = useCallback(
    (path: string, ctxPath: string) => {
      const templ = `{{${ctxPath}}}`;
      const nextInput = setDeep(inputObj, path, templ);
      onConfigChange({ ...config, input: nextInput });
      setTemplateDrafts((prev) => {
        const { [path]: _omit, ...rest } = prev;
        return rest;
      });
      setTemplateFieldErrors((prev) => {
        const { [path]: _omit, ...rest } = prev;
        return rest;
      });
      setTemplateFieldWarnings((prev) => {
        const { [path]: _omit, ...rest } = prev;
        return rest;
      });
      toast({ title: "Inserted ctx reference", description: templ, duration: 1500 });
    },
    [config, inputObj, onConfigChange, setDeep, toast]
  );

  const models = modelsQuery.data?.models ?? [];
  const selectedModel = useMemo(() => models.find((m) => m.slug === resourceSlug), [models, resourceSlug]);
  const enabledOps = selectedModel?.enabled_operations ?? [];
  const opOptions = useMemo(() => {
    const opsFromDetails = Object.keys(resourceDetails?.operations || {});
    const base = enabledOps.length > 0 ? enabledOps : opsFromDetails;
    const uniq = Array.from(new Set(base.filter(Boolean)));
    return uniq;
  }, [enabledOps, resourceDetails?.operations]);

  const outputSchemaText = useMemo(() => {
    if (!outputSchema) return "";
    try {
      return JSON.stringify(outputSchema, null, 2);
    } catch {
      return String(outputSchema);
    }
  }, [outputSchema]);

  return (
    <div className="space-y-4">
      <Alert>
        <AlertTitle>CRM CRUD</AlertTitle>
        <AlertDescription className="text-xs">
          Un único nodo para operar recursos CRM (<code>contact</code>, <code>ticket</code>, <code>deal</code>, <code>audience</code>).
          Configurá <code>resource_slug</code>, <code>operation</code> y completá <code>input</code> usando templates{" "}
          <code>{"{{ctx.*}}"}</code>.
          <div className="mt-2 space-y-1">
            <div>
              Luego de ejecutar, el resultado queda disponible en{" "}
              <code>
                {"{{ctx.crm.<resource>.last}}"}
              </code>{" "}
              (alias:{" "}
              <code>
                {"{{ctx.last.crm.<resource>}}"}
              </code>
              ).
            </div>
            <div className="text-[11px] text-muted-foreground">
              Ejemplos:{" "}
              <code>
                {`{{ctx.crm.${resourceSlug || "contact"}.last.email}}`}
              </code>
              {", "}
              <code>
                {`{{ctx.crm.${resourceSlug || "deal"}.last.status}}`}
              </code>
              {" == 'won'"}
              .
            </div>
          </div>
        </AlertDescription>
      </Alert>

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1">
          <Label className="text-xs">Model</Label>
          <Select
            value={resourceSlug}
            onValueChange={(v) => {
              onConfigChange({ ...config, resource_slug: v, operation: "", input: {} });
            }}
            disabled={modelsQuery.isLoading}
          >
            <SelectTrigger className="h-9" data-testid="select-crm-model">
              <SelectValue placeholder={modelsQuery.isLoading ? "Loading..." : "Select model"} />
            </SelectTrigger>
            <SelectContent>
              {models.map((m) => (
                <SelectItem key={m.slug} value={m.slug}>
                  {m.label} ({m.slug})
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {selectedModel?.description && (
            <p className="text-xs text-muted-foreground">{selectedModel.description}</p>
          )}
        </div>

        <div className="space-y-1">
          <Label className="text-xs">Operation</Label>
          <Select
            value={operation}
            onValueChange={(v) => onConfigChange({ ...config, operation: v, input: {} })}
            disabled={!resourceSlug || resourceDetailsQuery.isLoading}
          >
            <SelectTrigger className="h-9" data-testid="select-crm-operation">
              <SelectValue placeholder={!resourceSlug ? "Select model first" : resourceDetailsQuery.isLoading ? "Loading..." : "Select operation"} />
            </SelectTrigger>
            <SelectContent>
              {opOptions.map((op) => (
                <SelectItem key={op} value={op}>
                  {op}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {selectedOperationSchemas?.description && (
            <p className="text-xs text-muted-foreground">{selectedOperationSchemas.description}</p>
          )}
        </div>
      </div>

      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <div>
            <Label className="text-xs">Input (from input_schema)</Label>
            <p className="text-xs text-muted-foreground">
              Toggle between <strong>Literal</strong> (type-aware input) and <strong>Template</strong> (raw text for <code>{"{{ctx.*}}"}</code> expressions).
            </p>
          </div>
          {ctxFields.length > 0 && (
            <Badge variant="outline" className="text-[10px]">
              ctx fields: {ctxFields.length}
            </Badge>
          )}
        </div>

        {!resourceSlug ? (
          <div className="rounded-md border bg-muted/30 p-3 text-xs text-muted-foreground">
            Select a model to load schemas.
          </div>
        ) : resourceDetailsQuery.isError ? (
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertTitle>Failed to load CRM model</AlertTitle>
            <AlertDescription className="text-xs">
              {(resourceDetailsQuery.error as any)?.message || "Could not load CRM model details."}
            </AlertDescription>
          </Alert>
        ) : !operation ? (
          <div className="rounded-md border bg-muted/30 p-3 text-xs text-muted-foreground">
            Select an operation to load its input schema.
          </div>
        ) : rootInputEditor ? (
          <div className="space-y-2 rounded-md border p-3">
            <div className="flex items-center justify-between gap-2">
              <div>
                <Label className="text-xs">Input (schema)</Label>
                <p className="text-xs text-muted-foreground">
                  This operation expects a single value (not an object). Templates like <code>{"{{ctx.*}}"}</code> are allowed.
                </p>
              </div>
              {rootInputEditor.type && (
                <Badge variant="outline" className="text-[10px]">
                  {rootInputEditor.type}
                </Badge>
              )}
            </div>

            <Textarea
              value={rootInputText}
              onChange={(e) => {
                const next = e.target.value;
                setRootInputText(next);
                const coerced = coerceRootValue(next, rootInputEditor.type);
                if (!coerced.ok) {
                  setRootInputError(coerced.error);
                  return;
                }
                const schemaCheck = validateInputAgainstSchema(coerced.value, inputSchema, "input", false);
                if (!schemaCheck.ok) {
                  setRootInputError(schemaCheck.error);
                  return;
                }
                setRootInputError(null);
                onConfigChange({ ...config, input: coerced.value });
              }}
              rows={3}
              className={cn("text-sm font-mono", rootInputError ? "border-destructive" : "")}
              placeholder={rootInputEditor.type === "string" ? "{{ctx.contact_id}}" : ""}
              data-testid="textarea-crm-input-root"
            />
            {rootInputError && <p className="text-xs text-destructive">{rootInputError}</p>}

            <Collapsible>
              <CollapsibleTrigger className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
                <ChevronDown className="h-3 w-3" />
                Advanced: raw input JSON
              </CollapsibleTrigger>
              <CollapsibleContent className="pt-2">
                <Textarea
                  value={rawInputText}
                  onChange={(e) => {
                    const next = e.target.value;
                    setRawInputText(next);
                    try {
                      const parsed = next.trim().length ? JSON.parse(next) : {};
                      const schemaCheck = validateInputAgainstSchema(parsed, inputSchema, "input", false);
                      if (!schemaCheck.ok) {
                        setRawInputError(schemaCheck.error);
                        return;
                      }
                      setRawInputError(null);
                      onConfigChange({ ...config, input: parsed });
                    } catch (err) {
                      setRawInputError(err instanceof Error ? err.message : "Invalid JSON");
                    }
                  }}
                  rows={6}
                  className={cn("text-sm font-mono", rawInputError ? "border-destructive" : "")}
                  placeholder="{}"
                  data-testid="textarea-crm-input-raw"
                />
                {rawInputError && <p className="text-xs text-destructive mt-1">{rawInputError}</p>}
              </CollapsibleContent>
            </Collapsible>
          </div>
        ) : inputSchemaFields.length === 0 ? (
          <div className="rounded-md border bg-muted/30 p-3 text-xs text-muted-foreground">
            No input_schema fields available for this operation (or schema is not object/properties-based).
            <div className="mt-2">
              <Collapsible>
                <CollapsibleTrigger className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
                  <ChevronDown className="h-3 w-3" />
                  View raw input_schema
                </CollapsibleTrigger>
                <CollapsibleContent className="pt-2">
                  <pre className="text-xs bg-muted/50 p-2 rounded border overflow-x-auto max-h-[240px] overflow-y-auto">
                    {(() => {
                      try {
                        return JSON.stringify(inputSchema, null, 2);
                      } catch {
                        return String(inputSchema);
                      }
                    })()}
                  </pre>
                </CollapsibleContent>
              </Collapsible>
            </div>

            <div className="mt-3">
              <Collapsible>
                <CollapsibleTrigger className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
                  <ChevronDown className="h-3 w-3" />
                  Advanced: raw input JSON
                </CollapsibleTrigger>
                <CollapsibleContent className="pt-2">
                  <Textarea
                    value={rawInputText}
                    onChange={(e) => {
                      const next = e.target.value;
                      setRawInputText(next);
                      try {
                        const parsed = next.trim().length ? JSON.parse(next) : {};
                        const schemaCheck = validateInputAgainstSchema(parsed, inputSchema, "input", false);
                        if (!schemaCheck.ok) {
                          setRawInputError(schemaCheck.error);
                          return;
                        }
                        setRawInputError(null);
                        onConfigChange({ ...config, input: parsed });
                      } catch (err) {
                        setRawInputError(err instanceof Error ? err.message : "Invalid JSON");
                      }
                    }}
                    rows={6}
                    className={cn("text-sm font-mono", rawInputError ? "border-destructive" : "")}
                    placeholder="{}"
                    data-testid="textarea-crm-input-raw"
                  />
                  {rawInputError && <p className="text-xs text-destructive mt-1">{rawInputError}</p>}
                </CollapsibleContent>
              </Collapsible>
            </div>
          </div>
        ) : (
          <div className="space-y-2">
            {inputSchemaFields.map((f) => {
              const depth = f.path ? f.path.split(".").length - 1 : 0;
              const val = f.isLeaf ? (getDeep(inputObj, f.path) ?? "") : "";
              const isMissingRequired = f.isLeaf && f.required && String(val).trim().length === 0;
              const isInTemplateMode = isFieldInTemplateMode(f.path);
              const fieldError = templateFieldErrors[f.path];
              const fieldWarning = templateFieldWarnings[f.path];
              const displayValue =
                isInTemplateMode && typeof templateDrafts[f.path] === "string" ? templateDrafts[f.path] : String(val);

              // For object headers, show a divider/label only
              if (!f.isLeaf) {
                return (
                  <div key={f.path} className="pt-2">
                    <div className="flex items-center gap-2">
                      <Badge variant="secondary" className="text-[10px]">
                        object
                      </Badge>
                      <span className="text-xs font-medium" style={{ paddingLeft: depth * 8 }}>
                        {f.path}
                      </span>
                      {f.required && (
                        <Badge variant="outline" className="text-[10px]">
                          required
                        </Badge>
                      )}
                    </div>
                    {f.description && (
                      <p className="text-xs text-muted-foreground mt-1" style={{ paddingLeft: depth * 8 }}>
                        {f.description}
                      </p>
                    )}
                  </div>
                );
              }

              const isLong = String(val).length > 80 || f.type === "array" || isInTemplateMode;

              return (
                <div key={f.path} className="rounded-md border p-2">
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2 min-w-0">
                      <code className="text-xs font-mono truncate" title={f.path} style={{ paddingLeft: depth * 8 }}>
                        {f.path}
                      </code>
                      {f.type && (
                        <Badge variant="outline" className="text-[10px]">
                          {f.type}
                        </Badge>
                      )}
                      {f.required && (
                        <Badge variant="secondary" className="text-[10px]">
                          required
                        </Badge>
                      )}
                    </div>

                    <div className="flex items-center gap-1">
                      <Button
                        variant={!isInTemplateMode && !isFieldInFormulaMode(f.path) ? "default" : "outline"}
                        size="sm"
                        className="h-7 px-2 text-xs"
                        onClick={() => setFieldMode(f.path, "literal")}
                        title="Literal value"
                      >
                        Literal
                      </Button>
                      <Button
                        variant={isInTemplateMode ? "default" : "outline"}
                        size="sm"
                        className="h-7 px-2 text-xs"
                        onClick={() => setFieldMode(f.path, "template")}
                        title="Template {{ctx.*}}"
                      >
                        Template
                      </Button>
                      <Button
                        variant={isFieldInFormulaMode(f.path) ? "default" : "outline"}
                        size="sm"
                        className="h-7 px-2"
                        onClick={() => setFieldMode(f.path, "formula")}
                        title="Formula =..."
                      >
                        <Zap className="h-3.5 w-3.5" />
                        <span className="sr-only">Formula</span>
                      </Button>

                      {ctxFields.length > 0 && isInTemplateMode && (
                        <Popover>
                          <PopoverTrigger asChild>
                            <Button variant="ghost" size="sm" className="h-7 px-2 text-xs text-muted-foreground">
                              <Plus className="h-3 w-3 mr-1" />
                              Pick ctx
                            </Button>
                          </PopoverTrigger>
                          <PopoverContent className="w-[360px] p-0" align="end">
                            <Command>
                              <CommandInput placeholder="Search ctx paths..." className="text-sm" />
                              <CommandList className="max-h-[280px] overflow-y-auto">
                                <CommandEmpty className="text-sm p-2">No ctx fields.</CommandEmpty>
                                <CommandGroup>
                                  {ctxFields.map((field) => (
                                    <CommandItem
                                      key={field.key}
                                      value={field.key}
                                      onSelect={() => handlePickCtx(f.path, field.key)}
                                      className="flex flex-col items-start gap-0.5"
                                    >
                                      <div className="flex w-full items-center justify-between gap-2">
                                        <code className="text-sm font-mono">{field.key}</code>
                                        <Badge variant="outline" className="text-[10px]">
                                          {field.type}
                                        </Badge>
                                      </div>
                                      {field.description && (
                                        <p className="text-xs text-muted-foreground">{field.description}</p>
                                      )}
                                    </CommandItem>
                                  ))}
                                </CommandGroup>
                              </CommandList>
                            </Command>
                          </PopoverContent>
                        </Popover>
                      )}

                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 px-2 text-xs text-muted-foreground"
                        onClick={() => onConfigChange({ ...config, input: clearDeep(inputObj, f.path) })}
                        disabled={String(val).length === 0}
                        title="Clear value"
                        data-testid={`button-crm-clear-${f.path}`}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </div>

                  {f.description && <p className="text-xs text-muted-foreground mt-1">{f.description}</p>}

                  <div className="mt-2">
                    {isFieldInFormulaMode(f.path) ? (
                      <FormulaAwareStringInput
                        value={String(val)}
                        onChange={(v) => onConfigChange({ ...config, input: setDeep(inputObj, f.path, v) })}
                        availableData={availableData}
                        singleLine={!isLong}
                        placeholderTemplate={`{{ctx.deal.contact_id}}`}
                        placeholderFormula={'coalesce(ctx.contact.email, "")'}
                        error={fieldError}
                        data-testid={`input-crm-input-${f.path}`}
                      />
                    ) : isInTemplateMode ? (
                      // Template mode: always use textarea with template placeholder
                      <Textarea
                        value={displayValue}
                        onChange={(e) => {
                          const nextValue = e.target.value;
                          setTemplateDrafts((prev) => ({ ...prev, [f.path]: nextValue }));

                          const trimmed = nextValue.trim();
                          // If it looks like a template, validate namespace + (optionally) type.
                          if (trimmed.startsWith("{{")) {
                            if (isTemplateString(trimmed)) {
                              const lint = isAllowedTemplateExpression(trimmed);
                              if (!lint.ok) {
                                setTemplateFieldErrors((prev) => ({ ...prev, [f.path]: lint.error }));
                                return; // do not commit
                              }

                              // composite warning + prevent commit into primitive fields if we know it's composite
                              const inner = lint.inner ?? getTemplateInner(trimmed);
                              if (inner.startsWith("ctx.")) {
                                const t = ctxTypeByPath.get(inner);
                                const expects = (f.type ?? "").toLowerCase();
                                const composite = t ? isCompositeType(t) || isArrayType(t) : false;
                                if (composite) {
                                  setTemplateFieldWarnings((prev) => ({
                                    ...prev,
                                    [f.path]: `Objeto/valor compuesto; usá una clave hija, ej. ${inner}.email`,
                                  }));
                                  if (expects && expects !== "object" && expects !== "array") {
                                    // prevent saving known-composite into primitive fields
                                    setTemplateFieldErrors((prev) => ({
                                      ...prev,
                                      [f.path]: `Este template resuelve a un objeto/array y el campo espera ${expects}. Elegí una clave hija (ej. ${inner}.email).`,
                                    }));
                                    return;
                                  }
                                } else {
                                  setTemplateFieldWarnings((prev) => {
                                    const { [f.path]: _omit, ...rest } = prev;
                                    return rest;
                                  });
                                }
                              }

                              setTemplateFieldErrors((prev) => {
                                const { [f.path]: _omit, ...rest } = prev;
                                return rest;
                              });
                              onConfigChange({ ...config, input: setDeep(inputObj, f.path, trimmed) });
                              return;
                            }
                            // still typing a template -> don't commit
                            setTemplateFieldErrors((prev) => {
                              const { [f.path]: _omit, ...rest } = prev;
                              return rest;
                            });
                            return;
                          }

                          // plain string (not a template) -> commit
                          setTemplateFieldErrors((prev) => {
                            const { [f.path]: _omit, ...rest } = prev;
                            return rest;
                          });
                          setTemplateFieldWarnings((prev) => {
                            const { [f.path]: _omit, ...rest } = prev;
                            return rest;
                          });
                          onConfigChange({ ...config, input: setDeep(inputObj, f.path, nextValue) });
                        }}
                        rows={2}
                        className={cn(
                          "text-sm font-mono",
                          isMissingRequired || Boolean(fieldError) ? "border-destructive" : ""
                        )}
                        placeholder={`{{ctx.deal.contact_id}}`}
                        data-testid={`textarea-crm-input-${f.path}`}
                      />
                    ) : (
                      // Literal mode: use type-aware inputs
                      (() => {
                        const fieldType = f.type?.toLowerCase();
                        const stringVal = String(val);

                        if (fieldType === "boolean") {
                          return (
                            <Select
                              value={stringVal}
                              onValueChange={(v) => {
                                const coerced = coerceFieldValue(v, f, false);
                                if (coerced.ok) {
                                  onConfigChange({ ...config, input: setDeep(inputObj, f.path, coerced.value) });
                                }
                              }}
                            >
                              <SelectTrigger className={cn("text-sm", isMissingRequired ? "border-destructive" : "")}>
                                <SelectValue placeholder="Select..." />
                              </SelectTrigger>
                              <SelectContent>
                                <SelectItem value="true">True</SelectItem>
                                <SelectItem value="false">False</SelectItem>
                              </SelectContent>
                            </Select>
                          );
                        }

                        if (fieldType === "number" || fieldType === "integer") {
                          return (
                      <Input
                              type="number"
                              value={stringVal}
                              onChange={(e) => {
                                const nextValue = e.target.value;
                                const coerced = coerceFieldValue(nextValue, f, false);
                                if (coerced.ok) {
                                  onConfigChange({ ...config, input: setDeep(inputObj, f.path, coerced.value) });
                                }
                              }}
                              className={cn("text-sm", isMissingRequired ? "border-destructive" : "")}
                              placeholder="123"
                              data-testid={`input-crm-input-${f.path}`}
                            />
                          );
                        }

                        if (fieldType === "array" || fieldType === "object") {
                          return (
                            <Textarea
                              value={stringVal}
                              onChange={(e) => {
                                const nextValue = e.target.value;
                                const coerced = coerceFieldValue(nextValue, f, false);
                                if (coerced.ok) {
                                  onConfigChange({ ...config, input: setDeep(inputObj, f.path, coerced.value) });
                                }
                              }}
                              rows={3}
                        className={cn("text-sm font-mono", isMissingRequired ? "border-destructive" : "")}
                              placeholder={fieldType === "array" ? "[]" : "{}"}
                              data-testid={`textarea-crm-input-${f.path}`}
                            />
                          );
                        }

                        // Default string input
                        return isLong ? (
                          <Textarea
                            value={stringVal}
                            onChange={(e) => {
                              const nextValue = e.target.value;
                              const coerced = coerceFieldValue(nextValue, f, false);
                              if (coerced.ok) {
                                onConfigChange({ ...config, input: setDeep(inputObj, f.path, coerced.value) });
                              }
                            }}
                            rows={2}
                            className={cn("text-sm", isMissingRequired ? "border-destructive" : "")}
                            placeholder="Enter value..."
                            data-testid={`textarea-crm-input-${f.path}`}
                          />
                        ) : (
                          <Input
                            value={stringVal}
                            onChange={(e) => {
                              const nextValue = e.target.value;
                              const coerced = coerceFieldValue(nextValue, f, false);
                              if (coerced.ok) {
                                onConfigChange({ ...config, input: setDeep(inputObj, f.path, coerced.value) });
                              }
                            }}
                            className={cn("text-sm", isMissingRequired ? "border-destructive" : "")}
                            placeholder="Enter value..."
                        data-testid={`input-crm-input-${f.path}`}
                      />
                        );
                      })()
                    )}
                    {isMissingRequired && (
                      <p className="text-xs text-destructive mt-1">Required field is empty</p>
                    )}
                    {fieldError && (
                      <p className="text-xs text-destructive mt-1">{fieldError}</p>
                    )}
                    {!fieldError && fieldWarning && (
                      <div className="mt-1 space-y-1">
                        <p className="text-xs text-muted-foreground">{fieldWarning}</p>
                        {(() => {
                          // If warning is about ctx.<path> being composite, suggest known children
                          const current = String(displayValue || "").trim();
                          if (!isTemplateString(current)) return null;
                          const inner = getTemplateInner(current);
                          if (!inner.startsWith("ctx.")) return null;
                          const t = ctxTypeByPath.get(inner);
                          if (!t || !(isCompositeType(t) || isArrayType(t))) return null;
                          const children = ctxFields
                            .map((x) => x.key)
                            .filter((k) => typeof k === "string" && k.startsWith(`${inner}.`))
                            .slice(0, 6) as string[];
                          if (children.length === 0) return null;
                          return (
                            <div className="flex flex-wrap gap-1">
                              {children.map((k) => (
                                <Button
                                  key={k}
                                  type="button"
                                  variant="outline"
                                  size="sm"
                                  className="h-7 px-2 text-xs"
                                  onClick={() => handlePickCtx(f.path, k)}
                                >
                                  {k.replace(`${inner}.`, "")}
                                </Button>
                              ))}
                            </div>
                          );
                        })()}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <Label className="text-xs">Output (output_schema)</Label>
          {!!outputSchema && (
            <Button
              variant="ghost"
              size="sm"
              className="h-7 px-2 text-xs text-muted-foreground"
              onClick={() => {
                navigator.clipboard.writeText(outputSchemaText);
                toast({ title: "Output schema copied" });
              }}
              data-testid="button-copy-crm-output-schema"
            >
              <Copy className="h-3.5 w-3.5 mr-1" />
              Copy
            </Button>
          )}
        </div>

        {!outputSchema ? (
          <div className="rounded-md border bg-muted/30 p-3 text-xs text-muted-foreground">
            No output_schema loaded for this operation yet.
          </div>
        ) : (
          <Collapsible>
            <CollapsibleTrigger className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
              <ChevronDown className="h-3 w-3" />
              View output schema
            </CollapsibleTrigger>
            <CollapsibleContent className="pt-2">
              <pre className="text-xs bg-muted/50 p-2 rounded border overflow-x-auto max-h-[260px] overflow-y-auto">
                {outputSchemaText}
              </pre>
              <p className="text-[11px] text-muted-foreground mt-2">
                El output queda disponible como <code>nodes.&lt;nodeId&gt;.output.*</code> para el Normalize.
              </p>
            </CollapsibleContent>
          </Collapsible>
        )}
      </div>
    </div>
  );
}

// =============================================================================
// DataLab Forms
// =============================================================================

/**
 * DataLab File Adapter Form
 * Configures a flow node to run an import process on a file from upstream data
 * 
 * Config schema:
 * - import_process_id: string (required) - ID of the import process to use
 * - file_source: string (required) - Expression referencing file ID from upstream (e.g., "{{input.body.file_id}}")
 */
function DataLabFileAdapterForm({ config, onConfigChange, availableData = [] }: NodeConfigFormProps) {
  const { toast } = useToast();
  const [isSelectorOpen, setIsSelectorOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  
  // Fetch import processes list
  const { data: processesData, isLoading: processesLoading, refetch } = useDataLabImportProcesses(1, 100);
  const processes = processesData?.results || [];
  
  // Fetch selected process details
  const { data: selectedProcess, isLoading: processLoading } = useDataLabImportProcess(config?.import_process_id);
  
  // Filter processes by search
  const filteredProcesses = useMemo(() => {
    if (!searchQuery.trim()) return processes;
    const q = searchQuery.toLowerCase();
    return processes.filter((p: ImportProcess) => 
      p.name?.toLowerCase().includes(q) || 
      p.file_type?.toLowerCase().includes(q)
    );
  }, [processes, searchQuery]);

  const handleSelectProcess = (processId: string) => {
    const process = processes.find((p: ImportProcess) => p.id === processId);
    if (!process) return;
    setIsSelectorOpen(false);
    onConfigChange({
      ...config,
      import_process_id: process.id,
      import_process_name: process.name,
      import_process_file_type: process.file_type,
    });
  };

  const handleFileSourceChange = (value: string) => {
    onConfigChange({
      ...config,
      file_source: value,
    });
  };

  return (
    <div className="space-y-4">
      {/* Import Process Selector */}
      <div className="space-y-2">
        <Label className="text-xs font-medium">Import Process</Label>
        <Popover open={isSelectorOpen} onOpenChange={setIsSelectorOpen}>
          <PopoverTrigger asChild>
            <Button
              variant="outline"
              role="combobox"
              aria-expanded={isSelectorOpen}
              className="w-full justify-between text-sm h-9"
              data-testid="button-select-import-process"
            >
              {config?.import_process_id ? (
                <span className="truncate">
                  {config.import_process_name || selectedProcess?.name || "Loading..."}
                </span>
              ) : (
                <span className="text-muted-foreground">Select import process...</span>
              )}
              <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-[350px] p-0" align="start">
            <Command>
              <CommandInput 
                placeholder="Search import processes..." 
                value={searchQuery}
                onValueChange={setSearchQuery}
              />
              <CommandList>
                <CommandEmpty>
                  {processesLoading ? (
                    <div className="flex items-center justify-center py-4">
                      <Loader2 className="h-4 w-4 animate-spin mr-2" />
                      Loading...
                    </div>
                  ) : (
                    <div className="py-4 text-center text-sm text-muted-foreground">
                      No import processes found.
                      <br />
                      <a href="/datalab/import-process/new" target="_blank" className="text-primary hover:underline">
                        Create one in DataLab
                      </a>
                    </div>
                  )}
                </CommandEmpty>
                <CommandGroup>
                  {filteredProcesses.map((process: ImportProcess) => (
                    <CommandItem
                      key={process.id}
                      value={process.id}
                      onSelect={() => handleSelectProcess(process.id)}
                      className="cursor-pointer"
                    >
                      <div className="flex items-center gap-2 w-full">
                        <Check
                          className={cn(
                            "h-4 w-4",
                            config?.import_process_id === process.id ? "opacity-100" : "opacity-0"
                          )}
                        />
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium truncate">{process.name}</p>
                          <p className="text-xs text-muted-foreground">
                            {process.file_type?.toUpperCase()} • {process.contract_json?.mapping?.length || 0} columns
                          </p>
                        </div>
                      </div>
                    </CommandItem>
                  ))}
                </CommandGroup>
              </CommandList>
            </Command>
          </PopoverContent>
        </Popover>
        
        {/* Refresh button */}
        <div className="flex justify-end">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => refetch()}
            className="h-7 text-xs"
          >
            <RefreshCw className="h-3 w-3 mr-1" />
            Refresh
          </Button>
        </div>
      </div>

      {/* Selected Process Info */}
      {selectedProcess && (
        <div className="rounded-md border bg-muted/30 p-3 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium">Selected Process</span>
            <Badge variant="outline" className="text-[10px]">
              {selectedProcess.file_type?.toUpperCase()}
            </Badge>
          </div>
          <p className="text-sm font-medium">{selectedProcess.name}</p>
          {selectedProcess.contract_json?.mapping && selectedProcess.contract_json.mapping.length > 0 && (
            <div className="text-xs text-muted-foreground">
              <span className="font-medium">{selectedProcess.contract_json.mapping.length}</span> column mappings configured
            </div>
          )}
        </div>
      )}

      {/* File Source Expression */}
      <div className="space-y-2">
        <Label className="text-xs font-medium">File Source (Expression)</Label>
        <div className="space-y-1">
          <Input
            value={config?.file_source || ""}
            onChange={(e) => handleFileSourceChange(e.target.value)}
            placeholder="{{input.body.file_id}}"
            className="text-sm font-mono h-9"
            data-testid="input-file-source"
          />
          <p className="text-[11px] text-muted-foreground">
            Expression to get the file ID from upstream data. Example: <code className="bg-muted px-1 rounded">{"{{input.body.file_id}}"}</code>
          </p>
        </div>
        
        {/* Available data helper */}
        {availableData.length > 0 && (
          <Collapsible>
            <CollapsibleTrigger className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
              <ChevronDown className="h-3 w-3" />
              Available data fields
            </CollapsibleTrigger>
            <CollapsibleContent className="pt-2">
              <ScrollArea className="h-[120px] rounded border bg-muted/30 p-2">
                <div className="space-y-1">
                  {availableData.map((field) => (
                    <button
                      key={field.key}
                      type="button"
                      className="w-full text-left text-xs px-2 py-1 rounded hover:bg-muted"
                      onClick={() => handleFileSourceChange(`{{${field.key}}}`)}
                    >
                      <code className="text-primary">{field.key}</code>
                      <span className="text-muted-foreground ml-2">({field.type})</span>
                    </button>
                  ))}
                </div>
              </ScrollArea>
            </CollapsibleContent>
          </Collapsible>
        )}
      </div>

      {/* Info */}
      <Alert>
        <Zap className="h-4 w-4" />
        <AlertTitle className="text-xs">How it works</AlertTitle>
        <AlertDescription className="text-xs text-muted-foreground">
          This node will run the selected import process on the file referenced by the expression.
          The output will be a ResultSet ID that can be used by downstream nodes.
        </AlertDescription>
      </Alert>
    </div>
  );
}

/**
 * DataLab Promote Form
 * Promotes a ResultSet to a named Dataset
 * 
 * Config schema:
 * - name: string (required) - Dataset name (can include expressions)
 * - description: string (optional) - Dataset description
 * - source: string (required) - Expression referencing upstream resultset ID
 * - strategy: "replace" | "append" | "merge" (default: "replace")
 * - merge_keys: string[] (required if strategy = "merge")
 */
function DataLabPromoteForm({ config, onConfigChange, availableData = [] }: NodeConfigFormProps) {
  const handleChange = (field: string, value: any) => {
    onConfigChange({
      ...config,
      [field]: value,
    });
  };

  const strategy = config?.strategy || "replace";

  return (
    <div className="space-y-4">
      {/* Dataset Name */}
      <div className="space-y-2">
        <Label className="text-xs font-medium">Dataset Name</Label>
        <Input
          value={config?.name || ""}
          onChange={(e) => handleChange("name", e.target.value)}
          placeholder="My Dataset"
          className="text-sm h-9"
          data-testid="input-dataset-name"
        />
        <p className="text-[11px] text-muted-foreground">
          Name for the promoted dataset. Can include expressions like <code className="bg-muted px-1 rounded">{"{{input.body.name}}"}</code>
        </p>
      </div>

      {/* Description */}
      <div className="space-y-2">
        <Label className="text-xs font-medium">Description (Optional)</Label>
        <Textarea
          value={config?.description || ""}
          onChange={(e) => handleChange("description", e.target.value)}
          placeholder="Dataset description..."
          className="text-sm"
          rows={2}
          data-testid="textarea-dataset-description"
        />
      </div>

      {/* Source ResultSet Expression */}
      <div className="space-y-2">
        <Label className="text-xs font-medium">Source ResultSet ID</Label>
        <div className="space-y-1">
          <Input
            value={config?.source || ""}
            onChange={(e) => handleChange("source", e.target.value)}
            placeholder="{{nodes.import_node.output.resultset_id}}"
            className="text-sm font-mono h-9"
            data-testid="input-source-resultset"
          />
          <p className="text-[11px] text-muted-foreground">
            Expression referencing the ResultSet ID from an upstream node
          </p>
        </div>
        
        {/* Available data helper */}
        {availableData.length > 0 && (
          <Collapsible>
            <CollapsibleTrigger className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
              <ChevronDown className="h-3 w-3" />
              Available data fields
            </CollapsibleTrigger>
            <CollapsibleContent className="pt-2">
              <ScrollArea className="h-[120px] rounded border bg-muted/30 p-2">
                <div className="space-y-1">
                  {availableData.map((field) => (
                    <button
                      key={field.key}
                      type="button"
                      className="w-full text-left text-xs px-2 py-1 rounded hover:bg-muted"
                      onClick={() => handleChange("source", `{{${field.key}}}`)}
                    >
                      <code className="text-primary">{field.key}</code>
                      <span className="text-muted-foreground ml-2">({field.type})</span>
                    </button>
                  ))}
                </div>
              </ScrollArea>
            </CollapsibleContent>
          </Collapsible>
        )}
      </div>

      {/* Accumulation Strategy */}
      <div className="space-y-2">
        <Label className="text-xs font-medium">Accumulation Strategy</Label>
        <Select
          value={strategy}
          onValueChange={(value) => handleChange("strategy", value)}
        >
          <SelectTrigger className="h-9 text-sm" data-testid="select-strategy">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="replace">Replace (overwrite existing)</SelectItem>
            <SelectItem value="append">Append (add rows)</SelectItem>
            <SelectItem value="merge">Merge (upsert by keys)</SelectItem>
          </SelectContent>
        </Select>
        <p className="text-[11px] text-muted-foreground">
          {strategy === "replace" && "Completely replace the dataset contents with the new data"}
          {strategy === "append" && "Add new rows to the existing dataset"}
          {strategy === "merge" && "Update existing rows by key, insert new ones"}
        </p>
      </div>

      {/* Merge Keys (only if strategy is merge) */}
      {strategy === "merge" && (
        <div className="space-y-2">
          <Label className="text-xs font-medium">Merge Keys</Label>
          <Input
            value={(config?.merge_keys || []).join(", ")}
            onChange={(e) => {
              const keys = e.target.value
                .split(",")
                .map((k) => k.trim())
                .filter(Boolean);
              handleChange("merge_keys", keys);
            }}
            placeholder="id, email"
            className="text-sm h-9"
            data-testid="input-merge-keys"
          />
          <p className="text-[11px] text-muted-foreground">
            Comma-separated column names to use as unique keys for merging
          </p>
        </div>
      )}

      {/* Info */}
      <Alert>
        <Zap className="h-4 w-4" />
        <AlertTitle className="text-xs">How it works</AlertTitle>
        <AlertDescription className="text-xs text-muted-foreground">
          This node promotes a temporary ResultSet to a durable, named Dataset.
          The output will be the Dataset ID for downstream use.
        </AlertDescription>
      </Alert>
    </div>
  );
}

// Default/Generic Form for unknown types
function GenericConfigForm({ config, onConfigChange }: NodeConfigFormProps) {
  return (
    <div className="space-y-3">
      <div>
        <Label htmlFor="config-json" className="text-xs">Configuration (JSON)</Label>
        <Textarea
          id="config-json"
          value={JSON.stringify(config, null, 2)}
          onChange={(e) => {
            try {
              const parsed = JSON.parse(e.target.value);
              onConfigChange(parsed);
            } catch {
              // Invalid JSON, don't update
            }
          }}
          rows={8}
          className="text-sm font-mono"
          data-testid="textarea-config-json"
        />
      </div>
      <p className="text-xs text-muted-foreground">
        Edit the configuration as JSON. Must be valid JSON format.
      </p>
    </div>
  );
}

// Form component registry
const formComponentRegistry: Record<string, React.ComponentType<NodeConfigFormProps>> = {
  // HTTP requests
  form_http_request: HttpRequestForm,
  http: HttpRequestForm,
  
  // Email
  form_email: EmailForm,
  email: EmailForm,
  form_email_account_picker: (props: NodeConfigFormProps) => <AccountPickerForm {...props} kind="email" />,
  form_calendar_account_picker: (props: NodeConfigFormProps) => <AccountPickerForm {...props} kind="calendar" />,
  
  // Scripts
  form_script: ScriptForm,
  script: ScriptForm,
  code: ScriptForm,
  
  // AI Agents
  form_agent: AgentForm,
  agent: AgentForm,
  ai: AgentForm,
  
  // Webhooks
  form_webhook: WebhookForm,
  webhook: WebhookForm,
  
  // Logic
  form_branch: BranchForm,
  branch: BranchForm,
  logic_branch: BranchForm,
  form_condition: ConditionForm,
  condition: ConditionForm,
  logic_condition: ConditionForm,
  
  form_while: WhileForm,
  while: WhileForm,
  loop: WhileForm,
  logic_while: WhileForm,

  // Normalize (ctx contract)
  form_normalize: NormalizeForm,
  normalize: NormalizeForm,
  logic_normalize: NormalizeForm,
  
  // WhatsApp
  form_whatsapp_template: WhatsAppTemplateForm,
  whatsapp: WhatsAppTemplateForm,
  
  // Event triggers
  form_event: EventTriggerForm,
  event: EventTriggerForm,
  trigger_event: EventTriggerForm,
  
  // Schedule triggers
  form_schedule: ScheduleTriggerForm,
  schedule: ScheduleTriggerForm,
  scheduled: ScheduleTriggerForm,
  trigger_scheduled: ScheduleTriggerForm,
  cron: ScheduleTriggerForm,
  trigger_cron: ScheduleTriggerForm,
  
  // Data operations - Set Values
  form_set_values: SetValuesForm,
  set_values: SetValuesForm,
  data_set_values: SetValuesForm,
  set_value: SetValuesForm,
  assign: SetValuesForm,

  // CRM CRUD
  tool_crm_crud: CrmCrudForm,
  crm_crud: CrmCrudForm,

  // DataLab
  datalab_file_adapter: DataLabFileAdapterForm,
  datalab_promote: DataLabPromoteForm,
};

interface DynamicNodeConfigFormProps {
  formComponent?: string;
  nodeType: string;
  config: Record<string, any>;
  onConfigChange: (updates: Record<string, any>) => void;
  availableData?: AvailableDataField[];
  dataNodes?: any[];
  hints?: NodeHints;
  scope?: NodeConfigFormProps["scope"];
}

/**
 * Dynamic form renderer that selects the appropriate form based on formComponent or nodeType
 */
export function DynamicNodeConfigForm({
  formComponent,
  nodeType,
  config,
  onConfigChange,
  availableData,
  dataNodes,
  hints,
  scope,
}: DynamicNodeConfigFormProps) {
  // First try to find form by formComponent
  let FormComponent = formComponent ? formComponentRegistry[formComponent] : undefined;
  
  // Fallback: try to match by nodeType keywords
  if (!FormComponent) {
    const typeKey = Object.keys(formComponentRegistry).find((key) =>
      nodeType.toLowerCase().includes(key)
    );
    FormComponent = typeKey ? formComponentRegistry[typeKey] : undefined;
  }
  
  // Final fallback: use generic JSON editor
  if (!FormComponent) {
    FormComponent = GenericConfigForm;
  }
  
  return (
    <FormComponent
      config={config}
      onConfigChange={onConfigChange}
      availableData={availableData}
      dataNodes={dataNodes}
      hints={hints}
      scope={scope}
    />
  );
}
