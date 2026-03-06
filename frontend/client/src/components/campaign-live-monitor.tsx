import { useState } from "react";
import { useCampaignSSE, useCampaignFSMSSE, type SSEConnectionState } from "@/hooks/use-campaign-sse";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type {
  CampaignStatsEvent,
  CampaignMessageEvent,
  CampaignTimelineEvent,
  MessageStatus,
  CampaignStatus,
} from "@shared/schema";
import {
  Send,
  CheckCircle2,
  XCircle,
  Clock,
  MessageSquare,
  Eye,
  RefreshCw,
  Wifi,
  WifiOff,
  AlertTriangle,
  TrendingUp,
  Users,
  Activity,
  Loader2,
  Calendar,
  Rocket,
  CheckCheck,
} from "lucide-react";
import { formatDistanceToNow } from "date-fns";

interface CampaignLiveMonitorProps {
  campaignId: string;
  enabled?: boolean;
}

const statusColors: Record<MessageStatus, string> = {
  pending: "bg-muted text-muted-foreground",
  sent: "bg-blue-500/10 text-blue-600",
  delivered: "bg-green-500/10 text-green-600",
  read: "bg-emerald-500/10 text-emerald-600",
  failed: "bg-destructive/10 text-destructive",
  responded: "bg-primary/10 text-primary",
};

const statusIcons: Record<MessageStatus, typeof Send> = {
  pending: Clock,
  sent: Send,
  delivered: CheckCircle2,
  read: Eye,
  failed: XCircle,
  responded: MessageSquare,
};

const connectionStateConfig: Record<SSEConnectionState, { label: string; color: string; icon: typeof Wifi }> = {
  connecting: { label: "Connecting", color: "text-yellow-500", icon: Wifi },
  connected: { label: "Live", color: "text-green-500", icon: Wifi },
  disconnected: { label: "Disconnected", color: "text-muted-foreground", icon: WifiOff },
  error: { label: "Error", color: "text-destructive", icon: AlertTriangle },
};

function StatCard({
  label,
  value,
  icon: Icon,
  trend,
  percentage,
}: {
  label: string;
  value: number;
  icon: typeof Send;
  trend?: "up" | "down" | "neutral";
  percentage?: number;
}) {
  return (
    <Card className="p-4">
      <div className="flex items-center justify-between">
        <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
          <Icon className="w-5 h-5 text-primary" />
        </div>
        {trend === "up" && <TrendingUp className="w-4 h-4 text-green-500" />}
      </div>
      <div className="mt-3">
        <p className="text-2xl font-bold" data-testid={`stat-${label.toLowerCase().replace(/\s+/g, '-')}`}>
          {value.toLocaleString()}
        </p>
        <p className="text-sm text-muted-foreground">{label}</p>
        {percentage !== undefined && (
          <p className="text-xs text-muted-foreground mt-1">
            {percentage.toFixed(1)}%
          </p>
        )}
      </div>
    </Card>
  );
}

function MessageLogItem({ event }: { event: CampaignMessageEvent }) {
  const StatusIcon = statusIcons[event.status];

  return (
    <div
      className="flex items-center gap-3 p-3 rounded-lg border hover-elevate"
      data-testid={`message-log-${event.message_id}`}
    >
      <div className={`w-8 h-8 rounded-full flex items-center justify-center ${statusColors[event.status]}`}>
        <StatusIcon className="w-4 h-4" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <p className="font-medium truncate">
            {event.contact_name || event.contact_id}
          </p>
          <Badge variant="outline" className="text-xs shrink-0">
            {event.channel}
          </Badge>
        </div>
        <div className="flex items-center gap-2 text-xs text-muted-foreground mt-0.5">
          <span>{event.status}</span>
          {event.error && (
            <Tooltip>
              <TooltipTrigger>
                <AlertTriangle className="w-3 h-3 text-destructive" />
              </TooltipTrigger>
              <TooltipContent>
                <p className="max-w-xs">{event.error}</p>
              </TooltipContent>
            </Tooltip>
          )}
          <span>·</span>
          <span>{formatDistanceToNow(new Date(event.timestamp), { addSuffix: true })}</span>
        </div>
      </div>
    </div>
  );
}

function TimelineItem({ event }: { event: CampaignTimelineEvent }) {
  const statusLabels: Record<CampaignStatus, string> = {
    draft: "Draft",
    scheduled: "Scheduled",
    active: "Active",
    paused: "Paused",
    ended: "Ended",
    archived: "Archived",
  };

  return (
    <div className="flex items-start gap-3 py-2">
      <div className="w-2 h-2 rounded-full bg-primary mt-2" />
      <div>
        <p className="text-sm">
          Status changed to <Badge variant="outline">{statusLabels[event.status]}</Badge>
          {event.previous_status && (
            <span className="text-muted-foreground">
              {" "}from {statusLabels[event.previous_status]}
            </span>
          )}
        </p>
        <p className="text-xs text-muted-foreground mt-0.5">
          {formatDistanceToNow(new Date(event.timestamp), { addSuffix: true })}
          {event.changed_by && ` by ${event.changed_by}`}
        </p>
      </div>
    </div>
  );
}

