import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { MessageSquare, Search, Plus, Users, MoreVertical } from "lucide-react";
import { PageLayout } from "@/components/layout/page-layout";
import { EmptyState } from "@/components/empty-state";
import { ErrorDisplay } from "@/components/error-display";
import { fetchJson } from "@/lib/queryClient";
import { apiV1 } from "@/lib/api";
import { Link } from "wouter";
import { CampaignWizard } from "@/components/campaign-wizard";
import { CampaignWizardV2, ResumeCampaignData } from "@/components/campaign-wizard-v2";
import type { Campaign as CampaignRecord, CampaignStatus, CampaignChannel, CampaignDetail } from "@/lib/moio-types";
import { PlayCircle } from "lucide-react";
import { useToast } from "@/hooks/use-toast";

const statusColors: Record<CampaignStatus, "default" | "secondary" | "outline" | "destructive"> = {
  draft: "outline",
  ready: "default",
  scheduled: "secondary",
  active: "default",
  ended: "secondary",
  archived: "outline",
};

const channelFilterOptions: Array<{ label: string; value: "all" | CampaignChannel }> = [
  { label: "All Channels", value: "all" },
  { label: "Email", value: "email" },
  { label: "WhatsApp", value: "whatsapp" },
  { label: "Telegram", value: "telegram" },
  { label: "SMS", value: "sms" },
];

const statusFilterOptions: Array<{ label: string; value: "all" | CampaignStatus }> = [
  { label: "All Statuses", value: "all" },
  { label: "Draft", value: "draft" },
  { label: "Ready", value: "ready" },
  { label: "Scheduled", value: "scheduled" },
  { label: "Active", value: "active" },
  { label: "Ended", value: "ended" },
  { label: "Archived", value: "archived" },
];

