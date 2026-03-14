import "./i18n";
import { Switch, Route, Redirect, useLocation, Link } from "wouter";
import { queryClient } from "./lib/queryClient";
import { QueryClientProvider, useQuery } from "@tanstack/react-query";
import { fetchJson } from "@/lib/queryClient";
import { apiV1 } from "@/lib/api";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { SidebarProvider } from "@/components/ui/sidebar";
import { AppBarActionProvider } from "@/contexts/AppBarActionContext";
import { AppSidebar } from "@/components/app-sidebar";
import { MobileAppBar } from "@/components/mobile-app-bar";
import { GlobalFooter } from "@/components/global-footer";
import { CacheBuster } from "@/components/cache-buster";
import { ThemeProvider } from "@/contexts/ThemeContext";
import { AuthProvider, useAuth } from "@/contexts/AuthContext";
import { UserLocationProvider } from "@/hooks/use-user-location";
import { LocaleProvider } from "@/contexts/LocaleContext";
import Login from "@/pages/login";
import PlatformRouter from "@/pages/platform-router";
import Dashboard from "@/pages/dashboard";
import CRM from "@/pages/crm";
import Deals from "@/pages/deals";
import DealsAnalytics from "@/pages/deals-analytics";
import DealManager from "@/pages/deal-manager";
import Communications from "@/pages/communications";
import Tickets from "@/pages/tickets";
import CampaignDetail from "@/pages/campaign-detail";
import Workflows from "@/pages/workflows";
import FlowBuilder from "@/pages/flow-builder";
import ScriptBuilder from "@/pages/script-builder";
import ScriptsManager from "@/pages/scripts-manager";
import WhatsAppTemplatesManager from "@/pages/whatsapp-templates-manager";
import WebhooksManager from "@/pages/webhooks-manager";
import AgentToolsManager from "@/pages/agent-tools-manager";
import EventsBrowser from "@/pages/events-browser";
import MCPConnectionsManager from "@/pages/mcp-connections-manager";
import JsonSchemasManager from "@/pages/json-schemas-manager";
import AgentConsole from "@/pages/agent-console";
import Settings from "@/pages/settings";
import PlatformAdmin from "@/pages/admin";
import PlatformAdminLegacyPage from "@/pages/platform-admin-legacy";
import TenantAdminLegacyPage from "@/pages/tenant-admin-legacy";
import DesktopAgentConsoleAccessHubPage from "@/pages/desktop-agent-console-access-hub";
import DesktopAgentConsoleConsolePage from "@/pages/desktop-agent-console-console";
import ApiTester from "@/pages/api-tester";
import Activities from "@/pages/activities";
import NotFound from "@/pages/not-found";
import DataLabHome from "@/pages/datalab/index";
import CreateImportDataset from "@/pages/datalab/create/import";
import CreateDatasetFromCRM from "@/pages/datalab/create/query";
import ShopifyLandingPage from "@/pages/shopify-landing";
import LandingPage from "@/pages/landing";
import ShopifyAppErrorPage from "@/pages/shopify-app-error";
import ShopifyAppInstallPage from "@/pages/shopify-app-install";
import { SHOPIFY_APP_PATH, isShopifyAppRoute } from "@/constants/shopify";
import {
  PLATFORM_ADMIN_NAMESPACE,
  PLATFORM_ADMIN_PATHS,
  isPlatformAdminRoute,
} from "@/constants/routes";
import DocsHomePage from "@/pages/docs/index";
import DocsGuidePage from "@/pages/docs/guide";
import DocsEndpointPage from "@/pages/docs/endpoint";
import DocsSearchPage from "@/pages/docs/search";
import { normalizeAppRole } from "@/lib/rbac";
import { lazy, Suspense } from "react";
import {
  type ModuleEnablements,
  type ModuleKey,
  inferModuleForRoute,
  isAddonRouteBlocked,
  isRouteBlockedByDevicePolicy,
  resolveModuleEnablements,
} from "@/lib/module-entitlements";
import { useIsMobile } from "@/hooks/use-mobile";
import { AlertTriangle, Home, MonitorSmartphone } from "lucide-react";

