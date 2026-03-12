"use client";

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery, useMutation } from "@tanstack/react-query";
import {
  Zap,
  Phone,
  Mail,
  Building2,
  Loader2,
  Briefcase,
  ExternalLink,
  Users,
  Trash2,
  Pencil,
  MoreHorizontal,
  MapPin,
  FileText,
  ChevronRight,
} from "lucide-react";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { EmptyState } from "@/components/empty-state";
import { fetchJson, apiRequest, queryClient } from "@/lib/queryClient";
import { apiV1 } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { isTenantAdminRole } from "@/lib/rbac";
import { useToast } from "@/hooks/use-toast";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
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
  onEdit?: (account: AccountDetailsAccount) => void;
  onDeleted?: () => void;
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
    if (days < 7) return `${days} days`;
    if (days < 30) return `${Math.floor(days / 7)} weeks`;
    if (days < 365) {
      const months = Math.floor(days / 30);
      return months === 1 ? "About 1 month" : `About ${months} months`;
    }
    const years = Math.floor(days / 365);
    return years === 1 ? "About 1 year" : `About ${years} years`;
  } catch {
    return ts ?? "—";
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

function VerticalTimelineRail({ children }: { children: React.ReactNode }) {
  return (
    <div className="relative pl-6">
      <div className="absolute left-[5px] top-0 bottom-0 w-px bg-border" />
      <div className="space-y-4">{children}</div>
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

function StatBox({ label, value, isLast }: { label: string; value: string | number; isLast?: boolean }) {
  return (
    <div className={`px-5 py-3 ${isLast ? "" : "border-r"}`}>
      <p className="text-xs font-medium text-muted-foreground">{label}</p>
      <p className="text-base font-semibold mt-0.5">{value}</p>
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

function DealCard({ deal }: { deal: DealLite }) {
  const valueStr =
    typeof deal.value === "number"
      ? new Intl.NumberFormat(undefined, { style: "currency", currency: deal.currency ?? "USD" }).format(deal.value)
      : deal.value ?? "—";
  return (
    <Link href="/deals">
      <div className="p-3 rounded-lg border bg-card text-sm space-y-1.5 hover:bg-muted/50 transition-colors cursor-pointer">
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
      </div>
    </Link>
  );
}

function ContactMiniCard({ contact, onView }: { contact: ContactLite; onView: (id: string) => void }) {
  return (
    <div
      className="flex items-center justify-between gap-2 p-2.5 rounded-lg hover:bg-muted/50 transition-colors cursor-pointer -mx-1"
      onClick={() => onView(contact.id)}
    >
      <div className="flex items-center gap-2.5 min-w-0">
        <div className="h-8 w-8 rounded-full bg-primary/10 flex items-center justify-center text-xs font-semibold text-primary shrink-0">
          {contact.name?.charAt(0).toUpperCase() ?? "?"}
        </div>
        <div className="min-w-0">
          <p className="text-sm font-medium truncate">{contact.name ?? "Unknown"}</p>
          <p className="text-xs text-muted-foreground truncate">{contact.email || contact.phone || ""}</p>
        </div>
      </div>
      <ChevronRight className="h-4 w-4 text-muted-foreground shrink-0" />
    </div>
  );
}

export function AccountDetailsModal({ open, onOpenChange, accountId, onEdit, onDeleted }: AccountDetailsModalProps) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const { toast } = useToast();
  const [selectedActivity, setSelectedActivity] = useState<TimelineItem | null>(null);
  const [activityDetailOpen, setActivityDetailOpen] = useState(false);
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);

  const canDelete = isTenantAdminRole(user?.role);

  const deleteMutation = useMutation({
    mutationFn: async (id: string) => {
      await apiRequest("DELETE", apiV1(`/crm/customers/${id}/`));
    },
    onSuccess: () => {
      toast({ title: t("account.account_deleted"), description: t("account.account_deleted_description") });
      onOpenChange(false);
      onDeleted?.();
      queryClient.invalidateQueries({ queryKey: [apiV1("/crm/customers/")] });
    },
    onError: (error: Error) => {
      toast({ title: "Failed to delete account", description: error.message, variant: "destructive" });
    },
  });

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

  const firstAddress = account?.addresses?.[0];
  const addressStr = firstAddress
    ? [firstAddress.street, firstAddress.city, firstAddress.state, firstAddress.zip, firstAddress.country]
        .filter(Boolean)
        .join(", ")
    : null;

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent
        className="max-w-5xl w-[95vw] h-[85vh] p-0 gap-0 overflow-hidden flex flex-col max-md:inset-0 max-md:w-screen max-md:h-[100dvh] max-md:max-w-none max-md:rounded-none"
        data-testid="dialog-account-details"
      >
        {accountQuery.isLoading ? (
          <div className="flex-1 flex items-center justify-center">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        ) : !account ? (
          <div className="flex-1 flex items-center justify-center">
            <p className="text-sm text-muted-foreground">{t("account.no_account_selected")}</p>
          </div>
        ) : (
          <>
            {/* Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b bg-muted/20 shrink-0">
              <div className="flex items-center gap-3 min-w-0">
                <div className="h-10 w-10 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
                  <Building2 className="h-5 w-5 text-primary" />
                </div>
                <div className="min-w-0">
                  <h2 className="text-lg font-semibold truncate">{account.name}</h2>
                  {account.type && (
                    <Badge variant="secondary" className="capitalize text-xs mt-0.5">
                      {account.type}
                    </Badge>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                {onEdit && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => onEdit(account)}
                    data-testid="button-edit-account"
                  >
                    <Pencil className="h-3.5 w-3.5 mr-1.5" />
                    {t("account.edit")}
                  </Button>
                )}
                {canDelete && (
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button variant="outline" size="sm" data-testid="button-more-actions">
                        <MoreHorizontal className="h-4 w-4" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      <DropdownMenuItem
                        className="text-destructive focus:text-destructive"
                        onClick={() => setDeleteConfirmOpen(true)}
                        data-testid="menu-delete-account"
                      >
                        <Trash2 className="h-4 w-4 mr-2" />
                        {t("account.delete_account")}
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                )}
              </div>
            </div>

            {/* Stats ribbon */}
            <div className="grid grid-cols-2 md:grid-cols-4 border-b bg-card shrink-0">
              <StatBox label={t("account.contacts")} value={contacts.length} />
              <StatBox label={t("account.deals")} value={deals.length} />
              <StatBox label={t("account.account_since")} value={formatRelativeDate(account.created_at)} />
              <StatBox label={t("account.type_label")} value={account.type ?? "—"} isLast />
            </div>

            {/* Two-column body */}
            <div className="grid grid-cols-1 md:grid-cols-[1fr_22rem] flex-1 overflow-hidden min-h-0">
              {/* Left: Main content – Timeline */}
              <ScrollArea className="h-full">
                <div className="p-5 space-y-5">
                  <Card>
                    <CardHeader className="pb-3">
                      <CardTitle className="text-base font-semibold flex items-center gap-2">
                        <Zap className="h-4 w-4 text-muted-foreground" />
                        {t("account.timeline")}
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      {timelineQuery.isLoading ? (
                        <div className="flex items-center justify-center py-8">
                          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                        </div>
                      ) : activityItems.length === 0 ? (
                        <EmptyState icon={Zap} title={t("account.no_activity")} description={t("account.activity_description")} />
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
                              ))
                            )}
                        </VerticalTimelineRail>
                      )}
                    </CardContent>
                  </Card>
                </div>
              </ScrollArea>

              {/* Right: Sidebar cards */}
              <ScrollArea className="h-full border-l bg-muted/20">
                <div className="p-4 space-y-4">
                  {/* Account info card */}
                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm font-semibold">{t("account.account_info")}</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      <SidebarSection title={t("account.contact_information")}>
                        <div className="space-y-2">
                          {account.email ? (
                            <InfoRow icon={Mail}>{account.email}</InfoRow>
                          ) : (
                            <p className="text-sm text-muted-foreground">{t("account.no_email")}</p>
                          )}
                          {account.phone ? (
                            <InfoRow icon={Phone}>{account.phone}</InfoRow>
                          ) : (
                            <p className="text-sm text-muted-foreground">{t("account.no_phone")}</p>
                          )}
                        </div>
                      </SidebarSection>

                      <Separator />

                      <SidebarSection title={t("account.address")}>
                        {addressStr ? (
                          <InfoRow icon={MapPin}>{addressStr}</InfoRow>
                        ) : (
                          <p className="text-sm text-muted-foreground">{t("account.no_address")}</p>
                        )}
                      </SidebarSection>

                      {(account.legal_name || account.tax_id) && (
                        <>
                          <Separator />
                          <SidebarSection title={t("account.legal_details")}>
                            <div className="space-y-2">
                              {account.legal_name && account.legal_name !== account.name && (
                                <InfoRow icon={FileText}>{account.legal_name}</InfoRow>
                              )}
                              {account.tax_id && (
                                <div className="text-sm">
                                  <span className="text-muted-foreground">{t("account.tax_id")}: </span>
                                  <span>{account.tax_id}</span>
                                </div>
                              )}
                            </div>
                          </SidebarSection>
                        </>
                      )}
                    </CardContent>
                  </Card>

                  {/* Contacts card */}
                  <Card>
                    <CardHeader className="pb-2">
                      <div className="flex items-center justify-between">
                        <CardTitle className="text-sm font-semibold flex items-center gap-2">
                          <Users className="h-4 w-4 text-muted-foreground" />
                          {t("account.contacts")}
                        </CardTitle>
                        {contacts.length > 0 && (
                          <Badge variant="secondary" className="text-xs">{contacts.length}</Badge>
                        )}
                      </div>
                    </CardHeader>
                    <CardContent>
                      {contactsQuery.isLoading ? (
                        <div className="flex items-center justify-center py-4">
                          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                        </div>
                      ) : contacts.length === 0 ? (
                        <p className="text-sm text-muted-foreground py-2">{t("account.no_contacts")}</p>
                      ) : (
                        <div className="space-y-1">
                          {contacts.map((contact) => (
                            <ContactMiniCard
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
                    </CardContent>
                  </Card>

                  {/* Deals card */}
                  <Card>
                    <CardHeader className="pb-2">
                      <div className="flex items-center justify-between">
                        <CardTitle className="text-sm font-semibold flex items-center gap-2">
                          <Briefcase className="h-4 w-4 text-muted-foreground" />
                          {t("account.deals")}
                        </CardTitle>
                        {deals.length > 0 && (
                          <Badge variant="secondary" className="text-xs">{deals.length}</Badge>
                        )}
                      </div>
                    </CardHeader>
                    <CardContent>
                      {dealsQuery.isLoading ? (
                        <div className="flex items-center justify-center py-4">
                          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                        </div>
                      ) : deals.length === 0 ? (
                        <p className="text-sm text-muted-foreground py-2">{t("account.no_deals")}</p>
                      ) : (
                        <div className="space-y-2">
                          {deals.map((deal) => (
                            <DealCard key={deal.id} deal={deal} />
                          ))}
                        </div>
                      )}
                    </CardContent>
                  </Card>
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

      <AlertDialog open={deleteConfirmOpen} onOpenChange={setDeleteConfirmOpen}>
        <AlertDialogContent data-testid="dialog-delete-account-confirm">
          <AlertDialogHeader>
            <AlertDialogTitle>{t("account.delete_account_title")}</AlertDialogTitle>
            <AlertDialogDescription>
              {t("account.delete_account_description", { name: account?.name ?? "" })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel data-testid="button-cancel-delete-account">{t("account.cancel")}</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => accountId && deleteMutation.mutate(accountId)}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              data-testid="button-confirm-delete-account"
            >
              {deleteMutation.isPending ? t("account.deleting") : t("account.delete")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Dialog>
  );
}
