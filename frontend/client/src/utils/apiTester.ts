import { apiRequest } from "@/lib/queryClient";
import { apiV1 } from "@/lib/api";

export interface EndpointTest {
  module: string;
  method: string;
  path: string;
  description: string;
  status: "pending" | "success" | "error" | "skipped";
  statusCode?: number;
  response?: any;
  error?: string;
  implemented: boolean;
}

const LEGACY_CAMPAIGNS_PREFIX = "/campaigns/api";

function stripLegacyCampaignsPrefix(path: string) {
  if (!path.startsWith(LEGACY_CAMPAIGNS_PREFIX)) {
    return path;
  }

  const withoutPrefix = path.slice(LEGACY_CAMPAIGNS_PREFIX.length);
  return withoutPrefix.startsWith("/") ? withoutPrefix : `/${withoutPrefix}`;
}

function resolveApiPath(path: string) {
  path = stripLegacyCampaignsPrefix(path);

  if (path.startsWith("/api/")) {
    return path;
  }

  if (path.startsWith("/v1/")) {
    return path;
  }

  if (path.startsWith("/")) {
    return apiV1(path);
  }

  return apiV1(`/${path}`);
}

// NOTE: Paths below are relative to the API router. They are automatically prefixed with `/api/v1`
// via `resolveApiPath` so the historical `/campaigns/api/...` references continue to work.
export const ENDPOINT_INVENTORY: EndpointTest[] = [
  // Core Services - Authentication
  { module: "Core Services", method: "POST", path: "/auth/login", description: "Login with credentials", status: "pending", implemented: true },
  { module: "Core Services", method: "GET", path: "/auth/me", description: "Get current user profile", status: "pending", implemented: true },
  { module: "Core Services", method: "POST", path: "/auth/refresh", description: "Refresh access token", status: "pending", implemented: true },
  { module: "Core Services", method: "POST", path: "/auth/logout", description: "Logout current session", status: "pending", implemented: true },
  
  // Core Services - Settings
  { module: "Core Services", method: "GET", path: "/settings/preferences", description: "Get user preferences", status: "pending", implemented: true },
  { module: "Core Services", method: "PATCH", path: "/settings/preferences", description: "Update user preferences", status: "pending", implemented: true },
  { module: "Core Services", method: "GET", path: "/settings/integrations", description: "List connected integrations", status: "pending", implemented: true },
  { module: "Core Services", method: "POST", path: "/settings/integrations/{id}/connect", description: "Connect new integration", status: "pending", implemented: true },
  
  // Contacts & Deals (backend under /api/v1/crm/)
  { module: "Contacts & Deals", method: "GET", path: "/crm/contacts/", description: "List contacts with filters", status: "pending", implemented: true },
  { module: "Contacts & Deals", method: "POST", path: "/crm/contacts/", description: "Create new contact", status: "pending", implemented: true },
  { module: "Contacts & Deals", method: "GET", path: "/crm/contacts/{id}/", description: "Get contact details", status: "pending", implemented: true },
  { module: "Contacts & Deals", method: "PATCH", path: "/crm/contacts/{id}/", description: "Update contact", status: "pending", implemented: true },
  { module: "Contacts & Deals", method: "DELETE", path: "/crm/contacts/{id}/", description: "Delete contact", status: "pending", implemented: true },
  { module: "Contacts & Deals", method: "POST", path: "/crm/contacts/import/", description: "Import contacts from CSV", status: "pending", implemented: true },
  { module: "Contacts & Deals", method: "GET", path: "/crm/contacts/export/", description: "Export contacts to CSV", status: "pending", implemented: true },
  { module: "Contacts & Deals", method: "GET", path: "/crm/deals/", description: "List deals by pipeline stage", status: "pending", implemented: true },
  { module: "Contacts & Deals", method: "POST", path: "/crm/deals/", description: "Create new deal", status: "pending", implemented: true },
  { module: "Contacts & Deals", method: "PATCH", path: "/crm/deals/{id}/", description: "Update deal stage/fields", status: "pending", implemented: true },
  
  // Communications (backend: /api/v1/crm/communications/conversations/ and channels/)
  { module: "Communications", method: "GET", path: "/crm/communications/conversations/", description: "List conversations", status: "pending", implemented: true },
  { module: "Communications", method: "GET", path: "/crm/communications/conversations/{id}/messages/", description: "Get conversation messages", status: "pending", implemented: true },
  { module: "Communications", method: "POST", path: "/crm/communications/conversations/{id}/messages/", description: "Send message", status: "pending", implemented: true },
  { module: "Communications", method: "GET", path: "/crm/communications/channels/", description: "List enabled channels", status: "pending", implemented: true },
  { module: "Communications", method: "POST", path: "/crm/communications/channels/{id}/test/", description: "Test channel health", status: "pending", implemented: true },
  
  // Campaigns (list/create at /api/v1/campaigns/campaigns/; templates under crm)
  { module: "Campaigns", method: "GET", path: "/campaigns/campaigns/", description: "List campaigns with metrics", status: "pending", implemented: true },
  { module: "Campaigns", method: "POST", path: "/campaigns/campaigns/", description: "Create draft campaign", status: "pending", implemented: true },
  { module: "Campaigns", method: "GET", path: "/campaigns/campaigns/{id}/", description: "Get campaign details", status: "pending", implemented: true },
  { module: "Campaigns", method: "POST", path: "/campaigns/campaigns/{id}/send/", description: "Launch or confirm send", status: "pending", implemented: true },
  { module: "Campaigns", method: "GET", path: "/campaigns/campaigns/{id}/analytics/", description: "Get campaign analytics", status: "pending", implemented: true },
  { module: "Campaigns", method: "GET", path: "/crm/templates/", description: "List reusable templates", status: "pending", implemented: true },
  
  // Flows & Automation (executions/ not runs; toggle-active, preview)
  { module: "Flows & Automation", method: "GET", path: "/flows/", description: "List workflows", status: "pending", implemented: true },
  { module: "Flows & Automation", method: "POST", path: "/flows/", description: "Create workflow", status: "pending", implemented: true },
  { module: "Flows & Automation", method: "GET", path: "/flows/{id}/", description: "Get workflow definition", status: "pending", implemented: true },
  { module: "Flows & Automation", method: "PATCH", path: "/flows/{id}/save/", description: "Update workflow (save graph)", status: "pending", implemented: true },
  { module: "Flows & Automation", method: "POST", path: "/flows/{id}/toggle-active/", description: "Toggle workflow active state", status: "pending", implemented: true },
  { module: "Flows & Automation", method: "POST", path: "/flows/{id}/preview/", description: "Preview/test workflow run", status: "pending", implemented: true },
  { module: "Flows & Automation", method: "GET", path: "/flows/executions/", description: "Get execution history", status: "pending", implemented: true },
  
  // Moio User Management (tenant-scoped at /api/v1/users/)
  { module: "Moio Users", method: "GET", path: "/api/v1/users/", description: "List users", status: "pending", implemented: true },
  { module: "Moio Users", method: "POST", path: "/api/v1/users/", description: "Create user", status: "pending", implemented: true },
  { module: "Moio Users", method: "GET", path: "/api/v1/users/{id}/", description: "Get user details", status: "pending", implemented: true },
  { module: "Moio Users", method: "PATCH", path: "/api/v1/users/{id}/", description: "Update user", status: "pending", implemented: true },
  { module: "Moio Users", method: "DELETE", path: "/api/v1/users/{id}/", description: "Delete user", status: "pending", implemented: true },
  { module: "Admin Console", method: "GET", path: "/settings/organization", description: "Get organization settings", status: "pending", implemented: false },
  { module: "Admin Console", method: "PATCH", path: "/settings/organization", description: "Update organization", status: "pending", implemented: false },
  { module: "Admin Console", method: "GET", path: "/settings/roles", description: "List roles and permissions", status: "pending", implemented: false },
  
  // Platform Experience (content/navigation and engagement/topics not implemented on backend)
  { module: "Platform Experience", method: "GET", path: "/content/pages/{slug}", description: "Get published page", status: "pending", implemented: false },
  { module: "Platform Experience", method: "GET", path: "/content/navigation", description: "Get menu hierarchy", status: "pending", implemented: false },
  { module: "Platform Experience", method: "POST", path: "/conversations/session", description: "Initialize AI session", status: "pending", implemented: false },
  { module: "Platform Experience", method: "GET", path: "/engagement/topics", description: "Get trending topics", status: "pending", implemented: false },
  { module: "Platform Experience", method: "POST", path: "/meetings/slots", description: "Propose meeting slots", status: "pending", implemented: false },

  // Dashboard (backend under /api/v1/crm/)
  { module: "Dashboard", method: "GET", path: "/crm/dashboard/summary/", description: "Get campaigns dashboard bundle", status: "pending", implemented: true },

  // Audiences
  { module: "Audiences", method: "GET", path: "/campaigns/audiences/", description: "List tenant audiences", status: "pending", implemented: true },
  { module: "Audiences", method: "POST", path: "/campaigns/audiences/", description: "Create audience", status: "pending", implemented: true },
  { module: "Audiences", method: "POST", path: "/campaigns/audiences/{id}/dynamic/preview/", description: "Preview dynamic rules", status: "pending", implemented: true },
  { module: "Audiences", method: "POST", path: "/campaigns/audiences/{id}/dynamic/autosave/", description: "Autosave dynamic rules", status: "pending", implemented: true },
  { module: "Audiences", method: "POST", path: "/campaigns/audiences/{id}/dynamic/finalize/", description: "Finalize dynamic audience", status: "pending", implemented: true },
  { module: "Audiences", method: "POST", path: "/campaigns/audiences/{id}/static/contacts/", description: "Manage static members", status: "pending", implemented: true },
  { module: "Audiences", method: "POST", path: "/campaigns/audiences/{id}/static/finalize/", description: "Finalize static audience", status: "pending", implemented: true },
  
  // Support
  { module: "Support", method: "GET", path: "/tickets", description: "List support tickets", status: "pending", implemented: true },
];

