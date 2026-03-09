import { useEffect } from "react";

type Role = "admin" | "member" | "viewer";

type MockState = {
  platform: {
    tenantsEnabled: boolean;
    publicSchema: string;
    currentUser: {
      id: number;
      email: string;
      displayName: string;
      isPlatformAdmin: boolean;
      isActive: boolean;
    } | null;
    tenants: Array<{
      id: string;
      uuid?: string;
      name: string;
      slug: string;
      schemaName: string;
      isActive: boolean;
      primaryDomain: string;
    }>;
    users: Array<{
      id: number;
      email: string;
      displayName: string;
      isPlatformAdmin: boolean;
      isActive: boolean;
      lastLoginAt: string;
      tenantMemberships: Array<{ tenantSlug: string; role: Role; isActive: boolean }>;
    }>;
    integrations: Array<Record<string, unknown>>;
    globalSkills: Array<Record<string, unknown>>;
    tenantIntegrations: Array<Record<string, unknown>>;
    pluginSync: { syncedCount: number; invalid: Array<{ manifestPath: string; error: string }> };
    plugins: Array<Record<string, unknown>>;
    tenantPlugins: Array<Record<string, unknown>>;
    tenantPluginAssignments: Array<Record<string, unknown>>;
    notificationSettings: Record<string, unknown>;
  };
  tenant: {
    tenant: string;
    tenantUuid: string;
    workspace: string;
    workspaceUuid: string;
    role: Role;
    currentUser: { id: number; email: string; displayName: string };
    users: Array<Record<string, unknown>>;
    skills: Record<string, unknown>;
    workspaces: Array<Record<string, unknown>>;
    automations: Record<string, unknown>;
    integrations: Array<Record<string, unknown>>;
    tenantIntegrations: Array<Record<string, unknown>>;
    pluginSync: { syncedCount: number; invalid: Array<{ manifestPath: string; error: string }> };
    plugins: Array<Record<string, unknown>>;
    tenantPlugins: Array<Record<string, unknown>>;
    tenantPluginAssignments: Array<Record<string, unknown>>;
  };
};

const PLATFORM_ACCESS = "mock-platform-access";
const PLATFORM_REFRESH = "mock-platform-refresh";
const TENANT_ACCESS = "mock-tenant-access";
const TENANT_REFRESH = "mock-tenant-refresh";

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function iso(minutesAgo = 0): string {
  return new Date(Date.now() - minutesAgo * 60_000).toISOString();
}

