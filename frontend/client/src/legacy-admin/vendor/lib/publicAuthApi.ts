// @ts-nocheck
import { resolveApiBase } from "./runtimeConfig";

const PUBLIC_API_BASE = resolveApiBase("/api/public", import.meta.env.VITE_PUBLIC_AUTH_BASE);
const AUTH_API_BASE = resolveApiBase("/api/auth", import.meta.env.VITE_PLATFORM_ADMIN_AUTH_BASE);

const PUBLIC_TOKEN_STORAGE_KEY = "moio_public_tokens";
const TENANT_SESSION_TOKEN_STORAGE_KEY = "moio_tenant_session_tokens";
const TENANT_SESSION_CONTEXT_STORAGE_KEY = "moio_tenant_session_context";
const PUBLIC_CLIENT_KEY_STORAGE_KEY = "moio_public_client_key";
const PUBLIC_TENANTS_STORAGE_KEY = "moio_public_tenants";
const PUBLIC_USER_STORAGE_KEY = "moio_public_user";
const PLATFORM_ACCESS_TOKEN_KEY = "platform_admin_access_token";
const PLATFORM_REFRESH_TOKEN_KEY = "platform_admin_refresh_token";

export type SessionTokens = {
  access: string;
  refresh: string;
};

export type PublicWorkspaceRow = {
  uuid: string;
  slug: string;
  name: string;
};

export type PublicTenantRow = {
  uuid: string;
  id: string;
  slug: string;
  schemaName: string;
  name: string;
  isActive: boolean;
  role: string;
  workspaces: PublicWorkspaceRow[];
};

export type PublicAuthUser = {
  id: number;
  email: string;
  displayName: string;
};

export type PublicAuthCapabilities = {
  tenantConsole: boolean;
  platformAdmin: boolean;
};

export type PublicAuthPayload = {
  tokens?: SessionTokens | null;
  platformTokens?: SessionTokens | null;
  user: PublicAuthUser;
  capabilities: PublicAuthCapabilities;
  tenants: PublicTenantRow[];
  plan?: string;
};

export type StoredPublicSessionState = {
  user: PublicAuthUser | null;
  tenants: PublicTenantRow[];
  capabilities: PublicAuthCapabilities;
  hasPublicSession: boolean;
  hasTenantSession: boolean;
};

export type ActiveTenantSessionContext = {
  tenantId: string;
  tenantSlug: string;
  tenantSchema: string;
  workspaceId: string;
  workspaceSlug: string;
};

export type TenantSessionPayload = {
  tokens: SessionTokens;
  tenant: {
    id: string;
    slug: string;
    schemaName: string;
  };
};

export class PublicAuthApiError extends Error {
  status: number;
  code: string;

  constructor(message: string, status = 500, code = "request_failed") {
    super(message);
    this.status = status;
    this.code = code;
  }
}

