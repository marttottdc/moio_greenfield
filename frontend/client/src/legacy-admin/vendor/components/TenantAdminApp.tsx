// @ts-nocheck
import { FormEvent, useEffect, useMemo, useState } from "react";

import {
  deleteTenantAutomation,
  saveTenantPlugin,
  deleteTenantWorkspace,
  deleteTenantSkill,
  deleteTenantUser,
  logoutTenantSession,
  saveTenantAutomation,
  saveTenantIntegration,
  saveTenantSkill,
  saveTenantUser,
  saveTenantWorkspace,
  tenantBootstrap,
  tenantPlugins as listTenantPlugins,
  TenantAdminApiError,
} from "../lib/tenantAdminApi";
import {
  getActiveTenantSessionContext,
  getStoredPublicSessionState,
  setActiveTenantSessionContext,
} from "../lib/publicAuthApi";
import { ManageIntegrationsContent } from "@/pages/settings";
import { PLATFORM_ADMIN_NAMESPACE } from "@/constants/routes";
import type {
  AutomationInstance,
  AutomationRunLog,
  AutomationTemplate,
  FlashTone,
  IntegrationDefinition,
  PluginRegistryEntry,
  PluginSyncState,
  SkillDefinition,
  TenantBootstrapPayload,
  TenantIntegration,
  TenantPluginAssignment,
  TenantPluginBinding,
  TenantUserRow,
  TenantWorkspace,
} from "../types";

type NavSection =
  | "overview"
  | "workspaces"
  | "users"
  | "skills"
  | "automations"
  | "plugins"
  | "integrations"
  | "settings";

type UserFormState = {
  id: number | null;
  email: string;
  displayName: string;
  password: string;
  role: "admin" | "member" | "viewer";
  isActive: boolean;
  membershipActive: boolean;
};

type SkillFormState = {
  key: string;
  name: string;
  description: string;
  bodyMarkdown: string;
  isActive: boolean;
};

type WorkspaceFormState = {
  id: string | null;
  slug: string;
  name: string;
  displayName: string;
  specialtyPrompt: string;
  toolAllowlistText: string;
  pluginAllowlist: string[];
  integrationAllowlist: string[];
  defaultVendor: string;
  defaultModel: string;
  defaultThinking: string;
  defaultVerbosity: string;
  isActive: boolean;
};

type IntegrationDraft = {
  isEnabled: boolean;
  notes: string;
  assistantDocsOverride: string;
  secretValue: string;
  username: string;
  password: string;
  clientId: string;
  clientSecret: string;
  apiKeyHeaderName: string;
  apiKeyQueryParamName: string;
  tokenUrl: string;
  scope: string;
  baseUrl: string;
  timeoutSeconds: string;
  defaultHeadersText: string;
  clearStoredSecrets: boolean;
  hasVaultKey: boolean;
  hasUsernameVaultKey: boolean;
  hasPasswordVaultKey: boolean;
  hasClientIdVaultKey: boolean;
  hasClientSecretVaultKey: boolean;
};

type PluginAssignmentDraft = {
  assignmentType: "role" | "user";
  role: "admin" | "member" | "viewer";
  userId: number;
  userEmail: string;
  isActive: boolean;
  notes: string;
};

type PluginFormState = {
  pluginId: string;
  isEnabled: boolean;
  notes: string;
  pluginConfigText: string;
  pluginConfigObject: Record<string, unknown>;
  assignments: PluginAssignmentDraft[];
};

type PluginConfigSchemaField = {
  key: string;
  title: string;
  description: string;
  type: string;
  enumValues: string[];
  defaultValue: unknown;
};

type AutomationTemplateFormState = {
  id: string | null;
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
};

type AutomationInstanceFormState = {
  id: string | null;
  workspace: string;
  templateKey: string;
  name: string;
  message: string;
  executionMode: "local" | "worktree";
  scheduleType: "manual" | "daily" | "interval";
  scheduleTime: string;
  intervalMinutes: number;
  weekdays: string[];
  isActive: boolean;
};

const NAV_ITEMS: Array<{ key: NavSection; label: string; icon: React.ReactNode }> = [
  {
    key: "overview",
    label: "Overview",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4" stroke="currentColor" strokeWidth="1.8">
        <path d="M3 12h8V3H3v9Zm10 9h8v-6h-8v6Zm0-8h8V3h-8v10Zm-10 8h8v-6H3v6Z" />
      </svg>
    ),
  },
  {
    key: "workspaces",
    label: "Workspaces",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4" stroke="currentColor" strokeWidth="1.8">
        <path d="M4 20h16M7 20V8l5-4 5 4v12M10 12h4M10 16h4" />
      </svg>
    ),
  },
  {
    key: "users",
    label: "Users",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4" stroke="currentColor" strokeWidth="1.8">
        <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm13 10v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" />
      </svg>
    ),
  },
  {
    key: "skills",
    label: "Skills",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4" stroke="currentColor" strokeWidth="1.8">
        <path d="M7 5h10M7 9h10M7 13h7M5 3h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z" />
      </svg>
    ),
  },
  {
    key: "automations",
    label: "Automations",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4" stroke="currentColor" strokeWidth="1.8">
        <path d="M8 12h8M8 8h8M8 16h5M5 4h14a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Z" />
      </svg>
    ),
  },
  {
    key: "plugins",
    label: "Plugins",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4" stroke="currentColor" strokeWidth="1.8">
        <path d="M8 7h8M8 12h8M8 17h5M4 5a2 2 0 0 1 2-2h9l5 5v11a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V5Z" />
      </svg>
    ),
  },
  {
    key: "integrations",
    label: "Integrations",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4" stroke="currentColor" strokeWidth="1.8">
        <path d="M15 7h4a2 2 0 1 1 0 4h-4m-6 2H5a2 2 0 1 0 0 4h4m-3-6h12m-12 2h12" />
      </svg>
    ),
  },
  {
    key: "settings",
    label: "Settings",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4" stroke="currentColor" strokeWidth="1.8">
        <path d="M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z" />
        <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1Z" />
      </svg>
    ),
  },
];

const DEFAULT_USER_FORM: UserFormState = {
  id: null,
  email: "",
  displayName: "",
  password: "",
  role: "member",
  isActive: true,
  membershipActive: true,
};

const DEFAULT_SKILL_FORM: SkillFormState = {
  key: "",
  name: "",
  description: "",
  bodyMarkdown: "",
  isActive: true,
};

const DEFAULT_WORKSPACE_FORM: WorkspaceFormState = {
  id: null,
  slug: "",
  name: "",
  displayName: "",
  specialtyPrompt: "",
  toolAllowlistText: "",
  pluginAllowlist: [],
  integrationAllowlist: [],
  defaultVendor: "",
  defaultModel: "",
  defaultThinking: "default",
  defaultVerbosity: "minimal",
  isActive: true,
};

const DEFAULT_AUTOMATION_TEMPLATE_FORM: AutomationTemplateFormState = {
  id: null,
  key: "",
  name: "",
  description: "",
  instructionsMarkdown: "",
  examplePrompt: "",
  defaultMessage: "",
  icon: "",
  category: "",
  isActive: true,
  isRecommended: true,
};

const DEFAULT_AUTOMATION_INSTANCE_FORM: AutomationInstanceFormState = {
  id: null,
  workspace: "main",
  templateKey: "",
  name: "",
  message: "",
  executionMode: "worktree",
  scheduleType: "manual",
  scheduleTime: "09:00",
  intervalMinutes: 60,
  weekdays: ["mo", "tu", "we", "th", "fr"],
  isActive: true,
};

const DEFAULT_PLUGIN_SYNC: PluginSyncState = {
  syncedCount: 0,
  invalid: [],
};

const DEFAULT_PLUGIN_FORM: PluginFormState = {
  pluginId: "",
  isEnabled: false,
  notes: "",
  pluginConfigText: "{}",
  pluginConfigObject: {},
  assignments: [],
};

function integrationDraftFromConfig(source: Record<string, unknown> | null | undefined, enabled: boolean, notes: string, assistantDocsOverride: string): IntegrationDraft {
  const data = source || {};
  const defaultHeaders =
    data.defaultHeaders && typeof data.defaultHeaders === "object" && !Array.isArray(data.defaultHeaders)
      ? (data.defaultHeaders as Record<string, unknown>)
      : {};
  return {
    isEnabled: enabled,
    notes,
    assistantDocsOverride,
    secretValue: "",
    username: "",
    password: "",
    clientId: "",
    clientSecret: "",
    apiKeyHeaderName: String(data.apiKeyHeaderName || "X-API-Key"),
    apiKeyQueryParamName: String(data.apiKeyQueryParamName || "api_key"),
    tokenUrl: String(data.tokenUrl || ""),
    scope: String(data.scope || ""),
    baseUrl: String(data.baseUrl || ""),
    timeoutSeconds:
      data.timeoutSeconds === undefined || data.timeoutSeconds === null || data.timeoutSeconds === ""
        ? ""
        : String(data.timeoutSeconds),
    defaultHeadersText: JSON.stringify(defaultHeaders, null, 2),
    clearStoredSecrets: false,
    hasVaultKey: Boolean(data.hasVaultKey),
    hasUsernameVaultKey: Boolean(data.hasUsernameVaultKey),
    hasPasswordVaultKey: Boolean(data.hasPasswordVaultKey),
    hasClientIdVaultKey: Boolean(data.hasClientIdVaultKey),
    hasClientSecretVaultKey: Boolean(data.hasClientSecretVaultKey),
  };
}

function formatAutomationTimestamp(value: string): string {
  if (!value) {
    return "never";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "invalid";
  }
  return parsed.toLocaleString();
}

function automationInstanceMeta(row: AutomationInstance): string {
  const parts = [`${row.scheduleType} · ${row.executionMode}`];
  if (row.templateKey) {
    parts.push(row.templateKey);
  }
  if (row.runInProgress) {
    parts.push("running");
  } else if (row.lastRunStatus) {
    parts.push(`last ${row.lastRunStatus}`);
  }
  if (row.nextRunAt) {
    parts.push(`next ${formatAutomationTimestamp(row.nextRunAt)}`);
  }
  return parts.join(" · ");
}

function automationRunMeta(row: AutomationRunLog): string {
  const status = row.status || "unknown";
  const finished = row.finishedAt ? `finished ${formatAutomationTimestamp(row.finishedAt)}` : "in progress";
  return `${status} · started ${formatAutomationTimestamp(row.startedAt)} · ${finished}`;
}

function normalizePluginRole(value: string): PluginAssignmentDraft["role"] {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "admin" || normalized === "viewer") {
    return normalized;
  }
  return "member";
}

function parseToolAllowlistText(raw: string): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const token of String(raw || "").split(/[\n,]/g).map((item) => item.trim()).filter(Boolean)) {
    if (seen.has(token)) continue;
    seen.add(token);
    out.push(token);
  }
  return out;
}

const WORKSPACE_TOOL_HINTS = [
  "files.read",
  "files.write",
  "files.search",
  "shell.run",
  "web.fetch",
  "web.request",
  "api.run",
  "moio_api.run",
  "tools.list",
];

function pluginAssignmentDraftFromRow(row: TenantPluginAssignment): PluginAssignmentDraft {
  return {
    assignmentType: row.assignmentType === "user" ? "user" : "role",
    role: normalizePluginRole(row.role),
    userId: Number(row.userId || 0),
    userEmail: String(row.userEmail || ""),
    isActive: Boolean(row.isActive),
    notes: String(row.notes || ""),
  };
}

function pluginConfigSchemaFields(plugin: PluginRegistryEntry | null): PluginConfigSchemaField[] {
  if (!plugin || !plugin.manifest || typeof plugin.manifest !== "object" || Array.isArray(plugin.manifest)) {
    return [];
  }
  const manifest = plugin.manifest as Record<string, unknown>;
  const configSchema = manifest.config_schema;
  if (!configSchema || typeof configSchema !== "object" || Array.isArray(configSchema)) {
    return [];
  }
  const properties = (configSchema as Record<string, unknown>).properties;
  if (!properties || typeof properties !== "object" || Array.isArray(properties)) {
    return [];
  }
  return Object.entries(properties as Record<string, unknown>)
    .map(([key, value]) => {
      const row = value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
      const enumValues = Array.isArray(row.enum)
        ? row.enum
            .map((item) => String(item || "").trim())
            .filter((item) => Boolean(item))
        : [];
      return {
        key,
        title: String(row.title || key),
        description: String(row.description || ""),
        type: String(row.type || "string").trim().toLowerCase() || "string",
        enumValues,
        defaultValue: row.default,
      };
    })
    .filter((row) => Boolean(String(row.key || "").trim()));
}

