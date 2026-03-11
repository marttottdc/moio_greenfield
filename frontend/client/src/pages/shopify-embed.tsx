/**
 * Shopify Embedded App Page
 *
 * This page is served inside the Shopify Admin iframe via Shopify App Bridge.
 * Entry point: /shopify-embed?shop=<domain>&host=<base64>&instance_id=<id>
 *
 * On load it:
 * 1. Reads ?shop, ?host, ?instance_id from the URL
 * 2. Initialises Shopify App Bridge (loaded from CDN via <script> in index.html
 *    or injected dynamically here)
 * 3. Fetches the integration config from the moio backend
 * 4. Renders a clean config UI (no sidebar) for managing the Shopify integration
 */

import { useEffect, useState, useCallback } from "react";
import { useLocation } from "wouter";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "@/lib/api";

// ── Types ────────────────────────────────────────────────────────────────────

interface ShopifyEmbedConfig {
  shopify_client_id: string;
  instance_id: string;
  configured: boolean;
  enabled: boolean;
  store_url: string;
  api_version: string;
  direction: string;
  receive_products: boolean;
  receive_customers: boolean;
  receive_orders: boolean;
  receive_inventory: boolean;
  last_sync_metadata: Record<string, unknown>;
}

interface SyncResult {
  status: string;
  task_id?: string;
  sync_type: string;
  error?: string;
}

// ── Shopify App Bridge initialisation ────────────────────────────────────────

declare global {
  interface Window {
    ShopifyApp?: {
      init: (config: Record<string, unknown>) => void;
      Bar?: {
        initialize: (config: Record<string, unknown>) => void;
        loadingOn: () => void;
        loadingOff: () => void;
      };
    };
    // App Bridge 3.x / 4.x
    shopify?: {
      toast: { show: (msg: string, opts?: { isError?: boolean }) => void };
      loading: (show: boolean) => void;
    };
  }
}

function loadAppBridgeScript(clientId: string, host: string) {
  if (document.getElementById("shopify-app-bridge")) return;
  const script = document.createElement("script");
  script.id = "shopify-app-bridge";
  script.src = `https://cdn.shopify.com/shopifycloud/app-bridge.js`;
  script.setAttribute("data-api-key", clientId);
  script.setAttribute("data-host", host);
  document.head.appendChild(script);
}

