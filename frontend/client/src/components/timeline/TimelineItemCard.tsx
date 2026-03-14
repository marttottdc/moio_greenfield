"use client";

import { useState } from "react";
import {
  StickyNote,
  CheckSquare,
  Lightbulb,
  CalendarDays,
  Clock,
  Eye,
  MapPin,
  Star,
  Tag,
  User,
  Building2,
  Briefcase,
  Pencil,
} from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { Link } from "wouter";
import { useAuth } from "@/contexts/AuthContext";
import { cn } from "@/lib/utils";
import { apiV1 } from "@/lib/api";
import { fetchJson } from "@/lib/queryClient";
import type { TimelineItem } from "@/lib/timeline/types";

function contactDisplayName(c: { fullname?: string; display_name?: string; whatsapp_name?: string; first_name?: string; last_name?: string }) {
  const name = (c?.fullname || c?.display_name || c?.whatsapp_name || "").trim();
  if (name) return name;
  const fn = (c?.first_name || "").trim();
  const ln = (c?.last_name || "").trim();
  const combined = `${fn} ${ln}`.trim();
  return combined || null;
}
function customerDisplayName(c: { name?: string; legal_name?: string }) {
  return (c?.name || c?.legal_name || "").trim() || null;
}

export function RelatedEntityLabel({
  kind,
  id,
  name,
  fallback,
  icon,
  href,
  className,
}: {
  kind: "contact" | "customer";
  id: string;
  name?: string | null;
  fallback: string;
  icon: React.ReactNode;
  href: string;
  className?: string;
}) {
  const hasName = name && String(name).trim();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["related-entity", kind, id],
    queryFn: async () => {
      if (kind === "contact") {
        const c = await fetchJson<any>(apiV1(`/crm/contacts/${encodeURIComponent(id)}/`));
        return contactDisplayName(c);
      }
      const c = await fetchJson<any>(apiV1(`/crm/customers/${encodeURIComponent(id)}/`));
      return customerDisplayName(c);
    },
    enabled: !hasName && !!id,
    staleTime: 5 * 60 * 1000,
    retry: false,
  });
  const label = hasName ? name : (isError ? fallback : (data ?? (isLoading ? fallback : fallback)));
  return (
    <Link href={href} className={className}>
      <span className="inline-flex items-center gap-1.5 text-primary hover:underline">
        {icon}
        {label}
      </span>
    </Link>
  );
}

