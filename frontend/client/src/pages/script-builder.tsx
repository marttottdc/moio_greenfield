import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import { useRoute, useLocation } from "wouter";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Editor } from "@monaco-editor/react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import {
  ArrowLeft,
  Save,
  Play,
  Check,
  X,
  Clock,
  FileCode,
  Terminal,
  Loader2,
  Plus,
  Trash2,
  CheckCircle,
  XCircle,
} from "lucide-react";
import { apiRequest, fetchJson } from "@/lib/queryClient";
import { apiV1 } from "@/lib/api";
import { useToast } from "@/hooks/use-toast";

interface Script {
  id: string;
  name: string;
  description: string;
  code: string;
  language: string;
  params_schema?: Record<string, any>;
  status: "draft" | "pending_approval" | "approved" | "rejected";
  created_at?: string;
  updated_at?: string;
}

interface ParamDef {
  name: string;
  type: string;
  required: boolean;
  default?: string;
}

const DEFAULT_SCRIPT_CODE = `def main(params):
    """
    Entry point for the script. The function MUST be named 'main'.
    
    Args:
        params (dict): Input parameters passed to the script
                       Access values with params.get('param_name')
    
    Returns:
        dict: Output data from the script
    """
    print(f"Script started with params: {params}")
    
    # Your script logic here
    result = {
        'status': 'success',
        'data': {}
    }
    
    return result
`;

