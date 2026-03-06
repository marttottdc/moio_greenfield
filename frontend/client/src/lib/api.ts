const DEFAULT_API_BASE = "/api";
const API_BASE_OVERRIDE_KEY = "moio:api_base_override";

function normalizeBaseUrl(value?: string | null) {
  if (typeof value !== "string") {
    return undefined;
  }

  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : undefined;
}

const ACCESS_TOKEN_STORAGE_KEY = "moio:access_token";
const REFRESH_TOKEN_STORAGE_KEY = "moio:refresh_token";

const rawEnvAccessToken = import.meta.env.VITE_API_ACCESS_TOKEN;
const rawEnvRefreshToken = import.meta.env.VITE_API_REFRESH_TOKEN;
const rawEnvTenant = import.meta.env.VITE_MOIO_TENANT;
const rawEnvGithubSha = import.meta.env.VITE_GITHUB_SHA;
const rawEnvGithubRunNumber = import.meta.env.VITE_GITHUB_RUN_NUMBER;
const rawEnvAppBuild = import.meta.env.VITE_APP_BUILD;

function normalizeEnvToken(value: unknown) {
  return typeof value === "string" && value.trim().length > 0 ? value.trim() : undefined;
}

const envAccessToken = normalizeEnvToken(rawEnvAccessToken);
const envRefreshToken = normalizeEnvToken(rawEnvRefreshToken);
const envTenant = normalizeEnvToken(rawEnvTenant);
const envGithubSha = normalizeEnvToken(rawEnvGithubSha);
const envGithubRunNumber = normalizeEnvToken(rawEnvGithubRunNumber);
const envAppBuild = normalizeEnvToken(rawEnvAppBuild);

function readFromStorage(key: string) {
  if (typeof window === "undefined") {
    return undefined;
  }

  try {
    return window.localStorage.getItem(key) ?? undefined;
  } catch (error) {
    console.warn(`Unable to read ${key} from localStorage`, error);
    return undefined;
  }
}

function writeToStorage(key: string, value?: string | null) {
  if (typeof window === "undefined") {
    return;
  }

  try {
    if (value && value.length > 0) {
      window.localStorage.setItem(key, value);
    } else {
      window.localStorage.removeItem(key);
    }
  } catch (error) {
    console.warn(`Unable to write ${key} to localStorage`, error);
  }
}

function getEnvApiBaseUrl() {
  return normalizeBaseUrl(import.meta.env.VITE_API_BASE_URL) ?? DEFAULT_API_BASE;
}

function getStoredApiBaseOverride() {
  return normalizeBaseUrl(readFromStorage(API_BASE_OVERRIDE_KEY));
}

export function getDefaultApiBaseUrl() {
  return getEnvApiBaseUrl();
}

export function getApiBaseOverride() {
  return getStoredApiBaseOverride();
}

export function setApiBaseOverride(value?: string | null) {
  const normalizedValue = normalizeBaseUrl(value);
  writeToStorage(API_BASE_OVERRIDE_KEY, normalizedValue ?? null);
}

export function clearApiBaseOverride() {
  writeToStorage(API_BASE_OVERRIDE_KEY, null);
}

export function getApiBaseUrl() {
  return getStoredApiBaseOverride() ?? getEnvApiBaseUrl();
}

const LOGGED_OUT_FLAG_KEY = "moio:logged_out";

function isLoggedOutSession(): boolean {
  if (typeof window === "undefined") return false;
  try {
    return window.localStorage.getItem(LOGGED_OUT_FLAG_KEY) === "true";
  } catch {
    return false;
  }
}

function setLoggedOutSession(value: boolean) {
  if (typeof window === "undefined") return;
  try {
    if (value) {
      window.localStorage.setItem(LOGGED_OUT_FLAG_KEY, "true");
    } else {
      window.localStorage.removeItem(LOGGED_OUT_FLAG_KEY);
    }
  } catch {
    // Ignore storage errors
  }
}

export function getAccessToken() {
  const stored = readFromStorage(ACCESS_TOKEN_STORAGE_KEY);
  if (stored) return stored;
  if (isLoggedOutSession()) return undefined;
  return envAccessToken;
}

