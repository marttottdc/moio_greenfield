import { useState, useMemo } from "react";
import { ChevronRight, ChevronDown, Copy, Check } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface SchemaViewerProps {
  schema: any;
  title?: string;
  className?: string;
  defaultExpanded?: boolean;
}

interface PropertyRowProps {
  name: string;
  schema: any;
  required?: boolean;
  depth?: number;
}

const typeColors: Record<string, string> = {
  string: "text-emerald-400",
  number: "text-amber-400",
  integer: "text-amber-400",
  boolean: "text-purple-400",
  array: "text-blue-400",
  object: "text-cyan-400",
  null: "text-slate-500",
};

function getTypeBadge(schema: any): { type: string; format?: string } {
  if (!schema) return { type: "unknown" };
  
  if (schema.type === "array") {
    const itemType = schema.items?.type || "any";
    return { type: `${itemType}[]`, format: schema.items?.format };
  }
  
  return { type: schema.type || "any", format: schema.format };
}

function PropertyRow({ name, schema, required = false, depth = 0 }: PropertyRowProps) {
  const [expanded, setExpanded] = useState(depth < 2);
  const hasChildren =
    schema?.type === "object" && schema?.properties && Object.keys(schema.properties).length > 0;
  const hasArrayChildren =
    schema?.type === "array" && schema?.items?.type === "object" && schema?.items?.properties;

  const { type, format } = getTypeBadge(schema);
  const typeColor = typeColors[schema?.type] || typeColors[schema?.items?.type] || "text-slate-400";

  return (
    <div className="border-l border-slate-800 ml-2">
      <div
        className={cn(
          "flex items-start gap-2 py-1.5 px-2 hover:bg-slate-800/50 transition-colors",
          (hasChildren || hasArrayChildren) && "cursor-pointer"
        )}
        onClick={() => (hasChildren || hasArrayChildren) && setExpanded(!expanded)}
      >
        <div className="flex-shrink-0 w-4 mt-0.5">
          {(hasChildren || hasArrayChildren) ? (
            expanded ? (
              <ChevronDown className="h-4 w-4 text-slate-500" />
            ) : (
              <ChevronRight className="h-4 w-4 text-slate-500" />
            )
          ) : null}
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <code className="text-cyan-300 font-mono text-sm">{name}</code>
            <span className={cn("font-mono text-xs", typeColor)}>{type}</span>
            {format && (
              <Badge variant="outline" className="text-[10px] px-1 py-0 border-slate-700 text-slate-400">
                {format}
              </Badge>
            )}
            {required && (
              <Badge className="text-[10px] px-1 py-0 bg-rose-500/20 text-rose-300 border-rose-500/40">
                required
              </Badge>
            )}
            {schema?.deprecated && (
              <Badge variant="outline" className="text-[10px] px-1 py-0 border-amber-500/40 text-amber-400">
                deprecated
              </Badge>
            )}
          </div>
          {schema?.description && (
            <p className="text-slate-400 text-xs mt-0.5 leading-relaxed">
              {schema.description}
            </p>
          )}
          {schema?.enum && (
            <div className="flex flex-wrap gap-1 mt-1">
              <span className="text-xs text-slate-500">Enum:</span>
              {schema.enum.map((val: any, i: number) => (
                <code
                  key={i}
                  className="text-[11px] bg-slate-800 px-1.5 py-0.5 rounded text-emerald-300"
                >
                  {JSON.stringify(val)}
                </code>
              ))}
            </div>
          )}
          {schema?.default !== undefined && (
            <div className="text-xs text-slate-500 mt-0.5">
              Default: <code className="text-slate-300">{JSON.stringify(schema.default)}</code>
            </div>
          )}
          {schema?.example !== undefined && (
            <div className="text-xs text-slate-500 mt-0.5">
              Example: <code className="text-slate-300">{JSON.stringify(schema.example)}</code>
            </div>
          )}
        </div>
      </div>

      {expanded && hasChildren && (
        <div className="ml-4">
          {Object.entries(schema.properties).map(([propName, propSchema]) => (
            <PropertyRow
              key={propName}
              name={propName}
              schema={propSchema}
              required={schema.required?.includes(propName)}
              depth={depth + 1}
            />
          ))}
        </div>
      )}

      {expanded && hasArrayChildren && (
        <div className="ml-4">
          <div className="text-xs text-slate-500 px-2 py-1 italic">Array items:</div>
          {Object.entries(schema.items.properties).map(([propName, propSchema]) => (
            <PropertyRow
              key={propName}
              name={propName}
              schema={propSchema}
              required={schema.items.required?.includes(propName)}
              depth={depth + 1}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export function SchemaViewer({ schema, title, className, defaultExpanded = true }: SchemaViewerProps) {
  const [showRaw, setShowRaw] = useState(false);
  const [copied, setCopied] = useState(false);

  const properties = useMemo(() => {
    if (!schema) return null;
    
    // Handle OpenAPI content wrapper
    if (schema.content?.["application/json"]?.schema) {
      return schema.content["application/json"].schema;
    }
    
    // Handle direct schema
    if (schema.schema) {
      return schema.schema;
    }
    
    return schema;
  }, [schema]);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(JSON.stringify(schema, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 1200);
  };

  if (!schema || (typeof schema === "object" && Object.keys(schema).length === 0)) {
    return null;
  }

  const hasViewableProperties =
    properties?.type === "object" && properties?.properties && Object.keys(properties.properties).length > 0;

  return (
    <div className={cn("rounded-lg border border-slate-800 bg-slate-900/70 overflow-hidden", className)}>
      <div className="flex items-center justify-between px-3 py-2 border-b border-slate-800 bg-slate-900/50">
        <div className="flex items-center gap-2">
          {title && <span className="text-sm font-medium text-slate-200">{title}</span>}
          {properties?.type && (
            <Badge variant="outline" className="text-xs border-slate-700 text-slate-400">
              {properties.type}
            </Badge>
          )}
        </div>
        <div className="flex items-center gap-1">
          {hasViewableProperties && (
            <Button
              type="button"
              size="sm"
              variant="ghost"
              className="h-7 px-2 text-xs text-slate-400 hover:text-slate-200"
              onClick={() => setShowRaw(!showRaw)}
            >
              {showRaw ? "Formatted" : "Raw JSON"}
            </Button>
          )}
          <Button
            type="button"
            size="icon"
            variant="ghost"
            className="h-7 w-7 text-slate-400 hover:text-slate-200"
            onClick={handleCopy}
          >
            {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
          </Button>
        </div>
      </div>

      <div className="max-h-[400px] overflow-auto">
        {showRaw || !hasViewableProperties ? (
          <pre className="p-3 text-xs text-slate-200 font-mono leading-relaxed">
            {JSON.stringify(schema, null, 2)}
          </pre>
        ) : (
          <div className="py-1">
            {Object.entries(properties.properties).map(([name, propSchema]) => (
              <PropertyRow
                key={name}
                name={name}
                schema={propSchema}
                required={properties.required?.includes(name)}
                depth={0}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default SchemaViewer;
