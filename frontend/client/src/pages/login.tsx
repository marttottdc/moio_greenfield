import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useLocation } from "wouter";
import { Bot, LayoutDashboard, Loader2, Settings, Shield } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { ApiError } from "@/lib/queryClient";
import {
  getLastAuthError,
  clearLastAuthError,
  logLoginSubmitStart,
  logLoginSubmitError,
  persistLastAuthError,
} from "@/lib/loginMonitor";
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
import { GlobalFooter } from "@/components/global-footer";
import moioLogo from "@assets/FAVICON_MOIO_1763393251809.png";

// ─── Schema ───────────────────────────────────────────────────────────────────

const loginSchema = z.object({
  email: z.string().email("Valid email is required"),
  password: z.string().min(1, "Password is required"),
});
type LoginFormData = z.infer<typeof loginSchema>;

// ─── Component ────────────────────────────────────────────────────────────────

export default function Login() {
  const { t } = useTranslation();
  const { login, isAuthenticated } = useAuth();
  const [, navigate] = useLocation();

  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [sessionExpiredMessage, setSessionExpiredMessage] = useState<string | null>(null);

  useEffect(() => {
    const last = getLastAuthError();
    if (!last) return;
    clearLastAuthError();
    if (last.reason === "force_logout") {
      setSessionExpiredMessage(last.message || t("login.session_expired"));
    } else {
      const text = [
        last.step && `Step: ${last.step}`,
        last.status && `HTTP ${last.status}`,
        last.message,
      ].filter(Boolean).join(" · ");
      setErrorMessage(text);
    }
  }, [t]);

  // If already authenticated, go to platform router (single entry point after login).
  useEffect(() => {
    if (isAuthenticated) {
      navigate("/platform-router");
    }
  }, [isAuthenticated, navigate]);

  const form = useForm<LoginFormData>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: "", password: "" },
  });

  const onSubmit = async (data: LoginFormData) => {
    setIsLoading(true);
    setErrorMessage(null);
    setSessionExpiredMessage(null);
    logLoginSubmitStart();
    try {
      await login(data.email, data.password);
      navigate("/platform-router");
    } catch (error) {
      const status = error instanceof ApiError ? error.status : undefined;
      const message = error instanceof Error ? error.message : String(error);
      logLoginSubmitError(status, message);
      persistLastAuthError(message, { status });
      // Network error (status 0) = "Failed to fetch", connection refused, CORS, etc.
      const friendlyMessage =
        status === 0
          ? "No se pudo conectar al servidor. Verifica que el frontend esté en http://localhost:5177, que el backend esté corriendo (puerto 8093) y que no haya override de API en localStorage."
          : error instanceof ApiError
            ? error.message || t("login.invalid_credentials")
            : t("login.unexpected_error");
      setErrorMessage(friendlyMessage);
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
                  {t("login.access_hub")}
                </h1>
              </div>
            </div>

            <div className="grid gap-8 lg:grid-cols-[1.2fr_0.8fr]">
                <div>
                  <p className="text-slate-600 mb-6 text-sm leading-relaxed">
                    {t("login.sign_in_prompt")}
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
                              <FormLabel>{t("login.email")}</FormLabel>
                              <FormControl>
                                <Input
                                  type="email"
                                  placeholder={t("login.email_placeholder")}
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
                              <FormLabel>{t("login.password")}</FormLabel>
                              <FormControl>
                                <Input
                                  type="password"
                                  placeholder={t("login.password_placeholder")}
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
                          {isLoading ? t("login.signing_in") : t("login.sign_in")}
                        </Button>
                      </form>
                    </Form>
                  </div>
                </div>

                <aside className="rounded-2xl border border-slate-800 bg-slate-950 px-6 py-7 text-slate-100 shadow-lg hidden lg:block">
                  <div className="text-xs font-semibold uppercase tracking-[0.24em] text-cyan-300 mb-5">
                    {t("login.whats_inside")}
                  </div>
                  <div className="space-y-4 text-sm text-slate-300 leading-relaxed">
                    <div>
                      <div className="text-white font-medium mb-0.5 flex items-center gap-2">
                        <LayoutDashboard className="h-3.5 w-3.5 text-sky-400 shrink-0" />
                        {t("login.crm_platform")}
                      </div>
                      {t("login.crm_platform_feature")}
                    </div>
                    <div>
                      <div className="text-white font-medium mb-0.5 flex items-center gap-2">
                        <Bot className="h-3.5 w-3.5 text-violet-400 shrink-0" />
                        {t("login.agent_console")}
                      </div>
                      {t("login.agent_console_feature")}
                    </div>
                    <div>
                      <div className="text-white font-medium mb-0.5 flex items-center gap-2">
                        <Settings className="h-3.5 w-3.5 text-amber-400 shrink-0" />
                        {t("login.tenant_admin")}
                      </div>
                      {t("login.tenant_admin_feature")}
                    </div>
                    <div>
                      <div className="text-white font-medium mb-0.5 flex items-center gap-2">
                        <Shield className="h-3.5 w-3.5 text-rose-400 shrink-0" />
                        {t("login.platform_admin")}
                      </div>
                      {t("login.platform_admin_feature")}
                    </div>
                  </div>
                </aside>
              </div>
          </section>
        </div>
      </div>

      <GlobalFooter className="border-0 bg-transparent text-slate-400" />
    </div>
  );
}
