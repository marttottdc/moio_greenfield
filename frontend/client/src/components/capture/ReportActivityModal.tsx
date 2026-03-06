import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Check, ChevronsUpDown, Loader2 } from "lucide-react";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { useToast } from "@/hooks/use-toast";
import { ApiError, fetchJson, queryClient } from "@/lib/queryClient";
import { apiV1 } from "@/lib/api";
import { captureApi } from "@/lib/capture/captureApi";
import type { CaptureEntry, CaptureVisibility, ClassifySyncResponse, ProposedActivity } from "@/lib/capture/types";

type AnchorType = "deal" | "contact";

type DealLite = { id: string; title?: string; contact_name?: string | null; value?: number | string | null; currency?: string | null };
type ContactLite = { id: string; name?: string; email?: string | null; phone?: string | null; company?: string | null };

function normalizeArray<T>(data: any, keys: string[] = []): T[] {
  if (!data) return [];
  if (Array.isArray(data)) return data as T[];
  if (typeof data !== "object") return [];
  for (const k of keys) {
    if (Array.isArray((data as any)[k])) return (data as any)[k] as T[];
  }
  if (Array.isArray((data as any).results)) return (data as any).results as T[];
  if (Array.isArray((data as any).items)) return (data as any).items as T[];
  return [];
}

function formatProposedActivity(proposed?: ProposedActivity | null): string {
  if (!proposed || typeof proposed !== "object") return "Activity will be created.";
  const type = proposed.type ?? "activity";
  const title = proposed.title ?? proposed.description ?? "—";
  const due = proposed.due_date ? ` · Due ${proposed.due_date}` : "";
  return `${type}: ${title}${due}`;
}

