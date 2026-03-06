"use client";

import { useCallback, useRef, useState } from "react";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Zap } from "lucide-react";
import type { AvailableDataField } from "@/components/flow/types";
import { cn } from "@/lib/utils";

const FORMULA_SNIPPET_GROUPS = [
  {
    group: "String",
    items: [
      { label: "concat", body: "concat(ctx.contact.first_name, \" \", ctx.contact.last_name)" },
      { label: "upper", body: "upper(ctx.contact.city)" },
      { label: "lower", body: "lower(ctx.contact.email)" },
      { label: "trim", body: "trim(ctx.contact.first_name)" },
      { label: "replace", body: "replace(ctx.contact.phone, \"-\", \"\")" },
      { label: "substring", body: "substring(ctx.contact.phone, 0, 3)" },
      { label: "length", body: "length(ctx.contact.first_name)" },
      { label: "split", body: "split(ctx.contact.full_name, \" \")" },
    ],
  },
  {
    group: "Numeric",
    items: [
      { label: "round", body: "round(ctx.order.total)" },
      { label: "floor", body: "floor(ctx.order.total)" },
      { label: "ceil", body: "ceil(ctx.order.total)" },
      { label: "abs", body: "abs(ctx.balance.delta)" },
      { label: "min", body: "min(ctx.metrics.current, ctx.metrics.previous)" },
      { label: "max", body: "max(ctx.metrics.current, ctx.metrics.previous)" },
      { label: "sum", body: "sum(ctx.metrics.value_a, ctx.metrics.value_b, ctx.metrics.value_c)" },
    ],
  },
  {
    group: "Date/Time",
    items: [
      { label: "now", body: "now()" },
      { label: "today", body: "today()" },
      { label: "date_add", body: "date_add(today(), 7, \"days\")" },
      { label: "date_diff", body: "date_diff(now(), ctx.contact.created_at, \"days\")" },
      { label: "format_date", body: "format_date(today(), \"%Y-%m-%d\")" },
      { label: "parse_date", body: "parse_date(ctx.contact.last_seen, \"%Y-%m-%d\")" },
    ],
  },
  {
    group: "Logic",
    items: [
      { label: "if_else", body: "if_else(is_empty(ctx.contact.phone), \"missing\", \"ok\")" },
      { label: "coalesce", body: "coalesce(ctx.contact.first_name, \"friend\")" },
      { label: "is_null", body: "is_null(ctx.contact.last_seen)" },
      { label: "is_empty", body: "is_empty(ctx.contact.email)" },
    ],
  },
  {
    group: "Utility",
    items: [
      { label: "path", body: "path(input.body, \"contact.email\")" },
      { label: "int", body: "int(ctx.contact.score)" },
      { label: "float", body: "float(ctx.contact.score)" },
      { label: "str", body: "str(ctx.contact.id)" },
      { label: "len", body: "len(ctx.contact.tags)" },
      { label: "bool", body: "bool(ctx.contact.active)" },
    ],
  },
] as const;

export interface FormulaAwareStringInputProps {
  value: string;
  onChange: (value: string) => void;
  availableData?: AvailableDataField[];
  singleLine?: boolean;
  placeholderTemplate?: string;
  placeholderFormula?: string;
  id?: string;
  error?: string;
  className?: string;
  "data-testid"?: string;
}

function inferMode(value: string): "template" | "formula" {
  const raw = String(value ?? "").trim();
  if (raw.startsWith("{{") && raw.endsWith("}}") && raw.length >= 4) return "template";
  return "formula";
}

function getFormulaBody(value: string): string {
  const raw = String(value ?? "").trim();
  if (raw.startsWith("=") && !raw.startsWith("==")) {
    const idx = raw.indexOf("=");
    return idx >= 0 ? raw.slice(idx + 1) : "";
  }
  if (raw.startsWith("{{") && raw.endsWith("}}") && raw.length >= 4) {
    return raw.slice(2, -2).trim();
  }
  return raw;
}

