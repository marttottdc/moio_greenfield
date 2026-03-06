import { useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { ChevronDown, ChevronRight, Database, AlertCircle, Zap, ArrowLeft, Layers } from "lucide-react";

export interface DataNode {
  key: string;
  type: string;
  description?: string;
  source: string;
  children?: DataNode[];
}

interface DataVisualizerProps {
  data?: DataNode[];
  title?: string;
  compact?: boolean;
  maxHeight?: string;
}

function TreeItem({ item, level = 0 }: { item: DataNode; level: number }) {
  const [expanded, setExpanded] = useState(level < 2);
  const hasChildren = (item.children?.length ?? 0) > 0;

  const typeColor: Record<string, string> = {
    string: "bg-blue-100 dark:bg-blue-900/40 text-blue-800 dark:text-blue-200",
    number: "bg-green-100 dark:bg-green-900/40 text-green-800 dark:text-green-200",
    object: "bg-purple-100 dark:bg-purple-900/40 text-purple-800 dark:text-purple-200",
    array: "bg-orange-100 dark:bg-orange-900/40 text-orange-800 dark:text-orange-200",
    boolean: "bg-pink-100 dark:bg-pink-900/40 text-pink-800 dark:text-pink-200",
    unknown: "bg-gray-100 dark:bg-gray-900/40 text-gray-800 dark:text-gray-200",
  };

  const badgeClass = typeColor[item.type] || typeColor.unknown;

  return (
    <div className="space-y-0.5">
      <div
        className="flex items-start gap-1 py-0.5 px-1 hover:bg-muted/30 rounded text-xs cursor-pointer group"
        onClick={() => hasChildren && setExpanded(!expanded)}
      >
        {hasChildren ? (
          expanded ? (
            <ChevronDown className="h-3 w-3 text-muted-foreground flex-shrink-0 mt-0.5" />
          ) : (
            <ChevronRight className="h-3 w-3 text-muted-foreground flex-shrink-0 mt-0.5" />
          )
        ) : (
          <div className="h-3 w-3 flex-shrink-0" />
        )}

        <code className="font-mono text-muted-foreground break-all flex-1">
          {item.key}
        </code>

        <Badge variant="secondary" className={`ml-1 text-[10px] flex-shrink-0 ${badgeClass}`}>
          {item.type}
        </Badge>
      </div>

      {item.description && (
        <div className="pl-4 text-xs text-muted-foreground italic">
          {item.description}
        </div>
      )}

      {hasChildren && expanded && (
        <div className="pl-3 border-l border-border space-y-0">
          {item.children!.map((child, idx) => (
            <div key={`${child.key}-${idx}`}>
              <TreeItem item={child} level={level + 1} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/**
 * Deduplicate DataNode children recursively by composite key (source + key)
 * This preserves nodes with same key but different sources (e.g., 'data' from $input vs ctx.Event)
 */
function deduplicateDataNodes(nodes: DataNode[]): DataNode[] {
  const seen = new Set<string>();
  const result: DataNode[] = [];
  
  for (const node of nodes) {
    // Use composite key to allow same key from different sources
    const compositeKey = `${node.source}:${node.key}`;
    if (!seen.has(compositeKey)) {
      seen.add(compositeKey);
      result.push({
        ...node,
        children: node.children ? deduplicateDataNodes(node.children) : undefined,
      });
    }
  }
  
  return result;
}

export function DataVisualizer({
  data,
  title = "Available Data",
  compact = false,
  maxHeight = "300px",
}: DataVisualizerProps) {
  const isEmpty = !data || data.length === 0;

  // Deduplicate data at all levels to prevent duplicate key warnings
  const deduplicatedData = useMemo(() => {
    if (!data) return [];
    return deduplicateDataNodes(data);
  }, [data]);

  const groupedBySources = useMemo(() => {
    if (!deduplicatedData.length) return {};
    
    return deduplicatedData.reduce(
      (acc, item) => {
        if (!acc[item.source]) {
          acc[item.source] = [];
        }
        acc[item.source].push(item);
        return acc;
      },
      {} as Record<string, DataNode[]>
    );
  }, [deduplicatedData]);

  return (
    <div className={`space-y-2 p-3 bg-muted/20 rounded-md border border-border ${compact ? "text-xs" : ""}`}>
      <div className="flex items-center gap-2">
        <Database className="h-4 w-4 text-muted-foreground" />
        <h3 className={`font-semibold ${compact ? "text-xs" : "text-sm"}`}>
          {title}
        </h3>
        {data && (
          <Badge variant="outline" className="text-xs ml-auto">
            {data.length} fields
          </Badge>
        )}
      </div>

      {isEmpty ? (
        <Alert className="border-dashed">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription className="text-xs">
            No data available at this point in the flow. Connect an upstream trigger or node.
          </AlertDescription>
        </Alert>
      ) : (
        <ScrollArea className={maxHeight ? `h-[${maxHeight}]` : ""} data-testid="scroll-data-visualizer">
          <div className="space-y-3 pr-4">
            {Object.entries(groupedBySources).map(([source, items]) => (
              <div key={source}>
                <div className="text-xs font-semibold text-muted-foreground mb-1.5 flex items-center gap-2">
                  {source === "$input" ? (
                    <Zap className="h-3 w-3 text-amber-500" />
                  ) : source === "$trigger" ? (
                    <Zap className="h-3 w-3 text-orange-500" />
                  ) : source === "previous_node" ? (
                    <ArrowLeft className="h-3 w-3 text-blue-500" />
                  ) : source === "ctx" ? (
                    <Layers className="h-3 w-3 text-purple-500" />
                  ) : (
                    <div className="w-2 h-2 rounded-full bg-primary" />
                  )}
                  {source === "$input" 
                    ? "Webhook Input Data" 
                    : source === "$trigger"
                    ? "Trigger Metadata"
                    : source === "previous_node" 
                    ? "Previous Node Output" 
                    : source === "ctx"
                    ? "All Upstream Context"
                    : source}
                </div>
                <div className="space-y-0 pl-1">
                  {items.map((item, idx) => (
                    <div key={`${source}:${item.key}:${idx}`}>
                      <TreeItem item={item} level={0} />
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </ScrollArea>
      )}
    </div>
  );
}
