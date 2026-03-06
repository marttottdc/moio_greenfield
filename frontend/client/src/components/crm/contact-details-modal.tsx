"use client";

import { useQuery } from "@tanstack/react-query";
import {
  Zap,
  MessageSquare,
  Bell,
  Phone,
  Mail,
  Building2,
  Loader2,
  Pencil,
  StickyNote,
  CheckSquare,
  Lightbulb,
  CalendarDays,
  Clock,
  User,
  Briefcase,
  ExternalLink,
} from "lucide-react";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ScrollArea } from "@/components/ui/scroll-area";
import { EmptyState } from "@/components/empty-state";
import { fetchJson } from "@/lib/queryClient";
import { apiV1 } from "@/lib/api";
import { timelineApi } from "@/lib/timeline/timelineApi";
import type { TimelineItem } from "@/lib/timeline/types";
import { useAuth } from "@/contexts/AuthContext";
import { Link } from "wouter";
import { cn } from "@/lib/utils";

export interface ContactDetailsContact {
  id: string;
  name: string;
  email?: string | null;
  phone?: string | null;
  company?: string | null;
  type?: string | null;
  tags?: string[];
  address?: string | null;
  activity_summary?: {
    total_deals?: number;
    total_tickets?: number;
    total_messages?: number;
    last_contact?: string;
  };
}

export interface ContactDetailsModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  contactId: string | null;
  initialContact?: ContactDetailsContact | null;
  onEdit?: (contact: ContactDetailsContact) => void;
}

interface DealLite {
  id: string;
  title: string;
  value?: number | null;
  currency?: string | null;
  stage?: string | null;
  stage_id?: string | null;
  stage_name?: string | null;
  contact_id?: string | null;
  contact?: string | null;
  updated_at?: string;
}

interface ConversationLite {
  id: string;
  contact?: { id?: string; name?: string; phone?: string; email?: string };
  channel?: string;
  status?: string;
  last_message?: { content?: string; timestamp?: string };
  updated_at?: string;
  summary?: string;
}

function formatTimelineDateShort(ts?: string): string {
  if (!ts) return "";
  try {
    const d = new Date(ts);
    return d.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit", hour12: true });
  } catch {
    return ts;
  }
}