function createInitialState(): MockState {
  const integrations = [
    {
      id: 1,
      key: "hubspot",
      name: "HubSpot",
      category: "crm",
      baseUrl: "https://api.hubapi.com",
      openapiUrl: "https://api.hubapi.com/api-catalog-public/v1/apis/crm/v3/openapi",
      defaultAuthType: "bearer",
      authScope: "tenant",
      authConfigSchema: {
        type: "object",
        properties: {
          api_key: { type: "string", title: "API key" },
        },
      },
      globalAuthConfig: {},
      globalAuthConfigured: false,
      assistantDocsMarkdown: "Primary CRM integration used by sales teams.",
      defaultHeaders: {},
      isActive: true,
      metadata: {},
    },
    {
      id: 2,
      key: "gmail",
      name: "Gmail",
      category: "communications",
      baseUrl: "https://gmail.googleapis.com",
      openapiUrl: "",
      defaultAuthType: "oauth2",
      authScope: "user",
      authConfigSchema: {
        type: "object",
        properties: {
          client_id: { type: "string", title: "Client ID" },
          client_secret: { type: "string", title: "Client Secret" },
        },
      },
      globalAuthConfig: {},
      globalAuthConfigured: false,
      assistantDocsMarkdown: "Mailbox access for support and customer ops.",
      defaultHeaders: {},
      isActive: true,
      metadata: {},
    },
  ];

  const globalSkills = [
    {
      id: 1,
      key: "summarize_deal",
      name: "Summarize deal",
      description: "Summarizes CRM deal state for operators.",
      bodyMarkdown: "Use current deal timeline and recent notes.",
      isActive: true,
      isGlobal: true,
      scope: "global",
      createdByEmail: "martin@moio.ai",
      updatedAt: iso(55),
    },
    {
      id: 2,
      key: "plan_followup",
      name: "Plan follow-up",
      description: "Drafts next steps and follow-up copy.",
      bodyMarkdown: "Create a concise follow-up proposal.",
      isActive: true,
      isGlobal: true,
      scope: "global",
      createdByEmail: "martin@moio.ai",
      updatedAt: iso(45),
    },
  ];

  const tenants = [
    {
      id: "tenant-acme",
      uuid: "tenant-acme",
      name: "Acme Corp",
      slug: "acme",
      schemaName: "acme",
      isActive: true,
      primaryDomain: "acme.devcrm.moio.ai",
    },
    {
      id: "tenant-orbit",
      uuid: "tenant-orbit",
      name: "Orbit Logistics",
      slug: "orbit",
      schemaName: "orbit",
      isActive: true,
      primaryDomain: "orbit.devcrm.moio.ai",
    },
  ];

  const plugins = [
    {
      pluginId: "salesforce-sync",
      name: "Salesforce Sync",
      version: "0.8.1",
      sourceType: "bundle",
      bundlePath: "/plugins/salesforce-sync.zip",
      manifestPath: "/plugins/salesforce-sync/manifest.json",
      capabilities: ["crm.sync", "contacts.read"],
      permissions: ["network", "storage"],
      manifest: {
        id: "salesforce-sync",
        name: "Salesforce Sync",
        configSchema: {
          type: "object",
          properties: {
            baseUrl: { type: "string", title: "Base URL" },
            syncWindowMinutes: { type: "number", title: "Sync Window (minutes)", default: 15 },
          },
        },
      },
      isValidated: true,
      isPlatformApproved: true,
      validationError: "",
      updatedAt: iso(30),
    },
    {
      pluginId: "ops-notifier",
      name: "Ops Notifier",
      version: "1.1.0",
      sourceType: "bundle",
      bundlePath: "/plugins/ops-notifier.zip",
      manifestPath: "/plugins/ops-notifier/manifest.json",
      capabilities: ["notifications.send"],
      permissions: ["notifications"],
      manifest: {
        id: "ops-notifier",
        name: "Ops Notifier",
        configSchema: {
          type: "object",
          properties: {
            channel: { type: "string", title: "Channel", enum: ["slack", "email"] },
          },
        },
      },
      isValidated: true,
      isPlatformApproved: false,
      validationError: "",
      updatedAt: iso(25),
    },
  ];

  return {
    platform: {
      tenantsEnabled: true,
      publicSchema: "public",
      currentUser: {
        id: 1,
        email: "martin@moio.ai",
        displayName: "Martin Otero",
        isPlatformAdmin: true,
        isActive: true,
      },
      tenants,
      users: [
        {
          id: 1,
          email: "martin@moio.ai",
          displayName: "Martin Otero",
          isPlatformAdmin: true,
          isActive: true,
          lastLoginAt: iso(4),
          tenantMemberships: [
            { tenantSlug: "acme", role: "admin", isActive: true },
            { tenantSlug: "orbit", role: "admin", isActive: true },
          ],
        },
        {
          id: 2,
          email: "ops@acme.ai",
          displayName: "Acme Ops",
          isPlatformAdmin: false,
          isActive: true,
          lastLoginAt: iso(120),
          tenantMemberships: [{ tenantSlug: "acme", role: "member", isActive: true }],
        },
      ],
      integrations,
      globalSkills,
      tenantIntegrations: [
        {
          id: 1,
          tenantSlug: "acme",
          integrationKey: "hubspot",
          authScope: "tenant",
          isEnabled: true,
          notes: "Primary CRM auth configured",
          assistantDocsOverride: "",
          tenantAuthConfigured: true,
          tenantAuthConfig: { api_key: "configured" },
          updatedAt: iso(22),
        },
      ],
      pluginSync: { syncedCount: plugins.length, invalid: [] },
      plugins,
      tenantPlugins: [
        {
          tenantSlug: "acme",
          pluginId: "salesforce-sync",
          isEnabled: true,
          pluginConfig: { baseUrl: "https://acme.salesforce.com", syncWindowMinutes: 15 },
          notes: "Enabled for enterprise sync",
          updatedAt: iso(15),
        },
      ],
      tenantPluginAssignments: [
        {
          tenantSlug: "acme",
          pluginId: "salesforce-sync",
          assignmentType: "role",
          role: "admin",
          userId: 0,
          userEmail: "",
          isActive: true,
          notes: "Admins only",
          updatedAt: iso(14),
        },
      ],
      notificationSettings: {
        title: "Moio",
        iconUrl: "/pwa-icon.svg",
        badgeUrl: "/pwa-icon.svg",
        requireInteraction: false,
        renotify: false,
        silent: false,
        testTitle: "Moio Preview",
        testBody: "This is a mocked platform admin preview.",
      },
    },
    tenant: {
      tenant: "acme",
      tenantUuid: "tenant-acme",
      workspace: "main",
      workspaceUuid: "workspace-main",
      role: "admin",
      currentUser: {
        id: 1,
        email: "martin@moio.ai",
        displayName: "Martin Otero",
      },
      users: [
        {
          id: 11,
          email: "owner@acme.ai",
          displayName: "Acme Owner",
          isActive: true,
          role: "admin",
          membershipActive: true,
        },
        {
          id: 12,
          email: "success@acme.ai",
          displayName: "Customer Success",
          isActive: true,
          role: "member",
          membershipActive: true,
        },
      ],
      skills: {
        tenant: "acme",
        role: "admin",
        workspace: "main",
        enabledSkillKeys: ["summarize_deal", "plan_followup"],
        globalSkills,
        tenantSkills: [
          {
            id: 101,
            key: "acme_discount_policy",
            name: "Acme discount policy",
            description: "Guides discount approvals for Acme.",
            bodyMarkdown: "Escalate discounts over 12%.",
            isActive: true,
            isGlobal: false,
            scope: "tenant",
            createdByEmail: "owner@acme.ai",
            updatedAt: iso(32),
          },
        ],
        mergedSkills: [
          ...globalSkills,
          {
            id: 101,
            key: "acme_discount_policy",
            name: "Acme discount policy",
            description: "Guides discount approvals for Acme.",
            bodyMarkdown: "Escalate discounts over 12%.",
            isActive: true,
            isGlobal: false,
            scope: "tenant",
            createdByEmail: "owner@acme.ai",
            updatedAt: iso(32),
          },
        ],
        enabledSkills: globalSkills,
      },
      workspaces: [
        {
          id: "workspace-main",
          uuid: "workspace-main",
          slug: "main",
          name: "Main",
          displayName: "Main Workspace",
          specialtyPrompt: "Handle sales operations with concise summaries.",
          enabledSkillKeys: ["summarize_deal", "plan_followup"],
          defaultVendor: "openai",
          defaultModel: "gpt-5-mini",
          defaultThinking: "default",
          defaultVerbosity: "minimal",
          isActive: true,
        },
        {
          id: "workspace-support",
          uuid: "workspace-support",
          slug: "support",
          name: "Support",
          displayName: "Support Desk",
          specialtyPrompt: "Resolve customer tickets and triage escalations.",
          enabledSkillKeys: ["plan_followup"],
          defaultVendor: "openai",
          defaultModel: "gpt-5-mini",
          defaultThinking: "default",
          defaultVerbosity: "detailed",
          isActive: true,
        },
      ],
      automations: {
        workspace: "main",
        workspaceId: "workspace-main",
        templates: [
          {
            id: "template-daily-summary",
            key: "daily-summary",
            name: "Daily Summary",
            description: "Morning account summary for operators.",
            instructionsMarkdown: "Summarize yesterday pipeline movement.",
            examplePrompt: "Summarize open risks for key accounts.",
            defaultMessage: "Prepare a concise morning summary.",
            icon: "calendar",
            category: "operations",
            isActive: true,
            isRecommended: true,
            createdByEmail: "martin@moio.ai",
            metadata: {},
            updatedAt: iso(80),
          },
        ],
        instances: [
          {
            id: "instance-daily-summary-main",
            workspaceId: "workspace-main",
            workspaceSlug: "main",
            templateId: "template-daily-summary",
            templateKey: "daily-summary",
            name: "Daily Summary / Main",
            message: "Generate a morning operational summary.",
            executionMode: "worktree",
            scheduleType: "daily",
            scheduleTime: "08:30",
            intervalMinutes: 0,
            weekdays: ["MO", "TU", "WE", "TH", "FR"],
            isActive: true,
            runInProgress: false,
            runStartedAt: "",
            lastRunStatus: "success",
            lastRunId: "run-123",
            lastRunAt: iso(600),
            nextRunAt: iso(-600),
            createdByEmail: "martin@moio.ai",
            metadata: {},
            updatedAt: iso(90),
          },
        ],
        runLogs: [
          {
            id: "runlog-1",
            automationId: "instance-daily-summary-main",
            runId: "run-123",
            sessionKey: "sess-1",
            status: "success",
            startedAt: iso(620),
            finishedAt: iso(618),
            summary: "Summary generated and posted to ops channel.",
          },
        ],
      },
      integrations,
      tenantIntegrations: [
        {
          id: 1,
          tenantSlug: "acme",
          integrationKey: "hubspot",
          authScope: "tenant",
          isEnabled: true,
          notes: "Tenant-level token configured",
          assistantDocsOverride: "",
          tenantAuthConfigured: true,
          tenantAuthConfig: { api_key: "configured" },
          updatedAt: iso(10),
        },
      ],
      pluginSync: { syncedCount: plugins.length, invalid: [] },
      plugins,
      tenantPlugins: [
        {
          tenantSlug: "acme",
          pluginId: "salesforce-sync",
          isEnabled: true,
          pluginConfig: { baseUrl: "https://acme.salesforce.com", syncWindowMinutes: 15 },
          notes: "Enabled in preview",
          updatedAt: iso(5),
        },
      ],
      tenantPluginAssignments: [
        {
          tenantSlug: "acme",
          pluginId: "salesforce-sync",
          assignmentType: "role",
          role: "admin",
          userId: 0,
          userEmail: "",
          isActive: true,
          notes: "Admins only",
          updatedAt: iso(3),
        },
      ],
    },
  };
}

