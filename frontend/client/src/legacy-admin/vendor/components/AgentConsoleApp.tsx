// @ts-nocheck
import { useEffect, useMemo, useRef, useState } from "react";
import {
  installPromptEventName,
  isInstallPromptAvailable,
  promptInstall,
  registerPwa,
  requestGeolocation,
  requestPushNotifications,
  showBrowserNotification,
} from "../lib/pwa";
import {
  clearPublicSessions,
  getActiveTenantSessionContext,
  setActiveTenantSessionContext,
} from "../lib/publicAuthApi";
import { tenantBootstrap } from "../lib/tenantAdminApi";
import { getAccessToken, getRefreshToken, setAccessToken } from "@/lib/api";
import { useToast } from "@/hooks/use-toast";
import { resolveApiBase, resolveWebSocketBase } from "../lib/runtimeConfig";
import { MarkdownRenderer } from "@/components/docs/markdown-renderer";

type SessionRow = {
  sessionKey: string;
  title: string;
  scope: "shared" | "private";
  messageCount: number;
  updatedAtMs: number;
};

type UsageTotals = {
  input: number;
  output: number;
  total: number;
};

type UiMessage = {
  id: string;
  role: "user" | "assistant" | "system";
  text: string;
  authorLabel?: string;
  runId?: string;
  usage?: UsageTotals | null;
  exchangedFiles?: ExchangedFileRef[];
};

type RunStatus = "idle" | "queued" | "thinking" | "tools" | "done" | "aborted" | "error";

type ToolEvent = {
  id: string;
  text: string;
  phase: string;
};

type QueuedTurn = {
  id: string;
  message: string;
  attachmentsCount: number;
  createdAtMs: number;
  selectedProfile: string;
  authorId: number;
  authorEmail: string;
  authorLabel: string;
};

type AuthUser = {
  id: number;
  email: string;
  displayName: string;
  tenantId: string;
  tenantRole: string;
  tenantAdmin: boolean;
};

type PendingAttachment = {
  id: string;
  file: File;
  name: string;
  type: string;
  size: number;
  previewUrl: string;
};

type ExchangedFileRef = {
  id: string;
  name: string;
  url: string;
  mimeType: string;
  source: "uploaded" | "generated";
};

type AgentConfig = {
  tenant: string;
  workspace: string;
  sessionKey: string;
  model: string;
  vendor: string;
  thinking: string;
  verbosity: string;
};

type TenantWorkspaceOption = {
  value: string;
  uuid: string;
  slug: string;
  name: string;
};

const PUBLIC_TENANTS_STORAGE_KEY = "moio_public_tenants";
const AUTH_BASE = resolveApiBase("/api/auth", import.meta.env.VITE_PLATFORM_ADMIN_AUTH_BASE);
const WS_BASE = resolveWebSocketBase(import.meta.env.VITE_WS_BASE_URL);

const FOLLOW_THRESHOLD_PX = 96;
const MAX_PENDING_ATTACHMENTS = 8;
const MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024;

function resolveBackendOrigin(): string {
  if (typeof window === "undefined") return "";
  const candidates = [resolveApiBase("/", undefined), AUTH_BASE, WS_BASE];
  for (const candidate of candidates) {
    const value = String(candidate || "").trim();
    if (!value) continue;
    try {
      const parsed = new URL(value, window.location.origin);
      const protocol = parsed.protocol.toLowerCase();
      if (protocol === "ws:" || protocol === "wss:") {
        const httpProtocol = protocol === "wss:" ? "https:" : "http:";
        return `${httpProtocol}//${parsed.host}`;
      }
      return parsed.origin;
    } catch {
      // ignore malformed URL candidates
    }
  }
  return window.location.origin;
}

