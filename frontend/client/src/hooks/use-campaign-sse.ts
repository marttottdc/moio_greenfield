import { useEffect, useRef, useState, useCallback } from "react";
import type {
  CampaignSSEEvent,
  CampaignStatsEvent,
  CampaignMessageEvent,
  CampaignTimelineEvent,
  CampaignFSMStatsEvent,
  CampaignScheduledEvent,
  CampaignLaunchedEvent,
  CampaignCompletedEvent,
  MessageSentEvent,
  MessageDeliveredEvent,
  MessageFailedEvent,
  CampaignFSMSSEEvent,
} from "@shared/schema";

export type SSEConnectionState = "connecting" | "connected" | "disconnected" | "error";

interface UseCampaignSSEOptions {
  campaignId?: string;
  enabled?: boolean;
  onStats?: (event: CampaignStatsEvent) => void;
  onMessage?: (event: CampaignMessageEvent) => void;
  onTimeline?: (event: CampaignTimelineEvent) => void;
  onError?: (error: Event) => void;
  onConnect?: () => void;
  onDisconnect?: () => void;
  maxRetries?: number;
  baseRetryDelay?: number;
}

interface UseCampaignSSEReturn {
  connectionState: SSEConnectionState;
  lastEventId: string | null;
  stats: CampaignStatsEvent | null;
  messages: CampaignMessageEvent[];
  timeline: CampaignTimelineEvent[];
  reconnect: () => void;
  disconnect: () => void;
}

export function useCampaignSSE(options: UseCampaignSSEOptions = {}): UseCampaignSSEReturn {
  const {
    campaignId,
    enabled = true,
    onStats,
    onMessage,
    onTimeline,
    onError,
    onConnect,
    onDisconnect,
    maxRetries = 5,
    baseRetryDelay = 1000,
  } = options;

  const [connectionState, setConnectionState] = useState<SSEConnectionState>("disconnected");
  const [lastEventId, setLastEventId] = useState<string | null>(null);
  const [stats, setStats] = useState<CampaignStatsEvent | null>(null);
  const [messages, setMessages] = useState<CampaignMessageEvent[]>([]);
  const [timeline, setTimeline] = useState<CampaignTimelineEvent[]>([]);

  const eventSourceRef = useRef<EventSource | null>(null);
  const retryCountRef = useRef(0);
  const retryTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);

  const clearRetryTimeout = useCallback(() => {
    if (retryTimeoutRef.current) {
      clearTimeout(retryTimeoutRef.current);
      retryTimeoutRef.current = null;
    }
  }, []);

  const disconnect = useCallback(() => {
    clearRetryTimeout();
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    if (mountedRef.current) {
      setConnectionState("disconnected");
      onDisconnect?.();
    }
  }, [clearRetryTimeout, onDisconnect]);

  const connect = useCallback(() => {
    if (!enabled || eventSourceRef.current) return;

    clearRetryTimeout();

    const params = new URLSearchParams();
    if (campaignId) {
      params.set("campaign_id", campaignId);
    }

    const url = `/api/v1/campaigns/stream${params.toString() ? `?${params.toString()}` : ""}`;

    setConnectionState("connecting");

    const eventSource = new EventSource(url);
    eventSourceRef.current = eventSource;

    eventSource.onopen = () => {
      if (!mountedRef.current) return;
      retryCountRef.current = 0;
      setConnectionState("connected");
      onConnect?.();
    };

    eventSource.onerror = (event) => {
      if (!mountedRef.current) return;

      eventSource.close();
      eventSourceRef.current = null;
      setConnectionState("error");
      onError?.(event);

      if (retryCountRef.current < maxRetries && enabled) {
        const delay = baseRetryDelay * Math.pow(2, retryCountRef.current);
        retryCountRef.current++;

        retryTimeoutRef.current = setTimeout(() => {
          if (mountedRef.current && enabled) {
            connect();
          }
        }, delay);
      } else {
        setConnectionState("disconnected");
        onDisconnect?.();
      }
    };

    const handleEvent = (event: MessageEvent) => {
      if (!mountedRef.current) return;

      try {
        const data = JSON.parse(event.data) as CampaignSSEEvent;
        setLastEventId(event.lastEventId || null);

        switch (data.type) {
          case "stats":
            setStats(data);
            onStats?.(data);
            break;
          case "message":
            setMessages((prev) => {
              const exists = prev.some((m) => m.message_id === data.message_id);
              if (exists) {
                return prev.map((m) =>
                  m.message_id === data.message_id ? data : m
                );
              }
              return [...prev, data].slice(-100);
            });
            onMessage?.(data);
            break;
          case "timeline":
            setTimeline((prev) => [...prev, data].slice(-50));
            onTimeline?.(data);
            break;
        }
      } catch (error) {
        console.error("Failed to parse SSE event:", error);
      }
    };

    eventSource.addEventListener("stats", handleEvent);
    eventSource.addEventListener("message", handleEvent);
    eventSource.addEventListener("timeline", handleEvent);
  }, [
    enabled,
    campaignId,
    clearRetryTimeout,
    maxRetries,
    baseRetryDelay,
    onConnect,
    onDisconnect,
    onError,
    onStats,
    onMessage,
    onTimeline,
  ]);

  const reconnect = useCallback(() => {
    disconnect();
    retryCountRef.current = 0;
    setStats(null);
    setMessages([]);
    setTimeline([]);
    setTimeout(() => {
      if (mountedRef.current && enabled) {
        connect();
      }
    }, 100);
  }, [disconnect, connect, enabled]);

  useEffect(() => {
    mountedRef.current = true;

    if (enabled) {
      connect();
    }

    return () => {
      mountedRef.current = false;
      disconnect();
    };
  }, [enabled, campaignId, connect, disconnect]);

  return {
    connectionState,
    lastEventId,
    stats,
    messages,
    timeline,
    reconnect,
    disconnect,
  };
}

