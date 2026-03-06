import { useCallback, useEffect, useRef, useState } from "react";
import { getAccessToken, getApiBaseOverride, getApiBaseUrl } from "@/lib/api";
import { refreshAccessToken } from "@/lib/queryClient";

export type WebSocketStatus = "connecting" | "connected" | "disconnected" | "error" | "reconnecting";

export interface WebSocketMessage<T = unknown> {
  event_type: string;
  payload: T;
  timestamp?: string;
}

export interface OutgoingCommand {
  action: string;
  data: Record<string, unknown>;
  timestamp: number;
}

export interface UseWebSocketOptions<T = unknown> {
  path: string;
  enabled?: boolean;
  autoReconnect?: boolean;
  reconnectInterval?: number;
  maxReconnectAttempts?: number;
  onMessage?: (message: WebSocketMessage<T>) => void;
  onSend?: (command: OutgoingCommand) => void;
  onConnect?: () => void;
  onDisconnect?: (event: CloseEvent) => void;
  onError?: (error: Event) => void;
}

export interface UseWebSocketReturn<T = unknown> {
  status: WebSocketStatus;
  isConnected: boolean;
  lastMessage: WebSocketMessage<T> | null;
  send: (action: string, data?: Record<string, unknown>) => void;
  connect: () => void;
  disconnect: () => void;
}

export function buildWebSocketUrl(path: string): string {
  // Prefer explicit override, fallback to configured base, then current origin.
  const apiBase = getApiBaseOverride() ?? getApiBaseUrl();
  
  let wsBase: string;
  
  if (apiBase && apiBase.startsWith("https://")) {
    // Absolute HTTPS URL - convert to WSS
    wsBase = apiBase.replace("https://", "wss://");
  } else if (apiBase && apiBase.startsWith("http://")) {
    // Absolute HTTP URL - convert to WS
    wsBase = apiBase.replace("http://", "ws://");
  } else if (typeof window !== "undefined" && window.location?.origin) {
    // Relative base (e.g. "/api") or empty → use same-origin WebSocket.
    wsBase = window.location.origin.replace("https://", "wss://").replace("http://", "ws://");
  } else {
    return "";
  }
  
  // Strip API suffixes since WebSocket endpoints are at root level (e.g., /ws/*)
  wsBase = wsBase.replace(/\/api\/v1\/?$/, "");
  wsBase = wsBase.replace(/\/api\/?$/, "");
  wsBase = wsBase.replace(/\/$/, "");
  
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  
  const token = getAccessToken();
  const separator = normalizedPath.includes("?") ? "&" : "?";
  const urlWithToken = token ? `${wsBase}${normalizedPath}${separator}token=${token}` : `${wsBase}${normalizedPath}`;
  
  return urlWithToken;
}

