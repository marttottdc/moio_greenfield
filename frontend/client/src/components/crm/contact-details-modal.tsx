"use client";

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  Zap,
  MessageSquare,
  Bell,
  Phone,
  Mail,
  Building2,
  Loader2,
  Pencil,
  User,
  Briefcase,
  ExternalLink,
  MapPin,
  ChevronRight,
} from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { EmptyState } from "@/components/empty-state";
import { fetchJson, apiRequest, queryClient } from "@/lib/queryClient";
import { apiV1 } from "@/lib/api";
import { timelineApi } from "@/lib/timeline/timelineApi";
import type { TimelineItem } from "@/lib/timeline/types";
import { TimelineItemCard, ActivityDetailSheet, type ActivityDetailData } from "@/components/timeline/TimelineItemCard";
import { Link } from "wouter";
import { cn } from "@/lib/utils";
import { useToast } from "@/hooks/use-toast";

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

interface DealDetail {
  id: string;
  title: string;
  description?: string | null;
  stage?: string | null;
  stage_name?: string | null;
  status?: string | null;
  value?: number | null;
  currency?: string | null;
  expected_close_date?: string | null;
  updated_at?: string | null;
  pipeline?: string | null;
  stage?: string | null;
}

interface StageOption {
  id: string;
  name: string;
  is_won_stage?: boolean;
  is_lost_stage?: boolean;
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

function formatRelativeDate(ts?: string | null): string {
  if (!ts) return "—";
  try {
    const d = new Date(ts);
    const now = Date.now();
    const diffMs = now - d.getTime();
    const days = Math.floor(diffMs / (1000 * 60 * 60 * 24));
    if (days < 1) return "Today";
    if (days === 1) return "Yesterday";
    if (days < 7) return `${days} days ago`;
    if (days < 30) {
      const weeks = Math.floor(days / 7);
      return weeks === 1 ? "About 1 week ago" : `About ${weeks} weeks ago`;
    }
    if (days < 365) {
      const months = Math.floor(days / 30);
      return months === 1 ? "About 1 month ago" : `About ${months} months ago`;
    }
    const years = Math.floor(days / 365);
    return years === 1 ? "About 1 year ago" : `About ${years} years ago`;
  } catch {
    return ts ?? "—";
  }
}

function getStatusPill(
  contact: ContactDetailsContact,
  t: (key: string) => string,
): { label: string; variant: "default" | "secondary" | "outline" | "destructive"; className?: string } {
  const last = contact.activity_summary?.last_contact;
  if (!last)
    return {
      label: t("contact.up_to_date"),
      variant: "outline",
      className: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 border-emerald-300",
    };
  try {
    const days = (Date.now() - new Date(last).getTime()) / (24 * 60 * 60 * 1000);
    if (days <= 7)
      return {
        label: t("contact.up_to_date"),
        variant: "outline",
        className: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 border-emerald-300",
      };
    if (days <= 30) return { label: t("contact.recent"), variant: "secondary" };
  } catch {}
  return { label: t("contact.needs_attention"), variant: "outline", className: "text-amber-700 dark:text-amber-400" };
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

function VerticalTimelineRail({ children }: { children: React.ReactNode }) {
  return (
    <div className="relative pl-5 md:pl-6">
      <div className="absolute left-[3px] md:left-[5px] top-0 bottom-0 w-px bg-border" />
      <div className="space-y-4">{children}</div>
    </div>
  );
}

function TimelineNode({ timestamp, children }: { timestamp: string; children: React.ReactNode }) {
  return (
    <div className="relative flex gap-3">
      <div className="absolute left-[-19px] md:left-[-21px] top-1 h-2.5 w-2.5 rounded-full bg-primary border-2 border-background" />
      <div className="flex-1 min-w-0 space-y-2">
        <p className="text-xs text-muted-foreground">{timestamp}</p>
        {children}
      </div>
    </div>
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

function SidebarSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="space-y-2">
      <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">{title}</h3>
      {children}
    </div>
  );
}

function InfoRow({ icon: Icon, children }: { icon: React.ElementType; children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-2.5 text-sm">
      <Icon className="h-4 w-4 text-muted-foreground shrink-0 mt-0.5" />
      <span className="break-all">{children}</span>
    </div>
  );
}

function DealCard({ deal, onOpen }: { deal: DealLite; onOpen: (dealId: string) => void }) {
  const valueStr =
    typeof deal.value === "number"
      ? new Intl.NumberFormat(undefined, { style: "currency", currency: deal.currency ?? "USD" }).format(deal.value)
      : deal.value ?? "—";
  return (
    <button
      type="button"
      onClick={() => onOpen(deal.id)}
      className="w-full text-left p-3 rounded-lg border bg-card text-sm space-y-1.5 hover:bg-muted/50 transition-colors cursor-pointer"
      data-testid={`deal-${deal.id}`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="font-medium truncate">{deal.title}</span>
        <ExternalLink className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
      </div>
      <div className="flex items-center gap-2 flex-wrap">
        {(deal.stage_name ?? deal.stage) && (
          <Badge variant="secondary" className="text-xs">
            {deal.stage_name ?? deal.stage}
          </Badge>
        )}
        <span className="text-xs text-muted-foreground">{valueStr}</span>
      </div>
    </button>
  );
}

function ConversationMiniCard({ conv }: { conv: ConversationLite }) {
  const preview = conv.last_message?.content?.trim() || conv.summary || "";
  const ts = conv.updated_at ?? conv.last_message?.timestamp;
  return (
    <Link href={`/communications?conversation=${encodeURIComponent(conv.id)}`}>
      <div
        className="p-3 rounded-lg border bg-card text-sm space-y-1.5 hover:bg-muted/50 transition-colors cursor-pointer"
        data-testid={`conversation-${conv.id}`}
      >
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 min-w-0">
            <MessageSquare className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
            <Badge variant="outline" className="text-xs">
              {conv.channel ?? "Chat"}
            </Badge>
          </div>
          <ChevronRight className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
        </div>
        {preview && <p className="text-muted-foreground text-xs line-clamp-2">{preview}</p>}
        {ts && <p className="text-xs text-muted-foreground">{formatTimelineDateShort(ts)}</p>}
      </div>
    </Link>
  );
}

export function ContactDetailsModal({
  open,
  onOpenChange,
  contactId,
  initialContact,
  onEdit,
}: ContactDetailsModalProps) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const [selectedActivity, setSelectedActivity] = useState<TimelineItem | null>(null);
  const [activityDetailOpen, setActivityDetailOpen] = useState(false);
  const [openDealId, setOpenDealId] = useState<string | null>(null);
  const [targetStageId, setTargetStageId] = useState<string>("");
  const [moveComment, setMoveComment] = useState<string>("");

  const handleActivityClick = (item: TimelineItem) => {
    if (item.type === "activity") {
      setSelectedActivity(item);
      setActivityDetailOpen(true);
    }
  };

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
        (d: any) => String(d.contact_id ?? d.contact ?? "").trim() === String(contactId ?? "").trim(),
      ) as DealLite[];
    },
    enabled: open && Boolean(contactId),
    retry: false,
    staleTime: 60 * 1000,
  });

  const conversationsQuery = useQuery({
    queryKey: [apiV1("/crm/communications/conversations/"), "by-contact", contactId],
    queryFn: async () => {
      const raw = await fetchJson<{ conversations?: ConversationLite[] }>(
        apiV1("/crm/communications/conversations/"),
        { page: 1, page_size: 100 },
      );
      const list = raw?.conversations ?? [];
      return list.filter(
        (c) => String(c.contact?.id ?? "").trim() === String(contactId ?? "").trim(),
      ) as ConversationLite[];
    },
    enabled: open && Boolean(contactId),
    retry: false,
    staleTime: 60 * 1000,
  });

  const dealDetailQuery = useQuery({
    queryKey: [apiV1("/crm/deals/"), "detail", openDealId],
    queryFn: () => fetchJson<DealDetail>(apiV1(`/crm/deals/${openDealId}/`)),
    enabled: Boolean(openDealId),
    retry: false,
    staleTime: 60 * 1000,
  });

  const stageOptionsQuery = useQuery({
    queryKey: [apiV1("/crm/deals/pipelines/"), "stages-for-deal", dealDetailQuery.data?.pipeline],
    queryFn: async () => {
      const raw = await fetchJson<{ pipelines?: Array<{ id: string; stages?: StageOption[] }> }>(apiV1("/crm/deals/pipelines/"));
      const pipelines = raw?.pipelines ?? [];
      const pipelineId = String(dealDetailQuery.data?.pipeline ?? "");
      const pipeline = pipelines.find((p) => String(p.id) === pipelineId);
      return pipeline?.stages ?? [];
    },
    enabled: Boolean(openDealId && dealDetailQuery.data?.pipeline),
    retry: false,
    staleTime: 60 * 1000,
  });

  useEffect(() => {
    if (!openDealId) {
      setTargetStageId("");
      setMoveComment("");
      return;
    }
    if (dealDetailQuery.data?.stage) {
      setTargetStageId(String(dealDetailQuery.data.stage));
    }
  }, [openDealId, dealDetailQuery.data?.stage]);

  const moveStageMutation = useMutation({
    mutationFn: async (stageId: string) => {
      if (!openDealId) return;
      await apiRequest("POST", apiV1(`/crm/deals/${openDealId}/move-stage/`), {
        data: { stage_id: stageId, comment: moveComment.trim() },
      });
    },
    onSuccess: async () => {
      toast({ title: "Deal moved", description: "The deal stage was updated." });
      await Promise.all([
        dealDetailQuery.refetch(),
        dealsQuery.refetch(),
      ]);
      queryClient.invalidateQueries({ queryKey: [apiV1("/crm/deals/")] });
    },
    onError: (error: Error) => {
      toast({ title: "Failed to move deal", description: error.message, variant: "destructive" });
    },
  });

  const timelineItems = timelineQuery.data?.items ?? [];
  const deals = dealsQuery.data ?? [];
  const conversations = conversationsQuery.data ?? [];
  const activityItems = timelineItems.filter((i) => i.type === "capture_entry" || i.type === "activity");
  const notificationItems = timelineItems.filter((i) => {
    const tp = String((i as any).type ?? "").toLowerCase();
    return tp.includes("notification") || tp.includes("audit") || tp.includes("system");
  });

  const activityByDate = groupByDate(activityItems);
  const notificationByDate = groupByDate(notificationItems);
  const statusPill = contact ? getStatusPill(contact, t) : null;

  const handleOpenChange = (next: boolean) => {
    if (!next) setActivityDetailOpen(false);
    onOpenChange(next);
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent
        className="max-w-[96vw] w-[96vw] h-[88vh] p-0 gap-0 overflow-hidden flex flex-col bg-background max-md:inset-0 max-md:w-screen max-md:h-[100dvh] max-md:max-w-none max-md:rounded-none"
        data-testid="dialog-contact-details"
      >
        {(contactQuery.isLoading && !initialContact) ? (
          <div className="flex-1 flex items-center justify-center">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        ) : !contact ? (
          <div className="flex-1 flex items-center justify-center">
            <p className="text-sm text-muted-foreground">{t("contact.no_contact_selected")}</p>
          </div>
        ) : (
          <>
            {/* Header */}
            <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3 px-4 md:px-6 py-3.5 md:py-3.5 pr-14 border-b bg-gradient-to-b from-muted/30 to-muted/10 shrink-0">
              <div className="flex items-center gap-3 min-w-0">
                <div className="h-11 w-11 rounded-full bg-primary/10 ring-1 ring-primary/15 flex items-center justify-center text-base font-semibold text-primary shrink-0">
                  {contact.name?.charAt(0).toUpperCase() ?? "?"}
                </div>
                <div className="min-w-0">
                  <div className="flex items-center gap-1.5 min-w-0">
                    <h2 className="text-lg md:text-xl font-semibold tracking-tight truncate">{contact.name}</h2>
                    {onEdit && (
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-6 w-6 shrink-0 text-muted-foreground hover:text-foreground hover:bg-muted/60"
                        onClick={() => onEdit(contact)}
                        data-testid="button-contact-details-edit"
                        aria-label={t("contact.edit")}
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </Button>
                    )}
                  </div>
                  <div className="mt-1.5 space-y-1">
                    {contact.email && (
                      <p className="text-sm text-muted-foreground flex items-center gap-1.5 truncate">
                        <Mail className="h-3.5 w-3.5 shrink-0" />
                        <span className="truncate">{contact.email}</span>
                      </p>
                    )}
                    {contact.phone && (
                      <p className="text-sm text-muted-foreground flex items-center gap-1.5 truncate">
                        <Phone className="h-3.5 w-3.5 shrink-0" />
                        <span className="truncate">{contact.phone}</span>
                      </p>
                    )}
                  </div>
                  <div className="mt-1 flex items-center gap-1.5 flex-wrap">
                    {statusPill && (
                      <Badge variant={statusPill.variant} className={cn("text-xs px-2.5 py-0.5", statusPill.className)}>
                        {statusPill.label}
                      </Badge>
                    )}
                    {contact.type && (
                      <Badge variant="secondary" className="text-xs px-2.5 py-0.5">
                        {contact.type}
                      </Badge>
                    )}
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-2 shrink-0 self-end md:self-auto">
                <div className="hidden md:flex items-center gap-1.5 mr-1">
                  <Badge variant="secondary" className="text-xs px-2 py-0.5">
                    {t("contact.messages")}: {conversations.length}
                  </Badge>
                  <Badge variant="secondary" className="text-xs px-2 py-0.5">
                    {t("contact.deals")}: {deals.length}
                  </Badge>
                </div>
                <p className="text-xs text-muted-foreground whitespace-nowrap">
                  <span className="uppercase tracking-[0.12em]">{t("contact.last_contact")}:</span>{" "}
                  <span className="text-sm font-semibold text-foreground normal-case tracking-normal">
                    {formatRelativeDate(contact.activity_summary?.last_contact)}
                  </span>
                </p>
              </div>
            </div>

            {/* Responsive body: one smooth scroll on mobile, split columns on desktop */}
            <div className="flex-1 overflow-hidden min-h-0">
              <ScrollArea className="h-full">
                <div className="grid grid-cols-1 md:grid-cols-[minmax(0,1.65fr)_minmax(320px,1fr)] md:gap-4 p-4 md:p-5 min-h-full">
                  {/* Mobile-first sidebar summary */}
                  <div className="space-y-4 md:order-2">
                    {/* Contact info card */}
                    <Card className="border-border/70 shadow-sm">
                      <CardContent className="space-y-4 pt-4">
                        {contact.company && (
                          <>
                            <SidebarSection title={t("contact.company")}>
                              <InfoRow icon={Building2}>{contact.company}</InfoRow>
                            </SidebarSection>
                          </>
                        )}

                        <Separator />

                        <SidebarSection title={t("contact.address_label")}>
                          {contact.address ? (
                            <InfoRow icon={MapPin}>{contact.address}</InfoRow>
                          ) : (
                            <p className="text-sm text-muted-foreground">{t("contact.no_address")}</p>
                          )}
                        </SidebarSection>

                        {contact.tags && contact.tags.length > 0 && (
                          <>
                            <Separator />
                            <SidebarSection title={t("contact.tags")}>
                              <div className="flex flex-wrap gap-1.5">
                                {contact.tags.map((tag) => (
                                  <span
                                    key={tag}
                                    className="inline-flex items-center gap-1.5 rounded-full bg-muted px-2.5 py-1 text-xs font-medium"
                                  >
                                    <User className="h-3 w-3 text-muted-foreground" />
                                    {tag}
                                  </span>
                                ))}
                              </div>
                            </SidebarSection>
                          </>
                        )}
                      </CardContent>
                    </Card>

                    {/* Messages card */}
                    <Card className="border-border/70 shadow-sm">
                      <CardHeader className="pb-2">
                        <div className="flex items-center justify-between">
                          <CardTitle className="text-sm font-semibold tracking-tight flex items-center gap-2">
                            <MessageSquare className="h-4 w-4 text-muted-foreground" />
                            {t("contact.messages")}
                          </CardTitle>
                          <Badge variant="secondary" className="text-xs rounded-md px-2 py-0.5">
                            {conversations.length}
                          </Badge>
                        </div>
                      </CardHeader>
                      <CardContent>
                        {conversationsQuery.isLoading ? (
                          <div className="flex items-center justify-center py-4">
                            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                          </div>
                        ) : conversations.length === 0 ? (
                          <p className="text-sm text-muted-foreground py-2">{t("contact.no_conversations")}</p>
                        ) : (
                          <div className="space-y-2">
                            {conversations
                              .sort(
                                (a, b) =>
                                  parseTime(b.updated_at ?? b.last_message?.timestamp) -
                                  parseTime(a.updated_at ?? a.last_message?.timestamp),
                              )
                              .map((conv) => (
                                <ConversationMiniCard key={conv.id} conv={conv} />
                              ))}
                          </div>
                        )}
                      </CardContent>
                    </Card>

                    {/* Deals card */}
                    <Card className="border-border/70 shadow-sm">
                      <CardHeader className="pb-2">
                        <div className="flex items-center justify-between">
                          <CardTitle className="text-sm font-semibold tracking-tight flex items-center gap-2">
                            <Briefcase className="h-4 w-4 text-muted-foreground" />
                            {t("contact.deals")}
                          </CardTitle>
                          <Badge variant="secondary" className="text-xs rounded-md px-2 py-0.5">
                            {deals.length}
                          </Badge>
                        </div>
                      </CardHeader>
                      <CardContent>
                        {dealsQuery.isLoading ? (
                          <div className="flex items-center justify-center py-4">
                            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                          </div>
                        ) : deals.length === 0 ? (
                          <p className="text-sm text-muted-foreground py-2">{t("contact.no_deals")}</p>
                        ) : (
                          <div className="space-y-2.5">
                            {deals.map((deal) => (
                              <DealCard key={deal.id} deal={deal} onOpen={setOpenDealId} />
                            ))}
                          </div>
                        )}
                      </CardContent>
                    </Card>
                  </div>

                  {/* Timeline and events */}
                  <div className="mt-3 md:mt-0 space-y-5 md:order-1">
                  {/* Activity timeline */}
                  <Card className="border-border/70 shadow-sm">
                    <CardHeader className="pb-3">
                      <CardTitle className="text-base font-semibold tracking-tight flex items-center gap-2">
                        <Zap className="h-4 w-4 text-muted-foreground" />
                        {t("contact.timeline")}
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      {timelineQuery.isLoading ? (
                        <div className="flex items-center justify-center py-8">
                          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                        </div>
                      ) : activityItems.length === 0 ? (
                        <EmptyState icon={Zap} title={t("contact.no_activity")} description={t("contact.activity_description")} />
                      ) : (
                        <VerticalTimelineRail>
                          {Array.from(activityByDate.entries())
                            .sort(([a], [b]) => b.localeCompare(a))
                            .flatMap(([, items]) =>
                              items.map((item) => (
                                <TimelineNode
                                  key={`${(item as TimelineItem).type}-${(item as TimelineItem).id}`}
                                  timestamp={formatTimelineDateShort((item as TimelineItem).created_at)}
                                >
                                  <TimelineItemCard item={item as TimelineItem} onActivityClick={handleActivityClick} />
                                </TimelineNode>
                              )),
                            )}
                        </VerticalTimelineRail>
                      )}
                    </CardContent>
                  </Card>

                  {/* Notifications */}
                  {notificationItems.length > 0 && (
                    <Card className="border-border/70 shadow-sm">
                      <CardHeader className="pb-3">
                        <CardTitle className="text-base font-semibold tracking-tight flex items-center gap-2">
                          <Bell className="h-4 w-4 text-muted-foreground" />
                          {t("contact.notifications")}
                        </CardTitle>
                      </CardHeader>
                      <CardContent>
                        <VerticalTimelineRail>
                          {Array.from(notificationByDate.entries())
                            .sort(([a], [b]) => b.localeCompare(a))
                            .flatMap(([, items]) =>
                              items.map((item) => (
                                <TimelineNode
                                  key={`n-${(item as TimelineItem).id}`}
                                  timestamp={formatTimelineDateShort((item as TimelineItem).created_at)}
                                >
                                  <NotificationEventCard item={item as TimelineItem} />
                                </TimelineNode>
                              )),
                            )}
                        </VerticalTimelineRail>
                      </CardContent>
                    </Card>
                  )}
                </div>
                </div>
              </ScrollArea>
            </div>
          </>
        )}
      </DialogContent>

      <ActivityDetailSheet
        open={activityDetailOpen}
        onOpenChange={setActivityDetailOpen}
        activity={selectedActivity?.type === "activity" ? (selectedActivity as ActivityDetailData) : null}
      />

      <Dialog open={Boolean(openDealId)} onOpenChange={(next) => { if (!next) setOpenDealId(null); }}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>{dealDetailQuery.data?.title ?? "Deal"}</DialogTitle>
            <DialogDescription>
              {dealDetailQuery.data?.stage_name ?? dealDetailQuery.data?.stage ?? "No stage"}
            </DialogDescription>
          </DialogHeader>
          {dealDetailQuery.isLoading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : (
            <div className="space-y-3 text-sm">
              {dealDetailQuery.data?.description && (
                <p className="whitespace-pre-wrap">{dealDetailQuery.data.description}</p>
              )}
              {typeof dealDetailQuery.data?.value === "number" && (
                <p>
                  Value:{" "}
                  {new Intl.NumberFormat(undefined, {
                    style: "currency",
                    currency: dealDetailQuery.data.currency ?? "USD",
                  }).format(dealDetailQuery.data.value)}
                </p>
              )}
              {dealDetailQuery.data?.status && <p>Status: {dealDetailQuery.data.status}</p>}
              {dealDetailQuery.data?.expected_close_date && (
                <p>Expected close: {formatTimelineDateShort(dealDetailQuery.data.expected_close_date)}</p>
              )}
              {stageOptionsQuery.data && stageOptionsQuery.data.length > 0 && (
                <div className="pt-2 space-y-2 border-t">
                  <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Move stage</p>
                  <Textarea
                    value={moveComment}
                    onChange={(e) => setMoveComment(e.target.value)}
                    placeholder="Add a comment for this movement..."
                    className="min-h-[84px]"
                  />
                  <div className="flex gap-2">
                    <Select value={targetStageId} onValueChange={setTargetStageId}>
                      <SelectTrigger className="flex-1">
                        <SelectValue placeholder="Select stage" />
                      </SelectTrigger>
                      <SelectContent>
                        {stageOptionsQuery.data.map((stage) => (
                          <SelectItem key={stage.id} value={stage.id}>
                            {stage.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <Button
                      type="button"
                      onClick={() => moveStageMutation.mutate(targetStageId)}
                      disabled={
                        !moveComment.trim() ||
                        !targetStageId ||
                        targetStageId === String(dealDetailQuery.data?.stage ?? "") ||
                        moveStageMutation.isPending
                      }
                    >
                      {moveStageMutation.isPending ? "Moving..." : "Move"}
                    </Button>
                  </div>
                </div>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>

    </Dialog>
  );
}
