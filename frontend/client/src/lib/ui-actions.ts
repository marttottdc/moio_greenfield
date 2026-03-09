/**
 * UI Action Catalog
 *
 * Single source of truth for every action the AI assistant can trigger in the UI.
 *
 * Usage:
 *   - Frontend: import types + UIActionDispatcher to execute actions
 *   - Backend:  serialize UI_ACTION_CATALOG to JSON and inject into the AI system prompt
 *   - Parser:   use parseAgentResponse() to safely decode backend responses
 */

// ---------------------------------------------------------------------------
// Route constants
// ---------------------------------------------------------------------------

export const AppRoute = {
  Dashboard:        "/",
  CRM:              "/crm",
  Deals:            "/deals",
  DealsAnalytics:   "/deals/analytics",
  DealsManager:     "/deals/manager",
  Communications:   "/communications",
  Activities:       "/activities",
  Workflows:        "/workflows",
  Tickets:          "/tickets",
  Settings:         "/settings",
  Admin:            "/platform-admin",
  DataLab:          "/datalab",
  FlowNew:          "/flows/new",
  ScriptNew:        "/scripts/new",
  WhatsAppTemplates: "/workflows/whatsapp-templates",
  Webhooks:         "/workflows/webhooks",
  AgentTools:       "/workflows/agent-tools",
  MCPConnections:   "/workflows/mcp-connections",
  JsonSchemas:      "/workflows/json-schemas",
  AgentConsole:     "/agent-console",
} as const;

export type AppRouteValue = typeof AppRoute[keyof typeof AppRoute];

// ---------------------------------------------------------------------------
// Tab enums  (match exactly the string values used in each page's query param)
// ---------------------------------------------------------------------------

export const CRMTab = {
  Overview:   "overview",
  Contacts:   "contacts",
  Accounts:   "accounts",
  MasterData: "master_data",
  Analytics:  "analytics",
} as const;
export type CRMTabValue = typeof CRMTab[keyof typeof CRMTab];

export const WorkflowsTab = {
  Flows:       "flows",
  Campaigns:   "campaigns",
  Audiences:   "audiences",
  AIAgents:    "ai_agents",
  Components:  "components",
  Analysis:    "analysis",
  Reports:     "reports",
  TaskMonitor: "task_monitor",
} as const;
export type WorkflowsTabValue = typeof WorkflowsTab[keyof typeof WorkflowsTab];

export const ActivitiesTab = {
  All:      "all",
  Task:     "task",
  Note:     "note",
  Idea:     "idea",
  Event:    "event",
  Email:    "email",
  Timeline: "timeline",
} as const;
export type ActivitiesTabValue = typeof ActivitiesTab[keyof typeof ActivitiesTab];

export const DataLabTab = {
  Datasets:   "datasets",
  Generators: "generators",
  Components: "components",
  Runs:       "runs",
} as const;
export type DataLabTabValue = typeof DataLabTab[keyof typeof DataLabTab];

// ---------------------------------------------------------------------------
// Field value enums  (match backend/schema values exactly)
// ---------------------------------------------------------------------------

/** Activity kind — matches ActivityKind in activities.tsx */
export const ActivityKind = {
  Task:  "task",
  Note:  "note",
  Idea:  "idea",
  Event: "event",
} as const;
export type ActivityKindValue = typeof ActivityKind[keyof typeof ActivityKind];

/**
 * Task priority — 1–5 numeric scale used in activities.tsx
 *   1 = Low, 2 = Medium-Low, 3 = Medium, 4 = Medium-High, 5 = High
 */
export const TaskPriority = {
  Low:        1,
  MediumLow:  2,
  Medium:     3,
  MediumHigh: 4,
  High:       5,
} as const;
export type TaskPriorityValue = typeof TaskPriority[keyof typeof TaskPriority];

/** Campaign channel — from CampaignChannelEnum in shared/schema.ts */
export const CampaignChannel = {
  WhatsApp: "whatsapp",
  Email:    "email",
  SMS:      "sms",
} as const;
export type CampaignChannelValue = typeof CampaignChannel[keyof typeof CampaignChannel];