export function setAccessToken(token?: string | null) {
  writeToStorage(ACCESS_TOKEN_STORAGE_KEY, token);
  if (token) {
    setLoggedOutSession(false);
  }
}

export function getRefreshToken() {
  const stored = readFromStorage(REFRESH_TOKEN_STORAGE_KEY);
  if (stored) return stored;
  if (isLoggedOutSession()) return undefined;
  return envRefreshToken;
}

export function setRefreshToken(token?: string | null) {
  writeToStorage(REFRESH_TOKEN_STORAGE_KEY, token);
}

export function clearStoredTokens() {
  setLoggedOutSession(true);
  writeToStorage(ACCESS_TOKEN_STORAGE_KEY, null);
  writeToStorage(REFRESH_TOKEN_STORAGE_KEY, null);
}

export function getClientVersion(): string {
  return import.meta.env.VITE_APP_VERSION || "1.0.0";
}

function getClientCommitHash(): string | undefined {
  if (!envGithubSha) {
    return undefined;
  }

  return envGithubSha.slice(0, 8);
}

export function getClientBuildNumber(): string {
  if (envGithubRunNumber) {
    return envGithubRunNumber;
  }

  if (envAppBuild) {
    return envAppBuild;
  }

  return getClientCommitHash() ?? getClientVersion();
}

interface BuildInfo {
  buildNumber: string | undefined;
  commit: string | undefined;
  fallbackVersion: string;
  buildDate?: string;
}

let cachedBuildInfo: BuildInfo | null = null;

export function getClientBuildInfo(): BuildInfo {
  if (cachedBuildInfo) {
    return cachedBuildInfo;
  }
  
  return {
    buildNumber: envGithubRunNumber ?? envAppBuild,
    commit: getClientCommitHash(),
    fallbackVersion: getClientVersion(),
  };
}

export async function loadBuildInfoFromMeta(): Promise<BuildInfo> {
  try {
    const response = await fetch("/meta.json", { cache: "no-store" });
    if (response.ok) {
      const meta = await response.json();
      const metaCommit =
        (typeof meta?.commitShort === "string" && meta.commitShort.trim().length > 0
          ? meta.commitShort.trim()
          : undefined) ??
        (typeof meta?.commit === "string" && meta.commit.trim().length > 0 ? meta.commit.trim().slice(0, 8) : undefined);
      cachedBuildInfo = {
        buildNumber: meta.buildId ?? meta.buildNumber,
        commit: metaCommit ?? getClientCommitHash(),
        fallbackVersion: meta.version || getClientVersion(),
        buildDate: meta.buildDate,
      };
      return cachedBuildInfo;
    }
  } catch (error) {
    // Silently fail to load meta.json
  }
  
  cachedBuildInfo = {
    buildNumber: envGithubRunNumber ?? envAppBuild,
    commit: getClientCommitHash(),
    fallbackVersion: getClientVersion(),
  };
  return cachedBuildInfo;
}

function getCsrfToken(): string | null {
  if (typeof document === "undefined") {
    return null;
  }
  
  // Try to get CSRF token from cookie
  const cookies = document.cookie.split(';');
  for (const cookie of cookies) {
    const [name, value] = cookie.trim().split('=');
    if (name === 'csrftoken') {
      return decodeURIComponent(value);
    }
  }
  
  return null;
}

export function getAuthHeaders(): HeadersInit {
  const accessToken = getAccessToken();
  const csrfToken = getCsrfToken();

  const headers: Record<string, string> = {
    "X-Moio-Client-Version": getClientVersion(),
  };

  if (envTenant) {
    headers["X-Moio-Tenant"] = envTenant;
  }
  if (csrfToken) {
    headers["X-CSRFToken"] = csrfToken;
  }
  if (accessToken) {
    headers["Authorization"] = `Bearer ${accessToken}`;
  }

  return headers;
}


function trimTrailingSlash(value: string) {
  return value.endsWith("/") ? value.slice(0, -1) : value;
}

function trimLeadingSlash(value: string) {
  return value.startsWith("/") ? value.slice(1) : value;
}

