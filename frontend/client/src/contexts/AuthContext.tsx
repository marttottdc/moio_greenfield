import { createContext, useContext, useState, useEffect, ReactNode } from "react";
import { useLocation } from "wouter";
import { apiRequest, refreshAccessToken as refreshTokens, clearQueryCacheWithLogging } from "@/lib/queryClient";
import { logLoginStep, persistLastAuthError, type LoginStep } from "@/lib/loginMonitor";
import {
  apiV1,
  applyTenantConnectionTarget,
  clearTenantConnectionTarget,
  getAccessToken,
  setAccessToken,
  setRefreshToken,
  clearStoredTokens,
  setApiBaseOverride,
  setWebSocketBaseOverride,
} from "@/lib/api";
import { ApiError } from "@/lib/queryClient";

/** Current user from GET /api/v1/auth/me/ (Moio-aligned: id may be number, includes username, avatar_url). */
interface User {
  id: string | number;
  full_name: string;
  role: string;
  email?: string;
  username?: string;
  avatar_url?: string | null;
  organization?: {
    id: string;
    name: string | null;
    domain?: string;
    subdomain?: string;
    primary_domain?: string;
    schema_name?: string;
  } | null;
}

interface AuthContextType {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshAccessToken: () => Promise<boolean>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [, setLocation] = useLocation();

  // Fetch current user profile
  const fetchCurrentUser = async (): Promise<boolean> => {
    try {
      const res = await apiRequest("GET", apiV1("/auth/me/"));
      const data = await res.json();
      setUser(data);
      applyTenantConnectionTarget(data.organization);
      return true;
    } catch (error) {
      const status = error instanceof ApiError ? error.status : undefined;
      logLoginStep("fetch_profile", "fail", status != null ? `HTTP ${status}` : undefined, error);
      setUser(null);
      return false;
    }
  };

  // Refresh access token using refresh token
  const refreshAccessToken = async (): Promise<boolean> => {
    const refreshed = await refreshTokens();
    if (!refreshed) {
      setUser(null);
    }
    return refreshed;
  };

  // Login function (each step logged so we can see where login fails)
  const login = async (email: string, password: string) => {
    let lastStep: LoginStep = "clear_cache";
    try {
      clearQueryCacheWithLogging("login - clearing previous session data");
      logLoginStep("clear_cache", "ok");

      lastStep = "login_request";
      logLoginStep("login_request", "start");
      // Some backends expect "email", others "username"; send both so either validation passes
      const res = await apiRequest("POST", apiV1("/auth/login/"), {
        data: { email, username: email, password },
      });
      logLoginStep("login_request", "ok", res.status);

      lastStep = "login_response";
      const data = await res.json();
      logLoginStep("login_response", "ok");

      // Support both Django (access/refresh) and OAuth-style (access_token/refresh_token)
      const access = data.access ?? data.access_token;
      const refresh = data.refresh ?? data.refresh_token;

      lastStep = "token_storage";
      setAccessToken(access);
      setRefreshToken(refresh);
      logLoginStep("token_storage", "ok");

      lastStep = "backend_host";
      if (data.backend_host) {
        setApiBaseOverride(data.backend_host);
        if (data.websocket_base || data.ws_base) {
          setWebSocketBaseOverride(data.websocket_base ?? data.ws_base);
        }
      } else {
        const possibleBackendFields = ["backend", "api_host", "api_base", "server_host"];
        for (const field of possibleBackendFields) {
          if (data[field]) {
            setApiBaseOverride(data[field]);
            break;
          }
        }
        const possibleWebSocketFields = ["websocket_base", "ws_base", "socket_host"];
        for (const field of possibleWebSocketFields) {
          if (data[field]) {
            setWebSocketBaseOverride(data[field]);
            break;
          }
        }
      }
      logLoginStep("backend_host", "ok");

      lastStep = "fetch_profile";
      // Use the token we just received so /auth/me/ is never sent without Authorization (avoids race with storage)
      if (!access || typeof access !== "string") {
        throw new Error("Login response did not include an access token");
      }
      const meRes = await apiRequest("GET", apiV1("/auth/me/"), { authTokenOverride: access });
      const meData = await meRes.json();
      setUser(meData);
      applyTenantConnectionTarget(meData.organization);
      logLoginStep("fetch_profile", "ok");

      lastStep = "redirect";
      setLocation("/login");
      logLoginStep("redirect", "ok");
    } catch (error) {
      logLoginStep(lastStep, "fail", undefined, error);
      const message = error instanceof Error ? error.message : String(error);
      const status = error && typeof (error as { status?: number }).status === "number" ? (error as { status: number }).status : undefined;
      persistLastAuthError(message, { step: lastStep, status });
      throw error;
    }
  };

  // Logout function
  const logout = async () => {
    try {
      await apiRequest("POST", apiV1("/auth/logout/"));
    } catch (error) {
      console.error("Logout request failed:", error);
    } finally {
      clearStoredTokens();
      clearTenantConnectionTarget();
      clearQueryCacheWithLogging("logout - clearing user session data");
      setUser(null);
      setLocation("/login");
    }
  };

  // Check authentication on mount
  useEffect(() => {
    const initAuth = async () => {
      const hasToken = !!getAccessToken();

      if (!hasToken) {
        setIsLoading(false);
        return;
      }

      // Try to fetch current user
      const success = await fetchCurrentUser();

      // If failed, try refreshing token
      if (!success) {
        const refreshed = await refreshAccessToken();
        if (refreshed) {
          await fetchCurrentUser();
        }
      }

      setIsLoading(false);
    };

    initAuth();
  }, []);

  const value: AuthContextType = {
    user,
    isAuthenticated: !!user,
    isLoading,
    login,
    logout,
    refreshAccessToken,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

const FALLBACK_AUTH: AuthContextType = {
  user: null,
  isAuthenticated: false,
  isLoading: false,
  login: async () => {
    console.warn("[Auth] login() called outside AuthProvider – no-op");
  },
  logout: async () => {
    console.warn("[Auth] logout() called outside AuthProvider – no-op");
  },
  refreshAccessToken: async () => false,
};

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    // Often seen when the runtime error overlay re-renders a component in isolation,
    // which masks the real error. Return a safe default and warn so the overlay
    // can show the original failure.
    if (import.meta.env?.DEV) {
      console.warn(
        "[Auth] useAuth() was called outside AuthProvider. Ensure the app root is wrapped in <AuthProvider>."
      );
    }
    return FALLBACK_AUTH;
  }
  return context;
}
