import React from "react";
import { MessageSquare, PlayCircle, ListChecks, LayoutDashboard, BarChart3, Activity, List } from "lucide-react";
import { WhatsAppTemplatesReport } from "@/pages/workflows/reports/WhatsAppTemplatesReport";
import { FlowExecutionsReport } from "@/pages/workflows/reports/FlowExecutionsReport";
import { WhatsAppLogsReport } from "@/pages/workflows/reports/WhatsAppLogsReport";
import { OverviewReport } from "@/pages/workflows/reports/OverviewReport";
import { VisualAnalyticsReport } from "@/pages/workflows/reports/VisualAnalyticsReport";

export type WorkflowRef = { id: string; name: string };
export type TemplateRef = { id?: string; name?: string };

export interface ReportContextProps {
  workflows: WorkflowRef[];
  whatsappTemplates: TemplateRef[];
  flowId?: string;
}

export type ReportId =
  | "overview_kpis"
  | "flow_executions"
  | "whatsapp_logs"
  | "whatsapp_templates"
  | "visual_analytics";

export interface ReportDefinition {
  id: ReportId;
  label: string;
  description: string;
  icon: any;
  bgClass: string;
  iconClass: string;
  render: (ctx: ReportContextProps) => JSX.Element;
}

export const reportRegistry: ReportDefinition[] = [
  {
    id: "overview_kpis",
    label: "Overview KPIs",
    description: "Flows, running now, recent executions (global or per-flow).",
    icon: LayoutDashboard,
    bgClass: "bg-slate-50 dark:bg-slate-900/30",
    iconClass: "text-slate-600 dark:text-slate-300",
    render: (ctx) => <OverviewReport flowId={ctx.flowId} />,
  },
  {
    id: "visual_analytics",
    label: "Visual Analytics",
    description: "Legacy analytics visuals dashboard, embedded as a report.",
    icon: BarChart3,
    bgClass: "bg-blue-50 dark:bg-blue-900/20",
    iconClass: "text-blue-700 dark:text-blue-300",
    render: (ctx) => <VisualAnalyticsReport workflows={ctx.workflows as any} />,
  },
  {
    id: "whatsapp_templates",
    label: "WhatsApp Templates",
    description: "Delivery + failures by template and date. Includes flow run context.",
    icon: MessageSquare,
    bgClass: "bg-emerald-50 dark:bg-emerald-900/20",
    iconClass: "text-emerald-600 dark:text-emerald-400",
    render: (ctx) => <WhatsAppTemplatesReport workflows={ctx.workflows} whatsappTemplates={ctx.whatsappTemplates} />,
  },
  {
    id: "flow_executions",
    label: "Flow Executions",
    description: "Runs, success rate, triggers, and latest runs. Optional flow filter.",
    icon: PlayCircle,
    bgClass: "bg-indigo-50 dark:bg-indigo-900/20",
    iconClass: "text-indigo-600 dark:text-indigo-400",
    render: (ctx) => <FlowExecutionsReport workflows={ctx.workflows} />,
  },
  {
    id: "whatsapp_logs",
    label: "WhatsApp Logs",
    description: "Delivery/event timeline grouped by msg_id for a flow execution or campaign.",
    icon: ListChecks,
    bgClass: "bg-amber-50 dark:bg-amber-900/20",
    iconClass: "text-amber-700 dark:text-amber-400",
    render: () => <WhatsAppLogsReport />,
  },
];


