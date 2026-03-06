import { useState, useRef, useEffect, useCallback } from "react";
import { GlassPanel } from "@/components/radiant/glass-panel";
import { Subheading } from "@/components/radiant/text";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { 
  Send, 
  Loader2, 
  Sparkles, 
  MessageSquare, 
  ChevronLeft, 
  ChevronRight,
  Clock,
  Plus,
  Wifi,
  WifiOff,
  AlertCircle,
  Bot,
  Bug
} from "lucide-react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { useAssistantPreferences } from "@/hooks/use-preferences";
import { useDesktopAgent, DesktopAgentSession, DesktopAgentMessage, OutgoingCommand } from "@/hooks/useWebSocket";
import { createApiUrl, desktopAgentApi, getAuthHeaders, DesktopAgentInfo, DesktopAgentStatus } from "@/lib/api";
import { queryClient } from "@/lib/queryClient";

type Message = {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  timestamp: Date;
  isStreaming?: boolean;
  isDebug?: boolean;
};

const DEBUG_MODE_KEY = "crm-assistant-debug-mode";

export function CRMAssistantWidget() {
  const { isSidebarCollapsed, setSidebarCollapsed } = useAssistantPreferences();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [streamingContent, setStreamingContent] = useState<string>("");
  const [pendingMessage, setPendingMessage] = useState<string | null>(null);
  const [debugMode, setDebugMode] = useState<boolean>(() => {
    try {
      return localStorage.getItem(DEBUG_MODE_KEY) === "true";
    } catch {
      return false;
    }
  });
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Toggle debug mode and persist to localStorage
  const toggleDebugMode = useCallback(() => {
    setDebugMode((prev) => {
      const newValue = !prev;
      try {
        localStorage.setItem(DEBUG_MODE_KEY, String(newValue));
      } catch {
        // Ignore localStorage errors
      }
      return newValue;
    });
  }, []);

  // Keyboard shortcut: Ctrl+Shift+D to toggle debug mode
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.shiftKey && e.key.toLowerCase() === "d") {
        e.preventDefault();
        toggleDebugMode();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [toggleDebugMode]);

  // Add debug message helper
  const addDebugMessage = useCallback((eventType: string, payload: unknown) => {
    const debugMsg: Message = {
      id: `debug-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      role: "system",
      content: `[WS] ${eventType}\n${JSON.stringify(payload, null, 2)}`,
      timestamp: new Date(),
      isDebug: true,
    };
    setMessages((prev) => [...prev, debugMsg]);
  }, []);

  // Fetch sessions from API using proper auth headers
  const sessionsQuery = useQuery({
    queryKey: ["desktop-agent", "sessions"],
    queryFn: async () => {
      try {
        const response = await fetch(createApiUrl(desktopAgentApi.getSessions()), {
          headers: getAuthHeaders(),
        });
        if (!response.ok) return [];
        const data = await response.json();
        // Handle different response formats
        if (Array.isArray(data)) return data;
        if (data?.sessions && Array.isArray(data.sessions)) return data.sessions;
        if (data?.results && Array.isArray(data.results)) return data.results;
        if (data?.data && Array.isArray(data.data)) return data.data;
        return [];
      } catch (error) {
        console.error("Failed to fetch sessions:", error);
        return [];
      }
    },
    refetchInterval: 30000,
  });

  // Fetch available agents
  const agentsQuery = useQuery({
    queryKey: ["desktop-agent", "agents"],
    queryFn: async () => {
      try {
        const response = await fetch(createApiUrl(desktopAgentApi.getAgents()), {
          headers: getAuthHeaders(),
        });
        if (!response.ok) return [];
        const data = await response.json();
        // Handle different response formats
        if (Array.isArray(data)) return data;
        if (data?.agents && Array.isArray(data.agents)) return data.agents;
        if (data?.results && Array.isArray(data.results)) return data.results;
        if (data?.data && Array.isArray(data.data)) return data.data;
        return [];
      } catch (error) {
        console.error("Failed to fetch agents:", error);
        return [];
      }
    },
  });

  // Fetch current agent status
  const statusQuery = useQuery({
    queryKey: ["desktop-agent", "status"],
    queryFn: async () => {
      try {
        const url = createApiUrl(desktopAgentApi.getStatus());
        const response = await fetch(url, {
          headers: getAuthHeaders(),
        });
        if (!response.ok) {
          return null;
        }
        const data = await response.json();
        // Map API response format to expected format
        // API returns: { agent: { id, name, model }, enabled }
        // We need: { configured, agent_id, agent_name }
        if (data?.agent) {
          return {
            configured: data.enabled ?? true,
            agent_id: data.agent.id,
            agent_name: data.agent.name,
          } as DesktopAgentStatus;
        }
        // Handle direct format
        if (data?.agent_id) {
          return data as DesktopAgentStatus;
        }
        return { configured: false } as DesktopAgentStatus;
      } catch (error) {
        console.error("Failed to fetch status:", error);
        return null;
      }
    },
  });

  // Mutation to set current agent
  const setAgentMutation = useMutation({
    mutationFn: async (agentId: string) => {
      const response = await fetch(desktopAgentApi.setAgent(), {
        method: "POST",
        headers: {
          ...getAuthHeaders(),
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ agent_id: agentId }),
      });
      if (!response.ok) {
        throw new Error(`Failed to set agent: ${response.status}`);
      }
      return response.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["desktop-agent", "status"] });
    },
  });

  const scrollToBottom = useCallback(() => {
    if (messagesEndRef.current) {
      const scrollContainer = messagesEndRef.current.closest('[data-radix-scroll-area-viewport]');
      if (scrollContainer) {
        scrollContainer.scrollTop = scrollContainer.scrollHeight;
      }
    }
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, streamingContent, scrollToBottom]);

  // Store debugMode in a ref to avoid stale closure in onAnyEvent
  const debugModeRef = useRef(debugMode);
  useEffect(() => {
    debugModeRef.current = debugMode;
  }, [debugMode]);

  // Store addDebugMessage in a ref to avoid stale closure
  const addDebugMessageRef = useRef(addDebugMessage);
  useEffect(() => {
    addDebugMessageRef.current = addDebugMessage;
  }, [addDebugMessage]);

  // Events to skip in debug mode (too noisy)
  const SKIP_DEBUG_EVENTS = new Set(["stream_chunk", "stream_start", "stream_end", "keep_alive"]);

  // WebSocket connection
  const agent = useDesktopAgent({
    enabled: true,
    onSend: (command: OutgoingCommand) => {
      if (debugModeRef.current) {
        addDebugMessageRef.current(`[OUT] ${command.action}`, command.data);
      }
    },
    onAnyEvent: (eventType, payload) => {
      // Log important WebSocket events when debug mode is on
      // Skip high-frequency events like stream_chunk to avoid UI spam
      if (debugModeRef.current && !SKIP_DEBUG_EVENTS.has(eventType)) {
        addDebugMessageRef.current(`[IN] ${eventType}`, payload);
      }
    },
    onSessionCreated: (session) => {
      setSelectedSessionId(session.session_id);
      setMessages((prev) => prev.filter((m) => m.isDebug)); // Keep debug messages
      // If there's a pending message, send it now
      if (pendingMessage) {
        agent.sendMessage(pendingMessage, session.session_id);
        const userMessage: Message = {
          id: Date.now().toString(),
          role: "user",
          content: pendingMessage,
          timestamp: new Date(),
        };
        setMessages((prev) => [...prev.filter((m) => m.isDebug), userMessage]);
        setPendingMessage(null);
      }
      sessionsQuery.refetch();
    },
    onSessionResumed: (session, historyMessages) => {
      setSelectedSessionId(session.session_id);
      // Convert history messages to our format
      const converted: Message[] = historyMessages.map((msg: DesktopAgentMessage) => ({
        id: msg.message_id || `${Date.now()}-${Math.random()}`,
        role: msg.role || "assistant",
        content: msg.content || "",
        timestamp: msg.timestamp ? new Date(msg.timestamp) : new Date(),
      }));
      setMessages((prev) => [...prev.filter((m) => m.isDebug), ...converted]);
    },
    onMessageReceived: (message) => {
      if (message.role === "assistant" && message.content) {
        const newMessage: Message = {
          id: message.message_id || `${Date.now()}-assistant`,
          role: "assistant",
          content: message.content,
          timestamp: message.timestamp ? new Date(message.timestamp) : new Date(),
        };
        setMessages((prev) => [...prev, newMessage]);
        setStreamingContent("");
      }
    },
    onStreamChunk: (chunk) => {
      setStreamingContent((prev) => prev + chunk);
    },
    onStreamComplete: (message) => {
      if (message.content) {
        const newMessage: Message = {
          id: message.message_id || `${Date.now()}-assistant`,
          role: "assistant",
          content: message.content,
          timestamp: new Date(),
        };
        setMessages((prev) => [...prev, newMessage]);
      }
      setStreamingContent("");
    },
    onError: (error) => {
      const errorMessage: Message = {
        id: `${Date.now()}-error`,
        role: "assistant",
        content: `Error: ${error}`,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errorMessage]);
      setStreamingContent("");
    },
  });

  // Refocus input when streaming completes
  useEffect(() => {
    if (!agent.isStreaming) {
      inputRef.current?.focus();
    }
  }, [agent.isStreaming]);

  // Auto-resume last session when WebSocket connects and sessions are loaded
  const hasAutoResumedRef = useRef(false);
  useEffect(() => {
    const sessions = sessionsQuery.data || [];
    // Only auto-resume once, when connected with sessions available and no active session
    if (
      agent.isConnected && 
      sessions.length > 0 && 
      !agent.currentSessionId && 
      !hasAutoResumedRef.current
    ) {
      // Resume the most recent session (first in list, assuming sorted by last_interaction desc)
      const lastSession = sessions[0];
      hasAutoResumedRef.current = true;
      agent.resumeSession(lastSession.session_id);
    }
  }, [agent.isConnected, agent.currentSessionId, sessionsQuery.data, agent]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || agent.isStreaming || !currentStatus?.agent_id) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      role: "user",
      content: input,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);

    if (!agent.currentSessionId) {
      // Store message and create session - will send after session created
      setPendingMessage(input);
      agent.createSession();
    } else {
      agent.sendMessage(input);
    }

    setInput("");
    setTimeout(() => {
      inputRef.current?.focus();
    }, 0);
  };

  const handleNewChat = () => {
    setMessages((prev) => prev.filter((m) => m.isDebug)); // Keep debug messages
    setSelectedSessionId(null);
    setStreamingContent("");
    agent.createSession();
  };

  const handleSelectSession = (sessionId: string) => {
    if (sessionId === selectedSessionId) return;
    setMessages((prev) => prev.filter((m) => m.isDebug)); // Keep debug messages
    setStreamingContent("");
    agent.resumeSession(sessionId);
  };

  const handleAgentChange = (agentId: string) => {
    setAgentMutation.mutate(agentId);
  };

  const handleClearDebugMessages = () => {
    setMessages((prev) => prev.filter((m) => !m.isDebug));
  };

  const sessions = sessionsQuery.data || [];
  const agents = agentsQuery.data || [];
  const currentStatus = statusQuery.data;
  const showAgentSelector = agents.length > 0;

  return (
    <GlassPanel className="p-0 overflow-hidden" data-testid="widget-crm-assistant">
      <div className="flex h-[400px]">
        {/* Sidebar - Previous Conversations */}
        <div
          className={`border-r border-border transition-all duration-200 flex flex-col ${
            isSidebarCollapsed ? "w-0 overflow-hidden" : "w-64"
          }`}
        >
          <div className="p-3 border-b border-border flex items-center justify-between gap-1">
            <Subheading className="text-sm flex items-center gap-2">
              <Clock className="h-4 w-4" />
              History
            </Subheading>
            <div className="flex items-center gap-1">
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6"
                onClick={handleNewChat}
                data-testid="button-new-chat"
              >
                <Plus className="h-4 w-4" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6"
                onClick={() => setSidebarCollapsed(true)}
                data-testid="button-collapse-sidebar"
              >
                <ChevronLeft className="h-4 w-4" />
              </Button>
            </div>
          </div>
          <ScrollArea className="flex-1">
            <div className="p-2 space-y-1">
              {sessions.length === 0 ? (
                <p className="text-xs text-muted-foreground text-center py-4">
                  No previous chats
                </p>
              ) : (
                sessions.map((session: DesktopAgentSession) => (
                  <button
                    key={session.session_id}
                    type="button"
                    onClick={() => handleSelectSession(session.session_id)}
                    className={`w-full text-left p-2 rounded-md text-sm transition-colors ${
                      selectedSessionId === session.session_id
                        ? "bg-primary/10"
                        : "hover-elevate"
                    }`}
                    data-testid={`conversation-item-${session.session_id}`}
                  >
                    <p className="font-medium truncate">
                      {session.current_agent || "Chat"}
                    </p>
                    {session.last_message_preview && (
                      <p className="text-xs text-muted-foreground truncate">
                        {session.last_message_preview}
                      </p>
                    )}
                    <p className="text-xs text-muted-foreground mt-1">
                      {new Date(session.last_interaction).toLocaleTimeString([], { 
                        hour: '2-digit', 
                        minute: '2-digit' 
                      })}
                    </p>
                  </button>
                ))
              )}
            </div>
          </ScrollArea>
        </div>

        {/* Main Chat Area */}
        <div className="flex-1 flex flex-col">
          {/* Header */}
          <div className="p-3 border-b border-border flex items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              {isSidebarCollapsed && (
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-6 w-6"
                  onClick={() => setSidebarCollapsed(false)}
                  data-testid="button-expand-sidebar"
                >
                  <ChevronRight className="h-4 w-4" />
                </Button>
              )}
              <Subheading className="flex items-center gap-2">
                <MessageSquare className="h-4 w-4" />
                CRM Assistant
              </Subheading>
            </div>
            <div className="flex items-center gap-2">
              {debugMode && (
                <>
                  <Badge 
                    variant="outline" 
                    className="text-[10px] h-5 bg-orange-500/10 border-orange-500/50 text-orange-600 dark:text-orange-400"
                    data-testid="badge-debug-mode"
                  >
                    <Bug className="h-3 w-3 mr-1" />
                    DEBUG
                  </Badge>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-5 text-[10px] px-2"
                    onClick={handleClearDebugMessages}
                    data-testid="button-clear-debug"
                  >
                    Clear
                  </Button>
                </>
              )}
              {showAgentSelector && (
                <Select
                  value={currentStatus?.agent_id || ""}
                  onValueChange={handleAgentChange}
                  disabled={setAgentMutation.isPending}
                >
                  <SelectTrigger 
                    className="h-7 w-[140px] text-xs"
                    data-testid="select-agent"
                  >
                    <Bot className="h-3 w-3 mr-1" />
                    <SelectValue placeholder="Select agent" />
                  </SelectTrigger>
                  <SelectContent>
                    {agents.map((agentItem: DesktopAgentInfo) => (
                      <SelectItem 
                        key={agentItem.id} 
                        value={agentItem.id}
                        data-testid={`agent-option-${agentItem.id}`}
                      >
                        {agentItem.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
              <Badge 
                variant={agent.isConnected ? "default" : "secondary"}
                className="text-[10px] h-5"
              >
                {agent.isConnected ? (
                  <span className="flex items-center gap-1">
                    <Wifi className="h-3 w-3" />
                    Live
                  </span>
                ) : agent.status === "connecting" ? (
                  <span className="flex items-center gap-1">
                    <Loader2 className="h-3 w-3 animate-spin" />
                    Connecting
                  </span>
                ) : agent.status === "error" ? (
                  <span className="flex items-center gap-1">
                    <AlertCircle className="h-3 w-3" />
                    Error
                  </span>
                ) : (
                  <span className="flex items-center gap-1">
                    <WifiOff className="h-3 w-3" />
                    Offline
                  </span>
                )}
              </Badge>
            </div>
          </div>

          {/* Messages Area */}
          <ScrollArea className="flex-1 p-4">
            {messages.length === 0 && !streamingContent ? (
              <div className="flex items-center justify-center h-full text-center">
                <div className="flex flex-col items-center gap-3 text-muted-foreground">
                  <div className="flex items-center gap-3">
                    <Sparkles className="h-5 w-5" style={{ color: '#ffba08' }} />
                    <p className="text-sm">
                      Ask about contacts, deals, campaigns, or get insights...
                    </p>
                  </div>
                  {debugMode && (
                    <p className="text-xs text-orange-500">
                      Debug mode active (Ctrl+Shift+D to toggle)
                    </p>
                  )}
                </div>
              </div>
            ) : (
              <div className="space-y-3">
                {messages.map((message) => (
                  <div
                    key={message.id}
                    className={`flex ${
                      message.role === "user" 
                        ? "justify-end" 
                        : message.isDebug 
                          ? "justify-center" 
                          : "justify-start"
                    }`}
                  >
                    {message.isDebug ? (
                      <div className="max-w-[95%] rounded-md px-3 py-2 bg-orange-500/10 border border-orange-500/30 font-mono text-[11px]">
                        <pre className="whitespace-pre-wrap overflow-x-auto text-orange-700 dark:text-orange-300">
                          {message.content}
                        </pre>
                      </div>
                    ) : (
                      <div
                        className={`max-w-[80%] rounded-lg px-4 py-3 ${
                          message.role === "user"
                            ? "bg-primary text-primary-foreground"
                            : "bg-muted"
                        }`}
                      >
                        <p className="text-sm whitespace-pre-wrap">{message.content}</p>
                        <span className="text-xs opacity-70 mt-1 block">
                          {message.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                        </span>
                      </div>
                    )}
                  </div>
                ))}
                {streamingContent && (
                  <div className="flex justify-start">
                    <div className="max-w-[80%] rounded-lg px-4 py-3 bg-muted">
                      <p className="text-sm whitespace-pre-wrap">{streamingContent}</p>
                      <Loader2 className="h-3 w-3 animate-spin mt-1 opacity-50" />
                    </div>
                  </div>
                )}
                {agent.isStreaming && !streamingContent && (
                  <div className="flex justify-start">
                    <div className="bg-muted rounded-lg px-4 py-3 flex items-center gap-2">
                      <Loader2 className="h-4 w-4 animate-spin" />
                      <span className="text-sm text-muted-foreground">Thinking...</span>
                    </div>
                  </div>
                )}
                <div ref={messagesEndRef} />
              </div>
            )}
          </ScrollArea>

          {/* Input Area */}
          <div className="p-4 border-t border-border">
            <form onSubmit={handleSubmit} className="flex gap-2">
              <Input
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Ask anything about your CRM..."
                className="flex-1"
                disabled={agent.isStreaming || !agent.isConnected}
                autoFocus
                data-testid="input-assistant-message"
              />
              <Button
                type="submit"
                size="icon"
                disabled={!input.trim() || agent.isStreaming || !agent.isConnected || !currentStatus?.agent_id}
                data-testid="button-send-assistant-message"
              >
                {agent.isStreaming ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Send className="h-4 w-4" />
                )}
              </Button>
            </form>
          </div>
        </div>
      </div>
    </GlassPanel>
  );
}
