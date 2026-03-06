import { memo } from "react";
import { EdgeProps, getBezierPath, EdgeLabelRenderer, BaseEdge } from "reactflow";
import { Button } from "@/components/ui/button";
import { X } from "lucide-react";
import { CustomEdgeData } from "./types";

function CustomEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  style = {},
  markerEnd,
  selected,
  data,
}: EdgeProps<CustomEdgeData>) {
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });

  const handleDelete = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (data?.onDelete) {
      data.onDelete(id);
    }
  };

  const hasDataPreview = data?.dataPreview && data.dataPreview.length > 0;
  const isBranchEdge = data?.isBranchEdge;
  const sourceHandle = data?.sourceHandle;
  const sourceLabel = data?.ruleName || data?.sourceHandle;
  const showBranchLabel = isBranchEdge && sourceLabel && !selected && !hasDataPreview;
  const isReadOnly = Boolean(data?.readOnly);

  return (
    <>
      <BaseEdge
        path={edgePath}
        markerEnd={markerEnd}
        style={{
          ...style,
          strokeWidth: selected ? 3 : 2,
          stroke: selected ? "hsl(45, 93%, 47%)" : "hsl(210, 100%, 50%)",
          opacity: selected ? 1 : 0.85,
        }}
      />
      <EdgeLabelRenderer>
        <div
          style={{
            position: "absolute",
            transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
            pointerEvents: "all",
          }}
          className="nodrag nopan"
        >
          {selected && !isReadOnly && (
            <Button
              variant="destructive"
              size="icon"
              className="h-6 w-6 rounded-full shadow-lg"
              onClick={handleDelete}
              data-testid={`button-delete-edge-${id}`}
            >
              <X className="h-3 w-3" />
            </Button>
          )}
          
          {!selected && hasDataPreview && (
            <div className="bg-background border rounded-md shadow-sm px-1.5 py-1 max-w-[180px]">
              <div className="text-[9px] font-medium text-muted-foreground mb-0.5">
                Data Flow ({data!.dataPreview!.length} fields)
              </div>
              <div className="space-y-0.5 max-h-16 overflow-y-auto">
                {data!.dataPreview!.slice(0, 4).map((field) => (
                  <div key={field.key} className="text-[8px] flex items-start gap-1">
                    <code className="bg-muted px-0.5 rounded font-mono flex-shrink-0 text-[8px]">
                      {field.key}
                    </code>
                    <span className="text-muted-foreground truncate text-[8px]">
                      {field.type}
                    </span>
                  </div>
                ))}
                {data!.dataPreview!.length > 4 && (
                  <div className="text-[8px] text-muted-foreground italic">
                    +{data!.dataPreview!.length - 4} more
                  </div>
                )}
              </div>
            </div>
          )}
          
          {showBranchLabel && (
            <div className="bg-primary/90 text-primary-foreground px-2 py-0.5 rounded-md shadow-md border border-primary/20">
              <span className="text-[10px] font-medium whitespace-nowrap">
                {sourceLabel}
              </span>
            </div>
          )}
        </div>
      </EdgeLabelRenderer>
    </>
  );
}

export default memo(CustomEdge);