/** Campaign kind — from CampaignKindEnum in shared/schema.ts */
export const CampaignKind = {
  Express: "express",
  OneShot: "one_shot",
  Drip:    "drip",
  Planned: "planned",
} as const;
export type CampaignKindValue = typeof CampaignKind[keyof typeof CampaignKind];

/** Campaign status — from CampaignStatusEnum in shared/schema.ts */
export const CampaignStatus = {
  Draft:     "draft",
  Scheduled: "scheduled",
  Active:    "active",
  Paused:    "paused",
  Ended:     "ended",
  Archived:  "archived",
} as const;
export type CampaignStatusValue = typeof CampaignStatus[keyof typeof CampaignStatus];

/**
 * Contact type — dynamic on the backend; these are the common defaults.
 * The backend may have additional custom types configured per organisation.
 */
export const ContactType = {
  Lead:     "Lead",
  Customer: "Customer",
  Partner:  "Partner",
  Vendor:   "Vendor",
} as const;
export type ContactTypeValue = typeof ContactType[keyof typeof ContactType];

/** Anchor type for activity log — the entity an activity entry is attached to */
export const AnchorType = {
  Deal:    "deal",
  Contact: "contact",
} as const;
export type AnchorTypeValue = typeof AnchorType[keyof typeof AnchorType];

// ---------------------------------------------------------------------------
// Prefill shapes (optional partial data the AI can pass to pre-populate forms)
// ---------------------------------------------------------------------------

export interface ContactPrefill {
  name?:    string;
  email?:   string;
  phone?:   string;
  company?: string;
  type?:    ContactTypeValue | string;
  notes?:   string;
}

export interface DealPrefill {
  title?:               string;
  description?:         string;
  value?:               number;
  currency?:            string;
  contact?:             string;   // contact id or name
  stage?:               string;   // stage id or slug (dynamic per pipeline)
  priority?:            string;
  expected_close_date?: string;   // ISO 8601 date string
}

export interface TaskPrefill {
  title?:       string;
  description?: string;
  due_date?:    string;           // ISO 8601 date string
  priority?:    TaskPriorityValue;
}

export interface NotePrefill {
  title?: string;
  body?:  string;
  tags?:  string[];
}

export interface IdeaPrefill {
  title?:  string;
  body?:   string;
  impact?: string;
}

export interface EventPrefill {
  title?:    string;
  start?:    string;             // ISO 8601 datetime
  end?:      string;             // ISO 8601 datetime
  location?: string;
  attendees?: string[];
}

export interface EmailPrefill {
  to?:      string | string[];
  cc?:      string | string[];
  subject?: string;
  body?:    string;
}

export interface ActivityLogPrefill {
  raw_text?:    string;
  anchor_type?: AnchorTypeValue;
  anchor_id?:   string;
}

// ---------------------------------------------------------------------------
// UIAction — discriminated union of every triggerable action
// ---------------------------------------------------------------------------

