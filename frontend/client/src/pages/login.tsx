import { useEffect, useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Loader2 } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { ApiError } from "@/lib/queryClient";
import { logLoginSubmitStart, logLoginSubmitError, getLastAuthError, clearLastAuthError, persistLastAuthError } from "@/lib/loginMonitor";
import { getApiBaseOverride, getDefaultApiBaseUrl, setApiBaseOverride } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { GlobalFooter } from "@/components/global-footer";
import moioLogo from "@assets/FAVICON_MOIO_1763393251809.png";

const loginSchema = z.object({
  email: z.string().email("Valid email is required"),
  password: z.string().min(1, "Password is required"),
});

type LoginFormData = z.infer<typeof loginSchema>;
const CUSTOM_PRESET_VALUE = "custom";

type ApiStatusState = "unknown" | "checking" | "online" | "slow" | "offline";

type ApiStatus = {
  state: ApiStatusState;
  latencyMs?: number;
};

const LATENCY_GOOD_THRESHOLD_MS = 700;

const now = () => (typeof performance !== "undefined" ? performance.now() : Date.now());

const trimTrailingSlash = (value: string) => value.replace(/\/+$/, "");
const trimLeadingSlash = (value: string) => value.replace(/^\/+/, "");

const buildProbeUrl = (base: string, path?: string) => {
  const normalizedBase = trimTrailingSlash(base);

  if (!path || path.length === 0) {
    return normalizedBase || "/";
  }

  const normalizedPath = trimLeadingSlash(path);

  if (!normalizedBase || normalizedBase === "/") {
    return `/${normalizedPath}`;
  }

  return `${normalizedBase}/${normalizedPath}`;
};

const getApiStatusDotClass = (status: ApiStatus): string => {
  switch (status.state) {
    case "online":
      return "bg-emerald-500";
    case "slow":
      return "bg-amber-400";
    case "offline":
      return "bg-red-500";
    default:
      return "bg-muted-foreground/60";
  }
};

const getApiStatusLabel = (status: ApiStatus): string => {
  const latencyInfo =
    typeof status.latencyMs === "number" ? ` (${status.latencyMs} ms)` : "";

  switch (status.state) {
    case "online":
      return `API reachable${latencyInfo}`;
    case "slow":
      return `High latency${latencyInfo}`;
    case "offline":
      return "API unreachable";
    case "checking":
      return "Checking API status…";
    default:
      return "Status unknown";
  }
};