function formatLabel(value?: string | null) {
  if (!value) return "—";
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

const CAMPAIGNS_PATH = apiV1("/campaigns/campaigns/");

export default function Campaigns() {
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | CampaignStatus>("all");
  const [channelFilter, setChannelFilter] = useState<"all" | CampaignChannel>("all");
  const [activeTab, setActiveTab] = useState<"campaigns" | "audiences" | "templates" | "analytics" | "whatsapp">("campaigns");
  const [wizardOpen, setWizardOpen] = useState(false);
  const [wizardV2Open, setWizardV2Open] = useState(false);
  const [resumeCampaign, setResumeCampaign] = useState<ResumeCampaignData | null>(null);
  const [isLoadingResume, setIsLoadingResume] = useState<string | null>(null);
  const { toast } = useToast();

  const campaignsQuery = useQuery<CampaignRecord[]>({
    queryKey: [CAMPAIGNS_PATH, { status: statusFilter, channel: channelFilter, search: searchQuery }],
    queryFn: async () => {
      const params: Record<string, string> = {};
      if (statusFilter && statusFilter !== "all") {
        params.status = statusFilter;
      }
      if (channelFilter && channelFilter !== "all") {
        params.channel = channelFilter;
      }
      if (searchQuery) {
        params.search = searchQuery;
      }
      return await fetchJson<CampaignRecord[]>(CAMPAIGNS_PATH, params);
    },
  });

  const campaigns = campaignsQuery.data ?? [];

  const handleResumeCampaign = async (campaignId: string) => {
    setIsLoadingResume(campaignId);
    try {
      const detail = await fetchJson<CampaignDetail>(`${CAMPAIGNS_PATH}${campaignId}/`);
      const supportedChannels = ["whatsapp", "email", "sms"] as const;
      const channel = supportedChannels.includes(detail.channel as typeof supportedChannels[number])
        ? (detail.channel as "whatsapp" | "email" | "sms")
        : "whatsapp";
      
      const mappings = detail.config?.message?.map?.map((m) => ({
        source: String(m.source ?? ""),
        target: String(m.target ?? ""),
      }));
      
      const messageConfig = detail.config?.message as Record<string, unknown> | undefined;
      const templateId = messageConfig?.whatsapp_template_id as string | undefined 
        || messageConfig?.template_id as string | undefined 
        || "";
      const templateName = messageConfig?.whatsapp_template_name as string | undefined 
        || messageConfig?.template_name as string | undefined 
        || "";
      
      setResumeCampaign({
        id: detail.id,
        name: detail.name,
        description: detail.description,
        channel,
        kind: detail.kind,
        config: {
          message: detail.config?.message ? {
            template_id: templateId,
            template_name: templateName,
            map: mappings,
          } : undefined,
          schedule: detail.config?.schedule,
        },
        configuration_state: detail.configuration_state,
      });
      setWizardV2Open(true);
    } catch (error) {
      console.error("Failed to load campaign details:", error);
      toast({
        variant: "destructive",
        title: "Error loading campaign",
        description: "Could not load campaign details. Please try again.",
      });
    } finally {
      setIsLoadingResume(null);
    }
  };

  const handleWizardClose = (open: boolean) => {
    setWizardV2Open(open);
    if (!open) {
      setResumeCampaign(null);
    }
  };

  return (
    <>
      <CampaignWizard open={wizardOpen} onOpenChange={setWizardOpen} />
      <CampaignWizardV2 open={wizardV2Open} onOpenChange={handleWizardClose} resumeCampaign={resumeCampaign} />
      
      <PageLayout
        title="Campañas"
        description="Administra tus campañas de marketing"
        headerAction={
          <Button onClick={() => setWizardV2Open(true)} data-testid="button-new-campaign">
            <Plus className="w-4 h-4 mr-2" />
            Nueva Campaña
          </Button>
        }
      >
      {/* Tabs */}
      <div className="flex items-center gap-1 border-b mb-6">
        <button
          onClick={() => setActiveTab("campaigns")}
          className={`px-4 py-2.5 text-sm font-medium transition-colors ${
            activeTab === "campaigns"
              ? "border-b-2 border-primary -mb-px text-primary"
              : "text-muted-foreground hover-elevate rounded-t-md"
          }`}
          data-testid="tab-campaigns"
        >
          Campañas
        </button>
        <button
          onClick={() => setActiveTab("audiences")}
          className={`px-4 py-2.5 text-sm font-medium transition-colors ${
            activeTab === "audiences"
              ? "border-b-2 border-primary -mb-px text-primary"
              : "text-muted-foreground hover-elevate rounded-t-md"
          }`}
          data-testid="tab-audiences"
        >
          Audiencias
        </button>
        <button
          onClick={() => setActiveTab("templates")}
          className={`px-4 py-2.5 text-sm font-medium transition-colors ${
            activeTab === "templates"
              ? "border-b-2 border-primary -mb-px text-primary"
              : "text-muted-foreground hover-elevate rounded-t-md"
          }`}
          data-testid="tab-templates"
        >
          Plantillas
        </button>
        <button
          onClick={() => setActiveTab("analytics")}
          className={`px-4 py-2.5 text-sm font-medium transition-colors ${
            activeTab === "analytics"
              ? "border-b-2 border-primary -mb-px text-primary"
              : "text-muted-foreground hover-elevate rounded-t-md"
          }`}
          data-testid="tab-analytics"
        >
          Análisis
        </button>
        <button
          onClick={() => setActiveTab("whatsapp")}
          className={`px-4 py-2.5 text-sm font-medium transition-colors ${
            activeTab === "whatsapp"
              ? "border-b-2 border-primary -mb-px text-primary"
              : "text-muted-foreground hover-elevate rounded-t-md"
          }`}
          data-testid="tab-whatsapp"
        >
          Plantillas de WhatsApp
        </button>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-3 mb-6 flex-wrap">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
          <Input
            placeholder="Search campaigns..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-10"
            data-testid="input-search"
          />
        </div>
        <Select value={statusFilter} onValueChange={(value) => setStatusFilter(value as "all" | CampaignStatus)}>
          <SelectTrigger className="w-48" data-testid="select-status">
            <SelectValue placeholder="All Statuses" />
          </SelectTrigger>
          <SelectContent>
            {statusFilterOptions.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={channelFilter} onValueChange={(value) => setChannelFilter(value as "all" | CampaignChannel)}>
          <SelectTrigger className="w-48" data-testid="select-channel">
            <SelectValue placeholder="All Channels" />
          </SelectTrigger>
          <SelectContent>
            {channelFilterOptions.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Content based on active tab */}
      {activeTab === "campaigns" && (
        <>
          {campaignsQuery.isLoading ? (
            <EmptyState
              title="Loading campaigns"
              description="Fetching campaigns from the backend..."
              isLoading
            />
          ) : campaignsQuery.isError ? (
            <ErrorDisplay
              error={campaignsQuery.error}
              endpoint="api/v1/campaigns"
            />
          ) : campaigns.length === 0 ? (
            <EmptyState
              title="No campaigns found"
              description={searchQuery || statusFilter !== "all" || channelFilter !== "all" ? "Try adjusting your filters." : "Create your first campaign to get started."}
            />
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
              {campaigns.map((campaign) => (
                <Link key={campaign.id} href={`/campaigns/${campaign.id}`}>
                  <div
                    className="p-4 rounded-lg border border-border bg-card hover-elevate active-elevate-2 cursor-pointer transition-all"
                    data-testid={`card-campaign-${campaign.id}`}
                  >
                    {/* Header */}
                    <div className="flex items-start justify-between gap-2 mb-3">
                      <div className="flex-1 min-w-0">
                        <h3 className="font-semibold text-sm mb-1 line-clamp-1" data-testid={`text-campaign-name-${campaign.id}`}>
                          {campaign.name}
                        </h3>
                        <p className="text-xs text-muted-foreground">{formatLabel(campaign.kind)}</p>
                      </div>
                      <div className="flex items-center gap-1.5 shrink-0">
                        <Badge variant={statusColors[campaign.status] || "secondary"} className="text-xs h-5 px-1.5 capitalize">
                          {formatLabel(campaign.status)}
                        </Badge>
                        {campaign.ready_to_launch && (
                          <Badge variant="secondary" className="text-[10px] h-5 px-2">
                            Ready to launch
                          </Badge>
                        )}
                        {campaign.status === "draft" && (
                          <Button
                            size="icon"
                            variant="ghost"
                            className="h-6 w-6"
                            disabled={isLoadingResume === campaign.id}
                            onClick={(e) => {
                              e.preventDefault();
                              e.stopPropagation();
                              handleResumeCampaign(campaign.id);
                            }}
                            data-testid={`button-continue-${campaign.id}`}
                          >
                            <PlayCircle className="h-3.5 w-3.5" />
                          </Button>
                        )}
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button
                              size="icon"
                              variant="ghost"
                              className="h-6 w-6"
                              onClick={(e) => {
                                e.preventDefault();
                                e.stopPropagation();
                              }}
                              data-testid={`button-more-${campaign.id}`}
                            >
                              <MoreVertical className="h-3.5 w-3.5" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end" onClick={(e) => e.stopPropagation()}>
                            {campaign.status === "draft" && (
                              <DropdownMenuItem
                                onClick={(e) => {
                                  e.preventDefault();
                                  handleResumeCampaign(campaign.id);
                                }}
                                data-testid={`menu-continue-${campaign.id}`}
                              >
                                <PlayCircle className="h-4 w-4 mr-2" />
                                Continuar configuración
                              </DropdownMenuItem>
                            )}
                            <DropdownMenuItem data-testid={`menu-view-${campaign.id}`}>
                              Ver detalles
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </div>
                    </div>

                    {/* Description */}
                    <p className="text-xs text-muted-foreground line-clamp-2 mb-3 min-h-[32px]">
                      {campaign.description || "No description provided"}
                    </p>

                    {/* Channel and Recipients */}
                    <div className="flex items-center justify-between mb-3 text-xs">
                      <div className="flex items-center gap-1.5">
                        <MessageSquare className="h-3.5 w-3.5 text-green-500" />
                        <span className="text-muted-foreground">{formatLabel(campaign.channel)}</span>
                      </div>
                      {(campaign.audience_size ?? 0) > 0 && (
                        <div className="flex items-center gap-1.5">
                          <Users className="h-3.5 w-3.5 text-muted-foreground" />
                          <span className="text-muted-foreground">
                            {campaign.audience_size?.toLocaleString()}{" "}
                            recipients
                          </span>
                        </div>
                      )}
                    </div>

                    {/* Metrics */}
                    <div className="grid grid-cols-3 gap-3 mb-3 py-3 border-y border-border/50">
                      <div className="text-center">
                        <div className="text-lg font-bold text-blue-500" data-testid={`text-sent-${campaign.id}`}>
                          {campaign.sent ?? 0}
                        </div>
                        <div className="text-xs text-muted-foreground">sent</div>
                      </div>
                      <div className="text-center">
                        <div className="text-lg font-bold text-green-500" data-testid={`text-opened-${campaign.id}`}>
                          {campaign.opened ?? 0}
                        </div>
                        <div className="text-xs text-muted-foreground">opened</div>
                      </div>
                      <div className="text-center">
                        <div className="text-lg font-bold" data-testid={`text-rate-${campaign.id}`}>
                          {campaign.open_rate !== undefined && campaign.open_rate !== null
                            ? `${campaign.open_rate.toFixed(1)}%`
                            : "—"}
                        </div>
                        <div className="text-xs text-muted-foreground">open rate</div>
                      </div>
                    </div>

                    {/* Date */}
                    {campaign.created && (
                      <div className="text-xs text-muted-foreground">
                        {new Date(campaign.created).toLocaleDateString('es-ES', { 
                          month: 'short', 
                          day: 'numeric', 
                          year: 'numeric' 
                        })}
                      </div>
                    )}
                  </div>
                </Link>
              ))}
            </div>
          )}
        </>
      )}

      {activeTab === "audiences" && (
        <EmptyState
          title="Audiencias"
          description="La sección de audiencias estará disponible próximamente."
        />
      )}

      {activeTab === "templates" && (
        <EmptyState
          title="Plantillas"
          description="La sección de plantillas estará disponible próximamente."
        />
      )}

      {activeTab === "analytics" && (
        <EmptyState
          title="Análisis"
          description="La sección de análisis estará disponible próximamente."
        />
      )}

      {activeTab === "whatsapp" && (
        <EmptyState
          title="Plantillas de WhatsApp"
          description="La sección de plantillas de WhatsApp estará disponible próximamente."
        />
      )}
      </PageLayout>
    </>
  );
}