let mockState: MockState = createInitialState();
let seeded = false;

function platformPayload() {
  return clone(mockState.platform);
}

function pluginAdminPayload() {
  return clone({
    sync: mockState.platform.pluginSync,
    plugins: mockState.platform.plugins,
    tenantPlugins: mockState.platform.tenantPlugins,
    tenantPluginAssignments: mockState.platform.tenantPluginAssignments,
  });
}

function tenantPayload(workspace?: string) {
  const selectedWorkspace = String(workspace || mockState.tenant.workspace || "main").trim().toLowerCase() || "main";
  const workspaceRow =
    mockState.tenant.workspaces.find((row) => String(row.slug || "").trim().toLowerCase() === selectedWorkspace) ||
    mockState.tenant.workspaces[0];
  const payload = clone(mockState.tenant);
  payload.workspace = String(workspaceRow?.slug || selectedWorkspace);
  payload.workspaceUuid = String(workspaceRow?.id || payload.workspaceUuid || "");
  payload.skills.workspace = payload.workspace;
  payload.skills.enabledSkillKeys = Array.isArray(workspaceRow?.enabledSkillKeys)
    ? clone(workspaceRow.enabledSkillKeys as string[])
    : [];
  payload.automations.workspace = payload.workspace;
  payload.automations.workspaceId = payload.workspaceUuid;
  const automationInstances = Array.isArray(payload.automations.instances)
    ? (payload.automations.instances as Array<Record<string, unknown>>)
    : [];
  payload.automations.instances = automationInstances.filter(
    (row: Record<string, unknown>) =>
      String(row.workspaceSlug || "").trim().toLowerCase() === payload.workspace
  ) as typeof payload.automations.instances;
  return payload;
}

