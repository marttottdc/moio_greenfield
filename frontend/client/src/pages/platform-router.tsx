/**
 * Single post-login screen: fetches /api/v1/auth/me/ and shows options based on response.
 * - Enter CRM if tenant not null and not public
 * - Platform Admin if superuser
 * - Tenant Admin if role is tenant_admin
 * User selects one → navigate to that link.
 */
import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useLocation, Link } from "wouter";
import { LayoutDashboard, Loader2, LogOut, Settings, Shield } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/contexts/AuthContext";
import { fetchJson, ApiError } from "@/lib/queryClient";
import { apiV1 } from "@/lib/api";
import { PLATFORM_ADMIN_NAMESPACE } from "@/constants/routes";
import { Button } from "@/components/ui/button";
import { GlobalFooter } from "@/components/global-footer";
import moioLogo from "@assets/FAVICON_MOIO_1763393251809.png";

interface MeUser {
  id: string | number;
  username?: string;
  email?: string;
  full_name?: string;
  role?: string;
  is_staff?: boolean;
  is_superuser?: boolean;
  organization?: {
    id: string;
    name: string | null;
    schema_name?: string;
    [key: string]: unknown;
  } | null;
}

const ME_PATH = "/auth/me/";

function useMe() {
  return useQuery({
    queryKey: [apiV1(ME_PATH)],
    queryFn: () => fetchJson<MeUser>(apiV1(ME_PATH)),
    staleTime: 60 * 1000,
    retry: false,
  });
}

