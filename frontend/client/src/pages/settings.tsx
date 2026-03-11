import { useMemo, useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import type { ComponentType, CSSProperties } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { formatDistanceToNow } from "date-fns";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/empty-state";
import { ErrorDisplay } from "@/components/error-display";
import { Mail, CheckCircle2, Plug, Eye, EyeOff, AlertCircle, Loader2, RefreshCw, Shield } from "lucide-react";
import { SiSlack, SiWordpress, SiOpenai, SiWhatsapp, SiTelegram, SiInstagram, SiGoogle } from "react-icons/si";
import { PageLayout } from "@/components/layout/page-layout";
import { GlassPanel } from "@/components/radiant/glass-panel";
import { Skeleton } from "@/components/ui/skeleton";
import { fetchJson, ApiError, apiRequest, queryClient } from "@/lib/queryClient";
import { apiV1 } from "@/lib/api";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useToast } from "@/hooks/use-toast";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select, SelectTrigger, SelectContent, SelectItem, SelectValue } from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { emailApi } from "@/lib/integrations/emailApi";
import { calendarApi } from "@/lib/integrations/calendarApi";
import type { EmailAccount, CalendarAccount } from "@/lib/integrations/types";
import { isTenantAdminRole } from "@/lib/rbac";

type IconComponent = ComponentType<{ className?: string; style?: CSSProperties }>;

interface IntegrationConfigField {
  name: string;
  label?: string;
  type: string;
  required?: boolean;
  sensitive?: boolean;
  default?: unknown;
  placeholder?: string;
  description?: string;
}

interface IntegrationCard {
  slug: string;
  name: string;
  description: string | null;
  category: string;
  icon: string;
  supports_multi_instance: boolean;
  is_configured: boolean;
  enabled: boolean;
  instance_count: number;
  connection_status?: "connected" | "configured" | "not_configured";
  config?: Record<string, unknown>;
}

interface Integration {
  id: string;
  slug: string;
  instance_id: string;
  name: string;
  enabled: boolean;
  config: Record<string, unknown>;
  metadata: Record<string, unknown>;
  integration_name: string;
  integration_category: string;
  is_configured: boolean;
  supports_multi_instance: boolean;
  created_at: string;
  updated_at: string;
  available_models?: { id: string; created?: number }[];
}

interface IntegrationSchema {
  fields: IntegrationConfigField[];
}

type IntegrationsResponse = IntegrationCard[];

interface IntegrationDisplayConfig {
  icon: IconComponent;
  color: string;
  bgColor: string;
}

const integrationDisplayMap: Record<string, IntegrationDisplayConfig> = {
  gmail: { icon: Mail, color: "#ff6b6b", bgColor: "rgba(255, 107, 107, 0.1)" },
  slack: { icon: SiSlack, color: "#58a6ff", bgColor: "rgba(88, 166, 255, 0.1)" },
  wordpress: { icon: SiWordpress, color: "#58a6ff", bgColor: "rgba(88, 166, 255, 0.1)" },
  openai: { icon: SiOpenai, color: "#74c365", bgColor: "rgba(116, 195, 101, 0.1)" },
  "google-maps": { icon: SiGoogle, color: "#58a6ff", bgColor: "rgba(88, 166, 255, 0.1)" },
  "google_maps": { icon: SiGoogle, color: "#58a6ff", bgColor: "rgba(88, 166, 255, 0.1)" },
  whatsapp: { icon: SiWhatsapp, color: "#74c365", bgColor: "rgba(116, 195, 101, 0.1)" },
  telegram: { icon: SiTelegram, color: "#58a6ff", bgColor: "rgba(88, 166, 255, 0.1)" },
  instagram: { icon: SiInstagram, color: "#ff6b6b", bgColor: "rgba(255, 107, 107, 0.1)" },
};

const defaultIntegrationDisplay: IntegrationDisplayConfig = {
  icon: Plug,
  color: "#58a6ff",
  bgColor: "rgba(88, 166, 255, 0.12)",
};

function resolveDisplayConfig(id: string) {
  return integrationDisplayMap[id] ?? integrationDisplayMap[id.replace(/-/g, "_")] ?? integrationDisplayMap[id.replace(/_/g, "-")] ?? defaultIntegrationDisplay;
}

function formatLastSync(lastSync?: string | null) {
  if (!lastSync) {
    return null;
  }

  const parsed = new Date(lastSync);
  if (Number.isNaN(parsed.getTime())) {
    return null;
  }

  try {
    return formatDistanceToNow(parsed, { addSuffix: true });
  } catch {
    return null;
  }
}

const integrationSkeletons = Array.from({ length: 6 });

type ProviderOption = "google" | "microsoft" | "imap";

interface CombinedAccount {
  external: EmailAccount["external_account"];
  email?: EmailAccount;
  calendar?: CalendarAccount;
}

interface AuthenticatedUser {
  role?: string | null;
}

