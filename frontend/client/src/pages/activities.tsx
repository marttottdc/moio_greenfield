import { useState, useMemo, useEffect, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { useQuery, useMutation } from "@tanstack/react-query";
import { Link, useLocation } from "wouter";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Calendar } from "@/components/ui/calendar";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { 
  Search, 
  Plus, 
  Clock, 
  CheckSquare, 
  StickyNote, 
  Lightbulb, 
  CalendarDays,
  Loader2,
  Trash2,
  Edit,
  Eye,
  EyeOff,
  ChevronUp,
  ChevronDown,
  Calendar as CalendarIcon,
  Mail,
  Tag,
  Star,
  MapPin,
  Users,
  LayoutGrid,
  Table2
} from "lucide-react";
import { PageLayout } from "@/components/layout/page-layout";
import { EmptyState } from "@/components/empty-state";
import { ErrorDisplay } from "@/components/error-display";
import { GlobalTimeline } from "@/components/timeline/GlobalTimeline";
import { ReportActivityModal } from "@/components/capture/ReportActivityModal";
import { useAppBarAction } from "@/contexts/AppBarActionContext";
import { useUserLocation } from "@/hooks/use-user-location";
import { useIsMobile } from "@/hooks/use-mobile";
import { captureApi } from "@/lib/capture/captureApi";
import { fetchJson, apiRequest, queryClient } from "@/lib/queryClient";
import { useToast } from "@/hooks/use-toast";
import { apiV1 } from "@/lib/api";
import { format, isSameDay, startOfDay } from "date-fns";
import { calendarApi } from "@/lib/integrations/calendarApi";
import type { CalendarAccount, CalendarEvent } from "@/lib/integrations/types";
import { SiGoogle } from "react-icons/si";
import { Calendar as CalendarIconLucide } from "lucide-react";
import { emailApi } from "@/lib/integrations/emailApi";
import type { EmailAccount, EmailMessage } from "@/lib/integrations/types";

type ActivityKind = "task" | "note" | "idea" | "event" | "other";
type ActivitiesTab = ActivityKind | "all" | "email" | "timeline";

function isActivityKind(value: ActivitiesTab): value is ActivityKind {
  return value === "task" || value === "note" || value === "idea" || value === "event" || value === "other";
}

interface TaskContent {
  description?: string;
  due_date?: string;
  priority?: number;
  status?: "open" | "in_progress" | "done";
}

interface NoteContent {
  body?: string;
  tags?: string[];
}

interface IdeaContent {
  body?: string;
  impact?: number;
  tags?: string[];
}

interface EventContent {
  start?: string;
  end?: string;
  location?: string;
  participants?: string[];
}

type ActivityContent = TaskContent | NoteContent | IdeaContent | EventContent;

interface Activity {
  id: string;
  title: string;
  kind: ActivityKind;
  kind_label?: string;
  type?: string | null;
  content: ActivityContent;
  source?: string | null;
  visibility: "public" | "private";
  visibility_label?: string;
  user_id?: string | null;
  author?: string | null;
  created_at: string;
}

interface ActivitiesResponse {
  activities: Activity[];
  pagination: {
    page: number;
    page_size: number;
    total_items: number;
    total_pages: number;
  };
}

type CaptureEntryLite = {
  id: string;
  raw_text?: string;
  summary?: string;
  status?: string;
  visibility?: string;
  actor_id?: string | null;
  anchor_model?: string;
  anchor_id?: string;
  created_at?: string;
};

type CaptureEntriesResponse = {
  entries: CaptureEntryLite[];
  pagination?: {
    current_page: number;
    total_pages: number;
    total_items: number;
    items_per_page: number;
  };
};

interface CreateActivityData {
  title: string;
  kind: ActivityKind;
  type?: string;
  content: ActivityContent;
  source?: string;
  visibility?: "public" | "private";
}

const kindConfig: Record<ActivityKind, { icon: typeof CheckSquare; color: string; label: string }> = {
  task: { icon: CheckSquare, color: "bg-blue-500", label: "Task" },
  note: { icon: StickyNote, color: "bg-amber-500", label: "Note" },
  idea: { icon: Lightbulb, color: "bg-purple-500", label: "Idea" },
  event: { icon: CalendarDays, color: "bg-green-500", label: "Event" },
  other: { icon: Clock, color: "bg-gray-500", label: "Other" },
};

const defaultKindConfig = { icon: Clock, color: "bg-gray-500", label: "Activity" };

const priorityLabels: Record<number, string> = {
  1: "Low",
  2: "Medium-Low",
  3: "Medium",
  4: "Medium-High",
  5: "High",
};

const priorityColors: Record<number, string> = {
  1: "bg-gray-400",
  2: "bg-blue-400",
  3: "bg-amber-400",
  4: "bg-orange-500",
  5: "bg-red-500",
};

const statusLabels: Record<string, string> = {
  open: "Open",
  in_progress: "In Progress",
  done: "Done",
};

const statusColors: Record<string, string> = {
  open: "bg-blue-500",
  in_progress: "bg-amber-500",
  done: "bg-green-500",
};

