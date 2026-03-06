import { useState, useEffect } from "react";
import { useParams, Link, useLocation } from "wouter";
import { PageLayout } from "@/components/layout/page-layout";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  useDataLabScripts,
  useDataLabScriptCreate,
  useDataLabScriptSpec,
} from "@/hooks/use-datalab";
import { ArrowLeft, Loader2, Save, Code } from "lucide-react";
import { useToast } from "@/hooks/use-toast";

const DEFAULT_SCRIPT_CODE = `import pandas as pd

def main(params):
    """
    Main function to process data.
    
    Args:
        params: Dictionary containing input data sources
        
    Returns:
        Dictionary with output results
    """
    # Access input DataSource as DataFrame
    # Example: df = params['input1']
    
    # Process data here
    # Example: result = df.groupby('column').sum()
    
    # Return outputs
    return {
        # 'output1': result
    }
`;

export default function ScriptEditor() {
  const { id } = useParams<{ id?: string }>();
  const [, setLocation] = useLocation();
  const isEditing = !!id;
  const { data: scripts } = useDataLabScripts();
  const createMutation = useDataLabScriptCreate();
  const { toast } = useToast();

  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [description, setDescription] = useState("");
  const [code, setCode] = useState(DEFAULT_SCRIPT_CODE);
  const [inputSpec, setInputSpec] = useState<Record<string, any>>({});
  const [outputSpec, setOutputSpec] = useState<Record<string, any>>({});

  // Load existing script if editing
  useEffect(() => {
    if (isEditing && scripts) {
      const script = scripts.find((s) => s.id === id);
      if (script) {
        setName(script.name);
        setSlug(script.slug);
        setDescription(script.description || "");
        setCode(script.code);
        setInputSpec(script.input_spec_json || {});
        setOutputSpec(script.output_spec_json || {});
      }
    }
  }, [id, isEditing, scripts]);

  const handleSave = async () => {
    if (!name.trim()) {
      toast({
        title: "Validation error",
        description: "Script name is required",
        variant: "destructive",
      });
      return;
    }

    if (!code.trim()) {
      toast({
        title: "Validation error",
        description: "Script code is required",
        variant: "destructive",
      });
      return;
    }

    try {
      await createMutation.mutateAsync({
        name: name.trim(),
        slug: slug.trim() || undefined,
        description: description.trim() || undefined,
        code: code.trim(),
        input_spec_json: inputSpec,
        output_spec_json: outputSpec,
        version_notes: isEditing ? "Updated script" : "Initial version",
      });

      toast({
        title: isEditing ? "Script updated" : "Script created",
        description: `Script "${name}" has been ${isEditing ? "updated" : "created"} successfully.`,
      });

      setLocation("/datalab/scripts");
    } catch (error) {
      toast({
        title: "Save failed",
        description: error instanceof Error ? error.message : "Failed to save script",
        variant: "destructive",
      });
    }
  };

  const addInput = () => {
    const inputKey = `input${Object.keys(inputSpec).length + 1}`;
    setInputSpec((prev) => ({
      ...prev,
      [inputKey]: {
        name: inputKey,
        type: "dataframe",
        required: true,
      },
    }));
  };

  const removeInput = (key: string) => {
    setInputSpec((prev) => {
      const newSpec = { ...prev };
      delete newSpec[key];
      return newSpec;
    });
  };

  const addOutput = () => {
    const outputKey = `output${Object.keys(outputSpec).length + 1}`;
    setOutputSpec((prev) => ({
      ...prev,
      [outputKey]: {
        name: outputKey,
        type: "dataframe",
      },
    }));
  };

  const removeOutput = (key: string) => {
    setOutputSpec((prev) => {
      const newSpec = { ...prev };
      delete newSpec[key];
      return newSpec;
    });
  };

  return (
    <PageLayout>
      <div className="space-y-6 max-w-6xl mx-auto">
        <div>
          <Link href="/datalab/scripts">
            <Button variant="ghost" size="sm" className="mb-2">
              <ArrowLeft className="mr-2 h-4 w-4" />
              Back
            </Button>
          </Link>
          <h1 className="text-3xl font-bold">
            {isEditing ? "Edit Script" : "New Script"}
          </h1>
          <p className="text-muted-foreground mt-2">
            Create a Python script for data transformation
          </p>
        </div>

        <div className="grid gap-6 md:grid-cols-3">
          <Card className="md:col-span-2">
            <CardHeader>
              <CardTitle>Script Details</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <Label htmlFor="name">Name *</Label>
                <Input
                  id="name"
                  value={name}
                  onChange={(e) => {
                    setName(e.target.value);
                    if (!slug && !isEditing) {
                      setSlug(
                        e.target.value
                          .toLowerCase()
                          .replace(/[^a-z0-9]+/g, "-")
                          .replace(/^-|-$/g, "")
                      );
                    }
                  }}
                  placeholder="Calculate Revenue"
                />
              </div>

              <div>
                <Label htmlFor="slug">Slug</Label>
                <Input
                  id="slug"
                  value={slug}
                  onChange={(e) => setSlug(e.target.value)}
                  placeholder="calculate-revenue"
                />
                <p className="text-xs text-muted-foreground mt-1">
                  Auto-generated from name if not provided
                </p>
              </div>

              <div>
                <Label htmlFor="description">Description</Label>
                <Textarea
                  id="description"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Describe what this script does..."
                  rows={3}
                />
              </div>

              <div>
                <Label htmlFor="code">Python Code *</Label>
                <Textarea
                  id="code"
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  placeholder={DEFAULT_SCRIPT_CODE}
                  rows={20}
                  className="font-mono text-sm"
                />
                <p className="text-xs text-muted-foreground mt-1">
                  Define a main(params) function that returns a dictionary of outputs
                </p>
              </div>
            </CardContent>
          </Card>

          <div className="space-y-6">
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle>Inputs</CardTitle>
                  <Button variant="outline" size="sm" onClick={addInput}>
                    Add
                  </Button>
                </div>
              </CardHeader>
              <CardContent>
                {Object.keys(inputSpec).length === 0 ? (
                  <p className="text-sm text-muted-foreground">
                    No inputs defined. Click "Add" to add an input.
                  </p>
                ) : (
                  <div className="space-y-2">
                    {Object.entries(inputSpec).map(([key, spec]: [string, any]) => (
                      <div key={key} className="p-2 border rounded text-sm">
                        <div className="font-medium">{spec.name || key}</div>
                        <div className="text-xs text-muted-foreground">{spec.type}</div>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="mt-1 h-6 text-xs"
                          onClick={() => removeInput(key)}
                        >
                          Remove
                        </Button>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle>Outputs</CardTitle>
                  <Button variant="outline" size="sm" onClick={addOutput}>
                    Add
                  </Button>
                </div>
              </CardHeader>
              <CardContent>
                {Object.keys(outputSpec).length === 0 ? (
                  <p className="text-sm text-muted-foreground">
                    No outputs defined. Click "Add" to add an output.
                  </p>
                ) : (
                  <div className="space-y-2">
                    {Object.entries(outputSpec).map(([key, spec]: [string, any]) => (
                      <div key={key} className="p-2 border rounded text-sm">
                        <div className="font-medium">{spec.name || key}</div>
                        <div className="text-xs text-muted-foreground">{spec.type}</div>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="mt-1 h-6 text-xs"
                          onClick={() => removeOutput(key)}
                        >
                          Remove
                        </Button>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </div>

        <div className="flex gap-2">
          <Link href="/datalab/scripts">
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
                Save Script
              </>
            )}
          </Button>
        </div>
      </div>
    </PageLayout>
  );
}
