/**
 * Post-login gate: superusers always enter Platform Admin; tenant users enter CRM.
 */
import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useLocation, Link } from "wouter";
import { Loader2, LogOut } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/contexts/AuthContext";
import { fetchJson, ApiError } from "@/lib/queryClient";
import { apiV1 } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { GlobalFooter } from "@/components/global-footer";

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

const DASHBOARD_PATH = "/dashboard";

export default function PlatformRouter() {
  const { t } = useTranslation();
  const { isAuthenticated, logout, isEmbeddedAdminConsole } = useAuth();
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
  const isSuperuser = Boolean(me?.is_superuser);
  const hasTenantAccess = Boolean(org && schemaName && schemaName !== publicSchema);

  useEffect(() => {
    if (me && isSuperuser && !isEmbeddedAdminConsole) {
      navigate("/platform-admin");
      return;
    }
    if (me && hasTenantAccess) {
      navigate(DASHBOARD_PATH);
    }
  }, [me, isSuperuser, hasTenantAccess, navigate, isEmbeddedAdminConsole]);

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

  if (!hasTenantAccess) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-[linear-gradient(135deg,#f8fafc,#e0ecff)] px-4">
        <p className="text-slate-600 text-center max-w-sm">
          {isSuperuser
            ? isEmbeddedAdminConsole
              ? "Preparing embedded tenant workspace..."
              : "Redirecting to Platform Admin..."
            : "You don’t have access to the CRM. Platform admins can use the platform admin URL directly."}
        </p>
        {!isSuperuser ? (
          <Button variant="outline" className="mt-4 gap-2" onClick={() => logout()}>
            <LogOut className="h-3.5 w-3.5" />
            Sign out
          </Button>
        ) : null}
      </div>
    );
  }

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-[linear-gradient(135deg,#f8fafc,#e0ecff)]">
      <Loader2 className="h-10 w-10 animate-spin text-slate-400" />
      <p className="mt-4 text-sm text-slate-500">{t("common.loading")}</p>
      <GlobalFooter className="mt-auto border-0 bg-transparent text-slate-400" />
    </div>
  );
}