export default function ScriptBuilder() {
  const [, params] = useRoute("/scripts/:id/edit");
  const [, navigate] = useLocation();
  const scriptId = params?.id;
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const logsEndRef = useRef<HTMLDivElement>(null);

  // Form state
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [code, setCode] = useState(DEFAULT_SCRIPT_CODE);
  const [paramsSpec, setParamsSpec] = useState<Record<string, ParamDef>>({});
  
  // Execution state
  const [testParams, setTestParams] = useState<Record<string, string>>({});
  const [executionResult, setExecutionResult] = useState<{
    status: "pending" | "running" | "success" | "failed";
    run_id?: string;
    task_id?: string;
    output?: any;
    error?: string;
    logs?: Array<{ timestamp: string; level: string; message: string }>;
  } | null>(null);
  const pollingRef = useRef<NodeJS.Timeout | null>(null);

  // Poll for task status via Celery
  const pollTaskStatus = useCallback(async (taskId: string) => {
    try {
      const response = await apiRequest("GET", apiV1(`/flows/task-executions/celery-status/${taskId}/`));
      const data = await response.json();
      
      // Response shape: { state, ready, successful, failed, result?, error?, traceback? }
      const { state, ready, successful, result, error, traceback } = data;
      
      if (ready && successful) {
        if (pollingRef.current) {
          clearInterval(pollingRef.current);
          pollingRef.current = null;
        }
        setExecutionResult((prev) => ({
          ...prev!,
          status: "success",
          output: result,
          logs: result?.logs,
        }));
        toast({ description: "Script execution completed!" });
      } else if (ready && !successful) {
        if (pollingRef.current) {
          clearInterval(pollingRef.current);
          pollingRef.current = null;
        }
        setExecutionResult((prev) => ({
          ...prev!,
          status: "failed",
          error: error || traceback?.split("\n").pop() || "Execution failed",
        }));
        toast({ variant: "destructive", description: "Script execution failed" });
      } else if (state === "STARTED" || state === "RETRY") {
        setExecutionResult((prev) => ({ ...prev!, status: "running" }));
      }
      // PENDING means it's still queued - keep polling
    } catch (err) {
      console.error("Failed to poll task status:", err);
    }
  }, [toast]);

  // Clean up polling on unmount
  useEffect(() => {
    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
      }
    };
  }, []);

  // Fetch script data if editing
  const scriptQuery = useQuery<Script | null>({
    queryKey: ["automation-scripts", scriptId],
    queryFn: async () => {
      if (!scriptId) return null;
      const response = await fetchJson<any>(apiV1(`/scripts/${scriptId}/`));
      // Handle both { script: {...} } and direct {...} responses
      return response?.script || response;
    },
    enabled: Boolean(scriptId),
  });

  // Track loaded script to prevent re-loading
  const [loadedScriptId, setLoadedScriptId] = useState<string | null>(null);

  // Load script data
  useEffect(() => {
    if (scriptId && scriptQuery.data && loadedScriptId !== scriptId) {
      const script = scriptQuery.data;
      console.log("Loading Automation Studio script data:", script);
      console.log("  - params_schema:", script.params_schema);
      setLoadedScriptId(scriptId);
      setName(script.name || "");
      setDescription(script.description || "");
      // Backend returns code inside latest_version
      setCode((script as any)?.latest_version?.code || (script as any)?.code || DEFAULT_SCRIPT_CODE);
      
      // Convert params_schema to paramsSpec
      const rawParamsSchema =
        // Canonical backend fields (v2)
        (script as any)?.latest_version?.parameters ??
        (script as any)?.latest_version?.parameters_text ??
        (script as any)?.params_text ??
        // Backward/compat fields
        (script as any).params_schema_json ??
        (script as any).params_schema;

      const parsedParamsSchema = (() => {
        if (!rawParamsSchema) return null;
        if (typeof rawParamsSchema === "object") return rawParamsSchema as Record<string, any>;
        if (typeof rawParamsSchema === "string") {
          try {
            const parsed = JSON.parse(rawParamsSchema);
            return parsed && typeof parsed === "object" ? (parsed as Record<string, any>) : null;
          } catch {
            return null;
          }
        }
        return null;
      })();

      if (parsedParamsSchema && typeof parsedParamsSchema === "object") {
        const converted: Record<string, ParamDef> = {};
        Object.entries(parsedParamsSchema).forEach(([key, value]) => {
          if (typeof value === "object" && value !== null) {
            converted[key] = {
              name: key,
              type: (value as any).type || "string",
              required: (value as any).required ?? true,
              default: (value as any).default,
            };
          } else {
            converted[key] = {
              name: key,
              type: String(value),
              required: true,
            };
          }
        });
        console.log("  - Converted paramsSpec:", converted);
        setParamsSpec(converted);
      } else {
        console.log("  - No params_schema found, setting empty paramsSpec");
        setParamsSpec({});
      }
    } else if (!scriptId && loadedScriptId !== null) {
      // Reset for new script
      setLoadedScriptId(null);
      setName("");
      setDescription("");
      setCode(DEFAULT_SCRIPT_CODE);
      setParamsSpec({});
      setTestParams({});
      setExecutionResult(null);
    }
  }, [scriptId, scriptQuery.data, loadedScriptId]);

  // Auto-scroll logs
  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [executionResult?.logs]);

  // Save script mutation
  const saveMutation = useMutation({
    mutationFn: async () => {
      // Convert paramsSpec to params_schema format
      const params_schema: Record<string, any> = {};
      const used = new Set<string>();
      for (const [key, def] of Object.entries(paramsSpec)) {
        const resolvedName = (def?.name || key).trim();
        if (!resolvedName) continue;
        if (used.has(resolvedName)) {
          throw new Error(`Duplicate parameter name "${resolvedName}". Parameter names must be unique.`);
        }
        used.add(resolvedName);
        params_schema[resolvedName] = {
          type: def.type,
          required: def.required,
          ...(def.default !== undefined && { default: def.default }),
        };
      }

      const payload = {
        name: name.trim(),
        description: description.trim(),
        code: code.trim(),
        language: "python",
        // Send both keys for backend compatibility (some versions accept params_schema_json)
        params_schema,
        params_schema_json: params_schema,
        // Canonical backend field (v2): persisted on Script + latest_version
        params_text: JSON.stringify(params_schema, null, 2),
        status: "draft",
      };

      if (scriptId) {
        const res = await apiRequest("PATCH", apiV1(`/scripts/${scriptId}/`), { data: payload });
        return await res.json();
      } else {
        const res = await apiRequest("POST", apiV1("/scripts/"), { data: payload });
        return await res.json();
      }
    },
    onSuccess: (data) => {
      toast({ description: "Script saved" });
      if (!scriptId && data.id) {
        navigate(`/scripts/${data.id}/edit`);
      }
      queryClient.invalidateQueries({ queryKey: ["automation-scripts"] });
      queryClient.invalidateQueries({ queryKey: [apiV1("/scripts/")] });
    },
    onError: (error: any) => {
      toast({
        variant: "destructive",
        description: error?.message || "Failed to save script",
      });
    },
  });

  // Execute script mutation
  const executeMutation = useMutation({
    mutationFn: async (targetScriptId: string) => {
      // Build params object from testParams
      const params: Record<string, any> = {};
      Object.entries(paramsSpec).forEach(([key, spec]) => {
        const value = testParams[key];
        if (value === undefined) return;
        const resolvedName = (spec?.name || key).trim() || key;
        // Convert value based on type
        if (spec?.type === "number" || spec?.type === "integer") {
          params[resolvedName] = Number(value);
        } else if (spec?.type === "boolean") {
          params[resolvedName] = value === "true";
        } else {
          params[resolvedName] = value;
        }
      });

      const res = await apiRequest("POST", apiV1(`/scripts/execute/`), {
        data: { script_id: targetScriptId, params },
      });
      return await res.json();
    },
    onSuccess: (data) => {
      // Check if async response (has run.id or task_id)
      const runId = data.run?.id;
      const taskId = data.task_id || data.run?.celery_task_id;
      
      if (runId || taskId) {
        // Async execution - start polling
        setExecutionResult({
          status: "running",
          run_id: runId,
          task_id: taskId,
        });
        toast({ description: `Execution started (run: ${(runId || taskId)?.slice(0, 8)}...)` });
        
        if (taskId) {
          pollingRef.current = setInterval(() => {
            pollTaskStatus(taskId);
          }, 2000);
        }
      } else {
        // Synchronous response (legacy or immediate result)
        setExecutionResult({
          status: data.status === "success" || data.ok ? "success" : "failed",
          output: data.output || data.result,
          error: data.error,
          logs: data.logs,
        });

        if (data.status === "success" || data.ok) {
          toast({ description: "Script executed successfully" });
        } else {
          toast({ variant: "destructive", description: data.error || "Execution failed" });
        }
      }
    },
    onError: (error: any) => {
      setExecutionResult({
        status: "failed",
        error: error?.message || "Execution failed",
      });
      toast({ variant: "destructive", description: error?.message || "Execution failed" });
    },
  });

  const handleSave = () => {
    if (!name?.trim()) {
      toast({ variant: "destructive", description: "Script name is required" });
      return;
    }
    if (!code?.trim()) {
      toast({ variant: "destructive", description: "Script code is required" });
      return;
    }
    saveMutation.mutate();
  };

  const handleExecute = async () => {
    if (!name?.trim()) {
      toast({ variant: "destructive", description: "Script name is required" });
      return;
    }
    if (!code?.trim()) {
      toast({ variant: "destructive", description: "Script code is required" });
      return;
    }

    // Check required params have values
    const missingParams = Object.entries(paramsSpec)
      .filter(([key, def]) => def.required && !testParams[key])
      .map(([key, def]) => (def?.name || key).trim() || key);
    
    if (missingParams.length > 0) {
      toast({
        variant: "destructive",
        description: `Missing required parameters: ${missingParams.join(", ")}`,
      });
      return;
    }

    // Clear any previous polling
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }

    let targetId = scriptId;

    // Auto-save if new script
    if (!targetId) {
      try {
        const params_schema: Record<string, any> = {};
        const used = new Set<string>();
        for (const [key, def] of Object.entries(paramsSpec)) {
          const resolvedName = (def?.name || key).trim();
          if (!resolvedName) continue;
          if (used.has(resolvedName)) {
            throw new Error(`Duplicate parameter name "${resolvedName}". Parameter names must be unique.`);
          }
          used.add(resolvedName);
          params_schema[resolvedName] = {
            type: def.type,
            required: def.required,
            ...(def.default !== undefined && { default: def.default }),
          };
        }

        const res = await apiRequest("POST", apiV1("/scripts/"), {
          data: {
            name: name.trim(),
            description: description.trim(),
            code: code.trim(),
            language: "python",
            params_schema,
            params_schema_json: params_schema,
            params_text: JSON.stringify(params_schema, null, 2),
            status: "draft",
    },
  });
        const created = await res.json();
        toast({ description: "Script saved" });
        targetId = created.id;
        navigate(`/scripts/${created.id}/edit`);
        queryClient.invalidateQueries({ queryKey: ["automation-scripts"] });
        queryClient.invalidateQueries({ queryKey: [apiV1("/scripts/")] });
      } catch (err: any) {
        toast({ variant: "destructive", description: err?.message || "Failed to save script" });
        return;
      }
    }

    setExecutionResult({ status: "running" });
    executeMutation.mutate(targetId);
  };

  const addParam = () => {
    const paramKey = `param${Object.keys(paramsSpec).length + 1}`;
    setParamsSpec((prev) => ({
      ...prev,
      [paramKey]: { name: paramKey, type: "string", required: true },
    }));
  };

  const removeParam = (key: string) => {
    setParamsSpec((prev) => {
      const newSpec = { ...prev };
      delete newSpec[key];
      return newSpec;
    });
    setTestParams((prev) => {
      const newParams = { ...prev };
      delete newParams[key];
      return newParams;
    });
  };

  const updateParam = (key: string, field: keyof ParamDef, value: any) => {
    setParamsSpec((prev) => ({
      ...prev,
      [key]: { ...prev[key], [field]: value },
    }));
  };

  const getStatusBadge = (status?: string) => {
    const statusConfig = {
      draft: { variant: "outline" as const, label: "Draft", icon: FileCode },
      pending_approval: { variant: "secondary" as const, label: "Pending", icon: Clock },
      approved: { variant: "default" as const, label: "Approved", icon: Check },
      rejected: { variant: "destructive" as const, label: "Rejected", icon: X },
    };

    const config = statusConfig[status as keyof typeof statusConfig] || statusConfig.draft;
    const Icon = config.icon;

    return (
      <Badge variant={config.variant} className="gap-1">
        <Icon className="h-3 w-3" />
        {config.label}
      </Badge>
    );
  };

  const isSaving = saveMutation.isPending;
  const isExecuting = executeMutation.isPending;
  const paramKeys = Object.keys(paramsSpec);
  const resolvedParamNames = useMemo(() => {
    const names = paramKeys.map((k) => (paramsSpec[k]?.name || k).trim()).filter(Boolean);
    const counts = new Map<string, number>();
    for (const n of names) counts.set(n, (counts.get(n) ?? 0) + 1);
    return {
      counts,
      getError: (key: string) => {
        const name = (paramsSpec[key]?.name || key).trim();
        if (!name) return "Parameter name is required";
        if (counts.get(name) && (counts.get(name) as number) > 1) return "Duplicate parameter name";
        return null;
      },
    };
  }, [paramKeys, paramsSpec]);

  return (
    <div className="h-screen flex flex-col overflow-hidden">
      {/* Compact header bar */}
      <div className="flex items-center gap-3 px-4 py-2 border-b bg-background shrink-0">
          <Button
            variant="ghost"
            size="sm"
          className="h-7 w-7 p-0"
            onClick={() => navigate("/workflows")}
          >
            <ArrowLeft className="h-4 w-4" />
          </Button>
        <span className="text-sm font-medium text-muted-foreground">Automation Studio</span>
        <span className="text-muted-foreground">/</span>
        <span className="text-sm font-medium">Script</span>
      </div>

      {/* Main content */}
      <div className="flex-1 overflow-hidden p-4">
        <div className="grid gap-4 lg:grid-cols-3 h-full">
          {/* Script details - 2 columns */}
          <Card className="lg:col-span-2 flex flex-col">
            <CardHeader className="pb-3 flex-row items-center justify-between space-y-0">
              <div>
                <CardTitle className="flex items-center gap-2">
                  {scriptId ? "Edit Script" : "New Script"}
                  {scriptQuery.data && getStatusBadge(scriptQuery.data.status)}
                </CardTitle>
                <CardDescription>
                  Python script for automation. Function must be named <code className="bg-muted px-1 rounded">main</code>.
                </CardDescription>
              </div>
              <Button size="sm" onClick={handleSave} disabled={isSaving}>
                {isSaving ? (
                  <Loader2 className="h-4 w-4 animate-spin mr-2" />
                ) : (
                  <Save className="h-4 w-4 mr-2" />
                )}
                {scriptId ? "Save" : "Create"}
              </Button>
            </CardHeader>
            <CardContent className="space-y-4 flex-1 flex flex-col min-h-0">
              <div>
                <Label htmlFor="name" className="text-xs">Name *</Label>
                <Input
                  id="name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="My Automation Script"
                  className="h-8"
                />
              </div>
                <div>
                <Label htmlFor="description" className="text-xs">Description</Label>
                  <Textarea
                    id="description"
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    placeholder="Describe what this script does..."
                  rows={2}
                  className="mt-1"
                  />
                </div>

              <div className="flex-1 flex flex-col min-h-0">
                <Label className="text-xs mb-1">Python Code *</Label>
                <div className="flex-1 border rounded-md overflow-hidden min-h-[300px]">
                  <Editor
                    height="100%"
                    language="python"
                    value={code}
                    onChange={(value) => setCode(value || "")}
                    theme="vs-dark"
                    options={{
                      minimap: { enabled: false },
                      fontSize: 13,
                      lineNumbers: "on",
                      scrollBeyondLastLine: false,
                      automaticLayout: true,
                      tabSize: 4,
                      wordWrap: "on",
                      scrollbar: {
                        vertical: "auto",
                        horizontal: "auto",
                        verticalScrollbarSize: 10,
                        horizontalScrollbarSize: 10,
                      },
                    }}
                  />
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Right column */}
          <div className="space-y-4 overflow-auto">
            {/* Parameters */}
            <Card>
              <CardHeader className="pb-2 pt-3 px-3">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-sm">Parameters</CardTitle>
                  <Button variant="outline" size="sm" className="h-6 text-xs" onClick={addParam}>
                    <Plus className="h-3 w-3 mr-1" />
                    Add
                  </Button>
        </div>
              </CardHeader>
              <CardContent className="px-3 pb-3">
                {paramKeys.length === 0 ? (
                  <p className="text-xs text-muted-foreground">
                    No parameters defined.
                  </p>
                ) : (
                  <div className="space-y-2">
                    {paramKeys.map((key) => {
                      const spec = paramsSpec[key];
                      const nameErr = resolvedParamNames.getError(key);
                      return (
                        <div key={key} className="p-2 border rounded space-y-1.5">
                          <div className="flex items-center justify-between">
                            <Input
                              value={spec.name}
                              onChange={(e) => updateParam(key, "name", e.target.value)}
                              className={`h-6 text-xs font-medium w-28 ${nameErr ? "border-destructive" : ""}`}
                              placeholder="param_name"
                            />
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-6 w-6 p-0"
                              onClick={() => removeParam(key)}
                            >
                              <Trash2 className="h-3 w-3" />
                            </Button>
            </div>
                          {nameErr && (
                            <p className="text-[11px] text-destructive">{nameErr}</p>
                          )}
                          <div className="flex gap-2 items-center">
                            <select
                              value={spec.type}
                              onChange={(e) => updateParam(key, "type", e.target.value)}
                              className="h-6 text-xs border rounded px-1.5 bg-background"
                            >
                              <option value="string">string</option>
                              <option value="number">number</option>
                              <option value="integer">integer</option>
                              <option value="boolean">boolean</option>
                            </select>
                            <label className="flex items-center gap-1 text-xs">
                              <input
                                type="checkbox"
                                checked={spec.required}
                                onChange={(e) => updateParam(key, "required", e.target.checked)}
                                className="h-3 w-3"
                              />
                              Required
                            </label>
            </div>
          </div>
                      );
                    })}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Test Execution */}
            <Card>
              <CardHeader className="pb-2 pt-3 px-3">
                <div className="flex items-center gap-2">
                  <Terminal className="h-3.5 w-3.5" />
                  <CardTitle className="text-sm">Test Execution</CardTitle>
                </div>
              </CardHeader>
              <CardContent className="space-y-3 px-3 pb-3">
                {paramKeys.length > 0 ? (
                  <div className="space-y-2">
                    <p className="text-xs text-muted-foreground">
                      Enter test values:
                    </p>
                    {paramKeys.map((key) => (
                      <div key={key}>
                        <Label className="text-xs">
                          {paramsSpec[key]?.name || key}
                          {paramsSpec[key]?.required && " *"}
                          <span className="text-muted-foreground ml-1">
                            ({paramsSpec[key]?.type})
                          </span>
                        </Label>
                        <Input
                          value={testParams[key] || ""}
                          onChange={(e) =>
                            setTestParams((prev) => ({ ...prev, [key]: e.target.value }))
                          }
                          placeholder={`Enter ${paramsSpec[key]?.type}...`}
                          className="mt-1 h-7 text-xs"
                        />
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-muted-foreground">
                    Add parameters to test with values.
                  </p>
                )}

                <Button
                  size="sm"
                  className="w-full h-8"
                  onClick={handleExecute}
                  disabled={isExecuting || isSaving}
                >
                  {isExecuting ? (
                    <Loader2 className="h-4 w-4 animate-spin mr-2" />
                  ) : (
                    <Play className="h-4 w-4 mr-2" />
                  )}
                  {!scriptId ? "Save & Run" : "Run Script"}
                </Button>

                {executionResult && (
                  <div
                    className={`p-2 rounded-md text-xs ${
                      executionResult.status === "success"
                        ? "bg-green-500/10 text-green-700 dark:text-green-400"
                        : executionResult.status === "failed"
                        ? "bg-red-500/10 text-red-700 dark:text-red-400"
                        : "bg-blue-500/10 text-blue-700 dark:text-blue-400"
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      {executionResult.status === "success" && (
                        <CheckCircle className="h-3.5 w-3.5" />
                      )}
                      {executionResult.status === "failed" && (
                        <XCircle className="h-3.5 w-3.5" />
                      )}
                      {(executionResult.status === "pending" ||
                        executionResult.status === "running") && (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      )}
                      <span className="capitalize">{executionResult.status}</span>
                      {(executionResult.status === "pending" ||
                        executionResult.status === "running") && (
                        <span className="opacity-75">- polling...</span>
                      )}
                    </div>
                    {(executionResult.run_id || executionResult.task_id) && (
                      <p className="text-xs mt-1 opacity-75">
                        Task: {(executionResult.task_id || executionResult.run_id)?.slice(0, 8)}...
                      </p>
                    )}
                    {executionResult.error && (
                      <p className="text-xs mt-1 text-red-600 dark:text-red-400">
                        {executionResult.error}
                      </p>
                    )}
                    {executionResult.status === "success" && executionResult.output && (
                      <pre className="text-xs mt-2 p-2 bg-background/50 rounded overflow-auto max-h-24">
                        {JSON.stringify(executionResult.output, null, 2)}
                      </pre>
                    )}
                  </div>
                )}

                {/* Execution Logs */}
                {executionResult?.logs && executionResult.logs.length > 0 && (
                  <div className="border rounded-md max-h-32 overflow-auto">
                    <div className="p-2 space-y-0.5 font-mono text-xs">
                      {executionResult.logs.map((log, index) => (
                  <div
                    key={index}
                          className={`p-1 rounded ${
                      log.level === "ERROR"
                        ? "bg-red-500/10 text-red-600 dark:text-red-400"
                        : log.level === "WARNING"
                        ? "bg-yellow-500/10 text-yellow-600 dark:text-yellow-400"
                              : "text-muted-foreground"
                    }`}
                  >
                          <span className="opacity-60">
                      {new Date(log.timestamp).toLocaleTimeString()}
                    </span>{" "}
                          [{log.level}] {log.message}
                        </div>
                      ))}
                      <div ref={logsEndRef} />
                    </div>
                  </div>
              )}
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </div>
  );
}
