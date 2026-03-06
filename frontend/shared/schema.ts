import { sql } from "drizzle-orm";
import { pgTable, text, varchar, timestamp, integer } from "drizzle-orm/pg-core";
import { createInsertSchema } from "drizzle-zod";
import { z } from "zod";

export const users = pgTable("users", {
  id: varchar("id").primaryKey().default(sql`gen_random_uuid()`),
  username: text("username").notNull().unique(),
  password: text("password").notNull(),
});

export const contacts = pgTable("contacts", {
  id: varchar("id").primaryKey().default(sql`gen_random_uuid()`),
  name: text("name").notNull(),
  email: text("email"),
  company: text("company"),
  phone: text("phone"),
  type: text("type").notNull().default("Lead"),
  createdAt: timestamp("created_at").defaultNow(),
});

export const campaigns = pgTable("campaigns", {
  id: varchar("id").primaryKey().default(sql`gen_random_uuid()`),
  name: text("name").notNull(),
  description: text("description"),
  status: text("status").notNull().default("Active"),
  channel: text("channel").notNull().default("WhatsApp"),
  sent: integer("sent").default(0),
  opened: integer("opened").default(0),
  clicked: integer("clicked").default(0),
  createdAt: timestamp("created_at").defaultNow(),
});

export const workflows = pgTable("workflows", {
  id: varchar("id").primaryKey().default(sql`gen_random_uuid()`),
  name: text("name").notNull(),
  status: text("status").notNull().default("Testing"),
  createdAt: timestamp("created_at").defaultNow(),
});

export const insertUserSchema = createInsertSchema(users).pick({
  username: true,
  password: true,
});

export const insertContactSchema = createInsertSchema(contacts).omit({
  id: true,
  createdAt: true,
});

export const insertCampaignSchema = createInsertSchema(campaigns).omit({
  id: true,
  createdAt: true,
});

export const insertWorkflowSchema = createInsertSchema(workflows).omit({
  id: true,
  createdAt: true,
});

export type InsertUser = z.infer<typeof insertUserSchema>;
export type User = typeof users.$inferSelect;
export type Contact = typeof contacts.$inferSelect;
export type InsertContact = z.infer<typeof insertContactSchema>;
export type Campaign = typeof campaigns.$inferSelect;
export type InsertCampaign = z.infer<typeof insertCampaignSchema>;
export type Workflow = typeof workflows.$inferSelect;
export type InsertWorkflow = z.infer<typeof insertWorkflowSchema>;

// Campaign Wizard V2 Types

export const CampaignChannelEnum = z.enum(["whatsapp", "email", "sms"]);
export type CampaignChannel = z.infer<typeof CampaignChannelEnum>;

export const CampaignKindEnum = z.enum(["express", "one_shot", "drip", "planned"]);
export type CampaignKind = z.infer<typeof CampaignKindEnum>;

export const CampaignStatusEnum = z.enum([
  "draft",
  "scheduled",
  "active",
  "paused",
  "ended",
  "archived"
]);
export type CampaignStatus = z.infer<typeof CampaignStatusEnum>;

export const templateVariableSchema = z.object({
  name: z.string(),
  type: z.enum(["text", "phone", "email", "date", "number", "url", "media"]),
  required: z.boolean().default(true),
  description: z.string().optional(),
  example: z.string().optional(),
});
export type TemplateVariable = z.infer<typeof templateVariableSchema>;

export const campaignTemplateSchema = z.object({
  id: z.string(),
  name: z.string(),
  channel: CampaignChannelEnum,
  content: z.string().optional(),
  variables: z.array(templateVariableSchema),
  language: z.string().optional(),
  status: z.string().optional(),
  category: z.string().optional(),
  preview_url: z.string().optional(),
  created_at: z.string().optional(),
  updated_at: z.string().optional(),
});
export type CampaignTemplate = z.infer<typeof campaignTemplateSchema>;

export const stagingColumnSchema = z.object({
  name: z.string(),
  index: z.number(),
  sample_values: z.array(z.string()),
  inferred_type: z.enum(["text", "phone", "email", "date", "number", "unknown"]).optional(),
});
export type StagingColumn = z.infer<typeof stagingColumnSchema>;

export const stagingImportSchema = z.object({
  staging_id: z.string(),
  filename: z.string(),
  total_rows: z.number(),
  columns: z.array(stagingColumnSchema),
  preview_rows: z.array(z.record(z.string())),
  errors: z.array(z.string()).optional(),
  created_at: z.string(),
});
export type StagingImport = z.infer<typeof stagingImportSchema>;

export const fieldMappingSchema = z.object({
  column_name: z.string(),
  variable_name: z.string(),
});
export type FieldMapping = z.infer<typeof fieldMappingSchema>;

