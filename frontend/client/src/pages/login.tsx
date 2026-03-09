import { useEffect, useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useLocation } from "wouter";
import {
  Bot,
  LayoutDashboard,
  Loader2,
  LogOut,
  Settings,
  Shield,
} from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { ApiError } from "@/lib/queryClient";
import {
  getLastAuthError,
  clearLastAuthError,
  logLoginSubmitStart,
  logLoginSubmitError,
  persistLastAuthError,
} from "@/lib/loginMonitor";
import { setApiBaseOverride, getApiBaseOverride } from "@/lib/api";
import { isPlatformAdminRole, isTenantAdminRole } from "@/lib/rbac";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { GlobalFooter } from "@/components/global-footer";
import moioLogo from "@assets/FAVICON_MOIO_1763393251809.png";

// ─── Backend host / API status ────────────────────────────────────────────────

const loginSchema = z.object({
  email: z.string().email("Valid email is required"),
  password: z.string().min(1, "Password is required"),
});
type LoginFormData = z.infer<typeof loginSchema>;

const CUSTOM_PRESET_VALUE = "custom";
type ApiStatusState = "unknown" | "checking" | "online" | "slow" | "offline";
type ApiStatus = { state: ApiStatusState; latencyMs?: number };
const LATENCY_GOOD_MS = 700;
const perfNow = () =>
  typeof performance !== "undefined" ? performance.now() : Date.now();

function buildProbeUrl(base: string, path?: string): string {
  const b = base.replace(/\/+$/, "");
  if (!path) return b || "/";
  const p = path.replace(/^\/+/, "");
  return b ? `${b}/${p}` : `/${p}`;
}

function apiStatusDotClass(s: ApiStatus): string {
  if (s.state === "online") return "bg-emerald-500";
  if (s.state === "slow") return "bg-amber-400";
  if (s.state === "offline") return "bg-red-500";
  return "bg-slate-400";
}

function apiStatusLabel(s: ApiStatus): string {
  const lat = typeof s.latencyMs === "number" ? ` (${s.latencyMs} ms)` : "";
  if (s.state === "online") return `API reachable${lat}`;
  if (s.state === "slow") return `High latency${lat}`;
  if (s.state === "offline") return "API unreachable";
  if (s.state === "checking") return "Checking…";
  return "Status unknown";
}

// ─── Destinations ─────────────────────────────────────────────────────────────

type DestCard = {
  key: string;
  label: string;
  description: string;
  icon: React.ElementType;
  path: string;
  iconBg: string;
};

function buildDestinations(role: string | null | undefined): DestCard[] {
  const cards: DestCard[] = [
    {
      key: "crm",
      label: "CRM Platform",
      description: "Contacts, deals, tickets, campaigns and workflows.",
      icon: LayoutDashboard,
      path: "/dashboard",
      iconBg: "bg-gradient-to-br from-sky-500 to-blue-600",
    },
    {
      key: "console",
      label: "Agent Console",
      description: "Interactive chat with AI agents and session history.",
      icon: Bot,
      path: "/agent-console",
      iconBg: "bg-gradient-to-br from-violet-500 to-purple-600",
    },
  ];

  if (isTenantAdminRole(role)) {
    cards.push({
      key: "tenant-admin",
      label: "Tenant Admin",
      description: "Workspaces, users, skills, automations and integrations.",
      icon: Settings,
      path: "/tenant-admin/legacy",
      iconBg: "bg-gradient-to-br from-amber-500 to-orange-600",
    });
  }

  if (isPlatformAdminRole(role)) {
    cards.push({
      key: "platform-admin",
      label: "Platform Admin",
      description: "Tenants, platform users, global settings and plugins.",
      icon: Shield,
      path: "/platform-admin",
      iconBg: "bg-gradient-to-br from-rose-500 to-red-600",
    });
  }

  return cards;
}

// ─── Component ────────────────────────────────────────────────────────────────

// Step 1 = credentials, Step 2 = destination selector (skipped if only one)
type LoginStep = "credentials" | "destinations";

