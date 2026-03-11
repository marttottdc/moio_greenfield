/**
 * Shopify Embedded App Page
 *
 * Rendered inside the Shopify Admin iframe via Shopify App Bridge.
 * Entry point: /shopify-embed?shop=<domain>&host=<base64>&instance_id=<id>
 *
 * Flow:
 * 1. Reads ?shop, ?host, ?instance_id from the URL
 * 2. Initialises Shopify App Bridge (script tag from CDN, keyed on ?host)
 * 3. Fetches the full integration config from moio backend
 * 4. Renders complete config UI: connection, sync direction, toggles, manual sync
 */

import { useEffect, useState, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import moioLogo from "@assets/Moio_New_Logo_Transparent_1764783655330.png";
import { apiRequest } from "@/lib/api";

// ── Types ────────────────────────────────────────────────────────────────────

interface ShopifyEmbedConfig {
  shopify_client_id: string;
  instance_id: string;
  configured: boolean;
  enabled: boolean;
  // Connection
  store_url: string;
  access_token: string;      // masked "••••••••" when set
  access_token_set: boolean;
  api_version: string;
  webhook_secret: string;    // masked "••••••••" when set
  webhook_secret_set: boolean;
  // Direction
  direction: "receive" | "send";
  // Receive
  receive_products: boolean;
  receive_customers: boolean;
  receive_orders: boolean;
  receive_inventory: boolean;
  // Send (future)
  send_inventory_updates: boolean;
  send_order_updates: boolean;
  // Meta
  last_sync_metadata: Record<string, unknown>;
}

// Fields the user can edit locally before saving
interface LocalConfig {
  enabled: boolean;
  store_url: string;
  access_token: string;       // empty = unchanged
  api_version: string;
  webhook_secret: string;     // empty = unchanged
  direction: "receive" | "send";
  receive_products: boolean;
  receive_customers: boolean;
  receive_orders: boolean;
  receive_inventory: boolean;
  send_inventory_updates: boolean;
  send_order_updates: boolean;
}

// ── Shopify App Bridge ────────────────────────────────────────────────────────

declare global {
  interface Window {
    shopify?: {
      toast: { show: (msg: string, opts?: { isError?: boolean; duration?: number }) => void };
      loading: (show: boolean) => void;
    };
  }
}

function loadAppBridge(clientId: string, host: string) {
  if (document.getElementById("shopify-app-bridge")) return;
  const s = document.createElement("script");
  s.id = "shopify-app-bridge";
  s.src = "https://cdn.shopify.com/shopifycloud/app-bridge.js";
  s.setAttribute("data-api-key", clientId);
  s.setAttribute("data-host", host);
  document.head.appendChild(s);
}

function toast(msg: string, isError = false) {
  if (window.shopify?.toast) {
    window.shopify.toast.show(msg, { isError, duration: 3000 });
  }
}

// ── URL helpers ───────────────────────────────────────────────────────────────

function qs(key: string) {
  return new URLSearchParams(window.location.search).get(key) ?? "";
}

function formatDate(ts: unknown): string {
  if (!ts || typeof ts !== "string") return "Never";
  try {
    return new Date(ts).toLocaleString();
  } catch {
    return "Unknown";
  }
}

// ── Sub-components ────────────────────────────────────────────────────────────

function Toggle({
  checked,
  onChange,
  label,
  description,
  disabled,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
  description?: string;
  disabled?: boolean;
}) {
  return (
    <label
      className={`flex items-start gap-3 ${disabled ? "opacity-50 cursor-not-allowed" : "cursor-pointer"}`}
    >
      <div className="relative mt-0.5 flex-shrink-0">
        <input
          type="checkbox"
          className="sr-only"
          checked={checked}
          disabled={disabled}
          onChange={(e) => !disabled && onChange(e.target.checked)}
        />
        <div
          className={`w-10 h-6 rounded-full transition-colors ${
            checked ? "bg-[#008060]" : "bg-gray-200"
          }`}
        />
        <div
          className={`absolute top-1 left-1 w-4 h-4 rounded-full bg-white shadow transition-transform ${
            checked ? "translate-x-4" : "translate-x-0"
          }`}
        />
      </div>
      <div>
        <p className="text-sm font-medium text-gray-800 leading-snug">{label}</p>
        {description && (
          <p className="text-xs text-gray-500 mt-0.5 leading-snug">{description}</p>
        )}
      </div>
    </label>
  );
}

function TextInput({
  label,
  value,
  onChange,
  placeholder,
  type = "text",
  hint,
  required,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  type?: string;
  hint?: string;
  required?: boolean;
}) {
  return (
    <div className="space-y-1">
      <label className="block text-sm font-medium text-gray-700">
        {label}
        {required && <span className="text-red-500 ml-0.5">*</span>}
      </label>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-[#008060] focus:border-transparent transition-shadow"
      />
      {hint && <p className="text-xs text-gray-400">{hint}</p>}
    </div>
  );
}

function SelectInput({
  label,
  value,
  onChange,
  options,
  hint,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
  hint?: string;
}) {
  return (
    <div className="space-y-1">
      <label className="block text-sm font-medium text-gray-700">{label}</label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-[#008060] focus:border-transparent bg-white"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
      {hint && <p className="text-xs text-gray-400">{hint}</p>}
    </div>
  );
}

function RevealInput({
  label,
  value,
  onChange,
  placeholder,
  hint,
  required,
  show,
  onToggleShow,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  hint?: string;
  required?: boolean;
  show: boolean;
  onToggleShow: () => void;
}) {
  return (
    <div className="space-y-1">
      <label className="block text-sm font-medium text-gray-700">
        {label}
        {required && <span className="text-red-500 ml-0.5">*</span>}
      </label>
      <div className="relative">
        <input
          type={show ? "text" : "password"}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className="w-full px-3 py-2 pr-10 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-[#008060] focus:border-transparent"
        />
        <button
          type="button"
          onClick={onToggleShow}
          className="absolute inset-y-0 right-2 flex items-center text-gray-400 hover:text-gray-600"
          tabIndex={-1}
        >
          {show ? (
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
            </svg>
          ) : (
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
            </svg>
          )}
        </button>
      </div>
      {hint && <p className="text-xs text-gray-400">{hint}</p>}
    </div>
  );
}

function Card({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
      <div className="px-5 py-4 border-b border-gray-100">
        <h2 className="text-sm font-semibold text-gray-800">{title}</h2>
        {subtitle && <p className="text-xs text-gray-500 mt-0.5">{subtitle}</p>}
      </div>
      <div className="px-5 py-4 space-y-4">{children}</div>
    </div>
  );
}

function StatusBadge({ ok }: { ok: boolean }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${
        ok
          ? "bg-green-50 text-green-700 border border-green-200"
          : "bg-yellow-50 text-yellow-700 border border-yellow-200"
      }`}
    >
      <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${ok ? "bg-green-500" : "bg-yellow-400"}`} />
      {ok ? "Connected" : "Not configured"}
    </span>
  );
}

// ── Main Page ────────────────────────────────────────────────────────────────

const SYNC_TYPES = [
  { id: "all", label: "All data" },
  { id: "products", label: "Products" },
  { id: "customers", label: "Customers" },
  { id: "orders", label: "Orders" },
] as const;

const API_VERSIONS = ["2024-01", "2024-04", "2024-07", "2024-10"].map((v) => ({
  value: v,
  label: v,
}));

export default function ShopifyEmbedPage() {
  const shop = qs("shop");
  const host = qs("host");
  const instanceId = qs("instance_id") || "default";

  const [local, setLocal] = useState<LocalConfig | null>(null);
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [syncingType, setSyncingType] = useState<string | null>(null);
  const [showToken, setShowToken] = useState(false);
  const [showSecret, setShowSecret] = useState(false);

  const qc = useQueryClient();

  // ── Fetch config ──────────────────────────────────────────────────────────
  const { data: config, isLoading, error } = useQuery<ShopifyEmbedConfig>({
    queryKey: ["shopify-embed-config", instanceId],
    queryFn: async () => {
      const res = await apiRequest(
        "GET",
        `/api/v1/integrations/shopify/embed/config/?instance_id=${encodeURIComponent(instanceId)}`
      );
      return res.json();
    },
    retry: 1,
    staleTime: 30_000,
  });

  // Initialise App Bridge once we know the client ID
  useEffect(() => {
    if (config?.shopify_client_id && host) {
      loadAppBridge(config.shopify_client_id, host);
    }
  }, [config?.shopify_client_id, host]);

  // Seed local state from server (only on first load)
  useEffect(() => {
    if (config && !local) {
      setLocal({
        enabled: config.enabled,
        store_url: config.store_url,
        access_token: "",       // empty = keep existing; non-empty = user wants to update
        api_version: config.api_version,
        webhook_secret: "",     // same pattern
        direction: config.direction,
        receive_products: config.receive_products,
        receive_customers: config.receive_customers,
        receive_orders: config.receive_orders,
        receive_inventory: config.receive_inventory,
        send_inventory_updates: config.send_inventory_updates,
        send_order_updates: config.send_order_updates,
      });
    }
  }, [config, local]);

  // ── Save ──────────────────────────────────────────────────────────────────
  const saveMutation = useMutation({
    mutationFn: async (patch: LocalConfig) => {
      const configPayload: Record<string, unknown> = {
        store_url: patch.store_url,
        api_version: patch.api_version,
        direction: patch.direction,
        receive_products: patch.receive_products,
        receive_customers: patch.receive_customers,
        receive_orders: patch.receive_orders,
        receive_inventory: patch.receive_inventory,
        send_inventory_updates: patch.send_inventory_updates,
        send_order_updates: patch.send_order_updates,
      };
      // Only include sensitive fields when the user typed a new value
      if (patch.access_token) configPayload.access_token = patch.access_token;
      if (patch.webhook_secret) configPayload.webhook_secret = patch.webhook_secret;

      const res = await apiRequest("PATCH", `/api/v1/integrations/shopify/${instanceId}/`, {
        enabled: patch.enabled,
        config: configPayload,
      });
      if (!res.ok) throw new Error(await res.text());
      return res.json();
    },
    onSuccess: () => {
      setSaveState("saved");
      // Reset sensitive fields so they display as masked again
      setLocal((prev) =>
        prev ? { ...prev, access_token: "", webhook_secret: "" } : prev
      );
      qc.invalidateQueries({ queryKey: ["shopify-embed-config", instanceId] });
      toast("Settings saved");
      setTimeout(() => setSaveState("idle"), 2500);
    },
    onError: () => {
      setSaveState("error");
      toast("Failed to save settings", true);
      setTimeout(() => setSaveState("idle"), 3000);
    },
  });

  // ── Sync ──────────────────────────────────────────────────────────────────
  const syncMutation = useMutation({
    mutationFn: async (syncType: string) => {
      const res = await apiRequest("POST", "/api/v1/integrations/shopify/embed/sync/", {
        instance_id: instanceId,
        sync_type: syncType,
      });
      return res.json();
    },
    onSuccess: (data) => {
      setSyncingType(null);
      toast(
        data.error ? `Sync failed: ${data.error}` : `${data.sync_type} sync queued`,
        !!data.error
      );
    },
    onError: () => {
      setSyncingType(null);
      toast("Failed to start sync", true);
    },
  });

  const update = useCallback(
    <K extends keyof LocalConfig>(key: K, value: LocalConfig[K]) =>
      setLocal((prev) => (prev ? { ...prev, [key]: value } : prev)),
    []
  );

  const handleSave = () => {
    if (!local) return;
    setSaveState("saving");
    saveMutation.mutate(local);
  };

  const handleSync = (type: string) => {
    setSyncingType(type);
    syncMutation.mutate(type);
  };

  // ── Error / loading states ────────────────────────────────────────────────

  if (!shop) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-[#f6f6f7]">
        <div className="bg-white border border-gray-200 rounded-xl p-8 max-w-sm text-center shadow">
          <p className="text-red-600 font-semibold mb-1">Missing shop parameter</p>
          <p className="text-sm text-gray-500">Open this page from inside the Shopify admin.</p>
        </div>
      </div>
    );
  }

  if (isLoading || !local) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-[#f6f6f7]">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-[3px] border-[#008060] border-t-transparent rounded-full animate-spin" />
          <p className="text-sm text-gray-500">Loading configuration…</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-[#f6f6f7]">
        <div className="bg-white border border-red-200 rounded-xl p-8 max-w-sm text-center shadow">
          <p className="text-red-600 font-semibold mb-1">Failed to load configuration</p>
          <p className="text-sm text-gray-500">
            Make sure you are logged in to moio and try again.
          </p>
        </div>
      </div>
    );
  }

  const isConnected = config?.configured && config?.enabled && config?.access_token_set;
  const lastSync =
    (config?.last_sync_metadata?.last_synced_at as string) ||
    (config?.last_sync_metadata?.last_connection_at as string);

  return (
    <div className="min-h-screen bg-[#f6f6f7] font-sans">

      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <header className="bg-white border-b border-gray-200 px-5 py-3 flex items-center justify-between sticky top-0 z-10">
        <div className="flex items-center gap-3">
          <img src={moioLogo} alt="moio" className="h-8 w-auto object-contain" />
          <div className="w-px h-6 bg-gray-200" />
          <div>
            <p className="text-sm font-semibold text-gray-900 leading-tight">
              Shopify Integration
            </p>
            <p className="text-xs text-gray-400 leading-tight">{shop}</p>
          </div>
        </div>
        <StatusBadge ok={!!isConnected} />
      </header>

      {/* ── Body ───────────────────────────────────────────────────────────── */}
      <main className="max-w-2xl mx-auto px-4 py-6 space-y-5 pb-24">

        {/* Connection */}
        <Card
          title="Connection"
          subtitle="API credentials used to communicate with your Shopify store"
        >
          <TextInput
            label="Store URL"
            required
            value={local.store_url}
            onChange={(v) => update("store_url", v)}
            placeholder="mystore.myshopify.com"
            hint="Your Shopify store domain without https://"
          />

          <RevealInput
            label="Admin API access token"
            required
            value={local.access_token}
            onChange={(v) => update("access_token", v)}
            placeholder={
              config?.access_token_set
                ? "Leave blank to keep the current token"
                : "shpat_…"
            }
            hint="Generate in Shopify admin → Apps → Develop apps → API credentials"
            show={showToken}
            onToggleShow={() => setShowToken((v) => !v)}
          />

          <SelectInput
            label="API version"
            value={local.api_version}
            onChange={(v) => update("api_version", v)}
            options={API_VERSIONS}
            hint="Shopify Admin API version to use for all requests"
          />

          <RevealInput
            label="Webhook signing secret"
            value={local.webhook_secret}
            onChange={(v) => update("webhook_secret", v)}
            placeholder={
              config?.webhook_secret_set
                ? "Leave blank to keep the current secret"
                : "Optional — verifies incoming webhook signatures"
            }
            hint="Found in Shopify admin → Settings → Notifications → Webhooks → Signing secret"
            show={showSecret}
            onToggleShow={() => setShowSecret((v) => !v)}
          />
        </Card>

        {/* Data flow direction */}
        <Card
          title="Data flow direction"
          subtitle="How data should flow between Shopify and moio CRM"
        >
          <div className="space-y-2">
            {[
              {
                value: "receive",
                label: "Shopify → moio  (recommended)",
                description:
                  "Products, customers and orders are pulled from Shopify into the CRM. Shopify is the source of truth.",
              },
              {
                value: "send",
                label: "moio → Shopify",
                description:
                  "Push inventory and order updates from the CRM back to Shopify. CRM is the source of truth.",
              },
            ].map((opt) => (
              <label
                key={opt.value}
                className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                  local.direction === opt.value
                    ? "border-[#008060] bg-green-50"
                    : "border-gray-200 hover:border-gray-300 bg-white"
                }`}
              >
                <input
                  type="radio"
                  name="direction"
                  value={opt.value}
                  checked={local.direction === opt.value}
                  onChange={() => update("direction", opt.value as "receive" | "send")}
                  className="mt-0.5 accent-[#008060]"
                />
                <div>
                  <p className="text-sm font-medium text-gray-800">{opt.label}</p>
                  <p className="text-xs text-gray-500 mt-0.5">{opt.description}</p>
                </div>
              </label>
            ))}
          </div>
        </Card>

        {/* Receive toggles */}
        {local.direction === "receive" && (
          <Card
            title="What to import from Shopify"
            subtitle="Choose which data types moio should pull from your store"
          >
            <Toggle
              checked={local.receive_products}
              onChange={(v) => update("receive_products", v)}
              label="Products"
              description="Full product catalogue including variants, pricing and tags"
            />
            <Toggle
              checked={local.receive_customers}
              onChange={(v) => update("receive_customers", v)}
              label="Customers"
              description="Customer records, email addresses and shipping addresses"
            />
            <Toggle
              checked={local.receive_orders}
              onChange={(v) => update("receive_orders", v)}
              label="Orders"
              description="Ecommerce orders with line items, totals and fulfilment status"
            />
            <Toggle
              checked={local.receive_inventory}
              onChange={(v) => update("receive_inventory", v)}
              label="Inventory"
              description="Inventory levels across all locations"
            />
          </Card>
        )}

        {/* Send toggles */}
        {local.direction === "send" && (
          <Card
            title="What to push back to Shopify"
            subtitle="Choose which updates moio should send to your store"
          >
            <Toggle
              checked={local.send_inventory_updates}
              onChange={(v) => update("send_inventory_updates", v)}
              label="Inventory updates"
              description="Push inventory adjustments made in moio back to Shopify"
            />
            <Toggle
              checked={local.send_order_updates}
              onChange={(v) => update("send_order_updates", v)}
              label="Order status updates"
              description="Push order status changes from moio back to Shopify"
            />
          </Card>
        )}

        {/* Integration on/off */}
        <Card title="Integration status">
          <Toggle
            checked={local.enabled}
            onChange={(v) => update("enabled", v)}
            label="Integration enabled"
            description="Disable to pause all syncing without losing your configuration"
          />
        </Card>

        {/* Save */}
        <div className="flex items-center gap-3">
          <button
            onClick={handleSave}
            disabled={saveState === "saving"}
            className="px-5 py-2 rounded-lg bg-[#008060] hover:bg-[#006e52] active:bg-[#005e47] text-white text-sm font-semibold transition-colors disabled:opacity-60 disabled:cursor-not-allowed shadow-sm"
          >
            {saveState === "saving" ? "Saving…" : "Save settings"}
          </button>
          {saveState === "saved" && (
            <span className="text-sm text-green-700 font-medium">Saved!</span>
          )}
          {saveState === "error" && (
            <span className="text-sm text-red-600">Failed to save — check your settings</span>
          )}
        </div>

        {/* Sync */}
        <Card
          title="Data sync"
          subtitle={`Last sync: ${formatDate(lastSync)}`}
        >
          <p className="text-xs text-gray-500">
            Trigger an immediate sync. Large stores may take a few minutes. You can also
            monitor the sync log in moio's admin panel.
          </p>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {SYNC_TYPES.map(({ id, label }) => {
              const isSyncing = syncingType === id;
              const isDisabled = syncingType !== null;
              return (
                <button
                  key={id}
                  onClick={() => handleSync(id)}
                  disabled={isDisabled}
                  className={`flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg border text-sm font-medium transition-colors ${
                    isSyncing
                      ? "border-[#008060] text-[#008060] bg-green-50"
                      : "border-gray-200 text-gray-700 hover:border-[#008060] hover:text-[#008060] hover:bg-green-50"
                  } disabled:opacity-50 disabled:cursor-not-allowed`}
                >
                  {isSyncing && (
                    <span className="w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin flex-shrink-0" />
                  )}
                  {label}
                </button>
              );
            })}
          </div>
        </Card>

        {/* Footer */}
        <p className="text-center text-xs text-gray-400 pb-4">
          moio CRM · Shopify integration · instance{" "}
          <code className="font-mono bg-gray-100 px-1 py-0.5 rounded">{instanceId}</code>
        </p>
      </main>
    </div>
  );
}
