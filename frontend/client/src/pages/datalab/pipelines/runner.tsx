import { useState } from "react";
import { useParams, Link, useLocation } from "wouter";
import { PageLayout } from "@/components/layout/page-layout";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  useDataLabPipelines,
  useDataLabPipelineExecute,
} from "@/hooks/use-datalab";
import { ArrowLeft, Loader2, Play, Workflow } from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

export default function PipelineRunner() {
  const { id } = useParams<{ id: string }>();
  const [, setLocation] = useLocation();
  const { data: pipelines } = useDataLabPipelines();
  const executeMutation = useDataLabPipelineExecute(id);
  const { toast } = useToast();

  const pipeline = pipelines?.find((p) => p.id === id);
  const [params, setParams] = useState<Record<string, any>>({});

  if (!pipeline) {
    return (
      <PageLayout>
        <div className="text-center py-12">
          <Workflow className="h-12 w-12 mx-auto mb-4 opacity-50 text-muted-foreground" />
          <h2 className="text-2xl font-bold mb-2">Pipeline Not Found</h2>
          <Link href="/datalab/pipelines">
            <Button>
              <ArrowLeft className="mr-2 h-4 w-4" />
              Back to Pipelines
            </Button>
          </Link>
        </div>
      </PageLayout>
    );
  }

  const handleParamChange = (paramName: string, value: any) => {
    setParams((prev) => ({
      ...prev,
      [paramName]: value,
    }));
  };

  const handleExecute = async () => {
    try {
      const result = await executeMutation.mutateAsync(params);

      toast({
        title: "Pipeline executed",
        description: `Pipeline "${pipeline.name}" completed successfully.`,
      });

      // Navigate to run history or results
      setLocation(`/datalab/pipelines/${pipeline.id}/runs`);
    } catch (error) {
      toast({
        title: "Execution failed",
        description: error instanceof Error ? error.message : "Failed to execute pipeline",
        variant: "destructive",
      });
    }
  };

  const pipelineParams = pipeline.params_json || [];

  return (
    <PageLayout>
      <div className="space-y-6 max-w-4xl mx-auto">
        <div>
          <Link href="/datalab/pipelines">
            <Button variant="ghost" size="sm" className="mb-2">
              <ArrowLeft className="mr-2 h-4 w-4" />
              Back
            </Button>
          </Link>
          <h1 className="text-3xl font-bold">Run Pipeline</h1>
          <p className="text-muted-foreground mt-2">{pipeline.name}</p>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Pipeline Information</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              <div>
                <span className="text-sm font-medium">Name:</span> {pipeline.name}
              </div>
              {pipeline.description && (
                <div>
                  <span className="text-sm font-medium">Description:</span> {pipeline.description}
                </div>
              )}
              <div>
                <span className="text-sm font-medium">Steps:</span> {pipeline.steps_json?.length || 0}
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Parameters</CardTitle>
            <CardDescription>
              Configure pipeline parameters for this run
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {pipelineParams.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                This pipeline has no parameters. Click "Execute" to run it.
              </p>
            ) : (
              pipelineParams.map((param) => (
                <div key={param.name}>
                  <Label htmlFor={param.name}>
                    {param.name}
                    {param.type && (
                      <span className="text-xs text-muted-foreground ml-2">({param.type})</span>
                    )}
                  </Label>
                  {param.type === "boolean" ? (
                    <Select
                      value={params[param.name]?.toString() || ""}
                      onValueChange={(value) =>
                        handleParamChange(param.name, value === "true")
                      }
                    >
                      <SelectTrigger>
                        <SelectValue placeholder={`Select ${param.name}`} />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="true">True</SelectItem>
                        <SelectItem value="false">False</SelectItem>
                      </SelectContent>
                    </Select>
                  ) : param.type === "date" ? (
                    <Input
                      id={param.name}
                      type="date"
                      value={params[param.name] || param.default || ""}
                      onChange={(e) => handleParamChange(param.name, e.target.value)}
                      placeholder={param.default || `Enter ${param.name}`}
                    />
                  ) : param.type === "number" ? (
                    <Input
                      id={param.name}
                      type="number"
                      value={params[param.name] || param.default || ""}
                      onChange={(e) =>
                        handleParamChange(
                          param.name,
                          e.target.value ? parseFloat(e.target.value) : undefined
                        )
                      }
                      placeholder={param.default || `Enter ${param.name}`}
                    />
                  ) : (
                    <Input
                      id={param.name}
                      value={params[param.name] || param.default || ""}
                      onChange={(e) => handleParamChange(param.name, e.target.value)}
                      placeholder={param.default || `Enter ${param.name}`}
                    />
                  )}
                  {param.default && (
                    <p className="text-xs text-muted-foreground mt-1">
                      Default: {param.default}
                    </p>
                  )}
                </div>
              ))
            )}
          </CardContent>
        </Card>

        <div className="flex gap-2">
          <Link href="/datalab/pipelines">
            <Button variant="outline">Cancel</Button>
          </Link>
          <Button
            onClick={handleExecute}
            disabled={executeMutation.isPending}
            className="ml-auto"
            size="lg"
          >
            {executeMutation.isPending ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Executing...
              </>
            ) : (
              <>
                <Play className="mr-2 h-4 w-4" />
                Execute Pipeline
              </>
            )}
          </Button>
        </div>
      </div>
    </PageLayout>
  );
}