function formatRelativeTime(dateString: string): string {
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
  return date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function CapturedNoteCard({ entry }: { entry: CaptureEntryLite }) {
  const [, navigate] = useLocation();
  const status = String(entry.status ?? "captured");
  const visibility = entry.visibility ? String(entry.visibility) : undefined;
  const created = entry.created_at ? formatDateTime(entry.created_at) : "";
  const text = String(entry.summary ?? entry.raw_text ?? "").trim();

  const anchorModel = String(entry.anchor_model ?? "").toLowerCase();
  const anchorId = String(entry.anchor_id ?? "");

  const anchorQuery = useQuery({
    queryKey: ["activities", "capture-anchor-label", anchorModel, anchorId],
    enabled: Boolean(anchorModel && anchorId && (anchorModel === "crm.contact" || anchorModel === "crm.deal")),
    queryFn: async () => {
      if (anchorModel === "crm.contact") {
        const c = await fetchJson<any>(apiV1(`/crm/contacts/${anchorId}/`));
        const label = String(c?.name ?? c?.display_name ?? c?.fullname ?? c?.whatsapp_name ?? c?.email ?? c?.phone ?? anchorId);
        return { kind: "Contact" as const, label, href: `/crm?tab=contacts&contactId=${encodeURIComponent(anchorId)}` };
      }
      const d = await fetchJson<any>(apiV1(`/crm/deals/${anchorId}/`));
      const label = String(d?.title ?? d?.name ?? anchorId);
      return { kind: "Deal" as const, label, href: "/deals" };
    },
    retry: false,
    staleTime: 10 * 60 * 1000,
  });

  return (
    <div
      className={`p-4 rounded-lg border bg-card hover-elevate transition-all space-y-2 ${anchorQuery.data?.href ? "cursor-pointer" : ""}`}
      onClick={() => {
        const href = anchorQuery.data?.href;
        if (!href) return;
        navigate(href);
      }}
      data-testid={`captured-note-${entry.id}`}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <StickyNote className="h-4 w-4 text-amber-600 shrink-0" />
          <Badge variant="secondary" className="shrink-0">Note</Badge>
          <Badge variant="outline" className="shrink-0 border-amber-300 text-amber-700">Captured</Badge>
          <Badge variant="outline" className="shrink-0">{status}</Badge>
          {visibility && <Badge variant="outline" className="shrink-0">{visibility}</Badge>}
        </div>
        <span className="text-xs text-muted-foreground shrink-0">{created}</span>
      </div>

      {anchorQuery.data?.label && (
        <div className="text-xs text-muted-foreground truncate">
          Anchored to{" "}
          <Link href={anchorQuery.data.href} className="text-foreground hover:underline">
            {anchorQuery.data.kind}: {anchorQuery.data.label}
          </Link>
        </div>
      )}

      {text ? (
        <div className="text-sm whitespace-pre-wrap break-words line-clamp-4">{text}</div>
      ) : (
        <div className="text-sm text-muted-foreground">No content</div>
      )}
    </div>
  );
}

function TaskCard({ 
  activity, 
  onEdit, 
  onDelete,
  onToggleComplete,
  isUpdating,
}: { 
  activity: Activity; 
  onEdit: (activity: Activity) => void;
  onDelete: (id: string) => void;
  onToggleComplete: (activity: Activity) => void;
  isUpdating: boolean;
}) {
  const content = activity.content as TaskContent;
  const isDone = content.status === "done";
  const author = activity.author ?? "—";

  return (
    <div 
      className={`p-4 rounded-lg border bg-card hover-elevate transition-all cursor-pointer ${isDone ? "opacity-60" : ""}`}
      data-testid={`task-card-${activity.id}`}
      onClick={() => onEdit(activity)}
    >
      <div className="flex items-start gap-3">
        <button
          onClick={(e) => { e.stopPropagation(); onToggleComplete(activity); }}
          disabled={isUpdating}
          className={`mt-0.5 h-5 w-5 rounded border-2 flex items-center justify-center transition-colors ${
            isDone 
              ? "bg-green-500 border-green-500 text-white" 
              : "border-muted-foreground/50 hover:border-primary"
          }`}
          data-testid={`checkbox-task-${activity.id}`}
        >
          {isDone && <CheckSquare className="h-3 w-3" />}
        </button>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <h3 className={`font-medium truncate ${isDone ? "line-through text-muted-foreground" : ""}`}>
              {activity.title}
            </h3>
            {activity.visibility === "private" && (
              <EyeOff className="h-3 w-3 text-muted-foreground" />
            )}
          </div>
          <p className="text-xs text-muted-foreground mb-1">
            By <span className="text-foreground">{author}</span>
          </p>
          <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
            {content.priority && (
              <Badge variant="outline" className="text-xs">
                <span className={`w-2 h-2 rounded-full ${priorityColors[content.priority]} mr-1`} />
                P{content.priority}
              </Badge>
            )}
            {content.due_date && (
              <span className="flex items-center gap-1">
                <Clock className="h-3 w-3" />
                {formatDateTime(content.due_date)}
              </span>
            )}
          </div>
          {content.description && (
            <p className="text-sm text-muted-foreground mt-1 line-clamp-2">{content.description}</p>
          )}
        </div>

        <div className="flex items-center gap-1">
          <Button 
            variant="ghost" 
            size="icon" 
            className="h-8 w-8 text-destructive"
            onClick={(e) => { e.stopPropagation(); onDelete(activity.id); }}
            data-testid={`button-delete-${activity.id}`}
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      </div>
      <div className="text-xs text-muted-foreground mt-2 pl-8">
        {formatRelativeTime(activity.created_at)}
      </div>
    </div>
  );
}

function ActivityCard({ 
  activity, 
  onEdit, 
  onDelete 
}: { 
  activity: Activity; 
  onEdit: (activity: Activity) => void;
  onDelete: (id: string) => void;
}) {
  const config = kindConfig[activity.kind as ActivityKind] ?? defaultKindConfig;
  const Icon = config.icon;
  const content = activity.content as any;
  const author = activity.author ?? "—";

  return (
    <div 
      className="p-4 rounded-lg border bg-card hover-elevate transition-all cursor-pointer"
      data-testid={`activity-card-${activity.id}`}
      onClick={() => onEdit(activity)}
    >
      <div className="flex items-start gap-3">
        <div className={`p-2 rounded-md ${config.color} text-white`}>
          <Icon className="h-4 w-4" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <h3 className="font-medium truncate">{activity.title}</h3>
            {activity.visibility === "private" && (
              <EyeOff className="h-3 w-3 text-muted-foreground" />
            )}
          </div>
          <p className="text-xs text-muted-foreground mb-2">
            By <span className="text-foreground">{author}</span>
          </p>
          {activity.kind === "task" && (
            <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
              {content.status && (
                <Badge variant="secondary" className="text-xs">
                  <span className={`w-2 h-2 rounded-full ${statusColors[content.status]} mr-1`} />
                  {statusLabels[content.status] || content.status}
                </Badge>
              )}
              {content.priority && (
                <Badge variant="outline" className="text-xs">
                  <span className={`w-2 h-2 rounded-full ${priorityColors[content.priority]} mr-1`} />
                  P{content.priority}
                </Badge>
              )}
              {content.due_date && (
                <span className="flex items-center gap-1">
                  <Clock className="h-3 w-3" />
                  {formatDateTime(content.due_date)}
                </span>
              )}
            </div>
          )}

          {activity.kind === "note" && content.body && (
            <p className="text-sm text-muted-foreground line-clamp-2">{content.body}</p>
          )}

          {activity.kind === "idea" && (
            <div className="space-y-1">
              {content.body && (
                <p className="text-sm text-muted-foreground line-clamp-2">{content.body}</p>
              )}
              {content.impact && (
                <div className="flex items-center gap-1">
                  <Star className="h-3 w-3 text-amber-500" />
                  <span className="text-xs text-muted-foreground">Impact: {content.impact}/10</span>
                </div>
              )}
            </div>
          )}

          {activity.kind === "event" && (
            <div className="flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
              {content.start && (
                <span className="flex items-center gap-1">
                  <CalendarIcon className="h-3 w-3" />
                  {formatDateTime(content.start)}
                </span>
              )}
              {content.location && (
                <span className="flex items-center gap-1">
                  <MapPin className="h-3 w-3" />
                  {content.location}
                </span>
              )}
              {content.participants?.length > 0 && (
                <span className="flex items-center gap-1">
                  <Users className="h-3 w-3" />
                  {content.participants.length}
                </span>
              )}
            </div>
          )}

          {(activity.kind === "note" || activity.kind === "idea") && content.tags?.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-2">
              {content.tags.slice(0, 3).map((tag: string) => (
                <Badge key={tag} variant="outline" className="text-xs">
                  <Tag className="h-2 w-2 mr-1" />
                  {tag}
                </Badge>
              ))}
              {content.tags.length > 3 && (
                <Badge variant="outline" className="text-xs">+{content.tags.length - 3}</Badge>
              )}
            </div>
          )}
        </div>

        <div className="flex items-center gap-1">
          <Button 
            variant="ghost" 
            size="icon" 
            className="h-8 w-8 text-destructive"
            onClick={(e) => { e.stopPropagation(); onDelete(activity.id); }}
            data-testid={`button-delete-${activity.id}`}
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      </div>
      <div className="text-xs text-muted-foreground mt-2 pl-11">
        {formatRelativeTime(activity.created_at)}
      </div>
    </div>
  );
}