export const mappingValidationSchema = z.object({
  staging_id: z.string(),
  mappings: z.array(fieldMappingSchema),
});
export type MappingValidation = z.infer<typeof mappingValidationSchema>;

export const mappingValidationResultSchema = z.object({
  valid: z.boolean(),
  errors: z.array(z.object({
    row: z.number().optional(),
    column: z.string(),
    message: z.string(),
  })).optional(),
  warnings: z.array(z.string()).optional(),
  sample_output: z.array(z.record(z.string())).optional(),
});
export type MappingValidationResult = z.infer<typeof mappingValidationResultSchema>;

export const dripStepSchema = z.object({
  step_number: z.number(),
  delay_days: z.number().default(0),
  delay_hours: z.number().default(0),
  template_id: z.string().optional(),
  condition: z.string().optional(),
});
export type DripStep = z.infer<typeof dripStepSchema>;

export const campaignScheduleSchema = z.object({
  start_at: z.string().optional(),
  end_at: z.string().optional(),
  timezone: z.string().default("UTC"),
  drip_steps: z.array(dripStepSchema).optional(),
  send_windows: z.array(z.object({
    days: z.array(z.number()),
    start_hour: z.number(),
    end_hour: z.number(),
  })).optional(),
});
export type CampaignSchedule = z.infer<typeof campaignScheduleSchema>;

export const campaignCreatePayloadSchema = z.object({
  name: z.string().min(1, "Campaign name is required"),
  description: z.string().optional(),
  channel: CampaignChannelEnum,
  kind: CampaignKindEnum,
  template_id: z.string(),
  staging_id: z.string().optional(),
  mappings: z.array(fieldMappingSchema).optional(),
  schedule: campaignScheduleSchema.optional(),
  audience_id: z.string().optional(),
});
export type CampaignCreatePayload = z.infer<typeof campaignCreatePayloadSchema>;

// SSE Event Types for Live Campaign Monitoring

export const campaignStatsEventSchema = z.object({
  type: z.literal("stats"),
  campaign_id: z.string(),
  sent: z.number(),
  delivered: z.number(),
  opened: z.number(),
  failed: z.number(),
  responded: z.number(),
  pending: z.number().optional(),
  updated_at: z.string(),
});
export type CampaignStatsEvent = z.infer<typeof campaignStatsEventSchema>;

export const MessageStatusEnum = z.enum([
  "pending",
  "sent",
  "delivered",
  "read",
  "failed",
  "responded"
]);
export type MessageStatus = z.infer<typeof MessageStatusEnum>;

export const campaignMessageEventSchema = z.object({
  type: z.literal("message"),
  campaign_id: z.string(),
  message_id: z.string(),
  contact_id: z.string(),
  contact_name: z.string().optional(),
  status: MessageStatusEnum,
  channel: CampaignChannelEnum,
  error: z.string().optional(),
  timestamp: z.string(),
});
export type CampaignMessageEvent = z.infer<typeof campaignMessageEventSchema>;

export const campaignTimelineEventSchema = z.object({
  type: z.literal("timeline"),
  campaign_id: z.string(),
  status: CampaignStatusEnum,
  previous_status: CampaignStatusEnum.optional(),
  changed_by: z.string().optional(),
  timestamp: z.string(),
});
export type CampaignTimelineEvent = z.infer<typeof campaignTimelineEventSchema>;

export const campaignSSEEventSchema = z.discriminatedUnion("type", [
  campaignStatsEventSchema,
  campaignMessageEventSchema,
  campaignTimelineEventSchema,
]);
export type CampaignSSEEvent = z.infer<typeof campaignSSEEventSchema>;

// ============================================================================
// Campaign FSM (Finite State Machine) Types
// ============================================================================

export const CampaignFlowStateEnum = z.enum([
  "DRAFT",
  "SELECT_TEMPLATE",
  "IMPORT_DATA",
  "CONFIGURE_MAPPING",
  "SET_AUDIENCE",
  "READY",
  "SCHEDULED",
  "ACTIVE",
  "ENDED",
  "ARCHIVED",
]);
export type CampaignFlowState = z.infer<typeof CampaignFlowStateEnum>;

export const CampaignTransitionActionEnum = z.enum([
  "select-template",
  "import-data",
  "configure-mapping",
  "set-audience",
  "mark-ready",
  "set-schedule",
  "launch-now",
  "rollback",
  "pause",
  "resume",
  "end",
  "archive",
]);
export type CampaignTransitionAction = z.infer<typeof CampaignTransitionActionEnum>;

export const flowStateMissingRequirementSchema = z.object({
  field: z.string(),
  message: z.string(),
});
export type FlowStateMissingRequirement = z.infer<typeof flowStateMissingRequirementSchema>;

