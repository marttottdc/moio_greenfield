"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Zap,
  Phone,
  Mail,
  Building2,
  Loader2,
  Briefcase,
  ExternalLink,
  Users,
} from "lucide-react";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ScrollArea } from "@/components/ui/scroll-area";
import { EmptyState } from "@/components/empty-state";
import { fetchJson } from "@/lib/queryClient";
import { apiV1 } from "@/lib/api";
import { timelineApi } from "@/lib/timeline/timelineApi";
import type { TimelineItem } from "@/lib/timeline/types";
import { TimelineItemCard, ActivityDetailSheet, type ActivityDetailData } from "@/components/timeline/TimelineItemCard";
import { Link } from "wouter";

export interface AccountDetailsAccount {
  id: string;
  name: string;
  legal_name?: string | null;
  type?: string | null;
  status?: string | null;
  email?: string | null;
  phone?: string | null;
  tax_id?: string | null;
  addresses?: Array<Record<string, unknown>>;
  created_at?: string | null;
}

export interface AccountDetailsModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  accountId: string | null;
}

interface DealLite {
  id: string;
  title: string;
  value?: number | null;
  currency?: string | null;
  stage?: string | null;
  stage_name?: string | null;
  contact_id?: string | null;
  updated_at?: string;
}

interface ContactLite {
  id: string;
  name?: string | null;
  email?: string | null;
  phone?: string | null;
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
  return map;
}

