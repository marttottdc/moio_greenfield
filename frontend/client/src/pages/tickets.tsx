import { useState, useEffect, useMemo, useRef, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { useQuery, useMutation } from "@tanstack/react-query";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Search, Ticket as TicketIcon, Plus, Clock, User, UserPlus, Send, RefreshCw, CheckCircle, AlertCircle, Loader2, Mail, Phone, X, CalendarClock, Hourglass, MessageCircle } from "lucide-react";
import { Calendar } from "@/components/ui/calendar";
import { PageLayout } from "@/components/layout/page-layout";
import { EmptyState } from "@/components/empty-state";
import { ErrorDisplay } from "@/components/error-display";
import { fetchJson, apiRequest, queryClient } from "@/lib/queryClient";
import { useToast } from "@/hooks/use-toast";
import { apiV1 } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { useTicketUpdates } from "@/hooks/useWebSocket";
import { ConnectionStatus } from "@/components/connection-status";

interface TicketCustomer {
  id: string;
  name?: string;
  email?: string;
  phone?: string;
  company?: string;
  contacttype?: {
    id: string;
    name: string;
  };
}

interface TicketAssignee {
  id: string;
  name?: string;
  email?: string;
  phone?: string;
  company?: string;
  avatar_url?: string | null;
  contacttype?: {
    id: string;
    name: string;
  };
}

interface TicketComment {
  id: string;
  comment?: string;
  created_at?: string;
  creator?: {
    id: string;
    name?: string;
    email?: string;
  };
}

interface Ticket {
  id: string;
  ticket_number?: string;
  description?: string;
  customer?: TicketCustomer;
  creator?: TicketAssignee | null;
  status?: string;
  status_label?: string;
  type?: string;
  type_label?: string;
  priority?: string;
  category?: string;
  service?: string;
  assigned_to?: TicketAssignee | null;
  created_at?: string;
  updated_at?: string;
  target?: string | null;
  target_at?: string | null;
  closed_at?: string | null;
  waiting_since?: string | null;
  waiting_for?: TicketCustomer | null;
  tags?: string[];
  comments?: TicketComment[];
  comments_count?: number;
}

interface TicketsResponse {
  tickets?: Ticket[];
  pagination?: {
    current_page?: number;
    total_pages?: number;
    total_items?: number;
  };
}

interface TenantUser {
  id: string | number;
  username?: string;
  email?: string;
  full_name?: string;
  first_name?: string;
  last_name?: string;
  avatar_url?: string | null;
  role?: string;
  is_active?: boolean;
  status?: string;
}

const statusColors: Record<string, string> = {
  O: "bg-blue-500",
  A: "bg-purple-500",
  I: "bg-amber-500",
  W: "bg-orange-500",
  C: "bg-gray-500",
  P: "bg-cyan-500",
};

const statusLabels: Record<string, string> = {
  O: "Open",
  A: "Assigned",
  I: "In Progress",
  W: "Waiting",
  C: "Closed",
  P: "Planned",
};

const typeLabels: Record<string, string> = {
  I: "Incident",
  C: "Change",
  P: "Planned",
};

const priorityColors: Record<string, string> = {
  urgent: "bg-red-500",
  high: "bg-red-400",
  medium: "bg-orange-500",
  low: "bg-blue-400",
};

const priorityLabels: Record<string, string> = {
  urgent: "Urgent",
  high: "High",
  medium: "Medium",
  low: "Low",
};

function formatRelativeTime(dateString?: string): string {
  if (!dateString) return "";
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 1) return "just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString();
}

