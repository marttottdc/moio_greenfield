/**
 * Moio Platform Public API TypeScript Definitions
 * Based on MOIO_PUBLIC_API_REFERENCE.md
 */

// Standard pagination response structure used across all list endpoints
export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

// Standard error response structure
export interface MoioErrorResponse {
  error: string;
  message: string;
  fields?: Record<string, string[]>;
}

// Authentication responses
export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  user: User;
}

export interface RefreshTokenResponse {
  access_token: string;
  refresh_token: string;
}

export interface User {
  id: string;
  full_name: string;
  role: string;
  email?: string;
  username?: string;
  avatar_url?: string | null;
  organization?: OrganizationSummary | null;
}

export interface OrganizationSummary {
  id: string;
  name: string | null;
}

// Contact & Deal module types
export interface Contact {
  id: string;
  name: string;
  // Additional identity fields (create may accept them; backend may return them)
  fullname?: string | null;
  whatsapp_name?: string | null;

  email?: string | null;
  phone?: string | null;
  company?: string | null;
  source?: string | null;

  // Backend supports dynamic contact types (Lead/Customer/Partner/Vendor/etc)
  type: string;
  tags?: string[];
  custom_fields?: Record<string, unknown>;
  activity_summary?: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface Deal {
  id: string;
  title: string;
  contact_id: string;
  stage: "Qualified" | "Proposal" | "Negotiation" | "Closed";
  value: number;
  probability: number;
  expected_close_date?: string;
  created_at: string;
  updated_at: string;
}

// Communications module types
export interface Conversation {
  id: string;
  contact_id: string;
  channel: "WhatsApp" | "Email" | "SMS";
  last_message_at: string;
  unread_count: number;
  status: "active" | "archived";
}

export interface Message {
  id: string;
  conversation_id: string;
  content: string;
  sender: "user" | "contact" | "system";
  timestamp: string;
  status?: "sent" | "delivered" | "read" | "failed";
}

// Campaigns module types (Campaigns & Audiences API)
export type CampaignChannel = "email" | "whatsapp" | "telegram" | "sms";
export type CampaignKind = "express" | "one_shot" | "drip" | "planned";
export type CampaignStatus = "draft" | "ready" | "scheduled" | "active" | "ended" | "archived";
export type AudienceKind = "static" | "dynamic";

export interface CampaignConfigurationState {
  audience?: boolean;
  template?: boolean;
  mapping?: boolean;
  defaults?: boolean;
  schedule?: boolean;
  data_ready?: boolean;
  [key: string]: boolean | undefined;
}

export interface CampaignMessageConfig {
  template_id?: string;
  template_name?: string;
  map?: Array<Record<string, unknown>>;
  [key: string]: unknown;
}

export interface CampaignScheduleConfig {
  date?: string | null;
  timezone?: string | null;
  [key: string]: unknown;
}

export interface CampaignConfig {
  message?: CampaignMessageConfig;
  defaults?: Record<string, unknown>;
  schedule?: CampaignScheduleConfig;
  [key: string]: unknown;
}

export interface Campaign {
  id: string;
  name: string;
  description?: string | null;
  channel: CampaignChannel;
  kind: CampaignKind;
  status: CampaignStatus;
  sent: number;
  opened: number;
  responded: number;
  audience?: string | null;
  audience_name: string;
  audience_size: number;
  open_rate: number;
  ready_to_launch: boolean;
  created: string;
  updated: string;
}

export interface CampaignDetail extends Campaign {
  config?: CampaignConfig;
  configuration_state?: CampaignConfigurationState;
  audience_kind?: AudienceKind | null;
}

export interface AudienceRecord {
  id: string;
  name: string;
  description?: string | null;
  kind: AudienceKind;
  size: number;
  is_draft: boolean;
  materialized_at?: string | null;
  created: string;
  updated: string;
  rules?: Record<string, unknown> | null;
}

// Workflows & Automation module types
export interface Workflow {
  id: string;
  name: string;
  status: "Testing" | "Active" | "Disabled";
  trigger_type: "webhook" | "schedule" | "manual" | "event";
  actions_count: number;
  executions_count: number;
  created_at: string;
  updated_at: string;
}

// Tickets module types
export interface Ticket {
  id: string;
  title: string;
  description?: string;
  contact_id?: string;
  status: "Open" | "In Progress" | "Resolved" | "Closed";
  priority: "Low" | "Medium" | "High" | "Urgent";
  assigned_to?: string;
  created_at: string;
  updated_at: string;
}

// Platform Experience - Conversational Widgets
export interface ConversationTurn {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
}

export interface ChatResponse {
  message: string;
  suggestions?: string[];
  action?: {
    type: string;
    data: Record<string, unknown>;
  };
}

// Core Services - Integration Management
export interface Integration {
  id: string;
  name: string;
  provider: string;
  status: "connected" | "disconnected" | "error";
  config: Record<string, unknown>;
  last_sync_at?: string;
}

// Query parameters for filtering and pagination
export interface ListQueryParams {
  page?: number;
  page_size?: number;
  search?: string;
  ordering?: string;
  [key: string]: string | number | boolean | undefined;
}

// Common field types
export type ISODateString = string;
export type UUID = string;

// ============================================================================
// Data Lab Module Types
// ============================================================================

// Core Data Lab Types
export interface ColumnDefinition {
  name: string;
  type: 'string' | 'integer' | 'decimal' | 'boolean' | 'date' | 'datetime' | 'uuid';
  nullable: boolean;
  original_type?: string;
}

export interface ResultSet {
  id: string;
  name: string | null;
  origin: 'import' | 'crm_query' | 'script' | 'pipeline';
  schema_json: ColumnDefinition[];
  row_count: number;
  storage: 'memory' | 'parquet';
  storage_key?: string;
  preview_json: Record<string, any>[];
  lineage_json: {
    inputs?: any[];
    filters?: Record<string, any>;
    contract?: ImportContract;
    [key: string]: any;
  };
  created_by?: string;
  created_at: string;
  expires_at?: string | null;
}

// Import Contract Types
export interface PageSelector {
  type: "first" | "last" | "repeated" | "regex";
  value?: string;
}

export interface ImportContract {
  version: "1";
  parser: {
    type: "csv" | "excel" | "pdf";
    delimiter?: string;
    header_row?: number;
    skip_rows?: number;
    sheet?: string | number;
    encoding?: string;
    range?: {
      start_row?: number;
      end_row?: number;
      start_col?: string;
      end_col?: string;
    };
    date_format?: string;
    datetime_format?: string;
    structural_unit?: {
      kind: "pdf_table" | "pdf_region";
      selector: {
        page_selector: PageSelector;
        bbox?: [number, number, number, number];
      };
    };
  };
  mapping: MappingItem[];
  dedupe?: {
    keys: string[];
    strategy: "keep_first" | "keep_last";
  };
  output: {
    name: string;
    materialize?: boolean;
    accumulation_strategy?: "append" | "merge";
    merge_keys?: string[];
  };
}

export interface MappingItem {
  source: string;
  target: string;
  type: "string" | "integer" | "decimal" | "boolean" | "date" | "datetime";
  clean?: ("trim" | "upper" | "lower" | "capitalize" | "remove_non_numeric" | "currency_to_decimal")[];
}

// File & FileSet Types
export interface DataLabFile {
  id: string;
  filename: string;
  content_type: string;
  size: number;
  storage_key?: string;
  created_at: string;
}

export interface FileSet {
  id: string;
  name: string;
  description?: string;
  file_count: number;
  created_at: string;
  updated_at: string;
}

// CRM DataSource Types
export interface CRMView {
  id: string;
  key: string;
  label: string;
  description?: string;
  schema_json: ColumnDefinition[];
  allowed_filters_json: string[];
  default_filters_json: Record<string, any>;
  is_active: boolean;
  created_at?: string; // ISO 8601 timestamp
}

export interface CRMQueryRequest {
  view_key: string;
  filters?: Record<string, any>;
  limit?: number;
  materialize?: boolean;
}

// Script Types
export interface Script {
  id: string;
  name: string;
  slug: string;
  description?: string;
  code: string;
  // Backend returns input_spec/output_spec, but accepts input_spec_json/output_spec_json on create/update
  input_spec?: Record<string, ScriptInputSpec>;
  output_spec?: Record<string, ScriptOutputSpec>;
  input_spec_json?: Record<string, ScriptInputSpec>;
  output_spec_json?: Record<string, ScriptOutputSpec>;
  created_at: string;
  updated_at: string;
}

export interface ScriptInputSpec {
  name: string;
  type: "dataframe";
  required: boolean;
}

export interface ScriptOutputSpec {
  name: string;
  type: "number" | "string" | "dataframe" | "boolean";
}

export interface ScriptExecuteRequest {
  inputs: Record<string, string>; // DataSource ID
  params?: Record<string, any>;
}

export interface ScriptExecuteResponse {
  task_id: string;
  run_id: string;  // UUID of the FlowScriptRun for polling
  status: "pending" | "running" | "success" | "failed";
  script_id: string;
}

// Pipeline Types
export interface PipelineStep {
  id: string;
  type: "crm_query" | "script";
  config: {
    view_key?: string;
    filters?: Record<string, any>;
    script_id?: string;
    inputs?: Record<string, string>;
    params?: Record<string, any>;
  };
  output?: string;
}

export interface Pipeline {
  id: string;
  name: string;
  description?: string;
  steps_json: PipelineStep[];
  params_json: PipelineParam[];
  is_active: boolean;
  created_at: string;
}

export interface PipelineParam {
  name: string;
  type: "string" | "number" | "date" | "boolean";
  default?: string;
}

export interface PipelineRun {
  id: string;
  pipeline: string;
  pipeline_name: string;
  status: "pending" | "running" | "success" | "failed";
  params_json: Record<string, any>;
  outputs_json: Record<string, string>; // ResultSet IDs
  step_results_json: Record<string, string>; // Step ID -> ResultSet ID
  started_at: string;
  completed_at?: string;
  duration_seconds?: number;
}

// Panel & Widget Types
export interface Panel {
  id: string;
  name: string;
  description?: string;
  layout_json: {
    grid: {
      columns: number;
      rowHeight: number;
    };
  };
  is_public: boolean;
  shared_with_roles: string[];
  widget_count: number;
  created_at: string;
}

export type WidgetType = "table" | "kpi" | "linechart" | "barchart" | "piechart";

export interface Widget {
  id: string;
  panel: string;
  name: string;
  widget_type: WidgetType;
  datasource_id: string;
  config_json: WidgetConfig;
  position_x: number;
  position_y: number;
  width: number;
  height: number;
  order: number;
}

export interface WidgetConfig {
  // Table Widget
  columns?: string[];
  page?: number;
  page_size?: number;
  sort_by?: string;
  sort_ascending?: boolean;
  filters?: Record<string, any>;
  
