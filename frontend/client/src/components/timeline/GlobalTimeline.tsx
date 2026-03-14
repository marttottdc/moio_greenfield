import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Loader2, Clock, AlertTriangle, StickyNote, CheckSquare, Lightbulb, CalendarDays, User, Building2, Briefcase, ChevronLeft, ChevronRight } from "lucide-react";
import { Link } from "wouter";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/empty-state";
import { ErrorDisplay } from "@/components/error-display";
import { captureApi } from "@/lib/capture/captureApi";
import { fetchJson } from "@/lib/queryClient";
import { apiV1 } from "@/lib/api";
import type { TimelineItem } from "@/lib/timeline/types";
import { getItemWhen, getItemDayKey } from "@/lib/timeline/timelineRowModel";
import { useAuth } from "@/contexts/AuthContext";
import { cn } from "@/lib/utils";
import { Calendar } from "@/components/ui/calendar";
import { format, isSameDay, startOfDay } from "date-fns";
import { GlobalTimelineTable } from "./GlobalTimelineTable";
import { ActivityDetailSheet, RelatedEntityLabel, type ActivityDetailData } from "./TimelineItemCard";

type CaptureTimelinePage = {
  items: TimelineItem[];
  sources?: {
    capture?: { current_page: number; total_pages: number };
    activities?: { page: number; total_pages: number };
  };
  pagination?: {
    current_page: number;
    total_pages: number;
    total_items: number;
    items_per_page: number;
  };
};

function formatWhen(ts?: string) {
  if (!ts) return "";
  try {
    return new Date(ts).toLocaleString();
  } catch {
    return ts;
  }
}

function labelFromContact(contact: any): string | null {
  const candidates = [
    contact?.name,
    contact?.display_name,
    contact?.fullname,
    contact?.whatsapp_name,
    contact?.email,
    contact?.phone,
  ];
  const first = candidates.find((v) => typeof v === "string" && v.trim().length > 0);
  return first ? String(first).trim() : null;
}

function labelFromDeal(deal: any): string | null {
  const candidates = [deal?.title, deal?.name, deal?.company];
  const first = candidates.find((v) => typeof v === "string" && v.trim().length > 0);
  return first ? String(first).trim() : null;
}

function shortId(id: string, keep: number = 6) {
  const v = String(id || "").trim();
  if (!v) return "";
  return v.length <= keep * 2 + 3 ? v : `${v.slice(0, keep)}…${v.slice(-keep)}`;
}

function parseTime(value?: string): number {
  if (!value) return 0;
  const t = new Date(value).getTime();
  return Number.isFinite(t) ? t : 0;
}

