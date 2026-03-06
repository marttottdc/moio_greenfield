import { useQuery } from "@tanstack/react-query";
import { GlassPanel } from "@/components/radiant/glass-panel";
import { Subheading } from "@/components/radiant/text";
import { EmptyState } from "@/components/empty-state";
import { Badge } from "@/components/ui/badge";
import { fetchJson } from "@/lib/queryClient";
import { apiV1 } from "@/lib/api";
import type { AudienceRecord } from "@/lib/moio-types";

interface DashboardBundle {
  audiences?: AudienceRecord[];
}

function formatLabel(value?: string | null) {
  if (!value) return "—";
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function RecentAudiencesWidget() {
  const { data, isLoading } = useQuery<DashboardBundle>({
    queryKey: [apiV1("/campaigns/campaigns/dashboard/")],
    queryFn: () => fetchJson<DashboardBundle>(apiV1("/campaigns/campaigns/dashboard/")),
  });

  const audiences = data?.audiences?.slice(0, 4) ?? [];

  return (
    <GlassPanel className="p-6 h-full" data-testid="widget-recent-audiences">
      <Subheading className="mb-4">Recent Audiences</Subheading>
      {isLoading ? (
        <EmptyState
          title="Loading audiences"
          description="Syncing data from backend..."
          isLoading
        />
      ) : audiences.length === 0 ? (
        <EmptyState
          title="No audiences"
          description="Create static or dynamic audiences for reuse."
        />
      ) : (
        <div className="space-y-3 text-sm">
          {audiences.map((audience) => (
            <div
              key={audience.id}
              className="border rounded-lg p-3 hover-elevate"
              data-testid={`audience-item-${audience.id}`}
            >
              <p className="font-semibold">{audience.name}</p>
              <p className="text-xs text-muted-foreground">
                {formatLabel(audience.kind)} · {audience.size.toLocaleString()} contacts
              </p>
              <div className="mt-1">
                <Badge variant={audience.is_draft ? "outline" : "secondary"} className="text-xs">
                  {audience.is_draft ? "Draft" : "Ready"}
                </Badge>
              </div>
            </div>
          ))}
        </div>
      )}
    </GlassPanel>
  );
}
