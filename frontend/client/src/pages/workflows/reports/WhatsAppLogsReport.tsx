import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { GlassPanel } from "@/components/radiant/glass-panel";
import { EmptyState } from "@/components/empty-state";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { ChevronRight, MessageSquare, Phone, RefreshCw } from "lucide-react";
import {
  fetchCrmWhatsappLogs,
  type WaMessageLog,
  type WaLogStatus,
} from "@/lib/reports/crmWhatsappLogsRepo";

const statusBadgeVariant = (s: string): "default" | "secondary" | "outline" | "destructive" => {
  const v = String(s || "").toLowerCase();
  if (v === "failed" || v === "error") return "destructive";
  if (v === "read") return "default";
  if (v === "delivered") return "secondary";
  if (v === "sent") return "outline";
  return "outline";
};

function latestStatus(msg: WaMessageLog): string {
  return msg.latest_status ?? msg.last_status ?? msg.first_status ?? "unknown";
}

function recipientKey(msg: WaMessageLog): string {
  const s = (msg.recipient ?? msg.contact_phone ?? msg.contact?.phone ?? "").trim();
  return s || "—";
}

function statusTimestamp(s: WaLogStatus): string {
  return s.occurred_at ?? s.timestamp ?? "";
}

/** Events (status timeline) for one message from CRM logs. */
function MessageRow({ msg }: { msg: WaMessageLog }) {
  const status = latestStatus(msg);
  const statuses = msg.statuses ?? msg.events ?? [];
  const timeStr = msg.updated ?? msg.created ?? "—";

  return (
    <div className="p-3">
      <div className="flex items-start justify-between gap-2 flex-wrap">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            {msg.flow_execution_id && (
              <Badge variant="outline" className="text-[10px] font-normal">
                Execution {msg.flow_execution_id.slice(0, 8)}…
              </Badge>
            )}
            <Badge variant={statusBadgeVariant(status)} className="text-[10px]">
              {status}
            </Badge>
            <span className="text-xs text-muted-foreground">{timeStr}</span>
          </div>
          {(msg.contact_name || msg.contact?.name) && (
            <div className="text-xs text-muted-foreground mb-0.5">
              {msg.contact_name ?? msg.contact?.name}
            </div>
          )}
          {msg.body && (
            <p className="text-sm text-muted-foreground line-clamp-2">{msg.body}</p>
          )}
        </div>
        <code className="text-[10px] font-mono text-muted-foreground shrink-0" title={msg.msg_id}>
          {msg.msg_id.slice(0, 12)}…
        </code>
      </div>
      {statuses.length > 0 && (
        <ul className="mt-2 pl-3 space-y-1 text-xs text-muted-foreground border-l-2 border-border">
          {statuses.map((e, idx) => (
            <li key={`${e.occurred_at ?? e.timestamp ?? idx}-${idx}`} className="flex items-center gap-2">
              <Badge variant={statusBadgeVariant(e.status ?? "")} className="text-[10px]">
                {e.status ?? "—"}
              </Badge>
              <span>
                {statusTimestamp(e) ? new Date(statusTimestamp(e)).toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" }) : "—"}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** One row: phone number + expandable list of messages (CRM format). */
function PhoneRow({ phone, entries }: { phone: string; entries: WaMessageLog[] }) {
  const lastMsg = entries[entries.length - 1];
  const latestStatusVal = lastMsg ? latestStatus(lastMsg) : "unknown";

  return (
    <Collapsible className="rounded-lg border bg-card">
      <CollapsibleTrigger asChild>
        <button
          type="button"
          className="group w-full flex items-center gap-3 py-3 px-4 text-left hover:bg-muted/50 transition-colors rounded-lg"
        >
          <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-data-[state=open]:rotate-90" />
          <Phone className="h-4 w-4 shrink-0 text-muted-foreground" />
          <div className="min-w-0 flex-1">
            <span className="font-mono font-medium truncate block">{phone}</span>
            <span className="text-xs text-muted-foreground">
              {entries.length} message{entries.length !== 1 ? "s" : ""}
            </span>
          </div>
          <Badge variant={statusBadgeVariant(latestStatusVal)} className="text-[10px] shrink-0">
            {latestStatusVal}
          </Badge>
        </button>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="border-t bg-muted/20">
          <div className="divide-y divide-border/50">
            {entries.map((msg) => (
              <MessageRow key={msg.msg_id} msg={msg} />
            ))}
          </div>
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}

export function WhatsAppLogsReport() {
  const [refreshNonce, setRefreshNonce] = useState(0);
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [recipient, setRecipient] = useState("");

  const crmLogsQuery = useQuery({
    queryKey: ["reports", "whatsapp-logs", "crm", refreshNonce, fromDate, toDate, recipient.trim()],
    queryFn: () =>
      fetchCrmWhatsappLogs({
        page: 1,
        page_size: 500,
        from_date: fromDate || undefined,
        to_date: toDate || undefined,
        recipient: recipient.trim() || undefined,
      }),
    staleTime: 60_000,
  });

  const byPhone = useMemo(() => {
    const messages = crmLogsQuery.data?.messages ?? [];
    const map = new Map<string, WaMessageLog[]>();
    for (const m of messages) {
      const key = recipientKey(m);
      if (!map.has(key)) map.set(key, []);
      map.get(key)!.push(m);
    }
    return Array.from(map.entries())
      .map(([phone, entries]) => ({
        phone,
        entries: entries.sort((a, b) => {
          const ta = a.updated ?? a.created ?? "";
          const tb = b.updated ?? b.created ?? "";
          return tb.localeCompare(ta);
        }),
      }))
      .sort((a, b) => b.entries.length - a.entries.length);
  }, [crmLogsQuery.data?.messages]);

  return (
    <div className="space-y-4">
      <GlassPanel className="p-4 space-y-3">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <div className="flex items-center gap-2">
            <MessageSquare className="h-4 w-4 text-muted-foreground" />
            <h3 className="font-semibold">WhatsApp Logs</h3>
          </div>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => setRefreshNonce((n) => n + 1)}
            disabled={crmLogsQuery.isFetching}
          >
            <RefreshCw className={`h-4 w-4 mr-1 ${crmLogsQuery.isFetching ? "animate-spin" : ""}`} />
            Refresh
          </Button>
        </div>
        <p className="text-xs text-muted-foreground">
          Messages from CRM WhatsApp logs, grouped by recipient. Optional filters: date range and phone number.
        </p>
        <div className="grid gap-3 sm:grid-cols-4 items-end">
          <div>
            <Label className="text-xs">From date</Label>
            <Input type="date" value={fromDate} onChange={(e) => setFromDate(e.target.value)} className="mt-1 h-9" />
          </div>
          <div>
            <Label className="text-xs">To date</Label>
            <Input type="date" value={toDate} onChange={(e) => setToDate(e.target.value)} className="mt-1 h-9" />
          </div>
          <div>
            <Label className="text-xs">Phone number</Label>
            <Input
              type="text"
              placeholder="Filter by recipient…"
              value={recipient}
              onChange={(e) => setRecipient(e.target.value)}
              className="mt-1 h-9"
            />
          </div>
        </div>
        {crmLogsQuery.data && (
          <div className="text-xs text-muted-foreground">
            {crmLogsQuery.data.message_count} messages
            {crmLogsQuery.data.pagination && (
              <span> · page {crmLogsQuery.data.pagination.current_page} of {crmLogsQuery.data.pagination.total_pages}</span>
            )}
          </div>
        )}
      </GlassPanel>

      {crmLogsQuery.isLoading ? (
        <div className="space-y-2">
          <Skeleton className="h-14 rounded-lg" />
          <Skeleton className="h-14 rounded-lg" />
          <Skeleton className="h-14 rounded-lg" />
        </div>
      ) : crmLogsQuery.isError ? (
        <EmptyState
          title="Failed to load logs"
          description={(crmLogsQuery.error as Error)?.message ?? "Could not fetch WhatsApp logs."}
          action={{ label: "Retry", onClick: () => crmLogsQuery.refetch() }}
        />
      ) : byPhone.length === 0 ? (
        <EmptyState
          title="No WhatsApp messages"
          description="No messages in CRM WhatsApp logs for the selected filters."
        />
      ) : (
        <div className="space-y-2">
          {byPhone.map(({ phone, entries }) => (
            <PhoneRow key={phone} phone={phone} entries={entries} />
          ))}
        </div>
      )}
    </div>
  );
}
