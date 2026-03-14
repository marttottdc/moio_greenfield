import { useMemo, useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { Link, useLocation } from "wouter";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import moioLogo from "@assets/Moio_New_Logo_Transparent_1764783655330.png";
import {
  LayoutDashboard,
  BarChart3,
  Users,
  Briefcase,
  ListTodo,
  Calendar,
  MessageSquare,
  Building2,
  Ticket,
  Workflow,
  Package,
  Settings,
  Shield,
  LogOut,
  UserCircle,
  KeyRound,
  Key,
  Copy,
  AlertCircle,
  ChevronDown,
  Sliders,
  PanelLeftClose,
  PanelLeftOpen,
  Sun,
  Moon,
  CheckSquare,
  Database,
  Loader2,
  Bot,
} from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { useLocale } from "@/contexts/LocaleContext";
import { useTranslation } from "react-i18next";
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarHeader,
  SidebarFooter,
  useSidebar,
} from "@/components/ui/sidebar";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { useTheme } from "@/contexts/ThemeContext";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { Skeleton } from "@/components/ui/skeleton";
import { fetchJson, ApiError, apiRequest, queryClient } from "@/lib/queryClient";
import { apiV1 } from "@/lib/api";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Form, FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { useToast } from "@/hooks/use-toast";
import { getApiKeyStatus, createApiKey, revokeApiKey } from "@/lib/auth/apiKeyApi";
import { formatDistanceToNow } from "date-fns";
import { Badge } from "@/components/ui/badge";
import { PLATFORM_ADMIN_NAMESPACE } from "@/constants/routes";
import { isPlatformAdminRole, isTenantAdminRole, normalizeAppRole } from "@/lib/rbac";
import {
  inferModuleForRoute,
  isRouteBlockedByDevicePolicy,
  resolveModuleEnablements,
} from "@/lib/module-entitlements";

interface OrganizationSummary {
  id?: string;
  name?: string | null;
  plan?: string;
}

interface AuthenticatedUser {
  id: string;
  username: string;
  email?: string;
  full_name?: string | null;
  role?: string | null;
  avatar_url?: string | null;
  organization?: OrganizationSummary | null;
}

interface NavigationNode {
  id: string;
  label: string;
  url?: string;
  icon?: string;
  feature_enabled?: boolean;
  requires_role?: string[];
  children?: NavigationNode[];
}

interface NavigationResponse {
  items: NavigationNode[];
  version?: string;
}

const iconMap: Record<string, any> = {
  dashboard: LayoutDashboard,
  contacts: Users,
  deals: Briefcase,
  tasks: ListTodo,
  calendar: Calendar,
  communications: MessageSquare,
  campaigns: Building2,
  tickets: Ticket,
  workflows: Workflow,
  assets: Package,
  admin: Shield,
  settings: Settings,
  activities: CheckSquare,
  datalab: Database,
  agents: Bot,
  agent_console: Bot,
};

/** Map navigation node id from API to translation key (so menu items are localized) */
const NAV_ID_TO_TRANSLATION_KEY: Record<string, string> = {
  dashboard: "menu.dashboard",
  crm: "menu.crm",
  contacts: "menu.crm",
  deals: "menu.deals",
  activities: "menu.activities",
  communications: "menu.communications",
  tickets: "menu.tickets",
  workflows: "menu.automation_studio",
  campaigns: "menu.crm",
  datalab: "menu.data_lab",
  "data lab": "menu.data_lab",
  agent_console: "menu.agent_console",
  agents: "menu.agent_console",
  settings: "menu.settings",
  admin: "menu.platform_admin",
  platform_admin: "menu.platform_admin",
  api_tester: "menu.api_tester",
};


const passwordChangeSchema = z.object({
  current_password: z.string().min(1, "Current password is required"),
  new_password: z.string().min(8, "Password must be at least 8 characters"),
  confirm_password: z.string().min(1, "Please confirm your password"),
}).refine((data) => data.new_password === data.confirm_password, {
  message: "Passwords don't match",
  path: ["confirm_password"],
});

const localizationSchema = z.object({
  language: z.enum(["en", "es", "pt"]),
  timezone: z.string(),
  currency: z.string(),
});