export function useWebSocket<T = unknown>(options: UseWebSocketOptions<T>): UseWebSocketReturn<T> {
  const {
    path,
    enabled = true,
    autoReconnect = true,
    reconnectInterval = 3000,
    maxReconnectAttempts = 5,
    onMessage,
    onSend,
    onConnect,
    onDisconnect,
    onError,
  } = options;

  const [status, setStatus] = useState<WebSocketStatus>("disconnected");
  const [lastMessage, setLastMessage] = useState<WebSocketMessage<T> | null>(null);
  
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttempts = useRef(0);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const intentionalClose = useRef(false);
  const mountedRef = useRef(true);
  
  // Store callbacks in refs to avoid stale closures
  const onMessageRef = useRef(onMessage);
  const onSendRef = useRef(onSend);
  const onConnectRef = useRef(onConnect);
  const onDisconnectRef = useRef(onDisconnect);
  const onErrorRef = useRef(onError);
  
  // Update callback refs on every render
  useEffect(() => {
    onMessageRef.current = onMessage;
    onSendRef.current = onSend;
    onConnectRef.current = onConnect;
    onDisconnectRef.current = onDisconnect;
    onErrorRef.current = onError;
  });

  const clearReconnectTimeout = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
  }, []);

  const disconnect = useCallback(() => {
    intentionalClose.current = true;
    clearReconnectTimeout();
    
    if (wsRef.current) {
      wsRef.current.close(1000, "Client disconnect");
      wsRef.current = null;
    }
    
    if (mountedRef.current) {
      setStatus("disconnected");
    }
  }, [clearReconnectTimeout]);

  const connect = useCallback(async () => {
    // Skip connection if path is falsy
    if (!path) {
      return;
    }
    
    if (wsRef.current?.readyState === WebSocket.OPEN || wsRef.current?.readyState === WebSocket.CONNECTING) {
      return;
    }

    intentionalClose.current = false;
    setStatus("connecting");

    const url = buildWebSocketUrl(path);
    if (!url) {
      console.error("[WS] Cannot build WebSocket URL (missing base URL)");
      setStatus("error");
      return;
    }

    try {
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        if (!mountedRef.current) return;
        setStatus("connected");
        reconnectAttempts.current = 0;
        onConnectRef.current?.();
      };

      ws.onmessage = (event) => {
        if (!mountedRef.current) return;
        try {
          const message = JSON.parse(event.data) as WebSocketMessage<T>;
          setLastMessage(message);
          onMessageRef.current?.(message);
        } catch (error) {
          console.error("[WS] Failed to parse message:", error);
        }
      };

      ws.onerror = (error) => {
        if (!mountedRef.current) return;
        console.error("[WS] Connection error:", error);
        setStatus("error");
        onErrorRef.current?.(error);
      };

      ws.onclose = (event) => {
        if (!mountedRef.current) return;
        wsRef.current = null;
        
        onDisconnectRef.current?.(event);

        if (intentionalClose.current) {
          setStatus("disconnected");
          return;
        }

        if (event.code === 4001 || event.code === 4003) {
          refreshAccessToken().then((refreshed) => {
            if (refreshed && autoReconnect && mountedRef.current) {
              reconnectAttempts.current = 0;
              connect();
            } else {
              setStatus("error");
            }
          });
          return;
        }

        if (autoReconnect && reconnectAttempts.current < maxReconnectAttempts) {
          reconnectAttempts.current += 1;
          const delay = reconnectInterval * Math.pow(1.5, reconnectAttempts.current - 1);
          setStatus("reconnecting");
          
          reconnectTimeoutRef.current = setTimeout(() => {
            if (mountedRef.current && !intentionalClose.current) {
              connect();
            }
          }, delay);
        } else {
          setStatus("disconnected");
        }
      };
    } catch (error) {
      console.error("[WS] Failed to create WebSocket:", error);
      setStatus("error");
    }
  }, [path, autoReconnect, reconnectInterval, maxReconnectAttempts]);

  const send = useCallback((action: string, data: Record<string, unknown> = {}) => {
    if (wsRef.current?.readyState !== WebSocket.OPEN) {
      return;
    }

    const message = JSON.stringify({ action, data });
    wsRef.current.send(message);
    
    // Call onSend callback for tracking outgoing commands
    onSendRef.current?.({ action, data, timestamp: Date.now() });
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    
    // Only connect if enabled AND path is valid
    if (enabled && path) {
      connect();
    }

    return () => {
      mountedRef.current = false;
      disconnect();
    };
  }, [enabled, path, connect, disconnect]);

  return {
    status,
    isConnected: status === "connected",
    lastMessage,
    send,
    connect,
    disconnect,
  };
}

export interface TicketEventPayload {
  ticket_id?: string;
  ticket?: unknown;
  old_status?: string;
  new_status?: string;
  assigned_to?: unknown;
  comment?: unknown;
}