function activityPreview(activity: any): string | null {
  const content = (activity?.content ?? {}) as Record<string, unknown>;
  const kind = String(activity?.kind ?? "").toLowerCase();

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

function toActivityDetail(item: TimelineItem): ActivityDetailData | null {
  if (item.type === "activity") {
    return ((item as any).activity ?? item) as ActivityDetailData;
  }
  if (item.type === "capture_entry") {
    const entry: any = (item as any).entry ?? item;
    const anchorModel = String(entry.anchor_model ?? "").trim().toLowerCase();
    const anchorId = entry.anchor_id ? String(entry.anchor_id) : "";
    return {
      id: `capture-${String(item.id)}`,
      title: entry.summary ? String(entry.summary) : "Captured note",
      kind: "note",
      created_at: item.created_at,
      user_id: entry.actor_id ? String(entry.actor_id) : null,
      visibility: entry.visibility ? String(entry.visibility) : undefined,
      status: entry.status ? String(entry.status) : "captured",
      content: {
        body: entry.raw_text ? String(entry.raw_text) : "",
        summary: entry.summary ? String(entry.summary) : "",
        capture_entry_id: String(entry.id ?? item.id),
      },
      contact_id: anchorModel === "crm.contact" && anchorId ? anchorId : null,
      customer_id: anchorModel === "crm.customer" && anchorId ? anchorId : null,
      deal_id: anchorModel === "crm.deal" && anchorId ? anchorId : null,
    };
  }
  return null;
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

function CaptureEntryCard({ item, onCaptureClick }: { item: TimelineItem; onCaptureClick?: (item: TimelineItem) => void }) {
  const { user } = useAuth();
  const entry: any = (item as any).entry ?? item;
  const raw = String(entry.raw_text ?? "").trim();
  const status = String(entry.status ?? "captured");
  const visibility = entry.visibility ? String(entry.visibility) : undefined;
  const summary = entry.summary ? String(entry.summary) : undefined;

  const anchorModel = String(entry.anchor_model ?? "").trim().toLowerCase();
  const anchorId = String(entry.anchor_id ?? "").trim();

  const actorId = entry.actor_id ? String(entry.actor_id) : "";
  const author = (() => {
    if (!actorId) return "—";
    if (user?.id && actorId === user.id) return "You";
    return `User ${shortId(actorId)}`;
  })();

  const anchorQuery = useQuery({
    queryKey: ["timeline", "anchor-label", anchorModel, anchorId],
    enabled: Boolean(anchorModel && anchorId && (anchorModel === "crm.contact" || anchorModel === "crm.deal")),
    queryFn: async () => {
      if (anchorModel === "crm.contact") {
        const c = await fetchJson<any>(apiV1(`/crm/contacts/${anchorId}/`));
        return { kind: "Contact" as const, label: labelFromContact(c), href: `/crm?tab=contacts&contactId=${encodeURIComponent(anchorId)}` };
      }
      const d = await fetchJson<any>(apiV1(`/crm/deals/${anchorId}/`));
      return { kind: "Deal" as const, label: labelFromDeal(d), href: "/deals" };
    },
    retry: false,
    staleTime: 10 * 60 * 1000,
  });

  const anchor = anchorQuery.data;
  const anchorText =
    anchor?.label ||
    (anchorModel && anchorId ? `${anchorModel} (${anchorId})` : null);

  return (
    <div
      className={cn(
        "w-full max-w-full p-4 rounded-lg border border-border/80 bg-card shadow-sm hover-elevate transition-all space-y-2",
        onCaptureClick && "cursor-pointer hover:bg-muted/30"
      )}
      onClick={() => {
        onCaptureClick?.(item);
      }}
      data-testid={`timeline-capture-${item.id}`}
    >
      <div className="flex items-start justify-between gap-2 min-w-0">
        <div className="flex items-center gap-2 min-w-0 flex-wrap">
          <StickyNote className="h-4 w-4 text-amber-600 shrink-0" />
          <Badge variant="secondary" className="shrink-0">Note</Badge>
          <Badge variant="outline" className="shrink-0 border-amber-300 text-amber-700">Captured</Badge>
          <Badge variant="outline" className="shrink-0">{status}</Badge>
          {visibility && <Badge variant="outline" className="shrink-0">{visibility}</Badge>}
        </div>
      </div>

      <div className="text-xs text-muted-foreground min-w-0 truncate">
        By <span className="text-foreground">{author}</span>
      </div>

      {anchorText && (
        <div className="text-xs text-muted-foreground min-w-0">
          {anchor?.href ? (
            <span className="truncate">
              Anchored to{" "}
              <Link
                href={anchor.href}
                className="text-foreground hover:underline"
                onClick={(event) => event.stopPropagation()}
              >
                {anchor.kind}: {anchorText}
              </Link>
            </span>
          ) : (
            <span className="truncate">Anchored to {anchorText}</span>
          )}
        </div>
      )}

      {summary ? (
        <div className="text-sm">{summary}</div>
      ) : raw ? (
        <div className="text-sm whitespace-pre-wrap break-words line-clamp-4">{raw}</div>
      ) : (
        <div className="text-sm text-muted-foreground">No content</div>
      )}
      <div className="text-xs text-muted-foreground text-right whitespace-nowrap">{formatWhen(item.created_at)}</div>
    </div>
  );
}

function ActivityCard({ item, onActivityClick }: { item: TimelineItem; onActivityClick?: (item: TimelineItem) => void }) {
  const { user } = useAuth();
  const title = (item as any).title ?? (item as any).name ?? (item as any)?.activity?.title ?? "Activity";
  const kind = (item as any).kind ?? (item as any).type ?? (item as any)?.activity?.kind;
  const Icon = activityIcon(kind);
  const activity: any = (item as any).activity ?? item;
  const preview = activityPreview(activity);
  const author = (() => {
    if (activity?.author && String(activity.author).trim()) return String(activity.author).trim();
    const actorId = activity?.user_id ? String(activity.user_id) : "";
    if (!actorId) return "—";
    if (user?.id && actorId === user.id) return "You";
    return `User ${shortId(actorId)}`;
  })();
  const hasRelated = activity?.contact_id || activity?.customer_id || activity?.deal_id;
  const createdWhen = formatWhen(item.created_at);

  return (
    <div
      className={cn(
        "w-full max-w-full p-4 rounded-lg border border-border/80 bg-card shadow-sm space-y-2",
        onActivityClick && "cursor-pointer hover:bg-muted/50 transition-colors"
      )}
      data-testid={`timeline-activity-${item.id}`}
      onClick={() => onActivityClick?.(item)}
      role={onActivityClick ? "button" : undefined}
    >
      <div className="flex items-center gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <Icon className={cn("h-4 w-4 shrink-0", String(kind || "").toLowerCase() === "note" ? "text-amber-600" : "text-muted-foreground")} />
          {kind && (
            <Badge variant="secondary" className="shrink-0 hidden min-[380px]:inline-flex">
              {String(kind)}
            </Badge>
          )}
          <span className="font-medium truncate">{String(title)}</span>
        </div>
      </div>
      <div className="text-xs text-muted-foreground min-w-0 truncate">
        By <span className="text-foreground">{author}</span>
      </div>
      {hasRelated && (
        <div className="text-xs text-muted-foreground flex flex-wrap gap-x-3 gap-y-1">
          {activity.contact_id && (
            <RelatedEntityLabel
              kind="contact"
              id={activity.contact_id}
              name={activity.contact_name}
              fallback="Contact"
              icon={<User className="h-3 w-3 inline mr-0.5 align-middle" />}
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
              icon={<Building2 className="h-3 w-3 inline mr-0.5 align-middle" />}
              href={`/crm?tab=accounts&accountId=${encodeURIComponent(activity.customer_id)}`}
              className="hover:underline text-primary"
            />
          )}
          {activity.deal_id && (
            <Link href={`/deals?dealId=${encodeURIComponent(activity.deal_id)}`} className="hover:underline text-primary">
              <Briefcase className="h-3 w-3 inline mr-0.5 align-middle" />
              {activity.deal_title || "Deal"}
            </Link>
          )}
        </div>
      )}
      {preview && <div className="text-xs text-muted-foreground line-clamp-2">{preview}</div>}
      <div className="text-xs text-muted-foreground text-right">{createdWhen}</div>
    </div>
  );
}

function FallbackCard({ item }: { item: TimelineItem }) {
  return (
    <div className="w-full max-w-full p-4 rounded-lg border border-border/80 bg-card shadow-sm space-y-2" data-testid={`timeline-item-${item.id}`}>
      <div className="flex items-start justify-between gap-2 min-w-0">
        <div className="flex items-center gap-2 min-w-0">
          <Badge variant="secondary" className="shrink-0">{String(item.type || "item")}</Badge>
          <span className="font-medium truncate">{item.id}</span>
        </div>
      </div>
      <span className="block text-xs text-muted-foreground text-right whitespace-nowrap">{formatWhen(item.created_at)}</span>
    </div>
  );
}

function TimelineItemCard({ item, onItemClick }: { item: TimelineItem; onItemClick?: (item: TimelineItem) => void }) {
  if (item.type === "capture_entry") return <CaptureEntryCard item={item} onCaptureClick={onItemClick} />;
  if (item.type === "activity") return <ActivityCard item={item} onActivityClick={onItemClick} />;
  return <FallbackCard item={item} />;
}

export function GlobalTimeline(props: {
  pageSize?: number;
  view?: "cards" | "table" | "calendar";
  onEditActivity?: (activity: any) => void;
  renderActivityEditForm?: (props: { activity: ActivityDetailData; onSaved: () => void; onCancel: () => void }) => React.ReactNode;
}) {
  const pageSize = props.pageSize ?? 20;
  const view = props.view ?? "cards";
  const [page, setPage] = useState(1);
  const [items, setItems] = useState<TimelineItem[]>([]);
  const [selectedDetail, setSelectedDetail] = useState<ActivityDetailData | null>(null);
  const [selectedDetailEditable, setSelectedDetailEditable] = useState(false);
  const [activityDetailOpen, setActivityDetailOpen] = useState(false);
  const [selectedCalendarDate, setSelectedCalendarDate] = useState<Date | undefined>(undefined);

  const handleItemClick = (item: TimelineItem) => {
    const detail = toActivityDetail(item);
    if (!detail) return;
    setSelectedDetail(detail);
    setSelectedDetailEditable(item.type === "activity");
    setActivityDetailOpen(true);
  };

  const mergeUnique = (prev: TimelineItem[], next: TimelineItem[]) => {
    const seen = new Set(prev.map((it) => `${it.type}-${it.id}`));
    const merged = [...prev];
    for (const it of next) {
      const key = `${it.type}-${it.id}`;
      if (seen.has(key)) continue;
      seen.add(key);
      merged.push(it);
    }
    return merged;
  };

  const query = useQuery<CaptureTimelinePage>({
    queryKey: ["timeline", "global", "merged", pageSize, page],
    queryFn: async () => {
      const capturePromise = captureApi.listEntries({ limit: pageSize, page });
      const activitiesPromise = fetchJson<any>(apiV1("/activities/"), {
        page,
        page_size: pageSize,
        sort_by: "created_at",
        order: "desc",
      });

      const [capture, activities] = await Promise.all([capturePromise, activitiesPromise]);

      const captureItems: TimelineItem[] = (capture.entries ?? []).map((entry) => ({
        type: "capture_entry",
        id: String(entry.id),
        created_at: entry.created_at,
        entry,
      }));

      const activityItems: TimelineItem[] = ((activities?.activities ?? []) as any[]).map((activity) => ({
        type: "activity",
        id: String(activity.id),
        created_at: activity.created_at,
        kind: activity.kind,
        title: activity.title,
        activity,
      }));

      const merged = [...captureItems, ...activityItems].sort((a, b) => {
        const dt = parseTime(getItemWhen(b)) - parseTime(getItemWhen(a));
        if (dt !== 0) return dt;
        return String(b.id).localeCompare(String(a.id));
      });

      return {
        items: merged,
        sources: {
          capture: capture.pagination
            ? { current_page: capture.pagination.current_page, total_pages: capture.pagination.total_pages }
            : undefined,
          activities: activities?.pagination
            ? { page: activities.pagination.page, total_pages: activities.pagination.total_pages }
            : undefined,
        },
      };
    },
    retry: false,
  });

  useEffect(() => {
    if (!query.data) return;
    const pageItems = query.data.items ?? [];
    setItems((prev) => (page > 1 ? mergeUnique(prev, pageItems) : pageItems));
  }, [query.data, page]);

  const canLoadMore = Boolean(
    (query.data?.sources?.capture &&
      query.data.sources.capture.current_page < query.data.sources.capture.total_pages) ||
      (query.data?.sources?.activities &&
        query.data.sources.activities.page < query.data.sources.activities.total_pages)
  );

  const handleLoadMore = () => {
    if (!canLoadMore) return;
    setPage((p) => p + 1);
  };

  const isInitialLoading = query.isLoading && page === 1 && items.length === 0;

  if (isInitialLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (query.error) {
    return (
      <div className="space-y-3">
        <ErrorDisplay
          error={query.error as Error}
          endpoint="/api/v1/capture/entries/"
          action={{ label: "Retry", onClick: () => query.refetch() }}
        />
        <div className="rounded-lg border p-4 text-sm text-muted-foreground flex items-start gap-2">
          <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
          <div>
            This feed is backed by capture entries. If you want a unified Activity + Capture timeline, the backend endpoint is anchor-scoped (`/api/v1/timeline/?anchor_model=...&anchor_id=...`).
          </div>
        </div>
      </div>
    );
  }

  if (!items || items.length === 0) {
    return (
      <EmptyState
        icon={Clock}
        title="No timeline yet"
        description="Report the first note to start building your timeline."
      />
    );
  }

  if (view === "table") {
    return (
      <>
        <GlobalTimelineTable
          items={items}
          isLoading={query.isFetching}
          canLoadMore={canLoadMore}
          onLoadMore={handleLoadMore}
          onEditActivity={props.onEditActivity}
          onItemClick={handleItemClick}
        />
        <ActivityDetailSheet
          open={activityDetailOpen}
          onOpenChange={setActivityDetailOpen}
          activity={selectedDetail}
          onEdit={selectedDetailEditable ? (a) => {
            setActivityDetailOpen(false);
            props.onEditActivity?.(a);
          } : undefined}
          renderActivityEditForm={selectedDetailEditable ? props.renderActivityEditForm : undefined}
        />
      </>
    );
  }

  if (view === "calendar") {
    const itemDates = items.reduce((acc, item) => {
      const when = getItemWhen(item);
      const key = getItemDayKey(when);
      if (!key) return acc;
      const list = acc.get(key) ?? [];
      list.push(item);
      acc.set(key, list);
      return acc;
    }, new Map<string, TimelineItem[]>());

    const calendarModifiers = {
      hasItem: (date: Date) => itemDates.has(getItemDayKey(date.toISOString())),
    };

    const filteredByDate = selectedCalendarDate
      ? items.filter((item) => {
          const when = getItemWhen(item);
          if (!when) return false;
          return isSameDay(new Date(when), selectedCalendarDate);
        })
      : items;

    return (
      <div className="grid grid-cols-1 lg:grid-cols-[auto_1fr] gap-6 h-full">
        <div className="lg:sticky lg:top-0 lg:self-start bg-card border rounded-lg p-4">
          <Calendar
            mode="single"
            selected={selectedCalendarDate}
            onSelect={setSelectedCalendarDate}
            defaultMonth={new Date()}
            modifiers={calendarModifiers}
            components={{
              IconLeft: ({ className, ...p }) => <ChevronLeft className={cn("h-4 w-4", className)} {...p} />,
              IconRight: ({ className, ...p }) => <ChevronRight className={cn("h-4 w-4", className)} {...p} />,
              DayContent: ({ date, activeModifiers }) => (
                <span className="flex flex-col items-center justify-center gap-0.5">
                  <span>{date.getDate()}</span>
                  {activeModifiers?.hasItem && (
                    <span className="w-1.5 h-1.5 rounded-full bg-primary shrink-0" aria-hidden />
                  )}
                </span>
              ),
            }}
            className="rounded-md"
          />
          {selectedCalendarDate && (
            <Button
              variant="ghost"
              size="sm"
              className="w-full mt-3"
              onClick={() => setSelectedCalendarDate(undefined)}
            >
              Show all
            </Button>
          )}
        </div>
        <div className="space-y-3 overflow-y-auto overflow-x-hidden">
          {selectedCalendarDate && (
            <p className="text-sm text-muted-foreground">
              {format(selectedCalendarDate, "MMMM d, yyyy")}
            </p>
          )}
          {filteredByDate.length === 0 ? (
            <EmptyState
              icon={CalendarDays}
              title="No items"
              description={selectedCalendarDate ? "No activities on this date" : "Select a date or create activities"}
            />
          ) : (
            <>
              {filteredByDate.map((item) => (
                <TimelineItemCard key={`${item.type}-${item.id}`} item={item} onItemClick={handleItemClick} />
              ))}
              {canLoadMore && (
                <Button variant="outline" onClick={handleLoadMore} disabled={query.isFetching}>
                  {query.isFetching && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                  Load more
                </Button>
              )}
            </>
          )}
        </div>
        <ActivityDetailSheet
          open={activityDetailOpen}
          onOpenChange={setActivityDetailOpen}
          activity={selectedDetail}
          onEdit={selectedDetailEditable ? (a) => {
            setActivityDetailOpen(false);
            props.onEditActivity?.(a);
          } : undefined}
          renderActivityEditForm={selectedDetailEditable ? props.renderActivityEditForm : undefined}
        />
      </div>
    );
  }

  return (
    <div className="space-y-3 overflow-x-hidden touch-pan-y">
      {items.map((item) => (
        <TimelineItemCard key={`${item.type}-${item.id}`} item={item} onItemClick={handleItemClick} />
      ))}
      <ActivityDetailSheet
        open={activityDetailOpen}
        onOpenChange={setActivityDetailOpen}
        activity={selectedDetail}
        onEdit={selectedDetailEditable ? (a) => {
          setActivityDetailOpen(false);
          props.onEditActivity?.(a);
        } : undefined}
        renderActivityEditForm={selectedDetailEditable ? props.renderActivityEditForm : undefined}
      />
      <div className="flex items-center justify-center pt-2">
        <Button variant="outline" onClick={handleLoadMore} disabled={!canLoadMore || query.isFetching}>
          {query.isFetching && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
          {canLoadMore ? "Load more" : "No more"}
        </Button>
      </div>
    </div>
  );
}