function formatTimelineDateShort(ts?: string): string {
  if (!ts) return "";
  try {
    const d = new Date(ts);
    return d.toLocaleDateString("en-US", {
      weekday: "short",
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

function shortId(id: string, keep = 6): string {
  const v = String(id || "").trim();
  if (!v) return "";
  return v.length <= keep * 2 + 3 ? v : `${v.slice(0, keep)}…${v.slice(-keep)}`;
}

function activityPreview(activity: ActivityDetailData): string | null {
  const content = (activity.content ?? {}) as Record<string, unknown>;
  const kind = String(activity.kind ?? "").toLowerCase();

  if (kind === "task") {
    const description = typeof content.description === "string" ? content.description.trim() : "";
    if (description) return description;
  }
  if (kind === "note" || kind === "idea") {
    const body = typeof content.body === "string" ? content.body.trim() : "";
    if (body) return body;
  }

  const eventPayload =
    content && typeof content.event === "object" && content.event && typeof (content.event as any).payload === "object"
      ? ((content.event as any).payload as Record<string, unknown>)
      : null;
  const moveComment = eventPayload && typeof eventPayload.move_comment === "string"
    ? eventPayload.move_comment.trim()
    : "";
  if (moveComment) return `Movement comment: ${moveComment}`;

  return null;
}

function humanizeFieldName(key: string): string {
  return String(key || "")
    .replace(/_/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/^./, (ch) => ch.toUpperCase());
}

function isIdField(key: string): boolean {
  const normalized = String(key || "").trim().toLowerCase();
  return normalized === "id" || normalized.endsWith("_id") || normalized === "event_id";
}

function summarizeValue(value: unknown): string {
  if (value == null) return "—";
  if (typeof value === "string") return value.trim() || "—";
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) {
    if (value.length === 0) return "—";
    const printable = value.filter((v) => typeof v === "string" || typeof v === "number" || typeof v === "boolean");
    if (printable.length === value.length) return printable.map((v) => String(v)).join(", ");
    return `${value.length} item${value.length === 1 ? "" : "s"}`;
  }
  if (typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>);
    if (entries.length === 0) return "—";
    const flat = entries
      .filter(([, v]) => typeof v === "string" || typeof v === "number" || typeof v === "boolean")
      .slice(0, 3)
      .map(([k, v]) => `${humanizeFieldName(k)}: ${String(v)}`);
    if (flat.length > 0) {
      return flat.join(" · ");
    }
    return `${entries.length} field${entries.length === 1 ? "" : "s"}`;
  }
  return String(value);
}

function DetailSection({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-lg border border-border/70 bg-card/70 p-3 space-y-2.5">
      <p className="text-[11px] font-semibold text-muted-foreground uppercase tracking-[0.12em]">{title}</p>
      {children}
    </section>
  );
}

export function resolveActivityAuthor(
  activity: { author?: string | null; user_id?: string | null } | null,
  currentUserId?: string | null
): string {
  if (!activity) return "—";
  if (activity.author && String(activity.author).trim()) return String(activity.author).trim();
  const actorId = activity.user_id ? String(activity.user_id) : "";
  if (!actorId) return "—";
  if (currentUserId && actorId === currentUserId) return "You";
  return `User ${shortId(actorId)}`;
}

type ActivityKind = "task" | "note" | "idea" | "event" | string;
function activityIcon(kind: ActivityKind) {
  const k = String(kind || "").toLowerCase();
  if (k === "task") return CheckSquare;
  if (k === "note") return StickyNote;
  if (k === "idea") return Lightbulb;
  if (k === "event") return CalendarDays;
  return Clock;
}

export interface ActivityDetailData {
  id: string;
  title: string;
  kind: string;
  content?: Record<string, unknown>;
  author?: string | null;
  user_id?: string | null;
  created_at?: string;
  visibility?: string;
  status?: string;
  contact_id?: string | null;
  contact_name?: string | null;
  customer_id?: string | null;
  customer_name?: string | null;
  deal_id?: string | null;
  deal_title?: string | null;
}

export function ActivityDetailSheet({
  open,
  onOpenChange,
  activity,
  onEdit,
  renderActivityEditForm,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  activity: ActivityDetailData | null;
  onEdit?: (activity: ActivityDetailData) => void;
  renderActivityEditForm?: (props: { activity: ActivityDetailData; onSaved: () => void; onCancel: () => void }) => React.ReactNode;
}) {
  const { user } = useAuth();
  const [isEditing, setIsEditing] = useState(false);

  if (!activity) return null;

  const handleCancelEdit = () => setIsEditing(false);
  const handleSavedEdit = () => setIsEditing(false);

  const canEditInDrawer = !!renderActivityEditForm;
  const showEditForm = isEditing && canEditInDrawer;

  const content = activity.content ?? {};
  const kind = String(activity.kind ?? "").toLowerCase();
  const Icon = activityIcon(kind);
  const created = activity.created_at ? formatTimelineDateShort(activity.created_at) : "—";
  const author = resolveActivityAuthor(activity, user?.id);
  const eventPayload =
    content && typeof (content as any).event === "object" && (content as any).event
      ? ((content as any).event?.payload as Record<string, unknown> | undefined)
      : undefined;
  const moveComment =
    eventPayload && typeof eventPayload.move_comment === "string"
      ? eventPayload.move_comment.trim()
      : "";
  const rawEvent =
    content && typeof (content as any).event === "object" && (content as any).event
      ? ((content as any).event as Record<string, unknown>)
      : null;
  const eventName = rawEvent && typeof rawEvent.name === "string" ? rawEvent.name : "";
  const eventOccurredAt = rawEvent && typeof rawEvent.occurred_at === "string" ? rawEvent.occurred_at : "";
  const eventPayloadForDisplay =
    rawEvent && typeof rawEvent.payload === "object" && rawEvent.payload
      ? (rawEvent.payload as Record<string, unknown>)
      : null;

  const handleEditClick = () => {
    if (canEditInDrawer) {
      setIsEditing(true);
    } else if (onEdit) {
      onEdit(activity);
      onOpenChange(false);
    }
  };

  const hasEditAction = canEditInDrawer || onEdit;

  return (
    <Sheet open={open} onOpenChange={(next) => { if (!next) setIsEditing(false); onOpenChange(next); }}>
      <SheetContent className="sm:max-w-xl overflow-y-auto" side="right">
        {showEditForm ? (
          renderActivityEditForm!({ activity, onSaved: handleSavedEdit, onCancel: handleCancelEdit })
        ) : (
        <>
        <SheetHeader className="text-left pr-10">
          <div className="flex items-center justify-between gap-2">
            <SheetTitle className="flex items-center gap-2 min-w-0 text-left">
              <Icon className="h-5 w-5 text-muted-foreground" />
              <span className="truncate">{activity.title || "Activity"}</span>
            </SheetTitle>
            {hasEditAction && (
              <Button
                variant="outline"
                size="sm"
                onClick={handleEditClick}
                className="shrink-0"
              >
                <Pencil className="h-3.5 w-3.5 mr-1.5" />
                Edit
              </Button>
            )}
          </div>
        </SheetHeader>
        <div className="mt-6 space-y-4">
          <DetailSection title="Overview">
            <div className="flex flex-wrap gap-2">
            {kind && <Badge variant="secondary">{kind}</Badge>}
            {activity.visibility && <Badge variant="outline">{activity.visibility}</Badge>}
            {activity.status && <Badge variant="outline">{activity.status}</Badge>}
            </div>
            <div className="text-sm text-muted-foreground space-y-1.5">
              <p>
                By <span className="text-foreground">{author}</span>
              </p>
              <p>{created}</p>
            </div>
          </DetailSection>
          {moveComment && (
            <DetailSection title="Movement comment">
              <p className="text-sm whitespace-pre-wrap">{moveComment}</p>
            </DetailSection>
          )}
          {(activity.contact_id || activity.customer_id || activity.deal_id) && (
            <DetailSection title="Related">
              <div className="flex flex-wrap gap-2">
                {activity.contact_id && (
                  <RelatedEntityLabel
                    kind="contact"
                    id={activity.contact_id}
                    name={activity.contact_name}
                    fallback="Contact"
                    icon={<User className="h-3.5 w-3.5" />}
                    href={`/crm?tab=contacts&contactId=${encodeURIComponent(activity.contact_id)}`}
                  />
                )}
                {activity.customer_id && (
                  <RelatedEntityLabel
                    kind="customer"
                    id={activity.customer_id}
                    name={activity.customer_name}
                    fallback="Account"
                    icon={<Building2 className="h-3.5 w-3.5" />}
                    href={`/crm?tab=accounts&accountId=${encodeURIComponent(activity.customer_id)}`}
                  />
                )}
                {activity.deal_id && (
                  <Link href={`/deals?dealId=${encodeURIComponent(activity.deal_id)}`}>
                    <span className="inline-flex items-center gap-1.5 text-sm text-primary hover:underline">
                      <Briefcase className="h-3.5 w-3.5" />
                      {activity.deal_title || `Deal ${activity.deal_id}`}
                    </span>
                  </Link>
                )}
              </div>
            </DetailSection>
          )}
          {kind === "task" && (
            <DetailSection title="Task details">
              {(content as { description?: string }).description && (
                <div>
                  <p className="text-xs font-medium text-muted-foreground uppercase mb-1">Description</p>
                  <p className="text-sm whitespace-pre-wrap">{(content as { description?: string }).description}</p>
                </div>
              )}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-sm">
                {(content as { status?: string }).status && (
                  <p>Status: {(content as { status?: string }).status}</p>
                )}
                {(content as { due_date?: string }).due_date && (
                  <p className="flex items-center gap-2">
                    <CalendarDays className="h-4 w-4" />
                    Due {formatTimelineDateShort((content as { due_date?: string }).due_date)}
                  </p>
                )}
                {(content as { priority?: number }).priority != null && (
                  <p>Priority: {(content as { priority?: number }).priority}</p>
                )}
              </div>
            </DetailSection>
          )}
          {(kind === "note" || kind === "idea") && (
            <DetailSection title={kind === "idea" ? "Idea details" : "Note details"}>
              {(content as { body?: string }).body && (
                <div>
                  <p className="text-xs font-medium text-muted-foreground uppercase mb-1">Content</p>
                  <p className="text-sm whitespace-pre-wrap">{(content as { body?: string }).body}</p>
                </div>
              )}
              {(content as { impact?: number }).impact != null && (
                <p className="text-sm flex items-center gap-2">
                  <Star className="h-4 w-4 text-amber-500" />
                  Impact: {(content as { impact?: number }).impact}/10
                </p>
              )}
              {(content as { tags?: string[] })?.tags?.length ? (
                <div className="flex flex-wrap gap-1">
                  {(content as { tags?: string[] }).tags!.map((t: string) => (
                    <Badge key={t} variant="outline" className="text-xs">
                      <Tag className="h-2.5 w-2.5 mr-1" />
                      {t}
                    </Badge>
                  ))}
                </div>
              ) : null}
            </DetailSection>
          )}
          {kind === "event" && (
            <DetailSection title="Event details">
              {(content as { start?: string }).start && (
                <p className="text-sm flex items-center gap-2">
                  <Clock className="h-4 w-4" />
                  Start: {formatTimelineDateShort((content as { start?: string }).start)}
                </p>
              )}
              {(content as { end?: string }).end && (
                <p className="text-sm">End: {formatTimelineDateShort((content as { end?: string }).end)}</p>
              )}
              {(content as { location?: string }).location && (
                <p className="text-sm flex items-center gap-2">
                  <MapPin className="h-4 w-4" />
                  {(content as { location?: string }).location}
                </p>
              )}
            </DetailSection>
          )}
          {(kind === "other" || !["task", "note", "idea", "event"].includes(kind)) &&
            content &&
            Object.keys(content).length > 0 && (
              <DetailSection title="Details">
                {rawEvent && (
                  <div className="space-y-2">
                    <p className="text-xs font-medium text-muted-foreground uppercase">Event</p>
                    {eventName && (
                      <p className="text-sm">
                        <span className="text-muted-foreground">Name:</span> {eventName}
                      </p>
                    )}
                    {eventOccurredAt && (
                      <p className="text-sm">
                        <span className="text-muted-foreground">Occurred:</span> {formatTimelineDateShort(eventOccurredAt)}
                      </p>
                    )}
                    {eventPayloadForDisplay && Object.keys(eventPayloadForDisplay).length > 0 && (
                      <div>
                        <p className="text-xs font-medium text-muted-foreground uppercase mb-1">Payload</p>
                        <dl className="text-sm space-y-1.5">
                          {Object.entries(eventPayloadForDisplay)
                            .filter(([key]) => !isIdField(key))
                            .map(([key, val]) => (
                            <div key={key} className="flex gap-2">
                              <dt className="text-muted-foreground shrink-0">{humanizeFieldName(key)}:</dt>
                              <dd className="break-words">{summarizeValue(val)}</dd>
                            </div>
                          ))}
                        </dl>
                      </div>
                    )}
                  </div>
                )}
                {((content as { body?: string }).body || (content as { description?: string }).description) && (
                  <div>
                    <p className="text-xs font-medium text-muted-foreground uppercase mb-1">Details</p>
                    <p className="text-sm whitespace-pre-wrap">
                      {(content as { body?: string }).body || (content as { description?: string }).description}
                    </p>
                  </div>
                )}
                {(() => {
                  const c = content as Record<string, unknown>;
                  const skip = new Set(["body", "description", "event"]);
                  const rest = Object.entries(c).filter(
                    ([k]) => !skip.has(k) && !isIdField(k) && c[k] != null && c[k] !== ""
                  );
                  if (rest.length === 0) return null;
                  return (
                    <div>
                      <p className="text-xs font-medium text-muted-foreground uppercase mb-1">Additional info</p>
                      <dl className="text-sm space-y-1">
                        {rest.map(([key, val]) => (
                          <div key={key} className="flex gap-2">
                            <dt className="text-muted-foreground shrink-0">{humanizeFieldName(key)}:</dt>
                            <dd className="break-words">{summarizeValue(val)}</dd>
                          </div>
                        ))}
                      </dl>
                    </div>
                  );
                })()}
              </DetailSection>
            )}
        </div>
        </>
        )}
      </SheetContent>
    </Sheet>
  );
}

export interface TimelineItemCardProps {
  item: TimelineItem;
  onActivityClick?: (item: TimelineItem) => void;
}

export function TimelineItemCard({ item, onActivityClick }: TimelineItemCardProps) {
  const { user } = useAuth();

  if (item.type === "capture_entry") {
    const entry: any = (item as any).entry ?? item;
    const summary = entry.summary ? String(entry.summary) : String(entry.raw_text ?? "").trim();
    const status = String(entry.status ?? "captured");
    return (
      <div className="p-3 rounded-lg border bg-card text-sm space-y-1">
        <div className="flex items-center justify-between gap-2">
          <StickyNote className="h-4 w-4 text-amber-600 shrink-0" />
          <Badge variant="outline" className="text-xs">
            {status}
          </Badge>
        </div>
        {summary && <p className="text-muted-foreground line-clamp-2">{summary}</p>}
      </div>
    );
  }

  if (item.type === "activity") {
    const title = (item as any).title ?? (item as any).name ?? (item as any)?.activity?.title ?? "Activity";
    const kind = (item as any).kind ?? (item as any)?.activity?.kind;
    const Icon = activityIcon(kind);
    const activity: any = (item as any).activity ?? item;
    const preview = activityPreview(activity as ActivityDetailData);
    const author = (() => {
      if (activity?.author && String(activity.author).trim()) return String(activity.author).trim();
      const actorId = activity?.user_id ? String(activity.user_id) : "";
      if (!actorId) return "—";
      if (user?.id && actorId === user.id) return "You";
      return `User ${shortId(actorId)}`;
    })();
    const handleClick = () => onActivityClick?.(item);
    return (
      <div
        className={cn(
          "p-3 rounded-lg border bg-card space-y-1",
          onActivityClick && "cursor-pointer hover:bg-muted/50 transition-colors"
        )}
        data-testid={`timeline-activity-${item.id}`}
        onClick={handleClick}
        role={onActivityClick ? "button" : undefined}
      >
        <div className="flex items-center gap-2 min-w-0">
          <Icon
            className={cn(
              "h-4 w-4 shrink-0",
              String(kind || "").toLowerCase() === "note" ? "text-amber-600" : "text-muted-foreground"
            )}
          />
          {kind && (
            <Badge variant="secondary" className="text-xs">
              {String(kind)}
            </Badge>
          )}
          <span className="font-medium truncate">{String(title)}</span>
          {onActivityClick && <Eye className="h-3.5 w-3.5 ml-auto shrink-0 text-muted-foreground" />}
        </div>
        <p className="text-xs text-muted-foreground">
          By <span className="text-foreground">{author}</span>
        </p>
        {(activity.contact_id || activity.customer_id || activity.deal_id) && (
          <p className="text-xs text-muted-foreground flex flex-wrap gap-x-3 gap-y-1">
            {activity.contact_id && (
              <RelatedEntityLabel
                kind="contact"
                id={activity.contact_id}
                name={activity.contact_name}
                fallback="Contact"
                icon={<User className="h-3 w-3 inline mr-0.5" />}
                href={`/crm?tab=contacts&contactId=${encodeURIComponent(activity.contact_id)}`}
                className="hover:underline text-primary"
              />
            )}
            {activity.customer_id && (
              <RelatedEntityLabel
                kind="customer"
                id={activity.customer_id}
                name={activity.customer_name}
                fallback="Account"
                icon={<Building2 className="h-3 w-3 inline mr-0.5" />}
                href={`/crm?tab=accounts&accountId=${encodeURIComponent(activity.customer_id)}`}
                className="hover:underline text-primary"
              />
            )}
            {activity.deal_id && (
              <Link href={`/deals?dealId=${encodeURIComponent(activity.deal_id)}`} className="hover:underline text-primary">
                <Briefcase className="h-3 w-3 inline mr-0.5" />
                {activity.deal_title || "Deal"}
              </Link>
            )}
          </p>
        )}
        {preview && (
          <p className="text-xs text-muted-foreground line-clamp-2">{preview}</p>
        )}
      </div>
    );
  }

  return (
    <div className="p-3 rounded-lg border bg-card space-y-1" data-testid={`timeline-item-${item.id}`}>
      <Badge variant="secondary">{String(item.type || "item")}</Badge>
      <span className="text-sm truncate">{item.id}</span>
    </div>
  );
}