function EventsCalendarView({
  events,
  selectedDate,
  onSelectDate,
  onEdit,
  onDelete,
}: {
  events: Activity[];
  selectedDate: Date | undefined;
  onSelectDate: (date: Date | undefined) => void;
  onEdit: (activity: Activity) => void;
  onDelete: (id: string) => void;
}) {
  const eventDates = useMemo(() => {
    return events.reduce((acc, event) => {
      const content = event.content as EventContent;
      if (content.start) {
        const date = startOfDay(new Date(content.start));
        acc.set(date.getTime(), [...(acc.get(date.getTime()) || []), event]);
      }
      return acc;
    }, new Map<number, Activity[]>());
  }, [events]);

  const filteredEvents = useMemo(() => {
    if (!selectedDate) return events;
    return events.filter(event => {
      const content = event.content as EventContent;
      if (!content.start) return false;
      return isSameDay(new Date(content.start), selectedDate);
    });
  }, [events, selectedDate]);

  const modifiers = useMemo(() => {
    return {
      hasEvent: (date: Date) => eventDates.has(startOfDay(date).getTime()),
    };
  }, [eventDates]);

  const modifiersStyles = {
    hasEvent: {
      fontWeight: 'bold' as const,
      textDecoration: 'underline' as const,
      textUnderlineOffset: '4px',
    },
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[auto_1fr] gap-4 lg:gap-6 h-full">
      <div className="lg:sticky lg:top-0 lg:self-start bg-card border rounded-lg p-4 order-2 lg:order-1">
        <Calendar
          mode="single"
          selected={selectedDate}
          onSelect={onSelectDate}
          modifiers={modifiers}
          modifiersStyles={modifiersStyles}
          className="rounded-md"
        />
        {selectedDate && (
          <div className="mt-3 pt-3 border-t">
            <Button 
              variant="ghost" 
              size="sm" 
              className="w-full"
              onClick={() => onSelectDate(undefined)}
              data-testid="button-clear-date"
            >
              Show all events
            </Button>
          </div>
        )}
      </div>
      <div className="space-y-3 overflow-y-auto order-1 lg:order-2">
        {selectedDate && (
          <div className="text-sm text-muted-foreground mb-2">
            Showing events for {format(selectedDate, "MMMM d, yyyy")}
          </div>
        )}
        {filteredEvents.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-center bg-card border rounded-lg">
            <EmptyState
              icon={CalendarDays}
              title="No events found"
              description={selectedDate ? "No events on this date" : "Create your first event to get started"}
            />
          </div>
        ) : (
          filteredEvents.map((activity) => (
            <ActivityCard
              key={activity.id}
              activity={activity}
              onEdit={onEdit}
              onDelete={onDelete}
            />
          ))
        )}
      </div>
    </div>
  );
}