const ShopifyEmbed = lazy(() => import("@/pages/shopify-embed"));

function moduleLabel(moduleKey: ModuleKey): string {
  switch (moduleKey) {
    case "crm":
      return "CRM";
    case "flowsDatalab":
      return "Flows & Data Lab";
    case "chatbot":
      return "Chatbot";
    case "agentConsole":
      return "Agent Console";
    default:
      return "Module";
  }
}

function ModuleAccessBlocked({
  moduleKey,
  reason,
}: {
  moduleKey: ModuleKey;
  reason: "disabled" | "desktop-required";
}) {
  const title =
    reason === "disabled"
      ? `${moduleLabel(moduleKey)} is not enabled for this tenant`
      : `${moduleLabel(moduleKey)} is desktop-first`;
  const description =
    reason === "disabled"
      ? "Ask a platform administrator to enable this addon in tenant module settings."
      : "This section is optimized for desktop. Use a larger screen to access this functionality.";

  return (
    <div className="flex min-h-[60vh] items-center justify-center px-4">
      <div className="w-full max-w-xl rounded-2xl border border-slate-200 bg-white/90 p-6 shadow-sm">
        <div className="mb-4 flex items-start gap-3">
          <div className="rounded-xl bg-amber-100 p-2 text-amber-700">
            {reason === "disabled" ? (
              <AlertTriangle className="h-5 w-5" />
            ) : (
              <MonitorSmartphone className="h-5 w-5" />
            )}
          </div>
          <div>
            <h2 className="text-lg font-semibold text-slate-900">{title}</h2>
            <p className="mt-1 text-sm text-slate-600">{description}</p>
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          <Link
            href="/dashboard"
            className="inline-flex items-center gap-2 rounded-md border border-slate-700 bg-slate-800 px-3 py-2 text-xs font-medium text-white hover:bg-slate-700"
          >
            <Home className="h-3.5 w-3.5" />
            Go to dashboard
          </Link>
          {moduleKey === "flowsDatalab" && reason === "desktop-required" ? (
            <Link
              href="/analytics"
              className="inline-flex items-center gap-2 rounded-md border border-slate-300 bg-white px-3 py-2 text-xs font-medium text-slate-700 hover:bg-slate-50"
            >
              Open reports view
            </Link>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function RootRedirect() {
  const { isAuthenticated, isLoading, hasTenantAccess, isSuperuser, isEmbeddedAdminConsole } = useAuth();
  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto mb-4" />
          <p className="text-muted-foreground">Loading...</p>
        </div>
      </div>
    );
  }
  if (!isAuthenticated) return <Redirect to="/login" />;
  if (isSuperuser && !isEmbeddedAdminConsole) return <Redirect to="/platform-admin" />;
  if (hasTenantAccess) return <Redirect to="/dashboard" />;
  return <Redirect to="/platform-router" />;
}

function ProtectedRoute({
  component: Component,
  requiredRole,
  requiredModule,
  moduleEnablements,
}: {
  component: () => JSX.Element;
  requiredRole?: "tenant_admin";
  requiredModule?: ModuleKey;
  moduleEnablements?: ModuleEnablements;
}) {
  const { isAuthenticated, isLoading, user, hasTenantAccess } = useAuth();
  const [location] = useLocation();
  const isMobile = useIsMobile();

  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto mb-4"></div>
          <p className="text-muted-foreground">Loading...</p>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Redirect to="/login" />;
  }

  if (requiredRole && normalizeAppRole(user?.role) !== requiredRole) {
    return <Redirect to={hasTenantAccess ? "/dashboard" : "/platform-router"} />;
  }

  if (requiredModule && moduleEnablements && !moduleEnablements[requiredModule]) {
    return <ModuleAccessBlocked moduleKey={requiredModule} reason="disabled" />;
  }

  if (requiredModule && isRouteBlockedByDevicePolicy(location, requiredModule, isMobile)) {
    return <ModuleAccessBlocked moduleKey={requiredModule} reason="desktop-required" />;
  }

  if (moduleEnablements && isAddonRouteBlocked(location, moduleEnablements)) {
    const inferred = inferModuleForRoute(location);
    if (inferred) {
      return <ModuleAccessBlocked moduleKey={inferred} reason="disabled" />;
    }
    return <Redirect to="/dashboard" />;
  }

  return <Component />;
}

/** Layout for the platform-admin namespace: only logged-in superusers. Others redirect to avoid loops. */
function PlatformAdminLayout({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isSuperuser, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto mb-4"></div>
          <p className="text-muted-foreground">Loading...</p>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Redirect to="/login" />;
  }

  if (!isSuperuser) {
    return <Redirect to="/platform-router" />;
  }

  return <>{children}</>;
}

function AppRoutes() {
  const { isAuthenticated, isLoading } = useAuth();
  const { data: bootstrapData, isLoading: isBootstrapLoading } = useQuery<{
    entitlements?: {
      features?: Record<string, unknown>;
      ui?: Record<string, unknown>;
    };
    capabilities?: {
      effective_features?: Record<string, unknown>;
    };
  } | null>({
    queryKey: [apiV1("/bootstrap/")],
    queryFn: async () => fetchJson(apiV1("/bootstrap/")),
    enabled: isAuthenticated,
    staleTime: 60_000,
    refetchOnMount: "always",
    refetchOnWindowFocus: true,
    retry: false,
  });
  const moduleEnablements = resolveModuleEnablements(bootstrapData);

  if (isLoading || (isAuthenticated && isBootstrapLoading)) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto mb-4"></div>
          <p className="text-muted-foreground">Loading...</p>
        </div>
      </div>
    );
  }

  return (
    <Switch>
      <Route path="/login">
        <Login />
      </Route>
      <Route path="/platform-router">
        <PlatformRouter />
      </Route>

      {/* Legacy desktop-agent-console paths: redirect to Access Hub or canonical routes */}
      <Route path="/desktop-agent-console/platform-admin">
        <Redirect to={PLATFORM_ADMIN_NAMESPACE} />
      </Route>
      <Route path="/desktop-agent-console/platform-admin/">
        <Redirect to={PLATFORM_ADMIN_NAMESPACE} />
      </Route>
      <Route path="/desktop-agent-console/tenant-admin">
        <Redirect to="/tenant-admin" />
      </Route>
      <Route path="/desktop-agent-console/tenant-admin/">
        <Redirect to="/tenant-admin" />
      </Route>
      <Route path="/desktop-agent-console/console">
        <Redirect to="/agent-console" />
      </Route>
      <Route path="/desktop-agent-console/console/">
        <Redirect to="/agent-console" />
      </Route>
      <Route path="/desktop-agent-console/">
        <Redirect to="/login" />
      </Route>
      <Route path="/desktop-agent-console">
        <Redirect to="/login" />
      </Route>

      {/* Platform admin: single entry at /platform-admin (Django admin only) */}
      <Route path={`${PLATFORM_ADMIN_NAMESPACE}/`}>
        <PlatformAdminLayout>
          <PlatformAdminLegacyPage />
        </PlatformAdminLayout>
      </Route>
      <Route path={PLATFORM_ADMIN_PATHS.console}>
        <PlatformAdminLayout>
          <PlatformAdmin />
        </PlatformAdminLayout>
      </Route>
      <Route path={PLATFORM_ADMIN_NAMESPACE}>
        <PlatformAdminLayout>
          <PlatformAdminLegacyPage />
        </PlatformAdminLayout>
      </Route>

      <Route path="/docs/search">
        <DocsSearchPage />
      </Route>
      <Route path="/docs/guides/:slug">
        <DocsGuidePage />
      </Route>
      <Route path="/docs/api/:operationId">
        <DocsEndpointPage />
      </Route>
      <Route path="/docs">
        <DocsHomePage />
      </Route>
      
      <Route path="/dashboard">
        <ProtectedRoute component={Dashboard} moduleEnablements={moduleEnablements} />
      </Route>
      <Route path="/crm">
        <ProtectedRoute component={CRM} moduleEnablements={moduleEnablements} />
      </Route>
      <Route path="/contacts">
        <Redirect to="/crm?tab=contacts" />
      </Route>
      <Route path="/deals">
        <ProtectedRoute component={Deals} moduleEnablements={moduleEnablements} />
      </Route>
      <Route path="/deals/analytics">
        <ProtectedRoute component={DealsAnalytics} moduleEnablements={moduleEnablements} />
      </Route>
      <Route path="/deals/manager">
        <ProtectedRoute component={DealManager} moduleEnablements={moduleEnablements} />
      </Route>
      <Route path="/communications">
        <ProtectedRoute component={Communications} moduleEnablements={moduleEnablements} />
      </Route>
      <Route path="/tickets">
        <ProtectedRoute component={Tickets} moduleEnablements={moduleEnablements} />
      </Route>
      <Route path="/campaigns/:id">
        <ProtectedRoute component={CampaignDetail} moduleEnablements={moduleEnablements} />
      </Route>
      <Route path="/campaigns">
        <Redirect to="/workflows?tab=campaigns" />
      </Route>
      <Route path="/workflows">
        <ProtectedRoute component={Workflows} requiredModule="flowsDatalab" moduleEnablements={moduleEnablements} />
      </Route>
      <Route path="/flows/new">
        <ProtectedRoute component={FlowBuilder} requiredModule="flowsDatalab" moduleEnablements={moduleEnablements} />
      </Route>
      <Route path="/flows/:id/edit">
        <ProtectedRoute component={FlowBuilder} requiredModule="flowsDatalab" moduleEnablements={moduleEnablements} />
      </Route>
      <Route path="/scripts/new">
        <ProtectedRoute component={ScriptBuilder} requiredModule="flowsDatalab" moduleEnablements={moduleEnablements} />
      </Route>
      <Route path="/scripts/:id/edit">
        <ProtectedRoute component={ScriptBuilder} requiredModule="flowsDatalab" moduleEnablements={moduleEnablements} />
      </Route>
      <Route path="/workflows/scripts">
        <ProtectedRoute component={ScriptsManager} requiredModule="flowsDatalab" moduleEnablements={moduleEnablements} />
      </Route>
      <Route path="/workflows/whatsapp-templates">
        <ProtectedRoute component={WhatsAppTemplatesManager} requiredModule="flowsDatalab" moduleEnablements={moduleEnablements} />
      </Route>
      <Route path="/workflows/webhooks">
        <ProtectedRoute component={WebhooksManager} requiredModule="flowsDatalab" moduleEnablements={moduleEnablements} />
      </Route>
      <Route path="/workflows/agent-tools">
        <ProtectedRoute component={AgentToolsManager} requiredModule="flowsDatalab" moduleEnablements={moduleEnablements} />
      </Route>
      <Route path="/workflows/events">
        <ProtectedRoute component={EventsBrowser} requiredModule="flowsDatalab" moduleEnablements={moduleEnablements} />
      </Route>
      <Route path="/workflows/mcp-connections">
        <ProtectedRoute component={MCPConnectionsManager} requiredModule="flowsDatalab" moduleEnablements={moduleEnablements} />
      </Route>
      <Route path="/workflows/json-schemas">
        <ProtectedRoute component={JsonSchemasManager} requiredModule="flowsDatalab" moduleEnablements={moduleEnablements} />
      </Route>
      <Route path="/workflows/robots">
        <Redirect to="/agent-console" />
      </Route>
      <Route path="/agent-console">
        <ProtectedRoute component={AgentConsole} requiredModule="agentConsole" moduleEnablements={moduleEnablements} />
      </Route>
      <Route path="/settings">
        <ProtectedRoute component={Settings} requiredRole="tenant_admin" moduleEnablements={moduleEnablements} />
      </Route>
      <Route path="/tenant-admin/legacy">
        <Redirect to="/tenant-admin" />
      </Route>
      <Route path="/tenant-admin/">
        <ProtectedRoute component={TenantAdminLegacyPage} moduleEnablements={moduleEnablements} />
      </Route>
      <Route path="/tenant-admin">
        <ProtectedRoute component={TenantAdminLegacyPage} moduleEnablements={moduleEnablements} />
      </Route>
      <Route path="/admin">
        <Redirect to={PLATFORM_ADMIN_NAMESPACE} />
      </Route>
      <Route path="/api-tester">
        <ProtectedRoute component={ApiTester} moduleEnablements={moduleEnablements} />
      </Route>
      <Route path="/activities">
        <ProtectedRoute component={Activities} moduleEnablements={moduleEnablements} />
      </Route>
      <Route path="/analytics">
        {moduleEnablements.flowsDatalab ? (
          <Redirect to="/workflows?tab=reports" />
        ) : (
          <Redirect to="/dashboard?module=disabled" />
        )}
      </Route>
      <Route path="/datalab/create/import">
        <ProtectedRoute component={CreateImportDataset} requiredModule="flowsDatalab" moduleEnablements={moduleEnablements} />
      </Route>
      <Route path="/datalab/create/query">
        <ProtectedRoute component={CreateDatasetFromCRM} requiredModule="flowsDatalab" moduleEnablements={moduleEnablements} />
      </Route>
      <Route path="/datalab/dataset/:id">
        <ProtectedRoute component={DataLabHome} requiredModule="flowsDatalab" moduleEnablements={moduleEnablements} />
      </Route>
      <Route path="/datalab/resultset/:id">
        <ProtectedRoute component={DataLabHome} requiredModule="flowsDatalab" moduleEnablements={moduleEnablements} />
      </Route>
      <Route path="/datalab/generator/new">
        <ProtectedRoute component={DataLabHome} requiredModule="flowsDatalab" moduleEnablements={moduleEnablements} />
      </Route>
      <Route path="/datalab/generator/:id">
        <ProtectedRoute component={DataLabHome} requiredModule="flowsDatalab" moduleEnablements={moduleEnablements} />
      </Route>
      <Route path="/datalab/script/new">
        <ProtectedRoute component={DataLabHome} requiredModule="flowsDatalab" moduleEnablements={moduleEnablements} />
      </Route>
      <Route path="/datalab/script/:id">
        <ProtectedRoute component={DataLabHome} requiredModule="flowsDatalab" moduleEnablements={moduleEnablements} />
      </Route>
      <Route path="/datalab/import-process/new">
        <ProtectedRoute component={DataLabHome} requiredModule="flowsDatalab" moduleEnablements={moduleEnablements} />
      </Route>
      <Route path="/datalab/import-process/:id">
        <ProtectedRoute component={DataLabHome} requiredModule="flowsDatalab" moduleEnablements={moduleEnablements} />
      </Route>
      <Route path="/datalab">
        <ProtectedRoute component={DataLabHome} requiredModule="flowsDatalab" moduleEnablements={moduleEnablements} />
      </Route>
      
      <Route path="/landing">
        <LandingPage />
      </Route>

      {/* Shopify embedded app – no auth wrapper (App Bridge handles identity), lazy loaded */}
      <Route path={SHOPIFY_APP_PATH}>
        <Suspense fallback={
          <div className="flex min-h-screen items-center justify-center bg-[#f6f6f7]">
            <div className="flex flex-col items-center gap-3">
              <div className="w-8 h-8 border-[3px] border-[#008060] border-t-transparent rounded-full animate-spin" />
              <p className="text-sm text-gray-500">Loading…</p>
            </div>
          </div>
        }>
          <ShopifyEmbed />
        </Suspense>
      </Route>
      <Route path="/apps/shopify/error">
        <ShopifyAppErrorPage />
      </Route>
      <Route path="/apps/shopify/install">
        <ShopifyAppInstallPage />
      </Route>
      <Route path="/apps/shopify">
        <ShopifyLandingPage />
      </Route>

      <Route path="/">
        <RootRedirect />
      </Route>

      <Route component={NotFound} />
    </Switch>
  );
}