export function useTicketUpdates(options: {
  onTicketCreated?: (payload: TicketEventPayload) => void;
  onTicketUpdated?: (payload: TicketEventPayload) => void;
  onTicketStatusChanged?: (payload: TicketEventPayload) => void;
  onTicketAssigned?: (payload: TicketEventPayload) => void;
  onTicketCommentAdded?: (payload: TicketEventPayload) => void;
  onAnyTicketEvent?: (eventType: string, payload: TicketEventPayload) => void;
  enabled?: boolean;
} = {}) {
  const { 
    onTicketCreated, 
    onTicketUpdated, 
    onTicketStatusChanged,
    onTicketAssigned,
    onTicketCommentAdded,
    onAnyTicketEvent,
    enabled = true 
  } = options;
  
  const ws = useWebSocket<TicketEventPayload>({
    path: "/ws/tickets/",
    enabled,
    onMessage: (message) => {
      const payload = message.payload as TicketEventPayload;
      onAnyTicketEvent?.(message.event_type, payload);
      
      switch (message.event_type) {
        case "ticket_created":
          onTicketCreated?.(payload);
          break;
        case "ticket_updated":
          onTicketUpdated?.(payload);
          break;
        case "ticket_status_changed":
          onTicketStatusChanged?.(payload);
          break;
        case "ticket_assigned":
          onTicketAssigned?.(payload);
          break;
        case "ticket_comment_added":
          onTicketCommentAdded?.(payload);
          break;
      }
    },
  });

  const subscribeTicket = useCallback((ticketId: string) => {
    ws.send("subscribe_ticket", { ticket_id: ticketId });
  }, [ws]);

  return {
    ...ws,
    subscribeTicket,
  };
}

export interface WhatsAppEventPayload {
  message_id?: string;
  conversation_id?: string;
  message?: unknown;
  status?: string;
  error?: string;
}

export function useWhatsAppMessages(options: {
  onMessageReceived?: (payload: WhatsAppEventPayload) => void;
  onMessageSent?: (payload: WhatsAppEventPayload) => void;
  onMessageDelivered?: (payload: WhatsAppEventPayload) => void;
  onMessageRead?: (payload: WhatsAppEventPayload) => void;
  onMessageFailed?: (payload: WhatsAppEventPayload) => void;
  onConversationStarted?: (payload: WhatsAppEventPayload) => void;
  onAnyWhatsAppEvent?: (eventType: string, payload: WhatsAppEventPayload) => void;
  onCommandSent?: (command: OutgoingCommand) => void;
  enabled?: boolean;
} = {}) {
  const { 
    onMessageReceived,
    onMessageSent,
    onMessageDelivered,
    onMessageRead,
    onMessageFailed,
    onConversationStarted,
    onAnyWhatsAppEvent,
    onCommandSent,
    enabled = true 
  } = options;
  
  const ws = useWebSocket<WhatsAppEventPayload>({
    path: "/ws/whatsapp/",
    enabled,
    onMessage: (message) => {
      const payload = message.payload as WhatsAppEventPayload;
      onAnyWhatsAppEvent?.(message.event_type, payload);
      
      switch (message.event_type) {
        case "message_received":
          onMessageReceived?.(payload);
          break;
        case "message_sent":
          onMessageSent?.(payload);
          break;
        case "message_delivered":
          onMessageDelivered?.(payload);
          break;
        case "message_read":
          onMessageRead?.(payload);
          break;
        case "message_failed":
          onMessageFailed?.(payload);
          break;
        case "conversation_started":
          onConversationStarted?.(payload);
          break;
      }
    },
    onSend: onCommandSent,
  });

  const subscribeConversation = useCallback((conversationId: string) => {
    ws.send("subscribe_conversation", { conversation_id: conversationId });
  }, [ws]);

  const unsubscribeConversation = useCallback((conversationId: string) => {
    ws.send("unsubscribe_conversation", { conversation_id: conversationId });
  }, [ws]);

  return {
    ...ws,
    subscribeConversation,
    unsubscribeConversation,
  };
}

export interface CampaignEventPayload {
  campaign_id?: string;
  stats?: unknown;
  status?: string;
  old_status?: string;
  new_status?: string;
  recipient_id?: string;
  message_id?: string;
  error?: string;
}

