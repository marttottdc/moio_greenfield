import { QueryClient, QueryFunction } from "@tanstack/react-query";
import {
  apiV1,
  createApiUrl,
  getAuthHeaders,
  getRefreshToken,
  setAccessToken,
  setRefreshToken,
  clearStoredTokens,
  type QueryParams
} from "./api";
import { persistLastAuthError } from "./loginMonitor";

const AUTH_LOGIN_PATH = apiV1("/auth/login/");
const AUTH_LOGOUT_PATH = apiV1("/auth/logout/");
const AUTH_REFRESH_PATH = apiV1("/auth/refresh/");
const AUTH_ME_PATH = apiV1("/auth/me/");

/**
 * Auth endpoints and expected responses (aligned with backend spec):
 *
 * POST /api/v1/auth/login/
 *   Body: { username, password } (username or email accepted; we send username with email value).
 *   Success 200: { access, refresh }.
 *   Errors: 400 invalid_request, 401 invalid_credentials.
 *
 * POST /api/v1/auth/refresh/
 *   Body: { refresh }.
 *   Success 200: { access, refresh? } (rotating: new access and optionally new refresh).
 *   Error 401: invalid_refresh_token → send user to login.
 *
 * GET /api/v1/auth/me/
 *   Headers: Authorization: Bearer <access>
 *   Success 200: User object (id, username, email, full_name, role, avatar_url, organization, preferences).
 *   Error 401: missing or invalid access token.
 *
 * POST /api/v1/auth/logout/
 *   Headers: Authorization: Bearer <access>
 *   Success 200: { message: "Successfully logged out" } (access may be blacklisted).
 *   Error 401: missing or invalid access token.
 *
 * Protected calls: use Authorization: Bearer <access>. On 401/403 → refresh once, then retry or logout.
 */

// Caching disabled - always fetch fresh data from server

export function forceLogout(reason?: string) {
  const msg = reason || "Session ended";
  console.error("[AUTH] Forcing logout.", msg);
  persistLastAuthError(msg, { reason: "force_logout" });
  clearStoredTokens();
  // Use direct clear here since clearQueryCacheWithLogging references queryClient
  // which may cause circular dependency issues
  if (typeof queryClient !== "undefined") {
    queryClient.cancelQueries();
    queryClient.clear();
    resetRefreshState();
  }
  window.location.href = "/login";
}

type MoioErrorResponse =
  | {
      error: string | { code?: string; message?: string };
      message?: string;
      fields?: Record<string, string[]>;
    }
  | { detail?: string; message?: string; fields?: Record<string, string[]> };

export class ApiError extends Error {
  status: number;
  body: string;
  errorCode?: string;
  fields?: Record<string, string[]>;