function ActivityDialog({
  open,
  onOpenChange,
  activity,
  defaultKind,
  onSave,
  isLoading,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  activity?: Activity | null;
  defaultKind: ActivityKind;
  onSave: (data: CreateActivityData) => void;
  isLoading: boolean;
}) {
  const [title, setTitle] = useState(activity?.title || "");
  const [kind, setKind] = useState<ActivityKind>(activity?.kind || defaultKind);
  const [visibility, setVisibility] = useState<"public" | "private">(activity?.visibility || "public");
  
  // Task fields
  const [description, setDescription] = useState((activity?.content as TaskContent)?.description || "");
  const [dueDate, setDueDate] = useState<Date | undefined>(
    (activity?.content as TaskContent)?.due_date ? new Date((activity?.content as TaskContent).due_date!) : undefined
  );
  const [priority, setPriority] = useState<number>((activity?.content as TaskContent)?.priority || 3);
  const [status, setStatus] = useState<string>((activity?.content as TaskContent)?.status || "open");
  
  // Note/Idea fields
  const [body, setBody] = useState(
    (activity?.content as NoteContent)?.body || (activity?.content as IdeaContent)?.body || ""
  );
  const [tagsInput, setTagsInput] = useState(
    ((activity?.content as NoteContent)?.tags || (activity?.content as IdeaContent)?.tags || []).join(", ")
  );
  const [impact, setImpact] = useState<number>((activity?.content as IdeaContent)?.impact || 5);
  
  // Event fields
  const [startDate, setStartDate] = useState<Date | undefined>(
    (activity?.content as EventContent)?.start ? new Date((activity?.content as EventContent).start!) : undefined
  );
  const [endDate, setEndDate] = useState<Date | undefined>(
    (activity?.content as EventContent)?.end ? new Date((activity?.content as EventContent).end!) : undefined
  );
  const [location, setLocation] = useState((activity?.content as EventContent)?.location || "");

  // Reset form when dialog opens
  useEffect(() => {
    if (open) {
      if (activity) {
        setTitle(activity.title);
        setKind(activity.kind);
        setVisibility(activity.visibility);
        setDescription((activity.content as TaskContent)?.description || "");
        setDueDate((activity.content as TaskContent)?.due_date ? new Date((activity.content as TaskContent).due_date!) : undefined);
        setPriority((activity.content as TaskContent)?.priority || 3);
        setStatus((activity.content as TaskContent)?.status || "open");
        setBody((activity.content as NoteContent)?.body || (activity.content as IdeaContent)?.body || "");
        setTagsInput(((activity.content as NoteContent)?.tags || (activity.content as IdeaContent)?.tags || []).join(", "));
        setImpact((activity.content as IdeaContent)?.impact || 5);
        setStartDate((activity.content as EventContent)?.start ? new Date((activity.content as EventContent).start!) : undefined);
        setEndDate((activity.content as EventContent)?.end ? new Date((activity.content as EventContent).end!) : undefined);
        setLocation((activity.content as EventContent)?.location || "");
      } else {
        setTitle("");
        setKind(defaultKind);
        setVisibility("public");
        setDescription("");
        setDueDate(undefined);
        setPriority(3);
        setStatus("open");
        setBody("");
        setTagsInput("");
        setImpact(5);
        setStartDate(undefined);
        setEndDate(undefined);
        setLocation("");
      }
    }
  }, [open, activity, defaultKind]);

  const handleSave = () => {
    let content: ActivityContent = {};
    
    if (kind === "task") {
      content = {
        description,
        due_date: dueDate?.toISOString(),
        priority,
        status: status as "open" | "in_progress" | "done",
      };
    } else if (kind === "note") {
      content = {
        body,
        tags: tagsInput.split(",").map(t => t.trim()).filter(Boolean),
      };
    } else if (kind === "idea") {
      content = {
        body,
        impact,
        tags: tagsInput.split(",").map(t => t.trim()).filter(Boolean),
      };
    } else if (kind === "event") {
      content = {
        start: startDate?.toISOString(),
        end: endDate?.toISOString(),
        location,
        participants: [],
      };
    } else if (kind === "other") {
      content = activity?.content ? (activity.content as Record<string, unknown>) : {};
    }

    onSave({
      title,
      kind,
      content,
      visibility,
    });
  };

  const isEditing = !!activity;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg max-h-[90vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle>{isEditing ? "Edit" : "Create"} {kindConfig[kind]?.label ?? defaultKindConfig.label}</DialogTitle>
          <DialogDescription>
            {isEditing ? "Update the activity details below." : "Fill in the details for your new activity."}
          </DialogDescription>
        </DialogHeader>
        
        <ScrollArea className="flex-1 pr-4">
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="title">Title</Label>
              <Input
                id="title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Enter title..."
                data-testid="input-activity-title"
              />
            </div>

            {!isEditing && (
              <div className="space-y-2">
                <Label>Type</Label>
                <div className="flex gap-2">
                  {(Object.keys(kindConfig) as ActivityKind[]).map((k) => {
                    const cfg = kindConfig[k];
                    const Icon = cfg.icon;
                    return (
                      <Button
                        key={k}
                        type="button"
                        variant={kind === k ? "default" : "outline"}
                        size="sm"
                        onClick={() => setKind(k)}
                        className="flex-1"
                        data-testid={`button-kind-${k}`}
                      >
                        <Icon className="h-4 w-4 mr-1" />
                        {cfg.label}
                      </Button>
                    );
                  })}
                </div>
              </div>
            )}

            <div className="space-y-2">
              <Label>Visibility</Label>
              <Select value={visibility} onValueChange={(v) => setVisibility(v as "public" | "private")}>
                <SelectTrigger data-testid="select-visibility">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="public">
                    <span className="flex items-center gap-2">
                      <Eye className="h-4 w-4" /> Public
                    </span>
                  </SelectItem>
                  <SelectItem value="private">
                    <span className="flex items-center gap-2">
                      <EyeOff className="h-4 w-4" /> Private
                    </span>
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>

            {kind === "task" && (
              <>
                <div className="space-y-2">
                  <Label htmlFor="description">Description</Label>
                  <Textarea
                    id="description"
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    placeholder="Task description..."
                    rows={3}
                    data-testid="input-task-description"
                  />
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label>Priority</Label>
                    <Select value={String(priority)} onValueChange={(v) => setPriority(Number(v))}>
                      <SelectTrigger data-testid="select-priority">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {[1, 2, 3, 4, 5].map((p) => (
                          <SelectItem key={p} value={String(p)}>
                            <span className="flex items-center gap-2">
                              <span className={`w-2 h-2 rounded-full ${priorityColors[p]}`} />
                              {priorityLabels[p]}
                            </span>
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="space-y-2">
                    <Label>Status</Label>
                    <Select value={status} onValueChange={setStatus}>
                      <SelectTrigger data-testid="select-status">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {Object.entries(statusLabels).map(([value, label]) => (
                          <SelectItem key={value} value={value}>
                            <span className="flex items-center gap-2">
                              <span className={`w-2 h-2 rounded-full ${statusColors[value]}`} />
                              {label}
                            </span>
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                <div className="space-y-2">
                  <Label>Due Date</Label>
                  <Popover>
                    <PopoverTrigger asChild>
                      <Button variant="outline" className="w-full justify-start" data-testid="button-due-date">
                        <CalendarIcon className="h-4 w-4 mr-2" />
                        {dueDate ? format(dueDate, "PPP") : "Select date..."}
                      </Button>
                    </PopoverTrigger>
                    <PopoverContent className="w-auto p-0" align="start">
                      <Calendar
                        mode="single"
                        selected={dueDate}
                        onSelect={setDueDate}
                        initialFocus
                      />
                    </PopoverContent>
                  </Popover>
                </div>
              </>
            )}

            {(kind === "note" || kind === "idea") && (
              <>
                <div className="space-y-2">
                  <Label htmlFor="body">Content</Label>
                  <Textarea
                    id="body"
                    value={body}
                    onChange={(e) => setBody(e.target.value)}
                    placeholder={kind === "note" ? "Write your note..." : "Describe your idea..."}
                    rows={4}
                    data-testid="input-body"
                  />
                </div>

                <div className="space-y-2">
                  <Label htmlFor="tags">Tags (comma-separated)</Label>
                  <Input
                    id="tags"
                    value={tagsInput}
                    onChange={(e) => setTagsInput(e.target.value)}
                    placeholder="tag1, tag2, tag3"
                    data-testid="input-tags"
                  />
                </div>

                {kind === "idea" && (
                  <div className="space-y-2">
                    <Label>Impact Score (1-10)</Label>
                    <div className="flex items-center gap-4">
                      <input
                        type="range"
                        min="1"
                        max="10"
                        value={impact}
                        onChange={(e) => setImpact(Number(e.target.value))}
                        className="flex-1"
                        data-testid="input-impact"
                      />
                      <Badge variant="secondary" className="w-10 justify-center">
                        {impact}
                      </Badge>
                    </div>
                  </div>
                )}
              </>
            )}

            {kind === "event" && (
              <>
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label>Start</Label>
                    <Popover>
                      <PopoverTrigger asChild>
                        <Button variant="outline" className="w-full justify-start" data-testid="button-start-date">
                          <CalendarIcon className="h-4 w-4 mr-2" />
                          {startDate ? format(startDate, "PPP") : "Start date..."}
                        </Button>
                      </PopoverTrigger>
                      <PopoverContent className="w-auto p-0" align="start">
                        <Calendar
                          mode="single"
                          selected={startDate}
                          onSelect={setStartDate}
                          initialFocus
                        />
                      </PopoverContent>
                    </Popover>
                  </div>

                  <div className="space-y-2">
                    <Label>End</Label>
                    <Popover>
                      <PopoverTrigger asChild>
                        <Button variant="outline" className="w-full justify-start" data-testid="button-end-date">
                          <CalendarIcon className="h-4 w-4 mr-2" />
                          {endDate ? format(endDate, "PPP") : "End date..."}
                        </Button>
                      </PopoverTrigger>
                      <PopoverContent className="w-auto p-0" align="start">
                        <Calendar
                          mode="single"
                          selected={endDate}
                          onSelect={setEndDate}
                          initialFocus
                        />
                      </PopoverContent>
                    </Popover>
                  </div>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="location">Location</Label>
                  <Input
                    id="location"
                    value={location}
                    onChange={(e) => setLocation(e.target.value)}
                    placeholder="Enter location..."
                    data-testid="input-location"
                  />
                </div>
              </>
            )}
          </div>
        </ScrollArea>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} data-testid="button-cancel">
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={!title.trim() || isLoading} data-testid="button-save">
            {isLoading && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
            {isEditing ? "Update" : "Create"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default function Activities() {
  const { t } = useTranslation();
  const { toast } = useToast();
  const { lastLocation } = useUserLocation();
  const { setAction } = useAppBarAction();
  const isMobile = useIsMobile();
  const isEmbedded = new URLSearchParams(window.location.search).get("embed") === "true";
  const [activeTab] = useState<ActivitiesTab>("timeline");
  const [timelineView, setTimelineView] = useState<"cards" | "table" | "calendar">(() => {
    const view = new URLSearchParams(window.location.search).get("view");
    if (view === "table" || view === "cards" || view === "calendar") return view;
    return "cards";
  });
  const [search, setSearch] = useState("");
  const [sortBy, setSortBy] = useState("created_at");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("desc");
  const [visibilityFilter, setVisibilityFilter] = useState<string>("all");
  const [page, setPage] = useState(1);
  const pageSize = 20;

  const [dialogOpen, setDialogOpen] = useState(false);
  const [reportActivityOpen, setReportActivityOpen] = useState(false);
  const [editingActivity, setEditingActivity] = useState<Activity | null>(null);
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);
  const [selectedEventDate, setSelectedEventDate] = useState<Date | undefined>(undefined);
  const [selectedCalendarAccounts, setSelectedCalendarAccounts] = useState<string[]>([]);
  const [calendarEventsByAccount, setCalendarEventsByAccount] = useState<
    Record<string, { items: (CalendarEvent & { accountId: string })[]; next_cursor: string | null }>
  >({});
  const [calendarEventDialogOpen, setCalendarEventDialogOpen] = useState(false);
  const [editingCalendarEvent, setEditingCalendarEvent] = useState<{
    accountId: string;
    event?: CalendarEvent;
  } | null>(null);
  const [calendarEventForm, setCalendarEventForm] = useState({
    accountId: "",
    title: "",
    start: "",
    end: "",
    attendees: "",
  });

  // Personal Email (user scope) inbox state (Activities tab)
  const [emailAccountsSelected, setEmailAccountsSelected] = useState<string[]>([]);
  const [emailMessagesByAccount, setEmailMessagesByAccount] = useState<
    Record<string, { items: (EmailMessage & { accountId: string })[]; next_cursor: string | null }>
  >({});
  const [selectedEmailMessage, setSelectedEmailMessage] = useState<{ accountId: string; id: string } | null>(null);
  const [selectedEmailDetail, setSelectedEmailDetail] = useState<EmailMessage | null>(null);
  const [emailComposeForm, setEmailComposeForm] = useState({
    accountId: "",
    to: "",
    cc: "",
    bcc: "",
    subject: "",
    text: "",
    html: "",
    attachments: [] as File[],
  });

  const activitiesPath = apiV1("/activities/");

  const openReportActivity = useCallback(() => setReportActivityOpen(true), []);

  useEffect(() => {
    setAction({ onClick: openReportActivity, label: "Log activity" });
    return () => setAction(null);
  }, [setAction, openReportActivity]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    params.set("view", timelineView);
    const next = params.toString();
    window.history.replaceState(window.history.state, "", `${window.location.pathname}?${next}`);
  }, [timelineView]);

  const effectivePageSize = activeTab === "event" ? 500 : pageSize;

  const { data, isLoading, error, refetch } = useQuery<ActivitiesResponse>({
    queryKey: ["activities", activeTab, search, sortBy, sortOrder, visibilityFilter, page, effectivePageSize],
    queryFn: () => {
      const params: Record<string, string | number> = {
        page: activeTab === "event" ? 1 : page,
        page_size: effectivePageSize,
        sort_by: sortBy,
        order: sortOrder,
      };
      if (isActivityKind(activeTab)) params.kind = activeTab;
      if (search) params.search = search;
      if (visibilityFilter !== "all") params.visibility = visibilityFilter;
      return fetchJson<ActivitiesResponse>(activitiesPath, params);
    },
    enabled: activeTab !== "email" && activeTab !== "timeline",
  });

  const captureAllQuery = useQuery<CaptureEntriesResponse>({
    queryKey: ["capture", "entries", "activities-all", page, effectivePageSize],
    queryFn: () => captureApi.listEntries({ page, limit: effectivePageSize }) as any,
    enabled: activeTab === "all",
    retry: false,
  });

  const calendarTenantQuery = useQuery<CalendarAccount[]>({
    queryKey: ["calendar-flow-tenant"],
    queryFn: () => calendarApi.flowAccounts("tenant"),
    retry: false,
  });

  const calendarUserQuery = useQuery<CalendarAccount[]>({
    queryKey: ["calendar-flow-user"],
    queryFn: () => calendarApi.flowAccounts("user"),
    retry: false,
  });

  const emailUserQuery = useQuery<EmailAccount[]>({
    queryKey: ["email-flow-user"],
    queryFn: () => emailApi.flowAccounts("user"),
    retry: false,
  });

  const createMutation = useMutation({
    mutationFn: async (activityData: CreateActivityData) => {
      return apiRequest("POST", activitiesPath, { data: activityData });
    },
    onSuccess: () => {
      toast({ title: "Activity created successfully" });
      setDialogOpen(false);
      queryClient.invalidateQueries({ queryKey: ["activities"] });
    },
    onError: (error: Error) => {
      toast({ title: "Failed to create activity", description: error.message, variant: "destructive" });
    },
  });

  const updateMutation = useMutation({
    mutationFn: async ({ id, data }: { id: string; data: Partial<CreateActivityData> }) => {
      return apiRequest("PATCH", `${activitiesPath}${id}/`, { data });
    },
    onSuccess: () => {
      toast({ title: "Activity updated successfully" });
      setDialogOpen(false);
      setEditingActivity(null);
      queryClient.invalidateQueries({ queryKey: ["activities"] });
    },
    onError: (error: Error) => {
      toast({ title: "Failed to update activity", description: error.message, variant: "destructive" });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: async (id: string) => {
      return apiRequest("DELETE", `${activitiesPath}${id}/`);
    },
    onSuccess: () => {
      toast({ title: "Activity deleted successfully" });
      setDeleteConfirmId(null);
      queryClient.invalidateQueries({ queryKey: ["activities"] });
    },
    onError: (error: Error) => {
      toast({ title: "Failed to delete activity", description: error.message, variant: "destructive" });
    },
  });

  const toggleCompleteMutation = useMutation({
    mutationFn: async ({ id, currentContent }: { id: string; currentContent: TaskContent }) => {
      const newStatus = currentContent.status === "done" ? "open" : "done";
      return apiRequest("PATCH", `${activitiesPath}${id}/`, { 
        data: { content: { ...currentContent, status: newStatus } } 
      });
    },
    onMutate: async ({ id, currentContent }) => {
      await queryClient.cancelQueries({ queryKey: ["activities"] });
      const queryKey = ["activities", activeTab, search, sortBy, sortOrder, visibilityFilter, page];
      const previousData = queryClient.getQueryData<ActivitiesResponse>(queryKey);
      
      if (previousData) {
        const newStatus = currentContent.status === "done" ? "open" : "done";
        queryClient.setQueryData<ActivitiesResponse>(queryKey, {
          ...previousData,
          activities: previousData.activities.map((a) =>
            a.id === id
              ? { ...a, content: { ...a.content, status: newStatus } }
              : a
          ),
        });
      }
      return { previousData, queryKey };
    },
    onError: (error: Error, _variables, context) => {
      if (context?.previousData) {
        queryClient.setQueryData(context.queryKey, context.previousData);
      }
      toast({ title: "Failed to update task", description: error.message, variant: "destructive" });
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["activities"] });
    },
  });

  const handleToggleComplete = (activity: Activity) => {
    const content = activity.content as TaskContent;
    toggleCompleteMutation.mutate({ id: activity.id, currentContent: content });
  };

  const handleSave = (activityData: CreateActivityData) => {
    if (editingActivity) {
      updateMutation.mutate({ id: editingActivity.id, data: activityData });
    } else {
      createMutation.mutate(activityData);
    }
  };

  const handleEdit = (activity: Activity) => {
    setEditingActivity(activity);
    setDialogOpen(true);
  };

  const handleDelete = (id: string) => {
    setDeleteConfirmId(id);
  };

  const confirmDelete = () => {
    if (deleteConfirmId) {
      deleteMutation.mutate(deleteConfirmId);
    }
  };

  const handleNewActivity = () => {
    setEditingActivity(null);
    setDialogOpen(true);
  };

  const activities = data?.activities || [];
  const pagination = data?.pagination;
  const totalPages = pagination?.total_pages || 1;
  const captureEntries = captureAllQuery.data?.entries ?? [];

  const mergedAllItems = useMemo(() => {
    if (activeTab !== "all") return [];
    const merged = [
      ...activities.map((a) => ({ type: "activity" as const, created_at: a.created_at, activity: a })),
      ...captureEntries.map((e) => ({ type: "capture" as const, created_at: String(e.created_at ?? ""), entry: e })),
    ];
    merged.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
    return merged;
  }, [activeTab, activities, captureEntries]);

  const calendarAccounts = useMemo(() => {
    return [
      ...(calendarTenantQuery.data ?? []),
      ...(calendarUserQuery.data ?? []),
    ];
  }, [calendarTenantQuery.data, calendarUserQuery.data]);

  useEffect(() => {
    if (calendarAccounts.length > 0 && selectedCalendarAccounts.length === 0) {
      setSelectedCalendarAccounts(calendarAccounts.map((a) => a.id));
    }
  }, [calendarAccounts, selectedCalendarAccounts.length]);

  useEffect(() => {
    if (selectedCalendarAccounts.length > 0 && !calendarEventForm.accountId) {
      setCalendarEventForm((prev) => ({ ...prev, accountId: selectedCalendarAccounts[0] }));
    }
  }, [selectedCalendarAccounts, calendarEventForm.accountId]);

  const fetchCalendarEvents = async (accountId: string, cursor?: string | null) => {
    const res = await calendarApi.listEvents(accountId, cursor ? { cursor } : undefined);
    setCalendarEventsByAccount((prev) => {
      const existing = prev[accountId]?.items ?? [];
      const mergedItems = cursor ? [...existing, ...res.items.map((ev) => ({ ...ev, accountId }))] : res.items.map((ev) => ({ ...ev, accountId }));
      return {
        ...prev,
        [accountId]: { items: mergedItems, next_cursor: res.next_cursor },
      };
    });
  };

  useEffect(() => {
    // Load events when selection changes
    selectedCalendarAccounts.forEach((id) => {
      const alreadyLoaded = calendarEventsByAccount[id];
      if (!alreadyLoaded) {
        fetchCalendarEvents(id).catch(() => {
          toast({ title: "Failed to load calendar events", variant: "destructive" });
        });
      }
    });
  }, [selectedCalendarAccounts, calendarEventsByAccount, toast]);

  const mergedCalendarEvents = useMemo(() => {
    return Object.values(calendarEventsByAccount)
      .flatMap((entry) => entry.items)
      .sort((a, b) => {
        const aTime = new Date(a.start).getTime();
        const bTime = new Date(b.start).getTime();
        return bTime - aTime;
      });
  }, [calendarEventsByAccount]);

  const loadMoreCalendarEvents = () => {
    const targets = Object.entries(calendarEventsByAccount).filter(([, v]) => v.next_cursor);
    targets.forEach(([accountId, v]) => {
      fetchCalendarEvents(accountId, v.next_cursor).catch(() => {
        toast({ title: "Failed to load more events", variant: "destructive" });
      });
    });
  };

  const createOrUpdateCalendarEvent = async (payload: { accountId: string; title: string; start: string; end: string; attendees: string[]; eventId?: string }) => {
    if (payload.eventId) {
      await calendarApi.updateEvent(payload.accountId, payload.eventId, {
        title: payload.title,
        start: payload.start,
        end: payload.end,
        attendees: payload.attendees,
      });
      setCalendarEventsByAccount((prev) => {
        const existing = prev[payload.accountId]?.items ?? [];
        return {
          ...prev,
          [payload.accountId]: {
            items: existing.map((ev) =>
              ev.id === payload.eventId ? { ...ev, title: payload.title, start: payload.start, end: payload.end, attendees: payload.attendees } : ev
            ),
            next_cursor: prev[payload.accountId]?.next_cursor ?? null,
          },
        };
      });
    } else {
      const res = await calendarApi.createEvent(payload.accountId, {
        title: payload.title,
        start: payload.start,
        end: payload.end,
        attendees: payload.attendees,
      });
      // Fetch refreshed list for that account to include server data
      await fetchCalendarEvents(payload.accountId);
      toast({ title: "Event created", description: res.id || "Created" });
    }
  };

  const deleteCalendarEvent = async (accountId: string, eventId: string) => {
    await calendarApi.deleteEvent(accountId, eventId);
    setCalendarEventsByAccount((prev) => {
      const existing = prev[accountId]?.items ?? [];
      return {
        ...prev,
        [accountId]: {
          items: existing.filter((ev) => ev.id !== eventId),
          next_cursor: prev[accountId]?.next_cursor ?? null,
        },
      };
    });
  };

  const handleSaveCalendarEvent = async () => {
    const accountId = calendarEventForm.accountId || selectedCalendarAccounts[0];
    if (!accountId) {
      toast({ title: "Select an account", description: "Choose at least one calendar account.", variant: "destructive" });
      return;
    }
    const attendees = calendarEventForm.attendees
      .split(",")
      .map((a) => a.trim())
      .filter(Boolean);
    const startIso = calendarEventForm.start ? new Date(calendarEventForm.start).toISOString() : "";
    const endIso = calendarEventForm.end ? new Date(calendarEventForm.end).toISOString() : "";
    try {
      await createOrUpdateCalendarEvent({
        accountId,
        title: calendarEventForm.title,
        start: startIso,
        end: endIso,
        attendees,
        eventId: editingCalendarEvent?.event?.id,
      });
      toast({ title: editingCalendarEvent?.event ? "Event updated" : "Event created" });
      setCalendarEventDialogOpen(false);
      setEditingCalendarEvent(null);
      setCalendarEventForm({ accountId, title: "", start: "", end: "", attendees: "" });
      await fetchCalendarEvents(accountId);
    } catch (err: any) {
      toast({ title: "Failed to save event", description: err?.message || "Error", variant: "destructive" });
    }
  };

  const handleEditCalendarEvent = (accountId: string, event: CalendarEvent) => {
    setEditingCalendarEvent({ accountId, event });
    setCalendarEventForm({
      accountId,
      title: event.title,
      start: event.start,
      end: event.end,
      attendees: event.attendees?.join(", ") ?? "",
    });
    setCalendarEventDialogOpen(true);
  };

  const handleNewCalendarEvent = () => {
    const accountId = selectedCalendarAccounts[0] || calendarAccounts[0]?.id || "";
    setEditingCalendarEvent(null);
    setCalendarEventForm({ accountId, title: "", start: "", end: "", attendees: "" });
    setCalendarEventDialogOpen(true);
  };

  const hasMoreCalendar = useMemo(
    () => Object.values(calendarEventsByAccount).some((v) => v.next_cursor),
    [calendarEventsByAccount]
  );

  const counts = useMemo(() => {
    return {
      all: pagination?.total_items || 0,
      task: activities.filter(a => a.kind === "task").length,
      note: activities.filter(a => a.kind === "note").length,
      idea: activities.filter(a => a.kind === "idea").length,
      event: activities.filter(a => a.kind === "event").length,
    };
  }, [activities, pagination]);

  // Personal email accounts + inbox merge
  const personalEmailAccounts = useMemo(() => (emailUserQuery.data ?? []), [emailUserQuery.data]);

  useEffect(() => {
    if (personalEmailAccounts.length > 0 && emailAccountsSelected.length === 0) {
      setEmailAccountsSelected(personalEmailAccounts.map((a) => a.id));
      setEmailComposeForm((prev) => ({ ...prev, accountId: personalEmailAccounts[0].id }));
    }
  }, [personalEmailAccounts, emailAccountsSelected.length]);

  const fetchEmailMessages = async (accountId: string, cursor?: string | null) => {
    const res = await emailApi.listMessages(accountId, cursor ? { cursor } : undefined);
    setEmailMessagesByAccount((prev) => {
      const existing = prev[accountId]?.items ?? [];
      const merged = cursor
        ? [...existing, ...res.items.map((m) => ({ ...m, accountId }))]
        : res.items.map((m) => ({ ...m, accountId }));
      return {
        ...prev,
        [accountId]: { items: merged, next_cursor: res.next_cursor },
      };
    });
  };

  useEffect(() => {
    if (activeTab !== "email") return;
    emailAccountsSelected.forEach((id) => {
      if (!emailMessagesByAccount[id]) {
        fetchEmailMessages(id).catch(() => toast({ title: "Failed to load inbox", variant: "destructive" }));
      }
    });
  }, [activeTab, emailAccountsSelected, emailMessagesByAccount, toast]);

  const mergedEmailMessages = useMemo(() => {
    return Object.values(emailMessagesByAccount)
      .flatMap((entry) => entry.items)
      .sort((a, b) => {
        const aTime = a.received_at ? new Date(a.received_at).getTime() : 0;
        const bTime = b.received_at ? new Date(b.received_at).getTime() : 0;
        return bTime - aTime;
      });
  }, [emailMessagesByAccount]);

  const hasMoreEmail = useMemo(
    () => Object.values(emailMessagesByAccount).some((v) => v.next_cursor),
    [emailMessagesByAccount]
  );

  const loadMoreEmailMessages = () => {
    const targets = Object.entries(emailMessagesByAccount).filter(([, v]) => v.next_cursor);
    targets.forEach(([accountId, v]) => {
      fetchEmailMessages(accountId, v.next_cursor).catch(() =>
        toast({ title: "Failed to load more messages", variant: "destructive" })
      );
    });
  };

  const fetchEmailDetail = async (accountId: string, id: string) => {
    const detail = await emailApi.getMessage(accountId, id);
    setSelectedEmailDetail(detail);
  };

  const emailSendMutation = useMutation({
    mutationFn: async () => {
      const accountId = emailComposeForm.accountId || emailAccountsSelected[0];
      if (!accountId) throw new Error("Select an account");
      const attachments =
        emailComposeForm.attachments.length > 0
          ? await Promise.all(
              emailComposeForm.attachments.map(
                (file) =>
                  new Promise<{ filename: string; mime_type: string; content_base64: string }>((resolve, reject) => {
                    const reader = new FileReader();
                    reader.onload = () => {
                      const result = reader.result as string;
                      const base64 = result.split(",")[1] || "";
                      resolve({ filename: file.name, mime_type: file.type, content_base64: base64 });
                    };
                    reader.onerror = () => reject(reader.error);
                    reader.readAsDataURL(file);
                  })
              )
            )
          : undefined;
      return emailApi.sendMessage(accountId, {
        to: emailComposeForm.to.split(",").map((v) => v.trim()).filter(Boolean),
        cc: emailComposeForm.cc.split(",").map((v) => v.trim()).filter(Boolean),
        bcc: emailComposeForm.bcc.split(",").map((v) => v.trim()).filter(Boolean),
        subject: emailComposeForm.subject,
        text: emailComposeForm.text,
        html: emailComposeForm.html || undefined,
        attachments,
      });
    },
    onSuccess: () => {
      toast({ title: "Email sent" });
      setEmailComposeForm((prev) => ({ ...prev, subject: "", text: "", html: "", attachments: [] }));
    },
    onError: (err: any) => {
      toast({ title: "Send failed", description: err?.message || "Could not send email", variant: "destructive" });
    },
  });

  const emailDeleteMutation = useMutation({
    mutationFn: ({ accountId, id }: { accountId: string; id: string }) => emailApi.deleteMessage(accountId, id),
    onSuccess: (_data, variables) => {
      setEmailMessagesByAccount((prev) => {
        const existing = prev[variables.accountId]?.items ?? [];
        return {
          ...prev,
          [variables.accountId]: {
            items: existing.filter((m) => m.id !== variables.id),
            next_cursor: prev[variables.accountId]?.next_cursor ?? null,
          },
        };
      });
      toast({ title: "Message deleted" });
    },
    onError: (err: any) => {
      toast({ title: "Delete failed", description: err?.message || "Could not delete message", variant: "destructive" });
    },
  });

  const activitiesNavBar = (
    <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 w-full" data-testid="activities-nav-bar">
      <ToggleGroup
        type="single"
        value={timelineView}
        onValueChange={(v) => v && (v === "cards" || v === "table" || v === "calendar") && setTimelineView(v)}
        className="flex-shrink-0"
        data-testid="timeline-view-toggle"
      >
        <ToggleGroupItem value="cards" aria-label="Cards view">
          <LayoutGrid className="h-4 w-4 mr-1" />
          Cards
        </ToggleGroupItem>
        <ToggleGroupItem value="table" aria-label="Table view">
          <Table2 className="h-4 w-4 mr-1" />
          Table
        </ToggleGroupItem>
        <ToggleGroupItem value="calendar" aria-label="Calendar view">
          <CalendarIcon className="h-4 w-4 mr-1" />
          Calendar
        </ToggleGroupItem>
      </ToggleGroup>
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
        <div className="relative w-full sm:w-auto sm:min-w-[200px] max-w-sm sm:max-w-none">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search activities..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9"
            data-testid="input-search"
          />
        </div>
        {!isMobile && (
          <Button
            variant="default"
            onClick={() => setReportActivityOpen(true)}
            data-testid="button-report-activity"
            className="flex-shrink-0"
          >
            <Plus className="h-4 w-4 mr-2" />
            Log activity
          </Button>
        )}
      </div>
    </div>
  );

  const activitiesContent = (
    <div className="space-y-4" data-testid="page-activities">
      <div className="mt-1">
        <div className="space-y-3">
          <GlobalTimeline pageSize={20} view={timelineView} onEditActivity={handleEdit} />
        </div>
      </div>

      <ActivityDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        activity={editingActivity}
        defaultKind="task"
        onSave={handleSave}
        isLoading={createMutation.isPending || updateMutation.isPending}
      />

      <ReportActivityModal
        open={reportActivityOpen}
        onOpenChange={setReportActivityOpen}
        userGeoAddress={lastLocation}
      />

      <Dialog open={calendarEventDialogOpen} onOpenChange={setCalendarEventDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editingCalendarEvent ? "Edit Event" : "New Event"}</DialogTitle>
            <DialogDescription>Calendar events are created on the selected integration account.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1">
              <Label>Account</Label>
              <Select
                value={calendarEventForm.accountId}
                onValueChange={(v) => setCalendarEventForm((prev) => ({ ...prev, accountId: v }))}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select account" />
                </SelectTrigger>
                <SelectContent>
                  {calendarAccounts.map((acc) => (
                    <SelectItem key={acc.id} value={acc.id}>
                      {acc.external_account.email_address} ({acc.external_account.ownership})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label>Title</Label>
              <Input
                value={calendarEventForm.title}
                onChange={(e) => setCalendarEventForm((prev) => ({ ...prev, title: e.target.value }))}
                placeholder="Event title"
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label>Start</Label>
                <Input
                  type="datetime-local"
                  value={calendarEventForm.start}
                  onChange={(e) => setCalendarEventForm((prev) => ({ ...prev, start: e.target.value }))}
                />
              </div>
              <div className="space-y-1">
                <Label>End</Label>
                <Input
                  type="datetime-local"
                  value={calendarEventForm.end}
                  onChange={(e) => setCalendarEventForm((prev) => ({ ...prev, end: e.target.value }))}
                />
              </div>
            </div>
            <div className="space-y-1">
              <Label>Attendees (comma separated emails)</Label>
              <Input
                value={calendarEventForm.attendees}
                onChange={(e) => setCalendarEventForm((prev) => ({ ...prev, attendees: e.target.value }))}
                placeholder="a@example.com, b@example.com"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCalendarEventDialogOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleSaveCalendarEvent}>
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!deleteConfirmId} onOpenChange={() => setDeleteConfirmId(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Activity</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete this activity? This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteConfirmId(null)} data-testid="button-cancel-delete">
              Cancel
            </Button>
            <Button 
              variant="destructive" 
              onClick={confirmDelete}
              disabled={deleteMutation.isPending}
              data-testid="button-confirm-delete"
            >
              {deleteMutation.isPending && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );

  if (isEmbedded) {
    return (
      <div className="p-4 space-y-4">
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div>
            <h1 className="text-xl font-semibold">Activities</h1>
            <p className="text-sm text-muted-foreground">Manage your tasks, notes, ideas, and events</p>
          </div>
        </div>
        {activitiesContent}
      </div>
    );
  }

  return (
    <PageLayout title={t("activities.title")} description={t("activities.description")} toolbar={activitiesNavBar} toolbarClassName="py-2" className="pt-2">
      {activitiesContent}
    </PageLayout>
  );
}
