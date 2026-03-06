import { useState, useEffect } from "react";
import { useParams, Link, useLocation } from "wouter";
import { PageLayout } from "@/components/layout/page-layout";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  useDataLabPanels,
  useDataLabPanelCreate,
  useDataLabResultSets,
  useDataLabWidgetCreate,
} from "@/hooks/use-datalab";
import { ArrowLeft, Loader2, Save, Plus, Trash2 } from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import type { WidgetType } from "@/lib/moio-types";

interface WidgetForm {
  name: string;
  widget_type: WidgetType;
  datasource_id: string;
  config_json: any;
  position_x: number;
  position_y: number;
  width: number;
  height: number;
  order: number;
}

export default function PanelDesigner() {
  const { id } = useParams<{ id?: string }>();
  const [, setLocation] = useLocation();
  const isEditing = !!id;
  const { data: panels } = useDataLabPanels();
  const { data: resultsets } = useDataLabResultSets();
  const createPanelMutation = useDataLabPanelCreate();
  const createWidgetMutation = useDataLabWidgetCreate();
  const { toast } = useToast();

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [isPublic, setIsPublic] = useState(false);
  const [widgets, setWidgets] = useState<WidgetForm[]>([]);

  // Load existing panel if editing
  useEffect(() => {
    if (isEditing && panels) {
      const panel = panels.find((p) => p.id === id);
      if (panel) {
        setName(panel.name);
        setDescription(panel.description || "");
        setIsPublic(panel.is_public);
        // Note: Widgets would be loaded separately via renderPanel
      }
    }
  }, [id, isEditing, panels]);

  const handleSave = async () => {
    if (!name.trim()) {
      toast({
        title: "Validation error",
        description: "Panel name is required",
        variant: "destructive",
      });
      return;
    }

    try {
      const panel = await createPanelMutation.mutateAsync({
        name: name.trim(),
        description: description.trim() || undefined,
        layout_json: {
          grid: {
            columns: 12,
            rowHeight: 50,
          },
        },
        is_public: isPublic,
        shared_with_roles: [],
      });

      // Create widgets
      for (const widget of widgets) {
        await createWidgetMutation.mutateAsync({
          ...widget,
          panel: panel.id,
        });
      }

      toast({
        title: isEditing ? "Panel updated" : "Panel created",
        description: `Panel "${name}" has been ${isEditing ? "updated" : "created"} successfully.`,
      });

      setLocation(`/datalab/panels/${panel.id}`);
    } catch (error) {
      toast({
        title: "Save failed",
        description: error instanceof Error ? error.message : "Failed to save panel",
        variant: "destructive",
      });
    }
  };

  const addWidget = () => {
    const newWidget: WidgetForm = {
      name: `Widget ${widgets.length + 1}`,
      widget_type: "table",
      datasource_id: "",
      config_json: {},
      position_x: 0,
      position_y: widgets.length * 2,
      width: 6,
      height: 2,
      order: widgets.length + 1,
    };
    setWidgets([...widgets, newWidget]);
  };

  const removeWidget = (index: number) => {
    setWidgets(widgets.filter((_, i) => i !== index));
  };

  const updateWidget = (index: number, updates: Partial<WidgetForm>) => {
    const newWidgets = [...widgets];
    newWidgets[index] = { ...newWidgets[index], ...updates };
    setWidgets(newWidgets);
  };

  const availableResultSets = resultsets?.results || [];

  return (
    <PageLayout>
      <div className="space-y-6 max-w-6xl mx-auto">
        <div>
          <Link href="/datalab/panels">
            <Button variant="ghost" size="sm" className="mb-2">
              <ArrowLeft className="mr-2 h-4 w-4" />
              Back
            </Button>
          </Link>
          <h1 className="text-3xl font-bold">
            {isEditing ? "Edit Panel" : "New Panel"}
          </h1>
          <p className="text-muted-foreground mt-2">
            Create a custom dashboard with widgets
          </p>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Panel Details</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <Label htmlFor="name">Name *</Label>
              <Input
                id="name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Sales Dashboard"
              />
            </div>

            <div>
              <Label htmlFor="description">Description</Label>
              <Textarea
                id="description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Describe this dashboard..."
                rows={3}
              />
            </div>

            <div className="flex items-center space-x-2">
              <Switch
                id="isPublic"
                checked={isPublic}
                onCheckedChange={setIsPublic}
              />
              <Label htmlFor="isPublic" className="cursor-pointer">
                Make panel public
              </Label>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle>Widgets</CardTitle>
                <CardDescription>Add widgets to display data</CardDescription>
              </div>
              <Button variant="outline" size="sm" onClick={addWidget}>
                <Plus className="mr-2 h-4 w-4" />
                Add Widget
              </Button>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            {widgets.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-8">
                No widgets added. Click "Add Widget" to get started.
              </p>
            ) : (
              widgets.map((widget, index) => (
                <Card key={index} className="border-2">
                  <CardHeader>
                    <div className="flex items-center justify-between">
                      <CardTitle className="text-lg">Widget {index + 1}</CardTitle>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => removeWidget(index)}
                      >
                        <Trash2 className="h-4 w-4 text-destructive" />
                      </Button>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div>
                      <Label>Widget Name</Label>
                      <Input
                        value={widget.name}
                        onChange={(e) => updateWidget(index, { name: e.target.value })}
                        placeholder="Total Revenue"
                      />
                    </div>

                    <div>
                      <Label>Widget Type</Label>
                      <Select
                        value={widget.widget_type}
                        onValueChange={(value: WidgetType) =>
                          updateWidget(index, { widget_type: value })
                        }
                      >
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="table">Table</SelectItem>
                          <SelectItem value="kpi">KPI</SelectItem>
                          <SelectItem value="linechart">Line Chart</SelectItem>
                          <SelectItem value="barchart">Bar Chart</SelectItem>
                          <SelectItem value="piechart">Pie Chart</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>

                    <div>
                      <Label>Data Source</Label>
                      <Select
                        value={widget.datasource_id}
                        onValueChange={(value) =>
                          updateWidget(index, { datasource_id: value })
                        }
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
                    </div>

                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <Label>Width (columns)</Label>
                        <Input
                          type="number"
                          min={1}
                          max={12}
                          value={widget.width}
                          onChange={(e) =>
                            updateWidget(index, { width: parseInt(e.target.value) || 1 })
                          }
                        />
                      </div>
                      <div>
                        <Label>Height (rows)</Label>
                        <Input
                          type="number"
                          min={1}
                          max={10}
                          value={widget.height}
                          onChange={(e) =>
                            updateWidget(index, { height: parseInt(e.target.value) || 1 })
                          }
                        />
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))
            )}
          </CardContent>
        </Card>

        <div className="flex gap-2">
          <Link href="/datalab/panels">
            <Button variant="outline">Cancel</Button>
          </Link>
          <Button
            onClick={handleSave}
            disabled={createPanelMutation.isPending || createWidgetMutation.isPending}
            className="ml-auto"
          >
            {(createPanelMutation.isPending || createWidgetMutation.isPending) ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Saving...
              </>
            ) : (
              <>
                <Save className="mr-2 h-4 w-4" />
                Save Panel
              </>
            )}
          </Button>
        </div>
      </div>
    </PageLayout>
  );
}