export function FormulaAwareStringInput({
  value,
  onChange,
  availableData = [],
  singleLine = false,
  placeholderTemplate = "{{ctx.contact.first_name}}",
  placeholderFormula = "coalesce(ctx.contact.first_name, \"friend\")",
  id,
  error,
  className,
  "data-testid": dataTestId,
}: FormulaAwareStringInputProps) {
  const [modeOverride, setModeOverride] = useState<"template" | "formula" | null>(null);
  const [openFormulaBuilder, setOpenFormulaBuilder] = useState(false);
  const [openFieldPicker, setOpenFieldPicker] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const selectionRef = useRef<{ start: number; end: number } | null>(null);

  const mode = modeOverride ?? inferMode(value);
  const displayValue = mode === "formula" ? getFormulaBody(value) : value;
  const setDisplayValue = useCallback(
    (next: string, isFormula: boolean) => {
      if (isFormula) {
        const t = next.trim();
        const full = t.length > 0 ? (t.startsWith("=") ? t : `=${t}`) : "";
        onChange(full);
      } else {
        onChange(next);
      }
    },
    [onChange]
  );

  const validateLightweight = useCallback((isFormula: boolean, v: string): string | null => {
    const trimmed = String(v ?? "").trim();
    if (isFormula) {
      if (!trimmed) return null;
      if (!v.startsWith("=")) return "Formula expects value starting with '='.";
      if (trimmed === "=") return "Formula cannot be empty after '='.";
      if (trimmed.startsWith("==")) return "Use a single '='. For literals use =\"text\".";
    }
    if (!isFormula && trimmed.startsWith("{{") && !trimmed.endsWith("}}")) {
      return "Close template with '}}'.";
    }
    return null;
  }, []);

  const commitFormulaBody = useCallback(
    (body: string) => {
      const t = body.trim();
      const full = t.length > 0 ? (t.startsWith("=") ? t : `=${t}`) : "";
      const err = validateLightweight(true, full);
      setDisplayValue(t.length > 0 ? full : "", true);
      return err;
    },
    [setDisplayValue, validateLightweight]
  );

  const restoreSelection = useCallback((start: number, end: number = start) => {
    selectionRef.current = { start, end };
    setTimeout(() => {
      const el = textareaRef.current ?? inputRef.current;
      if (!el) return;
      try {
        el.focus();
        el.setSelectionRange(start, end);
      } catch {
        /* ignore */
      }
    }, 0);
  }, []);

  const insertAtCursor = useCallback(
    (token: string) => {
      const body = getFormulaBody(value);
      const { start, end } = selectionRef.current ?? { start: body.length, end: body.length };
      const nextBody = `${body.slice(0, start)}${token}${body.slice(end)}`;
      commitFormulaBody(nextBody);
      restoreSelection(start + token.length, start + token.length);
    },
    [value, commitFormulaBody, restoreSelection]
  );

  const applyFunctionTemplate = useCallback(
    (templateBody: string) => {
      commitFormulaBody(templateBody);
      const openIdx = templateBody.indexOf("(");
      const closeIdx = templateBody.lastIndexOf(")");
      if (openIdx < 0 || closeIdx <= openIdx) {
        restoreSelection(templateBody.length, templateBody.length);
        return;
      }
      const argsText = templateBody.slice(openIdx + 1, closeIdx);
      if (!argsText.trim()) {
        restoreSelection(openIdx + 1, openIdx + 1);
        return;
      }
      const firstComma = argsText.indexOf(",");
      const argStart = openIdx + 1;
      const argEnd = firstComma >= 0 ? openIdx + 1 + firstComma : closeIdx;
      restoreSelection(argStart, argEnd);
    },
    [commitFormulaBody, restoreSelection]
  );

  const switchMode = useCallback(
    (nextMode: "template" | "formula") => {
      setModeOverride(nextMode);
      const current = String(value ?? "").trim();
      if (nextMode === "formula") {
        if (!current) {
          onChange("");
          setOpenFormulaBuilder(true);
          return;
        }
        if (current.startsWith("{{") && current.endsWith("}}") && current.length >= 4) {
          const inner = current.slice(2, -2).trim();
          onChange(inner ? `=${inner}` : "");
        } else if (current.startsWith("==")) {
          onChange(`=${current.slice(2)}`);
        } else if (!current.startsWith("=")) {
          const escaped = current.replace(/\\/g, "\\\\").replace(/"/g, '\\"');
          onChange(`="${escaped}"`);
        }
        setOpenFormulaBuilder(true);
      } else {
        if (current.startsWith("=") && !current.startsWith("==")) {
          const body = current.slice(1).trim();
          if (/^(ctx(\.[A-Za-z0-9_-]+)*|input\.body(\.[A-Za-z0-9_-]+)*|nodes\.[A-Za-z0-9_-]+\.output(\.[A-Za-z0-9_-]+)*|config(\.[A-Za-z0-9_-]+)*)$/.test(body)) {
            onChange(`{{${body}}}`);
          }
        }
      }
    },
    [value, onChange]
  );

  const handleDataFieldSelect = useCallback(
    (fieldKey: string) => {
      if (mode === "formula") {
        insertAtCursor(fieldKey);
        setOpenFieldPicker(false);
      } else {
        onChange(`{{${fieldKey}}}`);
        setOpenFieldPicker(false);
      }
    },
    [mode, insertAtCursor, onChange]
  );

  const saveSelection = useCallback(() => {
    const el = textareaRef.current ?? inputRef.current;
    if (el) {
      selectionRef.current = { start: el.selectionStart ?? 0, end: el.selectionEnd ?? 0 };
    }
  }, []);

  return (
    <div className={cn("flex flex-col gap-2 flex-1 min-w-0", className)}>
      {/* Buttons row (Template, Formula, Select data field) */}
      <div className="flex items-center gap-1 flex-wrap shrink-0">
        <Button
          type="button"
          size="sm"
          variant={mode === "template" ? "default" : "outline"}
          className="h-6 px-2 text-[10px] uppercase"
          onClick={() => switchMode("template")}
          data-testid={dataTestId ? `${dataTestId}-template` : undefined}
        >
          template
        </Button>
        <Popover open={openFormulaBuilder} onOpenChange={setOpenFormulaBuilder}>
          <PopoverTrigger asChild>
            <Button
              type="button"
              size="sm"
              variant={mode === "formula" ? "default" : "outline"}
              className="h-6 px-2"
              onClick={() => switchMode("formula")}
              title="Open formula builder"
              data-testid={dataTestId ? `${dataTestId}-formula` : undefined}
            >
              <Zap className="h-3.5 w-3.5" />
              <span className="sr-only">Formula builder</span>
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-[420px] p-3 space-y-3" align="end">
            <div className="space-y-1">
              <p className="text-xs font-medium">Formula Builder</p>
              <p className="text-[11px] text-muted-foreground">
                Formula always starts with <code>=</code>. Edit the body after it.
              </p>
            </div>
            <div className="space-y-1">
              <Label className="text-[11px] uppercase text-muted-foreground">Formula body</Label>
              <div className="flex items-start gap-1">
                <code className="h-8 min-w-8 rounded border bg-muted/40 px-2 flex items-center justify-center text-xs font-mono">=</code>
                <Textarea
                  ref={textareaRef}
                  value={getFormulaBody(value)}
                  onChange={(e) => {
                    saveSelection();
                    const body = e.target.value.trim();
                    const full = body ? (body.startsWith("=") ? body : `=${body}`) : "";
                    onChange(full);
                  }}
                  onSelect={saveSelection}
                  onClick={saveSelection}
                  onKeyUp={saveSelection}
                  placeholder={placeholderFormula}
                  rows={3}
                  className="text-xs font-mono flex-1"
                  data-testid={dataTestId ? `${dataTestId}-formula-textarea` : undefined}
                />
              </div>
            </div>
            <div className="space-y-2">
              <Label className="text-[11px] uppercase text-muted-foreground">Functions</Label>
              {FORMULA_SNIPPET_GROUPS.map((group) => (
                <div key={group.group} className="space-y-1">
                  <p className="text-[10px] uppercase text-muted-foreground">{group.group}</p>
                  <div className="flex flex-wrap gap-1">
                    {group.items.map((snippet) => (
                      <Button
                        key={`${group.group}-${snippet.label}`}
                        type="button"
                        variant="outline"
                        size="sm"
                        className="h-6 px-2 text-[10px]"
                        onClick={() => applyFunctionTemplate(snippet.body)}
                      >
                        {snippet.label}
                      </Button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
            {availableData.length > 0 && (
              <div className="space-y-1">
                <Label className="text-[11px] uppercase text-muted-foreground">Available fields</Label>
                <p className="text-[10px] text-muted-foreground">
                  Click a field to insert at cursor. For literal text use <code>{'="your text"'}</code>.
                </p>
                <ScrollArea className="h-[120px] rounded border p-1">
                  <div className="space-y-1">
                    {availableData.slice(0, 40).map((field) => (
                      <Button
                        key={field.key}
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="h-6 w-full justify-start px-2 text-[10px] font-mono"
                        onClick={() => insertAtCursor(field.key)}
                      >
                        {field.key}
                      </Button>
                    ))}
                  </div>
                </ScrollArea>
              </div>
            )}
          </PopoverContent>
        </Popover>
        {availableData.length > 0 && mode !== "formula" && (
          <Popover open={openFieldPicker} onOpenChange={setOpenFieldPicker}>
            <PopoverTrigger asChild>
              <Button
                variant="outline"
                size="sm"
                className="w-[200px] justify-between text-sm shrink-0"
                data-testid={dataTestId ? `${dataTestId}-pick-field` : undefined}
              >
                <span className="truncate">Select data field</span>
              </Button>
            </PopoverTrigger>
            <PopoverContent
              className="w-[300px] p-0 max-h-[min(320px,50vh)] flex flex-col"
              align="end"
              side="top"
              sideOffset={6}
              collisionPadding={12}
              avoidCollisions
            >
              <Command className="flex flex-col max-h-full">
                <CommandInput placeholder="Search data fields..." className="text-sm shrink-0" />
                <CommandList className="max-h-52 overflow-auto shrink min-h-0">
                  <CommandEmpty className="text-sm">No data fields found.</CommandEmpty>
                  <CommandGroup>
                    {availableData.map((field) => (
                      <CommandItem
                        key={field.key}
                        value={field.key}
                        onSelect={() => handleDataFieldSelect(field.key)}
                        className="text-xs font-mono"
                      >
                        {field.key}
                      </CommandItem>
                    ))}
                  </CommandGroup>
                </CommandList>
              </Command>
            </PopoverContent>
          </Popover>
        )}
      </div>
      {/* Input row below buttons (full width) */}
      <div className="flex items-stretch gap-1 flex-1 min-w-0">
        {mode === "formula" ? (
          <>
            <code className="h-9 min-w-9 rounded border bg-muted/40 px-2 flex items-center justify-center text-sm font-mono shrink-0">=</code>
            {singleLine ? (
              <Input
                ref={inputRef}
                id={id}
                value={displayValue}
                onChange={(e) => {
                  saveSelection();
                  const next = e.target.value.trim();
                  onChange(next ? (next.startsWith("=") ? next : `=${next}`) : "");
                }}
                onSelect={saveSelection}
                onClick={saveSelection}
                onKeyUp={saveSelection}
                placeholder={placeholderFormula}
                className="text-sm flex-1 font-mono min-w-0"
                data-testid={dataTestId}
              />
            ) : (
              <Textarea
                ref={textareaRef}
                id={id}
                value={displayValue}
                onChange={(e) => {
                  saveSelection();
                  const next = e.target.value.trim();
                  onChange(next ? (next.startsWith("=") ? next : `=${next}`) : "");
                }}
                onSelect={saveSelection}
                onClick={saveSelection}
                onKeyUp={saveSelection}
                placeholder={placeholderFormula}
                rows={2}
                className="text-sm flex-1 font-mono min-w-0"
                data-testid={dataTestId}
              />
            )}
          </>
        ) : (
          singleLine ? (
            <Input
              id={id}
              value={displayValue}
              onChange={(e) => onChange(e.target.value)}
              placeholder={placeholderTemplate}
              className="text-sm flex-1 min-w-0"
              data-testid={dataTestId}
            />
          ) : (
            <Textarea
              id={id}
              value={displayValue}
              onChange={(e) => onChange(e.target.value)}
              placeholder={placeholderTemplate}
              rows={2}
              className="text-sm flex-1 min-w-0"
              data-testid={dataTestId}
            />
          )
        )}
      </div>
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  );
}
