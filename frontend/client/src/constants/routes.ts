/**
 * Central route constants. Use these for links and redirects so the app has a single source of truth.
 */

/** Platform admin: single entry for Django-admin-only UI (tenants, tiers, integrations, plugins). */
export const PLATFORM_ADMIN_NAMESPACE = "/platform-admin";

export const PLATFORM_ADMIN_PATHS = {
  /** Admin console (users, org, roles, docs). */
  console: `${PLATFORM_ADMIN_NAMESPACE}/console`,
} as const;

function normalizePath(location: string): string {
  return location.replace(/\/+$/, "") || "/";
}

/** True if location is under the platform-admin namespace (no main app shell). */
export function isPlatformAdminRoute(location: string): boolean {
  const path = normalizePath(location);
  return (
    path === PLATFORM_ADMIN_NAMESPACE ||
    path.startsWith(`${PLATFORM_ADMIN_NAMESPACE}/`)
  );
}
