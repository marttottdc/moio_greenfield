import { useState, useEffect, useRef, useCallback } from "react";
import { Editor } from "@monaco-editor/react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  useDataLabScripts,
  useDataLabScript,
  useDataLabScriptCreate,
  useDataLabScriptExecute,
  useDataLabResultSets,
} from "@/hooks/use-datalab";
import { Loader2, Save, Plus, Trash2, Play, CheckCircle, XCircle, Terminal, ExternalLink, AlertTriangle, ShieldAlert, Check } from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import { dataLabApi, apiV1 } from "@/lib/api";
import { apiRequest } from "@/lib/queryClient";
import { useMutation, useQueryClient } from "@tanstack/react-query";

const DEFAULT_SCRIPT_CODE = `import pandas as pd

def main(inputs):
    """
    Entry point for the script. The function MUST be named 'main'.
    
    Args:
        inputs: Dict of input DataFrames, keyed by input name
                e.g. inputs['input1'] returns a pandas DataFrame
        
    Returns:
        Dict of output DataFrames, keyed by output name
    """
    # Access your input DataFrames
    # df = inputs['input1']
    
    # Transform data
    # result = df.groupby('column').sum()
    
    # Return outputs as a dict
    return {
        # 'output1': result
    }
`;

export function ScriptEditor({
  id,
  onSelect,
}: {
  id?: string;
  onSelect: (view: "dataset" | "generator" | "script" | "welcome", id?: string) => void;
}) {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const { data: scripts, isLoading: scriptsLoading } = useDataLabScripts();
  const { data: script, isLoading: scriptLoading } = useDataLabScript(id);
  const { data: resultSets } = useDataLabResultSets(undefined, 1, 100);
  const createMutation = useDataLabScriptCreate();
  const executeMutation = useDataLabScriptExecute(id || "");

  const isLoading = scriptsLoading || (id ? scriptLoading : false);

  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [description, setDescription] = useState("");
  const [code, setCode] = useState(DEFAULT_SCRIPT_CODE);
  const [inputSpec, setInputSpec] = useState<Record<string, any>>({});
  const [outputSpec, setOutputSpec] = useState<Record<string, any>>({});
  
  // Execution state
  const [inputBindings, setInputBindings] = useState<Record<string, string>>({});
  const [executionResult, setExecutionResult] = useState<{
    status: "pending" | "running" | "success" | "failed";
    task_id?: string;
    run_id?: string;
    error?: string;
    traceback?: string;
    logs?: string[];
    result?: any;
    resultsets?: Array<{ id: string; name: string }>;
  } | null>(null);
  const pollingRef = useRef<NodeJS.Timeout | null>(null);
  
  // Validation state
  interface ValidationError {
    type: "syntax" | "structure" | "security" | "schema" | "pattern" | "required";
    message: string;
    line?: number | null;
  }
  const [validationResult, setValidationResult] = useState<{
    valid: boolean;
    errors: ValidationError[];
    warnings: ValidationError[];
  } | null>(null);
  const [isValidating, setIsValidating] = useState(false);

  // Track loaded script ID to prevent repeated loading
  const [loadedScriptId, setLoadedScriptId] = useState<string | null>(null);

  // Poll for script status using the dedicated status endpoint
  const pollScriptStatus = useCallback(async (taskId: string) => {
    try {
      const response = await apiRequest("GET", apiV1(`/datalab/scripts/status/${taskId}/`));
      const data = await response.json();
      
      // Response shape: { task_id, state, ready, successful, failed, run_id, run_status, output_payload?, error_payload? }
      const { ready, successful, run_id, output_payload, error_payload } = data;
      
      if (ready && successful) {
        // Task completed successfully
        if (pollingRef.current) {
          clearInterval(pollingRef.current);
          pollingRef.current = null;
        }
        
        // Extract resultset IDs from output_payload
        const resultsetIds = output_payload?.resultset_ids || {};
        const resultsets = Object.entries(resultsetIds).map(([name, id]) => ({
          id: id as string,
          name,
        }));
        
        setExecutionResult((prev) => ({
          ...prev!,
          status: "success",
          run_id,
          result: output_payload,
          resultsets,
          logs: output_payload?.logs,
        }));
        queryClient.invalidateQueries({ queryKey: ["datalab", "resultsets"] });
        toast({ description: "Script execution completed!" });
      } else if (ready && !successful) {
        // Task failed - extract detailed error info
        if (pollingRef.current) {
          clearInterval(pollingRef.current);
          pollingRef.current = null;
        }
        setExecutionResult((prev) => ({
          ...prev!,
          status: "failed",
          run_id,
          error: error_payload?.error || "Execution failed",
          traceback: error_payload?.traceback,
          logs: error_payload?.logs,
        }));
        toast({ variant: "destructive", description: error_payload?.error || "Script execution failed" });
      } else {
        // Task is still running or pending
        setExecutionResult((prev) => ({ 
          ...prev!, 
          status: data.state === "STARTED" ? "running" : "pending" 
        }));
      }
    } catch (err) {
      console.error("Failed to poll script status:", err);
      // Don't stop polling on network errors, could be transient
    }
  }, [queryClient, toast]);

  // Clean up polling on unmount
  useEffect(() => {
    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
      }
    };
  }, []);

  // Validate script
  const handleValidate = async () => {
    if (!code?.trim()) {
      toast({ variant: "destructive", description: "No code to validate" });
      return;
    }
    
    setIsValidating(true);
    setValidationResult(null);
    
    try {
      const response = await apiRequest("POST", apiV1("/datalab/scripts/validate/"), {
        data: {
          code: code.trim(),
          input_spec: inputSpec,
          output_spec: outputSpec,
        },
      });
      const result = await response.json();
      setValidationResult(result);
      
      if (result.valid) {
        toast({ description: "Script is valid!" });
      } else {
        toast({ 
          variant: "destructive", 
          description: `Validation failed: ${result.errors.length} error(s)` 
        });
      }
    } catch (err: any) {
      toast({ variant: "destructive", description: err?.message || "Validation failed" });
    } finally {
      setIsValidating(false);
    }
  };

  // Load existing script if editing
  useEffect(() => {
    if (id && script && loadedScriptId !== id) {
      console.log("Loading Data Lab script data:", script);
      setLoadedScriptId(id);
      setName(script.name || "");
      setSlug(script.slug || "");
      setDescription(script.description || "");
      setCode(script.code || DEFAULT_SCRIPT_CODE);
      
      // Backend returns input_spec/output_spec (not input_spec_json/output_spec_json)
      const scriptAny = script as any;
      const loadedInputSpec = scriptAny.input_spec || scriptAny.input_spec_json || {};
      const loadedOutputSpec = scriptAny.output_spec || scriptAny.output_spec_json || {};
      
      console.log("  - Loaded inputSpec:", loadedInputSpec);
      console.log("  - Loaded outputSpec:", loadedOutputSpec);
      
      setInputSpec(typeof loadedInputSpec === 'object' ? loadedInputSpec : {});
      setOutputSpec(typeof loadedOutputSpec === 'object' ? loadedOutputSpec : {});
    } else if (!id && loadedScriptId !== null) {
      // Reset for new script
      setLoadedScriptId(null);
      setName("");
      setSlug("");
      setDescription("");
      setCode(DEFAULT_SCRIPT_CODE);
      setInputSpec({});
      setOutputSpec({});
      setInputBindings({});
      setExecutionResult(null);
    }
  }, [id, script, loadedScriptId]);

  // Update mutation for existing scripts
  const updateMutation = useMutation({
    mutationFn: async () => {
      if (!id) throw new Error("No script ID");
      return dataLabApi.updateScript(id, {
        name: name.trim(),
        slug: slug.trim() || undefined,
        description: description.trim() || undefined,
        code: code.trim(),
        input_spec_json: inputSpec,
        output_spec_json: outputSpec,
      });
    },
    onSuccess: () => {
      toast({ description: "Script updated" });
      setValidationResult(null); // Clear validation on success
      queryClient.invalidateQueries({ queryKey: ["datalab", "scripts"] });
    },
    onError: (err: any) => {
      // Check for validation errors in the response
      const validationErrors = err?.validation_errors || [];
      if (err?.code && Array.isArray(err.code)) {
        err.code.forEach((msg: string) => {
          const match = msg.match(/\[(\w+)\]\s*(.+?)(?:\s*\(line\s*(\d+)\))?$/);
          if (match) {
            validationErrors.push({
              type: match[1],
              message: match[2],
              line: match[3] ? parseInt(match[3]) : null,
            });
          }
        });
      }
      if (validationErrors.length > 0) {
        setValidationResult({ valid: false, errors: validationErrors, warnings: [] });
        toast({ variant: "destructive", description: `Validation failed: ${validationErrors.length} error(s)` });
      } else {
        toast({ variant: "destructive", description: err?.message || "Failed to update script" });
      }
    },
  });

  const handleSave = async () => {
    if (!name?.trim()) {
      toast({ variant: "destructive", description: "Script name is required" });
      return;
    }
    if (!code?.trim()) {
      toast({ variant: "destructive", description: "Script code is required" });
      return;
    }

    try {
      if (id) {
        await updateMutation.mutateAsync();
      } else {
        const created = await createMutation.mutateAsync({
          name: name.trim(),
          slug: slug.trim() || name.toLowerCase().replace(/[^a-z0-9]+/g, "-"),
          description: description.trim() || undefined,
          code: code.trim(),
          input_spec_json: inputSpec,
          output_spec_json: outputSpec,
          version_notes: "Initial version",
        });
        toast({ description: "Script created" });
        onSelect("script", created.id);
      }
    } catch (error: any) {
      // Check for validation errors from backend (400 response)
      if (error?.validation_errors || error?.code) {
        const validationErrors = error.validation_errors || [];
        // Also parse errors from the code field if present (legacy format)
        if (error.code && Array.isArray(error.code)) {
          error.code.forEach((msg: string) => {
            const match = msg.match(/\[(\w+)\]\s*(.+?)(?:\s*\(line\s*(\d+)\))?$/);
            if (match) {
              validationErrors.push({
                type: match[1],
                message: match[2],
                line: match[3] ? parseInt(match[3]) : null,
              });
            }
          });
        }
        if (validationErrors.length > 0) {
          setValidationResult({
            valid: false,
            errors: validationErrors,
            warnings: [],
          });
          toast({ 
            variant: "destructive", 
            description: `Save failed: ${validationErrors.length} validation error(s)` 
          });
          return;
        }
      }
      // Other errors handled by mutation's onError
    }
  };

  const handleExecute = async () => {
    // Validate name and code
    if (!name?.trim()) {
      toast({ variant: "destructive", description: "Script name is required" });
      return;
    }
    if (!code?.trim()) {
      toast({ variant: "destructive", description: "Script code is required" });
      return;
    }

    // Check all required inputs have bindings
    const currentInputKeys = Object.keys(inputSpec);
    const missingInputs = currentInputKeys.filter(
      (key) => inputSpec[key]?.required && !inputBindings[key]
    );
    if (missingInputs.length > 0) {
      toast({
        variant: "destructive",
        description: `Missing required inputs: ${missingInputs.join(", ")}`,
      });
      return;
    }

    let scriptId = id;

    // Auto-save if new script
    if (!scriptId) {
      try {
        const created = await createMutation.mutateAsync({
          name: name.trim(),
          slug: slug.trim() || name.toLowerCase().replace(/[^a-z0-9]+/g, "-"),
          description: description.trim() || undefined,
          code: code.trim(),
          input_spec_json: inputSpec,
          output_spec_json: outputSpec,
          version_notes: "Initial version",
        });
        toast({ description: "Script saved" });
        scriptId = created.id;
        onSelect("script", created.id);
      } catch (err: any) {
        toast({ variant: "destructive", description: err?.message || "Failed to save script" });
        return;
      }
    }

    // Clear any previous polling
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }

    setExecutionResult({ status: "pending" });

    try {
      const result = await dataLabApi.executeScript(scriptId, {
        inputs: inputBindings,
        params: {},
      });
      
      const { task_id, run_id } = result;
      setExecutionResult({
        status: "running",
        task_id,
        run_id,
      });
      toast({ description: `Execution started (task: ${task_id?.slice(0, 8)}...)` });

      // Start polling for script status using task_id
      if (task_id) {
        pollingRef.current = setInterval(() => {
          pollScriptStatus(task_id);
        }, 2000); // Poll every 2 seconds
      }
    } catch (err: any) {
      setExecutionResult({
        status: "failed",
        error: err?.message || "Execution failed",
      });
      toast({ variant: "destructive", description: err?.message || "Execution failed" });
    }
  };

  const addInput = () => {
    const inputKey = `input${Object.keys(inputSpec).length + 1}`;
    setInputSpec((prev) => ({
      ...prev,
      [inputKey]: { name: inputKey, type: "dataframe", required: true },
    }));
  };

  const removeInput = (key: string) => {
    setInputSpec((prev) => {
      const newSpec = { ...prev };
      delete newSpec[key];
      return newSpec;
    });
    setInputBindings((prev) => {
      const newBindings = { ...prev };
      delete newBindings[key];
      return newBindings;
    });
  };

  const addOutput = () => {
    const outputKey = `output${Object.keys(outputSpec).length + 1}`;
    setOutputSpec((prev) => ({
      ...prev,
      [outputKey]: { name: outputKey, type: "dataframe" },
    }));
  };

  const removeOutput = (key: string) => {
    setOutputSpec((prev) => {
      const newSpec = { ...prev };
      delete newSpec[key];
      return newSpec;
    });
  };

  if (isLoading) {
    return (
      <div className="h-full flex items-center justify-center text-muted-foreground">
        <Loader2 className="h-5 w-5 animate-spin mr-2" />
        Loading...
      </div>
    );
  }

  const isSaving = createMutation.isPending || updateMutation.isPending;
  const resultsets = resultSets?.results || [];  // These are ResultSets, not Datasets
  const inputKeys = Object.keys(inputSpec);

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* Main content */}
      <div className="flex-1 overflow-hidden p-4">
        <div className="grid gap-4 lg:grid-cols-3 h-full">
          {/* Script details - 2 columns */}
          <Card className="lg:col-span-2 flex flex-col">
            <CardHeader className="pb-3 flex-row items-center justify-between space-y-0">
              <div>
                <CardTitle className="flex items-center gap-2">
                  {id ? "Edit Script" : "New Script"}
                  {script?.slug && (
                    <Badge variant="secondary" className="font-mono text-xs">
                      {script.slug}
                    </Badge>
                  )}
                </CardTitle>
                <CardDescription>
                  Python script for data transformation. Function must be named <code className="bg-muted px-1 rounded">main</code>.
                </CardDescription>
              </div>
              <Button size="sm" onClick={handleSave} disabled={isSaving}>
                {isSaving ? (
                  <Loader2 className="h-4 w-4 animate-spin mr-2" />
                ) : (
                  <Save className="h-4 w-4 mr-2" />
                )}
                {id ? "Save" : "Create"}
              </Button>
            </CardHeader>
            <CardContent className="space-y-4 flex-1 flex flex-col min-h-0">
              <div className="grid gap-3 sm:grid-cols-2">
                <div>
                  <Label htmlFor="name" className="text-xs">Name *</Label>
                  <Input
                    id="name"
                    value={name}
                    onChange={(e) => {
                      setName(e.target.value);
                      if (!slug && !id) {
                        setSlug(
                          e.target.value
                            .toLowerCase()
                            .replace(/[^a-z0-9]+/g, "-")
                            .replace(/^-|-$/g, "")
                        );
                      }
                    }}
                    placeholder="Calculate Revenue"
                    className="h-8"
                  />
                </div>
                <div>
                  <Label htmlFor="slug" className="text-xs">Slug</Label>
                  <Input
                    id="slug"
                    value={slug}
                    onChange={(e) => setSlug(e.target.value)}
                    placeholder="calculate-revenue"
                    className="h-8"
                  />
                </div>
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
                <div className="flex items-center justify-between mb-1">
                  <Label className="text-xs">Python Code *</Label>
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-6 text-xs"
                    onClick={handleValidate}
                    disabled={isValidating || !code?.trim()}
                  >
                    {isValidating ? (
                      <Loader2 className="h-3 w-3 animate-spin mr-1" />
                    ) : validationResult?.valid ? (
                      <Check className="h-3 w-3 mr-1 text-green-500" />
                    ) : validationResult && !validationResult.valid ? (
                      <ShieldAlert className="h-3 w-3 mr-1 text-red-500" />
                    ) : null}
                    Validate
                  </Button>
                </div>
                <div className="flex-1 border rounded-md overflow-hidden min-h-[300px]">
                  <Editor
                    height="100%"
                    language="python"
                    value={code}
                    onChange={(value) => {
                      setCode(value || "");
                      // Clear validation when code changes
                      if (validationResult) setValidationResult(null);
                    }}
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
                
                {/* Validation Results */}
                {validationResult && (
                  <div className={`mt-2 p-2 rounded-md text-xs ${
                    validationResult.valid 
                      ? "bg-green-500/10 text-green-700 dark:text-green-400"
                      : "bg-red-500/10 text-red-700 dark:text-red-400"
                  }`}>
                    {validationResult.valid ? (
                      <div className="flex items-center gap-2">
                        <CheckCircle className="h-3.5 w-3.5" />
                        <span>Script is valid</span>
                      </div>
                    ) : (
                      <div className="space-y-2">
                        <div className="flex items-center gap-2 font-medium">
                          <ShieldAlert className="h-3.5 w-3.5" />
                          <span>{validationResult.errors.length} validation error(s)</span>
                        </div>
                        <div className="space-y-1">
                          {validationResult.errors.map((err, i) => (
                            <div key={i} className="flex items-start gap-2 pl-5">
                              <Badge variant="destructive" className="text-[10px] px-1 py-0 shrink-0">
                                {err.type}
                              </Badge>
                              <span>
                                {err.message}
                                {err.line && <span className="opacity-75"> (line {err.line})</span>}
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                    {validationResult.warnings && validationResult.warnings.length > 0 && (
                      <div className="mt-2 pt-2 border-t border-yellow-500/30">
                        <div className="flex items-center gap-2 text-yellow-600 dark:text-yellow-400">
                          <AlertTriangle className="h-3.5 w-3.5" />
                          <span className="font-medium">{validationResult.warnings.length} warning(s)</span>
                        </div>
                        <div className="space-y-1 mt-1">
                          {validationResult.warnings.map((warn, i) => (
                            <div key={i} className="flex items-start gap-2 pl-5 text-yellow-600 dark:text-yellow-400">
                              <Badge variant="outline" className="text-[10px] px-1 py-0 shrink-0 border-yellow-500">
                                {warn.type}
                              </Badge>
                              <span>
                                {warn.message}
                                {warn.line && <span className="opacity-75"> (line {warn.line})</span>}
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </CardContent>
          </Card>

          {/* Right column */}
          <div className="space-y-4 overflow-auto">
            {/* Inputs */}
            <Card>
              <CardHeader className="pb-2 pt-3 px-3">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-sm">Inputs</CardTitle>
                  <Button variant="outline" size="sm" className="h-6 text-xs" onClick={addInput}>
                    <Plus className="h-3 w-3 mr-1" />
                    Add
                  </Button>
                </div>
              </CardHeader>
              <CardContent className="px-3 pb-3">
                {inputKeys.length === 0 ? (
                  <p className="text-xs text-muted-foreground">
                    No inputs defined.
                  </p>
                ) : (
                  <div className="space-y-1.5">
                    {inputKeys.map((key) => {
                      const spec = inputSpec[key];
                      return (
                        <div
                          key={key}
                          className="flex items-center justify-between p-2 border rounded text-xs"
                        >
                          <div>
                            <div className="font-medium">{spec.name || key}</div>
                            <div className="text-muted-foreground">
                              {spec.type} {spec.required && "(required)"}
                            </div>
                          </div>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-6 w-6 p-0"
                            onClick={() => removeInput(key)}
                          >
                            <Trash2 className="h-3 w-3" />
                          </Button>
                        </div>
                      );
                    })}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Outputs */}
            <Card>
              <CardHeader className="pb-2 pt-3 px-3">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-sm">Outputs</CardTitle>
                  <Button variant="outline" size="sm" className="h-6 text-xs" onClick={addOutput}>
                    <Plus className="h-3 w-3 mr-1" />
                    Add
                  </Button>
                </div>
              </CardHeader>
              <CardContent className="px-3 pb-3">
                {Object.keys(outputSpec).length === 0 ? (
                  <p className="text-xs text-muted-foreground">
                    No outputs defined.
                  </p>
                ) : (
                  <div className="space-y-1.5">
                    {Object.entries(outputSpec).map(([key, spec]: [string, any]) => (
                      <div
                        key={key}
                        className="flex items-center justify-between p-2 border rounded text-xs"
                      >
                        <div>
                          <div className="font-medium">{spec.name || key}</div>
                          <div className="text-muted-foreground">{spec.type}</div>
                        </div>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-6 w-6 p-0"
                          onClick={() => removeOutput(key)}
                        >
                          <Trash2 className="h-3 w-3" />
                        </Button>
                      </div>
                    ))}
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
                {inputKeys.length > 0 ? (
                  <div className="space-y-2">
                    <p className="text-xs text-muted-foreground">
                      Select result sets for inputs:
                    </p>
                    {inputKeys.map((key) => (
                      <div key={key}>
                        <Label className="text-xs">{inputSpec[key]?.name || key}</Label>
                        <Select
                          value={inputBindings[key] || ""}
                          onValueChange={(value) =>
                            setInputBindings((prev) => ({ ...prev, [key]: value }))
                          }
                        >
                          <SelectTrigger className="mt-1 h-7 text-xs">
                            <SelectValue placeholder="Select result set..." />
                          </SelectTrigger>
                          <SelectContent>
                            {resultsets.length === 0 ? (
                              <div className="p-2 text-xs text-muted-foreground text-center">
                                No result sets available
                              </div>
                            ) : (
                              resultsets.map((rs) => (
                                <SelectItem key={rs.id} value={rs.id}>
                                  <span>{rs.name || "Untitled"}</span>
                                  <span className="text-muted-foreground ml-1">
                                    ({rs.row_count?.toLocaleString() || 0} rows • {rs.origin})
                                  </span>
                                </SelectItem>
                              ))
                            )}
                          </SelectContent>
                        </Select>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-muted-foreground">
                    Add inputs to test with result sets.
                  </p>
                )}

                <Button
                  size="sm"
                  className="w-full h-8"
                  onClick={handleExecute}
                  disabled={executeMutation.isPending || createMutation.isPending || inputKeys.length === 0}
                >
                  {(executeMutation.isPending || createMutation.isPending) ? (
                    <Loader2 className="h-4 w-4 animate-spin mr-2" />
                  ) : (
                    <Play className="h-4 w-4 mr-2" />
                  )}
                  {!id ? "Save & Run" : "Run Script"}
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
                    {executionResult.run_id && (
                      <p className="text-xs mt-1 opacity-75">
                        Run: {executionResult.run_id.slice(0, 8)}...
                      </p>
                    )}
                    
                    {/* Error display with traceback */}
                    {executionResult.status === "failed" && (
                      <div className="mt-2 space-y-2">
                        {executionResult.error && (
                          <p className="font-medium text-red-600 dark:text-red-400">
                            {executionResult.error}
                          </p>
                        )}
                        {executionResult.traceback && (
                          <details className="text-xs">
                            <summary className="cursor-pointer opacity-75 hover:opacity-100">
                              Show traceback
                            </summary>
                            <pre className="mt-1 p-2 bg-red-950/20 rounded overflow-auto max-h-32 text-[10px] whitespace-pre-wrap">
                              {executionResult.traceback}
                            </pre>
                          </details>
                        )}
                        {executionResult.logs && executionResult.logs.length > 0 && (
                          <details className="text-xs">
                            <summary className="cursor-pointer opacity-75 hover:opacity-100">
                              Show logs ({executionResult.logs.length})
                            </summary>
                            <pre className="mt-1 p-2 bg-red-950/20 rounded overflow-auto max-h-24 text-[10px]">
                              {executionResult.logs.join("\n")}
                            </pre>
                          </details>
                        )}
                      </div>
                    )}
                    
                    {/* Success display */}
                    {executionResult.status === "success" && (
                      <div className="mt-2 space-y-2">
                        {/* DataFrame info */}
                        {executionResult.result?.shape && (
                          <div className="text-xs opacity-90">
                            <span className="font-medium">Output:</span>{" "}
                            {executionResult.result.return_type || "DataFrame"}{" "}
                            ({executionResult.result.shape[0].toLocaleString()} rows × {executionResult.result.shape[1]} cols)
                          </div>
                        )}
                        
                        {/* Columns */}
                        {executionResult.result?.columns && executionResult.result.columns.length > 0 && (
                          <details className="text-xs">
                            <summary className="cursor-pointer opacity-75 hover:opacity-100">
                              Columns ({executionResult.result.columns.length})
                            </summary>
                            <div className="mt-1 p-2 bg-green-950/20 rounded text-[10px] flex flex-wrap gap-1">
                              {executionResult.result.columns.map((col: string) => (
                                <Badge key={col} variant="secondary" className="text-[10px] px-1">
                                  {col}
                                </Badge>
                              ))}
                            </div>
                          </details>
                        )}
                        
                        {/* Logs */}
                        {executionResult.logs && executionResult.logs.length > 0 && (
                          <details className="text-xs">
                            <summary className="cursor-pointer opacity-75 hover:opacity-100">
                              Logs ({executionResult.logs.length})
                            </summary>
                            <pre className="mt-1 p-2 bg-green-950/20 rounded overflow-auto max-h-24 text-[10px]">
                              {executionResult.logs.join("\n")}
                            </pre>
                          </details>
                        )}
                        
                        {/* ResultSets - intermediate outputs from scripts */}
                        {executionResult.resultsets && executionResult.resultsets.length > 0 && (
                          <div className="pt-2 border-t border-green-500/20">
                            <p className="font-medium mb-1">Produced Result Sets:</p>
                            <div className="space-y-1">
                              {executionResult.resultsets.map((rs) => (
                                <div key={rs.id} className="flex items-center gap-2">
                                  <Badge variant="outline" className="text-[10px]">{rs.name}</Badge>
                                  <span className="text-[10px] opacity-75 truncate">{rs.id.slice(0, 8)}...</span>
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    className="h-5 w-5 p-0"
                                    onClick={() => {
                                      // Copy ResultSet ID to clipboard for now
                                      navigator.clipboard.writeText(rs.id);
                                      toast({ description: `ResultSet ID copied: ${rs.id.slice(0, 8)}...` });
                                    }}
                                    title="Copy ResultSet ID"
                                  >
                                    <ExternalLink className="h-3 w-3" />
                                  </Button>
                                </div>
                              ))}
                            </div>
                            <p className="text-[10px] opacity-60 mt-1">
                              Use a Pipeline to promote to a durable Dataset
                            </p>
                          </div>
                        )}
                        
                        {(!executionResult.resultsets || executionResult.resultsets.length === 0) && !executionResult.result?.shape && (
                          <p className="opacity-75">
                            Execution completed (no output datasets)
                          </p>
                        )}
                      </div>
                    )}
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