export default function TenantAdminApp() {
  const initialWorkspaceFromContext = (() => {
    const active = getActiveTenantSessionContext();
    if (typeof window === "undefined") {
      return String(active?.workspaceSlug || "main").trim().toLowerCase() || "main";
    }
    const query = new URLSearchParams(window.location.search);
    return (
      String(query.get("workspace") || active?.workspaceSlug || "main")
        .trim()
        .toLowerCase() || "main"
    );
  })();
  const canReturnToPlatform = getStoredPublicSessionState().capabilities.platformAdmin;
  const [activeSection, setActiveSection] = useState<NavSection>("overview");
  const [loading, setLoading] = useState(true);
  const [flashText, setFlashText] = useState("");
  const [flashTone, setFlashTone] = useState<FlashTone>("info");

  const [tenantSlug, setTenantSlug] = useState("");
  const [tenantUuid, setTenantUuid] = useState("");
  const [role, setRole] = useState<"admin" | "member" | "viewer">("member");
  const [workspaceSlug, setWorkspaceSlug] = useState(initialWorkspaceFromContext);
  const [workspaceUuid, setWorkspaceUuid] = useState("");
  const [currentUser, setCurrentUser] = useState<{ email: string; displayName: string } | null>(null);

  const [users, setUsers] = useState<TenantUserRow[]>([]);
  const [workspaces, setWorkspaces] = useState<TenantWorkspace[]>([]);
  const [skillsMerged, setSkillsMerged] = useState<SkillDefinition[]>([]);
  const [skillsTenant, setSkillsTenant] = useState<SkillDefinition[]>([]);
  const [enabledSkillKeys, setEnabledSkillKeys] = useState<string[]>([]);
  const [automationTemplates, setAutomationTemplates] = useState<AutomationTemplate[]>([]);
  const [automationInstances, setAutomationInstances] = useState<AutomationInstance[]>([]);
  const [automationRunLogs, setAutomationRunLogs] = useState<AutomationRunLog[]>([]);
  const [integrations, setIntegrations] = useState<IntegrationDefinition[]>([]);
  const [tenantIntegrations, setTenantIntegrations] = useState<TenantIntegration[]>([]);
  const [pluginSync, setPluginSync] = useState<PluginSyncState>(DEFAULT_PLUGIN_SYNC);
  const [plugins, setPlugins] = useState<PluginRegistryEntry[]>([]);
  const [tenantPlugins, setTenantPlugins] = useState<TenantPluginBinding[]>([]);
  const [tenantPluginAssignments, setTenantPluginAssignments] = useState<TenantPluginAssignment[]>([]);
  const [selectedPluginId, setSelectedPluginId] = useState("");

  const [userForm, setUserForm] = useState<UserFormState>(DEFAULT_USER_FORM);
  const [skillForm, setSkillForm] = useState<SkillFormState>(DEFAULT_SKILL_FORM);
  const [workspaceForm, setWorkspaceForm] = useState<WorkspaceFormState>(DEFAULT_WORKSPACE_FORM);
  const [automationTemplateForm, setAutomationTemplateForm] = useState<AutomationTemplateFormState>(
    DEFAULT_AUTOMATION_TEMPLATE_FORM
  );
  const [automationInstanceForm, setAutomationInstanceForm] = useState<AutomationInstanceFormState>(
    DEFAULT_AUTOMATION_INSTANCE_FORM
  );
  const [userModalOpen, setUserModalOpen] = useState(false);
  const [workspaceModalOpen, setWorkspaceModalOpen] = useState(false);
  const [skillModalOpen, setSkillModalOpen] = useState(false);
  const [automationTemplateModalOpen, setAutomationTemplateModalOpen] = useState(false);
  const [automationInstanceModalOpen, setAutomationInstanceModalOpen] = useState(false);
  const [pluginForm, setPluginForm] = useState<PluginFormState>(DEFAULT_PLUGIN_FORM);
  const [integrationDrafts, setIntegrationDrafts] = useState<Record<string, IntegrationDraft>>({});
  const [skillQuery, setSkillQuery] = useState("");
  const [automationQuery, setAutomationQuery] = useState("");

  const isTenantAdmin = role === "admin";

  const integrationBindingMap = useMemo(() => {
    const out = new Map<string, TenantIntegration>();
    tenantIntegrations.forEach((item) => out.set(String(item.integrationKey || "").toLowerCase(), item));
    return out;
  }, [tenantIntegrations]);

  const selectedPlugin = useMemo(
    () => plugins.find((row) => row.pluginId === selectedPluginId) || null,
    [plugins, selectedPluginId]
  );
  const selectedPluginConfigFields = useMemo(
    () => pluginConfigSchemaFields(selectedPlugin),
    [selectedPlugin]
  );

  function setFlash(message: string, tone: FlashTone = "info") {
    setFlashText(message);
    setFlashTone(tone);
  }

  function applyPluginStateFromPayload(payload: {
    pluginSync?: PluginSyncState;
    sync?: PluginSyncState;
    plugins?: PluginRegistryEntry[];
    tenantPlugins?: TenantPluginBinding[];
    tenantPluginAssignments?: TenantPluginAssignment[];
  }) {
    setPluginSync(payload.pluginSync || payload.sync || DEFAULT_PLUGIN_SYNC);
    setPlugins(Array.isArray(payload.plugins) ? payload.plugins : []);
    setTenantPlugins(Array.isArray(payload.tenantPlugins) ? payload.tenantPlugins : []);
    setTenantPluginAssignments(
      Array.isArray(payload.tenantPluginAssignments) ? payload.tenantPluginAssignments : []
    );
  }

  function getTenantPluginBinding(pluginId: string): TenantPluginBinding | null {
    const pid = String(pluginId || "").trim().toLowerCase();
    const tenant = String(tenantSlug || "").trim().toLowerCase();
    return (
      tenantPlugins.find(
        (row) =>
          String(row.pluginId || "").trim().toLowerCase() === pid &&
          String(row.tenantSlug || "").trim().toLowerCase() === tenant
      ) || null
    );
  }

  function getTenantPluginAssignments(pluginId: string): TenantPluginAssignment[] {
    const pid = String(pluginId || "").trim().toLowerCase();
    const tenant = String(tenantSlug || "").trim().toLowerCase();
    return tenantPluginAssignments.filter(
      (row) =>
        String(row.pluginId || "").trim().toLowerCase() === pid &&
        String(row.tenantSlug || "").trim().toLowerCase() === tenant
    );
  }

  function resetPluginForm(pluginId: string) {
    const normalizedPluginId = String(pluginId || "").trim().toLowerCase();
    const selected = plugins.find((row) => String(row.pluginId || "").trim().toLowerCase() === normalizedPluginId) || null;
    const schemaFields = pluginConfigSchemaFields(selected);
    const binding = getTenantPluginBinding(normalizedPluginId);
    const rawConfig =
      binding?.pluginConfig && typeof binding.pluginConfig === "object" && !Array.isArray(binding.pluginConfig)
        ? (binding.pluginConfig as Record<string, unknown>)
        : {};
    const configObject =
      schemaFields.length > 0
        ? schemaFields.reduce<Record<string, unknown>>((acc, field) => {
            if (Object.prototype.hasOwnProperty.call(rawConfig, field.key)) {
              acc[field.key] = rawConfig[field.key];
            } else if (field.defaultValue !== undefined) {
              acc[field.key] = field.defaultValue;
            }
            return acc;
          }, {})
        : {};
    const assignments = getTenantPluginAssignments(normalizedPluginId);
    setPluginForm({
      pluginId: normalizedPluginId,
      isEnabled: Boolean(binding?.isEnabled),
      notes: String(binding?.notes || ""),
      pluginConfigText: JSON.stringify(configObject, null, 2),
      pluginConfigObject: { ...configObject },
      assignments: assignments.map((row) => pluginAssignmentDraftFromRow(row)),
    });
  }

  function applyPayload(payload: TenantBootstrapPayload) {
    const currentSession = getActiveTenantSessionContext();
    setTenantSlug(String(payload.tenant || ""));
    setTenantUuid(String(payload.tenantUuid || ""));
    setRole((payload.role || "member") as "admin" | "member" | "viewer");
    setWorkspaceSlug(String(payload.workspace || "main"));
    setWorkspaceUuid(String(payload.workspaceUuid || ""));
    setCurrentUser(payload.currentUser || null);
    setUsers(Array.isArray(payload.users) ? payload.users : []);
    setWorkspaces(Array.isArray(payload.workspaces) ? payload.workspaces : []);
    const skillsPayload = payload.skills || ({} as TenantBootstrapPayload["skills"]);
    setSkillsMerged(Array.isArray(skillsPayload.mergedSkills) ? skillsPayload.mergedSkills : []);
    setSkillsTenant(Array.isArray(skillsPayload.tenantSkills) ? skillsPayload.tenantSkills : []);
    setEnabledSkillKeys(Array.isArray(skillsPayload.enabledSkillKeys) ? skillsPayload.enabledSkillKeys : []);
    const automationsPayload = payload.automations || ({} as TenantBootstrapPayload["automations"]);
    setAutomationTemplates(Array.isArray(automationsPayload.templates) ? automationsPayload.templates : []);
    setAutomationInstances(Array.isArray(automationsPayload.instances) ? automationsPayload.instances : []);
    setAutomationRunLogs(Array.isArray(automationsPayload.runLogs) ? automationsPayload.runLogs : []);
    const allIntegrations = Array.isArray(payload.integrations) ? payload.integrations : [];
    const allTenantIntegrations = Array.isArray(payload.tenantIntegrations) ? payload.tenantIntegrations : [];
    setIntegrations(allIntegrations);
    setTenantIntegrations(allTenantIntegrations);
    applyPluginStateFromPayload(payload);
    setActiveTenantSessionContext({
      ...(getActiveTenantSessionContext() || {
        tenantId: "",
        tenantSlug: "",
        tenantSchema: "",
        workspaceId: "",
        workspaceSlug: "",
      }),
      tenantId: String(payload.tenantUuid || "").trim(),
      tenantSlug: String(payload.tenant || "").trim().toLowerCase(),
      tenantSchema: String(currentSession?.tenantSchema || "").trim().toLowerCase(),
      workspaceId: String(payload.workspaceUuid || "").trim(),
      workspaceSlug: String(payload.workspace || "main").trim().toLowerCase(),
    });
    const drafts: Record<string, IntegrationDraft> = {};
    allIntegrations.forEach((integration) => {
      const key = String(integration.key || "").toLowerCase();
      const binding = allTenantIntegrations.find((item) => String(item.integrationKey || "").toLowerCase() === key);
      const scope = String(integration.authScope || "tenant").toLowerCase();
      const configSource =
        scope === "tenant"
          ? ((binding?.tenantAuthConfig || {}) as Record<string, unknown>)
          : scope === "user"
          ? ((binding?.userAuthConfig || integration.userAuthConfig || {}) as Record<string, unknown>)
          : ({} as Record<string, unknown>);
      drafts[key] = integrationDraftFromConfig(
        configSource,
        Boolean(binding?.isEnabled),
        String(binding?.notes || ""),
        String(binding?.assistantDocsOverride || "")
      );
    });
    setIntegrationDrafts(drafts);
    setAutomationTemplateForm(DEFAULT_AUTOMATION_TEMPLATE_FORM);
    setAutomationInstanceForm((prev) => ({
      ...DEFAULT_AUTOMATION_INSTANCE_FORM,
      workspace: String(payload.workspace || prev.workspace || "main"),
    }));
  }

  function onReturnToPlatform() {
    window.location.assign(PLATFORM_ADMIN_NAMESPACE);
  }

  async function loadBootstrap(nextWorkspace?: string) {
    setLoading(true);
    try {
      const payload = await tenantBootstrap(nextWorkspace || workspaceSlug || "main");
      applyPayload(payload);
      if (flashText) setFlash("");
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      const apiError = error as TenantAdminApiError;
      if (apiError?.status === 401 || apiError?.status === 403 || apiError?.code === "auth_required") {
        logoutTenantSession();
        window.location.replace("/desktop-agent-console/");
        return;
      }
      setFlash(message, "error");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadBootstrap(initialWorkspaceFromContext || "main");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (plugins.length === 0) {
      if (selectedPluginId) setSelectedPluginId("");
      setPluginForm(DEFAULT_PLUGIN_FORM);
      return;
    }
    const exists = plugins.some((row) => row.pluginId === selectedPluginId);
    if (!exists) {
      setSelectedPluginId(plugins[0].pluginId);
      return;
    }
    resetPluginForm(selectedPluginId);
  }, [plugins, selectedPluginId, tenantPlugins, tenantPluginAssignments, tenantSlug]);

  function resetUserForm() {
    setUserForm(DEFAULT_USER_FORM);
  }

  function newUserForm() {
    resetUserForm();
    setUserModalOpen(true);
  }

  function editUserForm(row: TenantUserRow) {
    setUserForm({
      id: row.id,
      email: row.email,
      displayName: row.displayName,
      password: "",
      role: row.role,
      isActive: row.isActive,
      membershipActive: row.membershipActive,
    });
    setUserModalOpen(true);
  }

  async function onSaveUser(event: FormEvent) {
    event.preventDefault();
    try {
      await saveTenantUser({
        email: userForm.email,
        displayName: userForm.displayName,
        password: userForm.password || undefined,
        role: userForm.role,
        isActive: userForm.isActive,
        membershipActive: userForm.membershipActive,
      });
      await loadBootstrap(workspaceSlug);
      setUserForm((prev) => ({ ...prev, password: "" }));
      setUserModalOpen(false);
      setFlash("Tenant user saved.", "ok");
    } catch (error) {
      setFlash(error instanceof Error ? error.message : String(error), "error");
    }
  }

  async function onDeleteUser() {
    if (!userForm.id && !userForm.email) {
      setFlash("Select a user first.", "error");
      return;
    }
    if (!window.confirm(`Delete tenant membership for "${userForm.email}"?`)) return;
    try {
      await deleteTenantUser({ id: userForm.id || undefined, email: userForm.email || undefined });
      await loadBootstrap(workspaceSlug);
      resetUserForm();
      setUserModalOpen(false);
      setFlash("Tenant user removed.", "ok");
    } catch (error) {
      setFlash(error instanceof Error ? error.message : String(error), "error");
    }
  }

  function resetSkillForm() {
    setSkillForm(DEFAULT_SKILL_FORM);
  }

  function newSkillForm() {
    resetSkillForm();
    setSkillModalOpen(true);
  }

  function resetWorkspaceForm() {
    setWorkspaceForm(DEFAULT_WORKSPACE_FORM);
  }

  function newWorkspaceForm() {
    resetWorkspaceForm();
    setWorkspaceModalOpen(true);
  }

  function editWorkspaceForm(row: TenantWorkspace) {
    setWorkspaceForm({
      id: row.id,
      slug: row.slug,
      name: row.name,
      displayName: row.displayName,
      specialtyPrompt: row.specialtyPrompt || "",
      toolAllowlistText: Array.isArray(row.toolAllowlist) ? row.toolAllowlist.join("\n") : "",
      pluginAllowlist: Array.isArray(row.pluginAllowlist) ? row.pluginAllowlist.map((item) => String(item || "").trim().toLowerCase()).filter(Boolean) : [],
      integrationAllowlist: Array.isArray(row.integrationAllowlist) ? row.integrationAllowlist.map((item) => String(item || "").trim().toLowerCase()).filter(Boolean) : [],
      defaultVendor: row.defaultVendor || "",
      defaultModel: row.defaultModel || "",
      defaultThinking: row.defaultThinking || "default",
      defaultVerbosity: row.defaultVerbosity || "minimal",
      isActive: row.isActive,
    });
    setWorkspaceModalOpen(true);
  }

  function editSkillForm(row: SkillDefinition) {
    setSkillForm({
      key: row.key,
      name: row.name,
      description: row.description || "",
      bodyMarkdown: row.bodyMarkdown || "",
      isActive: row.isActive,
    });
    setSkillModalOpen(true);
  }

  function resetAutomationTemplateForm() {
    setAutomationTemplateForm(DEFAULT_AUTOMATION_TEMPLATE_FORM);
  }

  function newAutomationTemplateForm() {
    resetAutomationTemplateForm();
    setAutomationTemplateModalOpen(true);
  }

  function editAutomationTemplateForm(row: AutomationTemplate) {
    setAutomationTemplateForm({
      id: row.id,
      key: row.key,
      name: row.name,
      description: row.description || "",
      instructionsMarkdown: row.instructionsMarkdown || "",
      examplePrompt: row.examplePrompt || "",
      defaultMessage: row.defaultMessage || "",
      icon: row.icon || "",
      category: row.category || "",
      isActive: row.isActive,
      isRecommended: row.isRecommended,
    });
    setAutomationTemplateModalOpen(true);
  }

  function resetAutomationInstanceForm() {
    setAutomationInstanceForm({
      ...DEFAULT_AUTOMATION_INSTANCE_FORM,
      workspace: workspaceSlug || "main",
    });
  }

  function newAutomationInstanceForm() {
    resetAutomationInstanceForm();
    setAutomationInstanceModalOpen(true);
  }

  function editAutomationInstanceForm(row: AutomationInstance) {
    setAutomationInstanceForm({
      id: row.id,
      workspace: row.workspaceSlug || workspaceSlug || "main",
      templateKey: row.templateKey || "",
      name: row.name || "",
      message: row.message || "",
      executionMode: row.executionMode || "worktree",
      scheduleType: row.scheduleType || "manual",
      scheduleTime: row.scheduleTime || "09:00",
      intervalMinutes: row.intervalMinutes || 60,
      weekdays: Array.isArray(row.weekdays) ? row.weekdays : [],
      isActive: row.isActive,
    });
    setAutomationInstanceModalOpen(true);
  }

  function draftAutomationInstanceFromTemplate(row: AutomationTemplate) {
    setAutomationInstanceForm({
      ...DEFAULT_AUTOMATION_INSTANCE_FORM,
      workspace: workspaceSlug || "main",
      templateKey: row.key,
      name: row.name,
      message: row.defaultMessage || row.examplePrompt || "",
    });
    setAutomationInstanceModalOpen(true);
  }

  async function onSaveSkill(event: FormEvent) {
    event.preventDefault();
    try {
      await saveTenantSkill({
        workspace: workspaceSlug,
        key: skillForm.key,
        name: skillForm.name,
        description: skillForm.description,
        bodyMarkdown: skillForm.bodyMarkdown,
        isActive: skillForm.isActive,
      });
      await loadBootstrap(workspaceSlug);
      setSkillModalOpen(false);
      setFlash("Tenant skill saved.", "ok");
    } catch (error) {
      setFlash(error instanceof Error ? error.message : String(error), "error");
    }
  }

  async function onDeleteSkill() {
    if (!skillForm.key) {
      setFlash("Select a tenant skill first.", "error");
      return;
    }
    if (!window.confirm(`Delete tenant skill "${skillForm.key}"?`)) return;
    try {
      await deleteTenantSkill({ workspace: workspaceSlug, key: skillForm.key });
      await loadBootstrap(workspaceSlug);
      resetSkillForm();
      setSkillModalOpen(false);
      setFlash("Tenant skill deleted.", "ok");
    } catch (error) {
      setFlash(error instanceof Error ? error.message : String(error), "error");
    }
  }

  async function onSaveAutomationTemplate(event: FormEvent) {
    event.preventDefault();
    try {
      await saveTenantAutomation({
        recordType: "template",
        id: automationTemplateForm.id || undefined,
        workspace: workspaceSlug,
        key: automationTemplateForm.key,
        name: automationTemplateForm.name,
        description: automationTemplateForm.description,
        instructionsMarkdown: automationTemplateForm.instructionsMarkdown,
        examplePrompt: automationTemplateForm.examplePrompt,
        defaultMessage: automationTemplateForm.defaultMessage,
        icon: automationTemplateForm.icon,
        category: automationTemplateForm.category,
        isActive: automationTemplateForm.isActive,
        isRecommended: automationTemplateForm.isRecommended,
      });
      await loadBootstrap(workspaceSlug);
      setAutomationTemplateModalOpen(false);
      setFlash("Automation template saved.", "ok");
    } catch (error) {
      setFlash(error instanceof Error ? error.message : String(error), "error");
    }
  }

  async function onDeleteAutomationTemplate() {
    if (!automationTemplateForm.id && !automationTemplateForm.key.trim()) {
      setFlash("Select an automation template first.", "error");
      return;
    }
    if (!window.confirm(`Delete automation template "${automationTemplateForm.name || automationTemplateForm.key}"?`)) {
      return;
    }
    try {
      await deleteTenantAutomation({
        recordType: "template",
        id: automationTemplateForm.id || undefined,
        key: automationTemplateForm.key || undefined,
        workspace: workspaceSlug,
      });
      await loadBootstrap(workspaceSlug);
      resetAutomationTemplateForm();
      setAutomationTemplateModalOpen(false);
      setFlash("Automation template deleted.", "ok");
    } catch (error) {
      setFlash(error instanceof Error ? error.message : String(error), "error");
    }
  }

  async function onSaveAutomationInstance(event: FormEvent) {
    event.preventDefault();
    try {
      await saveTenantAutomation({
        recordType: "instance",
        id: automationInstanceForm.id || undefined,
        workspace: automationInstanceForm.workspace || workspaceSlug || "main",
        templateKey: automationInstanceForm.templateKey || undefined,
        name: automationInstanceForm.name,
        message: automationInstanceForm.message,
        executionMode: automationInstanceForm.executionMode,
        scheduleType: automationInstanceForm.scheduleType,
        scheduleTime: automationInstanceForm.scheduleTime,
        intervalMinutes: automationInstanceForm.intervalMinutes,
        weekdays: automationInstanceForm.weekdays,
        isActive: automationInstanceForm.isActive,
      });
      await loadBootstrap(automationInstanceForm.workspace || workspaceSlug);
      setAutomationInstanceModalOpen(false);
      setFlash("Automation installed for this workspace.", "ok");
    } catch (error) {
      setFlash(error instanceof Error ? error.message : String(error), "error");
    }
  }

  async function onDeleteAutomationInstance() {
    if (!automationInstanceForm.id) {
      setFlash("Select an installed automation first.", "error");
      return;
    }
    if (!window.confirm(`Delete automation "${automationInstanceForm.name}" from this workspace?`)) return;
    try {
      await deleteTenantAutomation({
        recordType: "instance",
        id: automationInstanceForm.id,
        workspace: automationInstanceForm.workspace || workspaceSlug,
      });
      await loadBootstrap(workspaceSlug);
      resetAutomationInstanceForm();
      setAutomationInstanceModalOpen(false);
      setFlash("Automation removed from workspace.", "ok");
    } catch (error) {
      setFlash(error instanceof Error ? error.message : String(error), "error");
    }
  }

  function toggleEnabledSkillKey(key: string) {
    const normalized = String(key || "").trim();
    if (!normalized) return;
    setEnabledSkillKeys((prev) => {
      if (prev.includes(normalized)) return prev.filter((item) => item !== normalized);
      return [...prev, normalized];
    });
  }

  async function onSaveWorkspaceSkillEnablement() {
    const workspace = workspaces.find((row) => row.slug === workspaceSlug);
    try {
      await saveTenantWorkspace({
        id: workspace?.id,
        slug: workspaceSlug,
        name: workspace?.name || workspaceSlug.toUpperCase(),
        displayName: workspace?.displayName || workspace?.name || workspaceSlug.toUpperCase(),
        specialtyPrompt: workspace?.specialtyPrompt || "",
        toolAllowlist: Array.isArray(workspace?.toolAllowlist) ? workspace.toolAllowlist : [],
        pluginAllowlist: Array.isArray(workspace?.pluginAllowlist) ? workspace.pluginAllowlist : [],
        integrationAllowlist: Array.isArray(workspace?.integrationAllowlist) ? workspace.integrationAllowlist : [],
        enabledSkillKeys,
        isActive: workspace?.isActive ?? true,
      });
      await loadBootstrap(workspaceSlug);
      setFlash("Workspace skill enablement updated.", "ok");
    } catch (error) {
      setFlash(error instanceof Error ? error.message : String(error), "error");
    }
  }

  async function onSaveWorkspace(event: FormEvent) {
    event.preventDefault();
    if (!workspaceForm.slug.trim()) {
      setFlash("Workspace slug is required.", "error");
      return;
    }
    const existingWorkspace =
      workspaces.find((row) => row.id === workspaceForm.id) ||
      workspaces.find((row) => row.slug === workspaceForm.slug.trim());
    try {
      await saveTenantWorkspace({
        id: workspaceForm.id || undefined,
        slug: workspaceForm.slug.trim(),
        name: workspaceForm.name.trim() || workspaceForm.slug.trim().toUpperCase(),
        displayName: workspaceForm.displayName.trim() || workspaceForm.name.trim() || workspaceForm.slug.trim(),
        specialtyPrompt: workspaceForm.specialtyPrompt,
        defaultVendor: workspaceForm.defaultVendor.trim().toLowerCase(),
        defaultModel: workspaceForm.defaultModel.trim(),
        defaultThinking: workspaceForm.defaultThinking.trim().toLowerCase(),
        defaultVerbosity: workspaceForm.defaultVerbosity.trim().toLowerCase(),
        toolAllowlist: parseToolAllowlistText(workspaceForm.toolAllowlistText),
        pluginAllowlist: [...workspaceForm.pluginAllowlist],
        integrationAllowlist: [...workspaceForm.integrationAllowlist],
        enabledSkillKeys: existingWorkspace?.enabledSkillKeys || [],
        isActive: workspaceForm.isActive,
      });
      await loadBootstrap(workspaceForm.slug.trim());
      setWorkspaceSlug(workspaceForm.slug.trim());
      setWorkspaceModalOpen(false);
      setFlash("Workspace saved.", "ok");
    } catch (error) {
      setFlash(error instanceof Error ? error.message : String(error), "error");
    }
  }

  async function onDeleteWorkspace() {
    if (!workspaceForm.id && !workspaceForm.slug.trim()) {
      setFlash("Select a workspace first.", "error");
      return;
    }
    if (!window.confirm(`Delete workspace "${workspaceForm.slug || workspaceForm.name}"?`)) return;
    try {
      await deleteTenantWorkspace({
        id: workspaceForm.id || undefined,
        slug: workspaceForm.slug.trim() || undefined,
      });
      const fallback = workspaceSlug === workspaceForm.slug ? "main" : workspaceSlug;
      await loadBootstrap(fallback);
      setWorkspaceSlug(fallback);
      resetWorkspaceForm();
      setWorkspaceModalOpen(false);
      setFlash("Workspace deleted.", "ok");
    } catch (error) {
      setFlash(error instanceof Error ? error.message : String(error), "error");
    }
  }

  function openAgentForWorkspace(slug: string, uuid?: string) {
    const target = String(slug || "").trim() || "main";
    setActiveTenantSessionContext({
      ...(getActiveTenantSessionContext() || {
        tenantId: "",
        tenantSlug: "",
        tenantSchema: "",
        workspaceId: "",
        workspaceSlug: "",
      }),
      tenantId: tenantUuid || "",
      tenantSlug: tenantSlug || "",
      tenantSchema: getActiveTenantSessionContext()?.tenantSchema || tenantSlug || "",
      workspaceId: String(uuid || "").trim(),
      workspaceSlug: target.toLowerCase(),
    });
    const url = new URL(window.location.origin + "/desktop-agent-console/console/");
    if (uuid) {
      url.searchParams.set("workspaceId", uuid);
    } else {
      url.searchParams.set("workspace", target);
    }
    window.location.assign(url.toString());
  }

  async function onSaveIntegration(integrationKey: string) {
    const key = String(integrationKey || "").trim().toLowerCase();
    if (!key) return;
    const draft = integrationDrafts[key];
    if (!draft) return;
    const integration = integrations.find((item) => String(item.key || "").trim().toLowerCase() === key);
    const scope = String(integration?.authScope || "tenant").toLowerCase();
    let defaultHeaders: Record<string, unknown> = {};
    if (draft.defaultHeadersText.trim()) {
      try {
        const parsed = JSON.parse(draft.defaultHeadersText);
        if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
          throw new Error("default headers must be a JSON object");
        }
        defaultHeaders = parsed as Record<string, unknown>;
      } catch (error) {
        setFlash(`Invalid default headers JSON: ${error instanceof Error ? error.message : String(error)}`, "error");
        return;
      }
    }
    const authInput: Record<string, unknown> = {
      secretValue: draft.secretValue,
      username: draft.username,
      password: draft.password,
      clientId: draft.clientId,
      clientSecret: draft.clientSecret,
      apiKeyHeaderName: draft.apiKeyHeaderName,
      apiKeyQueryParamName: draft.apiKeyQueryParamName,
      tokenUrl: draft.tokenUrl,
      scope: draft.scope,
      baseUrl: draft.baseUrl,
      timeoutSeconds: draft.timeoutSeconds,
      defaultHeaders,
      clearStoredSecrets: draft.clearStoredSecrets,
    };
    const hasAuthInput =
      Boolean(draft.clearStoredSecrets) ||
      Boolean(draft.secretValue.trim()) ||
      Boolean(draft.username.trim()) ||
      Boolean(draft.password.trim()) ||
      Boolean(draft.clientId.trim()) ||
      Boolean(draft.clientSecret.trim()) ||
      Boolean(draft.apiKeyHeaderName.trim() && draft.apiKeyHeaderName.trim() !== "X-API-Key") ||
      Boolean(draft.apiKeyQueryParamName.trim() && draft.apiKeyQueryParamName.trim() !== "api_key") ||
      Boolean(draft.tokenUrl.trim()) ||
      Boolean(draft.scope.trim()) ||
      Boolean(draft.baseUrl.trim()) ||
      Boolean(draft.timeoutSeconds.trim()) ||
      Boolean(draft.defaultHeadersText.trim() && draft.defaultHeadersText.trim() !== "{}");
    try {
      await saveTenantIntegration({
        integrationKey: key,
        isEnabled: Boolean(draft.isEnabled),
        notes: String(draft.notes || ""),
        assistantDocsOverride: String(draft.assistantDocsOverride || ""),
        tenantAuthInput: scope === "tenant" && hasAuthInput ? authInput : undefined,
        userAuthInput: scope === "user" && hasAuthInput ? authInput : undefined,
      });
      await loadBootstrap(workspaceSlug);
      setFlash(`Integration "${key}" updated.`, "ok");
    } catch (error) {
      setFlash(error instanceof Error ? error.message : String(error), "error");
    }
  }

  async function onRefreshPlugins() {
    try {
      const payload = await listTenantPlugins();
      applyPluginStateFromPayload(payload);
      setFlash("Plugin state refreshed.", "ok");
    } catch (error) {
      setFlash(error instanceof Error ? error.message : String(error), "error");
    }
  }

  function addPluginAssignment(assignmentType: "role" | "user") {
    setPluginForm((prev) => ({
      ...prev,
      assignments: [
        ...prev.assignments,
        {
          assignmentType,
          role: "member",
          userId: 0,
          userEmail: "",
          isActive: true,
          notes: "",
        },
      ],
    }));
  }

  function updatePluginAssignment(index: number, patch: Partial<PluginAssignmentDraft>) {
    setPluginForm((prev) => ({
      ...prev,
      assignments: prev.assignments.map((row, idx) => (idx === index ? { ...row, ...patch } : row)),
    }));
  }

  function removePluginAssignment(index: number) {
    setPluginForm((prev) => ({
      ...prev,
      assignments: prev.assignments.filter((_, idx) => idx !== index),
    }));
  }

  function updatePluginConfigField(field: PluginConfigSchemaField, nextValue: unknown) {
    setPluginForm((prev) => {
      const nextConfig = { ...(prev.pluginConfigObject || {}) };
      if (nextValue === undefined) {
        delete nextConfig[field.key];
      } else {
        nextConfig[field.key] = nextValue;
      }
      return {
        ...prev,
        pluginConfigObject: nextConfig,
        pluginConfigText: JSON.stringify(nextConfig, null, 2),
      };
    });
  }

  async function onSavePlugin() {
    if (!pluginForm.pluginId) {
      setFlash("Select a plugin first.", "error");
      return;
    }
    if (pluginForm.isEnabled && (!selectedPlugin?.isValidated || !selectedPlugin?.isPlatformApproved)) {
      setFlash("Plugin must be validated and platform-approved before enabling.", "error");
      return;
    }
    const configFields = selectedPluginConfigFields;
    let parsedPluginConfig: Record<string, unknown> = {};
    if (configFields.length > 0) {
      parsedPluginConfig = configFields.reduce<Record<string, unknown>>((acc, field) => {
        if (Object.prototype.hasOwnProperty.call(pluginForm.pluginConfigObject, field.key)) {
          acc[field.key] = pluginForm.pluginConfigObject[field.key];
        } else if (field.defaultValue !== undefined) {
          acc[field.key] = field.defaultValue;
        }
        return acc;
      }, {});
    }

    const normalizedAssignments = pluginForm.assignments
      .map((row) => {
        const assignmentType = row.assignmentType === "user" ? "user" : "role";
        const role = normalizePluginRole(row.role);
        const userId = Number(row.userId || 0);
        const knownUser = users.find((item) => Number(item.id) === userId);
        const userEmail = String(row.userEmail || knownUser?.email || "").trim().toLowerCase();
        return {
          assignmentType,
          role,
          userId: userId > 0 ? userId : 0,
          userEmail,
          isActive: Boolean(row.isActive),
          notes: String(row.notes || ""),
        };
      })
      .filter((row) => (row.assignmentType === "role" ? Boolean(row.role) : row.userId > 0 || Boolean(row.userEmail)));

    try {
      const payload = await saveTenantPlugin({
        pluginId: pluginForm.pluginId,
        isEnabled: Boolean(pluginForm.isEnabled),
        notes: String(pluginForm.notes || ""),
        pluginConfig: parsedPluginConfig,
        assignments: normalizedAssignments,
      });
      applyPluginStateFromPayload(payload);
      setFlash(`Plugin "${pluginForm.pluginId}" updated for tenant ${tenantSlug}.`, "ok");
    } catch (error) {
      setFlash(error instanceof Error ? error.message : String(error), "error");
    }
  }

  async function onLogout() {
    await logoutTenantSession();
    window.location.replace("/desktop-agent-console/");
  }

  const flashClass =
    flashTone === "ok"
      ? "border-emerald-300 bg-emerald-50 text-emerald-700"
      : flashTone === "error"
      ? "border-rose-300 bg-rose-50 text-rose-700"
      : "border-slate-300 bg-white text-slate-700";

  const normalizedSkillQuery = skillQuery.trim().toLowerCase();
  const installedSkills = useMemo(
    () =>
      skillsMerged.filter((skill) => enabledSkillKeys.includes(String(skill.key || ""))).filter((skill) => {
        if (!normalizedSkillQuery) return true;
        const haystack = `${skill.name} ${skill.key} ${skill.description}`.toLowerCase();
        return haystack.includes(normalizedSkillQuery);
      }),
    [enabledSkillKeys, normalizedSkillQuery, skillsMerged]
  );
  const availableSkills = useMemo(
    () =>
      skillsMerged
        .filter((skill) => !enabledSkillKeys.includes(String(skill.key || "")))
        .filter((skill) => {
          if (!normalizedSkillQuery) return true;
          const haystack = `${skill.name} ${skill.key} ${skill.description}`.toLowerCase();
          return haystack.includes(normalizedSkillQuery);
        }),
    [enabledSkillKeys, normalizedSkillQuery, skillsMerged]
  );

  const normalizedAutomationQuery = automationQuery.trim().toLowerCase();
  const filteredAutomationTemplates = useMemo(
    () =>
      automationTemplates.filter((row) => {
        if (!normalizedAutomationQuery) return true;
        const haystack = `${row.name} ${row.key} ${row.description} ${row.category}`.toLowerCase();
        return haystack.includes(normalizedAutomationQuery);
      }),
    [automationTemplates, normalizedAutomationQuery]
  );
  const filteredAutomationInstances = useMemo(
    () =>
      automationInstances.filter((row) => {
        if (!normalizedAutomationQuery) return true;
        const haystack = `${row.name} ${row.templateKey} ${row.message}`.toLowerCase();
        return haystack.includes(normalizedAutomationQuery);
      }),
    [automationInstances, normalizedAutomationQuery]
  );

  return (
    <main className="h-screen bg-slate-100 text-slate-900 antialiased">
      <div className="grid h-full grid-cols-[212px_minmax(0,1fr)]">
        <aside className="flex min-h-0 flex-col border-r border-slate-200 bg-slate-900 text-slate-100 shadow-sm">
          <div className="shrink-0 border-b border-slate-700/80 px-2 py-2">
            <div className="flex items-center gap-2.5">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-gradient-to-br from-cyan-400 via-blue-500 to-indigo-500 text-sm font-bold text-white">
                M
              </div>
              <div className="min-w-0">
                <p className="truncate text-base font-semibold leading-tight text-white">moio</p>
                <p className="text-[10px] uppercase tracking-wider text-slate-400">Tenant Admin</p>
              </div>
            </div>
          </div>
          <nav className="min-h-0 flex-1 space-y-0.5 overflow-y-auto px-2 py-2">
            {NAV_ITEMS.map((item) => {
              const active = activeSection === item.key;
              return (
                <button
                  key={item.key}
                  type="button"
                  onClick={() => setActiveSection(item.key)}
                  className={`flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-left text-sm font-medium transition-colors ${
                    active
                      ? "bg-slate-700/90 text-white"
                      : "text-slate-300 hover:bg-slate-800/80 hover:text-white"
                  }`}
                >
                  <span className={`shrink-0 ${active ? "text-sky-400" : "text-slate-400"}`}>{item.icon}</span>
                  <span className="truncate">{item.label}</span>
                </button>
              );
            })}
          </nav>
          <div className="shrink-0 border-t border-slate-700/80 p-2.5">
            <div className="rounded border border-slate-700/80 bg-slate-800/50 px-2.5 py-1.5 text-[11px] text-slate-400">
              <div>Tenant: <span className="font-mono text-slate-200">{tenantSlug || "—"}</span></div>
            </div>
            <button
              type="button"
              onClick={onLogout}
              className="mt-2 w-full rounded border border-slate-600 bg-slate-800 px-2.5 py-1.5 text-xs font-medium text-slate-200 transition hover:bg-slate-700"
            >
              Logout
            </button>
          </div>
        </aside>

        <section className="flex min-h-0 flex-col bg-slate-50">
          <header className="shrink-0 border-b border-slate-200 bg-white px-4 py-3 shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-baseline gap-3">
                <h1 className="text-xl font-semibold tracking-tight text-slate-900">Tenant Admin</h1>
                <span className="text-sm text-slate-500">
                  Manage users, skills, and integrations for tenant{" "}
                  <span className="font-mono text-slate-700">{tenantSlug || "..."}</span>
                </span>
              </div>
              <div className="flex items-center gap-2">
                {currentUser ? (
                  <span className="rounded border border-slate-200 bg-slate-50 px-2 py-1 font-mono text-xs text-slate-600">
                    {currentUser.email}
                  </span>
                ) : null}
                {canReturnToPlatform ? (
                  <button
                    type="button"
                    onClick={onReturnToPlatform}
                    className="rounded border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 shadow-sm transition hover:bg-slate-50"
                  >
                    Back to Platform
                  </button>
                ) : null}
                <button
                  type="button"
                  onClick={() => window.location.reload()}
                  className="rounded border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 shadow-sm transition hover:bg-slate-50"
                >
                  Refresh
                </button>
              </div>
            </div>
            <div className={`mt-2 rounded border px-2.5 py-1.5 text-xs ${flashClass}`}>{flashText || "Ready."}</div>
          </header>

          <div className="flex min-h-0 flex-1 flex-col overflow-y-auto p-4">
            {!isTenantAdmin ? (
              <section className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-xs text-rose-700">
                Tenant admin permission is required.
              </section>
            ) : (
              <div className="space-y-3">
                {activeSection === "overview" ? (
                  <section className="grid gap-2 sm:grid-cols-2 xl:grid-cols-6">
                    <MetricCard label="Users" value={users.length} />
                    <MetricCard label="Workspaces" value={workspaces.length} />
                    <MetricCard label="Skills" value={skillsMerged.length} />
                    <MetricCard label="Automations" value={automationTemplates.length} />
                    <MetricCard label="Plugins" value={plugins.length} />
                    <MetricCard label="Integrations" value={integrations.length} />
                  </section>
                ) : null}

                {activeSection === "users" ? (
                  <Panel
                    title="Tenant Users"
                    subtitle="Create or update users and their tenant role."
                    actionLabel="New User"
                    onAction={newUserForm}
                  >
                    <TableWrap>
                      <table className="min-w-full text-left text-xs">
                        <thead className="bg-slate-50 text-[11px] font-medium uppercase tracking-wide text-slate-500">
                          <tr>
                            <th className="px-2 py-1.5">Email</th>
                            <th className="px-2 py-1.5">Role</th>
                            <th className="px-2 py-1.5">Active</th>
                            <th className="w-14 px-2 py-1.5" />
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                          {users.length === 0 ? (
                            <tr>
                              <td className="px-2 py-2 text-slate-500" colSpan={4}>
                                No users in this tenant.
                              </td>
                            </tr>
                          ) : (
                            users.map((row) => (
                              <tr key={row.id} className="hover:bg-slate-50/80">
                                <td className="px-2 py-1.5 font-mono text-slate-700">{row.email}</td>
                                <td className="px-2 py-1.5 text-slate-700">{row.role}</td>
                                <td className="px-2 py-1.5 text-slate-700">
                                  {row.isActive && row.membershipActive ? "yes" : "no"}
                                </td>
                                <td className="px-2 py-1.5">
                                  <button
                                    type="button"
                                    onClick={() => editUserForm(row)}
                                    className="rounded border border-slate-300 bg-white px-2 py-1 text-xs font-medium text-slate-700 shadow-sm hover:bg-slate-50"
                                  >
                                    Edit
                                  </button>
                                </td>
                              </tr>
                            ))
                          )}
                        </tbody>
                      </table>
                    </TableWrap>
                  </Panel>
                ) : null}

                {activeSection === "workspaces" ? (
                  <Panel
                    title="Workspaces"
                    subtitle="Create and manage tenant workspaces."
                    actionLabel="New Workspace"
                    onAction={newWorkspaceForm}
                  >
                    <TableWrap>
                      <table className="min-w-full text-left text-sm">
                        <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                          <tr>
                            <th className="px-3 py-2">Workspace</th>
                            <th className="px-3 py-2">Slug</th>
                            <th className="px-3 py-2">Active</th>
                            <th className="px-3 py-2" />
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                          {workspaces.length === 0 ? (
                            <tr>
                              <td className="px-3 py-3 text-sm text-slate-500" colSpan={4}>
                                No workspaces available.
                              </td>
                            </tr>
                          ) : (
                            workspaces.map((row) => (
                              <tr key={row.id}>
                                <td className="px-3 py-2 font-medium text-slate-900">
                                  <div>{row.displayName || row.name || row.slug}</div>
                                  <div className="mt-0.5 text-[11px] font-normal text-slate-500">
                                    {row.defaultVendor || "openai"} · {row.defaultModel || "gpt-4.1-mini"} ·{" "}
                                    {row.defaultThinking || "default"} · {row.defaultVerbosity || "minimal"}
                                  </div>
                                </td>
                                <td className="px-3 py-2 font-mono text-xs text-slate-700">{row.slug}</td>
                                <td className="px-3 py-2 text-xs text-slate-700">{row.isActive ? "yes" : "no"}</td>
                                <td className="px-3 py-2">
                                  <div className="flex items-center gap-1.5">
                                    <button
                                      type="button"
                                      onClick={() => editWorkspaceForm(row)}
                                      className="rounded-md border border-slate-300 bg-white px-2 py-1 text-xs font-semibold text-slate-700 hover:bg-slate-50"
                                    >
                                      Edit
                                    </button>
                                    <button
                                      type="button"
                                      onClick={() => openAgentForWorkspace(row.slug, row.uuid)}
                                      className="rounded-md border border-sky-300 bg-sky-50 px-2 py-1 text-xs font-semibold text-sky-700 hover:bg-sky-100"
                                    >
                                      Open Agent
                                    </button>
                                  </div>
                                </td>
                              </tr>
                            ))
                          )}
                        </tbody>
                      </table>
                    </TableWrap>
                  </Panel>
                ) : null}

                {activeSection === "skills" ? (
                  <Panel
                    title="Skills"
                    subtitle="Browse the catalog, enable skills per workspace, and author tenant-owned skills."
                    actionLabel="New Skill"
                    onAction={newSkillForm}
                  >
                    <div className="mb-4 flex flex-wrap items-center gap-2">
                      <span className="text-sm font-medium text-slate-700">Workspace</span>
                      <select
                        className="rounded-lg border border-slate-300 bg-white px-2.5 py-2 text-sm"
                        value={workspaceSlug}
                        onChange={(event) => {
                          const next = event.target.value || "main";
                          setWorkspaceSlug(next);
                          void loadBootstrap(next);
                        }}
                      >
                        {workspaces.map((workspace) => (
                          <option key={workspace.slug} value={workspace.slug}>
                            {workspace.displayName || workspace.name || workspace.slug}
                          </option>
                        ))}
                      </select>
                      <input
                        className="min-w-[240px] flex-1 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
                        value={skillQuery}
                        onChange={(event) => setSkillQuery(event.target.value)}
                        placeholder="Search skills"
                      />
                      <button
                        type="button"
                        onClick={() => void onSaveWorkspaceSkillEnablement()}
                        className="rounded-lg border border-sky-300 bg-sky-50 px-3 py-2 text-xs font-semibold text-sky-700 hover:bg-sky-100"
                      >
                        Save Workspace Enablement
                      </button>
                    </div>

                    <div className="space-y-4">
                      <section>
                        <div className="mb-2 flex items-center justify-between">
                          <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Installed</h3>
                          <span className="text-xs text-slate-500">{installedSkills.length} enabled in {workspaceSlug}</span>
                        </div>
                        <div className="grid gap-2 md:grid-cols-2">
                          {installedSkills.length === 0 ? (
                            <EmptyStateCard text="No skills enabled for this workspace." />
                          ) : (
                            installedSkills.map((skill) => (
                              <CatalogCard
                                key={`${skill.scope}:${skill.key}:installed`}
                                title={skill.name || skill.key}
                                subtitle={skill.description || "No description provided."}
                                meta={`${skill.scope} · ${skill.key}`}
                                active
                                actionLabel="Disable"
                                onAction={() => toggleEnabledSkillKey(skill.key)}
                                onSelect={() => {
                                  if (skill.scope === "tenant") editSkillForm(skill);
                                }}
                              />
                            ))
                          )}
                        </div>
                      </section>

                      <section>
                        <div className="mb-2 flex items-center justify-between">
                          <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Catalog</h3>
                          <span className="text-xs text-slate-500">Global and tenant skills available to install.</span>
                        </div>
                        <div className="grid gap-2 md:grid-cols-2">
                          {availableSkills.length === 0 ? (
                            <EmptyStateCard text="Everything matching the current search is already installed." />
                          ) : (
                            availableSkills.map((skill) => (
                              <CatalogCard
                                key={`${skill.scope}:${skill.key}:catalog`}
                                title={skill.name || skill.key}
                                subtitle={skill.description || "No description provided."}
                                meta={`${skill.scope} · ${skill.key}`}
                                actionLabel="Install"
                                onAction={() => toggleEnabledSkillKey(skill.key)}
                                onSelect={() => {
                                  if (skill.scope === "tenant") editSkillForm(skill);
                                }}
                              />
                            ))
                          )}
                        </div>
                      </section>
                    </div>
                  </Panel>
                ) : null}

                {activeSection === "automations" ? (
                  <Panel title="Automations" subtitle="Create reusable templates and install scheduled automations per workspace.">
                    <div className="mb-4 flex flex-wrap items-center gap-2">
                      <span className="text-sm font-medium text-slate-700">Workspace</span>
                      <select
                        className="rounded-lg border border-slate-300 bg-white px-2.5 py-2 text-sm"
                        value={workspaceSlug}
                        onChange={(event) => {
                          const next = event.target.value || "main";
                          setWorkspaceSlug(next);
                          setAutomationInstanceForm((prev) => ({ ...prev, workspace: next }));
                          void loadBootstrap(next);
                        }}
                      >
                        {workspaces.map((workspace) => (
                          <option key={workspace.slug} value={workspace.slug}>
                            {workspace.displayName || workspace.name || workspace.slug}
                          </option>
                        ))}
                      </select>
                      <input
                        className="min-w-[240px] flex-1 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
                        value={automationQuery}
                        onChange={(event) => setAutomationQuery(event.target.value)}
                        placeholder="Search automations"
                      />
                    </div>

                    <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
                      <section className="rounded-xl border border-slate-200 bg-slate-50/50 p-3">
                        <div className="mb-3 flex items-center justify-between">
                          <div>
                            <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Installed in {workspaceSlug}</h3>
                            <p className="text-xs text-slate-500">Instances bound to the current workspace.</p>
                          </div>
                          <button
                            className="rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50"
                            type="button"
                            onClick={newAutomationInstanceForm}
                          >
                            New Instance
                          </button>
                        </div>
                        <div className="grid gap-2">
                          {filteredAutomationInstances.length === 0 ? (
                            <EmptyStateCard text="No automation instances are installed in this workspace." />
                          ) : (
                            filteredAutomationInstances.map((row) => (
                              <CatalogCard
                                key={row.id}
                                title={row.name}
                                subtitle={row.message || "No message configured."}
                                meta={automationInstanceMeta(row)}
                                active={row.isActive}
                                actionLabel="Edit"
                                onAction={() => editAutomationInstanceForm(row)}
                                onSelect={() => editAutomationInstanceForm(row)}
                              />
                            ))
                          )}
                        </div>
                      </section>

                      <section className="rounded-xl border border-slate-200 bg-slate-50/50 p-3">
                        <div className="mb-3 flex items-center justify-between">
                          <div>
                            <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Template Catalog</h3>
                            <p className="text-xs text-slate-500">Reusable automation recipes for this tenant.</p>
                          </div>
                          <button
                            className="rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50"
                            type="button"
                            onClick={newAutomationTemplateForm}
                          >
                            New Template
                          </button>
                        </div>
                        <div className="grid gap-2">
                          {filteredAutomationTemplates.length === 0 ? (
                            <EmptyStateCard text="No templates match the current search." />
                          ) : (
                            filteredAutomationTemplates.map((row) => (
                              <CatalogCard
                                key={row.id}
                                title={row.name}
                                subtitle={row.description || "No description provided."}
                                meta={`${row.category || "general"} · ${row.key}`}
                                active={row.isActive}
                                actionLabel="Install"
                                onAction={() => draftAutomationInstanceFromTemplate(row)}
                                onSelect={() => editAutomationTemplateForm(row)}
                              />
                            ))
                          )}
                        </div>
                      </section>
                    </div>

                    <section className="mt-3 rounded-xl border border-slate-200 bg-slate-50/50 p-3">
                      <div className="mb-3">
                        <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Recent Runs</h3>
                        <p className="text-xs text-slate-500">Latest execution logs for the selected workspace.</p>
                      </div>
                      <div className="grid gap-2">
                        {automationRunLogs.length === 0 ? (
                          <EmptyStateCard text="No automation runs have been recorded yet." />
                        ) : (
                          automationRunLogs.slice(0, 8).map((row) => (
                            <div key={row.id} className="rounded-xl border border-slate-200 bg-white p-3">
                              <div className="flex items-center justify-between gap-3">
                                <div>
                                  <p className="text-sm font-semibold text-slate-900">{row.status || "unknown"}</p>
                                  <p className="text-xs text-slate-500">{automationRunMeta(row)}</p>
                                </div>
                                <span className="text-[11px] font-mono text-slate-400">{row.runId.slice(0, 8)}</span>
                              </div>
                              {row.errorMessage ? (
                                <p className="mt-2 text-xs text-rose-600">{row.errorMessage}</p>
                              ) : row.summary ? (
                                <p className="mt-2 text-xs text-slate-600">{row.summary}</p>
                              ) : null}
                            </div>
                          ))
                        )}
                      </div>
                    </section>

                  </Panel>
                ) : null}

                {activeSection === "plugins" ? (
                  <Panel
                    title="Plugins"
                    subtitle="Enable validated plugins for this tenant, configure runtime settings, and manage assignment rules."
                  >
                    <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                      <div className="text-xs text-slate-600">
                        Registry sync:{" "}
                        <span className="font-mono text-slate-800">{pluginSync.syncedCount} manifests</span>
                      </div>
                      <button
                        type="button"
                        onClick={() => void onRefreshPlugins()}
                        className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50"
                      >
                        Refresh Plugin State
                      </button>
                    </div>

                    {pluginSync.invalid.length > 0 ? (
                      <div className="mb-3 rounded-xl border border-amber-300 bg-amber-50 p-3">
                        <div className="text-xs font-semibold uppercase tracking-wide text-amber-700">
                          Invalid Plugin Bundles
                        </div>
                        <div className="mt-2 space-y-1.5 text-xs text-amber-800">
                          {pluginSync.invalid.map((row, index) => (
                            <div key={`${row.manifestPath}:${index}`} className="rounded-md bg-white/70 p-2">
                              <div className="font-mono">{row.manifestPath}</div>
                              <div>{row.error}</div>
                            </div>
                          ))}
                        </div>
                      </div>
                    ) : null}

                    <div className="grid grid-cols-1 gap-3 xl:grid-cols-[minmax(0,1fr)_460px]">
                      <TableWrap>
                        <table className="min-w-full text-left text-sm">
                          <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                            <tr>
                              <th className="px-3 py-2">Plugin</th>
                              <th className="px-3 py-2">Version</th>
                              <th className="px-3 py-2">Validated</th>
                              <th className="px-3 py-2">Platform</th>
                              <th className="px-3 py-2">Enabled</th>
                              <th className="px-3 py-2" />
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-100">
                            {plugins.length === 0 ? (
                              <tr>
                                <td className="px-3 py-3 text-sm text-slate-500" colSpan={6}>
                                  No plugins discovered for this environment.
                                </td>
                              </tr>
                            ) : (
                              plugins.map((row) => {
                                const selected = row.pluginId === selectedPluginId;
                                const binding = getTenantPluginBinding(row.pluginId);
                                return (
                                  <tr key={row.pluginId} className={selected ? "bg-sky-50/60" : ""}>
                                    <td className="px-3 py-2">
                                      <div className="flex items-center gap-2">
                                        <PluginAvatar
                                          iconDataUrl={row.iconDataUrl}
                                          fallback={row.iconFallback || row.name || row.pluginId}
                                        />
                                        <div>
                                          <div className="font-medium text-slate-900">{row.name || row.pluginId}</div>
                                          <div className="font-mono text-[11px] text-slate-500">{row.pluginId}</div>
                                        </div>
                                      </div>
                                    </td>
                                    <td className="px-3 py-2 font-mono text-xs text-slate-700">{row.version || "-"}</td>
                                    <td className="px-3 py-2 text-xs text-slate-700">
                                      {row.isValidated ? "yes" : "no"}
                                    </td>
                                    <td className="px-3 py-2 text-xs text-slate-700">
                                      {row.isPlatformApproved ? "approved" : "blocked"}
                                    </td>
                                    <td className="px-3 py-2 text-xs text-slate-700">
                                      {binding?.isEnabled ? "yes" : "no"}
                                    </td>
                                    <td className="px-3 py-2">
                                      <button
                                        type="button"
                                        onClick={() => setSelectedPluginId(row.pluginId)}
                                        className="rounded-md border border-slate-300 bg-white px-2 py-1 text-xs font-semibold text-slate-700 hover:bg-slate-50"
                                      >
                                        Select
                                      </button>
                                    </td>
                                  </tr>
                                );
                              })
                            )}
                          </tbody>
                        </table>
                      </TableWrap>

                      <form
                        className="rounded-xl border border-slate-200 bg-white p-3"
                        onSubmit={(event) => {
                          event.preventDefault();
                          void onSavePlugin();
                        }}
                      >
                        {selectedPlugin ? (
                          <>
                            <div className="mb-2">
                              <div className="flex items-center gap-2">
                                <PluginAvatar
                                  iconDataUrl={selectedPlugin.iconDataUrl}
                                  fallback={selectedPlugin.iconFallback || selectedPlugin.name || selectedPlugin.pluginId}
                                  size="md"
                                />
                                <h3 className="text-sm font-semibold text-slate-900">
                                  {selectedPlugin.name || selectedPlugin.pluginId}
                                </h3>
                              </div>
                              <div className="mt-1 font-mono text-xs text-slate-500">
                                {selectedPlugin.pluginId} · v{selectedPlugin.version || "?"}
                              </div>
                            </div>

                            {!selectedPlugin.isValidated ? (
                              <div className="mb-2 rounded-lg border border-rose-300 bg-rose-50 px-2.5 py-2 text-xs text-rose-700">
                                This plugin is not validated and cannot be enabled.
                              </div>
                            ) : null}
                            {selectedPlugin.isValidated && !selectedPlugin.isPlatformApproved ? (
                              <div className="mb-2 rounded-lg border border-amber-300 bg-amber-50 px-2.5 py-2 text-xs text-amber-700">
                                Waiting for platform admin approval before tenant enablement.
                              </div>
                            ) : null}

                            <label className="mb-2 inline-flex items-center gap-2 text-xs text-slate-700">
                              <input
                                type="checkbox"
                                checked={pluginForm.isEnabled}
                                disabled={!selectedPlugin.isValidated || !selectedPlugin.isPlatformApproved}
                                onChange={(event) =>
                                  setPluginForm((prev) => ({ ...prev, isEnabled: event.target.checked }))
                                }
                              />
                              Enabled for this tenant
                            </label>

                            <Field label="Notes">
                              <input
                                className="w-full rounded-lg border border-slate-300 px-2.5 py-2 text-sm"
                                value={pluginForm.notes}
                                onChange={(event) =>
                                  setPluginForm((prev) => ({ ...prev, notes: event.target.value }))
                                }
                                placeholder="Tenant-specific notes"
                              />
                            </Field>

                            <Field label="Plugin Configuration">
                              {selectedPluginConfigFields.length === 0 ? (
                                <div className="rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-2 text-xs text-slate-600">
                                  This plugin does not declare <span className="font-mono">config_schema.properties</span>.
                                  No guided tenant config form is available.
                                </div>
                              ) : (
                                <div className="space-y-2">
                                  {selectedPluginConfigFields.map((field) => {
                                    const value = pluginForm.pluginConfigObject[field.key];
                                    const normalizedType = field.type || "string";
                                    return (
                                      <div key={field.key} className="rounded-lg border border-slate-200 bg-slate-50 p-2">
                                        <div className="mb-1 flex items-center justify-between gap-2">
                                          <label className="text-xs font-semibold text-slate-700">{field.title}</label>
                                          <span className="font-mono text-[11px] text-slate-500">{field.key}</span>
                                        </div>
                                        {normalizedType === "boolean" ? (
                                          <label className="inline-flex items-center gap-2 text-xs text-slate-700">
                                            <input
                                              type="checkbox"
                                              checked={Boolean(value)}
                                              onChange={(event) => updatePluginConfigField(field, event.target.checked)}
                                            />
                                            Enabled
                                          </label>
                                        ) : field.enumValues.length > 0 ? (
                                          <select
                                            className="w-full rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-sm"
                                            value={String(value ?? field.defaultValue ?? "")}
                                            onChange={(event) => updatePluginConfigField(field, event.target.value)}
                                          >
                                            <option value="">Select...</option>
                                            {field.enumValues.map((item) => (
                                              <option key={item} value={item}>
                                                {item}
                                              </option>
                                            ))}
                                          </select>
                                        ) : normalizedType === "integer" || normalizedType === "number" ? (
                                          <input
                                            type="number"
                                            className="w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
                                            value={value === undefined || value === null ? "" : String(value)}
                                            onChange={(event) => {
                                              const raw = String(event.target.value || "").trim();
                                              if (!raw) {
                                                updatePluginConfigField(field, undefined);
                                                return;
                                              }
                                              const parsed = normalizedType === "integer" ? Number.parseInt(raw, 10) : Number.parseFloat(raw);
                                              updatePluginConfigField(field, Number.isFinite(parsed) ? parsed : undefined);
                                            }}
                                          />
                                        ) : (
                                          <input
                                            type="text"
                                            className="w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
                                            value={value === undefined || value === null ? "" : String(value)}
                                            onChange={(event) => updatePluginConfigField(field, event.target.value)}
                                          />
                                        )}
                                        {field.description ? (
                                          <div className="mt-1 text-[11px] text-slate-500">{field.description}</div>
                                        ) : null}
                                      </div>
                                    );
                                  })}
                                </div>
                              )}
                            </Field>

                            <Field label="Plugin Help (README.md)">
                              {selectedPlugin.helpMarkdown ? (
                                <pre className="max-h-52 overflow-auto whitespace-pre-wrap rounded-lg border border-slate-200 bg-slate-50 p-2 text-[11px] text-slate-700">
                                  {selectedPlugin.helpMarkdown}
                                </pre>
                              ) : (
                                <div className="rounded-lg border border-slate-200 bg-slate-50 px-2 py-1.5 text-xs text-slate-500">
                                  No README.md found in this plugin bundle.
                                </div>
                              )}
                            </Field>

                            <div className="mb-2 rounded-lg border border-slate-200 bg-slate-50 p-2">
                              <div className="mb-2 flex items-center justify-between gap-2">
                                <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                                  Assignment Rules
                                </div>
                                <div className="flex items-center gap-1.5">
                                  <button
                                    type="button"
                                    onClick={() => addPluginAssignment("role")}
                                    className="rounded-md border border-slate-300 bg-white px-2 py-1 text-[11px] font-semibold text-slate-700 hover:bg-slate-50"
                                  >
                                    Add Role
                                  </button>
                                  <button
                                    type="button"
                                    onClick={() => addPluginAssignment("user")}
                                    className="rounded-md border border-slate-300 bg-white px-2 py-1 text-[11px] font-semibold text-slate-700 hover:bg-slate-50"
                                  >
                                    Add User
                                  </button>
                                </div>
                              </div>

                              <div className="space-y-2">
                                {pluginForm.assignments.length === 0 ? (
                                  <div className="text-xs text-slate-500">
                                    No rules configured. When empty, plugin is available to all tenant users.
                                  </div>
                                ) : (
                                  pluginForm.assignments.map((row, index) => (
                                    <div key={`${row.assignmentType}:${index}`} className="rounded-md border border-slate-200 bg-white p-2">
                                      <div className="grid gap-2 md:grid-cols-2">
                                        <select
                                          className="w-full rounded-lg border border-slate-300 px-2 py-1.5 text-xs"
                                          value={row.assignmentType}
                                          onChange={(event) =>
                                            updatePluginAssignment(index, {
                                              assignmentType: event.target.value as "role" | "user",
                                              role: "member",
                                              userId: 0,
                                              userEmail: "",
                                            })
                                          }
                                        >
                                          <option value="role">role</option>
                                          <option value="user">user</option>
                                        </select>
                                        <label className="inline-flex items-center gap-1.5 text-xs text-slate-700">
                                          <input
                                            type="checkbox"
                                            checked={row.isActive}
                                            onChange={(event) =>
                                              updatePluginAssignment(index, { isActive: event.target.checked })
                                            }
                                          />
                                          active
                                        </label>
                                      </div>
                                      {row.assignmentType === "role" ? (
                                        <select
                                          className="mt-2 w-full rounded-lg border border-slate-300 px-2 py-1.5 text-xs"
                                          value={row.role}
                                          onChange={(event) =>
                                            updatePluginAssignment(index, {
                                              role: event.target.value as PluginAssignmentDraft["role"],
                                            })
                                          }
                                        >
                                          <option value="admin">admin</option>
                                          <option value="member">member</option>
                                          <option value="viewer">viewer</option>
                                        </select>
                                      ) : (
                                        <div className="mt-2 grid gap-2">
                                          <select
                                            className="w-full rounded-lg border border-slate-300 px-2 py-1.5 text-xs"
                                            value={row.userId > 0 ? String(row.userId) : ""}
                                            onChange={(event) => {
                                              const nextUserId = Number(event.target.value || 0);
                                              const selectedUserRow = users.find(
                                                (item) => Number(item.id) === nextUserId
                                              );
                                              updatePluginAssignment(index, {
                                                userId: nextUserId,
                                                userEmail: selectedUserRow?.email || row.userEmail,
                                              });
                                            }}
                                          >
                                            <option value="">Select user</option>
                                            {users.map((user) => (
                                              <option key={user.id} value={user.id}>
                                                {user.displayName || user.email} ({user.email})
                                              </option>
                                            ))}
                                          </select>
                                          <input
                                            className="w-full rounded-lg border border-slate-300 px-2 py-1.5 text-xs font-mono"
                                            value={row.userEmail}
                                            onChange={(event) =>
                                              updatePluginAssignment(index, {
                                                userEmail: event.target.value,
                                              })
                                            }
                                            placeholder="or user email"
                                          />
                                        </div>
                                      )}
                                      <div className="mt-2 flex items-center gap-2">
                                        <input
                                          className="min-w-0 flex-1 rounded-lg border border-slate-300 px-2 py-1.5 text-xs"
                                          value={row.notes}
                                          onChange={(event) =>
                                            updatePluginAssignment(index, { notes: event.target.value })
                                          }
                                          placeholder="Rule notes"
                                        />
                                        <button
                                          type="button"
                                          onClick={() => removePluginAssignment(index)}
                                          className="rounded-md border border-rose-300 bg-rose-50 px-2 py-1 text-[11px] font-semibold text-rose-700 hover:bg-rose-100"
                                        >
                                          Remove
                                        </button>
                                      </div>
                                    </div>
                                  ))
                                )}
                              </div>
                            </div>

                            <div className="flex gap-2">
                              <button
                                className="rounded-lg bg-slate-900 px-3 py-2 text-xs font-semibold text-white hover:bg-slate-800"
                                type="submit"
                              >
                                Save Plugin
                              </button>
                              <button
                                type="button"
                                onClick={() => resetPluginForm(pluginForm.pluginId)}
                                className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50"
                              >
                                Reset
                              </button>
                            </div>
                          </>
                        ) : (
                          <div className="text-sm text-slate-500">Select a plugin to configure it for this tenant.</div>
                        )}
                      </form>
                    </div>
                  </Panel>
                ) : null}

                {activeSection === "integrations" ? (
                  <Panel title="Integrations" subtitle="Enable and tune integration guidance for this tenant.">
                    <div className="space-y-2">
                      {integrations.length === 0 ? (
                        <div className="rounded-xl border border-slate-200 bg-white p-4 text-sm text-slate-500">
                          No integrations found.
                        </div>
                      ) : (
                        integrations.map((integration) => {
                          const key = String(integration.key || "").toLowerCase();
                          const draft =
                            integrationDrafts[key] ||
                            integrationDraftFromConfig({}, false, "", "");
                          const binding = integrationBindingMap.get(key);
                          const scope = String(integration.authScope || "tenant").toLowerCase();
                          const authType = String(integration.defaultAuthType || "bearer").toLowerCase();
                          const updateDraft = (patch: Partial<IntegrationDraft>) =>
                            setIntegrationDrafts((prev) => ({
                              ...prev,
                              [key]: { ...draft, ...patch },
                            }));
                          return (
                            <article key={integration.key} className="rounded-xl border border-slate-200 bg-white p-3">
                              <div className="flex items-center justify-between gap-2">
                                <div>
                                  <div className="font-semibold text-slate-900">{integration.name || integration.key}</div>
                                  <div className="font-mono text-xs text-slate-600">
                                    {integration.key} | {integration.defaultAuthType || "bearer"} | scope:{scope}
                                  </div>
                                </div>
                                <label className="inline-flex items-center gap-1.5 text-xs text-slate-700">
                                  <input
                                    type="checkbox"
                                    checked={Boolean(draft.isEnabled)}
                                    onChange={(event) => updateDraft({ isEnabled: event.target.checked })}
                                  />
                                  Enabled
                                </label>
                              </div>
                              <div className="mt-2 grid gap-2">
                                <input
                                  className="w-full rounded-lg border border-slate-300 px-2.5 py-2 text-xs"
                                  value={draft.notes}
                                  onChange={(event) => updateDraft({ notes: event.target.value })}
                                  placeholder="Notes"
                                />
                                <textarea
                                  className="h-24 w-full rounded-lg border border-slate-300 px-2.5 py-2 text-xs font-mono"
                                  value={draft.assistantDocsOverride}
                                  onChange={(event) => updateDraft({ assistantDocsOverride: event.target.value })}
                                  placeholder="Assistant docs override (markdown)"
                                />
                                {scope === "global" ? (
                                  <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600">
                                    This integration uses global credentials managed by platform admin.
                                  </div>
                                ) : scope === "user" ? (
                                  <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600">
                                    This integration uses user-scoped credentials. Tenant admin can enable the integration and adjust guidance here, but individual users must provide their own credentials in a user-level flow.
                                  </div>
                                ) : (
                                  <div className="grid gap-2 rounded-lg border border-slate-200 bg-slate-50/70 p-3">
                                    <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                                      Tenant Credential Configuration
                                    </div>
                                    {(authType === "bearer" || authType === "api_key_header" || authType === "api_key_query") ? (
                                      <input
                                        type="password"
                                        className="w-full rounded-lg border border-slate-300 px-2.5 py-2 text-sm"
                                        value={draft.secretValue}
                                        onChange={(event) => updateDraft({ secretValue: event.target.value })}
                                        placeholder={authType === "bearer" ? "Paste token to store/update" : "Paste API key to store/update"}
                                      />
                                    ) : null}
                                    {authType === "basic" ? (
                                      <div className="grid gap-2 md:grid-cols-2">
                                        <input
                                          className="w-full rounded-lg border border-slate-300 px-2.5 py-2 text-sm"
                                          value={draft.username}
                                          onChange={(event) => updateDraft({ username: event.target.value })}
                                          placeholder="Username"
                                        />
                                        <input
                                          type="password"
                                          className="w-full rounded-lg border border-slate-300 px-2.5 py-2 text-sm"
                                          value={draft.password}
                                          onChange={(event) => updateDraft({ password: event.target.value })}
                                          placeholder="Password"
                                        />
                                      </div>
                                    ) : null}
                                    {authType === "oauth2_client_credentials" ? (
                                      <>
                                        <div className="grid gap-2 md:grid-cols-2">
                                          <input
                                            className="w-full rounded-lg border border-slate-300 px-2.5 py-2 text-sm"
                                            value={draft.clientId}
                                            onChange={(event) => updateDraft({ clientId: event.target.value })}
                                            placeholder="Client ID"
                                          />
                                          <input
                                            type="password"
                                            className="w-full rounded-lg border border-slate-300 px-2.5 py-2 text-sm"
                                            value={draft.clientSecret}
                                            onChange={(event) => updateDraft({ clientSecret: event.target.value })}
                                            placeholder="Client Secret"
                                          />
                                        </div>
                                        <div className="grid gap-2 md:grid-cols-2">
                                          <input
                                            className="w-full rounded-lg border border-slate-300 px-2.5 py-2 text-sm"
                                            value={draft.tokenUrl}
                                            onChange={(event) => updateDraft({ tokenUrl: event.target.value })}
                                            placeholder="Token URL"
                                          />
                                          <input
                                            className="w-full rounded-lg border border-slate-300 px-2.5 py-2 text-sm"
                                            value={draft.scope}
                                            onChange={(event) => updateDraft({ scope: event.target.value })}
                                            placeholder="OAuth scope"
                                          />
                                        </div>
                                      </>
                                    ) : null}
                                    {(authType === "api_key_header" || authType === "api_key_query") ? (
                                      <input
                                        className="w-full rounded-lg border border-slate-300 px-2.5 py-2 text-sm"
                                        value={authType === "api_key_header" ? draft.apiKeyHeaderName : draft.apiKeyQueryParamName}
                                        onChange={(event) =>
                                          updateDraft(
                                            authType === "api_key_header"
                                              ? { apiKeyHeaderName: event.target.value }
                                              : { apiKeyQueryParamName: event.target.value }
                                          )
                                        }
                                        placeholder={authType === "api_key_header" ? "Header name" : "Query parameter name"}
                                      />
                                    ) : null}
                                    <div className="grid gap-2 md:grid-cols-2">
                                      <input
                                        className="w-full rounded-lg border border-slate-300 px-2.5 py-2 text-sm"
                                        value={draft.baseUrl}
                                        onChange={(event) => updateDraft({ baseUrl: event.target.value })}
                                        placeholder="Optional base URL override"
                                      />
                                      <input
                                        className="w-full rounded-lg border border-slate-300 px-2.5 py-2 text-sm"
                                        value={draft.timeoutSeconds}
                                        onChange={(event) => updateDraft({ timeoutSeconds: event.target.value })}
                                        placeholder="Timeout seconds"
                                      />
                                    </div>
                                    <textarea
                                      className="h-20 w-full rounded-lg border border-slate-300 px-2.5 py-2 text-xs font-mono"
                                      value={draft.defaultHeadersText}
                                      onChange={(event) => updateDraft({ defaultHeadersText: event.target.value })}
                                      placeholder='Optional default headers JSON, e.g. {"Accept":"application/json"}'
                                    />
                                    <label className="inline-flex items-center gap-1.5 text-[11px] text-slate-600">
                                      <input
                                        type="checkbox"
                                        checked={draft.clearStoredSecrets}
                                        onChange={(event) => updateDraft({ clearStoredSecrets: event.target.checked })}
                                      />
                                      Replace/clear previously stored secret references when saving
                                    </label>
                                    <div className="flex flex-wrap gap-1">
                                      {draft.hasVaultKey ? <SecretBadge label="secret stored" /> : null}
                                      {draft.hasUsernameVaultKey ? <SecretBadge label="username stored" /> : null}
                                      {draft.hasPasswordVaultKey ? <SecretBadge label="password stored" /> : null}
                                      {draft.hasClientIdVaultKey ? <SecretBadge label="client id stored" /> : null}
                                      {draft.hasClientSecretVaultKey ? <SecretBadge label="client secret stored" /> : null}
                                    </div>
                                  </div>
                                )}
                              </div>
                              <div className="mt-2 flex items-center justify-between">
                                <div className="text-[11px] text-slate-500">
                                  Last update: {binding?.updatedAt ? new Date(binding.updatedAt).toLocaleString() : "never"}
                                </div>
                                <button
                                  type="button"
                                  onClick={() => void onSaveIntegration(key)}
                                  className="rounded-lg border border-sky-300 bg-sky-50 px-3 py-1.5 text-xs font-semibold text-sky-700 hover:bg-sky-100"
                                >
                                  Save
                                </button>
                              </div>
                            </article>
                          );
                        })
                      )}
                    </div>
                  </Panel>
                ) : null}

                {activeSection === "settings" ? (
                  <div className="space-y-3">
                    <ManageIntegrationsContent />
                  </div>
                ) : null}
              </div>
            )}
          </div>
        </section>
      </div>

      <Modal open={userModalOpen} onClose={() => setUserModalOpen(false)} title={userForm.id ? "Edit user" : "New user"}>
        <form onSubmit={onSaveUser}>
          <Field label="Email">
            <input
              className="w-full rounded-lg border border-slate-300 px-2.5 py-2 text-sm font-mono"
              value={userForm.email}
              onChange={(event) => setUserForm((prev) => ({ ...prev, email: event.target.value }))}
              placeholder="user@company.com"
            />
          </Field>
          <Field label="Display Name">
            <input
              className="w-full rounded-lg border border-slate-300 px-2.5 py-2 text-sm"
              value={userForm.displayName}
              onChange={(event) => setUserForm((prev) => ({ ...prev, displayName: event.target.value }))}
              placeholder="User name"
            />
          </Field>
          <Field label={userForm.id ? "Password (leave empty to keep current)" : "Password"}>
            <input
              type="password"
              className="w-full rounded-lg border border-slate-300 px-2.5 py-2 text-sm"
              value={userForm.password}
              onChange={(event) => setUserForm((prev) => ({ ...prev, password: event.target.value }))}
              placeholder="********"
            />
          </Field>
          <Field label="Role">
            <select
              className="w-full rounded-lg border border-slate-300 px-2.5 py-2 text-sm"
              value={userForm.role}
              onChange={(event) =>
                setUserForm((prev) => ({
                  ...prev,
                  role: event.target.value as UserFormState["role"],
                }))
              }
            >
              <option value="admin">admin</option>
              <option value="member">member</option>
              <option value="viewer">viewer</option>
            </select>
          </Field>
          <div className="mb-2 flex gap-4 text-xs text-slate-700">
            <label className="inline-flex items-center gap-1.5">
              <input
                type="checkbox"
                checked={userForm.isActive}
                onChange={(event) => setUserForm((prev) => ({ ...prev, isActive: event.target.checked }))}
              />
              Account active
            </label>
            <label className="inline-flex items-center gap-1.5">
              <input
                type="checkbox"
                checked={userForm.membershipActive}
                onChange={(event) => setUserForm((prev) => ({ ...prev, membershipActive: event.target.checked }))}
              />
              Membership active
            </label>
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              className="rounded-lg bg-slate-900 px-3 py-2 text-xs font-semibold text-white hover:bg-slate-800"
              type="submit"
            >
              Save User
            </button>
            {userForm.id ? (
              <button
                className="rounded-lg border border-rose-300 bg-rose-50 px-3 py-2 text-xs font-semibold text-rose-700 hover:bg-rose-100"
                type="button"
                onClick={() => void onDeleteUser()}
              >
                Delete
              </button>
            ) : null}
            <button
              className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50"
              type="button"
              onClick={() => setUserModalOpen(false)}
            >
              Cancel
            </button>
          </div>
        </form>
      </Modal>

      <Modal
        open={workspaceModalOpen}
        onClose={() => setWorkspaceModalOpen(false)}
        title={workspaceForm.id ? "Edit workspace" : "New workspace"}
        size="lg"
      >
        <form onSubmit={onSaveWorkspace}>
          <Field label="Slug">
            <input
              className="w-full rounded-lg border border-slate-300 px-2.5 py-2 text-sm font-mono"
              value={workspaceForm.slug}
              onChange={(event) => setWorkspaceForm((prev) => ({ ...prev, slug: event.target.value }))}
              placeholder="main"
            />
          </Field>
          <Field label="Name">
            <input
              className="w-full rounded-lg border border-slate-300 px-2.5 py-2 text-sm"
              value={workspaceForm.name}
              onChange={(event) => setWorkspaceForm((prev) => ({ ...prev, name: event.target.value }))}
              placeholder="Main Workspace"
            />
          </Field>
          <Field label="Display Name">
            <input
              className="w-full rounded-lg border border-slate-300 px-2.5 py-2 text-sm"
              value={workspaceForm.displayName}
              onChange={(event) => setWorkspaceForm((prev) => ({ ...prev, displayName: event.target.value }))}
              placeholder="Main"
            />
          </Field>
          <Field label="Specialty Prompt">
            <textarea
              className="h-24 w-full rounded-lg border border-slate-300 px-2.5 py-2 text-xs"
              value={workspaceForm.specialtyPrompt}
              onChange={(event) => setWorkspaceForm((prev) => ({ ...prev, specialtyPrompt: event.target.value }))}
              placeholder="Optional workspace specialty prompt"
            />
          </Field>
          <Field label="Tool Allowlist (one per line or comma-separated)">
            <textarea
              className="h-20 w-full rounded-lg border border-slate-300 px-2.5 py-2 font-mono text-xs"
              value={workspaceForm.toolAllowlistText}
              onChange={(event) => setWorkspaceForm((prev) => ({ ...prev, toolAllowlistText: event.target.value }))}
              placeholder={"api.run\nmoio_api.run\nfiles.read"}
            />
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {WORKSPACE_TOOL_HINTS.map((toolName) => (
                <button
                  key={toolName}
                  type="button"
                  onClick={() =>
                    setWorkspaceForm((prev) => {
                      const current = parseToolAllowlistText(prev.toolAllowlistText);
                      if (current.includes(toolName)) return prev;
                      return {
                        ...prev,
                        toolAllowlistText: [...current, toolName].join("\n"),
                      };
                    })
                  }
                  className="rounded-full border border-slate-300 bg-slate-50 px-2 py-0.5 text-[10px] font-semibold text-slate-700 hover:bg-slate-100"
                >
                  + {toolName}
                </button>
              ))}
            </div>
          </Field>
          <Field label="Workspace Plugin Activation">
            {plugins.length === 0 ? (
              <div className="rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-2 text-xs text-slate-500">
                No plugins available.
              </div>
            ) : (
              <div className="max-h-32 space-y-1.5 overflow-auto rounded-lg border border-slate-200 bg-slate-50 p-2">
                {plugins
                  .filter((plugin) => plugin.isValidated && plugin.isPlatformApproved)
                  .map((plugin) => {
                    const pluginId = String(plugin.pluginId || "").trim().toLowerCase();
                    const checked = workspaceForm.pluginAllowlist.includes(pluginId);
                    return (
                      <label key={pluginId} className="flex items-center gap-2 text-xs text-slate-700">
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={(event) =>
                            setWorkspaceForm((prev) => ({
                              ...prev,
                              pluginAllowlist: event.target.checked
                                ? Array.from(new Set([...prev.pluginAllowlist, pluginId]))
                                : prev.pluginAllowlist.filter((item) => item !== pluginId),
                            }))
                          }
                        />
                        <span>{plugin.name || pluginId}</span>
                        <span className="font-mono text-[10px] text-slate-500">{pluginId}</span>
                      </label>
                    );
                  })}
              </div>
            )}
          </Field>
          <Field label="Workspace Integration Activation">
            {integrations.length === 0 ? (
              <div className="rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-2 text-xs text-slate-500">
                No integrations available.
              </div>
            ) : (
              <div className="max-h-32 space-y-1.5 overflow-auto rounded-lg border border-slate-200 bg-slate-50 p-2">
                {integrations.map((integration) => {
                  const key = String(integration.key || "").trim().toLowerCase();
                  const checked = workspaceForm.integrationAllowlist.includes(key);
                  return (
                    <label key={key} className="flex items-center gap-2 text-xs text-slate-700">
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={(event) =>
                          setWorkspaceForm((prev) => ({
                            ...prev,
                            integrationAllowlist: event.target.checked
                              ? Array.from(new Set([...prev.integrationAllowlist, key]))
                              : prev.integrationAllowlist.filter((item) => item !== key),
                          }))
                        }
                      />
                      <span>{integration.name || key}</span>
                      <span className="font-mono text-[10px] text-slate-500">{key}</span>
                    </label>
                  );
                })}
              </div>
            )}
          </Field>
          <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
            <Field label="Default Vendor">
              <select
                className="w-full rounded-lg border border-slate-300 px-2.5 py-2 text-sm"
                value={workspaceForm.defaultVendor}
                onChange={(event) => setWorkspaceForm((prev) => ({ ...prev, defaultVendor: event.target.value }))}
              >
                <option value="">System default</option>
                <option value="openai">OpenAI</option>
                <option value="xai">xAI</option>
                <option value="anthropic">Anthropic</option>
              </select>
            </Field>
            <Field label="Default Model">
              <input
                className="w-full rounded-lg border border-slate-300 px-2.5 py-2 text-sm"
                value={workspaceForm.defaultModel}
                onChange={(event) => setWorkspaceForm((prev) => ({ ...prev, defaultModel: event.target.value }))}
                placeholder="gpt-4.1-mini"
              />
            </Field>
            <Field label="Thinking">
              <select
                className="w-full rounded-lg border border-slate-300 px-2.5 py-2 text-sm"
                value={workspaceForm.defaultThinking}
                onChange={(event) => setWorkspaceForm((prev) => ({ ...prev, defaultThinking: event.target.value }))}
              >
                <option value="default">Default</option>
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
              </select>
            </Field>
            <Field label="Verbosity">
              <select
                className="w-full rounded-lg border border-slate-300 px-2.5 py-2 text-sm"
                value={workspaceForm.defaultVerbosity}
                onChange={(event) => setWorkspaceForm((prev) => ({ ...prev, defaultVerbosity: event.target.value }))}
              >
                <option value="minimal">Minimal</option>
                <option value="normal">Normal</option>
                <option value="detailed">Detailed</option>
              </select>
            </Field>
          </div>
          <label className="mb-2 flex items-center gap-1.5 text-xs text-slate-700">
            <input
              type="checkbox"
              checked={workspaceForm.isActive}
              onChange={(event) => setWorkspaceForm((prev) => ({ ...prev, isActive: event.target.checked }))}
            />
            Active
          </label>
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              className="rounded-lg bg-slate-900 px-3 py-2 text-xs font-semibold text-white hover:bg-slate-800"
              type="submit"
            >
              Save Workspace
            </button>
            {workspaceForm.id ? (
              <button
                className="rounded-lg border border-rose-300 bg-rose-50 px-3 py-2 text-xs font-semibold text-rose-700 hover:bg-rose-100"
                type="button"
                onClick={() => void onDeleteWorkspace()}
              >
                Delete
              </button>
            ) : null}
            <button
              className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50"
              type="button"
              onClick={() => setWorkspaceModalOpen(false)}
            >
              Cancel
            </button>
          </div>
        </form>
      </Modal>

      <Modal open={skillModalOpen} onClose={() => setSkillModalOpen(false)} title={skillForm.key ? "Edit skill" : "New skill"} size="lg">
        <form onSubmit={onSaveSkill}>
          <Field label="Skill Key">
            <input
              className="w-full rounded-lg border border-slate-300 px-2.5 py-2 text-sm font-mono"
              value={skillForm.key}
              onChange={(event) => setSkillForm((prev) => ({ ...prev, key: event.target.value }))}
              placeholder="tenant_followup"
            />
          </Field>
          <Field label="Name">
            <input
              className="w-full rounded-lg border border-slate-300 px-2.5 py-2 text-sm"
              value={skillForm.name}
              onChange={(event) => setSkillForm((prev) => ({ ...prev, name: event.target.value }))}
              placeholder="Tenant follow-up"
            />
          </Field>
          <Field label="Description">
            <input
              className="w-full rounded-lg border border-slate-300 px-2.5 py-2 text-sm"
              value={skillForm.description}
              onChange={(event) => setSkillForm((prev) => ({ ...prev, description: event.target.value }))}
              placeholder="What this skill does"
            />
          </Field>
          <Field label="Skill Markdown">
            <textarea
              className="h-48 w-full rounded-lg border border-slate-300 px-2.5 py-2 text-xs font-mono"
              value={skillForm.bodyMarkdown}
              onChange={(event) => setSkillForm((prev) => ({ ...prev, bodyMarkdown: event.target.value }))}
              placeholder="# Objective&#10;...&#10;&#10;# Constraints&#10;..."
            />
          </Field>
          <label className="mb-2 flex items-center gap-1.5 text-xs text-slate-700">
            <input
              type="checkbox"
              checked={skillForm.isActive}
              onChange={(event) => setSkillForm((prev) => ({ ...prev, isActive: event.target.checked }))}
            />
            Active
          </label>
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              className="rounded-lg bg-slate-900 px-3 py-2 text-xs font-semibold text-white hover:bg-slate-800"
              type="submit"
            >
              Save Skill
            </button>
            {skillForm.key ? (
              <button
                className="rounded-lg border border-rose-300 bg-rose-50 px-3 py-2 text-xs font-semibold text-rose-700 hover:bg-rose-100"
                type="button"
                onClick={() => void onDeleteSkill()}
              >
                Delete
              </button>
            ) : null}
            <button
              className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50"
              type="button"
              onClick={() => setSkillModalOpen(false)}
            >
              Cancel
            </button>
          </div>
        </form>
      </Modal>

      <Modal
        open={automationTemplateModalOpen}
        onClose={() => setAutomationTemplateModalOpen(false)}
        title={automationTemplateForm.id ? "Edit template" : "New template"}
        size="lg"
      >
        <form onSubmit={onSaveAutomationTemplate}>
          <Field label="Key">
            <input
              className="w-full rounded-lg border border-slate-300 px-2.5 py-2 text-sm font-mono"
              value={automationTemplateForm.key}
              onChange={(event) => setAutomationTemplateForm((prev) => ({ ...prev, key: event.target.value }))}
              placeholder="daily_pipeline_review"
            />
          </Field>
          <Field label="Name">
            <input
              className="w-full rounded-lg border border-slate-300 px-2.5 py-2 text-sm"
              value={automationTemplateForm.name}
              onChange={(event) => setAutomationTemplateForm((prev) => ({ ...prev, name: event.target.value }))}
              placeholder="Daily Pipeline Review"
            />
          </Field>
          <Field label="Description">
            <input
              className="w-full rounded-lg border border-slate-300 px-2.5 py-2 text-sm"
              value={automationTemplateForm.description}
              onChange={(event) =>
                setAutomationTemplateForm((prev) => ({ ...prev, description: event.target.value }))
              }
              placeholder="What this automation does"
            />
          </Field>
          <Field label="Default Message">
            <textarea
              className="h-24 w-full rounded-lg border border-slate-300 px-2.5 py-2 text-xs"
              value={automationTemplateForm.defaultMessage}
              onChange={(event) =>
                setAutomationTemplateForm((prev) => ({ ...prev, defaultMessage: event.target.value }))
              }
              placeholder="Analyze the pipeline state and summarize blockers."
            />
          </Field>
          <Field label="Example Prompt">
            <textarea
              className="h-20 w-full rounded-lg border border-slate-300 px-2.5 py-2 text-xs"
              value={automationTemplateForm.examplePrompt}
              onChange={(event) =>
                setAutomationTemplateForm((prev) => ({ ...prev, examplePrompt: event.target.value }))
              }
              placeholder="Check the deployment backlog and produce today's ops digest."
            />
          </Field>
          <Field label="Instructions Markdown">
            <textarea
              className="h-32 w-full rounded-lg border border-slate-300 px-2.5 py-2 text-xs font-mono"
              value={automationTemplateForm.instructionsMarkdown}
              onChange={(event) =>
                setAutomationTemplateForm((prev) => ({
                  ...prev,
                  instructionsMarkdown: event.target.value,
                }))
              }
              placeholder="# Goal&#10;...&#10;&#10;# Output&#10;..."
            />
          </Field>
          <div className="grid grid-cols-2 gap-2">
            <Field label="Category">
              <input
                className="w-full rounded-lg border border-slate-300 px-2.5 py-2 text-sm"
                value={automationTemplateForm.category}
                onChange={(event) =>
                  setAutomationTemplateForm((prev) => ({ ...prev, category: event.target.value }))
                }
                placeholder="ops"
              />
            </Field>
            <Field label="Icon">
              <input
                className="w-full rounded-lg border border-slate-300 px-2.5 py-2 text-sm"
                value={automationTemplateForm.icon}
                onChange={(event) =>
                  setAutomationTemplateForm((prev) => ({ ...prev, icon: event.target.value }))
                }
                placeholder="bolt"
              />
            </Field>
          </div>
          <div className="mb-2 flex gap-4 text-xs text-slate-700">
            <label className="inline-flex items-center gap-1.5">
              <input
                type="checkbox"
                checked={automationTemplateForm.isActive}
                onChange={(event) =>
                  setAutomationTemplateForm((prev) => ({ ...prev, isActive: event.target.checked }))
                }
              />
              Active
            </label>
            <label className="inline-flex items-center gap-1.5">
              <input
                type="checkbox"
                checked={automationTemplateForm.isRecommended}
                onChange={(event) =>
                  setAutomationTemplateForm((prev) => ({ ...prev, isRecommended: event.target.checked }))
                }
              />
              Recommended
            </label>
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              className="rounded-lg bg-slate-900 px-3 py-2 text-xs font-semibold text-white hover:bg-slate-800"
              type="submit"
            >
              Save Template
            </button>
            {automationTemplateForm.id || automationTemplateForm.key ? (
              <button
                className="rounded-lg border border-rose-300 bg-rose-50 px-3 py-2 text-xs font-semibold text-rose-700 hover:bg-rose-100"
                type="button"
                onClick={() => void onDeleteAutomationTemplate()}
              >
                Delete
              </button>
            ) : null}
            <button
              className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50"
              type="button"
              onClick={() => setAutomationTemplateModalOpen(false)}
            >
              Cancel
            </button>
          </div>
        </form>
      </Modal>

      <Modal
        open={automationInstanceModalOpen}
        onClose={() => setAutomationInstanceModalOpen(false)}
        title={automationInstanceForm.id ? "Edit instance" : "New instance"}
        size="lg"
      >
        <form onSubmit={onSaveAutomationInstance}>
          <Field label="Workspace">
            <select
              className="w-full rounded-lg border border-slate-300 px-2.5 py-2 text-sm"
              value={automationInstanceForm.workspace}
              onChange={(event) =>
                setAutomationInstanceForm((prev) => ({ ...prev, workspace: event.target.value || "main" }))
              }
            >
              {workspaces.map((workspace) => (
                <option key={workspace.slug} value={workspace.slug}>
                  {workspace.displayName || workspace.name || workspace.slug}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Template Key (optional)">
            <input
              className="w-full rounded-lg border border-slate-300 px-2.5 py-2 text-sm font-mono"
              value={automationInstanceForm.templateKey}
              onChange={(event) =>
                setAutomationInstanceForm((prev) => ({ ...prev, templateKey: event.target.value }))
              }
              placeholder="daily_pipeline_review"
            />
          </Field>
          <Field label="Name">
            <input
              className="w-full rounded-lg border border-slate-300 px-2.5 py-2 text-sm"
              value={automationInstanceForm.name}
              onChange={(event) => setAutomationInstanceForm((prev) => ({ ...prev, name: event.target.value }))}
              placeholder="Daily Pipeline Review"
            />
          </Field>
          <Field label="Message">
            <textarea
              className="h-24 w-full rounded-lg border border-slate-300 px-2.5 py-2 text-xs"
              value={automationInstanceForm.message}
              onChange={(event) =>
                setAutomationInstanceForm((prev) => ({ ...prev, message: event.target.value }))
              }
              placeholder="Describe the work to run on schedule."
            />
          </Field>
          <div className="grid grid-cols-2 gap-2">
            <Field label="Execution Mode">
              <select
                className="w-full rounded-lg border border-slate-300 px-2.5 py-2 text-sm"
                value={automationInstanceForm.executionMode}
                onChange={(event) =>
                  setAutomationInstanceForm((prev) => ({
                    ...prev,
                    executionMode: event.target.value as AutomationInstanceFormState["executionMode"],
                  }))
                }
              >
                <option value="worktree">worktree</option>
                <option value="local">local</option>
              </select>
            </Field>
            <Field label="Schedule">
              <select
                className="w-full rounded-lg border border-slate-300 px-2.5 py-2 text-sm"
                value={automationInstanceForm.scheduleType}
                onChange={(event) =>
                  setAutomationInstanceForm((prev) => ({
                    ...prev,
                    scheduleType: event.target.value as AutomationInstanceFormState["scheduleType"],
                  }))
                }
              >
                <option value="manual">manual</option>
                <option value="daily">daily</option>
                <option value="interval">interval</option>
              </select>
            </Field>
          </div>
          {automationInstanceForm.scheduleType === "daily" ? (
            <>
              <Field label="Time">
                <input
                  type="time"
                  className="w-full rounded-lg border border-slate-300 px-2.5 py-2 text-sm"
                  value={automationInstanceForm.scheduleTime}
                  onChange={(event) =>
                    setAutomationInstanceForm((prev) => ({ ...prev, scheduleTime: event.target.value }))
                  }
                />
              </Field>
              <Field label="Days">
                <WeekdayToggleGroup
                  value={automationInstanceForm.weekdays}
                  onToggle={(day) =>
                    setAutomationInstanceForm((prev) => ({
                      ...prev,
                      weekdays: prev.weekdays.includes(day)
                        ? prev.weekdays.filter((item) => item !== day)
                        : [...prev.weekdays, day],
                    }))
                  }
                />
              </Field>
            </>
          ) : null}
          {automationInstanceForm.scheduleType === "interval" ? (
            <Field label="Interval Minutes">
              <input
                type="number"
                min={5}
                step={5}
                className="w-full rounded-lg border border-slate-300 px-2.5 py-2 text-sm"
                value={automationInstanceForm.intervalMinutes}
                onChange={(event) =>
                  setAutomationInstanceForm((prev) => ({
                    ...prev,
                    intervalMinutes: Number(event.target.value || 60),
                  }))
                }
              />
            </Field>
          ) : null}
          <label className="mb-2 flex items-center gap-1.5 text-xs text-slate-700">
            <input
              type="checkbox"
              checked={automationInstanceForm.isActive}
              onChange={(event) =>
                setAutomationInstanceForm((prev) => ({ ...prev, isActive: event.target.checked }))
              }
            />
            Active
          </label>
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              className="rounded-lg bg-slate-900 px-3 py-2 text-xs font-semibold text-white hover:bg-slate-800"
              type="submit"
            >
              Save Instance
            </button>
            {automationInstanceForm.id ? (
              <button
                className="rounded-lg border border-rose-300 bg-rose-50 px-3 py-2 text-xs font-semibold text-rose-700 hover:bg-rose-100"
                type="button"
                onClick={() => void onDeleteAutomationInstance()}
              >
                Delete
              </button>
            ) : null}
            <button
              className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50"
              type="button"
              onClick={() => setAutomationInstanceModalOpen(false)}
            >
              Cancel
            </button>
          </div>
        </form>
      </Modal>

      {loading ? (
        <div className="pointer-events-none fixed inset-0 z-40 flex items-center justify-center bg-slate-900/20 backdrop-blur-[1px]">
          <div className="rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 shadow-lg">
            Loading...
          </div>
        </div>
      ) : null}
    </main>
  );
}

function Panel(props: {
  title: string;
  subtitle: string;
  children: React.ReactNode;
  actionLabel?: string;
  onAction?: () => void;
}) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div>
          <h2 className="text-base font-semibold text-slate-900">{props.title}</h2>
          <p className="text-xs text-slate-500">{props.subtitle}</p>
        </div>
        {props.actionLabel && props.onAction ? (
          <button
            type="button"
            onClick={props.onAction}
            className="rounded border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 shadow-sm hover:bg-slate-50"
          >
            {props.actionLabel}
          </button>
        ) : null}
      </div>
      {props.children}
    </section>
  );
}

