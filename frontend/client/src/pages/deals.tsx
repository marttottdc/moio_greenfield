import { useMemo, useState, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "wouter";
import { DndContext, DragEndEvent, closestCenter, PointerSensor, useSensor, useSensors, DragOverlay } from "@dnd-kit/core";
import { useDraggable, useDroppable } from "@dnd-kit/core";
import { CSS } from "@dnd-kit/utilities";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { Plus, MoreVertical, Trash2, Pencil, Loader2, Check, ChevronsUpDown, User, Trophy, XCircle, MessageSquare, Calendar, Send, Mail, MessageCircle, BarChart3, Settings2, Phone, ArrowRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { PageLayout } from "@/components/layout/page-layout";
import { GlassPanel } from "@/components/radiant/glass-panel";
import { Subheading } from "@/components/radiant/text";
import { EmptyState } from "@/components/empty-state";
import { ErrorDisplay } from "@/components/error-display";
import { Skeleton } from "@/components/ui/skeleton";
import { fetchJson, apiRequest, queryClient } from "@/lib/queryClient";
import { apiV1 } from "@/lib/api";
import { useToast } from "@/hooks/use-toast";
// @ts-ignore
import confetti from "canvas-confetti";

interface PipelineStage {
  id: string;
  name: string;
  order: number;
  probability: number;
  is_won?: boolean;
  is_lost?: boolean;
  is_won_stage?: boolean;
  is_lost_stage?: boolean;
  color: string;
}

interface Pipeline {
  id: string;
  name: string;
  description?: string;
  is_default: boolean;
  stages: PipelineStage[];
}

interface DealComment {
  id: string;
  text: string;
  type?: string;
  from_stage?: string;
  to_stage?: string;
  author_id?: string;
  author_name?: string;
  created_at: string;
}

interface Deal {
  id: string;
  title: string;
  description?: string;
  contact?: string | null;
  contact_name?: string | null;
  value?: number | null;
  currency?: string;
  stage?: string;
  stage_id?: string;
  stage_name?: string;
  pipeline?: string;
  pipeline_id?: string;
  priority?: string;
  status?: string;
  expected_close_date?: string;
  created_at?: string;
  updated_at?: string;
  comments?: DealComment[];
}

interface DealsResponse {
  deals?: Deal[];
  results?: Deal[];
  items?: Deal[];
}

const PRIORITY_OPTIONS = [
  { value: "low", label: "Low" },
  { value: "medium", label: "Medium" },
  { value: "high", label: "High" },
  { value: "urgent", label: "Urgent" },
];

const CURRENCY_OPTIONS = [
  { value: "USD", label: "USD - US Dollar" },
  { value: "EUR", label: "EUR - Euro" },
  { value: "GBP", label: "GBP - British Pound" },
  { value: "MXN", label: "MXN - Mexican Peso" },
  { value: "ARS", label: "ARS - Argentine Peso" },
  { value: "BRL", label: "BRL - Brazilian Real" },
  { value: "CLP", label: "CLP - Chilean Peso" },
  { value: "COP", label: "COP - Colombian Peso" },
  { value: "UYU", label: "UYU - Uruguayan Peso" },
];

interface Contact {
  id: string;
  name: string;
  email?: string;
  phone?: string;
}

interface ContactsResponse {
  contacts?: Contact[];
  results?: Contact[];
}


function DealCardContent({ deal }: { deal: Deal }) {
  return (
    <div className="bg-card rounded-lg p-4 shadow-lg touch-none opacity-90">
      <div className="flex items-start justify-between mb-2 gap-2">
        <h3 className="font-semibold text-sm truncate flex-1">{deal.title}</h3>
      </div>
      {deal.contact_name && (
        <p className="text-xs text-muted-foreground mb-1 truncate">{deal.contact_name}</p>
      )}
      {deal.description && (
        <p className="text-xs text-muted-foreground mb-2 line-clamp-2">
          {deal.description.length > 40 ? deal.description.slice(0, 40) + "..." : deal.description}
        </p>
      )}
      <div className="text-lg font-bold text-[#58a6ff]">
        {typeof deal.value === "number" ? deal.value.toLocaleString(undefined, { style: "currency", currency: deal.currency || "USD", maximumFractionDigits: 0 }) : "--"}
      </div>
      {deal.created_at && (
        <p className="text-[10px] text-muted-foreground mt-1 flex items-center gap-1">
          <Calendar className="h-3 w-3" />
          Created: {new Date(deal.created_at).toLocaleDateString()}
        </p>
      )}
      {deal.priority && deal.priority !== "medium" && (
        <Badge variant={deal.priority === "urgent" || deal.priority === "high" ? "destructive" : "secondary"} className="text-xs mt-2">
          {deal.priority}
        </Badge>
      )}
      <div className="flex gap-1 mt-2 border-t min-w-0 overflow-hidden">
        <Button 
          size="sm" 
          variant="ghost" 
          disabled
          className="flex-1 min-w-0 h-7 text-[10px] text-red-600 px-1.5 mt-2"
        >
          <XCircle className="h-3 w-3 shrink-0 mr-0.5" />
          Lost
        </Button>
        <Button 
          size="sm" 
          variant="ghost" 
          disabled
          className="flex-1 min-w-0 h-7 text-[10px] text-green-600 px-1.5 mt-2"
        >
          <Trophy className="h-3 w-3 shrink-0 mr-0.5" />
          Won
        </Button>
      </div>
    </div>
  );
}

function DraggableDealCard({ deal, stage, onEdit, onDelete, onWon, onLost, onProgress, onViewDetails, isDragging, contacts }: { 
  deal: Deal; 
  stage: PipelineStage;
  onEdit: (deal: Deal) => void;
  onDelete: (deal: Deal) => void;
  onWon: (deal: Deal) => void;
  onLost: (deal: Deal) => void;
  onProgress: (deal: Deal) => void;
  onViewDetails: (deal: Deal) => void;
  isDragging: boolean;
  contacts: Contact[];
}) {
  const { attributes, listeners, setNodeRef, transform } = useDraggable({
    id: deal.id,
    data: { deal, stageId: stage.id }
  });

  const style: React.CSSProperties = {
    transform: CSS.Translate.toString(transform),
    cursor: 'grab',
  };

  const handleCardClick = (e: React.MouseEvent) => {
    onViewDetails(deal);
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      {...attributes}
      {...listeners}
      className={cn("bg-card border rounded-lg p-4 shadow-sm touch-none hover-elevate w-[95%] mx-auto", isDragging && "opacity-0")}
      data-testid={`card-deal-${deal.id}`}
      onClick={handleCardClick}
    >
      <div className="flex items-start justify-between mb-2 gap-2">
        <h3 className="font-semibold text-sm truncate flex-1" data-testid={`text-deal-title-${deal.id}`}>
          {deal.title}
        </h3>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button 
              size="icon" 
              variant="ghost" 
              className="h-6 w-6 shrink-0" 
              data-testid={`button-deal-menu-${deal.id}`}
              onPointerDown={(e) => e.stopPropagation()}
            >
              <MoreVertical className="h-3 w-3" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={(e) => { e.stopPropagation(); onEdit(deal); }}>
              <Pencil className="h-4 w-4 mr-2" />
              Edit
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={(e) => { e.stopPropagation(); onDelete(deal); }} className="text-destructive">
              <Trash2 className="h-4 w-4 mr-2" />
              Delete
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      {(() => {
        const contact = deal.contact ? contacts.find(c => c.id === deal.contact) : null;
        const contactPhone = contact?.phone;
        const contactEmail = contact?.email;
        const whatsappNumber = contactPhone?.replace(/[^0-9]/g, "");
        
        if (!deal.contact_name && !contact) return null;
        
        return (
          <div className="mb-2">
            {deal.contact_name && (
              <p className="text-xs text-muted-foreground truncate">{deal.contact_name}</p>
            )}
            {(contactPhone || contactEmail) && (
              <div className="flex items-center gap-2 mt-0.5">
                {contactPhone && (
                  <a
                    href={`https://wa.me/${whatsappNumber}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    onClick={(e) => e.stopPropagation()}
                    onPointerDown={(e) => e.stopPropagation()}
                    className="text-[10px] text-green-600 hover:underline flex items-center gap-0.5"
                    data-testid={`link-deal-card-phone-${deal.id}`}
                  >
                    <Phone className="h-2.5 w-2.5" />
                    <span className="truncate max-w-[70px]">{contactPhone}</span>
                  </a>
                )}
                {contactEmail && !contactPhone && (
                  <a
                    href={`mailto:${contactEmail}`}
                    onClick={(e) => e.stopPropagation()}
                    onPointerDown={(e) => e.stopPropagation()}
                    className="text-[10px] text-primary hover:underline flex items-center gap-0.5"
                    data-testid={`link-deal-card-email-${deal.id}`}
                  >
                    <Mail className="h-2.5 w-2.5" />
                    <span className="truncate max-w-[80px]">{contactEmail}</span>
                  </a>
                )}
              </div>
            )}
          </div>
        );
      })()}
      {deal.description && (
        <p className="text-xs text-muted-foreground mb-2 line-clamp-2">
          {deal.description.length > 40 ? deal.description.slice(0, 40) + "..." : deal.description}
        </p>
      )}
      <div className="text-lg font-bold text-[#58a6ff]" data-testid={`text-deal-value-${deal.id}`}>
        {typeof deal.value === "number" ? deal.value.toLocaleString(undefined, { style: "currency", currency: deal.currency || "USD", maximumFractionDigits: 0 }) : "--"}
      </div>
      {deal.created_at && (
        <p className="text-[10px] text-muted-foreground mt-1 flex items-center gap-1">
          <Calendar className="h-3 w-3" />
          Created: {new Date(deal.created_at).toLocaleDateString()}
        </p>
      )}
      {deal.priority && deal.priority !== "medium" && (
        <Badge variant={deal.priority === "urgent" || deal.priority === "high" ? "destructive" : "secondary"} className="text-xs mt-2">
          {deal.priority}
        </Badge>
      )}
      <div className="flex gap-1 mt-2 pt-2 border-t min-w-0 overflow-hidden">
        <Button 
          size="sm" 
          variant="ghost" 
          className="flex-1 min-w-0 h-7 text-[10px] text-red-600 hover:text-red-700 hover:bg-red-50 dark:hover:bg-red-950 px-1.5"
          onClick={(e) => { e.stopPropagation(); onLost(deal); }}
          onPointerDown={(e) => e.stopPropagation()}
          data-testid={`button-lost-${deal.id}`}
        >
          <XCircle className="h-3 w-3 shrink-0 mr-0.5" />
          Lost
        </Button>
        <Button 
          size="sm" 
          variant="ghost" 
          className="flex-1 min-w-0 h-7 text-[10px] text-blue-600 hover:text-blue-700 hover:bg-blue-50 dark:hover:bg-blue-950 px-1.5"
          onClick={(e) => { e.stopPropagation(); onProgress(deal); }}
          onPointerDown={(e) => e.stopPropagation()}
          data-testid={`button-followup-${deal.id}`}
        >
          <ArrowRight className="h-3 w-3 shrink-0 mr-0.5" />
          Followup
        </Button>
        <Button 
          size="sm" 
          variant="ghost" 
          className="flex-1 min-w-0 min-h-[44px] sm:h-7 sm:min-h-0 text-[10px] text-green-600 hover:text-green-700 hover:bg-green-50 dark:hover:bg-green-950 px-1.5"
          onClick={(e) => { e.stopPropagation(); onWon(deal); }}
          onPointerDown={(e) => e.stopPropagation()}
          data-testid={`button-won-${deal.id}`}
        >
          <Trophy className="h-3 w-3 shrink-0 mr-0.5" />
          Won
        </Button>
      </div>
    </div>
  );
}

function DroppableStageColumn({ stage, children }: { stage: PipelineStage; children: React.ReactNode }) {
  const { isOver, setNodeRef } = useDroppable({
    id: stage.id,
    data: { stage }
  });

  return (
    <div
      ref={setNodeRef}
      className={cn(
        "space-y-1.5 w-full min-h-[300px] max-h-[calc(100vh-300px)] overflow-y-auto scrollbar-hide flex-1 rounded-lg transition-colors flex flex-col items-center",
        isOver && "bg-primary/10 ring-2 ring-primary/30"
      )}
    >
      {children}
    </div>
  );
}

export default function Deals() {
  const { toast } = useToast();
  const searchParams = new URLSearchParams(window.location.search);
  const isEmbedded = searchParams.get("embed") === "true";
  const urlDealId = searchParams.get("dealId");
  const [selectedPipelineId, setSelectedPipelineId] = useState<string | null>(null);
  const [editingDeal, setEditingDeal] = useState<Deal | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [contactPopoverOpen, setContactPopoverOpen] = useState(false);
  const [activeDeal, setActiveDeal] = useState<Deal | null>(null);
  
  const [commentDialogOpen, setCommentDialogOpen] = useState(false);
  const [pendingMove, setPendingMove] = useState<{ deal: Deal; targetStageId: string; targetStageName: string; previousData?: DealsResponse; isFollowup?: boolean } | null>(null);
  const [moveComment, setMoveComment] = useState("");
  const [followupStageSelection, setFollowupStageSelection] = useState<string>("");
  
  const [viewingDeal, setViewingDeal] = useState<Deal | null>(null);
  const [isContactExpanded, setIsContactExpanded] = useState(false);

  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: {
        distance: 8,
      },
    })
  );

  interface PipelinesResponse {
    pipelines?: Pipeline[];
  }

  const pipelinesQuery = useQuery<PipelinesResponse>({
    queryKey: [apiV1("/crm/deals/pipelines/")],
    queryFn: async () => {
      try {
        return await fetchJson<PipelinesResponse>(apiV1("/crm/deals/pipelines/"));
      } catch {
        return { pipelines: [] };
      }
    },
    retry: false,
  });

  const dealByIdQuery = useQuery<Deal>({
    queryKey: [apiV1("/crm/deals/"), "by-id", urlDealId],
    queryFn: () => fetchJson<Deal>(apiV1(`/crm/deals/${urlDealId}/`)),
    enabled: !!urlDealId,
    retry: false,
  });

  useEffect(() => {
    if (urlDealId && dealByIdQuery.data && !editingDeal) {
      const deal = dealByIdQuery.data;
      setEditingDeal({
        ...deal,
        value: typeof deal.value === "string" ? parseFloat(deal.value) : (deal.value ?? 0),
      });
      if (deal.pipeline_id || deal.pipeline) {
        setSelectedPipelineId((deal.pipeline_id ?? deal.pipeline) ?? null);
      }
      const params = new URLSearchParams(window.location.search);
      params.delete("dealId");
      const q = params.toString();
      const url = q ? `${window.location.pathname}?${q}` : window.location.pathname;
      window.history.replaceState({}, "", url);
    }
  }, [urlDealId, dealByIdQuery.data]);

  const pipelines = Array.isArray(pipelinesQuery.data?.pipelines) ? pipelinesQuery.data.pipelines : [];
  
  const activePipeline = useMemo(() => {
    if (selectedPipelineId) {
      return pipelines.find(p => p.id === selectedPipelineId);
    }
    return pipelines.find(p => p.is_default) || pipelines[0];
  }, [pipelines, selectedPipelineId]);

  const dealsQuery = useQuery<DealsResponse>({
    queryKey: [apiV1("/crm/deals/"), activePipeline?.id],
    queryFn: () => fetchJson<DealsResponse>(apiV1("/crm/deals/"), activePipeline?.id ? { pipeline: activePipeline.id } : {}),
  });

  const contactsQuery = useQuery<ContactsResponse>({
    queryKey: [apiV1("/crm/contacts/"), "all"],
    queryFn: async () => {
      try {
        return await fetchJson<ContactsResponse>(apiV1("/crm/contacts/"), { page: 1, page_size: 500 });
      } catch {
        return { contacts: [] };
      }
    },
    retry: false,
    staleTime: 0,
  });

  const contacts = useMemo(() => {
    const data = contactsQuery.data;
    return data?.contacts ?? data?.results ?? [];
  }, [contactsQuery.data]);

  const deals = useMemo(() => {
    const data = dealsQuery.data;
    let rawDeals: Deal[] = [];
    if (Array.isArray(data)) {
      rawDeals = data;
    } else {
      rawDeals = data?.deals ?? data?.results ?? data?.items ?? [];
    }
    return rawDeals.map(deal => ({
      ...deal,
      value: typeof deal.value === 'string' ? parseFloat(deal.value) : (deal.value || 0),
    }));
  }, [dealsQuery.data]);

  const allStages = useMemo(() => {
    if (activePipeline?.stages?.length) {
      return [...activePipeline.stages].sort((a, b) => a.order - b.order);
    }
    return [];
  }, [activePipeline?.stages]);

  const stages = useMemo(() => {
    return allStages.filter(stage => 
      !stage.is_won && !stage.is_lost && !stage.is_won_stage && !stage.is_lost_stage
    );
  }, [allStages]);

  const wonStage = useMemo(() => {
    return allStages.find(stage => stage.is_won || stage.is_won_stage);
  }, [allStages]);

  const lostStage = useMemo(() => {
    return allStages.find(stage => stage.is_lost || stage.is_lost_stage);
  }, [allStages]);

  const dealsByStage = useMemo(() => {
    return stages.reduce<Record<string, Deal[]>>((acc, stage) => {
      acc[stage.id] = deals.filter((deal) => {
        const dealStage = deal.stage_id ?? deal.stage;
        return dealStage === stage.id || dealStage === stage.name;
      });
      return acc;
    }, {});
  }, [deals, stages]);

  // Calculate active deals (excluding won/lost stages) - matching Pipeline Summary in analytics
  const activeDeals = useMemo(() => {
    return deals.filter((deal) => {
      const dealStage = deal.stage_id ?? deal.stage;
      return stages.some(s => s.id === dealStage || s.name === dealStage);
    });
  }, [deals, stages]);

  const activeValue = useMemo(() => {
    return activeDeals.reduce((sum, d) => sum + (d.value || 0), 0);
  }, [activeDeals]);

  const metrics = deals.length
    ? [
        { label: "Active Deals", value: activeDeals.length.toString(), testId: "text-active-deals" },
        { label: "Active Pipeline Value", value: activeValue.toLocaleString(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 0 }), testId: "text-active-pipeline-value" },
        { label: "Active Stages", value: stages.length.toString(), testId: "text-active-stages" },
      ]
    : undefined;

  const handleAddDeal = (stageId?: string) => {
    contactsQuery.refetch();
    setIsCreating(true);
    setEditingDeal({
      id: "",
      title: "",
      description: "",
      value: 0,
      currency: "USD",
      contact: null,
      priority: "medium",
      stage: stageId || stages[0]?.id || "",
      pipeline: activePipeline?.id || "",
    });
  };

  const handleEditDeal = (deal: Deal) => {
    contactsQuery.refetch();
    setIsCreating(false);
    setEditingDeal({ ...deal });
  };

  const handleSaveDeal = async () => {
    if (!editingDeal) return;
    setIsSaving(true);
    try {
      // Validate contact exists if one is selected (only if contacts query succeeded)
      let validContact: string | null = editingDeal.contact || null;
      if (validContact && contactsQuery.isSuccess && contacts.length > 0) {
        const contactExists = contacts.some(c => c.id === validContact);
        if (!contactExists) {
          validContact = null;
          toast({ 
            title: "Contact cleared", 
            description: "The selected contact no longer exists and was removed from the deal.",
            variant: "default"
          });
        }
      }
      
      const dealData = {
        title: editingDeal.title,
        description: editingDeal.description || "",
        value: String(editingDeal.value || 0),
        currency: editingDeal.currency || "USD",
        priority: editingDeal.priority || "medium",
        stage: editingDeal.stage ?? editingDeal.stage_id,
        pipeline: editingDeal.pipeline ?? editingDeal.pipeline_id ?? activePipeline?.id,
        contact: validContact,
        expected_close_date: editingDeal.expected_close_date || null,
      };

      if (isCreating) {
        await apiRequest("POST", apiV1("/crm/deals/"), { data: dealData });
        toast({ title: "Created", description: "Deal created successfully." });
      } else {
        await apiRequest("PUT", apiV1(`/crm/deals/${editingDeal.id}/`), { data: dealData });
        toast({ title: "Saved", description: "Deal updated successfully." });
      }
      setEditingDeal(null);
      setIsCreating(false);
      queryClient.invalidateQueries({ queryKey: [apiV1("/crm/deals/")] });
    } catch (error) {
      toast({ title: "Error", description: (error as Error).message, variant: "destructive" });
    } finally {
      setIsSaving(false);
    }
  };

  const handleDeleteDeal = async (deal: Deal) => {
    try {
      await apiRequest("DELETE", apiV1(`/crm/deals/${deal.id}/`), {});
      toast({ title: "Deleted", description: "Deal deleted successfully." });
      queryClient.invalidateQueries({ queryKey: [apiV1("/crm/deals/")] });
    } catch (error) {
      toast({ title: "Error", description: (error as Error).message, variant: "destructive" });
    }
  };

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    setActiveDeal(null);
    
    if (!over) return;
    
    const dealId = active.id as string;
    const targetStageId = over.id as string;
    const deal = deals.find(d => d.id === dealId);
    const currentStageId = deal?.stage_id ?? deal?.stage;
    
    if (!deal || currentStageId === targetStageId) return;
    
    const targetStage = stages.find(s => s.id === targetStageId);
    if (!targetStage) return;

    // Optimistic update - move the deal immediately in the cache
    const queryKey = [apiV1("/crm/deals/"), activePipeline?.id];
    const previousData = queryClient.getQueryData<DealsResponse>(queryKey);
    
    queryClient.setQueryData<DealsResponse>(queryKey, (old) => {
      if (!old) return old;
      const updateDeal = (d: Deal) => 
        d.id === dealId ? { ...d, stage_id: targetStageId, stage: targetStageId } : d;
      
      return {
        ...old,
        deals: old.deals?.map(updateDeal),
        results: old.results?.map(updateDeal),
        items: old.items?.map(updateDeal),
      };
    });

    setPendingMove({ deal, targetStageId, targetStageName: targetStage.name, previousData });
    setMoveComment("");
    setCommentDialogOpen(true);
  };

  const handleConfirmMove = async () => {
    if (!pendingMove) return;
    
    // For followup, comment is required
    if (pendingMove.isFollowup && !moveComment.trim()) {
      toast({ 
        title: "Comment required", 
        description: "Please add a comment for the followup.", 
        variant: "destructive" 
      });
      return;
    }
    
    // For followup, stage selection is required
    if (pendingMove.isFollowup && !followupStageSelection) {
      toast({ 
        title: "Stage selection required", 
        description: "Please select whether to stay in current stage or move to next stage.", 
        variant: "destructive" 
      });
      return;
    }
    
    setIsSaving(true);
    try {
      // If followup without moving stage (stay in current), just add comment
      if (pendingMove.isFollowup && followupStageSelection === "stay") {
        await apiRequest("POST", apiV1(`/crm/deals/${pendingMove.deal.id}/comments/`), { 
          data: { text: moveComment.trim() } 
        });
        toast({ title: "Followup added", description: "Your followup comment was added successfully." });
      } else {
        // Move stage with comment
        const isWonStage = wonStage && pendingMove.targetStageId === wonStage.id;
        await apiRequest("POST", apiV1(`/crm/deals/${pendingMove.deal.id}/move-stage/`), { 
          data: { 
            stage_id: pendingMove.targetStageId,
            comment: moveComment || undefined
          } 
        });
        
        if (isWonStage) {
          confetti({
            particleCount: 150,
            spread: 100,
            origin: { y: 0.6 },
            colors: ['#22c55e', '#16a34a', '#15803d', '#fbbf24', '#f59e0b']
          });
          toast({ title: "Congratulations!", description: "Deal marked as Won!" });
        }
      }
      setCommentDialogOpen(false);
      setPendingMove(null);
      setMoveComment("");
      setFollowupStageSelection("");
      queryClient.invalidateQueries({ queryKey: [apiV1("/crm/deals/")] });
    } catch (error) {
      // Revert optimistic update on error
      if (pendingMove.previousData) {
        queryClient.setQueryData([apiV1("/crm/deals/"), activePipeline?.id], pendingMove.previousData);
      }
      toast({ title: "Error", description: (error as Error).message, variant: "destructive" });
    } finally {
      setIsSaving(false);
    }
  };

  const handleCancelMove = () => {
    // Revert optimistic update when user cancels
    if (pendingMove?.previousData) {
      queryClient.setQueryData([apiV1("/crm/deals/"), activePipeline?.id], pendingMove.previousData);
    }
    setCommentDialogOpen(false);
    setPendingMove(null);
    setMoveComment("");
    setFollowupStageSelection("");
  };

  const handleMarkWon = (deal: Deal) => {
    if (!wonStage) {
      toast({ title: "Error", description: "No 'Won' stage configured in the pipeline.", variant: "destructive" });
      return;
    }
    setPendingMove({ deal, targetStageId: wonStage.id, targetStageName: wonStage.name });
    setMoveComment("");
    setCommentDialogOpen(true);
  };

  const handleMarkLost = (deal: Deal) => {
    if (!lostStage) {
      toast({ title: "Error", description: "No 'Lost' stage configured in the pipeline.", variant: "destructive" });
      return;
    }
    setPendingMove({ deal, targetStageId: lostStage.id, targetStageName: lostStage.name });
    setMoveComment("");
    setCommentDialogOpen(true);
  };

  const handleProgress = (deal: Deal) => {
    // Open dialog for followup - allows comment without moving stage
    setPendingMove({ deal, targetStageId: "", targetStageName: "", isFollowup: true });
    setMoveComment("");
    setFollowupStageSelection("");
    setCommentDialogOpen(true);
  };

  const handleViewDetails = (deal: Deal) => {
    setViewingDeal(deal);
  };

  const isLoading = pipelinesQuery.isLoading || dealsQuery.isLoading;
  const isError = dealsQuery.isError;
  const error = dealsQuery.error;

  const content = (
    <>
      {pipelines.length > 1 && (
        <div className="flex justify-end mb-4">
          <Select
            value={activePipeline?.id || ""}
            onValueChange={(value) => setSelectedPipelineId(value)}
          >
            <SelectTrigger className="w-full max-w-[200px]" data-testid="select-pipeline">
              <SelectValue placeholder="Select pipeline" />
            </SelectTrigger>
            <SelectContent>
              {pipelines.map((pipeline) => (
                <SelectItem key={pipeline.id} value={pipeline.id}>
                  {pipeline.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}

      <div className="overflow-x-auto overflow-y-visible -mx-4 px-4 md:mx-0 md:px-0">
        {isLoading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="space-y-3">
                <Skeleton className="h-8 w-full" />
                <Skeleton className="h-32 w-full" />
                <Skeleton className="h-32 w-full" />
              </div>
            ))}
          </div>
        ) : isError ? (
          <ErrorDisplay error={error} endpoint="api/v1/deals" />
        ) : stages.length === 0 ? (
          <EmptyState
            title="No pipeline configured"
            description="Go to CRM > Master Data > Pipelines to create a pipeline with stages."
          />
        ) : (
          <DndContext
            sensors={sensors}
            collisionDetection={closestCenter}
            onDragStart={(event) => {
              const deal = deals.find(d => d.id === event.active.id);
              if (deal) setActiveDeal(deal);
            }}
            onDragEnd={handleDragEnd}
          >
            <div
              className="grid gap-2 overflow-visible"
              style={{
                gridTemplateColumns: `repeat(${stages.length}, minmax(140px, 1fr))`,
                minWidth: `${Math.max(stages.length * 140, 280)}px`,
              }}
            >
              {stages.map((stage, index) => {
                const stageDeals = dealsByStage[stage.id] ?? [];
                const isLast = index === stages.length - 1;
                return (
                  <div 
                    key={stage.id} 
                    className={cn(
                      "flex flex-col overflow-visible items-center",
                      !isLast && "border-r border-dotted border-border"
                    )}
                  >
                    <div className="w-full flex items-center justify-between mb-4 gap-2">
                      <div className="flex items-center gap-2 min-w-0">
                        <div className="w-3 h-3 rounded-full shrink-0" style={{ backgroundColor: stage.color }} />
                        <Subheading as="h3" className="!text-sm truncate">
                          {stage.name}
                        </Subheading>
                      </div>
                      <Badge variant="secondary" className="text-xs h-5 px-2 shrink-0" data-testid={`badge-count-${stage.id}`}>
                        {stageDeals.length}
                      </Badge>
                    </div>

                    <DroppableStageColumn stage={stage}>
                      {stageDeals.length === 0 ? (
                        <div className="flex-1 flex items-center justify-center py-8 text-muted-foreground text-sm">
                          No deals
                        </div>
                      ) : (
                        stageDeals.map((deal) => (
                          <DraggableDealCard
                            key={deal.id}
                            deal={deal}
                            stage={stage}
                            onEdit={handleEditDeal}
                            onDelete={handleDeleteDeal}
                            onWon={handleMarkWon}
                            onLost={handleMarkLost}
                            onProgress={handleProgress}
                            onViewDetails={handleViewDetails}
                            isDragging={activeDeal?.id === deal.id}
                            contacts={contacts}
                          />
                        ))
                      )}
                    </DroppableStageColumn>
                  </div>
                );
              })}
            </div>
            <DragOverlay>
              {activeDeal ? <DealCardContent deal={activeDeal} /> : null}
            </DragOverlay>
          </DndContext>
        )}
      </div>

      <Dialog open={!!editingDeal} onOpenChange={(open) => { if (!open) { setEditingDeal(null); setIsCreating(false); } }}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>{isCreating ? "New Deal" : "Edit Deal"}</DialogTitle>
            <DialogDescription>
              {isCreating ? "Create a new deal in your pipeline" : "Update deal information"}
            </DialogDescription>
          </DialogHeader>
          {editingDeal && (
            <div className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="deal-title">Title</Label>
                <Input
                  id="deal-title"
                  value={editingDeal.title}
                  onChange={(e) => setEditingDeal({ ...editingDeal, title: e.target.value })}
                  placeholder="Deal name"
                  data-testid="input-deal-title"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="deal-description">Description</Label>
                <Textarea
                  id="deal-description"
                  value={editingDeal.description || ""}
                  onChange={(e) => setEditingDeal({ ...editingDeal, description: e.target.value })}
                  placeholder="Deal details..."
                  data-testid="input-deal-description"
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="deal-value">Value</Label>
                  <Input
                    id="deal-value"
                    type="number"
                    value={editingDeal.value || 0}
                    onChange={(e) => setEditingDeal({ ...editingDeal, value: parseFloat(e.target.value) || 0 })}
                    data-testid="input-deal-value"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="deal-currency">Currency</Label>
                  <Select
                    value={editingDeal.currency || "USD"}
                    onValueChange={(value) => setEditingDeal({ ...editingDeal, currency: value })}
                  >
                    <SelectTrigger id="deal-currency" data-testid="select-deal-currency">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {CURRENCY_OPTIONS.map((opt) => (
                        <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="deal-contact">Contact</Label>
                  <Popover open={contactPopoverOpen} onOpenChange={setContactPopoverOpen}>
                    <PopoverTrigger asChild>
                      <Button
                        variant="outline"
                        role="combobox"
                        aria-expanded={contactPopoverOpen}
                        className="w-full justify-between font-normal"
                        data-testid="select-deal-contact"
                      >
                        {editingDeal.contact ? (
                          contacts.find(c => c.id === editingDeal.contact) ? (
                            <span className="flex items-center gap-2 truncate">
                              <User className="h-4 w-4 shrink-0 text-muted-foreground" />
                              {contacts.find(c => c.id === editingDeal.contact)?.name}
                            </span>
                          ) : (
                            <span className="flex items-center gap-2 truncate text-destructive">
                              <User className="h-4 w-4 shrink-0" />
                              Invalid contact - please select another
                            </span>
                          )
                        ) : (
                          <span className="text-muted-foreground">Search contacts...</span>
                        )}
                        <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                      </Button>
                    </PopoverTrigger>
                    <PopoverContent className="w-[min(300px,calc(100vw-2rem))] p-0" align="start">
                      <Command>
                        <CommandInput placeholder="Search contacts..." />
                        <CommandList>
                          <CommandEmpty>No contacts found.</CommandEmpty>
                          <CommandGroup>
                            <CommandItem
                              value="__clear__"
                              onSelect={() => {
                                setEditingDeal({ ...editingDeal, contact: null });
                                setContactPopoverOpen(false);
                              }}
                            >
                              <Check className={cn("mr-2 h-4 w-4", !editingDeal.contact ? "opacity-100" : "opacity-0")} />
                              <span className="text-muted-foreground">No contact</span>
                            </CommandItem>
                            {contacts.map((contact) => (
                              <CommandItem
                                key={contact.id}
                                value={`${contact.name} ${contact.email || ""}`}
                                onSelect={() => {
                                  setEditingDeal({ ...editingDeal, contact: contact.id });
                                  setContactPopoverOpen(false);
                                }}
                              >
                                <Check className={cn("mr-2 h-4 w-4", editingDeal.contact === contact.id ? "opacity-100" : "opacity-0")} />
                                <div className="flex flex-col">
                                  <span>{contact.name}</span>
                                  {contact.email && (
                                    <span className="text-xs text-muted-foreground">{contact.email}</span>
                                  )}
                                </div>
                              </CommandItem>
                            ))}
                          </CommandGroup>
                        </CommandList>
                      </Command>
                    </PopoverContent>
                  </Popover>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="deal-priority">Priority</Label>
                  <Select
                    value={editingDeal.priority || "medium"}
                    onValueChange={(value) => setEditingDeal({ ...editingDeal, priority: value })}
                  >
                    <SelectTrigger id="deal-priority" data-testid="select-deal-priority">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {PRIORITY_OPTIONS.map((opt) => (
                        <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="deal-stage">Stage</Label>
                <Select
                  value={editingDeal.stage ?? editingDeal.stage_id ?? ""}
                  onValueChange={(value) => setEditingDeal({ ...editingDeal, stage: value })}
                >
                  <SelectTrigger id="deal-stage" data-testid="select-deal-stage">
                    <SelectValue placeholder="Select stage" />
                  </SelectTrigger>
                  <SelectContent>
                    {allStages.map((stage) => (
                      <SelectItem key={stage.id} value={stage.id}>
                        <div className="flex items-center gap-2">
                          <div className="w-3 h-3 rounded-full" style={{ backgroundColor: stage.color }} />
                          {stage.name}
                        </div>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label htmlFor="deal-close-date">Expected Close Date</Label>
                <Input
                  id="deal-close-date"
                  type="date"
                  value={editingDeal.expected_close_date || ""}
                  onChange={(e) => setEditingDeal({ ...editingDeal, expected_close_date: e.target.value })}
                  data-testid="input-deal-close-date"
                />
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => { setEditingDeal(null); setIsCreating(false); }}>
              Cancel
            </Button>
            <Button onClick={handleSaveDeal} disabled={isSaving || !editingDeal?.title.trim()} data-testid="button-save-deal">
              {isSaving ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Saving...
                </>
              ) : (
                isCreating ? "Create" : "Save"
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={commentDialogOpen} onOpenChange={(open) => { if (!open) handleCancelMove(); }}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{pendingMove?.isFollowup ? "Followup" : "Move Deal"}</DialogTitle>
            <DialogDescription>
              {pendingMove?.isFollowup 
                ? `Add a followup comment for "${pendingMove?.deal.title}"`
                : `Moving "${pendingMove?.deal.title}" to ${pendingMove?.targetStageName}`
              }
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            {pendingMove?.isFollowup && (() => {
              const currentStageId = pendingMove.deal.stage_id ?? pendingMove.deal.stage;
              const currentStageIndex = allStages.findIndex(s => s.id === currentStageId || s.name === currentStageId);
              const nextStages = allStages
                .filter(s => !s.is_won && !s.is_lost && !s.is_won_stage && !s.is_lost_stage)
                .filter(s => {
                  const stageIndex = allStages.findIndex(st => st.id === s.id);
                  return stageIndex > currentStageIndex;
                });
              
              return (
                <div className="space-y-2">
                  <Label htmlFor="followup-stage">Stage Selection *</Label>
                  <Select
                    value={followupStageSelection}
                    onValueChange={(value) => {
                      setFollowupStageSelection(value);
                      if (value === "stay") {
                        setPendingMove(prev => prev ? { ...prev, targetStageId: "", targetStageName: "" } : null);
                      } else {
                        const selectedStage = nextStages.find(s => s.id === value);
                        setPendingMove(prev => prev ? { ...prev, targetStageId: value, targetStageName: selectedStage?.name || "" } : null);
                      }
                    }}
                  >
                    <SelectTrigger id="followup-stage" data-testid="select-followup-stage">
                      <SelectValue placeholder="Select stage..." />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="stay">
                        <div className="flex items-center gap-2">
                          <div className="w-3 h-3 rounded-full bg-gray-400" />
                          Stay in current stage
                        </div>
                      </SelectItem>
                      {nextStages.length > 0 && (
                        <>
                          {nextStages.map((stage) => (
                            <SelectItem key={stage.id} value={stage.id}>
                              <div className="flex items-center gap-2">
                                <div className="w-3 h-3 rounded-full" style={{ backgroundColor: stage.color }} />
                                Move to {stage.name}
                              </div>
                            </SelectItem>
                          ))}
                        </>
                      )}
                    </SelectContent>
                  </Select>
                  {nextStages.length === 0 && followupStageSelection === "" && (
                    <p className="text-xs text-muted-foreground">No next stages available</p>
                  )}
                </div>
              );
            })()}
            <div className="space-y-2">
              <Label htmlFor="move-comment">
                Add a comment {pendingMove?.isFollowup ? "*" : "(optional)"}
              </Label>
              <Textarea
                id="move-comment"
                value={moveComment}
                onChange={(e) => setMoveComment(e.target.value)}
                placeholder={pendingMove?.isFollowup ? "What's the followup?" : "Why is this deal moving to this stage?"}
                data-testid="input-move-comment"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={handleCancelMove}>
              Cancel
            </Button>
            <Button 
              onClick={handleConfirmMove} 
              disabled={isSaving || (pendingMove?.isFollowup && (!moveComment.trim() || !followupStageSelection))} 
              data-testid="button-confirm-move"
            >
              {isSaving ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  {pendingMove?.isFollowup ? "Adding..." : "Moving..."}
                </>
              ) : (
                pendingMove?.isFollowup ? "Add Followup" : "Move"
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!viewingDeal} onOpenChange={(open) => { if (!open) { setViewingDeal(null); setIsContactExpanded(false); } }}>
        <DialogContent className="sm:max-w-2xl max-h-[80vh] overflow-hidden flex flex-col">
          <DialogHeader>
            <DialogTitle data-testid="text-deal-detail-title">{viewingDeal?.title}</DialogTitle>
            <DialogDescription>
              Stage: {viewingDeal?.stage_name || stages.find(s => s.id === (viewingDeal?.stage_id ?? viewingDeal?.stage))?.name || "Unknown"}
            </DialogDescription>
          </DialogHeader>
          <div className="flex-1 overflow-auto space-y-4">
            {viewingDeal?.description && (
              <p className="text-sm text-muted-foreground" data-testid="text-deal-detail-description">{viewingDeal.description}</p>
            )}
            <div>
              <span className="text-xs text-muted-foreground">Value</span>
              <p className="font-bold text-2xl text-primary" data-testid="text-deal-detail-value">
                {typeof viewingDeal?.value === "number" 
                  ? viewingDeal.value.toLocaleString(undefined, { style: "currency", currency: viewingDeal.currency || "USD", maximumFractionDigits: 0 }) 
                  : "--"}
              </p>
            </div>
            <div className="flex flex-col sm:flex-row gap-6 sm:gap-8">
              <div className="flex-1 space-y-3 text-sm">
                <div className="space-y-1">
                  <span className="text-muted-foreground">Priority</span>
                  <p className="font-semibold capitalize" data-testid="text-deal-detail-priority">{viewingDeal?.priority || "Medium"}</p>
                </div>
                <div className="space-y-1">
                  <span className="text-muted-foreground">Expected Close</span>
                  <p className="font-semibold flex items-center gap-1" data-testid="text-deal-detail-close-date">
                    <Calendar className="h-3 w-3" />
                    {viewingDeal?.expected_close_date || "Not set"}
                  </p>
                </div>
                {viewingDeal?.created_at && (
                  <div className="space-y-1">
                    <span className="text-muted-foreground">Created</span>
                    <p className="font-semibold flex items-center gap-1" data-testid="text-deal-detail-created-date">
                      <Calendar className="h-3 w-3" />
                      {new Date(viewingDeal.created_at).toLocaleDateString()}
                    </p>
                  </div>
                )}
              </div>
              <div className="w-full sm:w-48 shrink-0">
                {(() => {
                    const dealContact = viewingDeal?.contact 
                      ? contacts.find(c => c.id === viewingDeal.contact)
                      : null;
                    const contactEmail = dealContact?.email;
                    const contactPhone = dealContact?.phone;
                    const whatsappNumber = contactPhone?.replace(/[^0-9]/g, "");
                    const contactName = viewingDeal?.contact_name || dealContact?.name;
                    
                    if (!contactName) {
                      return (
                        <div className="bg-muted/50 rounded-lg border border-border p-4 flex flex-col items-center justify-center text-center">
                          <User className="h-8 w-8 text-muted-foreground mb-2" />
                          <p className="text-sm text-muted-foreground" data-testid="text-deal-detail-contact">No contact</p>
                        </div>
                      );
                    }

                    return (
                      <div
                        className="h-32 cursor-pointer [perspective:1000px]"
                        onClick={() => setIsContactExpanded(!isContactExpanded)}
                        data-testid="button-deal-contact-card"
                      >
                        <div
                          className={`relative w-full h-full transition-transform duration-500 [transform-style:preserve-3d] ${
                            isContactExpanded ? "[transform:rotateY(180deg)]" : ""
                          }`}
                        >
                          <div className="absolute inset-0 bg-muted/50 rounded-lg border border-border p-3 [backface-visibility:hidden] flex flex-col items-center justify-center text-center">
                            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary text-primary-foreground font-semibold text-sm mb-2">
                              {contactName.charAt(0).toUpperCase()}
                            </div>
                            <p className="font-medium text-sm truncate w-full" data-testid="text-deal-detail-contact">
                              {contactName}
                            </p>
                            <p className="text-xs text-muted-foreground mt-1">Click to see details</p>
                          </div>

                          <div className="absolute inset-0 bg-muted/50 rounded-lg border border-border p-3 [backface-visibility:hidden] [transform:rotateY(180deg)] flex flex-col items-center justify-center text-center">
                            <p className="font-medium text-sm mb-2">{contactName}</p>
                            <div className="space-y-1.5 w-full">
                              {contactEmail && (
                                <a
                                  href={`mailto:${contactEmail}`}
                                  onClick={(e) => e.stopPropagation()}
                                  className="flex items-center justify-center gap-2 text-xs text-primary hover:underline"
                                  data-testid="link-deal-contact-email"
                                >
                                  <Mail className="h-3.5 w-3.5" />
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
                                  data-testid="link-deal-contact-whatsapp"
                                >
                                  <MessageCircle className="h-3.5 w-3.5" />
                                  <span>{contactPhone}</span>
                                </a>
                              )}
                              {!contactEmail && !contactPhone && (
                                <p className="text-xs text-muted-foreground">No contact details available</p>
                              )}
                            </div>
                            <p className="text-xs text-muted-foreground mt-2">Click to flip back</p>
                          </div>
                        </div>
                      </div>
                    );
                  })()}
              </div>
            </div>
            <div className="border-t pt-4">
              <div className="flex gap-2 mb-4">
                <Button 
                  size="sm" 
                  variant="outline" 
                  className="flex-1 text-red-600 hover:text-red-700 hover:bg-red-50 dark:hover:bg-red-950 border-red-200"
                  onClick={() => viewingDeal && handleMarkLost(viewingDeal)}
                  data-testid="button-detail-lost"
                >
                  <XCircle className="h-4 w-4 mr-2" />
                  Lost
                </Button>
                <Button 
                  size="sm" 
                  variant="outline" 
                  className="flex-1 text-blue-600 hover:text-blue-700 hover:bg-blue-50 dark:hover:bg-blue-950 border-blue-200"
                  onClick={() => viewingDeal && handleProgress(viewingDeal)}
                  data-testid="button-detail-followup"
                >
                  <ArrowRight className="h-4 w-4 mr-2" />
                  Followup
                </Button>
                <Button 
                  size="sm" 
                  variant="outline" 
                  className="flex-1 text-green-600 hover:text-green-700 hover:bg-green-50 dark:hover:bg-green-950 border-green-200"
                  onClick={() => viewingDeal && handleMarkWon(viewingDeal)}
                  data-testid="button-detail-won"
                >
                  <Trophy className="h-4 w-4 mr-2" />
                  Won
                </Button>
              </div>
            </div>
            <div className="border-t pt-4">
              <h4 className="text-sm font-semibold flex items-center gap-2 mb-3">
                <MessageSquare className="h-4 w-4" />
                Comments ({viewingDeal?.comments?.length || 0})
              </h4>
              <div className="space-y-3 max-h-[200px] overflow-auto">
                {viewingDeal?.comments && viewingDeal.comments.length > 0 ? (
                  viewingDeal.comments.map((comment) => (
                    <div key={comment.id} className="bg-muted/50 rounded-lg p-3 text-sm" data-testid={`comment-${comment.id}`}>
                      <div className="flex items-center justify-between mb-1">
                        <span className="font-medium">{comment.author_name || "System"}</span>
                        <span className="text-xs text-muted-foreground">
                          {new Date(comment.created_at).toLocaleDateString()}
                        </span>
                      </div>
                      <p>{comment.text}</p>
                      {comment.type === "stage_change" && comment.from_stage && comment.to_stage && (
                        <p className="text-xs text-muted-foreground mt-1">
                          Stage changed: {comment.from_stage} → {comment.to_stage}
                        </p>
                      )}
                    </div>
                  ))
                ) : (
                  <p className="text-sm text-muted-foreground">No comments yet</p>
                )}
              </div>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );

  if (isEmbedded) {
    return (
      <div className="p-4 space-y-4">
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div>
            <h1 className="text-xl font-semibold">Deals</h1>
            <p className="text-sm text-muted-foreground">Manage your sales pipeline</p>
          </div>
          <Button onClick={() => handleAddDeal()} data-testid="button-add-deal">
            <Plus className="h-4 w-4 mr-2" />
            New Deal
          </Button>
        </div>
        {content}
      </div>
    );
  }

  return (
    <PageLayout
      title="Deals"
      description="Manage your sales pipeline and opportunities"
      metrics={metrics}
      ctaLabel="New Deal"
      ctaIcon={Plus}
      onCtaClick={() => handleAddDeal()}
      ctaTestId="button-add-deal"
      showSidebarTrigger={false}
      headerAction={
        <div className="flex gap-2">
          <Link href="/deals/analytics">
            <Button variant="outline" size="sm" data-testid="button-deals-analytics">
              <BarChart3 className="h-4 w-4 mr-2" />
              Analytics
            </Button>
          </Link>
          <Link href="/deals/manager">
            <Button variant="outline" size="sm" data-testid="button-deals-manager">
              <Settings2 className="h-4 w-4 mr-2" />
              Manager
            </Button>
          </Link>
        </div>
      }
    >
      {content}
    </PageLayout>
  );
}