interface UseCampaignFSMSSEOptions {
  campaignId?: string;
  enabled?: boolean;
  onStats?: (event: CampaignFSMStatsEvent) => void;
  onScheduled?: (event: CampaignScheduledEvent) => void;
  onLaunched?: (event: CampaignLaunchedEvent) => void;
  onCompleted?: (event: CampaignCompletedEvent) => void;
  onMessageSent?: (event: MessageSentEvent) => void;
  onMessageDelivered?: (event: MessageDeliveredEvent) => void;
  onMessageFailed?: (event: MessageFailedEvent) => void;
  onError?: (error: Event) => void;
  onConnect?: () => void;
  onDisconnect?: () => void;
  maxRetries?: number;
  baseRetryDelay?: number;
}

interface MessageLogEntry {
  id: string;
  contact_id: string;
  message_id?: string;
  status: "sent" | "delivered" | "failed";
  error?: string;
  timestamp: string;
}

interface UseCampaignFSMSSEReturn {
  connectionState: SSEConnectionState;
  lastEventId: string | null;
  stats: CampaignFSMStatsEvent | null;
  isScheduled: boolean;
  scheduleDate: string | null;
  isLaunched: boolean;
  isCompleted: boolean;
  completionReason: string | null;
  messageLog: MessageLogEntry[];
  reconnect: () => void;
  disconnect: () => void;
  clearMessageLog: () => void;
}