export function ReportActivityModal(props: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated?: (entry: CaptureEntry) => void;
}) {
  const { toast } = useToast();
  const [anchorType, setAnchorType] = useState<AnchorType>("deal");
  const [anchorId, setAnchorId] = useState<string>("");
  const [anchorPopoverOpen, setAnchorPopoverOpen] = useState(false);

  const [rawText, setRawText] = useState("");
  const [visibility, setVisibility] = useState<CaptureVisibility>("internal");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [classifyResult, setClassifyResult] = useState<ClassifySyncResponse | null>(null);
  const [isApplying, setIsApplying] = useState(false);

  const dealsQuery = useQuery({
    queryKey: [apiV1("/crm/deals/"), "report-activity"],
    queryFn: () => fetchJson<any>(apiV1("/crm/deals/")),
    enabled: props.open && anchorType === "deal",
    retry: false,
  });

  const contactsQuery = useQuery({
    queryKey: [apiV1("/crm/contacts/"), "report-activity", ""],
    queryFn: () => fetchJson<any>(apiV1("/crm/contacts"), { page: 1, page_size: 50 }),
    enabled: props.open && anchorType === "contact",
    retry: false,
  });

  const deals = useMemo(() => normalizeArray<DealLite>(dealsQuery.data, ["deals"]), [dealsQuery.data]);
  const contacts = useMemo(() => {
    const arr = normalizeArray<ContactLite>(contactsQuery.data, ["contacts"]);
    return arr;
  }, [contactsQuery.data]);

  const selectedAnchorLabel = useMemo(() => {
    if (!anchorId) return "";
    if (anchorType === "deal") {
      const deal = deals.find((d) => d.id === anchorId);
      return deal?.title ? `${deal.title} (${deal.id})` : anchorId;
    }
    const contact = contacts.find((c) => c.id === anchorId);
    return contact?.name ? `${contact.name} (${contact.id})` : anchorId;
  }, [anchorId, anchorType, deals, contacts]);

  const resetIfClosed = (open: boolean) => {
    if (!open) {
      setAnchorId("");
      setAnchorPopoverOpen(false);
      setRawText("");
      setVisibility("internal");
      setAnchorType("deal");
      setIsSubmitting(false);
      setClassifyResult(null);
      setIsApplying(false);
    }
  };

  const anchorModelFor = (type: AnchorType): "crm.deal" | "crm.contact" => {
    // moio_platform (a8da10d): CaptureAnchorModel = crm.deal | crm.contact | crm.client
    return type === "deal" ? "crm.deal" : "crm.contact";
  };

  const submitClassify = async () => {
    if (!anchorId) {
      toast({ title: "Select an anchor", description: "Choose a Deal or Contact.", variant: "destructive" });
      return;
    }
    if (!rawText.trim()) {
      toast({ title: "Add some text", description: "Write a note to capture.", variant: "destructive" });
      return;
    }

    setIsSubmitting(true);
    setClassifyResult(null);
    try {
      const result = await captureApi.classifySync({
        raw_text: rawText.trim(),
        anchor_model: anchorModelFor(anchorType),
        anchor_id: anchorId,
      });
      setClassifyResult(result);
    } catch (err: any) {
      const allowed = (() => {
        if (!(err instanceof ApiError)) return undefined;
        const field = err.fields?.anchor_model;
        if (Array.isArray(field) && field.length > 0) return field.join(" ");
        try {
          const parsed = JSON.parse(err.body || "{}");
          const fromFields = parsed?.fields?.anchor_model;
          if (Array.isArray(fromFields) && fromFields.length > 0) return fromFields.join(" ");
          const detail = parsed?.detail || parsed?.message;
          return typeof detail === "string" ? detail : undefined;
        } catch {
          return undefined;
        }
      })();

      toast({
        title: "Classification failed",
        description: allowed ? `${err?.message || "Could not classify."} Allowed: ${allowed}` : (err?.message || "Could not classify."),
        variant: "destructive",
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  const confirmApply = async () => {
    const entryId = classifyResult?.entry?.id;
    if (!entryId) return;

    setIsApplying(true);
    try {
      const result = await captureApi.applySync(entryId);
      toast({ title: "Activity created", description: "Your note was applied successfully." });
      const syntheticEntry: CaptureEntry = {
        id: entryId,
        status: "applied",
        applied_refs: result.applied_refs,
        raw_text: rawText.trim(),
        anchor_model: anchorModelFor(anchorType),
        anchor_id: anchorId,
      };
      props.onCreated?.(syntheticEntry);
      queryClient.invalidateQueries({ queryKey: [apiV1("/capture/entries/")] });
      queryClient.invalidateQueries({ queryKey: ["timeline"] });
      props.onOpenChange(false);
      resetIfClosed(false);
    } catch (err: any) {
      toast({
        title: "Apply failed",
        description: err?.message || "Could not create activity.",
        variant: "destructive",
      });
    } finally {
      setIsApplying(false);
    }
  };

  const anchorItems = anchorType === "deal" ? deals : contacts;
  const isAnchorLoading = anchorType === "deal" ? dealsQuery.isLoading : contactsQuery.isLoading;
  const anchorEmptyLabel = anchorType === "deal" ? "No deals found." : "No contacts found.";

  return (
    <Dialog
      open={props.open}
      onOpenChange={(open) => {
        props.onOpenChange(open);
        resetIfClosed(open);
      }}
    >
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Log or plan an activity</DialogTitle>
          <DialogDescription>
            What did you do or what’s next? One line is enough. We’ll link it to a deal or contact and add it to your timeline.
          </DialogDescription>
        </DialogHeader>

        {classifyResult ? (
          <div className="space-y-4 py-2">
            <div className="rounded-lg border bg-muted/30 p-4">
              <p className="text-sm font-medium text-muted-foreground mb-1">We’ll create</p>
              <p className="text-sm">{formatProposedActivity(classifyResult.proposed_activity)}</p>
            </div>
            <p className="text-sm text-muted-foreground">This will appear in your timeline right away.</p>
          </div>
        ) : (
        <div className="space-y-4 py-2">
          <div className="space-y-2">
            <Label htmlFor="capture-raw">What did you do or plan?</Label>
            <Textarea
              id="capture-raw"
              value={rawText}
              onChange={(e) => setRawText(e.target.value)}
              placeholder="e.g. Call John tomorrow re: quote, Schedule demo Tuesday 3pm"
              className="min-h-[100px] resize-none"
              data-testid="textarea-capture-raw"
              autoFocus
            />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label>Link to</Label>
            <Select
              value={anchorType}
              onValueChange={(v) => {
                setAnchorType(v as AnchorType);
                setAnchorId("");
              }}
            >
              <SelectTrigger data-testid="select-anchor-type">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="deal">Deal</SelectItem>
                <SelectItem value="contact">Contact</SelectItem>
              </SelectContent>
            </Select>
            </div>

            <div className="space-y-2">
              <Label>{anchorType === "deal" ? "Deal" : "Contact"}</Label>
              <Popover open={anchorPopoverOpen} onOpenChange={setAnchorPopoverOpen}>
              <PopoverTrigger asChild>
                <Button
                  variant="outline"
                  role="combobox"
                  aria-expanded={anchorPopoverOpen}
                  className="w-full justify-between font-normal"
                  data-testid="button-anchor-combobox"
                >
                  {anchorId ? (
                    <span className="truncate">{selectedAnchorLabel}</span>
                  ) : (
                    <span className="text-muted-foreground">
                      {anchorType === "deal" ? "Select deal..." : "Select contact..."}
                    </span>
                  )}
                  <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-[360px] p-0" align="start">
                <Command>
                  <CommandInput placeholder={`Search ${anchorType === "deal" ? "deals" : "contacts"}...`} />
                  <CommandList>
                    <CommandEmpty>
                      {isAnchorLoading ? "Loading..." : anchorEmptyLabel}
                    </CommandEmpty>
                    <CommandGroup>
                      {anchorItems.map((item: any) => {
                        const id = String(item.id);
                        const label =
                          anchorType === "deal"
                            ? String((item as DealLite).title ?? id)
                            : String((item as ContactLite).name ?? id);
                        const sub =
                          anchorType === "deal"
                            ? (item as DealLite).contact_name ?? ""
                            : ((item as ContactLite).email ?? (item as ContactLite).phone ?? (item as ContactLite).company ?? "");

                        return (
                          <CommandItem
                            key={id}
                            value={`${label} ${id} ${sub}`}
                            onSelect={() => {
                              setAnchorId(id);
                              setAnchorPopoverOpen(false);
                            }}
                          >
                            <Check className={`mr-2 h-4 w-4 ${anchorId === id ? "opacity-100" : "opacity-0"}`} />
                            <div className="flex flex-col min-w-0">
                              <span className="truncate">{label}</span>
                              {(sub || "").trim() && (
                                <span className="text-xs text-muted-foreground truncate">{sub}</span>
                              )}
                            </div>
                          </CommandItem>
                        );
                      })}
                    </CommandGroup>
                  </CommandList>
                </Command>
              </PopoverContent>
            </Popover>
            </div>
          </div>

          <details className="text-sm">
            <summary className="text-muted-foreground cursor-pointer hover:text-foreground">Visibility</summary>
            <div className="mt-2">
              <Select value={visibility} onValueChange={(v) => setVisibility(v as CaptureVisibility)}>
                <SelectTrigger data-testid="select-capture-visibility" className="w-full max-w-[200px]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="internal">internal</SelectItem>
                  <SelectItem value="confidential">confidential</SelectItem>
                  <SelectItem value="restricted">restricted</SelectItem>
                  <SelectItem value="public">public</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </details>
        </div>
        )}

        <DialogFooter className="gap-2">
          {classifyResult ? (
            <>
              <Button
                variant="outline"
                onClick={() => setClassifyResult(null)}
                disabled={isApplying}
                data-testid="button-capture-back"
              >
                Edit
              </Button>
              <Button onClick={confirmApply} disabled={isApplying} data-testid="button-capture-confirm">
                {isApplying && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                Create activity
              </Button>
            </>
          ) : (
            <>
              <Button variant="outline" onClick={() => props.onOpenChange(false)} disabled={isSubmitting}>
                Cancel
              </Button>
              <Button onClick={submitClassify} disabled={isSubmitting} data-testid="button-save-capture">
                {isSubmitting && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                Next
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