export function useCampaignStats(campaignId: string | null, options: {
  onStatsUpdated?: (payload: CampaignEventPayload) => void;
  onStatusChanged?: (payload: CampaignEventPayload) => void;
  onMessageSent?: (payload: CampaignEventPayload) => void;
  onMessageDelivered?: (payload: CampaignEventPayload) => void;
  onMessageFailed?: (payload: CampaignEventPayload) => void;
  onCampaignCompleted?: (payload: CampaignEventPayload) => void;
  onAnyCampaignEvent?: (eventType: string, payload: CampaignEventPayload) => void;
  enabled?: boolean;
} = {}) {
  const { 
    onStatsUpdated,
    onStatusChanged,
    onMessageSent,
    onMessageDelivered,
    onMessageFailed,
    onCampaignCompleted,
    onAnyCampaignEvent,
    enabled = true 
  } = options;
  
  return useWebSocket<CampaignEventPayload>({
    path: campaignId ? `/ws/campaigns/${campaignId}/` : "",
    enabled: enabled && Boolean(campaignId),
    onMessage: (message) => {
      const payload = message.payload as CampaignEventPayload;
      onAnyCampaignEvent?.(message.event_type, payload);
      
      switch (message.event_type) {
        case "stats_updated":
          onStatsUpdated?.(payload);
          break;
        case "status_changed":
          onStatusChanged?.(payload);
          break;
        case "message_sent":
          onMessageSent?.(payload);
          break;
        case "message_delivered":
          onMessageDelivered?.(payload);
          break;
        case "message_failed":
          onMessageFailed?.(payload);
          break;
        case "campaign_completed":
          onCampaignCompleted?.(payload);
          break;
      }
    },
  });
}

export interface FlowPreviewEvent {
  node_id?: string;
  node_kind?: string;
  node_name?: string;
  output?: unknown;
  error?: string;
  duration_ms?: number;
  summary?: string;
  run_id?: string;
}

export interface UseFlowPreviewStreamOptions {
  flowId: string | null;
  runId?: string | null;
  onNodeStarted?: (event: FlowPreviewEvent) => void;
  onNodeFinished?: (event: FlowPreviewEvent) => void;
  onNodeError?: (event: FlowPreviewEvent) => void;
  onCompleted?: (event: FlowPreviewEvent) => void;
  onEvent?: (eventType: string, payload: FlowPreviewEvent) => void;
  enabled?: boolean;
}

export function useFlowPreviewStream(options: UseFlowPreviewStreamOptions) {
  const {
    flowId,
    runId,
    onNodeStarted,
    onNodeFinished,
    onNodeError,
    onCompleted,
    onEvent,
    enabled = true,
  } = options;

  const [streamRunId, setStreamRunId] = useState<string | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const hasSentStartRef = useRef<string | null>(null);
  
  // Store callbacks in refs to avoid stale closures
  const onNodeStartedRef = useRef(onNodeStarted);
  const onNodeFinishedRef = useRef(onNodeFinished);
  const onNodeErrorRef = useRef(onNodeError);
  const onCompletedRef = useRef(onCompleted);
  const onEventRef = useRef(onEvent);
  
  useEffect(() => {
    onNodeStartedRef.current = onNodeStarted;
    onNodeFinishedRef.current = onNodeFinished;
    onNodeErrorRef.current = onNodeError;
    onCompletedRef.current = onCompleted;
    onEventRef.current = onEvent;
  });

  const ws = useWebSocket<FlowPreviewEvent>({
    path: flowId ? `/ws/flows/${flowId}/preview/stream/` : "",
    enabled: enabled && Boolean(flowId),
    onMessage: (message) => {
      console.log("[FlowPreviewStream] Event:", message.event_type, message.payload);
      
      onEventRef.current?.(message.event_type, message.payload);

      switch (message.event_type) {
        case "connected":
          console.log("[FlowPreviewStream] Connected to preview stream");
          break;
        case "stream_started":
          setIsStreaming(true);
          break;
        case "stream_ended":
          setIsStreaming(false);
          break;
        case "node_started":
          onNodeStartedRef.current?.(message.payload);
          break;
        case "node_finished":
          onNodeFinishedRef.current?.(message.payload);
          break;
        case "node_error":
          onNodeErrorRef.current?.(message.payload);
          break;
        case "preview_completed":
          setIsStreaming(false);
          onCompletedRef.current?.(message.payload);
          break;
        case "keep_alive":
          break;
        default:
          console.log("[FlowPreviewStream] Unknown event:", message.event_type);
      }
    },
  });

  const startStream = useCallback((newRunId: string) => {
    if (!newRunId) {
      console.warn("[FlowPreviewStream] Cannot start stream - no runId provided");
      return;
    }
    console.log("[FlowPreviewStream] Starting stream for run:", newRunId);
    ws.send("start_stream", { run_id: newRunId });
    setStreamRunId(newRunId);
    setIsStreaming(true);
    hasSentStartRef.current = newRunId;
  }, [ws]);

  const stopStream = useCallback(() => {
    console.log("[FlowPreviewStream] Stopping stream");
    ws.send("stop_stream", {});
    setStreamRunId(null);
    setIsStreaming(false);
    hasSentStartRef.current = null;
  }, [ws]);

  // Reset hasSentStartRef when runId is cleared (allows new preview runs)
  useEffect(() => {
    if (runId === null) {
      hasSentStartRef.current = null;
      setStreamRunId(null);
      setIsStreaming(false);
    }
  }, [runId]);

  // Auto-start stream when connected and runId is provided (only once per runId)
  useEffect(() => {
    if (ws.isConnected && runId && runId !== hasSentStartRef.current) {
      startStream(runId);
    }
  }, [ws.isConnected, runId, startStream]);

  return {
    ...ws,
    streamRunId,
    isStreaming,
    startStream,
    stopStream,
  };
}