export function CampaignLiveMonitor({ campaignId, enabled = true }: CampaignLiveMonitorProps) {
  const [activeTab, setActiveTab] = useState<"messages" | "timeline" | "fsm">("messages");

  const {
    connectionState,
    stats,
    messages,
    timeline,
    reconnect,
  } = useCampaignSSE({
    campaignId,
    enabled,
  });

  const {
    isScheduled,
    scheduleDate,
    isLaunched,
    isCompleted,
    completionReason,
    messageLog,
    stats: fsmStats,
  } = useCampaignFSMSSE({
    campaignId,
    enabled,
  });

  const stateConfig = connectionStateConfig[connectionState];
  const StateIcon = stateConfig.icon;

  const calculatePercentage = (value: number, total: number) => {
    if (total === 0) return 0;
    return (value / total) * 100;
  };

  const totalSent = fsmStats?.sent || stats?.sent || 0;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Activity className="w-5 h-5 text-primary" />
          <h3 className="font-semibold">Live Monitoring</h3>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1.5">
            {connectionState === "connecting" ? (
              <Loader2 className={`w-4 h-4 animate-spin ${stateConfig.color}`} />
            ) : (
              <StateIcon className={`w-4 h-4 ${stateConfig.color}`} />
            )}
            <span className={`text-sm ${stateConfig.color}`}>{stateConfig.label}</span>
          </div>
          <Button
            variant="ghost"
            size="icon"
            onClick={reconnect}
            disabled={connectionState === "connecting"}
            data-testid="button-reconnect"
          >
            <RefreshCw className={`w-4 h-4 ${connectionState === "connecting" ? "animate-spin" : ""}`} />
          </Button>
        </div>
      </div>

      {(isScheduled || isLaunched || isCompleted) && (
        <Card className="p-4">
          <div className="flex items-center flex-wrap gap-3">
            {isScheduled && !isLaunched && (
              <Badge variant="outline" className="flex items-center gap-1.5">
                <Calendar className="w-3.5 h-3.5" />
                Scheduled{scheduleDate ? ` for ${new Date(scheduleDate).toLocaleString()}` : ""}
              </Badge>
            )}
            {isLaunched && !isCompleted && (
              <Badge variant="default" className="flex items-center gap-1.5 bg-green-600">
                <Rocket className="w-3.5 h-3.5" />
                Launched
              </Badge>
            )}
            {isCompleted && (
              <Badge variant="secondary" className="flex items-center gap-1.5">
                <CheckCheck className="w-3.5 h-3.5" />
                Completed{completionReason ? ` - ${completionReason}` : ""}
              </Badge>
            )}
          </div>
        </Card>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard
          label="Sent"
          value={fsmStats?.sent || stats?.sent || 0}
          icon={Send}
        />
        <StatCard
          label="Delivered"
          value={fsmStats?.delivered || stats?.delivered || 0}
          icon={CheckCircle2}
          percentage={calculatePercentage(fsmStats?.delivered || stats?.delivered || 0, totalSent)}
        />
        <StatCard
          label="Opened"
          value={stats?.opened || 0}
          icon={Eye}
          percentage={calculatePercentage(stats?.opened || 0, totalSent)}
        />
        <StatCard
          label="Responded"
          value={stats?.responded || 0}
          icon={MessageSquare}
          percentage={calculatePercentage(stats?.responded || 0, totalSent)}
        />
      </div>

      {totalSent > 0 && (
        <Card className="p-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium">Delivery Progress</span>
            <span className="text-sm text-muted-foreground">
              {stats?.delivered || 0} / {totalSent}
            </span>
          </div>
          <Progress
            value={calculatePercentage(stats?.delivered || 0, totalSent)}
            className="h-2"
          />
          <div className="flex items-center justify-between mt-2 text-xs text-muted-foreground">
            <div className="flex items-center gap-4">
              <span className="flex items-center gap-1">
                <div className="w-2 h-2 rounded-full bg-green-500" />
                Delivered: {stats?.delivered || 0}
              </span>
              <span className="flex items-center gap-1">
                <div className="w-2 h-2 rounded-full bg-destructive" />
                Failed: {stats?.failed || 0}
              </span>
              {stats?.pending && stats.pending > 0 && (
                <span className="flex items-center gap-1">
                  <div className="w-2 h-2 rounded-full bg-yellow-500" />
                  Pending: {stats.pending}
                </span>
              )}
            </div>
          </div>
        </Card>
      )}

      <Separator />

      <div>
        <div className="flex items-center gap-2 mb-4">
          <Button
            variant={activeTab === "messages" ? "default" : "outline"}
            size="sm"
            onClick={() => setActiveTab("messages")}
            data-testid="tab-messages"
          >
            <MessageSquare className="w-4 h-4 mr-1" />
            Messages
            {messages.length > 0 && (
              <Badge variant="secondary" className="ml-2">
                {messages.length}
              </Badge>
            )}
          </Button>
          <Button
            variant={activeTab === "timeline" ? "default" : "outline"}
            size="sm"
            onClick={() => setActiveTab("timeline")}
            data-testid="tab-timeline"
          >
            <Clock className="w-4 h-4 mr-1" />
            Timeline
            {timeline.length > 0 && (
              <Badge variant="secondary" className="ml-2">
                {timeline.length}
              </Badge>
            )}
          </Button>
          <Button
            variant={activeTab === "fsm" ? "default" : "outline"}
            size="sm"
            onClick={() => setActiveTab("fsm")}
            data-testid="tab-fsm"
          >
            <Activity className="w-4 h-4 mr-1" />
            Activity Log
            {messageLog.length > 0 && (
              <Badge variant="secondary" className="ml-2">
                {messageLog.length}
              </Badge>
            )}
          </Button>
        </div>

        {activeTab === "messages" && (
          <ScrollArea className="h-[300px]">
            {messages.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full text-center p-6">
                <Users className="w-10 h-10 text-muted-foreground mb-3" />
                <p className="font-medium">No messages yet</p>
                <p className="text-sm text-muted-foreground">
                  Message activity will appear here in real-time
                </p>
              </div>
            ) : (
              <div className="space-y-2 pr-4">
                {messages.slice().reverse().map((msg) => (
                  <MessageLogItem key={msg.message_id} event={msg} />
                ))}
              </div>
            )}
          </ScrollArea>
        )}

        {activeTab === "timeline" && (
          <ScrollArea className="h-[300px]">
            {timeline.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full text-center p-6">
                <Clock className="w-10 h-10 text-muted-foreground mb-3" />
                <p className="font-medium">No timeline events</p>
                <p className="text-sm text-muted-foreground">
                  Campaign status changes will appear here
                </p>
              </div>
            ) : (
              <div className="pr-4">
                {timeline.slice().reverse().map((event, idx) => (
                  <TimelineItem key={idx} event={event} />
                ))}
              </div>
            )}
          </ScrollArea>
        )}

        {activeTab === "fsm" && (
          <ScrollArea className="h-[300px]">
            {messageLog.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full text-center p-6">
                <Activity className="w-10 h-10 text-muted-foreground mb-3" />
                <p className="font-medium">No activity yet</p>
                <p className="text-sm text-muted-foreground">
                  Message delivery events will appear here in real-time
                </p>
              </div>
            ) : (
              <div className="space-y-2 pr-4">
                {messageLog.slice().reverse().map((entry) => (
                  <div
                    key={entry.id}
                    className="flex items-center gap-3 p-3 rounded-lg border"
                    data-testid={`activity-log-${entry.id}`}
                  >
                    <div className={`w-8 h-8 rounded-full flex items-center justify-center ${
                      entry.status === "sent" ? "bg-blue-500/10 text-blue-600" :
                      entry.status === "delivered" ? "bg-green-500/10 text-green-600" :
                      "bg-destructive/10 text-destructive"
                    }`}>
                      {entry.status === "sent" && <Send className="w-4 h-4" />}
                      {entry.status === "delivered" && <CheckCircle2 className="w-4 h-4" />}
                      {entry.status === "failed" && <XCircle className="w-4 h-4" />}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <p className="font-medium truncate text-sm">
                          {entry.contact_id}
                        </p>
                        <Badge variant="outline" className="text-xs shrink-0">
                          {entry.status}
                        </Badge>
                      </div>
                      <div className="flex items-center gap-2 text-xs text-muted-foreground mt-0.5">
                        {entry.error && (
                          <Tooltip>
                            <TooltipTrigger>
                              <span className="text-destructive flex items-center gap-1">
                                <AlertTriangle className="w-3 h-3" />
                                Error
                              </span>
                            </TooltipTrigger>
                            <TooltipContent>
                              <p className="max-w-xs">{entry.error}</p>
                            </TooltipContent>
                          </Tooltip>
                        )}
                        <span>{formatDistanceToNow(new Date(entry.timestamp), { addSuffix: true })}</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </ScrollArea>
        )}
      </div>

      {stats?.updated_at && (
        <p className="text-xs text-muted-foreground text-center">
          Last updated {formatDistanceToNow(new Date(stats.updated_at), { addSuffix: true })}
        </p>
      )}
    </div>
  );
}
