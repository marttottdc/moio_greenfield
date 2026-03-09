// @ts-nocheck
export type FlashTone = "info" | "ok" | "error";

export type Tenant = {
  id: string;
  uuid?: string;
  name: string;
  slug: string;
  schemaName: string;
  isActive: boolean;
  primaryDomain: string;
};

export type IntegrationDefinition = {
  id: number;
  key: string;
  name: string;
  category: string;
  baseUrl: string;
  openapiUrl: string;
  defaultAuthType: string;
  authScope?: "global" | "tenant" | "user";
  authConfigSchema?: Record<string, unknown>;
  globalAuthConfig?: Record<string, unknown>;
  globalAuthConfigured?: boolean;
  assistantDocsMarkdown: string;
  defaultHeaders: Record<string, string>;
  isActive: boolean;
  metadata: Record<string, unknown>;
  userAuthConfigured?: boolean;
  userAuthConfig?: Record<string, unknown>;
};

export type TenantIntegration = {
  id: number;
  tenantSlug: string;
  integrationKey: string;
  authScope?: "global" | "tenant" | "user";
  isEnabled: boolean;
  notes: string;
  assistantDocsOverride: string;
  tenantAuthConfigured?: boolean;
  tenantAuthConfig?: Record<string, unknown>;
  userAuthConfigured?: boolean;
  userAuthConfig?: Record<string, unknown>;
  updatedAt: string;
};

export type SkillDefinition = {
  id: number;
  key: string;
  name: string;
  description: string;
  bodyMarkdown: string;
  isActive: boolean;
  isGlobal: boolean;
  scope: "global" | "tenant";
  createdByEmail: string;
  updatedAt: string;
};

export type TenantMembership = {
  tenantSlug: string;
  role: "admin" | "member" | "viewer";
  isActive: boolean;
};

export type PlatformUser = {
  id: number;
  email: string;
  displayName: string;
  isPlatformAdmin: boolean;
  isActive: boolean;
  lastLoginAt: string;
  tenantMemberships: TenantMembership[];
};

export type CurrentUser = {
  id: number;
  email: string;
  displayName: string;
  isPlatformAdmin: boolean;
  isActive: boolean;
};

export type NotificationSettings = {
  title: string;
  iconUrl: string;
  badgeUrl: string;
  requireInteraction: boolean;
  renotify: boolean;
  silent: boolean;
  testTitle: string;
  testBody: string;
};

export type PluginSyncInvalid = {
  manifestPath: string;
  error: string;
};

export type PluginSyncState = {
  syncedCount: number;
  invalid: PluginSyncInvalid[];
};

export type PluginRegistryEntry = {
  pluginId: string;
  name: string;
  version: string;
  sourceType: string;
  bundlePath: string;
  manifestPath: string;
  bundleFilename?: string;
  bundleSha256?: string;
  hasBundleBlob?: boolean;
  iconDataUrl?: string;
  iconFallback?: string;
  helpMarkdown?: string;
  manifest: Record<string, unknown>;
  capabilities: string[];
  permissions: string[];
  isValidated: boolean;
  isPlatformApproved: boolean;
  validationError: string;
  updatedAt: string;
};

export type TenantPluginBinding = {
  tenantSlug: string;
  pluginId: string;
  isEnabled: boolean;
  pluginConfig: Record<string, unknown>;
  notes: string;
  updatedAt: string;
};

export type TenantPluginAssignment = {
  tenantSlug: string;
  pluginId: string;
  assignmentType: "role" | "user" | string;
  role: string;
  userId: number;
  userEmail: string;
  isActive: boolean;
  notes: string;
  updatedAt: string;
};

export type PluginAdminState = {
  sync: PluginSyncState;
  plugins: PluginRegistryEntry[];
  tenantPlugins: TenantPluginBinding[];
  tenantPluginAssignments: TenantPluginAssignment[];
  pluginId?: string;
};