function safeJsonParse(raw: string | null): unknown {
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function normalizeWorkspaceRows(raw: unknown): PublicWorkspaceRow[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .map((entry) => {
      const row = entry && typeof entry === "object" ? (entry as Record<string, unknown>) : {};
      const slug = String(row.slug ?? "").trim().toLowerCase();
      if (!slug) return null;
      return {
        uuid: String(row.uuid ?? row.id ?? "").trim(),
        slug,
        name: String(row.name ?? row.displayName ?? row.slug ?? slug).trim() || slug,
      };
    })
    .filter((entry): entry is PublicWorkspaceRow => Boolean(entry));
}

function normalizeTenantRows(raw: unknown): PublicTenantRow[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .map((entry) => {
      const row = entry && typeof entry === "object" ? (entry as Record<string, unknown>) : {};
      const slug = String(row.slug ?? "").trim().toLowerCase();
      const schemaName = String(row.schemaName ?? "").trim().toLowerCase();
      const uuid = String(row.uuid ?? row.id ?? "").trim();
      if (!slug && !schemaName && !uuid) return null;
      return {
        uuid,
        id: uuid,
        slug,
        schemaName,
        name: String(row.name ?? row.slug ?? row.schemaName ?? "tenant").trim() || "tenant",
        isActive: Boolean(row.isActive ?? true),
        role: String(row.role ?? "member").trim() || "member",
        workspaces: normalizeWorkspaceRows(row.workspaces),
      };
    })
    .filter((entry): entry is PublicTenantRow => Boolean(entry));
}

function normalizeUser(raw: unknown): PublicAuthUser | null {
  const row = raw && typeof raw === "object" ? (raw as Record<string, unknown>) : null;
  if (!row) return null;
  const email = String(row.email ?? "").trim();
  const displayName = String(row.displayName ?? email).trim() || email;
  const id = Number(row.id ?? 0) || 0;
  if (!email && !displayName && !id) return null;
  return { id, email, displayName };
}

function hasPlatformTokens(): boolean {
  try {
    return Boolean(String(localStorage.getItem(PLATFORM_ACCESS_TOKEN_KEY) || "").trim());
  } catch {
    return false;
  }
}

function getStoredTokens(storageKey: string): SessionTokens | null {
  try {
    const parsed = safeJsonParse(localStorage.getItem(storageKey));
    const row = parsed && typeof parsed === "object" ? (parsed as Record<string, unknown>) : null;
    if (!row) return null;
    const access = String(row.access ?? "").trim();
    const refresh = String(row.refresh ?? "").trim();
    if (!access || !refresh) return null;
    return { access, refresh };
  } catch {
    return null;
  }
}

function setStoredTokens(storageKey: string, tokens: SessionTokens | null): void {
  try {
    if (tokens?.access && tokens?.refresh) {
      localStorage.setItem(storageKey, JSON.stringify(tokens));
    } else {
      localStorage.removeItem(storageKey);
    }
  } catch {
    // ignore storage failures
  }
}

function createClientKey(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `client-${Date.now()}-${Math.random().toString(36).slice(2, 12)}`;
}

function normalizeActiveTenantSessionContext(raw: unknown): ActiveTenantSessionContext | null {
  const row = raw && typeof raw === "object" ? (raw as Record<string, unknown>) : null;
  if (!row) return null;
  const tenantId = String(row.tenantId ?? "").trim();
  const tenantSlug = String(row.tenantSlug ?? "").trim().toLowerCase();
  const tenantSchema = String(row.tenantSchema ?? "").trim().toLowerCase();
  const workspaceId = String(row.workspaceId ?? "").trim();
  const workspaceSlug = String(row.workspaceSlug ?? "").trim().toLowerCase();
  if (!tenantId && !tenantSlug && !tenantSchema) return null;
  return {
    tenantId,
    tenantSlug,
    tenantSchema,
    workspaceId,
    workspaceSlug,
  };
}

function setPlatformTokens(tokens: SessionTokens | null): void {
  try {
    if (tokens?.access && tokens?.refresh) {
      localStorage.setItem(PLATFORM_ACCESS_TOKEN_KEY, tokens.access);
      localStorage.setItem(PLATFORM_REFRESH_TOKEN_KEY, tokens.refresh);
    } else {
      localStorage.removeItem(PLATFORM_ACCESS_TOKEN_KEY);
      localStorage.removeItem(PLATFORM_REFRESH_TOKEN_KEY);
    }
  } catch {
    // ignore storage failures
  }
}

async function request<TPayload>(
  path: string,
  options: RequestInit & {
    bodyJson?: unknown;
    headers?: Record<string, string>;
  } = {}
): Promise<TPayload> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers || {}),
  };

  const response = await fetch(`${PUBLIC_API_BASE}${path}`, {
    method: options.method || "GET",
    credentials: "same-origin",
    headers,
    body: options.bodyJson !== undefined ? JSON.stringify(options.bodyJson) : options.body,
  });

  const data = await response.json().catch(() => ({}));
  if (!response.ok || !data?.ok) {
    const message = data?.error?.message || data?.detail || `Request failed (${response.status})`;
    const code = data?.error?.code || "request_failed";
    throw new PublicAuthApiError(message, response.status, code);
  }

  return (data.payload || {}) as TPayload;
}

export function getStoredPublicTokens(): SessionTokens | null {
  return getStoredTokens(PUBLIC_TOKEN_STORAGE_KEY);
}

export function getStoredTenantSessionTokens(): SessionTokens | null {
  return getStoredTokens(TENANT_SESSION_TOKEN_STORAGE_KEY);
}

export function setStoredTenantSessionTokens(tokens: SessionTokens | null): void {
  setStoredTokens(TENANT_SESSION_TOKEN_STORAGE_KEY, tokens);
}

