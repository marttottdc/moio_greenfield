import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Check, ChevronsUpDown, Loader2, Pencil, X, CalendarDays, CheckSquare, Briefcase } from "lucide-react";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Calendar } from "@/components/ui/calendar";
import { ScrollArea } from "@/components/ui/scroll-area";
import { moioUsersApi } from "@/lib/api";
import { useToast } from "@/hooks/use-toast";
import { ApiError, fetchJson, queryClient } from "@/lib/queryClient";
import { apiV1 } from "@/lib/api";
import { captureApi } from "@/lib/capture/captureApi";
import type {
  CaptureEntry,
  CaptureVisibility,
  ClassifySyncResponse,
  ConfirmedActivityItem,
  ProposedActivity,
} from "@/lib/capture/types";

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
  const kind = proposed.kind ?? proposed.type ?? "activity";
  const title = proposed.title ?? proposed.description ?? "—";
  const due = (proposed.due_at ?? proposed.due_date) ? ` · Due ${proposed.due_at ?? proposed.due_date}` : "";
  const when =
    proposed.start_at && proposed.end_at
      ? ` · ${proposed.start_at} – ${proposed.end_at}`
      : "";
  const needsTime = proposed.needs_time_confirmation ? " (pick time)" : "";
  return `${kind}: ${title}${due}${when}${needsTime}`;
}

function toConfirmedItem(item: ProposedActivity): ConfirmedActivityItem {
  const rawKind = (item.kind ?? item.type ?? "event") as string;
  const kind = ["task", "event", "deal"].includes(rawKind) ? (rawKind as "task" | "event" | "deal") : "event";
  return {
    kind,
    title: (item.title ?? "Activity").toString(),
    description: item.description?.toString(),
    due_at: (item.due_at ?? item.due_date)?.toString(),
    start_at: item.start_at?.toString(),
    end_at: item.end_at?.toString(),
    status: item.status as "planned" | "completed" | undefined,
    location: item.location?.toString(),
    attendees: Array.isArray(item.attendees) ? item.attendees.map(String) : undefined,
    owner_id: (item as any).owner_id ?? null,
    proposed_value: (item as any).proposed_value,
    proposed_currency: (item as any).proposed_currency?.toString(),
  };
}

function formatActivityDate(ts?: string): string {
  if (!ts) return "";
  try {
    const d = new Date(ts);
    return d.toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "numeric",
      minute: "2-digit",
      hour12: true,
    });
  } catch {
    return ts;
  }
}

/** Convert ISO string to datetime-local input value (YYYY-MM-DDTHH:mm). */
function toDatetimeLocalValue(iso?: string): string {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    if (isNaN(d.getTime())) return "";
    const pad = (n: number) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  } catch {
    return "";
  }
}

/** Convert datetime-local value to ISO string for API (YYYY-MM-DDTHH:mm:00). */
function fromDatetimeLocalValue(local: string): string {
  if (!local || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(local)) return "";
  return local.length >= 19 ? local : `${local}:00`;
}

async function fetchUserLocation(): Promise<string | null> {
  if (!navigator?.geolocation) return null;
  return new Promise((resolve) => {
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        const { latitude, longitude } = pos.coords;
        try {
          const res = await fetch(
            `https://nominatim.openstreetmap.org/reverse?format=json&lat=${latitude}&lon=${longitude}`,
            { headers: { "Accept-Language": "es", "User-Agent": "MoioCRM/1.0" } }
          );
          const data = await res.json();
          resolve(data?.display_name ?? `${latitude}, ${longitude}`);
        } catch {
          resolve(`${latitude}, ${longitude}`);
        }
      },
      () => resolve(null)
    );
  });
}

