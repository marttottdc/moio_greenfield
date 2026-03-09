import { useEffect, useMemo, useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Search, Plus, Edit, Trash2, Users, Building, Shield, FileText, CheckCircle, AlertTriangle, RefreshCcw } from "lucide-react";
import { PageLayout } from "@/components/layout/page-layout";
import { GlassPanel } from "@/components/radiant/glass-panel";
import { Subheading } from "@/components/radiant/text";
import { EmptyState } from "@/components/empty-state";
import { fetchJson, apiRequest, queryClient, ApiError } from "@/lib/queryClient";
import { apiV1, moioUsersApi, MOIO_USER_ROLES, type MoioUserRead, type MoioUserWriteRequest } from "@/lib/api";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Form, FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useToast } from "@/hooks/use-toast";
import { Textarea } from "@/components/ui/textarea";
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
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/contexts/AuthContext";
import { canAccessPlatformAdmin, isPlatformAdminRole, normalizeAppRole } from "@/lib/rbac";

/** User row in admin: Moio GET /api/v1/users/ shape */
type User = MoioUserRead;

interface Organization {
  id: string;
  name: string;
  timezone?: string;
  currency?: string;
  date_format?: string;
  created_at?: string;
}

interface OrganizationResponse {
  organization?: Organization;
}

interface Role {
  id: string;
  name: string;
  description: string;
  permissions: string[];
  user_count: number;
}

interface RolesResponse {
  roles?: Role[];
}

const userSchema = z.object({
  username: z.string().min(3, "Username must be at least 3 characters"),
  email: z.string().email("Invalid email"),
  full_name: z.string().min(1, "Full name is required"),
  password: z.string().min(8, "Password must be at least 8 characters").optional(),
  role: z.enum([...MOIO_USER_ROLES] as [string, ...string[]]),
});

const orgSchema = z.object({
  name: z.string().min(1, "Organization name is required"),
  timezone: z.string().optional(),
  currency: z.string().optional(),
  date_format: z.string().optional(),
});

type UserFormData = z.infer<typeof userSchema>;
type OrgFormData = z.infer<typeof orgSchema>;
type AdminTab = "users" | "organization" | "roles" | "docs";