function Modal(props: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  size?: "sm" | "md" | "lg" | "xl";
}) {
  const sizeClass =
    props.size === "xl"
      ? "max-w-2xl"
      : props.size === "lg"
        ? "max-w-xl"
        : props.size === "sm"
          ? "max-w-sm"
          : "max-w-md";
  if (!props.open) return null;
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="modal-title"
    >
      <div
        className="absolute inset-0 bg-slate-900/60 backdrop-blur-sm"
        onClick={props.onClose}
        aria-hidden="true"
      />
      <div
        className={`relative flex max-h-[90vh] w-full ${sizeClass} flex-col overflow-hidden rounded-lg border border-slate-200 bg-white shadow-xl`}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex shrink-0 items-center justify-between border-b border-slate-200 px-4 py-3">
          <h2 id="modal-title" className="text-base font-semibold text-slate-900">
            {props.title}
          </h2>
          <button
            type="button"
            onClick={props.onClose}
            className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
            aria-label="Close"
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-4">{props.children}</div>
      </div>
    </div>
  );
}

function TableWrap(props: { children: React.ReactNode }) {
  return (
    <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
      <div className="max-h-[320px] overflow-auto">{props.children}</div>
    </div>
  );
}

function Field(props: { label: string; children: React.ReactNode }) {
  return (
    <div className="mb-1.5">
      <label className="mb-0.5 block text-[11px] font-medium uppercase tracking-wide text-slate-500">
        {props.label}
      </label>
      {props.children}
    </div>
  );
}

