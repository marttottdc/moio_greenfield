import { Link } from "wouter";
import { useQuery, useMutation } from "@tanstack/react-query";
import { GlassPanel } from "@/components/radiant/glass-panel";
import { Subheading } from "@/components/radiant/text";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { CheckSquare, Clock, ArrowRight } from "lucide-react";
import { fetchJson, apiRequest, queryClient } from "@/lib/queryClient";
import { apiV1 } from "@/lib/api";

interface TaskContent {
  description?: string;
  due_date?: string;
  priority?: number;
  status?: "open" | "in_progress" | "done";
}

interface Activity {
  id: string;
  title: string;
  kind: string;
  content: TaskContent;
  author?: string | null;
  created_at: string;
}

interface ActivitiesResponse {
  activities: Activity[];
  pagination: {
    total_items: number;
  };
}

const priorityColors: Record<number, string> = {
  1: "bg-gray-400",
  2: "bg-blue-400",
  3: "bg-amber-400",
  4: "bg-orange-500",
  5: "bg-red-500",
};

function formatDueDate(dateString?: string): string {
  if (!dateString) return "";
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = date.getTime() - now.getTime();
  const diffDays = Math.ceil(diffMs / 86400000);
  
  if (diffDays < 0) return "Overdue";
  if (diffDays === 0) return "Today";
  if (diffDays === 1) return "Tomorrow";
  if (diffDays < 7) return `${diffDays} days`;
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

export function MyTasksWidget() {
  const activitiesPath = apiV1("/activities/");
  const dashboardQueryKey = ["activities", "dashboard-tasks"];
  
  const { data, isLoading } = useQuery<ActivitiesResponse>({
    queryKey: dashboardQueryKey,
    queryFn: () => fetchJson<ActivitiesResponse>(activitiesPath, {
      kind: "task",
      page_size: 5,
      sort_by: "created_at",
      order: "desc",
    }),
    staleTime: 60000,
  });

  const toggleMutation = useMutation({
    mutationFn: async ({ id, currentContent }: { id: string; currentContent: TaskContent }) => {
      const newStatus = currentContent.status === "done" ? "open" : "done";
      return apiRequest("PATCH", `${activitiesPath}${id}/`, { 
        data: { content: { ...currentContent, status: newStatus } } 
      });
    },
    onMutate: async ({ id, currentContent }) => {
      await queryClient.cancelQueries({ queryKey: dashboardQueryKey });
      const previousData = queryClient.getQueryData<ActivitiesResponse>(dashboardQueryKey);
      
      if (previousData) {
        const newStatus = currentContent.status === "done" ? "open" : "done";
        queryClient.setQueryData<ActivitiesResponse>(dashboardQueryKey, {
          ...previousData,
          activities: previousData.activities.map((a) =>
            a.id === id
              ? { ...a, content: { ...a.content, status: newStatus } }
              : a
          ),
        });
      }
      return { previousData };
    },
    onError: (_error, _variables, context) => {
      if (context?.previousData) {
        queryClient.setQueryData(dashboardQueryKey, context.previousData);
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["activities"] });
    },
  });

  const pendingTasks = data?.activities?.filter(
    (a) => (a.content as TaskContent).status !== "done"
  ) || [];

  return (
    <GlassPanel className="p-6" data-testid="widget-my-tasks">
      <div className="flex items-center justify-between mb-4">
        <Subheading className="flex items-center gap-2">
          <CheckSquare className="h-4 w-4" />
          My Tasks
        </Subheading>
        <Link href="/activities">
          <Button variant="ghost" size="sm" className="text-xs" data-testid="link-view-all-tasks">
            View All
            <ArrowRight className="h-3 w-3 ml-1" />
          </Button>
        </Link>
      </div>

      {isLoading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-12 w-full" />
          ))}
        </div>
      ) : pendingTasks.length === 0 ? (
        <div className="text-center py-6 text-muted-foreground text-sm">
          <CheckSquare className="h-8 w-8 mx-auto mb-2 opacity-50" />
          <p>No pending tasks</p>
          <Link href="/activities">
            <Button variant="ghost" size="sm" className="mt-2">
              Create a task
            </Button>
          </Link>
        </div>
      ) : (
        <div className="space-y-2">
          {pendingTasks.slice(0, 5).map((task) => {
            const content = task.content as TaskContent;
            const isDone = content.status === "done";
            
            return (
              <div
                key={task.id}
                className="flex items-center gap-3 p-2 rounded-md hover-elevate"
                data-testid={`dashboard-task-${task.id}`}
              >
                <button
                  onClick={() => toggleMutation.mutate({ 
                    id: task.id, 
                    currentContent: content
                  })}
                  disabled={toggleMutation.isPending}
                  className={`h-5 w-5 rounded border-2 flex items-center justify-center transition-colors shrink-0 ${
                    isDone
                      ? "bg-green-500 border-green-500 text-white"
                      : "border-muted-foreground/50 hover:border-primary"
                  }`}
                  data-testid={`checkbox-dashboard-task-${task.id}`}
                >
                  {isDone && <CheckSquare className="h-3 w-3" />}
                </button>
                
                <div className="flex-1 min-w-0">
                  <p className={`text-sm truncate ${isDone ? "line-through text-muted-foreground" : ""}`}>
                    {task.title}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    By <span className="text-foreground">{task.author ?? "—"}</span>
                  </p>
                  <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    {content.priority && (
                      <span className={`w-2 h-2 rounded-full ${priorityColors[content.priority]}`} />
                    )}
                    {content.due_date && (
                      <span className="flex items-center gap-1">
                        <Clock className="h-3 w-3" />
                        {formatDueDate(content.due_date)}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
          
          {(data?.pagination?.total_items || 0) > 5 && (
            <Link href="/activities">
              <Button variant="ghost" size="sm" className="w-full text-xs mt-2">
                View {(data?.pagination?.total_items || 0) - 5} more tasks
              </Button>
            </Link>
          )}
        </div>
      )}
    </GlassPanel>
  );
}