export default function AdminConsole() {
  const { user: currentUser } = useAuth();
  const { toast } = useToast();
  const [activeTab, setActiveTab] = useState<AdminTab>("users");
  const [searchTerm, setSearchTerm] = useState("");
  const [roleFilter, setRoleFilter] = useState("all");
  const [createUserModalOpen, setCreateUserModalOpen] = useState(false);
  const [editUserModalOpen, setEditUserModalOpen] = useState(false);
  const [deleteUserConfirmOpen, setDeleteUserConfirmOpen] = useState(false);
  const [selectedUser, setSelectedUser] = useState<User | null>(null);
  const [docContent, setDocContent] = useState("");
  const [templateType, setTemplateType] = useState("guide");
  const [validationResult, setValidationResult] = useState<any | null>(null);
  const normalizedRole = normalizeAppRole(currentUser?.role);
  const isPlatformAdmin = isPlatformAdminRole(currentUser?.role);
  const canOpenPlatformAdmin = canAccessPlatformAdmin(currentUser?.role);
  const availableTabs = useMemo<AdminTab[]>(
    () => (isPlatformAdmin ? ["users", "organization", "roles", "docs"] : ["users", "organization", "roles"]),
    [isPlatformAdmin]
  );

  useEffect(() => {
    if (!availableTabs.includes(activeTab)) {
      setActiveTab(availableTabs[0]);
    }
  }, [activeTab, availableTabs]);

  const { data: usersList, isLoading: usersLoading } = useQuery<MoioUserRead[], ApiError>({
    queryKey: [apiV1("/users/"), searchTerm, roleFilter],
    queryFn: () => moioUsersApi.list(),
    enabled: canOpenPlatformAdmin && activeTab === "users",
  });

  const { data: orgData, isLoading: orgLoading } = useQuery<OrganizationResponse, ApiError>({
    queryKey: [apiV1("/settings/organization")],
    queryFn: () => fetchJson<OrganizationResponse>(apiV1("/settings/organization")),
    enabled: canOpenPlatformAdmin && activeTab === "organization",
  });

  const { data: rolesData, isLoading: rolesLoading } = useQuery<RolesResponse, ApiError>({
    queryKey: [apiV1("/settings/roles")],
    queryFn: () => fetchJson<RolesResponse>(apiV1("/settings/roles")),
    enabled: canOpenPlatformAdmin && activeTab === "roles",
  });

  const {
    data: ingestionStatus,
    isLoading: ingestionLoading,
    isFetching: ingestionFetching,
    refetch: refetchIngestion,
    dataUpdatedAt: ingestionUpdatedAt,
  } = useQuery<any, ApiError>({
    queryKey: ["/api/docs/ingestion/status/"],
    queryFn: () => fetchJson<any>("/api/docs/ingestion/status/"),
    enabled: canOpenPlatformAdmin && activeTab === "docs",
    staleTime: 10_000,
  });

  const templateMutation = useMutation({
    mutationFn: async (type: string) => fetchJson<any>("/api/docs/template/", { type }),
    onSuccess: (data) => {
      const content = (data as any)?.content || (data as any)?.template;
      setDocContent(content || "");
      toast({ description: "Template loaded" });
    },
    onError: (error: ApiError) => {
      toast({
        title: "Template load failed",
        description: error.message || "Unable to fetch template",
        variant: "destructive",
      });
    },
  });

  const validateMutation = useMutation({
    mutationFn: async (content: string) => {
      const res = await apiRequest("POST", "/api/docs/validate/", { data: { content } });
      return res.json();
    },
    onSuccess: (result) => {
      setValidationResult(result);
      toast({
        description: result?.is_valid ? "Document is valid" : "Validation completed",
        variant: result?.is_valid ? "default" : "destructive",
      });
    },
    onError: (error: ApiError) => {
      toast({
        title: "Validation failed",
        description: error.message || "Unable to validate document",
        variant: "destructive",
      });
    },
  });

  const createUserForm = useForm<UserFormData>({
    resolver: zodResolver(userSchema),
    defaultValues: {
      username: "",
      email: "",
      full_name: "",
      password: "",
      role: "member",
    },
  });

  const editUserForm = useForm<UserFormData>({
    resolver: zodResolver(userSchema.omit({ password: true })),
  });

  const orgForm = useForm<OrgFormData>({
    resolver: zodResolver(orgSchema),
    values: orgData?.organization || {
      name: "",
      timezone: "UTC",
      currency: "USD",
      date_format: "MM/DD/YYYY",
    },
  });

  const createUserMutation = useMutation({
    mutationFn: async (data: UserFormData) => {
      const parts = (data.full_name || "").trim().split(/\s+/);
      const first_name = parts[0] ?? "";
      const last_name = parts.slice(1).join(" ") ?? "";
      const payload: MoioUserWriteRequest = {
        email: data.email,
        username: data.username,
        first_name,
        last_name,
        role: data.role as MoioUserWriteRequest["role"],
        is_active: true,
      };
      if (data.password) payload.password = data.password;
      return moioUsersApi.create(payload);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [apiV1("/users/")] });
      toast({
        title: "User created",
        description: "The user has been created successfully.",
      });
      setCreateUserModalOpen(false);
      createUserForm.reset();
    },
    onError: (error: ApiError) => {
      toast({
        title: "Creation failed",
        description: error.message || "Failed to create user",
        variant: "destructive",
      });
    },
  });

  const updateUserMutation = useMutation({
    mutationFn: async ({ id, data }: { id: number; data: Partial<UserFormData> }) => {
      const payload: Partial<MoioUserWriteRequest> = {
        email: data.email,
        username: data.username,
        role: data.role as MoioUserWriteRequest["role"],
      };
      if (data.full_name !== undefined) {
        const parts = data.full_name.trim().split(/\s+/);
        payload.first_name = parts[0] ?? "";
        payload.last_name = parts.slice(1).join(" ") ?? "";
      }
      return moioUsersApi.update(id, payload);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [apiV1("/users/")] });
      toast({
        title: "User updated",
        description: "The user has been updated successfully.",
      });
      setEditUserModalOpen(false);
      setSelectedUser(null);
    },
    onError: (error: ApiError) => {
      toast({
        title: "Update failed",
        description: error.message || "Failed to update user",
        variant: "destructive",
      });
    },
  });

  const deleteUserMutation = useMutation({
    mutationFn: async (id: number) => moioUsersApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [apiV1("/users/")] });
      toast({
        title: "User deleted",
        description: "The user has been removed successfully.",
      });
      setDeleteUserConfirmOpen(false);
      setSelectedUser(null);
    },
    onError: (error: ApiError) => {
      toast({
        title: "Deletion failed",
        description: error.message || "Failed to delete user",
        variant: "destructive",
      });
    },
  });

  const updateOrgMutation = useMutation({
    mutationFn: async (data: OrgFormData) => {
      const res = await apiRequest("PATCH", apiV1("/settings/organization"), { data });
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [apiV1("/settings/organization")] });
      toast({
        title: "Organization updated",
        description: "Organization settings have been saved successfully.",
      });
    },
    onError: (error: ApiError) => {
      toast({
        title: "Update failed",
        description: error.message || "Failed to update organization",
        variant: "destructive",
      });
    },
  });

  const users = useMemo(() => {
    const list = Array.isArray(usersList) ? usersList : [];
    let filtered = list;
    if (searchTerm.trim()) {
      const term = searchTerm.trim().toLowerCase();
      filtered = filtered.filter(
        (u) =>
          u.email?.toLowerCase().includes(term) ||
          u.username?.toLowerCase().includes(term) ||
          u.full_name?.toLowerCase().includes(term)
      );
    }
    if (roleFilter !== "all") {
      filtered = filtered.filter((u) => u.role === roleFilter);
    }
    return filtered;
  }, [usersList, searchTerm, roleFilter]);

  const roles = useMemo(() => {
    return Array.isArray(rolesData?.roles) ? rolesData.roles : [];
  }, [rolesData?.roles]);

  const handleCreateUser = (data: UserFormData) => {
    createUserMutation.mutate(data);
  };

  const handleEditUser = (data: UserFormData) => {
    if (selectedUser) {
      updateUserMutation.mutate({ id: selectedUser.id, data });
    }
  };

  const handleUpdateOrg = (data: OrgFormData) => {
    updateOrgMutation.mutate(data);
  };

  const openEditUserModal = (user: User) => {
    setSelectedUser(user);
    editUserForm.reset({
      username: user.username,
      email: user.email,
      full_name: user.full_name,
      role: user.role,
    });
    setEditUserModalOpen(true);
  };

  const openDeleteUserConfirm = (user: User) => {
    setSelectedUser(user);
    setDeleteUserConfirmOpen(true);
  };

  const handleDeleteUserConfirm = () => {
    if (selectedUser) {
      deleteUserMutation.mutate(selectedUser.id);
    }
  };

  const getRoleBadgeVariant = (role: string) => {
    switch (role) {
      case "platform_admin":
        return "destructive";
      case "tenant_admin":
      case "manager":
        return "default";
      default:
        return "secondary";
    }
  };

  if (!canOpenPlatformAdmin) {
    return (
      <PageLayout
        title="Platform Admin"
        description="Administrative console for platform and tenant administrators"
        showSidebarTrigger={false}
      >
        <GlassPanel className="p-8">
          <div className="flex items-start gap-4">
            <div className="rounded-2xl bg-amber-100 p-3 text-amber-700">
              <AlertTriangle className="h-6 w-6" />
            </div>
            <div className="space-y-2">
              <h2 className="text-xl font-semibold text-slate-900">Administrative access required</h2>
              <p className="text-sm text-muted-foreground">
                This route is only available to <span className="font-mono">tenant_admin</span> and{" "}
                <span className="font-mono">platform_admin</span> users.
              </p>
              <div className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-1 text-xs text-slate-600">
                Current role
                <Badge variant="secondary">{normalizedRole}</Badge>
              </div>
            </div>
          </div>
        </GlassPanel>
      </PageLayout>
    );
  }

  return (
    <PageLayout
      title="Platform Admin"
      description={
        isPlatformAdmin
          ? "Global administration for platform users, roles, and operational tools"
          : "Tenant administration for users, tenant settings, and role visibility"
      }
      headerAction={
        <div className="flex flex-wrap items-center gap-2">
          <Button
            type="button"
            variant="outline"
            onClick={() => window.location.assign("/platform-admin/legacy")}
          >
            Legacy Platform UI
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={() => window.location.assign("/tenant-admin/legacy")}
          >
            Legacy Tenant UI
          </Button>
        </div>
      }
      showSidebarTrigger={false}
    >
      <div className="mb-6 grid gap-4 lg:grid-cols-3">
        <GlassPanel className="p-4">
          <div className="flex items-center gap-2 text-sm font-medium text-slate-600">
            <Shield className="h-4 w-4 text-[#58a6ff]" />
            Effective role
          </div>
          <div className="mt-3">
            <Badge variant={getRoleBadgeVariant(normalizedRole)}>{normalizedRole}</Badge>
          </div>
        </GlassPanel>
        <GlassPanel className="p-4 lg:col-span-2">
          <div className="flex items-center gap-2 text-sm font-medium text-slate-600">
            <Building className="h-4 w-4 text-[#58a6ff]" />
            Scope
          </div>
          <p className="mt-3 text-sm text-muted-foreground">
            {isPlatformAdmin
              ? "You are operating at platform scope. Global tools are visible and backend queries can return platform-wide objects."
              : "You are operating at tenant scope. Objects shown here are limited to the authenticated tenant."}
          </p>
        </GlassPanel>
      </div>

      <Tabs value={activeTab} onValueChange={(value) => setActiveTab(value as AdminTab)} className="space-y-6">
        <TabsList>
          {availableTabs.includes("users") ? (
            <TabsTrigger value="users" data-testid="tab-users">
              <Users className="h-4 w-4 mr-2" />
              Users
            </TabsTrigger>
          ) : null}
          {availableTabs.includes("organization") ? (
            <TabsTrigger value="organization" data-testid="tab-organization">
              <Building className="h-4 w-4 mr-2" />
              {isPlatformAdmin ? "Organization" : "Tenant"}
            </TabsTrigger>
          ) : null}
          {availableTabs.includes("roles") ? (
            <TabsTrigger value="roles" data-testid="tab-roles">
              <Shield className="h-4 w-4 mr-2" />
              Roles
            </TabsTrigger>
          ) : null}
          {availableTabs.includes("docs") ? (
            <TabsTrigger value="docs" data-testid="tab-docs">
              <FileText className="h-4 w-4 mr-2" />
              Docs
            </TabsTrigger>
          ) : null}
        </TabsList>

        <TabsContent value="users" className="space-y-6">
          <div className="flex items-center justify-between gap-4 flex-wrap">
            <div className="flex items-center gap-3 flex-1">
              <div className="relative flex-1 max-w-md">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
                <Input
                  placeholder="Search users..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="pl-10"
                  data-testid="input-search-users"
                />
              </div>
              <select
                value={roleFilter}
                onChange={(e) => setRoleFilter(e.target.value)}
                className="h-10 px-4 py-2 rounded-md border border-input bg-background text-sm hover-elevate active-elevate-2 cursor-pointer"
                data-testid="select-role-filter"
              >
                <option value="all">All Roles</option>
                {MOIO_USER_ROLES.map((r) => (
                  <option key={r} value={r}>
                    {r.replace(/_/g, " ")}
                  </option>
                ))}
              </select>
            </div>
            <Button onClick={() => setCreateUserModalOpen(true)} data-testid="button-create-user">
              <Plus className="h-4 w-4 mr-2" />
              Add User
            </Button>
          </div>

          <GlassPanel className="overflow-hidden">
            {usersLoading ? (
              <div className="p-6 space-y-4">
                {[...Array(5)].map((_, i) => (
                  <Skeleton key={i} className="h-12 w-full" />
                ))}
              </div>
            ) : users.length === 0 ? (
              <EmptyState
                title="No users found"
                description="Create a new user or adjust your search filters."
              />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-white/40 border-b border-white/60">
                    <tr>
                      <th className="text-left py-3 px-4 text-xs font-semibold uppercase tracking-wider text-[#58a6ff]">
                        User
                      </th>
                      <th className="text-left py-3 px-4 text-xs font-semibold uppercase tracking-wider text-[#58a6ff]">
                        Email
                      </th>
                      <th className="text-left py-3 px-4 text-xs font-semibold uppercase tracking-wider text-[#58a6ff]">
                        Role
                      </th>
                      <th className="text-left py-3 px-4 text-xs font-semibold uppercase tracking-wider text-[#58a6ff]">
                        Status
                      </th>
                      <th className="w-24"></th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/40 bg-white/60">
                    {users.map((user) => (
                      <tr
                        key={user.id}
                        className="hover:bg-white/80 transition-all"
                        data-testid={`row-user-${user.id}`}
                      >
                        <td className="py-3 px-4">
                          <div>
                            <div className="font-medium" data-testid={`text-fullname-${user.id}`}>
                              {user.full_name}
                            </div>
                            <div className="text-sm text-muted-foreground">@{user.username}</div>
                          </div>
                        </td>
                        <td className="py-3 px-4 text-sm text-muted-foreground">
                          {user.email}
                        </td>
                        <td className="py-3 px-4">
                          <Badge variant={getRoleBadgeVariant(user.role)} data-testid={`badge-role-${user.id}`}>
                            {user.role}
                          </Badge>
                        </td>
                        <td className="py-3 px-4">
                          <Badge
                            variant={user.is_active ? "default" : "secondary"}
                            data-testid={`badge-status-${user.id}`}
                          >
                            {user.is_active ? "Active" : "Inactive"}
                          </Badge>
                        </td>
                        <td className="py-3 px-4">
                          <div className="flex items-center gap-1">
                            <Button
                              size="icon"
                              variant="ghost"
                              onClick={() => openEditUserModal(user)}
                              data-testid={`button-edit-user-${user.id}`}
                            >
                              <Edit className="h-4 w-4" />
                            </Button>
                            <Button
                              size="icon"
                              variant="ghost"
                              onClick={() => openDeleteUserConfirm(user)}
                              data-testid={`button-delete-user-${user.id}`}
                            >
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </GlassPanel>
        </TabsContent>

        <TabsContent value="organization" className="space-y-6">
          <GlassPanel className="p-6">
              <div className="flex items-center gap-2 mb-6">
                <Building className="h-5 w-5" style={{ color: "#58a6ff" }} />
                <Subheading className="!text-base !normal-case !tracking-normal">
                  {isPlatformAdmin ? "Organization Settings" : "Tenant Settings"}
                </Subheading>
              </div>

            {orgLoading ? (
              <div className="space-y-4">
                <Skeleton className="h-10 w-full" />
                <Skeleton className="h-10 w-full" />
                <Skeleton className="h-10 w-full" />
              </div>
            ) : (
              <Form {...orgForm}>
                <form onSubmit={orgForm.handleSubmit(handleUpdateOrg)} className="space-y-6">
                  <FormField
                    control={orgForm.control}
                    name="name"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Organization Name</FormLabel>
                        <FormControl>
                          <Input {...field} data-testid="input-org-name" />
                        </FormControl>
                        <FormDescription>
                          {isPlatformAdmin
                            ? "The legal name of your organization"
                            : "The name exposed to users inside the current tenant"}
                        </FormDescription>
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  <FormField
                    control={orgForm.control}
                    name="timezone"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Timezone</FormLabel>
                        <Select onValueChange={field.onChange} value={field.value}>
                          <FormControl>
                            <SelectTrigger data-testid="select-org-timezone">
                              <SelectValue placeholder="Select timezone" />
                            </SelectTrigger>
                          </FormControl>
                          <SelectContent>
                            <SelectItem value="UTC">UTC</SelectItem>
                            <SelectItem value="America/New_York">Eastern Time</SelectItem>
                            <SelectItem value="America/Chicago">Central Time</SelectItem>
                            <SelectItem value="America/Los_Angeles">Pacific Time</SelectItem>
                            <SelectItem value="America/Montevideo">Montevideo</SelectItem>
                          </SelectContent>
                        </Select>
                        <FormDescription>Default timezone for the organization</FormDescription>
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  <FormField
                    control={orgForm.control}
                    name="currency"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Currency</FormLabel>
                        <Select onValueChange={field.onChange} value={field.value}>
                          <FormControl>
                            <SelectTrigger data-testid="select-org-currency">
                              <SelectValue placeholder="Select currency" />
                            </SelectTrigger>
                          </FormControl>
                          <SelectContent>
                            <SelectItem value="USD">USD - US Dollar</SelectItem>
                            <SelectItem value="EUR">EUR - Euro</SelectItem>
                            <SelectItem value="UYU">UYU - Uruguayan Peso</SelectItem>
                            <SelectItem value="ARS">ARS - Argentine Peso</SelectItem>
                          </SelectContent>
                        </Select>
                        <FormDescription>Default currency for transactions</FormDescription>
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  <Button
                    type="submit"
                    disabled={updateOrgMutation.isPending}
                    data-testid="button-save-org"
                  >
                    {updateOrgMutation.isPending ? "Saving..." : "Save Changes"}
                  </Button>
                </form>
              </Form>
            )}
          </GlassPanel>
        </TabsContent>

        <TabsContent value="roles" className="space-y-6">
          <GlassPanel className="p-6">
              <div className="flex items-center gap-2 mb-6">
                <Shield className="h-5 w-5" style={{ color: "#58a6ff" }} />
                <Subheading className="!text-base !normal-case !tracking-normal">
                  {isPlatformAdmin ? "Roles & Permissions" : "Tenant Roles"}
                </Subheading>
              </div>

            {rolesLoading ? (
              <div className="space-y-4">
                {[...Array(4)].map((_, i) => (
                  <Skeleton key={i} className="h-24 w-full" />
                ))}
              </div>
            ) : roles.length === 0 ? (
              <EmptyState
                title="No roles found"
                description="Unable to load roles from the backend."
              />
            ) : (
              <div className="space-y-4">
                {roles.map((role) => (
                  <GlassPanel key={role.id} className="p-4" data-testid={`card-role-${role.id}`}>
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <div className="flex items-center gap-3 mb-2">
                          <h3 className="font-semibold text-base">{role.name}</h3>
                          <Badge variant="secondary" data-testid={`badge-users-${role.id}`}>
                            {role.user_count} {role.user_count === 1 ? "user" : "users"}
                          </Badge>
                        </div>
                        <p className="text-sm text-muted-foreground mb-3">{role.description}</p>
                        <div className="flex flex-wrap gap-2">
                          {role.permissions.slice(0, 5).map((permission, idx) => (
                            <Badge key={idx} variant="outline" className="text-xs">
                              {permission}
                            </Badge>
                          ))}
                          {role.permissions.length > 5 && (
                            <Badge variant="outline" className="text-xs">
                              +{role.permissions.length - 5} more
                            </Badge>
                          )}
                        </div>
                      </div>
                    </div>
                  </GlassPanel>
                ))}
              </div>
            )}
          </GlassPanel>
        </TabsContent>

        <TabsContent value="docs" className="space-y-6">
          <GlassPanel className="p-6 space-y-4">
            <div className="flex items-center justify-between gap-3 flex-wrap">
              <div className="flex items-center gap-2">
                <FileText className="h-5 w-5" style={{ color: "#58a6ff" }} />
                <Subheading className="!text-base !normal-case !tracking-normal">
                  Docs ingestion status
                </Subheading>
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={() => refetchIngestion()}
                disabled={ingestionFetching}
                data-testid="button-refresh-ingestion"
              >
                <RefreshCcw className={`h-4 w-4 mr-2 ${ingestionFetching ? "animate-spin" : ""}`} />
                Refresh
              </Button>
            </div>

            {ingestionLoading ? (
              <div className="space-y-2 text-muted-foreground">Loading ingestion status…</div>
            ) : ingestionStatus ? (
              <div className="space-y-4">
                <div className="text-sm text-muted-foreground">
                  Last updated:{" "}
                  {ingestionUpdatedAt
                    ? new Date(ingestionUpdatedAt).toLocaleString()
                    : "Just now"}
                </div>
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  <GlassPanel className="p-3">
                    <p className="text-xs uppercase text-muted-foreground">Source dir</p>
                    <p className="font-mono text-sm">{ingestionStatus.source_dir || "—"}</p>
                  </GlassPanel>
                  <GlassPanel className="p-3">
                    <p className="text-xs uppercase text-muted-foreground">Folder files</p>
                    <p className="text-lg font-semibold">{ingestionStatus.folder_files ?? "0"}</p>
                  </GlassPanel>
                  <GlassPanel className="p-3">
                    <p className="text-xs uppercase text-muted-foreground">DB guides</p>
                    <p className="text-lg font-semibold">{ingestionStatus.db_guides ?? "0"}</p>
                  </GlassPanel>
                  <GlassPanel className="p-3">
                    <p className="text-xs uppercase text-muted-foreground">DB published</p>
                    <p className="text-lg font-semibold">{ingestionStatus.db_published ?? "0"}</p>
                  </GlassPanel>
                </div>
                <div className="rounded-lg border border-white/40 bg-white/40 p-3 text-xs text-muted-foreground">
                  <pre className="whitespace-pre-wrap break-words">
                    {JSON.stringify(ingestionStatus, null, 2)}
                  </pre>
                </div>
              </div>
            ) : (
              <EmptyState
                title="No status available"
                description="The ingestion service did not return data."
              />
            )}
          </GlassPanel>

          <GlassPanel className="p-6 space-y-4">
            <div className="flex items-center justify-between gap-3 flex-wrap">
              <div className="flex items-center gap-2">
                <CheckCircle className="h-5 w-5" style={{ color: "#58a6ff" }} />
                <Subheading className="!text-base !normal-case !tracking-normal">
                  Validate documentation content
                </Subheading>
              </div>
              <div className="flex items-center gap-2">
                <Select value={templateType} onValueChange={setTemplateType}>
                  <SelectTrigger className="w-[180px]" data-testid="select-template-type">
                    <SelectValue placeholder="Template type" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="guide">Guide</SelectItem>
                    <SelectItem value="tutorial">Tutorial</SelectItem>
                    <SelectItem value="reference">Reference</SelectItem>
                    <SelectItem value="concept">Concept</SelectItem>
                  </SelectContent>
                </Select>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => templateMutation.mutate(templateType)}
                  disabled={templateMutation.isPending}
                  data-testid="button-load-template"
                >
                  {templateMutation.isPending ? "Loading..." : "Load template"}
                </Button>
              </div>
            </div>

            <Textarea
              value={docContent}
              onChange={(e) => setDocContent(e.target.value)}
              rows={14}
              placeholder="Paste markdown (with frontmatter) to validate or load a template."
              className="font-mono text-sm"
              data-testid="textarea-doc-content"
            />

            <div className="flex items-center gap-2 flex-wrap">
              <Button
                onClick={() => validateMutation.mutate(docContent)}
                disabled={!docContent.trim() || validateMutation.isPending}
                data-testid="button-validate-doc"
              >
                {validateMutation.isPending ? "Validating..." : "Validate"}
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setDocContent("");
                  setValidationResult(null);
                }}
                data-testid="button-clear-doc"
              >
                Clear
              </Button>
              {validationResult && (
                <Badge variant={validationResult.valid ? "default" : "destructive"}>
                  {validationResult.valid ? "Valid" : "Invalid"}
                </Badge>
              )}
            </div>

            {validationResult && (
              <div className="space-y-3">
                {validationResult.errors?.length ? (
                  <div className="rounded border border-rose-200 bg-rose-50 p-3 text-rose-800 space-y-1">
                    <div className="flex items-center gap-2 font-semibold">
                      <AlertTriangle className="h-4 w-4" />
                      Errors
                    </div>
                    <ul className="list-disc pl-4 text-sm">
                      {validationResult.errors.map((err: any, idx: number) => (
                        <li key={idx}>{typeof err === "string" ? err : JSON.stringify(err)}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}

                {validationResult.warnings?.length ? (
                  <div className="rounded border border-amber-200 bg-amber-50 p-3 text-amber-900 space-y-1">
                    <div className="flex items-center gap-2 font-semibold">
                      <AlertTriangle className="h-4 w-4" />
                      Warnings
                    </div>
                    <ul className="list-disc pl-4 text-sm">
                      {validationResult.warnings.map((warn: any, idx: number) => (
                        <li key={idx}>{typeof warn === "string" ? warn : JSON.stringify(warn)}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}

                {validationResult.frontmatter && (
                  <div className="rounded border border-slate-200 bg-slate-50 p-3 text-slate-900">
                    <p className="text-sm font-semibold mb-2">Parsed frontmatter</p>
                    <pre className="text-xs overflow-x-auto">
                      {JSON.stringify(validationResult.frontmatter, null, 2)}
                    </pre>
                  </div>
                )}
              </div>
            )}
          </GlassPanel>
        </TabsContent>
      </Tabs>

      {/* Create User Modal */}
      <Dialog open={createUserModalOpen} onOpenChange={setCreateUserModalOpen}>
        <DialogContent data-testid="dialog-create-user">
          <DialogHeader>
            <DialogTitle>Create New User</DialogTitle>
            <DialogDescription>
              Add a new user to your organization
            </DialogDescription>
          </DialogHeader>

          <Form {...createUserForm}>
            <form onSubmit={createUserForm.handleSubmit(handleCreateUser)} className="space-y-4">
              <FormField
                control={createUserForm.control}
                name="full_name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Full Name</FormLabel>
                    <FormControl>
                      <Input {...field} data-testid="input-user-fullname" />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={createUserForm.control}
                name="username"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Username</FormLabel>
                    <FormControl>
                      <Input {...field} data-testid="input-user-username" />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={createUserForm.control}
                name="email"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Email</FormLabel>
                    <FormControl>
                      <Input type="email" {...field} data-testid="input-user-email" />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={createUserForm.control}
                name="password"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Password</FormLabel>
                    <FormControl>
                      <Input type="password" autoComplete="off" {...field} data-testid="input-user-password" />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={createUserForm.control}
                name="role"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Role</FormLabel>
                    <Select onValueChange={field.onChange} value={field.value}>
                      <FormControl>
                        <SelectTrigger data-testid="select-user-role">
                          <SelectValue placeholder="Select role" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {MOIO_USER_ROLES.map((r) => (
                          <SelectItem key={r} value={r}>
                            {r.replace(/_/g, " ")}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <DialogFooter>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setCreateUserModalOpen(false)}
                  data-testid="button-cancel-create-user"
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  disabled={createUserMutation.isPending}
                  data-testid="button-save-user"
                >
                  {createUserMutation.isPending ? "Creating..." : "Create User"}
                </Button>
              </DialogFooter>
            </form>
          </Form>
        </DialogContent>
      </Dialog>

      {/* Edit User Modal */}
      <Dialog open={editUserModalOpen} onOpenChange={setEditUserModalOpen}>
        <DialogContent data-testid="dialog-edit-user">
          <DialogHeader>
            <DialogTitle>Edit User</DialogTitle>
            <DialogDescription>
              Update user information and role
            </DialogDescription>
          </DialogHeader>

          <Form {...editUserForm}>
            <form onSubmit={editUserForm.handleSubmit(handleEditUser)} className="space-y-4">
              <FormField
                control={editUserForm.control}
                name="full_name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Full Name</FormLabel>
                    <FormControl>
                      <Input {...field} data-testid="input-edit-fullname" />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={editUserForm.control}
                name="email"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Email</FormLabel>
                    <FormControl>
                      <Input type="email" {...field} data-testid="input-edit-email" />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={editUserForm.control}
                name="role"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Role</FormLabel>
                    <Select onValueChange={field.onChange} value={field.value}>
                      <FormControl>
                        <SelectTrigger data-testid="select-edit-role">
                          <SelectValue placeholder="Select role" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {MOIO_USER_ROLES.map((r) => (
                          <SelectItem key={r} value={r}>
                            {r.replace(/_/g, " ")}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <DialogFooter>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setEditUserModalOpen(false)}
                  data-testid="button-cancel-edit-user"
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  disabled={updateUserMutation.isPending}
                  data-testid="button-update-user"
                >
                  {updateUserMutation.isPending ? "Updating..." : "Update User"}
                </Button>
              </DialogFooter>
            </form>
          </Form>
        </DialogContent>
      </Dialog>

      {/* Delete User Confirmation */}
      <AlertDialog open={deleteUserConfirmOpen} onOpenChange={setDeleteUserConfirmOpen}>
        <AlertDialogContent data-testid="dialog-delete-user-confirm">
          <AlertDialogHeader>
            <AlertDialogTitle>Delete User</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to deactivate {selectedUser?.full_name}? They will no longer be able to access the system.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel data-testid="button-cancel-delete-user">Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDeleteUserConfirm}
              data-testid="button-confirm-delete-user"
            >
              {deleteUserMutation.isPending ? "Deleting..." : "Deactivate"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </PageLayout>
  );
}
