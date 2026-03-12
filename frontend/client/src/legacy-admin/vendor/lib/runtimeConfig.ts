// @ts-nocheck
const API_ORIGIN = String(import.meta.env.VITE_API_ORIGIN || "").trim().replace(/\/+$/, "");

function stripTrailingSlash(value: string): string {
  return String(value || "").trim().replace(/\/+$/, "");
}

export function resolveApiBase(path: string, explicitBase: string | undefined): string {
  const explicit = stripTrailingSlash(explicitBase || "");
  if (explicit) return explicit;
  if (API_ORIGIN) return `${API_ORIGIN}${path}`;
  return path;
}

export function resolveWebSocketBase(explicitBase: string | undefined): string {
  const explicit = stripTrailingSlash(explicitBase || "");
  if (explicit) return explicit;
  // In dev, use same-origin /ws (proxied by Express to backend) so agent console connects locally
  if (import.meta.env?.DEV) {
    const proto = typeof window !== "undefined" && window.location?.protocol === "https:" ? "wss" : "ws";
    return `${proto}://${typeof window !== "undefined" ? window.location.host : "localhost:5177"}/ws`;
  }
  if (API_ORIGIN) {
    const url = new URL(API_ORIGIN);
    url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
    url.pathname = "/ws";
    url.search = "";
    url.hash = "";
    return stripTrailingSlash(url.toString());
  }
  const proto = typeof window !== "undefined" && window.location?.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${typeof window !== "undefined" ? window.location.host : "localhost"}/ws`;
}
