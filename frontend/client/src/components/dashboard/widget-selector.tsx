import { useState, useEffect } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { WIDGET_REGISTRY, WIDGET_CATEGORIES, type WidgetMeta } from "./widget-registry";
import type { WidgetConfig, WidgetType } from "@shared/schema";
import { Settings2 } from "lucide-react";

interface WidgetSelectorProps {
  open: boolean;
  onClose: () => void;
  widgets: WidgetConfig[];
  onSave: (widgets: WidgetConfig[]) => Promise<void> | void;
}

export function WidgetSelector({ open, onClose, widgets, onSave }: WidgetSelectorProps) {
  const [localWidgets, setLocalWidgets] = useState<WidgetConfig[]>(widgets);

  useEffect(() => {
    setLocalWidgets(widgets);
  }, [open, widgets]);

  const isEnabled = (type: WidgetType) => {
    const widget = localWidgets.find((w) => w.type === type);
    return widget?.enabled ?? false;
  };

  const toggleWidget = (type: WidgetType) => {
    const existing = localWidgets.find((w) => w.type === type);
    if (existing) {
      setLocalWidgets(
        localWidgets.map((w) =>
          w.type === type ? { ...w, enabled: !w.enabled } : w
        )
      );
    } else {
      const meta = WIDGET_REGISTRY[type];
      const newWidget: WidgetConfig = {
        id: `${type}-${Date.now()}`,
        type,
        enabled: true,
        size: meta.defaultSize,
        order: localWidgets.length,
      };
      setLocalWidgets([...localWidgets, newWidget]);
    }
  };

  const [isSaving, setIsSaving] = useState(false);

  const handleSave = async () => {
    setIsSaving(true);
    try {
      await onSave(localWidgets);
    } finally {
      setIsSaving(false);
    }
  };

  const handleReset = () => {
    setLocalWidgets(widgets);
  };

  const getCategoryWidgets = (category: WidgetMeta["category"]) => {
    return Object.values(WIDGET_REGISTRY).filter((w) => w.category === category);
  };

  return (
    <Dialog open={open} onOpenChange={(isOpen) => !isOpen && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Settings2 className="h-5 w-5" />
            Customize Dashboard
          </DialogTitle>
          <DialogDescription>
            Select which widgets to display on your dashboard.
          </DialogDescription>
        </DialogHeader>

        <ScrollArea className="h-[400px] pr-4">
          <div className="space-y-6">
            {WIDGET_CATEGORIES.map((category) => {
              const categoryWidgets = getCategoryWidgets(category.id);
              if (categoryWidgets.length === 0) return null;

              return (
                <div key={category.id}>
                  <h3 className="text-sm font-semibold mb-2 flex items-center gap-2">
                    {category.name}
                    <Badge variant="secondary" className="text-xs">
                      {categoryWidgets.filter((w) => isEnabled(w.type)).length}/
                      {categoryWidgets.length}
                    </Badge>
                  </h3>
                  <p className="text-xs text-muted-foreground mb-3">
                    {category.description}
                  </p>
                  <div className="space-y-2">
                    {categoryWidgets.map((widget) => {
                      const Icon = widget.icon;
                      return (
                        <div
                          key={widget.type}
                          className="flex items-center justify-between p-3 rounded-lg border hover-elevate"
                          data-testid={`widget-toggle-${widget.type}`}
                        >
                          <div className="flex items-center gap-3">
                            <div className="h-8 w-8 rounded-md bg-muted flex items-center justify-center">
                              <Icon className="h-4 w-4 text-muted-foreground" />
                            </div>
                            <div>
                              <p className="text-sm font-medium">{widget.name}</p>
                              <p className="text-xs text-muted-foreground">
                                {widget.description}
                              </p>
                            </div>
                          </div>
                          <Switch
                            checked={isEnabled(widget.type)}
                            onCheckedChange={() => toggleWidget(widget.type)}
                            data-testid={`switch-widget-${widget.type}`}
                          />
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        </ScrollArea>

        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={handleReset} data-testid="button-reset-widgets">
            Reset
          </Button>
          <Button variant="outline" onClick={onClose} data-testid="button-cancel-widgets">
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={isSaving} data-testid="button-save-widgets">
            {isSaving ? "Saving..." : "Save Changes"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