type QueryParamValue = string | number | boolean | null | undefined;
export type QueryParams = Record<string, QueryParamValue>;

function buildSearch(params?: QueryParams) {
  if (!params) {
    return "";
  }

  const searchParams = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null) continue;
    searchParams.set(key, String(value));
  }

  const queryString = searchParams.toString();
  return queryString ? `?${queryString}` : "";
}

export function createApiUrl(path: string, params?: QueryParams) {
  const base = trimTrailingSlash(getApiBaseUrl());
  let normalizedPath = trimLeadingSlash(path);
  const query = buildSearch(params);

  // Avoid double-prefixing when VITE_API_BASE_URL already includes /api or /api/v1.
  // Examples we want to support:
  // - base="/api" + path="/api/v1/..." -> "/api/v1/..."
  // - base="https://host/api/v1" + path="/api/v1/..." -> "https://host/api/v1/..."
  // - base="https://host" + path="/api/v1/..." -> "https://host/api/v1/..."
  const stripLeading = (prefix: string) => {
    if (normalizedPath.startsWith(prefix)) {
      normalizedPath = normalizedPath.slice(prefix.length);
    }
  };

  if (base.endsWith("/api/v1")) {
    stripLeading("api/v1/");
  } else if (base.endsWith("/api")) {
    stripLeading("api/");
  }

  // Add trailing slash for Django compatibility
  if (!normalizedPath.endsWith("/")) {
    normalizedPath = `${normalizedPath}/`;
  }

  if (!base) {
    return `/${normalizedPath}${query}`;
  }

  if (base.startsWith("http://") || base.startsWith("https://")) {
    return `${base}/${normalizedPath}${query}`;
  }

  return `${base}/${normalizedPath}${query}`;
}

export function apiV1(path: string) {
  const normalized = path.startsWith("/") ? path : `/${path}`;
  return `/api/v1${normalized}`;
}

// --- Moio Auth & User Management (OpenAPI-aligned) ---

/** POST /api/v1/auth/login/ request */
export interface MoioAuthLoginRequest {
  email?: string;
  username?: string;
  password: string;
}

/** POST /api/v1/auth/login/ response 200 */
export interface MoioAuthLoginResponse {
  access: string;
  refresh: string;
}

/** POST /api/v1/auth/refresh/ request */
export interface MoioAuthRefreshRequest {
  refresh: string;
}

/** POST /api/v1/auth/refresh/ response 200 (rotating: new access + optional new refresh) */
export interface MoioAuthRefreshResponse {
  access: string;
  refresh?: string;
}

/** GET /api/v1/auth/me/ response 200 */
export interface MoioAuthMeResponse {
  id: number;
  username: string;
  email: string;
  full_name: string;
  role: string;
  avatar_url?: string | null;
}

/** Organization shape in user responses */
export interface MoioOrganizationRef {
  id: string;
  name: string;
}

/** GET /api/v1/users/ list item & GET /api/v1/users/{id}/ response (MoioUserRead) */
export interface MoioUserRead {
  id: number;
  email: string;
  username: string;
  first_name: string;
  last_name: string;
  full_name: string;
  phone: string;
  avatar_url: string | null;
  is_active: boolean;
  is_staff: boolean;
  is_superuser: boolean;
  role: MoioUserRole;
  groups: string[];
  organization: MoioOrganizationRef;
  last_login: string | null;
  created: string;
}

/** Allowed role enum for Moio users */
export type MoioUserRole =
  | "viewer"
  | "member"
  | "manager"
  | "tenant_admin"
  | "platform_admin";

export const MOIO_USER_ROLES: MoioUserRole[] = [
  "viewer",
  "member",
  "manager",
  "tenant_admin",
  "platform_admin",
];

/** POST /api/v1/users/ request (MoioUserWriteRequest) */
export interface MoioUserWriteRequest {
  email: string;
  username: string;
  first_name?: string;
  last_name?: string;
  phone?: string;
  is_active?: boolean;
  role?: MoioUserRole;
  password?: string;
}

