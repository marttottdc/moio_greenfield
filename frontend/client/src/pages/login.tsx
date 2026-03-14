import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useLocation, Link } from "wouter";
import {
  ArrowLeft,
  BarChart3,
  Bot,
  Calendar,
  ChevronLeft,
  ChevronRight,
  LayoutDashboard,
  Loader2,
  Megaphone,
  MessageCircle,
  Plug,
  Sparkles,
  Workflow,
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
import { Button } from "@/components/ui/button";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import moioLogo from "@assets/Moio_New_Logo_Transparent_1764783655330.png";

// ─── Schema ───────────────────────────────────────────────────────────────────

const loginSchema = z.object({
  email: z.string().email("Valid email is required"),
  password: z.string().min(1, "Password is required"),
});
type LoginFormData = z.infer<typeof loginSchema>;

// ─── Dark-theme input (aligned with landing) ────────────────────────────────────

const inputBase =
  "flex h-11 w-full rounded-xl border border-white/[0.08] bg-white/[0.03] px-4 py-3 text-sm text-white placeholder:text-gray-500 outline-none transition-all duration-200 focus:border-[#58a6ff]/40 focus:bg-white/[0.05] focus:ring-1 focus:ring-[#58a6ff]/20 disabled:cursor-not-allowed disabled:opacity-50";

const LOGIN_CAROUSEL_ITEMS = [
  { icon: LayoutDashboard, title: "CRM Inteligente", desc: "Contactos, empresas, deals, pipeline visual, tickets y actividades en un solo lugar.", color: "#58a6ff" },
  { icon: MessageCircle, title: "Chatbot Multicanal", desc: "WhatsApp, Instagram, Messenger, web chat y Shopify con IA conversacional 24/7.", color: "#2ecc71" },
  { icon: Workflow, title: "Automatizaciones", desc: "Editor visual de flujos, triggers por eventos, webhooks, cron y scripts custom.", color: "#ffba08" },
  { icon: Bot, title: "Agent Console", desc: "Asistentes IA con workspaces, skills, plugins y herramientas personalizadas.", color: "#ff6b6b" },
  { icon: BarChart3, title: "Data Lab", desc: "Datasets, análisis, pipelines de importación y paneles de visualización.", color: "#a78bfa" },
  { icon: Calendar, title: "Calendario", desc: "Agendas de equipo, reservas de recursos y disponibilidad pública.", color: "#38bdf8" },
  { icon: Megaphone, title: "Campañas", desc: "Email, WhatsApp, Telegram y SMS con audiencias inteligentes.", color: "#f59e0b" },
  { icon: Plug, title: "Integraciones", desc: "Shopify, WooCommerce, OpenAI, Mercado Pago, Google APIs y más.", color: "#34d399" },
] as const;

const CAROUSEL_INTERVAL_MS = 5000;

// ─── Component ────────────────────────────────────────────────────────────────

export default function Login() {
  const { t } = useTranslation();
  const { login, isAuthenticated } = useAuth();
  const [, navigate] = useLocation();

  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [sessionExpiredMessage, setSessionExpiredMessage] = useState<string | null>(null);
  const [carouselIndex, setCarouselIndex] = useState(0);

  useEffect(() => {
    const id = setInterval(() => {
      setCarouselIndex((i) => (i + 1) % LOGIN_CAROUSEL_ITEMS.length);
    }, CAROUSEL_INTERVAL_MS);
    return () => clearInterval(id);
  }, []);

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
    <div className="relative min-h-screen font-sans text-white antialiased selection:bg-[#58a6ff]/30">
      {/* Background (aligned with landing) */}
      <div className="fixed inset-0 z-0 bg-[#08080d]" />
      <div className="pointer-events-none fixed inset-0 z-[1] overflow-hidden">
        <div
          className="absolute -top-40 -right-40 h-[600px] w-[600px] rounded-full opacity-60"
          style={{
            background: "radial-gradient(circle, rgba(88,166,255,0.15) 0%, transparent 70%)",
            filter: "blur(80px)",
          }}
        />
        <div
          className="absolute top-1/2 -left-40 h-[500px] w-[500px] rounded-full opacity-50"
          style={{
            background: "radial-gradient(circle, rgba(255,186,8,0.1) 0%, transparent 70%)",
            filter: "blur(70px)",
          }}
        />
      </div>
      <div
        className="pointer-events-none fixed inset-0 z-[1] opacity-[0.03]"
        style={{
          backgroundImage: "radial-gradient(circle, rgba(255,255,255,0.8) 1px, transparent 1px)",
          backgroundSize: "32px 32px",
        }}
      />

      <div className="relative z-[2] flex min-h-screen flex-col">
        {/* Header (same pattern as landing navbar) */}
        <header className="sticky top-0 z-50 border-b border-white/[0.04] bg-[#08080d]/70 backdrop-blur-2xl">
          <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
            <Link href="/">
              <img src={moioLogo} alt="Moio.ai" className="h-7 w-auto" data-testid="img-logo" />
            </Link>
            <Link
              href="/"
              className="flex items-center gap-2 rounded-lg px-4 py-2 text-[13px] font-medium text-gray-400 transition-colors hover:text-white"
            >
              <ArrowLeft className="h-3.5 w-3.5" />
              {t("login.back_to_home")}
            </Link>
          </div>
        </header>

        <div className="flex flex-1 items-center justify-center px-4 py-12">
          <div className="w-full max-w-5xl">
            {/* Card (GradientBorder-style like landing) */}
            <div className="relative overflow-hidden rounded-2xl border border-white/[0.08] bg-[#0c0c14] shadow-[0_32px_100px_-20px_rgba(0,0,0,0.8)]">
              <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-[#58a6ff]/40 to-transparent" />

              <div className="p-8 md:p-10">
                <div className="mb-8">
                  <h1 className="text-2xl font-semibold tracking-tight text-white md:text-3xl">
                    {t("login.access_hub")}
                  </h1>
                  <p className="mt-2 text-sm leading-relaxed text-gray-500">
                    {t("login.sign_in_prompt")}
                  </p>
                </div>

                <div className="grid gap-10 lg:grid-cols-[1.2fr_0.8fr]">
                  <div>
                    <Form {...form}>
                      <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
                        {sessionExpiredMessage && (
                          <div
                            className="rounded-xl border border-[#58a6ff]/25 bg-[#58a6ff]/10 px-4 py-3 text-sm text-[#7dd3fc]"
                            data-testid="alert-session-expired"
                          >
                            {sessionExpiredMessage}
                          </div>
                        )}
                        {errorMessage && (
                          <div
                            className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300"
                            data-testid="alert-error"
                          >
                            {errorMessage}
                          </div>
                        )}

                        <FormField
                          control={form.control}
                          name="email"
                          render={({ field }) => (
                            <FormItem>
                              <FormLabel className="text-sm font-medium text-gray-300">
                                {t("login.email")}
                              </FormLabel>
                              <FormControl>
                                <input
                                  type="email"
                                  placeholder={t("login.email_placeholder")}
                                  autoComplete="username"
                                  disabled={isLoading}
                                  data-testid="input-email"
                                  className={inputBase}
                                  {...field}
                                />
                              </FormControl>
                              <FormMessage className="text-red-400 text-xs" />
                            </FormItem>
                          )}
                        />

                        <FormField
                          control={form.control}
                          name="password"
                          render={({ field }) => (
                            <FormItem>
                              <FormLabel className="text-sm font-medium text-gray-300">
                                {t("login.password")}
                              </FormLabel>
                              <FormControl>
                                <input
                                  type="password"
                                  placeholder={t("login.password_placeholder")}
                                  autoComplete="current-password"
                                  disabled={isLoading}
                                  data-testid="input-password"
                                  className={inputBase}
                                  {...field}
                                />
                              </FormControl>
                              <FormMessage className="text-red-400 text-xs" />
                            </FormItem>
                          )}
                        />

                        <Button
                          type="submit"
                          className="h-12 w-full rounded-xl bg-[#58a6ff] px-6 text-[15px] font-semibold text-white transition-all hover:bg-[#4a96e8] hover:shadow-[0_0_40px_rgba(88,166,255,0.3)] disabled:opacity-50"
                          disabled={isLoading}
                          data-testid="button-login"
                        >
                          {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                          {isLoading ? t("login.signing_in") : t("login.sign_in")}
                        </Button>
                      </form>
                    </Form>
                  </div>

                  <aside className="hidden lg:block w-full min-w-0">
                    <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] overflow-hidden flex flex-col">
                      <div className="px-6 pt-6 pb-3 text-center">
                        <p className="text-[11px] font-medium tracking-widest text-gray-500 uppercase">Moio.ai</p>
                        <span className="mt-3 inline-flex items-center gap-1.5 rounded-full border border-[#58a6ff]/20 bg-[#58a6ff]/[0.06] px-3 py-1.5 text-[10px] font-semibold uppercase tracking-[0.15em] text-[#58a6ff]">
                          <Sparkles className="h-2.5 w-2.5" />
                          Todo en una plataforma
                        </span>
                        <h2 className="mt-4 text-lg font-bold tracking-tight text-white">
                          CRM, chatbots, automatizaciones e IA
                        </h2>
                        <p className="mt-1.5 text-xs text-gray-500">
                          Cada módulo integrado. Sin cambiar de herramienta.
                        </p>
                      </div>
                      <div className="relative flex-1 min-h-[280px] px-5 py-5">
                        {LOGIN_CAROUSEL_ITEMS.map((item, i) => {
                          const isActive = i === carouselIndex;
                          const Icon = item.icon;
                          return (
                            <div
                              key={item.title}
                              className={`absolute inset-5 flex flex-col items-center text-center rounded-2xl border border-white/[0.08] bg-[#0c0c14] p-6 transition-all duration-300 ${
                                isActive ? "opacity-100 z-10 translate-y-0" : "opacity-0 pointer-events-none translate-y-3"
                              }`}
                            >
                              <div
                                className="mb-5 inline-flex rounded-xl p-3"
                                style={{ backgroundColor: `${item.color}18` }}
                              >
                                <Icon className="h-6 w-6" style={{ color: item.color }} />
                              </div>
                              <h3 className="text-[15px] font-semibold text-white leading-snug">{item.title}</h3>
                              <p className="mt-3 text-[13px] leading-relaxed text-gray-500 flex-1 max-w-sm">{item.desc}</p>
                            </div>
                          );
                        })}
                      </div>
                      <div className="flex items-center justify-between gap-4 border-t border-white/[0.04] px-5 py-4">
                        <button
                          type="button"
                          onClick={() => setCarouselIndex((i) => (i - 1 + LOGIN_CAROUSEL_ITEMS.length) % LOGIN_CAROUSEL_ITEMS.length)}
                          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-white/[0.08] bg-white/[0.02] text-gray-400 transition-colors hover:border-[#58a6ff]/30 hover:bg-[#58a6ff]/10 hover:text-white"
                          aria-label="Anterior"
                        >
                          <ChevronLeft className="h-5 w-5" />
                        </button>
                        <div className="flex gap-2">
                          {LOGIN_CAROUSEL_ITEMS.map((_, i) => (
                            <button
                              key={i}
                              type="button"
                              onClick={() => setCarouselIndex(i)}
                              className={`h-2 rounded-full transition-all ${
                                i === carouselIndex ? "bg-[#58a6ff] w-6" : "w-2 bg-white/25 hover:bg-white/40"
                              }`}
                              aria-label={`Slide ${i + 1}`}
                            />
                          ))}
                        </div>
                        <button
                          type="button"
                          onClick={() => setCarouselIndex((i) => (i + 1) % LOGIN_CAROUSEL_ITEMS.length)}
                          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-white/[0.08] bg-white/[0.02] text-gray-400 transition-colors hover:border-[#58a6ff]/30 hover:bg-[#58a6ff]/10 hover:text-white"
                          aria-label="Siguiente"
                        >
                          <ChevronRight className="h-5 w-5" />
                        </button>
                      </div>
                    </div>
                  </aside>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Footer (aligned with landing) */}
        <footer className="border-t border-white/[0.04] py-6">
          <div className="mx-auto max-w-7xl px-6">
            <p className="text-center text-[12px] text-gray-600">
              © {new Date().getFullYear()} Moio.ai
            </p>
          </div>
        </footer>
      </div>
    </div>
  );
}
