import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "wouter";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { ScrollArea } from "@/components/ui/scroll-area";
import { PageLayout } from "@/components/layout/page-layout";
import { 
  ArrowLeft, Search, AlertTriangle, ArrowRight, Undo2, 
  Clock, Loader2, History, Filter, RefreshCw
} from "lucide-react";
import { fetchJson, apiRequest, queryClient } from "@/lib/queryClient";
import { apiV1 } from "@/lib/api";
import { useToast } from "@/hooks/use-toast";
import { format, formatDistanceToNow } from "date-fns";

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
  is_default?: boolean;
  stages: PipelineStage[];
}

interface DealComment {
  id: string;
  text: string;
  type?: string;
  from_stage?: string;
  to_stage?: string;
  author_name?: string;
  created_at: string;
}

interface Deal {
  id: string;
  title: string;
  description?: string;
  contact_name?: string;
  value?: number | null;
  currency?: string;
  stage?: string;
  stage_id?: string;
  stage_name?: string;
  priority?: string;
  status?: string;
  created_at?: string;
  updated_at?: string;
  comments?: DealComment[];
}

interface DealsResponse {
  deals?: Deal[];
  results?: Deal[];
}

interface PipelinesResponse {
  pipelines?: Pipeline[];
}

export default function DealManager() {
  const { toast } = useToast();
  const [searchQuery, setSearchQuery] = useState("");
  const [filterStage, setFilterStage] = useState<string>("all");
  const [selectedDeal, setSelectedDeal] = useState<Deal | null>(null);
  const [moveDialogOpen, setMoveDialogOpen] = useState(false);
  const [targetStageId, setTargetStageId] = useState<string>("");
  const [moveComment, setMoveComment] = useState("");
  const [isMoving, setIsMoving] = useState(false);

  const pipelinesQuery = useQuery<PipelinesResponse>({
    queryKey: [apiV1("/crm/deals/pipelines/")],
    queryFn: () => fetchJson<PipelinesResponse>(apiV1("/crm/deals/pipelines/")),
  });

  const dealsQuery = useQuery<DealsResponse>({
    queryKey: [apiV1("/crm/deals/"), "manager"],
    queryFn: () => fetchJson<DealsResponse>(apiV1("/crm/deals/")),
  });

  const pipelines = pipelinesQuery.data?.pipelines ?? [];
  const activePipeline = pipelines.find(p => p.is_default) || pipelines[0];
  const allStages = activePipeline?.stages?.sort((a, b) => a.order - b.order) ?? [];

  const deals = useMemo(() => {
    const data = dealsQuery.data;
    let rawDeals: Deal[] = [];
    if (Array.isArray(data)) {
      rawDeals = data;
    } else {
      rawDeals = data?.deals ?? data?.results ?? [];
    }
    return rawDeals.map(deal => ({
      ...deal,
      value: typeof deal.value === 'string' ? parseFloat(deal.value) : (deal.value || 0),
    }));
  }, [dealsQuery.data]);

  const getStageForDeal = (deal: Deal) => {
    const stageId = deal.stage_id ?? deal.stage;
    return allStages.find(s => s.id === stageId || s.name === stageId);
  };

  const getStageHistory = (deal: Deal) => {
    return (deal.comments || [])
      .filter(c => c.type === "stage_change")
      .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
  };

  const filteredDeals = useMemo(() => {
    return deals.filter(deal => {
      const matchesSearch = 
        deal.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
        (deal.contact_name?.toLowerCase().includes(searchQuery.toLowerCase()) ?? false) ||
        (deal.description?.toLowerCase().includes(searchQuery.toLowerCase()) ?? false);
      
      if (filterStage === "all") return matchesSearch;
      
      const stageId = deal.stage_id ?? deal.stage;
      return matchesSearch && (stageId === filterStage || deal.stage_name === filterStage);
    });
  }, [deals, searchQuery, filterStage]);

  const dealsWithHistory = useMemo(() => {
    return filteredDeals
      .map(deal => ({
        deal,
        history: getStageHistory(deal),
        currentStage: getStageForDeal(deal),
      }))
      .filter(item => item.history.length > 0)
      .sort((a, b) => {
        const aDate = a.history[0]?.created_at ? new Date(a.history[0].created_at).getTime() : 0;
        const bDate = b.history[0]?.created_at ? new Date(b.history[0].created_at).getTime() : 0;
        return bDate - aDate;
      });
  }, [filteredDeals, allStages]);

  const handleMoveDeal = (deal: Deal) => {
    setSelectedDeal(deal);
    setTargetStageId("");
    setMoveComment("");
    setMoveDialogOpen(true);
  };

  const handleConfirmMove = async () => {
    if (!selectedDeal || !targetStageId) return;
    
    setIsMoving(true);
    try {
      await apiRequest("POST", apiV1(`/crm/deals/${selectedDeal.id}/move-stage/`), {
        data: {
          stage_id: targetStageId,
          comment: moveComment || "Corrected stage via Deal Manager"
        }
      });
      
      toast({ title: "Success", description: "Deal moved to new stage successfully." });
      setMoveDialogOpen(false);
      setSelectedDeal(null);
      queryClient.invalidateQueries({ queryKey: [apiV1("/crm/deals/")] });
    } catch (error) {
      toast({ title: "Error", description: (error as Error).message, variant: "destructive" });
    } finally {
      setIsMoving(false);
    }
  };

  const handleRevertToPreviousStage = async (deal: Deal) => {
    const history = getStageHistory(deal);
    if (history.length === 0) return;
    
    const previousStageName = history[0].from_stage;
    const previousStage = allStages.find(s => s.name === previousStageName);
    
    if (!previousStage) {
      toast({ title: "Error", description: "Could not find the previous stage.", variant: "destructive" });
      return;
    }

    setSelectedDeal(deal);
    setTargetStageId(previousStage.id);
    setMoveComment(`Reverted from ${history[0].to_stage} back to ${previousStageName}`);
    setMoveDialogOpen(true);
  };

  const isLoading = pipelinesQuery.isLoading || dealsQuery.isLoading;

  if (isLoading) {
    return (
      <PageLayout title="Deal Manager" description="Fix incorrectly moved deals">
        <div className="space-y-4">
          {[1, 2, 3].map(i => (
            <Card key={i}>
              <CardContent className="pt-6">
                <Skeleton className="h-24" />
              </CardContent>
            </Card>
          ))}
        </div>
      </PageLayout>
    );
  }

  return (
    <PageLayout 
      title="Deal Manager" 
      description="Review and fix deals that were moved to incorrect stages"
    >
      <div className="mb-4 flex items-center justify-between gap-4 flex-wrap">
        <Link href="/deals">
          <Button variant="outline" size="sm" data-testid="button-back-to-deals">
            <ArrowLeft className="h-4 w-4 mr-2" />
            Back to Deals
          </Button>
        </Link>
        <Button 
          variant="outline" 
          size="sm" 
          onClick={() => dealsQuery.refetch()}
          data-testid="button-refresh"
        >
          <RefreshCw className="h-4 w-4 mr-2" />
          Refresh
        </Button>
      </div>

      <Card className="mb-6">
        <CardHeader className="pb-4">
          <CardTitle className="text-lg flex items-center gap-2">
            <Filter className="h-5 w-5" />
            Filters
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex gap-4 flex-wrap">
            <div className="flex-1 min-w-[200px]">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Search deals..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-9"
                  data-testid="input-search-deals"
                />
              </div>
            </div>
            <Select value={filterStage} onValueChange={setFilterStage}>
              <SelectTrigger className="w-[200px]" data-testid="select-filter-stage">
                <SelectValue placeholder="Filter by stage" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Stages</SelectItem>
                {allStages.map((stage) => (
                  <SelectItem key={stage.id} value={stage.id}>
                    {stage.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      <Card className="mb-6">
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <History className="h-5 w-5" />
            Deals with Stage History ({dealsWithHistory.length})
          </CardTitle>
          <CardDescription>
            These deals have been moved between stages. Click on a deal to view its history or move it to a different stage.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {dealsWithHistory.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <AlertTriangle className="h-12 w-12 mx-auto mb-4 opacity-50" />
              <p className="text-lg font-medium">No deals with stage history found</p>
              <p className="text-sm">Deals will appear here after they've been moved between stages.</p>
            </div>
          ) : (
            <ScrollArea className="h-[500px] pr-4">
              <div className="space-y-4">
                {dealsWithHistory.map(({ deal, history, currentStage }) => (
                  <div 
                    key={deal.id} 
                    className="p-4 rounded-lg border bg-card hover-elevate cursor-pointer"
                    onClick={() => handleMoveDeal(deal)}
                    data-testid={`card-deal-${deal.id}`}
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <h3 className="font-semibold truncate">{deal.title}</h3>
                          {deal.priority && deal.priority !== "medium" && (
                            <Badge variant={deal.priority === "urgent" || deal.priority === "high" ? "destructive" : "secondary"}>
                              {deal.priority}
                            </Badge>
                          )}
                        </div>
                        {deal.contact_name && (
                          <p className="text-sm text-muted-foreground mb-2">{deal.contact_name}</p>
                        )}
                        <div className="flex items-center gap-2 text-sm">
                          <Badge variant="outline" className="font-normal">
                            Current: {currentStage?.name || "Unknown"}
                          </Badge>
                          <span className="text-lg font-bold text-primary">
                            {typeof deal.value === "number" 
                              ? deal.value.toLocaleString(undefined, { style: "currency", currency: deal.currency || "USD", maximumFractionDigits: 0 }) 
                              : "--"}
                          </span>
                        </div>
                      </div>
                      <div className="flex gap-2 shrink-0">
                        {history.length > 0 && history[0].from_stage && (
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={(e) => {
                              e.stopPropagation();
                              handleRevertToPreviousStage(deal);
                            }}
                            data-testid={`button-revert-${deal.id}`}
                          >
                            <Undo2 className="h-4 w-4 mr-1" />
                            Revert
                          </Button>
                        )}
                        <Button
                          size="sm"
                          variant="default"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleMoveDeal(deal);
                          }}
                          data-testid={`button-move-${deal.id}`}
                        >
                          <ArrowRight className="h-4 w-4 mr-1" />
                          Move
                        </Button>
                      </div>
                    </div>
                    
                    <div className="mt-4 pt-4 border-t">
                      <p className="text-xs text-muted-foreground mb-2 flex items-center gap-1">
                        <Clock className="h-3 w-3" />
                        Recent stage changes:
                      </p>
                      <div className="space-y-2">
                        {history.slice(0, 3).map((change, idx) => (
                          <div key={change.id || idx} className="flex items-center gap-2 text-sm">
                            <span className="text-muted-foreground">{change.from_stage}</span>
                            <ArrowRight className="h-3 w-3 text-muted-foreground" />
                            <span className="font-medium">{change.to_stage}</span>
                            <span className="text-xs text-muted-foreground ml-auto">
                              {formatDistanceToNow(new Date(change.created_at), { addSuffix: true })}
                            </span>
                          </div>
                        ))}
                        {history.length > 3 && (
                          <p className="text-xs text-muted-foreground">
                            + {history.length - 3} more changes
                          </p>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </ScrollArea>
          )}
        </CardContent>
      </Card>

      <Dialog open={moveDialogOpen} onOpenChange={setMoveDialogOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Move Deal to New Stage</DialogTitle>
            <DialogDescription>
              Select the correct stage for "{selectedDeal?.title}"
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label>Current Stage</Label>
              <Badge variant="secondary" className="text-sm">
                {selectedDeal ? (getStageForDeal(selectedDeal)?.name || "Unknown") : "Unknown"}
              </Badge>
            </div>
            <div className="space-y-2">
              <Label htmlFor="target-stage">Move to Stage</Label>
              <Select value={targetStageId} onValueChange={setTargetStageId}>
                <SelectTrigger data-testid="select-target-stage">
                  <SelectValue placeholder="Select target stage" />
                </SelectTrigger>
                <SelectContent>
                  {allStages.map((stage) => (
                    <SelectItem 
                      key={stage.id} 
                      value={stage.id}
                      disabled={stage.id === (selectedDeal?.stage_id ?? selectedDeal?.stage)}
                    >
                      {stage.name}
                      {(stage.is_won || stage.is_won_stage) && " (Won)"}
                      {(stage.is_lost || stage.is_lost_stage) && " (Lost)"}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="move-comment">Comment (optional)</Label>
              <Textarea
                id="move-comment"
                value={moveComment}
                onChange={(e) => setMoveComment(e.target.value)}
                placeholder="Why is this deal being moved?"
                data-testid="input-move-comment"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setMoveDialogOpen(false)}>
              Cancel
            </Button>
            <Button 
              onClick={handleConfirmMove} 
              disabled={!targetStageId || isMoving}
              data-testid="button-confirm-move"
            >
              {isMoving ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Moving...
                </>
              ) : (
                "Move Deal"
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </PageLayout>
  );
}