/** Moio user management API: tenant-scoped CRUD at /api/v1/users/ */
export const moioUsersApi = {
  /** GET /api/v1/users/ — list users (returns array) */
  list: async (): Promise<MoioUserRead[]> => {
    const res = await apiRequest("GET", apiV1("/users/"));
    const data = await res.json();
    return Array.isArray(data) ? data : [];
  },

  /** GET /api/v1/users/{id}/ — retrieve one user */
  get: async (id: number | string): Promise<MoioUserRead> => {
    const res = await apiRequest("GET", apiV1(`/users/${id}/`));
    return res.json();
  },

  /** POST /api/v1/users/ — create user. Required: email, username. Optional: first_name, last_name, phone, is_active, role, password. */
  create: async (data: MoioUserWriteRequest): Promise<MoioUserRead> => {
    const res = await apiRequest("POST", apiV1("/users/"), { data });
    return res.json();
  },

  /** PATCH /api/v1/users/{id}/ — partial update */
  update: async (id: number | string, data: Partial<MoioUserWriteRequest>): Promise<MoioUserRead> => {
    const res = await apiRequest("PATCH", apiV1(`/users/${id}/`), { data });
    return res.json();
  },

  /** PUT /api/v1/users/{id}/ — full replace (typically email, username required) */
  replace: async (id: number | string, data: MoioUserWriteRequest): Promise<MoioUserRead> => {
    const res = await apiRequest("PUT", apiV1(`/users/${id}/`), { data });
    return res.json();
  },

  /** DELETE /api/v1/users/{id}/ — 204 no body */
  delete: async (id: number | string): Promise<void> => {
    const res = await apiRequest("DELETE", apiV1(`/users/${id}/`));
    if (res.status !== 204 && res.headers.get("content-type")?.includes("application/json")) {
      await res.json();
    }
  },
};

// Desktop Agent API types and functions
export interface DesktopAgentSession {
  session_id: string;
  active: boolean;
  started_at: string;
  last_interaction: string;
  current_agent?: string;
  last_message_preview?: string | null;
}

export interface DesktopAgentStatus {
  configured: boolean;
  agent_id?: string;
  agent_name?: string;
}

export interface DesktopAgentInfo {
  id: string;
  name: string;
  description?: string;
}

export const desktopAgentApi = {
  getSessions: () => {
    return apiV1("/desktop-agent/sessions/");
  },
  getSession: (id: string) => {
    return apiV1(`/desktop-agent/sessions/${id}/`);
  },
  closeSession: (id: string) => {
    return apiV1(`/desktop-agent/sessions/${id}/close/`);
  },
  getStatus: () => {
    return apiV1("/desktop-agent/status/");
  },
  getAgents: () => {
    return apiV1("/desktop-agent/agents/");
  },
  setAgent: () => {
    return apiV1("/desktop-agent/set-agent/");
  },
};

// Data Lab API - Import types
import type {
  DataLabFile,
  FileSet,
  ResultSet,
  ImportContract,
  ColumnDefinition,
  CRMView,
  CRMQueryRequest,
  Script,
  ScriptExecuteRequest,
  ScriptExecuteResponse,
  Pipeline,
  PipelineRun,
  Panel,
  Widget,
  WidgetType,
  WidgetConfig,
  RenderedWidget,
  WidgetData,
  Snapshot,
  PaginatedResponse,
  ImportProcess,
  ImportRun,
  ShapeDescription,
} from "./moio-types";
import { apiRequest } from "./queryClient";