export function useCampaignFSMSSE(options: UseCampaignFSMSSEOptions = {}): UseCampaignFSMSSEReturn {
  const {
    campaignId,
    enabled = true,
    onStats,
    onScheduled,
    onLaunched,
    onCompleted,
    onMessageSent,
    onMessageDelivered,
    onMessageFailed,
    onError,
    onConnect,
    onDisconnect,
    maxRetries = 5,
    baseRetryDelay = 1000,
  } = options;

  const [connectionState, setConnectionState] = useState<SSEConnectionState>("disconnected");
  const [lastEventId, setLastEventId] = useState<string | null>(null);
  const [stats, setStats] = useState<CampaignFSMStatsEvent | null>(null);
  const [isScheduled, setIsScheduled] = useState(false);
  const [scheduleDate, setScheduleDate] = useState<string | null>(null);
  const [isLaunched, setIsLaunched] = useState(false);
  const [isCompleted, setIsCompleted] = useState(false);
  const [completionReason, setCompletionReason] = useState<string | null>(null);
  const [messageLog, setMessageLog] = useState<MessageLogEntry[]>([]);

  const eventSourceRef = useRef<EventSource | null>(null);
  const retryCountRef = useRef(0);
  const retryTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);

  const clearRetryTimeout = useCallback(() => {
    if (retryTimeoutRef.current) {
      clearTimeout(retryTimeoutRef.current);
      retryTimeoutRef.current = null;
    }
  }, []);

  const clearMessageLog = useCallback(() => {
    setMessageLog([]);
  }, []);

  const disconnect = useCallback(() => {
    clearRetryTimeout();
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    if (mountedRef.current) {
      setConnectionState("disconnected");
      onDisconnect?.();
    }
  }, [clearRetryTimeout, onDisconnect]);

  const connect = useCallback(() => {
    if (!enabled || eventSourceRef.current) return;

    clearRetryTimeout();

    const params = new URLSearchParams();
    if (campaignId) {
      params.set("campaign_id", campaignId);
    }

    const url = `/api/v1/campaigns/stream${params.toString() ? `?${params.toString()}` : ""}`;

    setConnectionState("connecting");

    const eventSource = new EventSource(url);
    eventSourceRef.current = eventSource;

    eventSource.onopen = () => {
      if (!mountedRef.current) return;
      retryCountRef.current = 0;
      setConnectionState("connected");
      onConnect?.();
    };

    eventSource.onerror = (event) => {
      if (!mountedRef.current) return;

      eventSource.close();
      eventSourceRef.current = null;
      setConnectionState("error");
      onError?.(event);

      if (retryCountRef.current < maxRetries && enabled) {
        const delay = baseRetryDelay * Math.pow(2, retryCountRef.current);
        retryCountRef.current++;

        retryTimeoutRef.current = setTimeout(() => {
          if (mountedRef.current && enabled) {
            connect();
          }
        }, delay);
      } else {
        setConnectionState("disconnected");
        onDisconnect?.();
      }
    };

    const handleFSMEvent = (event: MessageEvent) => {
      if (!mountedRef.current) return;

      try {
        const data = JSON.parse(event.data) as CampaignFSMSSEEvent;
        setLastEventId(event.lastEventId || null);

        switch (data.type) {
          case "stats":
            setStats(data);
            onStats?.(data);
            break;

          case "campaign_scheduled":
            setIsScheduled(true);
            setScheduleDate(data.schedule_date);
            onScheduled?.(data);
            break;

          case "campaign_launched":
            setIsLaunched(true);
            onLaunched?.(data);
            break;

          case "campaign_completed":
            setIsCompleted(true);
            setCompletionReason(data.reason);
            onCompleted?.(data);
            break;

          case "message_sent":
            setMessageLog((prev) => [
              ...prev,
              {
                id: `${data.contact_id}-${data.message_id}`,
                contact_id: data.contact_id,
                message_id: data.message_id,
                status: "sent" as const,
                timestamp: data.timestamp || new Date().toISOString(),
              },
            ].slice(-500));
            onMessageSent?.(data);
            break;

          case "message_delivered":
            setMessageLog((prev) => {
              const existingIndex = prev.findIndex(
                (m) => m.contact_id === data.contact_id && m.message_id === data.message_id
              );
              if (existingIndex >= 0) {
                const updated = [...prev];
                updated[existingIndex] = {
                  ...updated[existingIndex],
                  status: "delivered" as const,
                  timestamp: data.timestamp || new Date().toISOString(),
                };
                return updated;
              }
              return [
                ...prev,
                {
                  id: `${data.contact_id}-${data.message_id}`,
                  contact_id: data.contact_id,
                  message_id: data.message_id,
                  status: "delivered" as const,
                  timestamp: data.timestamp || new Date().toISOString(),
                },
              ].slice(-500);
            });
            onMessageDelivered?.(data);
            break;

          case "message_failed":
            setMessageLog((prev) => [
              ...prev,
              {
                id: `${data.contact_id}-failed-${Date.now()}`,
                contact_id: data.contact_id,
                status: "failed" as const,
                error: data.error,
                timestamp: data.timestamp || new Date().toISOString(),
              },
            ].slice(-500));
            onMessageFailed?.(data);
            break;
        }
      } catch (error) {
        console.error("Failed to parse FSM SSE event:", error);
      }
    };

    eventSource.addEventListener("stats", handleFSMEvent);
    eventSource.addEventListener("campaign_scheduled", handleFSMEvent);
    eventSource.addEventListener("campaign_launched", handleFSMEvent);
    eventSource.addEventListener("campaign_completed", handleFSMEvent);
    eventSource.addEventListener("message_sent", handleFSMEvent);
    eventSource.addEventListener("message_delivered", handleFSMEvent);
    eventSource.addEventListener("message_failed", handleFSMEvent);
  }, [
    enabled,
    campaignId,
    clearRetryTimeout,
    maxRetries,
    baseRetryDelay,
    onConnect,
    onDisconnect,
    onError,
    onStats,
    onScheduled,
    onLaunched,
    onCompleted,
    onMessageSent,
    onMessageDelivered,
    onMessageFailed,
  ]);

  const reconnect = useCallback(() => {
    disconnect();
    retryCountRef.current = 0;
    setStats(null);
    setIsScheduled(false);
    setScheduleDate(null);
    setIsLaunched(false);
    setIsCompleted(false);
    setCompletionReason(null);
    setMessageLog([]);
    setTimeout(() => {
      if (mountedRef.current && enabled) {
        connect();
      }
    }, 100);
  }, [disconnect, connect, enabled]);

  useEffect(() => {
    mountedRef.current = true;

    if (enabled) {
      connect();
    }

    return () => {
      mountedRef.current = false;
      disconnect();
    };
  }, [enabled, campaignId, connect, disconnect]);

  return {
    connectionState,
    lastEventId,
    stats,
    isScheduled,
    scheduleDate,
    isLaunched,
    isCompleted,
    completionReason,
    messageLog,
    reconnect,
    disconnect,
    clearMessageLog,
  };
}