export function getOrCreatePublicClientKey(): string {
  try {
    const existing = String(localStorage.getItem(PUBLIC_CLIENT_KEY_STORAGE_KEY) || "").trim();
    if (existing) return existing;
    const next = createClientKey();
    localStorage.setItem(PUBLIC_CLIENT_KEY_STORAGE_KEY, next);
    return next;
  } catch {
    return createClientKey();
  }
}

export function getActiveTenantSessionContext(): ActiveTenantSessionContext | null {
  try {
    return normalizeActiveTenantSessionContext(safeJsonParse(localStorage.getItem(TENANT_SESSION_CONTEXT_STORAGE_KEY)));
  } catch {
    return null;
  }
}

export function setActiveTenantSessionContext(context: ActiveTenantSessionContext | null): void {
  try {
    if (context) {
      localStorage.setItem(TENANT_SESSION_CONTEXT_STORAGE_KEY, JSON.stringify(context));
    } else {
      localStorage.removeItem(TENANT_SESSION_CONTEXT_STORAGE_KEY);
    }
  } catch {
    // ignore storage failures
  }
}

async function refreshStoredAccessToken(
  refresh: string,
  storageKey: string,
): Promise<string | null> {
  try {
    const response = await fetch(`${AUTH_API_BASE}/refresh`, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data?.ok) return null;
    const access = String(data?.payload?.access || "").trim();
    if (!access) return null;
    setStoredTokens(storageKey, { access, refresh });
    return access;
  } catch {
    return null;
  }
}

async function refreshPublicAccessToken(refresh: string): Promise<string | null> {
  return refreshStoredAccessToken(refresh, PUBLIC_TOKEN_STORAGE_KEY);
}

async function refreshTenantAccessToken(refresh: string): Promise<string | null> {
  return refreshStoredAccessToken(refresh, TENANT_SESSION_TOKEN_STORAGE_KEY);
}

export async function revokeActiveTenantSession(): Promise<void> {
  const tokens = getStoredTenantSessionTokens();
  if (!tokens?.access && !tokens?.refresh) {
    clearTenantConsoleSession();
    return;
  }

  try {
    await fetch(`${AUTH_API_BASE}/logout`, {
      method: "POST",
      credentials: "same-origin",
      headers: tokens?.access
        ? {
            "Content-Type": "application/json",
            Authorization: `Bearer ${tokens.access}`,
          }
        : {
            "Content-Type": "application/json",
          },
      body: JSON.stringify({
        refresh: tokens?.refresh || "",
      }),
    });
  } catch {
    // Best effort; local session is cleared below.
  }
  clearTenantConsoleSession();
}

export function getStoredPublicSessionState(): StoredPublicSessionState {
  let user: PublicAuthUser | null = null;
  let tenants: PublicTenantRow[] = [];

  try {
    user = normalizeUser(safeJsonParse(localStorage.getItem(PUBLIC_USER_STORAGE_KEY)));
    tenants = normalizeTenantRows(safeJsonParse(localStorage.getItem(PUBLIC_TENANTS_STORAGE_KEY)));
  } catch {
    user = null;
    tenants = [];
  }

  const hasPublicSession = Boolean(getStoredPublicTokens());
  const hasTenantSession = Boolean(getStoredTenantSessionTokens());
  const platformAdmin = hasPlatformTokens();
  const tenantConsole = hasPublicSession && tenants.length > 0;

  return {
    user,
    tenants,
    capabilities: {
      tenantConsole,
      platformAdmin,
    },
    hasPublicSession,
    hasTenantSession,
  };
}

export function persistPublicSession(payload: PublicAuthPayload): void {
  try {
    localStorage.setItem(PUBLIC_USER_STORAGE_KEY, JSON.stringify(payload.user || null));
    localStorage.setItem(PUBLIC_TENANTS_STORAGE_KEY, JSON.stringify(payload.tenants || []));
  } catch {
    // ignore storage failures
  }

  if (payload.tokens !== undefined) {
    setStoredTokens(PUBLIC_TOKEN_STORAGE_KEY, payload.tokens);
    clearTenantConsoleSession();
  }
  if (payload.platformTokens !== undefined) {
    setPlatformTokens(payload.platformTokens);
  }
}

export function clearTenantConsoleSession(): void {
  try {
    localStorage.removeItem(TENANT_SESSION_TOKEN_STORAGE_KEY);
    localStorage.removeItem(TENANT_SESSION_CONTEXT_STORAGE_KEY);
  } catch {
    // ignore storage failures
  }
}

