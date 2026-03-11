import { useMemo, useState, useEffect, useRef, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { useQuery, useMutation } from "@tanstack/react-query";
import { useLocation, Link } from "wouter";
import { 
  Search, 
  Users, 
  Briefcase, 
  Building2, 
  Database, 
  BarChart3, 
  LayoutDashboard,
  Plus,
  Package,
  BookOpen,
  Wrench,
  UserCog,
  Tags,
  TrendingUp,
  Clock,
  Target,
  ChevronLeft,
  ChevronRight,
  X,
  Phone,
  Mail,
  MessageSquare,
  ArrowLeft,
  Eye,
  EyeOff,
  Globe,
  Lock,
  Save,
  Trash2,
  Map as MapIcon,
  FileText,
  Pencil,
  Tags as TagsIcon,
  Maximize2,
  Minimize2,
  Loader2,
  Home,
  Bot,
  GitBranch,
  GripVertical,
  CheckCircle2,
  XCircle,
  Percent
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { ScrollArea } from "@/components/ui/scroll-area";
import { PageLayout } from "@/components/layout/page-layout";
import { GlassPanel } from "@/components/radiant/glass-panel";
import { EmptyState } from "@/components/empty-state";
import { ErrorDisplay } from "@/components/error-display";
import { ContactEditorModal } from "@/components/crm/contact-editor-modal";
import { ContactDetailsModal, type ContactDetailsContact } from "@/components/crm/contact-details-modal";
import { AccountDetailsModal } from "@/components/crm/account-details-modal";
import { AccountEditorModal } from "@/components/crm/account-editor-modal";
import { fetchJson, apiRequest, queryClient } from "@/lib/queryClient";
import { cn } from "@/lib/utils";
import { apiV1, getAuthHeaders } from "@/lib/api";
import { useToast } from "@/hooks/use-toast";
import { useIsMobile } from "@/hooks/use-mobile";
import { useAppBarAction } from "@/contexts/AppBarActionContext";
import { Contact, PaginatedResponse } from "@/lib/moio-types";
import { SiWhatsapp } from "react-icons/si";

type CRMTabType = "overview" | "contacts" | "accounts" | "master_data" | "analytics";

interface Deal {
  id: string;
  title: string;
  company?: string | null;
  value?: number | null;
  currency?: string;
  stage?: string;
}

interface DealsResponse {
  deals?: Deal[];
}

interface ContactsPagination {
  current_page: number;
  total_pages: number;
  total_items: number;
  items_per_page: number;
}

interface ContactsResponse {
  contacts: any[];
  pagination: ContactsPagination;
}

interface CRMAccount {
  id: string;
  name: string;
  legal_name?: string | null;
  type?: string;
  status?: string | null;
  email?: string | null;
  phone?: string | null;
  tax_id?: string | null;
  addresses?: Array<Record<string, unknown>>;
  created_at?: string | null;
}

interface AccountsResponse {
  customers: CRMAccount[];
  pagination: ContactsPagination;
}

interface PipelineStage {
  id: string;
  name: string;
  order: number;
  probability: number;
  is_won: boolean;
  is_lost: boolean;
  color: string;
}

interface Pipeline {
  id: string;
  name: string;
  description?: string;
  is_default: boolean;
  stages: PipelineStage[];
  created_at?: string;
  updated_at?: string;
}

interface ServiceTemplate {
  id: string;
  title: string;
  description?: string;
  type: string;
  visibility: "public" | "private" | "internal";
  precedence?: number;
  data?: {
    service_area?: {
      polygon?: Array<{ lat: number; lng: number }>;
      center?: { lat: number; lng: number };
    };
    business_hours?: Array<{
      day: string;
      open: string;
      close: string;
      enabled: boolean;
    }>;
  };
  created_at?: string;
  updated_at?: string;
}

interface BusinessHour {
  day: string;
  open: string;
  close: string;
  enabled: boolean;
}

const DEFAULT_BUSINESS_HOURS: BusinessHour[] = [
  { day: "monday", open: "09:00", close: "18:00", enabled: true },
  { day: "tuesday", open: "09:00", close: "18:00", enabled: true },
  { day: "wednesday", open: "09:00", close: "18:00", enabled: true },
  { day: "thursday", open: "09:00", close: "18:00", enabled: true },
  { day: "friday", open: "09:00", close: "18:00", enabled: true },
  { day: "saturday", open: "10:00", close: "14:00", enabled: false },
  { day: "sunday", open: "10:00", close: "14:00", enabled: false },
];

interface CRMContact {
  id: string;
  name: string;
  email?: string | null;
  phone?: string | null;
  company?: string | null;
  type?: string;
  tags?: string[];
  notes?: string;
  address?: string;
  created_at?: string;
  updated_at?: string;
  activity_summary?: {
    total_deals: number;
    total_tickets: number;
    total_messages: number;
    last_contact?: string;
  };
}

interface AddContactModalProps {
  open: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

interface AgentBasic {
  id: string;
  name: string | null;
  enabled: boolean;
}

type AgentsListResponse =
  | AgentBasic[]
  | {
      results?: AgentBasic[];
      agents?: AgentBasic[];
      items?: AgentBasic[];
      data?: AgentBasic[];
      count?: number;
      next?: string | null;
      previous?: string | null;
    };

function extractAgents(data: AgentsListResponse | undefined): AgentBasic[] {
  if (!data) return [];
  if (Array.isArray(data)) return data;
  const results = (data as any).results;
  if (Array.isArray(results)) return results as AgentBasic[];
  const agents = (data as any).agents;
  if (Array.isArray(agents)) return agents as AgentBasic[];
  const items = (data as any).items;
  if (Array.isArray(items)) return items as AgentBasic[];
  const inner = (data as any).data;
  if (Array.isArray(inner)) return inner as AgentBasic[];
  return [];
}

type ContactTypesListResponse = {
  // Legacy/non-paginated shape
  contact_types?: ContactType[];
  // Paginated shape (common)
  count?: number;
  next?: string | null;
  previous?: string | null;
  results?: ContactType[] | { contact_types?: ContactType[] };
};

function extractContactTypes(data: ContactTypesListResponse | undefined): ContactType[] {
  if (!data) return [];
  if (Array.isArray(data.contact_types)) return data.contact_types;
  const results: any = (data as any).results;
  if (Array.isArray(results)) return results as ContactType[];
  if (results && Array.isArray(results.contact_types)) return results.contact_types as ContactType[];
  return [];
}

function AddContactModal({ open, onClose, onSuccess }: AddContactModalProps) {
  const { toast } = useToast();
  const [formData, setFormData] = useState({
    name: "",
    email: "",
    phone: "",
    company: "",
    type: "",
    agent_id: "",
    notes: "",
  });
  const [isSubmitting, setIsSubmitting] = useState(false);

  const contactTypesQuery = useQuery<ContactTypesListResponse>({
    queryKey: [apiV1("/crm/contact_types/")],
    queryFn: () => fetchJson<ContactTypesListResponse>(apiV1("/crm/contact_types/"), { page_size: 200 }),
  });

  const agentsQuery = useQuery<AgentsListResponse>({
    queryKey: [apiV1("/settings/agents/")],
    queryFn: () => fetchJson<AgentsListResponse>(apiV1("/settings/agents/"), { page_size: 200 }),
  });

  const contactTypes = extractContactTypes(contactTypesQuery.data);
  const agents = extractAgents(agentsQuery.data as any).filter((a) => a.enabled);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!formData.name.trim()) {
      toast({
        title: "Validation Error",
        description: "Name is required",
        variant: "destructive",
      });
      return;
    }

    setIsSubmitting(true);
    try {
      await apiRequest("POST", apiV1("/crm/contacts/"), { data: formData });
      toast({
        title: "Contact Created",
        description: `${formData.name} has been added successfully.`,
      });
      onSuccess();
      onClose();
      setFormData({ name: "", email: "", phone: "", company: "", type: "", agent_id: "", notes: "" });
    } catch (error: any) {
      toast({
        title: "Error",
        description: error.message || "Failed to create contact",
        variant: "destructive",
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleClose = () => {
    setFormData({ name: "", email: "", phone: "", company: "", type: "", agent_id: "", notes: "" });
    onClose();
  };

  return (
    <Dialog open={open} onOpenChange={(isOpen) => !isOpen && handleClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Add New Contact</DialogTitle>
          <DialogDescription>
            Fill in the details to create a new contact.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4 py-4">
          <div className="space-y-2">
            <Label htmlFor="name">Name *</Label>
            <Input
              id="name"
              placeholder="Full name"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              data-testid="input-contact-name"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="email">Email</Label>
            <Input
              id="email"
              type="email"
              placeholder="email@example.com"
              value={formData.email}
              onChange={(e) => setFormData({ ...formData, email: e.target.value })}
              data-testid="input-contact-email"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="phone">Phone</Label>
            <Input
              id="phone"
              placeholder="+1 (555) 123-4567"
              value={formData.phone}
              onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
              data-testid="input-contact-phone"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="company">Company</Label>
            <Input
              id="company"
              placeholder="Company name"
              value={formData.company}
              onChange={(e) => setFormData({ ...formData, company: e.target.value })}
              data-testid="input-contact-company"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="type">Contact Type</Label>
            <Select
              value={formData.type}
              onValueChange={(value) => setFormData({ ...formData, type: value })}
              disabled={contactTypesQuery.isLoading}
            >
              <SelectTrigger data-testid="select-contact-type">
                <SelectValue placeholder={contactTypesQuery.isLoading ? "Loading..." : "Select type"} />
              </SelectTrigger>
              <SelectContent>
                {contactTypes.map((type) => (
                  <SelectItem key={type.id} value={type.name}>
                    {type.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="agent">Assigned Agent</Label>
            <Select
              value={formData.agent_id}
              onValueChange={(value) => setFormData({ ...formData, agent_id: value })}
              disabled={agentsQuery.isLoading}
            >
              <SelectTrigger data-testid="select-contact-agent">
                <SelectValue placeholder={agentsQuery.isLoading ? "Loading..." : "Select agent (optional)"} />
              </SelectTrigger>
              <SelectContent>
                {agents.map((agent) => (
                  <SelectItem key={agent.id} value={agent.id}>
                    {agent.name || `Agent ${agent.id.slice(0, 8)}`}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="notes">Notes</Label>
            <Textarea
              id="notes"
              placeholder="Additional notes about this contact..."
              value={formData.notes}
              onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
              className="min-h-[80px]"
              data-testid="input-contact-notes"
            />
          </div>

          <DialogFooter className="pt-4">
            <Button type="button" variant="outline" onClick={handleClose} disabled={isSubmitting}>
              Cancel
            </Button>
            <Button type="submit" disabled={isSubmitting} data-testid="button-save-contact">
              {isSubmitting ? "Saving..." : "Save Contact"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function useQueryParams() {
  const [search, setSearch] = useState(window.location.search);

  useEffect(() => {
    const handlePopState = () => {
      setSearch(window.location.search);
    };
    
    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  return useMemo(() => new URLSearchParams(search), [search]);
}

const crmSections = [
  { id: "overview", labelKey: "crm.overview", icon: LayoutDashboard },
  { id: "contacts", labelKey: "crm.contacts", icon: Users },
  { id: "accounts", labelKey: "crm.accounts", icon: Building2 },
  { id: "master_data", labelKey: "crm.master_data", icon: Database },
  { id: "analytics", labelKey: "crm.analytics", icon: BarChart3 },
];

const masterDataSubsections = [
  { id: "services", label: "Services" },
  { id: "knowledge_base", label: "Knowledge Base" },
  { id: "tags", label: "Tags" },
  { id: "contact_types", label: "Contact Types" },
  { id: "pipelines", label: "Pipelines" },
];

interface BreadcrumbItem {
  id: string;
  label: string;
  onClick?: () => void;
}

function Breadcrumbs({ items }: { items: BreadcrumbItem[] }) {
  return (
    <nav className="flex items-center gap-1 text-sm">
      {items.map((item, index) => (
        <div key={item.id} className="flex items-center gap-1">
          {index > 0 && <ChevronRight className="h-4 w-4 text-muted-foreground" />}
          {item.onClick ? (
            <button
              type="button"
              onClick={item.onClick}
              className="text-muted-foreground hover:text-foreground transition-colors"
              data-testid={`breadcrumb-${item.id}`}
            >
              {item.label}
            </button>
          ) : (
            <span className="font-medium text-foreground" data-testid={`breadcrumb-${item.id}`}>
              {item.label}
            </span>
          )}
        </div>
      ))}
    </nav>
  );
}

export default function CRM() {
  const { t } = useTranslation();
  const isMobile = useIsMobile();
  const [location, navigate] = useLocation();
  const [searchQuery, setSearchQuery] = useState("");
  const queryParams = useQueryParams();

  const activeTab: CRMTabType = useMemo(() => {
    const tab = queryParams.get("tab");
    if (tab && ["overview", "contacts", "accounts", "master_data", "analytics"].includes(tab)) {
      return tab as CRMTabType;
    }
    return "overview";
  }, [queryParams]);

  const activeSubsection = useMemo(() => {
    return queryParams.get("section") || null;
  }, [queryParams]);

  const openContactId = useMemo(() => {
    const raw = queryParams.get("contactId");
    return raw ? String(raw).trim() : null;
  }, [queryParams]);

  const openAccountId = useMemo(() => {
    const raw = queryParams.get("accountId");
    return raw ? String(raw).trim() : null;
  }, [queryParams]);

  const setActiveTab = (tab: CRMTabType) => {
    const newUrl = `/crm?tab=${tab}`;
    window.history.pushState({ tab }, '', newUrl);
    window.dispatchEvent(new PopStateEvent('popstate'));
  };

  const setActiveSubsection = (section: string | null) => {
    const newUrl = section ? `/crm?tab=${activeTab}&section=${section}` : `/crm?tab=${activeTab}`;
    window.history.pushState({ tab: activeTab, section }, '', newUrl);
    window.dispatchEvent(new PopStateEvent('popstate'));
  };

  const setOpenContactId = useCallback((id: string | null) => {
    const params = new URLSearchParams(window.location.search);
    if (id) params.set("contactId", id);
    else params.delete("contactId");
    const query = params.toString();
    const url = query ? `${window.location.pathname}?${query}` : window.location.pathname;
    window.history.pushState({}, '', url);
    window.dispatchEvent(new PopStateEvent('popstate'));
  }, []);

  const setOpenAccountId = useCallback((id: string | null) => {
    const params = new URLSearchParams(window.location.search);
    if (id) params.set("accountId", id);
    else params.delete("accountId");
    const query = params.toString();
    const url = query ? `${window.location.pathname}?${query}` : window.location.pathname;
    window.history.pushState({}, '', url);
    window.dispatchEvent(new PopStateEvent('popstate'));
  }, []);

  useEffect(() => {
    setSearchQuery("");
  }, [activeTab, activeSubsection]);

  const currentSection = crmSections.find(s => s.id === activeTab);
  const currentSubsection = masterDataSubsections.find(s => s.id === activeSubsection);

  const breadcrumbs: BreadcrumbItem[] = useMemo(() => {
    const items: BreadcrumbItem[] = [
      { id: "crm", label: "CRM", onClick: () => setActiveTab("overview") },
    ];
    
    if (currentSection && activeTab !== "overview") {
      if (activeTab === "master_data" && activeSubsection) {
        items.push({ 
          id: activeTab, 
          label: currentSection.label, 
          onClick: () => setActiveSubsection(null) 
        });
        if (currentSubsection) {
          items.push({ id: activeSubsection, label: currentSubsection.label });
        }
      } else {
        items.push({ id: activeTab, label: currentSection.label });
      }
    }
    
    return items;
  }, [activeTab, activeSubsection, currentSection, currentSubsection]);

  const renderSearchPlaceholder = () => {
    if (activeSubsection) {
      const sub = masterDataSubsections.find(s => s.id === activeSubsection);
      return `Search ${sub?.label.toLowerCase() || "items"}...`;
    }
    switch (activeTab) {
      case "contacts": return "Search contacts...";
      case "accounts": return "Search accounts...";
      case "master_data": return "Search master data...";
      case "analytics": return "Search analytics...";
      default: return "Search CRM...";
    }
  };

  const renderContent = () => {
    if (activeTab === "master_data") {
      if (activeSubsection === "services") {
        return <ServicesSection onBack={() => setActiveSubsection(null)} />;
      }
      if (activeSubsection === "knowledge_base") {
        return <KnowledgeBaseSection onBack={() => setActiveSubsection(null)} />;
      }
      if (activeSubsection === "tags") {
        return <TagsSection onBack={() => setActiveSubsection(null)} />;
      }
      if (activeSubsection === "contact_types") {
        return <ContactTypesSection onBack={() => setActiveSubsection(null)} />;
      }
      if (activeSubsection === "pipelines") {
        return <PipelinesSection onBack={() => setActiveSubsection(null)} />;
      }
      return <MasterDataGrid searchQuery={searchQuery} onSelectSection={setActiveSubsection} />;
    }
    
    switch (activeTab) {
      case "overview": return (
        <OverviewTab
          setActiveTab={setActiveTab}
          onViewContact={(id) => {
            const params = new URLSearchParams();
            params.set("tab", "contacts");
            params.set("contactId", id);
            window.history.pushState({}, "", `/crm?${params.toString()}`);
            window.dispatchEvent(new PopStateEvent("popstate"));
          }}
        />
      );
      case "contacts": return <ContactsTab searchQuery={searchQuery} openContactId={openContactId} setOpenContactId={setOpenContactId} />;
      case "accounts": return <AccountsTab searchQuery={searchQuery} openAccountId={openAccountId} setOpenAccountId={setOpenAccountId} />;
      case "analytics": return <AnalyticsTab />;
      default: return <OverviewTab />;
    }
  };

  const hideSubmenuOnMobile = isMobile && activeTab === "contacts";

  return (
    <div className="flex h-full">
      {!hideSubmenuOnMobile && (
        <div className="w-64 border-r border-border bg-background flex flex-col shrink-0">
          <div className="p-3 border-b border-border">
            <h2 className="font-semibold text-sm">{t("crm.title")}</h2>
            <p className="text-xs text-muted-foreground mt-0.5">{t("crm.description")}</p>
          </div>
          <div className="p-2 space-y-1 border-b border-border">
            {crmSections.map((section) => {
              const Icon = section.icon;
              const isActive = activeTab === section.id;
              return (
                <button
                  key={section.id}
                  type="button"
                  onClick={() => setActiveTab(section.id as CRMTabType)}
                  className={`w-full flex items-center gap-2 px-3 py-2 text-sm rounded-md transition-colors ${
                    isActive 
                      ? "bg-accent text-accent-foreground" 
                      : "text-muted-foreground hover-elevate"
                  }`}
                  data-testid={`nav-${section.id}`}
                >
                  <Icon className="h-4 w-4" />
                  {t(section.labelKey)}
                </button>
              );
            })}
          </div>
        </div>
      )}

      <div className="flex-1 flex flex-col bg-muted/20 overflow-hidden min-w-0">
        <div className={`flex items-center justify-between gap-4 pl-2 pr-4 py-3 border-b border-border ${hideSubmenuOnMobile ? "flex-row gap-2" : ""}`}>
          {!hideSubmenuOnMobile ? <Breadcrumbs items={breadcrumbs} /> : <span className="text-sm font-medium truncate">{t("crm.contacts")}</span>}
          <div className={`relative flex-1 min-w-0 ${hideSubmenuOnMobile ? "max-w-full" : "w-72"}`}>
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
            <Input
              placeholder={renderSearchPlaceholder()}
              className="pl-10"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              data-testid="input-crm-search"
            />
          </div>
        </div>
        
        <div className={cn(
          "flex-1 overflow-y-auto py-4",
          hideSubmenuOnMobile ? "px-4" : "pl-2 pr-4",
          "pb-24 md:pb-4"
        )}>
          {renderContent()}
        </div>
      </div>
    </div>
  );
}


function OverviewTab({ setActiveTab, onViewContact }: {
  setActiveTab: (tab: CRMTabType) => void;
  onViewContact: (contactId: string) => void;
}) {
  const contactsQuery = useQuery<ContactsResponse>({
    queryKey: [apiV1("/crm/contacts/"), 1, 10],
    queryFn: () => fetchJson<ContactsResponse>(apiV1("/crm/contacts/"), { page: "1", page_size: "10" }),
  });

  const dealsQuery = useQuery<DealsResponse>({
    queryKey: [apiV1("/crm/deals/")],
    queryFn: () => fetchJson<DealsResponse>(apiV1("/crm/deals/")),
  });

  const contacts = contactsQuery.data?.contacts || [];
  const totalContacts = contactsQuery.data?.pagination?.total_items ?? contacts.length;
  const deals = dealsQuery.data?.deals || [];
  
  const pipelineValuesByCurrency = useMemo(() => {
    const byCurrency: Record<string, number> = {};
    for (const deal of deals) {
      const currency = deal.currency || "USD";
      const value = Number(deal.value) || 0;
      byCurrency[currency] = (byCurrency[currency] || 0) + value;
    }
    return Object.entries(byCurrency)
      .sort((a, b) => b[1] - a[1])
      .map(([currency, total]) => ({ currency, total }));
  }, [deals]);

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <GlassPanel
          className="p-4 cursor-pointer hover-elevate transition-shadow"
          onClick={() => setActiveTab("contacts")}
          data-testid="kpi-total-contacts"
        >
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-blue-500/10">
              <Users className="h-5 w-5 text-blue-500" />
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Total Contacts</p>
              {contactsQuery.isLoading ? (
                <Skeleton className="h-7 w-16" />
              ) : (
                <p className="text-2xl font-bold" data-testid="text-total-contacts">
                  {totalContacts.toLocaleString()}
                </p>
              )}
            </div>
          </div>
        </GlassPanel>

        <Link href="/deals">
          <GlassPanel className="p-4 cursor-pointer hover-elevate transition-shadow" data-testid="kpi-active-deals">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-green-500/10">
                <Briefcase className="h-5 w-5 text-green-500" />
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Active Deals</p>
                {dealsQuery.isLoading ? (
                  <Skeleton className="h-7 w-16" />
                ) : (
                  <p className="text-2xl font-bold" data-testid="text-active-deals">
                    {deals.length}
                  </p>
                )}
              </div>
            </div>
          </GlassPanel>
        </Link>

        <Link href="/deals">
          <GlassPanel className="p-4 cursor-pointer hover-elevate transition-shadow" data-testid="kpi-pipeline-value">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-purple-500/10">
                <TrendingUp className="h-5 w-5 text-purple-500" />
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Pipeline Value</p>
                {dealsQuery.isLoading ? (
                  <Skeleton className="h-7 w-24" />
                ) : pipelineValuesByCurrency.length === 0 ? (
                  <p className="text-2xl font-bold" data-testid="text-pipeline-value">$0</p>
                ) : (
                  <div className="space-y-0.5" data-testid="text-pipeline-value">
                    {pipelineValuesByCurrency.map(({ currency, total }) => (
                      <p key={currency} className="text-lg font-bold">
                        {total.toLocaleString(undefined, { style: "currency", currency, maximumFractionDigits: 0 })}
                      </p>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </GlassPanel>
        </Link>

        <GlassPanel className="p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-orange-500/10">
              <Target className="h-5 w-5 text-orange-500" />
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Conversion Rate</p>
              <p className="text-2xl font-bold" data-testid="text-conversion-rate">--</p>
            </div>
          </div>
        </GlassPanel>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <GlassPanel className="p-4">
          <h3 className="text-lg font-semibold mb-4">Recent Contacts</h3>
          {contactsQuery.isLoading ? (
            <div className="space-y-3">
              {[...Array(3)].map((_, i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
          ) : contacts.length === 0 ? (
            <EmptyState title="No contacts yet" description="Add your first contact to get started." />
          ) : (
            <div className="space-y-3">
              {contacts.slice(0, 5).map((contact: any) => (
                <div
                  key={contact.id}
                  className="flex items-center gap-3 p-2 rounded-lg hover-elevate cursor-pointer"
                  onClick={() => onViewContact(contact.id)}
                  data-testid={`overview-contact-${contact.id}`}
                >
                  <div className="h-8 w-8 rounded-full bg-primary/10 flex items-center justify-center text-sm font-medium">
                    {contact.name?.charAt(0).toUpperCase() || "?"}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate">{contact.name}</p>
                    <p className="text-xs text-muted-foreground truncate">{contact.email || contact.phone || "No contact info"}</p>
                  </div>
                  {contact.type && (
                    <Badge variant="secondary" className="text-xs">{contact.type}</Badge>
                  )}
                </div>
              ))}
            </div>
          )}
        </GlassPanel>

        <GlassPanel className="p-4">
          <h3 className="text-lg font-semibold mb-4">Recent Deals</h3>
          {dealsQuery.isLoading ? (
            <div className="space-y-3">
              {[...Array(3)].map((_, i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
          ) : deals.length === 0 ? (
            <EmptyState title="No deals yet" description="Create your first deal to track opportunities." />
          ) : (
            <div className="space-y-3">
              {deals.slice(0, 5).map((deal) => (
                <Link key={deal.id} href={`/deals?dealId=${encodeURIComponent(deal.id)}`}>
                  <div className="flex items-center gap-3 p-2 rounded-lg hover-elevate cursor-pointer" data-testid={`overview-deal-${deal.id}`}>
                    <div className="h-8 w-8 rounded-full bg-green-500/10 flex items-center justify-center">
                      <Briefcase className="h-4 w-4 text-green-500" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">{deal.title}</p>
                      <p className="text-xs text-muted-foreground truncate">{deal.company || "No company"}</p>
                    </div>
                    <p className="text-sm font-semibold text-green-600">
                      {typeof deal.value === "number" ? deal.value.toLocaleString(undefined, { style: "currency", currency: "USD" }) : "--"}
                    </p>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </GlassPanel>
      </div>
    </div>
  );
}

function ContactsTab({ searchQuery, openContactId, setOpenContactId }: {
  searchQuery: string;
  openContactId?: string | null;
  setOpenContactId: (id: string | null) => void;
}) {
  const isMobile = useIsMobile();
  const { setAction } = useAppBarAction();
  const [page, setPage] = useState(1);
  const [pageSize] = useState(50);
  const [accountIdFilter, setAccountIdFilter] = useState<string | null>(null);
  const [isEditorOpen, setIsEditorOpen] = useState(false);
  const [editorMode, setEditorMode] = useState<"create" | "edit">("create");
  const [editorContact, setEditorContact] = useState<CRMContact | null>(null);

  useEffect(() => {
    setPage(1);
  }, [searchQuery, accountIdFilter]);

  const { data, isLoading, isError, error, refetch } = useQuery<ContactsResponse>({
    queryKey: [apiV1("/crm/contacts"), page, pageSize, searchQuery, accountIdFilter],
    queryFn: async () => {
      const params: Record<string, string | number> = {
        page,
        limit: pageSize,
      };
      if (searchQuery) params.search = searchQuery;
      if (accountIdFilter) params.account_id = accountIdFilter;
      return fetchJson<ContactsResponse>(apiV1("/crm/contacts"), params);
    },
    staleTime: accountIdFilter ? 0 : undefined,
  });

  const contacts = data?.contacts || [];
  const pagination = data?.pagination;
  const totalItems = pagination?.total_items ?? contacts.length;
  const totalPages = pagination?.total_pages ?? 1;
  const currentPage = pagination?.current_page ?? page;

  const startItem = totalItems === 0 ? 0 : (currentPage - 1) * pageSize + 1;
  const endItem = Math.min(currentPage * pageSize, totalItems);

  const handleContactClick = (contact: any) => {
    setOpenContactId(contact.id);
  };

  const handleAddSuccess = () => {
    refetch();
    queryClient.invalidateQueries({ queryKey: [apiV1("/crm/contacts")] });
  };

  const openCreate = useCallback(() => {
    setEditorMode("create");
    setEditorContact(null);
    setIsEditorOpen(true);
  }, []);

  const openEdit = (contactToEdit: CRMContact) => {
    setEditorMode("edit");
    setEditorContact(contactToEdit);
    setIsEditorOpen(true);
  };

  useEffect(() => {
    if (isMobile) {
      setAction({ onClick: openCreate, label: "Add contact" });
      return () => setAction(null);
    }
  }, [isMobile, setAction, openCreate]);

  const handleEditFromDetails = (contact: ContactDetailsContact) => {
    setOpenContactId(null);
    openEdit(contact as CRMContact);
  };

  const accountsForFilter = useQuery<AccountsResponse>({
    queryKey: [apiV1("/crm/customers/"), "list-for-filter"],
    queryFn: () => fetchJson<AccountsResponse>(apiV1("/crm/customers/"), { page: 1, limit: 200 }),
  });
  const accountOptions = accountsForFilter.data?.customers ?? [];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-3 flex-wrap">
          <Select
            value={accountIdFilter ?? "all"}
            onValueChange={(v) => {
              const id = v === "all" ? null : v;
              setAccountIdFilter(id);
            }}
          >
            <SelectTrigger className="w-[200px] h-8" data-testid="select-account-filter">
              <SelectValue placeholder="All accounts" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All accounts</SelectItem>
              {accountOptions.map((a: CRMAccount) => (
                <SelectItem key={a.id} value={a.id}>{a.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        {!isMobile && (
          <Button onClick={openCreate} data-testid="button-add-contact">
            <Plus className="h-4 w-4 mr-2" />
            Add Contact
          </Button>
        )}
      </div>

      <div className={isMobile ? "-mx-4" : ""}>
        <GlassPanel className={cn("w-full min-w-0 overflow-hidden", isMobile ? "py-4 px-0 rounded-none" : "p-4")}>
        {isLoading ? (
          <div className="space-y-3">
            {[...Array(5)].map((_, i) => (
              <Skeleton key={i} className="h-16 w-full" />
            ))}
          </div>
        ) : isError ? (
          <ErrorDisplay error={error as Error} endpoint="api/v1/crm/contacts" />
        ) : contacts.length === 0 ? (
          <EmptyState
            title="No contacts found"
            description={searchQuery ? "Try adjusting your search." : "Add your first contact to get started."}
          />
        ) : (
          <div className="space-y-2 w-full min-w-0">
            {contacts.map((contact: any) => (
              <div
                key={contact.id}
                className="flex items-center gap-3 p-3 rounded-lg border bg-card hover-elevate cursor-pointer w-full min-w-0"
                onClick={() => handleContactClick(contact)}
                data-testid={`card-contact-${contact.id}`}
              >
                <div className="h-10 w-10 shrink-0 rounded-full bg-primary/10 flex items-center justify-center text-sm font-semibold">
                  {contact.name?.charAt(0).toUpperCase() || "?"}
                </div>
                <div className="flex-1 min-w-0 overflow-hidden">
                  <p className="font-medium truncate" title={contact.name}>{contact.name}</p>
                  <p className="text-sm text-muted-foreground truncate min-h-[1.25rem]" title={contact.account_name || undefined}>
                    {contact.account_name || ""}
                  </p>
                </div>
                <div className="flex items-center gap-1 shrink-0" onClick={(e) => e.stopPropagation()}>
                  {contact.email ? (
                    <a
                      href={`mailto:${contact.email}`}
                      className="p-2.5 min-h-[44px] min-w-[44px] flex items-center justify-center rounded-md hover:bg-muted text-muted-foreground hover:text-foreground"
                      aria-label="Email"
                    >
                      <Mail className="h-4 w-4" />
                    </a>
                  ) : (
                    <span
                      className="p-2.5 min-h-[44px] min-w-[44px] flex items-center justify-center rounded-md text-muted-foreground/40 cursor-not-allowed pointer-events-none"
                      aria-label="Email unavailable"
                      title="No email"
                    >
                      <Mail className="h-4 w-4" />
                    </span>
                  )}
                  {contact.phone ? (
                    <a
                      href={`tel:${contact.phone}`}
                      className="p-2.5 min-h-[44px] min-w-[44px] flex items-center justify-center rounded-md hover:bg-muted text-muted-foreground hover:text-foreground"
                      aria-label="Call"
                    >
                      <Phone className="h-4 w-4" />
                    </a>
                  ) : (
                    <span
                      className="p-2.5 min-h-[44px] min-w-[44px] flex items-center justify-center rounded-md text-muted-foreground/40 cursor-not-allowed pointer-events-none"
                      aria-label="Phone unavailable"
                      title="No phone"
                    >
                      <Phone className="h-4 w-4" />
                    </span>
                  )}
                  {contact.phone ? (
                    <a
                      href={`https://wa.me/${(contact.phone || "").replace(/\D/g, "")}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="p-2.5 min-h-[44px] min-w-[44px] flex items-center justify-center rounded-md hover:bg-muted text-muted-foreground hover:text-foreground"
                      aria-label="WhatsApp"
                    >
                      <SiWhatsapp className="h-4 w-4 text-[#25D366]" />
                    </a>
                  ) : (
                    <span
                      className="p-2.5 min-h-[44px] min-w-[44px] flex items-center justify-center rounded-md text-[#25D366]/40 cursor-not-allowed pointer-events-none"
                      aria-label="WhatsApp unavailable"
                      title="No phone for WhatsApp"
                    >
                      <SiWhatsapp className="h-4 w-4" />
                    </span>
                  )}
                </div>
                {contact.company && (
                  <p className="text-sm text-muted-foreground hidden md:block shrink-0">{contact.company}</p>
                )}
                {contact.type && (
                  <Badge variant="secondary" className="shrink-0">{contact.type}</Badge>
                )}
              </div>
            ))}
          </div>
        )}
      </GlassPanel>
      </div>

      {(totalItems > 0 || totalPages > 1) && (
        <div className="flex items-center justify-between flex-wrap gap-2">
          <p className="text-sm text-muted-foreground" data-testid="text-contacts-count">
            {totalItems === 0
              ? "No contacts"
              : `Showing ${startItem}-${endItem} of ${totalItems} contact${totalItems !== 1 ? "s" : ""}`}
          </p>
          {totalPages > 1 && (
            <div className="flex items-center gap-2">
              <p className="text-sm text-muted-foreground hidden sm:block">
                Page {currentPage} of {totalPages}
              </p>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={currentPage <= 1 || isLoading}
                data-testid="button-prev-page"
              >
                <ChevronLeft className="h-4 w-4 mr-1" />
                Previous
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={currentPage >= totalPages || isLoading}
                data-testid="button-next-page"
              >
                Next
                <ChevronRight className="h-4 w-4 ml-1" />
              </Button>
            </div>
          )}
        </div>
      )}

      <ContactDetailsModal
        open={Boolean(openContactId)}
        onOpenChange={(open) => !open && setOpenContactId(null)}
        contactId={openContactId ?? null}
        onEdit={handleEditFromDetails}
      />
      <ContactEditorModal
        open={isEditorOpen}
        mode={editorMode}
        contact={editorContact}
        onClose={() => setIsEditorOpen(false)}
        onSaved={() => handleAddSuccess()}
      />
    </div>
  );
}

function AccountsTab({ searchQuery, openAccountId, setOpenAccountId }: {
  searchQuery: string;
  openAccountId?: string | null;
  setOpenAccountId: (id: string | null) => void;
}) {
  const [page, setPage] = useState(1);
  const [pageSize] = useState(50);
  const [isEditorOpen, setIsEditorOpen] = useState(false);

  useEffect(() => {
    setPage(1);
  }, [searchQuery]);

  const { data, isLoading, isError, error, refetch } = useQuery<AccountsResponse>({
    queryKey: [apiV1("/crm/customers/"), page, pageSize, searchQuery],
    queryFn: async () => {
      const params: Record<string, string | number> = {
        page,
        limit: pageSize,
      };
      if (searchQuery) params.search = searchQuery;
      return fetchJson<AccountsResponse>(apiV1("/crm/customers/"), params);
    },
  });

  const customers = data?.customers || [];
  const pagination = data?.pagination;
  const totalItems = pagination?.total_items ?? customers.length;
  const totalPages = pagination?.total_pages ?? 1;
  const currentPage = pagination?.current_page ?? page;
  const startItem = totalItems === 0 ? 0 : (currentPage - 1) * pageSize + 1;
  const endItem = Math.min(currentPage * pageSize, totalItems);

  const handleAccountClick = (account: CRMAccount) => {
    setOpenAccountId(account.id);
  };

  const handleAddSuccess = () => {
    refetch();
    queryClient.invalidateQueries({ queryKey: [apiV1("/crm/customers/")] });
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <p className="text-sm text-muted-foreground" data-testid="text-accounts-count">
          {totalItems === 0
            ? "No accounts"
            : `Showing ${startItem}-${endItem} of ${totalItems} account${totalItems !== 1 ? "s" : ""}`}
        </p>
        <Button data-testid="button-add-account" onClick={() => setIsEditorOpen(true)}>
          <Plus className="h-4 w-4 mr-2" />
          Add Account
        </Button>
      </div>

      <GlassPanel className="p-4">
        {isLoading ? (
          <div className="space-y-3">
            {[...Array(5)].map((_, i) => (
              <Skeleton key={i} className="h-16 w-full" />
            ))}
          </div>
        ) : isError ? (
          <ErrorDisplay error={error as Error} endpoint="api/v1/crm/customers" />
        ) : customers.length === 0 ? (
          <EmptyState
            title="No accounts found"
            description={searchQuery ? "Try adjusting your search." : "Add your first account (customer) to get started."}
          />
        ) : (
          <div className="space-y-2">
            {customers.map((account: CRMAccount) => (
              <div
                key={account.id}
                className="flex items-center gap-4 p-3 rounded-lg border bg-card hover-elevate cursor-pointer"
                onClick={() => handleAccountClick(account)}
                data-testid={`card-account-${account.id}`}
              >
                <div className="h-10 w-10 rounded-lg bg-primary/10 flex items-center justify-center">
                  <Building2 className="h-5 w-5 text-primary" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="font-medium truncate">{account.name}</p>
                  <p className="text-sm text-muted-foreground truncate">
                    {account.email || account.phone || (account.legal_name && account.legal_name !== account.name ? account.legal_name : "No contact info")}
                  </p>
                </div>
                {account.type && (
                  <Badge variant="secondary" className="capitalize">{account.type}</Badge>
                )}
              </div>
            ))}
          </div>
        )}
      </GlassPanel>

      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-muted-foreground">
            Page {currentPage} of {totalPages}
          </p>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={currentPage <= 1 || isLoading}
              data-testid="button-accounts-prev"
            >
              <ChevronLeft className="h-4 w-4 mr-1" />
              Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={currentPage >= totalPages || isLoading}
              data-testid="button-accounts-next"
            >
              Next
              <ChevronRight className="h-4 w-4 ml-1" />
            </Button>
          </div>
        </div>
      )}

      <AccountDetailsModal
        open={Boolean(openAccountId)}
        onOpenChange={(open) => !open && setOpenAccountId(null)}
        accountId={openAccountId ?? null}
      />
      <AccountEditorModal
        open={isEditorOpen}
        onClose={() => setIsEditorOpen(false)}
        onSaved={handleAddSuccess}
      />
    </div>
  );
}

interface SectionProps {
  onBack: () => void;
}

interface KnowledgeItem {
  id: string;
  title: string;
  description?: string;
  type: string;
  content?: string;
  data?: Record<string, unknown>;
  visibility: "public" | "private" | "internal";
  created?: string;
  updated?: string;
}

interface Tag {
  id: string;
  name: string;
  color?: string;
  description?: string;
  usage_count?: number;
}

interface ContactType {
  id: string;
  name: string;
  description?: string;
  color?: string;
  is_default?: boolean;
  default_agent_id?: string | null;
}

function KnowledgeBaseSection({ onBack }: SectionProps) {
  const { toast } = useToast();
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedItemId, setSelectedItemId] = useState<string | null>(null);
  const [editedItem, setEditedItem] = useState<KnowledgeItem | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [dataJsonText, setDataJsonText] = useState("{}");
  const [dataJsonError, setDataJsonError] = useState<string | null>(null);

  const knowledgeQuery = useQuery<{ items: KnowledgeItem[] }>({
    queryKey: [apiV1("/crm/knowledge/")],
    queryFn: async () => {
      try {
        return await fetchJson<{ items: KnowledgeItem[] }>(apiV1("/crm/knowledge/"));
      } catch {
        return { items: [] };
      }
    },
    retry: false,
  });

  const items = (knowledgeQuery.data?.items ?? []).filter(item => item.type !== "service-template");

  const filteredItems = searchQuery.trim().length > 0
    ? items.filter(item =>
        item.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
        (item.description?.toLowerCase() || "").includes(searchQuery.toLowerCase())
      )
    : items;

  const selectedItem = filteredItems.find(item => item.id === selectedItemId);

  useEffect(() => {
    if (selectedItem) {
      setIsCreating(false);
      setEditedItem({ ...selectedItem });
      setDataJsonText(selectedItem.data ? JSON.stringify(selectedItem.data, null, 2) : "{}");
      setDataJsonError(null);
    } else if (!isCreating) {
      setEditedItem(null);
      setDataJsonText("{}");
      setDataJsonError(null);
    }
  }, [selectedItem, isCreating]);

  const handleCreateNew = () => {
    setSelectedItemId(null);
    setIsCreating(true);
    setEditedItem({
      id: "",
      title: "",
      description: "",
      type: "article",
      content: "",
      data: {},
      visibility: "private",
    });
    setDataJsonText("{}");
    setDataJsonError(null);
  };

  const handleSave = async () => {
    if (!editedItem) return;
    
    let parsedData: Record<string, unknown> = {};
    try {
      parsedData = JSON.parse(dataJsonText);
      setDataJsonError(null);
    } catch {
      setDataJsonError("Invalid JSON format");
      toast({ title: "Error", description: "Please fix the JSON data format before saving.", variant: "destructive" });
      return;
    }
    
    setIsSaving(true);
    try {
      const itemData = {
        title: editedItem.title,
        description: editedItem.description,
        type: editedItem.type,
        content: editedItem.content,
        data: parsedData,
        visibility: editedItem.visibility,
      };
      if (isCreating) {
        const response = await apiRequest("POST", apiV1("/crm/knowledge/"), { data: itemData });
        const result = await response.json();
        toast({ title: "Created", description: "Knowledge item created successfully." });
        setIsCreating(false);
        if (result?.id) {
          setSelectedItemId(result.id);
        }
      } else {
        await apiRequest("PATCH", apiV1(`/crm/knowledge/${editedItem.id}/`), { data: itemData });
        toast({ title: "Saved", description: "Knowledge item updated successfully." });
      }
      queryClient.invalidateQueries({ queryKey: [apiV1("/crm/knowledge/")] });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to save";
      if (message.includes("404") || message.includes("Not Found")) {
        toast({ 
          title: "Feature unavailable", 
          description: "Knowledge base is not yet available on this server.",
        });
      } else {
        toast({ title: "Error", description: message, variant: "destructive" });
      }
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!editedItem?.id) return;
    try {
      await apiRequest("DELETE", apiV1(`/crm/knowledge/${editedItem.id}/`), {});
      toast({ title: "Deleted", description: "Knowledge item deleted successfully." });
      setSelectedItemId(null);
      setEditedItem(null);
      queryClient.invalidateQueries({ queryKey: [apiV1("/crm/knowledge/")] });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to delete";
      if (message.includes("404") || message.includes("Not Found")) {
        toast({ 
          title: "Feature unavailable", 
          description: "Knowledge base is not yet available on this server.",
        });
      } else {
        toast({ title: "Error", description: message, variant: "destructive" });
      }
    }
  };

  const knowledgeTypes = [
    { value: "article", label: "Article" },
    { value: "faq", label: "FAQ" },
    { value: "documentation", label: "Documentation" },
    { value: "guide", label: "Guide" },
    { value: "policy", label: "Policy" },
  ];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="icon" onClick={onBack} data-testid="button-back-kb">
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <h2 className="text-lg font-semibold">Knowledge Base</h2>
        </div>
        <Button onClick={handleCreateNew} data-testid="button-new-kb">
          <Plus className="h-4 w-4 mr-2" />
          New Article
        </Button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <GlassPanel className="p-4 lg:col-span-1">
          <div className="mb-4">
            <Input
              placeholder="Search knowledge base..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full"
              data-testid="input-search-kb"
            />
          </div>

          {knowledgeQuery.isLoading ? (
            <div className="space-y-2">
              {[1, 2, 3].map(i => <Skeleton key={i} className="h-16 w-full" />)}
            </div>
          ) : filteredItems.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              <BookOpen className="h-8 w-8 mx-auto mb-2 opacity-50" />
              <p className="text-sm">No articles found</p>
            </div>
          ) : (
            <ScrollArea className="h-[400px]">
              <div className="space-y-2">
                {filteredItems.map(item => (
                  <div
                    key={item.id}
                    className={`p-3 rounded-lg border cursor-pointer hover-elevate ${
                      selectedItemId === item.id ? "bg-primary/10 border-primary" : "bg-card"
                    }`}
                    onClick={() => setSelectedItemId(item.id)}
                    data-testid={`item-kb-${item.id}`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex-1 min-w-0">
                        <h4 className="font-medium text-sm truncate">{item.title}</h4>
                        <p className="text-xs text-muted-foreground truncate">{item.description || "No description"}</p>
                      </div>
                      <Badge variant="secondary" className="text-xs shrink-0">{item.type}</Badge>
                    </div>
                  </div>
                ))}
              </div>
            </ScrollArea>
          )}
        </GlassPanel>

        <GlassPanel className="p-4 lg:col-span-2">
          {!editedItem ? (
            <div className="h-full flex items-center justify-center text-muted-foreground">
              <div className="text-center">
                <FileText className="h-12 w-12 mx-auto mb-4 opacity-30" />
                <p>Select an article or create a new one</p>
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex-1 space-y-4">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <Label>Title</Label>
                      <Input
                        value={editedItem.title}
                        onChange={(e) => setEditedItem({ ...editedItem, title: e.target.value })}
                        placeholder="Article title"
                        data-testid="input-kb-title"
                      />
                    </div>
                    <div>
                      <Label>Type</Label>
                      <Select
                        value={editedItem.type}
                        onValueChange={(value) => setEditedItem({ ...editedItem, type: value })}
                      >
                        <SelectTrigger data-testid="select-kb-type">
                          <SelectValue placeholder="Select type" />
                        </SelectTrigger>
                        <SelectContent>
                          {knowledgeTypes.map(t => (
                            <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  </div>

                  <div>
                    <Label>Description</Label>
                    <Input
                      value={editedItem.description ?? ""}
                      onChange={(e) => setEditedItem({ ...editedItem, description: e.target.value })}
                      placeholder="Brief description"
                      data-testid="input-kb-description"
                    />
                  </div>

                  <div>
                    <Label>Content</Label>
                    <Textarea
                      value={editedItem.content ?? ""}
                      onChange={(e) => setEditedItem({ ...editedItem, content: e.target.value })}
                      placeholder="Write your article content..."
                      className="min-h-[200px]"
                      data-testid="textarea-kb-content"
                    />
                  </div>

                  <div>
                    <Label>Data (JSON)</Label>
                    <Textarea
                      value={dataJsonText}
                      onChange={(e) => {
                        setDataJsonText(e.target.value);
                        try {
                          JSON.parse(e.target.value);
                          setDataJsonError(null);
                        } catch {
                          setDataJsonError("Invalid JSON format");
                        }
                      }}
                      placeholder='{"key": "value"}'
                      className={`min-h-[120px] font-mono text-sm ${dataJsonError ? "border-destructive" : ""}`}
                      data-testid="textarea-kb-data"
                    />
                    {dataJsonError ? (
                      <p className="text-xs text-destructive mt-1">{dataJsonError}</p>
                    ) : (
                      <p className="text-xs text-muted-foreground mt-1">Additional structured data in JSON format</p>
                    )}
                  </div>

                  <div className="flex items-center gap-4">
                    <Label>Visibility</Label>
                    <Select
                      value={editedItem.visibility}
                      onValueChange={(value: "public" | "private" | "internal") => 
                        setEditedItem({ ...editedItem, visibility: value })
                      }
                    >
                      <SelectTrigger className="w-40" data-testid="select-kb-visibility">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="private">Private</SelectItem>
                        <SelectItem value="internal">Internal</SelectItem>
                        <SelectItem value="public">Public</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>
              </div>

              <div className="flex justify-between pt-4 border-t">
                <div>
                  {!isCreating && editedItem.id && (
                    <Button variant="destructive" onClick={handleDelete} data-testid="button-delete-kb">
                      <Trash2 className="h-4 w-4 mr-2" />
                      Delete
                    </Button>
                  )}
                </div>
                <div className="flex gap-2">
                  {isCreating && (
                    <Button variant="outline" onClick={() => { setIsCreating(false); setEditedItem(null); }}>
                      Cancel
                    </Button>
                  )}
                  <Button onClick={handleSave} disabled={isSaving || !editedItem.title.trim() || !!dataJsonError} data-testid="button-save-kb">
                    <Save className="h-4 w-4 mr-2" />
                    {isSaving ? "Saving..." : (isCreating ? "Create" : "Save")}
                  </Button>
                </div>
              </div>
            </div>
          )}
        </GlassPanel>
      </div>
    </div>
  );
}

function TagsSection({ onBack }: SectionProps) {
  const { toast } = useToast();
  const [searchQuery, setSearchQuery] = useState("");
  const [editingTag, setEditingTag] = useState<Tag | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  const tagsQuery = useQuery<{ tags: Tag[] }>({
    queryKey: [apiV1("/crmtags/")],
    queryFn: () => fetchJson<{ tags: Tag[] }>(apiV1("/crmtags/")),
  });

  const tags = tagsQuery.data?.tags ?? [];

  const filteredTags = searchQuery.trim().length > 0
    ? tags.filter(tag =>
        tag.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        (tag.description?.toLowerCase() || "").includes(searchQuery.toLowerCase())
      )
    : tags;

  const handleCreateNew = () => {
    setIsCreating(true);
    setEditingTag({
      id: "",
      name: "",
      color: "#3b82f6",
      description: "",
    });
  };

  const handleSave = async () => {
    if (!editingTag) return;
    setIsSaving(true);
    try {
      const tagData = {
        name: editingTag.name,
        color: editingTag.color,
        description: editingTag.description,
      };
      if (isCreating) {
        await apiRequest("POST", apiV1("/crmtags/"), { data: tagData });
        toast({ title: "Created", description: "Tag created successfully." });
      } else {
        await apiRequest("PATCH", apiV1(`/crmtags/${editingTag.id}/`), { data: tagData });
        toast({ title: "Saved", description: "Tag updated successfully." });
      }
      setEditingTag(null);
      setIsCreating(false);
      queryClient.invalidateQueries({ queryKey: [apiV1("/crmtags/")] });
    } catch (error) {
      toast({ title: "Error", description: (error as Error).message, variant: "destructive" });
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async (tag: Tag) => {
    try {
      await apiRequest("DELETE", apiV1(`/crmtags/${tag.id}/`), {});
      toast({ title: "Deleted", description: "Tag deleted successfully." });
      queryClient.invalidateQueries({ queryKey: [apiV1("/crmtags/")] });
    } catch (error) {
      toast({ title: "Error", description: (error as Error).message, variant: "destructive" });
    }
  };

  const colorOptions = [
    { value: "#3b82f6", label: "Blue" },
    { value: "#10b981", label: "Green" },
    { value: "#f59e0b", label: "Orange" },
    { value: "#ef4444", label: "Red" },
    { value: "#8b5cf6", label: "Purple" },
    { value: "#ec4899", label: "Pink" },
    { value: "#6b7280", label: "Gray" },
  ];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="icon" onClick={onBack} data-testid="button-back-tags">
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <h2 className="text-lg font-semibold">Tags & Labels</h2>
        </div>
        <Button onClick={handleCreateNew} data-testid="button-new-tag">
          <Plus className="h-4 w-4 mr-2" />
          New Tag
        </Button>
      </div>

      <GlassPanel className="p-4">
        <div className="mb-4">
          <Input
            placeholder="Search tags..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="max-w-sm"
            data-testid="input-search-tags"
          />
        </div>

        {tagsQuery.isLoading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {[1, 2, 3, 4, 5, 6].map(i => <Skeleton key={i} className="h-20 w-full" />)}
          </div>
        ) : filteredTags.length === 0 ? (
          <div className="text-center py-12 text-muted-foreground">
            <TagsIcon className="h-12 w-12 mx-auto mb-4 opacity-30" />
            <p>No tags found</p>
            <p className="text-sm mt-1">Create your first tag to organize contacts</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {filteredTags.map(tag => (
              <div
                key={tag.id}
                className="p-4 rounded-lg border bg-card hover-elevate"
                data-testid={`card-tag-${tag.id}`}
              >
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <div
                      className="w-4 h-4 rounded-full"
                      style={{ backgroundColor: tag.color ?? "#6b7280" }}
                    />
                    <div>
                      <h4 className="font-medium">{tag.name}</h4>
                      {tag.description && (
                        <p className="text-xs text-muted-foreground mt-0.5">{tag.description}</p>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-1">
                    {tag.usage_count !== undefined && (
                      <Badge variant="secondary" className="text-xs">{tag.usage_count}</Badge>
                    )}
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8"
                      onClick={() => { setEditingTag(tag); setIsCreating(false); }}
                      data-testid={`button-edit-tag-${tag.id}`}
                    >
                      <Pencil className="h-3.5 w-3.5" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8 text-destructive"
                      onClick={() => handleDelete(tag)}
                      data-testid={`button-delete-tag-${tag.id}`}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </GlassPanel>

      <Dialog open={!!editingTag} onOpenChange={(open) => { if (!open) { setEditingTag(null); setIsCreating(false); } }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{isCreating ? "Create Tag" : "Edit Tag"}</DialogTitle>
            <DialogDescription>
              {isCreating ? "Create a new tag for organizing contacts" : "Update tag details"}
            </DialogDescription>
          </DialogHeader>
          {editingTag && (
            <div className="space-y-4 py-4">
              <div>
                <Label>Name</Label>
                <Input
                  value={editingTag.name}
                  onChange={(e) => setEditingTag({ ...editingTag, name: e.target.value })}
                  placeholder="Tag name"
                  data-testid="input-tag-name"
                />
              </div>
              <div>
                <Label>Description</Label>
                <Textarea
                  value={editingTag.description ?? ""}
                  onChange={(e) => setEditingTag({ ...editingTag, description: e.target.value })}
                  placeholder="Optional description"
                  rows={5}
                  data-testid="input-tag-description"
                />
              </div>
              <div>
                <Label>Color</Label>
                <div className="flex gap-2 mt-2">
                  {colorOptions.map(color => (
                    <button
                      key={color.value}
                      type="button"
                      className={`w-8 h-8 rounded-full border-2 ${
                        editingTag.color === color.value ? "border-primary" : "border-transparent"
                      }`}
                      style={{ backgroundColor: color.value }}
                      onClick={() => setEditingTag({ ...editingTag, color: color.value })}
                      title={color.label}
                      data-testid={`button-color-${color.label.toLowerCase()}`}
                    />
                  ))}
                </div>
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => { setEditingTag(null); setIsCreating(false); }}>
              Cancel
            </Button>
            <Button onClick={handleSave} disabled={isSaving || !editingTag?.name.trim()} data-testid="button-save-tag">
              {isSaving ? "Saving..." : (isCreating ? "Create" : "Save")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function ContactTypesSection({ onBack }: SectionProps) {
  const { toast } = useToast();
  const [searchQuery, setSearchQuery] = useState("");
  const [editingType, setEditingType] = useState<ContactType | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  const typesQuery = useQuery<ContactTypesListResponse>({
    queryKey: [apiV1("/crm/contact_types/")],
    queryFn: () => fetchJson<ContactTypesListResponse>(apiV1("/crm/contact_types/"), { page_size: 200 }),
  });

  const agentsQuery = useQuery<AgentsListResponse>({
    queryKey: [apiV1("/settings/agents/")],
    queryFn: () => fetchJson<AgentsListResponse>(apiV1("/settings/agents/"), { page_size: 200 }),
  });

  const types = extractContactTypes(typesQuery.data);
  const allAgents = extractAgents(agentsQuery.data as any);
  const agents = allAgents.filter((a) => a.enabled);

  const getAgentName = (agentId: string | null | undefined): string | null => {
    if (!agentId) return null;
    const agent = allAgents.find((a) => a.id === agentId);
    return agent?.name || agentId.slice(0, 8) + "...";
  };

  const filteredTypes = searchQuery.trim().length > 0
    ? types.filter(t =>
        t.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        (t.description?.toLowerCase() || "").includes(searchQuery.toLowerCase())
      )
    : types;

  const handleCreateNew = () => {
    setIsCreating(true);
    setEditingType({
      id: "",
      name: "",
      description: "",
      color: "#3b82f6",
      default_agent_id: null,
    });
  };

  const handleSave = async () => {
    if (!editingType) return;
    setIsSaving(true);
    try {
      const payload = {
        name: editingType.name,
        description: editingType.description,
        color: editingType.color,
        // Important: use nullish coalescing (not ||) so we never
        // accidentally coerce a legitimate value to null.
        default_agent_id: editingType.default_agent_id ?? null,
      };
      if (isCreating) {
        await apiRequest("POST", apiV1("/crm/contact_types/"), { data: payload });
        toast({ title: "Created", description: "Contact type created successfully." });
      } else {
        await apiRequest("PATCH", apiV1(`/crm/contact_types/${editingType.id}/`), { data: payload });
        toast({ title: "Saved", description: "Contact type updated successfully." });
      }
      setEditingType(null);
      setIsCreating(false);
      queryClient.invalidateQueries({ queryKey: [apiV1("/crm/contact_types/")] });
    } catch (error) {
      toast({ title: "Error", description: (error as Error).message, variant: "destructive" });
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async (type: ContactType) => {
    if (type.is_default) {
      toast({ title: "Cannot delete", description: "Default contact types cannot be deleted.", variant: "destructive" });
      return;
    }
    try {
      await apiRequest("DELETE", apiV1(`/crm/contact_types/${type.id}/`), {});
      toast({ title: "Deleted", description: "Contact type deleted successfully." });
      queryClient.invalidateQueries({ queryKey: [apiV1("/crm/contact_types/")] });
    } catch (error) {
      toast({ title: "Error", description: (error as Error).message, variant: "destructive" });
    }
  };

  const colorOptions = [
    { value: "#3b82f6", label: "Blue" },
    { value: "#10b981", label: "Green" },
    { value: "#f59e0b", label: "Orange" },
    { value: "#ef4444", label: "Red" },
    { value: "#8b5cf6", label: "Purple" },
    { value: "#ec4899", label: "Pink" },
    { value: "#6b7280", label: "Gray" },
  ];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="icon" onClick={onBack} data-testid="button-back-ctypes">
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <h2 className="text-lg font-semibold">Contact Types</h2>
        </div>
        <Button onClick={handleCreateNew} data-testid="button-new-ctype">
          <Plus className="h-4 w-4 mr-2" />
          New Type
        </Button>
      </div>

      <GlassPanel className="p-4">
        <div className="mb-4">
          <Input
            placeholder="Search contact types..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="max-w-sm"
            data-testid="input-search-ctypes"
          />
        </div>

        {typesQuery.isLoading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {[1, 2, 3, 4].map(i => <Skeleton key={i} className="h-24 w-full" />)}
          </div>
        ) : filteredTypes.length === 0 ? (
          <div className="text-center py-12 text-muted-foreground">
            <UserCog className="h-12 w-12 mx-auto mb-4 opacity-30" />
            <p>No contact types found</p>
            <p className="text-sm mt-1">Create types to categorize your contacts</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {filteredTypes.map(type => (
              <div
                key={type.id}
                className="p-4 rounded-lg border bg-card hover-elevate"
                data-testid={`card-ctype-${type.id}`}
              >
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <div
                      className="w-10 h-10 rounded-lg flex items-center justify-center"
                      style={{ backgroundColor: `${type.color ?? "#6b7280"}20` }}
                    >
                      <UserCog className="h-5 w-5" style={{ color: type.color ?? "#6b7280" }} />
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <h4 className="font-medium">{type.name}</h4>
                        {type.is_default && (
                          <Badge variant="outline" className="text-xs">Default</Badge>
                        )}
                      </div>
                      {type.description && (
                        <p className="text-xs text-muted-foreground mt-0.5">{type.description}</p>
                      )}
                      {type.default_agent_id && (
                        <p className="text-xs text-muted-foreground mt-1 flex items-center gap-1">
                          <Bot className="h-3 w-3" />
                          {getAgentName(type.default_agent_id)}
                        </p>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-1">
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8"
                      onClick={() => { setEditingType(type); setIsCreating(false); }}
                      data-testid={`button-edit-ctype-${type.id}`}
                    >
                      <Pencil className="h-3.5 w-3.5" />
                    </Button>
                    {!type.is_default && (
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 text-destructive"
                        onClick={() => handleDelete(type)}
                        data-testid={`button-delete-ctype-${type.id}`}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </GlassPanel>

      <Dialog open={!!editingType} onOpenChange={(open) => { if (!open) { setEditingType(null); setIsCreating(false); } }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{isCreating ? "Create Contact Type" : "Edit Contact Type"}</DialogTitle>
            <DialogDescription>
              {isCreating ? "Create a new contact classification type" : "Update contact type details"}
            </DialogDescription>
          </DialogHeader>
          {editingType && (
            <div className="space-y-4 py-4">
              <div>
                <Label>Name</Label>
                <Input
                  value={editingType.name}
                  onChange={(e) => setEditingType({ ...editingType, name: e.target.value })}
                  placeholder="Type name (e.g., Lead, Customer, Partner)"
                  data-testid="input-ctype-name"
                />
              </div>
              <div>
                <Label>Description</Label>
                <Input
                  value={editingType.description ?? ""}
                  onChange={(e) => setEditingType({ ...editingType, description: e.target.value })}
                  placeholder="Optional description"
                  data-testid="input-ctype-description"
                />
              </div>
              <div>
                <Label>Color</Label>
                <div className="flex gap-2 mt-2">
                  {colorOptions.map(color => (
                    <button
                      key={color.value}
                      type="button"
                      className={`w-8 h-8 rounded-full border-2 ${
                        editingType.color === color.value ? "border-primary" : "border-transparent"
                      }`}
                      style={{ backgroundColor: color.value }}
                      onClick={() => setEditingType({ ...editingType, color: color.value })}
                      title={color.label}
                      data-testid={`button-ctype-color-${color.label.toLowerCase()}`}
                    />
                  ))}
                </div>
              </div>
              <div>
                <Label>Default Agent</Label>
                <Select
                  value={editingType.default_agent_id ?? "__none__"}
                  onValueChange={(value) =>
                    setEditingType((prev) =>
                      prev
                        ? {
                            ...prev,
                            default_agent_id: value === "__none__" ? null : value,
                          }
                        : prev
                    )
                  }
                  disabled={agentsQuery.isLoading}
                >
                  <SelectTrigger className="mt-1" data-testid="select-ctype-agent">
                    <SelectValue placeholder={agentsQuery.isLoading ? "Loading agents..." : "Select an agent (optional)"} />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__none__">None</SelectItem>
                    {agents.map(agent => (
                      <SelectItem key={agent.id} value={agent.id}>
                        {agent.name || agent.id.slice(0, 8) + "..."}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground mt-1">
                  Agent to handle contacts of this type by default
                </p>
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => { setEditingType(null); setIsCreating(false); }}>
              Cancel
            </Button>
            <Button onClick={handleSave} disabled={isSaving || !editingType?.name.trim()} data-testid="button-save-ctype">
              {isSaving ? "Saving..." : (isCreating ? "Create" : "Save")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

interface ServicesSectionProps {
  onBack: () => void;
}

function ServicesSection({ onBack }: ServicesSectionProps) {
  const { toast } = useToast();
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedServiceId, setSelectedServiceId] = useState<string | null>(null);
  const [editedService, setEditedService] = useState<ServiceTemplate | null>(null);
  const [businessHours, setBusinessHours] = useState<BusinessHour[]>(DEFAULT_BUSINESS_HOURS);
  const [isSaving, setIsSaving] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [isMapFullscreen, setIsMapFullscreen] = useState(false);

  const servicesQuery = useQuery<{ items: ServiceTemplate[] }>({
    queryKey: [apiV1("/crm/knowledge/"), { type: "service-template" }],
    queryFn: async () => {
      try {
        return await fetchJson<{ items: ServiceTemplate[] }>(apiV1("/crm/knowledge/"), { type: "service-template" });
      } catch {
        return { items: [] };
      }
    },
    retry: false,
  });

  const googleMapsKeyQuery = useQuery<{ apiKey: string }>({
    queryKey: [apiV1("/integrations/google")],
    queryFn: async () => {
      try {
        const data = await fetchJson<any>(apiV1("/integrations/google"));
        const integrations = Array.isArray(data) ? data : [];
        
        if (integrations.length === 0) {
          throw new Error("Google Maps integration not configured");
        }
        
        const googleIntegration = integrations[0];
        const config = googleIntegration.config || {};
        const apiKey = config.browser_key || config.api_key;
        
        if (!apiKey) {
          throw new Error("Google Maps API key not found in integration config");
        }
        
        return { apiKey };
      } catch (error) {
        throw new Error("Failed to fetch Google Maps API key");
      }
    },
    staleTime: 1000 * 60 * 60, // Cache for 1 hour
  });

  const services = servicesQuery.data?.items ?? [];
  const googleMapsApiKey = googleMapsKeyQuery.data?.apiKey;

  const filteredServices = useMemo(() => {
    const filtered = searchQuery.trim().length > 0
      ? services.filter(s => 
          s.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
          (s.description?.toLowerCase() || "").includes(searchQuery.toLowerCase())
        )
      : services;
    return [...filtered].sort((a, b) => (a.precedence ?? 999) - (b.precedence ?? 999));
  }, [services, searchQuery]);

  const selectedService = filteredServices.find(s => s.id === selectedServiceId);

  useEffect(() => {
    if (selectedService) {
      setIsCreating(false);
      setEditedService({ ...selectedService });
      setBusinessHours(selectedService.data?.business_hours ?? DEFAULT_BUSINESS_HOURS);
    } else if (!isCreating) {
      setEditedService(null);
      setBusinessHours(DEFAULT_BUSINESS_HOURS);
    }
  }, [selectedService, isCreating]);

  const handleCreateNew = () => {
    setSelectedServiceId(null);
    setIsCreating(true);
    setEditedService({
      id: "",
      title: "",
      description: "",
      type: "service-template",
      visibility: "private",
      precedence: 1,
      data: {
        service_area: { polygon: [], center: undefined },
        business_hours: DEFAULT_BUSINESS_HOURS,
      },
    });
    setBusinessHours(DEFAULT_BUSINESS_HOURS);
  };

  const handleSave = async () => {
    if (!editedService) return;
    
    setIsSaving(true);
    try {
      const serviceData = {
        title: editedService.title,
        description: editedService.description,
        type: "service-template",
        visibility: editedService.visibility,
        precedence: editedService.precedence ?? 1,
        data: {
          service_area: editedService.data?.service_area || { polygon: [], center: undefined },
          business_hours: businessHours,
        },
      };
      if (isCreating) {
        const response = await apiRequest("POST", apiV1("/crm/knowledge/"), { data: serviceData });
        const result = await response.json();
        toast({ title: "Created", description: "Service template created successfully." });
        setIsCreating(false);
        if (result?.id) {
          setSelectedServiceId(result.id);
        }
      } else {
        await apiRequest("PATCH", apiV1(`/crm/knowledge/${editedService.id}/`), { 
          data: serviceData
        });
        toast({ title: "Saved", description: "Service template updated successfully." });
      }
      queryClient.invalidateQueries({ queryKey: [apiV1("/crm/knowledge/")] });
      servicesQuery.refetch();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to save";
      if (message.includes("404") || message.includes("Not Found")) {
        toast({ 
          title: "Feature unavailable", 
          description: "Service templates are not yet available on this server.",
        });
      } else {
        toast({ 
          title: "Error", 
          description: message,
          variant: "destructive" 
        });
      }
    } finally {
      setIsSaving(false);
    }
  };

  const handleSavePolygon = async () => {
    if (!editedService || isCreating) return;
    
    setIsSaving(true);
    try {
      const currentData = editedService.data || {};
      const serviceArea = currentData.service_area || { polygon: [], center: undefined };
      
      await apiRequest("PATCH", apiV1(`/crm/knowledge/${editedService.id}/`), { 
        data: {
          data: {
            service_area: {
              polygon: serviceArea.polygon || [],
              center: serviceArea.center,
            },
          },
        }
      });
      toast({ title: "Saved", description: "Service area updated successfully." });
      queryClient.invalidateQueries({ queryKey: [apiV1("/crm/knowledge/")] });
      servicesQuery.refetch();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to save";
      if (message.includes("404") || message.includes("Not Found")) {
        toast({ 
          title: "Feature unavailable", 
          description: "Service templates are not yet available on this server.",
        });
      } else {
        toast({ 
          title: "Error", 
          description: message,
          variant: "destructive" 
        });
      }
    } finally {
      setIsSaving(false);
    }
  };

  const updateBusinessHour = (index: number, field: keyof BusinessHour, value: string | boolean) => {
    setBusinessHours(prev => prev.map((h, i) => i === index ? { ...h, [field]: value } : h));
  };

  const dayLabels: Record<string, string> = {
    monday: "Mon", tuesday: "Tue", wednesday: "Wed", thursday: "Thu",
    friday: "Fri", saturday: "Sat", sunday: "Sun",
  };

  return (
    <div className="h-full flex -ml-2 -mr-4 -my-4">
      <div className="w-80 border-r border-border bg-background flex flex-col shrink-0">
        <div className="p-3 border-b border-border flex items-center gap-2">
          <Button onClick={handleCreateNew} size="sm" data-testid="button-new-service">
            <Plus className="h-4 w-4 mr-2" />
            New Service
          </Button>
        </div>
        <div className="p-3 border-b border-border">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
            <Input
              placeholder="Search services..."
              className="pl-10"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              data-testid="input-search-services"
            />
          </div>
        </div>

        <ScrollArea className="flex-1">
          {servicesQuery.isLoading ? (
            <div className="p-4 space-y-3">
              {[...Array(5)].map((_, i) => (
                <Skeleton key={i} className="h-16 w-full" />
              ))}
            </div>
          ) : filteredServices.length === 0 ? (
            <div className="p-4">
              <EmptyState
                title={searchQuery.trim() ? "No services match" : "No service templates"}
                description={searchQuery.trim() ? "Try a different search." : "Create your first service template."}
              />
            </div>
          ) : (
            filteredServices.map((service) => (
              <div
                key={service.id}
                onClick={() => setSelectedServiceId(service.id)}
                className={`p-3 border-b border-border cursor-pointer transition-colors ${
                  selectedServiceId === service.id ? "bg-accent" : "hover-elevate"
                }`}
                data-testid={`item-service-${service.id}`}
              >
                <div className="flex items-center justify-between gap-2 mb-1">
                  <h3 className="font-semibold text-sm truncate flex-1">{service.title}</h3>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    {service.visibility === "public" ? (
                      <Globe className="h-3 w-3 text-green-500" />
                    ) : (
                      <Lock className="h-3 w-3 text-muted-foreground" />
                    )}
                  </div>
                </div>
                {service.description && (
                  <p className="text-xs text-muted-foreground line-clamp-2">{service.description}</p>
                )}
              </div>
            ))
          )}
        </ScrollArea>
      </div>

      <div className="flex-1 flex flex-col bg-muted/20 overflow-hidden">
        {!selectedServiceId && !isCreating ? (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center">
              <div className="inline-flex h-16 w-16 items-center justify-center rounded-full bg-muted mb-4">
                <Wrench className="h-8 w-8 text-muted-foreground" />
              </div>
              <p className="text-sm text-muted-foreground">Select a service to configure or create a new one</p>
            </div>
          </div>
        ) : editedService ? (
            <ScrollArea className="flex-1">
              <div className="p-6 space-y-6">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 space-y-4">
                    <div>
                      <Label htmlFor="service-title">Service Name</Label>
                      <Input
                        id="service-title"
                        value={editedService.title}
                        onChange={(e) => setEditedService({ ...editedService, title: e.target.value })}
                        className="mt-1"
                        data-testid="input-service-title"
                      />
                    </div>
                    <div>
                      <Label htmlFor="service-description">Description</Label>
                      <Textarea
                        id="service-description"
                        value={editedService.description || ""}
                        onChange={(e) => setEditedService({ ...editedService, description: e.target.value })}
                        className="mt-1"
                        rows={3}
                        data-testid="input-service-description"
                      />
                    </div>
                  </div>
                  <div className="flex flex-col gap-2">
                    <Button onClick={handleSave} disabled={isSaving || !editedService.title.trim()} data-testid="button-save-service">
                      <Save className="h-4 w-4 mr-2" />
                      {isSaving ? (isCreating ? "Creating..." : "Saving...") : (isCreating ? "Create" : "Save")}
                    </Button>
                    {isCreating && (
                      <Button variant="outline" onClick={() => { setIsCreating(false); setEditedService(null); }} data-testid="button-cancel-create">
                        Cancel
                      </Button>
                    )}
                  </div>
                </div>

                <div className="flex items-center gap-6 flex-wrap">
                  <div className="flex items-center gap-4">
                    <Label>Visibility</Label>
                    <Select
                      value={editedService.visibility}
                      onValueChange={(val) => setEditedService({ ...editedService, visibility: val as "public" | "private" | "internal" })}
                    >
                      <SelectTrigger className="w-40" data-testid="select-visibility">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="public">
                          <div className="flex items-center gap-2">
                            <Globe className="h-4 w-4" />
                            Public
                          </div>
                        </SelectItem>
                        <SelectItem value="private">
                          <div className="flex items-center gap-2">
                            <Lock className="h-4 w-4" />
                            Private
                          </div>
                        </SelectItem>
                        <SelectItem value="internal">
                          <div className="flex items-center gap-2">
                            <Eye className="h-4 w-4" />
                            Internal
                          </div>
                        </SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="flex items-center gap-4">
                    <Label htmlFor="service-precedence">Precedence</Label>
                    <Input
                      id="service-precedence"
                      type="number"
                      min="1"
                      max="999"
                      value={editedService.precedence ?? 1}
                      onChange={(e) => setEditedService({ ...editedService, precedence: parseInt(e.target.value) || 1 })}
                      className="w-20"
                      data-testid="input-service-precedence"
                    />
                    <span className="text-xs text-muted-foreground">Lower values shown first in search</span>
                  </div>
                </div>

                <GlassPanel className="p-4">
                  <div className="flex items-center gap-2 mb-4">
                    <MapIcon className="h-5 w-5 text-muted-foreground" />
                    <h3 className="font-semibold">Service Area</h3>
                    <div className="flex-1" />
                    {googleMapsApiKey && (
                      <Button 
                        variant="outline" 
                        size="sm" 
                        onClick={() => setIsMapFullscreen(true)}
                        data-testid="button-fullscreen-map"
                      >
                        <Maximize2 className="h-4 w-4 mr-2" />
                        Fullscreen
                      </Button>
                    )}
                  </div>
                  
                  <div className="h-64 rounded-lg border bg-muted/50 flex items-center justify-center overflow-hidden">
                    {googleMapsApiKey ? (
                      <GoogleMapArea
                        apiKey={googleMapsApiKey}
                        polygon={editedService.data?.service_area?.polygon}
                        center={editedService.data?.service_area?.center}
                        onPolygonChange={(polygon) => {
                          setEditedService({
                            ...editedService,
                            data: {
                              ...editedService.data,
                              service_area: {
                                ...editedService.data?.service_area,
                                polygon,
                              },
                            },
                          });
                        }}
                        onSave={!isCreating ? handleSavePolygon : undefined}
                        isSaving={isSaving}
                      />
                    ) : (
                      <div className="text-center p-4">
                        <MapIcon className="h-12 w-12 text-muted-foreground mx-auto mb-2" />
                        <p className="text-sm text-muted-foreground">
                          {googleMapsKeyQuery.isLoading 
                            ? "Loading map configuration..." 
                            : googleMapsKeyQuery.isError
                            ? "Unable to load map. Please try again later."
                            : "Google Maps API key not configured. Add GOOGLE_API_KEY to your secrets."}
                        </p>
                      </div>
                    )}
                  </div>
                </GlassPanel>

                {isMapFullscreen && googleMapsApiKey && (
                  <div className="fixed inset-0 z-50 bg-background flex flex-col">
                    <div className="flex items-center justify-between p-4 border-b">
                      <div className="flex items-center gap-2">
                        <MapIcon className="h-5 w-5 text-muted-foreground" />
                        <h3 className="font-semibold">Draw Service Area</h3>
                      </div>
                      <Button 
                        variant="outline" 
                        onClick={() => setIsMapFullscreen(false)}
                        data-testid="button-exit-fullscreen"
                      >
                        <Minimize2 className="h-4 w-4 mr-2" />
                        Exit Fullscreen
                      </Button>
                    </div>
                    <div className="flex-1">
                      <GoogleMapArea
                        apiKey={googleMapsApiKey}
                        polygon={editedService.data?.service_area?.polygon}
                        center={editedService.data?.service_area?.center}
                        onPolygonChange={(polygon) => {
                          setEditedService({
                            ...editedService,
                            data: {
                              ...editedService.data,
                              service_area: {
                                ...editedService.data?.service_area,
                                polygon,
                              },
                            },
                          });
                        }}
                        onSave={!isCreating ? handleSavePolygon : undefined}
                        isSaving={isSaving}
                        isFullscreen
                      />
                    </div>
                  </div>
                )}

                <GlassPanel className="p-4">
                  <div className="flex items-center gap-2 mb-4">
                    <Clock className="h-5 w-5 text-muted-foreground" />
                    <h3 className="font-semibold">Business Hours</h3>
                  </div>
                  
                  <div className="space-y-3">
                    {businessHours.map((hour, index) => (
                      <div key={hour.day} className="flex items-center gap-3">
                        <div className="w-12">
                          <span className="text-sm font-medium">{dayLabels[hour.day]}</span>
                        </div>
                        <Switch
                          checked={hour.enabled}
                          onCheckedChange={(checked) => updateBusinessHour(index, "enabled", checked)}
                          data-testid={`switch-${hour.day}`}
                        />
                        <Input
                          type="time"
                          value={hour.open}
                          onChange={(e) => updateBusinessHour(index, "open", e.target.value)}
                          disabled={!hour.enabled}
                          className="w-28"
                          data-testid={`input-open-${hour.day}`}
                        />
                        <span className="text-muted-foreground">to</span>
                        <Input
                          type="time"
                          value={hour.close}
                          onChange={(e) => updateBusinessHour(index, "close", e.target.value)}
                          disabled={!hour.enabled}
                          className="w-28"
                          data-testid={`input-close-${hour.day}`}
                        />
                      </div>
                    ))}
                  </div>
                </GlassPanel>
              </div>
            </ScrollArea>
          ) : null}
      </div>
    </div>
  );
}

interface GoogleMapAreaProps {
  apiKey: string;
  polygon?: Array<{ lat: number; lng: number }>;
  center?: { lat: number; lng: number };
  onPolygonChange: (polygon: Array<{ lat: number; lng: number }>) => void;
  onSave?: () => Promise<void>;
  isSaving?: boolean;
  isFullscreen?: boolean;
}

const terraDrawInstances = new Map<string, boolean>();

function GoogleMapArea({ apiKey, polygon, center, onPolygonChange, onSave, isSaving, isFullscreen }: GoogleMapAreaProps) {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<any>(null);
  const terraDrawRef = useRef<any>(null);
  const [isReady, setIsReady] = useState(false);
  const [currentMode, setCurrentMode] = useState<"polygon" | "select">("polygon");
  const [hasChanges, setHasChanges] = useState(false);
  const polygonIdRef = useRef<string | null>(null);
  const instanceIdRef = useRef<string>(`td-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`);
  const cleanupRef = useRef<(() => void) | null>(null);
  const lastSavedPolygonRef = useRef<string>(JSON.stringify(polygon || []));
  const isExternalUpdateRef = useRef(false);

  const lastPolygonPropRef = useRef<string>(JSON.stringify(polygon || []));

  useEffect(() => {
    const newPolygonStr = JSON.stringify(polygon || []);
    if (!isExternalUpdateRef.current) {
      lastSavedPolygonRef.current = newPolygonStr;
      setHasChanges(false);
    }
    isExternalUpdateRef.current = false;
  }, [polygon]);

  useEffect(() => {
    if (!isReady || !terraDrawRef.current || !mapInstanceRef.current) return;
    
    const newPolygonStr = JSON.stringify(polygon || []);
    if (newPolygonStr === lastPolygonPropRef.current) return;
    
    console.log("[TerraDraw] Polygon prop changed, syncing map", { 
      old: lastPolygonPropRef.current.substring(0, 50), 
      new: newPolygonStr.substring(0, 50) 
    });
    
    lastPolygonPropRef.current = newPolygonStr;
    isExternalUpdateRef.current = true;
    
    const draw = terraDrawRef.current;
    const gMaps = (window as any).google?.maps;
    
    try {
      const allFeatures = draw.getSnapshot();
      if (allFeatures && allFeatures.length > 0) {
        const featureIds = allFeatures.map((f: any) => f.id);
        console.log("[TerraDraw] Removing existing features:", featureIds);
        draw.removeFeatures(featureIds);
      }
      polygonIdRef.current = null;
      
      if (polygon && polygon.length >= 3) {
        const coords = [...polygon.map(p => [p.lng, p.lat]), [polygon[0].lng, polygon[0].lat]];
        const featureIds = draw.addFeatures([{
          type: "Feature",
          properties: { mode: "polygon" },
          geometry: { type: "Polygon", coordinates: [coords] },
        }]);
        if (featureIds?.length > 0) {
          polygonIdRef.current = String(featureIds[0]);
          console.log("[TerraDraw] Added new polygon with id:", polygonIdRef.current);
        }
        
        if (gMaps && mapInstanceRef.current) {
          const bounds = new gMaps.LatLngBounds();
          polygon.forEach(p => bounds.extend(p));
          mapInstanceRef.current.fitBounds(bounds);
        }
        
        draw.setMode("select");
        setCurrentMode("select");
      } else {
        console.log("[TerraDraw] No polygon to draw, switching to polygon mode");
        draw.setMode("polygon");
        setCurrentMode("polygon");
      }
      
      setHasChanges(false);
      lastSavedPolygonRef.current = newPolygonStr;
    } catch (e) {
      console.warn("[TerraDraw] Failed to sync polygon:", e);
    }
  }, [polygon, isReady]);

  useEffect(() => {
    const instanceId = instanceIdRef.current;
    
    if (!apiKey || !mapContainerRef.current) return;
    if (terraDrawInstances.get(instanceId)) return;
    
    terraDrawInstances.set(instanceId, true);
    
    let isMounted = true;
    let mapInstance: any = null;
    let draw: any = null;

    const initialize = async () => {
      try {
        const google = (window as any).google;
        
        if (!google?.maps) {
          await new Promise<void>((resolve, reject) => {
            const existingScript = document.querySelector(`script[src*="maps.googleapis.com"]`);
            if (existingScript) {
              const check = setInterval(() => {
                if ((window as any).google?.maps) {
                  clearInterval(check);
                  resolve();
                }
              }, 50);
              setTimeout(() => { clearInterval(check); reject(new Error("Timeout")); }, 10000);
              return;
            }
            
            const script = document.createElement("script");
            script.src = `https://maps.googleapis.com/maps/api/js?key=${apiKey}&libraries=geometry`;
            script.async = true;
            script.onload = () => resolve();
            script.onerror = () => reject(new Error("Script load failed"));
            document.head.appendChild(script);
          });
        }

        if (!isMounted || !mapContainerRef.current) return;

        const gMaps = (window as any).google.maps;
        const mapDiv = mapContainerRef.current;
        mapDiv.id = instanceId;

        const defaultCenter = center || { lat: -34.6037, lng: -58.3816 };
        
        mapInstance = new gMaps.Map(mapDiv, {
          center: defaultCenter,
          zoom: 12,
          disableDefaultUI: true,
          zoomControl: true,
          clickableIcons: false,
          gestureHandling: "greedy",
          mapId: instanceId,
        });
        
        mapInstanceRef.current = mapInstance;

        await new Promise<void>((resolve) => {
          const listener = mapInstance!.addListener("projection_changed", () => {
            gMaps.event.removeListener(listener);
            resolve();
          });
        });

        if (!isMounted) return;

        const { TerraDraw, TerraDrawPolygonMode, TerraDrawSelectMode } = await import("terra-draw");
        const { TerraDrawGoogleMapsAdapter } = await import("terra-draw-google-maps-adapter");

        const adapter = new TerraDrawGoogleMapsAdapter({
          lib: gMaps,
          map: mapInstance,
          coordinatePrecision: 9,
        });

        draw = new TerraDraw({
          adapter,
          modes: [
            new TerraDrawPolygonMode({
              styles: {
                fillColor: "#4f46e5",
                fillOpacity: 0.3,
                outlineColor: "#4f46e5",
                outlineWidth: 2,
                closingPointColor: "#4f46e5",
                closingPointWidth: 6,
                closingPointOutlineColor: "#ffffff",
                closingPointOutlineWidth: 2,
              } as any,
            }),
            new TerraDrawSelectMode({
              flags: {
                polygon: {
                  feature: {
                    draggable: true,
                    coordinates: {
                      midpoints: true,
                      draggable: true,
                      deletable: true,
                    },
                  },
                },
              },
            }),
          ],
        });

        draw.start();
        terraDrawRef.current = draw;

        await new Promise<void>((resolve) => {
          draw.on("ready", () => resolve());
        });

        if (!isMounted) {
          draw.stop();
          return;
        }

        if (polygon && polygon.length >= 3) {
          try {
            const coords = [...polygon.map(p => [p.lng, p.lat]), [polygon[0].lng, polygon[0].lat]];
            const featureIds = draw.addFeatures([{
              type: "Feature",
              properties: { mode: "polygon" },
              geometry: { type: "Polygon", coordinates: [coords] },
            }]);
            if (featureIds?.length > 0) {
              polygonIdRef.current = String(featureIds[0]);
            }
            
            const bounds = new gMaps.LatLngBounds();
            polygon.forEach(p => bounds.extend(p));
            mapInstance.fitBounds(bounds);
            
            draw.setMode("select");
            setCurrentMode("select");
          } catch (e) {
            console.error("[TerraDraw] Failed to add polygon:", e);
            draw.setMode("polygon");
            setCurrentMode("polygon");
          }
        } else {
          draw.setMode("polygon");
          setCurrentMode("polygon");
        }

        draw.on("finish", (id: string | number) => {
          polygonIdRef.current = String(id);
          const snapshot = draw.getSnapshot();
          const feature = snapshot.find((f: any) => String(f.id) === String(id));
          if (feature?.geometry?.type === "Polygon") {
            const coords = (feature.geometry.coordinates[0] as number[][])
              .slice(0, -1)
              .map((c: number[]) => ({ lat: c[1], lng: c[0] }));
            isExternalUpdateRef.current = true;
            onPolygonChange(coords);
            setHasChanges(JSON.stringify(coords) !== lastSavedPolygonRef.current);
          }
          draw.setMode("select");
          setCurrentMode("select");
        });

        draw.on("change", (ids: (string | number)[], type: string) => {
          if (type === "update" && polygonIdRef.current && ids.map(String).includes(polygonIdRef.current)) {
            const snapshot = draw.getSnapshot();
            const feature = snapshot.find((f: any) => String(f.id) === polygonIdRef.current);
            if (feature?.geometry?.type === "Polygon") {
              const coords = (feature.geometry.coordinates[0] as number[][])
                .slice(0, -1)
                .map((c: number[]) => ({ lat: c[1], lng: c[0] }));
              isExternalUpdateRef.current = true;
              onPolygonChange(coords);
              setHasChanges(JSON.stringify(coords) !== lastSavedPolygonRef.current);
            }
          }
        });

        setIsReady(true);

      } catch (error) {
        console.error("[TerraDraw] Initialization failed:", error);
        terraDrawInstances.delete(instanceId);
      }
    };

    cleanupRef.current = () => {
      isMounted = false;
      if (draw) {
        try { draw.stop(); } catch (e) { }
      }
      terraDrawInstances.delete(instanceId);
    };

    initialize();

    return () => {
      cleanupRef.current?.();
    };
  }, [apiKey]);

  const handleClear = useCallback(() => {
    if (!terraDrawRef.current || !isReady) return;
    try {
      terraDrawRef.current.clear();
      polygonIdRef.current = null;
      isExternalUpdateRef.current = true;
      onPolygonChange([]);
      setHasChanges(lastSavedPolygonRef.current !== "[]");
      terraDrawRef.current.setMode("polygon");
      setCurrentMode("polygon");
    } catch (e) {
      console.warn("[TerraDraw] Clear error:", e);
    }
  }, [onPolygonChange, isReady]);

  const handleSave = useCallback(async () => {
    if (!onSave || isSaving) return;
    try {
      await onSave();
      const currentPolygon = JSON.stringify(polygon || []);
      lastSavedPolygonRef.current = currentPolygon;
      setHasChanges(false);
    } catch (error) {
      // Keep hasChanges true on error so user can retry
    }
  }, [onSave, isSaving, polygon]);

  const handleStartDrawing = useCallback(() => {
    if (!terraDrawRef.current || !isReady) return;
    try {
      if (polygonIdRef.current) {
        terraDrawRef.current.removeFeatures([polygonIdRef.current]);
        polygonIdRef.current = null;
        onPolygonChange([]);
      }
      terraDrawRef.current.setMode("polygon");
      setCurrentMode("polygon");
    } catch (e) {
      console.warn("[TerraDraw] Start drawing error:", e);
    }
  }, [onPolygonChange, isReady]);

  if (!apiKey) {
    return (
      <div className="w-full h-full flex items-center justify-center bg-muted/50 rounded-lg">
        <div className="text-center p-4">
          <MapIcon className="h-12 w-12 text-muted-foreground mx-auto mb-2" />
          <p className="text-sm text-muted-foreground">Google Maps API key not configured</p>
        </div>
      </div>
    );
  }

  return (
    <div className="w-full h-full flex flex-col">
      <div className="flex items-center gap-2 p-2 bg-background/80 backdrop-blur-sm border-b">
        <Button
          size="sm"
          variant={currentMode === "polygon" ? "default" : "outline"}
          onClick={handleStartDrawing}
          disabled={!isReady}
          data-testid="button-draw-polygon"
        >
          <Pencil className="h-4 w-4 mr-2" />
          Draw Polygon
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={handleClear}
          disabled={!isReady}
          data-testid="button-clear-polygon"
        >
          <Trash2 className="h-4 w-4 mr-2" />
          Clear
        </Button>
        {polygon && polygon.length > 0 && (
          <Badge variant="secondary" className="ml-2">
            {polygon.length} points
          </Badge>
        )}
        <div className="flex-1" />
        {onSave && (
          <Button
            size="sm"
            onClick={handleSave}
            disabled={!isReady || isSaving || !hasChanges}
            data-testid="button-save-polygon"
          >
            {isSaving ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                Saving...
              </>
            ) : (
              <>
                <Save className="h-4 w-4 mr-2" />
                Save Area
              </>
            )}
          </Button>
        )}
        <span className="text-xs text-muted-foreground">
          {!isReady 
            ? "Loading map..." 
            : currentMode === "polygon" 
              ? "Click to add points, click first point to close" 
              : "Drag points to edit polygon"}
        </span>
      </div>
      <div
        ref={mapContainerRef}
        className="flex-1"
        style={{ minHeight: "200px" }}
        data-testid="google-map-container"
      />
    </div>
  );
}

const STAGE_COLORS = [
  "#3b82f6", "#22c55e", "#eab308", "#f97316", "#ef4444",
  "#8b5cf6", "#ec4899", "#06b6d4", "#14b8a6", "#64748b"
];

interface PipelinesSectionProps {
  onBack: () => void;
}

function PipelinesSection({ onBack }: PipelinesSectionProps) {
  const { toast } = useToast();
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedPipelineId, setSelectedPipelineId] = useState<string | null>(null);
  const [editingPipeline, setEditingPipeline] = useState<Pipeline | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [editingStage, setEditingStage] = useState<PipelineStage | null>(null);
  const [isCreatingStage, setIsCreatingStage] = useState(false);

  const [backendFailed, setBackendFailed] = useState(false);

  interface PipelinesResponse {
    pipelines?: Pipeline[];
  }

  const pipelinesQuery = useQuery<PipelinesResponse>({
    queryKey: [apiV1("/crm/deals/pipelines/")],
    queryFn: async () => {
      try {
        const result = await fetchJson<PipelinesResponse>(apiV1("/crm/deals/pipelines/"));
        setBackendFailed(false);
        return result;
      } catch {
        setBackendFailed(true);
        return { pipelines: [] };
      }
    },
    retry: false,
  });

  const pipelines = Array.isArray(pipelinesQuery.data?.pipelines) ? pipelinesQuery.data.pipelines : [];
  const backendUnavailable = backendFailed;

  const filteredPipelines = useMemo(() => {
    if (!searchQuery.trim()) return pipelines;
    const query = searchQuery.toLowerCase();
    return pipelines.filter(p => 
      p.name.toLowerCase().includes(query) ||
      (p.description?.toLowerCase() || "").includes(query)
    );
  }, [pipelines, searchQuery]);

  const selectedPipeline = pipelines.find(p => p.id === selectedPipelineId);

  useEffect(() => {
    if (selectedPipeline && !isCreating) {
      setEditingPipeline({ ...selectedPipeline });
    } else if (!isCreating) {
      setEditingPipeline(null);
    }
  }, [selectedPipeline, isCreating]);

  const handleCreateNew = () => {
    setSelectedPipelineId(null);
    setIsCreating(true);
    setEditingPipeline({
      id: "",
      name: "",
      description: "",
      is_default: false,
      stages: [],
    });
  };

  const handleSavePipeline = async () => {
    if (!editingPipeline || backendFailed) {
      if (backendFailed) {
        toast({ title: "Unavailable", description: "Pipeline management is not available.", variant: "destructive" });
      }
      return;
    }
    setIsSaving(true);
    try {
      const pipelineData = {
        name: editingPipeline.name,
        description: editingPipeline.description || "",
        is_default: editingPipeline.is_default,
      };
      if (isCreating) {
        const response = await apiRequest("POST", apiV1("/crm/deals/pipelines/"), { data: pipelineData });
        const result = await response.json();
        toast({ title: "Created", description: "Pipeline created successfully." });
        setIsCreating(false);
        if (result?.id) {
          setSelectedPipelineId(result.id);
        }
      } else {
        await apiRequest("PUT", apiV1(`/crm/deals/pipelines/${editingPipeline.id}/`), { data: pipelineData });
        toast({ title: "Saved", description: "Pipeline updated successfully." });
      }
      queryClient.invalidateQueries({ queryKey: [apiV1("/crm/deals/pipelines/")] });
    } catch (error) {
      toast({ title: "Error", description: (error as Error).message, variant: "destructive" });
    } finally {
      setIsSaving(false);
    }
  };

  const handleDeletePipeline = async (pipeline: Pipeline) => {
    if (backendFailed) return;
    try {
      await apiRequest("DELETE", apiV1(`/crm/deals/pipelines/${pipeline.id}/`), {});
      toast({ title: "Deleted", description: "Pipeline deleted successfully." });
      if (selectedPipelineId === pipeline.id) {
        setSelectedPipelineId(null);
        setEditingPipeline(null);
      }
      queryClient.invalidateQueries({ queryKey: [apiV1("/crm/deals/pipelines/")] });
    } catch (error) {
      toast({ title: "Error", description: (error as Error).message, variant: "destructive" });
    }
  };

  const handleCreateDefaultPipeline = async () => {
    if (backendFailed) return;
    try {
      const response = await apiRequest("POST", apiV1("/crm/deals/pipelines/create-default/"), {});
      const result = await response.json();
      toast({ title: "Created", description: "Default pipeline created successfully." });
      queryClient.invalidateQueries({ queryKey: [apiV1("/crm/deals/pipelines/")] });
      if (result?.id) {
        setSelectedPipelineId(result.id);
      }
    } catch (error) {
      toast({ title: "Error", description: (error as Error).message, variant: "destructive" });
    }
  };

  const handleCreateStage = () => {
    if (!editingPipeline) return;
    setIsCreatingStage(true);
    const maxOrder = Math.max(0, ...(editingPipeline.stages?.map(s => s.order) || []));
    setEditingStage({
      id: "",
      name: "",
      order: maxOrder + 1,
      probability: 50,
      is_won: false,
      is_lost: false,
      color: STAGE_COLORS[Math.floor(Math.random() * STAGE_COLORS.length)],
    });
  };

  const handleSaveStage = async () => {
    if (!editingStage || !selectedPipelineId || backendFailed) return;
    setIsSaving(true);
    try {
      const stageData = {
        name: editingStage.name,
        order: editingStage.order,
        probability: editingStage.probability,
        is_won_stage: editingStage.is_won,
        is_lost_stage: editingStage.is_lost,
        color: editingStage.color,
      };
      if (isCreatingStage) {
        await apiRequest("POST", apiV1(`/crm/deals/pipelines/${selectedPipelineId}/stages/`), { data: stageData });
        toast({ title: "Created", description: "Stage created successfully." });
      } else {
        await apiRequest("PUT", apiV1(`/crm/deals/pipelines/${selectedPipelineId}/stages/${editingStage.id}/`), { data: stageData });
        toast({ title: "Saved", description: "Stage updated successfully." });
      }
      setEditingStage(null);
      setIsCreatingStage(false);
      queryClient.invalidateQueries({ queryKey: [apiV1("/crm/deals/pipelines/")] });
    } catch (error) {
      toast({ title: "Error", description: (error as Error).message, variant: "destructive" });
    } finally {
      setIsSaving(false);
    }
  };

  const handleDeleteStage = async (stage: PipelineStage) => {
    if (!selectedPipelineId || backendFailed) return;
    try {
      await apiRequest("DELETE", apiV1(`/crm/deals/pipelines/${selectedPipelineId}/stages/${stage.id}/`), {});
      toast({ title: "Deleted", description: "Stage deleted successfully." });
      queryClient.invalidateQueries({ queryKey: [apiV1("/crm/deals/pipelines/")] });
    } catch (error) {
      toast({ title: "Error", description: (error as Error).message, variant: "destructive" });
    }
  };

  const sortedStages = useMemo(() => {
    if (!editingPipeline?.stages) return [];
    return [...editingPipeline.stages].sort((a, b) => a.order - b.order);
  }, [editingPipeline?.stages]);

  return (
    <div className="h-full flex -ml-2 -mr-4 -my-4">
      <div className="w-80 border-r border-border bg-background flex flex-col shrink-0">
        <div className="p-3 border-b border-border flex items-center gap-2">
          <Button onClick={handleCreateNew} size="sm" disabled={backendUnavailable} data-testid="button-new-pipeline">
            <Plus className="h-4 w-4 mr-2" />
            New Pipeline
          </Button>
          <Button onClick={handleCreateDefaultPipeline} size="sm" variant="outline" disabled={backendUnavailable} data-testid="button-create-default-pipeline">
            Default
          </Button>
        </div>
        {backendUnavailable && (
          <div className="p-3 bg-muted/50 border-b border-border">
            <p className="text-xs text-muted-foreground">
              Pipeline management is not yet available. The Deals page uses default stages automatically.
            </p>
          </div>
        )}
        <div className="p-3 border-b border-border">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
            <Input
              placeholder="Search pipelines..."
              className="pl-10"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              data-testid="input-search-pipelines"
            />
          </div>
        </div>

        <ScrollArea className="flex-1">
          {pipelinesQuery.isLoading ? (
            <div className="p-4 space-y-3">
              {[...Array(3)].map((_, i) => (
                <Skeleton key={i} className="h-16 w-full" />
              ))}
            </div>
          ) : filteredPipelines.length === 0 ? (
            <div className="p-4">
              <EmptyState
                title={searchQuery.trim() ? "No pipelines match" : "No pipelines"}
                description={searchQuery.trim() ? "Try a different search." : "Create your first pipeline or use the Default button."}
              />
            </div>
          ) : (
            filteredPipelines.map((pipeline) => (
              <div
                key={pipeline.id}
                onClick={() => { setSelectedPipelineId(pipeline.id); setIsCreating(false); }}
                className={`p-3 border-b border-border cursor-pointer transition-colors ${
                  selectedPipelineId === pipeline.id ? "bg-accent" : "hover-elevate"
                }`}
                data-testid={`item-pipeline-${pipeline.id}`}
              >
                <div className="flex items-center justify-between gap-2 mb-1">
                  <h3 className="font-semibold text-sm truncate flex-1">{pipeline.name}</h3>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    {pipeline.is_default && (
                      <Badge variant="secondary" className="text-xs">Default</Badge>
                    )}
                    <Badge variant="outline" className="text-xs">{pipeline.stages?.length || 0} stages</Badge>
                  </div>
                </div>
                {pipeline.description && (
                  <p className="text-xs text-muted-foreground line-clamp-2">{pipeline.description}</p>
                )}
              </div>
            ))
          )}
        </ScrollArea>
      </div>

      <div className="flex-1 flex flex-col overflow-hidden">
        {editingPipeline ? (
          <div className="flex-1 overflow-auto p-6 space-y-6">
            <div className="flex items-center justify-between">
              <h2 className="text-xl font-semibold">
                {isCreating ? "New Pipeline" : editingPipeline.name}
              </h2>
              <div className="flex items-center gap-2">
                {!isCreating && (
                  <Button
                    variant="destructive"
                    size="sm"
                    onClick={() => handleDeletePipeline(editingPipeline)}
                    data-testid="button-delete-pipeline"
                  >
                    <Trash2 className="h-4 w-4 mr-2" />
                    Delete
                  </Button>
                )}
                <Button onClick={handleSavePipeline} disabled={isSaving || !editingPipeline.name.trim()} data-testid="button-save-pipeline">
                  {isSaving ? (
                    <>
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      Saving...
                    </>
                  ) : (
                    <>
                      <Save className="h-4 w-4 mr-2" />
                      Save Pipeline
                    </>
                  )}
                </Button>
              </div>
            </div>

            <GlassPanel className="p-4 space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="pipeline-name">Name</Label>
                  <Input
                    id="pipeline-name"
                    value={editingPipeline.name}
                    onChange={(e) => setEditingPipeline({ ...editingPipeline, name: e.target.value })}
                    placeholder="Sales Pipeline"
                    data-testid="input-pipeline-name"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="pipeline-description">Description</Label>
                  <Input
                    id="pipeline-description"
                    value={editingPipeline.description || ""}
                    onChange={(e) => setEditingPipeline({ ...editingPipeline, description: e.target.value })}
                    placeholder="Main sales pipeline"
                    data-testid="input-pipeline-description"
                  />
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Switch
                  id="pipeline-default"
                  checked={editingPipeline.is_default}
                  onCheckedChange={(checked) => setEditingPipeline({ ...editingPipeline, is_default: checked })}
                  data-testid="switch-pipeline-default"
                />
                <Label htmlFor="pipeline-default">Set as default pipeline</Label>
              </div>
            </GlassPanel>

            {!isCreating && (
              <GlassPanel className="p-4 space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="font-semibold">Stages</h3>
                  <Button size="sm" onClick={handleCreateStage} data-testid="button-add-stage">
                    <Plus className="h-4 w-4 mr-2" />
                    Add Stage
                  </Button>
                </div>

                {sortedStages.length === 0 ? (
                  <div className="text-center py-8 text-muted-foreground">
                    <GitBranch className="h-12 w-12 mx-auto mb-4 opacity-30" />
                    <p>No stages defined</p>
                    <p className="text-sm mt-1">Add stages to define your sales process</p>
                  </div>
                ) : (
                  <div className="space-y-2">
                    {sortedStages.map((stage) => (
                      <div
                        key={stage.id}
                        className="flex items-center gap-3 p-3 rounded-lg border bg-card hover-elevate"
                        data-testid={`card-stage-${stage.id}`}
                      >
                        <GripVertical className="h-4 w-4 text-muted-foreground cursor-move" />
                        <div
                          className="w-4 h-4 rounded-full shrink-0"
                          style={{ backgroundColor: stage.color }}
                        />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="font-medium truncate">{stage.name}</span>
                            {stage.is_won && (
                              <Badge variant="default" className="text-xs gap-1">
                                <CheckCircle2 className="h-3 w-3" />
                                Won
                              </Badge>
                            )}
                            {stage.is_lost && (
                              <Badge variant="destructive" className="text-xs gap-1">
                                <XCircle className="h-3 w-3" />
                                Lost
                              </Badge>
                            )}
                          </div>
                          <div className="text-xs text-muted-foreground flex items-center gap-2">
                            <span>Order: {stage.order}</span>
                            <span className="flex items-center gap-1">
                              <Percent className="h-3 w-3" />
                              {stage.probability}%
                            </span>
                          </div>
                        </div>
                        <div className="flex items-center gap-1">
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8"
                            onClick={() => { setEditingStage(stage); setIsCreatingStage(false); }}
                            data-testid={`button-edit-stage-${stage.id}`}
                          >
                            <Pencil className="h-3.5 w-3.5" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8 text-destructive"
                            onClick={() => handleDeleteStage(stage)}
                            data-testid={`button-delete-stage-${stage.id}`}
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </GlassPanel>
            )}
          </div>
        ) : (
          <div className="flex-1 flex items-center justify-center">
            <EmptyState
              title="Select a pipeline"
              description="Choose a pipeline from the list to view and edit its stages"
            />
          </div>
        )}
      </div>

      <Dialog open={!!editingStage} onOpenChange={(open) => { if (!open) { setEditingStage(null); setIsCreatingStage(false); } }}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{isCreatingStage ? "New Stage" : "Edit Stage"}</DialogTitle>
            <DialogDescription>
              Configure the stage properties for your sales pipeline
            </DialogDescription>
          </DialogHeader>
          {editingStage && (
            <div className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="stage-name">Name</Label>
                <Input
                  id="stage-name"
                  value={editingStage.name}
                  onChange={(e) => setEditingStage({ ...editingStage, name: e.target.value })}
                  placeholder="Qualification"
                  data-testid="input-stage-name"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="stage-order">Order</Label>
                  <Input
                    id="stage-order"
                    type="number"
                    value={editingStage.order}
                    onChange={(e) => setEditingStage({ ...editingStage, order: parseInt(e.target.value) || 0 })}
                    data-testid="input-stage-order"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="stage-probability">Probability (%)</Label>
                  <Input
                    id="stage-probability"
                    type="number"
                    min={0}
                    max={100}
                    value={editingStage.probability}
                    onChange={(e) => setEditingStage({ ...editingStage, probability: Math.min(100, Math.max(0, parseInt(e.target.value) || 0)) })}
                    data-testid="input-stage-probability"
                  />
                </div>
              </div>

              <div className="space-y-2">
                <Label>Color</Label>
                <div className="flex flex-wrap gap-2">
                  {STAGE_COLORS.map((color) => (
                    <button
                      key={color}
                      type="button"
                      className={`w-8 h-8 rounded-full transition-all ${editingStage.color === color ? "ring-2 ring-offset-2 ring-primary" : ""}`}
                      style={{ backgroundColor: color }}
                      onClick={() => setEditingStage({ ...editingStage, color })}
                      data-testid={`button-color-${color.replace("#", "")}`}
                    />
                  ))}
                </div>
              </div>

              <div className="flex items-center gap-6">
                <div className="flex items-center gap-2">
                  <Switch
                    id="stage-won"
                    checked={editingStage.is_won}
                    onCheckedChange={(checked) => setEditingStage({ ...editingStage, is_won: checked, is_lost: checked ? false : editingStage.is_lost })}
                    data-testid="switch-stage-won"
                  />
                  <Label htmlFor="stage-won" className="flex items-center gap-1">
                    <CheckCircle2 className="h-4 w-4 text-green-500" />
                    Won Stage
                  </Label>
                </div>
                <div className="flex items-center gap-2">
                  <Switch
                    id="stage-lost"
                    checked={editingStage.is_lost}
                    onCheckedChange={(checked) => setEditingStage({ ...editingStage, is_lost: checked, is_won: checked ? false : editingStage.is_won })}
                    data-testid="switch-stage-lost"
                  />
                  <Label htmlFor="stage-lost" className="flex items-center gap-1">
                    <XCircle className="h-4 w-4 text-red-500" />
                    Lost Stage
                  </Label>
                </div>
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => { setEditingStage(null); setIsCreatingStage(false); }}>
              Cancel
            </Button>
            <Button onClick={handleSaveStage} disabled={isSaving || !editingStage?.name.trim()} data-testid="button-save-stage">
              {isSaving ? "Saving..." : (isCreatingStage ? "Create" : "Save")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

/** Paginated API response shape used by products, tags, contact_types, knowledge */
interface PaginatedCountResponse {
  pagination?: { total_items: number };
}

/** Pipelines API response shape */
interface PipelinesCountResponse {
  pipelines?: unknown[];
}

function MasterDataGrid({ searchQuery, onSelectSection }: { searchQuery: string; onSelectSection: (section: string) => void }) {
  const productsQ = useQuery({
    queryKey: [apiV1("/crm/products/"), { page: 1, limit: 1 }],
    queryFn: () => fetchJson<PaginatedCountResponse>(apiV1("/crm/products/"), { page: 1, limit: 1 }),
    staleTime: 60_000,
  });
  const knowledgeQ = useQuery({
    queryKey: [apiV1("/crm/knowledge/"), { page: 1, limit: 1 }],
    queryFn: () => fetchJson<PaginatedCountResponse>(apiV1("/crm/knowledge/"), { page: 1, limit: 1 }),
    staleTime: 60_000,
  });
  const servicesQ = useQuery({
    queryKey: [apiV1("/crm/knowledge/"), { type: "service-template", page: 1, limit: 1 }],
    queryFn: () => fetchJson<PaginatedCountResponse>(apiV1("/crm/knowledge/"), { type: "service-template", page: 1, limit: 1 }),
    staleTime: 60_000,
  });
  const contactTypesQ = useQuery({
    queryKey: [apiV1("/crm/contact_types/"), { page: 1, limit: 1 }],
    queryFn: () => fetchJson<PaginatedCountResponse>(apiV1("/crm/contact_types/"), { page: 1, limit: 1 }),
    staleTime: 60_000,
  });
  const tagsQ = useQuery({
    queryKey: [apiV1("/crm/tags/"), { page: 1, limit: 1 }],
    queryFn: () => fetchJson<PaginatedCountResponse>(apiV1("/crm/tags/"), { page: 1, limit: 1 }),
    staleTime: 60_000,
  });
  const pipelinesQ = useQuery({
    queryKey: [apiV1("/crm/deals/pipelines/")],
    queryFn: () => fetchJson<PipelinesCountResponse>(apiV1("/crm/deals/pipelines/")),
    staleTime: 60_000,
  });

  const counts: Record<string, number> = {
    products: productsQ.data?.pagination?.total_items ?? 0,
    knowledge_base: knowledgeQ.data?.pagination?.total_items ?? 0,
    services: servicesQ.data?.pagination?.total_items ?? 0,
    contact_types: contactTypesQ.data?.pagination?.total_items ?? 0,
    tags: tagsQ.data?.pagination?.total_items ?? 0,
    pipelines: Array.isArray(pipelinesQ.data?.pipelines) ? pipelinesQ.data.pipelines.length : 0,
  };

  const masterDataCategories = [
    {
      id: "products",
      title: "Products",
      description: "Manage your product catalog and pricing",
      icon: Package,
      count: counts.products,
      color: "blue",
    },
    {
      id: "knowledge_base",
      title: "Knowledge Base",
      description: "Articles, FAQs, and documentation",
      icon: BookOpen,
      count: counts.knowledge_base,
      color: "purple",
    },
    {
      id: "services",
      title: "Services",
      description: "Service offerings and configurations",
      icon: Wrench,
      count: counts.services,
      color: "green",
    },
    {
      id: "contact_types",
      title: "Contact Types",
      description: "Categories and classifications for contacts",
      icon: UserCog,
      count: counts.contact_types,
      color: "orange",
    },
    {
      id: "tags",
      title: "Tags & Labels",
      description: "Custom tags for organizing records",
      icon: Tags,
      count: counts.tags,
      color: "pink",
    },
    {
      id: "pipelines",
      title: "Pipelines",
      description: "Sales pipelines and deal stages",
      icon: GitBranch,
      count: counts.pipelines,
      color: "cyan",
    },
  ];

  const colorMap: Record<string, string> = {
    blue: "bg-blue-500/10 text-blue-500",
    purple: "bg-purple-500/10 text-purple-500",
    green: "bg-green-500/10 text-green-500",
    orange: "bg-orange-500/10 text-orange-500",
    pink: "bg-pink-500/10 text-pink-500",
    cyan: "bg-cyan-500/10 text-cyan-500",
  };

  const filteredCategories = masterDataCategories.filter(cat => {
    if (!searchQuery) return true;
    const query = searchQuery.toLowerCase();
    return cat.title.toLowerCase().includes(query) || 
           cat.description.toLowerCase().includes(query);
  });

  const handleCategoryClick = (categoryId: string) => {
    if (["services", "knowledge_base", "tags", "contact_types", "pipelines"].includes(categoryId)) {
      onSelectSection(categoryId);
    }
  };

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        Configure and manage reusable data across your CRM
      </p>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {filteredCategories.map((category) => (
          <GlassPanel
            key={category.id}
            className="p-4 cursor-pointer hover-elevate"
            onClick={() => handleCategoryClick(category.id)}
            data-testid={`card-master-${category.id}`}
          >
            <div className="flex items-start gap-4">
              <div className={`p-3 rounded-lg ${colorMap[category.color]}`}>
                <category.icon className="h-6 w-6" />
              </div>
              <div className="flex-1">
                <div className="flex items-center justify-between">
                  <h3 className="font-semibold">{category.title}</h3>
                  <Badge variant="secondary" className="text-xs">
                    {category.count}
                  </Badge>
                </div>
                <p className="text-sm text-muted-foreground mt-1">
                  {category.description}
                </p>
              </div>
            </div>
          </GlassPanel>
        ))}
      </div>
    </div>
  );
}

function AnalyticsTab() {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <GlassPanel className="p-4">
          <div className="flex items-center gap-3 mb-4">
            <div className="p-2 rounded-lg bg-blue-500/10">
              <TrendingUp className="h-5 w-5 text-blue-500" />
            </div>
            <h3 className="font-semibold">Sales Performance</h3>
          </div>
          <div className="h-32 flex items-center justify-center text-muted-foreground">
            Chart placeholder
          </div>
        </GlassPanel>

        <GlassPanel className="p-4">
          <div className="flex items-center gap-3 mb-4">
            <div className="p-2 rounded-lg bg-green-500/10">
              <Users className="h-5 w-5 text-green-500" />
            </div>
            <h3 className="font-semibold">Contact Growth</h3>
          </div>
          <div className="h-32 flex items-center justify-center text-muted-foreground">
            Chart placeholder
          </div>
        </GlassPanel>

        <GlassPanel className="p-4">
          <div className="flex items-center gap-3 mb-4">
            <div className="p-2 rounded-lg bg-purple-500/10">
              <Target className="h-5 w-5 text-purple-500" />
            </div>
            <h3 className="font-semibold">Conversion Funnel</h3>
          </div>
          <div className="h-32 flex items-center justify-center text-muted-foreground">
            Chart placeholder
          </div>
        </GlassPanel>
      </div>

      <GlassPanel className="p-6">
        <EmptyState
          title="Analytics Dashboard"
          description="Comprehensive CRM analytics and reporting will be available here. Track sales performance, customer insights, and pipeline health."
        />
      </GlassPanel>
    </div>
  );
}
