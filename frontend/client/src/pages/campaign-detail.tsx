import { useQuery } from "@tanstack/react-query";
import { useRoute, Link } from "wouter";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ChevronLeft, MessageSquare, Users, Play, Activity } from "lucide-react";
import { PageLayout } from "@/components/layout/page-layout";
import { EmptyState } from "@/components/empty-state";
import { ErrorDisplay } from "@/components/error-display";
import { CampaignLiveMonitor } from "@/components/campaign-live-monitor";
import { fetchJson } from "@/lib/queryClient";
import { apiV1 } from "@/lib/api";
import type { CampaignDetail as CampaignRecord, CampaignStatus } from "@/lib/moio-types";

const statusColors: Record<CampaignStatus, "default" | "secondary" | "outline" | "destructive"> = {
  draft: "outline",
  ready: "default",
  scheduled: "secondary",
  active: "default",
  ended: "secondary",
  archived: "outline",
};

function formatLabel(value?: string | null) {
  if (!value) return "—";
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

const CAMPAIGN_COLLECTION_PATH = apiV1("/campaigns/campaigns/");

export default function CampaignDetail() {
  const [, params] = useRoute("/campaigns/:id");
  const campaignId = params?.id;

  const campaignQuery = useQuery<CampaignRecord>({
    queryKey: [CAMPAIGN_COLLECTION_PATH, campaignId],
    queryFn: async () => {
      return await fetchJson<CampaignRecord>(apiV1(`/campaigns/campaigns/${campaignId}/`));
    },
    enabled: Boolean(campaignId),
  });

  const campaign = campaignQuery.data;

  if (!campaignId) {
    return (
      <PageLayout title="Campaign Not Found">
        <EmptyState
          title="Campaign not found"
          description="The requested campaign does not exist."
        />
      </PageLayout>
    );
  }

  return (
    <PageLayout
      title={campaign?.name || "Campaign Details"}
      description="Configuración de campaña"
      className="max-w-7xl"
    >
      {/* Back Button */}
      <div className="mb-4">
        <Link href="/campaigns">
          <Button variant="ghost" size="sm" className="gap-2" data-testid="button-back">
            <ChevronLeft className="h-4 w-4" />
            Volver a Campañas
          </Button>
        </Link>
      </div>

      {campaignQuery.isLoading ? (
        <EmptyState
          title="Loading campaign"
          description="Fetching campaign details..."
          isLoading
        />
      ) : campaignQuery.isError ? (
        <ErrorDisplay
          error={campaignQuery.error}
          endpoint={`api/v1/campaigns/${campaignId}`}
        />
      ) : !campaign ? (
        <EmptyState
          title="Campaign not found"
          description="The requested campaign does not exist."
        />
      ) : (
        <div className="space-y-6">
          {/* Campaign Header */}
          <div className="p-6 rounded-lg border border-border bg-card">
            <div className="flex items-start justify-between gap-4 mb-4">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-2 flex-wrap">
                  <Badge variant="outline" className="text-xs capitalize">
                    {formatLabel(campaign.kind)}
                  </Badge>
                  <span className="text-xs text-muted-foreground flex items-center gap-1">
                    <MessageSquare className="h-3 w-3 text-green-500" />
                    {formatLabel(campaign.channel)}
                  </span>
                  {campaign.audience_name && (
                    <span className="text-xs text-muted-foreground flex items-center gap-1">
                      <Users className="h-3 w-3" />
                      {campaign.audience_name}
                    </span>
                  )}
                  {(campaign.audience_size ?? 0) > 0 && (
                    <span className="text-xs text-muted-foreground">
                      {campaign.audience_size?.toLocaleString()} recipients
                    </span>
                  )}
                  {campaign.ready_to_launch && (
                    <Badge variant="secondary" className="text-[10px] h-5 px-2">
                      Ready to launch
                    </Badge>
                  )}
                </div>
                <h1 className="text-xl font-semibold mb-2 break-words">{campaign.name}</h1>
                {campaign.description && (
                  <p className="text-sm text-muted-foreground">{campaign.description}</p>
                )}
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <Badge variant={statusColors[campaign.status] || "secondary"} className="capitalize">
                  {formatLabel(campaign.status)}
                </Badge>
                <Button size="sm" variant="secondary" disabled data-testid="button-validate">
                  Validar
                </Button>
                <Button size="sm" data-testid="button-launch" disabled>
                  <Play className="h-4 w-4 mr-2" />
                  Lanzar
                </Button>
              </div>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="text-center">
                <div className="text-2xl font-bold text-blue-500">{campaign.sent ?? 0}</div>
                <div className="text-xs text-muted-foreground">Enviados</div>
              </div>
              <div className="text-center">
                <div className="text-2xl font-bold text-green-500">{campaign.opened ?? 0}</div>
                <div className="text-xs text-muted-foreground">Abiertos</div>
              </div>
              <div className="text-center">
                <div className="text-2xl font-bold text-red-500">{campaign.responded ?? 0}</div>
                <div className="text-xs text-muted-foreground">Respondidos</div>
              </div>
              <div className="text-center">
                <div className="text-2xl font-bold">
                  {campaign.open_rate !== undefined && campaign.open_rate !== null
                    ? `${campaign.open_rate.toFixed(1)}%`
                    : "—"}
                </div>
                <div className="text-xs text-muted-foreground">Open rate</div>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
            <div className="space-y-4 xl:col-span-2">
              <div className="p-6 rounded-lg border border-border bg-card space-y-4">
                <div>
                  <h3 className="font-semibold text-base mb-4">Información Básica</h3>
                  <div className="grid grid-cols-2 gap-4 text-sm">
                    <div>
                      <p className="text-muted-foreground">Nombre</p>
                      <p className="font-medium">{campaign.name}</p>
                    </div>
                    <div>
                      <p className="text-muted-foreground">Tipo</p>
                      <p>{formatLabel(campaign.kind)}</p>
                    </div>
                    <div>
                      <p className="text-muted-foreground">Canal</p>
                      <p>{formatLabel(campaign.channel)}</p>
                    </div>
                    <div>
                      <p className="text-muted-foreground">Estado</p>
                      <p className="capitalize">{formatLabel(campaign.status)}</p>
                    </div>
                  </div>
                </div>

                <div className="pt-4 border-t">
                  <h3 className="font-semibold text-base mb-4">Estado de Configuración</h3>
                  {campaign.configuration_state ? (
                    <div className="grid grid-cols-2 gap-3">
                      {Object.entries(campaign.configuration_state).map(([key, value]) => (
                        <div key={key} className="flex items-center justify-between text-sm p-2 rounded-md border">
                          <span className="text-muted-foreground">{formatLabel(key)}</span>
                          <Badge variant={value ? "secondary" : "outline"} className="text-[10px] uppercase">
                            {value ? "Completo" : "Pendiente"}
                          </Badge>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <EmptyState
                      title="Sin estado disponible"
                      description="Los pasos de configuración aparecerán aquí."
                    />
                  )}
                </div>
              </div>

              <div className="p-6 rounded-lg border border-border bg-card space-y-6">
                <h3 className="font-semibold text-base">Configuración del Builder</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div>
                    <p className="text-sm font-medium mb-2">Plantilla seleccionada</p>
                    {campaign.config?.message?.template_name || campaign.config?.message?.template_id ? (
                      <div className="text-sm">
                        <p className="font-semibold">
                          {campaign.config?.message?.template_name || campaign.config?.message?.template_id}
                        </p>
                        {Array.isArray(campaign.config?.message?.map) && (
                          <p className="text-muted-foreground text-xs mt-1">
                            {campaign.config?.message?.map?.length} mapeos definidos
                          </p>
                        )}
                      </div>
                    ) : (
                      <EmptyState
                        title="Sin plantilla"
                        description="Asocia una plantilla de WhatsApp para continuar."
                      />
                    )}
                  </div>
                  <div>
                    <p className="text-sm font-medium mb-2">Valores predeterminados</p>
                    {campaign.config?.defaults && Object.keys(campaign.config.defaults).length > 0 ? (
                      <div className="space-y-2 text-sm">
                        {Object.entries(campaign.config.defaults).map(([key, value]) => (
                          <div key={key} className="flex items-center justify-between">
                            <span className="text-muted-foreground">{formatLabel(key)}</span>
                            <span className="font-medium">{typeof value === "boolean" ? (value ? "Sí" : "No") : String(value)}</span>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <EmptyState
                        title="Sin preferencias"
                        description="Los toggles del builder se mostrarán cuando se guarden."
                      />
                    )}
                  </div>
                </div>
              </div>
            </div>

            <div className="space-y-4">
              {(campaign.status === "active" || campaign.status === "scheduled") && (
                <div className="p-6 rounded-lg border border-border bg-card">
                  <CampaignLiveMonitor
                    campaignId={campaignId}
                    enabled={campaign.status === "active" || campaign.status === "scheduled"}
                  />
                </div>
              )}

              <div className="p-6 rounded-lg border border-border bg-card space-y-3">
                <h3 className="font-semibold text-base">Audiencia</h3>
                <div className="text-sm">
                  <p className="text-muted-foreground">Nombre</p>
                  <p className="font-medium">{campaign.audience_name || "Sin asignar"}</p>
                </div>
                <div className="text-sm">
                  <p className="text-muted-foreground">Tipo</p>
                  <p>{campaign.audience_kind ? formatLabel(campaign.audience_kind) : "—"}</p>
                </div>
                <div className="text-sm">
                  <p className="text-muted-foreground">Tamaño</p>
                  <p>{campaign.audience_size ? campaign.audience_size.toLocaleString() : "—"}</p>
                </div>
              </div>

              <div className="p-6 rounded-lg border border-border bg-card space-y-4">
                <h3 className="font-semibold text-base">Programación</h3>
                <div className="text-sm">
                  <p className="text-muted-foreground">Fecha configurada</p>
                  <p>
                    {campaign.config?.schedule?.date
                      ? new Date(campaign.config.schedule.date).toLocaleString()
                      : "No programada"}
                  </p>
                </div>
                <div className="space-y-2 text-sm border-t pt-3">
                  {[
                    { label: "Creada", value: campaign.created },
                    { label: "Actualizada", value: campaign.updated },
                  ].map(({ label, value }) => (
                    value ? (
                      <div key={label} className="flex justify-between">
                        <span className="text-muted-foreground">{label}</span>
                        <span className="font-medium">{new Date(value).toLocaleString()}</span>
                      </div>
                    ) : null
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </PageLayout>
  );
}
