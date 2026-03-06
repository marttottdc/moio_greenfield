import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { CheckCircle, Eye, FileText, MessageSquare, XCircle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { GlassPanel } from "@/components/radiant/glass-panel";
import { EmptyState } from "@/components/empty-state";
import { StatCard } from "@/pages/workflows/components/StatCard";
import {
  fetchCrmWhatsappLogs,
  flattenCrmLogsToEvents,
} from "@/lib/reports/crmWhatsappLogsRepo";
import { useToast } from "@/hooks/use-toast";

type WorkflowRef = { id: string; name: string };
type TemplateRef = { id?: string; name?: string };

type WaStatus = "sent" | "sent_pending_id" | "failed" | "error" | "delivered" | "read" | string;

export function WhatsAppTemplatesReport({
  workflows,
  whatsappTemplates,
}: {
  workflows: WorkflowRef[];
  whatsappTemplates: TemplateRef[];
}) {
  const { toast } = useToast();

  const [flowId, setFlowId] = useState<string>("");
  const [templateId, setTemplateId] = useState<string>("all");
  const [phoneNumber, setPhoneNumber] = useState<string>("");
  const [fromDate, setFromDate] = useState<string>("");
  const [toDate, setToDate] = useState<string>("");
  const [runNonce, setRunNonce] = useState<number>(0);

  const runParams = useMemo(() => {
    if (!runNonce) return null;
    return {
      flowId: flowId || undefined,
      templateId: templateId !== "all" ? templateId : undefined,
      phoneNumber: phoneNumber.trim() || undefined,
      fromDate: fromDate || undefined,
      toDate: toDate || undefined,
      nonce: runNonce,
    };
  }, [flowId, templateId, phoneNumber, fromDate, toDate, runNonce]);

  const selectedFlow = useMemo(() => workflows.find((w) => w.id === flowId) ?? null, [workflows, flowId]);

  const crmLogsQuery = useQuery({
    queryKey: ["reports", "wa", "crm-logs", runParams],
    enabled: !!runParams?.nonce,
    queryFn: () =>
      fetchCrmWhatsappLogs({
        page: 1,
        page_size: 500,
        flow_id: runParams?.flowId || undefined,
        from_date: runParams?.fromDate,
        to_date: runParams?.toDate,
        recipient: runParams?.phoneNumber?.trim() || undefined,
      }),
    staleTime: 0,
  });

  const messages = useMemo(() => {
    const data = crmLogsQuery.data;
    if (!data?.messages) return [];
    const events = flattenCrmLogsToEvents(data.messages);
    // Template filter applied when API returns template_id on messages
    if (runParams?.templateId) {
      return events.filter((m) => "template_id" in m && (m as { template_id?: string }).template_id === runParams.templateId);
    }
    return events;
  }, [crmLogsQuery.data, runParams]);

  const templateOptions = useMemo(() => {
    const fromCatalog = (whatsappTemplates ?? [])
      .map((t) => ({ id: String(t.id ?? ""), name: String(t.name ?? "") }))
      .filter((t) => t.id && t.name);

    const fromLogs = messages
      .map((m) => ({ id: ("template_id" in m ? (m as { template_id?: string }).template_id : undefined) ?? "", name: ("template_name" in m ? (m as { template_name?: string }).template_name : undefined) ?? "" }))
      .filter((t) => t.id && t.name);

    const seen = new Set<string>();
    const merged: Array<{ id: string; name: string }> = [];
    for (const t of [...fromCatalog, ...fromLogs]) {
      const k = `${t.id}:${t.name}`;
      if (seen.has(k)) continue;
      seen.add(k);
      merged.push(t);
    }
    return merged.sort((a, b) => a.name.localeCompare(b.name));
  }, [whatsappTemplates, messages]);

  const summary = useMemo(() => {
    const byStatus: Record<string, number> = {};
    for (const m of messages) {
      const k = String(m.status ?? "unknown");
      byStatus[k] = (byStatus[k] ?? 0) + 1;
    }
    const total = messages.length;
    const delivered = (byStatus.delivered ?? 0) + (byStatus.read ?? 0);
    const failed = (byStatus.failed ?? 0) + (byStatus.error ?? 0);
    const deliveryRate = total > 0 ? Math.round((delivered / total) * 100) : 0;
    const failRate = total > 0 ? Math.round((failed / total) * 100) : 0;
    return { total, delivered, failed, deliveryRate, failRate, byStatus };
  }, [messages]);

  const byTemplate = useMemo(() => {
    const map = new Map<string, { template_id?: string; template_name?: string; total: number; delivered: number; read: number; failed: number }>();
    for (const m of messages) {
      const tid = "template_id" in m ? (m as { template_id?: string }).template_id : undefined;
      const tname = "template_name" in m ? (m as { template_name?: string }).template_name : undefined;
      const key = tid || tname || "(unknown template)";
      const cur = map.get(key) ?? { template_id: tid, template_name: tname, total: 0, delivered: 0, read: 0, failed: 0 };
      cur.total += 1;
      if (m.status === "delivered") cur.delivered += 1;
      if (m.status === "read") cur.read += 1;
      if (m.status === "failed" || m.status === "error") cur.failed += 1;
      map.set(key, cur);
    }
    return Array.from(map.values()).sort((a, b) => b.total - a.total);
  }, [messages]);

  /** Groups formed by msg_id; phone number shown when present (some logs have no phone). */
  const messagesByMsgId = useMemo(() => {
    const byMsgId = new Map<string, typeof messages>();
    for (const m of messages) {
      const msgId = m.message_id ?? m.id ?? "";
      if (!byMsgId.has(msgId)) byMsgId.set(msgId, []);
      byMsgId.get(msgId)!.push(m);
    }
    return Array.from(byMsgId.entries())
      .map(([msgId, list]) => {
        const statuses = list.sort(
          (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
        );
        const phone = statuses.map((s) => (s.recipient ?? "").trim()).find(Boolean) || undefined;
        return { msgId, statuses, phone };
      })
      .sort((a, b) => b.statuses.length - a.statuses.length);
  }, [messages]);

  const byDay = useMemo(() => {
    const map = new Map<string, { day: string; total: number; delivered: number; failed: number; read: number }>();
    for (const m of messages) {
      const day = new Date(m.created_at).toISOString().slice(0, 10);
      const cur = map.get(day) ?? { day, total: 0, delivered: 0, failed: 0, read: 0 };
      cur.total += 1;
      if (m.status === "delivered") cur.delivered += 1;
      if (m.status === "read") cur.read += 1;
      if (m.status === "failed" || m.status === "error") cur.failed += 1;
      map.set(day, cur);
    }
    return Array.from(map.values()).sort((a, b) => a.day.localeCompare(b.day)).slice(-30);
  }, [messages]);

  const errorsTop = useMemo(() => {
    const counts = new Map<string, number>();
    for (const m of messages) {
      const s = String(m.error_message ?? "").trim();
      if (!s) continue;
      counts.set(s, (counts.get(s) ?? 0) + 1);
    }
    return Array.from(counts.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 10)
      .map(([error, count]) => ({ error, count }));
  }, [messages]);

  const isRunning = crmLogsQuery.isLoading;

  const onGenerate = () => {
    if (!flowId && !fromDate && !toDate && templateId === "all") {
      toast({
        title: "Running tenant-wide report",
        description: "No filters selected. We'll scan the latest executions we can fetch; add a date range for faster, more accurate reports.",
      });
    }
    setRunNonce(Date.now());
  };

  return (
    <div className="space-y-6">
      <GlassPanel className="p-4 space-y-4" data-testid="wa-report-filters">
        <div className="grid gap-3 lg:grid-cols-6">
          <div className="lg:col-span-2">
            <Label className="text-xs">Flow (optional)</Label>
            <select
              className="mt-1 w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
              value={flowId}
              onChange={(e) => setFlowId(e.target.value)}
              data-testid="select-wa-report-flow"
            >
              <option value="">All flows</option>
              {workflows
                .slice()
                .sort((a, b) => a.name.localeCompare(b.name))
                .map((w) => (
                  <option key={w.id} value={w.id}>
                    {w.name}
                  </option>
                ))}
            </select>
          </div>

          <div className="lg:col-span-2">
            <Label className="text-xs">Template</Label>
            <select
              className="mt-1 w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
              value={templateId}
              onChange={(e) => setTemplateId(e.target.value)}
              data-testid="select-wa-report-template"
            >
              <option value="all">All templates</option>
              {templateOptions.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name} ({t.id.slice(0, 8)}…)
                </option>
              ))}
            </select>
          </div>

          <div className="lg:col-span-2">
            <Label className="text-xs">Phone number</Label>
            <Input
              type="text"
              placeholder="Filter by recipient…"
              value={phoneNumber}
              onChange={(e) => setPhoneNumber(e.target.value)}
              className="mt-1 h-9"
              data-testid="input-wa-report-phone"
            />
          </div>

          <div>
            <Label className="text-xs">From</Label>
            <Input type="date" value={fromDate} onChange={(e) => setFromDate(e.target.value)} className="mt-1 h-9" />
          </div>

          <div>
            <Label className="text-xs">To</Label>
            <Input type="date" value={toDate} onChange={(e) => setToDate(e.target.value)} className="mt-1 h-9" />
          </div>

          <div className="flex items-end justify-end">
            <Button onClick={onGenerate} disabled={isRunning} className="h-9 w-full" data-testid="button-wa-report-generate">
              {isRunning ? "Generating..." : "Generate"}
            </Button>
          </div>
        </div>

        {runParams?.nonce && (
          <div className="text-xs text-muted-foreground">
            {crmLogsQuery.data?.message_count != null
              ? `${crmLogsQuery.data.message_count} messages from CRM WhatsApp logs`
              : `${messages.length} message events`}
            {crmLogsQuery.data?.pagination && (
              <span> · page {crmLogsQuery.data.pagination.current_page} of {crmLogsQuery.data.pagination.total_pages}</span>
            )}
          </div>
        )}
      </GlassPanel>

      {isRunning ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <Skeleton className="h-24" />
          <Skeleton className="h-24" />
          <Skeleton className="h-24" />
          <Skeleton className="h-24" />
        </div>
      ) : runParams?.nonce ? (
        <>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <StatCard label="Messages" value={summary.total.toString()} helper="Total logs" icon={MessageSquare} accent="bg-primary/10 text-primary" />
            <StatCard label="Delivered" value={summary.delivered.toString()} helper={`Delivery rate ${summary.deliveryRate}%`} icon={CheckCircle} accent="bg-blue-100 text-blue-600 dark:bg-blue-900/30" />
            <StatCard label="Failed" value={summary.failed.toString()} helper={`Fail rate ${summary.failRate}%`} icon={XCircle} accent="bg-red-100 text-red-600 dark:bg-red-900/30" />
            <StatCard label="Read" value={String(summary.byStatus.read ?? 0)} helper="Read receipts" icon={Eye} accent="bg-purple-100 text-purple-600 dark:bg-purple-900/30" />
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <GlassPanel className="p-4">
              <div className="flex items-center justify-between mb-3">
                <h3 className="font-semibold text-sm">Volume by template</h3>
                <Badge variant="outline" className="text-[10px]">{byTemplate.length} total</Badge>
              </div>
              {byTemplate.length === 0 ? (
                <div className="text-sm text-muted-foreground">No messages found for the selected filters.</div>
              ) : (
                <div className="space-y-2">
                  {byTemplate.slice(0, 12).map((t) => (
                    <div key={t.template_id ?? t.template_name ?? "(unknown)"} className="border rounded-md p-3">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="font-medium text-sm truncate">
                            {t.template_name && t.template_id
                              ? `${t.template_name} (${t.template_id})`
                              : t.template_name ?? t.template_id ?? "(unknown template)"}
                          </div>
                        </div>
                        <Badge variant="secondary">{t.total}</Badge>
                      </div>
                      <div className="mt-2 flex flex-wrap gap-2 text-xs text-muted-foreground">
                        <span>Delivered: {t.delivered + t.read}</span>
                        <span>Read: {t.read}</span>
                        <span>Failed: {t.failed}</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </GlassPanel>

            <GlassPanel className="p-4">
              <div className="flex items-center justify-between mb-3">
                <h3 className="font-semibold text-sm">Last 30 days</h3>
              </div>
              {byDay.length === 0 ? (
                <div className="text-sm text-muted-foreground">No messages found for the selected filters.</div>
              ) : (
                <div className="space-y-2">
                  {byDay.map((d) => (
                    <div key={d.day} className="flex items-center justify-between border rounded-md px-3 py-2 text-sm">
                      <div className="text-xs text-muted-foreground">{d.day}</div>
                      <div className="flex items-center gap-3 text-xs">
                        <span>Total <Badge variant="outline">{d.total}</Badge></span>
                        <span>Delivered <Badge variant="outline">{d.delivered + d.read}</Badge></span>
                        <span>Failed <Badge variant="outline">{d.failed}</Badge></span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </GlassPanel>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <GlassPanel className="p-4">
              <div className="flex items-center justify-between mb-3">
                <h3 className="font-semibold text-sm">Top failure reasons</h3>
                <Badge variant="outline" className="text-[10px]">{errorsTop.length} shown</Badge>
              </div>
              {errorsTop.length === 0 ? (
                <div className="text-sm text-muted-foreground">No errors found for the selected filters.</div>
              ) : (
                <div className="space-y-2">
                  {errorsTop.map((e) => (
                    <div key={e.error} className="flex items-start justify-between gap-3 border rounded-md p-2">
                      <div className="text-xs text-muted-foreground break-words flex-1">{e.error}</div>
                      <Badge variant="secondary" className="shrink-0">{e.count}</Badge>
                    </div>
                  ))}
                </div>
              )}
            </GlassPanel>

            <GlassPanel className="p-4">
              <div className="flex items-center justify-between mb-3">
                <h3 className="font-semibold text-sm">Status breakdown</h3>
              </div>
              <div className="grid grid-cols-2 gap-2 text-sm">
                {Object.entries(summary.byStatus)
                  .sort((a, b) => b[1] - a[1])
                  .map(([k, v]) => (
                    <div key={k} className="flex items-center justify-between border rounded-md px-3 py-2">
                      <span className="capitalize">{k.replaceAll("_", " ")}</span>
                      <Badge variant="outline">{v}</Badge>
                    </div>
                  ))}
              </div>
            </GlassPanel>
          </div>

          <GlassPanel className="p-4" data-testid="wa-report-recent">
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-semibold text-sm">Messages by msg_id</h3>
              <Badge variant="outline" className="text-[10px]">{messagesByMsgId.length} messages</Badge>
            </div>
            {messagesByMsgId.length === 0 ? (
              <EmptyState title="No messages" description="No messages found for the selected filters." />
            ) : (
              <div className="divide-y divide-border/50 max-h-[500px] overflow-y-auto space-y-0">
                {messagesByMsgId.map(({ msgId, statuses, phone }) => {
                  const latest = statuses[statuses.length - 1];
                  return (
                    <div
                      key={msgId || latest?.id}
                      className="py-3 first:pt-0"
                    >
                      <div className="flex items-center gap-2 flex-wrap mb-1.5">
                        {phone ? (
                          <span className="font-mono text-sm font-medium" title={phone}>
                            {phone}
                          </span>
                        ) : (
                          <span className="text-muted-foreground text-sm">No phone</span>
                        )}
                        {latest?.contact_name && (
                          <span className="text-xs text-muted-foreground">{latest.contact_name}</span>
                        )}
                        <code className="text-[10px] font-mono text-muted-foreground truncate max-w-[200px]" title={msgId || undefined}>
                          {msgId ? `${msgId.slice(0, 20)}${msgId.length > 20 ? "…" : ""}` : latest?.id ?? "—"}
                        </code>
                        {"template_id" in (latest ?? {}) && (() => {
                          const t = latest as { template_id?: string; template_name?: string };
                          return t.template_id && (
                            <span className="text-[10px] text-muted-foreground">
                              {t.template_name ? `${t.template_name} (${t.template_id})` : t.template_id}
                            </span>
                          );
                        })()}
                      </div>
                      <ul className="space-y-1 pl-2 border-l-2 border-border">
                        {statuses.map((s, idx) => (
                          <li key={`${s.id}-${idx}`} className="flex items-center gap-2 text-xs">
                            <Badge variant="outline" className="text-[10px] capitalize">
                              {String(s.status ?? "unknown").replaceAll("_", " ")}
                            </Badge>
                            <span className="text-muted-foreground">
                              {new Date(s.created_at).toLocaleString()}
                            </span>
                            {s.error_message && (
                              <span className="text-destructive truncate max-w-[200px]" title={s.error_message}>
                                {s.error_message}
                              </span>
                            )}
                          </li>
                        ))}
                      </ul>
                    </div>
                  );
                })}
              </div>
            )}
          </GlassPanel>
        </>
      ) : (
        <GlassPanel className="p-6">
          <EmptyState
            title="Generate a report"
            description="Pick optional filters (flow/template/date range) and click Generate."
          />
        </GlassPanel>
      )}
    </div>
  );
}