export type UIAction =

  // --- Navigation ---

  /** Navigate to any arbitrary path in the app. Prefer specific actions when available. */
  | {
      type: "ui.navigate";
      payload: { path: AppRouteValue | string };
    }

  /** Open the CRM hub, optionally jumping to a specific tab. */
  | {
      type: "ui.navigate_to_crm";
      payload?: { tab?: CRMTabValue };
    }

  /** Open the deals Kanban board. */
  | {
      type: "ui.navigate_to_deals";
      payload?: never;
    }

  /** Open the activities / tasks list, optionally at a specific tab. */
  | {
      type: "ui.navigate_to_activities";
      payload?: { tab?: ActivitiesTabValue };
    }

  /** Open the communications / conversations inbox. */
  | {
      type: "ui.navigate_to_communications";
      payload?: never;
    }

  /** Open the workflows hub, optionally at a specific tab. */
  | {
      type: "ui.navigate_to_workflows";
      payload?: { tab?: WorkflowsTabValue };
    }

  /** Open the DataLab workbench, optionally at a specific tab. */
  | {
      type: "ui.navigate_to_datalab";
      payload?: { tab?: DataLabTabValue };
    }

  /** Navigate to a specific campaign detail page. */
  | {
      type: "ui.navigate_to_campaign";
      payload: { campaign_id: string };
    }

  // --- Contacts ---

  /** Open the contact creation form, optionally pre-filling known fields. */
  | {
      type: "ui.open_contact_create";
      payload?: { prefill?: ContactPrefill };
    }

  /** Open the contact edit form for an existing contact. */
  | {
      type: "ui.open_contact_edit";
      payload: { contact_id: string };
    }

  /** Open the contact details view (read-only) for an existing contact. */
  | {
      type: "ui.open_contact_details";
      payload: { contact_id: string };
    }

  /** Navigate to the contacts list with an active search query or type filter. */
  | {
      type: "ui.filter_contacts";
      payload?: { query?: string; type?: ContactTypeValue | string };
    }

  // --- Deals ---

  /** Open the deal creation form, optionally pre-filling known fields. */
  | {
      type: "ui.open_deal_create";
      payload?: { prefill?: DealPrefill };
    }

  /** Open the deal edit form for an existing deal. */
  | {
      type: "ui.open_deal_edit";
      payload: { deal_id: string };
    }

  /** Open the deal details view for an existing deal. */
  | {
      type: "ui.open_deal_view";
      payload: { deal_id: string };
    }

  // --- Campaigns ---

  /** Open the campaign creation wizard. */
  | {
      type: "ui.open_campaign_create";
      payload?: never;
    }

  // --- Activities & Tasks ---

  /** Open the task creation form, optionally pre-filling known fields. */
  | {
      type: "ui.open_task_create";
      payload?: { prefill?: TaskPrefill };
    }

  /** Open the note creation form, optionally pre-filling known fields. */
  | {
      type: "ui.open_note_create";
      payload?: { prefill?: NotePrefill };
    }

  /** Open the calendar event creation form, optionally pre-filling known fields. */
  | {
      type: "ui.open_event_create";
      payload?: { prefill?: EventPrefill };
    }

  /** Open the idea creation form, optionally pre-filling known fields. */
  | {
      type: "ui.open_idea_create";
      payload?: { prefill?: IdeaPrefill };
    }

  /**
   * Open the quick activity log modal to record an interaction
   * (a meeting, call, or note) optionally linked to a contact or deal.
   */
  | {
      type: "ui.log_activity";
      payload?: { prefill?: ActivityLogPrefill };
    }

  // --- Communications ---

  /** Navigate to communications and open the email compose panel, optionally pre-filled. */
  | {
      type: "ui.compose_email";
      payload?: { prefill?: EmailPrefill };
    }

  /** Open a specific conversation thread in the communications inbox. */
  | {
      type: "ui.open_conversation";
      payload: { conversation_id: string };
    }

  // --- Workflows ---

  /** Open the new workflow flow creation dialog. */
  | {
      type: "ui.open_flow_create";
      payload?: never;
    }

  /** Open the new script creation dialog. */
  | {
      type: "ui.open_script_create";
      payload?: never;
    }

  /** Open the new AI agent creation dialog. */
  | {
      type: "ui.open_agent_create";
      payload?: never;
    };

// ---------------------------------------------------------------------------
// Action type string literal — useful for exhaustive switch checks
// ---------------------------------------------------------------------------

export type UIActionType = UIAction["type"];

export const UI_ACTION_TYPES: UIActionType[] = [
  "ui.navigate",
  "ui.navigate_to_crm",
  "ui.navigate_to_deals",
  "ui.navigate_to_activities",
  "ui.navigate_to_communications",
  "ui.navigate_to_workflows",
  "ui.navigate_to_datalab",
  "ui.navigate_to_campaign",
  "ui.open_contact_create",
  "ui.open_contact_edit",
  "ui.open_contact_details",
  "ui.filter_contacts",
  "ui.open_deal_create",
  "ui.open_deal_edit",
  "ui.open_deal_view",
  "ui.open_campaign_create",
  "ui.open_task_create",
  "ui.open_note_create",
  "ui.open_event_create",
  "ui.open_idea_create",
  "ui.log_activity",
  "ui.compose_email",
  "ui.open_conversation",
  "ui.open_flow_create",
  "ui.open_script_create",
  "ui.open_agent_create",
];

