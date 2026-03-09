export const APP_ROLE_ORDER = [
  "viewer",
  "member",
  "manager",
  "tenant_admin",
  "platform_admin",
] as const;

export type AppRole = (typeof APP_ROLE_ORDER)[number];

const LEGACY_ROLE_MAP: Record<string, AppRole> = {
  admin: "platform_admin",
  superuser: "platform_admin",
  user: "member",
};

export function normalizeAppRole(rawRole: string | null | undefined): AppRole {
  const normalized = String(rawRole || "").trim().toLowerCase();
  if (normalized in LEGACY_ROLE_MAP) {
    return LEGACY_ROLE_MAP[normalized];
  }
  if ((APP_ROLE_ORDER as readonly string[]).includes(normalized)) {
    return normalized as AppRole;
  }
  return "member";
}

export function hasAtLeastRole(rawRole: string | null | undefined, requiredRole: AppRole): boolean {
  const current = APP_ROLE_ORDER.indexOf(normalizeAppRole(rawRole));
  const required = APP_ROLE_ORDER.indexOf(requiredRole);
  return current >= required;
}

export function isPlatformAdminRole(rawRole: string | null | undefined): boolean {
  return normalizeAppRole(rawRole) === "platform_admin";
}

export function isTenantAdminRole(rawRole: string | null | undefined): boolean {
  const role = normalizeAppRole(rawRole);
  return role === "tenant_admin" || role === "platform_admin";
}

export function canAccessPlatformAdmin(rawRole: string | null | undefined): boolean {
  return isTenantAdminRole(rawRole);
}
