import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Loader2, Clock, AlertTriangle, StickyNote, CheckSquare, Lightbulb, CalendarDays } from "lucide-react";
import { Link, useLocation } from "wouter";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/empty-state";
import { ErrorDisplay } from "@/components/error-display";
import { captureApi } from "@/lib/capture/captureApi";
import { fetchJson } from "@/lib/queryClient";
import { apiV1 } from "@/lib/api";
import type { TimelineItem } from "@/lib/timeline/types";
import { getItemWhen } from "@/lib/timeline/timelineRowModel";
import { useAuth } from "@/contexts/AuthContext";
import { cn } from "@/lib/utils";
import { GlobalTimelineTable } from "./GlobalTimelineTable";

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

type ActivityKind = "task" | "note" | "idea" | "event" | string;

function activityIcon(kind: ActivityKind) {
  const k = String(kind || "").toLowerCase();
  if (k === "task") return CheckSquare;
  if (k === "note") return StickyNote;
  if (k === "idea") return Lightbulb;
  if (k === "event") return CalendarDays;
  return Clock;
}

function CaptureEntryCard({ item }: { item: TimelineItem }) {
  const { user } = useAuth();
  const [, navigate] = useLocation();
  const entry: any = (item as any).entry ?? item;
  const raw = String(entry.raw_text ?? "").trim();
  const status = String(entry.status ?? "captured");
  const visibility = entry.visibility ? String(entry.visibility) : undefined;
  const summary = entry.summary ? String(entry.summary) : undefined;

  const anchorModel = String(entry.anchor_model ?? "").trim().toLowerCase();
  const anchorId = String(entry.anchor_id ?? "").trim();

  const actorId = entry.actor_id ? String(entry.actor_id) : "";
  const authorLabel = (() => {
    if (!actorId) return null;
    if (user?.id && actorId === user.id) return "You";
    // We only have actor_id in capture payload; show a stable fallback until we wire a user lookup.
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
        "p-4 rounded-lg border bg-card hover-elevate transition-all space-y-2",
        anchor?.href ? "cursor-pointer" : undefined
      )}
      onClick={() => {
        if (!anchor?.href) return;
        navigate(anchor.href);
      }}
      data-testid={`timeline-capture-${item.id}`}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <StickyNote className="h-4 w-4 text-amber-600 shrink-0" />
          <Badge variant="secondary" className="shrink-0">Note</Badge>
          <Badge variant="outline" className="shrink-0 border-amber-300 text-amber-700">Captured</Badge>
          <Badge variant="outline" className="shrink-0">{status}</Badge>
          {visibility && <Badge variant="outline" className="shrink-0">{visibility}</Badge>}
        </div>
        <span className="text-xs text-muted-foreground shrink-0">{formatWhen(item.created_at)}</span>
      </div>

      {authorLabel && (
        <div className="text-xs text-muted-foreground min-w-0 truncate">
          By <span className="text-foreground">{authorLabel}</span>
        </div>
      )}

      {anchorText && (
        <div className="text-xs text-muted-foreground min-w-0">
          {anchor?.href ? (
            <span className="truncate">
              Anchored to{" "}
              <Link href={anchor.href} className="text-foreground hover:underline">
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
    </div>
  );
}

function ActivityCard({ item }: { item: TimelineItem }) {
  const { user } = useAuth();
  const title = (item as any).title ?? (item as any).name ?? (item as any)?.activity?.title ?? "Activity";
  const kind = (item as any).kind ?? (item as any).type ?? (item as any)?.activity?.kind;
  const Icon = activityIcon(kind);
  const activity: any = (item as any).activity ?? item;
  const actorId = activity?.user_id ? String(activity.user_id) : "";
  const authorLabel = (() => {
    if (!actorId) return null;
    if (user?.id && actorId === user.id) return "You";
    return `User ${shortId(actorId)}`;
  })();

  return (
    <div className="p-4 rounded-lg border bg-card space-y-2" data-testid={`timeline-activity-${item.id}`}>
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <Icon className={cn("h-4 w-4 shrink-0", String(kind || "").toLowerCase() === "note" ? "text-amber-600" : "text-muted-foreground")} />
          {kind && <Badge variant="secondary" className="shrink-0">{String(kind)}</Badge>}
          <span className="font-medium truncate">{String(title)}</span>
        </div>
        <span className="text-xs text-muted-foreground shrink-0">{formatWhen(item.created_at)}</span>
      </div>
      {authorLabel && (
        <div className="text-xs text-muted-foreground min-w-0 truncate">
          By <span className="text-foreground">{authorLabel}</span>
        </div>
      )}
    </div>
  );
}

function FallbackCard({ item }: { item: TimelineItem }) {
  return (
    <div className="p-4 rounded-lg border bg-card space-y-2" data-testid={`timeline-item-${item.id}`}>
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <Badge variant="secondary" className="shrink-0">{String(item.type || "item")}</Badge>
          <span className="font-medium truncate">{item.id}</span>
        </div>
        <span className="text-xs text-muted-foreground shrink-0">{formatWhen(item.created_at)}</span>
      </div>
    </div>
  );
}

function TimelineItemCard({ item }: { item: TimelineItem }) {
  if (item.type === "capture_entry") return <CaptureEntryCard item={item} />;
  if (item.type === "activity") return <ActivityCard item={item} />;
  return <FallbackCard item={item} />;
}

export function GlobalTimeline(props: {
  pageSize?: number;
  view?: "cards" | "table";
  onEditActivity?: (activity: any) => void;
}) {
  const pageSize = props.pageSize ?? 20;
  const view = props.view ?? "cards";
  const [page, setPage] = useState(1);
  const [items, setItems] = useState<TimelineItem[]>([]);

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
      <GlobalTimelineTable
        items={items}
        isLoading={query.isFetching}
        canLoadMore={canLoadMore}
        onLoadMore={handleLoadMore}
        onEditActivity={props.onEditActivity}
      />
    );
  }

  return (
    <div className="space-y-3">
      {items.map((item) => (
        <TimelineItemCard key={`${item.type}-${item.id}`} item={item} />
      ))}
      <div className="flex items-center justify-center pt-2">
        <Button variant="outline" onClick={handleLoadMore} disabled={!canLoadMore || query.isFetching}>
          {query.isFetching && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
          {canLoadMore ? "Load more" : "No more"}
        </Button>
      </div>
    </div>
  );
}

