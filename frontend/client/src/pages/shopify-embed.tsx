/**
 * Shopify Embedded App Page
 *
 * Rendered inside the Shopify Admin iframe via Shopify App Bridge.
 * Entry point: /apps/shopify/app?shop=<domain>&host=<base64>&instance_id=<id>
 *
 * Flow:
 * 1. Reads ?shop, ?host, ?instance_id from the URL
 * 2. Initialises Shopify App Bridge (createApp + getSessionToken for auth)
 * 3. Fetches the full integration config from moio backend using session token
 * 4. Renders complete config UI: connection, sync direction, toggles, manual sync
 */

import { useEffect, useMemo, useState, useCallback, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import createApp from "@shopify/app-bridge";
import { getSessionToken } from "@shopify/app-bridge/utilities";
import moioLogo from "@assets/Moio_New_Logo_Transparent_1764783655330.png";
import { apiV1, createApiUrl } from "@/lib/api";
import { ApiError, apiRequest } from "@/lib/queryClient";
import { useAuth } from "@/contexts/AuthContext";

// ── Types ────────────────────────────────────────────────────────────────────

interface ShopifyEmbedConfig {
  shopify_client_id: string;
  shopify_client_id_set: boolean;
  shopify_client_secret_set: boolean;
  merchant_profile: Record<string, unknown>;
  merchant_profile_error: string;
  instance_id: string;
  configured: boolean;
  enabled: boolean;
  status?: string;  // e.g. "connected", "uninstalled", "pending_link"
  // Platform / tunnel
  app_url: string;
  oauth_callback_url: string;
  webhook_base_url: string;
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
  // Send
  send_inventory_updates: boolean;
  send_order_updates: boolean;
  // Meta
  last_sync_metadata: Record<string, unknown>;
  // Chat widget (storefront)
  chat_widget?: {
    enabled: boolean;
    title: string;
    bubble_icon: string;
    greeting: string;
    primary_color: string;
    position: string;
    offset_x: number;
    offset_y: number;
    bubble_size: number;
    window_width: number;
    window_height: number;
    allowed_templates?: string[] | null;
  };
}

// Fields the user can edit locally before saving
interface LocalConfig {
  enabled: boolean;
  store_url: string;
  api_version: string;
  direction: "receive" | "send";
  receive_products: boolean;
  receive_customers: boolean;
  receive_orders: boolean;
  receive_inventory: boolean;
  send_inventory_updates: boolean;
  send_order_updates: boolean;
  sync_interval: number;
  chat_widget?: {
    enabled: boolean;
    title: string;
    bubble_icon: string;
    greeting: string;
    primary_color: string;
    position: string;
    offset_x: number;
    offset_y: number;
    bubble_size: number;
    window_width: number;
    window_height: number;
    allowed_templates?: string[] | null;
  };
}

// Platform-level settings (app URL, client ID/secret) are managed by platform admins only; not editable here.

// ── Shopify App Bridge ────────────────────────────────────────────────────────

declare global {
  interface Window {
    shopify?: {
      toast: { show: (msg: string, opts?: { isError?: boolean; duration?: number }) => void };
      loading: (show: boolean) => void;
    };
  }
}

function loadAppBridgeScript(clientId: string, host: string) {
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

/** Request to embed API using Shopify session token (no moio JWT). */
async function shopifyEmbedRequest(
  app: ReturnType<typeof createApp>,
  method: string,
  path: string,
  options: { body?: Record<string, unknown>; params?: Record<string, string> } = {}
): Promise<Response> {
  const token = await getSessionToken(app);
  const url = createApiUrl(path, options.params as Record<string, string> | undefined);
  const headers: Record<string, string> = {
    "Authorization": `Bearer ${token}`,
    "X-Moio-Client-Version": import.meta.env.VITE_APP_VERSION || "1.0.0",
  };
  if (options.body && method !== "GET") {
    headers["Content-Type"] = "application/json";
  }
  const res = await fetch(url, {
    method,
    headers,
    credentials: "include",
    body: options.body && method !== "GET" ? JSON.stringify(options.body) : undefined,
  });
  return res;
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

function labelizeMerchantKey(key: string): string {
  return key
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
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
            checked ? "bg-[#58a6ff]" : "bg-gray-200"
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
        className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-[#58a6ff] focus:border-transparent transition-shadow"
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
        className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-[#58a6ff] focus:border-transparent bg-white"
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
          className="w-full px-3 py-2 pr-10 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-[#58a6ff] focus:border-transparent"
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

// ── Feature Slider ───────────────────────────────────────────────────────────

const FEATURES = [
  {
    icon: "📊",
    title: "CRM Platform",
    desc: "Contacts, deals, tickets, and pipelines — all synced with your Shopify store.",
    gradient: "from-[#58a6ff]/10 to-[#58a6ff]/5",
    accent: "#58a6ff",
  },
  {
    icon: "🤖",
    title: "AI Agent Console",
    desc: "Interactive AI sessions with model selection. Let agents handle repetitive tasks.",
    gradient: "from-[#2ecc71]/10 to-[#2ecc71]/5",
    accent: "#2ecc71",
  },
  {
    icon: "⚡",
    title: "Automation Flows",
    desc: "Build visual workflows to automate order follow-ups, lead scoring, and notifications.",
    gradient: "from-[#ffba08]/10 to-[#ffba08]/5",
    accent: "#ffba08",
  },
  {
    icon: "📈",
    title: "Deal Analytics",
    desc: "Track pipeline health, conversion rates, and revenue forecasts in real time.",
    gradient: "from-[#a78bfa]/10 to-[#a78bfa]/5",
    accent: "#a78bfa",
  },
  {
    icon: "🗂️",
    title: "Activity Capture",
    desc: "Auto-log emails, calls, and notes. Never lose context on a customer relationship.",
    gradient: "from-[#ff6b6b]/10 to-[#ff6b6b]/5",
    accent: "#ff6b6b",
  },
];

function FeatureSlider() {
  const [idx, setIdx] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => setIdx((i) => (i + 1) % FEATURES.length), 5000);
    return () => clearInterval(timer);
  }, []);

  const f = FEATURES[idx];

  return (
    <div className={`rounded-xl border border-gray-200 shadow-sm overflow-hidden bg-gradient-to-br ${f.gradient}`}>
      <div className="p-5">
        <div className="flex items-center gap-2 mb-3">
          <span className="text-2xl">{f.icon}</span>
          <h3 className="text-sm font-semibold text-[#2f3542]">{f.title}</h3>
        </div>
        <p className="text-xs text-gray-600 leading-relaxed mb-4">{f.desc}</p>
        <div className="flex items-center gap-1.5">
          {FEATURES.map((_, i) => (
            <button
              key={i}
              type="button"
              onClick={() => setIdx(i)}
              className="h-1.5 rounded-full transition-all duration-300"
              style={{
                width: i === idx ? 20 : 8,
                backgroundColor: i === idx ? f.accent : "#d1d5db",
              }}
            />
          ))}
        </div>
      </div>
    </div>
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
  const clientIdFromUrl = qs("client_id");
  const { user, isAuthenticated, login, logout } = useAuth();

  const [local, setLocal] = useState<LocalConfig | null>(null);
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [syncingType, setSyncingType] = useState<string | null>(null);
  const [activeSyncTask, setActiveSyncTask] = useState<{ taskId: string; syncType: string } | null>(null);
  const [loginEmail, setLoginEmail] = useState("");
  const [loginPassword, setLoginPassword] = useState("");
  const [onboardingState, setOnboardingState] = useState<"idle" | "authenticating" | "linking">("idle");
  const [onboardingError, setOnboardingError] = useState<string | null>(null);
  const [activeSection, setActiveSection] = useState("connection");
  const [expandedSection, setExpandedSection] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<{
    shop: boolean | null;
    products?: boolean | null;
    customers?: boolean | null;
    orders?: boolean | null;
    inventory?: boolean | null;
    counts: { products?: number | null; customers?: number | null; orders?: number | null; inventory?: number | null };
    checks: { products: boolean; customers: boolean; orders: boolean; inventory: boolean };
    error?: string;
  } | null>(null);
  const installUrl = typeof window !== "undefined"
    ? `${window.location.origin}/api/v1/integrations/shopify/oauth/install/?shop=${encodeURIComponent(shop)}${host ? `&host=${encodeURIComponent(host)}` : ""}`
    : "#";

  const qc = useQueryClient();

  // Bootstrap: get client_id when not in URL (e.g. opened from Admin without OAuth redirect)
  const { data: bootstrap, isLoading: bootstrapLoading, isError: bootstrapError } = useQuery<{ shopify_client_id: string }>({
    queryKey: ["shopify-embed-bootstrap"],
    queryFn: async () => {
      const res = await fetch(createApiUrl("/api/v1/integrations/shopify/embed/bootstrap/"));
      if (!res.ok) throw new Error("Bootstrap failed");
      return res.json();
    },
    enabled: !clientIdFromUrl && !!host,
    retry: 1,
    staleTime: 60_000,
  });

  const clientId = clientIdFromUrl || bootstrap?.shopify_client_id || "";

  const app = useMemo(() => {
    if (clientId && host) return createApp({ apiKey: clientId, host });
    return null;
  }, [clientId, host]);

  useEffect(() => {
    if (clientId && host) loadAppBridgeScript(clientId, host);
  }, [clientId, host]);

  // ── Fetch config (using Shopify session token) ─────────────────────────────
  const { data: config, isLoading, error, refetch } = useQuery<ShopifyEmbedConfig>({
    queryKey: ["shopify-embed-config", instanceId, !!app],
    queryFn: async () => {
      if (!app) throw new Error("App Bridge not ready");
      const res = await shopifyEmbedRequest(app, "GET", `/api/v1/integrations/shopify/embed/config/`, {
        params: { instance_id: instanceId },
      });
      if (res.status === 401) {
        throw new Error("Session expired or app not linked. Try opening the app again from Shopify Admin.");
      }
      if (!res.ok) throw new Error(await res.text());
      return res.json();
    },
    enabled: !!app,
    retry: 1,
    staleTime: 30_000,
  });

  // Resolved instance (e.g. moioplatform) from config so we never send "default" to sync/save
  const resolvedInstanceId = config?.instance_id ?? instanceId;

  // Merchant profile loaded independently so config response is never blocked by Shopify API
  const { data: merchantProfileData, isLoading: merchantProfileLoading } = useQuery<{
    merchant_profile: Record<string, unknown>;
    merchant_profile_error: string;
  }>({
    queryKey: ["shopify-embed-merchant-profile", resolvedInstanceId],
    queryFn: async () => {
      if (!app) throw new Error("App Bridge not ready");
      const res = await shopifyEmbedRequest(app, "GET", `/api/v1/integrations/shopify/embed/merchant-profile/`, {
        params: { instance_id: resolvedInstanceId },
      });
      if (!res.ok) throw new Error(await res.text());
      return res.json();
    },
    enabled: !!app && !!config && !!config.store_url?.trim(),
    retry: 1,
    staleTime: 60_000,
  });

  // When config resolves a different instance (e.g. moioplatform), add instance_id to URL so refresh keeps it
  useEffect(() => {
    if (!config?.instance_id || typeof window === "undefined") return;
    const want = config.instance_id;
    const url = new URL(window.location.href);
    if (url.searchParams.get("instance_id") !== want) {
      url.searchParams.set("instance_id", want);
      window.history.replaceState(null, "", url.pathname + url.search + url.hash);
    }
  }, [config?.instance_id]);

  // Seed local state from server (only on first load)
  useEffect(() => {
    if (config && !local) {
      setLocal({
        enabled: config.enabled,
        store_url: config.store_url,
        api_version: config.api_version,
        direction: config.direction,
        receive_products: config.receive_products,
        receive_customers: config.receive_customers,
        receive_orders: config.receive_orders,
        receive_inventory: config.receive_inventory,
        send_inventory_updates: config.send_inventory_updates,
        send_order_updates: config.send_order_updates,
        sync_interval: config.sync_interval ?? 0,
        chat_widget: config.chat_widget
          ? {
              enabled: true,
              title: config.chat_widget.title ?? "Chat",
              bubble_icon: config.chat_widget.bubble_icon ?? "💬",
              greeting: config.chat_widget.greeting ?? "Hello! How can we help?",
              primary_color: config.chat_widget.primary_color ?? "#000000",
              position: config.chat_widget.position ?? "bottom-right",
              offset_x: Number(config.chat_widget.offset_x ?? 20),
              offset_y: Number(config.chat_widget.offset_y ?? 20),
              bubble_size: Number(config.chat_widget.bubble_size ?? 56),
              window_width: Number(config.chat_widget.window_width ?? 360),
              window_height: Number(config.chat_widget.window_height ?? 480),
              allowed_templates: config.chat_widget.allowed_templates ?? null,
            }
          : {
              enabled: true,
              title: "Chat",
              bubble_icon: "💬",
              greeting: "Hello! How can we help?",
              primary_color: "#000000",
              position: "bottom-right",
              offset_x: 20,
              offset_y: 20,
              bubble_size: 56,
              window_width: 360,
              window_height: 480,
              allowed_templates: null,
            },
      });
    }
  }, [config, local]);

  // ── Save ──────────────────────────────────────────────────────────────────
  const saveMutation = useMutation({
    mutationFn: async (patch: LocalConfig) => {
      if (!app) throw new Error("App Bridge not ready");
      const configPayload: Record<string, unknown> = {
        api_version: patch.api_version,
        direction: patch.direction,
        receive_products: patch.receive_products,
        receive_customers: patch.receive_customers,
        receive_orders: patch.receive_orders,
        receive_inventory: patch.receive_inventory,
        send_inventory_updates: patch.send_inventory_updates,
        send_order_updates: patch.send_order_updates,
        sync_interval: patch.sync_interval,
      };
      if (patch.chat_widget) {
        configPayload.chat_widget = patch.chat_widget;
      }

      const res = await shopifyEmbedRequest(app, "PATCH", `/api/v1/integrations/shopify/embed/config/`, {
        params: { instance_id: resolvedInstanceId },
        body: { enabled: patch.enabled, config: configPayload },
      });
      if (res.status === 401) throw new Error("Session expired. Open the app again from Shopify Admin.");
      if (!res.ok) throw new Error(await res.text());
      return res.json();
    },
    onSuccess: () => {
      setSaveState("saved");
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
      if (!app) throw new Error("App Bridge not ready");
      const res = await shopifyEmbedRequest(app, "POST", "/api/v1/integrations/shopify/embed/sync/", {
        body: { instance_id: resolvedInstanceId, sync_type: syncType },
      });
      if (res.status === 401) throw new Error("Session expired. Open the app again from Shopify Admin.");
      if (!res.ok) throw new Error(await res.text());
      return res.json();
    },
    onSuccess: (data) => {
      if (data.error) {
        setSyncingType(null);
        toast(`Sync failed: ${data.error}`, true);
      } else if (data.task_id) {
        setActiveSyncTask({ taskId: data.task_id, syncType: data.sync_type });
        toast(`${data.sync_type} sync started`);
      } else {
        setSyncingType(null);
        toast(`${data.sync_type} sync queued`);
      }
    },
    onError: () => {
      setSyncingType(null);
      toast("Failed to start sync", true);
    },
  });

  // Poll task status while sync is running
  const { data: syncStatus } = useQuery<{
    task_id: string;
    status: string;
    ready: boolean;
    successful?: boolean;
    result?: unknown;
    error?: string;
  }>({
    queryKey: ["shopify-embed-sync-status", activeSyncTask?.taskId],
    queryFn: async () => {
      if (!app || !activeSyncTask) throw new Error("Missing app or task");
      const res = await shopifyEmbedRequest(app, "GET", "/api/v1/integrations/shopify/embed/sync-status/", {
        params: { task_id: activeSyncTask.taskId },
      });
      if (!res.ok) throw new Error(await res.text());
      return res.json();
    },
    enabled: !!app && !!activeSyncTask,
    refetchInterval: (query) =>
      query.state.data?.ready ? false : 2000,
  });

  useEffect(() => {
    if (!syncStatus?.ready || !activeSyncTask) return;

    const isTest = activeSyncTask.syncType === "test";

    if (isTest) {
      const result = syncStatus.result as Record<string, unknown> | undefined;
      const testInner = result?.test_result as Record<string, unknown> | undefined;
      const checkedProducts = testInner?.products_preview !== undefined;
      const checkedCustomers = testInner?.customers_preview !== undefined;
      const checkedOrders = testInner?.orders_preview !== undefined;
      const checkedInventory = testInner?.inventory_preview !== undefined;
      setTestResults({
        shop: result?.shop_info ? true : false,
        products: checkedProducts ? true : false,
        customers: checkedCustomers ? true : false,
        orders: checkedOrders ? true : false,
        inventory: checkedInventory ? true : false,
        counts: {
          products: testInner?.products_count as number | null | undefined,
          customers: testInner?.customers_count as number | null | undefined,
          orders: testInner?.orders_count as number | null | undefined,
          inventory: testInner?.inventory_count as number | null | undefined,
        },
        checks: {
          products: checkedProducts,
          customers: checkedCustomers,
          orders: checkedOrders,
          inventory: checkedInventory,
        },
        error: !syncStatus.successful ? (syncStatus.error || "Test failed") : undefined,
      });
      setSyncingType(null);
      setActiveSyncTask(null);
      if (syncStatus.successful) {
        toast("Integration test completed");
      } else {
        toast(syncStatus.error || "Test failed", true);
      }
    } else {
      setSyncingType(null);
      setActiveSyncTask(null);
      if (syncStatus.successful) {
        toast(`${activeSyncTask.syncType} sync completed`);
        qc.invalidateQueries({ queryKey: ["shopify-embed-config", instanceId] });
        refetch();
      } else {
        toast(syncStatus.error || "Sync failed", true);
      }
    }
  }, [syncStatus?.ready, syncStatus?.successful, syncStatus?.error, syncStatus?.result, activeSyncTask, qc, instanceId, refetch]);

  const linkShopToTenant = useCallback(async () => {
    if (!app) throw new Error("App Bridge not ready");
    const shopifyToken = await getSessionToken(app);
    const res = await apiRequest("POST", apiV1("/integrations/shopify/embed/link/"), {
      headers: {
        "X-Shopify-Session-Token": shopifyToken,
      },
    });
    return res.json();
  }, [app]);

  // Auto-save: debounce PATCH after every field change
  const autoSaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const update = useCallback(
    <K extends keyof LocalConfig>(key: K, value: LocalConfig[K]) =>
      setLocal((prev) => {
        if (!prev) return prev;
        const next = { ...prev, [key]: value };
        if (autoSaveTimer.current) clearTimeout(autoSaveTimer.current);
        autoSaveTimer.current = setTimeout(() => {
          setSaveState("saving");
          saveMutation.mutate(next);
        }, 600);
        return next;
      }),
    [saveMutation]
  );

  const updateChatWidget = useCallback(
    <K extends keyof NonNullable<LocalConfig["chat_widget"]>>(key: K, value: NonNullable<LocalConfig["chat_widget"]>[K]) =>
      setLocal((prev) => {
        if (!prev) return prev;
        const cw = prev.chat_widget ?? {
          enabled: false,
          title: "Chat",
          bubble_icon: "💬",
          greeting: "Hello! How can we help?",
          primary_color: "#000000",
          position: "bottom-right",
          offset_x: 20,
          offset_y: 20,
          bubble_size: 56,
          window_width: 360,
          window_height: 480,
          allowed_templates: null,
        };
        const next = { ...prev, chat_widget: { ...cw, [key]: value } };
        if (autoSaveTimer.current) clearTimeout(autoSaveTimer.current);
        autoSaveTimer.current = setTimeout(() => {
          setSaveState("saving");
          saveMutation.mutate(next);
        }, 600);
        return next;
      }),
    [saveMutation]
  );

  const handleSync = (type: string) => {
    setSyncingType(type);
    syncMutation.mutate(type);
  };

  const handleOnboardingSubmit = async () => {
    setOnboardingError(null);
    try {
      if (!isAuthenticated) {
        if (!loginEmail.trim() || !loginPassword.trim()) {
          setOnboardingError("Enter your moio email and password to continue.");
          return;
        }
        setOnboardingState("authenticating");
        await login(loginEmail.trim(), loginPassword, { redirectTo: null });
      }

      setOnboardingState("linking");
      await linkShopToTenant();
      setLocal(null);
      await qc.invalidateQueries({ queryKey: ["shopify-embed-config"] });
      await refetch();
      toast("Store connected");
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : "Failed to connect your store.";
      setOnboardingError(message);
    } finally {
      setOnboardingState("idle");
    }
  };

  const openInstallFlow = () => {
    if (typeof window === "undefined") return;
    window.open(installUrl, "_top");
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

  const waitingForApp = !!host && !clientId;
  if (waitingForApp || bootstrapLoading || (app && isLoading) || (app && config && !local)) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-[#f6f6f7]">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-[3px] border-[#58a6ff] border-t-transparent rounded-full animate-spin" />
          <p className="text-sm text-gray-500">
            {waitingForApp || bootstrapLoading ? "Loading…" : "Loading configuration…"}
          </p>
        </div>
      </div>
    );
  }

  if (bootstrapError && !clientIdFromUrl && host) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-[#f6f6f7]">
        <div className="bg-white border border-red-200 rounded-xl p-8 max-w-sm text-center shadow">
          <p className="text-red-600 font-semibold mb-1">App not configured</p>
          <p className="text-sm text-gray-500">Shopify app credentials are not set. Contact your platform administrator.</p>
        </div>
      </div>
    );
  }

  // First page when not linked: login / auto-provision / link flow
  if (error) {
    const isUnauthorized = error instanceof Error && (
      error.message.includes("Session expired") ||
      error.message.includes("app not linked") ||
      error.message.includes("not linked")
    );

    if (isUnauthorized) {
      return (
        <div className="flex items-center justify-center min-h-screen bg-[#f6f6f7]">
          <div className="bg-white border border-gray-200 rounded-xl p-8 max-w-md w-full shadow space-y-5">
            <img src={moioLogo} alt="moio" className="h-10 w-auto object-contain mx-auto" />
            <div className="text-center">
              <p className="text-gray-900 font-semibold mb-1">Connect your Shopify store</p>
              <p className="text-sm text-gray-500">
                Sign in to moio. If you do not have a workspace yet, we will create one and connect this store automatically.
              </p>
            </div>

            {isAuthenticated ? (
              <div className="rounded-lg border border-gray-200 bg-gray-50 px-4 py-3">
                <p className="text-sm font-medium text-gray-900">
                  Signed in as {user?.full_name || user?.email || user?.username || "moio user"}
                </p>
                <p className="text-xs text-gray-500 mt-1">
                  Continue to link <span className="font-medium">{shop}</span> to your moio organization.
                </p>
              </div>
            ) : (
              <div className="space-y-3">
                <TextInput
                  label="Moio email"
                  value={loginEmail}
                  onChange={setLoginEmail}
                  placeholder="you@company.com"
                  type="email"
                  required
                />
                <TextInput
                  label="Password"
                  value={loginPassword}
                  onChange={setLoginPassword}
                  placeholder="Enter your password"
                  type="password"
                  required
                />
              </div>
            )}

            {onboardingError && (
              <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                {onboardingError}
              </div>
            )}

            <div className="space-y-2">
              <button
                type="button"
                onClick={() => void handleOnboardingSubmit()}
                disabled={onboardingState !== "idle"}
                className="inline-flex w-full items-center justify-center rounded-md bg-gradient-to-r from-[#58a6ff] to-[#3b82f6] px-4 py-2.5 text-sm font-medium text-white shadow-sm hover:from-[#4896ef] hover:to-[#2563eb] transition-all disabled:opacity-60"
              >
                {onboardingState === "authenticating"
                  ? "Signing in…"
                  : onboardingState === "linking"
                    ? "Connecting store…"
                    : isAuthenticated
                      ? "Continue setup"
                      : "Sign in and continue"}
              </button>

              {isAuthenticated ? (
                <button
                  type="button"
                  onClick={() => logout({ redirectTo: `${window.location.pathname}${window.location.search}` })}
                  className="inline-flex w-full items-center justify-center rounded-md border border-[#58a6ff]/30 bg-[#58a6ff]/5 px-4 py-2 text-sm font-medium text-[#2563eb] hover:bg-[#58a6ff]/10 transition-colors"
                >
                  Use another account
                </button>
              ) : null}

              <button
                type="button"
                onClick={openInstallFlow}
                className="inline-flex w-full items-center justify-center rounded-md border border-[#ffba08]/35 bg-[#ffba08]/10 px-4 py-2 text-sm font-medium text-[#b77900] hover:bg-[#ffba08]/15 transition-colors"
              >
                Re-run Shopify install
              </button>
            </div>
          </div>
        </div>
      );
    }

    const message = error instanceof Error ? error.message : "Failed to load configuration.";
    return (
      <div className="flex items-center justify-center min-h-screen bg-[#f6f6f7]">
        <div className="bg-white border border-red-200 rounded-xl p-8 max-w-sm text-center shadow">
          <p className="text-red-600 font-semibold mb-1">Failed to load configuration</p>
          <p className="text-sm text-gray-500">{message}</p>
        </div>
      </div>
    );
  }

  const isConnected = config?.configured && config?.enabled && config?.access_token_set;
  const lastSync =
    (config?.last_sync_metadata?.last_synced_at as string) ||
    (config?.last_sync_metadata?.last_connection_at as string);

  // Tasks for progress
  const task1Done = !!config?.access_token_set && config?.status !== "uninstalled";
  const task2Done = !!config?.configured;
  const task3Done = !!local?.direction;
  const task4Done = true;
  const task5Done = !!config?.enabled && !!local?.enabled;
  const tasksCompleted = [task1Done, task2Done, task3Done, task4Done, task5Done].filter(Boolean).length;
  const totalTasks = 5;

  const syncSectionOpen = activeSection === "sync";
  const toggleSyncSection = () => setActiveSection(syncSectionOpen ? "connection" : "sync");

  // Test integration: single button that triggers test_shopify_connection and shows per-line pass/fail
  const handleTestIntegration = async () => {
    if (!app || !local) return;
    const checks = {
      products: !!local.receive_products,
      customers: !!local.receive_customers,
      orders: !!local.receive_orders,
      inventory: !!local.receive_inventory,
    };
    setTestResults(null);
    setSyncingType("test");
    try {
      const res = await shopifyEmbedRequest(app, "POST", "/api/v1/integrations/shopify/embed/test/", {
        body: { instance_id: resolvedInstanceId, checks },
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      if (data.task_id) {
        setActiveSyncTask({ taskId: data.task_id, syncType: "test" });
      } else {
        setSyncingType(null);
        toast("Test queued");
      }
    } catch {
      setSyncingType(null);
      toast("Failed to start test", true);
    }
  };

  type TestCheckStatus = "idle" | "running" | "pass" | "fail";
  const testRunning = syncingType === "test";
  const shopCheck: TestCheckStatus = testRunning ? "running" : testResults ? (testResults.shop ? "pass" : "fail") : "idle";

  const enabledChecks: { key: string; label: string; enabled: boolean }[] = [
    { key: "products", label: "Products (read)", enabled: !!local?.receive_products },
    { key: "customers", label: "Customers (read)", enabled: !!local?.receive_customers },
    { key: "orders", label: "Orders (read)", enabled: !!local?.receive_orders },
    { key: "inventory", label: "Inventory (read)", enabled: !!local?.receive_inventory },
  ];

  const getCheckStatus = (key: string): TestCheckStatus => {
    if (testRunning) return "running";
    if (!testResults) return "idle";
    const val = testResults[key as keyof typeof testResults];
    if (typeof val === "boolean") return val ? "pass" : "fail";
    return "idle";
  };

  const CheckIcon = ({ status }: { status: TestCheckStatus }) => {
    if (status === "running") return <span className="w-4 h-4 border-2 border-[#58a6ff] border-t-transparent rounded-full animate-spin inline-block" />;
    if (status === "pass") return <svg className="w-4 h-4 text-green-600" fill="currentColor" viewBox="0 0 20 20"><path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" /></svg>;
    if (status === "fail") return <svg className="w-4 h-4 text-red-500" fill="currentColor" viewBox="0 0 20 20"><path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" /></svg>;
    return <span className="w-4 h-4 rounded-full border border-gray-300 inline-block" />;
  };

  return (
    <div className="min-h-screen bg-[#f8f9fa] font-sans">

      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <header className="bg-white border-b border-gray-200 px-6 py-4">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <img src={moioLogo} alt="moio" className="h-8 w-auto object-contain" />
              <span className="text-lg font-semibold text-gray-900">moio CRM</span>
            </div>
            <div className="h-6 w-px bg-gray-200" />
            <div>
              <h1 className="text-lg font-bold text-gray-900 leading-tight">
                Get started with moio CRM & Shopify
              </h1>
              <p className="text-sm text-gray-500 leading-tight">{shop}</p>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <StatusBadge ok={!!isConnected} />
            <div className="text-right">
              <p className="text-xs text-gray-500">Last sync</p>
              <p className="text-xs font-medium text-gray-700">
                {lastSync ? new Date(lastSync).toLocaleString() : "Never"}
              </p>
            </div>
          </div>
        </div>
      </header>

      {/* ── Two-column body ────────────────────────────────────────────────── */}
      <div className="max-w-6xl mx-auto px-6 py-8 flex gap-8">
        <main className="flex-1 min-w-0 space-y-4">

          {/* Primary card – Set up your online store */}
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
            <div className="px-6 py-5 border-b border-gray-100">
              <h2 className="text-base font-semibold text-gray-900">Set up your online store</h2>
              <p className="mt-1 text-sm text-gray-600">
                The moio CRM app syncs your Shopify products, customers, and orders into your CRM.
                Let&apos;s get started.
              </p>
              <div className="mt-4 flex items-center gap-3">
                <p className="text-sm text-gray-600">{tasksCompleted} of {totalTasks} tasks completed</p>
                <div className="flex-1 h-2 bg-gray-200 rounded-full overflow-hidden">
                  <div className="h-full bg-[#58a6ff] rounded-full transition-all duration-300" style={{ width: `${(tasksCompleted / totalTasks) * 100}%` }} />
                </div>
              </div>
            </div>

            <div className="divide-y divide-gray-100">
              {/* Task 1: Store connection */}
              <div className="px-6 py-4">
                <div className="flex items-start gap-4">
                  <div className="flex-shrink-0 mt-0.5">
                    {task1Done ? (
                      <span className="flex h-6 w-6 items-center justify-center rounded-full bg-green-100 text-green-600">
                        <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20"><path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" /></svg>
                      </span>
                    ) : (
                      <span className="flex h-6 w-6 items-center justify-center rounded-full border-2 border-dashed border-gray-300 text-gray-400 text-xs font-medium">1</span>
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <h3 className="text-sm font-medium text-gray-900">Connect your Shopify store</h3>
                    <p className="mt-0.5 text-xs text-gray-500">
                      {task1Done ? `Connected to ${config?.store_url || shop}` : "OAuth install flow authorizes moio to access your store"}
                    </p>
                    <div className="mt-3 flex flex-wrap items-center gap-2">
                      <button type="button" onClick={openInstallFlow} className={`inline-flex items-center rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${task1Done ? "border border-gray-200 text-gray-700 hover:bg-gray-50" : "bg-[#58a6ff] text-white hover:bg-[#4090e0]"}`}>
                        {task1Done ? "Re-run Shopify install" : "Run install"}
                      </button>
                      {task1Done && config?.access_token_set && (
                        <span className="text-xs text-green-700">Token active</span>
                      )}
                    </div>
                  </div>
                </div>
              </div>

              {/* Task 2: Link to moio */}
              <div className="px-6 py-4">
                <div className="flex items-start gap-4">
                  <div className="flex-shrink-0 mt-0.5">
                    {task2Done ? (
                      <span className="flex h-6 w-6 items-center justify-center rounded-full bg-green-100 text-green-600">
                        <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20"><path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" /></svg>
                      </span>
                    ) : (
                      <span className="flex h-6 w-6 items-center justify-center rounded-full border-2 border-dashed border-gray-300 text-gray-400 text-xs font-medium">2</span>
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <h3 className="text-sm font-medium text-gray-900">Link store to moio</h3>
                    <p className="mt-0.5 text-xs text-gray-500">Sign in to moio and connect this store to your organization</p>
                    {!task2Done && config?.access_token_set && (
                      <p className="mt-2 text-xs text-amber-700">Store is installed but not linked. Sign in above to continue.</p>
                    )}
                  </div>
                </div>
              </div>

              {/* Task 3: Configure data flow – toggle expand/collapse */}
              <div className="px-6 py-4 cursor-pointer hover:bg-gray-50/50 transition-colors" onClick={toggleSyncSection}>
                <div className="flex items-start gap-4">
                  <div className="flex-shrink-0 mt-0.5">
                    {task3Done ? (
                      <span className="flex h-6 w-6 items-center justify-center rounded-full bg-green-100 text-green-600">
                        <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20"><path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" /></svg>
                      </span>
                    ) : (
                      <span className="flex h-6 w-6 items-center justify-center rounded-full border-2 border-dashed border-gray-300 text-gray-400 text-xs font-medium">3</span>
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <h3 className="text-sm font-medium text-gray-900">Configure data flow</h3>
                    <p className="mt-0.5 text-xs text-gray-500">
                      {local?.direction === "receive" ? "Shopify → moio (receiving)" : local?.direction === "send" ? "moio → Shopify (sending)" : "Choose direction"}
                    </p>
                  </div>
                  <svg className={`w-5 h-5 text-gray-400 transition-transform ${syncSectionOpen ? "rotate-180" : ""}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                  </svg>
                </div>
              </div>

              {/* Expanded sync config */}
              {syncSectionOpen && (
                <>
                  <div className="px-6 py-4 bg-white">
                    <div className="pl-10 space-y-4">
                      <div>
                        <h4 className="text-sm font-medium text-gray-800 mb-2">Data flow direction</h4>
                        <div className="space-y-2">
                          {([{ value: "receive" as const, label: "Shopify → moio (recommended)", desc: "Products, customers, orders pulled from Shopify" }, { value: "send" as const, label: "moio → Shopify", desc: "Push inventory and order updates to Shopify" }]).map((opt) => (
                            <label key={opt.value} className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${local?.direction === opt.value ? "border-[#58a6ff] bg-blue-50" : "border-gray-200 hover:border-gray-300"}`}>
                              <input type="radio" name="direction" value={opt.value} checked={local?.direction === opt.value} onChange={() => update("direction", opt.value)} className="mt-0.5 accent-[#58a6ff]" />
                              <div>
                                <p className="text-sm font-medium text-gray-800">{opt.label}</p>
                                <p className="text-xs text-gray-500">{opt.desc}</p>
                              </div>
                            </label>
                          ))}
                        </div>
                      </div>

                      <div>
                        <h4 className="text-sm font-medium text-gray-800 mb-2">
                          {local?.direction === "receive" ? "What to import from Shopify" : "What to push to Shopify"}
                        </h4>
                        {local?.direction === "receive" && (
                          <div className="space-y-3">
                            <Toggle checked={local?.receive_products ?? false} onChange={(v) => update("receive_products", v)} label="Products" description="Product catalogue, variants, pricing" />
                            <Toggle checked={local?.receive_customers ?? false} onChange={(v) => update("receive_customers", v)} label="Customers" description="Customer records and addresses" />
                            <Toggle checked={local?.receive_orders ?? false} onChange={(v) => update("receive_orders", v)} label="Orders" description="Orders with line items and status" />
                            <Toggle checked={local?.receive_inventory ?? false} onChange={(v) => update("receive_inventory", v)} label="Inventory" description="Inventory levels" />
                          </div>
                        )}
                        {local?.direction === "send" && (
                          <div className="space-y-3">
                            <Toggle checked={local?.send_inventory_updates ?? false} onChange={(v) => update("send_inventory_updates", v)} label="Inventory updates" description="Push adjustments to Shopify" />
                            <Toggle checked={local?.send_order_updates ?? false} onChange={(v) => update("send_order_updates", v)} label="Order status updates" description="Push status changes" />
                          </div>
                        )}
                      </div>

                      <div className="flex items-center gap-3 pt-2">
                        <Toggle checked={local?.enabled ?? false} onChange={(v) => update("enabled", v)} label="Integration enabled" description="Enable syncing" />
                        {saveState === "saving" && <span className="text-xs text-gray-400">Saving…</span>}
                        {saveState === "saved" && <span className="text-xs text-green-600">Saved</span>}
                        {saveState === "error" && <span className="text-xs text-red-600">Save failed</span>}
                      </div>

                      <div>
                        <label className="block text-xs font-medium text-gray-500 mb-1">Sync frequency</label>
                        <p className="text-[11px] text-gray-400 mb-1.5">Real-time webhooks are always active. This sets an additional periodic full sync.</p>
                        <div className="grid grid-cols-4 gap-2">
                          {([
                            { value: 30, label: "30 min" },
                            { value: 60, label: "1 hour" },
                            { value: 480, label: "8 hours" },
                            { value: 1440, label: "24 hours" },
                          ] as const).map((opt) => (
                            <button
                              key={opt.value}
                              type="button"
                              onClick={() => update("sync_interval", opt.value)}
                              className={`px-3 py-2 rounded-lg text-xs font-medium border transition-colors ${
                                local?.sync_interval === opt.value
                                  ? "border-[#58a6ff] bg-blue-50 text-[#58a6ff]"
                                  : "border-gray-200 text-gray-600 hover:border-gray-300"
                              }`}
                            >
                              {opt.label}
                            </button>
                          ))}
                        </div>
                      </div>

                      <div>
                        <label className="block text-xs font-medium text-gray-500 mb-1">API Version</label>
                        <SelectInput value={local?.api_version ?? "2024-01"} onChange={(v) => update("api_version", v)} options={API_VERSIONS} />
                      </div>
                    </div>
                  </div>
                </>
              )}

              {/* Task 4: Test integration – per-line pass/fail for each enabled resource */}
              <div className="px-6 py-4">
                <div className="flex items-start gap-4">
                  <div className="flex-shrink-0 mt-0.5">
                    {testResults && !testResults.error && shopCheck === "pass" && enabledChecks.filter(c => c.enabled).every(c => getCheckStatus(c.key) === "pass") ? (
                      <span className="flex h-6 w-6 items-center justify-center rounded-full bg-green-100 text-green-600">
                        <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20"><path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" /></svg>
                      </span>
                    ) : (
                      <span className="flex h-6 w-6 items-center justify-center rounded-full border-2 border-dashed border-gray-300 text-gray-400 text-xs font-medium">4</span>
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <h3 className="text-sm font-medium text-gray-900">Test integration</h3>
                    <p className="mt-0.5 text-xs text-gray-500">Verify API access for each enabled resource</p>

                    {(shopCheck !== "idle" || testRunning) && (
                      <div className="mt-3 space-y-1.5">
                        <div className="flex items-center gap-2">
                          <CheckIcon status={shopCheck} />
                          <span className="text-xs text-gray-700">Shop info</span>
                          {shopCheck === "pass" && testResults?.shop && (
                            <span className="text-xs text-gray-400">connected</span>
                          )}
                        </div>
                        {enabledChecks.filter(c => c.enabled).map(c => {
                          const status = getCheckStatus(c.key);
                          const count = testResults?.counts?.[c.key as keyof typeof testResults.counts];
                          return (
                            <div key={c.key} className="flex items-center gap-2">
                              <CheckIcon status={status} />
                              <span className="text-xs text-gray-700">{c.label}</span>
                              {status === "pass" && count != null && (
                                <span className="text-xs text-gray-400">{count.toLocaleString()} found</span>
                              )}
                            </div>
                          );
                        })}
                        {testResults?.error && (
                          <p className="text-xs text-red-600 mt-1">{testResults.error}</p>
                        )}
                      </div>
                    )}

                    <div className="mt-3">
                      <button
                        type="button"
                        onClick={handleTestIntegration}
                        disabled={syncingType === "test"}
                        className={`inline-flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                          syncingType === "test"
                            ? "bg-gray-100 text-gray-400 cursor-wait"
                            : "bg-[#58a6ff] text-white hover:bg-[#4090e0]"
                        }`}
                      >
                        {syncingType === "test" && (
                          <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                        )}
                        {syncingType === "test" ? "Testing…" : "Test integration"}
                      </button>
                    </div>
                  </div>
                </div>
              </div>

              {/* Task 5: Confirm setup */}
              <div className="px-6 py-4">
                <div className="flex items-start gap-4">
                  <div className="flex-shrink-0 mt-0.5">
                    {task5Done ? (
                      <span className="flex h-6 w-6 items-center justify-center rounded-full bg-green-100 text-green-600">
                        <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20"><path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" /></svg>
                      </span>
                    ) : (
                      <span className="flex h-6 w-6 items-center justify-center rounded-full border-2 border-dashed border-gray-300 text-gray-400 text-xs font-medium">5</span>
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <h3 className="text-sm font-medium text-gray-900">Enable integration</h3>
                    <p className="mt-0.5 text-xs text-gray-500">
                      {task5Done ? "Integration is active and syncing" : "Enable the integration in step 3 and save"}
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Collapsible: Chat widget (storefront) */}
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
            <button
              type="button"
              onClick={() => setExpandedSection(expandedSection === "chat" ? null : "chat")}
              className="w-full px-6 py-4 flex items-center justify-between text-left hover:bg-gray-50 transition-colors"
            >
              <div className="flex items-center gap-3">
                <span className="text-lg">💬</span>
                <div>
                  <h2 className="text-sm font-semibold text-gray-900">Chat widget on your store</h2>
                  <p className="text-xs text-gray-500">
                    Turn on in Theme editor (App embeds) · Configure greeting, position, and pages
                  </p>
                </div>
              </div>
              <svg
                className={`w-5 h-5 text-gray-400 transition-transform ${expandedSection === "chat" ? "rotate-180" : ""}`}
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
            </button>
            {expandedSection === "chat" && (
              <div className="px-6 py-4 border-t border-gray-100 space-y-4">
                <TextInput
                  label="Widget title"
                  value={local?.chat_widget?.title ?? "Chat"}
                  onChange={(v) => updateChatWidget("title", v)}
                  placeholder="Chat"
                />
                <TextInput
                  label="Widget icon (emoji or URL)"
                  value={local?.chat_widget?.bubble_icon ?? "💬"}
                  onChange={(v) => updateChatWidget("bubble_icon", v)}
                  placeholder="💬 or https://cdn.example.com/icon.png"
                />
                <TextInput
                  label="Greeting"
                  value={local?.chat_widget?.greeting ?? ""}
                  onChange={(v) => updateChatWidget("greeting", v)}
                  placeholder="Hello! How can we help?"
                />
                <div className="grid grid-cols-2 gap-4">
                  <TextInput
                    label="Primary color"
                    value={local?.chat_widget?.primary_color ?? "#000000"}
                    onChange={(v) => updateChatWidget("primary_color", v)}
                    placeholder="#000000"
                  />
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Position</label>
                    <select
                      value={local?.chat_widget?.position ?? "bottom-right"}
                      onChange={(e) => updateChatWidget("position", e.target.value)}
                      className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-[#58a6ff] bg-white"
                    >
                      <option value="bottom-right">Bottom right</option>
                      <option value="bottom-left">Bottom left</option>
                      <option value="top-right">Top right</option>
                      <option value="top-left">Top left</option>
                    </select>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <TextInput
                    label="Horizontal offset (px)"
                    type="number"
                    value={String(local?.chat_widget?.offset_x ?? 20)}
                    onChange={(v) =>
                      updateChatWidget(
                        "offset_x",
                        Math.max(0, Math.min(64, Number.parseInt(v || "20", 10) || 20))
                      )
                    }
                    hint="0-64 px"
                  />
                  <TextInput
                    label="Vertical offset (px)"
                    type="number"
                    value={String(local?.chat_widget?.offset_y ?? 20)}
                    onChange={(v) =>
                      updateChatWidget(
                        "offset_y",
                        Math.max(0, Math.min(96, Number.parseInt(v || "20", 10) || 20))
                      )
                    }
                    hint="0-96 px"
                  />
                </div>
                <div className="grid grid-cols-3 gap-4">
                  <TextInput
                    label="Bubble size (px)"
                    type="number"
                    value={String(local?.chat_widget?.bubble_size ?? 56)}
                    onChange={(v) =>
                      updateChatWidget(
                        "bubble_size",
                        Math.max(44, Math.min(72, Number.parseInt(v || "56", 10) || 56))
                      )
                    }
                    hint="44-72 px"
                  />
                  <TextInput
                    label="Window width (px)"
                    type="number"
                    value={String(local?.chat_widget?.window_width ?? 360)}
                    onChange={(v) =>
                      updateChatWidget(
                        "window_width",
                        Math.max(280, Math.min(520, Number.parseInt(v || "360", 10) || 360))
                      )
                    }
                    hint="280-520 px"
                  />
                  <TextInput
                    label="Window height (px)"
                    type="number"
                    value={String(local?.chat_widget?.window_height ?? 480)}
                    onChange={(v) =>
                      updateChatWidget(
                        "window_height",
                        Math.max(320, Math.min(760, Number.parseInt(v || "480", 10) || 480))
                      )
                    }
                    hint="320-760 px"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Show on templates (optional)</label>
                  <input
                    type="text"
                    value={(local?.chat_widget?.allowed_templates ?? []).join(", ")}
                    onChange={(e) =>
                      updateChatWidget(
                        "allowed_templates",
                        e.target.value
                          .split(",")
                          .map((s) => s.trim())
                          .filter(Boolean)
                      )
                    }
                    placeholder="index, product, collection (empty = all)"
                    className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-[#58a6ff] bg-white"
                  />
                  <p className="text-xs text-gray-500 mt-1">Comma-separated template names. Leave empty to show on all pages.</p>
                </div>
                <p className="text-xs text-gray-500">
                  En móviles el widget se ajusta automáticamente al ancho de pantalla para mantener legibilidad y evitar desbordes.
                </p>
                <div className="rounded-lg border border-[#58a6ff]/30 bg-[#58a6ff]/5 p-4">
                  <p className="text-sm font-medium text-gray-800 mb-1">Activate the widget on your store</p>
                  <p className="text-xs text-gray-600 mb-2">
                    In the Theme editor, go to App embeds and turn on &quot;Moio Chat&quot;. No API URL to set — the app proxy uses your store domain automatically.
                  </p>
                  <a
                    href={
                      shop
                        ? `https://admin.shopify.com/store/${shop.replace(".myshopify.com", "")}/themes/current/editor`
                        : "#"
                    }
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1.5 text-sm font-medium text-[#2563eb] hover:underline"
                  >
                    Open Theme editor
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                    </svg>
                  </a>
                </div>
                {(saveState === "saving" || saveState === "saved" || saveState === "error") && (
                  <p className="text-xs text-gray-500">
                    {saveState === "saving" && "Saving…"}
                    {saveState === "saved" && "Saved"}
                    {saveState === "error" && "Save failed"}
                  </p>
                )}
              </div>
            )}
          </div>
        </main>

        {/* Right sidebar */}
        <aside className="w-80 flex-shrink-0 hidden lg:block">
          <div className="sticky top-24 space-y-4">

            {/* Feature slider */}
            <FeatureSlider />

            {/* Merchant profile (loaded independently so config is not blocked) */}
            {config?.store_url?.trim() && (
              <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
                <h3 className="text-sm font-semibold text-gray-900 mb-3">Merchant profile</h3>
                {merchantProfileLoading && (
                  <p className="text-sm text-gray-500">Loading…</p>
                )}
                {!merchantProfileLoading && merchantProfileData?.merchant_profile_error && (
                  <p className="text-sm text-amber-600">{merchantProfileData.merchant_profile_error}</p>
                )}
                {!merchantProfileLoading && merchantProfileData?.merchant_profile && Object.keys(merchantProfileData.merchant_profile).length > 0 && (
                  <div className="space-y-2">
                    {Object.entries(merchantProfileData.merchant_profile)
                      .filter(([, v]) => v !== null && v !== undefined && String(v).trim() !== "")
                      .map(([key, value]) => (
                        <div key={key}>
                          <p className="text-xs text-gray-500">{labelizeMerchantKey(key)}</p>
                          <p className="text-sm text-gray-700 break-words">{String(value)}</p>
                        </div>
                      ))}
                  </div>
                )}
              </div>
            )}

            {/* Platform URLs — informational, at the bottom */}
            {config?.oauth_callback_url && (
              <div className="bg-gray-50 rounded-xl border border-gray-200 p-4">
                <h3 className="text-xs font-medium text-gray-500 mb-2">Platform URLs</h3>
                <div className="space-y-1.5">
                  {[{ label: "OAuth callback", value: config.oauth_callback_url }, { label: "Webhook base", value: config.webhook_base_url }].map(({ label, value }) => (
                    <div key={label}>
                      <p className="text-[10px] text-gray-400 uppercase tracking-wider">{label}</p>
                      <div className="flex gap-1.5 mt-0.5">
                        <code className="flex-1 text-[11px] bg-white border rounded px-1.5 py-1 truncate text-gray-500">{value}</code>
                        <button type="button" onClick={() => navigator.clipboard.writeText(value)} className="text-[11px] text-[#58a6ff] hover:underline flex-shrink-0">Copy</button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </aside>
      </div>

      {/* Footer */}
      <div className="max-w-6xl mx-auto px-6 py-4 border-t border-gray-200 bg-white/50">
        <p className="text-center text-xs text-gray-400">
          moio CRM · Shopify integration · instance{" "}
          <code className="font-mono bg-gray-100 px-1 py-0.5 rounded">{config?.instance_id ?? instanceId}</code>
        </p>
      </div>
    </div>
  );
}