function AppLayout() {
  const { isAuthenticated } = useAuth();
  const [location] = useLocation();
  const isDocsPage = /^\/docs(\/|$)/.test(location);
  const isShopifyEmbed = isShopifyAppRoute(location);
  const isAgentConsoleSurface = /^\/agent-console(\/|$)/.test(location);
  const isEntrySurface =
    location === "/" || /^\/desktop-agent-console(\/|$)/.test(location);

  // Shopify embedded app – always render without any shell
  if (isShopifyEmbed) {
    return <AppRoutes />;
  }

  // Public landing page – no app shell
  if (location === "/landing") {
    return <AppRoutes />;
  }

  // Platform admin – no CRM shell, single entry at /platform-admin
  if (isPlatformAdminRoute(location)) {
    return <AppRoutes />;
  }

  // Agent Console has its own workspace shell; avoid double sidebars/bars.
  if (isAgentConsoleSurface) {
    return <AppRoutes />;
  }

  if (!isAuthenticated) {
    return <AppRoutes />;
  }

  if (isEntrySurface) {
    return <AppRoutes />;
  }

  if (isDocsPage) {
    return (
      <div className="min-h-screen bg-slate-950">
        <AppRoutes />
      </div>
    );
  }

  const isTenantAdmin = location.startsWith("/tenant-admin");
  if (isTenantAdmin) {
    return <AppRoutes />;
  }

  // Some workspaces need full-bleed layout (no main padding, no page scroll).
  const isFullBleedPage =
    location === "/flows/new" ||
    /^\/flows\/[^/]+\/edit\/?$/.test(location) ||
    /^\/datalab(\/|$)/.test(location) ||
    location === "/agent-console";

  return (
    <SidebarProvider 
      defaultOpen={false}
      style={{ 
        "--sidebar-width": "15rem",
        "--sidebar-width-icon": "4rem"
      } as React.CSSProperties}
    >
      <AppBarActionProvider>
      <div className="flex h-screen min-h-[100dvh] w-full relative bg-gradient-to-br from-slate-50 via-blue-50/30 to-amber-50/20">
        <div className="fixed inset-0 -z-10 overflow-hidden">
          <div className="absolute -top-40 -right-40 w-[600px] h-[600px] bg-gradient-to-br from-[#58a6ff]/30 via-blue-200/20 to-transparent rounded-full blur-3xl animate-float" />
          <div className="absolute top-1/2 -left-40 w-[500px] h-[500px] bg-gradient-to-tr from-[#ffba08]/25 via-amber-200/15 to-transparent rounded-full blur-3xl animate-float-delayed" />
          <div className="absolute -bottom-40 right-1/3 w-[550px] h-[550px] bg-gradient-to-tl from-blue-300/25 via-transparent to-[#58a6ff]/15 rounded-full blur-3xl animate-float-slow" />
        </div>
        
        <AppSidebar />
        <div className="flex flex-1 flex-col overflow-hidden min-h-0">
          <main
            className={cn(
              "flex-1 overflow-auto",
              isFullBleedPage ? "p-0" : "p-4 md:pl-4",
              "pb-24 md:pb-4" /* 96px: app bar + safe-area clearance for mobile */
            )}
          >
            <AppRoutes />
          </main>
          <GlobalFooter />
          <MobileAppBar />
        </div>
      </div>
      </AppBarActionProvider>
    </SidebarProvider>
  );
}

function AppContent() {
  return (
    <>
      <AppLayout />
      <Toaster />
    </>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <TooltipProvider>
          <AuthProvider>
            <UserLocationProvider>
              <LocaleProvider>
                <CacheBuster>
                  <AppContent />
                </CacheBuster>
              </LocaleProvider>
            </UserLocationProvider>
          </AuthProvider>
        </TooltipProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}