function getStatusPill(contact: ContactDetailsContact): { label: string; variant: "default" | "secondary" | "outline" | "destructive"; className?: string } {
  const last = contact.activity_summary?.last_contact;
  if (!last) return { label: "Up to Date", variant: "outline", className: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 border-emerald-300" };
  try {
    const days = (Date.now() - new Date(last).getTime()) / (24 * 60 * 60 * 1000);
    if (days <= 7) return { label: "Up to Date", variant: "outline", className: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 border-emerald-300" };
    if (days <= 30) return { label: "Recent", variant: "secondary" };
  } catch {}
  return { label: "Needs attention", variant: "outline", className: "text-amber-700 dark:text-amber-400" };
}

function parseTime(value?: string): number {
  if (!value) return 0;
  const t = new Date(value).getTime();
  return Number.isFinite(t) ? t : 0;
}

function groupByDate(items: { created_at?: string }[]): Map<string, { created_at?: string }[]> {
  const map = new Map<string, { created_at?: string }[]>();
  for (const item of items) {
    const key = item.created_at ? new Date(item.created_at).toISOString().slice(0, 10) : "unknown";
    const list = map.get(key) ?? [];
    list.push(item);
    map.set(key, list);
  }
  for (const list of map.values()) {
    list.sort((a, b) => parseTime(b.created_at) - parseTime(a.created_at));
  }
  return map;
}

function shortId(id: string, keep = 6): string {
  const v = String(id || "").trim();
  if (!v) return "";
  return v.length <= keep * 2 + 3 ? v : `${v.slice(0, keep)}…${v.slice(-keep)}`;
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

function TimelineEventCard({ item }: { item: TimelineItem }) {
  const { user } = useAuth();
  if (item.type === "capture_entry") {
    const entry: any = (item as any).entry ?? item;
    const summary = entry.summary ? String(entry.summary) : String(entry.raw_text ?? "").trim();
    const status = String(entry.status ?? "captured");
    return (
      <div className="p-3 rounded-lg border bg-card text-sm space-y-1">
        <div className="flex items-center justify-between gap-2">
          <StickyNote className="h-4 w-4 text-amber-600 shrink-0" />
          <Badge variant="outline" className="text-xs">{status}</Badge>
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
    const actorId = activity?.user_id ? String(activity.user_id) : "";
    const authorLabel = !actorId ? null : user?.id && actorId === user.id ? "You" : `User ${shortId(actorId)}`;
    return (
      <div className="p-3 rounded-lg border bg-card space-y-1" data-testid={`timeline-activity-${item.id}`}>
        <div className="flex items-center gap-2 min-w-0">
          <Icon className={cn("h-4 w-4 shrink-0", String(kind || "").toLowerCase() === "note" ? "text-amber-600" : "text-muted-foreground")} />
          {kind && <Badge variant="secondary" className="text-xs">{String(kind)}</Badge>}
          <span className="font-medium truncate">{String(title)}</span>
        </div>
        {authorLabel && <p className="text-xs text-muted-foreground">By <span className="text-foreground">{authorLabel}</span></p>}
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

function DealCard({ deal }: { deal: DealLite }) {
  const valueStr =
    typeof deal.value === "number"
      ? new Intl.NumberFormat(undefined, { style: "currency", currency: deal.currency ?? "USD" }).format(deal.value)
      : deal.value ?? "—";
  return (
    <Link href="/deals">
      <div className="p-3 rounded-lg border bg-card text-sm space-y-2 hover:bg-muted/50 transition-colors cursor-pointer" data-testid={`deal-${deal.id}`}>
        <div className="flex items-center justify-between gap-2">
          <span className="font-medium truncate">{deal.title}</span>
          <ExternalLink className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {(deal.stage_name ?? deal.stage) && (
            <Badge variant="secondary" className="text-xs">{deal.stage_name ?? deal.stage}</Badge>
          )}
          <span className="text-xs text-muted-foreground">{valueStr}</span>
        </div>
      </div>
    </Link>
  );
}

function ConversationCard({ conv, contactId }: { conv: ConversationLite; contactId: string }) {
  const preview = conv.last_message?.content?.trim() || conv.summary || "No messages yet";
  const ts = conv.updated_at ?? conv.last_message?.timestamp;
  return (
    <Link href={`/communications?conversation=${encodeURIComponent(conv.id)}`}>
      <div className="p-3 rounded-lg border bg-card text-sm space-y-2 hover:bg-muted/50 transition-colors cursor-pointer" data-testid={`conversation-${conv.id}`}>
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 min-w-0">
            <MessageSquare className="h-4 w-4 text-muted-foreground shrink-0" />
            <Badge variant="outline" className="text-xs">{conv.channel ?? "Chat"}</Badge>
          </div>
          <span className="text-xs text-muted-foreground shrink-0">{ts ? formatTimelineDateShort(ts) : ""}</span>
        </div>
        <p className="text-muted-foreground line-clamp-2">{preview}</p>
      </div>
    </Link>
  );
}

function NotificationEventCard({ item }: { item: TimelineItem }) {
  const title = (item as any).title ?? (item as any).message ?? String((item as any).type ?? "Notification");
  return (
    <div className="p-3 rounded-lg border bg-card space-y-1" data-testid={`timeline-notification-${item.id}`}>
      <div className="flex items-center gap-2 min-w-0">
        <Bell className="h-4 w-4 shrink-0 text-muted-foreground" />
        <span className="font-medium truncate text-sm">{title}</span>
      </div>
    </div>
  );
}

function VerticalTimelineRail({ children }: { children: React.ReactNode }) {
  return (
    <div className="relative pl-6">
      <div className="absolute left-[5px] top-0 bottom-0 w-px bg-border" />
      <div className="space-y-4">
        {children}
      </div>
    </div>
  );
}

function TimelineNode({ timestamp, children }: { timestamp: string; children: React.ReactNode }) {
  return (
    <div className="relative flex gap-3">
      <div className="absolute left-[-21px] top-1 h-2.5 w-2.5 rounded-full bg-primary border-2 border-background" />
      <div className="flex-1 min-w-0 space-y-2">
        <p className="text-xs text-muted-foreground">{timestamp}</p>
        {children}
      </div>
    </div>
  );
}

export function ContactDetailsModal({
  open,
  onOpenChange,
  contactId,
  initialContact,
  onEdit,
}: ContactDetailsModalProps) {
  const contactQuery = useQuery({
    queryKey: [apiV1("/crm/contacts/"), "detail", contactId],
    queryFn: () => fetchJson<ContactDetailsContact>(apiV1(`/crm/contacts/${contactId}/`)),
    enabled: open && Boolean(contactId) && !initialContact,
    retry: false,
    staleTime: 2 * 60 * 1000,
  });

  const contact = initialContact ?? contactQuery.data ?? null;

  const timelineQuery = useQuery({
    queryKey: ["timeline", "contact", contactId],
    queryFn: () => timelineApi.listForAnchor({ anchor_model: "crm.contact", anchor_id: contactId!, limit: 50 }),
    enabled: open && Boolean(contactId),
    retry: false,
    staleTime: 60 * 1000,
  });

  const dealsQuery = useQuery({
    queryKey: [apiV1("/crm/deals/"), "by-contact", contactId],
    queryFn: async () => {
      const raw = await fetchJson<any>(apiV1("/crm/deals/"), { contact_id: contactId ?? "", page_size: 100 });
      const list: DealLite[] = raw?.deals ?? raw?.results ?? raw?.items ?? [];
      return list.filter(
        (d: any) => String(d.contact_id ?? d.contact ?? "").trim() === String(contactId ?? "").trim()
      ) as DealLite[];
    },
    enabled: open && Boolean(contactId),
    retry: false,
    staleTime: 60 * 1000,
  });

  const conversationsQuery = useQuery({
    queryKey: [apiV1("/crm/communications/conversations/"), "by-contact", contactId],
    queryFn: async () => {
      const raw = await fetchJson<{ conversations?: ConversationLite[] }>(apiV1("/crm/communications/conversations/"), {
        page: 1,
        page_size: 100,
      });
      const list = raw?.conversations ?? [];
      return list.filter((c) => String(c.contact?.id ?? "").trim() === String(contactId ?? "").trim()) as ConversationLite[];
    },
    enabled: open && Boolean(contactId),
    retry: false,
    staleTime: 60 * 1000,
  });

  const timelineItems = timelineQuery.data?.items ?? [];
  const deals = dealsQuery.data ?? [];
  const conversations = conversationsQuery.data ?? [];
  const activityItems = timelineItems.filter((i) => i.type === "capture_entry" || i.type === "activity");
  const notificationItems = timelineItems.filter((i) => {
    const t = String((i as any).type ?? "").toLowerCase();
    return t.includes("notification") || t.includes("audit") || t.includes("system");
  });

  const activityByDate = groupByDate(activityItems);
  const notificationByDate = groupByDate(notificationItems);

  const statusPill = contact ? getStatusPill(contact) : null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="max-w-5xl w-[95vw] h-[85vh] p-0 gap-0 overflow-hidden flex flex-col"
        data-testid="dialog-contact-details"
      >
        <div className="grid grid-cols-1 md:grid-cols-[20rem_1fr] flex-1 overflow-hidden min-h-0">
          {/* Left: Profile */}
          <ScrollArea className="border-r bg-muted/30">
            <div className="p-5 space-y-5">
              {contactQuery.isLoading && !initialContact ? (
                <div className="flex items-center justify-center py-12">
                  <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                </div>
              ) : contact ? (
                <>
                  <div className="flex flex-col items-center text-center">
                    <div className="h-20 w-20 rounded-full bg-primary/10 flex items-center justify-center text-2xl font-semibold text-primary mb-2">
                      {contact.name?.charAt(0).toUpperCase() ?? "?"}
                    </div>
                    <h2 className="text-lg font-semibold leading-tight">{contact.name}</h2>
                    {statusPill && (
                      <Badge variant={statusPill.variant} className={cn("mt-1", statusPill.className)}>
                        {statusPill.label}
                      </Badge>
                    )}
                  </div>

                  {contact.tags && contact.tags.length > 0 && (
                    <div>
                      <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">Groups</h3>
                      <div className="flex flex-wrap gap-2">
                        {contact.tags.map((tag) => (
                          <span
                            key={tag}
                            className="inline-flex items-center gap-1.5 rounded-full bg-muted px-2.5 py-1 text-xs font-medium"
                          >
                            <User className="h-3.5 w-3.5 text-muted-foreground" />
                            {tag}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  <div className="space-y-2">
                    {[contact.phone].filter(Boolean).map((p, i) => (
                      <div key={i} className="flex items-center gap-2 text-sm">
                        <Phone className="h-4 w-4 text-muted-foreground shrink-0" />
                        <span>{p}</span>
                      </div>
                    ))}
                    {contact.email && (
                      <div className="flex items-center gap-2 text-sm">
                        <Mail className="h-4 w-4 text-muted-foreground shrink-0" />
                        <span className="break-all">{contact.email}</span>
                      </div>
                    )}
                  </div>

                  {(contact.company || contact.address) && (
                    <div className="space-y-2">
                      {contact.company && (
                        <div className="flex items-center gap-2 text-sm">
                          <Building2 className="h-4 w-4 text-muted-foreground shrink-0" />
                          <span>{contact.company}</span>
                        </div>
                      )}
                      {contact.address && (
                        <div className="flex items-center gap-2 text-sm">
                          <Building2 className="h-4 w-4 text-muted-foreground shrink-0" />
                          <span className="break-words">{contact.address}</span>
                        </div>
                      )}
                    </div>
                  )}

                  {onEdit && (
                    <Button variant="outline" size="sm" className="w-full" onClick={() => onEdit(contact)} data-testid="button-contact-details-edit">
                      <Pencil className="h-4 w-4 mr-2" />
                      Edit contact
                    </Button>
                  )}
                </>
              ) : (
                <div className="py-8 text-center text-sm text-muted-foreground">No contact selected</div>
              )}
            </div>
          </ScrollArea>

          {/* Right: Tabs + Timeline */}
          <div className="flex flex-col min-h-0">
            <Tabs defaultValue="activity" className="flex flex-col flex-1 min-h-0">
              <TabsList className="w-full justify-start rounded-none border-b bg-transparent p-0 h-11 gap-0">
                <TabsTrigger value="activity" className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-muted/50" data-testid="tab-activity">
                  <Zap className="h-4 w-4 mr-2" />
                  Activity
                </TabsTrigger>
                <TabsTrigger value="messages" className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-muted/50" data-testid="tab-messages">
                  <MessageSquare className="h-4 w-4 mr-2" />
                  Messages
                </TabsTrigger>
                <TabsTrigger value="deals" className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-muted/50" data-testid="tab-deals">
                  <Briefcase className="h-4 w-4 mr-2" />
                  Deals
                </TabsTrigger>
                <TabsTrigger value="notifications" className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-muted/50" data-testid="tab-notifications">
                  <Bell className="h-4 w-4 mr-2" />
                  Notifications
                </TabsTrigger>
              </TabsList>

              <TabsContent value="activity" className="flex-1 m-0 overflow-hidden data-[state=inactive]:hidden">
                <ScrollArea className="h-full p-4">
                  {timelineQuery.isLoading ? (
                    <div className="flex items-center justify-center py-12">
                      <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                    </div>
                  ) : activityItems.length === 0 ? (
                    <EmptyState icon={Zap} title="No activity" description="Activity for this contact will appear here." />
                  ) : (
                    <VerticalTimelineRail>
                      {Array.from(activityByDate.entries())
                        .sort(([a], [b]) => b.localeCompare(a))
                        .flatMap(([, items]) =>
                          items.map((item) => (
                            <TimelineNode key={`${(item as TimelineItem).type}-${(item as TimelineItem).id}`} timestamp={formatTimelineDateShort((item as TimelineItem).created_at)}>
                              <TimelineEventCard item={item as TimelineItem} />
                            </TimelineNode>
                          ))
                        )}
                    </VerticalTimelineRail>
                  )}
                </ScrollArea>
              </TabsContent>

              <TabsContent value="messages" className="flex-1 m-0 overflow-hidden data-[state=inactive]:hidden">
                <ScrollArea className="h-full p-4">
                  {conversationsQuery.isLoading ? (
                    <div className="flex items-center justify-center py-12">
                      <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                    </div>
                  ) : conversations.length === 0 ? (
                    <EmptyState icon={MessageSquare} title="No conversations" description="Conversations with this contact will appear here." />
                  ) : (
                    <div className="space-y-3">
                      {conversations
                        .sort((a, b) => parseTime(b.updated_at ?? b.last_message?.timestamp) - parseTime(a.updated_at ?? a.last_message?.timestamp))
                        .map((conv) => (
                          <ConversationCard key={conv.id} conv={conv} contactId={contactId ?? ""} />
                        ))}
                    </div>
                  )}
                </ScrollArea>
              </TabsContent>

              <TabsContent value="deals" className="flex-1 m-0 overflow-hidden data-[state=inactive]:hidden">
                <ScrollArea className="h-full p-4">
                  {dealsQuery.isLoading ? (
                    <div className="flex items-center justify-center py-12">
                      <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                    </div>
                  ) : deals.length === 0 ? (
                    <EmptyState icon={Briefcase} title="No deals" description="Deals associated with this contact will appear here." />
                  ) : (
                    <div className="space-y-3">
                      {deals.map((deal) => (
                        <DealCard key={deal.id} deal={deal} />
                      ))}
                    </div>
                  )}
                </ScrollArea>
              </TabsContent>

              <TabsContent value="notifications" className="flex-1 m-0 overflow-hidden data-[state=inactive]:hidden">
                <ScrollArea className="h-full p-4">
                  {timelineQuery.isLoading ? (
                    <div className="flex items-center justify-center py-12">
                      <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                    </div>
                  ) : notificationItems.length === 0 ? (
                    <EmptyState icon={Bell} title="No notifications" description="Notifications for this contact will appear here." />
                  ) : (
                    <VerticalTimelineRail>
                      {Array.from(notificationByDate.entries())
                        .sort(([a], [b]) => b.localeCompare(a))
                        .flatMap(([, items]) =>
                          items.map((item) => (
                            <TimelineNode key={`n-${(item as TimelineItem).id}`} timestamp={formatTimelineDateShort((item as TimelineItem).created_at)}>
                              <NotificationEventCard item={item as TimelineItem} />
                            </TimelineNode>
                          ))
                        )}
                    </VerticalTimelineRail>
                  )}
                </ScrollArea>
              </TabsContent>
            </Tabs>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
