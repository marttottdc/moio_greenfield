// @ts-nocheck
import type { BootstrapPayload, PluginAdminState } from "../types";
import { resolveApiBase } from "./runtimeConfig";

const API_BASE = resolveApiBase("/api/platform", import.meta.env.VITE_PLATFORM_ADMIN_API_BASE);
const AUTH_BASE = resolveApiBase("/api/auth", import.meta.env.VITE_PLATFORM_ADMIN_AUTH_BASE);
const ACCESS_TOKEN_KEY = "platform_admin_access_token";
const REFRESH_TOKEN_KEY = "platform_admin_refresh_token";
const PUBLIC_USER_STORAGE_KEY = "moio_public_user";
const PUBLIC_TOKEN_STORAGE_KEY = "moio_public_tokens";

export class PlatformAdminApiError extends Error {
  status: number;
  code: string;

  constructor(message: string, status = 500, code = "request_failed") {
    super(message);
    this.status = status;
    this.code = code;
  }
}

async function request<TPayload>(
  path: string,
  options: RequestInit & {
    bodyJson?: unknown;
    formData?: FormData;
    auth?: boolean;
    baseUrl?: string;
    retryAuth?: boolean;
  } = {}
): Promise<TPayload> {
  const authEnabled = options.auth !== false;
  const baseUrl = options.baseUrl || API_BASE;
  const retryAuth = options.retryAuth !== false;
  const headers = new Headers(options.headers || undefined);
  if (!options.formData && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const accessToken = authEnabled ? getAccessToken() : "";
  if (authEnabled && accessToken) {
    headers.set("Authorization", `Bearer ${accessToken}`);
  }

  const response = await fetch(`${baseUrl}${path}`, {
    method: options.method || "GET",
    credentials: "same-origin",
    headers,
    body:
      options.formData !== undefined
        ? options.formData
        : options.bodyJson !== undefined
        ? JSON.stringify(options.bodyJson)
        : options.body,
  });

  let data: any = null;
  try {
    data = await response.json();
  } catch {
    data = null;
  }

  if (
    (response.status === 401 || response.status === 403 || data?.error?.code === "auth_required") &&
    authEnabled &&
    retryAuth
  ) {
    const refreshed = await tryRefreshAccessToken();
    if (refreshed) {
      return request<TPayload>(path, { ...options, retryAuth: false });
    }
  }

  if (!response.ok || !data?.ok) {
    const msg = data?.error?.message || data?.detail || `Request failed (${response.status})`;
    const code = data?.error?.code || data?.code || "request_failed";
    throw new PlatformAdminApiError(msg, response.status, code);
  }

  return (data.payload || {}) as TPayload;
}

export function bootstrap() {
  return request<BootstrapPayload>("/bootstrap");
}

export function saveNotificationSettings(input: {
  settings: Record<string, unknown>;
}) {
  return request<BootstrapPayload>("/notifications", { method: "POST", bodyJson: input });
}

export function login(input: {
  email: string;
  password: string;
}) {
  return request<{ tokens: { access: string; refresh: string }; state: BootstrapPayload }>("/login", {
    baseUrl: AUTH_BASE,
    method: "POST",
    bodyJson: input,
    auth: false,
  }).then((payload) => {
    const access = String(payload?.tokens?.access || "").trim();
    const refresh = String(payload?.tokens?.refresh || "").trim();
    if (access && refresh) {
      setTokens(access, refresh);
    }
    return payload.state as BootstrapPayload;
  });
}

export function logout() {
  return request<{ loggedOut: boolean }>("/logout", { baseUrl: AUTH_BASE, method: "POST" }).finally(() => {
    clearTokens();
  });
}

export function clearPlatformAuthSession() {
  clearTokens();
}

export function saveTenant(input: {
  id?: string | null;
  name: string;
  slug: string;
  schemaName: string;
  primaryDomain?: string;
  isActive: boolean;
}) {
  return request<BootstrapPayload>("/tenants", { method: "POST", bodyJson: input });
}

export function deleteTenant(input: { id?: string; slug?: string }) {
  return request<BootstrapPayload>("/tenants/delete", { method: "POST", bodyJson: input });
}

export function saveUser(input: {
  id?: number | null;
  email: string;
  displayName: string;
  password?: string;
  isPlatformAdmin: boolean;
  isActive: boolean;
  tenantMemberships: Array<{ tenantSlug: string; role: "admin" | "member" | "viewer"; isActive: boolean }>;
}) {
  return request<BootstrapPayload>("/users", { method: "POST", bodyJson: input });
}

export function deleteUser(input: { id?: number; email?: string }) {
  return request<BootstrapPayload>("/users/delete", { method: "POST", bodyJson: input });
}

export function saveIntegration(input: {
  key: string;
  name: string;
  category: string;
  baseUrl: string;
  openapiUrl: string;
  defaultAuthType: string;
  authScope: "global" | "tenant" | "user";
  authConfigSchema: Record<string, unknown>;
  globalAuthConfig: Record<string, unknown>;
  assistantDocsMarkdown: string;
  defaultHeaders: Record<string, string>;
  isActive: boolean;
}) {
  return request<BootstrapPayload>("/integrations", { method: "POST", bodyJson: input });
}

export function deleteIntegration(input: { key: string }) {
  return request<BootstrapPayload>("/integrations/delete", { method: "POST", bodyJson: input });
}

export function saveTenantIntegration(input: {
  tenantSlug: string;
  integrationKey: string;
  isEnabled: boolean;
  notes: string;
  assistantDocsOverride: string;
  tenantAuthConfig?: Record<string, unknown>;
}) {
  return request<BootstrapPayload>("/tenant-integrations", { method: "POST", bodyJson: input });
}

export function saveGlobalSkill(input: {
  key: string;
  name: string;
  description: string;
  bodyMarkdown: string;
  isActive: boolean;
}) {
  return request<BootstrapPayload>("/skills", { method: "POST", bodyJson: input });
}

export function deleteGlobalSkill(input: { key: string }) {
  return request<BootstrapPayload>("/skills/delete", { method: "POST", bodyJson: input });
}

export function listPlugins(input: { tenantSlug?: string } = {}) {
  const tenantSlug = String(input.tenantSlug || "").trim();
  const query = tenantSlug ? `?tenant=${encodeURIComponent(tenantSlug)}` : "";
  return request<PluginAdminState>(`/plugins${query}`);
}

export function savePlatformPluginApproval(input: {
  pluginId: string;
  isPlatformApproved: boolean;
  tenantSlug?: string;
}) {
  return request<PluginAdminState>("/plugins", {
    method: "POST",
    bodyJson: {
      pluginId: String(input.pluginId || "").trim().toLowerCase(),
      isPlatformApproved: Boolean(input.isPlatformApproved),
      tenantSlug: String(input.tenantSlug || "").trim().toLowerCase() || undefined,
    },
  });
}

export function uploadPluginBundle(input: { file: File; tenantSlug?: string }) {
  const formData = new FormData();
  formData.append("bundle", input.file);
  const tenantSlug = String(input.tenantSlug || "").trim().toLowerCase();
  if (tenantSlug) {
    formData.append("tenantSlug", tenantSlug);
  }
  return request<PluginAdminState>("/plugins", {
    method: "POST",
    formData,
  });
}

function getAccessToken(): string {
  try {
    return String(localStorage.getItem(ACCESS_TOKEN_KEY) || "").trim();
  } catch {
    return "";
  }
}

function getRefreshToken(): string {
  try {
    return String(localStorage.getItem(REFRESH_TOKEN_KEY) || "").trim();
  } catch {
    return "";
  }
}

function setTokens(access: string, refresh: string): void {
  try {
    localStorage.setItem(ACCESS_TOKEN_KEY, access);
    localStorage.setItem(REFRESH_TOKEN_KEY, refresh);
  } catch {
    // ignore storage failures
  }
}

function clearTokens(): void {
  try {
    localStorage.removeItem(ACCESS_TOKEN_KEY);
    localStorage.removeItem(REFRESH_TOKEN_KEY);
    localStorage.removeItem(PUBLIC_USER_STORAGE_KEY);
    localStorage.removeItem(PUBLIC_TOKEN_STORAGE_KEY);
  } catch {
    // ignore storage failures
  }
}

async function tryRefreshAccessToken(): Promise<boolean> {
  const refresh = getRefreshToken();
  if (!refresh) return false;
  try {
    const payload = await request<{ access: string }>("/refresh", {
      baseUrl: AUTH_BASE,
      method: "POST",
      bodyJson: { refresh },
      auth: false,
      retryAuth: false,
    });
    const access = String(payload?.access || "").trim();
    if (!access) {
      clearTokens();
      return false;
    }
    setTokens(access, refresh);
    return true;
  } catch {
    clearTokens();
    return false;
  }
}
