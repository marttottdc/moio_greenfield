// @ts-nocheck
import { FormEvent, useEffect, useMemo, useState } from "react";

import {
  clearPublicSessions,
  fetchPublicContext,
  getActiveTenantSessionContext,
  getStoredPublicSessionState,
  joinPublic,
  loginPublic,
  persistPublicSession,
  setActiveTenantSessionContext,
  type PublicTenantRow,
  type PublicWorkspaceRow,
  type StoredPublicSessionState,
} from "../lib/publicAuthApi";
import { clearStoredTokens } from "@/lib/api";

type Mode = "login" | "join";
type Destination = "agent" | "platform";

const ACCESS_HUB_PATH = "/desktop-agent-console/";
const AGENT_CONSOLE_PATH = "/desktop-agent-console/console/";
const PLATFORM_ADMIN_PATH = "/desktop-agent-console/platform-admin/";

function defaultTenantValue(
  tenants: PublicTenantRow[],
  query: URLSearchParams,
  activeTenantId: string,
  activeTenantHint: string,
): string {
  const nextTenantId = String(query.get("nextTenantId") || "").trim();
  const nextTenant = String(query.get("nextTenant") || "").trim().toLowerCase();
  const preferredTenantId = nextTenantId || activeTenantId;
  const preferredTenantHint = nextTenant || activeTenantHint;
  const byId = preferredTenantId ? tenants.find((row) => row.uuid === preferredTenantId) : null;
  if (byId) return byId.uuid || byId.schemaName || byId.slug;
  const byName = preferredTenantHint
    ? tenants.find((row) => row.schemaName === preferredTenantHint || row.slug === preferredTenantHint)
    : null;
  if (byName) return byName.uuid || byName.schemaName || byName.slug;
  const first = tenants[0];
  return first ? first.uuid || first.schemaName || first.slug : "";
}

function defaultWorkspaceValue(
  workspaces: PublicWorkspaceRow[],
  query: URLSearchParams,
  activeWorkspaceId: string,
  activeWorkspaceSlug: string,
): string {
  const nextWorkspaceId = String(query.get("nextWorkspaceId") || "").trim();
  const nextWorkspace = String(query.get("nextWorkspace") || "").trim().toLowerCase();
  const preferredWorkspaceId = nextWorkspaceId || activeWorkspaceId;
  const preferredWorkspaceSlug = nextWorkspace || activeWorkspaceSlug;
  const byId = preferredWorkspaceId ? workspaces.find((row) => row.uuid === preferredWorkspaceId) : null;
  if (byId) return byId.uuid || byId.slug;
  const bySlug = preferredWorkspaceSlug ? workspaces.find((row) => row.slug === preferredWorkspaceSlug) : null;
  if (bySlug) return bySlug.uuid || bySlug.slug;
  const first = workspaces[0];
  return first ? first.uuid || first.slug : "main";
}

function buildAbsoluteUrl(path: string): URL {
  return new URL(path, window.location.origin);
}

