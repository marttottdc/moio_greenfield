import "./i18n";
import { Switch, Route, Redirect, useLocation } from "wouter";
import { queryClient } from "./lib/queryClient";
import { QueryClientProvider } from "@tanstack/react-query";
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
import IndexEntryPage from "@/pages/index-entry";
import Login from "@/pages/login";
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
import DocsHomePage from "@/pages/docs/index";
import DocsGuidePage from "@/pages/docs/guide";
import DocsEndpointPage from "@/pages/docs/endpoint";
import DocsSearchPage from "@/pages/docs/search";

function ProtectedRoute({ component: Component }: { component: () => JSX.Element }) {
  const { isAuthenticated, isLoading } = useAuth();

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

  return <Component />;
}

function AppRoutes() {
  const { isAuthenticated, isLoading } = useAuth();

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

  return (
    <Switch>
      <Route path="/login">
        <Login />
      </Route>

      <Route path="/desktop-agent-console/platform-admin">
        <PlatformAdminLegacyPage />
      </Route>
      <Route path="/desktop-agent-console/platform-admin/">
        <PlatformAdminLegacyPage />
      </Route>
      <Route path="/desktop-agent-console/tenant-admin">
        <TenantAdminLegacyPage />
      </Route>
      <Route path="/desktop-agent-console/tenant-admin/">
        <TenantAdminLegacyPage />
      </Route>
      <Route path="/desktop-agent-console/console">
        <DesktopAgentConsoleConsolePage />
      </Route>
      <Route path="/desktop-agent-console/console/">
        <DesktopAgentConsoleConsolePage />
      </Route>
      <Route path="/desktop-agent-console/">
        <DesktopAgentConsoleAccessHubPage />
      </Route>
      <Route path="/desktop-agent-console">
        <DesktopAgentConsoleAccessHubPage />
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
        <ProtectedRoute component={Dashboard} />
      </Route>
      <Route path="/crm">
        <ProtectedRoute component={CRM} />
      </Route>
      <Route path="/contacts">
        <Redirect to="/crm?tab=contacts" />
      </Route>
      <Route path="/deals">
        <ProtectedRoute component={Deals} />
      </Route>
      <Route path="/deals/analytics">
        <ProtectedRoute component={DealsAnalytics} />
      </Route>
      <Route path="/deals/manager">
        <ProtectedRoute component={DealManager} />
      </Route>
      <Route path="/communications">
        <ProtectedRoute component={Communications} />
      </Route>
      <Route path="/tickets">
        <ProtectedRoute component={Tickets} />
      </Route>
      <Route path="/campaigns/:id">
        <ProtectedRoute component={CampaignDetail} />
      </Route>
      <Route path="/campaigns">
        <Redirect to="/workflows?tab=campaigns" />
      </Route>
      <Route path="/workflows">
        <ProtectedRoute component={Workflows} />
      </Route>
      <Route path="/flows/new">
        <ProtectedRoute component={FlowBuilder} />
      </Route>
      <Route path="/flows/:id/edit">
        <ProtectedRoute component={FlowBuilder} />
      </Route>
      <Route path="/scripts/new">
        <ProtectedRoute component={ScriptBuilder} />
      </Route>
      <Route path="/scripts/:id/edit">
        <ProtectedRoute component={ScriptBuilder} />
      </Route>
      <Route path="/workflows/scripts">
        <ProtectedRoute component={ScriptsManager} />
      </Route>
      <Route path="/workflows/whatsapp-templates">
        <ProtectedRoute component={WhatsAppTemplatesManager} />
      </Route>
      <Route path="/workflows/webhooks">
        <ProtectedRoute component={WebhooksManager} />
      </Route>
      <Route path="/workflows/agent-tools">
        <ProtectedRoute component={AgentToolsManager} />
      </Route>
      <Route path="/workflows/events">
        <ProtectedRoute component={EventsBrowser} />
      </Route>
      <Route path="/workflows/mcp-connections">
        <ProtectedRoute component={MCPConnectionsManager} />
      </Route>
      <Route path="/workflows/json-schemas">
        <ProtectedRoute component={JsonSchemasManager} />
      </Route>
      <Route path="/workflows/robots">
        <Redirect to="/agent-console" />
      </Route>
      <Route path="/agent-console">
        <ProtectedRoute component={AgentConsole} />
      </Route>
      <Route path="/settings">
        <ProtectedRoute component={Settings} />
      </Route>
      <Route path="/platform-admin">
        <ProtectedRoute component={PlatformAdmin} />
      </Route>
      <Route path="/platform-admin/legacy">
        <ProtectedRoute component={PlatformAdminLegacyPage} />
      </Route>
      <Route path="/tenant-admin/legacy">
        <ProtectedRoute component={TenantAdminLegacyPage} />
      </Route>
      <Route path="/admin">
        <Redirect to="/platform-admin" />
      </Route>
      <Route path="/api-tester">
        <ProtectedRoute component={ApiTester} />
      </Route>
      <Route path="/activities">
        <ProtectedRoute component={Activities} />
      </Route>
      <Route path="/analytics">
        <Redirect to="/workflows?tab=reports" />
      </Route>
      <Route path="/datalab/create/import">
        <ProtectedRoute component={CreateImportDataset} />
      </Route>
      <Route path="/datalab/create/query">
        <ProtectedRoute component={CreateDatasetFromCRM} />
      </Route>
      <Route path="/datalab/dataset/:id">
        <ProtectedRoute component={DataLabHome} />
      </Route>
      <Route path="/datalab/resultset/:id">
        <ProtectedRoute component={DataLabHome} />
      </Route>
      <Route path="/datalab/generator/new">
        <ProtectedRoute component={DataLabHome} />
      </Route>
      <Route path="/datalab/generator/:id">
        <ProtectedRoute component={DataLabHome} />
      </Route>
      <Route path="/datalab/script/new">
        <ProtectedRoute component={DataLabHome} />
      </Route>
      <Route path="/datalab/script/:id">
        <ProtectedRoute component={DataLabHome} />
      </Route>
      <Route path="/datalab/import-process/new">
        <ProtectedRoute component={DataLabHome} />
      </Route>
      <Route path="/datalab/import-process/:id">
        <ProtectedRoute component={DataLabHome} />
      </Route>
      <Route path="/datalab">
        <ProtectedRoute component={DataLabHome} />
      </Route>
      
      <Route path="/">
        <IndexEntryPage />
      </Route>
      
      <Route component={NotFound} />
    </Switch>
  );
}

function AppLayout() {
  const { isAuthenticated } = useAuth();
  const [location] = useLocation();
  const isDocsPage = /^\/docs(\/|$)/.test(location);
  const isEntrySurface =
    location === "/" || /^\/desktop-agent-console(\/|$)/.test(location);

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

  const isLegacyAdminPreview =
    location === "/platform-admin/legacy" || location === "/tenant-admin/legacy";

  if (isLegacyAdminPreview) {
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
