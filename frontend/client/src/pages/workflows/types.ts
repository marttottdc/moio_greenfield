
export interface Workflow {
  id: string;
  name: string;
  description?: string | null;
  runs?: number;
  status?: string;
  updated_at?: string;
  is_enabled?: boolean;
  latest_version?: {
    id: string;
    label: string;
    is_published: boolean;
    is_active: boolean;
    preview_armed: boolean;
  };
}

export interface Script {
  id: string;
  name: string;
  description?: string | null;
  language?: string;
  status?: "draft" | "pending_approval" | "approved" | "rejected";
  created_at?: string;
  updated_at?: string;
}

export interface Agent {
  id: string;
  name: string;
  description?: string | null;
  status?: "active" | "inactive" | "draft";
  model?: string;
  system_prompt?: string;
  created_at?: string;
  updated_at?: string;
}

export type TabType = "flows" | "campaigns" | "audiences" | "ai_agents" | "components" | "analysis";

export interface AutomationStats {
  totalFlows: number;
  activeFlows: number;
  draftFlows: number;
  totalRuns: number;
}

export interface ScriptStats {
  total: number;
  approved: number;
  pending: number;
  draft: number;
}