export default function Login() {
  const { login } = useAuth();
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [sessionExpiredMessage, setSessionExpiredMessage] = useState<string | null>(null);
  const defaultApiBase = "https://platform.moio.ai";
  const backendPresets = useMemo(() => {
    return [
      { label: "Production (platform.moio.ai)", value: "https://platform.moio.ai", overridable: false },
      { label: "Staging (devcrm.moio.ai)", value: "https://devcrm.moio.ai", overridable: false },
    ];
  }, []);
  
  const initialBackendHost = getApiBaseOverride() ?? defaultApiBase;
  const [backendHost, setBackendHost] = useState(initialBackendHost);
  const [apiStatus, setApiStatus] = useState<ApiStatus>({ state: "unknown" });
  const [selectedPreset, setSelectedPreset] = useState<string>(() => {
    const match = backendPresets.find((preset) => preset.value === initialBackendHost);
    return match ? match.value : CUSTOM_PRESET_VALUE;
  });

  const applyBackendHost = (value: string) => {
    const nextValue = value.trim();
    setBackendHost(nextValue);

    if (!nextValue) {
      setApiBaseOverride(undefined);
      return;
    }

    setApiBaseOverride(nextValue);
  };

  const handlePresetChange = (value: string) => {
    setSelectedPreset(value);

    if (value === CUSTOM_PRESET_VALUE) {
      setBackendHost("");
      return;
    }

    applyBackendHost(value);
  };

  const isCustomSelected = selectedPreset === CUSTOM_PRESET_VALUE;
  const isInputDisabled = !isCustomSelected;

  // On mount, if no override is set, default to production
  useEffect(() => {
    if (!getApiBaseOverride()) {
      applyBackendHost(defaultApiBase);
    }
  }, []);

  useEffect(() => {
    const matchedPreset = backendPresets.find((preset) => preset.value === backendHost);
    const resolvedValue = matchedPreset ? matchedPreset.value : CUSTOM_PRESET_VALUE;
    if (resolvedValue !== selectedPreset) {
      setSelectedPreset(resolvedValue);
    }
  }, [backendHost, backendPresets, selectedPreset]);

  const resolvedBackendHost = backendHost || defaultApiBase;

  // After a reload (e.g. forceLogout), show the last auth info so the user knows why they're on login
  useEffect(() => {
    const last = getLastAuthError();
    if (last) {
      clearLastAuthError();
      if (last.reason === "force_logout") {
        setSessionExpiredMessage(last.message || "Your session expired. Please sign in again.");
        // Don't log as error — session expiry is an expected flow
      } else {
        const text = [last.step && `Step: ${last.step}`, last.status && `HTTP ${last.status}`, last.message].filter(Boolean).join(" · ");
        setErrorMessage(text);
        console.error("[Login] Last auth error (page reloaded before you could see it):", last);
      }
    }
  }, []);

  useEffect(() => {
    const hostToProbe = backendHost || defaultApiBase;

    if (!hostToProbe) {
      setApiStatus({ state: "unknown" });
      return;
    }

    let isActive = true;
    const controller = new AbortController();

    const probeApi = async () => {
      setApiStatus({ state: "checking" });
      const candidatePaths = ["api/v1/health/", "health/", ""];

      for (const candidate of candidatePaths) {
        const targetUrl = buildProbeUrl(hostToProbe, candidate);
        const start = now();

        try {
          const response = await fetch(targetUrl, {
            method: "GET",
            cache: "no-store",
            signal: controller.signal,
          });
          const latency = Math.round(now() - start);

          if (!response.ok) {
            continue;
          }

          if (!isActive) {
            return;
          }

          const state = latency <= LATENCY_GOOD_THRESHOLD_MS ? "online" : "slow";
          setApiStatus({ state, latencyMs: latency });
          return;
        } catch (error) {
          if (controller.signal.aborted) {
            return;
          }
        }
      }

      if (!isActive) {
        return;
      }

      setApiStatus({ state: "offline" });
    };

    probeApi();

    return () => {
      isActive = false;
      controller.abort();
    };
  }, [backendHost, defaultApiBase]);

  const form = useForm<LoginFormData>({
    resolver: zodResolver(loginSchema),
    defaultValues: {
      email: "",
      password: "",
    },
  });

  const onSubmit = async (data: LoginFormData) => {
    setIsLoading(true);
    setErrorMessage(null);
    setSessionExpiredMessage(null);
    logLoginSubmitStart();

    try {
      await login(data.email, data.password);
    } catch (error) {
      const status = error instanceof ApiError ? error.status : undefined;
      const message = error instanceof Error ? error.message : String(error);
      logLoginSubmitError(status, message);
      persistLastAuthError(message, { status });
      if (error instanceof ApiError) {
        setErrorMessage(error.message || "Invalid credentials. Please try again.");
      } else {
        setErrorMessage("An unexpected error occurred. Please try again.");
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex flex-col relative overflow-hidden bg-gradient-to-br from-slate-50 via-blue-50/30 to-amber-50/20">
      {/* Animated background gradients */}
      <div className="fixed inset-0 -z-10 overflow-hidden">
        <div className="absolute -top-40 -right-40 w-[600px] h-[600px] bg-gradient-to-br from-[#58a6ff]/30 via-blue-200/20 to-transparent rounded-full blur-3xl animate-float" />
        <div className="absolute top-1/2 -left-40 w-[500px] h-[500px] bg-gradient-to-tr from-[#ffba08]/25 via-amber-200/15 to-transparent rounded-full blur-3xl animate-float-delayed" />
        <div className="absolute -bottom-40 right-1/3 w-[550px] h-[550px] bg-gradient-to-tl from-blue-300/25 via-transparent to-[#58a6ff]/15 rounded-full blur-3xl animate-float-slow" />
      </div>

      <div className="flex-1 flex items-center justify-center px-4 py-10">
        <div className="w-full max-w-md">
          <Card className="backdrop-blur-sm bg-card/95 border-border/50 shadow-xl">
            <CardHeader className="space-y-1 text-center">
              <div className="mx-auto mb-4">
                <img
                  src={moioLogo}
                  alt="moio"
                  className="h-16 w-auto"
                  data-testid="img-logo"
                />
              </div>
              <CardTitle className="text-2xl font-bold">Welcome Back</CardTitle>
              <CardDescription>
                Sign in to access your CRM platform
              </CardDescription>
            </CardHeader>
            <CardContent>
            <Form {...form}>
              <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
                {sessionExpiredMessage && (
                  <Alert variant="default" data-testid="alert-session-expired">
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
                          placeholder="demo@moio.ai"
                          autoComplete="off"
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
                          autoComplete="off"
                          disabled={isLoading}
                          data-testid="input-password"
                          {...field}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <div className="space-y-2">
                  <Label htmlFor="backend-host">Backend host</Label>
                  <div className="flex flex-col gap-2 sm:flex-row">
                    <Select value={selectedPreset} onValueChange={handlePresetChange}>
                      <SelectTrigger className="sm:w-1/2" data-testid="select-backend-host">
                        <SelectValue placeholder="Select backend" />
                      </SelectTrigger>
                      <SelectContent>
                        {backendPresets.map((preset) => (
                          <SelectItem key={preset.value} value={preset.value}>
                            {preset.label}
                          </SelectItem>
                        ))}
                        <SelectItem value={CUSTOM_PRESET_VALUE}>Custom</SelectItem>
                      </SelectContent>
                    </Select>
                    <Input
                      id="backend-host"
                      value={backendHost}
                      onChange={(event) => applyBackendHost(event.target.value)}
                      placeholder="https://custom.example.com"
                      autoComplete="off"
                      disabled={isInputDisabled}
                      data-testid="input-backend-host"
                    />
                  </div>
                  <div className="space-y-1 text-xs text-muted-foreground">
                    <p>
                      Requests will be sent to:
                      <span className="font-mono"> {resolvedBackendHost}</span>
                      {!isInputDisabled && <span> (custom)</span>}
                    </p>
                    <div className="flex items-center gap-2" role="status" aria-live="polite">
                      <span
                        className={`inline-flex h-2.5 w-2.5 rounded-full ${getApiStatusDotClass(apiStatus)}${
                          apiStatus.state === "checking" ? " animate-pulse" : ""
                        }`}
                      />
                      <span>{getApiStatusLabel(apiStatus)}</span>
                    </div>
                  </div>
                </div>

                <Button
                  type="submit"
                  className="w-full"
                  disabled={isLoading}
                  data-testid="button-login"
                >
                  {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                  {isLoading ? "Signing in..." : "Sign in"}
                </Button>
              </form>
            </Form>

            <div className="mt-6 text-center text-sm text-muted-foreground">
              <p>Connecting to Moio Platform</p>
              <p className="text-xs mt-1">
                Production: platform.moio.ai | Staging: devcrm.moio.ai
              </p>
            </div>
          </CardContent>
          </Card>
        </div>
      </div>
      <GlobalFooter className="border-0 bg-transparent text-muted-foreground/80" />
    </div>
  );
}