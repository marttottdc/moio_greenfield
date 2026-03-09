// @ts-nocheck
import { useEffect } from "react";

type MockConsoleMessage = {
  role: "user" | "assistant" | "system";
  text: string;
  timestamp: string;
  runId?: string;
  usage?: { input: number; output: number; total: number } | null;
  author?: { id: number; email: string; displayName: string };
};

type MockConsoleSession = {
  sessionKey: string;
  title: string;
  scope: "shared" | "private";
  messages: MockConsoleMessage[];
  queue: Array<Record<string, unknown>>;
  updatedAtMs: number;
};

type MockConsoleState = {
  tenantSlug: string;
  tenantId: string;
  workspaceSlug: string;
  workspaceId: string;
  sessions: Record<string, MockConsoleSession>;
};

const TENANT_CONTEXT_KEY = "moio_tenant_session_context";
const PUBLIC_USER_KEY = "moio_public_user";
const PUBLIC_TENANTS_KEY = "moio_public_tenants";
const TENANT_TOKEN_KEY = "moio_tenant_session_tokens";

let mockConsoleState: MockConsoleState | null = null;

function nowMs(): number {
  return Date.now();
}

function isoNow(): string {
  return new Date().toISOString();
}

function readJson<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return fallback;
    const parsed = JSON.parse(raw);
    return (parsed as T) ?? fallback;
  } catch {
    return fallback;
  }
}

function getStoredUser() {
  return readJson(PUBLIC_USER_KEY, {
    id: 1,
    email: "martin@moio.ai",
    displayName: "Martin Otero",
  });
}

function getTenantRows(): Array<Record<string, unknown>> {
  const rows = readJson<Array<Record<string, unknown>>>(PUBLIC_TENANTS_KEY, []);
  return Array.isArray(rows) ? rows : [];
}

function getActiveContext() {
  return readJson<Record<string, string>>(TENANT_CONTEXT_KEY, {
    tenantId: "tenant-acme",
    tenantSlug: "acme",
    tenantSchema: "acme",
    workspaceId: "workspace-main",
    workspaceSlug: "main",
  });
}

function getWorkspaceRowsForTenant(tenantSlug: string): Array<Record<string, unknown>> {
  const tenant = getTenantRows().find((row) => String(row.slug || "").trim().toLowerCase() === tenantSlug);
  const workspaces = Array.isArray(tenant?.workspaces) ? tenant.workspaces : [];
  if (workspaces.length > 0) return workspaces as Array<Record<string, unknown>>;
  return [{ id: "workspace-main", uuid: "workspace-main", slug: "main", name: "Main Workspace" }];
}

function findWorkspace(tenantSlug: string, workspaceSlug: string, workspaceId: string) {
  const rows = getWorkspaceRowsForTenant(tenantSlug);
  return (
    rows.find((row) => String(row.uuid || row.id || "").trim() === workspaceId) ||
    rows.find((row) => String(row.slug || "").trim().toLowerCase() === workspaceSlug) ||
    rows[0] ||
    { id: "workspace-main", uuid: "workspace-main", slug: workspaceSlug || "main", name: workspaceSlug || "Main" }
  );
}

function welcomeMessages(workspaceLabel: string): MockConsoleMessage[] {
  return [
    {
      role: "system",
      text: `Workspace ${workspaceLabel} initialized in preview mode.`,
      timestamp: isoNow(),
      author: { id: 900, email: "system@moio.ai", displayName: "System" },
    },
    {
      role: "assistant",
      text: `Moio agent ready for ${workspaceLabel}. This is the original console UI running with a local preview transport.`,
      timestamp: isoNow(),
      author: { id: 901, email: "agent@moio.ai", displayName: "Moio Agent" },
      usage: { input: 54, output: 36, total: 90 },
    },
  ];
}

function createInitialConsoleState(): MockConsoleState {
  const context = getActiveContext();
  const tenantSlug = String(context.tenantSlug || context.tenantSchema || "acme").trim().toLowerCase() || "acme";
  const tenantId = String(context.tenantId || `tenant-${tenantSlug}`).trim() || `tenant-${tenantSlug}`;
  const workspaceSlug = String(context.workspaceSlug || "main").trim().toLowerCase() || "main";
  const workspaceId = String(context.workspaceId || `workspace-${workspaceSlug}`).trim() || `workspace-${workspaceSlug}`;
  const workspace = findWorkspace(tenantSlug, workspaceSlug, workspaceId);
  const workspaceLabel = String(workspace.name || workspace.displayName || workspace.slug || workspaceSlug).trim() || "Main Workspace";

  return {
    tenantSlug,
    tenantId,
    workspaceSlug,
    workspaceId,
    sessions: {
      main: {
        sessionKey: "main",
        title: "Main conversation",
        scope: "shared",
        messages: welcomeMessages(workspaceLabel),
        queue: [],
        updatedAtMs: nowMs(),
      },
    },
  };
}