function MetricCard(props: { label: string; value: number }) {
  return (
    <article className="rounded-lg border border-slate-200 bg-white px-2 py-1.5 shadow-sm">
      <p className="text-[11px] font-medium uppercase tracking-wide text-slate-500">{props.label}</p>
      <p className="mt-0.5 text-2xl font-semibold tabular-nums text-slate-900">
        {new Intl.NumberFormat().format(props.value)}
      </p>
    </article>
  );
}

function PluginAvatar(props: { iconDataUrl?: string; fallback: string; size?: "sm" | "md" }) {
  const size = props.size === "md" ? "h-8 w-8 text-sm" : "h-6 w-6 text-[11px]";
  const fallback = String(props.fallback || "").trim().charAt(0).toUpperCase() || "?";
  if (props.iconDataUrl) {
    return (
      <div className={`${size} overflow-hidden rounded-md border border-slate-200 bg-white`}>
        <img src={props.iconDataUrl} alt="" className="h-full w-full object-cover" />
      </div>
    );
  }
  return (
    <div
      className={`${size} flex items-center justify-center rounded-md border border-slate-300 bg-slate-100 font-semibold text-slate-700`}
    >
      {fallback}
    </div>
  );
}

function CatalogCard(props: {
  title: string;
  subtitle: string;
  meta: string;
  active?: boolean;
  actionLabel: string;
  onAction: () => void;
  onSelect?: () => void;
}) {
  return (
    <article className="rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <button type="button" className="min-w-0 flex-1 text-left" onClick={props.onSelect || props.onAction}>
          <div className="truncate text-sm font-semibold text-slate-900">{props.title}</div>
          <div className="mt-1 text-xs text-slate-600">{props.subtitle}</div>
          <div className="mt-2 font-mono text-[11px] text-slate-500">{props.meta}</div>
        </button>
        <div className="flex flex-col items-end gap-2">
          {props.active ? (
            <span className="rounded-full border border-emerald-300 bg-emerald-50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-emerald-700">
              active
            </span>
          ) : null}
          <button
            type="button"
            onClick={props.onAction}
            className="rounded-lg border border-sky-300 bg-sky-50 px-2.5 py-1.5 text-[11px] font-semibold text-sky-700 hover:bg-sky-100"
          >
            {props.actionLabel}
          </button>
        </div>
      </div>
    </article>
  );
}

function EmptyStateCard(props: { text: string }) {
  return (
    <div className="rounded-xl border border-dashed border-slate-300 bg-white px-4 py-5 text-sm text-slate-500">
      {props.text}
    </div>
  );
}

function WeekdayToggleGroup(props: { value: string[]; onToggle: (day: string) => void }) {
  const days = [
    ["mo", "Mo"],
    ["tu", "Tu"],
    ["we", "We"],
    ["th", "Th"],
    ["fr", "Fr"],
    ["sa", "Sa"],
    ["su", "Su"],
  ] as const;

  return (
    <div className="flex flex-wrap gap-1.5">
      {days.map(([key, label]) => {
        const active = props.value.includes(key);
        return (
          <button
            key={key}
            type="button"
            onClick={() => props.onToggle(key)}
            className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${
              active ? "bg-slate-900 text-white" : "border border-slate-300 bg-white text-slate-600"
            }`}
          >
            {label}
          </button>
        );
      })}
    </div>
  );
}

function SecretBadge(props: { label: string }) {
  return (
    <span className="rounded-full border border-emerald-300 bg-emerald-50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-emerald-700">
      {props.label}
    </span>
  );
}