export default function Login() {
  const { login, logout, user, isAuthenticated } = useAuth();
  const [, navigate] = useLocation();
  const [step, setStep] = useState<LoginStep>("credentials");

  // Backend host
  const defaultApiBase = "https://platform.moio.ai";
  const backendPresets = useMemo(
    () => [
      { label: "Production (platform.moio.ai)", value: "https://platform.moio.ai" },
      { label: "Staging (devcrm.moio.ai)", value: "https://devcrm.moio.ai" },
    ],
    []
  );
  const initialHost = getApiBaseOverride() ?? defaultApiBase;
  const [backendHost, setBackendHost] = useState(initialHost);
  const [selectedPreset, setSelectedPreset] = useState<string>(() => {
    const m = backendPresets.find((p) => p.value === initialHost);
    return m ? m.value : CUSTOM_PRESET_VALUE;
  });
  const [apiStatus, setApiStatus] = useState<ApiStatus>({ state: "unknown" });
  const isCustom = selectedPreset === CUSTOM_PRESET_VALUE;

  function applyHost(value: string) {
    const v = value.trim();
    setBackendHost(v);
    setApiBaseOverride(v || undefined);
  }

  function handlePresetChange(value: string) {
    setSelectedPreset(value);
    if (value === CUSTOM_PRESET_VALUE) {
      setBackendHost("");
    } else {
      applyHost(value);
    }
  }

  useEffect(() => {
    if (!getApiBaseOverride()) applyHost(defaultApiBase);
  }, []);

  useEffect(() => {
    const m = backendPresets.find((p) => p.value === backendHost);
    const v = m ? m.value : CUSTOM_PRESET_VALUE;
    if (v !== selectedPreset) setSelectedPreset(v);
  }, [backendHost, backendPresets]);

  useEffect(() => {
    const host = backendHost || defaultApiBase;
    if (!host) { setApiStatus({ state: "unknown" }); return; }
    let active = true;
    const ctrl = new AbortController();
    setApiStatus({ state: "checking" });
    (async () => {
      for (const candidate of ["api/v1/health/", "health/", ""]) {
        const url = buildProbeUrl(host, candidate);
        const start = perfNow();
        try {
          const res = await fetch(url, { method: "GET", cache: "no-store", signal: ctrl.signal });
          if (!res.ok) continue;
          if (!active) return;
          const lat = Math.round(perfNow() - start);
          setApiStatus({ state: lat <= LATENCY_GOOD_MS ? "online" : "slow", latencyMs: lat });
          return;
        } catch { if (ctrl.signal.aborted) return; }
      }
      if (active) setApiStatus({ state: "offline" });
    })();
    return () => { active = false; ctrl.abort(); };
  }, [backendHost]);

  // Login form
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [sessionExpiredMessage, setSessionExpiredMessage] = useState<string | null>(null);

  useEffect(() => {
    const last = getLastAuthError();
    if (!last) return;
    clearLastAuthError();
    if (last.reason === "force_logout") {
      setSessionExpiredMessage(last.message || "Your session expired. Please sign in again.");
    } else {
      const text = [
        last.step && `Step: ${last.step}`,
        last.status && `HTTP ${last.status}`,
        last.message,
      ].filter(Boolean).join(" · ");
      setErrorMessage(text);
    }
  }, []);

  const form = useForm<LoginFormData>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: "", password: "" },
  });

  const destinations = useMemo(() => buildDestinations(user?.role), [user?.role]);
  const resolvedHost = backendHost || defaultApiBase;

  // After auth: skip selector if only one destination, else advance to step 2
  useEffect(() => {
    if (!isAuthenticated || !user) return;
    const dests = buildDestinations(user.role);
    if (dests.length === 1) {
      navigate(dests[0].path);
    } else {
      setStep("destinations");
    }
  }, [isAuthenticated, user]);

  // If already authenticated when the page loads (e.g. refresh), handle the same way
  useEffect(() => {
    if (isAuthenticated && user && step === "credentials") {
      const dests = buildDestinations(user.role);
      if (dests.length === 1) {
        navigate(dests[0].path);
      } else {
        setStep("destinations");
      }
    }
  }, []);

  const onSubmit = async (data: LoginFormData) => {
    setIsLoading(true);
    setErrorMessage(null);
    setSessionExpiredMessage(null);
    logLoginSubmitStart();
    try {
      await login(data.email, data.password);
      // navigation handled by the useEffect above
    } catch (error) {
      const status = error instanceof ApiError ? error.status : undefined;
      const message = error instanceof Error ? error.message : String(error);
      logLoginSubmitError(status, message);
      persistLastAuthError(message, { status });
      setErrorMessage(
        error instanceof ApiError
          ? error.message || "Invalid credentials. Please try again."
          : "An unexpected error occurred. Please try again."
      );
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex flex-col relative overflow-hidden bg-[radial-gradient(circle_at_top_left,_rgba(59,130,246,0.18),_transparent_32%),radial-gradient(circle_at_top_right,_rgba(245,158,11,0.14),_transparent_28%),linear-gradient(135deg,#f8fafc,#e0ecff)]">
      {/* Floating blobs */}
      <div className="fixed inset-0 -z-10 overflow-hidden pointer-events-none">
        <div className="absolute -top-40 -right-40 w-[600px] h-[600px] bg-gradient-to-br from-[#58a6ff]/30 via-blue-200/20 to-transparent rounded-full blur-3xl animate-float" />
        <div className="absolute top-1/2 -left-40 w-[500px] h-[500px] bg-gradient-to-tr from-[#ffba08]/25 via-amber-200/15 to-transparent rounded-full blur-3xl animate-float-delayed" />
        <div className="absolute -bottom-40 right-1/3 w-[550px] h-[550px] bg-gradient-to-tl from-blue-300/25 via-transparent to-[#58a6ff]/15 rounded-full blur-3xl animate-float-slow" />
      </div>

      <div className="flex-1 flex items-center justify-center px-4 py-10">
        <div className="w-full max-w-5xl">
          <section className="rounded-[2rem] border border-slate-200/70 bg-white/85 p-8 shadow-[0_28px_90px_rgba(15,23,42,0.14)] backdrop-blur-md">
            {/* Header */}
            <div className="flex items-center gap-4 mb-8">
              <img src={moioLogo} alt="moio" className="h-12 w-auto" data-testid="img-logo" />
              <div>
                <div className="font-mono text-xs font-semibold uppercase tracking-[0.24em] text-slate-500">
                  Moio
                </div>
                <h1 className="text-3xl font-semibold tracking-tight text-slate-900">
                  {step === "destinations" ? "Where to?" : "Access Hub"}
                </h1>
              </div>
            </div>

            {step === "destinations" && user ? (
              /* ── Step 2: Destination selector ── */
              <div className="grid gap-8 lg:grid-cols-[220px_1fr]">
                {/* User info */}
                <div className="space-y-3">
                  <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                    <div className="text-xs font-semibold uppercase tracking-widest text-slate-400 mb-2">
                      Signed in
                    </div>
                    <div className="text-base font-semibold text-slate-900 truncate">
                      {user.full_name || user.username}
                    </div>
                    {user.email && (
                      <div className="text-xs text-slate-500 truncate mt-0.5">{user.email}</div>
                    )}
                    {user.role && (
                      <div className="mt-2 inline-block rounded-full border border-slate-200 bg-slate-50 px-2.5 py-0.5 text-xs font-medium text-slate-600 capitalize">
                        {user.role.replace(/_/g, " ")}
                      </div>
                    )}
                    {user.organization?.name && (
                      <div className="text-xs text-slate-400 mt-1 truncate">
                        {user.organization.name}
                      </div>
                    )}
                    <Button
                      variant="ghost"
                      size="sm"
                      className="mt-4 w-full gap-2 text-slate-600 hover:text-slate-900"
                      onClick={() => { logout(); setStep("credentials"); }}
                      data-testid="button-logout"
                    >
                      <LogOut className="h-3.5 w-3.5" />
                      Sign out
                    </Button>
                  </div>

                  {/* API status */}
                  <div className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs text-slate-500">
                    <div className="flex items-center gap-1.5">
                      <span className={`inline-flex h-2 w-2 rounded-full shrink-0 ${apiStatusDotClass(apiStatus)}`} />
                      <span className="font-mono truncate">{resolvedHost}</span>
                    </div>
                  </div>
                </div>

                {/* Destination cards */}
                <div>
                  <p className="text-slate-600 mb-4 text-sm">Select where you want to go:</p>
                  <div className="grid gap-3 sm:grid-cols-2">
                    {destinations.map((dest) => (
                      <button
                        key={dest.key}
                        type="button"
                        onClick={() => navigate(dest.path)}
                        className="group text-left rounded-2xl border border-slate-200 bg-white p-5 shadow-sm hover:shadow-md hover:-translate-y-0.5 transition-all duration-150 cursor-pointer"
                        data-testid={`button-dest-${dest.key}`}
                      >
                        <div className={`inline-flex h-9 w-9 items-center justify-center rounded-xl ${dest.iconBg} mb-3`}>
                          <dest.icon className="h-4 w-4 text-white" />
                        </div>
                        <div className="font-semibold text-slate-900 text-sm mb-1">{dest.label}</div>
                        <div className="text-xs text-slate-500 leading-relaxed">{dest.description}</div>
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            ) : (
              /* ── Step 1: Credentials form ── */
              <div className="grid gap-8 lg:grid-cols-[1.2fr_0.8fr]">
                <div>
                  <p className="text-slate-600 mb-6 text-sm leading-relaxed">
                    Sign in to access CRM, Agent Console, and administration surfaces.
                  </p>

                  <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                    <Form {...form}>
                      <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
                        {sessionExpiredMessage && (
                          <Alert data-testid="alert-session-expired">
                            <AlertDescription>{sessionExpiredMessage}</AlertDescription>
                          </Alert>
                        )}
                        {errorMessage && (
                          <Alert variant="destructive" data-testid="alert-error">
                            <AlertDescription>{errorMessage}</AlertDescription>
                          </Alert>
                        )}

                        <FormField
                          control={form.control}
                          name="email"
                          render={({ field }) => (
                            <FormItem>
                              <FormLabel>Email</FormLabel>
                              <FormControl>
                                <Input
                                  type="email"
                                  placeholder="you@moio.ai"
                                  autoComplete="username"
                                  disabled={isLoading}
                                  data-testid="input-email"
                                  {...field}
                                />
                              </FormControl>
                              <FormMessage />
                            </FormItem>
                          )}
                        />

                        <FormField
                          control={form.control}
                          name="password"
                          render={({ field }) => (
                            <FormItem>
                              <FormLabel>Password</FormLabel>
                              <FormControl>
                                <Input
                                  type="password"
                                  placeholder="••••••••"
                                  autoComplete="current-password"
                                  disabled={isLoading}
                                  data-testid="input-password"
                                  {...field}
                                />
                              </FormControl>
                              <FormMessage />
                            </FormItem>
                          )}
                        />

                        <Button
                          type="submit"
                          className="w-full"
                          disabled={isLoading}
                          data-testid="button-login"
                        >
                          {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                          {isLoading ? "Signing in…" : "Sign in"}
                        </Button>
                      </form>
                    </Form>
                  </div>

                  {/* Backend host selector */}
                  <div className="mt-4 space-y-2">
                    <div className="flex flex-col gap-2 sm:flex-row">
                      <Select value={selectedPreset} onValueChange={handlePresetChange}>
                        <SelectTrigger className="sm:w-1/2 text-xs" data-testid="select-backend-host">
                          <SelectValue placeholder="Backend" />
                        </SelectTrigger>
                        <SelectContent>
                          {backendPresets.map((p) => (
                            <SelectItem key={p.value} value={p.value} className="text-xs">
                              {p.label}
                            </SelectItem>
                          ))}
                          <SelectItem value={CUSTOM_PRESET_VALUE} className="text-xs">Custom</SelectItem>
                        </SelectContent>
                      </Select>
                      <Input
                        value={backendHost}
                        onChange={(e) => applyHost(e.target.value)}
                        placeholder="https://custom.example.com"
                        autoComplete="off"
                        disabled={!isCustom}
                        className="text-xs"
                        data-testid="input-backend-host"
                      />
                    </div>
                    <div className="flex items-center gap-2 text-xs text-slate-500">
                      <span className={`inline-flex h-2 w-2 rounded-full shrink-0 ${apiStatusDotClass(apiStatus)}${apiStatus.state === "checking" ? " animate-pulse" : ""}`} />
                      <span className="font-mono truncate">{resolvedHost}</span>
                      <span>—</span>
                      <span>{apiStatusLabel(apiStatus)}</span>
                    </div>
                  </div>
                </div>

                {/* Right panel */}
                <aside className="rounded-2xl border border-slate-800 bg-slate-950 px-6 py-7 text-slate-100 shadow-lg hidden lg:block">
                  <div className="text-xs font-semibold uppercase tracking-[0.24em] text-cyan-300 mb-5">
                    What's inside
                  </div>
                  <div className="space-y-4 text-sm text-slate-300 leading-relaxed">
                    <div>
                      <div className="text-white font-medium mb-0.5 flex items-center gap-2">
                        <LayoutDashboard className="h-3.5 w-3.5 text-sky-400 shrink-0" />
                        CRM Platform
                      </div>
                      Contacts, deals, tickets, campaigns, workflows, data lab.
                    </div>
                    <div>
                      <div className="text-white font-medium mb-0.5 flex items-center gap-2">
                        <Bot className="h-3.5 w-3.5 text-violet-400 shrink-0" />
                        Agent Console
                      </div>
                      Interactive AI sessions with workspace and model selection.
                    </div>
                    <div>
                      <div className="text-white font-medium mb-0.5 flex items-center gap-2">
                        <Settings className="h-3.5 w-3.5 text-amber-400 shrink-0" />
                        Tenant Admin
                      </div>
                      Workspaces, skills, automations — tenant admins.
                    </div>
                    <div>
                      <div className="text-white font-medium mb-0.5 flex items-center gap-2">
                        <Shield className="h-3.5 w-3.5 text-rose-400 shrink-0" />
                        Platform Admin
                      </div>
                      Tenants, global users, plugins — platform admins.
                    </div>
                  </div>
                </aside>
              </div>
            )}
          </section>
        </div>
      </div>

      <GlobalFooter className="border-0 bg-transparent text-slate-400" />
    </div>
  );
}
