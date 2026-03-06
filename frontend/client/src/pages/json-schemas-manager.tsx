import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { ArrowLeft, Search, Braces, Plus, Trash2, Edit2, Copy, Check } from "lucide-react";
import { Link } from "wouter";
import { fetchJson, apiRequest, queryClient } from "@/lib/queryClient";
import { useToast } from "@/hooks/use-toast";
import { apiV1 } from "@/lib/api";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";

interface JsonSchema {
  id: string;
  name: string;
  description?: string;
  schema: Record<string, any>;
  version: string;
  is_active: boolean;
  usage_count?: number;
  created_at?: string;
  updated_at?: string;
}

interface JsonSchemaFormData {
  name: string;
  description: string;
  schema_text: string;
  version: string;
  is_active: boolean;
}

interface SchemaField {
  name: string;
  type: "string" | "number" | "boolean" | "array" | "object";
  description: string;
  required: boolean;
}

const JSON_SCHEMAS_PATH = apiV1("/settings/json_schemas/");

const EXAMPLE_SCHEMAS = [
  {
    name: "Simple Response",
    schema: {
      type: "object",
      properties: {
        message: { type: "string", description: "The response message" },
        success: { type: "boolean", description: "Whether the operation was successful" },
      },
      required: ["message", "success"],
    },
  },
  {
    name: "Contact Info",
    schema: {
      type: "object",
      properties: {
        name: { type: "string", description: "Full name" },
        email: { type: "string", description: "Email address" },
        phone: { type: "string", description: "Phone number" },
        company: { type: "string", description: "Company name" },
      },
      required: ["name", "email"],
    },
  },
  {
    name: "Task Result",
    schema: {
      type: "object",
      properties: {
        task_id: { type: "string", description: "Unique task identifier" },
        status: { type: "string", enum: ["pending", "completed", "failed"], description: "Task status" },
        result: { type: "object", description: "Task result data" },
        error: { type: "string", description: "Error message if failed" },
      },
      required: ["task_id", "status"],
    },
  },
];

const DEFAULT_FORM_DATA: JsonSchemaFormData = {
  name: "",
  description: "",
  schema_text: JSON.stringify(
    {
      type: "object",
      properties: {},
      required: [],
    },
    null,
    2
  ),
  version: "1.0",
  is_active: true,
};

