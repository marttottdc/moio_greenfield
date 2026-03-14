// @ts-nocheck
import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

import {
  bootstrap,
  clearPlatformAuthSession,
  deleteGlobalSkill,
  deleteIntegration,
  deletePlan,
  deleteTenant,
  deleteUser,
  logout,
  savePlatformPluginApproval,
  PlatformAdminApiError,
  listPlugins,
  uploadPluginBundle,
  saveGlobalSkill,
  saveIntegration,
  saveNotificationSettings,
  savePlan,
  savePlatformConfiguration,
  saveTenant,
  saveTenantIntegration,
  saveUser,
  updateTenant,
} from "../lib/platformAdminApi";
import { showBrowserNotification } from "../lib/pwa";
import type {
  BootstrapPayload,
  CurrentUser,
  FlashTone,
  IntegrationDefinition,
  NotificationSettings,
  Plan as PlanType,
  PlatformConfiguration,
  PlatformUser,
  PluginAdminState,
  PluginRegistryEntry,
  PluginSyncState,
  SkillDefinition,
  Tenant,
  TenantIntegration,
  TenantPluginAssignment,
  TenantPluginBinding,
  TenantMembership,
} from "../types";

type TenantFormState = {
  id: string | null;
  name: string;
  slug: string;
  schemaName: string;
  primaryDomain: string;
  isActive: boolean;
  plan: string;
  moduleEnablements: {
    crm: boolean;
    flowsDatalab: boolean;
    chatbot: boolean;
    agentConsole: boolean;
  };
};

const ENTITLEMENT_FEATURE_KEYS = [
  "crm",
  "crm_contacts_read",
  "crm_contacts_write",
  "campaigns",
  "campaigns_read",
  "campaigns_send",
  "flows",
  "flows_read",
  "flows_run",
  "flows_edit",
  "chatbot",
  "datalab",
  "settings_integrations_manage",
  "users_manage",
] as const;

type EntitlementFeatures = Record<(typeof ENTITLEMENT_FEATURE_KEYS)[number], boolean>;
type ModuleEnablements = { crm: boolean; flowsDatalab: boolean; chatbot: boolean; agentConsole: boolean };

const DEFAULT_ENTITLEMENT_FEATURES: EntitlementFeatures = {
  crm: true,
  crm_contacts_read: true,
  crm_contacts_write: true,
  campaigns: false,
  campaigns_read: false,
  campaigns_send: false,
  flows: false,
  flows_read: false,
  flows_run: false,
  flows_edit: false,
  chatbot: false,
  datalab: false,
  settings_integrations_manage: false,
  users_manage: false,
};

const DEFAULT_MODULE_ENABLEMENTS: ModuleEnablements = {
  crm: true,
  flowsDatalab: false,
  chatbot: false,
  agentConsole: false,
};

function parseEntitlementPolicyFromPayload(policy: Record<string, unknown> | undefined): {
  features: EntitlementFeatures;
  limits: { seats: number; agents: number; flows: number };
  moduleEnablements: ModuleEnablements;
} {
  const raw = policy || {};
  const features = (raw.features as Record<string, boolean>) || {};
  const limits = (raw.limits as Record<string, number>) || {};
  const ui = (raw.ui as Record<string, unknown>) || {};
  const moduleEnablements = (ui.module_enablements as Record<string, boolean>) || {};
  return {
    features: { ...DEFAULT_ENTITLEMENT_FEATURES, ...Object.fromEntries(ENTITLEMENT_FEATURE_KEYS.map((k) => [k, !!features[k]])) } as EntitlementFeatures,
    limits: {
      seats: typeof limits.seats === "number" ? limits.seats : 5,
      agents: typeof limits.agents === "number" ? limits.agents : 0,
      flows: typeof limits.flows === "number" ? limits.flows : 0,
    },
    moduleEnablements: {
      crm: true,
      flowsDatalab: !!moduleEnablements.flowsDatalab,
      chatbot: !!moduleEnablements.chatbot,
      agentConsole: !!moduleEnablements.agentConsole,
    },
  };
}

function buildEntitlementPolicyPayload(form: {
  features: EntitlementFeatures;
  limits: { seats: number; agents: number; flows: number };
  moduleEnablements: ModuleEnablements;
}): Record<string, unknown> {
  return {
    features: form.features,
    limits: form.limits,
    ui: { module_enablements: form.moduleEnablements },
  };
}

type PlanFormState = {
  id: string | null;
  key: string;
  name: string;
  displayOrder: number;
  isActive: boolean;
  isSelfProvisionDefault: boolean;
  pricingCurrency: string;
  entitlementFeatures: EntitlementFeatures;
  entitlementLimits: { seats: number; agents: number; flows: number };
  entitlementModuleEnablements: ModuleEnablements;
};

type UserFormState = {
  id: number | null;
  email: string;
  displayName: string;
  password: string;
  isPlatformAdmin: boolean;
  isActive: boolean;
  tenantMemberships: TenantMembership[];
};

type IntegrationFormState = {
  key: string;
  name: string;
  category: string;
  baseUrl: string;
  openapiUrl: string;
  defaultAuthType: string;
  authScope: "global" | "tenant" | "user";
  authConfigSchemaText: string;
  globalAuthConfigText: string;
  assistantDocsMarkdown: string;
  defaultHeadersText: string;
  isActive: boolean;
};

type SkillFormState = {
  key: string;
  name: string;
  description: string;
  bodyMarkdown: string;
  isActive: boolean;
};

type NotificationFormState = NotificationSettings;

type PlatformConfigFormState = PlatformConfiguration;

type NavSection =
  | "overview"
  | "tenants"
  | "plans"
  | "users"
  | "integrations"
  | "plugins"
  | "skills"
  | "enablement"
  | "configuration"
  | "security";

type SectionProps = {
  title: string;
  subtitle: string;
  actionLabel?: string;
  onAction?: () => void;
  fillHeight?: boolean;
  children: React.ReactNode;
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
    key: "tenants",
    label: "Tenants",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4" stroke="currentColor" strokeWidth="1.8">
        <path d="M4 20h16M7 20V8l5-4 5 4v12M10 12h4M10 16h4" />
      </svg>
    ),
  },
  {
    key: "plans",
    label: "Plans",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4" stroke="currentColor" strokeWidth="1.8">
        <path d="M3 9h18M9 21V9M3 21l6-12 6 12 6-12" />
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
    key: "integrations",
    label: "Integrations",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4" stroke="currentColor" strokeWidth="1.8">
        <path d="M15 7h4a2 2 0 1 1 0 4h-4m-6 2H5a2 2 0 1 0 0 4h4m-3-6h12m-12 2h12" />
      </svg>
    ),
  },
  {
    key: "skills",
    label: "Global Skills",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4" stroke="currentColor" strokeWidth="1.8">
        <path d="M7 5h10M7 9h10M7 13h7M5 3h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z" />
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
    key: "enablement",
    label: "Enablement",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4" stroke="currentColor" strokeWidth="1.8">
        <path d="M8 12h8M8 8h8M8 16h5M5 4h14a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Z" />
      </svg>
    ),
  },
  {
    key: "configuration",
    label: "Configuration",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4" stroke="currentColor" strokeWidth="1.8">
        <path d="M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z" />
        <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1Z" />
      </svg>
    ),
  },
  {
    key: "security",
    label: "Security",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4" stroke="currentColor" strokeWidth="1.8">
        <path d="m12 3 8 4v6c0 5-3.5 8.5-8 10-4.5-1.5-8-5-8-10V7l8-4Zm0 7v4m0 4h.01" />
      </svg>
    ),
  },
];

const DEFAULT_TENANT_FORM: TenantFormState = {
  id: null,
  name: "",
  slug: "",
  schemaName: "",
  primaryDomain: "",
  isActive: true,
  plan: "",
  moduleEnablements: {
    crm: true,
    flowsDatalab: false,
    chatbot: false,
    agentConsole: false,
  },
};

const DEFAULT_PLAN_FORM: PlanFormState = {
  id: null,
  key: "",
  name: "",
  displayOrder: 0,
  isActive: true,
  isSelfProvisionDefault: false,
  pricingCurrency: "USD",
  entitlementFeatures: { ...DEFAULT_ENTITLEMENT_FEATURES },
  entitlementLimits: { seats: 5, agents: 0, flows: 0 },
  entitlementModuleEnablements: { ...DEFAULT_MODULE_ENABLEMENTS },
};

const DEFAULT_USER_FORM: UserFormState = {
  id: null,
  email: "",
  displayName: "",
  password: "",
  isPlatformAdmin: false,
  isActive: true,
  tenantMemberships: [],
};

const DEFAULT_INTEGRATION_FORM: IntegrationFormState = {
  key: "",
  name: "",
  category: "",
  baseUrl: "",
  openapiUrl: "",
  defaultAuthType: "bearer",
  authScope: "tenant",
  authConfigSchemaText: "{}",
  globalAuthConfigText: "{}",
  assistantDocsMarkdown: "",
  defaultHeadersText: "{}",
  isActive: true,
};

const DEFAULT_SKILL_FORM: SkillFormState = {
  key: "",
  name: "",
  description: "",
  bodyMarkdown: "",
  isActive: true,
};

const DEFAULT_NOTIFICATION_FORM: NotificationFormState = {
  title: "Moio",
  iconUrl: "/pwa-icon.svg",
  badgeUrl: "/pwa-icon.svg",
  requireInteraction: false,
  renotify: false,
  silent: false,
  testTitle: "Moio test notification",
  testBody: "Notifications are configured for this browser.",
};

const DEFAULT_PLATFORM_CONFIG_FORM: PlatformConfigFormState = {
  siteName: "",
  company: "",
  myUrl: "",
  logoUrl: "",
  faviconUrl: "",
  whatsappWebhookToken: "",
  whatsappWebhookRedirect: "",
  fbSystemToken: "",
  fbMoioBotAppId: "",
  fbMoioBusinessManagerId: "",
  fbMoioBotAppSecret: "",
  fbMoioBotConfigurationId: "",
  googleOauthClientId: "",
  googleOauthClientSecret: "",
  microsoftOauthClientId: "",
  microsoftOauthClientSecret: "",
  shopifyClientId: "",
  shopifyClientSecret: "",
};

const DEFAULT_PLUGIN_SYNC: PluginSyncState = {
  syncedCount: 0,
  invalid: [],
};