export const flowStateConfigurationSchema = z.object({
  template_id: z.string().nullable().optional(),
  template_name: z.string().nullable().optional(),
  staging_id: z.string().nullable().optional(),
  staging_filename: z.string().nullable().optional(),
  staging_row_count: z.number().nullable().optional(),
  mapping_configured: z.boolean().optional(),
  contact_name_field: z.string().nullable().optional(),
  audience_id: z.string().nullable().optional(),
  audience_name: z.string().nullable().optional(),
  audience_size: z.number().nullable().optional(),
});
export type FlowStateConfiguration = z.infer<typeof flowStateConfigurationSchema>;

export const campaignFlowStateResponseSchema = z.object({
  campaign_id: z.string(),
  state: CampaignFlowStateEnum,
  allowed_actions: z.array(CampaignTransitionActionEnum),
  missing_requirements: z.array(flowStateMissingRequirementSchema).optional(),
  configuration: flowStateConfigurationSchema.optional(),
  requirements: z.record(z.boolean()).optional(),
});
export type CampaignFlowStateResponse = z.infer<typeof campaignFlowStateResponseSchema>;

export const campaignTransitionResponseSchema = z.object({
  success: z.boolean(),
  message: z.string().optional(),
  campaign: z.record(z.unknown()).optional(),
  new_state: CampaignFlowStateEnum.optional(),
  error: z.string().optional(),
});
export type CampaignTransitionResponse = z.infer<typeof campaignTransitionResponseSchema>;

// Transition payloads
export const selectTemplatePayloadSchema = z.object({
  template_id: z.string(),
});
export type SelectTemplatePayload = z.infer<typeof selectTemplatePayloadSchema>;

export const importDataPayloadSchema = z.object({
  staging_id: z.string(),
  headers: z.array(z.string()),
  row_count: z.number(),
});
export type ImportDataPayload = z.infer<typeof importDataPayloadSchema>;

export const configureMappingPayloadSchema = z.object({
  mapping: z.array(z.object({
    source: z.string(),
    target: z.string(),
  })),
  contact_name_field: z.string().optional(),
});
export type ConfigureMappingPayload = z.infer<typeof configureMappingPayloadSchema>;

export const setAudiencePayloadSchema = z.object({
  audience_id: z.string(),
});
export type SetAudiencePayload = z.infer<typeof setAudiencePayloadSchema>;

export const setSchedulePayloadSchema = z.object({
  schedule_date: z.string(),
});
export type SetSchedulePayload = z.infer<typeof setSchedulePayloadSchema>;

// ============================================================================
// New SSE Event Types for FSM-based Campaign Monitoring
// ============================================================================

export const campaignFSMStatsEventSchema = z.object({
  type: z.literal("stats"),
  campaign_id: z.string(),
  total: z.number(),
  pending: z.number(),
  sent: z.number(),
  delivered: z.number(),
  failed: z.number(),
  skipped: z.number(),
  progress_percent: z.number(),
  success_rate: z.number(),
  updated_at: z.string().optional(),
});
export type CampaignFSMStatsEvent = z.infer<typeof campaignFSMStatsEventSchema>;

export const campaignScheduledEventSchema = z.object({
  type: z.literal("campaign_scheduled"),
  campaign_id: z.string(),
  schedule_date: z.string(),
  status: z.string(),
  timestamp: z.string().optional(),
});
export type CampaignScheduledEvent = z.infer<typeof campaignScheduledEventSchema>;

export const campaignLaunchedEventSchema = z.object({
  type: z.literal("campaign_launched"),
  campaign_id: z.string(),
  status: z.string(),
  timestamp: z.string().optional(),
});
export type CampaignLaunchedEvent = z.infer<typeof campaignLaunchedEventSchema>;

export const campaignCompletedEventSchema = z.object({
  type: z.literal("campaign_completed"),
  campaign_id: z.string(),
  reason: z.string(),
  stats: z.object({
    total: z.number(),
    sent: z.number(),
    delivered: z.number(),
    failed: z.number(),
  }).optional(),
  timestamp: z.string().optional(),
});
export type CampaignCompletedEvent = z.infer<typeof campaignCompletedEventSchema>;

export const messageSentEventSchema = z.object({
  type: z.literal("message_sent"),
  campaign_id: z.string(),
  contact_id: z.string(),
  message_id: z.string(),
  timestamp: z.string().optional(),
});
export type MessageSentEvent = z.infer<typeof messageSentEventSchema>;

export const messageDeliveredEventSchema = z.object({
  type: z.literal("message_delivered"),
  campaign_id: z.string(),
  contact_id: z.string(),
  message_id: z.string(),
  timestamp: z.string().optional(),
});
export type MessageDeliveredEvent = z.infer<typeof messageDeliveredEventSchema>;

export const messageFailedEventSchema = z.object({
  type: z.literal("message_failed"),
  campaign_id: z.string(),
  contact_id: z.string(),
  error: z.string(),
  timestamp: z.string().optional(),
});
export type MessageFailedEvent = z.infer<typeof messageFailedEventSchema>;

