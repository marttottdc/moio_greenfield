import { useState, useRef, useEffect, useMemo, useCallback } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { 
  Search, Send, MessageSquare, RefreshCw, Filter, 
  MessageCircle, Mail, Clock, Users, Phone, Forward, X,
  ChevronDown, UserCheck, Loader2
} from "lucide-react";
import { SiWhatsapp } from "react-icons/si";
import { fetchJson, apiRequest, queryClient } from "@/lib/queryClient";
import { apiV1 } from "@/lib/api";
import { EmptyState } from "@/components/empty-state";
import { ErrorDisplay } from "@/components/error-display";
import { PageLayout } from "@/components/layout/page-layout";
import { useToast } from "@/hooks/use-toast";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useWhatsAppMessages } from "@/hooks/useWebSocket";
import { ConnectionStatus } from "@/components/connection-status";
import { Separator } from "@/components/ui/separator";
import { emailApi } from "@/lib/integrations/emailApi";
import type { EmailAccount, EmailMessage } from "@/lib/integrations/types";

interface ConversationContact {
  id?: string;
  name?: string;
  phone?: string;
  email?: string;
  company?: string;
  avatar_url?: string | null;
  contacttype?: {
    id: string;
    name: string;
  };
}

interface ConversationMessage {
  id: string;
  conversation_id?: string;
  content: string;
  sender?: string;
  sender_name?: string;
  timestamp?: string;
  status?: string;
  type?: string;
  attachments?: any[];
}

interface Conversation {
  id: string;
  contact?: ConversationContact;
  channel?: string;
  status?: string;
  last_message?: ConversationMessage;
  unread_count?: number;
  updated_at?: string;
  tags?: string[];
  summary?: string;
  final_summary?: string;
}

interface ConversationsResponse {
  conversations?: Conversation[];
}

interface ConversationDetail {
  id: string;
  contact?: ConversationContact;
  channel?: string;
  status?: string;
  summary?: string;
  final_summary?: string;
  messages?: ConversationMessage[];
  active?: boolean;
  human_mode?: boolean;
}

interface Channel {
  id: string;
  name: string;
  type: string;
  status: string;
  capabilities: string[];
  total_conversations: number;
  active_conversations: number;
  last_activity?: string;
}

interface ChannelsResponse {
  channels?: Channel[];
}

function formatRelativeTime(timestamp?: string): string {
  if (!timestamp) return "";
  const date = new Date(timestamp);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);
  const diffWeeks = Math.floor(diffDays / 7);

  if (diffMins < 1) return "Just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  if (diffWeeks < 4) return `${diffWeeks}w ago`;
  return date.toLocaleDateString();
}

function formatMessageTime(timestamp?: string): string {
  if (!timestamp) return "";
  const date = new Date(timestamp);
  const dateStr = date.toLocaleDateString("es-ES", { 
    day: "numeric", 
    month: "long", 
    year: "numeric" 
  });
  const timeStr = date.toLocaleTimeString("es-ES", { 
    hour: "2-digit", 
    minute: "2-digit",
    hour12: false 
  });
  return `${dateStr} a las ${timeStr}`;
}

