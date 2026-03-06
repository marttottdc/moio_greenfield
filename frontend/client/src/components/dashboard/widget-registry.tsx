import { 
  LayoutDashboard, 
  MessageSquare, 
  Megaphone, 
  Users, 
  Star, 
  Clock, 
  BarChart3, 
  TrendingUp, 
  Zap,
  CheckSquare,
} from "lucide-react";
import type { WidgetType, WidgetSize } from "@shared/schema";

export interface WidgetMeta {
  type: WidgetType;
  name: string;
  description: string;
  icon: typeof LayoutDashboard;
  defaultSize: WidgetSize;
  minSize?: WidgetSize;
  maxSize?: WidgetSize;
  category: "analytics" | "content" | "tools" | "info";
}

export const WIDGET_REGISTRY: Record<WidgetType, WidgetMeta> = {
  kpi_card: {
    type: "kpi_card",
    name: "KPI Ribbon",
    description: "Display key performance indicators at a glance",
    icon: TrendingUp,
    defaultSize: "full",
    category: "analytics",
  },
  recent_campaigns: {
    type: "recent_campaigns",
    name: "Recent Campaigns",
    description: "View your latest marketing campaigns",
    icon: Megaphone,
    defaultSize: "large",
    category: "content",
  },
  recent_audiences: {
    type: "recent_audiences",
    name: "Recent Audiences",
    description: "Quick access to your audience segments",
    icon: Users,
    defaultSize: "medium",
    category: "content",
  },
  crm_assistant: {
    type: "crm_assistant",
    name: "CRM Assistant",
    description: "AI-powered assistant for your CRM tasks",
    icon: MessageSquare,
    defaultSize: "full",
    category: "tools",
  },
  favorites: {
    type: "favorites",
    name: "Favorites",
    description: "Quick access to your favorite items",
    icon: Star,
    defaultSize: "medium",
    category: "tools",
  },
  frequently_used: {
    type: "frequently_used",
    name: "Frequently Used",
    description: "Your most accessed features and items",
    icon: Clock,
    defaultSize: "medium",
    category: "tools",
  },
  activity_chart: {
    type: "activity_chart",
    name: "Activity Chart",
    description: "Visualize your activity and engagement trends",
    icon: BarChart3,
    defaultSize: "full",
    category: "analytics",
  },
  performance_metrics: {
    type: "performance_metrics",
    name: "Performance Metrics",
    description: "Detailed performance analytics",
    icon: TrendingUp,
    defaultSize: "large",
    category: "analytics",
  },
  quick_actions: {
    type: "quick_actions",
    name: "Quick Actions",
    description: "Frequently used actions at your fingertips",
    icon: Zap,
    defaultSize: "small",
    category: "tools",
  },
  my_tasks: {
    type: "my_tasks",
    name: "My Tasks",
    description: "View and manage your pending tasks",
    icon: CheckSquare,
    defaultSize: "medium",
    category: "tools",
  },
  global_timeline: {
    type: "global_timeline",
    name: "Global Timeline",
    description: "Recent activity across your CRM (including captured notes)",
    icon: Clock,
    defaultSize: "large",
    category: "tools",
  },
};

export const WIDGET_CATEGORIES = [
  { id: "analytics", name: "Analytics", description: "Charts and metrics" },
  { id: "content", name: "Content", description: "Campaigns and audiences" },
  { id: "tools", name: "Tools", description: "Productivity features" },
  { id: "info", name: "Information", description: "Status and notifications" },
] as const;

export function getWidgetMeta(type: WidgetType): WidgetMeta {
  return WIDGET_REGISTRY[type];
}

export function getWidgetsByCategory(category: WidgetMeta["category"]): WidgetMeta[] {
  return Object.values(WIDGET_REGISTRY).filter((w) => w.category === category);
}