export const campaignFSMSSEEventSchema = z.discriminatedUnion("type", [
  campaignFSMStatsEventSchema,
  campaignScheduledEventSchema,
  campaignLaunchedEventSchema,
  campaignCompletedEventSchema,
  messageSentEventSchema,
  messageDeliveredEventSchema,
  messageFailedEventSchema,
]);
export type CampaignFSMSSEEvent = z.infer<typeof campaignFSMSSEEventSchema>;

// ============================================================================
// Dashboard Preferences Schema (User Customization)
// ============================================================================

export const WidgetSizeEnum = z.enum(["small", "medium", "large", "full"]);
export type WidgetSize = z.infer<typeof WidgetSizeEnum>;

export const WidgetTypeEnum = z.enum([
  "kpi_card",
  "recent_campaigns",
  "recent_audiences",
  "crm_assistant",
  "favorites",
  "frequently_used",
  "activity_chart",
  "performance_metrics",
  "quick_actions",
  "my_tasks",
  "global_timeline",
]);
export type WidgetType = z.infer<typeof WidgetTypeEnum>;

export const KPITypeEnum = z.enum([
  "total_campaigns",
  "total_audiences",
  "total_sent",
  "total_opened",
  "open_rate",
  "click_rate",
  "total_contacts",
  "active_deals",
  "conversion_rate",
  "response_rate",
]);
export type KPIType = z.infer<typeof KPITypeEnum>;

export const widgetConfigSchema = z.object({
  id: z.string(),
  type: WidgetTypeEnum,
  enabled: z.boolean().default(true),
  size: WidgetSizeEnum.default("medium"),
  order: z.number().default(0),
  title: z.string().optional(),
  config: z.record(z.unknown()).optional(),
});
export type WidgetConfig = z.infer<typeof widgetConfigSchema>;

export const kpiPreferencesSchema = z.object({
  enabled: z.boolean().default(true),
  visible_kpis: z.array(KPITypeEnum).default([
    "total_campaigns",
    "total_audiences",
    "total_sent",
    "open_rate",
  ]),
  refresh_interval: z.number().optional(),
});
export type KPIPreferences = z.infer<typeof kpiPreferencesSchema>;

export const assistantPreferencesSchema = z.object({
  sidebar_collapsed: z.boolean().default(true),
  conversation_sort: z.enum(["recent", "oldest", "alphabetical"]).default("recent"),
  show_conversation_history: z.boolean().default(true),
});
export type AssistantPreferences = z.infer<typeof assistantPreferencesSchema>;

export const favoriteItemSchema = z.object({
  id: z.string(),
  type: z.enum(["page", "campaign", "contact", "deal", "workflow"]),
  name: z.string(),
  path: z.string().optional(),
});
export type FavoriteItem = z.infer<typeof favoriteItemSchema>;

export const userDashboardPreferencesSchema = z.object({
  layout_version: z.number().default(1),
  widgets: z.array(widgetConfigSchema).default([]),
  kpis: kpiPreferencesSchema.default({}),
  assistant: assistantPreferencesSchema.default({}),
  favorites: z.array(favoriteItemSchema).default([]),
  frequently_used: z.array(z.string()).default([]),
  theme: z.object({
    compact_mode: z.boolean().default(false),
    show_welcome_banner: z.boolean().default(true),
  }).default({}),
});
export type UserDashboardPreferences = z.infer<typeof userDashboardPreferencesSchema>;

// Default preferences for new users
export const DEFAULT_DASHBOARD_PREFERENCES: UserDashboardPreferences = {
  layout_version: 1,
  widgets: [
    { id: "kpi-ribbon", type: "kpi_card", enabled: true, size: "full", order: 0 },
    { id: "crm-assistant", type: "crm_assistant", enabled: true, size: "full", order: 1 },
    { id: "recent-campaigns", type: "recent_campaigns", enabled: true, size: "large", order: 2 },
    { id: "recent-audiences", type: "recent_audiences", enabled: true, size: "medium", order: 3 },
    { id: "favorites", type: "favorites", enabled: true, size: "medium", order: 4 },
    { id: "activity-chart", type: "activity_chart", enabled: true, size: "full", order: 5 },
    { id: "global-timeline", type: "global_timeline", enabled: true, size: "large", order: 6 },
  ],
  kpis: {
    enabled: true,
    visible_kpis: ["total_campaigns", "total_audiences", "total_sent", "open_rate"],
  },
  assistant: {
    sidebar_collapsed: true,
    conversation_sort: "recent",
    show_conversation_history: true,
  },
  favorites: [],
  frequently_used: [],
  theme: {
    compact_mode: false,
    show_welcome_banner: true,
  },
};
