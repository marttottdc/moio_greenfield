import { useQuery } from "@tanstack/react-query";
import { Link, useLocation } from "wouter";
import {
  Loader2,
  StickyNote,
  CheckSquare,
  Lightbulb,
  CalendarDays,
  Clock,
  ExternalLink,
  Pencil,
  User,
  Building2,
  Briefcase,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { fetchJson } from "@/lib/queryClient";
import { apiV1 } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import type { TimelineItem } from "@/lib/timeline/types";
import type { TimelineRowModel } from "@/lib/timeline/types";
import { itemToRowModel, groupRowsByDay } from "@/lib/timeline/timelineRowModel";
import { format, isToday } from "date-fns";
import { cn } from "@/lib/utils";
import { RelatedEntityLabel } from "./TimelineItemCard";

function labelFromContact(contact: any): string | null {
  const candidates = [
    contact?.name,
    contact?.display_name,
    contact?.fullname,
    contact?.whatsapp_name,
    contact?.email,
    contact?.phone,
  ];
  const first = candidates.find((v) => typeof v === "string" && (v as string).trim().length > 0);
  return first ? String(first).trim() : null;
}

function labelFromDeal(deal: any): string | null {
  const candidates = [deal?.title, deal?.name, deal?.company];
  const first = candidates.find((v) => typeof v === "string" && (v as string).trim().length > 0);
  return first ? String(first).trim() : null;
}

function activityIcon(kind: TimelineRowModel["kind"]) {
  const k = String(kind || "").toLowerCase();
  if (k === "task") return CheckSquare;
  if (k === "note" || k === "note_captured") return StickyNote;
  if (k === "idea") return Lightbulb;
  if (k === "event") return CalendarDays;
  return Clock;
}

function AnchorCell({ row }: { row: TimelineRowModel }) {
  const { anchorModel, anchorId } = row;
  const [, navigate] = useLocation();
  const enabled = Boolean(
    anchorModel &&
      anchorId &&
      (anchorModel === "crm.contact" || anchorModel === "crm.deal")
  );
  const query = useQuery({
    queryKey: ["timeline-table", "anchor", anchorModel, anchorId],
    enabled,
    queryFn: async () => {
      if (anchorModel === "crm.contact") {
        const c = await fetchJson<any>(apiV1(`/crm/contacts/${anchorId}/`));
        const label = labelFromContact(c) || anchorId;
        return {
          kind: "Contact" as const,
          label,
          href: `/crm?tab=contacts&contactId=${encodeURIComponent(anchorId!)}`,
        };
      }
      const d = await fetchJson<any>(apiV1(`/crm/deals/${anchorId}/`));
      const label = labelFromDeal(d) || anchorId;
      return { kind: "Deal" as const, label, href: `/deals?dealId=${encodeURIComponent(anchorId!)}` };
    },
    retry: false,
    staleTime: 10 * 60 * 1000,
  });
  if (!enabled) return <span className="text-muted-foreground">—</span>;
  if (query.isLoading || !query.data) return <span className="text-muted-foreground">…</span>;
  return (
    <Button
      variant="ghost"
      className="h-auto min-h-0 py-0 px-0 text-xs text-foreground hover:underline"
      onClick={() => navigate(query.data!.href)}
    >
      {query.data!.kind}: {query.data!.label}
      <ExternalLink className="ml-0.5 h-3 w-3" />
    </Button>
  );
}

function OpenAnchorButton({ row }: { row: TimelineRowModel }) {
  const [, navigate] = useLocation();
  const { anchorModel, anchorId } = row;
  const enabled = Boolean(
    anchorModel &&
      anchorId &&
      (anchorModel === "crm.contact" || anchorModel === "crm.deal")
  );
  const query = useQuery({
    queryKey: ["timeline-table", "anchor", anchorModel, anchorId],
    enabled,
    queryFn: async () => {
      if (anchorModel === "crm.contact") {
        const c = await fetchJson<any>(apiV1(`/crm/contacts/${anchorId}/`));
        const label = labelFromContact(c) || anchorId;
        return {
          kind: "Contact" as const,
          label,
          href: `/crm?tab=contacts&contactId=${encodeURIComponent(anchorId!)}`,
        };
      }
      const d = await fetchJson<any>(apiV1(`/crm/deals/${anchorId}/`));
      const label = labelFromDeal(d) || anchorId;
      return { kind: "Deal" as const, label, href: `/deals?dealId=${encodeURIComponent(anchorId!)}` };
    },
    retry: false,
    staleTime: 10 * 60 * 1000,
  });
  if (!enabled || !query.data) return null;
  return (
    <Button
      variant="outline"
      size="sm"
      className="h-6 px-1.5 text-xs"
      onClick={() => navigate(query.data!.href)}
    >
      <ExternalLink className="h-2.5 w-2.5 mr-0.5" />
      Open
    </Button>
  );
}

export function GlobalTimelineTable(props: {
  items: TimelineItem[];
  isLoading: boolean;
  canLoadMore: boolean;
  onLoadMore: () => void;
  onEditActivity?: (activity: any) => void;
  onActivityClick?: (item: TimelineItem) => void;
}) {
  const { user } = useAuth();
  const rows = props.items.map((item) => itemToRowModel(item, user?.id ?? null));
  const byDay = groupRowsByDay(rows);
  const dayKeys = Array.from(byDay.keys()).filter(Boolean).sort((a, b) => b.localeCompare(a));
  if (byDay.has("no-date")) dayKeys.push("no-date");

  const compactTable = "text-xs";
  const compactHead = "h-8 px-2 text-xs font-medium text-muted-foreground";
  const compactCell = "p-2 align-middle text-xs";

  return (
    <div className="space-y-4">
      {dayKeys.map((dayKey) => {
        const dayRows = byDay.get(dayKey) ?? [];
        const isTodayDate = dayKey && isToday(new Date(dayKey + "T12:00:00"));
        const dayLabel = dayKey
          ? format(new Date(dayKey + "T12:00:00"), "EEEE, MMM d, yyyy")
          : "No date";
        return (
          <div key={dayKey || "no-date"} className="space-y-1">
            <div className="flex items-center gap-1.5">
              <h3 className="text-xs font-medium">{dayLabel}</h3>
              {isTodayDate && (
                <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
                  Today
                </Badge>
              )}
            </div>
            <Table className={compactTable}>
              <TableHeader>
                <TableRow className="border-b">
                  <TableHead className={`w-[72px] ${compactHead}`}>When</TableHead>
                  <TableHead className={`w-[120px] ${compactHead}`}>Type</TableHead>
                  <TableHead className={compactHead}>Title / Summary</TableHead>
                  <TableHead className={`w-[140px] ${compactHead}`}>Anchor</TableHead>
                  <TableHead className={`w-[80px] ${compactHead}`}>Author</TableHead>
                  <TableHead className={`w-[72px] ${compactHead}`}>Status</TableHead>
                  <TableHead className={`w-[72px] ${compactHead}`}>Visibility</TableHead>
                  <TableHead className={`w-[100px] text-right ${compactHead}`}>Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {dayRows.map((row) => {
                  const Icon = activityIcon(row.kind);
                  const isCaptured = row.kind === "note_captured";
                  const isActivity = row.type === "activity";
                  const activity = isActivity ? (row.item as any).activity ?? row.item : null;
                  return (
                    <TableRow
                      key={`${row.type}-${row.id}`}
                      className={cn(
                        "border-b",
                        isActivity && props.onActivityClick && "cursor-pointer hover:bg-muted/50"
                      )}
                      onClick={() => isActivity && props.onActivityClick?.(row.item)}
                    >
                      <TableCell className={`${compactCell} text-muted-foreground`}>
                        {row.whenDisplay}
                      </TableCell>
                      <TableCell className={compactCell}>
                        <div className="flex items-center gap-1 flex-wrap">
                          <Icon
                            className={`h-3.5 w-3.5 shrink-0 ${
                              isCaptured ? "text-amber-600" : "text-muted-foreground"
                            }`}
                          />
                          <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
                            {isCaptured ? "Note" : row.kind}
                          </Badge>
                          {isCaptured && (
                            <Badge
                              variant="outline"
                              className="text-[10px] px-1.5 py-0 border-amber-300 text-amber-700"
                            >
                              Captured
                            </Badge>
                          )}
                        </div>
                      </TableCell>
                      <TableCell
                        className={`${compactCell} max-w-[240px] truncate`}
                        title={row.titleSummary}
                      >
                        {row.titleSummary}
                      </TableCell>
                      <TableCell className={compactCell} onClick={(e) => e.stopPropagation()}>
                        {row.anchorModel && row.anchorId ? (
                          <AnchorCell row={row} />
                        ) : isActivity && activity ? (
                          <div className="flex flex-wrap gap-x-2 gap-y-0.5">
                            {activity.contact_id && (
                              <RelatedEntityLabel
                                kind="contact"
                                id={activity.contact_id}
                                name={activity.contact_name}
                                fallback="Contact"
                                icon={<User className="h-3 w-3 inline mr-0.5" />}
                                href={`/crm?tab=contacts&contactId=${encodeURIComponent(activity.contact_id)}`}
                                className="text-primary hover:underline text-xs"
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
                                className="text-primary hover:underline text-xs"
                              />
                            )}
                            {activity.deal_id && (
                              <Link href={`/deals?dealId=${encodeURIComponent(activity.deal_id)}`} className="text-primary hover:underline text-xs">
                                <Briefcase className="h-3 w-3 inline mr-0.5" />
                                {activity.deal_title || "Deal"}
                              </Link>
                            )}
                            {!(activity.contact_id || activity.customer_id || activity.deal_id) && (
                              <span className="text-muted-foreground">—</span>
                            )}
                          </div>
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </TableCell>
                      <TableCell className={`${compactCell} text-muted-foreground`}>
                        {row.author || "—"}
                      </TableCell>
                      <TableCell className={compactCell}>
                        <Badge variant="outline" className="text-[10px] px-1.5 py-0">
                          {row.status}
                        </Badge>
                      </TableCell>
                      <TableCell className={`${compactCell} text-muted-foreground`}>
                        {row.visibility}
                      </TableCell>
                      <TableCell className={`${compactCell} text-right`} onClick={(e) => e.stopPropagation()}>
                        <div className="flex items-center justify-end gap-0.5">
                          <OpenAnchorButton row={row} />
                          {isActivity && activity && props.onEditActivity && (
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-6 min-h-0 px-1.5 text-xs"
                              onClick={(e) => {
                                e.stopPropagation();
                                props.onEditActivity?.(activity);
                              }}
                            >
                              <Pencil className="h-2.5 w-2.5 mr-0.5" />
                              Edit
                            </Button>
                          )}
                        </div>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        );
      })}
      <div className="flex justify-center pt-1">
        <Button
          variant="outline"
          size="sm"
          className="text-xs"
          onClick={props.onLoadMore}
          disabled={!props.canLoadMore || props.isLoading}
        >
          {props.isLoading && <Loader2 className="h-3 w-3 mr-1.5 animate-spin" />}
          {props.canLoadMore ? "Load more" : "No more"}
        </Button>
      </div>
    </div>
  );
}
