// @ts-nocheck
import type { TenantBootstrapPayload, TenantPluginState } from "../types";
import { getAccessToken, getApiBaseUrl } from "@/lib/api";
import {
  clearTenantConsoleSession,
  getActiveTenantSessionContext,
  setActiveTenantSessionContext,
} from "./publicAuthApi";
import { resolveApiBase } from "./runtimeConfig";

const TENANT_API_BASE = resolveApiBase("/api/tenant", import.meta.env.VITE_TENANT_ADMIN_API_BASE);
const PUBLIC_USER_STORAGE_KEY = "moio_public_user";
const PUBLIC_TENANTS_STORAGE_KEY = "moio_public_tenants";

/** Map GET /api/v1/bootstrap/ response to TenantBootstrapPayload (no /api/tenant/ backend). */
async function fetchV1BootstrapAndMap(workspace: string): Promise<TenantBootstrapPayload> {
  const base = (getApiBaseUrl() || "").replace(/\/+$/, "");
  const path = /\/api\/v1\/?$/.test(base) ? "bootstrap/" : "v1/bootstrap/";
  const url = `${base}/${path}`.replace(/([^:/])\/\/+/, "$1/");
  const access = (getAccessToken() || "").trim();
  if (!access) {
    throw new TenantAdminApiError("Authentication required.", 401, "auth_required");
  }
  const res = await fetch(url, {
    method: "GET",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${access}`,
    },
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const message = data?.detail || (typeof data?.message === "string" ? data.message : "") || `Request failed (${res.status})`;
    throw new TenantAdminApiError(message, res.status, "request_failed");
  }
  const user = data?.user ?? {};
  const org = user?.organization ?? {};
  const tenantData = data?.tenant ?? {};
  const slug = (org?.schema_name || org?.subdomain || tenantData?.id || org?.id || "main").toString().trim().toLowerCase() || "main";
  const roleRaw = (user?.role || "member").toString().toLowerCase();
  const role: "admin" | "member" | "viewer" =
    roleRaw === "tenant_admin" || roleRaw === "platform_admin" ? "admin" : roleRaw === "viewer" ? "viewer" : "member";
  const payload: TenantBootstrapPayload = {
    tenant: slug,
    tenantUuid: String(org?.id ?? tenantData?.id ?? ""),
    workspace: (workspace || "main").trim().toLowerCase() || "main",
    workspaceUuid: "",
    role,
    currentUser: {
      id: Number(user?.id) || 0,
      email: String(user?.email ?? ""),
      displayName: String(user?.full_name ?? user?.username ?? user?.email ?? ""),
    },
    users: [],
    skills: {
      tenant: slug,
      role,
      workspace: (workspace || "main").trim().toLowerCase() || "main",
      enabledSkillKeys: [],
      globalSkills: [],
      tenantSkills: [],
      mergedSkills: [],
      enabledSkills: [],
    },
    workspaces: [],
    automations: {
      workspace: (workspace || "main").trim().toLowerCase() || "main",
      workspaceId: "",
      templates: [],
      instances: [],
      runLogs: [],
    },
    integrations: [],
    tenantIntegrations: [],
    pluginSync: { syncedCount: 0, invalid: [] },
    plugins: [],
    tenantPlugins: [],
    tenantPluginAssignments: [],
    notificationSettings: data?.notification_settings ?? undefined,
  };
  return payload;
}

async function authMeOk(access: string): Promise<boolean> {
  const token = String(access || "").trim();
  if (!token) return false;
  const base = (getApiBaseUrl() || "").replace(/\/+$/, "");
  const path = /\/api\/v1\/?$/.test(base) ? "auth/me/" : "v1/auth/me/";
  const url = `${base}/${path}`.replace(/([^:/])\/\/+/, "$1/");
  try {
    const res = await fetch(url, {
      method: "GET",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
    });
    return res.ok;
  } catch {
    return false;
  }
}

export class TenantAdminApiError extends Error {
  status: number;
  code: string;

  constructor(message: string, status = 500, code = "request_failed") {
    super(message);
    this.status = status;
    this.code = code;
  }
}

type TenantRequestContext = {
  workspace: string;
  workspaceId: string;
};

function clearTenantTokens(): void {
  try {
    localStorage.removeItem(PUBLIC_USER_STORAGE_KEY);
  } catch {
    // Ignore local storage failures.
  }
  clearTenantConsoleSession();
}

function syncTenantWorkspacesInStorage(payload: TenantBootstrapPayload): void {
  try {
    const tenantSlug = String(payload.tenant || "").trim().toLowerCase();
    const tenantUuid = String(payload.tenantUuid || "").trim();
    if (!tenantSlug && !tenantUuid) return;

    const raw = localStorage.getItem(PUBLIC_TENANTS_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    const tenants = Array.isArray(parsed) ? parsed : [];
    const idx = tenants.findIndex((row) => {
      const item = row && typeof row === "object" ? (row as Record<string, unknown>) : {};
      const uuid = String(item.uuid ?? item.id ?? "").trim();
      const slug = String(item.slug ?? "").trim().toLowerCase();
      const schemaName = String(item.schemaName ?? "").trim().toLowerCase();
      if (tenantUuid && uuid === tenantUuid) return true;
      if (tenantSlug && (slug === tenantSlug || schemaName === tenantSlug)) return true;
      return false;
    });
    if (idx < 0) return;

    const workspaceRows = Array.isArray(payload.workspaces) ? payload.workspaces : [];
    const normalizedWorkspaces = workspaceRows
      .map((entry) => {
        const slug = String(entry?.slug ?? "").trim().toLowerCase();
        if (!slug) return null;
        const uuid = String(entry?.id ?? "").trim();
        return {
          uuid,
          slug,
          name: String(entry?.name ?? entry?.displayName ?? slug).trim() || slug,
        };
      })
      .filter((entry): entry is { uuid: string; slug: string; name: string } => Boolean(entry));

    const current = tenants[idx] && typeof tenants[idx] === "object" ? (tenants[idx] as Record<string, unknown>) : {};
    tenants[idx] = {
      ...current,
      workspaces: normalizedWorkspaces,
    };
    localStorage.setItem(PUBLIC_TENANTS_STORAGE_KEY, JSON.stringify(tenants));
  } catch {
    // Ignore local storage parse/write failures.
  }
}

function currentTenantRequestContext(): TenantRequestContext {
  const activeTenantContext = getActiveTenantSessionContext();
  if (typeof window === "undefined") {
    return { workspace: "", workspaceId: "" };
  }
  const query = new URLSearchParams(window.location.search);
  return {
    workspace: String(query.get("workspace") || activeTenantContext?.workspaceSlug || "").trim(),
    workspaceId: String(query.get("workspaceId") || activeTenantContext?.workspaceId || "").trim(),
  };
}

async function request<TPayload>(
  path: string,
  options: RequestInit & {
    bodyJson?: unknown;
    query?: Record<string, string>;
  } = {}
): Promise<TPayload> {
  const access = String(getAccessToken() ?? "").trim();
  if (!access) {
    throw new TenantAdminApiError("Authentication required.", 401, "auth_required");
  }

  const headers: HeadersInit = {
    "Content-Type": "application/json",
    Authorization: `Bearer ${access}`,
    ...(options.headers || {}),
  };
  const context = currentTenantRequestContext();
  const headerMap = headers as Record<string, string>;
  if (context.workspace) headerMap["X-Workspace"] = context.workspace;
  if (context.workspaceId) headerMap["X-Workspace-Id"] = context.workspaceId;

  const query = new URLSearchParams();
  if (options.query) {
    Object.entries(options.query).forEach(([key, value]) => {
      if (String(value || "").trim()) query.set(key, value);
    });
  }
  const querySuffix = query.toString() ? `?${query.toString()}` : "";
  const response = await fetch(`${TENANT_API_BASE}${path}${querySuffix}`, {
    method: options.method || "GET",
    credentials: "same-origin",
    headers,
    body: options.bodyJson !== undefined ? JSON.stringify(options.bodyJson) : options.body,
  });
  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    const message = data?.error?.message || data?.detail || `Request failed (${response.status})`;
    const code = data?.error?.code || "request_failed";
    throw new TenantAdminApiError(message, response.status, code);
  }

  return (data?.payload ?? data ?? {}) as TPayload;
}

export async function tenantBootstrap(workspace = "main"): Promise<TenantBootstrapPayload> {
  const context = currentTenantRequestContext();
  const mainAccess = (getAccessToken() ?? "").trim();
  if (!mainAccess) {
    throw new TenantAdminApiError(
      "Authentication required. Please sign in again.",
      401,
      "auth_required",
    );
  }

  try {
    const payload = await request<TenantBootstrapPayload>("/bootstrap", {
      query: { workspace, workspaceId: context.workspaceId },
    });
    setActiveTenantSessionContext({
      ...(getActiveTenantSessionContext() || {
        tenantId: "",
        tenantSlug: "",
        tenantSchema: "",
        workspaceId: "",
        workspaceSlug: "",
      }),
      workspaceId: String(payload.workspaceUuid || context.workspaceId || "").trim(),
      workspaceSlug: String(payload.workspace || workspace || "main").trim().toLowerCase(),
    });
    syncTenantWorkspacesInStorage(payload);
    return payload;
  } catch (error) {
    const apiError = error as TenantAdminApiError;
    if ((apiError?.status === 401 || apiError?.status === 403 || apiError?.code === "auth_required") && mainAccess) {
      const mainSessionValid = await authMeOk(mainAccess);
      if (!mainSessionValid) {
        throw error;
      }
    }
    // Compatibility fallback for environments where /api/tenant/bootstrap is unavailable.
    const payload = await fetchV1BootstrapAndMap(workspace);
    setActiveTenantSessionContext({
      ...(getActiveTenantSessionContext() || {
        tenantId: "",
        tenantSlug: "",
        tenantSchema: "",
        workspaceId: "",
        workspaceSlug: "",
      }),
      workspaceId: String(payload.workspaceUuid || context.workspaceId || "").trim(),
      workspaceSlug: String(payload.workspace || workspace || "main").trim().toLowerCase(),
    });
    syncTenantWorkspacesInStorage(payload);
    return payload;
  }
}

export function saveTenantUser(input: {
  email: string;
  displayName: string;
  password?: string;
  role: "admin" | "member" | "viewer";
  isActive: boolean;
  membershipActive: boolean;
}) {
  return request<Record<string, unknown>>("/users", { method: "POST", bodyJson: input });
}

export function deleteTenantUser(input: { id?: number; email?: string }) {
  return request<Record<string, unknown>>("/users/delete", { method: "POST", bodyJson: input });
}

export function saveTenantSkill(input: {
  workspace: string;
  key: string;
  name: string;
  description: string;
  bodyMarkdown: string;
  isActive: boolean;
}) {
  return request<Record<string, unknown>>("/skills", { method: "POST", bodyJson: input });
}

export function deleteTenantSkill(input: { workspace: string; key: string }) {
  return request<Record<string, unknown>>("/skills/delete", { method: "POST", bodyJson: input });
}

export function saveTenantAutomation(input: {
  recordType: "template" | "instance";
  id?: string;
  key?: string;
  workspace?: string;
  templateKey?: string;
  name?: string;
  description?: string;
  instructionsMarkdown?: string;
  examplePrompt?: string;
  defaultMessage?: string;
  icon?: string;
  category?: string;
  message?: string;
  executionMode?: "local" | "worktree";
  scheduleType?: "manual" | "daily" | "interval";
  scheduleTime?: string;
  intervalMinutes?: number;
  weekdays?: string[];
  isActive?: boolean;
  isRecommended?: boolean;
}) {
  return request<Record<string, unknown>>("/automations", { method: "POST", bodyJson: input });
}

export function deleteTenantAutomation(input: {
  recordType: "template" | "instance";
  id?: string;
  key?: string;
  workspace?: string;
}) {
  return request<Record<string, unknown>>("/automations/delete", { method: "POST", bodyJson: input });
}

export function saveTenantWorkspace(input: {
  id?: string;
  slug: string;
  name: string;
  displayName?: string;
  specialtyPrompt?: string;
  toolAllowlist?: string[];
  pluginAllowlist?: string[];
  integrationAllowlist?: string[];
  defaultVendor?: string;
  defaultModel?: string;
  defaultThinking?: string;
  defaultVerbosity?: string;
  enabledSkillKeys: string[];
  isActive: boolean;
}) {
  return request<Record<string, unknown>>("/workspaces", { method: "POST", bodyJson: input });
}

export function deleteTenantWorkspace(input: { id?: string; slug?: string }) {
  return request<Record<string, unknown>>("/workspaces/delete", { method: "POST", bodyJson: input });
}

export function saveTenantIntegration(input: {
  integrationKey: string;
  isEnabled: boolean;
  notes: string;
  assistantDocsOverride: string;
  tenantAuthConfig?: Record<string, unknown>;
  tenantAuthInput?: Record<string, unknown>;
  userAuthConfig?: Record<string, unknown>;
  userAuthInput?: Record<string, unknown>;
}) {
  return request<Record<string, unknown>>("/integrations", { method: "POST", bodyJson: input });
}

export function tenantPlugins(input: { tenantSlug?: string; tenantSchema?: string } = {}) {
  const query: Record<string, string> = {};
  const tenantSlug = String(input.tenantSlug || "").trim().toLowerCase();
  const tenantSchema = String(input.tenantSchema || "").trim().toLowerCase();
  if (tenantSlug) query.tenantSlug = tenantSlug;
  if (tenantSchema) query.tenantSchema = tenantSchema;
  return request<TenantPluginState>("/plugins", { query });
}

export function saveTenantPlugin(input: {
  pluginId: string;
  isEnabled: boolean;
  notes?: string;
  pluginConfig?: Record<string, unknown>;
  assignments?: Array<{
    assignmentType: "role" | "user";
    role?: string;
    userId?: number;
    userEmail?: string;
    isActive?: boolean;
    notes?: string;
  }>;
}) {
  return request<TenantPluginState>("/plugins", {
    method: "POST",
    bodyJson: {
      pluginId: String(input.pluginId || "").trim().toLowerCase(),
      isEnabled: Boolean(input.isEnabled),
      notes: String(input.notes || ""),
      pluginConfig: input.pluginConfig,
      assignments: Array.isArray(input.assignments) ? input.assignments : undefined,
    },
  });
}

export async function logoutTenantSession(): Promise<void> {
  clearTenantTokens();
}