export function ensureLegacyAgentConsoleMockState() {
  if (typeof window === "undefined") return;
  mockConsoleState = createInitialConsoleState();
}

function getConsoleState(): MockConsoleState {
  if (!mockConsoleState) {
    mockConsoleState = createInitialConsoleState();
  }
  return mockConsoleState;
}

function currentSession(state: MockConsoleState, sessionKey: string): MockConsoleSession {
  const key = String(sessionKey || "main").trim() || "main";
  if (!state.sessions[key]) {
    state.sessions[key] = {
      sessionKey: key,
      title: key === "main" ? "Main conversation" : key,
      scope: key === "main" ? "shared" : "private",
      messages: [],
      queue: [],
      updatedAtMs: nowMs(),
    };
  }
  return state.sessions[key];
}

function serializeMessage(message: MockConsoleMessage) {
  return {
    role: message.role,
    runId: String(message.runId || "").trim(),
    timestamp: message.timestamp,
    content: [{ type: "text", text: message.text }],
    usage: message.usage || undefined,
    author: message.author || undefined,
  };
}

function buildUsage(session: MockConsoleSession) {
  return session.messages.reduce(
    (acc, row) => {
      if (!row.usage) return acc;
      acc.input += Number(row.usage.input || 0) || 0;
      acc.output += Number(row.usage.output || 0) || 0;
      acc.total += Number(row.usage.total || 0) || 0;
      return acc;
    },
    { input: 0, output: 0, total: 0 },
  );
}

function buildSummary(session: MockConsoleSession) {
  const lastAssistant = [...session.messages].reverse().find((row) => row.role === "assistant");
  const summary = lastAssistant?.text
    ? `Latest assistant response: ${String(lastAssistant.text).slice(0, 180)}`
    : "No assistant response generated yet.";
  return {
    title: session.title || `Conversation ${session.sessionKey}`,
    summary,
    summaryUpTo: session.messages.length,
  };
}

function serializeSessions(state: MockConsoleState) {
  return Object.values(state.sessions)
    .map((session) => ({
      sessionKey: session.sessionKey,
      title: session.title,
      scope: session.scope,
      messageCount: session.messages.length,
      updatedAtMs: session.updatedAtMs,
    }))
    .sort((a, b) => b.updatedAtMs - a.updatedAtMs);
}

function buildResourcesEnvelope(state: MockConsoleState, workspaceSlug: string) {
  const workspace = findWorkspace(state.tenantSlug, workspaceSlug, state.workspaceId);
  const label = String(workspace.name || workspace.displayName || workspace.slug || workspaceSlug).trim() || workspaceSlug;
  return {
    models: {
      payload: {
        current: "gpt-5-mini",
        vendors: ["openai", "anthropic"],
      },
    },
    toolsCatalog: {
      payload: {
        available: [{ key: "crm_lookup" }, { key: "ticket_search" }, { key: "calendar" }],
        enabled: [{ key: "crm_lookup" }, { key: "ticket_search" }],
      },
    },
    skillsStatus: {
      payload: {
        enabledCount: workspaceSlug === "support" ? 1 : 2,
      },
    },
    workspaceProfile: {
      payload: {
        name: workspaceSlug,
        displayName: label,
      },
    },
    tenantIntegrations: {
      payload: {
        enabledCount: 1,
        integrations: [{ key: "hubspot", name: "HubSpot" }],
      },
    },
  };
}

