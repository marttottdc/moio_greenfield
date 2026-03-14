import { Component, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { registerSW } from "virtual:pwa-register";
import App from "./App";
import "./index.css";

/** Catches render errors so users see a message instead of a white page. */
class RootErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error) {
    console.error("[App] Root error boundary caught:", error);
  }

  render() {
    if (this.state.error) {
      return (
        <div
          style={{
            minHeight: "100vh",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            padding: 24,
            fontFamily: "system-ui, sans-serif",
            background: "#f8fafc",
            color: "#0f172a",
          }}
        >
          <h1 style={{ fontSize: "1.25rem", marginBottom: 8 }}>Something went wrong</h1>
          <p style={{ color: "#64748b", marginBottom: 16, textAlign: "center" }}>
            {this.state.error.message}
          </p>
          <p style={{ fontSize: "0.875rem", color: "#94a3b8" }}>
            Open the browser console (F12) for details. If assets failed to load, check the Network tab.
          </p>
          <button
            type="button"
            onClick={() => this.setState({ error: null })}
            style={{
              marginTop: 16,
              padding: "8px 16px",
              cursor: "pointer",
              border: "1px solid #e2e8f0",
              borderRadius: 6,
              background: "#fff",
            }}
          >
            Try again
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

if ("serviceWorker" in navigator && import.meta.env.PROD) {
  registerSW({ immediate: true });
}

const rootEl = document.getElementById("root");
if (!rootEl) {
  console.error("[App] No #root element found. Check that index.html is served and contains <div id=\"root\"></div>.");
} else {
  createRoot(rootEl).render(
    <RootErrorBoundary>
      <App />
    </RootErrorBoundary>,
  );
}
