/**
 * Login flow monitoring: log each step so we can see exactly where login fails.
 * In DevTools console, filter by "[Login]" to see the sequence.
 * Replace or extend logLoginStep to send to your monitoring (e.g. Sentry, analytics).
 */

export type LoginStep =
  | "clear_cache"
  | "login_request"
  | "login_response"
  | "token_storage"
  | "backend_host"
  | "fetch_profile"
  | "redirect";

export type LoginStepOutcome = "start" | "ok" | "fail";

export interface LoginStepEvent {
  step: LoginStep;
  outcome: LoginStepOutcome;
  detail?: string | number;
  error?: unknown;
  ts: number;
}

const LOGIN_LOG_PREFIX = "[Login]";

function formatDetail(detail?: string | number, error?: unknown): string {
  if (error != null) {
    if (error instanceof Error) {
      const msg = error.message || String(error);
      const status = (error as { status?: number }).status;
      return status != null ? `status=${status} ${msg}` : msg;
    }
    return String(error);
  }
  if (detail !== undefined && detail !== "") return String(detail);
  return "";
}

export function logLoginStep(
  step: LoginStep,
  outcome: LoginStepOutcome,
  detail?: string | number,
  error?: unknown
): void {
  const event: LoginStepEvent = {
    step,
    outcome,
    detail: detail !== undefined ? String(detail) : undefined,
    error: error !== undefined ? error : undefined,
    ts: Date.now(),
  };

  const detailStr = formatDetail(detail, error);
  const label =
    outcome === "fail"
      ? `${LOGIN_LOG_PREFIX} FAIL ${step}`
      : outcome === "start"
        ? `${LOGIN_LOG_PREFIX} → ${step}`
        : `${LOGIN_LOG_PREFIX} ✓ ${step}`;

  if (outcome === "fail") {
    console.groupCollapsed(label, detailStr || "(see details)");
    console.error("Step:", step, "Outcome:", outcome);
    if (detailStr) console.error("Detail:", detailStr);
    if (error) console.error("Error:", error);
    console.groupEnd();
  } else {
    console.debug(label, detailStr || "");
  }

  // Optional: send to analytics/monitoring (e.g. window.__loginMonitor?.(event))
  try {
    const hook = (window as unknown as { __loginMonitor?: (e: LoginStepEvent) => void }).__loginMonitor;
    if (typeof hook === "function") hook(event);
  } catch {
    // ignore
  }
}

/** Call from login page when submit starts (no credentials logged). */
export function logLoginSubmitStart(): void {
  console.debug(LOGIN_LOG_PREFIX, "→ submit started");
}

/** Call from login page when an error is caught (status + message for debugging). */
export function logLoginSubmitError(status?: number, message?: string): void {
  console.warn(LOGIN_LOG_PREFIX, "submit error", { status, message });
}

// Persist last auth error so it survives full-page reload (e.g. forceLogout redirect)
const LAST_AUTH_ERROR_KEY = "moio:last_auth_error";
const MAX_AGE_MS = 5 * 60 * 1000; // 5 minutes

export interface LastAuthError {
  message: string;
  step?: string;
  status?: number;
  reason?: string;
  ts: number;
}

export function persistLastAuthError(
  message: string,
  opts?: { step?: string; status?: number; reason?: string }
): void {
  try {
    const payload: LastAuthError = {
      message,
      step: opts?.step,
      status: opts?.status,
      reason: opts?.reason,
      ts: Date.now(),
    };
    sessionStorage.setItem(LAST_AUTH_ERROR_KEY, JSON.stringify(payload));
  } catch {
    // ignore
  }
}

export function getLastAuthError(): LastAuthError | null {
  try {
    const raw = sessionStorage.getItem(LAST_AUTH_ERROR_KEY);
    if (!raw) return null;
    const data = JSON.parse(raw) as LastAuthError;
    if (Date.now() - (data.ts || 0) > MAX_AGE_MS) {
      sessionStorage.removeItem(LAST_AUTH_ERROR_KEY);
      return null;
    }
    return data;
  } catch {
    return null;
  }
}

export function clearLastAuthError(): void {
  try {
    sessionStorage.removeItem(LAST_AUTH_ERROR_KEY);
  } catch {
    // ignore
  }
}