// Data Lab API client
export const dataLabApi = {
  // Files
  uploadFile: async (
    file: File,
    filename?: string,
    onProgress?: (progress: number) => void
  ): Promise<DataLabFile> => {
    const formData = new FormData();
    formData.append("file", file);
    if (filename) formData.append("filename", filename);

    // Use XMLHttpRequest for progress tracking (fetch doesn't support progress)
    if (onProgress) {
      return new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        const url = createApiUrl(apiV1("/datalab/files/"));
        const headers = getAuthHeaders();

        xhr.upload.addEventListener("progress", (e) => {
          if (e.lengthComputable) {
            onProgress((e.loaded / e.total) * 100);
          }
        });

        xhr.addEventListener("load", () => {
          if (xhr.status >= 200 && xhr.status < 300) {
            resolve(JSON.parse(xhr.responseText));
          } else {
            reject(new Error(`Upload failed: ${xhr.statusText}`));
          }
        });

        xhr.addEventListener("error", () => reject(new Error("Upload failed")));

        xhr.open("POST", url);
        Object.entries(headers).forEach(([key, value]) => {
          if (typeof value === "string") {
            xhr.setRequestHeader(key, value);
          }
        });
        xhr.send(formData);
      });
    }

    // Fallback to fetch if no progress callback
    const res = await apiRequest("POST", apiV1("/datalab/files/"), {
      body: formData,
    });
    return res.json();
  },

  getFileContent: async (fileId: string): Promise<Blob> => {
    const res = await apiRequest("GET", apiV1(`/datalab/files/${fileId}/download/`), {
      headers: { Accept: "*/*" },
    });
    return res.blob();
  },

  deleteFile: async (fileId: string): Promise<void> => {
    await apiRequest("DELETE", apiV1(`/datalab/files/${fileId}/`));
  },

  listFiles: async (
    page = 1,
    pageSize = 20
  ): Promise<PaginatedResponse<DataLabFile>> => {
    const res = await apiRequest("GET", apiV1("/datalab/files/"), {
      params: { page, page_size: pageSize },
    });
    const data = await res.json();
    console.log("listFiles API raw response:", data);
    
    // Handle both paginated response and plain array
    if (Array.isArray(data)) {
      console.log("API returned array, converting to paginated format");
      return {
        count: data.length,
        next: null,
        previous: null,
        results: data,
      };
    }
    
    // If it's already paginated, return as-is
    if (data.results && Array.isArray(data.results)) {
      return data;
    }
    
    // Fallback: wrap in paginated format
    console.warn("Unexpected API response format, attempting to normalize:", data);
    return {
      count: data.count || 0,
      next: data.next || null,
      previous: data.previous || null,
      results: data.results || data.data || data.files || [],
    };
  },

  // FileSets
  createFileSet: async (data: {
    name: string;
    description?: string;
    files: string[];
  }): Promise<FileSet> => {
    const res = await apiRequest("POST", apiV1("/datalab/filesets/"), { data });
    return res.json();
  },

  listFileSets: async (): Promise<FileSet[]> => {
    const res = await apiRequest("GET", apiV1("/datalab/filesets/"));
    return res.json();
  },

  // Imports
  previewImport: async (data: {
    source: { file_id: string };
    contract: ImportContract;
  }): Promise<{
    detected_schema: ColumnDefinition[];
    sample_rows: Record<string, any>[];
    row_count: number;
    warnings: string[];
  }> => {
    // Backend expects contract_json as an object (dictionary), not a string
    const requestData = {
      source: data.source,
      contract_json: data.contract,
    };
    console.log("Preview import request:", requestData);
    const res = await apiRequest("POST", apiV1("/datalab/imports/preview/"), {
      data: requestData,
    });
    return res.json();
  },

  executeImport: async (data: {
    source: { file_id?: string; fileset_id?: string };
    contract: ImportContract;
    rebuild?: boolean;
  }): Promise<{
    resultset_id: string;
    schema: ColumnDefinition[];
    row_count: number;
    preview: Record<string, any>[];
    snapshot_id?: string;
  }> => {
    // Backend expects contract_json as an object (dictionary), not a string
    const requestData = {
      source: data.source,
      contract_json: data.contract,
      rebuild: data.rebuild,
    };
    console.log("Execute import request:", requestData);
    const res = await apiRequest("POST", apiV1("/datalab/imports/execute/"), {
      data: requestData,
    });
    return res.json();
  },

  // Import Processes (control plane v3.1)
  createImportProcess: async (data: {
    name: string;
    file_type: "csv" | "excel" | "pdf";
    file_id: string;
    import_data_as_json?: boolean; // optional, default false - skip auto DF creation and output JSON instead
  }): Promise<ImportProcess> => {
    const res = await apiRequest("POST", apiV1("/datalab/import-processes/"), {
      data,
    });
    return res.json();
  },

  listImportProcesses: async (
    page = 1,
    pageSize = 20,
    filters?: Record<string, any>
  ): Promise<PaginatedResponse<ImportProcess>> => {
    const params = { page, page_size: pageSize, ...filters };
    const res = await apiRequest("GET", apiV1("/datalab/import-processes/"), {
      params,
    });
    const data = await res.json();

    if (Array.isArray(data)) {
      return {
        count: data.length,
        next: null,
        previous: null,
        results: data,
      };
    }
    if (data.results && Array.isArray(data.results)) {
      return data;
    }
    return {
      count: data.count || 0,
      next: data.next || null,
      previous: data.previous || null,
      results: data.results || data.data || [],
    };
  },

  getImportProcess: async (id: string): Promise<ImportProcess> => {
    const res = await apiRequest("GET", apiV1(`/datalab/import-processes/${id}/`));
    return res.json();
  },

  updateImportProcess: async (
    id: string,
    data: Partial<ImportProcess>
  ): Promise<ImportProcess> => {
    const res = await apiRequest("PATCH", apiV1(`/datalab/import-processes/${id}/`), {
      data,
    });
    return res.json();
  },

  runImportProcess: async (
    id: string,
    data: { raw_dataset_id: string }
  ): Promise<ImportRun> => {
    const res = await apiRequest("POST", apiV1(`/datalab/import-processes/${id}/run/`), {
      data,
    });
    return res.json();
  },

  cloneImportProcess: async (
    id: string,
    data?: { name?: string }
  ): Promise<ImportProcess> => {
    const res = await apiRequest("POST", apiV1(`/datalab/import-processes/${id}/clone/`), {
      data,
    });
    return res.json();
  },

  listImportRuns: async (
    page = 1,
    pageSize = 20,
    filters?: Record<string, any>
  ): Promise<PaginatedResponse<ImportRun>> => {
    const params = { page, page_size: pageSize, ...filters };
    const res = await apiRequest("GET", apiV1("/datalab/import-runs/"), {
      params,
    });
    const data = await res.json();

    if (Array.isArray(data)) {
      return {
        count: data.length,
        next: null,
        previous: null,
        results: data,
      };
    }
    if (data.results && Array.isArray(data.results)) {
      return data;
    }
    return {
      count: data.count || 0,
      next: data.next || null,
      previous: data.previous || null,
      results: data.results || data.data || [],
    };
  },

  inspectProcessShape: async (data: {
    file_id: string;
    file_type: "csv" | "excel" | "pdf";
  }): Promise<{
    fingerprint: string;
    description: ShapeDescription;
  }> => {
    const res = await apiRequest("POST", apiV1("/datalab/import-processes/inspect-shape/"), {
      data,
    });
    return res.json();
  },

  // CRM DataSources
  listCRMViews: async (): Promise<CRMView[]> => {
    const res = await apiRequest("GET", apiV1("/datalab/crm/views/"));
    const data = await res.json();
    // Handle both array and paginated response
    if (Array.isArray(data)) {
      return data;
    }
    if (data.results && Array.isArray(data.results)) {
      return data.results;
    }
    return [];
  },

  getCRMView: async (key: string): Promise<CRMView> => {
    // URL encode the key to handle special characters like dots
    const encodedKey = encodeURIComponent(key);
    const res = await apiRequest("GET", apiV1(`/datalab/crm/views/${encodedKey}/`));
    return res.json();
  },

  executeCRMQuery: async (data: CRMQueryRequest): Promise<{
    resultset_id: string;
    schema: ColumnDefinition[];
    row_count: number;
    preview: Record<string, any>[];
  }> => {
    const res = await apiRequest("POST", apiV1("/datalab/crm/query/query/"), {
      data,
    });
    return res.json();
  },

  // Scripts
  // Note: Backend returns input_spec/output_spec but may accept input_spec_json/output_spec_json
  // We send both versions to ensure compatibility
  createScript: async (data: {
    name: string;
    slug?: string;
    description?: string;
    code: string;
    input_spec_json?: Record<string, any>;
    output_spec_json?: Record<string, any>;
    input_spec?: Record<string, any>;
    output_spec?: Record<string, any>;
    version_notes?: string;
  }): Promise<Script> => {
    // Send with both field name variants for compatibility
    const payload = {
      ...data,
      input_spec: data.input_spec || data.input_spec_json,
      output_spec: data.output_spec || data.output_spec_json,
    };
    const res = await apiRequest("POST", apiV1("/datalab/scripts/"), { data: payload });
    return res.json();
  },

  updateScript: async (
    id: string,
    data: {
      name?: string;
      slug?: string;
      description?: string;
      code?: string;
      input_spec_json?: Record<string, any>;
      output_spec_json?: Record<string, any>;
      input_spec?: Record<string, any>;
      output_spec?: Record<string, any>;
    }
  ): Promise<Script> => {
    // Send with both field name variants for compatibility
    const payload = {
      ...data,
      input_spec: data.input_spec || data.input_spec_json,
      output_spec: data.output_spec || data.output_spec_json,
    };
    const res = await apiRequest("PATCH", apiV1(`/datalab/scripts/${id}/`), { data: payload });
    return res.json();
  },

  listScripts: async (): Promise<Script[]> => {
    const res = await apiRequest("GET", apiV1("/datalab/scripts/"));
    return res.json();
  },

  getScript: async (id: string): Promise<Script> => {
    const res = await apiRequest("GET", apiV1(`/datalab/scripts/${id}/`));
    return res.json();
  },

  getScriptSpec: async (id: string): Promise<{
    input_spec: any;
    output_spec: any;
  }> => {
    const res = await apiRequest("GET", apiV1(`/datalab/scripts/${id}/spec/`));
    return res.json();
  },

  executeScript: async (
    id: string,
    data: ScriptExecuteRequest
  ): Promise<ScriptExecuteResponse> => {
    const res = await apiRequest("POST", apiV1(`/datalab/scripts/${id}/execute/`), {
      data,
    });
    return res.json();
  },

  // Pipelines
  createPipeline: async (data: {
    name: string;
    description?: string;
    steps_json: any[];
    params_json: any[];
  }): Promise<Pipeline> => {
    const res = await apiRequest("POST", apiV1("/datalab/pipelines/"), { data });
    return res.json();
  },

  listPipelines: async (): Promise<Pipeline[]> => {
    const res = await apiRequest("GET", apiV1("/datalab/pipelines/"));
    const data = await res.json();
    // Handle both array and paginated response
    if (Array.isArray(data)) {
      return data;
    }
    if (data.results && Array.isArray(data.results)) {
      return data.results;
    }
    return [];
  },

  executePipeline: async (
    id: string,
    data: { params: Record<string, any> }
  ): Promise<PipelineRun> => {
    const res = await apiRequest("POST", apiV1(`/datalab/pipelines/${id}/run/`), {
      data,
    });
    return res.json();
  },

  listPipelineRuns: async (id: string): Promise<PipelineRun[]> => {
    const res = await apiRequest("GET", apiV1(`/datalab/pipelines/${id}/runs/`));
    return res.json();
  },

  getPipelineRunHistory: async (pipeline?: string): Promise<PipelineRun[]> => {
    const res = await apiRequest("GET", apiV1("/datalab/pipeline-runs/"), {
      params: pipeline ? { pipeline } : undefined,
    });
    return res.json();
  },

  // Panels & Widgets
  createPanel: async (data: {
    name: string;
    description?: string;
    layout_json: any;
    is_public?: boolean;
    shared_with_roles?: string[];
  }): Promise<Panel> => {
    const res = await apiRequest("POST", apiV1("/datalab/panels/"), { data });
    return res.json();
  },

  listPanels: async (): Promise<Panel[]> => {
    const res = await apiRequest("GET", apiV1("/datalab/panels/"));
    const data = await res.json();
    // Handle both array and paginated response
    if (Array.isArray(data)) {
      return data;
    }
    if (data.results && Array.isArray(data.results)) {
      return data.results;
    }
    return [];
  },

  renderPanel: async (id: string): Promise<{
    panel: Panel;
    widgets: RenderedWidget[];
    layout: any;
  }> => {
    const res = await apiRequest("GET", apiV1(`/datalab/panels/${id}/render/`));
    return res.json();
  },

  createWidget: async (data: {
    panel: string;
    name: string;
    widget_type: WidgetType;
    datasource_id: string;
    config_json: WidgetConfig;
    position_x: number;
    position_y: number;
    width: number;
    height: number;
    order: number;
  }): Promise<Widget> => {
    const res = await apiRequest("POST", apiV1("/datalab/widgets/"), { data });
    return res.json();
  },

  renderWidget: async (id: string): Promise<{
    widget: Widget;
    data: WidgetData;
  }> => {
    const res = await apiRequest("GET", apiV1(`/datalab/widgets/${id}/render/`));
    return res.json();
  },

  // ResultSets & Snapshots
  getResultSet: async (id: string): Promise<ResultSet> => {
    const res = await apiRequest("GET", apiV1(`/datalab/resultsets/${id}/`));
    return res.json();
  },

  listResultSets: async (
    origin?: string,
    page = 1,
    pageSize = 20
  ): Promise<PaginatedResponse<ResultSet>> => {
    const res = await apiRequest("GET", apiV1("/datalab/resultsets/"), {
      params: { origin, page, page_size: pageSize },
    });
    const data = await res.json();

    // Handle both paginated response and plain array
    if (Array.isArray(data)) {
      return {
        count: data.length,
        next: null,
        previous: null,
        results: data,
      };
    }

    if (data.results && Array.isArray(data.results)) {
      return data;
    }

    // Fallback: wrap unknown shape
    return {
      count: data.count || 0,
      next: data.next || null,
      previous: data.previous || null,
      results: data.results || data.data || [],
    };
  },

  materializeResultSet: async (id: string): Promise<ResultSet> => {
    const res = await apiRequest(
      "POST",
      apiV1(`/datalab/resultsets/${id}/materialize/`)
    );
    return res.json();
  },

  createSnapshot: async (data: {
    name: string;
    resultset_id: string;
    fileset?: string;
    description?: string;
  }): Promise<Snapshot> => {
    const res = await apiRequest("POST", apiV1("/datalab/snapshots/"), { data });
    return res.json();
  },

  listSnapshots: async (name?: string): Promise<Snapshot[]> => {
    const res = await apiRequest("GET", apiV1("/datalab/snapshots/"), {
      params: name ? { name } : undefined,
    });
    return res.json();
  },

  inspectImportShape: async (fileId: string): Promise<{
    fingerprint: string;
    description: any;
  }> => {
    const res = await apiRequest("POST", apiV1("/datalab/imports/inspect-shape/"), {
      data: { source: { file_id: fileId } },
    });
    return res.json();
  },

  // Datasets (durable, versioned - produced by pipelines or promotion)
  listDatasets: async (
    page = 1,
    pageSize = 20
  ): Promise<PaginatedResponse<any>> => {
    const res = await apiRequest("GET", apiV1("/datalab/datasets/"), {
      params: { page, page_size: pageSize },
    });
    const data = await res.json();
    // Handle both paginated response and plain array
    if (Array.isArray(data)) {
      return { count: data.length, next: null, previous: null, results: data };
    }
    return data;
  },

  getDataset: async (id: string): Promise<any> => {
    const res = await apiRequest("GET", apiV1(`/datalab/datasets/${id}/`));
    return res.json();
  },

  // Promote a ResultSet to a Dataset
  promoteResultSet: async (resultSetId: string, name?: string): Promise<any> => {
    const res = await apiRequest("POST", apiV1(`/datalab/resultsets/${resultSetId}/promote/`), {
      data: name ? { name } : {},
    });
    return res.json();
  },

  // Update a ResultSet (rename)
  updateResultSet: async (id: string, data: { name?: string }): Promise<ResultSet> => {
    const res = await apiRequest("PATCH", apiV1(`/datalab/resultsets/${id}/`), { data });
    return res.json();
  },

  // Delete a ResultSet
  deleteResultSet: async (id: string): Promise<void> => {
    await apiRequest("DELETE", apiV1(`/datalab/resultsets/${id}/`));
  },
};