export default function JsonSchemasManager() {
  const { toast } = useToast();
  const [searchQuery, setSearchQuery] = useState("");
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [editingSchema, setEditingSchema] = useState<JsonSchema | null>(null);
  const [formData, setFormData] = useState<JsonSchemaFormData>(DEFAULT_FORM_DATA);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [schemaToDelete, setSchemaToDelete] = useState<JsonSchema | null>(null);
  const [schemaError, setSchemaError] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [editorTab, setEditorTab] = useState<"json" | "builder">("json");
  const [fields, setFields] = useState<SchemaField[]>([]);

  const schemasQuery = useQuery<{ schemas: JsonSchema[] }>({
    queryKey: [JSON_SCHEMAS_PATH],
    queryFn: () => fetchJson<{ schemas: JsonSchema[] }>(JSON_SCHEMAS_PATH),
  });

  const schemas = schemasQuery.data?.schemas ?? [];

  const filteredSchemas = schemas.filter((schema) =>
    schema.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    (schema.description || "").toLowerCase().includes(searchQuery.toLowerCase())
  );

  const createMutation = useMutation({
    mutationFn: (data: { name: string; description: string; schema: Record<string, any>; version: string; is_active: boolean }) =>
      apiRequest("POST", JSON_SCHEMAS_PATH, { data }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [JSON_SCHEMAS_PATH] });
      setIsDialogOpen(false);
      setFormData(DEFAULT_FORM_DATA);
      setFields([]);
      toast({ title: "JSON schema created successfully" });
    },
    onError: (error: any) => {
      toast({
        title: "Failed to create JSON schema",
        description: error.message || "Please try again.",
        variant: "destructive",
      });
    },
  });

  const updateMutation = useMutation({
    mutationFn: (data: { name: string; description: string; schema: Record<string, any>; version: string; is_active: boolean }) =>
      apiRequest("PATCH", `${JSON_SCHEMAS_PATH}${editingSchema!.id}/`, { data }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [JSON_SCHEMAS_PATH] });
      setIsDialogOpen(false);
      setEditingSchema(null);
      setFormData(DEFAULT_FORM_DATA);
      setFields([]);
      toast({ title: "JSON schema updated successfully" });
    },
    onError: (error: any) => {
      toast({
        title: "Failed to update JSON schema",
        description: error.message || "Please try again.",
        variant: "destructive",
      });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) =>
      apiRequest("DELETE", `${JSON_SCHEMAS_PATH}${id}/`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [JSON_SCHEMAS_PATH] });
      setDeleteDialogOpen(false);
      setSchemaToDelete(null);
      toast({ title: "JSON schema deleted successfully" });
    },
    onError: (error: any) => {
      toast({
        title: "Failed to delete JSON schema",
        description: error.message || "Please try again.",
        variant: "destructive",
      });
    },
  });

  const parseSchemaToFields = (schema: Record<string, any>): SchemaField[] => {
    if (!schema.properties) return [];
    const required = schema.required || [];
    return Object.entries(schema.properties).map(([name, prop]: [string, any]) => ({
      name,
      type: prop.type || "string",
      description: prop.description || "",
      required: required.includes(name),
    }));
  };

  const fieldsToSchema = (fields: SchemaField[]): Record<string, any> => {
    const properties: Record<string, any> = {};
    const required: string[] = [];
    
    fields.forEach((field) => {
      properties[field.name] = {
        type: field.type,
        description: field.description,
      };
      if (field.required) {
        required.push(field.name);
      }
    });

    return {
      type: "object",
      properties,
      required,
    };
  };

  const handleCreate = () => {
    setEditingSchema(null);
    setFormData(DEFAULT_FORM_DATA);
    setFields([]);
    setSchemaError(null);
    setEditorTab("json");
    setIsDialogOpen(true);
  };

  const handleEdit = (schema: JsonSchema) => {
    setEditingSchema(schema);
    setFormData({
      name: schema.name,
      description: schema.description || "",
      schema_text: JSON.stringify(schema.schema, null, 2),
      version: schema.version,
      is_active: schema.is_active,
    });
    setFields(parseSchemaToFields(schema.schema));
    setSchemaError(null);
    setEditorTab("json");
    setIsDialogOpen(true);
  };

  const handleDelete = (schema: JsonSchema) => {
    setSchemaToDelete(schema);
    setDeleteDialogOpen(true);
  };

  const handleCopySchema = async (schema: JsonSchema) => {
    try {
      await navigator.clipboard.writeText(JSON.stringify(schema.schema, null, 2));
      setCopiedId(schema.id);
      setTimeout(() => setCopiedId(null), 2000);
      toast({ title: "Schema copied to clipboard" });
    } catch {
      toast({ title: "Failed to copy schema", variant: "destructive" });
    }
  };

  const validateSchema = (text: string): Record<string, any> | null => {
    try {
      const parsed = JSON.parse(text);
      if (typeof parsed !== "object" || parsed === null) {
        setSchemaError("Schema must be a JSON object");
        return null;
      }
      setSchemaError(null);
      return parsed;
    } catch (e) {
      setSchemaError("Invalid JSON syntax");
      return null;
    }
  };

  const handleSchemaTextChange = (text: string) => {
    setFormData({ ...formData, schema_text: text });
    const parsed = validateSchema(text);
    if (parsed) {
      setFields(parseSchemaToFields(parsed));
    }
  };

  const handleFieldsChange = (newFields: SchemaField[]) => {
    setFields(newFields);
    const schema = fieldsToSchema(newFields);
    setFormData({ ...formData, schema_text: JSON.stringify(schema, null, 2) });
    setSchemaError(null);
  };

  const addField = () => {
    handleFieldsChange([
      ...fields,
      { name: "", type: "string", description: "", required: false },
    ]);
  };

  const updateField = (index: number, updates: Partial<SchemaField>) => {
    const newFields = [...fields];
    newFields[index] = { ...newFields[index], ...updates };
    handleFieldsChange(newFields);
  };

  const removeField = (index: number) => {
    handleFieldsChange(fields.filter((_, i) => i !== index));
  };

  const applyTemplate = (template: typeof EXAMPLE_SCHEMAS[0]) => {
    setFormData({
      ...formData,
      schema_text: JSON.stringify(template.schema, null, 2),
    });
    setFields(parseSchemaToFields(template.schema));
    setSchemaError(null);
  };

  const handleSubmit = () => {
    const schema = validateSchema(formData.schema_text);
    if (!schema) return;

    const data = {
      name: formData.name,
      description: formData.description,
      schema,
      version: formData.version,
      is_active: formData.is_active,
    };

    if (editingSchema) {
      updateMutation.mutate(data);
    } else {
      createMutation.mutate(data);
    }
  };

  const isFormValid = formData.name.trim() !== "" && !schemaError;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Button variant="ghost" size="icon" asChild>
          <Link href="/workflows?tab=components" data-testid="button-back-components">
            <ArrowLeft className="h-4 w-4" />
          </Link>
        </Button>
        <div className="flex-1">
          <h1 className="text-xl font-semibold" data-testid="text-page-title">JSON Schemas</h1>
          <p className="text-sm text-muted-foreground">
            Reusable output schemas for structured AI agent responses
          </p>
        </div>
        <Button onClick={handleCreate} data-testid="button-create-schema">
          <Plus className="h-4 w-4 mr-2" />
          New Schema
        </Button>
      </div>

      <div className="flex items-center gap-2">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search schemas..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9"
            data-testid="input-search-schemas"
          />
        </div>
      </div>

      {schemasQuery.isLoading ? (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-40 bg-muted animate-pulse rounded-lg" />
          ))}
        </div>
      ) : filteredSchemas.length === 0 ? (
        <div className="flex flex-col items-center justify-center text-center border border-dashed border-muted-foreground/40 rounded-lg p-8 bg-white/60 dark:bg-slate-900/60">
          <Braces className="h-10 w-10 text-muted-foreground mb-4" />
          <h3 className="text-lg font-semibold text-foreground">
            {searchQuery ? "No schemas found" : "No JSON schemas yet"}
          </h3>
          <p className="mt-2 text-sm text-muted-foreground max-w-sm">
            {searchQuery
              ? "Try adjusting your search query"
              : "Create your first JSON schema to define structured outputs for AI agents"}
          </p>
          {!searchQuery && (
            <Button onClick={handleCreate} className="mt-4" data-testid="button-create-first-schema">
              <Plus className="h-4 w-4 mr-2" />
              Create Schema
            </Button>
          )}
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {filteredSchemas.map((schema) => (
            <div
              key={schema.id}
              className="group relative p-4 border rounded-lg bg-card hover-elevate"
              data-testid={`card-schema-${schema.id}`}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-lg bg-orange-50 flex items-center justify-center shrink-0">
                    <Braces className="h-5 w-5 text-orange-600" />
                  </div>
                  <div className="min-w-0">
                    <h3 className="font-medium truncate" data-testid={`text-schema-name-${schema.id}`}>
                      {schema.name}
                    </h3>
                    <p className="text-xs text-muted-foreground">
                      v{schema.version}
                    </p>
                  </div>
                </div>
                <Badge variant={schema.is_active ? "default" : "secondary"}>
                  {schema.is_active ? "Active" : "Inactive"}
                </Badge>
              </div>

              {schema.description && (
                <p className="mt-3 text-sm text-muted-foreground line-clamp-2">
                  {schema.description}
                </p>
              )}

              <div className="mt-3 flex items-center gap-2 flex-wrap">
                <Badge variant="outline" className="text-xs">
                  {Object.keys(schema.schema.properties || {}).length} fields
                </Badge>
                {schema.usage_count !== undefined && schema.usage_count > 0 && (
                  <Badge variant="outline" className="text-xs">
                    Used by {schema.usage_count} agents
                  </Badge>
                )}
              </div>

              <div className="mt-4 flex items-center justify-end gap-2">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => handleCopySchema(schema)}
                  data-testid={`button-copy-schema-${schema.id}`}
                >
                  {copiedId === schema.id ? (
                    <Check className="h-4 w-4 text-green-500" />
                  ) : (
                    <Copy className="h-4 w-4" />
                  )}
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => handleEdit(schema)}
                  data-testid={`button-edit-schema-${schema.id}`}
                >
                  <Edit2 className="h-4 w-4" />
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => handleDelete(schema)}
                  className="text-destructive hover:text-destructive"
                  data-testid={`button-delete-schema-${schema.id}`}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}

      <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
        <DialogContent className="max-w-3xl max-h-[90vh] overflow-hidden flex flex-col">
          <DialogHeader>
            <DialogTitle>
              {editingSchema ? "Edit JSON Schema" : "Create JSON Schema"}
            </DialogTitle>
            <DialogDescription>
              Define a structured output schema for AI agent responses
            </DialogDescription>
          </DialogHeader>

          <ScrollArea className="flex-1 pr-4">
            <div className="space-y-6 py-4">
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="schema-name">Schema Name *</Label>
                  <Input
                    id="schema-name"
                    value={formData.name}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                    placeholder="Contact Response"
                    data-testid="input-schema-name"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="schema-version">Version</Label>
                  <Input
                    id="schema-version"
                    value={formData.version}
                    onChange={(e) => setFormData({ ...formData, version: e.target.value })}
                    placeholder="1.0"
                    data-testid="input-schema-version"
                  />
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="schema-description">Description</Label>
                <Textarea
                  id="schema-description"
                  value={formData.description}
                  onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                  placeholder="Describe what this schema is used for..."
                  rows={2}
                  data-testid="input-schema-description"
                />
              </div>

              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <Label>Templates</Label>
                </div>
                <div className="flex flex-wrap gap-2">
                  {EXAMPLE_SCHEMAS.map((template) => (
                    <Button
                      key={template.name}
                      variant="outline"
                      size="sm"
                      onClick={() => applyTemplate(template)}
                      data-testid={`button-template-${template.name.toLowerCase().replace(/\s+/g, '-')}`}
                    >
                      {template.name}
                    </Button>
                  ))}
                </div>
              </div>

              <div className="space-y-2">
                <Tabs value={editorTab} onValueChange={(v) => setEditorTab(v as "json" | "builder")}>
                  <div className="flex items-center justify-between">
                    <Label>Schema Definition</Label>
                    <TabsList>
                      <TabsTrigger value="json" data-testid="tab-json-editor">JSON</TabsTrigger>
                      <TabsTrigger value="builder" data-testid="tab-visual-builder">Visual</TabsTrigger>
                    </TabsList>
                  </div>

                  <TabsContent value="json" className="mt-2">
                    <Textarea
                      value={formData.schema_text}
                      onChange={(e) => handleSchemaTextChange(e.target.value)}
                      className="font-mono text-sm min-h-[200px]"
                      placeholder="{}"
                      data-testid="input-schema-json"
                    />
                    {schemaError && (
                      <p className="text-sm text-destructive mt-1">{schemaError}</p>
                    )}
                  </TabsContent>

                  <TabsContent value="builder" className="mt-2">
                    <div className="border rounded-md p-4 space-y-4">
                      {fields.length === 0 ? (
                        <p className="text-sm text-muted-foreground text-center py-4">
                          No fields defined. Add your first field below.
                        </p>
                      ) : (
                        <div className="space-y-3">
                          {fields.map((field, index) => (
                            <div
                              key={index}
                              className="grid gap-2 sm:grid-cols-12 items-start p-3 border rounded-md bg-muted/30"
                            >
                              <div className="sm:col-span-3">
                                <Input
                                  placeholder="Field name"
                                  value={field.name}
                                  onChange={(e) => updateField(index, { name: e.target.value })}
                                  data-testid={`input-field-name-${index}`}
                                />
                              </div>
                              <div className="sm:col-span-2">
                                <select
                                  className="w-full h-9 rounded-md border border-input bg-background px-3 py-1 text-sm"
                                  value={field.type}
                                  onChange={(e) => updateField(index, { type: e.target.value as SchemaField["type"] })}
                                  data-testid={`select-field-type-${index}`}
                                >
                                  <option value="string">String</option>
                                  <option value="number">Number</option>
                                  <option value="boolean">Boolean</option>
                                  <option value="array">Array</option>
                                  <option value="object">Object</option>
                                </select>
                              </div>
                              <div className="sm:col-span-4">
                                <Input
                                  placeholder="Description"
                                  value={field.description}
                                  onChange={(e) => updateField(index, { description: e.target.value })}
                                  data-testid={`input-field-desc-${index}`}
                                />
                              </div>
                              <div className="sm:col-span-2 flex items-center gap-2">
                                <input
                                  type="checkbox"
                                  checked={field.required}
                                  onChange={(e) => updateField(index, { required: e.target.checked })}
                                  className="h-4 w-4"
                                  id={`required-${index}`}
                                  data-testid={`checkbox-field-required-${index}`}
                                />
                                <label htmlFor={`required-${index}`} className="text-xs">Required</label>
                              </div>
                              <div className="sm:col-span-1">
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => removeField(index)}
                                  className="text-destructive"
                                  data-testid={`button-remove-field-${index}`}
                                >
                                  <Trash2 className="h-4 w-4" />
                                </Button>
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={addField}
                        className="w-full"
                        data-testid="button-add-field"
                      >
                        <Plus className="h-4 w-4 mr-2" />
                        Add Field
                      </Button>
                    </div>
                  </TabsContent>
                </Tabs>
              </div>
            </div>
          </ScrollArea>

          <DialogFooter>
            <Button variant="outline" onClick={() => setIsDialogOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleSubmit}
              disabled={!isFormValid || createMutation.isPending || updateMutation.isPending}
              data-testid="button-save-schema"
            >
              {createMutation.isPending || updateMutation.isPending ? "Saving..." : "Save Schema"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete JSON Schema</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete "{schemaToDelete?.name}"? This action cannot be undone.
              Any agents using this schema will need to be updated.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => schemaToDelete && deleteMutation.mutate(schemaToDelete.id)}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {deleteMutation.isPending ? "Deleting..." : "Delete"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
