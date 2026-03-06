import { useState, useEffect } from "react";
import { useParams, Link, useLocation } from "wouter";
import { PageLayout } from "@/components/layout/page-layout";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  useDataLabPipelines,
  useDataLabPipelineCreate,
  useDataLabCRMViews,
  useDataLabScripts,
} from "@/hooks/use-datalab";
import { ArrowLeft, Loader2, Save, Plus, Trash2 } from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { PipelineStep } from "@/lib/moio-types";

export default function PipelineBuilder() {
  const { id } = useParams<{ id?: string }>();
  const [, setLocation] = useLocation();
  const isEditing = !!id;
  const { data: pipelines } = useDataLabPipelines();
  const { data: crmViews } = useDataLabCRMViews();
  const { data: scripts } = useDataLabScripts();
  const createMutation = useDataLabPipelineCreate();
  const { toast } = useToast();

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [steps, setSteps] = useState<PipelineStep[]>([]);
  type PipelineParamForm = { name: string; type: string; default?: string };
  const [params, setParams] = useState<PipelineParamForm[]>([]);

  // Load existing pipeline if editing
  useEffect(() => {
    if (isEditing && pipelines) {
      const pipeline = pipelines.find((p) => p.id === id);
      if (pipeline) {
        setName(pipeline.name);
        setDescription(pipeline.description || "");
        setSteps(pipeline.steps_json || []);
        setParams(pipeline.params_json || []);
      }
    }
  }, [id, isEditing, pipelines]);

  const handleSave = async () => {
    if (!name.trim()) {
      toast({
        title: "Validation error",
        description: "Pipeline name is required",
        variant: "destructive",
      });
      return;
    }

    if (steps.length === 0) {
      toast({
        title: "Validation error",
        description: "At least one step is required",
        variant: "destructive",
      });
      return;
    }

    try {
      await createMutation.mutateAsync({
        name: name.trim(),
        description: description.trim() || undefined,
        steps_json: steps,
        params_json: params,
      });

      toast({
        title: isEditing ? "Pipeline updated" : "Pipeline created",
        description: `Pipeline "${name}" has been ${isEditing ? "updated" : "created"} successfully.`,
      });

      setLocation("/datalab/pipelines");
    } catch (error) {
      toast({
        title: "Save failed",
        description: error instanceof Error ? error.message : "Failed to save pipeline",
        variant: "destructive",
      });
    }
  };

  const addStep = () => {
    const newStep: PipelineStep = {
      id: `step${steps.length + 1}`,
      type: "crm_query",
      config: {},
    };
    setSteps([...steps, newStep]);
  };

  const removeStep = (index: number) => {
    setSteps(steps.filter((_, i) => i !== index));
  };

  const updateStep = (index: number, updates: Partial<PipelineStep>) => {
    const newSteps = [...steps];
    newSteps[index] = { ...newSteps[index], ...updates };
    setSteps(newSteps);
  };

  const addParam = () => {
    setParams([...params, { name: "", type: "string" }]);
  };

  const removeParam = (index: number) => {
    setParams(params.filter((_, i) => i !== index));
  };

  const updateParam = (index: number, updates: Partial<typeof params[0]>) => {
    const newParams = [...params];
    newParams[index] = { ...newParams[index], ...updates };
    setParams(newParams);
  };

  return (
    <PageLayout>
      <div className="space-y-6 max-w-6xl mx-auto">
        <div>
          <Link href="/datalab/pipelines">
            <Button variant="ghost" size="sm" className="mb-2">
              <ArrowLeft className="mr-2 h-4 w-4" />
              Back
            </Button>
          </Link>
          <h1 className="text-3xl font-bold">
            {isEditing ? "Edit Pipeline" : "New Pipeline"}
          </h1>
          <p className="text-muted-foreground mt-2">
            Build a data processing pipeline with multiple steps
          </p>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Pipeline Details</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <Label htmlFor="name">Name *</Label>
              <Input
                id="name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Monthly Sales Report"
              />
            </div>

            <div>
              <Label htmlFor="description">Description</Label>
              <Textarea
                id="description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Describe what this pipeline does..."
                rows={3}
              />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle>Steps</CardTitle>
                <CardDescription>Configure pipeline execution steps</CardDescription>
              </div>
              <Button variant="outline" size="sm" onClick={addStep}>
                <Plus className="mr-2 h-4 w-4" />
                Add Step
              </Button>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            {steps.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-8">
                No steps defined. Click "Add Step" to get started.
              </p>
            ) : (
              steps.map((step, index) => (
                <Card key={index} className="border-2">
                  <CardHeader>
                    <div className="flex items-center justify-between">
                      <CardTitle className="text-lg">Step {index + 1}</CardTitle>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => removeStep(index)}
                      >
                        <Trash2 className="h-4 w-4 text-destructive" />
                      </Button>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div>
                      <Label>Step Type</Label>
                      <Select
                        value={step.type}
                        onValueChange={(value: "crm_query" | "script") =>
                          updateStep(index, {
                            type: value,
                            config: {},
                          })
                        }
                      >
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="crm_query">CRM Query</SelectItem>
                          <SelectItem value="script">Script</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>

                    {step.type === "crm_query" && (
                      <div>
                        <Label>CRM View</Label>
                        <Select
                          value={step.config.view_key || ""}
                          onValueChange={(value) =>
                            updateStep(index, {
                              config: { ...step.config, view_key: value },
                            })
                          }
                        >
                          <SelectTrigger>
                            <SelectValue placeholder="Select a CRM view" />
                          </SelectTrigger>
                          <SelectContent>
                            {crmViews?.map((view) => (
                              <SelectItem key={view.id} value={view.key}>
                                {view.label}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                    )}

                    {step.type === "script" && (
                      <div>
                        <Label>Script</Label>
                        <Select
                          value={step.config.script_id || ""}
                          onValueChange={(value) =>
                            updateStep(index, {
                              config: { ...step.config, script_id: value },
                            })
                          }
                        >
                          <SelectTrigger>
                            <SelectValue placeholder="Select a script" />
                          </SelectTrigger>
                          <SelectContent>
                            {scripts?.map((script) => (
                              <SelectItem key={script.id} value={script.id}>
                                {script.name}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                    )}

                    <div>
                      <Label>Output Name (Optional)</Label>
                      <Input
                        value={step.output || ""}
                        onChange={(e) =>
                          updateStep(index, { output: e.target.value })
                        }
                        placeholder="output_name"
                      />
                    </div>
                  </CardContent>
                </Card>
              ))
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle>Parameters</CardTitle>
                <CardDescription>Pipeline input parameters</CardDescription>
              </div>
              <Button variant="outline" size="sm" onClick={addParam}>
                <Plus className="mr-2 h-4 w-4" />
                Add Parameter
              </Button>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            {params.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-4">
                No parameters defined. Click "Add Parameter" to add one.
              </p>
            ) : (
              params.map((param, index) => (
                <div key={index} className="flex gap-2 items-end">
                  <div className="flex-1">
                    <Label>Name</Label>
                    <Input
                      value={param.name}
                      onChange={(e) =>
                        updateParam(index, { name: e.target.value })
                      }
                      placeholder="date_from"
                    />
                  </div>
                  <div className="flex-1">
                    <Label>Type</Label>
                    <Select
                      value={param.type}
                      onValueChange={(value) =>
                        updateParam(index, { type: value })
                      }
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="string">String</SelectItem>
                        <SelectItem value="number">Number</SelectItem>
                        <SelectItem value="date">Date</SelectItem>
                        <SelectItem value="boolean">Boolean</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="flex-1">
                    <Label>Default (Optional)</Label>
                    <Input
                      value={param.default || ""}
                      onChange={(e) =>
                        updateParam(index, { default: e.target.value })
                      }
                      placeholder="today-30d"
                    />
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => removeParam(index)}
                  >
                    <Trash2 className="h-4 w-4 text-destructive" />
                  </Button>
                </div>
              ))
            )}
          </CardContent>
        </Card>

        <div className="flex gap-2">
          <Link href="/datalab/pipelines">
            <Button variant="outline">Cancel</Button>
          </Link>
          <Button onClick={handleSave} disabled={createMutation.isPending} className="ml-auto">
            {createMutation.isPending ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Saving...
              </>
            ) : (
              <>
                <Save className="mr-2 h-4 w-4" />
                Save Pipeline
              </>
            )}
          </Button>
        </div>
      </div>
    </PageLayout>
  );
}