  // KPI Widget
  value_column?: string;
  aggregation?: "sum" | "avg" | "min" | "max" | "count";
  format?: string;
  label?: string;
  comparison_column?: string;
  
  // Chart Widgets
  x_column?: string;
  y_column?: string;
  limit?: number;
  x_label?: string;
  y_label?: string;
}

export interface RenderedWidget {
  id: string;
  name: string;
  type: WidgetType;
  position: {
    x: number;
    y: number;
    width: number;
    height: number;
  };
  data: WidgetData;
}

export interface WidgetData {
  type: WidgetType;
  // KPI Data
  value?: number;
  formatted_value?: string;
  aggregation?: string;
  label?: string;
  // Table Data
  columns?: string[];
  rows?: Record<string, any>[];
  pagination?: {
    page: number;
    page_size: number;
    total_rows: number;
    total_pages: number;
  };
  // Chart Data
  x_column?: string;
  y_column?: string;
  data_points?: Array<{ x: any; y: any }>;
}

// Snapshot Types
export interface Snapshot {
  id: string;
  name: string;
  version: number;
  resultset: ResultSet;
  fileset?: string;
  description?: string;
  created_at: string;
}

// Import Processes (control plane v3.1)
export interface ShapeDescription {
  file_type: "csv" | "excel" | "pdf";
  columns?: string[];
  column_count?: number;
  sheets?: string[];
  page_patterns?: {
    header: number[];
    detail: number[];
    footer: number[];
    page_count: number;
  };
  tables?: Array<{
    page: number;
    column_count: number;
    columns: string[];
    row_count_estimate: number;
  }>;
  page_count?: number;
}

export interface StructuralUnit {
  id: string;
  name: string;
  kind: "csv_whole" | "excel_sheet" | "pdf_table" | "pdf_region";
  selector: {
    sheet?: string;
    page_selector?: PageSelector;
    bbox?: [number, number, number, number];
  };
}

export interface SemanticDerivation {
  id: string;
  structural_unit_id: string;
  name: string;
  mapping: MappingItem[];
  output_config: {
    materialize?: boolean;
  };
}

export interface ImportProcessContractJson {
  version: string;
  parser: {
    type: "csv" | "excel" | "pdf";
    delimiter?: string;
    encoding?: string;
    header_row?: number;
    skip_rows?: number;
    sheet?: number | string;
    range?: {
      start_row?: number;
      end_row?: number;
      start_col?: string;
      end_col?: string;
    };
    date_format?: string;
    datetime_format?: string;
    structural_unit?: {
      kind: string;
      selector?: any;
      bbox?: [number, number, number, number];
    };
  };
  mapping: Array<{
    source: string;
    target: string;
    type: string;
    format?: string;
    clean?: string[];
  }>;
}

export interface ImportProcess {
  id: string;
  name: string;
  file_type: "csv" | "excel" | "pdf";
  file_id?: string;
  shape_fingerprint?: string;
  shape_description?: ShapeDescription;
  contract_json?: ImportProcessContractJson;
  structural_units?: StructuralUnit[];
  semantic_derivations?: SemanticDerivation[];
  version: number;
  is_active: boolean;
  created_at: string;
  updated_at?: string;
}

export interface ImportRun {
  id: string;
  import_process: string;
  import_process_name?: string;
  raw_dataset: string;
  raw_dataset_filename?: string;
  shape_match?: {
    status: "ok" | "error" | "warning";
    passed?: boolean;
    score?: number;
    errors?: string[];
    reasons?: string[];
  };
  status: "pending" | "running" | "success" | "failed" | "completed";
  resultset_ids: string[];
  resultsets?: Array<{
    id: string;
    name?: string;
  }>;
  started_at?: string;
  completed_at?: string;
  error_message?: string;
  error_details?: string;
}