function tenantPluginPayload() {
  return clone({
    tenant: mockState.tenant.tenant,
    role: mockState.tenant.role,
    isTenantAdmin: mockState.tenant.role === "admin",
    sync: mockState.tenant.pluginSync,
    plugins: mockState.tenant.plugins,
    tenantPlugins: mockState.tenant.tenantPlugins,
    tenantPluginAssignments: mockState.tenant.tenantPluginAssignments,
  });
}

function publicAuthPayload() {
  return clone({
    tokens: { access: TENANT_ACCESS, refresh: TENANT_REFRESH },
    platformTokens: { access: PLATFORM_ACCESS, refresh: PLATFORM_REFRESH },
    user: {
      id: 1,
      email: "martin@moio.ai",
      displayName: "Martin Otero",
    },
    capabilities: {
      tenantConsole: true,
      platformAdmin: true,
    },
    tenants: JSON.parse(String(localStorage.getItem("moio_public_tenants") || "[]")),
    plan: "preview",
  });
}

function ok(payload: unknown, init?: ResponseInit) {
  return new Response(JSON.stringify({ ok: true, payload }), {
    status: 200,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
    ...init,
  });
}

function parseJsonBody(init?: RequestInit): Record<string, unknown> {
  if (!init?.body || typeof init.body !== "string") return {};
  try {
    const parsed = JSON.parse(init.body);
    return parsed && typeof parsed === "object" ? (parsed as Record<string, unknown>) : {};
  } catch {
    return {};
  }
}