export function isKnownUIActionType(type: string): type is UIActionType {
  return (UI_ACTION_TYPES as string[]).includes(type);
}

// ---------------------------------------------------------------------------
// Descriptor — one entry per action, consumed by the AI backend
// ---------------------------------------------------------------------------

export interface UIActionDescriptor {
  /** Exact string the AI must place in the `type` field. */
  type: UIActionType;
  /** Plain-language description of when the AI should use this action. */
  description: string;
  /** JSON Schema object describing the payload (sent to the AI as context). */
  payloadSchema: Record<string, unknown>;
  /** Concrete example the AI can use as a reference. */
  example: UIAction;
}

// ---------------------------------------------------------------------------
// UI_ACTION_CATALOG — serialize this and send it to the AI system prompt
// ---------------------------------------------------------------------------

export const UI_ACTION_CATALOG: UIActionDescriptor[] = [
  // Navigation
  {
    type: "ui.navigate",
    description:
      "Navigate to any path in the app. Use only when no more specific navigation action exists. Prefer typed navigate_to_* actions instead.",
    payloadSchema: {
      type: "object",
      required: ["path"],
      properties: {
        path: { type: "string", description: "App path to navigate to, e.g. '/settings'" },
      },
    },
    example: { type: "ui.navigate", payload: { path: "/settings" } },
  },
  {
    type: "ui.navigate_to_crm",
    description:
      "Open the CRM hub. Use when the user asks to see contacts, accounts, or the CRM overview. Pass a tab to jump directly to a section.",
    payloadSchema: {
      type: "object",
      properties: {
        tab: {
          type: "string",
          enum: Object.values(CRMTab),
          description: "Which CRM tab to open. Defaults to 'overview'.",
        },
      },
    },
    example: { type: "ui.navigate_to_crm", payload: { tab: "contacts" } },
  },
  {
    type: "ui.navigate_to_deals",
    description:
      "Open the deals Kanban board. Use when the user asks to see the sales pipeline, deals, or opportunities.",
    payloadSchema: { type: "null" },
    example: { type: "ui.navigate_to_deals" },
  },
  {
    type: "ui.navigate_to_activities",
    description:
      "Open the activities list. Use when the user asks to see tasks, notes, ideas, calendar events, or their timeline. Pass a tab to filter by kind.",
    payloadSchema: {
      type: "object",
      properties: {
        tab: {
          type: "string",
          enum: Object.values(ActivitiesTab),
          description: "Which activities tab to open. Defaults to 'all'.",
        },
      },
    },
    example: { type: "ui.navigate_to_activities", payload: { tab: "task" } },
  },
  {
    type: "ui.navigate_to_communications",
    description:
      "Open the communications inbox. Use when the user asks to see conversations, messages, WhatsApp chats, or emails.",
    payloadSchema: { type: "null" },
    example: { type: "ui.navigate_to_communications" },
  },
  {
    type: "ui.navigate_to_workflows",
    description:
      "Open the workflows hub. Use when the user asks about automations, flows, campaigns, AI agents, or reports. Pass a tab to go directly to a section.",
    payloadSchema: {
      type: "object",
      properties: {
        tab: {
          type: "string",
          enum: Object.values(WorkflowsTab),
          description: "Which workflows tab to open. Defaults to 'flows'.",
        },
      },
    },
    example: { type: "ui.navigate_to_workflows", payload: { tab: "campaigns" } },
  },
  {
    type: "ui.navigate_to_datalab",
    description:
      "Open the DataLab workbench. Use when the user asks about datasets, data generators, or data imports.",
    payloadSchema: {
      type: "object",
      properties: {
        tab: {
          type: "string",
          enum: Object.values(DataLabTab),
          description: "Which DataLab tab to open. Defaults to 'datasets'.",
        },
      },
    },
    example: { type: "ui.navigate_to_datalab", payload: { tab: "datasets" } },
  },
  {
    type: "ui.navigate_to_campaign",
    description:
      "Navigate to the detail page of a specific campaign. Use when the user names a campaign or asks to see its results, stats, or configuration.",
    payloadSchema: {
      type: "object",
      required: ["campaign_id"],
      properties: {
        campaign_id: { type: "string", description: "ID of the campaign to open." },
      },
    },
    example: { type: "ui.navigate_to_campaign", payload: { campaign_id: "abc123" } },
  },

  // Contacts
  {
    type: "ui.open_contact_create",
    description:
      "Open the contact creation form. Use when the user says 'create a contact', 'add a client', 'new lead', or provides contact details (name, email, phone) and wants to save them. Pre-fill any known fields.",
    payloadSchema: {
      type: "object",
      properties: {
        prefill: {
          type: "object",
          properties: {
            name:    { type: "string" },
            email:   { type: "string", format: "email" },
            phone:   { type: "string" },
            company: { type: "string" },
            type:    { type: "string", enum: Object.values(ContactType), description: "Contact type. Common values: Lead, Customer, Partner, Vendor." },
            notes:   { type: "string" },
          },
        },
      },
    },
    example: {
      type: "ui.open_contact_create",
      payload: { prefill: { name: "Juan Pérez", phone: "12231231", type: "Lead" } },
    },
  },
  {
    type: "ui.open_contact_edit",
    description:
      "Open the edit form for an existing contact. Use when the user wants to update or modify a specific contact and you have their ID.",
    payloadSchema: {
      type: "object",
      required: ["contact_id"],
      properties: {
        contact_id: { type: "string", description: "ID of the contact to edit." },
      },
    },
    example: { type: "ui.open_contact_edit", payload: { contact_id: "cid_001" } },
  },
  {
    type: "ui.open_contact_details",
    description:
      "Open the details view for a specific contact (read-only). Use when the user asks to see a contact's profile, history, or deals.",
    payloadSchema: {
      type: "object",
      required: ["contact_id"],
      properties: {
        contact_id: { type: "string", description: "ID of the contact to view." },
      },
    },
    example: { type: "ui.open_contact_details", payload: { contact_id: "cid_001" } },
  },
  {
    type: "ui.filter_contacts",
    description:
      "Navigate to the contacts list with a pre-applied search or type filter. Use when the user wants to find contacts matching a name, company, or type.",
    payloadSchema: {
      type: "object",
      properties: {
        query: { type: "string", description: "Free-text search query." },
        type:  { type: "string", enum: Object.values(ContactType), description: "Filter by contact type." },
      },
    },
    example: { type: "ui.filter_contacts", payload: { query: "Acme", type: "Customer" } },
  },

  // Deals
  {
    type: "ui.open_deal_create",
    description:
      "Open the deal creation form. Use when the user says 'create a deal', 'add an opportunity', or provides deal details. Pre-fill any known fields.",
    payloadSchema: {
      type: "object",
      properties: {
        prefill: {
          type: "object",
          properties: {
            title:               { type: "string" },
            description:         { type: "string" },
            value:               { type: "number" },
            currency:            { type: "string", description: "ISO 4217 currency code, e.g. USD, EUR." },
            contact:             { type: "string", description: "Contact name or ID to link." },
            stage:               { type: "string", description: "Pipeline stage name or ID." },
            priority:            { type: "string" },
            expected_close_date: { type: "string", format: "date", description: "ISO 8601 date, e.g. 2026-03-15." },
          },
        },
      },
    },
    example: {
      type: "ui.open_deal_create",
      payload: { prefill: { title: "Enterprise contract", value: 15000, currency: "USD" } },
    },
  },
  {
    type: "ui.open_deal_edit",
    description:
      "Open the edit form for an existing deal. Use when the user wants to update a specific deal and you have its ID.",
    payloadSchema: {
      type: "object",
      required: ["deal_id"],
      properties: {
        deal_id: { type: "string", description: "ID of the deal to edit." },
      },
    },
    example: { type: "ui.open_deal_edit", payload: { deal_id: "deal_001" } },
  },
  {
    type: "ui.open_deal_view",
    description:
      "Open the details panel for a specific deal. Use when the user asks to see a deal's info, stage, or notes.",
    payloadSchema: {
      type: "object",
      required: ["deal_id"],
      properties: {
        deal_id: { type: "string", description: "ID of the deal to view." },
      },
    },
    example: { type: "ui.open_deal_view", payload: { deal_id: "deal_001" } },
  },

  // Campaigns
  {
    type: "ui.open_campaign_create",
    description:
      "Open the campaign creation wizard. Use when the user wants to create a new campaign, blast, or message sequence.",
    payloadSchema: { type: "null" },
    example: { type: "ui.open_campaign_create" },
  },

  // Activities & Tasks
  {
    type: "ui.open_task_create",
    description:
      "Open the task creation form. Use when the user says 'create a task', 'remind me to...', 'I need to do...', or provides a to-do item. Pre-fill title, due date, and priority if known.",
    payloadSchema: {
      type: "object",
      properties: {
        prefill: {
          type: "object",
          properties: {
            title:       { type: "string" },
            description: { type: "string" },
            due_date:    { type: "string", format: "date", description: "ISO 8601 date, e.g. 2026-02-25." },
            priority:    { type: "number", enum: Object.values(TaskPriority), description: "1=Low … 5=High." },
          },
        },
      },
    },
    example: {
      type: "ui.open_task_create",
      payload: { prefill: { title: "Follow up with Acme", due_date: "2026-02-25", priority: 4 } },
    },
  },
  {
    type: "ui.open_note_create",
    description:
      "Open the note creation form. Use when the user wants to jot something down, save a note, or record information without a due date.",
    payloadSchema: {
      type: "object",
      properties: {
        prefill: {
          type: "object",
          properties: {
            title: { type: "string" },
            body:  { type: "string" },
            tags:  { type: "array", items: { type: "string" } },
          },
        },
      },
    },
    example: { type: "ui.open_note_create", payload: { prefill: { title: "Meeting notes", body: "Discussed Q2 goals." } } },
  },
  {
    type: "ui.open_event_create",
    description:
      "Open the calendar event creation form. Use when the user wants to schedule a meeting, call, or appointment.",
    payloadSchema: {
      type: "object",
      properties: {
        prefill: {
          type: "object",
          properties: {
            title:     { type: "string" },
            start:     { type: "string", format: "date-time", description: "ISO 8601 datetime." },
            end:       { type: "string", format: "date-time", description: "ISO 8601 datetime." },
            location:  { type: "string" },
            attendees: { type: "array", items: { type: "string" } },
          },
        },
      },
    },
    example: {
      type: "ui.open_event_create",
      payload: { prefill: { title: "Kick-off call", start: "2026-02-24T10:00:00", end: "2026-02-24T11:00:00" } },
    },
  },
  {
    type: "ui.open_idea_create",
    description:
      "Open the idea creation form. Use when the user wants to capture a thought, suggestion, or creative idea.",
    payloadSchema: {
      type: "object",
      properties: {
        prefill: {
          type: "object",
          properties: {
            title:  { type: "string" },
            body:   { type: "string" },
            impact: { type: "string" },
          },
        },
      },
    },
    example: { type: "ui.open_idea_create", payload: { prefill: { title: "New onboarding flow idea" } } },
  },
  {
    type: "ui.log_activity",
    description:
      "Open the quick activity log to record a past interaction — a call, meeting, or note — optionally linked to a contact or deal. Use when the user says 'I just spoke with...', 'log a call', or 'record that I met with...'.",
    payloadSchema: {
      type: "object",
      properties: {
        prefill: {
          type: "object",
          properties: {
            raw_text:    { type: "string", description: "Free-text description of the interaction." },
            anchor_type: { type: "string", enum: Object.values(AnchorType), description: "Entity the log is linked to." },
            anchor_id:   { type: "string", description: "ID of the linked contact or deal." },
          },
        },
      },
    },
    example: {
      type: "ui.log_activity",
      payload: { prefill: { raw_text: "Called Juan, interested in enterprise plan.", anchor_type: "contact", anchor_id: "cid_001" } },
    },
  },

  // Communications
  {
    type: "ui.compose_email",
    description:
      "Open the email compose panel. Use when the user wants to send an email, optionally pre-filling the recipient, subject, or body.",
    payloadSchema: {
      type: "object",
      properties: {
        prefill: {
          type: "object",
          properties: {
            to:      { oneOf: [{ type: "string" }, { type: "array", items: { type: "string" } }] },
            cc:      { oneOf: [{ type: "string" }, { type: "array", items: { type: "string" } }] },
            subject: { type: "string" },
            body:    { type: "string" },
          },
        },
      },
    },
    example: { type: "ui.compose_email", payload: { prefill: { to: "juan@acme.com", subject: "Follow-up" } } },
  },
  {
    type: "ui.open_conversation",
    description:
      "Open a specific conversation thread in the communications inbox. Use when you have the conversation ID and the user wants to view or continue a chat.",
    payloadSchema: {
      type: "object",
      required: ["conversation_id"],
      properties: {
        conversation_id: { type: "string", description: "ID of the conversation to open." },
      },
    },
    example: { type: "ui.open_conversation", payload: { conversation_id: "conv_001" } },
  },

  // Workflows
  {
    type: "ui.open_flow_create",
    description:
      "Open the new workflow flow creation dialog. Use when the user wants to build a new automation or flow.",
    payloadSchema: { type: "null" },
    example: { type: "ui.open_flow_create" },
  },
  {
    type: "ui.open_script_create",
    description:
      "Open the new script creation dialog. Use when the user wants to create a new automation script.",
    payloadSchema: { type: "null" },
    example: { type: "ui.open_script_create" },
  },
  {
    type: "ui.open_agent_create",
    description:
      "Open the new AI agent creation dialog. Use when the user wants to create a new AI agent or bot.",
    payloadSchema: { type: "null" },
    example: { type: "ui.open_agent_create" },
  },
];

