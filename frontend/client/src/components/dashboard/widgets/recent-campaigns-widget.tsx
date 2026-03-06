import { useQuery } from "@tanstack/react-query";
import { GlassPanel } from "@/components/radiant/glass-panel";
import { Subheading } from "@/components/radiant/text";
import { EmptyState } from "@/components/empty-state";
import { Badge } from "@/components/ui/badge";
import { fetchJson } from "@/lib/queryClient";
import { apiV1 } from "@/lib/api";
import type { Campaign as CampaignRecord } from "@/lib/moio-types";

interface DashboardBundle {
  campaigns?: CampaignRecord[];
}

function formatLabel(value?: string | null) {
  if (!value) return "—";
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function RecentCampaignsWidget() {
  const { data, isLoading } = useQuery<DashboardBundle>({
    queryKey: [apiV1("/campaigns/campaigns/dashboard/")],
    queryFn: () => fetchJson<DashboardBundle>(apiV1("/campaigns/campaigns/dashboard/")),
  });

  const campaigns = data?.campaigns?.slice(0, 4) ?? [];

  return (
    <GlassPanel className="p-6 h-full" data-testid="widget-recent-campaigns">
      <Subheading className="mb-4">Recent Campaigns</Subheading>
      {isLoading ? (
        <EmptyState
          title="Loading campaigns"
          description="Fetching the latest data..."
          isLoading
        />
      ) : campaigns.length === 0 ? (
        <EmptyState
          title="No campaigns"
          description="Create a campaign to see it here."
        />
      ) : (
        <div className="space-y-3">
          {campaigns.map((campaign) => (
            <div
              key={campaign.id}
              className="flex items-center justify-between border rounded-lg p-3 hover-elevate"
              data-testid={`campaign-item-${campaign.id}`}
            >
              <div>
                <p className="font-semibold text-sm">{campaign.name}</p>
                <p className="text-xs text-muted-foreground">
                  {formatLabel(campaign.kind)} · {formatLabel(campaign.channel)}
                </p>
              </div>
              <div className="text-right">
                <Badge variant="secondary" className="capitalize">
                  {formatLabel(campaign.status)}
                </Badge>
                <p className="text-xs text-muted-foreground mt-1">
                  {campaign.audience_size
                    ? `${campaign.audience_size.toLocaleString()} recipients`
                    : "No audience"}
                </p>
              </div>
            </div>
          ))}
        </div>
      )}
    </GlassPanel>
  );
}
