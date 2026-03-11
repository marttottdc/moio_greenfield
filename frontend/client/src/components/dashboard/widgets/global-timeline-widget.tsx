import { Link } from "wouter";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Clock, Plus, ArrowRight, Loader2 } from "lucide-react";
import { GlassPanel } from "@/components/radiant/glass-panel";
import { Subheading } from "@/components/radiant/text";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/empty-state";
import { captureApi } from "@/lib/capture/captureApi";
import type { TimelineItem } from "@/lib/timeline/types";
import { ReportActivityModal } from "@/components/capture/ReportActivityModal";
import { fetchJson } from "@/lib/queryClient";
import { apiV1 } from "@/lib/api";

function formatWhen(ts?: string) {
  if (!ts) return "";
  try {
    return new Date(ts).toLocaleDateString();
  } catch {
    return ts;
  }
}

function shortId(id: string, keep = 6): string {
  const v = String(id || "").trim();
  if (!v) return "";
  return v.length <= keep * 2 + 3 ? v : `${v.slice(0, keep)}…${v.slice(-keep)}`;
}

function MiniTimelineRow({ item }: { item: TimelineItem }) {
  const label = (() => {
    if (item.type === "capture_entry") {
      const entry: any = (item as any).entry ?? item;
      return String(entry.summary ?? entry.raw_text ?? "Note");
    }
    if (item.type === "activity") {
      const kind = String((item as any).kind ?? (item as any).activity?.kind ?? "");
      const title = String((item as any).title ?? (item as any).name ?? (item as any).activity?.title ?? "Activity");
      return kind ? `${kind}: ${title}` : title;
    }
    return String(item.id);
  })();

  const author = (() => {
    if (item.type === "capture_entry") {
      const entry: any = (item as any).entry ?? item;
      const actorId = entry?.actor_id ? String(entry.actor_id) : "";
      return actorId ? `User ${shortId(actorId)}` : "—";
    }
    if (item.type === "activity") {
      const activity: any = (item as any).activity ?? item;
      if (activity?.author && String(activity.author).trim()) return String(activity.author).trim();
      const userId = activity?.user_id ? String(activity.user_id) : "";
      return userId ? `User ${shortId(userId)}` : "—";
    }
    return "—";
  })();

  const status = item.type === "capture_entry" ? String(((item as any).entry ?? item).status ?? "captured") : undefined;

  return (
    <div className="flex items-start justify-between gap-3 py-2 border-b last:border-b-0">
      <div className="min-w-0">
        <div className="text-sm truncate">{label}</div>
        <div className="text-xs text-muted-foreground flex items-center gap-2 flex-wrap">
          <span className="truncate">By {author}</span>
          <span className="truncate">· {formatWhen(item.created_at)}</span>
          {status && <Badge variant="outline" className="text-[10px]">{status}</Badge>}
        </div>
      </div>
    </div>
  );
}

export function GlobalTimelineWidget() {
  const [reportOpen, setReportOpen] = useState(false);

  const query = useQuery({
    queryKey: ["timeline", "global", "widget", "merged"],
    queryFn: async () => {
      const [capture, activities] = await Promise.all([
        captureApi.listEntries({ page: 1, limit: 6 }),
        fetchJson<any>(apiV1("/activities/"), { page: 1, page_size: 6, sort_by: "created_at", order: "desc" }),
      ]);

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

      const time = (v?: string) => {
        if (!v) return 0;
        const t = new Date(v).getTime();
        return Number.isFinite(t) ? t : 0;
      };

      const merged = [...captureItems, ...activityItems]
        .sort((a, b) => time(b.created_at) - time(a.created_at))
        .slice(0, 6);

      return { items: merged };
    },
    retry: false,
    staleTime: 30_000,
  });

  const items = query.data?.items ?? [];

  return (
    <GlassPanel className="p-6" data-testid="widget-global-timeline">
      <div className="flex items-center justify-between mb-4">
        <Subheading className="flex items-center gap-2">
          <Clock className="h-4 w-4" />
          Global Timeline
        </Subheading>
        <div className="flex items-center gap-2">
          <Button size="sm" variant="outline" onClick={() => setReportOpen(true)} data-testid="button-widget-report-activity">
            <Plus className="h-4 w-4 mr-1" />
            Log
          </Button>
          <Link href="/activities?tab=timeline">
            <Button size="sm" variant="ghost" className="text-xs" data-testid="link-widget-view-all-timeline">
              View all
              <ArrowRight className="h-3 w-3 ml-1" />
            </Button>
          </Link>
        </div>
      </div>

      {query.isLoading ? (
        <div className="flex items-center justify-center py-10">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      ) : items.length === 0 ? (
        <EmptyState
          icon={Clock}
          title="No timeline yet"
          description="Log what you did or what’s next to build your timeline."
        />
      ) : (
        <div className="rounded-lg border bg-card px-3">
          {items.slice(0, 6).map((it) => (
            <MiniTimelineRow key={`${it.type}-${it.id}`} item={it} />
          ))}
        </div>
      )}

      <ReportActivityModal open={reportOpen} onOpenChange={setReportOpen} />
    </GlassPanel>
  );
}