function normalizeUrl(input: RequestInfo | URL): URL {
  if (typeof input === "string") return new URL(input, window.location.origin);
  if (input instanceof URL) return new URL(input.toString(), window.location.origin);
  return new URL(input.url, window.location.origin);
}

function seedLegacySessionStorage() {
  if (seeded) return;
  try {
    localStorage.setItem("platform_admin_access_token", PLATFORM_ACCESS);
    localStorage.setItem("platform_admin_refresh_token", PLATFORM_REFRESH);
    localStorage.setItem("moio_public_tokens", JSON.stringify({ access: TENANT_ACCESS, refresh: TENANT_REFRESH }));
    localStorage.setItem("moio_tenant_session_tokens", JSON.stringify({ access: TENANT_ACCESS, refresh: TENANT_REFRESH }));
    localStorage.setItem(
      "moio_tenant_session_context",
      JSON.stringify({
        tenantId: mockState.tenant.tenantUuid,
        tenantSlug: mockState.tenant.tenant,
        tenantSchema: mockState.tenant.tenant,
        workspaceId: mockState.tenant.workspaceUuid,
        workspaceSlug: mockState.tenant.workspace,
      })
    );
    localStorage.setItem(
      "moio_public_tenants",
      JSON.stringify(
        mockState.platform.tenants.map((tenant) => ({
          uuid: tenant.uuid || tenant.id,
          id: tenant.uuid || tenant.id,
          slug: tenant.slug,
          schemaName: tenant.schemaName,
          name: tenant.name,
          isActive: tenant.isActive,
          role: tenant.slug === mockState.tenant.tenant ? "admin" : "member",
          workspaces:
            tenant.slug === mockState.tenant.tenant
              ? mockState.tenant.workspaces.map((workspace) => ({
                  uuid: String(workspace.id || workspace.uuid || ""),
                  id: String(workspace.id || workspace.uuid || ""),
                  slug: String(workspace.slug || ""),
                  name: String(workspace.displayName || workspace.name || workspace.slug || ""),
                }))
              : [
                  {
                    uuid: `${tenant.slug}-main`,
                    id: `${tenant.slug}-main`,
                    slug: "main",
                    name: "Main",
                  },
                ],
        }))
      )
    );
    localStorage.setItem(
      "moio_public_user",
      JSON.stringify({
        id: 1,
        email: "martin@moio.ai",
        displayName: "Martin Otero",
      })
    );
    seeded = true;
  } catch {
    // ignore storage issues in preview mode
  }
}