// Production Flow Execution Monitoring
export interface FlowExecutionEvent {
  execution_id?: string;
  node_id?: string;
  node_kind?: string;
  node_name?: string;
  output?: unknown;
  error?: string;
  duration_ms?: number;
  summary?: string;
  flow_id?: string;
  flow_name?: string;
  trigger_source?: string;
}

export interface UseFlowExecutionStreamOptions {
  executionId: string | null;
  onExecutionStarted?: (event: FlowExecutionEvent) => void;
  onNodeFinished?: (event: FlowExecutionEvent) => void;
  onNodeError?: (event: FlowExecutionEvent) => void;
  onExecutionCompleted?: (event: FlowExecutionEvent) => void;
  onEvent?: (eventType: string, payload: FlowExecutionEvent) => void;
  enabled?: boolean;
}

export function useFlowExecutionStream(options: UseFlowExecutionStreamOptions) {
  const {
    executionId,
    onExecutionStarted,
    onNodeFinished,
    onNodeError,
    onExecutionCompleted,
    onEvent,
    enabled = true,
  } = options;

  // Store callbacks in refs to avoid stale closures
  const onExecutionStartedRef = useRef(onExecutionStarted);
  const onNodeFinishedRef = useRef(onNodeFinished);
  const onNodeErrorRef = useRef(onNodeError);
  const onExecutionCompletedRef = useRef(onExecutionCompleted);
  const onEventRef = useRef(onEvent);
  
  useEffect(() => {
    onExecutionStartedRef.current = onExecutionStarted;
    onNodeFinishedRef.current = onNodeFinished;
    onNodeErrorRef.current = onNodeError;
    onExecutionCompletedRef.current = onExecutionCompleted;
    onEventRef.current = onEvent;
  });

  const ws = useWebSocket<FlowExecutionEvent>({
    path: executionId ? `/ws/flow_execution_${executionId}/` : "",
    enabled: enabled && Boolean(executionId),
    onMessage: (message) => {
      console.log("[FlowExecutionStream] Event:", message.event_type, message.payload);
      
      onEventRef.current?.(message.event_type, message.payload);

      switch (message.event_type) {
        case "execution_started":
          onExecutionStartedRef.current?.(message.payload);
          break;
        case "node_finished":
          onNodeFinishedRef.current?.(message.payload);
          break;
        case "node_error":
          onNodeErrorRef.current?.(message.payload);
          break;
        case "execution_completed":
          onExecutionCompletedRef.current?.(message.payload);
          break;
        case "keep_alive":
          break;
        default:
          console.log("[FlowExecutionStream] Unknown event:", message.event_type);
      }
    },
  });

  return ws;
}

