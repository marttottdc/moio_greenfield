import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { Check, ChevronsUpDown, Loader2, Pencil, CalendarDays, CheckSquare, Briefcase, Send, Building2, User, Mic, Square } from "lucide-react";
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
  ClassifySyncResponse,
  ConfirmedActivityItem,
  ProposedActivity,
} from "@/lib/capture/types";

type AnchorType = "contact" | "account" | "administrative";
const ADMIN_ANCHOR_ID = "__administrative__";

type DealLite = { id: string; title?: string; contact_name?: string | null; value?: number | string | null; currency?: string | null };
type ContactLite = { id: string; name?: string; email?: string | null; phone?: string | null; company?: string | null };
type AccountLite = { id: string; name?: string; legal_name?: string | null; email?: string | null };
type ContactBasics = { name: string; email: string; phone: string; company: string };

type BrowserSpeechRecognition = {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onresult: ((event: any) => void) | null;
  onerror: ((event: any) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
};

declare global {
  interface Window {
    webkitSpeechRecognition?: new () => BrowserSpeechRecognition;
    SpeechRecognition?: new () => BrowserSpeechRecognition;
  }
}

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
  const { t } = useTranslation();
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
  const [phase, setPhase] = useState<"anchor" | "activity" | "links" | "analyzing" | "review">("anchor");
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const [keyboardInsetBottom, setKeyboardInsetBottom] = useState(0);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [classifyResult, setClassifyResult] = useState<ClassifySyncResponse | null>(null);
  const [isApplying, setIsApplying] = useState(false);
  const [editableItems, setEditableItems] = useState<ConfirmedActivityItem[]>([]);
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [cardStates, setCardStates] = useState<Record<number, "pending" | "created" | "rejected">>({});
  const [reviewIndex, setReviewIndex] = useState(0);
  const [isDictationSupported, setIsDictationSupported] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [dictationInterim, setDictationInterim] = useState("");
  const recognitionRef = useRef<BrowserSpeechRecognition | null>(null);
  const [contactBasics, setContactBasics] = useState<ContactBasics>({ name: "", email: "", phone: "", company: "" });
  const [loadedContactId, setLoadedContactId] = useState<string | null>(null);
  const [isSavingContactBasics, setIsSavingContactBasics] = useState(false);
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

  const [contactCompanySearch, setContactCompanySearch] = useState("");
  const [debouncedContactCompanySearch, setDebouncedContactCompanySearch] = useState("");
  const [contactCompanyPopoverOpen, setContactCompanyPopoverOpen] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setDebouncedContactCompanySearch(contactCompanySearch), 200);
    return () => clearTimeout(t);
  }, [contactCompanySearch]);

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

  const contactBasicsCompaniesQuery = useQuery({
    queryKey: [apiV1("/crm/customers/"), "report-activity-contact-basics-company", debouncedContactCompanySearch],
    queryFn: () =>
      fetchJson<any>(apiV1("/crm/customers/"), {
        page: 1,
        limit: 50,
        ...(debouncedContactCompanySearch.trim() ? { search: debouncedContactCompanySearch.trim() } : {}),
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
        ...(anchorType === "contact" && anchorId && anchorId !== ADMIN_ANCHOR_ID ? { contact_id: anchorId } : {}),
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
  const contactBasicsCompanies = useMemo(
    () => normalizeArray<AccountLite>(contactBasicsCompaniesQuery.data, ["customers"]),
    [contactBasicsCompaniesQuery.data]
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
  const selectedContact = useMemo(
    () => (anchorType === "contact" ? contacts.find((c) => c.id === anchorId) : undefined),
    [anchorType, contacts, anchorId]
  );

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
  const pendingIndexes = useMemo(
    () => displayItems.map((_, idx) => idx).filter((idx) => (cardStates[idx] ?? "pending") === "pending"),
    [displayItems, cardStates]
  );
  const currentReviewIndex = pendingIndexes[reviewIndex] ?? null;
  const reviewedCount = displayItems.filter((_, idx) => (cardStates[idx] ?? "pending") !== "pending").length;

  const resetIfClosed = (open: boolean) => {
    if (!open) {
      recognitionRef.current?.stop();
      recognitionRef.current = null;
      setAnchorId("");
      setDealId("");
      setDealSearch("");
      setDealPopoverOpen(false);
      setContactCompanySearch("");
      setDebouncedContactCompanySearch("");
      setContactCompanyPopoverOpen(false);
      setAnchorPopoverOpen(false);
      setAnchorSearch("");
      setCreatedAnchorLabel(null);
      setRawText("");
      setPhase("anchor");
      setAnchorType("contact");
      setIsSubmitting(false);
      setClassifyResult(null);
      setIsApplying(false);
      setEditableItems([]);
      setEditingIndex(null);
      setCardStates({});
      setReviewIndex(0);
      setIsListening(false);
      setDictationInterim("");
      setContactBasics({ name: "", email: "", phone: "", company: "" });
      setLoadedContactId(null);
      setIsSavingContactBasics(false);
    }
  };

  useEffect(() => {
    if (typeof window === "undefined") return;
    setIsDictationSupported(Boolean(window.SpeechRecognition || window.webkitSpeechRecognition));
  }, []);

  useEffect(() => {
    if (phase !== "activity" || !props.open) {
      recognitionRef.current?.stop();
    }
  }, [phase, props.open]);

  useEffect(() => {
    return () => {
      recognitionRef.current?.stop();
      recognitionRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (anchorType !== "contact" || !anchorId) {
      setContactBasics({ name: "", email: "", phone: "", company: "" });
      setLoadedContactId(null);
      return;
    }
    if (loadedContactId === anchorId) return;
    const fallbackName = (createdAnchorLabel || selectedAnchorLabel || "").trim();
    setContactBasics({
      name: (selectedContact?.name ?? fallbackName).toString(),
      email: (selectedContact?.email ?? "").toString(),
      phone: (selectedContact?.phone ?? "").toString(),
      company: (selectedContact?.company ?? "").toString(),
    });
    setLoadedContactId(anchorId);
  }, [anchorType, anchorId, loadedContactId, selectedContact, selectedAnchorLabel, createdAnchorLabel]);

  // Stick input bar to top of keyboard on mobile using Visual Viewport API
  useEffect(() => {
    if (!props.open || phase !== "activity" || typeof window === "undefined" || !window.visualViewport) return;
    const updateInset = () => {
      const vv = window.visualViewport;
      const bottom = window.innerHeight - (vv.offsetTop + vv.height);
      setKeyboardInsetBottom(Math.max(0, bottom));
    };
    updateInset();
    window.visualViewport.addEventListener("resize", updateInset);
    window.visualViewport.addEventListener("scroll", updateInset);
    return () => {
      window.visualViewport?.removeEventListener("resize", updateInset);
      window.visualViewport?.removeEventListener("scroll", updateInset);
    };
  }, [props.open, phase]);

  const anchorModelFor = (type: AnchorType): "crm.contact" | "crm.customer" => {
    if (type === "administrative") return "crm.contact";
    if (type === "account") return "crm.customer";
    return "crm.contact";
  };

  const saveLinkedContactBasics = async (): Promise<boolean> => {
    if (anchorType !== "contact" || !anchorId) return true;
    const payload: Record<string, string> = {};
    const name = contactBasics.name.trim();
    const email = contactBasics.email.trim();
    const phone = contactBasics.phone.trim();
    const company = contactBasics.company.trim();
    if (name) payload.name = name;
    if (email) payload.email = email;
    if (phone) payload.phone = phone;
    if (company) payload.company = company;
    if (Object.keys(payload).length === 0) return true;
    setIsSavingContactBasics(true);
    try {
      await apiRequest("PATCH", apiV1(`/crm/contacts/${anchorId}/`), { data: payload });
      queryClient.invalidateQueries({ queryKey: [apiV1("/crm/contacts/")] });
      if (name) setCreatedAnchorLabel(name);
      return true;
    } catch (err: any) {
      toast({
        title: "No se pudo guardar el contacto",
        description: err?.message || "Revisa los datos básicos e intenta de nuevo.",
        variant: "destructive",
      });
      return false;
    } finally {
      setIsSavingContactBasics(false);
    }
  };

  const goToLinksStep = () => {
    const text = rawText.trim();
    if (!text) {
      toast({ title: "Add some text", description: "Write a note to capture.", variant: "destructive" });
      return;
    }
    setPhase("links");
  };

  const goToActivityStep = () => {
    if (anchorType === "administrative") {
      setAnchorId(ADMIN_ANCHOR_ID);
      setCreatedAnchorLabel("Actividad administrativa");
      setPhase("activity");
      return;
    }
    if (!anchorId) {
      toast({ title: "Selecciona con quién fue la actividad", description: "Elige un contacto o tipo administrativa antes de continuar.", variant: "destructive" });
      return;
    }
    if (anchorType === "contact") {
      void (async () => {
        const saved = await saveLinkedContactBasics();
        if (saved) setPhase("activity");
      })();
      return;
    }
    setPhase("activity");
  };

  const clearActivityDraft = () => {
    stopDictation();
    setRawText("");
    setDictationInterim("");
    inputRef.current?.focus();
  };

  const stopDictation = () => {
    recognitionRef.current?.stop();
  };

  const startDictation = () => {
    if (typeof window === "undefined") return;
    const Ctor = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Ctor) {
      toast({
        title: "Dictado no disponible",
        description: "Tu navegador no soporta reconocimiento de voz.",
        variant: "destructive",
      });
      return;
    }
    if (isListening) {
      stopDictation();
      return;
    }
    try {
      const recognition = new Ctor();
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.lang = "es-ES";
      recognition.onresult = (event: any) => {
        let finalChunk = "";
        let interimChunk = "";
        for (let i = event.resultIndex; i < event.results.length; i += 1) {
          const res = event.results[i];
          const transcript = String(res?.[0]?.transcript ?? "").trim();
          if (!transcript) continue;
          if (res.isFinal) {
            finalChunk += `${transcript} `;
          } else {
            interimChunk += `${transcript} `;
          }
        }
        if (finalChunk.trim()) {
          setRawText((prev) => `${prev.trimEnd()}${prev.trim() ? " " : ""}${finalChunk.trim()}`);
        }
        setDictationInterim(interimChunk.trim());
      };
      recognition.onerror = (event: any) => {
        setIsListening(false);
        setDictationInterim("");
        recognitionRef.current = null;
        const errorCode = String(event?.error ?? "");
        const description =
          errorCode === "not-allowed"
            ? "Permite el acceso al micrófono para usar dictado."
            : "No se pudo capturar audio. Intenta de nuevo.";
        toast({
          title: "Error de dictado",
          description,
          variant: "destructive",
        });
      };
      recognition.onend = () => {
        setIsListening(false);
        setDictationInterim("");
        recognitionRef.current = null;
      };
      recognitionRef.current = recognition;
      setIsListening(true);
      setDictationInterim("");
      recognition.start();
    } catch {
      toast({
        title: "Error de dictado",
        description: "No fue posible iniciar el dictado.",
        variant: "destructive",
      });
    }
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
    setPhase("analyzing");
    setClassifyResult(null);
    try {
      const result = await captureApi.classifyAsync(
        {
          raw_text: rawText.trim(),
          anchor_model: anchorModelFor(anchorType),
          anchor_id: anchorId,
        },
        { pollIntervalMs: 1500, timeoutMs: 90000 }
      );
      setClassifyResult(result);
      setReviewIndex(0);
      setPhase("review");
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
      setPhase("links");
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

  const moveToNextPending = () => {
    setReviewIndex(0);
  };

  const confirmCurrentActivity = async () => {
    if (currentReviewIndex === null) return;
    await applySingleActivity(currentReviewIndex);
    moveToNextPending();
  };

  const rejectCurrentActivity = () => {
    if (currentReviewIndex === null) return;
    rejectActivity(currentReviewIndex);
    moveToNextPending();
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
        setLoadedContactId(null);
        setContactBasics({
          name: trimmed,
          email: "",
          phone: "",
          company: "",
        });
        queryClient.invalidateQueries({ queryKey: [apiV1("/crm/contacts/")] });
      }
      setAnchorSearch("");
      setAnchorPopoverOpen(false);
      toast({ title: anchorType === "account" ? t("crm.account_created") : t("crm.contact_created"), description: anchorType === "account" ? t("crm.account_created_description") : t("crm.contact_created_description") });
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
      toast({ title: t("crm.deal_created"), description: t("crm.deal_created_toast") });
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

  const handleCreateCompanyForContactBasics = async (name: string) => {
    const trimmed = name.trim();
    if (!trimmed || isCreatingAnchor) return;
    setIsCreatingAnchor(true);
    try {
      const res = await apiRequest("POST", apiV1("/crm/customers/"), {
        data: { name: trimmed, legal_name: trimmed, type: "Business" },
      });
      const created = await res.json();
      const companyName = String(created?.name || trimmed);
      setContactBasics((prev) => ({ ...prev, company: companyName }));
      setContactCompanyPopoverOpen(false);
      setContactCompanySearch("");
      queryClient.invalidateQueries({ queryKey: [apiV1("/crm/customers/")] });
      toast({ title: t("crm.account_created"), description: t("crm.account_created_description") });
    } catch (err: any) {
      toast({
        title: "No se pudo crear la empresa",
        description: err?.message || "Intenta nuevamente.",
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
      <DialogContent className="sm:max-w-2xl flex flex-col max-h-[90vh] md:max-h-[90vh] p-0 gap-0 max-md:inset-0 max-md:w-screen max-md:h-[100dvh] max-md:max-w-none max-md:rounded-none max-md:overflow-auto max-md:pb-[env(safe-area-inset-bottom)]">
        <DialogHeader className="px-6 pt-6 pb-3 shrink-0 max-md:px-4 max-md:pt-4 max-md:pb-2">
          <DialogTitle className="max-md:text-lg">{t("crm.log_activity_title")}</DialogTitle>
          <DialogDescription className="m-0 text-xs text-muted-foreground">
            {phase === "anchor" && "Paso 1 de 5 · ¿Con quién fue la actividad?"}
            {phase === "activity" && "Paso 2 de 5 · ¿Cuál fue la actividad?"}
            {phase === "links" && "Paso 3 de 5 · Vinculaciones opcionales"}
            {phase === "analyzing" && "Paso 4 de 5 · Analizando y generando sugerencias"}
            {phase === "review" && "Paso 5 de 5 · Revisión de sugerencias una por una"}
          </DialogDescription>
        </DialogHeader>

        {phase === "anchor" && (
          <div className="flex flex-col flex-1 min-h-0">
            <ScrollArea className="flex-1 px-6">
              <div className="py-4 space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label>{t("crm.link_to_label")}</Label>
                    <Select
                      value={anchorType}
                      onValueChange={(v) => {
                        const nextType = v as AnchorType;
                        setAnchorType(nextType);
                        setAnchorId(nextType === "administrative" ? ADMIN_ANCHOR_ID : "");
                        setLoadedContactId(null);
                        setSecondaryAnchorId("");
                        setCreatedSecondaryAnchorLabel(null);
                        setDealId("");
                        setAnchorSearch("");
                        setCreatedAnchorLabel(nextType === "administrative" ? "Actividad administrativa" : null);
                      }}
                    >
                      <SelectTrigger data-testid="select-anchor-type">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="contact">Contacto</SelectItem>
                        <SelectItem value="administrative">Administrativa (sin contacto)</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  {anchorType === "contact" ? (
                  <div className="space-y-2">
                    <Label>Contacto</Label>
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
                              {t("crm.select_contact")}
                            </span>
                          )}
                          <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                        </Button>
                      </PopoverTrigger>
                      <PopoverContent className="w-[360px] p-0" align="start">
                        <Command shouldFilter={false}>
                          <CommandInput
                            placeholder={"Buscar o escribir contacto..."}
                            value={anchorSearch}
                            onValueChange={setAnchorSearch}
                          />
                          <CommandList>
                            {isAnchorLoading && (
                              <div className="flex items-center justify-center gap-2 py-4 text-sm text-muted-foreground">
                                <Loader2 className="h-4 w-4 animate-spin" />
                                Buscando...
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
                                  <User className="mr-2 h-4 w-4" />
                                  {isCreatingAnchor ? t("crm.creating") : t("crm.create_contact_account", { type: t("crm.contact_singular"), name: anchorSearch.trim() })}
                                </CommandItem>
                              )}
                              {anchorItems.map((item: any) => {
                                const id = String(item.id);
                                const label = String((item as ContactLite).name ?? id);
                                const sub = ((item as ContactLite).email ?? (item as ContactLite).phone ?? (item as ContactLite).company ?? "");

                                return (
                                  <CommandItem
                                    key={id}
                                    value={id}
                                    onSelect={() => {
                                      setAnchorId(id);
                                      setLoadedContactId(null);
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
                              <CommandEmpty>Escribe para buscar o crear</CommandEmpty>
                            )}
                          </CommandList>
                        </Command>
                      </PopoverContent>
                    </Popover>
                  </div>
                  ) : (
                    <div className="space-y-2">
                      <Label>Tipo</Label>
                      <div className="rounded-md border bg-muted/20 px-3 py-2 text-sm text-muted-foreground">
                        Actividad administrativa (sin contacto vinculado)
                      </div>
                    </div>
                  )}
                </div>
                {anchorType === "contact" && !!anchorId && (
                  <div className="rounded-lg border bg-muted/20 p-4 space-y-3">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      <div className="space-y-1">
                        <Label>Email</Label>
                        <Input
                          type="email"
                          value={contactBasics.email}
                          onChange={(e) => setContactBasics((prev) => ({ ...prev, email: e.target.value }))}
                          placeholder="correo@empresa.com"
                        />
                      </div>
                      <div className="space-y-1">
                        <Label>Telefono</Label>
                        <Input
                          value={contactBasics.phone}
                          onChange={(e) => setContactBasics((prev) => ({ ...prev, phone: e.target.value }))}
                          placeholder="+52..."
                        />
                      </div>
                      <div className="space-y-1">
                        <Label>Empresa</Label>
                        <Popover
                          open={contactCompanyPopoverOpen}
                          onOpenChange={(open) => {
                            setContactCompanyPopoverOpen(open);
                            if (!open) setContactCompanySearch("");
                          }}
                        >
                          <PopoverTrigger asChild>
                            <Button variant="outline" role="combobox" className="w-full justify-between font-normal mt-2">
                              <span className="truncate">
                                {contactBasics.company?.trim() ? contactBasics.company : "Buscar empresa en CRM"}
                              </span>
                              <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                            </Button>
                          </PopoverTrigger>
                          <PopoverContent className="w-[360px] p-0" align="start">
                            <Command shouldFilter={false}>
                              <CommandInput
                                placeholder="Buscar o crear empresa..."
                                value={contactCompanySearch}
                                onValueChange={setContactCompanySearch}
                              />
                              <CommandList>
                                {contactBasicsCompaniesQuery.isLoading && (
                                  <div className="flex items-center justify-center gap-2 py-4 text-sm text-muted-foreground">
                                    <Loader2 className="h-4 w-4 animate-spin" />
                                    Buscando...
                                  </div>
                                )}
                                <CommandGroup>
                                  {contactCompanySearch.trim() && !contactBasicsCompaniesQuery.isLoading && (
                                    <CommandItem
                                      value={`__create__${contactCompanySearch.trim()}`}
                                      onSelect={() => handleCreateCompanyForContactBasics(contactCompanySearch.trim())}
                                      disabled={isCreatingAnchor}
                                      className="font-medium"
                                    >
                                      <Building2 className="mr-2 h-4 w-4" />
                                      {isCreatingAnchor
                                        ? t("crm.creating")
                                        : t("crm.create_account_name", { name: contactCompanySearch.trim() })}
                                    </CommandItem>
                                  )}
                                  {contactBasicsCompanies.map((acc) => {
                                    const id = String(acc.id);
                                    const label = String(acc.name ?? id);
                                    return (
                                      <CommandItem
                                        key={id}
                                        value={id}
                                        onSelect={() => {
                                          setContactBasics((prev) => ({ ...prev, company: label }));
                                          setContactCompanyPopoverOpen(false);
                                          setContactCompanySearch("");
                                        }}
                                      >
                                        <Check className={`mr-2 h-4 w-4 ${contactBasics.company === label ? "opacity-100" : "opacity-0"}`} />
                                        <div className="flex flex-col min-w-0">
                                          <span className="truncate">{label}</span>
                                          {(acc.legal_name ?? acc.email ?? "").trim() && (
                                            <span className="text-xs text-muted-foreground truncate">
                                              {acc.legal_name ?? acc.email}
                                            </span>
                                          )}
                                        </div>
                                      </CommandItem>
                                    );
                                  })}
                                </CommandGroup>
                                {!contactCompanySearch.trim() && contactBasicsCompanies.length === 0 && !contactBasicsCompaniesQuery.isLoading && (
                                  <CommandEmpty>Escribe para buscar empresa</CommandEmpty>
                                )}
                              </CommandList>
                            </Command>
                          </PopoverContent>
                        </Popover>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </ScrollArea>
            <div className="px-6 py-4 border-t shrink-0 flex gap-2">
              <Button type="button" variant="outline" onClick={() => props.onOpenChange(false)}>
                {t("common.close")}
              </Button>
              <Button onClick={goToActivityStep} disabled={!anchorId || isSavingContactBasics} className="ml-auto">
                {isSavingContactBasics && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                Siguiente
              </Button>
            </div>
          </div>
        )}

        {phase === "activity" && (
          <div className="flex flex-col flex-1 min-h-0 max-md:flex-none max-md:min-h-0">
            <div className="flex-1 min-h-0 overflow-auto px-4 md:px-6 pt-4 md:pt-6 pb-2">
              <div className="mb-3">
                <p className="text-sm text-muted-foreground">Escribe o dicta la actividad.</p>
              </div>
              <Textarea
                ref={inputRef}
                placeholder={t("crm.log_activity_description")}
                value={rawText}
                onChange={(e) => setRawText(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && (e.preventDefault(), goToLinksStep())}
                className="min-h-[120px] resize-y scroll-mb-32 max-md:scroll-mb-40"
                rows={5}
                data-testid="textarea-capture-raw"
                inputMode="text"
                enterKeyHint="done"
              />
              <div className="mt-4 flex flex-col items-center gap-2">
                <div className="relative h-20 w-20 flex items-center justify-center">
                  {isListening && (
                    <>
                      <span className="absolute h-20 w-20 rounded-full bg-primary/15 animate-ping" />
                      <span
                        className="absolute h-16 w-16 rounded-full bg-primary/20 animate-ping"
                        style={{ animationDelay: "180ms" }}
                      />
                    </>
                  )}
                  <Button
                    type="button"
                    onClick={startDictation}
                    disabled={!isDictationSupported}
                    className="relative h-14 w-14 rounded-full p-0"
                    variant={isListening ? "default" : "outline"}
                    data-testid="button-dictation-toggle"
                    aria-label={isListening ? "Detener dictado" : "Iniciar dictado"}
                  >
                    {isListening ? <Square className="h-5 w-5" /> : <Mic className="h-5 w-5" />}
                  </Button>
                </div>
                <p className="text-xs text-muted-foreground">
                  {isListening ? "Grabando... toca el micrófono para detener." : "Toca el micrófono para dictar."}
                </p>
              </div>
              {!isDictationSupported && (
                <p className="mt-2 text-xs text-muted-foreground">
                  El dictado no está disponible en este navegador.
                </p>
              )}
              {isListening && dictationInterim && (
                <p className="mt-2 text-xs text-muted-foreground">
                  Escuchando: {dictationInterim}
                </p>
              )}
            </div>
            <div
              className="border-t p-4 shrink-0 max-md:pt-3 max-md:fixed max-md:left-0 max-md:right-0 max-md:z-50 max-md:bg-background"
              style={{ bottom: keyboardInsetBottom }}
            >
              <div className="flex gap-2">
                <Button variant="outline" onClick={() => setPhase("anchor")}>
                  {t("crm.back")}
                </Button>
                <Button
                  variant="outline"
                  onClick={clearActivityDraft}
                  disabled={!rawText.trim()}
                >
                  Borrar
                </Button>
                <Button
                  onClick={goToLinksStep}
                  disabled={!rawText.trim()}
                  className="flex-1 min-w-0 sm:flex-initial ml-auto"
                  data-testid="button-send-capture"
                >
                  <Check className="h-4 w-4 sm:mr-2" />
                  <span className="hidden sm:inline">Confirmar</span>
                </Button>
              </div>
            </div>
          </div>
        )}

        {phase === "links" && (
          <div className="flex flex-col flex-1 min-h-0">
            <ScrollArea className="flex-1 px-6">
              <div className="py-4 space-y-4">
                <div className="rounded-lg border border-primary/30 bg-primary/5 p-3 text-sm shadow-sm">
                  <p className="text-xs font-semibold uppercase tracking-wide text-primary/80">
                    Actividad reportada
                  </p>
                  <div className="mt-2 max-h-44 overflow-y-auto rounded-md border bg-background/80 p-3">
                    <p className="whitespace-pre-wrap break-words leading-relaxed">{rawText}</p>
                  </div>
                </div>

                {anchorId && anchorType === "account" && (
                  <div className="space-y-2">
                    <Label className="text-muted-foreground">Vincular contacto de esta empresa</Label>
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
                              Seleccionar contacto
                            </span>
                          )}
                          <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                        </Button>
                      </PopoverTrigger>
                      <PopoverContent className="w-[360px] p-0" align="start">
                        <Command shouldFilter={false}>
                          <CommandInput
                            placeholder={"Buscar contactos de esta empresa..."}
                            value={secondaryAnchorSearch}
                            onValueChange={setSecondaryAnchorSearch}
                          />
                          <CommandList>
                            {contactsByAccountQuery.isLoading && (
                              <div className="flex items-center justify-center gap-2 py-4 text-sm text-muted-foreground">
                                <Loader2 className="h-4 w-4 animate-spin" />
                                Buscando...
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
                                Ninguno
                              </CommandItem>
                              {contactsByAccount.map((c) => {
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
                )}

                {anchorId && (
                  <div className="space-y-2">
                    <Label className="text-muted-foreground">Vincular opcionalmente a un negocio</Label>
                    <div className="flex gap-2">
                      <Popover open={dealPopoverOpen} onOpenChange={setDealPopoverOpen}>
                        <PopoverTrigger asChild>
                          <Button
                            variant="outline"
                            role="combobox"
                            className="flex-1 justify-between font-normal"
                            data-testid="button-deal-combobox"
                          >
                            {dealId ? (deals.find((d) => d.id === dealId)?.title ?? dealId) : t("crm.select_deal_optional")}
                            <ChevronsUpDown className="h-4 w-4 shrink-0 opacity-50" />
                          </Button>
                        </PopoverTrigger>
                        <PopoverContent className="w-[360px] p-0" align="start">
                          <Command shouldFilter={false}>
                            <CommandInput
                              placeholder="Buscar o escribir negocio..."
                              value={dealSearch}
                              onValueChange={setDealSearch}
                            />
                            <CommandList>
                              {dealsQuery.isLoading && (
                                <div className="flex items-center justify-center gap-2 py-4 text-sm text-muted-foreground">
                                  <Loader2 className="h-4 w-4 animate-spin" />
                                  Buscando...
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
                                  <span className="text-muted-foreground">Ninguno</span>
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
                                    {isCreatingAnchor ? t("crm.creating") : t("crm.create_deal_name", { name: dealSearch.trim() })}
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
              </div>
            </ScrollArea>
            <div className="px-6 py-4 border-t shrink-0 flex gap-2">
              <Button variant="outline" onClick={() => setPhase("activity")}>
                {t("crm.back")}
              </Button>
              <Button onClick={submitClassify} disabled={isSubmitting || !anchorId} className="ml-auto" data-testid="button-save-capture">
                {isSubmitting && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                Generar sugerencias
              </Button>
            </div>
          </div>
        )}

        {phase === "analyzing" && (
          <div className="flex-1 flex items-center justify-center px-6">
            <div className="text-center space-y-4">
              <div className="mx-auto h-14 w-14 rounded-full border-2 border-primary/30 border-t-primary animate-spin" />
              <p className="text-sm text-muted-foreground">Estamos analizando la actividad y preparando sugerencias...</p>
            </div>
          </div>
        )}

        {phase === "review" && (
          <div className="flex flex-col flex-1 min-h-0">
            <div className="px-6 pt-3 pb-2 shrink-0 border-b bg-muted/30">
              <p className="text-sm font-medium text-foreground">
                Se generaron {displayItems.length} {displayItems.length === 1 ? "sugerencia" : "sugerencias"}
              </p>
              <p className="text-xs text-muted-foreground mt-0.5">
                Revisadas: {reviewedCount} de {displayItems.length}
              </p>
            </div>
            <ScrollArea className="flex-1 min-h-0 px-6">
              <div className="space-y-4 py-4 pb-6">
                {currentReviewIndex === null ? (
                  <Card>
                    <CardHeader className="space-y-2">
                      <p className="font-medium">No hay más sugerencias pendientes.</p>
                      <p className="text-sm text-muted-foreground">Puedes cerrar o empezar un nuevo registro.</p>
                      <div className="flex gap-2 pt-2">
                        <Button variant="outline" onClick={() => props.onOpenChange(false)}>
                          Cerrar
                        </Button>
                        <Button
                          onClick={() => {
                            setRawText("");
                            setClassifyResult(null);
                            setEditableItems([]);
                            setCardStates({});
                            setPhase("anchor");
                          }}
                        >
                          Nuevo registro
                        </Button>
                      </div>
                    </CardHeader>
                  </Card>
                ) : (
                  <>
                    {(() => {
                      const idx = currentReviewIndex;
                      const item = displayItems[idx];
                      const state = cardStates[idx] ?? "pending";
                      const kind = (item.kind ?? "event") as string;
                      const Icon = kind === "task" ? CheckSquare : kind === "deal" ? Briefcase : CalendarDays;
                      const ownerUser =
                        item.owner_id && usersQuery.data
                          ? usersQuery.data.find((u) => String(u.id) === String(item.owner_id))
                          : null;
                      const ownerLabel = ownerUser
                        ? (ownerUser.full_name || `${ownerUser.first_name || ""} ${ownerUser.last_name || ""}`.trim() || ownerUser.email)
                        : null;
                      return (
                        <Card>
                          <CardHeader className="pb-2 pt-4 px-4">
                            <div className="flex items-start gap-3">
                              <Icon className="h-4 w-4 text-muted-foreground shrink-0 mt-0.5" />
                              <div className="flex-1 min-w-0">
                                <p className="font-medium">{item.title}</p>
                                <div className="flex flex-wrap items-center gap-2 mt-1 text-xs text-muted-foreground">
                                  <span className="capitalize">{kind}</span>
                                  {item.due_at && <span>· Vence {formatActivityDate(item.due_at)}</span>}
                                  {item.start_at && item.end_at && (
                                    <span>· {formatActivityDate(item.start_at)} - {formatActivityDate(item.end_at)}</span>
                                  )}
                                  {ownerLabel && kind !== "event" && <span>· Responsable: {ownerLabel}</span>}
                                </div>
                                {item.description && (
                                  <p className="text-xs text-muted-foreground mt-2 whitespace-pre-wrap">{item.description}</p>
                                )}
                              </div>
                              {state !== "pending" && (
                                <span className="text-xs text-muted-foreground">
                                  {state === "created" ? "Confirmada" : "Rechazada"}
                                </span>
                              )}
                            </div>
                          </CardHeader>
                        </Card>
                      );
                    })()}
                    <div className="flex flex-wrap gap-2 pt-4 hidden md:flex">
                      <Button variant="outline" onClick={() => setEditingIndex(currentReviewIndex)}>
                        <Pencil className="h-4 w-4 mr-2" />
                        Editar
                      </Button>
                      <Button
                        variant="outline"
                        className="border-red-500 text-red-600 hover:bg-red-50 hover:text-red-700 hover:border-red-600"
                        onClick={rejectCurrentActivity}
                        disabled={isApplying}
                      >
                        Rechazar
                      </Button>
                      <Button onClick={confirmCurrentActivity} disabled={isApplying} className="ml-auto">
                        {isApplying && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                        Confirmar
                      </Button>
                    </div>
                  </>
                )}
              </div>
            </ScrollArea>
            {currentReviewIndex !== null && (
              <div className="shrink-0 border-t bg-background px-6 py-3 max-md:pb-[max(0.75rem,env(safe-area-inset-bottom))] md:hidden">
                <div className="flex flex-wrap gap-2">
                  <Button variant="outline" onClick={() => setEditingIndex(currentReviewIndex)} className="touch-manipulation min-h-[44px] flex-1 min-w-0">
                    <Pencil className="h-4 w-4 mr-2" />
                    Editar
                  </Button>
                  <Button
                    variant="outline"
                    className="border-red-500 text-red-600 hover:bg-red-50 touch-manipulation min-h-[44px]"
                    onClick={rejectCurrentActivity}
                    disabled={isApplying}
                  >
                    Rechazar
                  </Button>
                  <Button onClick={confirmCurrentActivity} disabled={isApplying} className="touch-manipulation min-h-[44px] flex-1 min-w-0">
                    {isApplying && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                    Confirmar
                  </Button>
                </div>
              </div>
            )}
            <SuggestedActivityEditSheet
              open={editingIndex !== null}
              onOpenChange={(open) => !open && setEditingIndex(null)}
              item={editingIndex !== null ? displayItems[editingIndex] : null}
              users={usersQuery.data ?? []}
              userGeoAddress={userGeoAddress}
              onSave={(edited) => {
                if (editingIndex !== null) {
                  const idx = editingIndex;
                  setEditableItems((prev) => {
                    const next = [...prev];
                    next[idx] = edited;
                    return next;
                  });
                  setEditingIndex(null);
                }
              }}
            />
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