function showToast(msg: string, isError = false) {
  if (window.shopify?.toast) {
    window.shopify.toast.show(msg, { isError });
  }
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function getUrlParam(search: string, key: string): string {
  return new URLSearchParams(search).get(key) ?? "";
}

function formatSyncMeta(meta: Record<string, unknown>): string {
  if (!meta || Object.keys(meta).length === 0) return "Never synced";
  const ts =
    (meta.last_synced_at as string) ||
    (meta.last_connection_at as string) ||
    "";
  if (!ts) return "Unknown";
  return new Date(ts).toLocaleString();
}

// ── Components ───────────────────────────────────────────────────────────────

function Toggle({
  checked,
  onChange,
  label,
  description,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
  description?: string;
}) {
  return (
    <label className="flex items-start gap-3 cursor-pointer group">
      <div className="relative mt-0.5">
        <input
          type="checkbox"
          className="sr-only"
          checked={checked}
          onChange={(e) => onChange(e.target.checked)}
        />
        <div
          className={`w-10 h-6 rounded-full transition-colors ${
            checked ? "bg-[#008060]" : "bg-gray-300"
          }`}
        />
        <div
          className={`absolute top-1 left-1 w-4 h-4 rounded-full bg-white shadow transition-transform ${
            checked ? "translate-x-4" : "translate-x-0"
          }`}
        />
      </div>
      <div>
        <p className="text-sm font-medium text-gray-800 leading-tight">{label}</p>
        {description && (
          <p className="text-xs text-gray-500 mt-0.5">{description}</p>
        )}
      </div>
    </label>
  );
}

function SectionCard({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-5">
      <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide mb-4">
        {title}
      </h2>
      {children}
    </div>
  );
}

// ── Main Page ────────────────────────────────────────────────────────────────

export default function ShopifyEmbedPage() {
  const [location] = useLocation();
  const search = window.location.search;

  const shop = getUrlParam(search, "shop");
  const host = getUrlParam(search, "host");
  const instanceId = getUrlParam(search, "instance_id") || "default";

  const [saveStatus, setSaveStatus] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [localConfig, setLocalConfig] = useState<Partial<ShopifyEmbedConfig>>({});
  const [syncingType, setSyncingType] = useState<string | null>(null);

  const qc = useQueryClient();

  // Fetch config from backend
  const { data: config, isLoading, error } = useQuery<ShopifyEmbedConfig>({
    queryKey: ["shopify-embed-config", instanceId],
    queryFn: async () => {
      const res = await apiRequest(
        "GET",
        `/api/v1/integrations/shopify/embed/config/?instance_id=${instanceId}`
      );
      return res.json();
    },
    retry: 1,
  });

  // Initialise App Bridge once we know the client ID
  useEffect(() => {
    const clientId = config?.shopify_client_id || "";
    if (clientId && host) {
      loadAppBridgeScript(clientId, host);
    }
  }, [config?.shopify_client_id, host]);

  // Seed local config when server data arrives
  useEffect(() => {
    if (config) {
      setLocalConfig({
        direction: config.direction,
        receive_products: config.receive_products,
        receive_customers: config.receive_customers,
        receive_orders: config.receive_orders,
        receive_inventory: config.receive_inventory,
        enabled: config.enabled,
      });
    }
  }, [config]);

  // Save settings mutation
  const saveMutation = useMutation({
    mutationFn: async (patch: Partial<ShopifyEmbedConfig>) => {
      const res = await apiRequest(
        "PATCH",
        `/api/v1/integrations/shopify/${instanceId}/`,
        { config: patch }
      );
      return res.json();
    },
    onSuccess: () => {
      setSaveStatus("saved");
      qc.invalidateQueries({ queryKey: ["shopify-embed-config", instanceId] });
      showToast("Settings saved");
      setTimeout(() => setSaveStatus("idle"), 2500);
    },
    onError: () => {
      setSaveStatus("error");
      showToast("Failed to save settings", true);
    },
  });

  // Sync trigger mutation
  const syncMutation = useMutation<SyncResult, Error, string>({
    mutationFn: async (syncType: string) => {
      const res = await apiRequest("POST", `/api/v1/integrations/shopify/embed/sync/`, {
        instance_id: instanceId,
        sync_type: syncType,
      });
      return res.json();
    },
    onSuccess: (data) => {
      setSyncingType(null);
      showToast(
        data.error
          ? `Sync failed: ${data.error}`
          : `${data.sync_type} sync queued (task ${data.task_id ?? "?"})`,
        !!data.error
      );
    },
    onError: () => {
      setSyncingType(null);
      showToast("Failed to trigger sync", true);
    },
  });

  const handleSave = useCallback(() => {
    setSaveStatus("saving");
    saveMutation.mutate(localConfig);
  }, [localConfig, saveMutation]);

  const handleSync = useCallback(
    (syncType: string) => {
      setSyncingType(syncType);
      syncMutation.mutate(syncType);
    },
    [syncMutation]
  );

  // ── Render ────────────────────────────────────────────────────────────────

  if (!shop) {
    return (
      <div className="flex items-center justify-center h-screen bg-[#f6f6f7]">
        <div className="bg-white rounded-lg border border-gray-200 p-8 max-w-sm text-center shadow">
          <p className="text-red-600 font-medium mb-2">Missing shop parameter</p>
          <p className="text-sm text-gray-500">
            This page must be opened from inside the Shopify admin.
          </p>
        </div>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-screen bg-[#f6f6f7]">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-2 border-[#008060] border-t-transparent rounded-full animate-spin" />
          <p className="text-sm text-gray-500">Loading configuration…</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#f6f6f7] font-sans">
      {/* Top bar */}
      <header className="bg-[#1a1a1a] text-white px-5 py-3 flex items-center gap-3">
        <svg
          viewBox="0 0 109.5 124.5"
          className="w-6 h-6 fill-[#96bf48]"
          xmlns="http://www.w3.org/2000/svg"
        >
          <path d="M74.7 14.8s-.3 0-.3-.1c-1.5-.4-3.1-.6-4.8-.6-5.9 0-11 3.7-12.9 9-1.9-1.2-4.1-2-6.5-2.4L39 7.7S38.5 7 37.8 7c-.6 0-1.3.5-1.3.5L23.8 18.4C14 20.2 4.8 28 3.1 39.5L.1 64.3c-.5 3.6 2.7 6.7 6.4 6.7h7.1l-1.8 17.8c-.7 6.4 4.3 12 10.7 12h67.2c6.4 0 11.4-5.6 10.7-12L98.6 71h7.1c3.7 0 6.9-3.1 6.4-6.7L109 39.5C107.3 28 98 20.2 88.2 18.4L74.7 14.8zm0 0" />
        </svg>
        <div>
          <p className="text-sm font-semibold leading-tight">moio · Shopify</p>
          <p className="text-xs text-gray-400 leading-tight">{shop}</p>
        </div>
      </header>

      <main className="max-w-2xl mx-auto px-4 py-6 space-y-5">
        {/* Status banner */}
        {config && (
          <div
            className={`rounded-lg px-4 py-3 text-sm flex items-center gap-2 ${
              config.configured && config.enabled
                ? "bg-green-50 text-green-800 border border-green-200"
                : "bg-yellow-50 text-yellow-800 border border-yellow-200"
            }`}
          >
            <span
              className={`w-2 h-2 rounded-full flex-shrink-0 ${
                config.configured && config.enabled ? "bg-green-500" : "bg-yellow-400"
              }`}
            />
            {config.configured && config.enabled
              ? `Connected to ${config.store_url}`
              : "Integration not yet active — save settings to activate"}
          </div>
        )}

        {/* Sync settings */}
        <SectionCard title="What to sync from Shopify">
          <div className="space-y-4">
            <Toggle
              checked={localConfig.receive_products ?? true}
              onChange={(v) => setLocalConfig((c) => ({ ...c, receive_products: v }))}
              label="Products"
              description="Sync product catalogue from Shopify into CRM"
            />
            <Toggle
              checked={localConfig.receive_customers ?? true}
              onChange={(v) => setLocalConfig((c) => ({ ...c, receive_customers: v }))}
              label="Customers"
              description="Sync customer records and addresses"
            />
            <Toggle
              checked={localConfig.receive_orders ?? true}
              onChange={(v) => setLocalConfig((c) => ({ ...c, receive_orders: v }))}
              label="Orders"
              description="Sync ecommerce orders with line items"
            />
            <Toggle
              checked={localConfig.receive_inventory ?? true}
              onChange={(v) => setLocalConfig((c) => ({ ...c, receive_inventory: v }))}
              label="Inventory"
              description="Sync inventory levels"
            />
          </div>
        </SectionCard>

        {/* Integration enabled */}
        <SectionCard title="Integration status">
          <Toggle
            checked={localConfig.enabled ?? false}
            onChange={(v) => setLocalConfig((c) => ({ ...c, enabled: v }))}
            label="Integration enabled"
            description="Turn off to pause all syncing without losing configuration"
          />
        </SectionCard>

        {/* Last sync info */}
        {config && (
          <SectionCard title="Sync history">
            <p className="text-sm text-gray-600">
              Last synced:{" "}
              <span className="font-medium">
                {formatSyncMeta(config.last_sync_metadata)}
              </span>
            </p>
          </SectionCard>
        )}

        {/* Save button */}
        <div className="flex gap-3 items-center">
          <button
            onClick={handleSave}
            disabled={saveStatus === "saving"}
            className="px-5 py-2 rounded-md bg-[#008060] hover:bg-[#006e52] text-white text-sm font-medium transition-colors disabled:opacity-60"
          >
            {saveStatus === "saving" ? "Saving…" : "Save settings"}
          </button>
          {saveStatus === "saved" && (
            <span className="text-sm text-green-700">Saved!</span>
          )}
          {saveStatus === "error" && (
            <span className="text-sm text-red-600">Failed to save</span>
          )}
        </div>

        {/* Manual sync */}
        <SectionCard title="Manual sync">
          <p className="text-xs text-gray-500 mb-4">
            Trigger an immediate sync. Large stores may take a few minutes.
          </p>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {(["all", "products", "customers", "orders"] as const).map((type) => (
              <button
                key={type}
                onClick={() => handleSync(type)}
                disabled={syncingType !== null}
                className="px-3 py-2 rounded-md border border-gray-300 hover:border-[#008060] hover:text-[#008060] text-sm transition-colors capitalize disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {syncingType === type ? (
                  <span className="flex items-center justify-center gap-1">
                    <span className="w-3 h-3 border border-current border-t-transparent rounded-full animate-spin" />
                    {type}
                  </span>
                ) : (
                  type === "all" ? "Sync all" : `Sync ${type}`
                )}
              </button>
            ))}
          </div>
        </SectionCard>
      </main>
    </div>
  );
}
