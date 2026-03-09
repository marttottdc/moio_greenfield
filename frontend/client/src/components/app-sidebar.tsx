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
} from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
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
import { isPlatformAdminRole, isTenantAdminRole } from "@/lib/rbac";

interface OrganizationSummary {
  id?: string;
  name?: string | null;
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
};


const passwordChangeSchema = z.object({
  current_password: z.string().min(1, "Current password is required"),
  new_password: z.string().min(8, "Password must be at least 8 characters"),
  confirm_password: z.string().min(1, "Please confirm your password"),
}).refine((data) => data.new_password === data.confirm_password, {
  message: "Passwords don't match",
  path: ["confirm_password"],
});

const userPreferencesSchema = z.object({
  language: z.string().optional(),
  timezone: z.string().optional(),
  notifications_enabled: z.boolean().optional(),
  email_notifications: z.boolean().optional(),
});

interface UserPreferences {
  language?: string;
  timezone?: string;
  notifications_enabled?: boolean;
  email_notifications?: boolean;
}

export function AppSidebar() {
  const [location] = useLocation();
  const { logout } = useAuth();
  const { toast } = useToast();
  const { open: sidebarOpen, toggleSidebar } = useSidebar();
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
  const preferencesPath = apiV1("/settings/preferences/");

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
    if (navigationData?.items && navigationData.items.length > 0) {
      const mapped = navigationData.items
        .filter((node) => {
          if (node.feature_enabled === false) return false;
          if (node.requires_role && node.requires_role.length > 0 && user?.role) {
            return node.requires_role.includes(user.role);
          }
          return node.url != null;
        })
        .map((node) => ({
          title: node.label,
          url: node.url || "#",
          icon: node.icon ? iconMap[node.icon] || LayoutDashboard : LayoutDashboard,
        }));

      // Keep left sidebar flat (consistent with the rest of the app).
      // Data Lab should land on Datasets.
      return mapped.map((item) =>
        item.title.toLowerCase() === "data lab" ? { ...item, url: "/datalab" } : item
      );
    }

    const items: MenuItem[] = [
      { title: "Dashboard", url: "/dashboard", icon: LayoutDashboard },
      { title: "CRM", url: "/crm", icon: Users },
      { title: "Deals", url: "/deals", icon: Briefcase },
      { title: "Activities", url: "/activities", icon: CheckSquare },
      { title: "Communications", url: "/communications", icon: MessageSquare },
      { title: "Tickets", url: "/tickets", icon: Ticket },
      { title: "Automation Studio", url: "/workflows", icon: Workflow },
      { title: "Data Lab", url: "/datalab", icon: Database },
    ];

    const userRole = user?.role;

    if (isTenantAdminRole(userRole)) {
      items.push({ title: "Settings", url: "/settings", icon: Settings });
    }

    if (isTenantAdminRole(userRole)) {
      items.push({ title: "Platform Admin", url: "/platform-admin", icon: Shield });
    }

    if (isPlatformAdminRole(userRole)) {
      items.push({ title: "API Tester", url: "/api-tester", icon: Sliders });
    }

    return items;
  }, [navigationData, user]);

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
      toast({ title: "API key created", description: "Copy and store it securely — it won't be shown again." });
    },
    onError: (err: ApiError) => {
      toast({ title: "Failed to create API key", description: err.message, variant: "destructive" });
    },
  });

  const revokeKeyMutation = useMutation({
    mutationFn: revokeApiKey,
    onSuccess: () => {
      setRevokeConfirmOpen(false);
      queryClient.invalidateQueries({ queryKey: ["auth", "api-key"] });
      toast({ title: "API key revoked" });
    },
    onError: (err: ApiError) => {
      toast({ title: "Failed to revoke API key", description: err.message, variant: "destructive" });
    },
  });

  const { data: userPreferences } = useQuery<UserPreferences, ApiError>({
    queryKey: [preferencesPath],
    queryFn: () => fetchJson<UserPreferences>(preferencesPath),
    retry: false,
  });

  const passwordForm = useForm<z.infer<typeof passwordChangeSchema>>({
    resolver: zodResolver(passwordChangeSchema),
    defaultValues: {
      current_password: "",
      new_password: "",
      confirm_password: "",
    },
  });

  const preferencesForm = useForm<z.infer<typeof userPreferencesSchema>>({
    resolver: zodResolver(userPreferencesSchema),
    values: userPreferences || {
      language: "en",
      timezone: "UTC",
      notifications_enabled: true,
      email_notifications: true,
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
        title: "Password changed",
        description: "Your password has been updated successfully.",
      });
      setPasswordModalOpen(false);
      passwordForm.reset();
    },
    onError: (error: ApiError) => {
      toast({
        title: "Password change failed",
        description: error.message || "Failed to update password",
        variant: "destructive",
      });
    },
  });

  const updatePreferencesMutation = useMutation({
    mutationFn: async (data: z.infer<typeof userPreferencesSchema>) => {
      const res = await apiRequest("PATCH", preferencesPath, { data });
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [preferencesPath] });
      toast({
        title: "Preferences updated",
        description: "Your preferences have been saved successfully.",
      });
      setPreferencesModalOpen(false);
    },
    onError: (error: ApiError) => {
      toast({
        title: "Update failed",
        description: error.message || "Failed to update preferences",
        variant: "destructive",
      });
    },
  });

  const handlePasswordChange = (data: z.infer<typeof passwordChangeSchema>) => {
    changePasswordMutation.mutate(data);
  };

  const handlePreferencesUpdate = (data: z.infer<typeof userPreferencesSchema>) => {
    updatePreferencesMutation.mutate(data);
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
                      <Link href={item.url} className="group-data-[collapsible=icon]:justify-center">
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
              {sidebarOpen ? "Collapse sidebar" : "Expand sidebar"}
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
            <DropdownMenuItem onClick={() => setProfileModalOpen(true)} data-testid="menu-profile">
              <UserCircle className="h-4 w-4 mr-2" />
              View Profile
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => setPreferencesModalOpen(true)} data-testid="menu-preferences">
              <Sliders className="h-4 w-4 mr-2" />
              Preferences
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => setPasswordModalOpen(true)} data-testid="menu-change-password">
              <KeyRound className="h-4 w-4 mr-2" />
              Change Password
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => setApiKeyModalOpen(true)} data-testid="menu-api-key">
              <Key className="h-4 w-4 mr-2" />
              API Key
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={toggleTheme} data-testid="menu-theme-toggle">
              {theme === "dark" ? (
                <Sun className="h-4 w-4 mr-2" />
              ) : (
                <Moon className="h-4 w-4 mr-2" />
              )}
              {theme === "dark" ? "Light Mode" : "Dark Mode"}
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={() => setLogoutConfirmOpen(true)} data-testid="menu-logout">
              <LogOut className="h-4 w-4 mr-2" />
              Logout
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </SidebarFooter>

      {/* Profile Modal */}
      <Dialog open={profileModalOpen} onOpenChange={setProfileModalOpen}>
        <DialogContent data-testid="dialog-profile">
          <DialogHeader>
            <DialogTitle>Profile Information</DialogTitle>
            <DialogDescription>
              View your account details and organization information
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
                <p className="text-sm text-muted-foreground" data-testid="text-profile-role">{user?.role || "User"}</p>
              </div>
            </div>

            <div className="space-y-3">
              <div>
                <label className="text-sm font-medium text-muted-foreground">Username</label>
                <p className="text-sm" data-testid="text-profile-username">{user?.username}</p>
              </div>
              
              <div>
                <label className="text-sm font-medium text-muted-foreground">Email</label>
                <p className="text-sm" data-testid="text-profile-email">{user?.email || "Not set"}</p>
              </div>

              {user?.organization && (
                <div>
                  <label className="text-sm font-medium text-muted-foreground">Organization</label>
                  <p className="text-sm" data-testid="text-profile-organization">{user.organization.name || "Not set"}</p>
                </div>
              )}
            </div>
          </div>

          <DialogFooter>
            <Button onClick={() => setProfileModalOpen(false)} data-testid="button-close-profile">
              Close
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Change Password Modal */}
      <Dialog open={passwordModalOpen} onOpenChange={setPasswordModalOpen}>
        <DialogContent data-testid="dialog-change-password">
          <DialogHeader>
            <DialogTitle>Change Password</DialogTitle>
            <DialogDescription>
              Update your account password
            </DialogDescription>
          </DialogHeader>
          
          <Form {...passwordForm}>
            <form onSubmit={passwordForm.handleSubmit(handlePasswordChange)} className="space-y-4">
              <FormField
                control={passwordForm.control}
                name="current_password"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Current Password</FormLabel>
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
                    <FormLabel>New Password</FormLabel>
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
                    <FormLabel>Confirm Password</FormLabel>
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
                  Cancel
                </Button>
                <Button 
                  type="submit" 
                  disabled={changePasswordMutation.isPending}
                  data-testid="button-save-password"
                >
                  {changePasswordMutation.isPending ? "Changing..." : "Change Password"}
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
            <DialogTitle>Personal Preferences</DialogTitle>
            <DialogDescription>
              Customize your personal language, timezone, and notification settings
            </DialogDescription>
          </DialogHeader>
          
          <Form {...preferencesForm}>
            <form onSubmit={preferencesForm.handleSubmit(handlePreferencesUpdate)} className="space-y-4">
              <FormField
                control={preferencesForm.control}
                name="language"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Language</FormLabel>
                    <Select onValueChange={field.onChange} value={field.value}>
                      <FormControl>
                        <SelectTrigger data-testid="select-language">
                          <SelectValue placeholder="Select language" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value="en">English</SelectItem>
                        <SelectItem value="es">Español</SelectItem>
                        <SelectItem value="pt">Português</SelectItem>
                      </SelectContent>
                    </Select>
                    <FormDescription>Your preferred language</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={preferencesForm.control}
                name="timezone"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Timezone</FormLabel>
                    <Select onValueChange={field.onChange} value={field.value}>
                      <FormControl>
                        <SelectTrigger data-testid="select-timezone">
                          <SelectValue placeholder="Select timezone" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value="UTC">UTC</SelectItem>
                        <SelectItem value="America/New_York">Eastern Time</SelectItem>
                        <SelectItem value="America/Chicago">Central Time</SelectItem>
                        <SelectItem value="America/Denver">Mountain Time</SelectItem>
                        <SelectItem value="America/Los_Angeles">Pacific Time</SelectItem>
                        <SelectItem value="America/Montevideo">Montevideo</SelectItem>
                      </SelectContent>
                    </Select>
                    <FormDescription>Your local timezone</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={preferencesForm.control}
                name="notifications_enabled"
                render={({ field }) => (
                  <FormItem className="flex items-center justify-between rounded-lg border p-4">
                    <div className="space-y-0.5">
                      <FormLabel className="text-base">Push Notifications</FormLabel>
                      <FormDescription>
                        Receive push notifications for important updates
                      </FormDescription>
                    </div>
                    <FormControl>
                      <Switch
                        checked={field.value}
                        onCheckedChange={field.onChange}
                        data-testid="switch-notifications"
                      />
                    </FormControl>
                  </FormItem>
                )}
              />

              <FormField
                control={preferencesForm.control}
                name="email_notifications"
                render={({ field }) => (
                  <FormItem className="flex items-center justify-between rounded-lg border p-4">
                    <div className="space-y-0.5">
                      <FormLabel className="text-base">Email Notifications</FormLabel>
                      <FormDescription>
                        Receive email notifications for activity
                      </FormDescription>
                    </div>
                    <FormControl>
                      <Switch
                        checked={field.value}
                        onCheckedChange={field.onChange}
                        data-testid="switch-email-notifications"
                      />
                    </FormControl>
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
                  Cancel
                </Button>
                <Button 
                  type="submit" 
                  disabled={updatePreferencesMutation.isPending}
                  data-testid="button-save-preferences"
                >
                  {updatePreferencesMutation.isPending ? "Saving..." : "Save Preferences"}
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
            <DialogTitle>API Key</DialogTitle>
            <DialogDescription>
              Use your API key for external API access. Manage it here with your login session.
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
                    Revoke
                  </Button>
                  <Button size="sm" onClick={() => setApiKeyCreateOpen(true)} data-testid="button-create-new-api-key">
                    Create new key
                  </Button>
                </div>
              </>
            ) : (
              <>
                <p className="text-sm text-muted-foreground">No API key. Create one to use the API with external tools.</p>
                <Button onClick={() => setApiKeyCreateOpen(true)} data-testid="button-create-api-key">
                  Create API key
                </Button>
              </>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setApiKeyModalOpen(false)}>Close</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Create API key — optional name */}
      <Dialog open={apiKeyCreateOpen} onOpenChange={setApiKeyCreateOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Create API key</DialogTitle>
            <DialogDescription>
              Creating a new key will revoke your current key. Optional: give this key a name (e.g. &quot;My Integration&quot;).
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2 py-2">
            <Label htmlFor="api-key-name">Name (optional)</Label>
            <Input
              id="api-key-name"
              placeholder="My Integration"
              value={apiKeyCreateName}
              onChange={(e) => setApiKeyCreateName(e.target.value)}
              data-testid="input-api-key-name"
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setApiKeyCreateOpen(false)}>Cancel</Button>
            <Button
              onClick={() => createKeyMutation.mutate({ name: apiKeyCreateName.trim() || undefined })}
              disabled={createKeyMutation.isPending}
              data-testid="button-confirm-create-api-key"
            >
              {createKeyMutation.isPending ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : null}
              Generate key
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* New key shown once — copy and warning */}
      <Dialog open={!!newKeyShown} onOpenChange={(open) => !open && setNewKeyShown(null)}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Your API key</DialogTitle>
            <DialogDescription>
              Copy this key now. It will not be shown again.
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
                      () => toast({ title: "Copied", description: "API key copied to clipboard." }),
                      () => toast({ title: "Copy failed", variant: "destructive" })
                    );
                  }}
                  title="Copy"
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
            <Button onClick={() => setNewKeyShown(null)} data-testid="button-done-api-key">Done</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Revoke API key confirmation */}
      <AlertDialog open={revokeConfirmOpen} onOpenChange={setRevokeConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Revoke API key?</AlertDialogTitle>
            <AlertDialogDescription>
              Your current API key will stop working immediately. You can create a new key afterward.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => revokeKeyMutation.mutate()}
              disabled={revokeKeyMutation.isPending}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              data-testid="button-confirm-revoke-api-key"
            >
              {revokeKeyMutation.isPending ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : null}
              Revoke
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Logout Confirmation */}
      <AlertDialog open={logoutConfirmOpen} onOpenChange={setLogoutConfirmOpen}>
        <AlertDialogContent data-testid="dialog-logout-confirm">
          <AlertDialogHeader>
            <AlertDialogTitle>Confirm Logout</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to logout? You'll need to sign in again to access your account.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel data-testid="button-cancel-logout">Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleLogout} data-testid="button-confirm-logout">
              Logout
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Sidebar>
  );
}
