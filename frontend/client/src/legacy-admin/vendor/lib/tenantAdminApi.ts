// @ts-nocheck
import type { TenantBootstrapPayload, TenantPluginState } from "../types";
import {
  clearTenantConsoleSession,
  getActiveTenantSessionContext,
  getStoredTenantSessionTokens,
  revokeActiveTenantSession,
  setActiveTenantSessionContext,
  setStoredTenantSessionTokens,
} from "./publicAuthApi";
import { resolveApiBase } from "./runtimeConfig";

const TENANT_API_BASE = resolveApiBase("/api/tenant", import.meta.env.VITE_TENANT_ADMIN_API_BASE);
const AUTH_BASE = resolveApiBase("/api/auth", import.meta.env.VITE_PLATFORM_ADMIN_AUTH_BASE);
const PUBLIC_USER_STORAGE_KEY = "moio_public_user";
const PLATFORM_ACCESS_TOKEN_KEY = "platform_admin_access_token";
const PLATFORM_REFRESH_TOKEN_KEY = "platform_admin_refresh_token";

export class TenantAdminApiError extends Error {
  status: number;
  code: string;

  constructor(message: string, status = 500, code = "request_failed") {
    super(message);
    this.status = status;
    this.code = code;
  }
}

type TenantTokens = {
  access: string;
  refresh: string;
};

type TenantRequestContext = {
  workspace: string;
  workspaceId: string;
};

function getTenantTokens(): TenantTokens | null {
  return getStoredTenantSessionTokens();
}

function setTenantTokens(tokens: TenantTokens): void {
  setStoredTenantSessionTokens(tokens);
}

function clearTenantTokens(): void {
  try {
    localStorage.removeItem(PUBLIC_USER_STORAGE_KEY);
    localStorage.removeItem(PLATFORM_ACCESS_TOKEN_KEY);
    localStorage.removeItem(PLATFORM_REFRESH_TOKEN_KEY);
  } catch {
    // Ignore local storage failures.
  }
  clearTenantConsoleSession();
}

async function refreshTenantAccessToken(refreshToken: string): Promise<string | null> {
  try {
    const response = await fetch(`${AUTH_BASE}/refresh`, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh: refreshToken }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data?.ok) return null;
    const access = String(data?.payload?.access || "").trim();
    if (!access) return null;
    setTenantTokens({ access, refresh: refreshToken });
    return access;
  } catch {
    return null;
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
    retryAuth?: boolean;
  } = {}
): Promise<TPayload> {
  const tokens = getTenantTokens();
  const access = String(tokens?.access || "").trim();
  const refresh = String(tokens?.refresh || "").trim();
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

  if (
    (response.status === 401 || response.status === 403 || data?.error?.code === "auth_required") &&
    options.retryAuth !== false &&
    refresh
  ) {
    const renewed = await refreshTenantAccessToken(refresh);
    if (renewed) {
      return request<TPayload>(path, { ...options, retryAuth: false });
    }
  }

  if (!response.ok || !data?.ok) {
    const message = data?.error?.message || data?.detail || `Request failed (${response.status})`;
    const code = data?.error?.code || "request_failed";
    throw new TenantAdminApiError(message, response.status, code);
  }

  return (data.payload || {}) as TPayload;
}

export function tenantBootstrap(workspace = "main") {
  const context = currentTenantRequestContext();
  return request<TenantBootstrapPayload>("/bootstrap", {
    query: {
      workspace,
      workspaceId: context.workspaceId,
    },
  }).then((payload) => {
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
    return payload;
  });
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
  await revokeActiveTenantSession();
  clearTenantTokens();
}
