import { memo } from "react";
import { Handle, Position, NodeProps } from "reactflow";
import { Database } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { CustomNodeData } from "./types";
import { isBranchNodeType } from "./branchUtils";

const nodeTypeColors: Record<string, string> = {
  trigger: "border-blue-500 bg-blue-100 dark:bg-blue-900/40 dark:border-blue-400",
  action: "border-green-500 bg-green-100 dark:bg-green-900/40 dark:border-green-400",
  logic: "border-purple-500 bg-purple-100 dark:bg-purple-900/40 dark:border-purple-400",
  script: "border-orange-500 bg-orange-100 dark:bg-orange-900/40 dark:border-orange-400",
  output: "border-pink-500 bg-pink-100 dark:bg-pink-900/40 dark:border-pink-400",
  tool: "border-teal-500 bg-teal-100 dark:bg-teal-900/40 dark:border-teal-400",
};

function CustomNode({ data, selected, id }: NodeProps<CustomNodeData>) {
  const nodeCategory = data.type.split("_")[0];
  const colorClass = nodeTypeColors[nodeCategory] || "border-gray-500/50 bg-gray-50/50 dark:bg-gray-950/20";
  const Icon = data.icon;

  const isTriggerNode =
    data.type.startsWith("trigger_") ||
    data.type === "webhook" ||
    data.type === "event" ||
    data.type === "scheduled";
  const hasTriggerSchema =
    isTriggerNode &&
    Boolean(
      (data.config as any)?.expected_schema ||
        (data.config as any)?.schema?.expected_schema ||
        (data.config as any)?.event_schema ||
        (data.config as any)?.schema?.event_schema
    );

  const handleConfig = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (data.onConfig) {
      data.onConfig(id);
    }
  };

  const inputHandles = data.inputs || [];
  const isBranchNode = isBranchNodeType(data.type);
  const outputHandlesRaw = data.outputs || [];
  // Enforce branch output ordering: rules first, default last
  const outputHandles = isBranchNode
    ? [
        ...outputHandlesRaw.filter((o) => o !== "else"),
        ...(outputHandlesRaw.includes("else") ? ["else"] : []),
      ]
    : outputHandlesRaw;

  const handleSizeClass = isBranchNode ? "!w-3 !h-3" : "!w-2 !h-2";

  const needsConfig =
    Boolean(data.formComponent) ||
    data.type.startsWith("tool_") ||
    data.type.includes('ai') ||
    data.type.includes('http') ||
    data.type.includes('script') ||
    data.type.includes('email') ||
    data.type.includes('webhook') ||
    data.type === 'trigger_event' ||
    data.type === 'trigger_scheduled' ||
    isBranchNode;
  
  const getHandlePosition = (index: number, total: number, isBranch: boolean = false) => {
    if (total === 1) return 50;
    
    if (isBranch || total > 2) {
      const range = 40;
      const start = 50 - range / 2;
      return start + (index / (total - 1)) * range;
    }
    
    return 35 + (index * 30);
  };

  return (
    <div
      className={`relative bg-background border rounded-md shadow-sm transition-all w-[170px] sm:w-[190px] ${
        selected ? "shadow-md ring-2 ring-primary ring-offset-1" : "shadow-sm"
      } ${colorClass}`}
      data-testid={`node-${id}`}
    >
      {inputHandles.length > 0 && inputHandles.map((inputName, index) => {
        const offset = getHandlePosition(index, inputHandles.length, isBranchNode);
        
        return (
          <Handle
            key={`in-${inputName}`}
            type="target"
            position={Position.Left}
            id={inputName}
            isValidConnection={() => true}
            style={{ top: `${offset}%` }}
            className={`${handleSizeClass} !bg-muted-foreground hover:!bg-primary transition-colors !border !border-background`}
            data-testid={`handle-input-${id}-${inputName}`}
          />
        );
      })}

      <div className="flex items-center justify-between gap-1 px-2 py-1 border-b">
        <div className="flex items-center gap-1.5 flex-1 min-w-0">
          {Icon && (
            <div className="flex-shrink-0">
              <Icon className="h-3 w-3 text-muted-foreground" />
            </div>
          )}
          <div className="flex-1 min-w-0">
            <div className="font-medium text-xs leading-tight truncate">{data.label}</div>
            {data.description && (
              <div className="text-[10px] text-muted-foreground leading-tight truncate">{data.description}</div>
            )}
          </div>
        </div>
        <div className="flex items-center gap-0.5 flex-shrink-0" />
      </div>

      <div className="px-2 py-1.5 space-y-1">
        <div className="flex items-center justify-between gap-2 text-[10px]">
          <code className="text-[10px] bg-muted px-1 py-0.5 rounded font-mono truncate" title={id}>
            {id}
          </code>
          <Badge variant="outline" className="text-[10px] px-1 py-0">
            {data.type}
          </Badge>
        </div>
        
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1 text-[10px] text-muted-foreground">
            <Database className="h-2.5 w-2.5" />
            <span>Data:</span>
            <span className="font-medium text-foreground">{data.availableData?.length ?? 0}</span>
          </div>
          <div className="flex items-center gap-1 text-[10px] text-muted-foreground">
            <span>Config:</span>
            <span className="font-medium text-foreground">{data.config ? Object.keys(data.config).length : 0}</span>
          </div>
          {isTriggerNode && (
            <div className="flex items-center gap-1 text-[10px] text-muted-foreground">
              <span>Schema:</span>
              <span className={`font-medium ${hasTriggerSchema ? "text-foreground" : "text-muted-foreground"}`}>
                {hasTriggerSchema ? "yes" : "no"}
              </span>
            </div>
          )}
        </div>
      </div>

      {outputHandles.length > 0 && outputHandles.map((outputName, index) => {
        const offset = getHandlePosition(index, outputHandles.length, isBranchNode);

        return (
          <Handle
            // Use a stable key so renaming an output handle doesn't unmount/remount handles
            // (ReactFlow can get confused if handles churn while the user is wiring edges).
            key={`out-${id}-${outputName}-${data.handlesNonce ?? 0}`}
            type="source"
            position={Position.Right}
            id={outputName}
            isValidConnection={() => true}
            style={{ top: `${offset}%` }}
            className={`${handleSizeClass} !bg-muted-foreground hover:!bg-primary transition-colors !border !border-background`}
            title={outputName}
            data-handle-label={outputName}
            data-testid={`handle-output-${id}-${outputName}`}
          />
        );
      })}
    </div>
  );
}

export default memo(CustomNode);
