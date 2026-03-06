import type { Express, Request, Response } from "express";
import { createServer, type Server } from "http";
import { storage } from "./storage";
import { EventEmitter } from "events";
import type { CampaignSSEEvent } from "@shared/schema";
import { userDashboardPreferencesSchema } from "@shared/schema";

const campaignEventEmitter = new EventEmitter();
campaignEventEmitter.setMaxListeners(100);

function isPrivateOrLocalHostname(hostname: string): boolean {
  const h = hostname.toLowerCase();
  if (h === "localhost" || h === "127.0.0.1" || h === "0.0.0.0" || h === "::1") return true;

  // Block literal IPv6 hosts (conservative; avoids SSRF to link-local/private ranges)
  if (h.includes(":")) return true;

  // IPv4 literal checks
  const ipv4Match = h.match(/^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/);
  if (!ipv4Match) return false;
  const parts = ipv4Match.slice(1).map((p) => Number(p));
  if (parts.some((p) => Number.isNaN(p) || p < 0 || p > 255)) return true;

  const [a, b] = parts;
  // 10.0.0.0/8
  if (a === 10) return true;
  // 172.16.0.0/12
  if (a === 172 && b >= 16 && b <= 31) return true;
  // 192.168.0.0/16
  if (a === 192 && b === 168) return true;
  // 169.254.0.0/16 (link-local)
  if (a === 169 && b === 254) return true;
  // 127.0.0.0/8
  if (a === 127) return true;
  return false;
}