function buildInitFrame(state: MockConsoleState, sessionKey: string, workspaceSlug: string) {
  const session = currentSession(state, sessionKey);
  const user = getStoredUser();
  const usage = buildUsage(session);
  const summary = buildSummary(session);
  return {
    type: "init",
    payload: {
      authUser: {
        id: Number(user.id || 1),
        email: String(user.email || "martin@moio.ai").trim().toLowerCase(),
        displayName: String(user.displayName || user.email || "User").trim(),
        tenantId: state.tenantId,
        tenantRole: "admin",
        tenantAdmin: true,
      },
      agentConfig: {
        tenant: state.tenantSlug,
        workspace: workspaceSlug,
        sessionKey: session.sessionKey,
        model: "gpt-5-mini",
        vendor: "openai",
        thinking: "default",
        verbosity: "minimal",
      },
      chatHistory: {
        payload: {
          sessionKey: session.sessionKey,
          messages: session.messages.map(serializeMessage),
        },
      },
      chatQueue: {
        payload: {
          sessionKey: session.sessionKey,
          items: session.queue,
        },
      },
      chatUsage: {
        payload: {
          sessionKey: session.sessionKey,
          ...usage,
        },
      },
      chatSummary: {
        payload: {
          sessionKey: session.sessionKey,
          ...summary,
        },
      },
      chatSessions: {
        payload: {
          sessions: serializeSessions(state),
        },
      },
      resources: buildResourcesEnvelope(state, workspaceSlug),
    },
  };
}

function createResponseText(workspaceSlug: string, userText: string, attachmentsCount = 0): string {
  const normalized = String(userText || "").trim() || "No message provided.";
  const attachmentNote = attachmentsCount > 0 ? ` I also received ${attachmentsCount} attachment${attachmentsCount === 1 ? "" : "s"}.` : "";
  return `Preview response from workspace ${workspaceSlug}: ${normalized}${attachmentNote}`;
}

class MockAgentConsoleWebSocket {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;