export default function PlatformRouter() {
  const { t } = useTranslation();
  const { isAuthenticated, logout } = useAuth();
  const [, navigate] = useLocation();
  const { data: me, isLoading, error } = useMe();

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      navigate("/login");
    }
  }, [isLoading, isAuthenticated, navigate]);

  const org = me?.organization;
  const schemaName = (org?.schema_name ?? "").trim().toLowerCase();
  const publicSchema = "public";
  const hasTenantAccess = Boolean(org && schemaName && schemaName !== publicSchema);
  const isSuperuser = Boolean(me?.is_superuser);
  const isTenantAdmin = (me?.role ?? "").toLowerCase() === "tenant_admin";

  const options: { key: string; labelKey: string; path: string; icon: typeof LayoutDashboard; iconBg: string }[] = [];
  if (hasTenantAccess) {
    options.push({
      key: "crm",
      labelKey: "login.crm_platform",
      path: "/dashboard",
      icon: LayoutDashboard,
      iconBg: "bg-gradient-to-br from-sky-500 to-blue-600",
    });
  }
  if (isSuperuser) {
    options.push({
      key: "platform-admin",
      labelKey: "login.platform_admin",
      path: PLATFORM_ADMIN_NAMESPACE,
      icon: Shield,
      iconBg: "bg-gradient-to-br from-rose-500 to-red-600",
    });
  }
  if (isTenantAdmin) {
    options.push({
      key: "tenant-admin",
      labelKey: "login.tenant_admin",
      path: "/tenant-admin",
      icon: Settings,
      iconBg: "bg-gradient-to-br from-amber-500 to-orange-600",
    });
  }

  const singlePath = options.length === 1 ? options[0].path : null;
  useEffect(() => {
    if (me && singlePath) {
      navigate(singlePath);
    }
  }, [me, singlePath, navigate]);

  if (!isAuthenticated || isLoading) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-[linear-gradient(135deg,#f8fafc,#e0ecff)]">
        <Loader2 className="h-10 w-10 animate-spin text-slate-400" />
        <p className="mt-4 text-sm text-slate-500">{t("common.loading")}</p>
      </div>
    );
  }

  if (error || !me) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-[linear-gradient(135deg,#f8fafc,#e0ecff)] px-4">
        <p className="text-slate-600">
          {error instanceof ApiError && error.status === 401
            ? t("login.session_expired")
            : t("login.unexpected_error")}
        </p>
        <Button asChild className="mt-4">
          <Link href="/login">Back to sign in</Link>
        </Button>
      </div>
    );
  }

  if (options.length === 0) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-[linear-gradient(135deg,#f8fafc,#e0ecff)] px-4">
        <p className="text-slate-600">You don’t have access to any area. Contact your administrator.</p>
        <Button variant="outline" className="mt-4" onClick={() => logout()}>
          Sign out
        </Button>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex flex-col relative overflow-hidden bg-[radial-gradient(circle_at_top_left,_rgba(59,130,246,0.18),_transparent_32%),radial-gradient(circle_at_top_right,_rgba(245,158,11,0.14),_transparent_28%),linear-gradient(135deg,#f8fafc,#e0ecff)]">
      <div className="fixed inset-0 -z-10 overflow-hidden pointer-events-none">
        <div className="absolute -top-40 -right-40 w-[600px] h-[600px] bg-gradient-to-br from-[#58a6ff]/30 via-blue-200/20 to-transparent rounded-full blur-3xl animate-float" />
        <div className="absolute top-1/2 -left-40 w-[500px] h-[500px] bg-gradient-to-tr from-[#ffba08]/25 via-amber-200/15 to-transparent rounded-full blur-3xl animate-float-delayed" />
      </div>

      <div className="flex-1 flex items-center justify-center px-4 py-10">
        <div className="w-full max-w-2xl">
          <section className="rounded-[2rem] border border-slate-200/70 bg-white/85 p-8 shadow-[0_28px_90px_rgba(15,23,42,0.14)] backdrop-blur-md">
            <div className="flex items-center gap-4 mb-8">
              <img src={moioLogo} alt="moio" className="h-12 w-auto" />
              <div>
                <div className="font-mono text-xs font-semibold uppercase tracking-[0.24em] text-slate-500">Moio</div>
                <h1 className="text-2xl font-semibold tracking-tight text-slate-900">{t("login.select_destination")}</h1>
              </div>
            </div>

            <div className="grid gap-8 lg:grid-cols-[200px_1fr]">
              <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                <div className="text-xs font-semibold uppercase tracking-widest text-slate-400 mb-2">{t("login.signed_in")}</div>
                <div className="text-sm font-semibold text-slate-900 truncate">{me.full_name || me.username || me.email}</div>
                {me.email && <div className="text-xs text-slate-500 truncate mt-0.5">{me.email}</div>}
                {me.role && (
                  <div className="mt-2 inline-block rounded-full border border-slate-200 bg-slate-50 px-2.5 py-0.5 text-xs font-medium text-slate-600 capitalize">
                    {String(me.role).replace(/_/g, " ")}
                  </div>
                )}
                {org?.name && <div className="text-xs text-slate-400 mt-1 truncate">{org.name}</div>}
                <Button
                  variant="ghost"
                  size="sm"
                  className="mt-4 w-full gap-2 text-slate-600"
                  onClick={() => logout()}
                >
                  <LogOut className="h-3.5 w-3.5" />
                  {t("login.sign_out")}
                </Button>
              </div>

              <div>
                <p className="text-slate-600 mb-4 text-sm">Choose where to go:</p>
                <div className="grid gap-3 sm:grid-cols-2">
                  {options.map((opt) => (
                    <button
                      key={opt.key}
                      type="button"
                      onClick={() => navigate(opt.path)}
                      className="group text-left rounded-2xl border border-slate-200 bg-white p-5 shadow-sm hover:shadow-md hover:-translate-y-0.5 transition-all duration-150"
                    >
                      <div className={`inline-flex h-9 w-9 items-center justify-center rounded-xl ${opt.iconBg} mb-3`}>
                        <opt.icon className="h-4 w-4 text-white" />
                      </div>
                      <div className="font-semibold text-slate-900 text-sm">{t(opt.labelKey)}</div>
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </section>
        </div>
      </div>

      <GlobalFooter className="border-0 bg-transparent text-slate-400" />
    </div>
  );
}