  constructor(status: number, body: string, errorData?: MoioErrorResponse) {
    const normalizedError = (() => {
      if (!errorData) return { code: undefined as string | undefined, message: undefined as string | undefined };
      const raw = (errorData as any)?.error;
      const code = typeof raw === "string" ? raw : raw?.code;
      const message =
        (typeof raw === "object" ? raw?.message : undefined) ??
        (errorData as any)?.message ??
        (errorData as any)?.detail;
      return { code, message };
    })();

    super(normalizedError.message || body || `HTTP ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
    this.errorCode = normalizedError.code;
    this.fields = (errorData as any)?.fields;
  }
}

async function throwIfResNotOk(res: Response) {
  if (!res.ok) {
    const text = (await res.text()) || res.statusText;

    let errorData: MoioErrorResponse | undefined;
    try {
      errorData = JSON.parse(text) as MoioErrorResponse;
    } catch {
      // If not JSON, treat as plain text error
    }

    throw new ApiError(res.status, text, errorData);
  }
}

let isRefreshing = false;
let refreshPromise: Promise<string | null> | null = null;

export function resetRefreshState() {
  isRefreshing = false;
  refreshPromise = null;
}

export function clearQueryCacheWithLogging(reason: string) {
  // Cancel any in-flight queries first
  queryClient.cancelQueries();
  
  // Clear all cached data
  queryClient.clear();
  
  // Reset refresh state to prevent stale promises
  resetRefreshState();
}

/** Returns the new access token on success, null on failure. Callers should use the returned token for retries to avoid using a stale cached bearer. */
export async function refreshAccessToken(): Promise<string | null> {
  if (isRefreshing && refreshPromise) {
    return refreshPromise;
  }

  isRefreshing = true;
  refreshPromise = (async (): Promise<string | null> => {
    try {
      const raw = getRefreshToken();
      const refreshToken = typeof raw === "string" ? raw.trim() : "";
      if (!refreshToken) {
        return null;
      }

      try {
        const res = await fetch(createApiUrl(AUTH_REFRESH_PATH), {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Moio-Client-Version": import.meta.env.VITE_APP_VERSION || "1.0.0",
          },
          body: JSON.stringify({ refresh: refreshToken }),
        });

        if (!res.ok) {
          return null;
        }

        const data = await res.json();
        const access = data.access ?? data.access_token;
        const refresh = data.refresh ?? data.refresh_token;
        setAccessToken(access);
        if (refresh) {
          setRefreshToken(refresh);
        }

        return typeof access === "string" ? access : null;
      } catch (error) {
        console.error("Token refresh failed:", error);
        return null;
      }
    } finally {
      isRefreshing = false;
      refreshPromise = null;
    }
  })();

  return refreshPromise;
}

function resolveQueryParams(params: unknown): QueryParams | undefined {
  if (!params || typeof params !== "object") {
    return undefined;
  }

  return params as QueryParams;
}

interface ApiRequestOptions {
  data?: unknown;
  params?: QueryParams;
  headers?: HeadersInit;
  body?: BodyInit;
  /** When set, use this token for Authorization (e.g. immediately after login so /auth/me/ is not sent without the new token). */
  authTokenOverride?: string;
}

function getCsrfToken(): string | null {
  const cookies = document.cookie.split(';');
  for (const cookie of cookies) {
    const [name, value] = cookie.trim().split('=');
    if (name === 'csrftoken') {
      return decodeURIComponent(value);
    }
  }
  return null;
}

const SAFE_METHODS = ['GET', 'HEAD', 'OPTIONS', 'TRACE'];

export async function apiRequest(
  method: string,
  path: string,
  options: ApiRequestOptions = {},
  retryCount = 0,
) {
  const { data, params, headers, body, authTokenOverride } = options;
  let res: Response;

  const url = createApiUrl(path, params);
  const baseAuth = getAuthHeaders();
  const authHeaders: HeadersInit =
    authTokenOverride != null && authTokenOverride !== ""
      ? { ...baseAuth, Authorization: `Bearer ${authTokenOverride}` }
      : baseAuth;
  
  // Add CSRF token for non-safe methods
  const csrfHeaders: Record<string, string> = {};
  if (!SAFE_METHODS.includes(method.toUpperCase())) {
    const csrfToken = getCsrfToken();
    if (csrfToken) {
      csrfHeaders['X-CSRFToken'] = csrfToken;
    }
  }
  
  // Determine body content
  const requestBody = body ?? (data ? JSON.stringify(data) : undefined);

  // Only set Content-Type for JSON data, not for FormData (browser will set it with boundary)
  const shouldSetContentType = data && !body;

  try {
    res = await fetch(url, {
      method,
      headers: {
        ...(shouldSetContentType ? { "Content-Type": "application/json" } : {}),
        ...authHeaders,
        ...csrfHeaders,
        ...headers,
      },
      body: requestBody,
      credentials: "include",
    });
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Network request failed";
    throw new ApiError(0, message);
  }

  const isAuthEndpoint =
    path === AUTH_LOGIN_PATH || path === AUTH_LOGOUT_PATH || path === AUTH_REFRESH_PATH;

  // Simple JWT: 401/403 → try refresh once, then retry with the new token (no cached bearer)
  const shouldRetryAuth = retryCount === 0 && !isAuthEndpoint;
  if (shouldRetryAuth && (res.status === 401 || res.status === 403)) {
    const newAccess = await refreshAccessToken();
    if (newAccess) {
      return apiRequest(method, path, { ...options, authTokenOverride: newAccess }, retryCount + 1);
    }
    forceLogout("Sesión expirada. Inicia sesión de nuevo.");
    throw new ApiError(res.status, "Sesión expirada. Inicia sesión de nuevo.");
  }

  await throwIfResNotOk(res);
  return res;
}

export async function fetchJson<T>(path: string, params?: QueryParams) {
  const res = await apiRequest("GET", path, { params });
  const json = await res.json();
  return json as T;
}

type UnauthorizedBehavior = "returnNull" | "throw";

export function getQueryFn<T>({ on401 }: { on401: UnauthorizedBehavior }): QueryFunction<T> {
  return async ({ queryKey, signal }) => {
    const [path, params] = queryKey as [string, QueryParams?];

    const makeRequest = async (retryCount = 0, bearerOverride?: string): Promise<Response> => {
      let res: Response;
      const authHeaders = bearerOverride != null
        ? { ...getAuthHeaders(), Authorization: `Bearer ${bearerOverride}` }
        : getAuthHeaders();

      try {
        res = await fetch(createApiUrl(path, resolveQueryParams(params)), {
          signal,
          headers: authHeaders,
        });
      } catch (error) {
        const message =
          error instanceof Error ? error.message : "Network request failed";
        throw new ApiError(0, message);
      }

      // Simple JWT: 401/403 → try refresh once, then retry with new token (no cached bearer)
      const shouldRetryAuth = retryCount === 0 && typeof path === "string";
      if (shouldRetryAuth && (res.status === 401 || res.status === 403)) {
        const isAuthEndpoint =
          path === AUTH_LOGIN_PATH || path === AUTH_LOGOUT_PATH || path === AUTH_REFRESH_PATH;

        if (!isAuthEndpoint) {
          if (on401 === "returnNull") {
            return res;
          }
          const newAccess = await refreshAccessToken();
          if (newAccess) {
            return makeRequest(retryCount + 1, newAccess);
          }
          forceLogout("Sesión expirada. Inicia sesión de nuevo.");
          throw new ApiError(res.status, "Sesión expirada. Inicia sesión de nuevo.");
        }
      }

      return res;
    };

    const res = await makeRequest();

    if (on401 === "returnNull" && res.status === 401) {
      return null as T;
    }

    await throwIfResNotOk(res);
    return (await res.json()) as T;
  };
}

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      queryFn: getQueryFn({ on401: "throw" }),
      refetchInterval: false,
      refetchOnWindowFocus: false,
      refetchOnMount: false,
      refetchOnReconnect: false,
      staleTime: 1000 * 60 * 5,
      gcTime: 1000 * 60 * 10,
      retry: false,
    },
    mutations: {
      retry: false,
    },
  },
});