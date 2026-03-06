import { useState, useMemo } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Trash2, Plus, ChevronDown, Zap, ArrowLeft, Layers } from "lucide-react";
import { cn } from "@/lib/utils";

const getSourceLabel = (source: string): string => {
  if (source === "$input") return "Webhook Input Data";
  if (source === "$trigger") return "Trigger Metadata";
  if (source === "previous_node") return "Previous Node Output";
  if (source === "ctx") return "All Upstream Context";
  return source;
};

export interface SchemaField {
  path: string;
  type: string;
  description?: string;
  source: string;
}

interface SchemaFieldSelectorProps {
  value?: string;
  onChange: (value: string) => void;
  availableFields: SchemaField[];
  placeholder?: string;
  label?: string;
  onSelect?: (field: SchemaField) => void;
}

/**
 * SchemaFieldSelector allows users to select fields from available data in the flow
 * and generates variable references like $webhook.form.email or $trigger.data.name
 */
export function SchemaFieldSelector({
  value,
  onChange,
  availableFields,
  placeholder = "Select a field...",
  label = "Field",
  onSelect,
}: SchemaFieldSelectorProps) {
  const [open, setOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");

  // Group fields by source (webhook, trigger, etc)
  const groupedFields = useMemo(() => {
    return availableFields.reduce(
      (acc, field) => {
        if (!acc[field.source]) {
          acc[field.source] = [];
        }
        acc[field.source].push(field);
        return acc;
      },
      {} as Record<string, SchemaField[]>
    );
  }, [availableFields]);

  // Filter fields by search query
  const filteredGroups = useMemo(() => {
    if (!searchQuery.trim()) return groupedFields;

    const query = searchQuery.toLowerCase();
    const filtered: Record<string, SchemaField[]> = {};

    Object.entries(groupedFields).forEach(([source, fields]) => {
      const match = fields.filter(
        (field) =>
          field.path.toLowerCase().includes(query) ||
          (field.description?.toLowerCase().includes(query) ?? false)
      );
      if (match.length > 0) {
        filtered[source] = match;
      }
    });

    return filtered;
  }, [groupedFields, searchQuery]);

  const handleSelect = (field: SchemaField) => {
    onChange(field.path);
    onSelect?.(field);
    setOpen(false);
    setSearchQuery("");
  };

  const displayValue = value
    ? availableFields.find((f) => f.path === value)?.path || value
    : undefined;

  return (
    <div className="space-y-2">
      {label && <Label className="text-xs">{label}</Label>}
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button
            variant="outline"
            role="combobox"
            aria-expanded={open}
            className="w-full justify-between text-sm"
            data-testid="button-field-selector"
          >
            <span className="truncate text-left flex-1">
              {displayValue ? (
                <code className="text-xs font-mono">{displayValue}</code>
              ) : (
                <span className="text-muted-foreground">{placeholder}</span>
              )}
            </span>
            <ChevronDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-72 p-0" side="bottom" align="start">
          <Command>
            <CommandInput
              placeholder="Search fields..."
              value={searchQuery}
              onValueChange={setSearchQuery}
              data-testid="input-field-search"
            />
            <CommandList>
              <CommandEmpty>No fields found.</CommandEmpty>
              {Object.entries(filteredGroups).map(([source, fields]) => (
                <CommandGroup key={source} heading={getSourceLabel(source)}>
                  {fields.map((field) => (
                    <CommandItem
                      key={field.path}
                      value={field.path}
                      onSelect={() => handleSelect(field)}
                      data-testid={`item-field-${field.path}`}
                    >
                      <div className="flex-1 min-w-0">
                        <code className="text-xs font-mono break-all">
                          {field.path}
                        </code>
                        {field.description && (
                          <p className="text-xs text-muted-foreground mt-1">
                            {field.description}
                          </p>
                        )}
                      </div>
                      <Badge variant="secondary" className="ml-2 text-xs shrink-0">
                        {field.type}
                      </Badge>
                    </CommandItem>
                  ))}
                </CommandGroup>
              ))}
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>
      {displayValue && (
        <div className="flex items-center gap-2">
          <code className="text-xs bg-muted px-2 py-1 rounded flex-1 break-all">
            {displayValue}
          </code>
          <Button
            size="icon"
            variant="ghost"
            onClick={() => onChange("")}
            data-testid="button-clear-field"
          >
            <Trash2 className="h-3 w-3" />
          </Button>
        </div>
      )}
    </div>
  );
}

/**
 * FieldReferenceBuilder helps users build variable references like $webhook.form.email
 * and shows them inline for easy copying
 */
export function FieldReferenceBuilder({
  selectedField,
  onCopy,
}: {
  selectedField?: string;
  onCopy?: (reference: string) => void;
}) {
  if (!selectedField) return null;

  // Generate the reference format
  const reference = `$${selectedField}`;

  return (
    <div className="mt-2 p-2 bg-muted rounded border border-border space-y-2">
      <p className="text-xs text-muted-foreground">Variable reference:</p>
      <div className="flex items-center gap-2">
        <code className="text-xs bg-background px-2 py-1 rounded flex-1 font-mono">
          {reference}
        </code>
        <Button
          size="sm"
          variant="ghost"
          onClick={() => {
            navigator.clipboard.writeText(reference);
            onCopy?.(reference);
          }}
          data-testid="button-copy-reference"
        >
          Copy
        </Button>
      </div>
    </div>
  );
}