export function ensureLegacyAdminMockPreviewState() {
  if (typeof window === "undefined") return;
  mockState = createInitialState();
  seedLegacySessionStorage();
}

function upsertById<T extends Record<string, unknown>>(rows: T[], idKey: keyof T, next: T): T[] {
  const needle = String(next[idKey] || "");
  if (!needle) return rows;
  const filtered = rows.filter((row) => String(row[idKey] || "") !== needle);
  return [...filtered, next];
}

function handlePlatformMutation(path: string, init?: RequestInit): Response {
  const body = parseJsonBody(init);

  if (path === "/api/platform/tenants") {
    const slug = String(body.slug || "").trim().toLowerCase();
    const next = {
      id: String(body.id || `tenant-${slug || Date.now()}`),
      uuid: String(body.id || `tenant-${slug || Date.now()}`),
      name: String(body.name || slug || "Tenant"),
      slug,
      schemaName: String(body.schemaName || slug || "tenant").trim().toLowerCase(),
      isActive: Boolean(body.isActive ?? true),
      primaryDomain: String(body.primaryDomain || `${slug}.devcrm.moio.ai`),
    };
    mockState.platform.tenants = upsertById(mockState.platform.tenants, "id", next);
    return ok(platformPayload());
  }

  if (path === "/api/platform/tenants/delete") {
    const id = String(body.id || "").trim();
    const slug = String(body.slug || "").trim().toLowerCase();
    mockState.platform.tenants = mockState.platform.tenants.filter(
      (row) => String(row.id || "") !== id && String(row.slug || "").trim().toLowerCase() !== slug
    );
    return ok(platformPayload());
  }

  if (path === "/api/platform/users") {
    const id = Number(body.id || 0) || Date.now();
    const next = {
      id,
      email: String(body.email || `user-${id}@moio.ai`),
      displayName: String(body.displayName || body.email || "User"),
      isPlatformAdmin: Boolean(body.isPlatformAdmin),
      isActive: Boolean(body.isActive ?? true),
      lastLoginAt: iso(0),
      tenantMemberships: Array.isArray(body.tenantMemberships)
        ? (body.tenantMemberships as Array<{ tenantSlug: string; role: Role; isActive: boolean }>)
        : [],
    };
    mockState.platform.users = upsertById(mockState.platform.users, "id", next);
    return ok(platformPayload());
  }

  if (path === "/api/platform/users/delete") {
    const id = Number(body.id || 0);
    const email = String(body.email || "").trim().toLowerCase();
    mockState.platform.users = mockState.platform.users.filter(
      (row) => row.id !== id && String(row.email || "").trim().toLowerCase() !== email
    );
    return ok(platformPayload());
  }

  if (path === "/api/platform/integrations") {
    const key = String(body.key || "").trim().toLowerCase();
    const next = {
      id: Number((mockState.platform.integrations.find((row) => String(row.key || "") === key) as any)?.id || Date.now()),
      key,
      name: String(body.name || key),
      category: String(body.category || "general"),
      baseUrl: String(body.baseUrl || ""),
      openapiUrl: String(body.openapiUrl || ""),
      defaultAuthType: String(body.defaultAuthType || "bearer"),
      authScope: String(body.authScope || "tenant"),
      authConfigSchema: body.authConfigSchema || {},
      globalAuthConfig: body.globalAuthConfig || {},
      assistantDocsMarkdown: String(body.assistantDocsMarkdown || ""),
      defaultHeaders: (body.defaultHeaders as Record<string, string>) || {},
      isActive: Boolean(body.isActive ?? true),
      metadata: {},
    };
    mockState.platform.integrations = upsertById(mockState.platform.integrations, "key", next);
    mockState.tenant.integrations = clone(mockState.platform.integrations);
    return ok(platformPayload());
  }

  if (path === "/api/platform/integrations/delete") {
    const key = String(body.key || "").trim().toLowerCase();
    mockState.platform.integrations = mockState.platform.integrations.filter(
      (row) => String(row.key || "").trim().toLowerCase() !== key
    );
    mockState.tenant.integrations = clone(mockState.platform.integrations);
    return ok(platformPayload());
  }

  if (path === "/api/platform/skills") {
    const key = String(body.key || "").trim().toLowerCase();
    const next = {
      id: Number((mockState.platform.globalSkills.find((row) => String(row.key || "") === key) as any)?.id || Date.now()),
      key,
      name: String(body.name || key),
      description: String(body.description || ""),
      bodyMarkdown: String(body.bodyMarkdown || ""),
      isActive: Boolean(body.isActive ?? true),
      isGlobal: true,
      scope: "global",
      createdByEmail: "martin@moio.ai",
      updatedAt: iso(0),
    };
    mockState.platform.globalSkills = upsertById(mockState.platform.globalSkills, "key", next);
    return ok(platformPayload());
  }

  if (path === "/api/platform/skills/delete") {
    const key = String(body.key || "").trim().toLowerCase();
    mockState.platform.globalSkills = mockState.platform.globalSkills.filter(
      (row) => String(row.key || "").trim().toLowerCase() !== key
    );
    return ok(platformPayload());
  }

  if (path === "/api/platform/tenant-integrations") {
    const tenantSlug = String(body.tenantSlug || "").trim().toLowerCase();
    const integrationKey = String(body.integrationKey || "").trim().toLowerCase();
    const next = {
      id: Number(Date.now()),
      tenantSlug,
      integrationKey,
      authScope: "tenant",
      isEnabled: Boolean(body.isEnabled ?? true),
      notes: String(body.notes || ""),
      assistantDocsOverride: String(body.assistantDocsOverride || ""),
      tenantAuthConfigured: Boolean(body.tenantAuthConfig),
      tenantAuthConfig: (body.tenantAuthConfig as Record<string, unknown>) || {},
      updatedAt: iso(0),
    };
    mockState.platform.tenantIntegrations = mockState.platform.tenantIntegrations.filter(
      (row) =>
        !(
          String(row.tenantSlug || "").trim().toLowerCase() === tenantSlug &&
          String(row.integrationKey || "").trim().toLowerCase() === integrationKey
        )
    );
    mockState.platform.tenantIntegrations.push(next);
    if (tenantSlug === mockState.tenant.tenant) {
      mockState.tenant.tenantIntegrations = clone(
        mockState.platform.tenantIntegrations.filter(
          (row) => String(row.tenantSlug || "").trim().toLowerCase() === tenantSlug
        )
      );
    }
    return ok(platformPayload());
  }

  if (path === "/api/platform/notifications") {
    mockState.platform.notificationSettings = { ...mockState.platform.notificationSettings, ...(body.settings || {}) };
    return ok(platformPayload());
  }

  if (path === "/api/platform/plugins") {
    if (init?.body instanceof FormData) {
      const pluginId = `uploaded-${Date.now()}`;
      mockState.platform.plugins.push({
        pluginId,
        name: "Uploaded Plugin",
        version: "0.0.1",
        sourceType: "bundle",
        bundlePath: `/plugins/${pluginId}.zip`,
        manifestPath: `/plugins/${pluginId}/manifest.json`,
        capabilities: [],
        permissions: [],
        manifest: { id: pluginId, name: "Uploaded Plugin" },
        isValidated: true,
        isPlatformApproved: false,
        validationError: "",
        updatedAt: iso(0),
      });
      mockState.platform.pluginSync.syncedCount = mockState.platform.plugins.length;
      mockState.tenant.plugins = clone(mockState.platform.plugins);
      mockState.tenant.pluginSync.syncedCount = mockState.tenant.plugins.length;
      return ok(pluginAdminPayload());
    }

    const pluginId = String(body.pluginId || "").trim().toLowerCase();
    const selected = mockState.platform.plugins.find(
      (row) => String(row.pluginId || "").trim().toLowerCase() === pluginId
    );
    if (selected) {
      selected.isPlatformApproved = Boolean(body.isPlatformApproved ?? selected.isPlatformApproved);
      selected.updatedAt = iso(0);
    }
    mockState.tenant.plugins = clone(mockState.platform.plugins);
    return ok(pluginAdminPayload());
  }

  return ok(platformPayload());
}

