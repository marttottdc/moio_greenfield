import { useState, useMemo } from "react";
import { ChevronDown, ChevronRight, HelpCircle, icons } from "lucide-react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { assertDefined } from "@/lib/errors";

/**
 * Convert kebab-case icon names (from backend) to camelCase (lucide format).
 * Examples: "message-square" → "MessageSquare", "check-circle" → "CheckCircle"
 */
function kebabToCamelCase(str: string): string {
  return str.split('-').reduce((acc, word, index) => {
    if (index === 0) return word.charAt(0).toUpperCase() + word.slice(1);
    return acc + word.charAt(0).toUpperCase() + word.slice(1);
  }, '');
}

/**
 * Resolve icon from backend icon string.
 * Converts kebab-case to camelCase and looks up in lucide icons.
 * Falls back to HelpCircle for unknown icons.
 */
function resolveIcon(iconString: string): React.ComponentType<{ className?: string }> {
  const camelCaseIcon = kebabToCamelCase(iconString);
  const iconComponent = icons[camelCaseIcon as keyof typeof icons];
  return iconComponent || HelpCircle;
}

interface PaletteNode {
  id: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  outputs?: string[];
  inputs?: string[];
  portSchemas?: PortSchemaMap;
  defaultConfig?: Record<string, any>;
  formComponent?: string;
  stageLimited?: boolean;
  hints?: BackendNodeDefinition['hints'];
}

interface PaletteCategory {
  id: string;
  label: string;
  items: PaletteNode[];
}

interface BackendPaletteCategory {
  id: string;
  label: string;
  items: Array<{
    kind: string;
    title: string;
    icon: string;
    description?: string;
  }>;
}

import { BackendNodeDefinition, PortDefinition } from "./types";

interface PortSchemaMap {
  in?: Record<string, PortDefinition>;
  out?: Record<string, PortDefinition>;
}

interface NodePaletteProps {
  onNodeDragStart: (
    nodeType: string, 
    label: string, 
    icon: any, 
    outputs?: string[], 
    inputs?: string[],
    portSchemas?: PortSchemaMap,
    defaultConfig?: Record<string, any>,
    formComponent?: string,
    hints?: BackendNodeDefinition['hints']
  ) => void;
  paletteData?: BackendPaletteCategory[];
  nodeDefinitions?: Record<string, BackendNodeDefinition>;
}

export function NodePalette({ onNodeDragStart, paletteData, nodeDefinitions }: NodePaletteProps) {
  // Collapsed by default; behaves like an accordion (only one open at a time).
  const [expandedCategories, setExpandedCategories] = useState<string[]>([]);

  // Convert backend palette data to component format
  const categories = useMemo<PaletteCategory[]>(() => {
    // Backend data is required - no silent fallbacks
    assertDefined(
      paletteData,
      "Flow Builder requires palette data from backend API endpoint /api/v1/flows/definitions/"
    );
    assertDefined(
      nodeDefinitions,
      "Flow Builder requires node definitions from backend API endpoint /api/v1/flows/definitions/"
    );

    // Transform backend data to component format
    return paletteData.map((category) => ({
      id: category.id,
      label: category.label.toUpperCase(),
      items: category.items.map((item) => {
        const definition = nodeDefinitions[item.kind];
        // Resolve icon from backend icon string using all lucide icons
        const iconString = (item.icon || '').toLowerCase();
        const iconComponent = resolveIcon(iconString);
        
        // Guard against missing definition
        if (!definition) {
          return {
            id: item.kind,
            label: item.title,
            icon: iconComponent,
            outputs: [],
            inputs: [],
          };
        }
        
        const portSchemas: PortSchemaMap = {};
        if (definition.ports?.in) {
          portSchemas.in = {};
          definition.ports.in.forEach((port) => {
            portSchemas.in![port.name] = port;
          });
        }
        if (definition.ports?.out) {
          portSchemas.out = {};
          definition.ports.out.forEach((port) => {
            portSchemas.out![port.name] = port;
          });
        }
        
        return {
          id: item.kind,
          label: item.title,
          icon: iconComponent,
          outputs: definition.ports?.out?.map((p) => p.name) || [],
          inputs: definition.ports?.in?.map((p) => p.name) || [],
          portSchemas,
          defaultConfig: definition.default_config,
          formComponent: definition.form_component,
          hints: definition.hints,
        };
      }),
    }));
  }, [paletteData, nodeDefinitions]);

  const toggleCategory = (categoryId: string) => {
    setExpandedCategories((prev) =>
      prev.includes(categoryId) ? [] : [categoryId]
    );
  };

  const handleDragStart = (
    event: React.DragEvent,
    nodeType: string,
    label: string,
    icon: any,
    outputs?: string[],
    inputs?: string[],
    portSchemas?: PortSchemaMap,
    defaultConfig?: Record<string, any>,
    formComponent?: string,
    hints?: BackendNodeDefinition['hints']
  ) => {
    event.dataTransfer.setData("application/reactflow", nodeType);
    event.dataTransfer.setData("nodeLabel", label);
    event.dataTransfer.setData("nodeOutputs", JSON.stringify(outputs || []));
    event.dataTransfer.setData("nodeInputs", JSON.stringify(inputs || []));
    event.dataTransfer.setData("nodePortSchemas", JSON.stringify(portSchemas || {}));
    event.dataTransfer.setData("nodeDefaultConfig", JSON.stringify(defaultConfig || {}));
    event.dataTransfer.setData("nodeFormComponent", formComponent || "");
    event.dataTransfer.setData("nodeHints", JSON.stringify(hints || {}));
    event.dataTransfer.effectAllowed = "move";
    onNodeDragStart(nodeType, label, icon, outputs, inputs, portSchemas, defaultConfig, formComponent, hints);
  };

  return (
    <div className="w-52 h-full flex flex-col border-r bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="px-3 py-3 border-b">
        <h2 className="font-semibold text-xs text-muted-foreground tracking-wide">NODE PALETTE</h2>
      </div>
      <ScrollArea className="flex-1 min-h-0">
        <div className="p-2">
          {categories.map((category) => {
            const isExpanded = expandedCategories.includes(category.id);
            return (
              <div key={category.id} className="mb-2">
                <button
                  type="button"
                  onClick={() => toggleCategory(category.id)}
                  className="flex items-center gap-2 w-full px-2 py-1.5 text-xs font-semibold text-muted-foreground hover:text-foreground transition-colors"
                  data-testid={`category-${category.id}`}
                >
                  {isExpanded ? (
                    <ChevronDown className="h-3 w-3" />
                  ) : (
                    <ChevronRight className="h-3 w-3" />
                  )}
                  {category.label}
                </button>
                {isExpanded && (
                  <div className="ml-2 mt-1 space-y-1">
                    {category.items.map((item) => {
                      const Icon = item.icon;
                      return (
                        <div
                          key={item.id}
                          draggable
                          onDragStart={(e) => handleDragStart(e, item.id, item.label, item.icon, item.outputs, item.inputs, item.portSchemas, item.defaultConfig, item.formComponent, item.hints)}
                          className="flex items-center gap-2 px-2 py-1.5 rounded-md hover-elevate active-elevate-2 cursor-grab active:cursor-grabbing border border-border/50 bg-card/50"
                          data-testid={`palette-node-${item.id}`}
                        >
                          <Icon className="h-3.5 w-3.5 text-muted-foreground flex-shrink-0" />
                          <span className="text-xs flex-1 truncate">{item.label}</span>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </ScrollArea>
    </div>
  );
}