function DealCard({ deal }: { deal: DealLite }) {
  const valueStr =
    typeof deal.value === "number"
      ? new Intl.NumberFormat(undefined, { style: "currency", currency: deal.currency ?? "USD" }).format(deal.value)
      : deal.value ?? "—";
  return (
    <Link href="/deals">
      <div className="p-3 rounded-lg border bg-card text-sm space-y-2 hover:bg-muted/50 transition-colors cursor-pointer">
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

function ContactCard({ contact, onView }: { contact: ContactLite; onView: (id: string) => void }) {
  return (
    <div
      className="p-3 rounded-lg border bg-card text-sm space-y-2 hover:bg-muted/50 transition-colors cursor-pointer"
      onClick={() => onView(contact.id)}
    >
      <div className="flex items-center gap-2">
        <span className="font-medium truncate">{contact.name ?? "Unknown"}</span>
      </div>
      <p className="text-xs text-muted-foreground truncate">
        {contact.email || contact.phone || "No contact info"}
      </p>
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

export function AccountDetailsModal({ open, onOpenChange, accountId }: AccountDetailsModalProps) {
  const [selectedActivity, setSelectedActivity] = useState<TimelineItem | null>(null);
  const [activityDetailOpen, setActivityDetailOpen] = useState(false);

  const handleActivityClick = (item: TimelineItem) => {
    if (item.type === "activity") {
      setSelectedActivity(item);
      setActivityDetailOpen(true);
    }
  };

  const accountQuery = useQuery({
    queryKey: [apiV1("/crm/customers/"), "detail", accountId],
    queryFn: () => fetchJson<AccountDetailsAccount>(apiV1(`/crm/customers/${accountId}/`)),
    enabled: open && Boolean(accountId),
    retry: false,
    staleTime: 2 * 60 * 1000,
  });

  const account = accountQuery.data ?? null;

  const timelineQuery = useQuery({
    queryKey: ["timeline", "customer", accountId],
    queryFn: () => timelineApi.listForAnchor({ anchor_model: "crm.customer", anchor_id: accountId!, limit: 50 }),
    enabled: open && Boolean(accountId),
    retry: false,
    staleTime: 60 * 1000,
  });

  const dealsQuery = useQuery({
    queryKey: [apiV1("/crm/deals/"), "by-customer", accountId],
    queryFn: async () => {
      const raw = await fetchJson<any>(apiV1("/crm/deals/"), { customer_id: accountId ?? "", limit: 100 });
      const list: DealLite[] = raw?.deals ?? [];
      return list;
    },
    enabled: open && Boolean(accountId),
    retry: false,
    staleTime: 60 * 1000,
  });

  const contactsQuery = useQuery({
    queryKey: [apiV1("/crm/contacts"), "by-account", accountId],
    queryFn: async () => {
      const raw = await fetchJson<any>(apiV1("/crm/contacts"), { account_id: accountId ?? "", limit: 100 });
      const list: ContactLite[] = raw?.contacts ?? [];
      return list;
    },
    enabled: open && Boolean(accountId),
    retry: false,
    staleTime: 0,
  });

  const timelineItems = timelineQuery.data?.items ?? [];
  const deals = dealsQuery.data ?? [];
  const contacts = contactsQuery.data ?? [];
  const activityItems = timelineItems.filter((i) => i.type === "capture_entry" || i.type === "activity");
  const activityByDate = groupByDate(activityItems);

  const handleOpenChange = (next: boolean) => {
    if (!next) setActivityDetailOpen(false);
    onOpenChange(next);
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent
        className="max-w-5xl w-[95vw] h-[85vh] p-0 gap-0 overflow-hidden flex flex-col max-md:inset-0 max-md:w-screen max-md:h-[100dvh] max-md:max-w-none max-md:rounded-none"
        data-testid="dialog-account-details"
      >
        <div className="grid grid-cols-1 md:grid-cols-[20rem_1fr] flex-1 overflow-hidden min-h-0">
          {/* Left: Profile */}
          <ScrollArea className="border-r bg-muted/30">
            <div className="p-5 space-y-5">
              {accountQuery.isLoading ? (
                <div className="flex items-center justify-center py-12">
                  <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                </div>
              ) : account ? (
                <>
                  <div className="flex flex-col items-center text-center">
                    <div className="h-20 w-20 rounded-lg bg-primary/10 flex items-center justify-center mb-2">
                      <Building2 className="h-10 w-10 text-primary" />
                    </div>
                    <h2 className="text-lg font-semibold leading-tight">{account.name}</h2>
                    {account.type && (
                      <Badge variant="secondary" className="mt-1 capitalize">{account.type}</Badge>
                    )}
                  </div>

                  <div className="space-y-2">
                    {account.phone && (
                      <div className="flex items-center gap-2 text-sm">
                        <Phone className="h-4 w-4 text-muted-foreground shrink-0" />
                        <span>{account.phone}</span>
                      </div>
                    )}
                    {account.email && (
                      <div className="flex items-center gap-2 text-sm">
                        <Mail className="h-4 w-4 text-muted-foreground shrink-0" />
                        <span className="break-all">{account.email}</span>
                      </div>
                    )}
                  </div>

                  {account.legal_name && account.legal_name !== account.name && (
                    <div className="space-y-1">
                      <h3 className="text-xs font-semibold text-muted-foreground uppercase">Legal name</h3>
                      <p className="text-sm">{account.legal_name}</p>
                    </div>
                  )}

                  {account.tax_id && (
                    <div className="space-y-1">
                      <h3 className="text-xs font-semibold text-muted-foreground uppercase">Tax ID</h3>
                      <p className="text-sm">{account.tax_id}</p>
                    </div>
                  )}
                </>
              ) : (
                <div className="py-8 text-center text-sm text-muted-foreground">No account selected</div>
              )}
            </div>
          </ScrollArea>

          {/* Right: Tabs */}
          <div className="flex flex-col min-h-0">
            <Tabs defaultValue="activity" className="flex flex-col flex-1 min-h-0">
              <TabsList className="w-full justify-start rounded-none border-b bg-transparent p-0 h-11 gap-0">
                <TabsTrigger value="activity" className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-muted/50">
                  <Zap className="h-4 w-4 mr-2" />
                  Activity
                </TabsTrigger>
                <TabsTrigger value="deals" className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-muted/50">
                  <Briefcase className="h-4 w-4 mr-2" />
                  Deals
                </TabsTrigger>
                <TabsTrigger value="contacts" className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-muted/50">
                  <Users className="h-4 w-4 mr-2" />
                  Contacts
                </TabsTrigger>
              </TabsList>

              <TabsContent value="activity" className="flex-1 m-0 overflow-hidden data-[state=inactive]:hidden">
                <ScrollArea className="h-full p-4">
                  {timelineQuery.isLoading ? (
                    <div className="flex items-center justify-center py-12">
                      <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                    </div>
                  ) : activityItems.length === 0 ? (
                    <EmptyState icon={Zap} title="No activity" description="Activity for this account will appear here." />
                  ) : (
                    <VerticalTimelineRail>
                      {Array.from(activityByDate.entries())
                        .sort(([a], [b]) => b.localeCompare(a))
                        .flatMap(([, items]) =>
                          items.map((item) => (
                            <TimelineNode key={`${(item as TimelineItem).type}-${(item as TimelineItem).id}`} timestamp={formatTimelineDateShort((item as TimelineItem).created_at)}>
                              <TimelineItemCard item={item as TimelineItem} onActivityClick={handleActivityClick} />
                            </TimelineNode>
                          ))
                        )}
                    </VerticalTimelineRail>
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
                    <EmptyState icon={Briefcase} title="No deals" description="Deals for this account will appear here." />
                  ) : (
                    <div className="space-y-3">
                      {deals.map((deal) => (
                        <DealCard key={deal.id} deal={deal} />
                      ))}
                    </div>
                  )}
                </ScrollArea>
              </TabsContent>

              <TabsContent value="contacts" className="flex-1 m-0 overflow-hidden data-[state=inactive]:hidden">
                <ScrollArea className="h-full p-4">
                  {contactsQuery.isLoading ? (
                    <div className="flex items-center justify-center py-12">
                      <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                    </div>
                  ) : contacts.length === 0 ? (
                    <EmptyState icon={Users} title="Sin contactos" description="Aún no hay contactos para este account." />
                  ) : (
                    <div className="space-y-3">
                      {contacts.map((contact) => (
                        <ContactCard
                          key={contact.id}
                          contact={contact}
                          onView={(id) => {
                            onOpenChange(false);
                            window.location.href = `/crm?tab=contacts&contactId=${encodeURIComponent(id)}`;
                          }}
                        />
                      ))}
                    </div>
                  )}
                </ScrollArea>
              </TabsContent>
            </Tabs>
          </div>
        </div>
      </DialogContent>
      <ActivityDetailSheet
        open={activityDetailOpen}
        onOpenChange={setActivityDetailOpen}
        activity={selectedActivity?.type === "activity" ? (selectedActivity as ActivityDetailData) : null}
      />
    </Dialog>
  );
}
