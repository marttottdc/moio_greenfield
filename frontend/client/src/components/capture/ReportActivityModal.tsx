import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Check, ChevronsUpDown, Loader2, Pencil, CalendarDays, CheckSquare, Briefcase, Send, Building2, User } from "lucide-react";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
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
import { ApiError, apiRequest, fetchJson, queryClient } from "@/lib/queryClient";
import { apiV1 } from "@/lib/api";
import { captureApi } from "@/lib/capture/captureApi";
import type {
  CaptureEntry,
  CaptureVisibility,
  ClassifySyncResponse,
  ConfirmedActivityItem,
  ProposedActivity,
} from "@/lib/capture/types";

type AnchorType = "contact" | "account";

type DealLite = { id: string; title?: string; contact_name?: string | null; value?: number | string | null; currency?: string | null };
type ContactLite = { id: string; name?: string; email?: string | null; phone?: string | null; company?: string | null };
type AccountLite = { id: string; name?: string; legal_name?: string | null; email?: string | null };

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
  const [anchorType, setAnchorType] = useState<AnchorType>("contact");
  const [anchorId, setAnchorId] = useState<string>("");
  const [secondaryAnchorId, setSecondaryAnchorId] = useState<string>("");
  const [createdSecondaryAnchorLabel, setCreatedSecondaryAnchorLabel] = useState<string | null>(null);
  const [dealId, setDealId] = useState<string>("");
  const [anchorPopoverOpen, setAnchorPopoverOpen] = useState(false);
  const [anchorSearch, setAnchorSearch] = useState("");
  const [debouncedAnchorSearch, setDebouncedAnchorSearch] = useState("");
  const [isCreatingAnchor, setIsCreatingAnchor] = useState(false);
  const [createdAnchorLabel, setCreatedAnchorLabel] = useState<string | null>(null);
  useEffect(() => {
    const t = setTimeout(() => setDebouncedAnchorSearch(anchorSearch), 200);
    return () => clearTimeout(t);
  }, [anchorSearch]);

  const [rawText, setRawText] = useState("");
  const [phase, setPhase] = useState<"input" | "link" | "classified">("input");
  const [visibility, setVisibility] = useState<CaptureVisibility>("internal");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [classifyResult, setClassifyResult] = useState<ClassifySyncResponse | null>(null);
  const [isApplying, setIsApplying] = useState(false);
  const [editableItems, setEditableItems] = useState<ConfirmedActivityItem[]>([]);
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [cardStates, setCardStates] = useState<Record<number, "pending" | "created" | "rejected">>({});
  /** Usamos la ubicación pasada por la app; no llamamos a navigator.geolocation aquí para evitar conflictos con extensiones (ej. location-spoofing → resolve is not defined). */
  const userGeoAddress = props.userGeoAddress ?? null;

  const contactsQuery = useQuery({
    queryKey: [apiV1("/crm/contacts/"), "report-activity", debouncedAnchorSearch],
    queryFn: () =>
      fetchJson<any>(apiV1("/crm/contacts/"), {
        page: 1,
        limit: 50,
        ...(debouncedAnchorSearch.trim() ? { search: debouncedAnchorSearch.trim() } : {}),
      }),
    enabled: props.open && anchorType === "contact",
    retry: false,
  });

  const accountsQuery = useQuery({
    queryKey: [apiV1("/crm/customers/"), "report-activity", debouncedAnchorSearch],
    queryFn: () =>
      fetchJson<any>(apiV1("/crm/customers/"), {
        page: 1,
        limit: 50,
        ...(debouncedAnchorSearch.trim() ? { search: debouncedAnchorSearch.trim() } : {}),
      }),
    enabled: props.open && anchorType === "account",
    retry: false,
  });

  const [dealSearch, setDealSearch] = useState("");
  const [debouncedDealSearch, setDebouncedDealSearch] = useState("");
  const [dealPopoverOpen, setDealPopoverOpen] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setDebouncedDealSearch(dealSearch), 200);
    return () => clearTimeout(t);
  }, [dealSearch]);

  const [secondaryAnchorSearch, setSecondaryAnchorSearch] = useState("");
  const [debouncedSecondaryAnchorSearch, setDebouncedSecondaryAnchorSearch] = useState("");
  const [secondaryAnchorPopoverOpen, setSecondaryAnchorPopoverOpen] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setDebouncedSecondaryAnchorSearch(secondaryAnchorSearch), 200);
    return () => clearTimeout(t);
  }, [secondaryAnchorSearch]);

  const contactsByAccountQuery = useQuery({
    queryKey: [apiV1("/crm/contacts/"), "report-activity-by-account", anchorId, debouncedSecondaryAnchorSearch],
    queryFn: () =>
      fetchJson<any>(apiV1("/crm/contacts/"), {
        page: 1,
        limit: 50,
        account_id: anchorId,
        ...(debouncedSecondaryAnchorSearch.trim() ? { search: debouncedSecondaryAnchorSearch.trim() } : {}),
      }),
    enabled: props.open && anchorType === "account" && !!anchorId,
    retry: false,
  });

  const accountsForSecondaryQuery = useQuery({
    queryKey: [apiV1("/crm/customers/"), "report-activity-secondary-accounts", debouncedSecondaryAnchorSearch],
    queryFn: () =>
      fetchJson<any>(apiV1("/crm/customers/"), {
        page: 1,
        limit: 50,
        ...(debouncedSecondaryAnchorSearch.trim() ? { search: debouncedSecondaryAnchorSearch.trim() } : {}),
      }),
    enabled: props.open && anchorType === "contact" && !!anchorId,
    retry: false,
  });

  const dealsQuery = useQuery({
    queryKey: [apiV1("/crm/deals/"), "report-activity-deals", debouncedDealSearch, anchorType, anchorId],
    queryFn: () =>
      fetchJson<any>(apiV1("/crm/deals/"), {
        page: 1,
        limit: 50,
        ...(debouncedDealSearch.trim() ? { search: debouncedDealSearch.trim() } : {}),
        ...(anchorType === "contact" && anchorId ? { contact_id: anchorId } : {}),
        ...(anchorType === "account" && anchorId ? { customer_id: anchorId } : {}),
      }),
    enabled: props.open && !!anchorId,
    retry: false,
  });

  const usersQuery = useQuery({
    queryKey: [apiV1("/users/"), "report-activity-owners"],
    queryFn: () => moioUsersApi.list(),
    enabled: props.open && !!classifyResult,
  });

  const deals = useMemo(() => normalizeArray<DealLite>(dealsQuery.data, ["deals"]), [dealsQuery.data]);
  const contactsByAccount = useMemo(
    () => normalizeArray<ContactLite>(contactsByAccountQuery.data, ["contacts"]),
    [contactsByAccountQuery.data]
  );
  const accountsForSecondary = useMemo(
    () => normalizeArray<AccountLite>(accountsForSecondaryQuery.data, ["customers"]),
    [accountsForSecondaryQuery.data]
  );
  const selectedSecondaryAnchorLabel = useMemo(() => {
    if (!secondaryAnchorId) return "";
    if (createdSecondaryAnchorLabel) return createdSecondaryAnchorLabel;
    if (anchorType === "account") {
      const c = contactsByAccount.find((x) => x.id === secondaryAnchorId);
      return c?.name ?? secondaryAnchorId;
    }
    const a = accountsForSecondary.find((x) => x.id === secondaryAnchorId);
    return a?.name ?? secondaryAnchorId;
  }, [secondaryAnchorId, anchorType, contactsByAccount, accountsForSecondary, createdSecondaryAnchorLabel]);
  const contacts = useMemo(() => {
    const arr = normalizeArray<ContactLite>(contactsQuery.data, ["contacts"]);
    return arr;
  }, [contactsQuery.data]);
  const accounts = useMemo(() => normalizeArray<AccountLite>(accountsQuery.data, ["customers"]), [accountsQuery.data]);

  const selectedAnchorLabel = useMemo(() => {
    if (!anchorId) return "";
    if (createdAnchorLabel) return createdAnchorLabel;
    if (anchorType === "account") {
      const acc = accounts.find((a) => a.id === anchorId);
      return acc?.name ? `${acc.name}` : anchorId;
    }
    const contact = contacts.find((c) => c.id === anchorId);
    return contact?.name ? `${contact.name}` : anchorId;
  }, [anchorId, anchorType, contacts, accounts, createdAnchorLabel]);

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
      setDealId("");
      setDealSearch("");
      setDealPopoverOpen(false);
      setAnchorPopoverOpen(false);
      setAnchorSearch("");
      setCreatedAnchorLabel(null);
      setRawText("");
      setPhase("input");
      setVisibility("internal");
      setAnchorType("contact");
      setIsSubmitting(false);
      setClassifyResult(null);
      setIsApplying(false);
      setEditableItems([]);
      setEditingIndex(null);
      setCardStates({});
    }
  };

  const anchorModelFor = (type: AnchorType): "crm.contact" | "crm.customer" => {
    if (type === "account") return "crm.customer";
    return "crm.contact";
  };

  const handleSendMessage = () => {
    const text = rawText.trim();
    if (!text) {
      toast({ title: "Add some text", description: "Write a note to capture.", variant: "destructive" });
      return;
    }
    setPhase("link");
  };

  const submitClassify = async () => {
    if (!anchorId) {
      toast({ title: "Select an anchor", description: "Choose a contact or account.", variant: "destructive" });
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

  const applySingleActivity = async (idx: number, itemOverride?: ConfirmedActivityItem) => {
    const entryId = classifyResult?.entry?.id;
    if (!entryId) return;
    let item = itemOverride ?? displayItems[idx];
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
        ...(dealId ? { deal_id: dealId } : {}),
        ...(anchorType === "account" && secondaryAnchorId ? { contact_id: secondaryAnchorId } : {}),
        ...(anchorType === "contact" && secondaryAnchorId ? { customer_id: secondaryAnchorId } : {}),
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

  const anchorItems = anchorType === "account" ? accounts : contacts;
  const isAnchorLoading = anchorType === "account" ? accountsQuery.isLoading : contactsQuery.isLoading;
  const anchorEmptyLabel = anchorType === "account" ? "No accounts found." : "No contacts found.";

  const handleCreateAnchor = async (name: string) => {
    const trimmed = name.trim();
    if (!trimmed || isCreatingAnchor) return;
    setIsCreatingAnchor(true);
    try {
      setCreatedAnchorLabel(trimmed);
      if (anchorType === "account") {
        const res = await apiRequest("POST", apiV1("/crm/customers/"), {
          data: { name: trimmed, legal_name: trimmed, type: "Business" },
        });
        const created = await res.json();
        setAnchorId(created.id);
        queryClient.invalidateQueries({ queryKey: [apiV1("/crm/customers/")] });
      } else {
        const res = await apiRequest("POST", apiV1("/crm/contacts/"), {
          data: { fullname: trimmed },
        });
        const created = await res.json();
        setAnchorId(created.id);
        queryClient.invalidateQueries({ queryKey: [apiV1("/crm/contacts/")] });
      }
      setAnchorSearch("");
      setAnchorPopoverOpen(false);
      toast({ title: "Created", description: `${anchorType === "account" ? "Account" : "Contact"} created.` });
    } catch (err: any) {
      const isApiError = err?.name === "ApiError";
      const status = err?.status;
      const msg = err?.message || "Failed to create.";
      const detail =
        status === 0 && msg.includes("fetch")
          ? "Network error. Check that the backend is running and reachable."
          : isApiError && status && status >= 400
            ? (err?.body ? (typeof err.body === "string" && err.body.length < 200 ? err.body : `HTTP ${status}`) : `HTTP ${status}`)
            : undefined;
      toast({
        title: "Could not create",
        description: detail || msg,
        variant: "destructive",
      });
    } finally {
      setIsCreatingAnchor(false);
    }
  };

  const handleCreateDeal = async (name: string) => {
    const trimmed = name.trim();
    if (!trimmed || isCreatingAnchor) return;
    setIsCreatingAnchor(true);
    try {
      const payload: Record<string, unknown> = { title: trimmed };
      if (anchorType === "contact" && anchorId) payload.contact = anchorId;
      const res = await apiRequest("POST", apiV1("/crm/deals/"), { data: payload });
      const created = await res.json();
      setDealId(created.id);
      setDealSearch("");
      setDealPopoverOpen(false);
      queryClient.invalidateQueries({ queryKey: [apiV1("/crm/deals/")] });
      toast({ title: "Created", description: "Deal created." });
    } catch (err: any) {
      const isApiError = err?.name === "ApiError";
      const status = err?.status;
      const msg = err?.message || "Failed to create.";
      const detail =
        status === 0 && msg.includes("fetch")
          ? "Network error. Check that the backend is running and reachable."
          : isApiError && status && status >= 400
            ? (err?.body ? (typeof err.body === "string" && err.body.length < 200 ? err.body : `HTTP ${status}`) : `HTTP ${status}`)
            : undefined;
      toast({
        title: "Could not create deal",
        description: detail || msg,
        variant: "destructive",
      });
    } finally {
      setIsCreatingAnchor(false);
    }
  };

  return (
    <Dialog
      open={props.open}
      onOpenChange={(open) => {
        props.onOpenChange(open);
        resetIfClosed(open);
      }}
    >
      <DialogContent className="sm:max-w-2xl flex flex-col max-h-[90vh] md:max-h-[90vh] p-0 gap-0 max-md:inset-0 max-md:w-screen max-md:h-[100dvh] max-md:max-w-none max-md:rounded-none">
        <DialogHeader className="px-6 pt-6 pb-4 shrink-0">
          <DialogTitle>Log or plan an activity</DialogTitle>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <DialogDescription className="m-0 flex-1 min-w-0">
              What did you do or what's next? One line is enough. We'll link it to a contact or account and add it to your timeline.
            </DialogDescription>
            {classifyResult && (
            <div className="flex gap-2 shrink-0">
              <Button
                variant="outline"
                size="sm"
                className="border-amber-500 text-amber-600 hover:bg-amber-50 hover:text-amber-700 hover:border-amber-600"
                onClick={() => { setClassifyResult(null); setPhase("input"); }}
                disabled={isApplying}
                data-testid="button-capture-back"
              >
                Editar informe
              </Button>
              <Button
                variant="default"
                size="sm"
                onClick={() => { setRawText(""); setClassifyResult(null); setPhase("input"); }}
                disabled={isApplying}
                data-testid="button-capture-new"
              >
                Ingresar nuevo informe
              </Button>
            </div>
            )}
          </div>
        </DialogHeader>

        {classifyResult ? (
          <ScrollArea className="flex-1 min-h-0 px-6">
          <div className="space-y-4 py-4 pb-6">
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
                              variant="outline"
                              className="h-8 border-red-500 text-red-600 hover:bg-red-50 hover:text-red-700 hover:border-red-600"
                              onClick={() => rejectActivity(idx)}
                              title="Descartar"
                            >
                              Descartar
                            </Button>
                            <Button
                              size="sm"
                              variant="default"
                              className="h-8"
                              onClick={(e) => {
                                e.stopPropagation();
                                setEditingIndex(idx);
                              }}
                              title="Revisar actividad"
                            >
                              Revisar
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
              onSave={async (edited) => {
                if (editingIndex !== null) {
                  const idx = editingIndex;
                  setEditableItems((prev) => {
                    const next = [...prev];
                    next[idx] = edited;
                    return next;
                  });
                  setEditingIndex(null);
                  await applySingleActivity(idx, edited);
                }
              }}
            />
          </div>
          </ScrollArea>
        ) : phase === "link" ? (
        <div className="flex flex-col flex-1 min-h-0">
          <ScrollArea className="flex-1 px-6">
            <div className="py-4 space-y-4">
              <div className="flex justify-end">
                <div className="max-w-[85%] rounded-lg bg-primary text-primary-foreground px-4 py-2 text-sm">
                  {rawText}
                </div>
              </div>
              <p className="text-sm font-medium">Link this to a contact, account, or deal?</p>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>Link to</Label>
                  <Select
                    value={anchorType}
                    onValueChange={(v) => {
                      setAnchorType(v as AnchorType);
                      setAnchorId("");
                      setSecondaryAnchorId("");
                      setCreatedSecondaryAnchorLabel(null);
                      setDealId("");
                      setAnchorSearch("");
                      setCreatedAnchorLabel(null);
                    }}
                  >
                    <SelectTrigger data-testid="select-anchor-type">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="contact">Contact</SelectItem>
                      <SelectItem value="account">Account</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>{anchorType === "account" ? "Account" : "Contact"}</Label>
              <Popover
                open={anchorPopoverOpen}
                onOpenChange={(open) => {
                  setAnchorPopoverOpen(open);
                  if (!open) setAnchorSearch("");
                }}
              >
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
                      {anchorType === "account" ? "Select account..." : "Select contact..."}
                    </span>
                  )}
                  <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-[360px] p-0" align="start">
                <Command shouldFilter={false}>
                  <CommandInput
                    placeholder={anchorType === "account" ? "Search or type account name…" : "Search or type contact name…"}
                    value={anchorSearch}
                    onValueChange={setAnchorSearch}
                  />
                  <CommandList>
                    {isAnchorLoading && (
                      <div className="flex items-center justify-center gap-2 py-4 text-sm text-muted-foreground">
                        <Loader2 className="h-4 w-4 animate-spin" />
                        Searching…
                      </div>
                    )}
                    <CommandGroup>
                      {anchorSearch.trim() && !isAnchorLoading && (
                        <CommandItem
                          key="create-new"
                          value={`__create__${anchorSearch.trim()}`}
                          onSelect={() => {
                            const name = anchorSearch.trim();
                            if (name) handleCreateAnchor(name);
                          }}
                          disabled={isCreatingAnchor}
                          className="font-medium"
                        >
                          {anchorType === "account" ? <Building2 className="mr-2 h-4 w-4" /> : <User className="mr-2 h-4 w-4" />}
                          {isCreatingAnchor ? "Creating..." : `Create ${anchorType === "account" ? "account" : "contact"} "${anchorSearch.trim()}"`}
                        </CommandItem>
                      )}
                      {anchorItems.map((item: any) => {
                        const id = String(item.id);
                        const label =
                          anchorType === "account"
                            ? String((item as AccountLite).name ?? id)
                            : String((item as ContactLite).name ?? id);
                        const sub =
                          anchorType === "account"
                            ? ((item as AccountLite).email ?? (item as AccountLite).legal_name ?? "")
                            : ((item as ContactLite).email ?? (item as ContactLite).phone ?? (item as ContactLite).company ?? "");

                        return (
                          <CommandItem
                            key={id}
                            value={id}
                            onSelect={() => {
                              setAnchorId(id);
                              setSecondaryAnchorId("");
                              setCreatedSecondaryAnchorLabel(null);
                              setAnchorPopoverOpen(false);
                              setAnchorSearch("");
                              setCreatedAnchorLabel(null);
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
                    {!anchorSearch.trim() && anchorItems.length === 0 && !isAnchorLoading && (
                      <CommandEmpty>Type to search or create</CommandEmpty>
                    )}
                  </CommandList>
                </Command>
              </PopoverContent>
            </Popover>
            </div>
          </div>

          {anchorId && (
            <div className="space-y-2">
              <Label className="text-muted-foreground">
                {anchorType === "account"
                  ? "Optionally link to a contact at this account"
                  : "Optionally link to an account"}
              </Label>
              <Popover
                open={secondaryAnchorPopoverOpen}
                onOpenChange={(open) => {
                  setSecondaryAnchorPopoverOpen(open);
                  if (!open) setSecondaryAnchorSearch("");
                }}
              >
                <PopoverTrigger asChild>
                  <Button
                    variant="outline"
                    role="combobox"
                    className="w-full justify-between font-normal"
                    data-testid="button-secondary-anchor-combobox"
                  >
                    {secondaryAnchorId ? (
                      <span className="truncate">{selectedSecondaryAnchorLabel}</span>
                    ) : (
                      <span className="text-muted-foreground">
                        {anchorType === "account"
                          ? "Select contact (optional)..."
                          : "Select account (optional)..."}
                      </span>
                    )}
                    <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                  </Button>
                </PopoverTrigger>
                <PopoverContent className="w-[360px] p-0" align="start">
                  <Command shouldFilter={false}>
                    <CommandInput
                      placeholder={
                        anchorType === "account"
                          ? "Search contacts at this account…"
                          : "Search or type account name…"
                      }
                      value={secondaryAnchorSearch}
                      onValueChange={setSecondaryAnchorSearch}
                    />
                    <CommandList>
                      {anchorType === "account" && contactsByAccountQuery.isLoading && (
                        <div className="flex items-center justify-center gap-2 py-4 text-sm text-muted-foreground">
                          <Loader2 className="h-4 w-4 animate-spin" />
                          Searching…
                        </div>
                      )}
                      {anchorType === "contact" && accountsForSecondaryQuery.isLoading && (
                        <div className="flex items-center justify-center gap-2 py-4 text-sm text-muted-foreground">
                          <Loader2 className="h-4 w-4 animate-spin" />
                          Searching…
                        </div>
                      )}
                      <CommandGroup>
                        <CommandItem
                          value="__none__"
                          onSelect={() => {
                            setSecondaryAnchorId("");
                            setCreatedSecondaryAnchorLabel(null);
                            setSecondaryAnchorPopoverOpen(false);
                            setSecondaryAnchorSearch("");
                          }}
                        >
                          <Check className={`mr-2 h-4 w-4 ${!secondaryAnchorId ? "opacity-100" : "opacity-0"}`} />
                          None
                        </CommandItem>
                        {anchorType === "contact" &&
                          secondaryAnchorSearch.trim() &&
                          !accountsForSecondaryQuery.isLoading && (
                            <CommandItem
                              value={`__create__${secondaryAnchorSearch.trim()}`}
                              onSelect={async () => {
                                const name = secondaryAnchorSearch.trim();
                                if (!name || isCreatingAnchor) return;
                                setIsCreatingAnchor(true);
                                try {
                                  const res = await apiRequest("POST", apiV1("/crm/customers/"), {
                                    data: { name, legal_name: name, type: "Business" },
                                  });
                                  const created = await res.json();
                                  setSecondaryAnchorId(created.id);
                                  setCreatedSecondaryAnchorLabel(created.name ?? name);
                                  setSecondaryAnchorPopoverOpen(false);
                                  setSecondaryAnchorSearch("");
                                  queryClient.invalidateQueries({ queryKey: [apiV1("/crm/customers/")] });
                                  toast({ title: "Created", description: "Account created and linked." });
                                } catch (err: any) {
                                  toast({
                                    title: "Could not create",
                                    description: err?.message || "Failed to create account.",
                                    variant: "destructive",
                                  });
                                } finally {
                                  setIsCreatingAnchor(false);
                                }
                              }}
                              disabled={isCreatingAnchor}
                              className="font-medium"
                            >
                              <Building2 className="mr-2 h-4 w-4" />
                              {isCreatingAnchor ? "Creating..." : `Create account "${secondaryAnchorSearch.trim()}"`}
                            </CommandItem>
                          )}
                        {anchorType === "account" &&
                          contactsByAccount.map((c) => {
                            const id = String(c.id);
                            return (
                              <CommandItem
                                key={id}
                                value={id}
                                onSelect={() => {
                                  setSecondaryAnchorId(id);
                                  setCreatedSecondaryAnchorLabel(null);
                                  setSecondaryAnchorPopoverOpen(false);
                                  setSecondaryAnchorSearch("");
                                }}
                              >
                                <Check className={`mr-2 h-4 w-4 ${secondaryAnchorId === id ? "opacity-100" : "opacity-0"}`} />
                                <div className="flex flex-col min-w-0">
                                  <span className="truncate">{c.name ?? id}</span>
                                  {(c.email ?? c.phone ?? c.company ?? "").trim() && (
                                    <span className="text-xs text-muted-foreground truncate">
                                      {c.email ?? c.phone ?? c.company}
                                    </span>
                                  )}
                                </div>
                              </CommandItem>
                            );
                          })}
                        {anchorType === "contact" &&
                          accountsForSecondary.map((a) => {
                            const id = String(a.id);
                            return (
                              <CommandItem
                                key={id}
                                value={id}
                                onSelect={() => {
                                  setSecondaryAnchorId(id);
                                  setCreatedSecondaryAnchorLabel(null);
                                  setSecondaryAnchorPopoverOpen(false);
                                  setSecondaryAnchorSearch("");
                                }}
                              >
                                <Check className={`mr-2 h-4 w-4 ${secondaryAnchorId === id ? "opacity-100" : "opacity-0"}`} />
                                <div className="flex flex-col min-w-0">
                                  <span className="truncate">{a.name ?? id}</span>
                                  {(a.legal_name ?? a.email ?? "").trim() && (
                                    <span className="text-xs text-muted-foreground truncate">
                                      {a.legal_name ?? a.email}
                                    </span>
                                  )}
                                </div>
                              </CommandItem>
                            );
                          })}
                      </CommandGroup>
                      {anchorType === "account" &&
                        !secondaryAnchorSearch.trim() &&
                        contactsByAccount.length === 0 &&
                        !contactsByAccountQuery.isLoading && (
                          <CommandEmpty>No contacts linked to this account yet</CommandEmpty>
                        )}
                      {anchorType === "contact" &&
                        !secondaryAnchorSearch.trim() &&
                        accountsForSecondary.length === 0 &&
                        !accountsForSecondaryQuery.isLoading && (
                          <CommandEmpty>Type to search accounts</CommandEmpty>
                        )}
                    </CommandList>
                  </Command>
                </PopoverContent>
              </Popover>
            </div>
          )}

          {anchorId && (
            <div className="space-y-2">
              <Label className="text-muted-foreground">Optionally link to a deal</Label>
              <div className="flex gap-2">
                <Popover open={dealPopoverOpen} onOpenChange={setDealPopoverOpen}>
                  <PopoverTrigger asChild>
                    <Button
                      variant="outline"
                      role="combobox"
                      className="flex-1 justify-between font-normal"
                      data-testid="button-deal-combobox"
                    >
                      {dealId ? (deals.find((d) => d.id === dealId)?.title ?? dealId) : "Select deal (optional)..."}
                      <ChevronsUpDown className="h-4 w-4 shrink-0 opacity-50" />
                    </Button>
                  </PopoverTrigger>
                  <PopoverContent className="w-[360px] p-0" align="start">
                    <Command shouldFilter={false}>
                      <CommandInput
                        placeholder="Search or type deal name…"
                        value={dealSearch}
                        onValueChange={setDealSearch}
                      />
                      <CommandList>
                        {dealsQuery.isLoading && (
                          <div className="flex items-center justify-center gap-2 py-4 text-sm text-muted-foreground">
                            <Loader2 className="h-4 w-4 animate-spin" />
                            Searching…
                          </div>
                        )}
                        <CommandGroup>
                          <CommandItem
                            value="__none__"
                            onSelect={() => {
                              setDealId("");
                              setDealPopoverOpen(false);
                              setDealSearch("");
                            }}
                          >
                            <Check className={`mr-2 h-4 w-4 ${!dealId ? "opacity-100" : "opacity-0"}`} />
                            <span className="text-muted-foreground">None</span>
                          </CommandItem>
                          {dealSearch.trim() && !dealsQuery.isLoading && (
                            <CommandItem
                              key="create-deal"
                              value={`__create__${dealSearch.trim()}`}
                              onSelect={() => {
                                const name = dealSearch.trim();
                                if (name) handleCreateDeal(name);
                              }}
                              disabled={isCreatingAnchor}
                              className="font-medium"
                            >
                              <Briefcase className="mr-2 h-4 w-4" />
                              {isCreatingAnchor ? "Creating..." : `Create deal "${dealSearch.trim()}"`}
                            </CommandItem>
                          )}
                          {deals.map((d) => (
                            <CommandItem
                              key={d.id}
                              value={d.id}
                              onSelect={() => {
                                setDealId(d.id);
                                setDealPopoverOpen(false);
                                setDealSearch("");
                              }}
                            >
                              <Check className={`mr-2 h-4 w-4 ${dealId === d.id ? "opacity-100" : "opacity-0"}`} />
                              {d.title ?? d.id}
                            </CommandItem>
                          ))}
                        </CommandGroup>
                        {!dealSearch.trim() && deals.length === 0 && !dealsQuery.isLoading && (
                          <CommandEmpty>Type to search or create</CommandEmpty>
                        )}
                      </CommandList>
                    </Command>
                  </PopoverContent>
                </Popover>
                {dealId && (
                  <Button variant="ghost" size="sm" className="shrink-0" onClick={() => setDealId("")}>
                    Clear
                  </Button>
                )}
              </div>
            </div>
          )}

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
          </ScrollArea>
          <div className="px-6 py-4 border-t shrink-0 flex gap-2">
            <Button variant="outline" onClick={() => setPhase("input")} data-testid="button-capture-back">
              Back
            </Button>
            <Button onClick={submitClassify} disabled={isSubmitting || !anchorId} data-testid="button-save-capture">
              {isSubmitting && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              Process
            </Button>
          </div>
        </div>
        ) : (
        <div className="flex flex-col flex-1 min-h-0">
          <div className="flex-1 min-h-[120px]" />
          <div className="border-t p-4 shrink-0">
            <div className="flex gap-2">
              <Input
                placeholder="e.g. Call John tomorrow re: quote, Schedule demo Tuesday 3pm"
                value={rawText}
                onChange={(e) => setRawText(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && (e.preventDefault(), handleSendMessage())}
                className="flex-1"
                data-testid="textarea-capture-raw"
                autoFocus
              />
              <Button
                onClick={handleSendMessage}
                disabled={!rawText.trim()}
                size="icon"
                className="shrink-0"
                data-testid="button-send-capture"
                aria-label="Send"
              >
                <Send className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </div>
        )}

      </DialogContent>
    </Dialog>
  );
}

