import { useState } from "react";
import { useParams, Link, useLocation } from "wouter";
import { PageLayout } from "@/components/layout/page-layout";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  useDataLabScripts,
  useDataLabScriptExecute,
  useDataLabResultSets,
} from "@/hooks/use-datalab";
import { ArrowLeft, Loader2, Play, Database } from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";

export default function ScriptExecutor() {
  const { id } = useParams<{ id: string }>();
  const [, setLocation] = useLocation();
  const { data: scripts } = useDataLabScripts();
  const { data: resultsets } = useDataLabResultSets();
  const executeMutation = useDataLabScriptExecute(id);
  const { toast } = useToast();

  const script = scripts?.find((s) => s.id === id);
  const [inputs, setInputs] = useState<Record<string, string>>({});
  const [params, setParams] = useState<Record<string, any>>({});

  if (!script) {
    return (
      <PageLayout>
        <div className="text-center py-12">
          <Database className="h-12 w-12 mx-auto mb-4 opacity-50 text-muted-foreground" />
          <h2 className="text-2xl font-bold mb-2">Script Not Found</h2>
          <Link href="/datalab/scripts">
            <Button>
              <ArrowLeft className="mr-2 h-4 w-4" />
              Back to Scripts
            </Button>
          </Link>
        </div>
      </PageLayout>
    );
  }

  const handleInputChange = (key: string, value: string) => {
    setInputs((prev) => ({
      ...prev,
      [key]: value,
    }));
  };

  const handleExecute = async () => {
    // Validate inputs
    const inputSpec = script.input_spec_json || {};
    const requiredInputs = Object.entries(inputSpec)
      .filter(([_, spec]: [string, any]) => spec.required)
      .map(([key]) => key);

    const missingInputs = requiredInputs.filter((key) => !inputs[key]);
    if (missingInputs.length > 0) {
      toast({
        title: "Validation error",
        description: `Missing required inputs: ${missingInputs.join(", ")}`,
        variant: "destructive",
      });
      return;
    }

    try {
      const result = await executeMutation.mutateAsync({
        inputs,
        params: Object.keys(params).length > 0 ? params : undefined,
      });

      toast({
        title: "Script execution started",
        description: `Task ID: ${result.task_id}. Status: ${result.status}`,
      });

      // Note: In a real implementation, you'd poll for task status
      // For now, we'll just show a message
      setTimeout(() => {
        toast({
          title: "Note",
          description: "Script execution is asynchronous. Check ResultSets for results.",
        });
      }, 2000);
    } catch (error) {
      toast({
        title: "Execution failed",
        description: error instanceof Error ? error.message : "Failed to execute script",
        variant: "destructive",
      });
    }
  };

  const inputSpec = script.input_spec_json || {};
  const availableResultSets = resultsets?.results || [];

  return (
    <PageLayout>
      <div className="space-y-6 max-w-4xl mx-auto">
        <div>
          <Link href="/datalab/scripts">
            <Button variant="ghost" size="sm" className="mb-2">
              <ArrowLeft className="mr-2 h-4 w-4" />
              Back
            </Button>
          </Link>
          <h1 className="text-3xl font-bold">Execute Script</h1>
          <p className="text-muted-foreground mt-2">{script.name}</p>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Script Information</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              <div>
                <span className="text-sm font-medium">Name:</span> {script.name}
              </div>
              {script.description && (
                <div>
                  <span className="text-sm font-medium">Description:</span> {script.description}
                </div>
              )}
              <div>
                <span className="text-sm font-medium">Slug:</span>{" "}
                <code className="text-xs bg-muted px-2 py-1 rounded">{script.slug}</code>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Input Configuration</CardTitle>
            <CardDescription>
              Select data sources for each required input
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {Object.keys(inputSpec).length === 0 ? (
              <p className="text-sm text-muted-foreground">
                This script has no inputs defined.
              </p>
            ) : (
              Object.entries(inputSpec).map(([key, spec]: [string, any]) => (
                <div key={key}>
                  <Label htmlFor={key}>
                    {spec.name || key}
                    {spec.required && <span className="text-destructive ml-1">*</span>}
                  </Label>
                  <Select
                    value={inputs[key] || ""}
                    onValueChange={(value) => handleInputChange(key, value)}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Select a ResultSet" />
                    </SelectTrigger>
                    <SelectContent>
                      {availableResultSets.length === 0 ? (
                        <SelectItem value="" disabled>
                          No ResultSets available
                        </SelectItem>
                      ) : (
                        availableResultSets.map((rs) => (
                          <SelectItem key={rs.id} value={rs.id}>
                            {rs.name || "Unnamed ResultSet"} ({rs.row_count.toLocaleString()} rows)
                          </SelectItem>
                        ))
                      )}
                    </SelectContent>
                  </Select>
                  <p className="text-xs text-muted-foreground mt-1">
                    Type: {spec.type} {spec.required && "(required)"}
                  </p>
                </div>
              ))
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Parameters (Optional)</CardTitle>
            <CardDescription>
              Additional parameters for script execution
            </CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              Parameter configuration coming soon. For now, scripts will run with default parameters.
            </p>
          </CardContent>
        </Card>

        <div className="flex gap-2">
          <Link href="/datalab/scripts">
            <Button variant="outline">Cancel</Button>
          </Link>
          <Button
            onClick={handleExecute}
            disabled={executeMutation.isPending || Object.keys(inputSpec).length === 0}
            className="ml-auto"
          >
            {executeMutation.isPending ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Executing...
              </>
            ) : (
              <>
                <Play className="mr-2 h-4 w-4" />
                Execute Script
              </>
            )}
          </Button>
        </div>
      </div>
    </PageLayout>
  );
}