export function clearPublicSessions(): void {
  try {
    localStorage.removeItem(PUBLIC_TOKEN_STORAGE_KEY);
    localStorage.removeItem(TENANT_SESSION_TOKEN_STORAGE_KEY);
    localStorage.removeItem(TENANT_SESSION_CONTEXT_STORAGE_KEY);
    localStorage.removeItem(PUBLIC_TENANTS_STORAGE_KEY);
    localStorage.removeItem(PUBLIC_USER_STORAGE_KEY);
    localStorage.removeItem(PUBLIC_CLIENT_KEY_STORAGE_KEY);
    localStorage.removeItem(PLATFORM_ACCESS_TOKEN_KEY);
    localStorage.removeItem(PLATFORM_REFRESH_TOKEN_KEY);
  } catch {
    // ignore storage failures
  }
}

export function loginPublic(input: { email: string; password: string }): Promise<PublicAuthPayload> {
  return request<PublicAuthPayload>("/login", {
    method: "POST",
    bodyJson: input,
  });
}

export function joinPublic(input: {
  email: string;
  password: string;
  displayName: string;
  tenantName: string;
}): Promise<PublicAuthPayload> {
  return request<PublicAuthPayload>("/join", {
    method: "POST",
    bodyJson: input,
  });
}

export async function fetchPublicContext(): Promise<PublicAuthPayload> {
  const tokens = getStoredPublicTokens();
  if (!tokens?.access) {
    throw new PublicAuthApiError("Authentication required.", 401, "auth_required");
  }

  const execute = (access: string) =>
    request<PublicAuthPayload>("/context", {
      headers: {
        Authorization: `Bearer ${access}`,
      },
    });

  try {
    return await execute(tokens.access);
  } catch (error) {
    const apiError = error as PublicAuthApiError;
    if ((apiError?.status === 401 || apiError?.status === 403 || apiError?.code === "auth_required") && tokens.refresh) {
      const nextAccess = await refreshPublicAccessToken(tokens.refresh);
      if (nextAccess) {
        return execute(nextAccess);
      }
    }
    throw error;
  }
}

export async function mintTenantSession(input: {
  tenantId?: string;
  tenantSchema?: string;
  tenantSlug?: string;
  workspaceId?: string;
  workspaceSlug?: string;
}): Promise<TenantSessionPayload> {
  const publicTokens = getStoredPublicTokens();
  if (!publicTokens?.access) {
    throw new PublicAuthApiError("Authentication required.", 401, "auth_required");
  }

  const body = {
    clientKey: getOrCreatePublicClientKey(),
    tenantId: String(input.tenantId || "").trim() || undefined,
    tenantSchema: String(input.tenantSchema || "").trim().toLowerCase() || undefined,
    tenantSlug: String(input.tenantSlug || "").trim().toLowerCase() || undefined,
  };

  const execute = (access: string) =>
    request<TenantSessionPayload>("/tenant-session", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${access}`,
      },
      bodyJson: body,
    });

  let payload: TenantSessionPayload;
  try {
    payload = await execute(publicTokens.access);
  } catch (error) {
    const apiError = error as PublicAuthApiError;
    if (
      (apiError?.status === 401 || apiError?.status === 403 || apiError?.code === "auth_required") &&
      publicTokens.refresh
    ) {
      const nextAccess = await refreshPublicAccessToken(publicTokens.refresh);
      if (!nextAccess) throw error;
      payload = await execute(nextAccess);
    } else {
      throw error;
    }
  }

  setStoredTenantSessionTokens(payload.tokens);
  setActiveTenantSessionContext({
    tenantId: String(payload.tenant?.id || "").trim(),
    tenantSlug: String(payload.tenant?.slug || "").trim().toLowerCase(),
    tenantSchema: String(payload.tenant?.schemaName || "").trim().toLowerCase(),
    workspaceId: String(input.workspaceId || "").trim(),
    workspaceSlug: String(input.workspaceSlug || "").trim().toLowerCase(),
  });
  return payload;
}

export async function refreshActiveTenantSessionAccess(): Promise<string | null> {
  const tokens = getStoredTenantSessionTokens();
  if (!tokens?.refresh) return null;
  return refreshTenantAccessToken(tokens.refresh);
}