function handleTenantMutation(path: string, init?: RequestInit): Response {
  const body = parseJsonBody(init);

  if (path === "/api/tenant/plugins") {
    const pluginId = String(body.pluginId || "").trim().toLowerCase();
    mockState.tenant.tenantPlugins = mockState.tenant.tenantPlugins.filter(
      (row) =>
        !(
          String(row.pluginId || "").trim().toLowerCase() === pluginId &&
          String(row.tenantSlug || "").trim().toLowerCase() === mockState.tenant.tenant
        )
    );
    mockState.tenant.tenantPlugins.push({
      tenantSlug: mockState.tenant.tenant,
      pluginId,
      isEnabled: Boolean(body.isEnabled),
      notes: String(body.notes || ""),
      pluginConfig: (body.pluginConfig as Record<string, unknown>) || {},
      updatedAt: iso(0),
    });
    mockState.tenant.tenantPluginAssignments = Array.isArray(body.assignments)
      ? (body.assignments as Array<Record<string, unknown>>).map((row) => ({
          tenantSlug: mockState.tenant.tenant,
          pluginId,
          assignmentType: String(row.assignmentType || "role"),
          role: String(row.role || ""),
          userId: Number(row.userId || 0),
          userEmail: String(row.userEmail || ""),
          isActive: Boolean(row.isActive ?? true),
          notes: String(row.notes || ""),
          updatedAt: iso(0),
        }))
      : mockState.tenant.tenantPluginAssignments;
    return ok(tenantPluginPayload());
  }

  return ok({});
}