export default function AccessHubApp() {
  const location = useMemo(() => ({ search: window.location.search }), []);
  const query = useMemo(() => new URLSearchParams(location.search), [location.search]);
  const activeTenantContext = useMemo(() => getActiveTenantSessionContext(), []);

  const [session, setSession] = useState<StoredPublicSessionState>(() => getStoredPublicSessionState());
  const [mode, setMode] = useState<Mode>("login");
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");

  const [loginEmail, setLoginEmail] = useState("");
  const [loginPassword, setLoginPassword] = useState("");
  const [joinDisplayName, setJoinDisplayName] = useState("");
  const [joinEmail, setJoinEmail] = useState("");
  const [joinPassword, setJoinPassword] = useState("");
  const [joinTenantName, setJoinTenantName] = useState("");

  const canTenantConsole = session.capabilities.tenantConsole && session.tenants.length > 0;
  const canPlatformAdmin = session.capabilities.platformAdmin;

  const [destination, setDestination] = useState<Destination>("agent");
  const [tenantValue, setTenantValue] = useState("");
  const [workspaceValue, setWorkspaceValue] = useState("");

  useEffect(() => {
    const preferred = canPlatformAdmin && !canTenantConsole ? "platform" : "agent";
    setDestination((prev) => {
      if (prev === "platform" && !canPlatformAdmin) return preferred;
      if (prev === "agent" && !canTenantConsole) return preferred;
      return prev || preferred;
    });
  }, [canPlatformAdmin, canTenantConsole]);

  useEffect(() => {
    const nextValue = defaultTenantValue(
      session.tenants,
      query,
      activeTenantContext?.tenantId || "",
      activeTenantContext?.tenantSchema || activeTenantContext?.tenantSlug || "",
    );
    setTenantValue((prev) => {
      if (prev && session.tenants.some((row) => (row.uuid || row.schemaName || row.slug) === prev)) return prev;
      return nextValue;
    });
  }, [activeTenantContext, query, session.tenants]);

  const selectedTenant = useMemo(
    () =>
      session.tenants.find((row) => {
        const value = row.uuid || row.schemaName || row.slug;
        return value === tenantValue;
      }) || null,
    [session.tenants, tenantValue]
  );

  const workspaceRows = useMemo(() => {
    if (!selectedTenant) return [];
    return selectedTenant.workspaces.length
      ? selectedTenant.workspaces
      : [{ uuid: "", slug: "main", name: "main" }];
  }, [selectedTenant]);

  useEffect(() => {
    const nextValue = defaultWorkspaceValue(
      workspaceRows,
      query,
      activeTenantContext?.workspaceId || "",
      activeTenantContext?.workspaceSlug || "",
    );
    setWorkspaceValue((prev) => {
      if (prev && workspaceRows.some((row) => (row.uuid || row.slug) === prev)) return prev;
      return nextValue;
    });
  }, [activeTenantContext, query, workspaceRows]);

  useEffect(() => {
    if (!session.hasPublicSession) return;
    let active = true;
    setLoading(true);
    void fetchPublicContext()
      .then((payload) => {
        persistPublicSession(payload);
        if (active) {
          setSession(getStoredPublicSessionState());
          setStatus("");
          setError("");
        }
      })
      .catch(() => {
        clearPublicSessions();
        if (active) {
          setSession(getStoredPublicSessionState());
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [session.hasPublicSession]);

  async function onSubmitLogin(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    setStatus("");
    try {
      const payload = await loginPublic({
        email: loginEmail.trim(),
        password: loginPassword,
      });
      persistPublicSession(payload);
      setSession(getStoredPublicSessionState());
      setLoginPassword("");
      setStatus("Signed in. Choose where to continue.");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  }

  async function onSubmitJoin(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    setStatus("");
    try {
      const payload = await joinPublic({
        displayName: joinDisplayName.trim(),
        email: joinEmail.trim(),
        password: joinPassword,
        tenantName: joinTenantName.trim(),
      });
      persistPublicSession(payload);
      setSession(getStoredPublicSessionState());
      setJoinPassword("");
      setStatus("Workspace created. You can enter the console now.");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  }

  async function openSelectedDestination() {
    if (destination === "platform") {
      window.location.assign(PLATFORM_ADMIN_PATH);
      return;
    }
    if (!selectedTenant) {
      setError("Select a tenant first.");
      return;
    }
    const selectedWorkspace =
      workspaceRows.find((row) => (row.uuid || row.slug) === workspaceValue) || workspaceRows[0];
    if (!selectedWorkspace) {
      setError("Select a workspace first.");
      return;
    }
    setSubmitting(true);
    setError("");
    setStatus("");
    try {
      setActiveTenantSessionContext({
        tenantId: String(selectedTenant.uuid || "").trim(),
        tenantSlug: String(selectedTenant.slug || "").trim().toLowerCase(),
        tenantSchema: String(selectedTenant.schemaName || "").trim().toLowerCase(),
        workspaceId: String(selectedWorkspace.uuid || "").trim(),
        workspaceSlug: String(selectedWorkspace.slug || "main").trim().toLowerCase(),
      });
      const url = buildAbsoluteUrl(AGENT_CONSOLE_PATH);
      if (selectedTenant.uuid) {
        url.searchParams.set("tenantId", selectedTenant.uuid);
      }
      if (selectedTenant.schemaName || selectedTenant.slug) {
        url.searchParams.set("tenant", selectedTenant.schemaName || selectedTenant.slug);
      }
      if (selectedWorkspace.uuid) {
        url.searchParams.set("workspaceId", selectedWorkspace.uuid);
      } else {
        url.searchParams.set("workspace", selectedWorkspace.slug || "main");
      }
      window.location.assign(url.toString());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  }

  async function onLogout() {
    clearStoredTokens();
    clearPublicSessions();
    setSession(getStoredPublicSessionState());
    setStatus("Signed out.");
    setError("");
  }

  const panelClass =
    error
      ? "border-rose-300 bg-rose-50 text-rose-700"
      : "border-slate-200 bg-white/85 text-slate-600";

  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top_left,_rgba(59,130,246,0.18),_transparent_32%),radial-gradient(circle_at_top_right,_rgba(245,158,11,0.14),_transparent_28%),linear-gradient(135deg,#f8fafc,#e0ecff)] p-6 text-slate-900">
      <section className="mx-auto mt-10 w-full max-w-6xl rounded-[2rem] border border-brand-200/70 bg-white/78 p-8 shadow-[0_28px_90px_rgba(15,23,42,0.14)] backdrop-blur-md">
        <div className="font-mono text-xs font-semibold uppercase tracking-[0.28em] text-brand-600">Moio</div>
        <div className="mt-3 grid gap-8 lg:grid-cols-[1.2fr_0.8fr]">
          <div>
            <h1 className="text-5xl font-semibold tracking-[-0.04em] text-slate-900">Access Hub</h1>
            <p className="mt-4 max-w-2xl text-xl leading-relaxed text-slate-600">
              Frontend-owned entrypoint for sign in, workspace selection, and navigation into the console or admin
              surfaces.
            </p>

            <div className={`mt-6 rounded-2xl border px-4 py-3 text-sm ${panelClass}`}>
              {error || status || (loading ? "Refreshing your existing session..." : "Use one login flow, then continue into the app.")}
            </div>

            {session.user ? (
              <div className="mt-8 space-y-6">
                <div className="rounded-3xl border border-brand-200/70 bg-white/90 p-6">
                  <div className="text-sm uppercase tracking-[0.2em] text-slate-500">Signed In</div>
                  <div className="mt-2 text-2xl font-semibold text-slate-900">
                    {session.user.displayName || session.user.email}
                  </div>
                  <div className="mt-1 text-sm text-slate-500">{session.user.email}</div>
                </div>

                {(canTenantConsole || canPlatformAdmin) && (
                  <div className="space-y-5 rounded-3xl border border-brand-200/70 bg-white/90 p-6">
                    {canTenantConsole && canPlatformAdmin && (
                      <div>
                        <label className="mb-2 block font-mono text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
                          Destination
                        </label>
                        <select
                          value={destination}
                          onChange={(event) => setDestination(event.target.value as Destination)}
                          className="w-full rounded-2xl border border-brand-200 bg-white px-4 py-3 text-lg text-slate-900"
                        >
                          <option value="agent">Agent Console</option>
                          <option value="platform">Platform Admin</option>
                        </select>
                      </div>
                    )}

                    {destination === "agent" && canTenantConsole && (
                      <div className="grid gap-4 md:grid-cols-2">
                        <div>
                          <label className="mb-2 block font-mono text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
                            Tenant
                          </label>
                          <select
                            value={tenantValue}
                            onChange={(event) => {
                              const nextTenantValue = event.target.value;
                              setTenantValue(nextTenantValue);
                              const nextTenant =
                                session.tenants.find((row) => (row.uuid || row.schemaName || row.slug) === nextTenantValue) ||
                                null;
                              const firstWorkspace = nextTenant?.workspaces?.[0];
                              setWorkspaceValue(firstWorkspace ? firstWorkspace.uuid || firstWorkspace.slug : "main");
                            }}
                            className="w-full rounded-2xl border border-brand-200 bg-white px-4 py-3 text-lg text-slate-900"
                          >
                            {session.tenants.map((row) => {
                              const value = row.uuid || row.schemaName || row.slug;
                              return (
                                <option key={value} value={value}>
                                  {row.name}
                                </option>
                              );
                            })}
                          </select>
                        </div>

                        <div>
                          <label className="mb-2 block font-mono text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
                            Workspace
                          </label>
                          <select
                            value={workspaceValue}
                            onChange={(event) => setWorkspaceValue(event.target.value)}
                            className="w-full rounded-2xl border border-brand-200 bg-white px-4 py-3 text-lg text-slate-900"
                          >
                            {workspaceRows.map((row) => {
                              const value = row.uuid || row.slug;
                              return (
                                <option key={value} value={value}>
                                  {row.name}
                                </option>
                              );
                            })}
                          </select>
                        </div>
                      </div>
                    )}

                    <div className="flex flex-wrap gap-3">
                      <button
                        type="button"
                        onClick={openSelectedDestination}
                        className="min-h-[56px] min-w-[240px] rounded-2xl bg-gradient-to-r from-brand-400 to-brand-600 px-6 text-lg font-semibold text-white shadow-[0_18px_38px_rgba(37,99,235,0.34)]"
                      >
                        {destination === "platform" ? "Open Platform Admin" : "Open Agent Console"}
                      </button>
                      <button
                        type="button"
                        onClick={onLogout}
                        className="min-h-[56px] rounded-2xl border border-slate-300 bg-white px-6 text-lg font-semibold text-slate-700"
                      >
                        Sign Out
                      </button>
                    </div>
                  </div>
                )}

                {!canTenantConsole && !canPlatformAdmin && (
                  <div className="rounded-2xl border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-800">
                    Your account is signed in but no frontend destination is available yet.
                  </div>
                )}
              </div>
            ) : (
              <div className="mt-8 rounded-3xl border border-brand-200/70 bg-white/90 p-6">
                <div className="inline-flex rounded-2xl bg-brand-100/70 p-1">
                  <button
                    type="button"
                    onClick={() => setMode("login")}
                    className={`rounded-2xl px-5 py-2 text-sm font-semibold ${mode === "login" ? "bg-white text-brand-700 shadow-sm" : "text-slate-600"}`}
                  >
                    Sign In
                  </button>
                  <button
                    type="button"
                    onClick={() => setMode("join")}
                    className={`rounded-2xl px-5 py-2 text-sm font-semibold ${mode === "join" ? "bg-white text-brand-700 shadow-sm" : "text-slate-600"}`}
                  >
                    Create Workspace
                  </button>
                </div>

                {mode === "login" ? (
                  <form className="mt-6 grid gap-4" onSubmit={onSubmitLogin}>
                    <input
                      type="email"
                      value={loginEmail}
                      onChange={(event) => setLoginEmail(event.target.value)}
                      placeholder="Email"
                      autoComplete="username"
                      className="rounded-2xl border border-brand-200 bg-white px-4 py-3 text-lg text-slate-900"
                    />
                    <input
                      type="password"
                      value={loginPassword}
                      onChange={(event) => setLoginPassword(event.target.value)}
                      placeholder="Password"
                      autoComplete="current-password"
                      className="rounded-2xl border border-brand-200 bg-white px-4 py-3 text-lg text-slate-900"
                    />
                    <button
                      type="submit"
                      disabled={submitting}
                      className="min-h-[56px] rounded-2xl bg-slate-900 px-6 text-lg font-semibold text-white disabled:opacity-60"
                    >
                      {submitting ? "Signing In..." : "Sign In"}
                    </button>
                  </form>
                ) : (
                  <form className="mt-6 grid gap-4" onSubmit={onSubmitJoin}>
                    <input
                      type="text"
                      value={joinDisplayName}
                      onChange={(event) => setJoinDisplayName(event.target.value)}
                      placeholder="Display name"
                      autoComplete="name"
                      className="rounded-2xl border border-brand-200 bg-white px-4 py-3 text-lg text-slate-900"
                    />
                    <input
                      type="email"
                      value={joinEmail}
                      onChange={(event) => setJoinEmail(event.target.value)}
                      placeholder="Email"
                      autoComplete="email"
                      className="rounded-2xl border border-brand-200 bg-white px-4 py-3 text-lg text-slate-900"
                    />
                    <input
                      type="password"
                      value={joinPassword}
                      onChange={(event) => setJoinPassword(event.target.value)}
                      placeholder="Password"
                      autoComplete="new-password"
                      className="rounded-2xl border border-brand-200 bg-white px-4 py-3 text-lg text-slate-900"
                    />
                    <input
                      type="text"
                      value={joinTenantName}
                      onChange={(event) => setJoinTenantName(event.target.value)}
                      placeholder="Workspace or tenant name"
                      className="rounded-2xl border border-brand-200 bg-white px-4 py-3 text-lg text-slate-900"
                    />
                    <button
                      type="submit"
                      disabled={submitting}
                      className="min-h-[56px] rounded-2xl bg-slate-900 px-6 text-lg font-semibold text-white disabled:opacity-60"
                    >
                      {submitting ? "Creating..." : "Create Workspace"}
                    </button>
                  </form>
                )}
              </div>
            )}
          </div>

          <aside className="rounded-3xl border border-brand-200/70 bg-slate-950 px-6 py-7 text-slate-100 shadow-[0_24px_60px_rgba(15,23,42,0.22)]">
            <div className="text-xs font-semibold uppercase tracking-[0.24em] text-cyan-300">Runtime Split</div>
            <div className="mt-4 space-y-5">
              <div>
                <div className="text-sm font-semibold text-white">Frontend (`{ACCESS_HUB_PATH}`)</div>
                <div className="mt-1 text-sm leading-6 text-slate-300">
                  Owns login, access hub, console route, and admin screens under the SPA.
                </div>
              </div>
              <div>
                <div className="text-sm font-semibold text-white">Backend (`api.moio.ai`)</div>
                <div className="mt-1 text-sm leading-6 text-slate-300">
                  Serves API endpoints, websocket transport, media downloads, and health checks only.
                </div>
              </div>
              <div>
                <div className="text-sm font-semibold text-white">Routes</div>
                <ul className="mt-2 space-y-2 text-sm text-slate-300">
                  <li>`/` access hub</li>
                  <li>`/console/` agent console</li>
                  <li>`/platform-admin/` platform admin</li>
                  <li>`/tenant-admin/` tenant admin</li>
                </ul>
              </div>
            </div>
          </aside>
        </div>
      </section>
    </main>
  );
}