  readyState = MockAgentConsoleWebSocket.CONNECTING;
  url: string;
  onopen: ((event: Event) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  private timers: number[] = [];
  private sessionKey = "main";
  private workspaceSlug = "main";

  constructor(url: string | URL) {
    this.url = String(url);
    const parsed = new URL(this.url, window.location.origin);
    const workspace = String(parsed.searchParams.get("workspace") || "").trim().toLowerCase();
    const workspaceId = String(parsed.searchParams.get("workspaceId") || "").trim();
    const state = getConsoleState();
    const activeWorkspace = workspace || state.workspaceSlug || "main";
    const resolved = findWorkspace(state.tenantSlug, activeWorkspace, workspaceId || state.workspaceId);
    this.workspaceSlug = String(resolved.slug || activeWorkspace || "main").trim().toLowerCase() || "main";
    state.workspaceSlug = this.workspaceSlug;
    state.workspaceId = String(resolved.uuid || resolved.id || state.workspaceId || "").trim();

    this.timers.push(
      window.setTimeout(() => {
        if (this.readyState !== MockAgentConsoleWebSocket.CONNECTING) return;
        this.readyState = MockAgentConsoleWebSocket.OPEN;
        this.onopen?.(new Event("open"));
        this.emit(buildInitFrame(state, this.sessionKey, this.workspaceSlug), 20);
      }, 10),
    );
  }

  private emit(frame: Record<string, unknown>, delay = 0): void {
    this.timers.push(
      window.setTimeout(() => {
        if (this.readyState !== MockAgentConsoleWebSocket.OPEN) return;
        this.onmessage?.({ data: JSON.stringify(frame) } as MessageEvent);
      }, delay),
    );
  }

  private emitQueueFrame(type: string, state: MockConsoleState, sessionKey: string): void {
    const session = currentSession(state, sessionKey);
    this.emit({
      type,
      payload: {
        payload: {
          sessionKey,
          items: session.queue,
        },
      },
    });
  }

  send(raw: string): void {
    if (this.readyState !== MockAgentConsoleWebSocket.OPEN) return;
    let payload: Record<string, unknown> = {};
    try {
      payload = JSON.parse(String(raw || "{}"));
    } catch {
      this.onerror?.(new Event("error"));
      return;
    }

    const state = getConsoleState();
    const action = String(payload.action || "").trim();
    const sessionKey = String(payload.sessionKey || this.sessionKey || "main").trim() || "main";
    const session = currentSession(state, sessionKey);
    this.sessionKey = sessionKey;

    if (action === "init") {
      this.emit(buildInitFrame(state, sessionKey, this.workspaceSlug));
      return;
    }

    if (action === "chat_history") {
      this.emit({
        type: "chat_history",
        payload: {
          payload: {
            sessionKey,
            messages: session.messages.map(serializeMessage),
          },
        },
      });
      return;
    }

    if (action === "chat_usage") {
      this.emit({
        type: "chat_usage",
        payload: {
          payload: {
            sessionKey,
            ...buildUsage(session),
          },
        },
      });
      return;
    }

    if (action === "chat_summary") {
      this.emit({
        type: "chat_summary",
        payload: {
          payload: {
            sessionKey,
            ...buildSummary(session),
          },
        },
      });
      return;
    }

    if (action === "chat_sessions_list") {
      this.emit({
        type: "chat_sessions_list",
        payload: {
          payload: {
            sessions: serializeSessions(state),
          },
        },
      });
      return;
    }

    if (action === "chat_queue") {
      this.emitQueueFrame("chat_queue", state, sessionKey);
      return;
    }

    if (action === "chat_session_create") {
      const nextKey = String(payload.sessionKey || `private-${Date.now().toString(36)}`).trim();
      const scope = String(payload.scope || "private").trim().toLowerCase() === "shared" ? "shared" : "private";
      state.sessions[nextKey] = {
        sessionKey: nextKey,
        title: scope === "private" ? "Private conversation" : "Shared conversation",
        scope,
        messages: [],
        queue: [],
        updatedAtMs: nowMs(),
      };
      this.sessionKey = nextKey;
      this.emit({
        type: "chat_session_create",
        payload: {
          payload: {
            session: {
              sessionKey: nextKey,
              scope,
            },
            sessions: serializeSessions(state),
          },
        },
      });
      return;
    }

    if (action === "chat_session_set_scope") {
      session.scope = String(payload.scope || "private").trim().toLowerCase() === "shared" ? "shared" : "private";
      session.updatedAtMs = nowMs();
      this.emit({
        type: "chat_session_set_scope",
        payload: {
          payload: {
            sessions: serializeSessions(state),
          },
        },
      });
      return;
    }

    if (action === "chat_session_rename") {
      session.title = String(payload.title || session.title || sessionKey).trim() || session.title || sessionKey;
      session.updatedAtMs = nowMs();
      this.emit({
        type: "chat_sessions_list",
        payload: {
          payload: {
            sessions: serializeSessions(state),
          },
        },
      });
      return;
    }

    if (action === "chat_queue_retire") {
      const queueItemId = String(payload.queueItemId || "").trim();
      session.queue = session.queue.filter((row) => String(row.id || row.queueItemId || "").trim() !== queueItemId);
      this.emitQueueFrame("chat_queue_retire", state, sessionKey);
      return;
    }

    if (action === "chat_queue_force_push") {
      session.queue = [];
      this.emitQueueFrame("chat_queue_force_push", state, sessionKey);
      return;
    }

    if (action === "abort") {
      this.emit({
        type: "chat_event",
        payload: {
          sessionKey,
          runId: `run-${Date.now().toString(36)}`,
          state: "aborted",
          errorMessage: "aborted by preview user",
        },
      });
      return;
    }

    if (action === "send_message") {
      const user = getStoredUser();
      const messageText = String(payload.message || "").trim() || "(empty)";
      const attachments = Array.isArray(payload.attachments) ? payload.attachments : [];
      const runId = `run-${Date.now().toString(36)}-${Math.random().toString(16).slice(2, 6)}`;
      const queueItemId = `queue-${runId}`;
      session.queue = [
        {
          id: queueItemId,
          queueItemId,
          message: messageText,
          attachmentsCount: attachments.length,
          createdAtMs: nowMs(),
          selectedProfile: `${payload.vendor || "openai"}/${payload.model || "gpt-5-mini"}`,
          author: {
            id: Number(user.id || 1),
            email: String(user.email || "martin@moio.ai").trim().toLowerCase(),
            displayName: String(user.displayName || user.email || "User").trim(),
          },
        },
      ];
      this.emit({
        type: "chat_send_ack",
        payload: {
          result: {
            payload: {
              status: "queued",
              queuePosition: 1,
              queue: {
                payload: {
                  sessionKey,
                  items: session.queue,
                },
              },
            },
          },
        },
      });

      const acceptedMessage = {
        role: "user",
        text: messageText,
        timestamp: isoNow(),
        runId,
        author: {
          id: Number(user.id || 1),
          email: String(user.email || "martin@moio.ai").trim().toLowerCase(),
          displayName: String(user.displayName || user.email || "User").trim(),
        },
      } satisfies MockConsoleMessage;

      const finalText = createResponseText(this.workspaceSlug, messageText, attachments.length);
      const usage = {
        input: Math.max(32, Math.min(800, messageText.length * 2)),
        output: Math.max(48, Math.min(900, finalText.length * 2)),
        total: 0,
      };
      usage.total = usage.input + usage.output;
      const finalMessage = {
        role: "assistant",
        text: finalText,
        timestamp: isoNow(),
        runId,
        usage,
        author: {
          id: 901,
          email: "agent@moio.ai",
          displayName: "Moio Agent",
        },
      } satisfies MockConsoleMessage;

      this.timers.push(
        window.setTimeout(() => {
          if (this.readyState !== MockAgentConsoleWebSocket.OPEN) return;
          session.queue = [];
          session.messages.push(acceptedMessage);
          session.updatedAtMs = nowMs();
          this.emit({
            type: "chat_event",
            payload: {
              sessionKey,
              runId,
              state: "accepted",
              message: serializeMessage(acceptedMessage),
            },
          });
          this.emitQueueFrame("chat_queue", state, sessionKey);
          this.emit({
            type: "agent_event",
            payload: {
              sessionKey,
              stream: "loop",
              data: {
                status: "thinking",
                phase: "draft",
                humanMessage: "drafting response",
              },
            },
          });
        }, 80),
      );

      const midpoint = Math.max(1, Math.floor(finalText.length / 2));
      const chunkA = finalText.slice(0, midpoint);
      const chunkB = finalText.slice(midpoint);
      this.emit(
        {
          type: "chat_event",
          payload: {
            sessionKey,
            runId,
            state: "delta",
            message: { content: [{ type: "text", text: chunkA }] },
          },
        },
        160,
      );
      this.emit(
        {
          type: "chat_event",
          payload: {
            sessionKey,
            runId,
            state: "delta",
            message: { content: [{ type: "text", text: chunkB }] },
          },
        },
        260,
      );
      this.timers.push(
        window.setTimeout(() => {
          if (this.readyState !== MockAgentConsoleWebSocket.OPEN) return;
          session.messages.push(finalMessage);
          session.updatedAtMs = nowMs();
          this.emit({
            type: "chat_event",
            payload: {
              sessionKey,
              runId,
              state: "final",
              message: serializeMessage(finalMessage),
            },
          });
        }, 360),
      );
      return;
    }

    this.emit({
      type: "error",
      error: {
        message: `Unsupported preview action: ${action || "unknown"}`,
      },
    });
  }

  close(): void {
    if (this.readyState === MockAgentConsoleWebSocket.CLOSED) return;
    this.readyState = MockAgentConsoleWebSocket.CLOSED;
    for (const timer of this.timers) {
      window.clearTimeout(timer);
    }
    this.timers = [];
    this.onclose?.({ code: 1000, reason: "preview closed", wasClean: true } as CloseEvent);
  }
}

function mockConsoleFetch(input: RequestInfo | URL, init?: RequestInit): Response | null {
  const url = typeof input === "string" ? new URL(input, window.location.origin) : input instanceof URL ? input : new URL(input.url, window.location.origin);
  const method = String(init?.method || (typeof input !== "string" && "method" in input ? input.method : "GET")).toUpperCase();
  const path = url.pathname;

  if (path === "/api/auth/push-config" && method === "GET") {
    return new Response(JSON.stringify({ ok: true, payload: { publicKey: "", configured: false } }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }

  if (path === "/api/auth/push-subscription" && method === "POST") {
    return new Response(JSON.stringify({ ok: true, payload: { saved: true } }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }

  if (path === "/api/auth/logout" && method === "POST") {
    return new Response(JSON.stringify({ ok: true, payload: { loggedOut: true } }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }

  if (path === "/api/auth/refresh" && method === "POST") {
    const tokens = readJson(TENANT_TOKEN_KEY, { access: "mock-tenant-access", refresh: "mock-tenant-refresh" });
    return new Response(JSON.stringify({ ok: true, payload: tokens }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }

  return null;
}

export function useLegacyAgentConsoleMockPreview() {
  useEffect(() => {
    ensureLegacyAgentConsoleMockState();

    const originalFetch = window.fetch.bind(window);
    const OriginalWebSocket = window.WebSocket;

    window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const mocked = mockConsoleFetch(input, init);
      if (mocked) return mocked;
      return originalFetch(input, init);
    };

    window.WebSocket = MockAgentConsoleWebSocket as unknown as typeof window.WebSocket;

    return () => {
      window.fetch = originalFetch;
      window.WebSocket = OriginalWebSocket;
    };
  }, []);
}