export type TenantPluginState = PluginAdminState & {
  tenant: string;
  role: "admin" | "member" | "viewer";
  isTenantAdmin: boolean;
};

export type BootstrapPayload = {
  tenantsEnabled: boolean;
  publicSchema: string;
  message?: string;
  currentUser: CurrentUser | null;
  tenants: Tenant[];
  users: PlatformUser[];
  integrations: IntegrationDefinition[];
  globalSkills: SkillDefinition[];
  tenantIntegrations: TenantIntegration[];
  pluginSync: PluginSyncState;
  plugins: PluginRegistryEntry[];
  tenantPlugins: TenantPluginBinding[];
  tenantPluginAssignments: TenantPluginAssignment[];
  notificationSettings: NotificationSettings;
};

export type ApiError = {
  message: string;
  status: number;
  code?: string;
};

export type TenantUserRow = {
  id: number;
  email: string;
  displayName: string;
  isActive: boolean;
  role: "admin" | "member" | "viewer";
  membershipActive: boolean;
};

export type TenantWorkspace = {
  id: string;
  uuid?: string;
  slug: string;
  name: string;
  displayName: string;
  specialtyPrompt: string;
  enabledSkillKeys: string[];
  defaultVendor?: string;
  defaultModel?: string;
  defaultThinking?: string;
  defaultVerbosity?: string;
  isActive: boolean;
};

export type AutomationTemplate = {
  id: string;
  key: string;
  name: string;
  description: string;
  instructionsMarkdown: string;
  examplePrompt: string;
  defaultMessage: string;
  icon: string;
  category: string;
  isActive: boolean;
  isRecommended: boolean;
  createdByEmail: string;
  metadata: Record<string, unknown>;
  updatedAt: string;
};

export type AutomationInstance = {
  id: string;
  workspaceId: string;
  workspaceSlug: string;
  templateId: string;
  templateKey: string;
  name: string;
  message: string;
  executionMode: "local" | "worktree";
  scheduleType: "manual" | "daily" | "interval";
  scheduleTime: string;
  intervalMinutes: number;
  weekdays: string[];
  isActive: boolean;
  runInProgress: boolean;
  runStartedAt: string;
  lastRunStatus: string;
  lastRunId: string;
  lastRunAt: string;
  nextRunAt: string;
  createdByEmail: string;
  metadata: Record<string, unknown>;
  updatedAt: string;
};

export type AutomationRunLog = {
  id: string;
  automationId: string;
  runId: string;
  sessionKey: string;
  status: string;
  startedAt: string;
  finishedAt: string;
  summary: string;
  errorMessage: string;
  metadata: Record<string, unknown>;
  updatedAt: string;
};

export type TenantAutomationsPayload = {
  workspace: string;
  workspaceId: string;
  templates: AutomationTemplate[];
  instances: AutomationInstance[];
  runLogs: AutomationRunLog[];
};

export type TenantSkillsPayload = {
  tenant: string;
  role: "admin" | "member" | "viewer";
  workspace: string;
  enabledSkillKeys: string[];
  globalSkills: SkillDefinition[];
  tenantSkills: SkillDefinition[];
  mergedSkills: SkillDefinition[];
  enabledSkills: SkillDefinition[];
};

export type TenantBootstrapPayload = {
  tenant: string;
  tenantUuid?: string;
  workspace: string;
  workspaceUuid?: string;
  role: "admin" | "member" | "viewer";
  currentUser: {
    id: number;
    email: string;
    displayName: string;
  };
  users: TenantUserRow[];
  skills: TenantSkillsPayload;
  workspaces: TenantWorkspace[];
  automations: TenantAutomationsPayload;
  integrations: IntegrationDefinition[];
  tenantIntegrations: TenantIntegration[];
  pluginSync: PluginSyncState;
  plugins: PluginRegistryEntry[];
  tenantPlugins: TenantPluginBinding[];
  tenantPluginAssignments: TenantPluginAssignment[];
};