// Desktop Agent Chat WebSocket
export interface DesktopAgentMessage {
  session_id?: string;
  message_id?: string;
  content?: string;
  role?: "user" | "assistant";
  timestamp?: string;
  is_streaming?: boolean;
  is_final?: boolean;
  error?: string;
  session?: {
    id: string;
    created_at: string;
    updated_at: string;
    is_active: boolean;
  };
}

export interface DesktopAgentSession {
  session_id: string;
  active: boolean;
  started_at: string;
  last_interaction: string;
  current_agent?: string;
  last_message_preview?: string | null;
}

export interface UseDesktopAgentOptions {
  onSessionCreated?: (session: DesktopAgentSession) => void;
  onSessionResumed?: (session: DesktopAgentSession, messages: DesktopAgentMessage[]) => void;
  onSessionClosed?: (sessionId: string) => void;
  onMessageReceived?: (message: DesktopAgentMessage) => void;
  onStreamChunk?: (chunk: string, messageId: string) => void;
  onStreamComplete?: (message: DesktopAgentMessage) => void;
  onError?: (error: string) => void;
  onAnyEvent?: (eventType: string, payload: DesktopAgentMessage) => void;
  onSend?: (command: OutgoingCommand) => void;
  enabled?: boolean;
}

export function useDesktopAgent(options: UseDesktopAgentOptions = {}) {
  const {
    onSessionCreated,
    onSessionResumed,
    onSessionClosed,
    onMessageReceived,
    onStreamChunk,
    onStreamComplete,
    onError,
    onAnyEvent,
    onSend,
    enabled = true,
  } = options;

  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const streamingContentRef = useRef<string>("");
  
  // Keep a ref to currentSessionId for use in callbacks to avoid stale closures
  const currentSessionIdRef = useRef<string | null>(null);
  
  // Update ref when state changes
  useEffect(() => {
    currentSessionIdRef.current = currentSessionId;
  }, [currentSessionId]);

  // Store callbacks in refs to avoid stale closures
  const onSessionCreatedRef = useRef(onSessionCreated);
  const onSessionResumedRef = useRef(onSessionResumed);
  const onSessionClosedRef = useRef(onSessionClosed);
  const onMessageReceivedRef = useRef(onMessageReceived);
  const onStreamChunkRef = useRef(onStreamChunk);
  const onStreamCompleteRef = useRef(onStreamComplete);
  const onErrorRef = useRef(onError);
  const onAnyEventRef = useRef(onAnyEvent);
  const onSendRef = useRef(onSend);

  useEffect(() => {
    onSessionCreatedRef.current = onSessionCreated;
    onSessionResumedRef.current = onSessionResumed;
    onSessionClosedRef.current = onSessionClosed;
    onMessageReceivedRef.current = onMessageReceived;
    onStreamChunkRef.current = onStreamChunk;
    onStreamCompleteRef.current = onStreamComplete;
    onErrorRef.current = onError;
    onAnyEventRef.current = onAnyEvent;
    onSendRef.current = onSend;
  });

  const ws = useWebSocket<DesktopAgentMessage>({
    path: "/ws/crm-agent/",
    enabled,
    onSend: (command) => {
      onSendRef.current?.(command);
    },
    onMessage: (message) => {
      const payload = message.payload;
      onAnyEventRef.current?.(message.event_type, payload);

      switch (message.event_type) {
        case "session_created": {
          // Handle both formats: session nested in payload.session OR session_id at payload level
          const wsSession = payload.session as any;
          const sessionId = wsSession?.session_id || wsSession?.id || payload.session_id;
          if (sessionId) {
            // Update ref synchronously for immediate use, then update state
            currentSessionIdRef.current = sessionId;
            setCurrentSessionId(sessionId);
            const normalizedSession: DesktopAgentSession = {
              session_id: sessionId,
              active: wsSession?.active ?? wsSession?.is_active ?? (payload as any).active ?? true,
              started_at: wsSession?.started_at || wsSession?.created_at || new Date().toISOString(),
              last_interaction: wsSession?.last_interaction || wsSession?.updated_at || new Date().toISOString(),
              current_agent: wsSession?.current_agent || (payload as any).agent_name,
              last_message_preview: wsSession?.last_message_preview || wsSession?.last_message || null,
            };
            onSessionCreatedRef.current?.(normalizedSession);
          }
          break;
        }

        case "session_resumed": {
          // Handle both formats: session nested in payload.session OR session_id at payload level
          const wsSession = payload.session as any;
          const sessionId = wsSession?.session_id || wsSession?.id || payload.session_id;
          if (sessionId) {
            // Update ref synchronously for immediate use, then update state
            currentSessionIdRef.current = sessionId;
            setCurrentSessionId(sessionId);
            const normalizedSession: DesktopAgentSession = {
              session_id: sessionId,
              active: wsSession?.active ?? wsSession?.is_active ?? (payload as any).active ?? true,
              started_at: wsSession?.started_at || wsSession?.created_at || new Date().toISOString(),
              last_interaction: wsSession?.last_interaction || wsSession?.updated_at || new Date().toISOString(),
              current_agent: wsSession?.current_agent || (payload as any).agent_name,
              last_message_preview: wsSession?.last_message_preview || wsSession?.last_message || null,
            };
            // Payload may contain messages array for history
            const messages = (payload as any).messages || [];
            onSessionResumedRef.current?.(normalizedSession, messages);
          }
          break;
        }

        case "session_closed":
          setCurrentSessionId(null);
          onSessionClosedRef.current?.(payload.session_id || "");
          break;

        case "message":
        case "assistant_message":
          setIsStreaming(false);
          onMessageReceivedRef.current?.(payload);
          break;

        case "agent_typing":
          setIsStreaming(true);
          break;

        case "stream_start":
          setIsStreaming(true);
          streamingContentRef.current = "";
          break;

        case "stream_chunk":
          if (payload.content) {
            streamingContentRef.current += payload.content;
            onStreamChunkRef.current?.(payload.content, payload.message_id || "");
          }
          break;

        case "stream_end":
          setIsStreaming(false);
          onStreamCompleteRef.current?.({
            ...payload,
            content: streamingContentRef.current,
          });
          streamingContentRef.current = "";
          break;

        case "error":
        case "agent_error":
        case "message_error":
        case "processing_error":
          setIsStreaming(false);
          onErrorRef.current?.(payload.error || (payload as any).message || "Unknown error");
          break;
      }
    },
    onError: () => {
      // WebSocket connection error - also clear streaming state
      setIsStreaming(false);
    },
    onDisconnect: () => {
      // WebSocket disconnected - also clear streaming state
      setIsStreaming(false);
    },
  });

  // Create a new session
  const createSession = useCallback(() => {
    ws.send("new_session", {});
  }, [ws]);

  // Resume an existing session
  const resumeSession = useCallback((sessionId: string) => {
    ws.send("resume_session", { session_id: sessionId });
  }, [ws]);

  // Close the current session
  const closeSession = useCallback((sessionId?: string) => {
    const id = sessionId || currentSessionIdRef.current;
    if (id) {
      ws.send("close_session", { session_id: id });
    }
  }, [ws]);

  // Send a message to the agent
  const sendMessage = useCallback((content: string, sessionId?: string) => {
    // Use ref to get latest session ID (avoids stale closure issues)
    const id = sessionId || currentSessionIdRef.current;
    if (!id) {
      console.warn("[DesktopAgent] No active session, creating one first");
      // If no session, create one and queue the message
      ws.send("new_session", {});
      // The message will need to be sent after session is created
      return;
    }
    ws.send("send_message", { 
      session_id: id, 
      content 
    });
  }, [ws]);

  return {
    ...ws,
    currentSessionId,
    isStreaming,
    createSession,
    resumeSession,
    closeSession,
    sendMessage,
  };
}
