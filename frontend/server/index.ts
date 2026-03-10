import express, { type Request, Response, NextFunction } from "express";
import { registerRoutes } from "./routes";
import { log } from "./log";
import { serveStatic } from "./static";

const app = express();

declare module 'http' {
  interface IncomingMessage {
    rawBody: unknown
  }
}
app.use(express.json({
  verify: (req, _res, buf) => {
    req.rawBody = buf;
  }
}));
app.use(express.urlencoded({ extended: false }));

app.use((req, res, next) => {
  const start = Date.now();
  const path = req.path;
  let capturedJsonResponse: Record<string, any> | undefined = undefined;

  const originalResJson = res.json;
  res.json = function (bodyJson, ...args) {
    capturedJsonResponse = bodyJson;
    return originalResJson.apply(res, [bodyJson, ...args]);
  };

  res.on("finish", () => {
    const duration = Date.now() - start;
    if (path.startsWith("/api")) {
      let logLine = `${req.method} ${path} ${res.statusCode} in ${duration}ms`;
      if (capturedJsonResponse) {
        logLine += ` :: ${JSON.stringify(capturedJsonResponse)}`;
      }

      if (logLine.length > 80) {
        logLine = logLine.slice(0, 79) + "…";
      }

      log(logLine);
    }
  });

  next();
});

(async () => {
  const server = await registerRoutes(app);

  // Proxy /api to Django backend (catches /api not handled by Express routes above)
  const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8093";
  app.use('/api', async (req, res) => {
    const targetPath = `/api${req.url}`;
    const targetUrl = `${BACKEND_URL}${targetPath}`;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);

    try {
      const headers: Record<string, string> = {
        'Accept': req.headers.accept || 'application/json',
        'Content-Type': req.headers['content-type'] || 'application/json',
      };
      ['authorization', 'x-moio-client-version', 'x-moio-tenant', 'x-csrftoken'].forEach((h) => {
        const v = req.headers[h];
        if (v && typeof v === 'string') headers[h] = v;
      });

      const hasBody = req.method !== 'GET' && req.method !== 'HEAD';
      const body = hasBody ? (req.rawBody ?? (req.body ? JSON.stringify(req.body) : undefined)) : undefined;

      const response = await fetch(targetUrl, {
        method: req.method,
        headers,
        body,
        signal: controller.signal,
      });

      clearTimeout(timeout);
      const data = await response.text();
      const contentType = response.headers.get('content-type');
      if (contentType) res.set('Content-Type', contentType);
      res.status(response.status).send(data);
    } catch (error) {
      clearTimeout(timeout);
      const msg = error instanceof Error ? error.message : String(error);
      log(`Proxy error [${targetUrl}]: ${msg}`);
      res.status(502).json({
        error: 'Backend unavailable',
        details: msg.includes('abort') ? 'Timeout' : msg,
      });
    }
  });

  app.use((err: any, _req: Request, res: Response, _next: NextFunction) => {
    const status = err.status || err.statusCode || 500;
    const message = err.message || "Internal Server Error";

    res.status(status).json({ message });
    throw err;
  });

  // importantly only setup vite in development and after
  // setting up all the other routes so the catch-all route
  // doesn't interfere with the other routes
  if (process.env.NODE_ENV !== "production") {
    const { setupVite } = await import("./vite-dev.js");
    await setupVite(app, server);
  } else {
    serveStatic(app);
  }

  // Serve on PORT (default 5177)
  // this serves both the API and the client.
  // It is the only port that is not firewalled.
  const port = parseInt(process.env.PORT || '5177', 10);
  server.listen(port, "0.0.0.0", () => {
    log(`serving on port ${port}`);
  });
})();