export function AppSidebar() {
  const [location] = useLocation();
  const { logout } = useAuth();
  const { toast } = useToast();
  const { open: sidebarOpen, toggleSidebar, setOpenMobile, isMobile } = useSidebar();
  const { theme, toggleTheme } = useTheme();
  const [profileModalOpen, setProfileModalOpen] = useState(false);
  const [passwordModalOpen, setPasswordModalOpen] = useState(false);
  const [preferencesModalOpen, setPreferencesModalOpen] = useState(false);
  const [logoutConfirmOpen, setLogoutConfirmOpen] = useState(false);
  const [apiKeyModalOpen, setApiKeyModalOpen] = useState(false);
  const [apiKeyCreateOpen, setApiKeyCreateOpen] = useState(false);
  const [apiKeyCreateName, setApiKeyCreateName] = useState("");
  const [newKeyShown, setNewKeyShown] = useState<{ key: string; warning?: string } | null>(null);
  const [revokeConfirmOpen, setRevokeConfirmOpen] = useState(false);
  const profilePath = apiV1("/auth/me/");
  const navigationPath = apiV1("/content/navigation/");
  const { t } = useTranslation();
  const {
    locale,
    timezone,
    currency,
    setLocale,
    setTimezone,
    setCurrency,
    isLoading: isLocaleLoading,
  } = useLocale();

  const {
    data: user,
    isLoading: isUserLoading,
  } = useQuery<AuthenticatedUser | null, ApiError>({
    queryKey: [profilePath],
    queryFn: async () => {
      try {
        return await fetchJson<AuthenticatedUser>(profilePath);
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) {
          return null;
        }

        if (error instanceof ApiError) {
          throw error;
        }

        const message =
          error instanceof Error ? error.message : "Unable to load user";
        throw new ApiError(0, message);
      }
    },
    staleTime: 5 * 60 * 1000,
    retry: false,
  });

  const {
    data: navigationData,
  } = useQuery<NavigationResponse | null, ApiError>({
    queryKey: [navigationPath],
    queryFn: async () => {
      try {
        return await fetchJson<NavigationResponse>(navigationPath);
      } catch (error) {
        if (error instanceof ApiError && (error.status === 404 || error.status === 501)) {
          return null;
        }
        throw error;
      }
    },
    staleTime: 10 * 60 * 1000,
    retry: false,
  });

  const { data: bootstrapData } = useQuery<
    {
      entitlements?: {
        features?: Record<string, unknown>;
        ui?: Record<string, unknown>;
      };
      capabilities?: {
        effective_features?: Record<string, unknown>;
      };
    } | null,
    ApiError
  >({
    queryKey: [apiV1("/bootstrap/")],
    queryFn: async () => {
      try {
        return await fetchJson(apiV1("/bootstrap/"));
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) {
          return null;
        }
        throw error;
      }
    },
    enabled: !!user,
    staleTime: 60 * 1000,
    refetchOnMount: "always",
    refetchOnWindowFocus: true,
    retry: false,
  });

  const moduleEnablements = resolveModuleEnablements(bootstrapData);

  const { displayName, organizationName, avatarFallback } = useMemo(() => {
    if (!user) {
      return {
        displayName: "Guest User",
        organizationName: "Connect to the Moio API",
        avatarFallback: "GU",
      };
    }

    const name = user.full_name?.trim() || user.username;
    const organization = user.organization?.name?.trim();

    const fallback = name
      .split(" ")
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0]?.toUpperCase())
      .join("");

    return {
      displayName: name,
      organizationName: organization || "Moio Platform",
      avatarFallback: fallback || user.username.slice(0, 2).toUpperCase(),
    };
  }, [user]);

  type MenuItem = {
    title: string;
    url: string;
    icon: any;
  };

  const menuItems = useMemo<MenuItem[]>(() => {
    const normalizedUserRole = normalizeAppRole(user?.role);
    const isExactTenantAdmin = normalizedUserRole === "tenant_admin";
    const tenantAdminPath = "/tenant-admin";

    if (navigationData?.items && navigationData.items.length > 0) {
      const mapped = navigationData.items
        .filter((node) => {
          if (node.feature_enabled === false) return false;
          const isSettingsNode =
            node.id === "settings" ||
            String(node.url || "").trim() === "/settings" ||
            String(node.label || "").trim().toLowerCase() === "settings";
          if (isSettingsNode) {
            return false;
          }
          const isTenantAdminOnlyNode =
            node.id === "admin" ||
            node.id === "platform_admin" ||
            (node.icon === "admin" && node.url === PLATFORM_ADMIN_NAMESPACE);
          if (isTenantAdminOnlyNode && !isExactTenantAdmin) {
            return false;
          }
          if (node.requires_role && node.requires_role.length > 0 && user?.role) {
            return node.requires_role.includes(user.role);
          }
          return node.url != null;
        })
        .map((node) => {
          const transKey = NAV_ID_TO_TRANSLATION_KEY[node.id] ?? NAV_ID_TO_TRANSLATION_KEY[node.label?.toLowerCase()];
          const title = transKey ? t(transKey) : node.label;
          const isDataLab = node.id === "datalab" || node.label?.toLowerCase() === "data lab";
          const isWorkflowsNode = node.id === "workflows" || String(node.url || "").trim() === "/workflows";
          const isTenantAdminOnlyNode =
            node.id === "admin" ||
            node.id === "platform_admin" ||
            (node.icon === "admin" && node.url === PLATFORM_ADMIN_NAMESPACE);
          const nextUrl = isTenantAdminOnlyNode
            ? tenantAdminPath
            : isDataLab
              ? "/datalab"
              : isWorkflowsNode && isMobile
                ? "/analytics"
                : (node.url || "#");
          return {
            title,
            url: nextUrl,
            icon: node.icon ? iconMap[node.icon] || LayoutDashboard : LayoutDashboard,
          };
        })
        .filter((item) => {
          const moduleKey = inferModuleForRoute(item.url);
          if (moduleKey && !moduleEnablements[moduleKey]) return false;
          if (moduleKey && isRouteBlockedByDevicePolicy(item.url, moduleKey, isMobile)) return false;
          return true;
        });

      return mapped;
    }

    const plan = (user?.organization?.plan ?? "free").toLowerCase();
    const isFreeTier = plan === "free";

    const items: MenuItem[] = [
      { title: t("menu.dashboard"), url: "/dashboard", icon: LayoutDashboard },
      { title: t("menu.crm"), url: "/crm", icon: Users },
      { title: t("menu.deals"), url: "/deals", icon: Briefcase },
      { title: t("menu.activities"), url: "/activities", icon: CheckSquare },
      ...(!isFreeTier ? [{ title: t("menu.communications"), url: "/communications", icon: MessageSquare }] : []),
      { title: t("menu.tickets"), url: "/tickets", icon: Ticket },
      ...(moduleEnablements.flowsDatalab
        ? [
            { title: t("menu.automation_studio"), url: isMobile ? "/analytics" : "/workflows", icon: Workflow },
            ...(!isMobile ? [{ title: t("menu.data_lab"), url: "/datalab", icon: Database }] : []),
          ]
        : []),
      ...(moduleEnablements.agentConsole ? [{ title: t("menu.agent_console"), url: "/agent-console", icon: Bot }] : []),
    ];

    const userRole = user?.role;

    if (isExactTenantAdmin) {
      items.push({ title: t("menu.platform_admin"), url: tenantAdminPath, icon: Shield });
    }

    if (isPlatformAdminRole(userRole)) {
      items.push({ title: t("menu.api_tester"), url: "/api-tester", icon: Sliders });
    }

    return items;
  }, [navigationData, user, t, moduleEnablements, isMobile]);

  const { data: apiKeyStatus, isLoading: apiKeyLoading } = useQuery({
    queryKey: ["auth", "api-key"],
    queryFn: getApiKeyStatus,
    retry: false,
    enabled: apiKeyModalOpen,
  });

  const createKeyMutation = useMutation({
    mutationFn: ({ name }: { name?: string }) => createApiKey(name),
    onSuccess: (data) => {
      setApiKeyCreateOpen(false);
      setApiKeyCreateName("");
      setNewKeyShown({ key: data.key, warning: data.warning });
      queryClient.invalidateQueries({ queryKey: ["auth", "api-key"] });
      toast({ title: t("toast.api_key_created"), description: t("toast.api_key_created_description") });
    },
    onError: (err: ApiError) => {
      toast({ title: t("toast.api_key_create_failed"), description: err.message, variant: "destructive" });
    },
  });

  const revokeKeyMutation = useMutation({
    mutationFn: revokeApiKey,
    onSuccess: () => {
      setRevokeConfirmOpen(false);
      queryClient.invalidateQueries({ queryKey: ["auth", "api-key"] });
      toast({ title: t("toast.api_key_revoked") });
    },
    onError: (err: ApiError) => {
      toast({ title: t("toast.api_key_revoke_failed"), description: err.message, variant: "destructive" });
    },
  });

  const passwordForm = useForm<z.infer<typeof passwordChangeSchema>>({
    resolver: zodResolver(passwordChangeSchema),
    defaultValues: {
      current_password: "",
      new_password: "",
      confirm_password: "",
    },
  });

  const preferencesForm = useForm<z.infer<typeof localizationSchema>>({
    resolver: zodResolver(localizationSchema),
    values: {
      language: (locale === "pt" ? "pt" : locale === "es" ? "es" : "en") as "en" | "es" | "pt",
      timezone,
      currency,
    },
  });

  const changePasswordMutation = useMutation({
    mutationFn: async (data: z.infer<typeof passwordChangeSchema>) => {
      const res = await apiRequest("POST", apiV1("/auth/change-password/"), {
        data: {
          current_password: data.current_password,
          new_password: data.new_password,
        }
      });
      return res.json();
    },
    onSuccess: () => {
      toast({
        title: t("toast.password_changed"),
        description: t("toast.password_changed_description"),
      });
      setPasswordModalOpen(false);
      passwordForm.reset();
    },
    onError: (error: ApiError) => {
      toast({
        title: t("toast.update_failed"),
        description: error.message || "Failed to update password",
        variant: "destructive",
      });
    },
  });

  const localizationMutation = useMutation({
    mutationFn: async (data: z.infer<typeof localizationSchema>) => {
      await setLocale(data.language);
      await setTimezone(data.timezone);
      await setCurrency(data.currency);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["localization"] });
      toast({
        title: t("toast.preferences_updated"),
        description: t("toast.preferences_updated_description"),
      });
      setPreferencesModalOpen(false);
    },
    onError: (error: ApiError) => {
      toast({
        title: t("toast.update_failed"),
        description: error.message || "Failed to update preferences",
        variant: "destructive",
      });
    },
  });

  const handlePasswordChange = (data: z.infer<typeof passwordChangeSchema>) => {
    changePasswordMutation.mutate(data);
  };

  const handlePreferencesUpdate = (data: z.infer<typeof localizationSchema>) => {
    localizationMutation.mutate(data);
  };

  const handleLogout = () => {
    setLogoutConfirmOpen(false);
    logout();
  };

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader className="p-6 pb-4">
        <div className="flex items-center gap-3 group-data-[collapsible=icon]:justify-center">
          <img 
            src={moioLogo} 
            alt="Moio Logo" 
            className="h-14 w-14 min-h-14 min-w-14 shrink-0 object-contain"
          />
          {sidebarOpen && (
            <div className="flex flex-col">
              <span className="text-lg font-bold tracking-tight">moio</span>
              <span className="text-xs text-muted-foreground">CRM PLATFORM</span>
            </div>
          )}
        </div>
      </SidebarHeader>
      
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupContent>
            <SidebarMenu className="group-data-[collapsible=icon]:items-center">
              {menuItems.map((item) => {
                // Check if current location matches this menu item
                // Handle sub-routes for sections like /datalab/script/123, /workflows/*, /crm/*
                const isActive = 
                  location === item.url || 
                  location.startsWith(item.url + "/") || 
                  location.startsWith(item.url + "?");
                return (
                  <SidebarMenuItem key={item.title}>
                    <SidebarMenuButton asChild isActive={isActive} data-testid={`link-${item.title.toLowerCase()}`} tooltip={item.title}>
                      <Link
                        href={item.url}
                        className="group-data-[collapsible=icon]:justify-center"
                        onClick={() => setOpenMobile(false)}
                      >
                        <item.icon className="h-4 w-4 shrink-0" />
                        <span className="group-data-[collapsible=icon]:hidden">{item.title}</span>
                      </Link>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                );
              })}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
        
        <div className="px-6 py-2 group-data-[collapsible=icon]:px-2 flex justify-center">
          <Tooltip>
            <TooltipTrigger asChild>
              <Button 
                variant="ghost" 
                size="icon"
                onClick={toggleSidebar}
                data-testid="button-sidebar-collapse"
              >
                {sidebarOpen ? (
                  <PanelLeftClose className="h-4 w-4 shrink-0" />
                ) : (
                  <PanelLeftOpen className="h-4 w-4 shrink-0" />
                )}
              </Button>
            </TooltipTrigger>
            <TooltipContent side="right">
              {sidebarOpen ? t("sidebar.collapse") : t("sidebar.expand")}
            </TooltipContent>
          </Tooltip>
        </div>
      </SidebarContent>

      <SidebarFooter className="p-4">
        <DropdownMenu>
          <Tooltip>
            <TooltipTrigger asChild>
              <DropdownMenuTrigger asChild>
                <button 
                  className="flex items-center gap-3 rounded-lg p-2 w-full hover-elevate active-elevate-2 text-left group-data-[collapsible=icon]:justify-center"
                  data-testid="button-user-menu"
                >
                  {isUserLoading ? (
                    <>
                      <Skeleton className="h-8 w-8 rounded-full shrink-0" />
                      <div className="flex flex-col flex-1 min-w-0 gap-1 group-data-[collapsible=icon]:hidden">
                        <Skeleton className="h-3 w-24" />
                        <Skeleton className="h-3 w-20" />
                      </div>
                    </>
                  ) : (
                    <>
                      <Avatar className="h-8 w-8 shrink-0" data-testid="img-avatar-user">
                        {user?.avatar_url ? (
                          <AvatarImage src={user.avatar_url} alt={displayName} />
                        ) : null}
                        <AvatarFallback className="bg-primary text-primary-foreground text-xs font-semibold">
                          {avatarFallback}
                        </AvatarFallback>
                      </Avatar>
                      <div className="flex flex-col flex-1 min-w-0 group-data-[collapsible=icon]:hidden">
                        <span className="text-sm font-medium truncate" data-testid="text-username">
                          {displayName}
                        </span>
                        <span className="text-xs text-muted-foreground truncate">
                          {organizationName}
                        </span>
                      </div>
                      <ChevronDown className="h-4 w-4 text-muted-foreground group-data-[collapsible=icon]:hidden" />
                    </>
                  )}
                </button>
              </DropdownMenuTrigger>
            </TooltipTrigger>
            {!sidebarOpen && (
              <TooltipContent side="right">
                <div className="flex flex-col">
                  <span className="font-medium">{displayName}</span>
                  <span className="text-xs text-muted-foreground">{organizationName}</span>
                </div>
              </TooltipContent>
            )}
          </Tooltip>
          <DropdownMenuContent align="end" className="w-56">
            <DropdownMenuItem onClick={() => { setOpenMobile(false); setProfileModalOpen(true); }} data-testid="menu-profile">
              <UserCircle className="h-4 w-4 mr-2" />
              {t("menu.view_profile")}
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => { setOpenMobile(false); setPreferencesModalOpen(true); }} data-testid="menu-preferences">
              <Sliders className="h-4 w-4 mr-2" />
              {t("menu.preferences")}
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => { setOpenMobile(false); setPasswordModalOpen(true); }} data-testid="menu-change-password">
              <KeyRound className="h-4 w-4 mr-2" />
              {t("menu.change_password")}
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => { setOpenMobile(false); setApiKeyModalOpen(true); }} data-testid="menu-api-key">
              <Key className="h-4 w-4 mr-2" />
              {t("menu.api_key")}
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={() => { setOpenMobile(false); toggleTheme(); }} data-testid="menu-theme-toggle">
              {theme === "dark" ? (
                <Sun className="h-4 w-4 mr-2" />
              ) : (
                <Moon className="h-4 w-4 mr-2" />
              )}
              {theme === "dark" ? t("menu.light_mode") : t("menu.dark_mode")}
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={() => { setOpenMobile(false); setLogoutConfirmOpen(true); }} data-testid="menu-logout">
              <LogOut className="h-4 w-4 mr-2" />
              {t("menu.logout")}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </SidebarFooter>

      {/* Profile Modal */}
      <Dialog open={profileModalOpen} onOpenChange={setProfileModalOpen}>
        <DialogContent data-testid="dialog-profile">
          <DialogHeader>
            <DialogTitle>{t("profile.title")}</DialogTitle>
            <DialogDescription>
              {t("profile.description")}
            </DialogDescription>
          </DialogHeader>
          
          <div className="space-y-6">
            <div className="flex items-center gap-4">
              <Avatar className="h-20 w-20">
                {user?.avatar_url ? (
                  <AvatarImage src={user.avatar_url} alt={user.full_name || user?.username} />
                ) : null}
                <AvatarFallback className="bg-primary text-primary-foreground text-xl font-semibold">
                  {avatarFallback}
                </AvatarFallback>
              </Avatar>
              <div>
                <h3 className="text-lg font-semibold" data-testid="text-profile-name">{user?.full_name || user?.username}</h3>
                <p className="text-sm text-muted-foreground" data-testid="text-profile-role">{user?.role || t("profile.user")}</p>
              </div>
            </div>

            <div className="space-y-3">
              <div>
                <label className="text-sm font-medium text-muted-foreground">{t("profile.username")}</label>
                <p className="text-sm" data-testid="text-profile-username">{user?.username}</p>
              </div>
              
              <div>
                <label className="text-sm font-medium text-muted-foreground">{t("profile.email")}</label>
                <p className="text-sm" data-testid="text-profile-email">{user?.email || t("profile.not_set")}</p>
              </div>

              {user?.organization && (
                <div>
                  <label className="text-sm font-medium text-muted-foreground">{t("profile.organization")}</label>
                  <p className="text-sm" data-testid="text-profile-organization">{user.organization.name || t("profile.not_set")}</p>
                </div>
              )}
            </div>
          </div>

          <DialogFooter>
            <Button onClick={() => setProfileModalOpen(false)} data-testid="button-close-profile">
              {t("common.close")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Change Password Modal */}
      <Dialog open={passwordModalOpen} onOpenChange={setPasswordModalOpen}>
        <DialogContent data-testid="dialog-change-password">
          <DialogHeader>
            <DialogTitle>{t("password.title")}</DialogTitle>
            <DialogDescription>
              {t("password.description")}
            </DialogDescription>
          </DialogHeader>
          
          <Form {...passwordForm}>
            <form onSubmit={passwordForm.handleSubmit(handlePasswordChange)} className="space-y-4">
              <FormField
                control={passwordForm.control}
                name="current_password"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{t("password.current")}</FormLabel>
                    <FormControl>
                      <Input type="password" {...field} data-testid="input-current-password" />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={passwordForm.control}
                name="new_password"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{t("password.new")}</FormLabel>
                    <FormControl>
                      <Input type="password" {...field} data-testid="input-new-password" />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={passwordForm.control}
                name="confirm_password"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{t("password.confirm")}</FormLabel>
                    <FormControl>
                      <Input type="password" {...field} data-testid="input-confirm-password" />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <DialogFooter>
                <Button 
                  type="button" 
                  variant="outline" 
                  onClick={() => {
                    setPasswordModalOpen(false);
                    passwordForm.reset();
                  }}
                  data-testid="button-cancel-password"
                >
                  {t("common.cancel")}
                </Button>
                <Button 
                  type="submit" 
                  disabled={changePasswordMutation.isPending}
                  data-testid="button-save-password"
                >
                  {changePasswordMutation.isPending ? t("password.changing") : t("password.change")}
                </Button>
              </DialogFooter>
            </form>
          </Form>
        </DialogContent>
      </Dialog>

      {/* User Preferences Modal */}
      <Dialog open={preferencesModalOpen} onOpenChange={setPreferencesModalOpen}>
        <DialogContent data-testid="dialog-preferences">
          <DialogHeader>
            <DialogTitle>{t("preferences.title")}</DialogTitle>
            <DialogDescription>
              {t("preferences.description")}
            </DialogDescription>
          </DialogHeader>
          
          <Form {...preferencesForm}>
            <form onSubmit={preferencesForm.handleSubmit(handlePreferencesUpdate)} className="space-y-4">
              <FormField
                control={preferencesForm.control}
                name="language"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{t("preferences.language")}</FormLabel>
                    <Select onValueChange={field.onChange} value={field.value} disabled={isLocaleLoading}>
                      <FormControl>
                        <SelectTrigger data-testid="select-language">
                          <SelectValue placeholder={t("preferences.select_language")} />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value="en">English</SelectItem>
                        <SelectItem value="es">Español</SelectItem>
                        <SelectItem value="pt">Português</SelectItem>
                      </SelectContent>
                    </Select>
                    <FormDescription>{t("preferences.language_description")}</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={preferencesForm.control}
                name="timezone"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{t("preferences.timezone")}</FormLabel>
                    <Select onValueChange={field.onChange} value={field.value} disabled={isLocaleLoading}>
                      <FormControl>
                        <SelectTrigger data-testid="select-timezone">
                          <SelectValue placeholder={t("preferences.select_timezone")} />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value="UTC">UTC</SelectItem>
                        <SelectItem value="America/New_York">Eastern Time</SelectItem>
                        <SelectItem value="America/Chicago">Central Time</SelectItem>
                        <SelectItem value="America/Denver">Mountain Time</SelectItem>
                        <SelectItem value="America/Los_Angeles">Pacific Time</SelectItem>
                        <SelectItem value="America/Montevideo">Montevideo</SelectItem>
                        <SelectItem value="America/Argentina/Buenos_Aires">Buenos Aires</SelectItem>
                        <SelectItem value="America/Sao_Paulo">São Paulo</SelectItem>
                        <SelectItem value="Europe/Madrid">Madrid</SelectItem>
                      </SelectContent>
                    </Select>
                    <FormDescription>{t("preferences.timezone_description")}</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={preferencesForm.control}
                name="currency"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{t("preferences.currency")}</FormLabel>
                    <Select onValueChange={field.onChange} value={field.value} disabled={isLocaleLoading}>
                      <FormControl>
                        <SelectTrigger data-testid="select-currency">
                          <SelectValue placeholder={t("preferences.select_currency")} />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value="USD">USD</SelectItem>
                        <SelectItem value="EUR">EUR</SelectItem>
                        <SelectItem value="GBP">GBP</SelectItem>
                        <SelectItem value="UYU">UYU</SelectItem>
                        <SelectItem value="ARS">ARS</SelectItem>
                        <SelectItem value="BRL">BRL</SelectItem>
                        <SelectItem value="CLP">CLP</SelectItem>
                        <SelectItem value="MXN">MXN</SelectItem>
                      </SelectContent>
                    </Select>
                    <FormDescription>{t("preferences.currency_description")}</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <DialogFooter>
                <Button 
                  type="button" 
                  variant="outline" 
                  onClick={() => setPreferencesModalOpen(false)}
                  data-testid="button-cancel-preferences"
                >
                  {t("common.cancel")}
                </Button>
                <Button 
                  type="submit" 
                  disabled={localizationMutation.isPending}
                  data-testid="button-save-preferences"
                >
                  {localizationMutation.isPending ? t("preferences.saving") : t("preferences.save")}
                </Button>
              </DialogFooter>
            </form>
          </Form>
        </DialogContent>
      </Dialog>

      {/* API Key modal */}
      <Dialog open={apiKeyModalOpen} onOpenChange={setApiKeyModalOpen}>
        <DialogContent className="max-w-md" data-testid="dialog-api-key">
          <DialogHeader>
            <DialogTitle>{t("api_key.title")}</DialogTitle>
            <DialogDescription>
              {t("api_key.description")}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 pt-2">
            {apiKeyLoading ? (
              <>
                <Skeleton className="h-5 w-48" />
                <Skeleton className="h-4 w-full" />
              </>
            ) : apiKeyStatus ? (
              <>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-sm bg-muted px-2 py-1 rounded" data-testid="api-key-masked">
                    {apiKeyStatus.masked_key}
                  </span>
                  <Badge variant="secondary">
                    Created {formatDistanceToNow(new Date(apiKeyStatus.created_at), { addSuffix: true })}
                  </Badge>
                  {apiKeyStatus.last_used_at && (
                    <span className="text-xs text-muted-foreground">
                      Last used {formatDistanceToNow(new Date(apiKeyStatus.last_used_at), { addSuffix: true })}
                    </span>
                  )}
                </div>
                <div className="flex gap-2">
                  <Button variant="outline" size="sm" onClick={() => setRevokeConfirmOpen(true)} data-testid="button-revoke-api-key">
                    {t("api_key.revoke")}
                  </Button>
                  <Button size="sm" onClick={() => setApiKeyCreateOpen(true)} data-testid="button-create-new-api-key">
                    {t("api_key.create_new")}
                  </Button>
                </div>
              </>
            ) : (
              <>
                <p className="text-sm text-muted-foreground">{t("api_key.no_key")}</p>
                <Button onClick={() => setApiKeyCreateOpen(true)} data-testid="button-create-api-key">
                  {t("api_key.create")}
                </Button>
              </>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setApiKeyModalOpen(false)}>{t("common.close")}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Create API key — optional name */}
      <Dialog open={apiKeyCreateOpen} onOpenChange={setApiKeyCreateOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{t("api_key.create_title")}</DialogTitle>
            <DialogDescription>
              {t("api_key.create_description")}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2 py-2">
            <Label htmlFor="api-key-name">{t("api_key.name_optional")}</Label>
            <Input
              id="api-key-name"
              placeholder={t("api_key.placeholder")}
              value={apiKeyCreateName}
              onChange={(e) => setApiKeyCreateName(e.target.value)}
              data-testid="input-api-key-name"
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setApiKeyCreateOpen(false)}>{t("common.cancel")}</Button>
            <Button
              onClick={() => createKeyMutation.mutate({ name: apiKeyCreateName.trim() || undefined })}
              disabled={createKeyMutation.isPending}
              data-testid="button-confirm-create-api-key"
            >
              {createKeyMutation.isPending ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : null}
              {t("api_key.create")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* New key shown once — copy and warning */}
      <Dialog open={!!newKeyShown} onOpenChange={(open) => !open && setNewKeyShown(null)}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>{t("api_key.your_key")}</DialogTitle>
            <DialogDescription>
              {t("api_key.copy_warning")}
            </DialogDescription>
          </DialogHeader>
          {newKeyShown && (
            <div className="space-y-3">
              <div className="flex gap-2">
                <Input
                  readOnly
                  value={newKeyShown.key}
                  className="font-mono text-sm"
                  data-testid="input-new-api-key"
                />
                <Button
                  variant="outline"
                  size="icon"
                  onClick={() => {
                    navigator.clipboard.writeText(newKeyShown.key).then(
                      () => toast({ title: t("common.copied"), description: t("toast.api_key_copied") }),
                      () => toast({ title: t("toast.update_failed"), variant: "destructive" })
                    );
                  }}
                  title={t("common.copy")}
                  data-testid="button-copy-api-key"
                >
                  <Copy className="h-4 w-4" />
                </Button>
              </div>
              {newKeyShown.warning && (
                <p className="text-sm text-amber-600 dark:text-amber-500 flex items-center gap-2">
                  <AlertCircle className="h-4 w-4 shrink-0" />
                  {newKeyShown.warning}
                </p>
              )}
            </div>
          )}
          <DialogFooter>
            <Button onClick={() => setNewKeyShown(null)} data-testid="button-done-api-key">{t("common.done")}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Revoke API key confirmation */}
      <AlertDialog open={revokeConfirmOpen} onOpenChange={setRevokeConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("api_key.revoke_confirm_title")}</AlertDialogTitle>
            <AlertDialogDescription>
              {t("api_key.revoke_confirm_description")}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("common.cancel")}</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => revokeKeyMutation.mutate()}
              disabled={revokeKeyMutation.isPending}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              data-testid="button-confirm-revoke-api-key"
            >
              {revokeKeyMutation.isPending ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : null}
              {t("api_key.revoke")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Logout Confirmation */}
      <AlertDialog open={logoutConfirmOpen} onOpenChange={setLogoutConfirmOpen}>
        <AlertDialogContent data-testid="dialog-logout-confirm">
          <AlertDialogHeader>
            <AlertDialogTitle>{t("logout.confirm_title")}</AlertDialogTitle>
            <AlertDialogDescription>
              {t("logout.confirm_description")}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel data-testid="button-cancel-logout">{t("common.cancel")}</AlertDialogCancel>
            <AlertDialogAction onClick={handleLogout} data-testid="button-confirm-logout">
              {t("logout.confirm")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Sidebar>
  );
}