export async function registerRoutes(app: Express): Promise<Server> {

  // SSE endpoint for live campaign monitoring
  app.get("/api/v1/campaigns/stream", (req, res) => {
    const campaignId = req.query.campaign_id as string | undefined;
    const lastEventId = req.headers["last-event-id"] as string | undefined;

    res.setHeader("Content-Type", "text/event-stream");
    res.setHeader("Cache-Control", "no-cache");
    res.setHeader("Connection", "keep-alive");
    res.setHeader("X-Accel-Buffering", "no");
    res.flushHeaders();

    let eventId = lastEventId ? parseInt(lastEventId, 10) : 0;

    const sendEvent = (event: CampaignSSEEvent) => {
      if (campaignId && event.campaign_id !== campaignId) {
        return;
      }
      eventId++;
      res.write(`id: ${eventId}\n`);
      res.write(`event: ${event.type}\n`);
      res.write(`data: ${JSON.stringify(event)}\n\n`);
    };

    campaignEventEmitter.on("event", sendEvent);

    const heartbeat = setInterval(() => {
      res.write(": heartbeat\n\n");
    }, 25000);

    res.write(": connected\n\n");

    req.on("close", () => {
      clearInterval(heartbeat);
      campaignEventEmitter.off("event", sendEvent);
    });
  });

  // Internal endpoint to emit SSE events (called by webhooks or jobs)
  app.post("/api/internal/campaigns/emit-event", (req, res) => {
    const internalKey = req.headers["x-internal-key"];
    if (internalKey !== process.env.INTERNAL_API_KEY && process.env.NODE_ENV === "production") {
      return res.status(403).json({ error: "Forbidden" });
    }

    const event = req.body as CampaignSSEEvent;
    campaignEventEmitter.emit("event", event);
    res.json({ success: true });
  });

  // ============================================================================
  // Dashboard Preferences Routes
  // ============================================================================

  // Get user dashboard preferences
  app.get("/api/v1/settings/preferences/", async (req, res) => {
    try {
      // In a real app, get userId from auth session
      // For now, use a default user ID or extract from auth header
      const userId = "default-user";
      const preferences = await storage.getPreferences(userId);
      res.json(preferences);
    } catch (error) {
      console.error("Error fetching preferences:", error);
      res.status(500).json({ error: "Failed to fetch preferences" });
    }
  });

  // Update user dashboard preferences (partial update)
  app.patch("/api/v1/settings/preferences/", async (req, res) => {
    try {
      const userId = "default-user";
      
      // Validate the incoming data with partial schema
      const partialSchema = userDashboardPreferencesSchema.partial();
      const parsed = partialSchema.safeParse(req.body);
      
      if (!parsed.success) {
        return res.status(400).json({ 
          error: "Invalid preferences data", 
          details: parsed.error.issues 
        });
      }

      const updated = await storage.updatePreferences(userId, parsed.data);
      res.json(updated);
    } catch (error) {
      console.error("Error updating preferences:", error);
      res.status(500).json({ error: "Failed to update preferences" });
    }
  });


  // AI Agent Chat endpoint - connects to backend agent engine
  app.post("/api/agent/chat", async (req, res) => {
    try {
      const { message, history } = req.body;

      if (!message || typeof message !== "string") {
        return res.status(400).json({ error: "Message is required" });
      }

      // TODO: Connect to your backend agent engine here
      // This is a placeholder that should be replaced with your agent engine integration
      
      // Example placeholder response
      const assistantMessage = `I received your message: "${message}". Please connect this endpoint to your backend agent engine to enable full AI capabilities.`;

      res.json({ 
        message: assistantMessage
      });
    } catch (error) {
      console.error("AI Agent error:", error);
      res.status(500).json({ 
        error: "Failed to process chat request",
        details: error instanceof Error ? error.message : "Unknown error"
      });
    }
  });

  // ============================================================================
  // Flow Builder: HTTP node test runner (development / optional)
  // ============================================================================
  app.post("/api/v1/flows/http-test/", async (req: Request, res: Response) => {
    try {
      const urlRaw = (req.body?.url ?? "").toString().trim();
      const method = (req.body?.method ?? "GET").toString().toUpperCase();
      const timeoutMs = Number(req.body?.timeout_ms ?? 15000);

      if (!urlRaw) {
        return res.status(400).json({ error: "url is required" });
      }

      let url: URL;
      try {
        url = new URL(urlRaw);
      } catch {
        return res.status(400).json({ error: "Invalid url" });
      }

      if (url.protocol !== "http:" && url.protocol !== "https:") {
        return res.status(400).json({ error: "Only http/https URLs are allowed" });
      }
      if (isPrivateOrLocalHostname(url.hostname)) {
        return res.status(400).json({ error: "Blocked hostname" });
      }

      const incomingHeaders = req.body?.headers && typeof req.body.headers === "object" ? req.body.headers : {};
      const headers: Record<string, string> = {};
      for (const [k, v] of Object.entries(incomingHeaders)) {
        const key = String(k).trim();
        if (!key) continue;
        if (v === null || v === undefined) continue;
        headers[key] = String(v);
      }

      const hasBody = req.body?.body !== undefined && req.body?.body !== null;
      const shouldSendBody = hasBody && method !== "GET" && method !== "HEAD";

      let bodyText: string | undefined = undefined;
      if (shouldSendBody) {
        if (typeof req.body.body === "string") {
          bodyText = req.body.body;
        } else {
          bodyText = JSON.stringify(req.body.body);
          const hasContentType = Object.keys(headers).some((h) => h.toLowerCase() === "content-type");
          if (!hasContentType) {
            headers["Content-Type"] = "application/json";
          }
        }
      }

      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), Math.max(1000, Math.min(timeoutMs, 60000)));
      const startedAt = Date.now();

      let fetchRes: globalThis.Response;
      try {
        fetchRes = await fetch(url.toString(), {
          method,
          headers,
          body: shouldSendBody ? bodyText : undefined,
          signal: controller.signal,
        });
      } finally {
        clearTimeout(timeout);
      }

      const elapsedMs = Date.now() - startedAt;
      const contentType = fetchRes.headers.get("content-type") ?? undefined;

      const headersOut: Record<string, string> = {};
      ["content-type", "content-length", "date", "etag", "x-request-id"].forEach((h) => {
        const v = fetchRes.headers.get(h);
        if (v) headersOut[h] = v;
      });

      const MAX = 256 * 1024;
      let rawText = "";
      try {
        rawText = await fetchRes.text();
      } catch {
        rawText = "";
      }
      const truncated = rawText.length > MAX;
      const safeText = truncated ? rawText.slice(0, MAX) + "\n\n/* truncated */" : rawText;

      let bodyJson: any = undefined;
      if (contentType?.includes("application/json")) {
        try {
          bodyJson = JSON.parse(safeText);
        } catch {
          bodyJson = undefined;
        }
      }

      return res.json({
        ok: fetchRes.ok,
        status: fetchRes.status,
        statusText: fetchRes.statusText,
        elapsedMs,
        contentType,
        headers: headersOut,
        bodyText: safeText,
        bodyJson,
      });
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error);
      return res.status(500).json({ error: "HTTP test failed", details: msg });
    }
  });

  const httpServer = createServer(app);

  return httpServer;
}