export async function testEndpoint(test: EndpointTest): Promise<EndpointTest> {
  const resolvedPath = resolveApiPath(test.path);
  try {
    const response = await apiRequest(test.method, resolvedPath);
    const data = await response.json();

    return {
      ...test,
      path: resolvedPath,
      status: "success",
      statusCode: response.status,
      response: data,
    };
  } catch (error: any) {
    return {
      ...test,
      status: "error",
      path: resolvedPath,
      error: error.message || "Unknown error",
      statusCode: error.status,
    };
  }
}

export async function testAllEndpoints(): Promise<EndpointTest[]> {
  const results: EndpointTest[] = [];
  
  for (const test of ENDPOINT_INVENTORY) {
    // Skip endpoints that require parameters for now
    if (test.path.includes("{id}")) {
      results.push({ ...test, status: "skipped", error: "Requires ID parameter" });
      continue;
    }
    
    const result = await testEndpoint(test);
    results.push(result);
    
    // Small delay to avoid rate limiting
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  
  return results;
}

export function generateReport(results: EndpointTest[]): string {
  const byModule = results.reduce((acc, test) => {
    if (!acc[test.module]) acc[test.module] = [];
    acc[test.module].push(test);
    return acc;
  }, {} as Record<string, EndpointTest[]>);
  
  let report = "# Moio Platform API Endpoint Test Report\n\n";
  report += `**Total Endpoints:** ${results.length}\n`;
  report += `**Tested:** ${results.filter(t => t.status !== "pending" && t.status !== "skipped").length}\n`;
  report += `**Successful:** ${results.filter(t => t.status === "success").length}\n`;
  report += `**Failed:** ${results.filter(t => t.status === "error").length}\n`;
  report += `**Skipped:** ${results.filter(t => t.status === "skipped").length}\n\n`;
  
  for (const [module, tests] of Object.entries(byModule)) {
    report += `## ${module}\n\n`;
    
    for (const test of tests) {
      const icon = test.status === "success" ? "✅" : test.status === "error" ? "❌" : test.status === "skipped" ? "⏭️" : "⏸️";
      const impl = test.implemented ? "🟢 Implemented" : "🔴 Not Implemented";
      
      report += `${icon} **${test.method} ${test.path}**\n`;
      report += `   ${test.description} | ${impl}\n`;
      
      if (test.status === "success") {
        report += `   Status: ${test.statusCode}\n`;
      } else if (test.status === "error") {
        report += `   Error: ${test.error}\n`;
      }
      
      report += "\n";
    }
  }
  
  return report;
}