function handleMockRequest(input: RequestInfo | URL, init?: RequestInit): Response | null {
  const url = normalizeUrl(input);
  const method = String(init?.method || (typeof input !== "string" && "method" in input ? input.method : "GET")).toUpperCase();
  const path = url.pathname;

  if (path === "/api/platform/bootstrap" && method === "GET") {
    return ok(platformPayload());
  }
  if (path === "/api/platform/plugins" && method === "GET") {
    return ok(pluginAdminPayload());
  }
  if (path.startsWith("/api/platform/") && method !== "GET") {
    return handlePlatformMutation(path, init);
  }

  if (path === "/api/tenant/bootstrap" && method === "GET") {
    const workspace = url.searchParams.get("workspace") || mockState.tenant.workspace;
    return ok(tenantPayload(workspace));
  }
  if (path === "/api/tenant/plugins" && method === "GET") {
    return ok(tenantPluginPayload());
  }
  if (path.startsWith("/api/tenant/") && method !== "GET") {
    return handleTenantMutation(path, init);
  }

  if (path === "/api/auth/refresh" && method === "POST") {
    return ok({ access: PLATFORM_ACCESS, refresh: PLATFORM_REFRESH });
  }
  if (path === "/api/auth/logout" && method === "POST") {
    return ok({ loggedOut: true });
  }
  if (path === "/api/public/login" && method === "POST") {
    return ok(publicAuthPayload());
  }
  if (path === "/api/public/join" && method === "POST") {
    return ok(publicAuthPayload());
  }
  if (path === "/api/public/context" && method === "GET") {
    return ok(publicAuthPayload());
  }
  if (path === "/api/public/tenant-session" && method === "POST") {
    return ok({
      tokens: { access: TENANT_ACCESS, refresh: TENANT_REFRESH },
      tenant: {
        id: mockState.tenant.tenantUuid,
        slug: mockState.tenant.tenant,
        schemaName: mockState.tenant.tenant,
      },
    });
  }

  return null;
}

export function useLegacyAdminMockPreview() {
  useEffect(() => {
    ensureLegacyAdminMockPreviewState();

    const originalFetch = window.fetch.bind(window);
    window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const mocked = handleMockRequest(input, init);
      if (mocked) {
        return mocked;
      }
      return originalFetch(input, init);
    };

    return () => {
      window.fetch = originalFetch;
    };
  }, []);
}
