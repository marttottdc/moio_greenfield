/**
 * User API Key management — JWT-only endpoints.
 * Base: GET/POST/DELETE /api/v1/auth/api-key/
 */

import { apiRequest, ApiError } from "@/lib/queryClient";
import { apiV1 } from "@/lib/api";

const API_KEY_PATH = apiV1("/auth/api-key/");

/** Response from GET /api/v1/auth/api-key/ (200) */
export interface ApiKeyStatus {
  id: number;
  name: string;
  masked_key: string;
  created_at: string;
  last_used_at: string | null;
  expires_at: string | null;
}

/** Response from POST /api/v1/auth/api-key/ (201). `key` is only returned here. */
export interface CreateApiKeyResponse extends ApiKeyStatus {
  key: string;
  warning?: string;
}

/** Fetch current API key status. Returns null when no key (404). */
export async function getApiKeyStatus(): Promise<ApiKeyStatus | null> {
  try {
    const res = await apiRequest("GET", API_KEY_PATH);
    return (await res.json()) as ApiKeyStatus;
  } catch (err: unknown) {
    if (err instanceof ApiError && err.status === 404) {
      return null;
    }
    throw err;
  }
}

/** Create or replace API key. Optional name; backend uses "API Key" if omitted. */
export async function createApiKey(name?: string): Promise<CreateApiKeyResponse> {
  const res = await apiRequest("POST", API_KEY_PATH, {
    data: name != null && name.trim() !== "" ? { name: name.trim() } : undefined,
  });
  return res.json() as Promise<CreateApiKeyResponse>;
}

/** Revoke current API key. */
export async function revokeApiKey(): Promise<void> {
  const res = await apiRequest("DELETE", API_KEY_PATH);
  if (res.status !== 200) {
    const text = await res.text();
    throw new Error(text || "Failed to revoke API key");
  }
}