function SuggestedActivityEditSheet({
  open,
  onOpenChange,
  item,
  users,
  userGeoAddress,
  onSave,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  item: ConfirmedActivityItem | null;
  users: { id: number | string; email?: string; first_name?: string; last_name?: string; full_name?: string }[];
  userGeoAddress: string | null;
  onSave: (edited: ConfirmedActivityItem) => void;
}) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [dueAt, setDueAt] = useState("");
  const [startAt, setStartAt] = useState("");
  const [endAt, setEndAt] = useState("");
  const [ownerId, setOwnerId] = useState<string | null>(null);

  const [status, setStatus] = useState<"planned" | "completed">("planned");

  useEffect(() => {
    if (item) {
      setTitle(item.title || "");
      setDescription(item.description || "");
      setDueAt(toDatetimeLocalValue(item.due_at));
      setStartAt(toDatetimeLocalValue(item.start_at));
      setEndAt(toDatetimeLocalValue(item.end_at));
      setOwnerId(item.owner_id ?? null);
      setStatus((item.status as "planned" | "completed") || "planned");
    }
  }, [item]);

  const handleSave = () => {
    if (!item) return;
    const isEvent = (item.kind ?? "event") === "event";
    const locationValue =
      ((item as any).location as string)?.trim() ||
      (isEvent && userGeoAddress ? userGeoAddress : undefined);
    onSave({
      ...item,
      title: title.trim() || item.title,
      description: description.trim() || undefined,
      due_at: dueAt ? fromDatetimeLocalValue(dueAt) : undefined,
      start_at: startAt ? fromDatetimeLocalValue(startAt) : undefined,
      end_at: endAt ? fromDatetimeLocalValue(endAt) : undefined,
      owner_id: ownerId || undefined,
      location: locationValue,
      status,
    });
    onOpenChange(false);
  };

  if (!item) return null;

  const kind = (item.kind ?? "event") as string;
  const isTask = kind === "task";
  const isEvent = kind === "event";

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="sm:max-w-md max-md:w-full overflow-y-auto" side="right">
        <SheetHeader>
          <SheetTitle>Editar actividad</SheetTitle>
        </SheetHeader>
        <ScrollArea className="h-[calc(100vh-8rem)] pr-4">
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label>Título</Label>
              <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Título" />
            </div>
            {isEvent && (
              <div className="space-y-2">
                <Label>Estado</Label>
                <Select value={status} onValueChange={(v) => setStatus(v as "planned" | "completed")}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="planned">Planificado</SelectItem>
                    <SelectItem value="completed">Completado</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            )}
            <div className="space-y-2">
              <Label>Descripción</Label>
              <Textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Descripción"
                rows={3}
              />
            </div>
            {isTask && (
              <div className="space-y-2">
                <Label>Responsable</Label>
                <Select
                  value={ownerId ?? "none"}
                  onValueChange={(v) => setOwnerId(v === "none" ? null : v)}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Seleccionar responsable" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">Sin asignar</SelectItem>
                    {users.map((u) => (
                      <SelectItem key={String(u.id)} value={String(u.id)}>
                        {u.full_name || `${u.first_name || ""} ${u.last_name || ""}`.trim() || u.email || String(u.id)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
            {isTask && (
              <div className="space-y-2">
                <Label>Fecha de vencimiento</Label>
                <Input
                  type="datetime-local"
                  value={dueAt}
                  onChange={(e) => setDueAt(e.target.value)}
                />
              </div>
            )}
            {isEvent && (
              <>
                <div className="space-y-2">
                  <Label>Inicio</Label>
                  <Input
                    type="datetime-local"
                    value={startAt}
                    onChange={(e) => setStartAt(e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label>Fin</Label>
                  <Input
                    type="datetime-local"
                    value={endAt}
                    onChange={(e) => setEndAt(e.target.value)}
                  />
                </div>
              </>
            )}
          </div>
        </ScrollArea>
        <div className="flex gap-2 mt-4">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancelar
          </Button>
          <Button onClick={handleSave}>Guardar</Button>
        </div>
      </SheetContent>
    </Sheet>
  );
}

export function ReportActivityModal(props: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated?: (entry: CaptureEntry) => void;
  /** Ubicación del usuario proporcionada por la app (p.ej. perfil, preferencias). Evita usar geolocalización del navegador para no conflictuar con extensiones como location-spoofing. */
  userGeoAddress?: string | null;
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
  const [editableItems, setEditableItems] = useState<ConfirmedActivityItem[]>([]);
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [cardStates, setCardStates] = useState<Record<number, "pending" | "created" | "rejected">>({});
  /** Usamos la ubicación pasada por la app; no llamamos a navigator.geolocation aquí para evitar conflictos con extensiones (ej. location-spoofing → resolve is not defined). */
  const userGeoAddress = props.userGeoAddress ?? null;

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

  const usersQuery = useQuery({
    queryKey: [apiV1("/users/"), "report-activity-owners"],
    queryFn: () => moioUsersApi.list(),
    enabled: props.open && !!classifyResult,
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

  const suggestedItems = useMemo(() => {
    if (!classifyResult) return [];
    const raw =
      classifyResult.suggested_activities ??
      classifyResult.proposed_activities ??
      (classifyResult.proposed_activity ? [classifyResult.proposed_activity] : []);
    return raw.map(toConfirmedItem);
  }, [classifyResult]);

  useEffect(() => {
    if (classifyResult && suggestedItems.length > 0) {
      setEditableItems(suggestedItems);
    }
  }, [classifyResult?.entry?.id, suggestedItems]);

  const displayItems = editableItems.length > 0 ? editableItems : suggestedItems;

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
      setEditableItems([]);
      setEditingIndex(null);
      setCardStates({});
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

  const applySingleActivity = async (idx: number) => {
    const entryId = classifyResult?.entry?.id;
    if (!entryId) return;
    let item = displayItems[idx];
    if (!item) return;
    if (cardStates[idx] === "created") return;

    const kind = (item.kind ?? "event") as string;
    if (kind === "event" && !item.location && userGeoAddress) {
      item = { ...item, location: userGeoAddress };
    }

    setIsApplying(true);
    try {
      const result = await captureApi.applySync(entryId, {
        confirmed_activities: [item],
      });
      if ((result.applied_refs?.length ?? 0) > 0) {
        setCardStates((prev) => ({ ...prev, [idx]: "created" }));
        toast({ title: "Activity created", description: "Activity was created successfully." });
        queryClient.invalidateQueries({ queryKey: [apiV1("/capture/entries/")] });
        queryClient.invalidateQueries({ queryKey: ["timeline"] });
        const syntheticEntry: CaptureEntry = {
          id: entryId,
          status: "applied",
          applied_refs: result.applied_refs,
          raw_text: rawText.trim(),
          anchor_model: anchorModelFor(anchorType),
          anchor_id: anchorId,
        };
        props.onCreated?.(syntheticEntry);
      } else {
        toast({ title: "Could not create", description: "Add dates/times for events or check required fields.", variant: "destructive" });
      }
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

  const rejectActivity = (idx: number) => {
    setCardStates((prev) => ({ ...prev, [idx]: "rejected" }));
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
      <DialogContent className="sm:max-w-2xl max-md:w-[95vw]">
        <DialogHeader>
          <DialogTitle>Log or plan an activity</DialogTitle>
          <DialogDescription>
            What did you do or what’s next? One line is enough. We’ll link it to a deal or contact and add it to your timeline.
          </DialogDescription>
        </DialogHeader>

        {classifyResult ? (
          <div className="space-y-4 py-2">
            <p className="text-sm font-medium text-muted-foreground">
              Suggested activities (click to edit, then create or reject)
            </p>
            <div className="grid gap-3">
              {displayItems.map((item, idx) => {
                const state = cardStates[idx] ?? "pending";
                const kind = (item.kind ?? "event") as string;
                const Icon =
                  kind === "task" ? CheckSquare : kind === "deal" ? Briefcase : CalendarDays;
                const ownerUser =
                  item.owner_id && usersQuery.data
                    ? usersQuery.data.find((u) => String(u.id) === String(item.owner_id))
                    : null;
                const ownerLabel = ownerUser
                  ? (ownerUser.full_name || `${ownerUser.first_name || ""} ${ownerUser.last_name || ""}`.trim() || ownerUser.email)
                  : null;
                const statusLabel = item.status === "completed" ? "Completado" : "Planificado";
                return (
                  <Card
                    key={idx}
                    className={
                      state === "rejected"
                        ? "opacity-60 bg-muted/30"
                        : "cursor-pointer hover:bg-muted/50 transition-colors"
                    }
                    onClick={() => state === "pending" && setEditingIndex(idx)}
                  >
                    <CardHeader className="pb-2 pt-3 px-4">
                      <div className="flex items-start gap-3">
                        <Icon className="h-4 w-4 text-muted-foreground shrink-0 mt-0.5" />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <p className="font-medium truncate">{item.title}</p>
                            {state === "created" && (
                              <span className="text-xs font-medium text-green-600 dark:text-green-400">Creado</span>
                            )}
                            {state === "rejected" && (
                              <span className="text-xs font-medium text-muted-foreground">Rechazado</span>
                            )}
                            {kind === "event" && state === "pending" && (
                              <span className="text-xs text-muted-foreground">· {statusLabel}</span>
                            )}
                          </div>
                          <div className="flex flex-wrap items-center gap-2 mt-1 text-xs text-muted-foreground">
                            <span className="capitalize">{kind}</span>
                            {item.due_at && (
                              <>
                                <span>·</span>
                                <span>Due {formatActivityDate(item.due_at)}</span>
                              </>
                            )}
                            {item.start_at && item.end_at && (
                              <>
                                <span>·</span>
                                <span>
                                  {formatActivityDate(item.start_at)} – {formatActivityDate(item.end_at)}
                                </span>
                              </>
                            )}
                            {!item.start_at && !item.end_at && kind === "event" && item.status === "planned" && (
                              <span className="text-muted-foreground">· Sin fecha definida</span>
                            )}
                            {ownerLabel && kind !== "event" && (
                              <>
                                <span>·</span>
                                <span>Responsable: {ownerLabel}</span>
                              </>
                            )}
                          </div>
                          {item.description && (
                            <p className="text-xs text-muted-foreground mt-1 line-clamp-2">{item.description}</p>
                          )}
                        </div>
                        {state === "pending" && (
                          <div className="flex items-center gap-1 shrink-0" onClick={(e) => e.stopPropagation()}>
                            <Button
                              size="sm"
                              variant="ghost"
                              className="h-8 w-8 p-0 text-destructive hover:text-destructive hover:bg-destructive/10"
                              onClick={() => rejectActivity(idx)}
                              title="Rechazar"
                            >
                              <X className="h-4 w-4" />
                            </Button>
                            <Button
                              size="sm"
                              variant="default"
                              className="h-8"
                              onClick={() => applySingleActivity(idx)}
                              disabled={isApplying}
                              title="Crear actividad"
                            >
                              {isApplying ? <Loader2 className="h-4 w-4 animate-spin" /> : "Crear"}
                            </Button>
                            <Button
                              size="sm"
                              variant="ghost"
                              className="h-8 w-8 p-0"
                              onClick={(e) => {
                                e.stopPropagation();
                                setEditingIndex(idx);
                              }}
                              title="Editar"
                            >
                              <Pencil className="h-3.5 w-3.5" />
                            </Button>
                          </div>
                        )}
                        {state !== "pending" && <Pencil className="h-3.5 w-3.5 text-muted-foreground shrink-0 opacity-50" />}
                      </div>
                    </CardHeader>
                  </Card>
                );
              })}
            </div>
            <SuggestedActivityEditSheet
              open={editingIndex !== null}
              onOpenChange={(open) => !open && setEditingIndex(null)}
              item={editingIndex !== null ? displayItems[editingIndex] : null}
              users={usersQuery.data ?? []}
              userGeoAddress={userGeoAddress}
              onSave={(edited) => {
                if (editingIndex !== null) {
                  setEditableItems((prev) => {
                    const next = [...prev];
                    next[editingIndex] = edited;
                    return next;
                  });
                  setEditingIndex(null);
                }
              }}
            />
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
            <Button
              variant="outline"
              onClick={() => setClassifyResult(null)}
              disabled={isApplying}
              data-testid="button-capture-back"
            >
              Cambiar texto
            </Button>
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

