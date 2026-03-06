import { defineConfig } from "vite";
import { configDefaults } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "path";
import runtimeErrorOverlay from "@replit/vite-plugin-runtime-error-modal";

const clientRoot = path.resolve(import.meta.dirname, "client");

export default defineConfig({
  plugins: [
    react(),
    runtimeErrorOverlay(),
    ...(process.env.NODE_ENV !== "production" &&
    process.env.REPL_ID !== undefined
      ? [
          await import("@replit/vite-plugin-cartographer").then((m) =>
            m.cartographer(),
          ),
          await import("@replit/vite-plugin-dev-banner").then((m) =>
            m.devBanner(),
          ),
        ]
      : []),
  ],
  resolve: {
    alias: {
      "@": path.resolve(import.meta.dirname, "client", "src"),
      "@shared": path.resolve(import.meta.dirname, "shared"),
      "@assets": path.resolve(import.meta.dirname, "attached_assets"),
    },
  },
  root: clientRoot,
  build: {
    outDir: path.resolve(import.meta.dirname, "dist/public"),
    emptyOutDir: true,
    manifest: true,
    rollupOptions: {
      input: {
        app: path.resolve(clientRoot, "index.html"),
        flowbuilder: path.resolve(clientRoot, "src/apps/flowbuilder/main.tsx"),
      },
    },
  },
  server: {
    fs: {
      strict: true,
      deny: ["**/.*"],
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: path.resolve(import.meta.dirname, "vitest.setup.ts"),
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
    exclude: [...configDefaults.exclude, "../server/**"],
    // NOTE: In some Node/Vitest combos, the worker pool can crash during teardown
    // with a tinypool "Maximum call stack size exceeded". Force single-threaded
    // execution to avoid worker teardown.
    pool: "threads",
    poolOptions: { threads: { singleThread: true } },
    minThreads: 1,
    maxThreads: 1,
    fileParallelism: false,
  },
});
