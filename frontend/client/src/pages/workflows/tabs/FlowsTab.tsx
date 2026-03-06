
import { useMemo } from "react";
import { Plus, Layers, Zap, Clock, PlayCircle, Circle, Shield, CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { GlassPanel } from "@/components/radiant/glass-panel";
import { EmptyState } from "@/components/empty-state";
import { ErrorDisplay } from "@/components/error-display";
import { StatCard } from "../components/StatCard";
import type { Workflow, AutomationStats } from "../types";

interface FlowsTabProps {
  workflows: Workflow[];
  originalWorkflows: Workflow[];
  automationStats: AutomationStats;
  isLoading: boolean;
  isError: boolean;
  error: Error | null;
  onNewFlow: () => void;
  onEditFlow: (id: string) => void;
  timeline: Workflow[];
}

const formatTimestamp = (value?: string | null) => {
  if (!value) return "Never";
  const date = new Date(value);
  return `${date.toLocaleDateString()} • ${date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;
};

const getStatusColor = (status?: string) => {
  if (!status) return "text-foreground/40";
  const statusColorMap: Record<string, string> = {
    active: "text-emerald-500",
    live: "text-emerald-500",
    draft: "text-amber-500",
    paused: "text-amber-500",
    error: "text-red-500",
  };
  return statusColorMap[status.toLowerCase()] || "text-foreground/40";
};

export function FlowsTab({
  workflows,
  originalWorkflows,
  automationStats,
  isLoading,
  isError,
  error,
  onNewFlow,
  onEditFlow,
  timeline,
}: FlowsTabProps) {
  const hasWorkflows = originalWorkflows.length > 0;

  return (
    <div className="space-y-8">
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Total flows"
          value={automationStats.totalFlows.toString()}
          helper="All automation blueprints"
          icon={Layers}
          accent="bg-primary/10 text-primary"
        />
        <StatCard
          label="Active"
          value={automationStats.activeFlows.toString()}
          helper="Live & processing events"
          icon={Zap}
          accent="bg-emerald-100 text-emerald-600"
        />
        <StatCard
          label="Drafts"
          value={automationStats.draftFlows.toString()}
          helper="Need review before launch"
          icon={Clock}
          accent="bg-amber-100 text-amber-600"
        />
        <StatCard
          label="Runs"
          value={automationStats.totalRuns.toString()}
          helper="Total executions tracked"
          icon={PlayCircle}
          accent="bg-indigo-100 text-indigo-600"
        />
      </div>

      <div className="grid gap-6 xl:grid-cols-3">
        <GlassPanel className="p-6 xl:col-span-2 space-y-5">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <p className="text-xs uppercase tracking-wide text-muted-foreground">Automation library</p>
              <h2 className="text-xl font-semibold">Flows</h2>
            </div>
            <Button size="sm" onClick={onNewFlow} data-testid="button-create-first-flow">
              <Plus className="h-4 w-4 mr-2" />
              Create flow
            </Button>
          </div>
          {isLoading ? (
            <EmptyState title="Loading flows..." isLoading />
          ) : isError ? (
            <ErrorDisplay error={error ?? new Error("Unable to load flows")} endpoint="api/v1/flows" />
          ) : workflows.length === 0 ? (
            <EmptyState
              title="No flows match"
              description={hasWorkflows ? "Try a different search" : "Create your first automation to get started."}
            />
          ) : (
            <div className="space-y-3">
              {workflows.map((workflow) => (
                <GlassPanel
                  key={workflow.id}
                  className="p-4 hover-elevate cursor-pointer"
                  onClick={() => onEditFlow(workflow.id)}
                  data-testid={`card-workflow-${workflow.id}`}
                >
                  <div className="flex items-start justify-between">
                    <div>
                      <div className="flex items-center gap-3 flex-wrap">
                        <h3 className="font-semibold" data-testid={`text-workflow-name-${workflow.id}`}>
                          {workflow.name}
                        </h3>
                        <Badge variant="secondary" data-testid={`badge-status-${workflow.id}`}>
                          {workflow.status ?? "Draft"}
                        </Badge>
                        {workflow.latest_version?.is_published && (
                          <Badge 
                            variant={workflow.latest_version.is_active ? "default" : "outline"} 
                            className="text-xs"
                            data-testid={`badge-published-${workflow.id}`}
                          >
                            <CheckCircle2 className="h-3 w-3 mr-1" />
                            {workflow.latest_version.is_active ? "Live" : "Published"}
                          </Badge>
                        )}
                        {workflow.latest_version?.preview_armed && (
                          <Badge 
                            variant="outline" 
                            className="text-xs text-amber-600 border-amber-500"
                            data-testid={`badge-armed-${workflow.id}`}
                          >
                            <Shield className="h-3 w-3 mr-1" />
                            Armed
                          </Badge>
                        )}
                      </div>
                      <p className="text-sm text-muted-foreground mt-2">
                        {workflow.description ?? "No description provided"}
                      </p>
                      <div className="flex flex-wrap items-center gap-4 mt-3 text-xs text-muted-foreground">
                        <div className="flex items-center gap-1">
                          <PlayCircle className="h-3.5 w-3.5" />
                          {workflow.runs ?? 0} runs
                        </div>
                        <div className="flex items-center gap-1">
                          <Clock className="h-3.5 w-3.5" />
                          Updated {formatTimestamp(workflow.updated_at)}
                        </div>
                      </div>
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="gap-1"
                      onClick={(event) => {
                        event.stopPropagation();
                        onEditFlow(workflow.id);
                      }}
                      data-testid={`button-edit-${workflow.id}`}
                    >
                      Edit
                    </Button>
                  </div>
                </GlassPanel>
              ))}
            </div>
          )}
        </GlassPanel>

        <GlassPanel className="p-6 space-y-4">
          <div>
            <p className="text-xs uppercase tracking-wide text-muted-foreground">Latest activity</p>
            <h2 className="text-xl font-semibold">Timeline</h2>
          </div>
          {timeline.length === 0 ? (
            <EmptyState
              title="No activity"
              description="Publish or edit a flow to populate the timeline."
            />
          ) : (
            <div className="space-y-4">
              {timeline.map((flow) => (
                <div key={flow.id} className="flex items-start gap-3">
                  <div className="mt-1">
                    <Circle className={`h-3 w-3 ${getStatusColor(flow.status)}`} />
                  </div>
                  <div className="flex-1">
                    <p className="font-medium text-sm">{flow.name}</p>
                    <p className="text-xs text-muted-foreground">
                      {flow.status ?? "draft"} • {formatTimestamp(flow.updated_at)}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </GlassPanel>
      </div>
    </div>
  );
}