function resolveFileUrl(value: unknown): string {
  const raw = String(value ?? "").trim();
  if (!raw) return "";
  if (/^https?:\/\//i.test(raw)) return raw;
  if (raw.startsWith("//")) {
    if (typeof window === "undefined") return `https:${raw}`;
    return `${window.location.protocol}${raw}`;
  }
  if (raw.startsWith("/")) {
    const origin = resolveBackendOrigin();
    return origin ? `${origin}${raw}` : raw;
  }
  return raw;
}

function isPreviewableFile(file: ExchangedFileRef): boolean {
  const mime = String(file.mimeType || "").toLowerCase();
  if (mime.startsWith("image/")) return true;
  if (mime === "application/pdf") return true;
  const lowerName = file.name.toLowerCase();
  return lowerName.endsWith(".png") || lowerName.endsWith(".jpg") || lowerName.endsWith(".jpeg") || lowerName.endsWith(".webp") || lowerName.endsWith(".gif") || lowerName.endsWith(".pdf");
}

function hasAccessChoicesFromStorage(): boolean {
  const hasPlatformToken = Boolean((getAccessToken() ?? "").trim());
  const rawTenants = (() => {
    try {
      const raw = localStorage.getItem(PUBLIC_TENANTS_STORAGE_KEY);
      return raw ? JSON.parse(raw) : [];
    } catch {
      return [];
    }
  })();
  const tenants = Array.isArray(rawTenants) ? rawTenants : [];
  const canTenant = hasPlatformToken && tenants.length > 0;
  const tenantChoices =
    canTenant &&
    (tenants.length > 1 ||
      tenants.some((row) => {
        const workspaces = Array.isArray((row as Record<string, unknown>)?.workspaces)
          ? ((row as Record<string, unknown>).workspaces as unknown[])
          : [];
        return workspaces.length > 1;
      }));
  const destinationChoices = canTenant && hasPlatformToken;
  return Boolean(tenantChoices || destinationChoices);
}

function normalizeSessionKey(value: unknown): string {
  const key = String(value ?? "").trim();
  return key || "main";
}

function normalizeSessionScope(value: unknown): "shared" | "private" {
  return String(value ?? "").trim().toLowerCase() === "private" ? "private" : "shared";
}

function textFromContent(content: unknown): string {
  if (!Array.isArray(content)) return "";
  return content
    .map((entry) => {
      if (!entry || typeof entry !== "object") return "";
      const text = (entry as { text?: unknown }).text;
      return typeof text === "string" ? text : "";
    })
    .filter(Boolean)
    .join("\n")
    .trim();
}

function labelFromActor(value: unknown): string {
  if (!value || typeof value !== "object") return "";
  const actor = value as Record<string, unknown>;
  const displayName = String(actor.displayName ?? "").trim();
  if (displayName) return displayName;
  const email = String(actor.email ?? "").trim();
  if (email) return email;
  return "";
}

function usageFromAny(value: unknown): UsageTotals | null {
  if (!value || typeof value !== "object") return null;
  const usage = value as Record<string, unknown>;
  const input = Number(usage.input ?? usage.prompt_tokens ?? 0) || 0;
  const output = Number(usage.output ?? usage.completion_tokens ?? 0) || 0;
  let total = Number(usage.total ?? usage.totalTokens ?? usage.total_tokens ?? 0) || 0;
  if (total <= 0) total = input + output;
  if (total <= 0 && input <= 0 && output <= 0) return null;
  return { input, output, total };
}

function formatUsage(usage: UsageTotals | null | undefined): string {
  if (!usage) return "";
  const nf = new Intl.NumberFormat();
  return `tokens ${nf.format(usage.total)} (in ${nf.format(usage.input)}, out ${nf.format(usage.output)})`;
}

function compactToolDetail(value: string, maxLen = 220): string {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  if (!text) return "";
  if (text.length <= maxLen) return text;
  return `${text.slice(0, maxLen - 1).trimEnd()}…`;
}

function formatElapsedMs(value: unknown): string {
  const ms = Number(value);
  if (!Number.isFinite(ms) || ms < 0) return "";
  if (ms < 1000) return `${Math.trunc(ms)}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.round(ms / 1000)}s`;
}

function isNonTerminalStatus(status: RunStatus): boolean {
  return status === "queued" || status === "thinking" || status === "tools";
}

function statusBadgeClass(status: RunStatus): string {
  if (status === "done") return "border-emerald-200 bg-emerald-50 text-emerald-700";
  if (status === "queued" || status === "thinking" || status === "tools") {
    return "animate-pulse border-amber-200 bg-amber-50 text-amber-700";
  }
  if (status === "error") return "border-rose-200 bg-rose-50 text-rose-700";
  if (status === "aborted") return "border-slate-300 bg-slate-100 text-slate-700";
  return "border-slate-200 bg-slate-50 text-slate-700";
}

function formatLoopEventText(data: Record<string, unknown>): string {
  const human = String(data.humanMessage ?? data.phaseLabel ?? "working").trim();
  const detailParts: string[] = [];
  const step = Number(data.step ?? 0);
  const maxSteps = Number(data.maxSteps ?? 0);
  const progressPct = Number(data.progressPct ?? 0);
  const count = Number(data.count ?? 0);
  const toolCalls = Number(data.toolCalls ?? 0);
  const outputChars = Number(data.outputChars ?? 0);
  const retryCount = Number(data.retryCount ?? 0);
  const elapsed = formatElapsedMs(data.elapsedMs);

  if (Number.isFinite(step) && step > 0 && Number.isFinite(maxSteps) && maxSteps > 0) {
    detailParts.push(`step ${Math.trunc(step)}/${Math.trunc(maxSteps)}`);
  }
  if (Number.isFinite(progressPct) && progressPct > 0) {
    detailParts.push(`${Math.trunc(progressPct)}%`);
  }
  if (elapsed) {
    detailParts.push(`+${elapsed}`);
  }
  if (Number.isFinite(count) && count > 0) {
    detailParts.push(`${Math.trunc(count)} tool call${Math.trunc(count) === 1 ? "" : "s"}`);
  }
  if (Number.isFinite(toolCalls) && toolCalls > 0) {
    detailParts.push(`${Math.trunc(toolCalls)} tool call${Math.trunc(toolCalls) === 1 ? "" : "s"}`);
  }
  if (Number.isFinite(outputChars) && outputChars > 0) {
    detailParts.push(`${Math.trunc(outputChars)} chars`);
  }
  if (Number.isFinite(retryCount) && retryCount > 0) {
    detailParts.push(`retry ${Math.trunc(retryCount)}`);
  }
  if (typeof data.reason === "string" && data.reason.trim()) {
    detailParts.push(data.reason.trim());
  }
  if (Array.isArray(data.toolNames) && data.toolNames.length > 0) {
    const toolNames = data.toolNames
      .slice(0, 4)
      .map((item) => String(item || "").trim())
      .filter(Boolean);
    if (toolNames.length > 0) {
      detailParts.push(toolNames.join(", "));
    }
  }

  return detailParts.length > 0 ? `${human} (${detailParts.join(" · ")})` : human;
}

function extractToolEventDetail(name: string, phase: string, data: Record<string, unknown>): string {
  const rawResult = String(data.result ?? "").trim();
  const rawError = String(data.error ?? "").trim();
  const fallback = rawError || rawResult;
  if (!fallback) return "";

  let parsed: Record<string, unknown> | null = null;
  try {
    const obj = JSON.parse(rawResult || fallback);
    if (obj && typeof obj === "object") parsed = obj as Record<string, unknown>;
  } catch {
    parsed = null;
  }

  if (!parsed) return compactToolDetail(fallback);

  const nestedError = parsed.error;
  if (nestedError && typeof nestedError === "object") {
    const nested = nestedError as Record<string, unknown>;
    const nestedMessage = String(nested.message ?? nested.detail ?? "").trim();
    if (nestedMessage) return compactToolDetail(nestedMessage);
  }
  if (typeof nestedError === "string" && nestedError.trim()) {
    return compactToolDetail(nestedError);
  }

  const message = String(parsed.message ?? parsed.detail ?? "").trim();
  if (message) return compactToolDetail(message);

  if (name === "api.run") {
    const statusCode = Number(parsed.status_code ?? 0) || 0;
    const ok = Boolean(parsed.ok ?? false);
    if (phase === "error" || !ok || statusCode >= 400) {
      const statusText = statusCode > 0 ? `HTTP ${statusCode}` : "request failed";
      return compactToolDetail(statusText);
    }
  }

  return compactToolDetail(fallback);
}

function humanFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function truncateName(name: string, max = 32): string {
  const value = (name || "").trim();
  if (!value || value.length <= max) return value || "file";
  const extIdx = value.lastIndexOf(".");
  if (extIdx > 0 && extIdx < value.length - 1) {
    const ext = value.slice(extIdx);
    const stem = value.slice(0, extIdx);
    return `${stem.slice(0, Math.max(8, max - ext.length - 3))}...${ext}`;
  }
  return `${value.slice(0, max - 3)}...`;
}

function clearAuthState(): void {
  clearPublicSessions();
  document.cookie = "tenant=; Max-Age=0; Path=/; SameSite=Lax";
  document.cookie = "workspace=; Max-Age=0; Path=/; SameSite=Lax";
}

function fileHintsFromMessageMeta(item: Record<string, unknown>, baseText: string): string {
  const lines: string[] = [];
  if (!baseText.includes("[Attachments:") && !baseText.includes("[Attachment paths]")) {
    const attachments = Array.isArray(item.attachments) ? item.attachments : [];
    for (const entry of attachments.slice(0, 4)) {
      if (!entry || typeof entry !== "object") continue;
      const row = entry as Record<string, unknown>;
      const name = String(row.name ?? "").trim() || "attachment";
      const summary = String(row.summary ?? "").trim();
      lines.push(summary ? `- ${name}: ${summary}` : `- ${name}`);
    }
  }
  const generatedFiles = Array.isArray(item.generatedFiles) ? item.generatedFiles : [];
  for (const entry of generatedFiles.slice(0, 4)) {
    if (!entry || typeof entry !== "object") continue;
    const row = entry as Record<string, unknown>;
    const name = String(row.name ?? "").trim() || "generated file";
    const downloadUrl = resolveFileUrl(row.downloadUrl);
    if (downloadUrl) {
      lines.push(`- [${name}](${downloadUrl})`);
      continue;
    }
    lines.push(`- ${name}`);
  }
  if (!lines.length) return "";
  return `\n\nFiles referenced in this turn:\n${lines.join("\n")}`;
}

function exchangedFilesFromMessageMeta(item: Record<string, unknown>): ExchangedFileRef[] {
  const out: ExchangedFileRef[] = [];
  const seen = new Set<string>();

  const pushEntry = (entry: Record<string, unknown>, source: "uploaded" | "generated") => {
    const name = String(entry.name ?? "").trim() || "file";
    const url = resolveFileUrl(entry.downloadUrl ?? entry.localUrl);
    const mimeType = String(entry.mimeType ?? "").trim();
    if (!url) return;
    const id = `${source}|${name}|${url}`;
    if (seen.has(id)) return;
    seen.add(id);
    out.push({ id, name, url, mimeType, source });
  };

  const attachments = Array.isArray(item.attachments) ? item.attachments : [];
  for (const entry of attachments) {
    if (!entry || typeof entry !== "object") continue;
    pushEntry(entry as Record<string, unknown>, "uploaded");
  }

  const generatedFiles = Array.isArray(item.generatedFiles) ? item.generatedFiles : [];
  for (const entry of generatedFiles) {
    if (!entry || typeof entry !== "object") continue;
    pushEntry(entry as Record<string, unknown>, "generated");
  }

  return out;
}

function toUiMessages(rows: unknown[]): UiMessage[] {
  const out: UiMessage[] = [];
  for (const row of rows) {
    if (!row || typeof row !== "object") continue;
    const item = row as Record<string, unknown>;
    const roleRaw = String(item.role ?? "").trim().toLowerCase();
    if (roleRaw !== "user" && roleRaw !== "assistant" && roleRaw !== "system") continue;
    const runId = String(item.runId ?? "").trim();
    const baseText = textFromContent(item.content);
    const text = `${baseText}${fileHintsFromMessageMeta(item, baseText)}`.trim();
    if (!text) continue;
    const usage = usageFromAny(item.usage);
    const authorLabel = labelFromActor(item.author) || labelFromActor(item.owner);
    const exchangedFiles = exchangedFilesFromMessageMeta(item);
    const fallbackId = `${roleRaw}-${String(item.timestamp ?? Date.now())}-${out.length}`;
    out.push({
      id: runId ? `${roleRaw}-${runId}` : fallbackId,
      role: roleRaw,
      runId,
      text,
      authorLabel,
      usage,
      exchangedFiles,
    });
  }
  return out;
}

function normalizeSessions(rows: unknown[]): SessionRow[] {
  const parsed: SessionRow[] = [];
  for (const row of rows) {
    if (!row || typeof row !== "object") continue;
    const item = row as Record<string, unknown>;
    parsed.push({
      sessionKey: normalizeSessionKey(item.sessionKey),
      title: String(item.title ?? "").trim(),
      scope: normalizeSessionScope(item.scope),
      messageCount: Number(item.messageCount ?? 0) || 0,
      updatedAtMs: Number(item.updatedAtMs ?? 0) || 0,
    });
  }
  if (!parsed.some((x) => x.sessionKey === "main")) {
    parsed.push({ sessionKey: "main", title: "", scope: "shared", messageCount: 0, updatedAtMs: 0 });
  }
  parsed.sort((a, b) => b.updatedAtMs - a.updatedAtMs);
  return parsed;
}

function normalizeQueuedTurns(rows: unknown[]): QueuedTurn[] {
  const parsed: QueuedTurn[] = [];
  for (const row of rows) {
    if (!row || typeof row !== "object") continue;
    const item = row as Record<string, unknown>;
    const id = String(item.id ?? item.queueItemId ?? "").trim();
    if (!id) continue;
    const rawMessage = String(item.message ?? "").trim();
    const attachmentsCount = Number(item.attachmentsCount ?? 0) || 0;
    parsed.push({
      id,
      message: rawMessage || (attachmentsCount > 0 ? "Attached files only." : ""),
      attachmentsCount: Math.max(0, attachmentsCount),
      createdAtMs: Number(item.createdAtMs ?? 0) || 0,
      selectedProfile: String(item.selectedProfile ?? "").trim(),
      authorId: Number(((item.author as Record<string, unknown> | undefined)?.id ?? 0)) || 0,
      authorEmail: String(((item.author as Record<string, unknown> | undefined)?.email ?? "")).trim().toLowerCase(),
      authorLabel: labelFromActor(item.author) || "User",
    });
  }
  parsed.sort((a, b) => a.createdAtMs - b.createdAtMs);
  return parsed;
}

function buildClientSessionKey(): string {
  const stamp = Date.now().toString(36);
  const nonce = Math.random().toString(36).slice(2, 6);
  return `chat-${stamp}-${nonce}`;
}

function queuedTurnOwnedByUser(item: QueuedTurn, user: AuthUser | null): boolean {
  if (!user) return false;
  if (item.authorId > 0 && user.id > 0 && item.authorId === user.id) return true;
  return Boolean(item.authorEmail && user.email && item.authorEmail === user.email);
}

function sessionScopeForKey(rows: SessionRow[], sessionKey: string): "shared" | "private" {
  const normalizedKey = normalizeSessionKey(sessionKey);
  const match = rows.find((row) => normalizeSessionKey(row.sessionKey) === normalizedKey);
  return normalizeSessionScope(match?.scope);
}

function decorateResourcesSummary(
  rows: Array<[string, string]>,
  sessionKey: string,
  scope: "shared" | "private",
): Array<[string, string]> {
  const filtered = rows.filter(([label]) => label !== "Session" && label !== "Conversation");
  const sessionRows: Array<[string, string]> = [
    ["Session", normalizeSessionKey(sessionKey)],
    ["Conversation", scope],
  ];
  if (filtered.length <= 2) {
    return [...filtered, ...sessionRows];
  }
  return [...filtered.slice(0, 2), ...sessionRows, ...filtered.slice(2)];
}

const ACCESS_HUB_PATH = "/desktop-agent-console/";
const AGENT_CONSOLE_PATH = "/desktop-agent-console/console/";
const TENANT_ADMIN_PATH = "/desktop-agent-console/tenant-admin/";

export default function AgentConsoleApp() {
  const { toast } = useToast();
  const location = useMemo(() => ({ search: window.location.search }), []);
  const query = useMemo(() => new URLSearchParams(location.search), [location.search]);
  const activeTenantContext = useMemo(() => getActiveTenantSessionContext(), []);
  const tenantIdFromQuery = (query.get("tenantId") || activeTenantContext?.tenantId || "").trim();
  const workspaceIdFromQuery = (query.get("workspaceId") || activeTenantContext?.workspaceId || "").trim();
  const tenantFromQuery = (() => {
    const explicit = (query.get("tenant") || "").trim().toLowerCase();
    if (explicit) return explicit;
    const activeTenant = String(activeTenantContext?.tenantSchema || activeTenantContext?.tenantSlug || "")
      .trim()
      .toLowerCase();
    if (activeTenant) return activeTenant;
    return "public";
  })();
  const workspaceFromQuery = (() => {
    const explicit = (query.get("workspace") || "").trim().toLowerCase();
    if (explicit) return explicit;
    const activeWorkspace = String(activeTenantContext?.workspaceSlug || "").trim().toLowerCase();
    if (activeWorkspace) return activeWorkspace;
    return "main";
  })();

  const [config, setConfig] = useState<AgentConfig>({
    tenant: tenantFromQuery,
    workspace: workspaceFromQuery,
    sessionKey: "main",
    model: "gpt-4.1-mini",
    vendor: "openai",
    thinking: "default",
    verbosity: "minimal",
  });
  const [gatewayConnected, setGatewayConnected] = useState(false);
  const [messages, setMessages] = useState<UiMessage[]>([]);
  const [sessions, setSessions] = useState<SessionRow[]>([]);
  const [queuedTurns, setQueuedTurns] = useState<QueuedTurn[]>([]);
  const [usage, setUsage] = useState<UsageTotals>({ input: 0, output: 0, total: 0 });
  const [summaryOpen, setSummaryOpen] = useState(false);
  const [snapshotOpen, setSnapshotOpen] = useState(false);
  const [summaryTitle, setSummaryTitle] = useState("");
  const [summaryText, setSummaryText] = useState("");
  const [summaryMeta, setSummaryMeta] = useState("");
  const [messageInput, setMessageInput] = useState("");
  const [pendingAttachments, setPendingAttachments] = useState<PendingAttachment[]>([]);
  const [runStatus, setRunStatus] = useState<RunStatus>("idle");
  const [runStatusMeta, setRunStatusMeta] = useState("waiting for a message");
  const [streamingRunIds, setStreamingRunIds] = useState<Set<string>>(new Set());
  const [resourcesSummary, setResourcesSummary] = useState<Array<[string, string]>>([]);
  const [toolEvents, setToolEvents] = useState<ToolEvent[]>([]);
  const [showJumpToLatest, setShowJumpToLatest] = useState(false);
  const [sessionLoading, setSessionLoading] = useState(false);
  const [sendInFlight, setSendInFlight] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [rightRailTab, setRightRailTab] = useState<"status" | "activity">("activity");
  const [sessionSearch, setSessionSearch] = useState("");
  const [socketRetryTick, setSocketRetryTick] = useState(0);
  const [hasAccessChoices, setHasAccessChoices] = useState(false);
  const [backendWorkspaceOptions, setBackendWorkspaceOptions] = useState<TenantWorkspaceOption[] | null>(null);
  const [installAvailable, setInstallAvailable] = useState(() => isInstallPromptAvailable());
  const [pushState, setPushState] = useState(() => {
    if (typeof window === "undefined" || typeof Notification === "undefined") return "unsupported";
    return Notification.permission || "default";
  });
  const [geoState, setGeoState] = useState("not shared");
  const [authUser, setAuthUser] = useState<AuthUser | null>(null);
  const [filePreview, setFilePreview] = useState<ExchangedFileRef | null>(null);
  const exchangedFiles = useMemo(() => {
    const seen = new Set<string>();
    const out: ExchangedFileRef[] = [];
    for (const message of messages) {
      const entries = Array.isArray(message.exchangedFiles) ? message.exchangedFiles : [];
      for (const entry of entries) {
        const key = `${entry.source}|${entry.name}|${entry.url}`;
        if (seen.has(key)) continue;
        seen.add(key);
        out.push(entry);
      }
    }
    return out;
  }, [messages]);

  const wsRef = useRef<WebSocket | null>(null);
  const chatScrollRef = useRef<HTMLDivElement | null>(null);
  const composerInputRef = useRef<HTMLTextAreaElement | null>(null);
  const activeSessionRef = useRef(config.sessionKey);
  const draftByRunRef = useRef<Map<string, string>>(new Map());
  const liveMessageIdByRunRef = useRef<Map<string, string>>(new Map());
  const reconnectTimerRef = useRef<number | null>(null);
  const reconnectAttemptRef = useRef(0);
  const sessionLoadingTimeoutRef = useRef<number | null>(null);
  const authRefreshInFlightRef = useRef<Promise<boolean> | null>(null);
  const fatalSocketErrorRef = useRef<string>("");

  function pushToolEvent(text: string, phase: string): void {
    setToolEvents((prev) => {
      const next: ToolEvent[] = [
        ...prev,
        {
          id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
          text,
          phase,
        },
      ];
      return next.slice(-120);
    });
  }

  function markSessionActivity(sessionKey: string, scope: "shared" | "private"): void {
    setToolEvents([
      {
        id: `session-${Date.now()}-${Math.random().toString(16).slice(2)}`,
        text: `${scope === "private" ? "Private" : "Shared"} conversation · ${normalizeSessionKey(sessionKey)}`,
        phase: "session",
      },
    ]);
    setResourcesSummary((prev) => decorateResourcesSummary(prev, sessionKey, scope));
  }

  async function refreshMainAccessToken(): Promise<boolean> {
    if (authRefreshInFlightRef.current) return authRefreshInFlightRef.current;
    const refreshToken = String(getRefreshToken() ?? "").trim();
    if (!refreshToken) return false;
    const task = (async () => {
      try {
        const refreshed = await fetch(`${AUTH_BASE}/refresh`, {
          method: "POST",
          credentials: "same-origin",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh: refreshToken }),
        });
        const refreshedData = await refreshed.json().catch(() => ({}));
        const renewedAccess = String(
          (refreshedData as Record<string, unknown>)?.payload &&
            typeof (refreshedData as Record<string, unknown>).payload === "object"
            ? ((refreshedData as Record<string, unknown>).payload as Record<string, unknown>).access ?? ""
            : "",
        ).trim();
        if (!refreshed.ok || !renewedAccess) return false;
        setAccessToken(renewedAccess);
        return true;
      } catch {
        return false;
      } finally {
        authRefreshInFlightRef.current = null;
      }
    })();
    authRefreshInFlightRef.current = task;
    return task;
  }

  useEffect(() => {
    activeSessionRef.current = config.sessionKey;
  }, [config.sessionKey]);

  useEffect(() => {
    if (tenantFromQuery === "public") return;
    const current = getActiveTenantSessionContext();
    setActiveTenantSessionContext({
      tenantId: tenantIdFromQuery || current?.tenantId || "",
      tenantSlug: current?.tenantSlug || "",
      tenantSchema: tenantFromQuery,
      workspaceId: workspaceIdFromQuery || current?.workspaceId || "",
      workspaceSlug: workspaceFromQuery || current?.workspaceSlug || "main",
    });
  }, [tenantFromQuery, tenantIdFromQuery, workspaceFromQuery, workspaceIdFromQuery]);

  useEffect(() => {
    setHasAccessChoices(hasAccessChoicesFromStorage());
  }, []);

  useEffect(() => {
    let active = true;
    const accessToken = String(getAccessToken() ?? "").trim();
    if (!accessToken) {
      setBackendWorkspaceOptions(null);
      return;
    }
    void tenantBootstrap(workspaceFromQuery || "main")
      .then((payload) => {
        if (!active) return;
        const rows = Array.isArray(payload.workspaces) ? payload.workspaces : [];
        const options = rows
          .map((entry) => {
            const slug = String(entry?.slug ?? "").trim().toLowerCase();
            if (!slug) return null;
            const uuid = String(entry?.id ?? "").trim();
            return {
              value: uuid || slug,
              uuid,
              slug,
              name: String(entry?.name ?? entry?.displayName ?? slug).trim() || slug,
            };
          })
          .filter((entry): entry is TenantWorkspaceOption => Boolean(entry));
        setBackendWorkspaceOptions(options.length ? options : [{ value: "main", uuid: "", slug: "main", name: "main" }]);
      })
      .catch(() => {
        if (!active) return;
        setBackendWorkspaceOptions(null);
      });
    return () => {
      active = false;
    };
  }, [workspaceFromQuery, workspaceIdFromQuery, socketRetryTick]);

  useEffect(() => {
    const eventName = installPromptEventName();
    const syncInstallAvailability = () => {
      setInstallAvailable(isInstallPromptAvailable());
    };
    syncInstallAvailability();
    void registerPwa().finally(syncInstallAvailability);
    window.addEventListener(eventName, syncInstallAvailability as EventListener);
    return () => {
      window.removeEventListener(eventName, syncInstallAvailability as EventListener);
    };
  }, []);

  useEffect(() => {
    const accessToken = String(getAccessToken() ?? "").trim();
    if (!accessToken) {
      const url = new URL(window.location.origin + ACCESS_HUB_PATH);
      if (workspaceIdFromQuery) url.searchParams.set("nextWorkspaceId", workspaceIdFromQuery);
      if (workspaceFromQuery) url.searchParams.set("nextWorkspace", workspaceFromQuery);
      window.location.replace(url.toString());
      return;
    }
    if (reconnectTimerRef.current !== null) {
      window.clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }

    let disposed = false;
    const scheduleReconnect = () => {
      if (disposed || tenantFromQuery === "public") return;
      if (fatalSocketErrorRef.current) return;
      const latestToken = String(getAccessToken() ?? "").trim();
      if (!latestToken || reconnectTimerRef.current !== null) return;
      const nextAttempt = reconnectAttemptRef.current + 1;
      reconnectAttemptRef.current = nextAttempt;
      const delayMs = Math.min(5000, 500 * 2 ** Math.min(nextAttempt - 1, 3));
      setRunStatus("idle");
      setRunStatusMeta(nextAttempt > 1 ? `reconnecting (${nextAttempt})` : "reconnecting");
      reconnectTimerRef.current = window.setTimeout(() => {
        reconnectTimerRef.current = null;
        if (disposed) return;
        setSocketRetryTick((prev) => prev + 1);
      }, delayMs);
    };
    const wsQuery = new URLSearchParams();
    if (workspaceFromQuery) wsQuery.set("workspace", workspaceFromQuery);
    if (workspaceIdFromQuery) wsQuery.set("workspaceId", workspaceIdFromQuery);
    if (accessToken) wsQuery.set("accessToken", accessToken);
    const wsBase = (WS_BASE || "").replace(/\/+$/, "");
    const wsUrl = `${wsBase}/agent-console${wsQuery.toString() ? `?${wsQuery.toString()}` : ""}`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      if (wsRef.current !== ws) return;
      fatalSocketErrorRef.current = "";
      setGatewayConnected(true);
      const wasReconnect = reconnectAttemptRef.current > 0;
      reconnectAttemptRef.current = 0;
      if (wasReconnect) {
        setRunStatus("idle");
        setRunStatusMeta("reconnected");
        ws.send(
          JSON.stringify({
            action: "init",
            sessionKey: activeSessionRef.current,
          }),
        );
      }
    };
    ws.onclose = (event) => {
      if (wsRef.current !== ws) return;
      if (sessionLoadingTimeoutRef.current !== null) {
        window.clearTimeout(sessionLoadingTimeoutRef.current);
        sessionLoadingTimeoutRef.current = null;
      }
      setGatewayConnected(false);
      setSessionLoading(false);
      setSendInFlight(false);
      wsRef.current = null;
      if (event.code === 4401) {
        setRunStatus("idle");
        setRunStatusMeta("auth expired, refreshing session");
        void (async () => {
          const refreshed = await refreshMainAccessToken();
          if (refreshed) {
            reconnectAttemptRef.current = 0;
            setRunStatusMeta("auth refreshed, reconnecting");
            setSocketRetryTick((prev) => prev + 1);
            return;
          }
          clearAuthState();
          const url = new URL(window.location.origin + ACCESS_HUB_PATH);
          if (workspaceIdFromQuery) url.searchParams.set("nextWorkspaceId", workspaceIdFromQuery);
          if (workspaceFromQuery) url.searchParams.set("nextWorkspace", workspaceFromQuery);
          window.location.replace(url.toString());
        })();
        return;
      }
      if (fatalSocketErrorRef.current) {
        return;
      }
      scheduleReconnect();
    };
    ws.onerror = () => {
      if (wsRef.current !== ws) return;
      setGatewayConnected(false);
      setSessionLoading(false);
    };
    ws.onmessage = (event) => {
      if (wsRef.current !== ws) return;
      try {
        const frame = JSON.parse(String(event.data || "{}")) as Record<string, unknown>;
        handleFrame(frame);
      } catch {
        // Ignore malformed frames.
      }
    };

    return () => {
      disposed = true;
      if (sessionLoadingTimeoutRef.current !== null) {
        window.clearTimeout(sessionLoadingTimeoutRef.current);
        sessionLoadingTimeoutRef.current = null;
      }
      if (reconnectTimerRef.current !== null) {
        window.clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      if (wsRef.current === ws) {
        wsRef.current = null;
      }
      ws.close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantFromQuery, workspaceFromQuery, workspaceIdFromQuery, socketRetryTick]);

  useEffect(() => {
    const container = chatScrollRef.current;
    if (!container) return;
    const onScroll = () => {
      const distance = container.scrollHeight - container.clientHeight - container.scrollTop;
      setShowJumpToLatest(distance > FOLLOW_THRESHOLD_PX);
    };
    container.addEventListener("scroll", onScroll, { passive: true });
    return () => container.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    const container = chatScrollRef.current;
    if (!container || showJumpToLatest) return;
    container.scrollTop = container.scrollHeight;
  }, [messages, showJumpToLatest]);

  function sendAction(action: string, payload: Record<string, unknown> = {}): boolean {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return false;
    ws.send(JSON.stringify({ action, ...payload }));
    return true;
  }

  function beginSessionSwitch(nextSessionKey: string): void {
    if (sessionLoadingTimeoutRef.current !== null) {
      window.clearTimeout(sessionLoadingTimeoutRef.current);
      sessionLoadingTimeoutRef.current = null;
    }
    setSessionLoading(true);
    draftByRunRef.current.clear();
    liveMessageIdByRunRef.current.clear();
    setMessages([]);
    setQueuedTurns([]);
    setUsage({ input: 0, output: 0, total: 0 });
    const historyRequested = sendAction("chat_history", { sessionKey: nextSessionKey });
    if (!historyRequested) {
      setSessionLoading(false);
      setRunStatus("error");
      setRunStatusMeta("connection offline");
      return;
    }
    sendAction("chat_queue", { sessionKey: nextSessionKey });
    sendAction("chat_summary", { sessionKey: nextSessionKey });
    sendAction("chat_usage", { sessionKey: nextSessionKey });
    sessionLoadingTimeoutRef.current = window.setTimeout(() => {
      sessionLoadingTimeoutRef.current = null;
      setSessionLoading(false);
    }, 12000);
  }

  function applyQueuePayload(envelope: Record<string, unknown>): void {
    const payload = (envelope.payload as Record<string, unknown>) || {};
    const sessionKey = normalizeSessionKey(payload.sessionKey);
    if (sessionKey !== normalizeSessionKey(activeSessionRef.current)) return;
    const rows = Array.isArray(payload.items) ? payload.items : [];
    setQueuedTurns(normalizeQueuedTurns(rows));
  }

  function handleInit(frame: Record<string, unknown>): void {
    const payload = (frame.payload as Record<string, unknown>) || {};
    const authPayload = (payload.authUser as Record<string, unknown>) || {};
    setAuthUser({
      id: Number(authPayload.id ?? 0) || 0,
      email: String(authPayload.email ?? "").trim().toLowerCase(),
      displayName: String(authPayload.displayName ?? "").trim(),
      tenantId: String(authPayload.tenantId ?? "").trim(),
      tenantRole: String(authPayload.tenantRole ?? "").trim().toLowerCase(),
      tenantAdmin: Boolean(authPayload.tenantAdmin),
    });
    const cfg = (payload.agentConfig as Record<string, unknown>) || {};
    const nextSession = normalizeSessionKey(cfg.sessionKey);
    setConfig((prev) => ({
      ...prev,
      tenant: String(cfg.tenant ?? prev.tenant),
      workspace: String(cfg.workspace ?? prev.workspace),
      sessionKey: nextSession,
      model: String(cfg.model ?? prev.model),
      vendor: String(cfg.vendor ?? prev.vendor),
      thinking: String(cfg.thinking ?? prev.thinking ?? "default") || "default",
      verbosity: String(cfg.verbosity ?? prev.verbosity ?? "minimal") || "minimal",
    }));
    activeSessionRef.current = nextSession;

    const historyEnvelope = (payload.chatHistory as Record<string, unknown>) || {};
    const historyPayload = (historyEnvelope.payload as Record<string, unknown>) || {};
    const rows = Array.isArray(historyPayload.messages) ? historyPayload.messages : [];
    setMessages(toUiMessages(rows));

    const queueEnvelope = (payload.chatQueue as Record<string, unknown>) || {};
    const queuePayload = (queueEnvelope.payload as Record<string, unknown>) || {};
    const queueRows = Array.isArray(queuePayload.items) ? queuePayload.items : [];
    setQueuedTurns(normalizeQueuedTurns(queueRows));

    const usageEnvelope = (payload.chatUsage as Record<string, unknown>) || {};
    const usagePayload = (usageEnvelope.payload as Record<string, unknown>) || {};
    setUsage({
      input: Number(usagePayload.input ?? 0) || 0,
      output: Number(usagePayload.output ?? 0) || 0,
      total: Number(usagePayload.total ?? 0) || 0,
    });

    const summaryEnvelope = (payload.chatSummary as Record<string, unknown>) || {};
    const summaryPayload = (summaryEnvelope.payload as Record<string, unknown>) || {};
    const summary = String(summaryPayload.summary ?? "");
    const title = String(summaryPayload.title ?? "");
    const summaryUpTo = Number(summaryPayload.summaryUpTo ?? 0) || 0;
    setSummaryTitle(title);
    setSummaryText(summary);
    setSummaryMeta(`session: ${nextSession} | covered messages: ${summaryUpTo}`);

    const sessionsEnvelope = (payload.chatSessions as Record<string, unknown>) || {};
    const sessionsPayload = (sessionsEnvelope.payload as Record<string, unknown>) || {};
    const nextSessions = normalizeSessions(Array.isArray(sessionsPayload.sessions) ? sessionsPayload.sessions : []);
    setSessions(nextSessions);
    const activeScope = sessionScopeForKey(nextSessions, nextSession);

    const resourcesEnvelope = (payload.resources as Record<string, unknown>) || {};
    setResourcesSummary(decorateResourcesSummary(buildResourcesSummary(resourcesEnvelope), nextSession, activeScope));
    markSessionActivity(nextSession, activeScope);
    setRunStatus("idle");
    setRunStatusMeta("ready");
    setSessionLoading(false);
  }

  function handleFrame(frame: Record<string, unknown>): void {
    const type = String(frame.type ?? "");
    if (type === "init") {
      handleInit(frame);
      return;
    }

    if (type === "auth_expiring") {
      setRunStatusMeta("session expiring, refreshing auth");
      void (async () => {
        const refreshed = await refreshMainAccessToken();
        if (!refreshed) return;
        if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
          setRunStatusMeta("auth refreshed, reconnecting");
          wsRef.current.close(4002, "auth_refreshed");
        }
      })();
      return;
    }

    if (type === "resources") {
      const envelope = (frame.payload as Record<string, unknown>) || {};
      setResourcesSummary(
        decorateResourcesSummary(
          buildResourcesSummary(envelope),
          activeSessionRef.current,
          sessionScopeForKey(sessions, activeSessionRef.current),
        ),
      );
      return;
    }

    if (type === "chat_history") {
      const envelope = (frame.payload as Record<string, unknown>) || {};
      const payload = (envelope.payload as Record<string, unknown>) || {};
      const sessionKey = normalizeSessionKey(payload.sessionKey);
      if (sessionKey !== normalizeSessionKey(activeSessionRef.current)) return;
      if (sessionLoadingTimeoutRef.current !== null) {
        window.clearTimeout(sessionLoadingTimeoutRef.current);
        sessionLoadingTimeoutRef.current = null;
      }
      const rows = Array.isArray(payload.messages) ? payload.messages : [];
      setMessages(toUiMessages(rows));
      setSessionLoading(false);
      return;
    }

    if (type === "chat_usage") {
      const envelope = (frame.payload as Record<string, unknown>) || {};
      const payload = (envelope.payload as Record<string, unknown>) || {};
      const sessionKey = normalizeSessionKey(payload.sessionKey);
      if (sessionKey !== normalizeSessionKey(activeSessionRef.current)) return;
      setUsage({
        input: Number(payload.input ?? 0) || 0,
        output: Number(payload.output ?? 0) || 0,
        total: Number(payload.total ?? 0) || 0,
      });
      return;
    }

    if (type === "chat_queue" || type === "chat_queue_retire" || type === "chat_queue_force_push") {
      const envelope = (frame.payload as Record<string, unknown>) || {};
      applyQueuePayload(envelope);
      return;
    }

    if (type === "chat_summary") {
      const envelope = (frame.payload as Record<string, unknown>) || {};
      const payload = (envelope.payload as Record<string, unknown>) || {};
      const sessionKey = normalizeSessionKey(payload.sessionKey);
      if (sessionKey !== normalizeSessionKey(activeSessionRef.current)) return;
      const title = String(payload.title ?? "");
      const summary = String(payload.summary ?? "");
      const summaryUpTo = Number(payload.summaryUpTo ?? 0) || 0;
      setSummaryTitle(title);
      setSummaryText(summary);
      setSummaryMeta(`session: ${sessionKey} | covered messages: ${summaryUpTo}`);
      return;
    }

    if (type === "chat_sessions_list") {
      const envelope = (frame.payload as Record<string, unknown>) || {};
      const payload = (envelope.payload as Record<string, unknown>) || {};
      const rows = Array.isArray(payload.sessions) ? payload.sessions : [];
      const nextSessions = normalizeSessions(rows);
      setSessions(nextSessions);
      setResourcesSummary((prev) =>
        decorateResourcesSummary(prev, activeSessionRef.current, sessionScopeForKey(nextSessions, activeSessionRef.current)),
      );
      return;
    }

    if (type === "chat_session_create") {
      const envelope = (frame.payload as Record<string, unknown>) || {};
      const payload = (envelope.payload as Record<string, unknown>) || {};
      const rows = Array.isArray(payload.sessions) ? payload.sessions : [];
      const nextSessions = normalizeSessions(rows);
      setSessions(nextSessions);
      const created = (payload.session as Record<string, unknown>) || {};
      const key = normalizeSessionKey(created.sessionKey);
      const scope = normalizeSessionScope(created.scope ?? sessionScopeForKey(nextSessions, key));
      setConfig((prev) => ({ ...prev, sessionKey: key }));
      activeSessionRef.current = key;
      markSessionActivity(key, scope);
      beginSessionSwitch(key);
      return;
    }

    if (type === "chat_session_set_scope") {
      const envelope = (frame.payload as Record<string, unknown>) || {};
      const payload = (envelope.payload as Record<string, unknown>) || {};
      const rows = Array.isArray(payload.sessions) ? payload.sessions : [];
      const nextSessions = normalizeSessions(rows);
      setSessions(nextSessions);
      const activeScope = sessionScopeForKey(nextSessions, activeSessionRef.current);
      markSessionActivity(activeSessionRef.current, activeScope);
      setResourcesSummary((prev) => decorateResourcesSummary(prev, activeSessionRef.current, activeScope));
      setRunStatus("idle");
      setRunStatusMeta(activeScope === "shared" ? "conversation shared" : "conversation is private");
      return;
    }

    if (type === "chat_send_ack") {
      const envelope = (frame.payload as Record<string, unknown>) || {};
      const result = (((envelope.result as Record<string, unknown>)?.payload ?? {}) as Record<string, unknown>) || {};
      const status = String(result.status ?? "").trim().toLowerCase();
      const queueEnvelope = (result.queue as Record<string, unknown>) || {};
      if (Object.keys(queueEnvelope).length > 0) {
        applyQueuePayload(queueEnvelope);
      }
      if (status === "queued") {
        const queuePosition = Number(result.queuePosition ?? 0) || 0;
        setRunStatus("queued");
        setRunStatusMeta(queuePosition > 0 ? `queued (#${queuePosition})` : "queued");
      } else {
        setRunStatus("queued");
        setRunStatusMeta("starting");
      }
      setSendInFlight(false);
      return;
    }

    if (type === "agent_event") {
      const payload = (frame.payload as Record<string, unknown>) || {};
      const sessionKey = normalizeSessionKey(payload.sessionKey);
      if (sessionKey !== normalizeSessionKey(activeSessionRef.current)) return;
      const stream = String(payload.stream ?? "");
      const data = (payload.data as Record<string, unknown>) || {};
      if (stream === "loop") {
        const status = String(data.status ?? "thinking") as RunStatus;
        const human = String(data.humanMessage ?? data.phaseLabel ?? "working");
        setRunStatus(
          status === "done" || status === "queued" || status === "thinking" || status === "tools" || status === "aborted" || status === "error"
            ? status
            : "thinking"
        );
        setRunStatusMeta(human);
        pushToolEvent(formatLoopEventText(data), `loop:${String(data.phase ?? "event")}`);
      } else if (stream === "tool") {
        const name = String(data.name ?? "tool");
        const phase = String(data.phase ?? "event");
        const detail = extractToolEventDetail(name, phase, data);
        pushToolEvent(detail ? `${name} · ${phase} · ${detail}` : `${name} · ${phase}`, phase);
      }
      return;
    }

    if (type === "chat_event") {
      const payload = (frame.payload as Record<string, unknown>) || {};
      const sessionKey = normalizeSessionKey(payload.sessionKey);
      if (sessionKey !== normalizeSessionKey(activeSessionRef.current)) return;
      const runId = String(payload.runId ?? "");
      const state = String(payload.state ?? "");
      if (state === "delta") {
        const chunkMessage = (payload.message as Record<string, unknown>) || {};
        const chunk = textFromContent(chunkMessage.content);
        if (!chunk) return;
        if (runId) {
          setStreamingRunIds((prev) => {
            if (prev.has(runId)) return prev;
            const next = new Set(prev);
            next.add(runId);
            return next;
          });
        }
        const existing = draftByRunRef.current.get(runId) || "";
        const next = existing + chunk;
        draftByRunRef.current.set(runId, next);
        const liveMessageId = liveMessageIdByRunRef.current.get(runId);
        if (liveMessageId) {
          setMessages((prev) =>
            prev.map((item) => (item.id === liveMessageId ? { ...item, text: next } : item)),
          );
        } else {
          const messageId = `assistant-${runId || Date.now()}`;
          liveMessageIdByRunRef.current.set(runId, messageId);
          setMessages((prev) => {
            const existingIndex = runId ? prev.findIndex((item) => item.runId === runId && item.role === "assistant") : -1;
            if (existingIndex >= 0) {
              return prev.map((item, index) =>
                index === existingIndex ? { ...item, id: messageId, text: next, runId } : item,
              );
            }
            return [
              ...prev,
              {
                id: messageId,
                role: "assistant",
                runId,
                text: next,
              },
            ];
          });
        }
        setRunStatus("thinking");
        return;
      }
      if (state === "accepted") {
        const message = (payload.message as Record<string, unknown>) || {};
        const parsed = toUiMessages([message]);
        const acceptedMessage = parsed[0];
        if (acceptedMessage) {
          setMessages((prev) => {
            const existingIndex = runId ? prev.findIndex((item) => item.runId === runId && item.role === "user") : -1;
            if (existingIndex >= 0) {
              return prev.map((item, index) => (index === existingIndex ? { ...acceptedMessage, id: item.id } : item));
            }
            return [...prev, acceptedMessage];
          });
        }
        setRunStatus("queued");
        setRunStatusMeta("processing");
        sendAction("chat_sessions_list", { limit: 300 });
        return;
      }
      if (state === "final") {
        if (runId) {
          setStreamingRunIds((prev) => {
            if (!prev.has(runId)) return prev;
            const next = new Set(prev);
            next.delete(runId);
            return next;
          });
        }
        const message = (payload.message as Record<string, unknown>) || {};
        const parsed = toUiMessages([message]);
        const finalMessage = parsed[0];
        const liveMessageId = liveMessageIdByRunRef.current.get(runId);
        if (liveMessageId) {
          const draft = draftByRunRef.current.get(runId) || "";
          const finalText = finalMessage?.text || draft || "(no text)";
          const nextUsage = finalMessage?.usage;
          setMessages((prev) =>
            prev.map((item) =>
              item.id === liveMessageId
                ? {
                    ...item,
                    ...(finalMessage || {}),
                    id: item.id,
                    text: finalText,
                    usage: nextUsage ?? finalMessage?.usage ?? item.usage,
                    runId: runId || item.runId,
                  }
                : item,
            ),
          );
        } else if (finalMessage) {
          setMessages((prev) => {
            const existingIndex = runId ? prev.findIndex((item) => item.runId === runId && item.role === "assistant") : -1;
            if (existingIndex >= 0) {
              return prev.map((item, index) => (index === existingIndex ? { ...finalMessage, id: item.id } : item));
            }
            return [...prev, finalMessage];
          });
        }
        draftByRunRef.current.delete(runId);
        liveMessageIdByRunRef.current.delete(runId);
        setRunStatus("done");
        setRunStatusMeta("completed");
        sendAction("chat_usage", { sessionKey });
        sendAction("chat_summary", { sessionKey });
        sendAction("chat_sessions_list", { limit: 300 });
        return;
      }
      if (state === "aborted") {
        if (runId) {
          setStreamingRunIds((prev) => {
            if (!prev.has(runId)) return prev;
            const next = new Set(prev);
            next.delete(runId);
            return next;
          });
        }
        const liveMessageId = liveMessageIdByRunRef.current.get(runId);
        if (liveMessageId) {
          setMessages((prev) => prev.filter((item) => item.id !== liveMessageId));
        }
        draftByRunRef.current.delete(runId);
        liveMessageIdByRunRef.current.delete(runId);
        setRunStatus("aborted");
        setRunStatusMeta(String(payload.errorMessage ?? "aborted"));
        return;
      }
      if (state === "error") {
        if (runId) {
          setStreamingRunIds((prev) => {
            if (!prev.has(runId)) return prev;
            const next = new Set(prev);
            next.delete(runId);
            return next;
          });
        }
        const liveMessageId = liveMessageIdByRunRef.current.get(runId);
        if (liveMessageId) {
          setMessages((prev) => prev.filter((item) => item.id !== liveMessageId));
        }
        draftByRunRef.current.delete(runId);
        liveMessageIdByRunRef.current.delete(runId);
        setRunStatus("error");
        setRunStatusMeta(String(payload.errorMessage ?? "run failed"));
      }
      return;
    }

    if (type === "browser_notification") {
      const payload = (frame.payload as Record<string, unknown>) || {};
      const title = String(payload.title ?? "Moio");
      const body = String(payload.body ?? "The agent finished responding.");
      const tag = String(payload.tag ?? "moio-event");
      const url = String(payload.url ?? "/");
      void showBrowserNotification(title, body, tag, url, {
        icon: String(payload.icon ?? "/pwa-icon.svg"),
        badge: String(payload.badge ?? "/pwa-icon.svg"),
        requireInteraction: Boolean(payload.requireInteraction),
        renotify: Boolean(payload.renotify),
        silent: Boolean(payload.silent),
      });
      return;
    }

    if (type === "error") {
      const payload = (frame.payload as Record<string, unknown>) || (frame.error as Record<string, unknown>) || {};
      const message = String(payload.message ?? "request failed");
      const code = String(payload.code ?? "");
      const lowerMessage = message.toLowerCase();
      setSessionLoading(false);
      setSendInFlight(false);
      setRunStatus("error");
      setRunStatusMeta(message);
      if (code === "tenant_required") {
        const url = new URL(window.location.origin + ACCESS_HUB_PATH);
        if (workspaceIdFromQuery) url.searchParams.set("nextWorkspaceId", workspaceIdFromQuery);
        if (workspaceFromQuery) url.searchParams.set("nextWorkspace", workspaceFromQuery);
        window.location.replace(url.toString());
        return;
      }
      if (code === "openai_not_configured" || message.toLowerCase().includes("openai")) {
        fatalSocketErrorRef.current = code || "openai_not_configured";
        toast({
          title: "Configuración requerida",
          description: message,
          variant: "destructive",
        });
      }
      if (code === "backend_error" && lowerMessage.includes("missing model api key")) {
        fatalSocketErrorRef.current = "backend_error";
        toast({
          title: "Modelo sin configurar",
          description: "Falta API key del modelo para este tenant. Configura OpenAI en Integrations.",
          variant: "destructive",
        });
      }
    }
  }

  function buildResourcesSummary(envelope: Record<string, unknown>): Array<[string, string]> {
    const rows: Array<[string, string]> = [];
    const modelsPayload = (((envelope.models as Record<string, unknown>)?.payload ?? {}) as Record<string, unknown>) || {};
    const vendors = Array.isArray(modelsPayload.vendors) ? modelsPayload.vendors : [];
    const toolCatalogPayload =
      (((envelope.toolsCatalog as Record<string, unknown>)?.payload ?? {}) as Record<string, unknown>) || {};
    const availableTools = Array.isArray(toolCatalogPayload.available) ? toolCatalogPayload.available : [];
    const enabledTools = Array.isArray(toolCatalogPayload.enabled) ? toolCatalogPayload.enabled : [];
    const skillsPayload = (((envelope.skillsStatus as Record<string, unknown>)?.payload ?? {}) as Record<string, unknown>) || {};
    const workspacePayload =
      (((envelope.workspaceProfile as Record<string, unknown>)?.payload ?? {}) as Record<string, unknown>) || {};
    const integrationsPayload =
      (((envelope.tenantIntegrations as Record<string, unknown>)?.payload ?? {}) as Record<string, unknown>) || {};
    const tenantIntegrations = Array.isArray(integrationsPayload.integrations)
      ? (integrationsPayload.integrations as Array<Record<string, unknown>>)
      : [];
    const enabledIntegrations = Number(integrationsPayload.enabledCount ?? tenantIntegrations.length) || 0;
    const integrationLabels = tenantIntegrations
      .map((row) => String(row.key ?? row.name ?? "").trim())
      .filter(Boolean);
    rows.push(["Tenant", String(config.tenant || "public")]);
    rows.push(["Workspace", String(config.workspace || "main")]);
    rows.push(["Model", String(modelsPayload.current ?? config.model ?? "-")]);
    rows.push(["Vendors", String(vendors.length)]);
    rows.push(["Tools", `${enabledTools.length}/${availableTools.length}`]);
    rows.push(["Skills", String(Number(skillsPayload.enabledCount ?? 0) || 0)]);
    rows.push(["Integrations", String(enabledIntegrations)]);
    if (integrationLabels.length > 0) {
      const shown = integrationLabels.slice(0, 3).join(", ");
      rows.push([
        "Integration Keys",
        integrationLabels.length > 3 ? `${shown} +${integrationLabels.length - 3} more` : shown,
      ]);
    }
    rows.push(["Agent", String(workspacePayload.displayName ?? workspacePayload.name ?? config.workspace)]);
    return rows;
  }

  function selectSession(sessionKey: string): void {
    const key = normalizeSessionKey(sessionKey);
    const scope = sessionScopeForKey(sessions, key);
    setMobileMenuOpen(false);
    setConfig((prev) => ({ ...prev, sessionKey: key }));
    activeSessionRef.current = key;
    setRunStatus("idle");
    setRunStatusMeta("loading session");
    markSessionActivity(key, scope);
    beginSessionSwitch(key);
  }

  function createSession(scope: "shared" | "private" = "private"): void {
    setMobileMenuOpen(false);
    const sessionKey = `${scope === "private" ? "private" : "chat"}-${buildClientSessionKey().replace(/^chat-/, "")}`;
    const sent = sendAction("chat_session_create", { sessionKey, scope });
    if (sent) {
      setRunStatus("idle");
      setRunStatusMeta(scope === "private" ? "creating private conversation" : "creating session");
      return;
    }
    setRunStatus("error");
    setRunStatusMeta("connection offline");
  }

  function shareActiveSession(): void {
    const activeScope = sessionScopeForKey(sessions, config.sessionKey);
    if (activeScope !== "private") return;
    const sent = sendAction("chat_session_set_scope", { sessionKey: config.sessionKey, scope: "shared" });
    if (!sent) {
      setRunStatus("error");
      setRunStatusMeta("connection offline");
      return;
    }
    setRunStatus("idle");
    setRunStatusMeta("sharing conversation");
  }

  function retireQueuedTurn(queueItemId: string): void {
    const sent = sendAction("chat_queue_retire", { sessionKey: config.sessionKey, queueItemId });
    if (!sent) {
      setRunStatus("error");
      setRunStatusMeta("connection offline");
    }
  }

  function forcePushQueuedTurn(queueItemId: string): void {
    const sent = sendAction("chat_queue_force_push", { sessionKey: config.sessionKey, queueItemId });
    if (!sent) {
      setRunStatus("error");
      setRunStatusMeta("connection offline");
    }
  }

  function requestSummary(): void {
    sendAction("chat_summary", { sessionKey: config.sessionKey });
  }

  function requestUsage(): void {
    sendAction("chat_usage", { sessionKey: config.sessionKey });
  }

  function abortRun(): void {
    sendAction("abort", { sessionKey: config.sessionKey });
    setRunStatus("aborted");
    setRunStatusMeta("aborted by user");
  }

  function openTenantAdmin(): void {
    setMobileMenuOpen(false);
    const url = new URL(window.location.origin + TENANT_ADMIN_PATH);
    if (workspaceIdFromQuery) url.searchParams.set("workspaceId", workspaceIdFromQuery);
    if (!workspaceIdFromQuery) url.searchParams.set("workspace", config.workspace || "main");
    window.location.assign(url.toString());
  }

  function openAccessHub(): void {
    setMobileMenuOpen(false);
    const url = new URL(window.location.origin + ACCESS_HUB_PATH);
    if (workspaceIdFromQuery) {
      url.searchParams.set("nextWorkspaceId", workspaceIdFromQuery);
    } else if (config.workspace) {
      url.searchParams.set("nextWorkspace", config.workspace);
    }
    window.location.assign(url.toString());
  }

  function switchWorkspace(nextValue: string): void {
    const target = currentWorkspaceOptions.find((row) => row.value === nextValue);
    if (!target) return;
    if (target.value === selectedWorkspaceValue) return;
    setMobileMenuOpen(false);
    const current = getActiveTenantSessionContext();
    setActiveTenantSessionContext({
      ...(current || {
        tenantId: tenantIdFromQuery || "",
        tenantSlug: "",
        tenantSchema: config.tenant || "",
        workspaceId: "",
        workspaceSlug: "",
      }),
      tenantId: current?.tenantId || tenantIdFromQuery || "",
      tenantSlug: current?.tenantSlug || "",
      tenantSchema: current?.tenantSchema || config.tenant || "",
      workspaceId: target.uuid || "",
      workspaceSlug: target.slug || "main",
    });
    const url = new URL(window.location.origin + AGENT_CONSOLE_PATH);
    if (target.uuid) {
      url.searchParams.set("workspaceId", target.uuid);
    } else {
      url.searchParams.set("workspace", target.slug || "main");
    }
    window.location.assign(url.toString());
  }

  async function logout(): Promise<void> {
    setMobileMenuOpen(false);
    clearAuthState();
    window.location.assign(ACCESS_HUB_PATH);
  }

  async function fileToBase64(file: File): Promise<string> {
    return await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        const value = typeof reader.result === "string" ? reader.result : "";
        const idx = value.indexOf(",");
        if (idx < 0) {
          reject(new Error("Invalid file payload"));
          return;
        }
        resolve(value.slice(idx + 1));
      };
      reader.onerror = () => reject(reader.error || new Error("Read failed"));
      reader.readAsDataURL(file);
    });
  }

  function onFilesSelected(files: FileList | File[] | null): void {
    if (!files) return;
    const list = Array.from(files);
    setPendingAttachments((prev) => {
      const next = [...prev];
      for (const file of list) {
        if (next.length >= MAX_PENDING_ATTACHMENTS) break;
        if (file.size > MAX_ATTACHMENT_BYTES) continue;
        const duplicate = next.some(
          (x) =>
            x.name === file.name &&
            x.size === file.size &&
            x.type === file.type &&
            x.file.lastModified === file.lastModified
        );
        if (duplicate) continue;
        next.push({
          id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
          file,
          name: file.name || "file",
          type: file.type || "application/octet-stream",
          size: Number(file.size || 0),
          previewUrl: file.type.startsWith("image/") ? URL.createObjectURL(file) : "",
        });
      }
      return next;
    });
  }

  async function sendMessage(): Promise<void> {
    const raw = messageInput.trim();
    if (!raw && pendingAttachments.length === 0) return;
    if (sendInFlight) return;
    setSendInFlight(true);
    const composed = raw || "Please analyze attached files.";

    const encodedAttachments = [];
    for (const item of pendingAttachments) {
      try {
        const data = await fileToBase64(item.file);
        encodedAttachments.push({
          name: item.name,
          type: item.type,
          size: item.size,
          data,
        });
      } catch {
        // Skip unreadable file.
      }
    }

    const sent = sendAction("send_message", {
      sessionKey: config.sessionKey,
      message: composed,
      attachments: encodedAttachments,
      thinking: config.thinking === "default" ? undefined : config.thinking,
      verbosity: config.verbosity,
      vendor: config.vendor,
      model: config.model,
      timeoutMs: 300000,
    });
    if (!sent) {
      setSendInFlight(false);
      setRunStatus("error");
      setRunStatusMeta("connection offline");
      return;
    }

    for (const item of pendingAttachments) {
      if (item.previewUrl) URL.revokeObjectURL(item.previewUrl);
    }
    setPendingAttachments([]);
    setMessageInput("");
    setRunStatus("queued");
    setRunStatusMeta("sending");
  }

  function removePendingAttachment(id: string): void {
    setPendingAttachments((prev) => {
      const next = prev.filter((x) => x.id !== id);
      const removed = prev.find((x) => x.id === id);
      if (removed?.previewUrl) URL.revokeObjectURL(removed.previewUrl);
      return next;
    });
  }

  function applyComposerPrompt(nextPrompt: string): void {
    setMessageInput(nextPrompt);
    if (typeof window !== "undefined") {
      window.requestAnimationFrame(() => composerInputRef.current?.focus());
    }
  }

  async function installApp(): Promise<void> {
    const accepted = await promptInstall();
    setInstallAvailable(isInstallPromptAvailable());
    setRunStatusMeta(accepted ? "app installed" : "install dismissed");
  }

  async function enablePushNotifications(): Promise<void> {
    let accessToken = String(getAccessToken() ?? "").trim();
    const refreshToken = String(getRefreshToken() ?? "").trim();

    const withTenantAuth = async (path: string, init: RequestInit): Promise<Response> => {
      const execute = (token: string) =>
        fetch(path, {
          ...init,
          credentials: "same-origin",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
            ...((init.headers as Record<string, string> | undefined) ?? {}),
          },
        });
      let response = await execute(accessToken);
      if ((response.status === 401 || response.status === 403) && refreshToken) {
        const refreshed = await fetch(`${AUTH_BASE}/refresh`, {
          method: "POST",
          credentials: "same-origin",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh: refreshToken }),
        });
        const refreshedData = await refreshed.json().catch(() => ({}));
        const renewedAccess = String(
          (refreshedData as Record<string, unknown>)?.payload &&
            typeof (refreshedData as Record<string, unknown>).payload === "object"
            ? ((refreshedData as Record<string, unknown>).payload as Record<string, unknown>).access ?? ""
            : "",
        ).trim();
        if (refreshed.ok && renewedAccess) {
          accessToken = renewedAccess;
          setAccessToken(renewedAccess);
          response = await execute(renewedAccess);
        }
      }
      return response;
    };

    let vapidPublicKey = "";
    let serverPushReady = false;
    if (accessToken) {
      try {
        const response = await withTenantAuth(`${AUTH_BASE}/push-config`, { method: "GET" });
        const data = await response.json().catch(() => ({}));
        if (response.ok && data?.ok && data?.payload && typeof data.payload === "object") {
          vapidPublicKey = String((data.payload as Record<string, unknown>).publicKey ?? "").trim();
          serverPushReady = Boolean((data.payload as Record<string, unknown>).configured);
        }
      } catch {
        vapidPublicKey = "";
      }
    }

    const { permission, profile } = await requestPushNotifications(vapidPublicKey);
    setPushState(permission);
    let profileSaved = false;
    if (permission === "granted" && profile && accessToken) {
      try {
        const response = await withTenantAuth(`${AUTH_BASE}/push-subscription`, {
          method: "POST",
          body: JSON.stringify({
            permission,
            profile,
          }),
        });
        profileSaved = response.ok;
      } catch {
        profileSaved = false;
      }
    }
    if (permission === "granted") {
      if (profileSaved && serverPushReady) {
        setRunStatusMeta("push notifications enabled");
      } else if (profileSaved) {
        setRunStatusMeta("push enabled locally (server push unavailable)");
      } else {
        setRunStatusMeta("push enabled locally");
      }
      return;
    }
    if (permission === "denied") {
      setRunStatusMeta("push notifications blocked");
      return;
    }
    if (permission === "unsupported") {
      setRunStatusMeta("push notifications unsupported on this device");
      return;
    }
    setRunStatusMeta("push notifications not granted");
  }

  async function shareLocation(): Promise<void> {
    const result = await requestGeolocation();
    if (!result.ok) {
      setGeoState(result.error || "permission denied");
      setRunStatusMeta(`location unavailable: ${result.error || "permission denied"}`);
      return;
    }
    const label = `${result.latitude.toFixed(4)}, ${result.longitude.toFixed(4)} ±${Math.round(result.accuracy)}m`;
    setGeoState(label);
    setRunStatusMeta("location captured on this device");
  }

  function describePushState(value: string): string {
    if (value === "granted") return "enabled";
    if (value === "denied") return "blocked";
    if (value === "unsupported") return "unsupported";
    return "idle";
  }

  const nf = useMemo(() => new Intl.NumberFormat(), []);
  const currentWorkspaceOptions = useMemo(() => {
    if (backendWorkspaceOptions && backendWorkspaceOptions.length > 0) return backendWorkspaceOptions;
    return [{ value: "main", uuid: "", slug: "main", name: "main" }];
  }, [backendWorkspaceOptions]);
  const selectedWorkspaceValue = useMemo(() => {
    if (!currentWorkspaceOptions.length) return "main";
    if (workspaceIdFromQuery) {
      const byId = currentWorkspaceOptions.find((row) => row.uuid === workspaceIdFromQuery);
      if (byId) return byId.value;
    }
    const workspaceKey = String(config.workspace || "main").trim().toLowerCase();
    const bySlug = currentWorkspaceOptions.find((row) => row.slug === workspaceKey);
    return bySlug ? bySlug.value : currentWorkspaceOptions[0].value;
  }, [currentWorkspaceOptions, workspaceIdFromQuery, config.workspace]);
  const sessionQuery = sessionSearch.trim().toLowerCase();
  const filteredSessions = useMemo(() => {
    if (!sessionQuery) return sessions;
    return sessions.filter((row) => {
      const haystack = `${row.title} ${row.sessionKey}`.toLowerCase();
      return haystack.includes(sessionQuery);
    });
  }, [sessions, sessionQuery]);
  const composerProfileLabel = `${config.model || "default"} | ${config.thinking || "default"} | ${config.verbosity || "minimal"}`;
  const activeSessionScope = sessionScopeForKey(sessions, config.sessionKey);
  const sidebarNav = (
    <>
      <header className="border-b border-sidebar-border px-4 py-4">
        <h2 className="text-2xl font-semibold tracking-tight text-sidebar-foreground">moio</h2>
        <p className="text-xs uppercase tracking-widest text-sidebar-foreground/70">CRM Platform · Agent</p>
      </header>
      <section className="min-h-0 flex flex-1 flex-col overflow-hidden p-3">
        <div className="mb-2 flex items-center justify-between">
          <p className="font-mono text-[11px] font-semibold uppercase tracking-widest text-sidebar-primary">Sessions</p>
          <div className="flex items-center gap-2">
            <span className="rounded-full border border-sidebar-border bg-sidebar-accent px-1.5 py-0.5 font-mono text-[10px] text-sidebar-foreground">
              {filteredSessions.length}
            </span>
            <button
              type="button"
              onClick={() => createSession()}
              className="rounded-md border border-sidebar-border bg-sidebar-accent px-2 py-1 text-[11px] font-semibold text-sidebar-foreground hover:bg-sidebar-accent/80"
              title="Create private conversation"
            >
              New
            </button>
          </div>
        </div>
        <div className="mb-2">
          <input
            type="text"
            value={sessionSearch}
            onChange={(event) => setSessionSearch(event.target.value)}
            placeholder="Search sessions"
            className="w-full rounded-md border border-sidebar-border bg-sidebar-accent px-2 py-1.5 text-[12px] text-sidebar-foreground placeholder:text-sidebar-foreground/60 outline-none focus-visible:ring-2 focus-visible:ring-sidebar-ring"
          />
        </div>
        <div className="min-h-0 flex-1 space-y-1 overflow-y-auto [scrollbar-width:none] [-ms-overflow-style:none] [&::-webkit-scrollbar]:hidden">
          {filteredSessions.map((row) => {
            const active = normalizeSessionKey(row.sessionKey) === normalizeSessionKey(config.sessionKey);
            return (
              <button
                key={row.sessionKey}
                type="button"
                onClick={() => selectSession(row.sessionKey)}
                className={`w-full rounded-lg border px-3 py-2 text-left text-xs ${
                  active
                    ? "border-sidebar-primary bg-sidebar-primary/20 text-sidebar-primary-foreground"
                    : "border-sidebar-border bg-sidebar-accent/50 text-sidebar-foreground hover:bg-sidebar-accent"
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="flex min-w-0 items-center gap-1.5">
                    <div className="truncate text-[12px] font-semibold">{row.title || row.sessionKey}</div>
                    {row.scope === "shared" ? (
                      <svg
                        viewBox="0 0 24 24"
                        className="h-3.5 w-3.5 shrink-0 text-emerald-400"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="1.8"
                        aria-label="Shared conversation"
                        title="Shared conversation"
                      >
                        <circle cx="9" cy="9" r="3" />
                        <circle cx="16.5" cy="10.5" r="2.5" />
                        <path d="M4 16c0-2.2 2.2-4 5-4s5 1.8 5 4" />
                        <path d="M14 16.5c.4-1.5 1.8-2.7 3.8-2.7 1.6 0 2.9.7 3.5 1.8" />
                      </svg>
                    ) : null}
                  </div>
                </div>
                <div className="mt-0.5 font-mono text-[10px] text-sidebar-foreground/80">
                  {row.sessionKey} · {row.messageCount} messages
                </div>
              </button>
            );
          })}
          {!filteredSessions.length ? (
            <div className="rounded-lg border border-dashed border-sidebar-border bg-sidebar-accent/40 px-3 py-2 text-[11px] text-sidebar-foreground/70">
              No sessions match this search.
            </div>
          ) : null}
        </div>
      </section>
      <footer className="shrink-0 border-t border-sidebar-border px-3 py-3 text-[11px] text-sidebar-foreground">
        <div className="space-y-2.5">
          <div className="rounded-xl border border-sidebar-border bg-sidebar-accent/50 p-2.5">
            <div className="mb-2 flex items-start justify-between gap-2">
              <div className="space-y-0.5 text-[12px] leading-4">
                <div className="flex items-center gap-1.5">
                  <span className="text-sidebar-foreground/70">Tenant:</span>
                  <span className="font-semibold text-sidebar-foreground">{config.tenant}</span>
                </div>
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-1.5">
                    <span className="text-sidebar-foreground/70">Workspace:</span>
                    <span className="font-semibold text-sidebar-foreground">{config.workspace}</span>
                  </div>
                  <button
                    type="button"
                    onClick={openTenantAdmin}
                    className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md border border-sidebar-border bg-sidebar-accent text-sidebar-foreground transition hover:bg-sidebar-accent/80"
                    aria-label="Workspace settings"
                    title="Workspace settings"
                  >
                    <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="1.8">
                      <circle cx="12" cy="12" r="3.2" />
                      <path d="M19.2 15a1 1 0 0 0 .2 1.1l.1.1a1.9 1.9 0 0 1-2.7 2.7l-.1-.1a1 1 0 0 0-1.1-.2 1 1 0 0 0-.6.9v.2a1.9 1.9 0 1 1-3.8 0v-.2a1 1 0 0 0-.6-.9 1 1 0 0 0-1.1.2l-.1.1a1.9 1.9 0 0 1-2.7-2.7l.1-.1a1 1 0 0 0 .2-1.1 1 1 0 0 0-.9-.6h-.2a1.9 1.9 0 0 1 0-3.8h.2a1 1 0 0 0 .9-.6 1 1 0 0 0-.2-1.1l-.1-.1a1.9 1.9 0 0 1 2.7-2.7l.1.1a1 1 0 0 0 1.1.2 1 1 0 0 0 .6-.9v-.2a1.9 1.9 0 0 1 3.8 0v.2a1 1 0 0 0 .6.9 1 1 0 0 0 1.1-.2l.1-.1a1.9 1.9 0 0 1 2.7 2.7l-.1.1a1 1 0 0 0-.2 1.1 1 1 0 0 0 .9.6h.2a1.9 1.9 0 0 1 0 3.8h-.2a1 1 0 0 0-.9.6Z" />
                    </svg>
                  </button>
                </div>
              </div>
              {hasAccessChoices ? (
                <button
                  type="button"
                  onClick={openAccessHub}
                  className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-sidebar-border bg-sidebar-accent text-sidebar-foreground transition hover:bg-sidebar-accent/80"
                  aria-label="Switch tenant and workspace"
                  title="Switch tenant and workspace"
                >
                  <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M7 7h11l-3-3" />
                    <path d="M17 17H6l3 3" />
                  </svg>
                </button>
              ) : null}
            </div>
            <label className="mb-1 block font-mono text-[10px] font-semibold uppercase tracking-widest text-sidebar-foreground/70">
              Workspace
            </label>
            <select
              value={selectedWorkspaceValue}
              onChange={(event) => switchWorkspace(event.target.value)}
              className="w-full rounded-lg border border-sidebar-border bg-sidebar-accent px-2.5 py-1.5 text-[12px] text-sidebar-foreground outline-none focus-visible:ring-2 focus-visible:ring-sidebar-ring"
            >
              {currentWorkspaceOptions.map((row) => (
                <option key={row.value} value={row.value} className="bg-background text-foreground">
                  {row.name}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div className="mt-2.5 border-t border-sidebar-border pt-2.5">
          <div className="rounded-xl border border-sidebar-border bg-sidebar-accent/80 p-2">
            <div className="mb-2 rounded-md border border-sidebar-border bg-sidebar-accent/60 p-2">
              <div className="mb-1 font-mono text-[10px] font-semibold uppercase tracking-widest text-sidebar-foreground/70">
                Preferences
              </div>
              <div className="space-y-1.5">
                <button
                  type="button"
                  onClick={() => void installApp()}
                  disabled={!installAvailable}
                  className="flex w-full items-center justify-between rounded-md border border-sidebar-border bg-sidebar-accent px-2.5 py-1.5 text-[10px] font-semibold text-sidebar-foreground transition hover:bg-sidebar-accent/80 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <span>Install app</span>
                  <span className="text-[9px] uppercase tracking-wide text-sidebar-foreground/60">{installAvailable ? "ready" : "used"}</span>
                </button>
                <button
                  type="button"
                  onClick={() => void enablePushNotifications()}
                  className="flex w-full items-center justify-between rounded-md border border-sidebar-border bg-sidebar-accent px-2.5 py-1.5 text-[10px] font-semibold text-sidebar-foreground transition hover:bg-sidebar-accent/80"
                >
                  <span>Push notifications</span>
                  <span className="text-[9px] uppercase tracking-wide text-sidebar-foreground/60">{describePushState(pushState)}</span>
                </button>
                <button
                  type="button"
                  onClick={() => void shareLocation()}
                  className="flex w-full items-center justify-between rounded-md border border-sidebar-border bg-sidebar-accent px-2.5 py-1.5 text-[10px] font-semibold text-sidebar-foreground transition hover:bg-sidebar-accent/80"
                >
                  <span>Share location</span>
                  <span className="text-[9px] uppercase tracking-wide text-sidebar-foreground/60">
                    {geoState === "not shared" ? "idle" : "shared"}
                  </span>
                </button>
              </div>
              <div className="mt-1 text-[10px] leading-4 text-sidebar-foreground/60">
                Push: {describePushState(pushState)} · Geo: {geoState}
              </div>
            </div>
            <button
              type="button"
              onClick={openTenantAdmin}
              className="mb-1 w-full rounded-md px-2 py-1.5 text-left text-[12px] font-medium text-sidebar-foreground transition hover:bg-sidebar-accent"
            >
              Tenant Admin
            </button>
            <button
              type="button"
              onClick={logout}
              className="w-full rounded-md px-2 py-1.5 text-left text-[12px] font-medium text-sidebar-foreground transition hover:bg-sidebar-accent"
            >
              Logout
            </button>
          </div>
        </div>
      </footer>
    </>
  );

  return (
    <main className="h-screen p-2 md:p-4 text-slate-900">
      {mobileMenuOpen ? (
        <div className="fixed inset-0 z-40 bg-background/80 backdrop-blur-sm lg:hidden" onClick={() => setMobileMenuOpen(false)}>
          <aside
            className="absolute inset-y-0 left-0 flex w-[84vw] max-w-[320px] min-h-0 flex-col overflow-hidden border-r border-sidebar-border bg-sidebar text-sidebar-foreground shadow-xl"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-sidebar-border px-4 py-3 lg:hidden">
              <div className="font-mono text-[11px] font-semibold uppercase tracking-widest text-sidebar-primary">Menu</div>
              <button
                type="button"
                onClick={() => setMobileMenuOpen(false)}
                className="flex h-8 w-8 items-center justify-center rounded-md border border-sidebar-border bg-sidebar-accent text-sidebar-foreground hover:bg-sidebar-accent/80"
                aria-label="Close menu"
              >
                ×
              </button>
            </div>
            {sidebarNav}
          </aside>
        </div>
      ) : null}
      <section className="grid h-full grid-cols-1 gap-3 lg:grid-cols-[220px_minmax(0,1fr)] xl:grid-cols-[220px_minmax(0,1fr)_340px]">
        <aside className="hidden min-h-0 flex-col overflow-hidden rounded-2xl border border-sidebar-border bg-sidebar text-sidebar-foreground shadow-sm lg:flex">
          {sidebarNav}
        </aside>

        <div className="flex min-h-0 flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-[0_10px_28px_rgba(15,23,42,0.08)]">
          <header className="sticky top-0 z-10 border-b border-slate-200/80 bg-white px-3 py-2.5 md:px-5">
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-start gap-3">
                <button
                  type="button"
                  onClick={() => setMobileMenuOpen(true)}
                  className="mt-0.5 flex h-10 w-10 items-center justify-center rounded-xl border border-slate-200 bg-white/90 text-slate-700 shadow-sm lg:hidden"
                  aria-label="Open menu"
                >
                  <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M4 7h16" />
                    <path d="M4 12h16" />
                    <path d="M4 17h16" />
                  </svg>
                </button>
                <div>
                  <h1 className="text-2xl font-medium tracking-tighter text-slate-900 md:text-4xl">Agent</h1>
                  <p className="hidden text-sm text-slate-500 md:block">Your personalized command center</p>
                </div>
              </div>
              <div className="hidden md:block">
                <div className="flex items-center gap-2 rounded-2xl border border-slate-200 bg-white p-1 shadow-sm">
                  {activeSessionScope === "private" ? (
                    <button
                      type="button"
                      onClick={shareActiveSession}
                      className="rounded-xl border border-brand-200 bg-brand-50 px-3 py-1.5 text-xs font-semibold text-brand-700"
                    >
                      Share
                    </button>
                  ) : null}
                  <button
                    type="button"
                    onClick={() => {
                      requestSummary();
                      setSummaryOpen(true);
                    }}
                    className="rounded-xl border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700"
                  >
                    View Summary
                  </button>
                  <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-medium">
                    <span className={gatewayConnected ? "text-emerald-600" : "text-rose-600"}>
                      {gatewayConnected ? "connected" : "disconnected"}
                    </span>
                  </div>
                </div>
              </div>
              <div className="md:hidden">
                <div className="flex items-center gap-1.5">
                  {activeSessionScope === "private" ? (
                    <button
                      type="button"
                      onClick={shareActiveSession}
                      className="rounded-full border border-brand-200 bg-brand-50 px-2 py-1 text-[10px] font-semibold text-brand-700"
                    >
                      Share
                    </button>
                  ) : null}
                  <button
                    type="button"
                    onClick={() => {
                      requestSummary();
                      setSummaryOpen(true);
                    }}
                    className="rounded-full border border-slate-300 bg-white px-2 py-1 text-[10px] font-semibold text-slate-700"
                  >
                    Summary
                  </button>
                  <span
                    className={`inline-flex rounded-full border px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide ${statusBadgeClass(
                      runStatus,
                    )}`}
                    aria-label={`Status ${runStatus}`}
                    title={runStatusMeta}
                  >
                    {runStatus}
                  </span>
                </div>
              </div>
            </div>
          </header>

          <div className="relative min-h-0 flex-1">
            <div ref={chatScrollRef} className="h-full space-y-4 overflow-y-auto px-3 py-4 md:space-y-5 md:px-4 md:py-6">
              <div className="mx-auto w-full max-w-5xl space-y-4 md:space-y-5">
              {messages.map((msg) => {
                if (msg.role === "user") {
                  return (
                    <div key={msg.id} className="mx-auto flex w-full max-w-4xl justify-end">
                      <div className="max-w-[82%] rounded-2xl border border-brand-200 bg-brand-50/80 px-3 py-2.5 text-[13px] text-slate-800 shadow-sm md:max-w-[68%] md:px-4 md:py-3 md:text-sm">
                        <div className="mb-1 font-mono text-[10px] font-semibold uppercase tracking-widest text-brand-700">
                          {msg.authorLabel || "User"}
                        </div>
                        <div className="whitespace-pre-wrap">{msg.text}</div>
                      </div>
                    </div>
                  );
                }
                const isDraft = Boolean(msg.runId && streamingRunIds.has(msg.runId));
                return (
                  <article
                    key={msg.id}
                    className={`mx-auto w-full max-w-4xl transition-opacity duration-200 ${
                      isDraft
                        ? "text-[13px] leading-6 text-slate-500 opacity-80 md:text-[14px] md:leading-6"
                        : "text-[14px] leading-6 text-slate-800 md:text-[15px] md:leading-7"
                    }`}
                  >
                    {msg.text != null && msg.text !== "" ? (
                      <MarkdownRenderer content={msg.text} variant="light" />
                    ) : (
                      <div className="whitespace-pre-wrap">{msg.text ?? ""}</div>
                    )}
                    {msg.usage ? (
                      <div className="mt-2 font-mono text-[11px] text-slate-400">{formatUsage(msg.usage)}</div>
                    ) : null}
                  </article>
                );
              })}
              {!sessionLoading && messages.length === 0 ? (
                <div className="flex min-h-[40vh] items-center justify-center">
                  <div className="w-full max-w-2xl rounded-2xl border border-slate-200 bg-white px-5 py-5 text-center shadow-sm">
                    <div className="font-mono text-[11px] font-semibold uppercase tracking-widest text-[#58a6ff]">
                      {normalizeSessionScope(
                        sessions.find((row) => normalizeSessionKey(row.sessionKey) === normalizeSessionKey(config.sessionKey))?.scope,
                      ) === "private"
                        ? "Private conversation"
                        : "Shared conversation"}
                    </div>
                    <div className="mt-2 text-sm text-slate-600">No messages in this conversation yet.</div>
                    <div className="mt-4 grid gap-2 text-left md:grid-cols-3">
                      <button
                        type="button"
                        onClick={() => applyComposerPrompt("Create a new CRM contact with name, email and phone.")}
                        className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-medium text-slate-700 transition hover:bg-slate-100"
                      >
                        + Create contact
                      </button>
                      <button
                        type="button"
                        onClick={() => applyComposerPrompt("Search CRM contacts by email and show matching records.")}
                        className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-medium text-slate-700 transition hover:bg-slate-100"
                      >
                        Search contacts
                      </button>
                      <button
                        type="button"
                        onClick={() => applyComposerPrompt("Draft a campaign brief with audience, objective and channels.")}
                        className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-medium text-slate-700 transition hover:bg-slate-100"
                      >
                        Start campaign
                      </button>
                    </div>
                  </div>
                </div>
              ) : null}
              </div>

            </div>

            {sessionLoading ? (
              <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center bg-white/65 backdrop-blur-sm">
                <div className="rounded-xl border border-slate-200 bg-white/90 px-4 py-3">
                  <div className="font-mono text-xs font-semibold uppercase tracking-widest text-[#58a6ff]">
                    Loading Session
                  </div>
                  <div className="mt-1 text-sm text-slate-700">Syncing conversation...</div>
                </div>
              </div>
            ) : null}

            {showJumpToLatest ? (
              <button
                type="button"
                onClick={() => {
                  const el = chatScrollRef.current;
                  if (!el) return;
                  el.scrollTop = el.scrollHeight;
                  setShowJumpToLatest(false);
                }}
                className="absolute bottom-4 right-4 flex h-10 w-10 items-center justify-center rounded-full border border-brand-300 bg-brand-600 text-white"
                aria-label="Jump to latest"
                title="Jump to latest"
              >
                ↓
              </button>
            ) : null}
          </div>

          <footer className="border-t border-slate-200/70 bg-white/75 px-3 py-3 md:px-5">
            <div className="rounded-3xl border border-slate-200 bg-white p-3 shadow-sm">
              {isNonTerminalStatus(runStatus) ? (
                <div className="mb-2 rounded-xl border border-amber-200 bg-amber-50/70 px-3 py-2">
                  <div className="font-mono text-[10px] font-semibold uppercase tracking-widest text-amber-700">Live run</div>
                  <div className="mt-0.5 text-xs text-amber-800">
                    {runStatus} · {runStatusMeta}
                  </div>
                </div>
              ) : null}
              {queuedTurns.length > 0 ? (
                <div className="mb-3 rounded-2xl border border-amber-200 bg-amber-50/70 p-3">
                  <div className="mb-2 flex items-center justify-between gap-2">
                    <div>
                      <div className="font-mono text-[11px] font-semibold uppercase tracking-widest text-amber-700">
                        Queue
                      </div>
                      <div className="text-[11px] text-amber-800">
                        {queuedTurns.length} pending message{queuedTurns.length === 1 ? "" : "s"}
                      </div>
                    </div>
                    <div className="rounded-full border border-amber-300/70 bg-white/80 px-2 py-1 font-mono text-[10px] font-semibold text-amber-700">
                      {activeSessionScope}
                    </div>
                  </div>
                  <div className="max-h-44 space-y-2 overflow-y-auto pr-1">
                    {queuedTurns.map((item, index) => {
                      const canRetire = activeSessionScope === "private" || queuedTurnOwnedByUser(item, authUser);
                      const preview = item.message || (item.attachmentsCount > 0 ? "Attached files only." : "(empty)");
                      return (
                        <div key={item.id} className="rounded-xl border border-amber-200/80 bg-white/80 px-3 py-2 text-xs text-slate-700">
                          <div className="flex items-center justify-between gap-2">
                            <div className="font-semibold text-slate-900">
                              #{index + 1} · {item.authorLabel}
                            </div>
                            {item.selectedProfile ? (
                              <div className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 font-mono text-[10px] text-slate-600">
                                {item.selectedProfile}
                              </div>
                            ) : null}
                          </div>
                          <div className="mt-1 whitespace-pre-wrap text-[12px] leading-5 text-slate-700">
                            {preview}
                          </div>
                          <div className="mt-2 flex items-center justify-between gap-2">
                            <div className="text-[10px] text-slate-500">
                              {item.attachmentsCount > 0 ? `${item.attachmentsCount} attachment${item.attachmentsCount === 1 ? "" : "s"}` : "text"}
                            </div>
                            <div className="flex items-center gap-2">
                              {canRetire ? (
                                <button
                                  type="button"
                                  onClick={() => retireQueuedTurn(item.id)}
                                  className="rounded-full border border-slate-300 bg-white px-2.5 py-1 text-[10px] font-semibold text-slate-700"
                                >
                                  Retire
                                </button>
                              ) : null}
                              {activeSessionScope === "private" ? (
                                <button
                                  type="button"
                                  onClick={() => forcePushQueuedTurn(item.id)}
                                  className="rounded-full border border-amber-300 bg-white px-2.5 py-1 text-[10px] font-semibold text-amber-700"
                                >
                                  Force Push
                                </button>
                              ) : null}
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ) : null}

              {pendingAttachments.length > 0 ? (
                <div className="mb-2 flex flex-wrap gap-2">
                  {pendingAttachments.map((item) => (
                    <div key={item.id} className="flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-50/90 px-2 py-1 text-xs text-slate-700">
                      {item.previewUrl ? (
                        <img src={item.previewUrl} alt={item.name} className="h-8 w-8 rounded-md border border-slate-200 object-cover" />
                      ) : (
                        <div className="flex h-8 w-8 items-center justify-center rounded-md border border-slate-200 bg-white text-[11px] font-semibold text-slate-500">
                          FILE
                        </div>
                      )}
                      <div className="min-w-0">
                        <div className="truncate font-medium">{truncateName(item.name)}</div>
                        <div className="text-[10px] text-slate-500">{humanFileSize(item.size)}</div>
                      </div>
                      <button
                        type="button"
                        onClick={() => removePendingAttachment(item.id)}
                        className="ml-1 rounded-md border border-slate-300 bg-white px-1.5 py-0.5 text-[11px] font-semibold text-slate-600"
                      >
                        x
                      </button>
                    </div>
                  ))}
                </div>
              ) : null}

              <textarea
                ref={composerInputRef}
                rows={2}
                value={messageInput}
                onChange={(e) => setMessageInput(e.target.value)}
                onMouseEnter={(e) => {
                  if (document.activeElement !== e.currentTarget) {
                    e.currentTarget.focus();
                  }
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    void sendMessage();
                  }
                }}
                placeholder="Ask for follow-up changes"
                className="w-full resize-none rounded-2xl border border-slate-200 bg-white px-3 py-3 text-[13px] leading-6 outline-none ring-brand-300 transition focus:ring md:text-[14px] md:leading-6"
              />

              <div className="mt-1 flex items-center justify-between gap-2">
                <div className="flex min-w-0 items-center gap-1.5 overflow-x-auto md:gap-2">
                  <input
                    type="file"
                    className="hidden"
                    id="agent-file-input"
                    multiple
                    accept="image/*,.pdf,.doc,.docx,.xls,.xlsx,.csv,.txt,.md,.json,.yaml,.yml,.xml,.html,.htm,.mp3,.wav,.m4a,.ogg,.mp4,.mov,.avi,.zip"
                    onChange={(e) => {
                      onFilesSelected(e.target.files);
                      e.currentTarget.value = "";
                    }}
                  />
                  <label
                    htmlFor="agent-file-input"
                    className="flex h-9 w-9 cursor-pointer items-center justify-center rounded-full text-xl leading-none text-slate-700 transition hover:bg-slate-200/70"
                    title="Attach files"
                    aria-label="Attach files"
                  >
                    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.8">
                      <path d="M21.44 11.05 12.25 20.24a6 6 0 0 1-8.49-8.49L13.3 2.22a4 4 0 1 1 5.66 5.66l-9.2 9.19a2 2 0 1 1-2.83-2.83l8.49-8.48" />
                    </svg>
                  </label>
                  <button
                    type="button"
                    onClick={() => setSnapshotOpen(true)}
                    className="inline-flex h-8 items-center rounded-full border border-slate-200 bg-slate-50 px-3 text-[12px] leading-none text-slate-700 transition hover:bg-slate-100"
                    title="Show realtime snapshot"
                  >
                    {composerProfileLabel}
                  </button>
                </div>
                <div className="flex items-center gap-2">
                  {isNonTerminalStatus(runStatus) ? (
                    <button
                      type="button"
                      onClick={abortRun}
                      className="flex h-9 w-9 items-center justify-center rounded-full border border-rose-300 text-rose-600 transition hover:bg-rose-50"
                      title="Abort"
                      aria-label="Abort"
                    >
                      <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="currentColor">
                        <rect x="7" y="7" width="10" height="10" rx="1.5" />
                      </svg>
                    </button>
                  ) : null}
                  <button
                    type="button"
                    disabled={sendInFlight}
                    onClick={() => void sendMessage()}
                    className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-slate-600 text-white shadow-sm disabled:cursor-not-allowed disabled:opacity-60"
                    aria-label="Send message"
                  >
                    ↑
                  </button>
                </div>
              </div>
            </div>
            <div className="mt-1.5 flex items-center justify-between gap-2 px-1">
              <div className="hidden font-mono text-[11px] font-semibold text-emerald-700 md:block" title="Session token totals">
                session tokens: {nf.format(usage.total)} (in {nf.format(usage.input)}, out {nf.format(usage.output)})
              </div>
              <p className="hidden text-right text-[11px] text-slate-500 md:block">Press Enter to send, Shift+Enter for newline.</p>
            </div>
          </footer>
        </div>

        <aside className="hidden min-h-0 flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-[0_10px_28px_rgba(15,23,42,0.08)] xl:flex">
          <header className="sticky top-0 z-10 flex items-center justify-between border-b border-slate-200/80 bg-white px-4 py-2.5">
            <h2 className="text-2xl font-medium tracking-tighter text-slate-900">Agent Status</h2>
            <span
              className={`inline-flex rounded-full border px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide ${statusBadgeClass(
                runStatus,
              )}`}
              title={runStatusMeta}
            >
              {runStatus}
            </span>
          </header>
          <div className="border-b border-slate-200/80 px-3 py-2">
            <div className="grid grid-cols-2 gap-1 rounded-xl border border-slate-200 bg-slate-50 p-1">
              <button
                type="button"
                onClick={() => setRightRailTab("status")}
                className={`rounded-lg px-2 py-1.5 text-xs font-semibold transition ${
                  rightRailTab === "status" ? "bg-white text-slate-900 shadow-sm" : "text-slate-600 hover:bg-white/70"
                }`}
              >
                Status
              </button>
              <button
                type="button"
                onClick={() => setRightRailTab("activity")}
                className={`rounded-lg px-2 py-1.5 text-xs font-semibold transition ${
                  rightRailTab === "activity" ? "bg-white text-slate-900 shadow-sm" : "text-slate-600 hover:bg-white/70"
                }`}
              >
                Activity
              </button>
            </div>
          </div>
          <section className="min-h-0 flex-1 overflow-hidden px-3 py-2">
            {rightRailTab === "status" ? (
              <div className="h-full space-y-2 overflow-y-auto pr-1">
                <div className="rounded-xl border border-slate-200 bg-white p-2.5">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono text-[10px] font-semibold uppercase tracking-widest text-slate-500">Run</span>
                    {isNonTerminalStatus(runStatus) ? <span className="font-mono text-[10px] text-amber-600">live</span> : null}
                  </div>
                  <div className="mt-1 text-[11px] text-slate-700">{runStatusMeta}</div>
                </div>
                <div className="rounded-xl border border-slate-200 bg-white p-2.5 text-[11px] text-slate-700">
                  <div className="flex items-center justify-between py-0.5">
                    <span className="text-slate-500">Session</span>
                    <span className="font-medium text-slate-800">{normalizeSessionKey(config.sessionKey)}</span>
                  </div>
                  <div className="flex items-center justify-between py-0.5">
                    <span className="text-slate-500">Queue</span>
                    <span className="font-medium text-slate-800">{queuedTurns.length}</span>
                  </div>
                  <div className="flex items-center justify-between py-0.5">
                    <span className="text-slate-500">Tokens</span>
                    <span className="font-medium text-slate-800">{nf.format(usage.total)}</span>
                  </div>
                </div>
                <div className="rounded-xl border border-slate-200 bg-white p-2.5 text-[11px] text-slate-700">
                  <div className="mb-1 font-mono text-[10px] font-semibold uppercase tracking-widest text-slate-500">Runtime</div>
                  <div className="space-y-1">
                    {resourcesSummary.slice(0, 6).map(([key, value]) => (
                      <div key={key} className="flex items-center justify-between gap-2">
                        <span className="text-slate-500">{key}</span>
                        <span className="font-medium text-slate-800">{value}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            ) : (
              <div className="h-full space-y-2 overflow-y-auto pr-1">
                {toolEvents.length ? (
                  toolEvents
                    .slice()
                    .reverse()
                    .map((item) => (
                      <div key={item.id} className="rounded-xl border border-slate-200 bg-white px-2.5 py-2 text-[11px] text-slate-700">
                        {item.text}
                      </div>
                    ))
                ) : (
                  <div className="rounded-xl border border-dashed border-slate-300 bg-white px-2.5 py-2 text-[11px] text-slate-500">
                    No tool activity yet.
                  </div>
                )}
              </div>
            )}
          </section>
        </aside>
      </section>

      {summaryOpen ? (
        <div className="fixed inset-0 z-30 flex items-center justify-center bg-slate-900/35 p-4 backdrop-blur-[1px]">
          <section className="flex max-h-[90vh] w-full max-w-4xl flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-[0_20px_60px_rgba(15,23,42,0.22)]">
            <header className="flex items-center justify-between border-b border-slate-200 px-5 py-3">
              <div>
                <h2 className="text-lg font-semibold text-slate-900">Conversation Summary</h2>
                <p className="font-mono text-xs uppercase tracking-widest text-brand-600">{summaryMeta}</p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={requestSummary}
                  className="rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm font-semibold text-slate-700"
                >
                  Refresh
                </button>
                <button
                  type="button"
                  onClick={() => setSummaryOpen(false)}
                  className="rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm font-semibold text-slate-700"
                >
                  Close
                </button>
              </div>
            </header>
            <div className="flex items-center gap-2 border-b border-slate-200 px-5 py-2">
              <input
                value={summaryTitle}
                onChange={(e) => setSummaryTitle(e.target.value)}
                placeholder="Session title"
                className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm"
              />
              <button
                type="button"
                onClick={() => sendAction("chat_session_rename", { sessionKey: config.sessionKey, title: summaryTitle })}
                className="rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm font-semibold text-slate-700"
              >
                Save
              </button>
            </div>
            <div className="overflow-y-auto bg-white px-5 py-4 text-[14px] leading-7 text-slate-800">
              <div className="mb-4 rounded-xl border border-slate-200 bg-slate-50/70 p-3">
                <div className="font-mono text-[10px] font-semibold uppercase tracking-widest text-slate-500">Files exchanged</div>
                {exchangedFiles.length > 0 ? (
                  <ul className="mt-2 space-y-2 text-sm leading-6">
                    {exchangedFiles.map((file) => (
                      <li key={file.id} className="flex items-center justify-between gap-2 rounded-lg border border-slate-200 bg-white px-2.5 py-2">
                        <div className="min-w-0">
                          <div className="truncate font-medium text-slate-800">{file.name}</div>
                          <div className="text-[11px] text-slate-500">
                            {file.source === "uploaded" ? "uploaded" : "generated"}
                            {file.mimeType ? ` · ${file.mimeType}` : ""}
                          </div>
                        </div>
                        <div className="flex items-center gap-1.5">
                          {isPreviewableFile(file) ? (
                            <button
                              type="button"
                              onClick={() => setFilePreview(file)}
                              className="rounded-md border border-slate-300 bg-white px-2.5 py-1 text-[11px] font-semibold text-slate-700"
                            >
                              Preview
                            </button>
                          ) : null}
                          <a
                            href={file.url}
                            target="_blank"
                            rel="noreferrer noopener"
                            download={file.name}
                            className="rounded-md border border-brand-200 bg-brand-50 px-2.5 py-1 text-[11px] font-semibold text-brand-700 hover:bg-brand-100"
                          >
                            Download
                          </a>
                        </div>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <div className="mt-1 text-sm text-slate-500">(no files exchanged yet)</div>
                )}
              </div>
              <div className="whitespace-pre-wrap">{summaryText || "(no summary yet)"}</div>
            </div>
          </section>
        </div>
      ) : null}

      {filePreview ? (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-slate-900/55 p-4 backdrop-blur-sm">
          <section className="flex max-h-[90vh] w-full max-w-5xl flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-[0_20px_60px_rgba(15,23,42,0.25)]">
            <header className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
              <div className="min-w-0">
                <h2 className="truncate text-base font-semibold text-slate-900">{filePreview.name}</h2>
                <p className="text-[11px] text-slate-500">{filePreview.mimeType || "file preview"}</p>
              </div>
              <div className="flex items-center gap-2">
                <a
                  href={filePreview.url}
                  target="_blank"
                  rel="noreferrer noopener"
                  download={filePreview.name}
                  className="rounded-xl border border-brand-200 bg-brand-50 px-3 py-1.5 text-sm font-semibold text-brand-700"
                >
                  Download
                </a>
                <button
                  type="button"
                  onClick={() => setFilePreview(null)}
                  className="rounded-xl border border-slate-300 bg-white px-3 py-1.5 text-sm font-semibold text-slate-700"
                >
                  Close
                </button>
              </div>
            </header>
            <div className="min-h-0 flex-1 overflow-hidden bg-slate-50">
              {String(filePreview.mimeType || "").toLowerCase().startsWith("image/") ? (
                <div className="flex h-full items-center justify-center p-4">
                  <img src={filePreview.url} alt={filePreview.name} className="max-h-full max-w-full rounded-lg border border-slate-200 bg-white object-contain" />
                </div>
              ) : (
                <iframe title={filePreview.name} src={filePreview.url} className="h-full w-full border-0" />
              )}
            </div>
          </section>
        </div>
      ) : null}

      {snapshotOpen ? (
        <div className="fixed inset-0 z-30 flex items-center justify-center bg-slate-900/45 p-4 backdrop-blur-sm">
          <section className="flex max-h-[80vh] w-full max-w-xl flex-col overflow-hidden rounded-2xl border border-slate-300/40 bg-white/95 backdrop-blur-md">
            <header className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
              <div>
                <h2 className="text-base font-semibold text-slate-900">Realtime Snapshot</h2>
                <p className="text-[11px] text-slate-500">Live workspace capabilities for this conversation</p>
              </div>
              <button
                type="button"
                onClick={() => setSnapshotOpen(false)}
                className="rounded-xl border border-slate-300 bg-white px-3 py-1.5 text-sm font-semibold text-slate-700"
              >
                Close
              </button>
            </header>
            <div className="overflow-y-auto p-4">
              <div className="space-y-1 rounded-xl border border-slate-200 bg-white p-3 text-sm text-slate-700">
                {resourcesSummary.length ? (
                  resourcesSummary.map(([k, v]) => (
                    <div key={k} className="flex items-center justify-between gap-3 py-0.5">
                      <span className="text-slate-500">{k}</span>
                      <span className="font-medium text-slate-800">{v}</span>
                    </div>
                  ))
                ) : (
                  <div className="text-slate-500">(loading)</div>
                )}
              </div>
            </div>
          </section>
        </div>
      ) : null}
    </main>
  );
}