function ChatBubble({ message }: { message: ConversationMessage }) {
  const isContact = message.sender === "contact";
  const isSystem = message.sender === "system";

  if (isContact) {
    return (
      <div className="flex justify-end mb-3">
        <div
          className="max-w-[75%] rounded-lg px-3 py-2 shadow-sm bg-amber-100 dark:bg-amber-900/50 text-foreground"
          data-testid={`message-${message.id}`}
        >
          <div className="flex items-center justify-end gap-2 mb-1">
            <span className="text-xs font-semibold text-amber-700 dark:text-amber-300">
              {message.sender_name || "Contact"}
            </span>
          </div>
          <p className="text-sm leading-relaxed whitespace-pre-wrap break-words">{message.content}</p>
          <p className="text-[11px] text-right mt-1.5 text-muted-foreground">
            {formatMessageTime(message.timestamp)}
          </p>
        </div>
      </div>
    );
  }

  if (isSystem) {
    return (
      <div className="flex justify-start mb-3">
        <div
          className="max-w-[85%] rounded-lg px-3 py-2 shadow-sm bg-blue-50 dark:bg-blue-950/50 text-foreground border border-blue-200 dark:border-blue-800"
          data-testid={`message-${message.id}`}
        >
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs font-bold text-blue-600 dark:text-blue-400">
              {message.sender_name || "Moio"}
            </span>
          </div>
          <p className="text-sm leading-relaxed whitespace-pre-wrap break-words">{message.content}</p>
          <p className="text-[11px] text-right mt-1.5 text-muted-foreground">
            {formatMessageTime(message.timestamp)}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start mb-3">
      <div
        className="max-w-[75%] rounded-lg px-3 py-2 shadow-sm bg-card text-foreground border border-border"
        data-testid={`message-${message.id}`}
      >
        <div className="flex items-center gap-2 mb-1">
          <span className="text-xs font-bold text-primary">
            {message.sender_name || "Agent"}
          </span>
        </div>
        <p className="text-sm leading-relaxed whitespace-pre-wrap break-words">{message.content}</p>
        <p className="text-[11px] text-right mt-1.5 text-muted-foreground">
          {formatMessageTime(message.timestamp)}
        </p>
      </div>
    </div>
  );
}

function ClosedConversationSummary({ conversationId, fallbackContent }: { conversationId: string; fallbackContent: string }) {
  const { data, isLoading } = useQuery<ConversationDetail>({
    queryKey: [apiV1("/crm/communications/conversations/"), conversationId, "summary"],
    queryFn: async () => {
      return await fetchJson<ConversationDetail>(apiV1(`/crm/communications/conversations/${conversationId}/`));
    },
    staleTime: 5 * 60 * 1000,
    gcTime: 10 * 60 * 1000,
  });

  if (isLoading) {
    return <span className="line-clamp-2 text-muted-foreground/50">Loading summary...</span>;
  }

  const summaryText = data?.final_summary || fallbackContent;
  return <span className="line-clamp-2">{summaryText}</span>;
}

const CONVERSATIONS_PATH = apiV1("/crm/communications/conversations/");
const CHANNELS_PATH = apiV1("/crm/communications/channels/");
const SUMMARY_PATH = apiV1("/crm/communications/summary/");

interface ConversationsResponseWithMeta extends ConversationsResponse {
  pagination?: {
    total_items?: number;
    current_page?: number;
    total_pages?: number;
  };
}

interface CommunicationsSummary {
  total?: number;
  active?: number;
  closed?: number;
  pending?: number;
  awaiting_response?: number;
  total_unread?: number;
  latest_interaction?: string;
  by_channel?: Record<string, number>;
}

export default function Communications() {
  const [viewMode, setViewMode] = useState<"conversations" | "email">("conversations");
  const [selectedChat, setSelectedChat] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [channelFilter, setChannelFilter] = useState<string>("all");
  const [messageText, setMessageText] = useState("");
  const [allAccumulatedConversations, setAllAccumulatedConversations] = useState<Conversation[]>([]);
  const [totalConversationsCount, setTotalConversationsCount] = useState(0);
  const [hasMoreConversations, setHasMoreConversations] = useState(true);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [wsDebugEvent, setWsDebugEvent] = useState<{eventType: string; payload: any} | null>(null);
  const [wsOutgoingCommand, setWsOutgoingCommand] = useState<{action: string; data: Record<string, unknown>; timestamp: number} | null>(null);
  const [wsSubscriptionStatus, setWsSubscriptionStatus] = useState<{conversationId: string | null; subscribed: boolean; subscribedAt?: number} | null>(null);
  const [messagesByConversation, setMessagesByConversation] = useState<Record<string, ConversationMessage[]>>({});
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);
  const currentPageRef = useRef(1);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const conversationsListRef = useRef<HTMLDivElement>(null);
  const { toast } = useToast();
  const [emailAccountsSelected, setEmailAccountsSelected] = useState<string[]>([]);
  const [emailMessagesByAccount, setEmailMessagesByAccount] = useState<
    Record<string, { items: (EmailMessage & { accountId: string })[]; next_cursor: string | null }>
  >({});
  const [selectedEmailMessage, setSelectedEmailMessage] = useState<{ accountId: string; id: string } | null>(null);
  const [selectedEmailDetail, setSelectedEmailDetail] = useState<EmailMessage | null>(null);
  const [emailComposeForm, setEmailComposeForm] = useState({
    accountId: "",
    to: "",
    cc: "",
    bcc: "",
    subject: "",
    text: "",
    html: "",
    attachments: [] as File[],
  });

  const PAGE_SIZE = 20;

  const wsHandlers = useWhatsAppMessages({
    onCommandSent: useCallback((command: {action: string; data: Record<string, unknown>; timestamp: number}) => {
      setWsOutgoingCommand(command);
    }, []),
    onAnyWhatsAppEvent: useCallback((eventType: string, payload: any) => {
      
      // Track event for debug visualizer
      setWsDebugEvent({ eventType, payload });
      
      // Handle message events - update conversation list with latest message
      if (eventType === "message_received" || eventType === "message_sent") {
        // Extract conversation ID (could be conversation_id or session_id)
        const conversationId = payload.conversation_id || payload.session_id;
        
        if (!conversationId) return;
        
        // Build message object from payload
        // The payload can be either: { message: {...} } or { id, content, role, author, created, session_id, ... }
        let messageObj: ConversationMessage;
        
        if (payload.message) {
          messageObj = payload.message as ConversationMessage;
        } else if (payload.id && payload.content) {
          // Payload is the message itself
          messageObj = {
            id: String(payload.id),
            conversation_id: conversationId,
            content: payload.content,
            sender: payload.role === "user" ? "contact" : (payload.role === "assistant" ? "system" : payload.author),
            sender_name: payload.author || (payload.role === "user" ? "User" : "Agent"),
            timestamp: payload.created || new Date().toISOString(),
            status: "received",
            type: "text",
          };
        } else {
          return;
        }
        
        setAllAccumulatedConversations(prev => {
          const existingIdx = prev.findIndex(c => c.id === conversationId);
          if (existingIdx >= 0) {
            // Existing conversation - update it
            const updated = [...prev];
            const conv = { ...updated[existingIdx] };
            conv.last_message = messageObj;
            conv.updated_at = messageObj.timestamp || new Date().toISOString();
            if (eventType === "message_received") {
              conv.unread_count = (conv.unread_count || 0) + 1;
            }
            updated[existingIdx] = conv;
            // Re-sort by updated_at
            updated.sort((a, b) => {
              const dateA = a.updated_at ? new Date(a.updated_at).getTime() : 0;
              const dateB = b.updated_at ? new Date(b.updated_at).getTime() : 0;
              return dateB - dateA;
            });
            return updated;
          } else {
            // Unknown conversation - just track for now
            return prev;
          }
        });
        
        // Append message to the map for this conversation
        setMessagesByConversation(prev => {
          const messages = prev[conversationId] || [];
          const exists = messages.some(m => m.id === messageObj.id);
          if (exists) return prev;
          return {
            ...prev,
            [conversationId]: [...messages, messageObj]
          };
        });
      }
      
      // Handle new conversation started or ended
      if (eventType === "conversation_started") {
        const isActive = payload?.active !== false; // Default to true if not specified
        const conversationId = payload?.conversation?.id || payload?.session_id || payload?.conversation_id;
        const conversationData = payload?.conversation as Conversation | undefined;
        
        if (conversationId) {
          if (isActive) {
            // New conversation started - add to top of list
            setAllAccumulatedConversations(prev => {
              const exists = prev.some(c => c.id === conversationId);
              if (exists) return prev;
              
              // If we have the full conversation data, add immediately
              if (conversationData) {
                setTotalConversationsCount(count => count + 1);
                return [conversationData, ...prev];
              }
              
              // Create minimal conversation entry to show immediately
              const contactInfo: ConversationContact = {
                name: (conversationData as Conversation | undefined)?.contact?.name || payload.contact?.fullname || "Unknown",
                phone: (conversationData as Conversation | undefined)?.contact?.phone || payload.contact?.phone,
                email: (conversationData as Conversation | undefined)?.contact?.email || payload.contact?.email,
              };
              const minimalConv: Conversation = {
                id: conversationId,
                status: "active",
                contact: contactInfo
              };
              setTotalConversationsCount(count => count + 1);
              return [minimalConv, ...prev];
            });
            
            // If we don't have full conversation data, fetch it
            if (!conversationData) {
              fetchJson<Conversation>(`${CONVERSATIONS_PATH}${conversationId}/`)
                .then(conversation => {
                  setAllAccumulatedConversations(prev => {
                    const idx = prev.findIndex(c => c.id === conversationId);
                    if (idx >= 0) {
                      // Replace the minimal entry with full data
                      const updated = [...prev];
                      updated[idx] = conversation;
                      return updated;
                    }
                    return prev;
                  });
                })
                .catch(() => {
                  // Failed to fetch conversation details
                });
            }
          } else {
            // Conversation ended (active: false) - update status to closed
            setAllAccumulatedConversations(prev => {
              return prev.map(c => {
                if (c.id === conversationId) {
                  return { ...c, status: "closed" };
                }
                return c;
              });
            });
          }
          
          queryClient.invalidateQueries({ queryKey: [SUMMARY_PATH] });
        }
      }
      
      // Handle conversation ended event
      if (eventType === "conversation_ended") {
        const conversationId = payload?.session_id || payload?.conversation_id;
        if (conversationId) {
          setAllAccumulatedConversations(prev => {
            return prev.map(c => {
              if (c.id === conversationId) {
                return { ...c, status: "closed" };
              }
              return c;
            });
          });
          queryClient.invalidateQueries({ queryKey: [SUMMARY_PATH] });
          if (conversationId === selectedChat) {
            queryClient.invalidateQueries({ queryKey: [CONVERSATIONS_PATH, selectedChat] });
          }
        }
      }
      
      // Handle conversation status changes (ended, closed, etc.)
      if (payload.status && payload.conversation_id) {
        setAllAccumulatedConversations(prev => {
          return prev.map(c => {
            if (c.id === payload.conversation_id) {
              return { ...c, status: payload.status };
            }
            return c;
          });
        });
        if (payload.conversation_id === selectedChat) {
          queryClient.invalidateQueries({ queryKey: [CONVERSATIONS_PATH, selectedChat] });
        }
      }
    }, [selectedChat]),
  });
  
  // Track the currently subscribed conversation to properly unsubscribe when switching
  const subscribedConversationRef = useRef<string | null>(null);
  
  // Derive the selected conversation's status to use as a stable trigger
  const selectedConvForStatus = allAccumulatedConversations.find(c => c.id === selectedChat);
  const selectedConversationStatus = selectedConvForStatus?.status;
  const hasConversationData = selectedConvForStatus !== undefined;
  
  // Reset subscription ref when connection drops so reconnect triggers re-subscribe
  useEffect(() => {
    if (!wsHandlers.isConnected && subscribedConversationRef.current) {
      subscribedConversationRef.current = null;
    }
  }, [wsHandlers.isConnected]);
  
  // Subscribe/unsubscribe based on selected conversation and its status
  useEffect(() => {
    // Unsubscribe from previous conversation if we were subscribed and switching to different conversation
    if (subscribedConversationRef.current && subscribedConversationRef.current !== selectedChat && wsHandlers.isConnected) {
      wsHandlers.unsubscribeConversation(subscribedConversationRef.current);
      subscribedConversationRef.current = null;
    }
    
    // Wait for conversation data before subscribing to avoid race conditions
    if (selectedChat && wsHandlers.isConnected && hasConversationData) {
      const isActive = selectedConversationStatus !== "closed";
      
      if (isActive) {
        // Only subscribe if not already subscribed to this conversation
        if (subscribedConversationRef.current !== selectedChat) {
          wsHandlers.subscribeConversation(selectedChat);
          subscribedConversationRef.current = selectedChat;
          setWsSubscriptionStatus({
            conversationId: selectedChat,
            subscribed: true,
            subscribedAt: Date.now()
          });
        }
      } else {
        // Conversation is closed - unsubscribe if we were subscribed
        if (subscribedConversationRef.current === selectedChat) {
          wsHandlers.unsubscribeConversation(selectedChat);
        }
        subscribedConversationRef.current = null;
        setWsSubscriptionStatus({
          conversationId: selectedChat,
          subscribed: false,
          subscribedAt: undefined
        });
      }
    }
  }, [selectedChat, selectedConversationStatus, hasConversationData, wsHandlers.isConnected, wsHandlers.subscribeConversation, wsHandlers.unsubscribeConversation]);

  const channelsQuery = useQuery<ChannelsResponse>({
    queryKey: [CHANNELS_PATH],
    queryFn: async () => {
      const result = await fetchJson<ChannelsResponse>(CHANNELS_PATH);
      return result;
    },
  });

  const emailTenantQuery = useQuery<EmailAccount[]>({
    queryKey: ["email-flow-tenant"],
    queryFn: () => emailApi.flowAccounts("tenant"),
    retry: false,
  });

  const summaryQuery = useQuery<CommunicationsSummary>({
    queryKey: [SUMMARY_PATH],
    queryFn: async () => {
      try {
        return await fetchJson<CommunicationsSummary>(SUMMARY_PATH);
      } catch {
        return {};
      }
    },
    retry: false,
  });

  const conversationsQuery = useQuery<ConversationsResponseWithMeta>({
    queryKey: [CONVERSATIONS_PATH],
    queryFn: async () => {
      const result = await fetchJson<ConversationsResponseWithMeta>(CONVERSATIONS_PATH, { page: 1, page_size: PAGE_SIZE });
      currentPageRef.current = 1;
      setAllAccumulatedConversations(result.conversations || []);
      setTotalConversationsCount(result.pagination?.total_items || result.conversations?.length || 0);
      setHasMoreConversations((result.conversations?.length || 0) >= PAGE_SIZE);
      return result;
    },
  });

  useEffect(() => {
    if (conversationsQuery.data?.conversations && allAccumulatedConversations.length === 0) {
      setAllAccumulatedConversations(conversationsQuery.data.conversations);
      setTotalConversationsCount(conversationsQuery.data.pagination?.total_items || conversationsQuery.data.conversations.length);
      setHasMoreConversations(conversationsQuery.data.conversations.length >= PAGE_SIZE);
      currentPageRef.current = 1;
    }
  }, [conversationsQuery.data]);

  const emailAccounts = useMemo(() => [...(emailTenantQuery.data ?? [])], [emailTenantQuery.data]);

  useEffect(() => {
    if (emailAccounts.length > 0 && emailAccountsSelected.length === 0) {
      setEmailAccountsSelected(emailAccounts.map((a) => a.id));
      setEmailComposeForm((prev) => ({ ...prev, accountId: emailAccounts[0].id }));
    }
  }, [emailAccounts, emailAccountsSelected.length]);

  const loadMoreConversations = useCallback(async () => {
    if (isLoadingMore || !hasMoreConversations) return;
    setIsLoadingMore(true);
    try {
      const nextPage = currentPageRef.current + 1;
      const result = await fetchJson<ConversationsResponseWithMeta>(CONVERSATIONS_PATH, { page: nextPage, page_size: PAGE_SIZE });
      if (result.conversations && result.conversations.length > 0) {
        currentPageRef.current = nextPage;
        setAllAccumulatedConversations(prev => {
          const existingIds = new Set(prev.map(c => c.id));
          const newConversations = result.conversations!.filter(c => !existingIds.has(c.id));
          return [...prev, ...newConversations];
        });
        setHasMoreConversations(result.conversations.length >= PAGE_SIZE);
      } else {
        setHasMoreConversations(false);
      }
    } catch (error) {
      console.error("Failed to load more conversations:", error);
    } finally {
      setIsLoadingMore(false);
    }
  }, [isLoadingMore, hasMoreConversations]);

  const fetchEmailMessages = async (accountId: string, cursor?: string | null) => {
    const res = await emailApi.listMessages(accountId, cursor ? { cursor } : undefined);
    setEmailMessagesByAccount((prev) => {
      const existing = prev[accountId]?.items ?? [];
      const merged = cursor
        ? [...existing, ...res.items.map((m) => ({ ...m, accountId }))]
        : res.items.map((m) => ({ ...m, accountId }));
      return {
        ...prev,
        [accountId]: {
          items: merged,
          next_cursor: res.next_cursor,
        },
      };
    });
  };

  useEffect(() => {
    emailAccountsSelected.forEach((id) => {
      if (!emailMessagesByAccount[id]) {
        fetchEmailMessages(id).catch(() => {
          toast({ title: "Failed to load inbox", variant: "destructive" });
        });
      }
    });
  }, [emailAccountsSelected, emailMessagesByAccount, toast]);

  const mergedEmailMessages = useMemo(() => {
    return Object.values(emailMessagesByAccount)
      .flatMap((entry) => entry.items)
      .sort((a, b) => {
        const aTime = a.received_at ? new Date(a.received_at).getTime() : 0;
        const bTime = b.received_at ? new Date(b.received_at).getTime() : 0;
        return bTime - aTime;
      });
  }, [emailMessagesByAccount]);

  const fetchEmailDetail = async (accountId: string, id: string) => {
    const detail = await emailApi.getMessage(accountId, id);
    setSelectedEmailDetail({ ...detail, accountId } as EmailMessage & { accountId: string });
  };

  const emailSendMutation = useMutation({
    mutationFn: async () => {
      const accountId = emailComposeForm.accountId || emailAccountsSelected[0];
      if (!accountId) throw new Error("Select an account");
      const attachments =
        emailComposeForm.attachments.length > 0
          ? await Promise.all(
              emailComposeForm.attachments.map(
                (file) =>
                  new Promise<{ filename: string; mime_type: string; content_base64: string }>((resolve, reject) => {
                    const reader = new FileReader();
                    reader.onload = () => {
                      const result = reader.result as string;
                      const base64 = result.split(",")[1] || "";
                      resolve({ filename: file.name, mime_type: file.type, content_base64: base64 });
                    };
                    reader.onerror = () => reject(reader.error);
                    reader.readAsDataURL(file);
                  })
              )
            )
          : undefined;
      return emailApi.sendMessage(accountId, {
        to: emailComposeForm.to.split(",").map((v) => v.trim()).filter(Boolean),
        cc: emailComposeForm.cc.split(",").map((v) => v.trim()).filter(Boolean),
        bcc: emailComposeForm.bcc.split(",").map((v) => v.trim()).filter(Boolean),
        subject: emailComposeForm.subject,
        text: emailComposeForm.text,
        html: emailComposeForm.html || undefined,
        attachments,
      });
    },
    onSuccess: () => {
      toast({ title: "Email sent" });
      setEmailComposeForm((prev) => ({ ...prev, subject: "", text: "", html: "", attachments: [] }));
    },
    onError: (err: any) => {
      toast({ title: "Send failed", description: err?.message || "Could not send email", variant: "destructive" });
    },
  });

  const emailDeleteMutation = useMutation({
    mutationFn: ({ accountId, id }: { accountId: string; id: string }) => emailApi.deleteMessage(accountId, id),
    onSuccess: (_data, variables) => {
      setEmailMessagesByAccount((prev) => {
        const existing = prev[variables.accountId]?.items ?? [];
        return {
          ...prev,
          [variables.accountId]: {
            items: existing.filter((m) => m.id !== variables.id),
            next_cursor: prev[variables.accountId]?.next_cursor ?? null,
          },
        };
      });
      toast({ title: "Message deleted" });
    },
    onError: (err: any) => {
      toast({ title: "Delete failed", description: err?.message || "Could not delete message", variant: "destructive" });
    },
  });

  const hasMoreEmail = useMemo(
    () => Object.values(emailMessagesByAccount).some((v) => v.next_cursor),
    [emailMessagesByAccount]
  );

  const loadMoreEmailMessages = () => {
    const targets = Object.entries(emailMessagesByAccount).filter(([, v]) => v.next_cursor);
    targets.forEach(([accountId, v]) => {
      fetchEmailMessages(accountId, v.next_cursor).catch(() => {
        toast({ title: "Failed to load more messages", variant: "destructive" });
      });
    });
  };

  const conversationDetailQuery = useQuery<ConversationDetail>({
    queryKey: [CONVERSATIONS_PATH, selectedChat],
    queryFn: async () => {
      setIsLoadingDetail(true);
      try {
        const result = await fetchJson<ConversationDetail>(apiV1(`/crm/communications/conversations/${selectedChat}/`));
        // Merge fetched messages with existing WebSocket messages (don't overwrite)
        if (selectedChat) {
          setMessagesByConversation(prev => {
            const existingMessages = prev[selectedChat] || [];
            const fetchedMessages = result.messages || [];
            // Combine: use fetched messages as base, then add any WebSocket messages not in fetched
            const fetchedIds = new Set(fetchedMessages.map(m => m.id));
            const wsOnlyMessages = existingMessages.filter(m => !fetchedIds.has(m.id));
            // Sort by timestamp to maintain chronological order
            const merged = [...fetchedMessages, ...wsOnlyMessages].sort((a, b) => {
              const dateA = a.timestamp ? new Date(a.timestamp).getTime() : 0;
              const dateB = b.timestamp ? new Date(b.timestamp).getTime() : 0;
              return dateA - dateB;
            });
            return {
              ...prev,
              [selectedChat]: merged
            };
          });
        }
        return result;
      } finally {
        setIsLoadingDetail(false);
      }
    },
    enabled: Boolean(selectedChat),
  });

  const sendMessageMutation = useMutation({
    mutationFn: async (data: { conversationId: string; content: string }) => {
      return await apiRequest("POST", apiV1(`/crm/communications/conversations/${data.conversationId}/messages/`), {
        data: { content: data.content, type: "text" },
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [CONVERSATIONS_PATH] });
      setMessageText("");
      toast({ title: "Message sent", description: "Your message has been sent." });
    },
    onError: (error: Error) => {
      toast({ title: "Failed to send", description: error.message, variant: "destructive" });
    },
  });

  const endConversationMutation = useMutation({
    mutationFn: async (data: { conversationId: string }) => {
      // End conversation by marking it closed (and ensure human mode is off).
      // Note: this endpoint already supports PATCH for `human_mode`.
      return await apiRequest("PATCH", apiV1(`/crm/communications/conversations/${data.conversationId}/`), {
        data: { status: "closed", human_mode: false },
      });
    },
    onMutate: async (variables) => {
      const key = [CONVERSATIONS_PATH, variables.conversationId];
      await queryClient.cancelQueries({ queryKey: key });

      const previous = queryClient.getQueryData<ConversationDetail>(key);
      const previousListStatus = selectedConversation?.status;

      // Optimistic UI: immediately show as ended/closed.
      queryClient.setQueryData<ConversationDetail>(key, (old) => ({
        ...(old ?? { id: variables.conversationId }),
        status: "closed",
        active: false,
        human_mode: false,
      }));

      setAllAccumulatedConversations((prev) =>
        prev.map((c) => (c.id === variables.conversationId ? { ...c, status: "closed" } : c))
      );

      return { previous, previousListStatus };
    },
    onSuccess: () => {
      toast({ title: "Conversation ended" });
    },
    onError: (error: Error, variables, context) => {
      const key = [CONVERSATIONS_PATH, variables.conversationId];
      if (context?.previous) {
        queryClient.setQueryData(key, context.previous);
      } else {
        queryClient.invalidateQueries({ queryKey: key });
      }

      if (typeof context?.previousListStatus !== "undefined") {
        setAllAccumulatedConversations((prev) =>
          prev.map((c) => (c.id === variables.conversationId ? { ...c, status: context.previousListStatus } : c))
        );
      }

      toast({ title: "Failed to end conversation", description: error.message, variant: "destructive" });
    },
    onSettled: (_data, _error, variables) => {
      queryClient.invalidateQueries({ queryKey: [CONVERSATIONS_PATH, variables.conversationId] });
      queryClient.invalidateQueries({ queryKey: [CONVERSATIONS_PATH] });
      queryClient.invalidateQueries({ queryKey: [SUMMARY_PATH] });
    },
  });

  const toggleHumanModeMutation = useMutation({
    mutationFn: async (data: { conversationId: string; enabled: boolean }) => {
      return await apiRequest("PATCH", apiV1(`/crm/communications/conversations/${data.conversationId}/`), {
        data: { human_mode: data.enabled },
      });
    },
    onMutate: async (variables) => {
      const key = [CONVERSATIONS_PATH, variables.conversationId];
      await queryClient.cancelQueries({ queryKey: key });

      const previous = queryClient.getQueryData<ConversationDetail>(key);

      // Optimistically update the cached conversation detail so the UI
      // instantly enables/disables the composer and updates the header badge.
      queryClient.setQueryData<ConversationDetail>(key, (old) => ({
        ...(old ?? { id: variables.conversationId }),
        human_mode: variables.enabled,
      }));

      return { previous };
    },
    onSuccess: (_, variables) => {
      toast({ 
        title: variables.enabled ? "Human mode activated" : "Human mode deactivated", 
        description: variables.enabled 
          ? "You have taken over the conversation." 
          : "Conversation returned to AI handling." 
      });
    },
    onError: (error: Error, variables, context) => {
      const key = [CONVERSATIONS_PATH, variables.conversationId];
      if (context?.previous) {
        queryClient.setQueryData(key, context.previous);
      } else {
        // If we had no previous value, just refetch to restore consistency.
        queryClient.invalidateQueries({ queryKey: key });
      }
      toast({ title: "Failed to toggle human mode", description: error.message, variant: "destructive" });
    },
    onSettled: (_data, _error, variables) => {
      // Ensure we sync with server truth after optimistic update.
      queryClient.invalidateQueries({ queryKey: [CONVERSATIONS_PATH, variables.conversationId] });
      queryClient.invalidateQueries({ queryKey: [CONVERSATIONS_PATH] });
      queryClient.invalidateQueries({ queryKey: [SUMMARY_PATH] });
    },
  });

  // Filter out 'desktop' channel from Communications hub - desktop is reserved for CRM assistant
  const channels = (channelsQuery.data?.channels ?? []).filter(ch => ch.id !== "desktop");
  
  const filteredConversations = useMemo(() => {
    // Exclude desktop channel conversations from Communications hub
    let result = allAccumulatedConversations.filter(c => c.channel !== "desktop");
    
    if (channelFilter !== "all") {
      result = result.filter(c => c.channel === channelFilter);
    }
    
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      result = result.filter(c => 
        c.contact?.name?.toLowerCase().includes(query) ||
        c.contact?.phone?.includes(query) ||
        c.contact?.email?.toLowerCase().includes(query) ||
        c.last_message?.content?.toLowerCase().includes(query)
      );
    }
    
    result.sort((a, b) => {
      const dateA = a.updated_at ? new Date(a.updated_at).getTime() : 0;
      const dateB = b.updated_at ? new Date(b.updated_at).getTime() : 0;
      return dateB - dateA;
    });
    
    return result;
  }, [allAccumulatedConversations, channelFilter, searchQuery]);

  const selectedConversation = allAccumulatedConversations.find(c => c.id === selectedChat);
  const conversationDetail = conversationDetailQuery.data;

  const summary = summaryQuery.data;
  const totalUnread = summary?.total_unread ?? allAccumulatedConversations.reduce((sum, c) => sum + (c.unread_count || 0), 0);
  const activeChats = summary?.active ?? allAccumulatedConversations.filter(c => c.status === "active" || c.status === "open").length;
  const awaitingResponse = summary?.awaiting_response ?? 0;
  const totalFromSummary = summary?.total ?? totalConversationsCount;

  const observerRef = useRef<IntersectionObserver | null>(null);
  
  const sentinelCallbackRef = useCallback((node: HTMLDivElement | null) => {
    if (observerRef.current) {
      observerRef.current.disconnect();
    }
    
    if (node && hasMoreConversations && !isLoadingMore) {
      observerRef.current = new IntersectionObserver(
        (entries) => {
          if (entries[0].isIntersecting) {
            loadMoreConversations();
          }
        },
        { threshold: 0.1, rootMargin: '100px' }
      );
      observerRef.current.observe(node);
    }
  }, [hasMoreConversations, isLoadingMore, loadMoreConversations]);

  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [selectedChat, messagesByConversation]);

  const handleSendMessage = () => {
    // Only allow sending when human mode is enabled for the conversation.
    if (!selectedChat || !messageText.trim()) return;
    if (!conversationDetail?.human_mode) return;
    sendMessageMutation.mutate({
      conversationId: selectedChat,
      content: messageText.trim(),
    });
  };

  const handleRefresh = () => {
    conversationsQuery.refetch();
    channelsQuery.refetch();
    if (selectedChat) {
      conversationDetailQuery.refetch();
    }
  };

  const getStatusBadge = (status?: string, active?: boolean) => {
    if (active === false) {
      return <Badge variant="secondary" className="text-xs">Conversation Ended</Badge>;
    }
    if (status === "closed") {
      return <Badge variant="secondary" className="text-xs">Conversation Ended</Badge>;
    }
    if (status === "active" || status === "open" || active === true) {
      return <Badge variant="default" className="text-xs bg-green-600">Active</Badge>;
    }
    return <Badge variant="outline" className="text-xs">{status || "Unknown"}</Badge>;
  };

  const getStatusDot = (status?: string, updated_at?: string) => {
    // Check if conversation is closed/ended
    if (status === "closed") {
      return <div className="h-2.5 w-2.5 rounded-full bg-gray-400 dark:bg-gray-600 flex-shrink-0" title="Ended" />;
    }
    
    // Check if more than 5 minutes since last interaction
    if (updated_at) {
      const now = new Date();
      const lastUpdate = new Date(updated_at);
      const diffMs = now.getTime() - lastUpdate.getTime();
      const diffMins = Math.floor(diffMs / 60000);
      
      if (diffMins > 5) {
        return <div className="h-2.5 w-2.5 rounded-full bg-yellow-400 dark:bg-yellow-600 flex-shrink-0" title="Idle (>5m)" />;
      }
    }
    
    // Active/open with recent activity
    return <div className="h-2.5 w-2.5 rounded-full bg-green-500 dark:bg-green-600 flex-shrink-0" title="Active" />;
  };

  const getChannelIcon = (channel?: string) => {
    if (channel === "whatsapp") {
      return <SiWhatsapp className="h-3.5 w-3.5 text-green-600" />;
    }
    return <MessageCircle className="h-3.5 w-3.5 text-muted-foreground" />;
  };

  if (viewMode === "email") {
    return (
      <PageLayout
        title="Company Email"
        description="Shared company inbox (tenant accounts only)"
        className="p-0 flex flex-col"
        showSidebarTrigger={false}
        headerAction={
          <Button variant="outline" size="sm" onClick={() => setViewMode("conversations")}>
            Back to Conversations
          </Button>
        }
      >
        <div className="p-4 space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            {emailTenantQuery.isLoading ? (
              <Skeleton className="h-8 w-32" />
            ) : emailTenantQuery.error ? (
              <ErrorDisplay error={emailTenantQuery.error} endpoint="/api/v1/integrations/email/flow/accounts?scope=tenant" />
            ) : emailAccounts.length === 0 ? (
              <EmptyState title="No company email accounts" description="Connect company email accounts in Settings." />
            ) : (
              emailAccounts.map((acc) => (
                <label key={acc.id} className="flex items-center gap-2 border rounded-full px-3 py-1 text-sm cursor-pointer">
                  <input
                    type="checkbox"
                    checked={emailAccountsSelected.includes(acc.id)}
                    onChange={(e) => {
                      const checked = e.target.checked;
                      setEmailAccountsSelected((prev) =>
                        checked ? [...prev, acc.id] : prev.filter((id) => id !== acc.id)
                      );
                    }}
                  />
                  <span className="truncate max-w-[160px]">{acc.external_account.email_address}</span>
                  <Badge variant="default">Company</Badge>
                </label>
              ))
            )}
          </div>

          <div className="flex items-center gap-2">
            <Button size="sm" onClick={loadMoreEmailMessages} disabled={!hasMoreEmail}>
              {hasMoreEmail ? "Load more" : "No more messages"}
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => {
                if (emailAccountsSelected[0]) {
                  fetchEmailMessages(emailAccountsSelected[0]).catch(() =>
                    toast({ title: "Refresh failed", variant: "destructive" })
                  );
                }
              }}
            >
              Refresh first account
            </Button>
          </div>

          <div className="flex gap-4 min-h-[70vh]">
            <div className="w-96 border rounded-lg bg-card flex flex-col">
              <div className="border-b px-3 py-2 font-semibold">Inbox</div>
              <div className="flex-1 overflow-y-auto">
                {mergedEmailMessages.length === 0 ? (
                  <div className="p-4">
                    <EmptyState title="No messages" description="Messages will appear here once fetched." />
                  </div>
                ) : (
                  mergedEmailMessages.map((msg) => (
                    <div
                      key={`${msg.accountId}-${msg.id}`}
                      className={`p-3 border-b cursor-pointer ${selectedEmailMessage?.id === msg.id ? "bg-muted" : ""}`}
                      onClick={() => {
                        setSelectedEmailMessage({ accountId: msg.accountId, id: msg.id });
                        fetchEmailDetail(msg.accountId, msg.id).catch(() =>
                          toast({ title: "Failed to load message", variant: "destructive" })
                        );
                      }}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <div className="text-sm font-semibold truncate">{msg.subject || "(no subject)"}</div>
                        <span className="text-xs text-muted-foreground">
                          {msg.received_at ? formatRelativeTime(msg.received_at) : ""}
                        </span>
                      </div>
                      <div className="text-xs text-muted-foreground truncate">
                        From: {msg.from} → {msg.to?.[0] ?? ""}
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>

            <div className="flex-1 border rounded-lg bg-card p-4 space-y-4">
              {selectedEmailDetail ? (
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="font-semibold text-lg">{selectedEmailDetail.subject || "(no subject)"}</div>
                      <div className="text-sm text-muted-foreground">From: {selectedEmailDetail.from}</div>
                      <div className="text-sm text-muted-foreground">To: {selectedEmailDetail.to?.join(", ")}</div>
                    </div>
                    <div className="flex items-center gap-2">
                      <Button
                        variant="destructive"
                        size="sm"
                        onClick={() =>
                          selectedEmailMessage &&
                          emailDeleteMutation.mutate({
                            accountId: selectedEmailMessage.accountId,
                            id: selectedEmailMessage.id,
                          })
                        }
                      >
                        Delete
                      </Button>
                    </div>
                  </div>
                  {selectedEmailDetail.html ? (
                    <div className="border rounded-md p-3 text-sm" dangerouslySetInnerHTML={{ __html: selectedEmailDetail.html }} />
                  ) : (
                    <p className="text-sm whitespace-pre-wrap">{selectedEmailDetail.text}</p>
                  )}
                </div>
              ) : (
                <div className="text-muted-foreground text-sm">Select a message to view details.</div>
              )}

              <Separator />

              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <h3 className="font-semibold">Compose</h3>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setEmailComposeForm((prev) => ({ ...prev, subject: "", text: "", html: "", attachments: [] }))}
                  >
                    Clear
                  </Button>
                </div>
                <Select
                  value={emailComposeForm.accountId}
                  onValueChange={(v) => setEmailComposeForm((prev) => ({ ...prev, accountId: v }))}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Select account" />
                  </SelectTrigger>
                  <SelectContent>
                    {emailAccounts.map((acc) => (
                      <SelectItem key={acc.id} value={acc.id}>
                        {acc.external_account.email_address} ({acc.external_account.ownership})
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Input
                  placeholder="To (comma separated)"
                  value={emailComposeForm.to}
                  onChange={(e) => setEmailComposeForm((prev) => ({ ...prev, to: e.target.value }))}
                />
                <Input
                  placeholder="Cc (comma separated)"
                  value={emailComposeForm.cc}
                  onChange={(e) => setEmailComposeForm((prev) => ({ ...prev, cc: e.target.value }))}
                />
                <Input
                  placeholder="Bcc (comma separated)"
                  value={emailComposeForm.bcc}
                  onChange={(e) => setEmailComposeForm((prev) => ({ ...prev, bcc: e.target.value }))}
                />
                <Input
                  placeholder="Subject"
                  value={emailComposeForm.subject}
                  onChange={(e) => setEmailComposeForm((prev) => ({ ...prev, subject: e.target.value }))}
                />
                <Textarea
                  placeholder="Body (text)"
                  value={emailComposeForm.text}
                  onChange={(e) => setEmailComposeForm((prev) => ({ ...prev, text: e.target.value }))}
                  rows={4}
                />
                <Input
                  type="file"
                  multiple
                  onChange={(e) =>
                    setEmailComposeForm((prev) => ({
                      ...prev,
                      attachments: e.target.files ? Array.from(e.target.files) : [],
                    }))
                  }
                />
                <Button onClick={() => emailSendMutation.mutate()} disabled={emailSendMutation.isPending}>
                  {emailSendMutation.isPending && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                  Send
                </Button>
              </div>
            </div>
          </div>
        </div>
      </PageLayout>
    );
  }

  return (
    <PageLayout
      title="Centro de Comunicaciones"
      description="Manage all your customer conversations and messages"
      className="p-0 flex flex-col"
      showSidebarTrigger={false}
      metrics={[
        { label: "Active", value: String(activeChats), testId: "stat-active-chats" },
        { label: "Awaiting Response", value: String(awaitingResponse), testId: "stat-awaiting-response" },
        { label: "Unread", value: String(totalUnread), testId: "stat-unread" },
        { label: "Total", value: String(totalFromSummary), testId: "stat-total-conversations" },
      ]}
      headerAction={
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => setViewMode("email")}>
            Company Email
          </Button>
          <ConnectionStatus service="whatsapp" />
          <Button variant="ghost" size="icon" onClick={handleRefresh} data-testid="button-refresh">
            <RefreshCw className="h-4 w-4" />
          </Button>
        </div>
      }
    >
      <div className="flex flex-1 min-h-0">
        <div className="w-96 border-r border-border bg-background flex flex-col shrink-0">
          <div className="p-3 border-b border-border space-y-2.5">
            <div className="flex items-center gap-2">
              <Select value={channelFilter} onValueChange={setChannelFilter}>
                <SelectTrigger className="w-32 h-8" data-testid="select-channel-filter">
                  <SelectValue placeholder="Channel" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Channels</SelectItem>
                  {channels.map(ch => (
                    <SelectItem key={ch.id} value={ch.id}>{ch.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <div className="relative flex-1">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Search..."
                  className="pl-9 h-8"
                  data-testid="input-search"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                />
              </div>
              <Button variant="ghost" size="icon" className="h-8 w-8" data-testid="button-filter">
                <Filter className="h-4 w-4" />
              </Button>
            </div>
          </div>

          <div ref={conversationsListRef} className="flex-1 overflow-y-auto">
              {conversationsQuery.isLoading && allAccumulatedConversations.length === 0 && !conversationsQuery.data ? (
                <div className="p-4">
                  <EmptyState
                    title="Loading conversations"
                    description="Fetching communication threads..."
                    isLoading
                  />
                </div>
              ) : conversationsQuery.isError && allAccumulatedConversations.length === 0 ? (
                <div className="p-4">
                  <ErrorDisplay
                    error={conversationsQuery.error}
                    endpoint="crmcommunications/conversations"
                  />
                </div>
              ) : filteredConversations.length === 0 ? (
                <div className="p-4">
                  <EmptyState
                    title="No conversations found"
                    description={searchQuery ? "Try a different search term." : "No conversations available."}
                  />
                </div>
              ) : (
                <>
                  {filteredConversations.map((chat) => (
                    <div
                      key={chat.id}
                      onClick={() => setSelectedChat(chat.id)}
                      className={`p-3 border-b border-border cursor-pointer transition-colors ${
                        selectedChat === chat.id ? "bg-blue-50 dark:bg-blue-950/30 border-l-2 border-l-blue-500" : "hover-elevate"
                      }`}
                      data-testid={`chat-item-${chat.id}`}
                    >
                      <div className="flex items-start justify-between gap-2 mb-1.5">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-0.5">
                            <h3 className="font-semibold text-sm truncate" data-testid={`text-chat-name-${chat.id}`}>
                              {chat.contact?.name ?? "Unknown"}
                            </h3>
                            <Badge variant="outline" className="text-[10px] px-1.5 py-0 h-4 shrink-0">
                              {chat.contact?.contacttype?.name ?? "Contact"}
                            </Badge>
                          </div>
                          <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                            {getChannelIcon(chat.channel)}
                            <span>{chat.contact?.phone ?? ""}</span>
                          </div>
                        </div>
                        {chat.unread_count ? (
                          <Badge variant="default" className="text-xs h-5 px-1.5 shrink-0">
                            {chat.unread_count}
                          </Badge>
                        ) : null}
                      </div>
                      <div className="flex items-center gap-1.5">
                        {getStatusDot(chat.status, chat.updated_at)}
                        <span className="text-xs text-muted-foreground">{formatRelativeTime(chat.updated_at)}</span>
                      </div>
                    </div>
                  ))}
                  {hasMoreConversations && (
                    <div ref={sentinelCallbackRef} className="h-10 flex items-center justify-center">
                      <span className="text-xs text-muted-foreground">Scroll to load more...</span>
                    </div>
                  )}
                  {isLoadingMore && (
                    <div className="p-3 text-center text-xs text-muted-foreground">
                      Loading more conversations...
                    </div>
                  )}
                </>
              )}
          </div>
        </div>

        <div className="flex-1 flex flex-col bg-muted/10 min-h-0">
          {!selectedChat ? (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center">
                <div className="inline-flex h-16 w-16 items-center justify-center rounded-full bg-muted mb-4">
                  <MessageSquare className="h-8 w-8 text-muted-foreground" />
                </div>
                <p className="text-sm text-muted-foreground">Select a conversation to view messages</p>
              </div>
            </div>
          ) : (
            <>
              <div className="p-4 border-b border-border bg-background">
                <div className="flex items-start justify-between gap-4 mb-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-3 mb-1">
                      <h2 className="font-semibold text-lg" data-testid="text-conversation-name">
                        {selectedConversation?.contact?.name ?? conversationDetail?.contact?.name ?? "Conversation"}
                      </h2>
                      {getStatusBadge(selectedConversation?.status ?? conversationDetail?.status, conversationDetail?.active)}
                      {conversationDetail?.human_mode && (
                        <Badge variant="default" className="text-xs bg-blue-600 flex items-center gap-1">
                          <UserCheck className="h-3 w-3" />
                          Human Mode
                        </Badge>
                      )}
                    </div>
                    <div className="flex items-center gap-2 text-sm text-muted-foreground">
                      <Phone className="h-3.5 w-3.5" />
                      <span data-testid="text-conversation-phone">
                        {selectedConversation?.contact?.phone ?? conversationDetail?.contact?.phone ?? ""}
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {conversationDetail?.active !== false && (
                      <Button 
                        variant={conversationDetail?.human_mode ? "default" : "outline"} 
                        size="sm" 
                        data-testid="button-human-mode"
                        onClick={() => selectedChat && toggleHumanModeMutation.mutate({ 
                          conversationId: selectedChat, 
                          enabled: !conversationDetail?.human_mode 
                        })}
                        disabled={toggleHumanModeMutation.isPending}
                      >
                        <UserCheck className="h-3.5 w-3.5 mr-1" />
                        {conversationDetail?.human_mode ? "End Human Mode" : "Start Human Mode"}
                      </Button>
                    )}
                    <Button
                      variant="outline"
                      size="sm"
                      data-testid="button-close"
                      onClick={() => selectedChat && endConversationMutation.mutate({ conversationId: selectedChat })}
                      disabled={
                        endConversationMutation.isPending ||
                        conversationDetail?.active === false ||
                        conversationDetail?.status === "closed" ||
                        selectedConversation?.status === "closed"
                      }
                    >
                      <X className="h-3.5 w-3.5 mr-1" />
                      Close
                    </Button>
                  </div>
                </div>

                {(selectedConversation?.last_message?.content || conversationDetail?.final_summary) && (
                  <details className="bg-muted/50 rounded-lg p-3 mb-3">
                    <summary className="cursor-pointer select-none text-xs font-medium text-muted-foreground">
                      Resumen
                    </summary>
                    <div className="mt-2">
                      <p className="text-sm text-foreground/80 leading-relaxed" data-testid="text-conversation-summary">
                        {conversationDetail?.final_summary || selectedConversation?.last_message?.content || "No summary available."}
                      </p>
                    </div>
                  </details>
                )}

                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <span className="font-medium">Session:</span>
                  <code className="bg-muted px-1.5 py-0.5 rounded text-[11px]" data-testid="text-session-id">
                    {selectedChat}
                  </code>
                </div>
              </div>

              <ScrollArea className="flex-1 p-4">
                {isLoadingDetail ? (
                  <EmptyState
                    title="Loading messages"
                    description="Fetching the conversation..."
                    isLoading
                  />
                ) : conversationDetailQuery.isError ? (
                  <ErrorDisplay
                    error={conversationDetailQuery.error}
                    endpoint={`conversations/${selectedChat}`}
                  />
                ) : (selectedChat && (messagesByConversation[selectedChat]?.length || 0) === 0) ? (
                  <EmptyState
                    title="No messages yet"
                    description="Messages will appear here once activity occurs."
                  />
                ) : (
                  <div className="space-y-1">
                    {selectedChat && messagesByConversation[selectedChat]?.map((message) => (
                      <ChatBubble key={message.id} message={message} />
                    ))}
                    <div ref={messagesEndRef} />
                  </div>
                )}
              </ScrollArea>

              <div className="p-3 border-t border-border bg-background">
                {conversationDetail?.active === false ||
                conversationDetail?.status === "closed" ||
                selectedConversation?.status === "closed" ? (
                  <div className="bg-muted/50 rounded-lg p-3 text-center">
                    <p className="text-sm text-muted-foreground">This conversation has ended and cannot receive new messages.</p>
                  </div>
                ) : (
                  <div className="space-y-2">
                    {!conversationDetail?.human_mode && (
                      <div className="text-xs text-muted-foreground">
                        Enable <span className="font-medium">Human Mode</span> to send messages from the inbox.
                      </div>
                    )}
                    <div className="flex gap-2">
                      <Input
                        placeholder={conversationDetail?.human_mode ? "Type a message..." : "Human Mode required to send"}
                        className="flex-1"
                        data-testid="input-message"
                        value={messageText}
                        onChange={(e) => setMessageText(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" && !e.shiftKey) {
                            e.preventDefault();
                            handleSendMessage();
                          }
                        }}
                        disabled={!conversationDetail?.human_mode || sendMessageMutation.isPending}
                      />
                      <Button 
                        size="icon" 
                        data-testid="button-send"
                        onClick={handleSendMessage}
                        disabled={!conversationDetail?.human_mode || !messageText.trim() || sendMessageMutation.isPending}
                      >
                        <Send className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </div>

    </PageLayout>
  );
}