// ---------------------------------------------------------------------------
// Agent response shape — what the backend AI returns
// ---------------------------------------------------------------------------

export interface AgentResponse {
  /** Human-readable message to display in the chat. */
  assistant_message: string;
  /** Zero or more UI actions to execute after displaying the message. */
  ui_actions?: UIAction[];
}

// ---------------------------------------------------------------------------
// parseAgentResponse — safely decode a raw backend message string
// ---------------------------------------------------------------------------

export interface ParsedAgentResponse {
  /** Text to display in the chat bubble. */
  message: string;
  /** Valid, known UI actions extracted from the response. */
  actions: UIAction[];
  /** Raw entries whose `type` was not in the catalog (AI hallucination / future action). */
  unknownActions: unknown[];
}

/**
 * Parse a raw string from the AI backend into a message + actions.
 *
 * - If the string is valid JSON with `assistant_message`, extracts it plus any `ui_actions`.
 * - If the string is plain text, returns it as the message with no actions.
 * - Unknown action types are silently collected in `unknownActions` and never executed.
 */
export function parseAgentResponse(raw: string): ParsedAgentResponse {
  const fallback: ParsedAgentResponse = { message: raw, actions: [], unknownActions: [] };

  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return fallback;
  }

  if (
    typeof parsed !== "object" ||
    parsed === null ||
    typeof (parsed as Record<string, unknown>).assistant_message !== "string"
  ) {
    return fallback;
  }

  const response = parsed as AgentResponse;
  const message = response.assistant_message;
  const rawActions: unknown[] = Array.isArray(response.ui_actions) ? response.ui_actions : [];

  const actions: UIAction[] = [];
  const unknownActions: unknown[] = [];

  for (const entry of rawActions) {
    if (
      typeof entry === "object" &&
      entry !== null &&
      typeof (entry as Record<string, unknown>).type === "string" &&
      isKnownUIActionType((entry as Record<string, unknown>).type as string)
    ) {
      actions.push(entry as UIAction);
    } else {
      unknownActions.push(entry);
    }
  }

  return { message, actions, unknownActions };
}

/**
 * Serialize the catalog to a JSON string suitable for injection into an AI system prompt.
 * The backend uses this to know exactly what UI actions it can produce.
 */
export function serializeCatalogForPrompt(): string {
  return JSON.stringify(
    UI_ACTION_CATALOG.map(({ type, description, payloadSchema, example }) => ({
      type,
      description,
      payloadSchema,
      example,
    })),
    null,
    2,
  );
}