function IntegrationConfigModal({
  integration,
  open,
  onOpenChange,
}: {
  integration: IntegrationCard | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { toast } = useToast();
  const [configValues, setConfigValues] = useState<Record<string, unknown>>({});
  const [showPasswords, setShowPasswords] = useState<Record<string, boolean>>({});
  const [activeTab, setActiveTab] = useState("config");
  const [openaiModels, setOpenaiModels] = useState<{ id: string }[]>([]);
  const [debouncedApiKey, setDebouncedApiKey] = useState<string>("");
  const [embeddedSession, setEmbeddedSession] = useState<{
    waba_id?: string;
    phone_number_id?: string;
    verified_name?: string;
    display_phone_number?: string;
  } | null>(null);
  const [fbReady, setFbReady] = useState(false);
  const [isLaunching, setIsLaunching] = useState(false);
  const [embeddedStatus, setEmbeddedStatus] = useState<string | null>(null);

  const slug = integration?.slug ?? "";
  const slugLower = slug.toLowerCase();
  const nameLower = (integration?.name ?? "").toLowerCase();
  // Some tenants use slugs like `wa_business` / `wa-cloud` instead of `whatsapp`.
  const isWhatsapp =
    slugLower.includes("whatsapp") ||
    nameLower.includes("whatsapp") ||
    /(^|[_-])wa($|[_-])/.test(slugLower) ||
    slugLower.startsWith("wa_");

  const schemaQuery = useQuery<IntegrationSchema>({
    queryKey: [apiV1(`/integrations/${slug}/schema/`)],
    queryFn: () => fetchJson<IntegrationSchema>(apiV1(`/integrations/${slug}/schema/`)),
    enabled: open && !!slug,
  });

  const configQuery = useQuery<Integration[]>({
    queryKey: [apiV1(`/integrations/${slug}/`)],
    queryFn: () => fetchJson<Integration[]>(apiV1(`/integrations/${slug}/`)),
    enabled: open && !!slug,
    staleTime: 0,
    refetchOnMount: "always",
  });

  const embeddedConfigQuery = useQuery({
    queryKey: ["wa-embedded-config"],
    enabled: open && isWhatsapp,
    queryFn: () => fetchJson<any>(apiV1("/integrations/whatsapp/embedded-signup/config/")),
  });

  const detailData = configQuery.data?.[0];

  const configSchema = useMemo(() => {
    return schemaQuery.data?.fields ?? [];
  }, [schemaQuery.data?.fields]);

  const canShowEmbeddedSignup = useMemo(() => {
    if (isWhatsapp) return true;
    const names = new Set(configSchema.map((f) => String(f.name || "").toLowerCase()));
    return names.has("phone_id") && names.has("business_account_id");
  }, [isWhatsapp, configSchema]);

  useEffect(() => {
    const defaults: Record<string, unknown> = {};
    configSchema.forEach((field) => {
      if (field.type === "boolean") {
        defaults[field.name] = field.default ?? false;
      } else {
        defaults[field.name] = field.default ?? "";
      }
    });
    const existingConfig = detailData?.config ?? integration?.config;
    if (existingConfig && Object.keys(existingConfig).length > 0) {
      setConfigValues({ ...defaults, ...existingConfig });
    } else if (configSchema.length > 0) {
      setConfigValues(defaults);
    }
    setShowPasswords({});
    setActiveTab("config");
    setEmbeddedSession(null);
    setEmbeddedStatus(null);
    setFbReady(false);
    setIsLaunching(false);
    setOpenaiModels([]);
    setDebouncedApiKey("");
  }, [integration, detailData, configQuery.isLoading, configQuery.data, configSchema]);

  const apiKeyRaw = (configValues.api_key as string) ?? "";
  const apiKeyValid = apiKeyRaw.length > 10 && !apiKeyRaw.includes("****");
  useEffect(() => {
    if (!apiKeyValid) {
      setDebouncedApiKey("");
      setOpenaiModels([]);
      return;
    }
    const t = setTimeout(() => setDebouncedApiKey(apiKeyRaw), 400);
    return () => clearTimeout(t);
  }, [apiKeyRaw, apiKeyValid]);

  const isOpenai = slugLower === "openai";
  const openaiModelsQuery = useQuery<{ success: boolean; models?: { id: string }[] }>({
    queryKey: [apiV1("/integrations/openai/models/"), debouncedApiKey],
    queryFn: async () => {
      const res = await apiRequest("POST", apiV1("/integrations/openai/models/"), {
        data: { config: { ...configValues, api_key: debouncedApiKey } },
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "Failed to fetch models");
      return data;
    },
    enabled: open && isOpenai && debouncedApiKey.length > 0,
    staleTime: 60_000,
  });

  useEffect(() => {
    if (openaiModelsQuery.data?.success && Array.isArray(openaiModelsQuery.data.models)) {
      setOpenaiModels(openaiModelsQuery.data.models);
    }
  }, [openaiModelsQuery.data]);

  // Load FB SDK once when WhatsApp modal opens
  useEffect(() => {
    if (!open || !isWhatsapp) return;
    const appId = embeddedConfigQuery.data?.app_id;
    const version = embeddedConfigQuery.data?.sdk_version || "v24.0";
    if (!appId) return;

    const ensureSdk = () =>
      new Promise<void>((resolve, reject) => {
        if ((window as any).FB) {
          setFbReady(true);
          return resolve();
        }
        (window as any).fbAsyncInit = function () {
          (window as any).FB.init({
            appId,
            xfbml: false,
            version,
          });
          setFbReady(true);
          resolve();
        };
        const existing = document.getElementById("facebook-jssdk");
        if (existing) {
          return;
        }
        const script = document.createElement("script");
        script.id = "facebook-jssdk";
        script.src = "https://connect.facebook.net/en_US/sdk.js";
        script.async = true;
        script.onerror = () => reject(new Error("Failed to load Facebook SDK"));
        document.body.appendChild(script);
        const root = document.getElementById("fb-root");
        if (!root) {
          const div = document.createElement("div");
          div.id = "fb-root";
          document.body.appendChild(div);
        }
      });

    ensureSdk().catch((err) => {
      console.error(err);
      setEmbeddedStatus("Could not load Facebook SDK");
    });
  }, [open, isWhatsapp, embeddedConfigQuery.data?.app_id, embeddedConfigQuery.data?.sdk_version]);

  // Listen for postMessage with session info
  useEffect(() => {
    if (!open || !isWhatsapp) return;
    const handler = (event: MessageEvent) => {
      if (event.origin !== "https://www.facebook.com" && event.origin !== "https://web.facebook.com") return;
      try {
        const data = JSON.parse(event.data as any);
        if (data?.type === "WA_EMBEDDED_SIGNUP" && data?.event === "FINISH") {
          setEmbeddedSession({
            waba_id: data?.data?.waba_id,
            phone_number_id: data?.data?.phone_number_id,
            verified_name: data?.data?.verified_name,
            display_phone_number: data?.data?.display_phone_number,
          });
          setEmbeddedStatus("Session received from Facebook");
        }
      } catch {
        // ignore
      }
    };
    window.addEventListener("message", handler);
    return () => window.removeEventListener("message", handler);
  }, [open, isWhatsapp]);

  const embeddedCompleteMutation = useMutation({
    mutationFn: async (payload: any) => {
      const res = await apiRequest(
        "POST",
        apiV1("/integrations/whatsapp/embedded-signup/complete/"),
        { data: payload }
      );
      return res.json();
    },
    onSuccess: () => {
      setEmbeddedStatus("Configuration saved");
      queryClient.invalidateQueries({ queryKey: [apiV1("/integrations/")] });
      queryClient.invalidateQueries({ queryKey: [apiV1("/integrations/whatsapp/")] });
      toast({ title: "WhatsApp connected", description: "Embedded signup completed successfully." });
    },
    onError: (err: any) => {
      toast({ title: "Signup failed", description: err?.message || "Could not save configuration.", variant: "destructive" });
      setEmbeddedStatus("Error saving configuration");
    },
  });

  const launchEmbeddedSignup = async () => {
    if (!isWhatsapp) return;
    if (!embeddedConfigQuery.data?.config_id) {
      setEmbeddedStatus("Missing config_id from backend");
      return;
    }
    const FB = (window as any).FB;
    if (!FB) {
      setEmbeddedStatus("Facebook SDK not ready");
      return;
    }
    setIsLaunching(true);
    setEmbeddedStatus("Opening Facebook...");
    FB.login(
      (resp: any) => {
        setIsLaunching(false);
        if (!resp?.authResponse?.code) {
          setEmbeddedStatus("No auth code returned");
          return;
        }
        const payload = {
          code: resp.authResponse.code,
          waba_id: embeddedSession?.waba_id,
          phone_number_id: embeddedSession?.phone_number_id,
          instance_name: embeddedSession?.verified_name || embeddedSession?.display_phone_number,
          set_as_default: false,
          display_phone_number: embeddedSession?.display_phone_number,
          verified_name: embeddedSession?.verified_name,
        };
        setEmbeddedStatus("Saving configuration...");
        embeddedCompleteMutation.mutate(payload);
      },
      {
        config_id: embeddedConfigQuery.data.config_id,
        response_type: "code",
        override_default_response_type: true,
        extras: embeddedConfigQuery.data.extras || { version: "v3" },
      }
    );
  };

  const saveMutation = useMutation({
    mutationFn: async (config: Record<string, unknown>) => {
      if (detailData) {
        const instanceId = detailData.instance_id || "default";
        const response = await apiRequest(
          "PATCH",
          apiV1(`/integrations/${slug}/${instanceId}/`),
          { data: { config } }
        );
        return response.json();
      }
      const response = await apiRequest(
        "POST",
        apiV1(`/integrations/${slug}/`),
        { data: { instance_id: "default", config, enabled: true } }
      );
      return response.json();
    },
    onSuccess: (savedData: { config?: Record<string, unknown>; is_configured?: boolean } & Record<string, unknown>) => {
      toast({ title: "Saved", description: "Integration configuration saved successfully." });
      queryClient.setQueryData([apiV1(`/integrations/${slug}/`)], (old: Integration[] | undefined) => {
        if (!old?.length) return savedData ? [savedData] : old;
        const instanceId = (savedData as { instance_id?: string })?.instance_id ?? "default";
        const idx = old.findIndex((c) => (c as { instance_id?: string }).instance_id === instanceId);
        if (idx >= 0) {
          const next = [...old];
          next[idx] = { ...next[idx], ...savedData };
          return next;
        }
        return [...old, savedData];
      });
      const isConfigured = savedData?.is_configured !== false;
      const enabled = (savedData as { enabled?: boolean })?.enabled !== false;
      queryClient.setQueryData(
        [apiV1("/integrations/")],
        (oldList: IntegrationCard[] | undefined) => {
          if (!oldList) return oldList;
          return oldList.map((card) =>
            card.slug === slug
              ? {
                  ...card,
                  is_configured: isConfigured || card.is_configured,
                  enabled: enabled || card.enabled,
                  instance_count: Math.max(card.instance_count || 0, 1),
                  connection_status: (enabled && isConfigured ? "connected" : "configured") as IntegrationCard["connection_status"],
                }
              : card
          );
        }
      );
      queryClient.invalidateQueries({ queryKey: [apiV1("/integrations/")] });
      queryClient.refetchQueries({ queryKey: [apiV1("/integrations/")] });
      onOpenChange(false);
    },
    onError: (error: Error) => {
      toast({ title: "Error", description: error.message, variant: "destructive" });
    },
  });

  const openaiModelsList = openaiModels.length > 0 ? openaiModels : (detailData?.available_models ?? []);

  const testMutation = useMutation({
    mutationFn: async () => {
      if (isOpenai) {
        const response = await apiRequest(
          "POST",
          apiV1("/integrations/openai/models/"),
          { data: { config: configValues } }
        );
        const data = await response.json();
        if (!response.ok) throw new Error(data.error ?? "Failed to verify API key");
        return data as { success: boolean; models?: { id: string }[] };
      }
      const instanceId = detailData?.instance_id || "default";
      const response = await apiRequest(
        "POST",
        apiV1(`/integrations/${slug}/${instanceId}/test/`),
        { data: { config: configValues } }
      );
      return response.json();
    },
    onSuccess: (data: { success?: boolean; message?: string; models?: { id: string }[] }) => {
      if (data.success) {
        if (isOpenai && Array.isArray(data.models)) {
          setOpenaiModels(data.models);
          toast({ title: "Success", description: `API key valid. ${data.models.length} models loaded.` });
        } else {
          toast({ title: "Success", description: data.message ?? "Connection test successful!" });
        }
        queryClient.invalidateQueries({ queryKey: [apiV1("/integrations/")] });
        queryClient.invalidateQueries({ queryKey: [apiV1(`/integrations/${slug}/`)] });
      } else {
        toast({ title: "Test Failed", description: data.message ?? "Connection test failed.", variant: "destructive" });
      }
    },
    onError: (error: Error) => {
      toast({ title: "Test Failed", description: error.message, variant: "destructive" });
      queryClient.invalidateQueries({ queryKey: [apiV1("/integrations/")] });
      queryClient.invalidateQueries({ queryKey: [apiV1(`/integrations/${slug}/`)] });
    },
  });

  const handleSave = () => {
    saveMutation.mutate(configValues);
  };

  const handleTest = () => {
    testMutation.mutate();
  };

  const togglePasswordVisibility = (key: string) => {
    setShowPasswords((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const updateValue = (key: string, value: unknown) => {
    setConfigValues((prev) => ({ ...prev, [key]: value }));
  };

  if (!integration) return null;

  const display = resolveDisplayConfig(integration.slug);
  const isSaving = saveMutation.isPending;
  const isTesting = testMutation.isPending;
  const isLoadingSchema = schemaQuery.isLoading || configQuery.isLoading;

  const connectionOk =
    (isOpenai && (openaiModelsQuery.data?.success === true || (detailData?.is_configured && detailData?.enabled))) ||
    (!isOpenai && detailData?.enabled && detailData?.is_configured);
  const connectionChecking = isOpenai && openaiModelsQuery.isFetching;
  const connectionError = isOpenai && openaiModelsQuery.isError && apiKeyValid;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <div className="flex items-center gap-3">
            <div
              className="w-10 h-10 rounded-lg flex items-center justify-center"
              style={{ backgroundColor: display.bgColor }}
            >
              <display.icon className="h-5 w-5" style={{ color: display.color }} />
            </div>
            <div className="flex-1">
              <div className="flex items-center gap-2">
                <DialogTitle>{integration.name}</DialogTitle>
                {connectionOk && (
                  <span className="flex items-center gap-1.5 text-sm font-normal text-green-600" data-testid="status-connected">
                    <span className="h-2 w-2 rounded-full bg-green-500" />
                    Connected
                  </span>
                )}
                {connectionChecking && (
                  <span className="flex items-center gap-1.5 text-sm text-muted-foreground" data-testid="status-checking">
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    Checking...
                  </span>
                )}
                {connectionError && !connectionOk && (
                  <span className="flex items-center gap-1.5 text-sm text-destructive" data-testid="status-error">
                    <span className="h-2 w-2 rounded-full bg-destructive" />
                    Invalid API key
                  </span>
                )}
                {!connectionOk && !connectionChecking && !connectionError && detailData?.is_configured && (
                  <span className="flex items-center gap-1.5 text-sm text-muted-foreground" data-testid="status-configured">
                    <span className="h-2 w-2 rounded-full bg-muted-foreground" />
                    Configured
                  </span>
                )}
              </div>
              <DialogDescription>
                {integration.is_configured ? "Manage your integration settings" : "Configure this integration to connect"}
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <Tabs value={activeTab} onValueChange={setActiveTab} className="mt-4">
          {canShowEmbeddedSignup ? (
            <TabsList className="grid w-full grid-cols-2 mb-4">
              <TabsTrigger value="config" data-testid="tab-config">Configuration</TabsTrigger>
              <TabsTrigger value="embedded_signup" data-testid="tab-embedded-signup">
                Embedded Signup
              </TabsTrigger>
            </TabsList>
          ) : null}

          <TabsContent value="config" className="space-y-4 mt-4">
            {isLoadingSchema ? (
              <div className="space-y-4">
                {[1, 2, 3].map(i => (
                  <div key={i} className="space-y-2">
                    <Skeleton className="h-4 w-24" />
                    <Skeleton className="h-10 w-full" />
                  </div>
                ))}
              </div>
            ) : configSchema.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                <AlertCircle className="h-8 w-8 mx-auto mb-2 opacity-50" />
                <p>No configuration options available for this integration.</p>
              </div>
            ) : (
              configSchema.map((field, index) => {
                const fieldName = field.name;
                const fieldType = field.sensitive ? "password" : (field.type === "integer" ? "number" : field.type === "boolean" ? "boolean" : "text");
                const fieldLabel = field.label || field.name.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
                const isSavedSensitive = field.sensitive && detailData?.is_configured;
                
                return (
                  <div key={`${fieldName}-${index}`} className="space-y-2">
                    <div className="flex items-center justify-between">
                      <Label htmlFor={fieldName}>
                        {fieldLabel}
                        {field.required && <span className="text-destructive ml-1">*</span>}
                      </Label>
                      {fieldType === "password" && !isSavedSensitive && (
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon"
                          className="h-6 w-6"
                          onClick={() => togglePasswordVisibility(fieldName)}
                          data-testid={`button-toggle-${fieldName}`}
                        >
                          {showPasswords[fieldName] ? (
                            <EyeOff className="h-3.5 w-3.5" />
                          ) : (
                            <Eye className="h-3.5 w-3.5" />
                          )}
                        </Button>
                      )}
                    </div>
                    {fieldType === "boolean" ? (
                      <div className="flex items-center gap-2">
                        <Switch
                          id={fieldName}
                          checked={configValues[fieldName] === true}
                          onCheckedChange={(checked) => updateValue(fieldName, checked)}
                          data-testid={`switch-${fieldName}`}
                        />
                        <Label htmlFor={fieldName} className="text-sm text-muted-foreground">
                          {configValues[fieldName] ? "Enabled" : "Disabled"}
                        </Label>
                      </div>
                    ) : fieldName === "default_model" && isOpenai ? (
                      openaiModelsList.length > 0 ? (
                        <Select
                          value={(configValues[fieldName] as string) ?? ""}
                          onValueChange={(v) => updateValue(fieldName, v)}
                        >
                          <SelectTrigger id={fieldName} data-testid={`select-${fieldName}`}>
                            <SelectValue placeholder="Select model" />
                          </SelectTrigger>
                          <SelectContent>
                            {openaiModelsList.map((m) => (
                              <SelectItem key={m.id} value={m.id}>
                                {m.id}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      ) : (
                        <div className="space-y-2">
                          <Input
                            id={fieldName}
                            type="text"
                            placeholder={field.placeholder || field.description}
                            value={(configValues[fieldName] as string) ?? ""}
                            onChange={(e) => updateValue(fieldName, e.target.value)}
                            data-testid={`input-${fieldName}`}
                          />
                          <p className="text-xs text-muted-foreground">
                            {openaiModelsQuery.isFetching
                              ? "Loading models..."
                              : openaiModelsQuery.isError
                                ? "Enter a valid API key to load models."
                                : "Models load automatically when API key is entered."}
                          </p>
                        </div>
                      )
                    ) : (
                      <Input
                        id={fieldName}
                        type={fieldType === "password" && (isSavedSensitive || !showPasswords[fieldName]) ? "password" : fieldType === "number" ? "number" : "text"}
                        placeholder={field.placeholder || field.description}
                        value={
                          isSavedSensitive && (configValues[fieldName] === undefined || configValues[fieldName] === "")
                            ? "••••••••••••"
                            : ((configValues[fieldName] as string | number) ?? "")
                        }
                        onChange={(e) => updateValue(fieldName, fieldType === "number" ? Number(e.target.value) : e.target.value)}
                        data-testid={`input-${fieldName}`}
                      />
                    )}
                    {field.description && (
                      <p className="text-xs text-muted-foreground">{field.description}</p>
                    )}
                    {fieldName === "api_key" && detailData?.is_configured && detailData?.updated_at && (
                      <p className="text-xs text-muted-foreground">
                        Saved {formatLastSync(detailData.updated_at) ?? "—"}
                      </p>
                    )}
                  </div>
                );
              })
            )}
          </TabsContent>

          {canShowEmbeddedSignup && (
            <TabsContent value="embedded_signup" className="space-y-4 mt-4">
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-xs uppercase tracking-wide text-muted-foreground">Facebook Embedded Signup</p>
                    <h3 className="font-semibold text-base">Connect WhatsApp Business</h3>
                  </div>
                  <Badge variant={embeddedSession?.phone_number_id ? "default" : "outline"}>
                    {embeddedSession?.phone_number_id ? "Session ready" : "Awaiting session"}
                  </Badge>
                </div>
                <p className="text-sm text-muted-foreground">
                  Use Meta embedded signup to provision a WhatsApp number. We will not set it as default unless you change it later.
                </p>

                <div className="flex items-center gap-3">
                  <Button
                    onClick={launchEmbeddedSignup}
                    disabled={
                      isLaunching ||
                      embeddedConfigQuery.isLoading ||
                      embeddedConfigQuery.isError ||
                      embeddedCompleteMutation.isPending
                    }
                  >
                    {isLaunching ? (
                      <>
                        <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                        Opening Facebook...
                      </>
                    ) : (
                      "Connect with Facebook"
                    )}
                  </Button>
                  {embeddedStatus && <span className="text-xs text-muted-foreground">{embeddedStatus}</span>}
                </div>

                {embeddedConfigQuery.isError && (
                  <p className="text-xs text-destructive">Could not load signup config from backend.</p>
                )}
                {embeddedCompleteMutation.isError && (
                  <p className="text-xs text-destructive">Failed to complete signup. Please retry.</p>
                )}

                <Separator />
                <p className="text-xs text-muted-foreground">
                  Debug: slug=<span className="font-mono">{slug || "—"}</span>
                </p>
              </div>
            </TabsContent>
          )}
        </Tabs>

        <DialogFooter className="mt-6 flex-col-reverse sm:flex-row sm:justify-between gap-2">
          <Button
            variant="outline"
            onClick={handleTest}
            disabled={isTesting}
            className="bg-yellow-500 hover:bg-yellow-600 text-black border-yellow-600"
            data-testid="button-test-connection"
          >
            {isTesting ? (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            ) : (
              <RefreshCw className="h-4 w-4 mr-2" />
            )}
            Test Connection
          </Button>
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => onOpenChange(false)} data-testid="button-cancel-config">
              Cancel
            </Button>
            <Button onClick={handleSave} disabled={isSaving || isLoadingSchema} data-testid="button-save-config">
              {isSaving ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Saving...
                </>
              ) : (
                "Save Configuration"
              )}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default function Settings() {
  const { t } = useTranslation();
  const [selectedIntegration, setSelectedIntegration] = useState<IntegrationCard | null>(null);
  const [configDialogOpen, setConfigDialogOpen] = useState(false);
  const [oauthLoading, setOauthLoading] = useState<string | null>(null);
  const [internetAccountsOpen, setInternetAccountsOpen] = useState(false);
  const [imapForm, setImapForm] = useState({
    ownership: "tenant" as "tenant" | "user",
    email_address: "",
    username: "",
    password: "",
    host: "",
    port: 993,
    use_ssl: true,
    smtp: {
      host: "",
      port: 587,
      username: "",
      password: "",
      use_ssl: true,
    },
  });
  const { toast } = useToast();
  const [newAccountProvider, setNewAccountProvider] = useState<ProviderOption>("google");
  const [newAccountOwnership, setNewAccountOwnership] = useState<"tenant" | "user">("tenant");

  const { data: integrations = [], isLoading, isError, error } = useQuery<IntegrationCard[], ApiError>({
    queryKey: [apiV1("/integrations/")],
    queryFn: () => fetchJson<IntegrationCard[]>(apiV1("/integrations/")),
    retry: false,
    staleTime: 0,
  });

  const {
    data: emailAccounts = [],
    isLoading: isEmailLoading,
    error: emailError,
  } = useQuery<EmailAccount[]>({
    queryKey: ["integrations-email-accounts"],
    queryFn: () => emailApi.listAccounts(),
    retry: false,
  });

  const {
    data: calendarAccounts = [],
    isLoading: isCalendarLoading,
    error: calendarError,
  } = useQuery<CalendarAccount[]>({
    queryKey: ["integrations-calendar-accounts"],
    queryFn: () => calendarApi.listAccounts(),
    retry: false,
  });

  const combinedAccounts: CombinedAccount[] = useMemo(() => {
    const byExternal = new Map<string, CombinedAccount>();
    emailAccounts.forEach((email) => {
      byExternal.set(email.external_account.id, { external: email.external_account, email });
    });
    calendarAccounts.forEach((cal) => {
      const existing = byExternal.get(cal.external_account.id);
      if (existing) {
        existing.calendar = cal;
      } else {
        byExternal.set(cal.external_account.id, { external: cal.external_account, calendar: cal });
      }
    });
    return Array.from(byExternal.values()).sort((a, b) =>
      a.external.email_address.localeCompare(b.external.email_address)
    );
  }, [emailAccounts, calendarAccounts]);

  const hasIntegrations = integrations.length > 0;

  const { data: me } = useQuery<AuthenticatedUser | null>({
    queryKey: [apiV1("/auth/me/")],
    queryFn: () => fetchJson<AuthenticatedUser>(apiV1("/auth/me/")),
    retry: false,
  });

  const canManageTenantAccounts = isTenantAdminRole(me?.role);

  const handleConfigure = (integration: IntegrationCard) => {
    setSelectedIntegration(integration);
    setConfigDialogOpen(true);
  };

  const emailToggleMutation = useMutation({
    mutationFn: async ({ id, action }: { id: string; action: "enable" | "disable" }) => {
      if (action === "enable") return emailApi.enableAccount(id);
      return emailApi.disableAccount(id);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["integrations-email-accounts"] });
      toast({ title: "Updated", description: "Email account updated." });
    },
    onError: (err: ApiError) => {
      toast({ title: "Failed", description: err.message, variant: "destructive" });
    },
  });

  const emailDisconnectMutation = useMutation({
    mutationFn: (id: string) => emailApi.deleteAccount(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["integrations-email-accounts"] });
      toast({ title: "Disconnected", description: "Email account removed." });
    },
    onError: (err: ApiError) => {
      toast({ title: "Failed to disconnect", description: err.message, variant: "destructive" });
    },
  });

  const calendarDisconnectMutation = useMutation({
    mutationFn: (id: string) => calendarApi.deleteAccount(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["integrations-calendar-accounts"] });
      toast({ title: "Disconnected", description: "Calendar account removed." });
    },
    onError: (err: ApiError) => {
      toast({ title: "Failed to disconnect", description: err.message, variant: "destructive" });
    },
  });

  const imapConnectMutation = useMutation({
    mutationFn: () => emailApi.imapConnect(imapForm),
    onSuccess: () => {
      toast({ title: "IMAP connected", description: "Account created successfully." });
      // Keep the modal open so users can add multiple accounts; they can close manually.
      queryClient.invalidateQueries({ queryKey: ["integrations-email-accounts"] });
    },
    onError: (err: ApiError) => {
      toast({ title: "IMAP connect failed", description: err.message, variant: "destructive" });
    },
  });

  const refreshInternetAccounts = () => {
    queryClient.invalidateQueries({ queryKey: ["integrations-email-accounts"] });
    queryClient.invalidateQueries({ queryKey: ["integrations-calendar-accounts"] });
  };

  const handleOauthStart = async (provider: "google" | "microsoft", ownership: "tenant" | "user") => {
    const key = `${provider}-${ownership}`;
    try {
      setOauthLoading(key);
      const res = await emailApi.oauthStart(provider, ownership);
      window.location.href = res.authorize_url;
    } catch (err: any) {
      toast({
        title: "OAuth start failed",
        description: err?.message || "Could not start OAuth flow.",
        variant: "destructive",
      });
    } finally {
      setOauthLoading(null);
    }
  };

  return (
    <PageLayout
      title={t("settings.title")}
      description={t("settings.description")}
      showSidebarTrigger={false}
    >
      <div className="space-y-6">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {isLoading
            ? integrationSkeletons.map((_, index) => (
                <GlassPanel key={`skeleton-${index}`} className="p-6 space-y-4">
                  <Skeleton className="h-14 w-14 rounded-lg" />
                  <div className="space-y-2">
                    <Skeleton className="h-4 w-32" />
                    <Skeleton className="h-3 w-full" />
                    <Skeleton className="h-3 w-2/3" />
                  </div>
                  <Skeleton className="h-9 w-full" />
                </GlassPanel>
              ))
            : isError
            ? (
                <GlassPanel className="p-8 md:col-span-2 lg:col-span-3">
                  <ErrorDisplay
                    error={error}
                    endpoint="api/v1/integrations"
                  />
                </GlassPanel>
              )
            : !hasIntegrations
            ? (
                <GlassPanel className="p-8 md:col-span-2 lg:col-span-3">
                  <EmptyState
                    title="No integrations available"
                    description="Connect the Moio Platform core API to surface integration options."
                  />
                </GlassPanel>
              )
            : (
                [
                  {
                    slug: "internet_accounts",
                    name: "Internet Accounts",
                    description: "Connect Google/Microsoft/IMAP and toggle Email/Calendar features.",
                    category: "integrations",
                    icon: "mail",
                    supports_multi_instance: true,
                    is_configured: combinedAccounts.length > 0,
                    enabled: true,
                    instance_count: combinedAccounts.length,
                    connection_status: combinedAccounts.length > 0 ? "connected" : "not_configured",
                  } as IntegrationCard,
                  ...integrations,
                ].map((integration) => {
                  const display = resolveDisplayConfig(integration.slug);
                  const isConfigured = integration.is_configured;
                  const isActive =
                    integration.connection_status === "connected" ||
                    (integration.enabled && isConfigured);

                  return (
                    <GlassPanel
                      key={integration.slug}
                      className="relative p-6"
                      data-testid={`card-integration-${integration.slug}`}
                    >
                      <div className="absolute top-4 right-4">
                        {isActive ? (
                          <Badge variant="default" className="gap-1 pl-1.5" data-testid={`badge-connected-${integration.slug}`}>
                            <CheckCircle2 className="h-3 w-3" />
                            Active
                          </Badge>
                        ) : isConfigured ? (
                          <Badge variant="secondary" className="gap-1 pl-1.5" data-testid={`badge-configured-${integration.slug}`}>
                            Configured
                          </Badge>
                        ) : (
                          <Badge variant="secondary" className="gap-1 pl-1.5" data-testid={`badge-disconnected-${integration.slug}`}>
                            Not Configured
                          </Badge>
                        )}
                      </div>

                      <div
                        className={`w-14 h-14 rounded-lg flex items-center justify-center mb-4 transition-opacity ${
                          isConfigured ? "" : "opacity-50 grayscale bg-muted/40"
                        }`}
                        style={isConfigured ? { backgroundColor: display.bgColor } : undefined}
                      >
                        <display.icon
                          className={`h-7 w-7 ${isConfigured ? "" : "text-muted-foreground"}`}
                          style={isConfigured ? { color: display.color } : undefined}
                        />
                      </div>

                      <div className="mb-4">
                        <h3 className="font-semibold text-base mb-2" data-testid={`text-integration-${integration.slug}`}>
                          {integration.name}
                        </h3>
                        <p className="text-sm text-muted-foreground">
                          {integration.description || "Connect to configure this integration."}
                        </p>
                      </div>

                      {integration.supports_multi_instance && isConfigured && integration.instance_count > 0 && (
                        <p className="text-xs text-muted-foreground mb-4" data-testid={`text-instances-${integration.slug}`}>
                          {integration.instance_count} instance{integration.instance_count !== 1 ? "s" : ""} configured
                        </p>
                      )}

                      <Button
                        variant={isActive ? "outline" : "default"}
                        className="w-full"
                        onClick={() => {
                          if (integration.slug === "internet_accounts") {
                            setInternetAccountsOpen(true);
                            return;
                          }
                          handleConfigure(integration);
                        }}
                        data-testid={`button-configure-${integration.slug}`}
                      >
                        {isActive ? "Manage" : "Configure"}
                      </Button>
                    </GlassPanel>
                  );
                })
              )}
        </div>
      </div>

      <Dialog open={internetAccountsOpen} onOpenChange={setInternetAccountsOpen}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle>Internet Accounts</DialogTitle>
            <DialogDescription>Connect accounts and manage access. Tenant accounts are admin-managed.</DialogDescription>
          </DialogHeader>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 max-h-[70vh] overflow-y-auto">
            <div className="space-y-3">
              <div className="flex items-center justify-between gap-2">
                <h4 className="font-semibold text-sm">Existing Connections</h4>
                <Button variant="outline" size="sm" onClick={refreshInternetAccounts}>
                  <RefreshCw className="h-4 w-4 mr-2" />
                  Refresh
                </Button>
              </div>

              {isEmailLoading || isCalendarLoading ? (
                <Skeleton className="h-10 w-full" />
              ) : emailError ? (
                <ErrorDisplay error={emailError} endpoint="/api/v1/integrations/email/accounts" />
              ) : calendarError ? (
                <ErrorDisplay error={calendarError} endpoint="/api/v1/integrations/calendar/accounts" />
              ) : combinedAccounts.length === 0 ? (
                <EmptyState title="No accounts" description="Connect Google, Microsoft, or IMAP to start." />
              ) : (
                combinedAccounts.map((acc) => {
                  const isTenant = acc.external.ownership === "tenant";
                  const canManage = !isTenant || canManageTenantAccounts;
                  const providerIcon =
                    acc.external.provider === "google" ? <SiGoogle className="h-4 w-4" /> : <Mail className="h-4 w-4" />;
                  return (
                    <div key={acc.external.id} className={`border rounded-md p-3 space-y-2 ${canManage ? "" : "opacity-50"}`}>
                      <div className="flex items-center justify-between gap-3">
                        <div className="flex items-center gap-2 min-w-0">
                          {providerIcon}
                          <span className="font-medium truncate">{acc.external.email_address}</span>
                          <Badge variant={isTenant ? "default" : "secondary"}>
                            {isTenant ? "Company" : "Personal"}
                          </Badge>
                          {isTenant && (
                            <span className="text-xs text-muted-foreground flex items-center gap-1">
                              <Shield className="h-3.5 w-3.5" />
                              Shared
                            </span>
                          )}
                        </div>
                        <Button
                          size="sm"
                          variant="destructive"
                          disabled={!canManage || calendarDisconnectMutation.isPending || emailDisconnectMutation.isPending}
                          onClick={() => {
                            if (acc.calendar) calendarDisconnectMutation.mutate(acc.calendar.id);
                            if (acc.email) emailDisconnectMutation.mutate(acc.email.id);
                          }}
                        >
                          {(calendarDisconnectMutation.isPending || emailDisconnectMutation.isPending) ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                          ) : (
                            "Delete"
                          )}
                        </Button>
                      </div>

                      <div className="flex items-center gap-4 text-xs text-muted-foreground">
                        <div className="flex items-center gap-2">
                          <span className="font-medium text-foreground/80">Email:</span>
                          <span>{acc.email ? "Connected" : "—"}</span>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="font-medium text-foreground/80">Calendar:</span>
                          <span>{acc.calendar ? "Connected" : "—"}</span>
                        </div>
                      </div>
                    </div>
                  );
                })
              )}
            </div>

            <div className="space-y-3">
              <h4 className="font-semibold text-sm">Add Connection</h4>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <Label className="text-sm">Provider</Label>
                  <Select value={newAccountProvider} onValueChange={(v) => setNewAccountProvider(v as ProviderOption)}>
                    <SelectTrigger>
                      <SelectValue placeholder="Provider" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="google">Google</SelectItem>
                      <SelectItem value="microsoft">Microsoft</SelectItem>
                      <SelectItem value="imap">IMAP</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1">
                  <Label className="text-sm">Ownership</Label>
                  <Select value={newAccountOwnership} onValueChange={(v) => setNewAccountOwnership(v as "tenant" | "user")}>
                    <SelectTrigger>
                      <SelectValue placeholder="Ownership" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="tenant">Company</SelectItem>
                      <SelectItem value="user">Personal</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>

              {newAccountProvider !== "imap" ? (
                <Button
                  onClick={() => handleOauthStart(newAccountProvider as "google" | "microsoft", newAccountOwnership)}
                  disabled={oauthLoading !== null || (newAccountOwnership === "tenant" && !canManageTenantAccounts)}
                >
                  {oauthLoading ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
                  Connect {newAccountProvider === "google" ? "Google" : "Microsoft"}
                </Button>
              ) : (
                <>
                  <div className="flex items-center gap-3">
                    <Label className="text-sm">Ownership</Label>
                    <Select
                      value={imapForm.ownership}
                      onValueChange={(v) => setImapForm((prev) => ({ ...prev, ownership: v as "tenant" | "user" }))}
                    >
                      <SelectTrigger className="w-36">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="tenant">Company</SelectItem>
                        <SelectItem value="user">Personal</SelectItem>
                      </SelectContent>
                    </Select>
                    {imapForm.ownership === "tenant" && !canManageTenantAccounts ? (
                      <span className="text-xs text-muted-foreground">Tenant admin required</span>
                    ) : null}
                  </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <Label>Email address</Label>
                  <Input
                    value={imapForm.email_address}
                    onChange={(e) => setImapForm((prev) => ({ ...prev, email_address: e.target.value }))}
                    placeholder="user@example.com"
                    disabled={imapForm.ownership === "tenant" && !canManageTenantAccounts}
                  />
                </div>
                <div className="space-y-1">
                  <Label>Username</Label>
                  <Input
                    value={imapForm.username}
                    onChange={(e) => setImapForm((prev) => ({ ...prev, username: e.target.value }))}
                    placeholder="IMAP login"
                    disabled={imapForm.ownership === "tenant" && !canManageTenantAccounts}
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <Label>Password</Label>
                  <Input
                    type="password"
                    value={imapForm.password}
                    onChange={(e) => setImapForm((prev) => ({ ...prev, password: e.target.value }))}
                    placeholder="••••••"
                    disabled={imapForm.ownership === "tenant" && !canManageTenantAccounts}
                  />
                </div>
                <div className="space-y-1">
                  <Label>IMAP Host</Label>
                  <Input
                    value={imapForm.host}
                    onChange={(e) => setImapForm((prev) => ({ ...prev, host: e.target.value }))}
                    placeholder="imap.example.com"
                    disabled={imapForm.ownership === "tenant" && !canManageTenantAccounts}
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <Label>IMAP Port</Label>
                  <Input
                    type="number"
                    value={imapForm.port}
                    onChange={(e) => setImapForm((prev) => ({ ...prev, port: Number(e.target.value) }))}
                    disabled={imapForm.ownership === "tenant" && !canManageTenantAccounts}
                  />
                </div>
                <div className="flex items-center gap-2 pt-6">
                  <Switch
                    checked={imapForm.use_ssl}
                    onCheckedChange={(checked) => setImapForm((prev) => ({ ...prev, use_ssl: checked }))}
                    disabled={imapForm.ownership === "tenant" && !canManageTenantAccounts}
                  />
                  <Label>IMAP SSL</Label>
                </div>
              </div>
              <Separator />
              <div className="space-y-2">
                <h4 className="font-medium text-sm">SMTP (required for send)</h4>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1">
                    <Label>SMTP Host</Label>
                    <Input
                      value={imapForm.smtp.host}
                      onChange={(e) => setImapForm((prev) => ({ ...prev, smtp: { ...prev.smtp, host: e.target.value } }))}
                      placeholder="smtp.example.com"
                      disabled={imapForm.ownership === "tenant" && !canManageTenantAccounts}
                    />
                  </div>
                  <div className="space-y-1">
                    <Label>SMTP Port</Label>
                    <Input
                      type="number"
                      value={imapForm.smtp.port}
                      onChange={(e) =>
                        setImapForm((prev) => ({ ...prev, smtp: { ...prev.smtp, port: Number(e.target.value) } }))
                      }
                      disabled={imapForm.ownership === "tenant" && !canManageTenantAccounts}
                    />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1">
                    <Label>SMTP Username</Label>
                    <Input
                      value={imapForm.smtp.username}
                      onChange={(e) =>
                        setImapForm((prev) => ({ ...prev, smtp: { ...prev.smtp, username: e.target.value } }))
                      }
                      disabled={imapForm.ownership === "tenant" && !canManageTenantAccounts}
                    />
                  </div>
                  <div className="space-y-1">
                    <Label>SMTP Password</Label>
                    <Input
                      type="password"
                      value={imapForm.smtp.password}
                      onChange={(e) =>
                        setImapForm((prev) => ({ ...prev, smtp: { ...prev.smtp, password: e.target.value } }))
                      }
                      disabled={imapForm.ownership === "tenant" && !canManageTenantAccounts}
                    />
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <Switch
                    checked={imapForm.smtp.use_ssl}
                    onCheckedChange={(checked) =>
                      setImapForm((prev) => ({ ...prev, smtp: { ...prev.smtp, use_ssl: checked } }))
                    }
                    disabled={imapForm.ownership === "tenant" && !canManageTenantAccounts}
                  />
                  <Label>SMTP SSL</Label>
                </div>
              </div>
                </>
              )}
            </div>
          </div>

          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setInternetAccountsOpen(false)}>
              Close
            </Button>
            {newAccountProvider === "imap" ? (
              <Button
                onClick={() => imapConnectMutation.mutate()}
                disabled={imapConnectMutation.isPending || (imapForm.ownership === "tenant" && !canManageTenantAccounts)}
              >
                {imapConnectMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
                Save IMAP Connection
              </Button>
            ) : null}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <IntegrationConfigModal
        integration={selectedIntegration}
        open={configDialogOpen}
        onOpenChange={setConfigDialogOpen}
      />
    </PageLayout>
  );
}
