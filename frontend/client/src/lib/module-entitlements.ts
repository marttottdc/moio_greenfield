export type ModuleKey = "crm" | "flowsDatalab" | "chatbot" | "agentConsole";

export type ModuleEnablements = Record<ModuleKey, boolean>;
export type DevicePolicy = "mobileFull" | "desktopFirst";

const DEFAULT_ENABLEMENTS: ModuleEnablements = {
  crm: true,
  flowsDatalab: false,
  chatbot: false,
  agentConsole: false,
};

type BootstrapPayloadLike = {
  entitlements?: {
    features?: Record<string, unknown>;
    ui?: Record<string, unknown>;
  };
  capabilities?: {
    effective_features?: Record<string, unknown>;
  };
};

function asBool(value: unknown, fallback: boolean): boolean {
  if (typeof value === "boolean") return value;
  return fallback;
}

export function resolveModuleEnablements(bootstrap?: BootstrapPayloadLike | null): ModuleEnablements {
  if (!bootstrap) return { ...DEFAULT_ENABLEMENTS };

  const entitlements = bootstrap.entitlements || {};
  const features = entitlements.features || {};
  const effectiveFeatures = bootstrap.capabilities?.effective_features || {};
  const uiEnablementsRaw = entitlements.ui?.module_enablements;
  const uiEnablements =
    uiEnablementsRaw && typeof uiEnablementsRaw === "object"
      ? (uiEnablementsRaw as Record<string, unknown>)
      : null;

  const flowsFromFeatures = asBool(features.flows, false) || asBool(features.datalab, false);
  const chatbotFromFeatures = asBool(features.chatbot, false);
  const agentConsoleFromFeatures =
    asBool(features.agent_console, false) || asBool(effectiveFeatures.agent_console, false);

  const merged: ModuleEnablements = {
    crm: true,
    flowsDatalab: flowsFromFeatures,
    chatbot: chatbotFromFeatures,
    agentConsole: agentConsoleFromFeatures,
  };

  if (uiEnablements) {
    // Tenant module toggles (ui.module_enablements) are authoritative when present.
    if ("flowsDatalab" in uiEnablements) {
      merged.flowsDatalab = asBool(uiEnablements.flowsDatalab, merged.flowsDatalab);
    }
    if ("chatbot" in uiEnablements) {
      merged.chatbot = asBool(uiEnablements.chatbot, merged.chatbot);
    }
    if ("agentConsole" in uiEnablements) {
      merged.agentConsole = asBool(uiEnablements.agentConsole, merged.agentConsole);
    }
  }

  merged.crm = true;
  return merged;
}

export function isAddonRouteBlocked(pathWithQuery: string, enablements: ModuleEnablements): boolean {
  const path = String(pathWithQuery || "");
  if (/^\/(workflows|flows|scripts|datalab)(\/|$|\?)/.test(path)) {
    return !enablements.flowsDatalab;
  }
  if (/^\/agent-console(\/|$|\?)/.test(path)) {
    return !enablements.agentConsole;
  }
  return false;
}

export function getModuleDevicePolicy(moduleKey: ModuleKey): DevicePolicy {
  switch (moduleKey) {
    case "crm":
    case "agentConsole":
      return "mobileFull";
    case "flowsDatalab":
    case "chatbot":
      return "desktopFirst";
    default:
      return "desktopFirst";
  }
}

export function isMobileLiteRouteAllowed(pathWithQuery: string, moduleKey: ModuleKey): boolean {
  const raw = String(pathWithQuery || "");
  const [pathname, query = ""] = raw.split("?");
  const params = new URLSearchParams(query);
  const tab = String(params.get("tab") || "").toLowerCase();

  if (moduleKey === "flowsDatalab") {
    // Desktop-first module: only reporting surfaces are allowed on mobile.
    if (pathname === "/analytics") return true;
    if (pathname === "/workflows" && (tab === "reports" || tab === "dashboard")) return true;
    return false;
  }

  if (moduleKey === "chatbot") {
    // Chatbot mobile-lite: dashboard/reports only.
    if (pathname === "/chatbot" && (tab === "reports" || tab === "dashboard")) return true;
    if (/^\/chatbot\/(reports|dashboard)(\/|$)/.test(pathname)) return true;
    return false;
  }

  return false;
}

export function isRouteBlockedByDevicePolicy(
  pathWithQuery: string,
  moduleKey: ModuleKey,
  isMobile: boolean
): boolean {
  if (!isMobile) return false;
  const policy = getModuleDevicePolicy(moduleKey);
  if (policy === "mobileFull") return false;
  return !isMobileLiteRouteAllowed(pathWithQuery, moduleKey);
}

export function inferModuleForRoute(pathWithQuery: string): ModuleKey | null {
  const path = String(pathWithQuery || "");
  if (/^\/agent-console(\/|$|\?)/.test(path)) return "agentConsole";
  if (/^\/(workflows|flows|scripts|datalab|analytics)(\/|$|\?)/.test(path)) return "flowsDatalab";
  if (/^\/chatbot(\/|$|\?)/.test(path)) return "chatbot";
  if (/^\/(crm|contacts|deals|communications|tickets|activities)(\/|$|\?)/.test(path)) return "crm";
  return null;
}