function formatDateTime(dateString?: string): string {
  if (!dateString) return "";
  const date = new Date(dateString);
  return date.toLocaleDateString("es-ES", {
    day: "numeric",
    month: "long",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function renderTextWithLinks(text?: string) {
  if (!text) return null;
  
  const urlRegex = /(https?:\/\/[^\s]+)/g;
  const parts = text.split(urlRegex);
  
  return (
    <>
      {parts.map((part, index) => {
        if (urlRegex.test(part)) {
          return (
            <a
              key={index}
              href={part}
              target="_blank"
              rel="noopener noreferrer"
              className="text-primary hover:underline break-all"
            >
              {part}
            </a>
          );
        }
        return <span key={index}>{part}</span>;
      })}
    </>
  );
}

export default function Tickets() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [selectedTicket, setSelectedTicket] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [commentText, setCommentText] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [ticketView, setTicketView] = useState<"all" | "my">("all");
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [isAssignOpen, setIsAssignOpen] = useState(false);
  const [isCloseOpen, setIsCloseOpen] = useState(false);
  const [isPlanOpen, setIsPlanOpen] = useState(false);
  const [isWaitingOpen, setIsWaitingOpen] = useState(false);
  const [isContactExpanded, setIsContactExpanded] = useState(false);
  const [userSearchQuery, setUserSearchQuery] = useState("");
  const [closeComment, setCloseComment] = useState("");
  const [waitingComment, setWaitingComment] = useState("");
  const [waitingForContact, setWaitingForContact] = useState<string | null>(null);
  const [contactSearchQuery, setContactSearchQuery] = useState("");
  const [planDate, setPlanDate] = useState<Date | undefined>(undefined);
  const [createForm, setCreateForm] = useState({ description: "", type: "I", priority: "medium" });
  const [allAccumulatedTickets, setAllAccumulatedTickets] = useState<Ticket[]>([]);
  const [totalTicketsCount, setTotalTicketsCount] = useState(0);
  const [hasMoreTickets, setHasMoreTickets] = useState(true);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const currentPageRef = useRef(1);
  const ticketsListRef = useRef<HTMLDivElement>(null);
  const { toast } = useToast();

  const PAGE_SIZE = 20;
  const TICKETS_PATH = apiV1("/crm/tickets");

  useTicketUpdates({
    onTicketCreated: useCallback(() => {
      queryClient.invalidateQueries({ 
        predicate: (query) => query.queryKey[0] === TICKETS_PATH 
      });
    }, [TICKETS_PATH]),
    onTicketUpdated: useCallback((payload: { ticket_id?: string }) => {
      queryClient.invalidateQueries({ 
        predicate: (query) => query.queryKey[0] === TICKETS_PATH 
      });
      if (payload.ticket_id) {
        queryClient.invalidateQueries({ queryKey: [TICKETS_PATH, payload.ticket_id] });
      }
      if (selectedTicket) {
        queryClient.invalidateQueries({ queryKey: [TICKETS_PATH, selectedTicket] });
      }
    }, [TICKETS_PATH, selectedTicket]),
    onTicketStatusChanged: useCallback((payload: { ticket_id?: string }) => {
      queryClient.invalidateQueries({ 
        predicate: (query) => query.queryKey[0] === TICKETS_PATH 
      });
      if (payload.ticket_id) {
        queryClient.invalidateQueries({ queryKey: [TICKETS_PATH, payload.ticket_id] });
      }
      if (selectedTicket) {
        queryClient.invalidateQueries({ queryKey: [TICKETS_PATH, selectedTicket] });
      }
    }, [TICKETS_PATH, selectedTicket]),
    onTicketAssigned: useCallback((payload: { ticket_id?: string }) => {
      queryClient.invalidateQueries({ 
        predicate: (query) => query.queryKey[0] === TICKETS_PATH 
      });
      if (payload.ticket_id) {
        queryClient.invalidateQueries({ queryKey: [TICKETS_PATH, payload.ticket_id] });
      }
      if (selectedTicket) {
        queryClient.invalidateQueries({ queryKey: [TICKETS_PATH, selectedTicket] });
      }
    }, [TICKETS_PATH, selectedTicket]),
    onTicketCommentAdded: useCallback((payload: { ticket_id?: string }) => {
      if (payload.ticket_id) {
        queryClient.invalidateQueries({ queryKey: [TICKETS_PATH, payload.ticket_id] });
      }
      if (selectedTicket) {
        queryClient.invalidateQueries({ queryKey: [TICKETS_PATH, selectedTicket] });
      }
    }, [TICKETS_PATH, selectedTicket]),
  });

  const ticketsQuery = useQuery<TicketsResponse>({
    queryKey: [TICKETS_PATH, { search: searchQuery }],
    queryFn: async () => {
      const params: Record<string, string | number> = {
        page: 1,
        page_size: PAGE_SIZE,
      };
      if (searchQuery) {
        params.search = searchQuery;
      }
      const result = await fetchJson<TicketsResponse>(TICKETS_PATH, params);
      currentPageRef.current = 1;
      setAllAccumulatedTickets(result.tickets || []);
      setTotalTicketsCount(result.pagination?.total_items || result.tickets?.length || 0);
      setHasMoreTickets((result.tickets?.length || 0) >= PAGE_SIZE);
      return result;
    },
  });

  useEffect(() => {
    if (ticketsQuery.data?.tickets && allAccumulatedTickets.length === 0) {
      setAllAccumulatedTickets(ticketsQuery.data.tickets);
      setTotalTicketsCount(ticketsQuery.data.pagination?.total_items || ticketsQuery.data.tickets.length);
      setHasMoreTickets(ticketsQuery.data.tickets.length >= PAGE_SIZE);
      currentPageRef.current = 1;
    }
  }, [ticketsQuery.data]);

  const loadMoreTickets = useCallback(async () => {
    if (isLoadingMore || !hasMoreTickets) return;
    setIsLoadingMore(true);
    try {
      const nextPage = currentPageRef.current + 1;
      const params: Record<string, string | number> = {
        page: nextPage,
        page_size: PAGE_SIZE,
      };
      if (searchQuery) {
        params.search = searchQuery;
      }
      const result = await fetchJson<TicketsResponse>(TICKETS_PATH, params);
      if (result.tickets && result.tickets.length > 0) {
        currentPageRef.current = nextPage;
        setAllAccumulatedTickets(prev => {
          const existingIds = new Set(prev.map(t => t.id));
          const newTickets = result.tickets!.filter(t => !existingIds.has(t.id));
          return [...prev, ...newTickets];
        });
        setHasMoreTickets(result.tickets.length >= PAGE_SIZE);
      } else {
        setHasMoreTickets(false);
      }
    } catch {
      // Failed to load more tickets
    } finally {
      setIsLoadingMore(false);
    }
  }, [isLoadingMore, hasMoreTickets, searchQuery]);

  const ticketDetailQuery = useQuery<Ticket>({
    queryKey: [TICKETS_PATH, selectedTicket],
    queryFn: async () => {
      const result = await fetchJson<Ticket>(apiV1(`/crm/tickets/${selectedTicket}`));
      return result;
    },
    enabled: Boolean(selectedTicket),
  });

  const addCommentMutation = useMutation({
    mutationFn: async (data: { ticketId: string; content: string }) => {
      return await apiRequest("POST", apiV1(`/crm/tickets/${data.ticketId}/comments/`), {
        data: {
          comment: data.content,
          internal: false,
        },
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [TICKETS_PATH, selectedTicket] });
      setCommentText("");
      toast({
        title: "Comment added",
        description: "Your comment has been added successfully.",
      });
    },
    onError: (error: Error) => {
      toast({
        title: "Failed to add comment",
        description: error.message,
        variant: "destructive",
      });
    },
  });

  const updateStatusMutation = useMutation({
    mutationFn: async (data: { ticketId: string; status: string }) => {
      return await apiRequest("PATCH", apiV1(`/crm/tickets/${data.ticketId}/`), {
        data: { status: data.status },
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [TICKETS_PATH] });
      queryClient.invalidateQueries({ queryKey: [TICKETS_PATH, selectedTicket] });
      toast({
        title: "Status updated",
        description: "The ticket status has been updated successfully.",
      });
    },
    onError: (error: Error) => {
      toast({
        title: "Failed to update status",
        description: error.message,
        variant: "destructive",
      });
    },
  });

  const assignTicketMutation = useMutation({
    mutationFn: async (ticketId: string) => {
      if (!user?.id) {
        return { skipped: true, reason: "no_user" };
      }

      return await apiRequest("PATCH", apiV1(`/crm/tickets/${ticketId}/`), {
        data: { assigned: user.id, status: "I" },
      });
    },
    onSuccess: (data) => {
      if (data && typeof data === 'object' && 'skipped' in data) {
        return;
      }
      queryClient.invalidateQueries({ queryKey: [TICKETS_PATH] });
      queryClient.invalidateQueries({ queryKey: [TICKETS_PATH, selectedTicket] });
    },
    onError: () => {
    },
  });

  const createTicketMutation = useMutation({
    mutationFn: async () => {
      return await apiRequest("POST", apiV1("/crm/tickets/"), {
        data: {
          description: createForm.description,
          type: createForm.type,
          priority: createForm.priority,
          status: "O",
        },
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [TICKETS_PATH] });
      setIsCreateOpen(false);
      setCreateForm({ description: "", type: "I", priority: "medium" });
      toast({
        title: "Ticket created",
        description: "A new support ticket has been created.",
      });
    },
    onError: (error: Error) => {
      toast({
        title: "Failed to create ticket",
        description: error.message,
        variant: "destructive",
      });
    },
  });

  const usersQuery = useQuery<unknown>({
    queryKey: [apiV1("/settings/users")],
    queryFn: async () => {
      return await fetchJson<unknown>(apiV1("/settings/users"));
    },
    enabled: isAssignOpen,
  });

  const manualAssignMutation = useMutation({
    mutationFn: async (data: { ticketId: string; userId: string }) => {
      return await apiRequest("PATCH", apiV1(`/crm/tickets/${data.ticketId}/`), {
        data: { assigned: data.userId, status: "A" },
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [TICKETS_PATH] });
      queryClient.invalidateQueries({ queryKey: [TICKETS_PATH, selectedTicket] });
      setIsAssignOpen(false);
      setUserSearchQuery("");
      toast({
        title: "Ticket assigned",
        description: "The ticket has been assigned successfully.",
      });
    },
    onError: (error: Error) => {
      toast({
        title: "Failed to assign ticket",
        description: error.message,
        variant: "destructive",
      });
    },
  });

  const closeTicketMutation = useMutation({
    mutationFn: async (data: { ticketId: string; comment: string }) => {
      await apiRequest("POST", apiV1(`/crm/tickets/${data.ticketId}/comments/`), {
        data: { comment: data.comment, internal: false },
      });
      return await apiRequest("PATCH", apiV1(`/crm/tickets/${data.ticketId}/`), {
        data: { status: "C" },
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [TICKETS_PATH] });
      queryClient.invalidateQueries({ queryKey: [TICKETS_PATH, selectedTicket] });
      setIsCloseOpen(false);
      setCloseComment("");
      toast({
        title: "Ticket closed",
        description: "The ticket has been closed with your comment.",
      });
    },
    onError: (error: Error) => {
      toast({
        title: "Failed to close ticket",
        description: error.message,
        variant: "destructive",
      });
    },
  });

  const planTicketMutation = useMutation({
    mutationFn: async (data: { ticketId: string; targetDate: Date }) => {
      return await apiRequest("PATCH", apiV1(`/crm/tickets/${data.ticketId}/`), {
        data: { status: "P", target: data.targetDate.toISOString() },
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [TICKETS_PATH] });
      queryClient.invalidateQueries({ queryKey: [TICKETS_PATH, selectedTicket] });
      setIsPlanOpen(false);
      setPlanDate(undefined);
      toast({
        title: "Ticket planned",
        description: "The ticket has been scheduled for the selected date.",
      });
    },
    onError: (error: Error) => {
      toast({
        title: "Failed to plan ticket",
        description: error.message,
        variant: "destructive",
      });
    },
  });

  const setWaitingMutation = useMutation({
    mutationFn: async (data: { ticketId: string; comment: string; waitingFor?: string }) => {
      await apiRequest("POST", apiV1(`/crm/tickets/${data.ticketId}/comments/`), {
        data: { comment: data.comment },
      });
      const patchData: Record<string, string> = { status: "W" };
      if (data.waitingFor) {
        patchData.waiting_for = data.waitingFor;
      }
      return await apiRequest("PATCH", apiV1(`/crm/tickets/${data.ticketId}/`), {
        data: patchData,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [TICKETS_PATH] });
      queryClient.invalidateQueries({ queryKey: [TICKETS_PATH, selectedTicket] });
      setIsWaitingOpen(false);
      setWaitingComment("");
      setWaitingForContact(null);
      setContactSearchQuery("");
      toast({
        title: "Ticket set to waiting",
        description: "The ticket is now waiting for a response.",
      });
    },
    onError: (error: Error) => {
      toast({
        title: "Failed to set waiting status",
        description: error.message,
        variant: "destructive",
      });
    },
  });

  const contactsQuery = useQuery<{ contacts: Array<{ id: string; name: string; email?: string; phone?: string }> }>({
    queryKey: [apiV1("/crmcontacts"), { search: contactSearchQuery }],
    enabled: isWaitingOpen,
  });

  const filteredContacts = useMemo(() => {
    const contacts = contactsQuery.data?.contacts || [];
    if (!contactSearchQuery.trim()) return contacts.slice(0, 10);
    const q = contactSearchQuery.toLowerCase();
    return contacts.filter((c) => 
      c.name?.toLowerCase().includes(q) || 
      c.email?.toLowerCase().includes(q) ||
      c.phone?.includes(q)
    ).slice(0, 10);
  }, [contactsQuery.data, contactSearchQuery]);

  const tenantUsers = useMemo(() => {
    if (!usersQuery.data) return [];
    const data: any = usersQuery.data as any;
    const userList: TenantUser[] = Array.isArray(data)
      ? (data as TenantUser[])
      : (data?.users ??
          data?.results ??
          data?.data ??
          data?.items ??
          []) as TenantUser[];

    return userList.filter((u) => {
      if (u?.is_active === false) return false;
      const status = typeof u?.status === "string" ? u.status.toLowerCase() : undefined;
      if (status && ["inactive", "suspended", "disabled"].includes(status)) return false;
      return true;
    });
  }, [usersQuery.data]);

  const filteredUsers = useMemo(() => {
    if (!userSearchQuery.trim()) return tenantUsers;
    const q = userSearchQuery.toLowerCase();
    return tenantUsers.filter((u) => {
      const name = u.full_name || `${u.first_name || ""} ${u.last_name || ""}`.trim() || u.username || "";
      return name.toLowerCase().includes(q) || u.email?.toLowerCase().includes(q);
    });
  }, [tenantUsers, userSearchQuery]);

  const filteredTickets = useMemo(() => {
    let result = [...allAccumulatedTickets];
    
    if (ticketView === "my" && user?.email) {
      result = result.filter(t => t.assigned_to?.email === user.email);
    }
    
    if (statusFilter !== "all") {
      result = result.filter(t => t.status === statusFilter);
    }
    
    result.sort((a, b) => {
      const dateA = a.updated_at ? new Date(a.updated_at).getTime() : 0;
      const dateB = b.updated_at ? new Date(b.updated_at).getTime() : 0;
      return dateB - dateA;
    });
    
    return result;
  }, [allAccumulatedTickets, ticketView, statusFilter, user?.email]);

  const selectedTicketData = ticketDetailQuery.data || allAccumulatedTickets.find((t) => t.id === selectedTicket);
  const comments = ticketDetailQuery.data?.comments ?? [];

  const openCount = allAccumulatedTickets.filter(t => t.status === "O").length;
  const inProgressCount = allAccumulatedTickets.filter(t => t.status === "I").length;
  const assignedCount = allAccumulatedTickets.filter(t => t.status === "A").length;

  const observerRef = useRef<IntersectionObserver | null>(null);
  
  const sentinelCallbackRef = useCallback((node: HTMLDivElement | null) => {
    if (observerRef.current) {
      observerRef.current.disconnect();
    }
    
    if (node && hasMoreTickets && !isLoadingMore) {
      observerRef.current = new IntersectionObserver(
        (entries) => {
          if (entries[0].isIntersecting) {
            loadMoreTickets();
          }
        },
        { threshold: 0.1, rootMargin: '100px' }
      );
      observerRef.current.observe(node);
    }
  }, [hasMoreTickets, isLoadingMore, loadMoreTickets]);

  useEffect(() => {
    if (
      selectedTicket && 
      selectedTicketData && 
      !selectedTicketData.assigned_to && 
      user?.id &&
      selectedTicketData.status === "O" &&
      !assignTicketMutation.isPending
    ) {
      assignTicketMutation.mutate(selectedTicket);
    }
  }, [selectedTicket, selectedTicketData?.assigned_to, selectedTicketData?.status, user?.id, assignTicketMutation.isPending]);

  useEffect(() => {
    if (
      selectedTicket &&
      selectedTicketData &&
      (selectedTicketData.status === "O" || selectedTicketData.status === "A") &&
      !updateStatusMutation.isPending
    ) {
      const timer = setTimeout(() => {
        updateStatusMutation.mutate({
          ticketId: selectedTicket,
          status: "I",
        });
      }, 60000);
      return () => clearTimeout(timer);
    }
  }, [selectedTicket, selectedTicketData?.status]);

  useEffect(() => {
    setIsContactExpanded(false);
  }, [selectedTicket]);

  const handleContactClick = () => {
    if (
      !isContactExpanded &&
      selectedTicket &&
      selectedTicketData &&
      (selectedTicketData.status === "O" || selectedTicketData.status === "A") &&
      !updateStatusMutation.isPending
    ) {
      updateStatusMutation.mutate({
        ticketId: selectedTicket,
        status: "I",
      });
    }
    setIsContactExpanded(!isContactExpanded);
  };

  const handleAddComment = () => {
    if (!selectedTicket || !commentText.trim()) return;
    addCommentMutation.mutate({
      ticketId: selectedTicket,
      content: commentText.trim(),
    });
  };

  const handleStatusChange = (newStatus: string) => {
    if (!selectedTicket) return;
    updateStatusMutation.mutate({
      ticketId: selectedTicket,
      status: newStatus,
    });
  };

  const handleRefresh = () => {
    ticketsQuery.refetch();
    if (selectedTicket) {
      ticketDetailQuery.refetch();
    }
  };

  const getStatusBadge = (status?: string) => {
    const label = status ? statusLabels[status] || status : "Unknown";
    const color = status ? statusColors[status] || "bg-gray-500" : "bg-gray-500";
    return (
      <Badge className={`${color} text-white text-xs`}>
        {label}
      </Badge>
    );
  };

  return (
    <PageLayout
      title={t("tickets.title")}
      description={t("tickets.description")}
      className="p-0 flex flex-col"
      showSidebarTrigger={false}
      metrics={[
        { label: "Open", value: String(openCount), color: "#3b82f6", testId: "stat-open" },
        { label: "Assigned", value: String(assignedCount), color: "#a855f7", testId: "stat-assigned" },
        { label: "In Progress", value: String(inProgressCount), color: "#f59e0b", testId: "stat-in-progress" },
        { label: "Total", value: String(totalTicketsCount), testId: "stat-total-tickets" },
      ]}
      headerAction={
        <div className="flex items-center gap-2">
          <ConnectionStatus service="tickets" />
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
              <Tabs value={ticketView} onValueChange={(v) => setTicketView(v as "all" | "my")} className="flex-1">
                <TabsList className="h-8 w-full">
                  <TabsTrigger value="all" className="flex-1 text-xs" data-testid="tab-all-tickets">
                    All Tickets
                  </TabsTrigger>
                  <TabsTrigger value="my" className="flex-1 text-xs" data-testid="tab-my-tickets">
                    My Tickets
                  </TabsTrigger>
                </TabsList>
              </Tabs>
              <Dialog open={isCreateOpen} onOpenChange={setIsCreateOpen}>
                <DialogTrigger asChild>
                  <Button size="sm" className="h-8" data-testid="button-new-ticket">
                    <Plus className="h-4 w-4" />
                  </Button>
                </DialogTrigger>
                <DialogContent>
                  <DialogHeader>
                    <DialogTitle>Create New Ticket</DialogTitle>
                    <DialogDescription>
                      Create a new support ticket to track customer inquiries and issues.
                    </DialogDescription>
                  </DialogHeader>
                  <div className="space-y-4">
                    <div>
                      <Label htmlFor="description">Description</Label>
                      <Textarea
                        id="description"
                        placeholder="Describe the issue or inquiry..."
                        className="mt-2"
                        value={createForm.description}
                        onChange={(e) => setCreateForm({ ...createForm, description: e.target.value })}
                      />
                    </div>
                    <div>
                      <Label htmlFor="type">Type</Label>
                      <Select value={createForm.type} onValueChange={(type) => setCreateForm({ ...createForm, type })}>
                        <SelectTrigger id="type" className="mt-2">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="I">Incident</SelectItem>
                          <SelectItem value="C">Change</SelectItem>
                          <SelectItem value="P">Planned</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div>
                      <Label htmlFor="priority">Priority</Label>
                      <Select value={createForm.priority} onValueChange={(priority) => setCreateForm({ ...createForm, priority })}>
                        <SelectTrigger id="priority" className="mt-2">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="low">Low</SelectItem>
                          <SelectItem value="medium">Medium</SelectItem>
                          <SelectItem value="high">High</SelectItem>
                          <SelectItem value="urgent">Urgent</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="flex gap-2 justify-end">
                      <Button variant="outline" onClick={() => setIsCreateOpen(false)}>
                        Cancel
                      </Button>
                      <Button
                        onClick={() => createTicketMutation.mutate()}
                        disabled={!createForm.description.trim() || createTicketMutation.isPending}
                        data-testid="button-create-ticket-submit"
                      >
                        {createTicketMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                        Create Ticket
                      </Button>
                    </div>
                  </div>
                </DialogContent>
              </Dialog>
            </div>
            <div className="flex items-center gap-2">
              <Select value={statusFilter} onValueChange={setStatusFilter}>
                <SelectTrigger className="w-32 h-8" data-testid="select-status-filter">
                  <SelectValue placeholder="Status" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Status</SelectItem>
                  <SelectItem value="O">Open</SelectItem>
                  <SelectItem value="A">Assigned</SelectItem>
                  <SelectItem value="I">In Progress</SelectItem>
                  <SelectItem value="W">Waiting</SelectItem>
                  <SelectItem value="C">Closed</SelectItem>
                  <SelectItem value="P">Planned</SelectItem>
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
            </div>
          </div>

          <div className="flex-1 overflow-y-auto" ref={ticketsListRef}>
            {ticketsQuery.isLoading && allAccumulatedTickets.length === 0 && !ticketsQuery.data ? (
              <div className="p-4">
                <EmptyState
                  title="Loading tickets"
                  description="Fetching support tickets from the backend..."
                  isLoading
                />
              </div>
            ) : ticketsQuery.isError && allAccumulatedTickets.length === 0 ? (
              <div className="p-4">
                <ErrorDisplay
                  error={ticketsQuery.error}
                  endpoint="api/v1/crm/tickets"
                />
              </div>
            ) : filteredTickets.length === 0 ? (
              <div className="p-4">
                <EmptyState
                  title="No tickets found"
                  description={searchQuery ? "Try a different search term." : ticketView === "my" ? "You have no assigned tickets." : "No tickets match the current filter."}
                />
              </div>
            ) : (
              <>
                {filteredTickets.map((ticket) => (
                  <div
                    key={ticket.id}
                    onClick={() => setSelectedTicket(ticket.id)}
                    className={`p-3 border-b border-border cursor-pointer transition-colors ${
                      selectedTicket === ticket.id ? "bg-accent" : "hover-elevate"
                    }`}
                    data-testid={`ticket-item-${ticket.id}`}
                  >
                    <div className="flex items-start justify-between gap-2 mb-1">
                      <p className="font-medium text-sm truncate flex-1" data-testid={`text-ticket-customer-${ticket.id}`}>
                        {ticket.customer?.name || ticket.creator?.name || "Unknown"}
                      </p>
                      {getStatusBadge(ticket.status)}
                    </div>
                    <p className="text-sm text-foreground/80 line-clamp-2 mb-1.5" data-testid={`text-ticket-desc-${ticket.id}`}>
                      {renderTextWithLinks(ticket.description) || "No description"}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {formatRelativeTime(ticket.updated_at || ticket.created_at)}
                    </p>
                  </div>
                ))}
                {hasMoreTickets && (
                  <div ref={sentinelCallbackRef} className="h-10 flex items-center justify-center">
                    <span className="text-xs text-muted-foreground">Scroll to load more...</span>
                  </div>
                )}
                {isLoadingMore && (
                  <div className="p-3 text-center text-xs text-muted-foreground">
                    Loading more tickets...
                  </div>
                )}
              </>
            )}
          </div>
        </div>

        <div className="flex-1 flex flex-col bg-muted/20 backdrop-blur-sm">
          {!selectedTicket ? (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center">
                <div className="inline-flex h-16 w-16 items-center justify-center rounded-full bg-muted mb-4">
                  <TicketIcon className="h-8 w-8 text-muted-foreground" />
                </div>
                <p className="text-sm text-muted-foreground">Select a ticket to view details</p>
              </div>
            </div>
          ) : (
            <>
              <div className="p-4 border-b border-border bg-gradient-to-br from-background to-muted/30">
                <div className="flex items-center justify-between gap-3 mb-4">
                  <div className="flex items-center gap-3">
                    <h2 className="font-semibold text-lg" data-testid="text-ticket-id">
                      Ticket: {selectedTicketData?.ticket_number || selectedTicket.slice(0, 8)}
                    </h2>
                    {getStatusBadge(selectedTicketData?.status)}
                  </div>
                  <div className="flex items-center gap-2">
                    <Dialog open={isPlanOpen} onOpenChange={setIsPlanOpen}>
                      <DialogTrigger asChild>
                        <Button
                          variant="outline"
                          size="sm"
                          className="h-8"
                          disabled={selectedTicketData?.status === "C" || selectedTicketData?.status === "P"}
                          data-testid="button-plan-ticket"
                        >
                          <CalendarClock className="h-4 w-4 mr-1" />
                          Plan
                        </Button>
                      </DialogTrigger>
                      <DialogContent>
                        <DialogHeader>
                          <DialogTitle>Schedule Ticket</DialogTitle>
                          <DialogDescription>
                            Select a target date for when this ticket should be addressed.
                          </DialogDescription>
                        </DialogHeader>
                        <div className="space-y-4 pt-4">
                          <div className="space-y-2">
                            <Label>Target Date *</Label>
                            <div className="flex justify-center">
                              <Calendar
                                mode="single"
                                selected={planDate}
                                onSelect={setPlanDate}
                                disabled={(date) => date < new Date()}
                                className="rounded-md border"
                                data-testid="calendar-plan-date"
                              />
                            </div>
                            {planDate && (
                              <p className="text-sm text-center text-muted-foreground">
                                Selected: {planDate.toLocaleDateString("es-ES", { weekday: "long", year: "numeric", month: "long", day: "numeric" })}
                              </p>
                            )}
                          </div>
                          <div className="flex justify-end gap-2">
                            <Button
                              variant="outline"
                              onClick={() => {
                                setIsPlanOpen(false);
                                setPlanDate(undefined);
                              }}
                              data-testid="button-cancel-plan"
                            >
                              Cancel
                            </Button>
                            <Button
                              onClick={() => {
                                if (selectedTicket && planDate) {
                                  planTicketMutation.mutate({
                                    ticketId: selectedTicket,
                                    targetDate: planDate,
                                  });
                                }
                              }}
                              disabled={!planDate || planTicketMutation.isPending}
                              data-testid="button-confirm-plan"
                            >
                              {planTicketMutation.isPending ? (
                                <>
                                  <Loader2 className="h-4 w-4 mr-1 animate-spin" />
                                  Scheduling...
                                </>
                              ) : (
                                "Schedule Ticket"
                              )}
                            </Button>
                          </div>
                        </div>
                      </DialogContent>
                    </Dialog>

                    <Dialog open={isWaitingOpen} onOpenChange={setIsWaitingOpen}>
                      <DialogTrigger asChild>
                        <Button
                          variant="outline"
                          size="sm"
                          className="h-8"
                          disabled={selectedTicketData?.status === "C" || selectedTicketData?.status === "W"}
                          data-testid="button-set-waiting"
                        >
                          <Hourglass className="h-4 w-4 mr-1" />
                          Set Waiting
                        </Button>
                      </DialogTrigger>
                      <DialogContent>
                        <DialogHeader>
                          <DialogTitle>Set Ticket to Waiting</DialogTitle>
                          <DialogDescription>
                            Add a comment explaining why the ticket is waiting. Optionally select a contact you're waiting for.
                          </DialogDescription>
                        </DialogHeader>
                        <div className="space-y-4 pt-4">
                          <div className="space-y-2">
                            <Label>Waiting Comment *</Label>
                            <Textarea
                              placeholder="Explain why the ticket is waiting (e.g., 'Waiting for customer to provide additional information')"
                              value={waitingComment}
                              onChange={(e) => setWaitingComment(e.target.value)}
                              className="min-h-[80px]"
                              data-testid="textarea-waiting-comment"
                            />
                          </div>
                          <div className="space-y-2">
                            <Label>Waiting For (Optional)</Label>
                            <div className="relative">
                              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                              <Input
                                placeholder="Search contacts..."
                                value={contactSearchQuery}
                                onChange={(e) => setContactSearchQuery(e.target.value)}
                                className="pl-8"
                                data-testid="input-contact-search"
                              />
                            </div>
                            {waitingForContact && (
                              <div className="flex items-center gap-2 p-2 bg-muted rounded-md">
                                <User className="h-4 w-4 text-muted-foreground" />
                                <span className="text-sm flex-1">
                                  {filteredContacts.find(c => c.id === waitingForContact)?.name || "Selected contact"}
                                </span>
                                <Button
                                  variant="ghost"
                                  size="icon"
                                  className="h-6 w-6"
                                  onClick={() => setWaitingForContact(null)}
                                  data-testid="button-clear-waiting-contact"
                                >
                                  <X className="h-3 w-3" />
                                </Button>
                              </div>
                            )}
                            {!waitingForContact && (
                              <div className="max-h-48 overflow-y-auto border border-border rounded-md">
                                {(selectedTicketData?.creator || selectedTicketData?.customer) && (
                                  <>
                                    <div className="px-2 py-1.5 text-xs font-medium text-muted-foreground bg-muted/50">
                                      Ticket Requestor
                                    </div>
                                    <button
                                      type="button"
                                      className="w-full flex items-center gap-2 p-2 hover-elevate text-left bg-primary/5"
                                      onClick={(e) => {
                                        e.preventDefault();
                                        const contact = selectedTicketData?.creator || selectedTicketData?.customer;
                                        if (contact?.id) {
                                          setWaitingForContact(contact.id);
                                          setContactSearchQuery("");
                                        }
                                      }}
                                      data-testid="button-select-ticket-requestor"
                                    >
                                      <Avatar className="h-7 w-7">
                                        <AvatarFallback className="text-xs bg-primary text-primary-foreground">
                                          {(selectedTicketData?.creator?.name || selectedTicketData?.customer?.name || "?").charAt(0).toUpperCase()}
                                        </AvatarFallback>
                                      </Avatar>
                                      <div className="flex-1 min-w-0">
                                        <p className="text-sm font-medium truncate">
                                          {selectedTicketData?.creator?.name || selectedTicketData?.customer?.name}
                                        </p>
                                        {(selectedTicketData?.creator?.email || selectedTicketData?.customer?.email) && (
                                          <p className="text-xs text-muted-foreground truncate">
                                            {selectedTicketData?.creator?.email || selectedTicketData?.customer?.email}
                                          </p>
                                        )}
                                      </div>
                                      <Badge variant="secondary" className="text-xs">Requestor</Badge>
                                    </button>
                                  </>
                                )}
                                {(contactSearchQuery || filteredContacts.length > 0) && (
                                  <>
                                    <div className="px-2 py-1.5 text-xs font-medium text-muted-foreground bg-muted/50">
                                      Other Contacts
                                    </div>
                                    {contactsQuery.isLoading ? (
                                      <div className="flex items-center justify-center py-4">
                                        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                                      </div>
                                    ) : filteredContacts.length === 0 ? (
                                      <p className="text-sm text-muted-foreground text-center py-4">
                                        No contacts found
                                      </p>
                                    ) : (
                                      filteredContacts.map((c) => (
                                        <button
                                          type="button"
                                          key={c.id}
                                          className="w-full flex items-center gap-2 p-2 hover-elevate text-left"
                                          onClick={(e) => {
                                            e.preventDefault();
                                            setWaitingForContact(c.id);
                                            setContactSearchQuery("");
                                          }}
                                          data-testid={`button-select-contact-${c.id}`}
                                        >
                                          <Avatar className="h-7 w-7">
                                            <AvatarFallback className="text-xs">
                                              {c.name?.charAt(0).toUpperCase() || "?"}
                                            </AvatarFallback>
                                          </Avatar>
                                          <div className="flex-1 min-w-0">
                                            <p className="text-sm font-medium truncate">{c.name}</p>
                                            {c.email && (
                                              <p className="text-xs text-muted-foreground truncate">{c.email}</p>
                                            )}
                                          </div>
                                        </button>
                                      ))
                                    )}
                                  </>
                                )}
                              </div>
                            )}
                          </div>
                          <div className="flex justify-end gap-2">
                            <Button
                              variant="outline"
                              onClick={() => {
                                setIsWaitingOpen(false);
                                setWaitingComment("");
                                setWaitingForContact(null);
                                setContactSearchQuery("");
                              }}
                              data-testid="button-cancel-waiting"
                            >
                              Cancel
                            </Button>
                            <Button
                              onClick={() => {
                                if (selectedTicket && waitingComment.trim()) {
                                  setWaitingMutation.mutate({
                                    ticketId: selectedTicket,
                                    comment: waitingComment.trim(),
                                    waitingFor: waitingForContact || undefined,
                                  });
                                }
                              }}
                              disabled={!waitingComment.trim() || setWaitingMutation.isPending}
                              data-testid="button-confirm-waiting"
                            >
                              {setWaitingMutation.isPending ? (
                                <>
                                  <Loader2 className="h-4 w-4 mr-1 animate-spin" />
                                  Setting...
                                </>
                              ) : (
                                "Set Waiting"
                              )}
                            </Button>
                          </div>
                        </div>
                      </DialogContent>
                    </Dialog>

                    <Popover open={isAssignOpen} onOpenChange={setIsAssignOpen}>
                      <PopoverTrigger asChild>
                        <Button
                          variant="outline"
                          size="sm"
                          className="h-8"
                          disabled={selectedTicketData?.status === "C"}
                          data-testid="button-assign-ticket"
                        >
                          <UserPlus className="h-4 w-4 mr-1" />
                          Assign To
                        </Button>
                      </PopoverTrigger>
                      <PopoverContent className="w-72 p-0" align="end">
                        <div className="p-3 border-b border-border">
                          <div className="relative">
                            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                            <Input
                              placeholder="Search users..."
                              value={userSearchQuery}
                              onChange={(e) => setUserSearchQuery(e.target.value)}
                              className="pl-8 h-8"
                              data-testid="input-user-search"
                            />
                          </div>
                        </div>
                        <div className="max-h-64 overflow-y-auto p-1">
                          {usersQuery.isLoading ? (
                            <div className="flex items-center justify-center py-4">
                              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                            </div>
                          ) : usersQuery.isError ? (
                            <div className="py-4 px-3">
                              <p className="text-sm font-medium">Unable to load team members</p>
                              <p className="text-xs text-muted-foreground mt-1">
                                {(usersQuery.error as any)?.message || "Check your permissions or try again."}
                              </p>
                            </div>
                          ) : filteredUsers.length === 0 ? (
                            <p className="text-sm text-muted-foreground text-center py-4">
                              {userSearchQuery ? "No users found" : "No team members available"}
                            </p>
                          ) : (
                            filteredUsers.map((u) => {
                              const displayName = u.full_name || `${u.first_name || ""} ${u.last_name || ""}`.trim() || u.username || u.email || "Unknown";
                              const initials = displayName.split(" ").map((n) => n[0]).join("").slice(0, 2).toUpperCase();
                              return (
                                <button
                                  key={u.id}
                                  className="w-full flex items-center gap-2 p-2 rounded-md hover-elevate text-left"
                                  onClick={() => {
                                    if (selectedTicket) {
                                      manualAssignMutation.mutate({
                                        ticketId: selectedTicket,
                                        userId: String(u.id),
                                      });
                                    }
                                  }}
                                  disabled={manualAssignMutation.isPending}
                                  data-testid={`button-assign-user-${u.id}`}
                                >
                                  <Avatar className="h-8 w-8">
                                    {u.avatar_url && <AvatarImage src={u.avatar_url} alt={displayName} />}
                                    <AvatarFallback className="text-xs">{initials}</AvatarFallback>
                                  </Avatar>
                                  <div className="flex-1 min-w-0">
                                    <p className="text-sm font-medium truncate">{displayName}</p>
                                    {u.email && (
                                      <p className="text-xs text-muted-foreground truncate">{u.email}</p>
                                    )}
                                  </div>
                                  {u.role && (
                                    <Badge variant="outline" className="text-xs shrink-0">{u.role}</Badge>
                                  )}
                                </button>
                              );
                            })
                          )}
                        </div>
                      </PopoverContent>
                    </Popover>

                    <Dialog open={isCloseOpen} onOpenChange={setIsCloseOpen}>
                      <DialogTrigger asChild>
                        <Button
                          variant="destructive"
                          size="sm"
                          className="h-8"
                          disabled={selectedTicketData?.status === "C"}
                          data-testid="button-close-ticket"
                        >
                          <X className="h-4 w-4 mr-1" />
                          Close Ticket
                        </Button>
                      </DialogTrigger>
                      <DialogContent>
                        <DialogHeader>
                          <DialogTitle>Close Ticket</DialogTitle>
                          <DialogDescription>
                            Please provide a closing comment before closing this ticket. This will be added to the ticket history.
                          </DialogDescription>
                        </DialogHeader>
                        <div className="space-y-4 pt-4">
                          <div className="space-y-2">
                            <Label htmlFor="close-comment">Closing Comment *</Label>
                            <Textarea
                              id="close-comment"
                              placeholder="Enter a reason for closing this ticket..."
                              value={closeComment}
                              onChange={(e) => setCloseComment(e.target.value)}
                              rows={4}
                              data-testid="input-close-comment"
                            />
                          </div>
                          <div className="flex justify-end gap-2">
                            <Button
                              variant="outline"
                              onClick={() => {
                                setIsCloseOpen(false);
                                setCloseComment("");
                              }}
                              data-testid="button-cancel-close"
                            >
                              Cancel
                            </Button>
                            <Button
                              variant="destructive"
                              onClick={() => {
                                if (selectedTicket && closeComment.trim()) {
                                  closeTicketMutation.mutate({
                                    ticketId: selectedTicket,
                                    comment: closeComment.trim(),
                                  });
                                }
                              }}
                              disabled={!closeComment.trim() || closeTicketMutation.isPending}
                              data-testid="button-confirm-close"
                            >
                              {closeTicketMutation.isPending ? (
                                <>
                                  <Loader2 className="h-4 w-4 mr-1 animate-spin" />
                                  Closing...
                                </>
                              ) : (
                                "Close Ticket"
                              )}
                            </Button>
                          </div>
                        </div>
                      </DialogContent>
                    </Dialog>
                  </div>
                </div>

                <div className="flex items-center flex-wrap gap-4 text-sm text-muted-foreground mb-4">
                  <span>Assigned to: <strong className="text-foreground">{selectedTicketData?.assigned_to?.name || "Unassigned"}</strong></span>
                  <span>{formatDateTime(selectedTicketData?.created_at)}</span>
                  {selectedTicketData?.target && (
                    <span className="flex items-center gap-1">
                      <CalendarClock className="h-3 w-3" />
                      Target: <strong className="text-foreground">{new Date(selectedTicketData.target).toLocaleDateString("es-ES", { day: "numeric", month: "short", year: "numeric" })}</strong>
                    </span>
                  )}
                  {selectedTicketData?.status === "W" && selectedTicketData?.waiting_since && (
                    <span className="flex items-center gap-1">
                      <Hourglass className="h-3 w-3" />
                      Waiting since: <strong className="text-foreground">{new Date(selectedTicketData.waiting_since).toLocaleDateString("es-ES", { day: "numeric", month: "short" })}</strong>
                    </span>
                  )}
                  {selectedTicketData?.waiting_for && (
                    <span className="flex items-center gap-1">
                      <User className="h-3 w-3" />
                      Waiting for: <strong className="text-foreground">{selectedTicketData.waiting_for.name || "Contact"}</strong>
                    </span>
                  )}
                  {selectedTicketData?.type_label && (
                    <Badge variant="outline" className="text-xs">{selectedTicketData.type_label}</Badge>
                  )}
                </div>

                <div className="flex gap-3 mb-0">
                  <div className="flex-1 bg-card rounded-lg border border-border p-4">
                    <h3 className="font-medium text-sm text-muted-foreground mb-2">User Request</h3>
                    <div className="text-base leading-relaxed" data-testid="text-ticket-description">
                      {renderTextWithLinks(selectedTicketData?.description) || "No description provided."}
                    </div>
                  </div>

                  {(selectedTicketData?.customer || selectedTicketData?.creator) && (() => {
                    const contact = selectedTicketData?.customer || selectedTicketData?.creator;
                    const contactEmail = contact?.email;
                    const contactPhone = contact?.phone;
                    const whatsappNumber = contactPhone?.replace(/[^0-9]/g, "");
                    
                    return (
                      <div
                        className="w-48 h-40 shrink-0 cursor-pointer [perspective:1000px]"
                        onClick={handleContactClick}
                        data-testid="button-contact-card"
                      >
                        <div
                          className={`relative w-full h-full transition-transform duration-500 [transform-style:preserve-3d] ${
                            isContactExpanded ? "[transform:rotateY(180deg)]" : ""
                          }`}
                        >
                          <div className="absolute inset-0 bg-card rounded-lg border border-border p-3 [backface-visibility:hidden] flex flex-col items-center justify-center text-center">
                            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-primary text-primary-foreground font-semibold text-lg mb-2">
                              {(contact?.name || "?").charAt(0).toUpperCase()}
                            </div>
                            <p className="font-medium text-sm mb-1 truncate w-full">
                              {contact?.name || "Unknown"}
                            </p>
                            {contact?.contacttype?.name && (
                              <Badge variant="secondary" className="text-xs mb-1">
                                {contact.contacttype.name}
                              </Badge>
                            )}
                            {contact?.company && (
                              <p className="text-xs text-muted-foreground truncate w-full">
                                {contact.company}
                              </p>
                            )}
                          </div>

                          <div className="absolute inset-0 bg-card rounded-lg border border-border p-3 [backface-visibility:hidden] [transform:rotateY(180deg)] flex flex-col items-center justify-center text-center">
                            <p className="font-medium text-sm mb-3">{contact?.name || "Unknown"}</p>
                            <div className="space-y-2 w-full">
                              {contactEmail && (
                                <a
                                  href={`mailto:${contactEmail}`}
                                  onClick={(e) => e.stopPropagation()}
                                  className="flex items-center justify-center gap-2 text-xs text-primary hover:underline"
                                  data-testid="link-contact-email"
                                >
                                  <Mail className="h-4 w-4" />
                                  <span className="truncate">{contactEmail}</span>
                                </a>
                              )}
                              {contactPhone && (
                                <a
                                  href={`https://wa.me/${whatsappNumber}`}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  onClick={(e) => e.stopPropagation()}
                                  className="flex items-center justify-center gap-2 text-xs text-green-600 hover:underline"
                                  data-testid="link-contact-whatsapp"
                                >
                                  <MessageCircle className="h-4 w-4" />
                                  <span>{contactPhone}</span>
                                </a>
                              )}
                            </div>
                            <p className="text-xs text-muted-foreground mt-3">Click to flip back</p>
                          </div>
                        </div>
                      </div>
                    );
                  })()}
                </div>
              </div>

              <div className="flex-1 overflow-y-auto p-4">
                <div className="bg-card rounded-lg border border-border">
                  <div className="px-4 py-2 border-b border-border">
                    <h3 className="font-medium text-sm text-muted-foreground">Comments</h3>
                  </div>
                  <div className="p-4">
                {ticketDetailQuery.isLoading ? (
                  <EmptyState
                    title="Loading ticket details"
                    description="Fetching the latest ticket information..."
                    isLoading
                  />
                ) : ticketDetailQuery.isError ? (
                  <ErrorDisplay
                    error={ticketDetailQuery.error}
                    endpoint={`api/v1/crm/tickets/${selectedTicket}`}
                  />
                ) : comments.length === 0 ? (
                  <EmptyState
                    title="No comments yet"
                    description="Comments and updates will appear here once team members add them."
                  />
                ) : (
                  <div className="space-y-3">
                    {comments.map((comment) => (
                      <div
                        key={comment.id}
                        className="p-3 rounded-lg bg-card border border-border shadow-sm"
                        data-testid={`comment-${comment.id}`}
                      >
                        <div className="flex items-start gap-2.5 mb-2">
                          <div className="flex h-7 w-7 items-center justify-center rounded-full bg-primary text-primary-foreground text-xs font-semibold shrink-0">
                            {comment.creator?.name?.charAt(0) || "?"}
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2">
                              <p className="font-semibold text-sm">
                                {comment.creator?.name ?? "Unknown User"}
                              </p>
                              {comment.creator?.email && (
                                <span className="text-xs text-muted-foreground">{comment.creator.email}</span>
                              )}
                            </div>
                            {comment.created_at && (
                              <p className="text-xs text-muted-foreground">
                                {new Date(comment.created_at).toLocaleString()}
                              </p>
                            )}
                          </div>
                        </div>
                        {comment.comment && (
                          <p className="text-sm text-foreground whitespace-pre-wrap break-words ml-9">
                            {comment.comment}
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                )}
                  </div>
                </div>
              </div>

              <div className="p-3 border-t border-border bg-background">
                <p className="text-xs text-muted-foreground mb-2">{user?.email}</p>
                <div className="flex gap-2">
                  <Input
                    placeholder="Add your comment..."
                    className="flex-1"
                    data-testid="input-comment"
                    value={commentText}
                    onChange={(e) => setCommentText(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.shiftKey) {
                        e.preventDefault();
                        handleAddComment();
                      }
                    }}
                    disabled={addCommentMutation.isPending}
                  />
                  <Button
                    data-testid="button-send-comment"
                    onClick={handleAddComment}
                    disabled={!commentText.trim() || addCommentMutation.isPending}
                  >
                    Guardar
                  </Button>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </PageLayout>
  );
}