export default function PlatformAdminApp() {
  const [activeSection, setActiveSection] = useState<NavSection>("overview");
  const [tenantsEnabled, setTenantsEnabled] = useState(false);
  const [publicSchema, setPublicSchema] = useState("public");
  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null);
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [plans, setPlans] = useState<PlanType[]>([]);
  const [users, setUsers] = useState<PlatformUser[]>([]);
  const [integrations, setIntegrations] = useState<IntegrationDefinition[]>([]);
  const [globalSkills, setGlobalSkills] = useState<SkillDefinition[]>([]);
  const [tenantIntegrations, setTenantIntegrations] = useState<TenantIntegration[]>([]);
  const [pluginSync, setPluginSync] = useState<PluginSyncState>(DEFAULT_PLUGIN_SYNC);
  const [plugins, setPlugins] = useState<PluginRegistryEntry[]>([]);
  const [tenantPlugins, setTenantPlugins] = useState<TenantPluginBinding[]>([]);
  const [tenantPluginAssignments, setTenantPluginAssignments] = useState<TenantPluginAssignment[]>([]);
  const [selectedTenantSlug, setSelectedTenantSlug] = useState("");
  const [selectedPluginId, setSelectedPluginId] = useState("");
  const [pluginUploadFile, setPluginUploadFile] = useState<File | null>(null);
  const [pluginUploadBusy, setPluginUploadBusy] = useState(false);
  const pluginUploadInputRef = useRef<HTMLInputElement | null>(null);

  const [tenantForm, setTenantForm] = useState<TenantFormState>(DEFAULT_TENANT_FORM);
  const [planForm, setPlanForm] = useState<PlanFormState>(DEFAULT_PLAN_FORM);
  const [userForm, setUserForm] = useState<UserFormState>(DEFAULT_USER_FORM);
  const [integrationForm, setIntegrationForm] = useState<IntegrationFormState>(DEFAULT_INTEGRATION_FORM);
  const [skillForm, setSkillForm] = useState<SkillFormState>(DEFAULT_SKILL_FORM);
  const [notificationForm, setNotificationForm] = useState<NotificationFormState>(DEFAULT_NOTIFICATION_FORM);
  const [configForm, setConfigForm] = useState<PlatformConfigFormState>(DEFAULT_PLATFORM_CONFIG_FORM);

  const [tenantModalOpen, setTenantModalOpen] = useState(false);
  const [planModalOpen, setPlanModalOpen] = useState(false);
  const [userModalOpen, setUserModalOpen] = useState(false);
  const [integrationModalOpen, setIntegrationModalOpen] = useState(false);
  const [skillModalOpen, setSkillModalOpen] = useState(false);
  const [userFilterTenantSlug, setUserFilterTenantSlug] = useState("");

  const [loading, setLoading] = useState(true);
  const [flashText, setFlashText] = useState("");
  const [flashTone, setFlashTone] = useState<FlashTone>("info");

  const enabledBindingCount = useMemo(
    () => tenantIntegrations.filter((row) => row.isEnabled).length,
    [tenantIntegrations]
  );
  const enabledPluginBindingCount = useMemo(
    () => tenantPlugins.filter((row) => row.isEnabled).length,
    [tenantPlugins]
  );
  const selectedPlugin = useMemo(
    () => plugins.find((row) => row.pluginId === selectedPluginId) || null,
    [plugins, selectedPluginId]
  );

  useEffect(() => {
    void reloadAll(false);
  }, []);

  useEffect(() => {
    if (!selectedTenantSlug && tenants.length > 0) {
      setSelectedTenantSlug(tenants[0].slug);
    }
  }, [selectedTenantSlug, tenants]);

  useEffect(() => {
    if (plugins.length === 0) {
      if (selectedPluginId) setSelectedPluginId("");
      return;
    }
    if (!plugins.some((row) => row.pluginId === selectedPluginId)) {
      setSelectedPluginId(plugins[0].pluginId);
    }
  }, [plugins, selectedPluginId]);

  function setFlash(message: string, tone: FlashTone = "info") {
    setFlashText(message);
    setFlashTone(tone);
  }

  function applyPluginAdminState(payload: PluginAdminState) {
    setPluginSync(payload.sync || DEFAULT_PLUGIN_SYNC);
    setPlugins(Array.isArray(payload.plugins) ? payload.plugins : []);
    setTenantPlugins(Array.isArray(payload.tenantPlugins) ? payload.tenantPlugins : []);
    setTenantPluginAssignments(
      Array.isArray(payload.tenantPluginAssignments) ? payload.tenantPluginAssignments : []
    );
  }

  function applyPayload(payload: BootstrapPayload) {
    setTenantsEnabled(Boolean(payload.tenantsEnabled));
    setPublicSchema(payload.publicSchema || "public");
    setCurrentUser(payload.currentUser ?? null);
    setTenants(Array.isArray(payload.tenants) ? payload.tenants : []);
    setPlans(Array.isArray(payload.plans) ? payload.plans : []);
    setUsers(Array.isArray(payload.users) ? payload.users : []);
    setIntegrations(Array.isArray(payload.integrations) ? payload.integrations : []);
    setGlobalSkills(Array.isArray(payload.globalSkills) ? payload.globalSkills : []);
    setTenantIntegrations(Array.isArray(payload.tenantIntegrations) ? payload.tenantIntegrations : []);
    setPluginSync(payload.pluginSync || DEFAULT_PLUGIN_SYNC);
    setPlugins(Array.isArray(payload.plugins) ? payload.plugins : []);
    setTenantPlugins(Array.isArray(payload.tenantPlugins) ? payload.tenantPlugins : []);
    setTenantPluginAssignments(
      Array.isArray(payload.tenantPluginAssignments) ? payload.tenantPluginAssignments : []
    );
    setConfigForm(payload.platformConfiguration ?? DEFAULT_PLATFORM_CONFIG_FORM);
    setNotificationForm(payload.notificationSettings ?? DEFAULT_NOTIFICATION_FORM);
  }

  async function reloadAll(showFlash = true) {
    setLoading(true);
    try {
      const payload = await bootstrap();
      applyPayload(payload);
      if (showFlash) setFlash("Platform state refreshed.", "ok");
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      const apiErr = error as PlatformAdminApiError;
      if (apiErr?.status === 401 || apiErr?.code === "auth_required") {
        clearPlatformAuthSession();
        setCurrentUser(null);
        setFlash("Session expired. Sign in again at the Access Hub.", "error");
      } else if (apiErr?.status === 403) {
        setCurrentUser(null);
        setFlash("You don’t have access to Platform Admin. Use the Access Hub to switch destination.", "error");
      } else {
        setFlash(message, "error");
      }
    } finally {
      setLoading(false);
    }
  }

  async function onSaveConfiguration(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    try {
      const payload = await savePlatformConfiguration({
        siteName: configForm.siteName,
        company: configForm.company,
        myUrl: configForm.myUrl,
        whatsappWebhookToken: configForm.whatsappWebhookToken,
        whatsappWebhookRedirect: configForm.whatsappWebhookRedirect,
        fbSystemToken: configForm.fbSystemToken,
        fbMoioBotAppId: configForm.fbMoioBotAppId,
        fbMoioBusinessManagerId: configForm.fbMoioBusinessManagerId,
        fbMoioBotAppSecret: configForm.fbMoioBotAppSecret,
        fbMoioBotConfigurationId: configForm.fbMoioBotConfigurationId,
        googleOauthClientId: configForm.googleOauthClientId,
        googleOauthClientSecret: configForm.googleOauthClientSecret,
        microsoftOauthClientId: configForm.microsoftOauthClientId,
        microsoftOauthClientSecret: configForm.microsoftOauthClientSecret,
        shopifyClientId: configForm.shopifyClientId,
        shopifyClientSecret: configForm.shopifyClientSecret,
      });
      applyPayload(payload);
      setFlash("Platform configuration saved.", "ok");
    } catch (error) {
      setFlash(error instanceof Error ? error.message : String(error), "error");
    } finally {
      setLoading(false);
    }
  }

  async function onSaveNotifications(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    try {
      const payload = await saveNotificationSettings({ settings: notificationForm });
      applyPayload(payload);
      setFlash("Notification settings saved.", "ok");
    } catch (error) {
      setFlash(error instanceof Error ? error.message : String(error), "error");
    } finally {
      setLoading(false);
    }
  }

  async function onRefreshPlugins() {
    try {
      const payload = await listPlugins();
      applyPluginAdminState(payload);
      setFlash("Plugin registry refreshed.", "ok");
    } catch (error) {
      setFlash(error instanceof Error ? error.message : String(error), "error");
    }
  }

  async function onUploadPluginBundle() {
    if (!pluginUploadFile) {
      setFlash("Choose a plugin zip bundle first.", "error");
      return;
    }
    setPluginUploadBusy(true);
    try {
      const payload = await uploadPluginBundle({
        file: pluginUploadFile,
      });
      applyPluginAdminState(payload);
      setPluginUploadFile(null);
      if (pluginUploadInputRef.current) {
        pluginUploadInputRef.current.value = "";
      }
      setFlash(`Plugin bundle "${pluginUploadFile.name}" uploaded and validated.`, "ok");
    } catch (error) {
      setFlash(error instanceof Error ? error.message : String(error), "error");
    } finally {
      setPluginUploadBusy(false);
    }
  }

  async function onTestNotification() {
    const ok = await showBrowserNotification(
      notificationForm.testTitle || notificationForm.title || "Moio",
      notificationForm.testBody || "Notifications are configured for this browser.",
      "platform-admin-test",
      "/desktop-agent-console/platform-admin/",
      {
        icon: notificationForm.iconUrl || "/pwa-icon.svg",
        badge: notificationForm.badgeUrl || "/pwa-icon.svg",
        requireInteraction: notificationForm.requireInteraction,
        renotify: notificationForm.renotify,
        silent: notificationForm.silent,
      }
    );
    setFlash(ok ? "Test notification sent to this browser." : "Browser notification was blocked or unavailable.", ok ? "ok" : "error");
  }

  function newTenantForm() {
    setTenantForm({
      ...DEFAULT_TENANT_FORM,
      plan: plans[0]?.key || "",
    });
    setTenantModalOpen(true);
  }

  function editTenantForm(row: Tenant) {
    const enablements = row.moduleEnablements || DEFAULT_TENANT_FORM.moduleEnablements;
    setTenantForm({
      id: row.id,
      name: row.name,
      slug: row.slug,
      schemaName: row.schemaName,
      primaryDomain: row.primaryDomain,
      isActive: row.isActive,
      plan: row.plan || "",
      moduleEnablements: {
        crm: true,
        flowsDatalab: Boolean(enablements.flowsDatalab),
        chatbot: Boolean(enablements.chatbot),
        agentConsole: Boolean(enablements.agentConsole),
      },
    });
    setSelectedTenantSlug(row.slug);
    setTenantModalOpen(true);
  }

  function newPlanForm() {
    setPlanForm(DEFAULT_PLAN_FORM);
    setPlanModalOpen(true);
  }

  function editPlanForm(row: PlanType) {
    const pricing = (row.pricingPolicy || {}) as Record<string, unknown>;
    const entitlement = parseEntitlementPolicyFromPayload(row.entitlementPolicy as Record<string, unknown> | undefined);
    setPlanForm({
      id: row.id,
      key: row.key,
      name: row.name,
      displayOrder: row.displayOrder ?? 0,
      isActive: row.isActive ?? true,
      isSelfProvisionDefault: row.isSelfProvisionDefault ?? false,
      pricingCurrency: typeof pricing.currency === "string" ? pricing.currency : "USD",
      entitlementFeatures: entitlement.features,
      entitlementLimits: entitlement.limits,
      entitlementModuleEnablements: entitlement.moduleEnablements,
    });
    setPlanModalOpen(true);
  }

  async function onSubmitPlan(event: FormEvent) {
    event.preventDefault();
    const pricingPolicy: Record<string, unknown> = planForm.pricingCurrency ? { currency: planForm.pricingCurrency } : {};
    const entitlementPolicy = buildEntitlementPolicyPayload({
      features: planForm.entitlementFeatures,
      limits: planForm.entitlementLimits,
      moduleEnablements: planForm.entitlementModuleEnablements,
    });
    try {
      await savePlan({
        id: planForm.id,
        key: planForm.key,
        name: planForm.name,
        displayOrder: planForm.displayOrder,
        isActive: planForm.isActive,
        isSelfProvisionDefault: planForm.isSelfProvisionDefault,
        pricingPolicy,
        entitlementPolicy,
      });
      const payload = await bootstrap();
      applyPayload(payload);
      setPlanModalOpen(false);
      setFlash("Plan saved.", "ok");
    } catch (error) {
      setFlash(error instanceof Error ? error.message : String(error), "error");
    }
  }

  async function onDeletePlan() {
    if (!planForm.id) {
      setFlash("Select a plan first.", "error");
      return;
    }
    if (!window.confirm(`Delete plan "${planForm.name || planForm.key}"? Tenants using this plan will keep the key but it will no longer be selectable.`)) return;
    try {
      await deletePlan({ id: planForm.id });
      const payload = await bootstrap();
      applyPayload(payload);
      setPlanForm(DEFAULT_PLAN_FORM);
      setPlanModalOpen(false);
      setFlash("Plan deleted.", "ok");
    } catch (error) {
      setFlash(error instanceof Error ? error.message : String(error), "error");
    }
  }

  function newUserForm() {
    setUserForm(DEFAULT_USER_FORM);
    setUserModalOpen(true);
  }

  function editUserForm(row: PlatformUser) {
    setUserForm({
      id: row.id,
      email: row.email,
      displayName: row.displayName,
      password: "",
      isPlatformAdmin: row.isPlatformAdmin,
      isActive: row.isActive,
      tenantMemberships: row.tenantMemberships,
    });
    setUserModalOpen(true);
  }

  function newIntegrationForm() {
    setIntegrationForm(DEFAULT_INTEGRATION_FORM);
    setIntegrationModalOpen(true);
  }

  function editIntegrationForm(row: IntegrationDefinition) {
    setIntegrationForm({
      key: row.key,
      name: row.name,
      category: row.category,
      baseUrl: row.baseUrl,
      openapiUrl: row.openapiUrl,
      defaultAuthType: row.defaultAuthType || "bearer",
      authScope: (row.authScope || "tenant") as "global" | "tenant" | "user",
      authConfigSchemaText: JSON.stringify(row.authConfigSchema || {}, null, 2),
      globalAuthConfigText: JSON.stringify(row.globalAuthConfig || {}, null, 2),
      assistantDocsMarkdown: row.assistantDocsMarkdown || "",
      defaultHeadersText: JSON.stringify(row.defaultHeaders || {}, null, 2),
      isActive: row.isActive,
    });
    setIntegrationModalOpen(true);
  }

  function newSkillForm() {
    setSkillForm(DEFAULT_SKILL_FORM);
    setSkillModalOpen(true);
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

  const usersFilteredByTenant =
    userFilterTenantSlug === ""
      ? users
      : users.filter((u) => u.tenantMemberships.some((m) => m.tenantSlug === userFilterTenantSlug));

  function getTenantIntegration(tenantSlug: string, integrationKey: string) {
    return (
      tenantIntegrations.find(
        (row) =>
          row.tenantSlug.toLowerCase() === tenantSlug.toLowerCase() &&
          row.integrationKey.toLowerCase() === integrationKey.toLowerCase()
      ) || null
    );
  }

  function upsertUserMembership(tenantSlug: string, updates: Partial<TenantMembership>) {
    setUserForm((prev) => {
      const current = prev.tenantMemberships.find((row) => row.tenantSlug === tenantSlug);
      const nextEntry: TenantMembership = {
        tenantSlug,
        role: current?.role || "member",
        isActive: current?.isActive ?? true,
        ...updates,
      };
      const next = prev.tenantMemberships.filter((row) => row.tenantSlug !== tenantSlug);
      next.push(nextEntry);
      next.sort((a, b) => a.tenantSlug.localeCompare(b.tenantSlug));
      return {
        ...prev,
        tenantMemberships: next,
      };
    });
  }

  function removeUserMembership(tenantSlug: string) {
    setUserForm((prev) => ({
      ...prev,
      tenantMemberships: prev.tenantMemberships.filter((row) => row.tenantSlug !== tenantSlug),
    }));
  }

  async function onSubmitTenant(event: FormEvent) {
    event.preventDefault();
    try {
      if (tenantForm.id) {
        const payload = await updateTenant({
          id: tenantForm.id,
          plan: tenantForm.plan,
          name: tenantForm.name,
          isActive: tenantForm.isActive,
          moduleEnablements: tenantForm.moduleEnablements,
        });
        applyPayload(payload);
      } else {
        const payload = await saveTenant({
          name: tenantForm.name,
          slug: tenantForm.slug,
          schemaName: tenantForm.schemaName,
          primaryDomain: tenantForm.primaryDomain,
          isActive: tenantForm.isActive,
          plan: tenantForm.plan,
          moduleEnablements: tenantForm.moduleEnablements,
        });
        applyPayload(payload);
      }
      setTenantModalOpen(false);
      setFlash("Tenant saved.", "ok");
    } catch (error) {
      setFlash(error instanceof Error ? error.message : String(error), "error");
    }
  }

  async function onDeleteTenant() {
    if (!tenantForm.id) {
      setFlash("Select a tenant first.", "error");
      return;
    }
    if (!window.confirm(`Delete tenant \"${tenantForm.name || tenantForm.slug}\"?`)) return;
    try {
      const payload = await deleteTenant({ id: tenantForm.id });
      applyPayload(payload);
      setTenantForm(DEFAULT_TENANT_FORM);
      setTenantModalOpen(false);
      setFlash("Tenant deleted.", "ok");
    } catch (error) {
      setFlash(error instanceof Error ? error.message : String(error), "error");
    }
  }

  async function onSubmitUser(event: FormEvent) {
    event.preventDefault();
    try {
      const payload = await saveUser({
        id: userForm.id,
        email: userForm.email,
        displayName: userForm.displayName,
        password: userForm.password || undefined,
        isPlatformAdmin: userForm.isPlatformAdmin,
        isActive: userForm.isActive,
        tenantMemberships: userForm.tenantMemberships,
      });
      applyPayload(payload);
      setUserForm((prev) => ({ ...prev, password: "" }));
      setUserModalOpen(false);
      setFlash("User saved.", "ok");
    } catch (error) {
      setFlash(error instanceof Error ? error.message : String(error), "error");
    }
  }

  async function onDeleteUser() {
    if (!userForm.id) {
      setFlash("Select a user first.", "error");
      return;
    }
    if (!window.confirm(`Delete user \"${userForm.email}\"?`)) return;
    try {
      const payload = await deleteUser({ id: userForm.id });
      applyPayload(payload);
      setUserForm(DEFAULT_USER_FORM);
      setUserModalOpen(false);
      setFlash("User deleted.", "ok");
    } catch (error) {
      setFlash(error instanceof Error ? error.message : String(error), "error");
    }
  }

  async function onSubmitIntegration(event: FormEvent) {
    event.preventDefault();
    let parsedHeaders: Record<string, string> = {};
    let parsedSchema: Record<string, unknown> = {};
    let parsedGlobalAuth: Record<string, unknown> = {};
    try {
      const raw = integrationForm.defaultHeadersText.trim();
      parsedHeaders = raw ? JSON.parse(raw) : {};
      if (!parsedHeaders || typeof parsedHeaders !== "object" || Array.isArray(parsedHeaders)) {
        throw new Error("Default headers must be a JSON object.");
      }
    } catch (error) {
      setFlash(`Invalid headers JSON: ${error instanceof Error ? error.message : String(error)}`, "error");
      return;
    }
    try {
      const raw = integrationForm.authConfigSchemaText.trim();
      parsedSchema = raw ? JSON.parse(raw) : {};
      if (!parsedSchema || typeof parsedSchema !== "object" || Array.isArray(parsedSchema)) {
        throw new Error("Auth config schema must be a JSON object.");
      }
    } catch (error) {
      setFlash(`Invalid auth config schema JSON: ${error instanceof Error ? error.message : String(error)}`, "error");
      return;
    }
    try {
      const raw = integrationForm.globalAuthConfigText.trim();
      parsedGlobalAuth = raw ? JSON.parse(raw) : {};
      if (!parsedGlobalAuth || typeof parsedGlobalAuth !== "object" || Array.isArray(parsedGlobalAuth)) {
        throw new Error("Global auth config must be a JSON object.");
      }
    } catch (error) {
      setFlash(`Invalid global auth config JSON: ${error instanceof Error ? error.message : String(error)}`, "error");
      return;
    }

    try {
      const payload = await saveIntegration({
        key: integrationForm.key,
        name: integrationForm.name,
        category: integrationForm.category,
        baseUrl: integrationForm.baseUrl,
        openapiUrl: integrationForm.openapiUrl,
        defaultAuthType: integrationForm.defaultAuthType,
        authScope: integrationForm.authScope,
        authConfigSchema: parsedSchema,
        globalAuthConfig: integrationForm.authScope === "global" ? parsedGlobalAuth : {},
        assistantDocsMarkdown: integrationForm.assistantDocsMarkdown,
        defaultHeaders: parsedHeaders,
        isActive: integrationForm.isActive,
      });
      applyPayload(payload);
      setIntegrationModalOpen(false);
      setFlash("Integration saved.", "ok");
    } catch (error) {
      setFlash(error instanceof Error ? error.message : String(error), "error");
    }
  }

  async function onDeleteIntegration() {
    if (!integrationForm.key) {
      setFlash("Select an integration first.", "error");
      return;
    }
    if (!window.confirm(`Delete integration \"${integrationForm.key}\"?`)) return;
    try {
      const payload = await deleteIntegration({ key: integrationForm.key });
      applyPayload(payload);
      setIntegrationForm(DEFAULT_INTEGRATION_FORM);
      setIntegrationModalOpen(false);
      setFlash("Integration deleted.", "ok");
    } catch (error) {
      setFlash(error instanceof Error ? error.message : String(error), "error");
    }
  }

  async function onSubmitSkill(event: FormEvent) {
    event.preventDefault();
    if (!skillForm.key && !skillForm.name) {
      setFlash("Skill key or name is required.", "error");
      return;
    }
    if (!skillForm.bodyMarkdown.trim()) {
      setFlash("Skill markdown is required.", "error");
      return;
    }
    try {
      const payload = await saveGlobalSkill({
        key: skillForm.key,
        name: skillForm.name,
        description: skillForm.description,
        bodyMarkdown: skillForm.bodyMarkdown,
        isActive: skillForm.isActive,
      });
      applyPayload(payload);
      setSkillModalOpen(false);
      setFlash("Global skill saved.", "ok");
    } catch (error) {
      setFlash(error instanceof Error ? error.message : String(error), "error");
    }
  }

  async function onDeleteSkill() {
    if (!skillForm.key) {
      setFlash("Select a skill first.", "error");
      return;
    }
    if (!window.confirm(`Delete global skill \"${skillForm.key}\"?`)) return;
    try {
      const payload = await deleteGlobalSkill({ key: skillForm.key });
      applyPayload(payload);
      setSkillForm(DEFAULT_SKILL_FORM);
      setSkillModalOpen(false);
      setFlash("Global skill deleted.", "ok");
    } catch (error) {
      setFlash(error instanceof Error ? error.message : String(error), "error");
    }
  }

  async function onSaveTenantIntegration(
    tenantSlug: string,
    integrationKey: string,
    isEnabled: boolean,
    notes: string,
    assistantDocsOverride: string,
    tenantAuthConfig: Record<string, unknown>
  ) {
    try {
      const payload = await saveTenantIntegration({
        tenantSlug,
        integrationKey,
        isEnabled,
        notes,
        assistantDocsOverride,
        tenantAuthConfig,
      });
      applyPayload(payload);
      setFlash(`Saved binding ${tenantSlug} | ${integrationKey}.`, "ok");
    } catch (error) {
      setFlash(error instanceof Error ? error.message : String(error), "error");
    }
  }

  async function onSetPlatformPluginApproval(pluginId: string, isPlatformApproved: boolean) {
    try {
      await savePlatformPluginApproval({
        pluginId,
        isPlatformApproved,
      });
      const payload = await listPlugins();
      applyPluginAdminState(payload);
      setFlash(
        `Plugin ${pluginId} ${isPlatformApproved ? "approved" : "set to not approved"} at platform level.`,
        "ok"
      );
    } catch (error) {
      setFlash(error instanceof Error ? error.message : String(error), "error");
    }
  }

  async function onLogout() {
    try {
      await logout();
      setCurrentUser(null);
      setFlash("Logged out.", "ok");
    } catch (error) {
      setFlash(error instanceof Error ? error.message : String(error), "error");
    }
  }

  const flashClass =
    flashTone === "ok"
      ? "border-emerald-300 bg-emerald-50 text-emerald-700"
      : flashTone === "error"
      ? "border-rose-300 bg-rose-50 text-rose-700"
      : "border-slate-300 bg-white text-slate-700";

  const sectionVisible = (key: NavSection) => activeSection === key;

  if (!currentUser) {
    if (!loading && typeof window !== "undefined") {
      window.location.replace("/platform-router");
    }
  return (
    <main className="flex h-screen items-center justify-center bg-slate-100 p-4 text-slate-900 antialiased">
      <div className="w-full max-w-sm rounded-lg border border-slate-200 bg-white p-6 shadow-sm text-center">
        <div className="mb-3 flex justify-center">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-gradient-to-br from-cyan-400 via-blue-500 to-indigo-500 text-lg font-bold text-white">
            M
          </div>
        </div>
        <h1 className="text-lg font-semibold text-slate-900">Platform Admin</h1>
        {loading ? (
          <p className="mt-1.5 text-sm text-slate-600">Loading…</p>
        ) : (
          <>
            <p className="mt-1.5 text-sm text-slate-600">Redirecting…</p>
            <p className="mt-2 text-xs text-slate-500">Sign in or choose another destination.</p>
          </>
        )}
      </div>
    </main>
  );
  }

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
                <p className="text-[10px] uppercase tracking-wider text-slate-400">Platform Admin</p>
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
              <div>Schema: <span className="font-mono text-slate-200">{publicSchema}</span></div>
              <div>Tenants: <span className="font-mono text-slate-200">{tenantsEnabled ? "on" : "off"}</span></div>
            </div>
          </div>
        </aside>

        <section className="flex min-h-0 flex-col bg-slate-50">
          <header className="shrink-0 border-b border-slate-200 bg-white px-4 py-3 shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-baseline gap-3">
                <h1 className="text-xl font-semibold tracking-tight text-slate-900">Platform Admin</h1>
                <span className="text-sm text-slate-500">Superuser console</span>
              </div>
              <div className="flex items-center gap-2">
                {currentUser ? (
                  <span className="rounded border border-slate-200 bg-slate-50 px-2 py-1 font-mono text-xs text-slate-600">
                    {currentUser.email}
                  </span>
                ) : null}
                <button
                  type="button"
                  onClick={() => window.location.reload()}
                  className="rounded border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 shadow-sm transition hover:bg-slate-50"
                >
                  Refresh
                </button>
                {currentUser ? (
                  <button
                    type="button"
                    onClick={onLogout}
                    className="rounded border border-slate-700 bg-slate-800 px-2.5 py-1.5 text-xs font-medium text-white shadow-sm transition hover:bg-slate-700"
                  >
                    Logout
                  </button>
                ) : null}
              </div>
            </div>
            <div className={`mt-2 rounded border px-2.5 py-1.5 text-xs ${flashClass}`}>{flashText || "Ready."}</div>
          </header>

          <div className="flex min-h-0 flex-1 flex-col overflow-y-auto p-4">
            {(
              <>
                {activeSection === "overview" ? (
                  <section className="space-y-4">
                    <section className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
                      <MetricCard label="Tenants" value={tenants.length} />
                      <MetricCard label="Users" value={users.length} />
                      <MetricCard label="Integrations" value={integrations.length} />
                      <MetricCard label="Plugins" value={plugins.length} />
                      <MetricCard label="Global Skills" value={globalSkills.length} />
                      <MetricCard label="Enabled Bindings" value={enabledBindingCount + enabledPluginBindingCount} />
                    </section>
                    <p className="text-xs text-slate-500">KPIs and uptime reports will be added here.</p>
                  </section>
                ) : null}

                {activeSection !== "overview" ? (
                <div
                  className={
                    activeSection === "tenants" || activeSection === "plans" || activeSection === "users"
                      ? "flex min-h-0 flex-1 flex-col gap-3"
                      : "space-y-3"
                  }
                >
                  {sectionVisible("tenants") ? (
                    <SectionCard fillHeight title="Tenants" subtitle="Create isolated tenant environments and assign plans." actionLabel="New Tenant" onAction={newTenantForm}>
                      <TableWrap fillHeight>
                        <table className="min-w-full text-left text-xs">
                          <thead className="bg-slate-50 text-[11px] font-medium uppercase tracking-wide text-slate-500">
                            <tr>
                              <th className="px-2 py-1.5">Name</th>
                              <th className="px-2 py-1.5">Slug</th>
                              <th className="px-2 py-1.5">Plan</th>
                              <th className="px-2 py-1.5">Modules</th>
                              <th className="px-2 py-1.5">Schema</th>
                              <th className="px-2 py-1.5">Domain</th>
                              <th className="w-14 px-2 py-1.5" />
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-100">
                            {tenants.length === 0 ? (
                              <tr>
                                <td className="px-2 py-2 text-slate-500" colSpan={7}>
                                  No tenants yet.
                                </td>
                              </tr>
                            ) : (
                              tenants.map((row) => (
                                <tr key={row.id} className="hover:bg-slate-50/80">
                                  <td className="px-2 py-1.5 font-medium text-slate-900">{row.name || row.slug}</td>
                                  <td className="px-2 py-1.5 font-mono text-slate-600">{row.slug}</td>
                                  <td className="px-2 py-1.5 font-mono text-slate-600">{row.plan || "unassigned"}</td>
                                  <td className="px-2 py-1.5 text-[11px] text-slate-600">
                                    <div className="flex flex-wrap gap-1">
                                      <span className="rounded-full border border-emerald-200 bg-emerald-50 px-1.5 py-0.5 font-semibold text-emerald-700">
                                        CRM
                                      </span>
                                      {row.moduleEnablements?.flowsDatalab ? (
                                        <span className="rounded-full border border-sky-200 bg-sky-50 px-1.5 py-0.5 font-semibold text-sky-700">
                                          Flows+DataLab
                                        </span>
                                      ) : null}
                                      {row.moduleEnablements?.chatbot ? (
                                        <span className="rounded-full border border-violet-200 bg-violet-50 px-1.5 py-0.5 font-semibold text-violet-700">
                                          Chatbot
                                        </span>
                                      ) : null}
                                      {row.moduleEnablements?.agentConsole ? (
                                        <span className="rounded-full border border-amber-200 bg-amber-50 px-1.5 py-0.5 font-semibold text-amber-700">
                                          AgentConsole
                                        </span>
                                      ) : null}
                                    </div>
                                  </td>
                                  <td className="px-2 py-1.5 font-mono text-slate-600">{row.schemaName}</td>
                                  <td className="px-2 py-1.5 font-mono text-slate-600">{row.primaryDomain || "-"}</td>
                                  <td className="px-2 py-1.5">
                                    <button
                                      onClick={() => editTenantForm(row)}
                                      className="rounded border border-slate-300 bg-white px-2 py-1 text-[11px] font-medium text-slate-700 hover:bg-slate-50"
                                      type="button"
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
                    </SectionCard>
                  ) : null}

                  {sectionVisible("plans") ? (
                    <SectionCard fillHeight title="Plans" subtitle="Define subscription tiers for tenants. Assign plans when creating or editing tenants." actionLabel="New Plan" onAction={newPlanForm}>
                      <TableWrap>
                        <table className="min-w-full text-left text-xs">
                          <thead className="bg-slate-50 text-[11px] font-medium uppercase tracking-wide text-slate-500">
                            <tr>
                              <th className="px-2 py-1.5">Key</th>
                              <th className="px-2 py-1.5">Name</th>
                              <th className="px-2 py-1.5">Order</th>
                              <th className="px-2 py-1.5">Active</th>
                              <th className="px-2 py-1.5">Self-provision</th>
                              <th className="w-14 px-2 py-1.5" />
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-100">
                            {plans.length === 0 ? (
                              <tr>
                                <td className="px-2 py-2 text-slate-500" colSpan={6}>
                                  No plans yet. Add Free, Pro, Business or custom plans.
                                </td>
                              </tr>
                            ) : (
                              plans.map((row) => (
                                <tr key={row.id} className="hover:bg-slate-50/80">
                                  <td className="px-2 py-1.5 font-mono text-slate-600">{row.key}</td>
                                  <td className="px-2 py-1.5 font-medium text-slate-900">{row.name}</td>
                                  <td className="px-2 py-1.5 font-mono text-slate-600">{row.displayOrder ?? 0}</td>
                                  <td className="px-2 py-1.5 text-slate-600">{row.isActive ? "yes" : "no"}</td>
                                  <td className="px-2 py-1.5 text-slate-600">{row.isSelfProvisionDefault ? "yes" : "no"}</td>
                                  <td className="px-2 py-1.5">
                                    <button
                                      onClick={() => editPlanForm(row)}
                                      className="rounded border border-slate-300 bg-white px-2 py-1 text-[11px] font-medium text-slate-700 hover:bg-slate-50"
                                      type="button"
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
                    </SectionCard>
                  ) : null}

                  {sectionVisible("users") ? (
                    <SectionCard fillHeight title="Platform Users" subtitle="Manage platform admins and tenant memberships." actionLabel="New User" onAction={newUserForm}>
                      <div className="flex min-h-0 flex-1 flex-col">
                        <div className="shrink-0 mb-2 flex flex-wrap items-center gap-2">
                          <label className="text-xs font-medium text-slate-600">Filter by tenant:</label>
                          <select
                            className="rounded border border-slate-300 bg-white px-2 py-1.5 text-xs text-slate-700"
                            value={userFilterTenantSlug}
                            onChange={(e) => setUserFilterTenantSlug(e.target.value)}
                          >
                            <option value="">All tenants</option>
                            {tenants.map((t) => (
                              <option key={t.id} value={t.slug}>
                                {t.name || t.slug}
                              </option>
                            ))}
                          </select>
                        </div>
                        <TableWrap fillHeight>
                        <table className="min-w-full text-left text-xs">
                          <thead className="bg-slate-50 text-[11px] font-medium uppercase tracking-wide text-slate-500">
                            <tr>
                              <th className="px-2 py-1.5">Email</th>
                              <th className="px-2 py-1.5">Display</th>
                              <th className="px-2 py-1.5">Admin</th>
                              <th className="w-14 px-2 py-1.5" />
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-100">
                            {usersFilteredByTenant.length === 0 ? (
                              <tr>
                                <td className="px-2 py-2 text-slate-500" colSpan={4}>
                                  {userFilterTenantSlug ? "No users in this tenant." : "No users yet."}
                                </td>
                              </tr>
                            ) : (
                              usersFilteredByTenant.map((row) => (
                                <tr key={row.id} className="hover:bg-slate-50/80">
                                  <td className="px-2 py-1.5 font-mono text-slate-600">{row.email}</td>
                                  <td className="px-2 py-1.5 text-slate-600">{row.displayName || "-"}</td>
                                  <td className="px-2 py-1.5 text-slate-600">{row.isPlatformAdmin ? "yes" : "no"}</td>
                                  <td className="px-2 py-1.5">
                                    <button
                                      onClick={() => editUserForm(row)}
                                      className="rounded border border-slate-300 bg-white px-2 py-1 text-[11px] font-medium text-slate-700 hover:bg-slate-50"
                                      type="button"
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
                      </div>
                    </SectionCard>
                  ) : null}

                  {sectionVisible("integrations") ? (
                    <SectionCard title="Integration Catalog" subtitle="Define API adapters and assistant-facing documentation." actionLabel="New Integration" onAction={newIntegrationForm}>
                      <TableWrap>
                        <table className="min-w-full text-left text-xs">
                          <thead className="bg-slate-50 text-[11px] font-medium uppercase tracking-wide text-slate-500">
                            <tr>
                              <th className="px-2 py-1.5">Key</th>
                              <th className="px-2 py-1.5">Name</th>
                              <th className="px-2 py-1.5">Category</th>
                              <th className="px-2 py-1.5">Auth</th>
                              <th className="px-2 py-1.5">Scope</th>
                              <th className="w-14 px-2 py-1.5" />
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-100">
                            {integrations.length === 0 ? (
                              <tr>
                                <td className="px-2 py-2 text-slate-500" colSpan={6}>
                                  No integrations yet.
                                </td>
                              </tr>
                            ) : (
                              integrations.map((row) => (
                                <tr key={row.id} className="hover:bg-slate-50/80">
                                  <td className="px-2 py-1.5 font-mono text-slate-600">{row.key}</td>
                                  <td className="px-2 py-1.5 font-medium text-slate-900">{row.name}</td>
                                  <td className="px-2 py-1.5 text-slate-600">{row.category || "-"}</td>
                                  <td className="px-2 py-1.5 font-mono text-slate-600">{row.defaultAuthType}</td>
                                  <td className="px-2 py-1.5 font-mono text-slate-600">{row.authScope || "tenant"}</td>
                                  <td className="px-2 py-1.5">
                                    <button
                                      onClick={() => editIntegrationForm(row)}
                                      className="rounded border border-slate-300 bg-white px-2 py-1 text-[11px] font-medium text-slate-700 hover:bg-slate-50"
                                      type="button"
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
                    </SectionCard>
                  ) : null}

                  {sectionVisible("skills") ? (
                    <SectionCard
                      title="Global Skills"
                      subtitle="Define platform-wide skills reusable across all tenants and workspaces."
                      actionLabel="New Global Skill"
                      onAction={newSkillForm}
                    >
                      <TableWrap>
                        <table className="min-w-full text-left text-xs">
                          <thead className="bg-slate-50 text-[11px] font-medium uppercase tracking-wide text-slate-500">
                            <tr>
                              <th className="px-2 py-1.5">Key</th>
                              <th className="px-2 py-1.5">Name</th>
                              <th className="px-2 py-1.5">Scope</th>
                              <th className="px-2 py-1.5">Active</th>
                              <th className="w-14 px-2 py-1.5" />
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-100">
                            {globalSkills.length === 0 ? (
                              <tr>
                                <td className="px-2 py-2 text-slate-500" colSpan={5}>
                                  No global skills yet.
                                </td>
                              </tr>
                            ) : (
                              globalSkills.map((row) => (
                                <tr key={row.id} className="hover:bg-slate-50/80">
                                  <td className="px-2 py-1.5 font-mono text-slate-600">{row.key}</td>
                                  <td className="px-2 py-1.5 font-medium text-slate-900">{row.name || row.key}</td>
                                  <td className="px-2 py-1.5 text-slate-600">{row.scope || "global"}</td>
                                  <td className="px-2 py-1.5 text-slate-600">{row.isActive ? "yes" : "no"}</td>
                                  <td className="px-2 py-1.5">
                                    <button
                                      onClick={() => editSkillForm(row)}
                                      className="rounded border border-slate-300 bg-white px-2 py-1 text-[11px] font-medium text-slate-700 hover:bg-slate-50"
                                      type="button"
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
                    </SectionCard>
                  ) : null}

                  {sectionVisible("plugins") ? (
                    <SectionCard
                      title="Plugins"
                      subtitle="Discover and validate plugin bundles, then control platform approvals."
                      actionLabel="Refresh Plugins"
                      onAction={() => void onRefreshPlugins()}
                    >
                      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                        <div className="text-xs text-slate-600">
                          Registry sync:{" "}
                          <span className="font-mono text-slate-800">
                            {pluginSync.syncedCount} manifests
                          </span>
                        </div>
                        <div className="flex flex-wrap items-center gap-2">
                          <input
                            ref={pluginUploadInputRef}
                            type="file"
                            accept=".zip,application/zip"
                            onChange={(event) => setPluginUploadFile(event.target.files?.[0] || null)}
                            className="hidden"
                          />
                          <button
                            type="button"
                            onClick={() => pluginUploadInputRef.current?.click()}
                            className="rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50"
                          >
                            Choose Plugin ZIP
                          </button>
                          <div className="max-w-[260px] truncate rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-2 text-xs text-slate-600">
                            {pluginUploadFile ? pluginUploadFile.name : "No file selected"}
                          </div>
                          <button
                            type="button"
                            disabled={!pluginUploadFile || pluginUploadBusy}
                            onClick={() => void onUploadPluginBundle()}
                            className="rounded-lg border border-sky-300 bg-sky-50 px-2 py-1.5 text-xs font-semibold text-sky-700 hover:bg-sky-100 disabled:cursor-not-allowed disabled:opacity-60"
                          >
                            {pluginUploadBusy ? "Uploading..." : "Upload Plugin ZIP"}
                          </button>
                        </div>
                      </div>

                      {pluginSync.invalid.length > 0 ? (
                        <div className="mb-3 rounded-lg border border-amber-300 bg-amber-50 p-3">
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

                      <div className="grid grid-cols-1 gap-3 xl:grid-cols-[minmax(0,1fr)_420px]">
                        <TableWrap>
                          <table className="min-w-full text-left text-sm">
                            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                              <tr>
                                <th className="px-2 py-1.5">Plugin</th>
                                <th className="px-2 py-1.5">Version</th>
                                <th className="px-2 py-1.5">Validated</th>
                                <th className="px-2 py-1.5">Platform</th>
                                <th className="px-2 py-1.5">Source</th>
                                <th className="px-2 py-1.5" />
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-100">
                              {plugins.length === 0 ? (
                                <tr>
                                  <td className="px-2 py-2 text-sm text-slate-500" colSpan={6}>
                                    No plugins discovered yet.
                                  </td>
                                </tr>
                              ) : (
                                plugins.map((row) => {
                                  const selected = row.pluginId === selectedPluginId;
                                  return (
                                    <tr
                                      key={row.pluginId}
                                      className={selected ? "bg-sky-50/60" : ""}
                                    >
                                      <td className="px-2 py-1.5">
                                        <div className="flex items-center gap-2">
                                          <PluginAvatar
                                            iconDataUrl={row.iconDataUrl}
                                            fallback={row.iconFallback || row.name || row.pluginId}
                                            size="sm"
                                          />
                                          <div>
                                            <div className="font-medium text-slate-900">{row.name || row.pluginId}</div>
                                            <div className="font-mono text-[11px] text-slate-500">{row.pluginId}</div>
                                          </div>
                                        </div>
                                      </td>
                                      <td className="px-2 py-1.5 font-mono text-xs text-slate-700">{row.version || "-"}</td>
                                      <td className="px-2 py-1.5 text-xs text-slate-700">
                                        {row.isValidated ? "yes" : "no"}
                                      </td>
                                      <td className="px-2 py-1.5 text-xs text-slate-700">
                                        {row.isPlatformApproved ? "approved" : "blocked"}
                                      </td>
                                      <td className="px-2 py-1.5 text-xs text-slate-700">{row.sourceType || "-"}</td>
                                      <td className="px-2 py-1.5">
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

                        <div className="rounded-lg border border-slate-200 bg-white p-3">
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
                              <dl className="grid grid-cols-1 gap-1.5 text-xs text-slate-700">
                                <div className="flex justify-between gap-2">
                                  <dt>Validated</dt>
                                  <dd>{selectedPlugin.isValidated ? "yes" : "no"}</dd>
                                </div>
                                <div className="flex justify-between gap-2">
                                  <dt>Platform Approved</dt>
                                  <dd>{selectedPlugin.isPlatformApproved ? "yes" : "no"}</dd>
                                </div>
                              </dl>
                              <div className="mt-2 text-[11px] text-slate-500">
                                Manifest: <span className="font-mono">{selectedPlugin.manifestPath || "-"}</span>
                              </div>
                              <div className="mt-1 text-[11px] text-slate-500">
                                Source: <span className="font-mono">{selectedPlugin.sourceType || "-"}</span>
                                {selectedPlugin.bundleSha256 ? (
                                  <span>
                                    {" "}· sha256:{selectedPlugin.bundleSha256.slice(0, 12)}
                                  </span>
                                ) : null}
                              </div>
                              {selectedPlugin.validationError ? (
                                <div className="mt-2 rounded-lg border border-rose-300 bg-rose-50 px-2.5 py-2 text-xs text-rose-700">
                                  {selectedPlugin.validationError}
                                </div>
                              ) : null}
                              <div className="mt-3 grid gap-2">
                                <div>
                                  <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                                    Capabilities
                                  </div>
                                  <div className="flex flex-wrap gap-1">
                                    {selectedPlugin.capabilities.length === 0 ? (
                                      <span className="text-xs text-slate-500">None declared.</span>
                                    ) : (
                                      selectedPlugin.capabilities.map((item) => (
                                        <span
                                          key={item}
                                          className="rounded-full border border-slate-300 bg-slate-50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-700"
                                        >
                                          {item}
                                        </span>
                                      ))
                                    )}
                                  </div>
                                </div>
                                <div>
                                  <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                                    Permissions
                                  </div>
                                  <div className="flex flex-wrap gap-1">
                                    {selectedPlugin.permissions.length === 0 ? (
                                      <span className="text-xs text-slate-500">None declared.</span>
                                    ) : (
                                      selectedPlugin.permissions.map((item) => (
                                        <span
                                          key={item}
                                          className="rounded-full border border-amber-300 bg-amber-50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-700"
                                        >
                                          {item}
                                        </span>
                                      ))
                                    )}
                                  </div>
                                </div>
                                <div>
                                  <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                                    Help (README.md)
                                  </div>
                                  {selectedPlugin.helpMarkdown ? (
                                    <pre className="max-h-52 overflow-auto whitespace-pre-wrap rounded-lg border border-slate-200 bg-slate-50 p-2 text-[11px] text-slate-700">
                                      {selectedPlugin.helpMarkdown}
                                    </pre>
                                  ) : (
                                    <div className="rounded-lg border border-slate-200 bg-slate-50 px-2 py-1.5 text-xs text-slate-500">
                                      No README.md found in this plugin bundle.
                                    </div>
                                  )}
                                </div>
                              </div>
                              <div className="mt-3 flex justify-end">
                                <button
                                  type="button"
                                  disabled={!selectedPlugin.isValidated}
                                  onClick={() =>
                                    void onSetPlatformPluginApproval(
                                      selectedPlugin.pluginId,
                                      !selectedPlugin.isPlatformApproved
                                    )
                                  }
                                  className={`rounded-lg px-2 py-1.5 text-xs font-semibold ${
                                    selectedPlugin.isPlatformApproved
                                      ? "border border-rose-300 bg-rose-50 text-rose-700 hover:bg-rose-100"
                                      : "border border-emerald-300 bg-emerald-50 text-emerald-700 hover:bg-emerald-100"
                                  } disabled:cursor-not-allowed disabled:opacity-60`}
                                >
                                  {selectedPlugin.isPlatformApproved ? "Revoke Platform Approval" : "Approve Plugin"}
                                </button>
                              </div>
                            </>
                          ) : (
                            <div className="text-sm text-slate-500">Select a plugin to inspect details.</div>
                          )}
                        </div>
                      </div>
                    </SectionCard>
                  ) : null}

                  {sectionVisible("enablement") ? (
                    <SectionCard
                      title="Tenant Integration Enablement"
                      subtitle="Enable integrations per tenant and optionally override assistant docs with tenant-specific guidance."
                    >
                      <div className="mb-3 flex items-center justify-between gap-2">
                        <span className="text-sm font-medium text-slate-700">Tenant</span>
                        <select
                          className="rounded-lg border border-slate-300 bg-white px-2.5 py-2 text-sm"
                          value={selectedTenantSlug}
                          onChange={(event) => setSelectedTenantSlug(event.target.value)}
                        >
                          {tenants.map((tenant) => (
                            <option key={tenant.slug} value={tenant.slug}>
                              {tenant.name || tenant.slug} ({tenant.slug})
                            </option>
                          ))}
                        </select>
                      </div>
                      <div className="space-y-2">
                        {integrations.map((integration) => {
                          const binding = selectedTenantSlug
                            ? getTenantIntegration(selectedTenantSlug, integration.key)
                            : null;
                          const [enabled, notes, override] = [
                            binding?.isEnabled ?? false,
                            binding?.notes ?? "",
                            binding?.assistantDocsOverride ?? "",
                          ];
                          return (
                            <TenantIntegrationCard
                              key={integration.key}
                              integration={integration}
                              enabled={enabled}
                              notes={notes}
                              override={override}
                              tenantAuthConfigText={JSON.stringify(binding?.tenantAuthConfig || {}, null, 2)}
                              onSave={(next) => {
                                if (!selectedTenantSlug) return;
                                let parsedTenantAuthConfig: Record<string, unknown> = {};
                                if (String(integration.authScope || "tenant") === "tenant") {
                                  try {
                                    parsedTenantAuthConfig = next.tenantAuthConfigText.trim()
                                      ? JSON.parse(next.tenantAuthConfigText)
                                      : {};
                                    if (
                                      !parsedTenantAuthConfig ||
                                      typeof parsedTenantAuthConfig !== "object" ||
                                      Array.isArray(parsedTenantAuthConfig)
                                    ) {
                                      throw new Error("Tenant auth config must be a JSON object.");
                                    }
                                  } catch (error) {
                                    setFlash(
                                      `Invalid tenant auth config JSON for ${integration.key}: ${
                                        error instanceof Error ? error.message : String(error)
                                      }`,
                                      "error"
                                    );
                                    return;
                                  }
                                }
                                void onSaveTenantIntegration(
                                  selectedTenantSlug,
                                  integration.key,
                                  next.enabled,
                                  next.notes,
                                  next.override,
                                  parsedTenantAuthConfig
                                );
                              }}
                            />
                          );
                        })}
                      </div>
                    </SectionCard>
                  ) : null}

                  {sectionVisible("configuration") ? (
                    <SectionCard title="Platform configuration" subtitle="Site, OAuth, WhatsApp, Facebook/Meta, and Shopify settings.">
                      <form className="rounded-lg border border-slate-200 bg-white p-3" onSubmit={onSaveConfiguration}>
                        <div className="space-y-4">
                          <div>
                            <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-600">General</h3>
                            <div className="mt-1.5 grid gap-2 sm:grid-cols-2">
                              <Field label="Site name">
                                <input
                                  className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm"
                                  value={configForm.siteName}
                                  onChange={(e) => setConfigForm((p) => ({ ...p, siteName: e.target.value }))}
                                  placeholder="Moio"
                                />
                              </Field>
                              <Field label="Company">
                                <input
                                  className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm"
                                  value={configForm.company}
                                  onChange={(e) => setConfigForm((p) => ({ ...p, company: e.target.value }))}
                                  placeholder="Acme Inc"
                                />
                              </Field>
                              <div className="sm:col-span-2">
                                <Field label="Base URL (my_url)">
                                  <input
                                    className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm font-mono"
                                    type="url"
                                    value={configForm.myUrl}
                                    onChange={(e) => setConfigForm((p) => ({ ...p, myUrl: e.target.value }))}
                                    placeholder="https://app.example.com/"
                                  />
                                </Field>
                              </div>
                              {configForm.logoUrl ? (
                                <div className="sm:col-span-2 text-xs text-slate-500">Logo: {configForm.logoUrl}</div>
                              ) : null}
                              {configForm.faviconUrl ? (
                                <div className="sm:col-span-2 text-xs text-slate-500">Favicon: {configForm.faviconUrl}</div>
                              ) : null}
                            </div>
                          </div>
                          <div>
                            <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-600">WhatsApp</h3>
                            <div className="mt-1.5 grid gap-2 sm:grid-cols-2">
                              <Field label="Webhook token">
                                <input
                                  className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm font-mono"
                                  type="password"
                                  autoComplete="off"
                                  value={configForm.whatsappWebhookToken}
                                  onChange={(e) => setConfigForm((p) => ({ ...p, whatsappWebhookToken: e.target.value }))}
                                  placeholder="••••••••"
                                />
                              </Field>
                              <Field label="Webhook redirect URL">
                                <input
                                  className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm font-mono"
                                  type="url"
                                  value={configForm.whatsappWebhookRedirect}
                                  onChange={(e) => setConfigForm((p) => ({ ...p, whatsappWebhookRedirect: e.target.value }))}
                                  placeholder="https://..."
                                />
                              </Field>
                            </div>
                          </div>
                          <div>
                            <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-600">Facebook / Meta</h3>
                            <div className="mt-1.5 grid gap-2 sm:grid-cols-2">
                              <Field label="System token">
                                <input
                                  className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm font-mono"
                                  type="password"
                                  autoComplete="off"
                                  value={configForm.fbSystemToken}
                                  onChange={(e) => setConfigForm((p) => ({ ...p, fbSystemToken: e.target.value }))}
                                  placeholder="••••••••"
                                />
                              </Field>
                              <Field label="Bot app ID">
                                <input
                                  className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm font-mono"
                                  value={configForm.fbMoioBotAppId}
                                  onChange={(e) => setConfigForm((p) => ({ ...p, fbMoioBotAppId: e.target.value }))}
                                  placeholder=""
                                />
                              </Field>
                              <Field label="Business manager ID">
                                <input
                                  className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm font-mono"
                                  value={configForm.fbMoioBusinessManagerId}
                                  onChange={(e) => setConfigForm((p) => ({ ...p, fbMoioBusinessManagerId: e.target.value }))}
                                  placeholder=""
                                />
                              </Field>
                              <Field label="Bot app secret">
                                <input
                                  className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm font-mono"
                                  type="password"
                                  autoComplete="off"
                                  value={configForm.fbMoioBotAppSecret}
                                  onChange={(e) => setConfigForm((p) => ({ ...p, fbMoioBotAppSecret: e.target.value }))}
                                  placeholder="••••••••"
                                />
                              </Field>
                              <Field label="Bot configuration ID">
                                <input
                                  className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm font-mono"
                                  value={configForm.fbMoioBotConfigurationId}
                                  onChange={(e) => setConfigForm((p) => ({ ...p, fbMoioBotConfigurationId: e.target.value }))}
                                  placeholder=""
                                />
                              </Field>
                            </div>
                          </div>
                          <div>
                            <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-600">Google OAuth</h3>
                            <div className="mt-1.5 grid gap-2 sm:grid-cols-2">
                              <Field label="Client ID">
                                <input
                                  className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm font-mono"
                                  value={configForm.googleOauthClientId}
                                  onChange={(e) => setConfigForm((p) => ({ ...p, googleOauthClientId: e.target.value }))}
                                  placeholder=""
                                />
                              </Field>
                              <Field label="Client secret">
                                <input
                                  className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm font-mono"
                                  type="password"
                                  autoComplete="off"
                                  value={configForm.googleOauthClientSecret}
                                  onChange={(e) => setConfigForm((p) => ({ ...p, googleOauthClientSecret: e.target.value }))}
                                  placeholder="••••••••"
                                />
                              </Field>
                            </div>
                          </div>
                          <div>
                            <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-600">Microsoft OAuth</h3>
                            <div className="mt-1.5 grid gap-2 sm:grid-cols-2">
                              <Field label="Client ID">
                                <input
                                  className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm font-mono"
                                  value={configForm.microsoftOauthClientId}
                                  onChange={(e) => setConfigForm((p) => ({ ...p, microsoftOauthClientId: e.target.value }))}
                                  placeholder=""
                                />
                              </Field>
                              <Field label="Client secret">
                                <input
                                  className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm font-mono"
                                  type="password"
                                  autoComplete="off"
                                  value={configForm.microsoftOauthClientSecret}
                                  onChange={(e) => setConfigForm((p) => ({ ...p, microsoftOauthClientSecret: e.target.value }))}
                                  placeholder="••••••••"
                                />
                              </Field>
                            </div>
                          </div>
                          <div>
                            <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-600">Shopify</h3>
                            <div className="mt-1.5 grid gap-2 sm:grid-cols-2">
                              <Field label="Client ID">
                                <input
                                  className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm font-mono"
                                  value={configForm.shopifyClientId}
                                  onChange={(e) => setConfigForm((p) => ({ ...p, shopifyClientId: e.target.value }))}
                                  placeholder=""
                                />
                              </Field>
                              <Field label="Client secret">
                                <input
                                  className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm font-mono"
                                  type="password"
                                  autoComplete="off"
                                  value={configForm.shopifyClientSecret}
                                  onChange={(e) => setConfigForm((p) => ({ ...p, shopifyClientSecret: e.target.value }))}
                                  placeholder="••••••••"
                                />
                              </Field>
                            </div>
                          </div>
                        </div>
                        <div className="mt-3">
                          <button
                            type="submit"
                            className="rounded border border-slate-700 bg-slate-800 px-2.5 py-1.5 text-xs font-medium text-white hover:bg-slate-700"
                          >
                            Save configuration
                          </button>
                        </div>
                      </form>
                    </SectionCard>
                  ) : null}

                  {sectionVisible("security") ? (
                    <SectionCard title="Security" subtitle="Platform-level access and runtime guardrails.">
                      <div className="grid gap-2 lg:grid-cols-2">
                        <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-600">Current Session</h3>
                          <dl className="mt-1.5 space-y-1 text-xs text-slate-700">
                            <div className="flex justify-between gap-2">
                              <dt>User</dt>
                              <dd className="font-mono text-xs">{currentUser.email}</dd>
                            </div>
                            <div className="flex justify-between gap-2">
                              <dt>Platform admin</dt>
                              <dd>{currentUser.isPlatformAdmin ? "yes" : "no"}</dd>
                            </div>
                            <div className="flex justify-between gap-2">
                              <dt>Account active</dt>
                              <dd>{currentUser.isActive ? "yes" : "no"}</dd>
                            </div>
                          </dl>
                        </div>
                        <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-600">Recommendations</h3>
                          <ul className="mt-1.5 list-disc space-y-0.5 pl-4 text-xs text-slate-700">
                            <li>Use tenant-scoped memberships and keep viewer users read-only.</li>
                            <li>Rotate vendor keys in vault regularly.</li>
                            <li>Use integration docs to constrain assistant behavior by tenant.</li>
                          </ul>
                        </div>
                      </div>
                      <form className="mt-2 rounded-lg border border-slate-200 bg-white p-3" onSubmit={onSaveNotifications}>
                        <div className="mb-2 flex items-center justify-between gap-2">
                          <div>
                            <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-600">Notification Defaults</h3>
                            <p className="mt-0.5 text-xs text-slate-600">
                              Configure default presentation for completion notifications.
                            </p>
                          </div>
                          <button
                            type="button"
                            onClick={() => void onTestNotification()}
                            className="rounded border border-sky-300 bg-sky-50 px-2.5 py-1.5 text-xs font-medium text-sky-700 hover:bg-sky-100"
                          >
                            Test
                          </button>
                        </div>
                        <div className="grid gap-2 lg:grid-cols-2">
                          <Field label="Default Title">
                            <input
                              className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm"
                              value={notificationForm.title}
                              onChange={(event) =>
                                setNotificationForm((prev) => ({ ...prev, title: event.target.value }))
                              }
                              placeholder="Moio"
                            />
                          </Field>
                          <Field label="Icon URL">
                            <input
                              className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm"
                              value={notificationForm.iconUrl}
                              onChange={(event) =>
                                setNotificationForm((prev) => ({ ...prev, iconUrl: event.target.value }))
                              }
                              placeholder="/pwa-icon.svg"
                            />
                          </Field>
                          <Field label="Badge URL">
                            <input
                              className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm"
                              value={notificationForm.badgeUrl}
                              onChange={(event) =>
                                setNotificationForm((prev) => ({ ...prev, badgeUrl: event.target.value }))
                              }
                              placeholder="/pwa-icon.svg"
                            />
                          </Field>
                          <Field label="Test Title">
                            <input
                              className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm"
                              value={notificationForm.testTitle}
                              onChange={(event) =>
                                setNotificationForm((prev) => ({ ...prev, testTitle: event.target.value }))
                              }
                              placeholder="Moio test notification"
                            />
                          </Field>
                          <Field label="Test Body">
                            <textarea
                              className="h-24 w-full rounded border border-slate-300 px-2 py-1.5 text-sm"
                              value={notificationForm.testBody}
                              onChange={(event) =>
                                setNotificationForm((prev) => ({ ...prev, testBody: event.target.value }))
                              }
                              placeholder="Notifications are configured for this browser."
                            />
                          </Field>
                          <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                            <div className="text-xs font-semibold uppercase tracking-wide text-slate-600">Delivery Options</div>
                            <div className="mt-2 space-y-2 text-sm text-slate-700">
                              <label className="flex items-center gap-2">
                                <input
                                  type="checkbox"
                                  checked={notificationForm.requireInteraction}
                                  onChange={(event) =>
                                    setNotificationForm((prev) => ({ ...prev, requireInteraction: event.target.checked }))
                                  }
                                />
                                Keep visible until dismissed
                              </label>
                              <label className="flex items-center gap-2">
                                <input
                                  type="checkbox"
                                  checked={notificationForm.renotify}
                                  onChange={(event) =>
                                    setNotificationForm((prev) => ({ ...prev, renotify: event.target.checked }))
                                  }
                                />
                                Re-alert when replacing same tag
                              </label>
                              <label className="flex items-center gap-2">
                                <input
                                  type="checkbox"
                                  checked={notificationForm.silent}
                                  onChange={(event) =>
                                    setNotificationForm((prev) => ({ ...prev, silent: event.target.checked }))
                                  }
                                />
                                Silent notification
                              </label>
                            </div>
                          </div>
                        </div>
                        <div className="mt-2 flex flex-wrap items-center gap-2">
                          <button
                            className="rounded border border-slate-700 bg-slate-800 px-2.5 py-1.5 text-xs font-medium text-white hover:bg-slate-700"
                            type="submit"
                          >
                            Save notification settings
                          </button>
                          <span className="text-[11px] text-slate-500">VAPID keys are env-backed; this form controls presentation only.</span>
                        </div>
                      </form>
                    </SectionCard>
                  ) : null}
                </div>
                ) : null}
              </>
            )}
          </div>
        </section>
      </div>

      <Modal open={tenantModalOpen} onClose={() => setTenantModalOpen(false)} title={tenantForm.id ? "Edit tenant" : "New tenant"}>
        <form onSubmit={onSubmitTenant}>
          <Field label="Tenant Name">
            <input
              className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm"
              value={tenantForm.name}
              onChange={(e) => setTenantForm((p) => ({ ...p, name: e.target.value }))}
              placeholder="Acme Corp"
            />
          </Field>
          <Field label="Plan">
            <select
              className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm"
              value={tenantForm.plan}
              onChange={(e) => setTenantForm((p) => ({ ...p, plan: e.target.value }))}
            >
              {plans.length === 0 ? (
                <option value="">Create a plan first</option>
              ) : null}
              {plans.map((plan) => (
                <option key={plan.key} value={plan.key}>
                  {plan.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Module Enablements">
            <div className="rounded border border-slate-200 bg-slate-50 p-2 text-xs text-slate-700">
              <label className="mb-1.5 flex items-center gap-2">
                <input type="checkbox" checked disabled />
                CRM (base, always enabled)
              </label>
              <label className="mb-1.5 flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={tenantForm.moduleEnablements.flowsDatalab}
                  onChange={(e) =>
                    setTenantForm((p) => ({
                      ...p,
                      moduleEnablements: { ...p.moduleEnablements, flowsDatalab: e.target.checked },
                    }))
                  }
                />
                Flows + Data Lab addon
              </label>
              <label className="mb-1.5 flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={tenantForm.moduleEnablements.chatbot}
                  onChange={(e) =>
                    setTenantForm((p) => ({
                      ...p,
                      moduleEnablements: { ...p.moduleEnablements, chatbot: e.target.checked },
                    }))
                  }
                />
                Chatbot addon
              </label>
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={tenantForm.moduleEnablements.agentConsole}
                  onChange={(e) =>
                    setTenantForm((p) => ({
                      ...p,
                      moduleEnablements: { ...p.moduleEnablements, agentConsole: e.target.checked },
                    }))
                  }
                />
                Agent Console addon
              </label>
            </div>
          </Field>
          {!tenantForm.id ? (
            <>
              <Field label="Tenant Slug">
                <input
                  className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm"
                  value={tenantForm.slug}
                  onChange={(e) => setTenantForm((p) => ({ ...p, slug: e.target.value }))}
                  placeholder="acme"
                />
              </Field>
              <Field label="Schema Name">
                <input
                  className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm font-mono"
                  value={tenantForm.schemaName}
                  onChange={(e) => setTenantForm((p) => ({ ...p, schemaName: e.target.value }))}
                  placeholder="acme"
                />
              </Field>
              <Field label="Primary Domain">
                <input
                  className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm font-mono"
                  value={tenantForm.primaryDomain}
                  onChange={(e) => setTenantForm((p) => ({ ...p, primaryDomain: e.target.value }))}
                  placeholder="acme.localhost"
                />
              </Field>
            </>
          ) : null}
          <label className="mb-1.5 flex items-center gap-2 text-xs text-slate-600">
            <input
              type="checkbox"
              checked={tenantForm.isActive}
              onChange={(e) => setTenantForm((p) => ({ ...p, isActive: e.target.checked }))}
            />
            Tenant active
          </label>
          <div className="mt-3 flex flex-wrap gap-2">
            <button type="submit" className="rounded border border-slate-700 bg-slate-800 px-2.5 py-1.5 text-xs font-medium text-white hover:bg-slate-700">
              Save Tenant
            </button>
            {tenantForm.id ? (
              <button
                type="button"
                className="rounded border border-rose-200 bg-rose-50 px-2.5 py-1.5 text-xs font-medium text-rose-700 hover:bg-rose-100"
                onClick={() => void onDeleteTenant()}
              >
                Delete
              </button>
            ) : null}
            <button type="button" onClick={() => setTenantModalOpen(false)} className="rounded border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50">
              Cancel
            </button>
          </div>
        </form>
      </Modal>

      <Modal open={planModalOpen} onClose={() => setPlanModalOpen(false)} title={planForm.id ? "Edit plan" : "New plan"}>
        <form onSubmit={onSubmitPlan}>
          <Field label="Key (slug)">
            <input
              className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm font-mono"
              value={planForm.key}
              onChange={(e) => setPlanForm((p) => ({ ...p, key: e.target.value.trim().toLowerCase() }))}
              placeholder="e.g. pro"
              readOnly={!!planForm.id}
            />
          </Field>
          <Field label="Name">
            <input
              className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm"
              value={planForm.name}
              onChange={(e) => setPlanForm((p) => ({ ...p, name: e.target.value }))}
              placeholder="e.g. Pro"
            />
          </Field>
          <Field label="Display order">
            <input
              type="number"
              className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm"
              value={planForm.displayOrder}
              onChange={(e) => setPlanForm((p) => ({ ...p, displayOrder: parseInt(e.target.value, 10) || 0 }))}
            />
          </Field>
          <label className="mb-1.5 flex items-center gap-2 text-xs text-slate-600">
            <input
              type="checkbox"
              checked={planForm.isActive}
              onChange={(e) => setPlanForm((p) => ({ ...p, isActive: e.target.checked }))}
            />
            Plan active (show in tenant dropdown)
          </label>
          <label className="mb-1.5 flex items-center gap-2 text-xs text-slate-600">
            <input
              type="checkbox"
              checked={planForm.isSelfProvisionDefault}
              onChange={(e) => setPlanForm((p) => ({ ...p, isSelfProvisionDefault: e.target.checked }))}
            />
            Use as default plan for self-provision
          </label>
          <Field label="Pricing – Currency">
            <input
              className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm font-mono"
              value={planForm.pricingCurrency}
              onChange={(e) => setPlanForm((p) => ({ ...p, pricingCurrency: e.target.value.trim() || "USD" }))}
              placeholder="USD"
            />
          </Field>
          <div className="space-y-3">
            <div className="text-xs font-medium text-slate-700">Entitlements – Limits</div>
            <div className="flex flex-wrap gap-4">
              <Field label="Seats">
                <input
                  type="number"
                  min={0}
                  className="w-24 rounded border border-slate-300 px-2 py-1.5 text-sm"
                  value={planForm.entitlementLimits.seats}
                  onChange={(e) =>
                    setPlanForm((p) => ({
                      ...p,
                      entitlementLimits: { ...p.entitlementLimits, seats: parseInt(e.target.value, 10) || 0 },
                    }))
                  }
                />
              </Field>
              <Field label="Agents">
                <input
                  type="number"
                  min={0}
                  className="w-24 rounded border border-slate-300 px-2 py-1.5 text-sm"
                  value={planForm.entitlementLimits.agents}
                  onChange={(e) =>
                    setPlanForm((p) => ({
                      ...p,
                      entitlementLimits: { ...p.entitlementLimits, agents: parseInt(e.target.value, 10) || 0 },
                    }))
                  }
                />
              </Field>
              <Field label="Flows">
                <input
                  type="number"
                  min={0}
                  className="w-24 rounded border border-slate-300 px-2 py-1.5 text-sm"
                  value={planForm.entitlementLimits.flows}
                  onChange={(e) =>
                    setPlanForm((p) => ({
                      ...p,
                      entitlementLimits: { ...p.entitlementLimits, flows: parseInt(e.target.value, 10) || 0 },
                    }))
                  }
                />
              </Field>
            </div>
            <div className="text-xs font-medium text-slate-700">Module enablements</div>
            <div className="rounded border border-slate-200 bg-slate-50 p-2 text-xs text-slate-700">
              <label className="mb-1.5 flex items-center gap-2">
                <input type="checkbox" checked disabled />
                CRM (base, always on)
              </label>
              <label className="mb-1.5 flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={planForm.entitlementModuleEnablements.flowsDatalab}
                  onChange={(e) =>
                    setPlanForm((p) => ({
                      ...p,
                      entitlementModuleEnablements: { ...p.entitlementModuleEnablements, flowsDatalab: e.target.checked },
                    }))
                  }
                />
                Flows + Data Lab
              </label>
              <label className="mb-1.5 flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={planForm.entitlementModuleEnablements.chatbot}
                  onChange={(e) =>
                    setPlanForm((p) => ({
                      ...p,
                      entitlementModuleEnablements: { ...p.entitlementModuleEnablements, chatbot: e.target.checked },
                    }))
                  }
                />
                Chatbot
              </label>
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={planForm.entitlementModuleEnablements.agentConsole}
                  onChange={(e) =>
                    setPlanForm((p) => ({
                      ...p,
                      entitlementModuleEnablements: { ...p.entitlementModuleEnablements, agentConsole: e.target.checked },
                    }))
                  }
                />
                Agent Console
              </label>
            </div>
            <div className="text-xs font-medium text-slate-700">Features (capabilities)</div>
            <div className="grid max-h-48 grid-cols-2 gap-x-4 gap-y-1 overflow-y-auto rounded border border-slate-200 bg-slate-50 p-2 text-xs text-slate-700 sm:grid-cols-3">
              {ENTITLEMENT_FEATURE_KEYS.map((key) => (
                <label key={key} className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={planForm.entitlementFeatures[key]}
                    onChange={(e) =>
                      setPlanForm((p) => ({
                        ...p,
                        entitlementFeatures: { ...p.entitlementFeatures, [key]: e.target.checked },
                      }))
                    }
                  />
                  <span className="font-mono">{key}</span>
                </label>
              ))}
            </div>
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            <button type="submit" className="rounded border border-slate-700 bg-slate-800 px-2.5 py-1.5 text-xs font-medium text-white hover:bg-slate-700">
              Save Plan
            </button>
            {planForm.id ? (
              <button
                type="button"
                className="rounded border border-rose-200 bg-rose-50 px-2.5 py-1.5 text-xs font-medium text-rose-700 hover:bg-rose-100"
                onClick={() => void onDeletePlan()}
              >
                Delete
              </button>
            ) : null}
            <button type="button" onClick={() => setPlanModalOpen(false)} className="rounded border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50">
              Cancel
            </button>
          </div>
        </form>
      </Modal>

      <Modal open={userModalOpen} onClose={() => setUserModalOpen(false)} title={userForm.id ? "Edit user" : "New user"} size="lg">
        <form onSubmit={onSubmitUser}>
          <Field label="Email">
            <input
              className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm font-mono"
              value={userForm.email}
              onChange={(e) => setUserForm((p) => ({ ...p, email: e.target.value }))}
              placeholder="user@company.com"
            />
          </Field>
          <Field label="Display Name">
            <input
              className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm"
              value={userForm.displayName}
              onChange={(e) => setUserForm((p) => ({ ...p, displayName: e.target.value }))}
              placeholder="User Name"
            />
          </Field>
          <Field label="Password (leave empty to keep current)">
            <input
              type="password"
              className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm"
              value={userForm.password}
              onChange={(e) => setUserForm((p) => ({ ...p, password: e.target.value }))}
              placeholder="********"
            />
          </Field>
          <div className="mb-1.5 flex flex-wrap items-center gap-3 text-xs text-slate-600">
            <label className="inline-flex items-center gap-2">
              <input type="checkbox" checked={userForm.isPlatformAdmin} onChange={(e) => setUserForm((p) => ({ ...p, isPlatformAdmin: e.target.checked }))} />
              Platform admin
            </label>
            <label className="inline-flex items-center gap-2">
              <input type="checkbox" checked={userForm.isActive} onChange={(e) => setUserForm((p) => ({ ...p, isActive: e.target.checked }))} />
              Active
            </label>
          </div>
          <div className="mb-1.5 rounded border border-slate-200 bg-slate-50 p-2">
            <div className="mb-1 text-[11px] font-medium uppercase tracking-wide text-slate-500">Tenant Memberships</div>
            <div className="space-y-1">
              {tenants.map((tenant) => {
                const membership = userForm.tenantMemberships.find((r) => r.tenantSlug === tenant.slug) || null;
                const active = Boolean(membership);
                return (
                  <div key={tenant.slug} className="rounded border border-slate-200 bg-white p-1.5">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <label className="inline-flex items-center gap-2 text-xs text-slate-600">
                        <input
                          type="checkbox"
                          checked={active}
                          onChange={(e) => {
                            if (!e.target.checked) {
                              removeUserMembership(tenant.slug);
                              return;
                            }
                            upsertUserMembership(tenant.slug, { tenantSlug: tenant.slug, role: "member", isActive: true });
                          }}
                        />
                        {tenant.name || tenant.slug}
                      </label>
                      {active ? (
                        <div className="flex items-center gap-2 text-xs">
                          <select
                            className="rounded border border-slate-300 px-1.5 py-0.5 text-xs"
                            value={membership?.role || "member"}
                            onChange={(e) => upsertUserMembership(tenant.slug, { role: e.target.value as TenantMembership["role"] })}
                          >
                            <option value="admin">admin</option>
                            <option value="member">member</option>
                            <option value="viewer">viewer</option>
                          </select>
                          <label className="inline-flex items-center gap-1 text-slate-700">
                            <input
                              type="checkbox"
                              checked={membership?.isActive ?? true}
                              onChange={(e) => upsertUserMembership(tenant.slug, { isActive: e.target.checked })}
                            />
                            active
                          </label>
                        </div>
                      ) : null}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            <button type="submit" className="rounded border border-slate-700 bg-slate-800 px-2.5 py-1.5 text-xs font-medium text-white hover:bg-slate-700">
              Save User
            </button>
            {userForm.id ? (
              <button type="button" className="rounded border border-rose-200 bg-rose-50 px-2.5 py-1.5 text-xs font-medium text-rose-700 hover:bg-rose-100" onClick={() => void onDeleteUser()}>
                Delete
              </button>
            ) : null}
            <button type="button" onClick={() => setUserModalOpen(false)} className="rounded border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50">
              Cancel
            </button>
          </div>
        </form>
      </Modal>

      <Modal open={integrationModalOpen} onClose={() => setIntegrationModalOpen(false)} title={integrationForm.key ? "Edit integration" : "New integration"} size="xl">
        <form onSubmit={onSubmitIntegration}>
          <Field label="Key">
            <input className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm font-mono" value={integrationForm.key} onChange={(e) => setIntegrationForm((p) => ({ ...p, key: e.target.value }))} placeholder="salesforce" />
          </Field>
          <Field label="Name">
            <input className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm" value={integrationForm.name} onChange={(e) => setIntegrationForm((p) => ({ ...p, name: e.target.value }))} placeholder="Salesforce CRM" />
          </Field>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            <Field label="Category">
              <input className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm" value={integrationForm.category} onChange={(e) => setIntegrationForm((p) => ({ ...p, category: e.target.value }))} placeholder="crm" />
            </Field>
            <Field label="Default Auth">
              <select className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm" value={integrationForm.defaultAuthType} onChange={(e) => setIntegrationForm((p) => ({ ...p, defaultAuthType: e.target.value }))}>
                <option value="none">none</option>
                <option value="bearer">bearer</option>
                <option value="api_key_header">api_key_header</option>
                <option value="api_key_query">api_key_query</option>
                <option value="basic">basic</option>
                <option value="oauth2_client_credentials">oauth2_client_credentials</option>
              </select>
            </Field>
            <Field label="Auth Scope">
              <select className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm" value={integrationForm.authScope} onChange={(e) => setIntegrationForm((p) => ({ ...p, authScope: e.target.value as "global" | "tenant" | "user" }))}>
                <option value="global">global</option>
                <option value="tenant">tenant</option>
                <option value="user">user</option>
              </select>
            </Field>
          </div>
          <Field label="Base URL">
            <input className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm font-mono" value={integrationForm.baseUrl} onChange={(e) => setIntegrationForm((p) => ({ ...p, baseUrl: e.target.value }))} placeholder="https://api.example.com" />
          </Field>
          <Field label="OpenAPI URL">
            <input className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm font-mono" value={integrationForm.openapiUrl} onChange={(e) => setIntegrationForm((p) => ({ ...p, openapiUrl: e.target.value }))} placeholder="https://api.example.com/openapi.json" />
          </Field>
          <Field label="Default Headers (JSON)">
            <textarea className="h-20 w-full rounded border border-slate-300 px-2 py-1.5 text-xs font-mono" value={integrationForm.defaultHeadersText} onChange={(e) => setIntegrationForm((p) => ({ ...p, defaultHeadersText: e.target.value }))} placeholder='{"Accept":"application/json"}' />
          </Field>
          <Field label="Auth Config Schema (JSON)">
            <textarea className="h-20 w-full rounded border border-slate-300 px-2 py-1.5 text-xs font-mono" value={integrationForm.authConfigSchemaText} onChange={(e) => setIntegrationForm((p) => ({ ...p, authConfigSchemaText: e.target.value }))} placeholder='{"fields":[{"key":"api_key","type":"secret_ref"}]}' />
          </Field>
          <Field label="Global Auth Config (JSON)">
            <textarea className="h-20 w-full rounded border border-slate-300 px-2 py-1.5 text-xs font-mono" value={integrationForm.globalAuthConfigText} onChange={(e) => setIntegrationForm((p) => ({ ...p, globalAuthConfigText: e.target.value }))} placeholder='{"vaultKey":"crm_prod_token"}' />
          </Field>
          <Field label="Assistant Docs (Markdown)">
            <textarea className="h-32 w-full rounded border border-slate-300 px-2 py-1.5 text-xs font-mono" value={integrationForm.assistantDocsMarkdown} onChange={(e) => setIntegrationForm((p) => ({ ...p, assistantDocsMarkdown: e.target.value }))} placeholder="Describe endpoints, workflows, constraints, and examples for the assistant." />
          </Field>
          <label className="mb-2 flex items-center gap-2 text-xs text-slate-600">
            <input type="checkbox" checked={integrationForm.isActive} onChange={(e) => setIntegrationForm((p) => ({ ...p, isActive: e.target.checked }))} />
            Integration active
          </label>
          <div className="mt-3 flex flex-wrap gap-2">
            <button type="submit" className="rounded border border-slate-700 bg-slate-800 px-2.5 py-1.5 text-xs font-medium text-white hover:bg-slate-700">Save Integration</button>
            {integrationForm.key ? <button type="button" className="rounded border border-rose-200 bg-rose-50 px-2.5 py-1.5 text-xs font-medium text-rose-700 hover:bg-rose-100" onClick={() => void onDeleteIntegration()}>Delete</button> : null}
            <button type="button" onClick={() => setIntegrationModalOpen(false)} className="rounded border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50">Cancel</button>
          </div>
        </form>
      </Modal>

      <Modal open={skillModalOpen} onClose={() => setSkillModalOpen(false)} title={skillForm.key ? "Edit global skill" : "New global skill"} size="lg">
        <form onSubmit={onSubmitSkill}>
          <Field label="Skill Key">
            <input className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm font-mono" value={skillForm.key} onChange={(e) => setSkillForm((p) => ({ ...p, key: e.target.value }))} placeholder="crm_followup" />
          </Field>
          <Field label="Display Name">
            <input className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm" value={skillForm.name} onChange={(e) => setSkillForm((p) => ({ ...p, name: e.target.value }))} placeholder="CRM Follow-up Automation" />
          </Field>
          <Field label="Description">
            <input className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm" value={skillForm.description} onChange={(e) => setSkillForm((p) => ({ ...p, description: e.target.value }))} placeholder="What this skill does and when to use it" />
          </Field>
          <Field label="Skill Markdown">
            <textarea className="h-48 w-full rounded border border-slate-300 px-2 py-1.5 text-xs font-mono" value={skillForm.bodyMarkdown} onChange={(e) => setSkillForm((p) => ({ ...p, bodyMarkdown: e.target.value }))} placeholder="# Objective&#10;...&#10;&#10;# Constraints&#10;..." />
          </Field>
          <label className="mb-2 flex items-center gap-2 text-xs text-slate-600">
            <input type="checkbox" checked={skillForm.isActive} onChange={(e) => setSkillForm((p) => ({ ...p, isActive: e.target.checked }))} />
            Skill active
          </label>
          <div className="mt-3 flex flex-wrap gap-2">
            <button type="submit" className="rounded border border-slate-700 bg-slate-800 px-2.5 py-1.5 text-xs font-medium text-white hover:bg-slate-700">Save Skill</button>
            {skillForm.key ? <button type="button" className="rounded border border-rose-200 bg-rose-50 px-2.5 py-1.5 text-xs font-medium text-rose-700 hover:bg-rose-100" onClick={() => void onDeleteSkill()}>Delete</button> : null}
            <button type="button" onClick={() => setSkillModalOpen(false)} className="rounded border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50">Cancel</button>
          </div>
        </form>
      </Modal>

      {loading ? (
        <div className="pointer-events-none fixed inset-0 z-40 flex items-center justify-center bg-slate-900/20 backdrop-blur-[1px]">
          <div className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 shadow-lg">
            Loading...
          </div>
        </div>
      ) : null}
    </main>
  );
}

function Panel(props: SectionProps) {
  const fill = Boolean(props.fillHeight);
  return (
    <section
      className={
        fill
          ? "flex min-h-0 flex-1 flex-col rounded-lg border border-slate-200 bg-white p-3 shadow-sm"
          : "rounded-lg border border-slate-200 bg-white p-3 shadow-sm"
      }
    >
      <div className="shrink-0 mb-2 flex items-center justify-between gap-2">
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
      {fill ? <div className="min-h-0 flex-1 flex flex-col overflow-hidden">{props.children}</div> : props.children}
    </section>
  );
}

function SectionCard(props: SectionProps) {
  return <Panel {...props} />;
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
        className={`relative w-full ${sizeClass} max-h-[90vh] overflow-hidden rounded-lg border border-slate-200 bg-white shadow-xl flex flex-col`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="shrink-0 flex items-center justify-between border-b border-slate-200 px-4 py-3">
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

function TableWrap(props: { children: React.ReactNode; fillHeight?: boolean }) {
  const fill = Boolean(props.fillHeight);
  return (
    <div
      className={
        fill
          ? "flex min-h-0 flex-1 flex-col overflow-hidden rounded-lg border border-slate-200 bg-white"
          : "overflow-hidden rounded-lg border border-slate-200 bg-white"
      }
    >
      <div className={fill ? "min-h-0 flex-1 overflow-auto" : "max-h-[320px] overflow-auto"}>{props.children}</div>
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

function TenantIntegrationCard(props: {
  integration: IntegrationDefinition;
  enabled: boolean;
  notes: string;
  override: string;
  tenantAuthConfigText: string;
  onSave: (input: { enabled: boolean; notes: string; override: string; tenantAuthConfigText: string }) => void;
}) {
  const [enabled, setEnabled] = useState(props.enabled);
  const [notes, setNotes] = useState(props.notes);
  const [override, setOverride] = useState(props.override);
  const [tenantAuthConfigText, setTenantAuthConfigText] = useState(props.tenantAuthConfigText || "{}");

  useEffect(() => {
    setEnabled(props.enabled);
    setNotes(props.notes);
    setOverride(props.override);
    setTenantAuthConfigText(props.tenantAuthConfigText || "{}");
  }, [props.enabled, props.notes, props.override, props.tenantAuthConfigText, props.integration.key]);

  return (
    <article className="rounded-lg border border-slate-200 bg-white p-2.5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="text-sm font-semibold text-slate-900">{props.integration.name || props.integration.key}</div>
          <div className="font-mono text-[11px] text-slate-500">
            {props.integration.key} | {props.integration.defaultAuthType || "bearer"}
          </div>
        </div>
        <label className="inline-flex items-center gap-2 text-xs text-slate-700">
          <input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} />
          Enabled
        </label>
      </div>
      <label className="mb-1 mt-2 block text-xs font-semibold uppercase tracking-wide text-slate-500">
        Notes
      </label>
      <input
        className="w-full rounded-lg border border-slate-300 px-2.5 py-2 text-xs"
        value={notes}
        onChange={(event) => setNotes(event.target.value)}
        placeholder="Tenant-specific details"
      />
      <label className="mb-1 mt-2 block text-xs font-semibold uppercase tracking-wide text-slate-500">
        Assistant Docs Override (Markdown)
      </label>
      <textarea
        className="h-24 w-full rounded-lg border border-slate-300 px-2.5 py-2 text-xs font-mono"
        value={override}
        onChange={(event) => setOverride(event.target.value)}
        placeholder="Optional tenant override docs"
      />
      {String(props.integration.authScope || "tenant") === "tenant" ? (
        <>
          <label className="mb-1 mt-2 block text-xs font-semibold uppercase tracking-wide text-slate-500">
            Tenant Auth Config (JSON)
          </label>
          <textarea
            className="h-20 w-full rounded-lg border border-slate-300 px-2.5 py-2 text-xs font-mono"
            value={tenantAuthConfigText}
            onChange={(event) => setTenantAuthConfigText(event.target.value)}
            placeholder='{"vaultKey":"tenant_secret_ref"}'
          />
        </>
      ) : null}
      <div className="mt-2 flex justify-end">
        <button
          className="rounded-lg border border-sky-300 bg-sky-50 px-3 py-1.5 text-xs font-semibold text-sky-700 hover:bg-sky-100"
          type="button"
          onClick={() => props.onSave({ enabled, notes, override, tenantAuthConfigText })}
        >
          Save Binding
        </button>
      </div>
    </article>
  );
}
