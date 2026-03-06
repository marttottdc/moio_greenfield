export interface ModelField {
  name: string;
  type: string;
  is_relation: boolean;
}

export interface AvailableModel {
  model_path: string;
  model_label: string;
  name: string;
  app_label: string;
  fields: ModelField[];
}

export interface FlowSchedule {
  id?: string;
  flow_id?: string;
  schedule_type: "cron" | "interval" | "one_off";
  cron_expression: string | null;
  interval_seconds: number | null;
  run_at: string | null;
  timezone: string;
  is_active: boolean;
  next_run_at?: string | null;
  last_run_at?: string | null;
  inputs?: Record<string, any>;
  created_at?: string;
  updated_at?: string;
}

export interface EventTriggerConfig {
  event_name: string;                          // Required - from EventDefinition.name
  event_id?: string;                           // Optional - event ID for fetching details
  conditions?: Record<string, string>;         // Optional - filter which events trigger
  event_schema?: Record<string, any> | null;   // Schema derived from payload_schema or example_payload
}

export interface ScheduleConfig {
  schedule_type: "cron" | "interval" | "one_off";
  cron_expression: string | null;
  interval_seconds: number | null;
  run_at: string | null;
  timezone: string;
}

export const DEFAULT_EVENT_CONFIG: EventTriggerConfig = {
  event_name: "",
  conditions: {},
};

export const DEFAULT_SCHEDULE_CONFIG: ScheduleConfig = {
  schedule_type: "cron",
  cron_expression: "0 9 * * *",
  interval_seconds: null,
  run_at: null,
  timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
};

export interface CronPreset {
  label: string;
  description: string;
  cron: string;
  category: "daily" | "weekly" | "monthly" | "custom";
}

export const CRON_PRESETS: CronPreset[] = [
  { label: "Every hour", description: "At the start of every hour", cron: "0 * * * *", category: "custom" },
  { label: "Every day at 9 AM", description: "Once daily at 9:00 AM", cron: "0 9 * * *", category: "daily" },
  { label: "Every day at 6 PM", description: "Once daily at 6:00 PM", cron: "0 18 * * *", category: "daily" },
  { label: "Every Monday at 9 AM", description: "Weekly on Monday morning", cron: "0 9 * * 1", category: "weekly" },
  { label: "Every Friday at 5 PM", description: "Weekly on Friday evening", cron: "0 17 * * 5", category: "weekly" },
  { label: "Weekdays at 9 AM", description: "Monday through Friday at 9 AM", cron: "0 9 * * 1-5", category: "weekly" },
  { label: "First day of month", description: "Monthly on the 1st at 9 AM", cron: "0 9 1 * *", category: "monthly" },
  { label: "Last weekday of month", description: "Last business day at 5 PM", cron: "0 17 L * 1-5", category: "monthly" },
];

export const INTERVAL_PRESETS = [
  { label: "Every 5 minutes", seconds: 300 },
  { label: "Every 15 minutes", seconds: 900 },
  { label: "Every 30 minutes", seconds: 1800 },
  { label: "Every hour", seconds: 3600 },
  { label: "Every 2 hours", seconds: 7200 },
  { label: "Every 6 hours", seconds: 21600 },
  { label: "Every 12 hours", seconds: 43200 },
  { label: "Every 24 hours", seconds: 86400 },
];

export const TIMEZONE_OPTIONS = [
  "UTC",
  "America/New_York",
  "America/Chicago",
  "America/Denver",
  "America/Los_Angeles",
  "America/Sao_Paulo",
  "Europe/London",
  "Europe/Paris",
  "Europe/Berlin",
  "Europe/Madrid",
  "Asia/Tokyo",
  "Asia/Shanghai",
  "Asia/Singapore",
  "Australia/Sydney",
];
