import { apiRequest } from "./queryClient";
import { apiV1, getRefreshToken, setAccessToken, setRefreshToken, type QueryParams } from "./api";

export interface TestResult {
  method: string;
  path: string;
  status: number;
  statusText: string;
  success: boolean;
  responseBody?: unknown;
  errorMessage?: string;
  errorDetails?: string;
  timestamp: string;
}

export interface TestCategory {
  category: string;
  results: TestResult[];
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

function extractIdFromObject(value: unknown): string | undefined {
  if (!value || typeof value !== "object") return undefined;

  const record = value as Record<string, unknown>;
  if (typeof record.id === "string") return record.id;
  if (typeof record.uuid === "string") return record.uuid;
  if (typeof record.pk === "string") return record.pk;

  if (record.data && typeof record.data === "object") {
    const nested = record.data as Record<string, unknown>;
    if (typeof nested.id === "string") return nested.id;
  }

  return undefined;
}

function extractIdFromList(body: unknown): string | undefined {
  if (Array.isArray(body) && body.length > 0) {
    return extractIdFromObject(body[0]);
  }

  if (body && typeof body === "object") {
    const record = body as Record<string, unknown>;
    if (Array.isArray(record.results) && record.results.length > 0) {
      return extractIdFromObject(record.results[0]);
    }
  }

  return undefined;
}

function extractTokens(body: unknown) {
  if (!body || typeof body !== "object") return { accessToken: undefined as string | undefined, refreshToken: undefined as string | undefined };

  const data = body as Record<string, unknown>;
  const accessToken =
    (typeof data.access === "string" && data.access) ||
    (typeof data.access_token === "string" && data.access_token) ||
    (typeof data.token === "string" && data.token) ||
    undefined;
  const refreshToken =
    (typeof data.refresh === "string" && data.refresh) ||
    (typeof data.refresh_token === "string" && data.refresh_token) ||
    undefined;

  return { accessToken, refreshToken };
}

async function testEndpoint(
  method: string,
  path: string,
  options?: {
    data?: unknown;
    params?: QueryParams;
    headers?: HeadersInit;
  }
): Promise<TestResult> {
  const timestamp = new Date().toISOString();
  const resolvedPath = resolveApiPath(path);

  try {
    const res = await apiRequest(method, resolvedPath, options);
    const contentType = res.headers.get("content-type");
    
    let responseBody: unknown;
    if (contentType?.includes("application/json")) {
      try {
        responseBody = await res.json();
      } catch {
        responseBody = null;
      }
    } else {
      responseBody = await res.text();
    }

    return {
      method,
      path: resolvedPath,
      status: res.status,
      statusText: res.statusText,
      success: res.ok,
      responseBody,
      timestamp,
    };
  } catch (error: unknown) {
    const errorMessage = error instanceof Error ? error.message : String(error);
    const errorDetails = error instanceof Error && "body" in error ? String(error.body) : undefined;
    
    return {
      method,
      path: resolvedPath,
      status: error instanceof Error && "status" in error ? Number(error.status) : 0,
      statusText: "Error",
      success: false,
      errorMessage,
      errorDetails,
      timestamp,
    };
  }
}

export async function testAuthEndpoints(credentials?: {
  username: string;
  password: string;
}): Promise<TestCategory> {
  const results: TestResult[] = [];
  let refreshToken = getRefreshToken();

  if (credentials) {
    results.push(
      await testEndpoint("POST", "/auth/login/", {
        data: credentials,
      })
    );

    const loginResult = results[results.length - 1];
    if (loginResult.success) {
      const { accessToken, refreshToken: loginRefreshToken } = extractTokens(loginResult.responseBody);

      if (accessToken) {
        setAccessToken(accessToken);
      }

      if (loginRefreshToken) {
        setRefreshToken(loginRefreshToken);
        refreshToken = loginRefreshToken;
      }
    }
  }

  results.push(await testEndpoint("GET", "/auth/me/"));

  if (refreshToken) {
    results.push(
      await testEndpoint("POST", "/auth/refresh/", {
        data: { refresh: refreshToken },
      })
    );
  } else {
    results.push({
      method: "POST",
      path: "/auth/refresh/",
      status: 0,
      statusText: "Skipped",
      success: false,
      errorMessage: "No refresh token available for refresh request",
      timestamp: new Date().toISOString(),
    });
  }

  // Skip logout test to prevent ending the user's session
  // results.push(await testEndpoint("POST", "/auth/logout/"));

  return {
    category: "Authentication",
    results,
  };
}

export async function testContactsEndpoints(): Promise<TestCategory> {
  const results: TestResult[] = [];

  results.push(await testEndpoint("GET", "/crm/contacts/"));

  results.push(await testEndpoint("GET", "/crm/contacts/", { params: { page: 1, page_size: 10 } }));

  // Test filtering by type
  results.push(await testEndpoint("GET", "/crm/contacts/", { params: { type: "Lead" } }));

  // Create a comprehensive test contact
  const createResult = await testEndpoint("POST", "/crm/contacts/", {
    data: {
      first_name: "API",
      last_name: "Test Contact",
      email: `api.test.${Date.now()}@moio-testing.com`,
      phone: "+1234567890",
      company: "Moio Test Corp",
      type: "Lead",
      tags: ["api-test", "automated"],
    },
  });
  results.push(createResult);

  let contactId = extractIdFromObject(createResult.responseBody) ?? extractIdFromList(createResult.responseBody);

  if (contactId) {
    results.push(await testEndpoint("GET", `/crm/contacts/${contactId}/`));

    // Test comprehensive update (backend expects PATCH)
    results.push(
      await testEndpoint("PATCH", `/crm/contacts/${contactId}/`, {
        data: {
          first_name: "Updated API",
          last_name: "Updated Test",
          email: `api.test.${Date.now()}@moio-testing.com`,
          phone: "+1234567890",
          type: "Customer",
          company: "Moio Updated Corp",
          tags: ["api-test", "automated", "updated"],
        },
      })
    );

    // Verify the update worked
    results.push(await testEndpoint("GET", `/crm/contacts/${contactId}/`));

    // Clean up - delete the test contact
    results.push(await testEndpoint("DELETE", `/crm/contacts/${contactId}/`));
  } else {
    results.push({
      method: "GET",
      path: "/crm/contacts/{id}/",
      status: 0,
      statusText: "Skipped",
      success: false,
      errorMessage: "No contact ID available from POST /crm/contacts/",
      timestamp: new Date().toISOString(),
    });

    results.push({
      method: "PATCH",
      path: "/crm/contacts/{id}/",
      status: 0,
      statusText: "Skipped",
      success: false,
      errorMessage: "No contact ID available from POST /crm/contacts/",
      timestamp: new Date().toISOString(),
    });

    results.push({
      method: "DELETE",
      path: "/crm/contacts/{id}/",
      status: 0,
      statusText: "Skipped",
      success: false,
      errorMessage: "No contact ID available from POST /crm/contacts/",
      timestamp: new Date().toISOString(),
    });
  }

  results.push(await testEndpoint("GET", "/crm/contacts/export/"));

  return {
    category: "Contacts",
    results,
  };
}

export async function testSettingsEndpoints(): Promise<TestCategory> {
  const results: TestResult[] = [];

  // Moio user management (GET /api/v1/users/ returns array)
  results.push(await testEndpoint("GET", "/users/"));

  // Create a test user (MoioUserWriteRequest: email, username required; first_name, last_name, role, password optional)
  const createUserResult = await testEndpoint("POST", "/users/", {
    data: {
      username: `apitest_${Date.now()}`,
      email: `apitest.${Date.now()}@moio-testing.com`,
      password: "TestPassword123!",
      first_name: "API",
      last_name: "Test User",
      role: "member",
      is_active: true,
    },
  });
  results.push(createUserResult);

  let userId =
    extractIdFromObject(createUserResult.responseBody) ?? extractIdFromList(createUserResult.responseBody);

  if (userId) {
    results.push(await testEndpoint("GET", `/users/${userId}/`));
    results.push(
      await testEndpoint("PATCH", `/users/${userId}/`, {
        data: {
          last_name: "TestPatched",
          role: "member",
        },
      })
    );
    results.push(await testEndpoint("DELETE", `/users/${userId}/`));
  }

  // Test organization settings
  results.push(await testEndpoint("GET", "/settings/organization"));

  // Update organization settings
  results.push(
    await testEndpoint("PATCH", "/settings/organization", {
      data: {
        name: "Moio Test Organization (API Test)",
        timezone: "UTC",
      },
    })
  );

  // Test roles
  results.push(await testEndpoint("GET", "/settings/roles"));

  // Test preferences (backend supports GET and PATCH only)
  results.push(await testEndpoint("GET", "/settings/preferences"));

  // Update preferences
  results.push(
    await testEndpoint("PATCH", "/settings/preferences", {
      data: {
        language: "en",
        timezone: "UTC",
        notifications_enabled: true,
      },
    })
  );

  // Test integrations
  results.push(await testEndpoint("GET", "/settings/integrations"));

  return {
    category: "Settings & Admin",
    results,
  };
}

export async function testDealsEndpoints(): Promise<TestCategory> {
  const results: TestResult[] = [];

  // List all deals (backend under /api/v1/crm/deals/)
  results.push(await testEndpoint("GET", "/crm/deals/"));

  // Create a comprehensive test deal
  const createResult = await testEndpoint("POST", "/crm/deals/", {
    data: {
      title: `API Test Deal - ${Date.now()}`,
      stage: "prospecting",
      value: 5000,
      currency: "USD",
      expected_close_date: new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString().split('T')[0],
      description: "Automated API test deal",
    },
  });
  results.push(createResult);

  let dealId = extractIdFromObject(createResult.responseBody) ?? extractIdFromList(createResult.responseBody);

  if (dealId) {
    // Get deal details
    results.push(await testEndpoint("GET", `/crm/deals/${dealId}/`));

    // Update deal - move to next stage
    results.push(
      await testEndpoint("PATCH", `/crm/deals/${dealId}/`, {
        data: {
          stage: "qualification",
          value: 7500,
        },
      })
    );

    // Update again - move to proposal stage
    results.push(
      await testEndpoint("PATCH", `/crm/deals/${dealId}/`, {
        data: {
          stage: "proposal",
        },
      })
    );

    // Verify final state
    results.push(await testEndpoint("GET", `/crm/deals/${dealId}/`));
  }

  return {
    category: "Deals",
    results,
  };
}

export async function testCampaignsEndpoints(): Promise<TestCategory> {
  const results: TestResult[] = [];

  // Backend: list/create at /api/v1/campaigns/campaigns/
  const listResult = await testEndpoint("GET", "/campaigns/campaigns/");
  results.push(listResult);

  // Template catalogue (CRM templates under /api/v1/crm/templates/)
  results.push(await testEndpoint("GET", "/crm/templates/"));

  // Try creating a draft campaign
  const createResult = await testEndpoint("POST", "/campaigns/campaigns/", {
    data: {
      name: `API Test Campaign - ${Date.now()}`,
      description: "Automated test campaign via API",
      channel: "whatsapp",
      kind: "broadcast",
      status: "draft",
      content: {
        body: "API smoke test message",
      },
    },
  });
  results.push(createResult);

  let campaignId =
    extractIdFromObject(createResult.responseBody) ||
    extractIdFromList(createResult.responseBody) ||
    extractIdFromList(listResult.responseBody);

  if (campaignId) {
    results.push(await testEndpoint("GET", `/campaigns/campaigns/${campaignId}/`));

    results.push(
      await testEndpoint("POST", `/campaigns/campaigns/${campaignId}/send/`, {
        data: {
          mode: "test",
          confirm: true,
        },
      })
    );

    results.push(await testEndpoint("GET", `/campaigns/campaigns/${campaignId}/analytics/`));
  } else {
    const timestamp = new Date().toISOString();
    results.push({
      method: "GET",
      path: "/campaigns/campaigns/{id}/",
      status: 0,
      statusText: "Skipped",
      success: false,
      errorMessage: "No campaign ID available from list or creation",
      timestamp,
    });
    results.push({
      method: "POST",
      path: "/campaigns/campaigns/{id}/send/",
      status: 0,
      statusText: "Skipped",
      success: false,
      errorMessage: "No campaign ID available from list or creation",
      timestamp,
    });
    results.push({
      method: "GET",
      path: "/campaigns/campaigns/{id}/analytics/",
      status: 0,
      statusText: "Skipped",
      success: false,
      errorMessage: "No campaign ID available from list or creation",
      timestamp,
    });
  }

  return {
    category: "Campaigns",
    results,
  };
}

export async function testFlowsEndpoints(): Promise<TestCategory> {
  const results: TestResult[] = [];

  // List all flows
  results.push(await testEndpoint("GET", "/flows/"));

  // Get execution history (backend: /flows/executions/ not runs)
  results.push(await testEndpoint("GET", "/flows/executions/"));

  // Create a comprehensive test workflow
  const createResult = await testEndpoint("POST", "/flows/", {
    data: {
      name: `API Test Flow - ${Date.now()}`,
      trigger_type: "manual",
      description: "Automated test workflow via API",
      definition: {
        nodes: [
          { id: "start", type: "trigger", config: { trigger_type: "manual" } },
          { id: "action1", type: "action", config: { action: "send_notification" } },
        ],
        edges: [
          { source: "start", target: "action1" },
        ],
      },
    },
  });
  results.push(createResult);

  let flowId = extractIdFromObject(createResult.responseBody) ?? extractIdFromList(createResult.responseBody);

  if (flowId) {
    // Get flow details
    results.push(await testEndpoint("GET", `/flows/${flowId}/`));

    // Update the workflow (backend: POST .../save/ or PATCH, not PUT on flow root)
    results.push(
      await testEndpoint("POST", `/flows/${flowId}/save/`, {
        data: {
          name: `Updated API Test Flow - ${Date.now()}`,
          description: "Updated automated test workflow",
          definition: {
            nodes: [
              { id: "start", type: "trigger", config: { trigger_type: "manual" } },
              { id: "action1", type: "action", config: { action: "send_email" } },
              { id: "action2", type: "action", config: { action: "create_task" } },
            ],
            edges: [
              { source: "start", target: "action1" },
              { source: "action1", target: "action2" },
            ],
          },
        },
      })
    );

    // Toggle workflow active state (backend: .../toggle-active/ not activate)
    results.push(await testEndpoint("POST", `/flows/${flowId}/toggle-active/`));

    // Preview/test workflow run (backend: .../preview/ not test)
    results.push(await testEndpoint("POST", `/flows/${flowId}/preview/`));
  }

  return {
    category: "Flows & Automation",
    results,
  };
}

export async function testCommunicationsEndpoints(): Promise<TestCategory> {
  const results: TestResult[] = [];

  // Backend uses conversations/ not chats
  const conversationsResult = await testEndpoint("GET", "/crm/communications/conversations/");
  results.push(conversationsResult);

  const conversationId = extractIdFromList(conversationsResult.responseBody);

  if (conversationId) {
    results.push(await testEndpoint("GET", `/crm/communications/conversations/${conversationId}/messages/`, { params: { page_size: 10 } }));

    results.push(
      await testEndpoint("POST", `/crm/communications/conversations/${conversationId}/messages/`, {
        data: {
          content: "API tester ping",
          channel: "whatsapp",
        },
      })
    );
  } else {
    const timestamp = new Date().toISOString();
    results.push({
      method: "GET",
      path: "/crm/communications/conversations/{id}/messages/",
      status: 0,
      statusText: "Skipped",
      success: false,
      errorMessage: "No conversation ID available for message lookups",
      timestamp,
    });
    results.push({
      method: "POST",
      path: "/crm/communications/conversations/{id}/messages/",
      status: 0,
      statusText: "Skipped",
      success: false,
      errorMessage: "No conversation ID available for message lookups",
      timestamp,
    });
  }

  const channelsResult = await testEndpoint("GET", "/crm/communications/channels/");
  results.push(channelsResult);

  const channelId = extractIdFromList(channelsResult.responseBody);
  if (channelId) {
    results.push(await testEndpoint("POST", `/crm/communications/channels/${channelId}/test/`));
  } else {
    results.push({
      method: "POST",
      path: "/crm/communications/channels/{id}/test/",
      status: 0,
      statusText: "Skipped",
      success: false,
      errorMessage: "No channel ID available to trigger test",
      timestamp: new Date().toISOString(),
    });
  }

  return {
    category: "Communications",
    results,
  };
}

export async function testDashboardEndpoints(): Promise<TestCategory> {
  const results: TestResult[] = [];

  results.push(await testEndpoint("GET", "/crm/dashboard/summary/"));

  return {
    category: "Dashboard",
    results,
  };
}

export async function testPlatformExperienceEndpoints(): Promise<TestCategory> {
  const results: TestResult[] = [];

  results.push(await testEndpoint("GET", "/content/navigation"));

  results.push(await testEndpoint("GET", "/engagement/topics"));

  return {
    category: "Platform Experience",
    results,
  };
}

export async function runAllTests(credentials?: {
  username: string;
  password: string;
}): Promise<TestCategory[]> {
  const categories: TestCategory[] = [];

  console.log("Starting API endpoint tests...");

  const authTests = await testAuthEndpoints(credentials);
  categories.push(authTests);
  console.log(`✓ Completed ${authTests.category} tests`);

  const contactsTests = await testContactsEndpoints();
  categories.push(contactsTests);
  console.log(`✓ Completed ${contactsTests.category} tests`);

  const settingsTests = await testSettingsEndpoints();
  categories.push(settingsTests);
  console.log(`✓ Completed ${settingsTests.category} tests`);

  const dealsTests = await testDealsEndpoints();
  categories.push(dealsTests);
  console.log(`✓ Completed ${dealsTests.category} tests`);

  const campaignsTests = await testCampaignsEndpoints();
  categories.push(campaignsTests);
  console.log(`✓ Completed ${campaignsTests.category} tests`);

  const flowsTests = await testFlowsEndpoints();
  categories.push(flowsTests);
  console.log(`✓ Completed ${flowsTests.category} tests`);

  const commsTests = await testCommunicationsEndpoints();
  categories.push(commsTests);
  console.log(`✓ Completed ${commsTests.category} tests`);

  const dashboardTests = await testDashboardEndpoints();
  categories.push(dashboardTests);
  console.log(`✓ Completed ${dashboardTests.category} tests`);

  const platformTests = await testPlatformExperienceEndpoints();
  categories.push(platformTests);
  console.log(`✓ Completed ${platformTests.category} tests`);

  console.log("All API endpoint tests completed!");

  return categories;
}

export function generateMarkdownReport(categories: TestCategory[]): string {
  let markdown = "# Moio Platform API Test Report\n\n";
  markdown += `**Generated:** ${new Date().toISOString()}\n\n`;
  markdown += "---\n\n";

  markdown += "## Summary\n\n";
  
  let totalTests = 0;
  let successfulTests = 0;
  let failedTests = 0;
  
  categories.forEach((category) => {
    category.results.forEach((result) => {
      totalTests++;
      if (result.success) {
        successfulTests++;
      } else {
        failedTests++;
      }
    });
  });

  markdown += `- **Total Endpoints Tested:** ${totalTests}\n`;
  markdown += `- **Successful:** ${successfulTests} ✅\n`;
  markdown += `- **Failed/Not Implemented:** ${failedTests} ❌\n\n`;

  markdown += "---\n\n";

  categories.forEach((category) => {
    markdown += `## ${category.category}\n\n`;
    markdown += "| Method | Endpoint | Status | Result |\n";
    markdown += "|--------|----------|--------|--------|\n";

    category.results.forEach((result) => {
      const statusIcon = result.success ? "✅" : result.status === 404 ? "⚠️" : "❌";
      const statusText = result.success ? `${result.status} ${result.statusText}` : `${result.status} ${result.errorMessage || result.statusText}`;
      
      markdown += `| ${result.method} | \`${result.path}\` | ${statusText} | ${statusIcon} |\n`;
    });

    markdown += "\n";

    const successfulResults = category.results.filter((r) => r.success);
    if (successfulResults.length > 0) {
      markdown += `### Successful Responses\n\n`;
      
      successfulResults.forEach((result) => {
        markdown += `#### ${result.method} ${result.path}\n\n`;
        markdown += "```json\n";
        
        if (result.responseBody && typeof result.responseBody === "object") {
          if (Array.isArray(result.responseBody)) {
            const firstItem = result.responseBody[0];
            markdown += JSON.stringify({ 
              count: result.responseBody.length,
              first_item: firstItem 
            }, null, 2);
          } else {
            markdown += JSON.stringify(result.responseBody, null, 2);
          }
        } else {
          markdown += String(result.responseBody);
        }
        
        markdown += "\n```\n\n";
      });
    }

    const failedResults = category.results.filter((r) => !r.success);
    if (failedResults.length > 0) {
      markdown += `### Failed/Not Implemented Endpoints\n\n`;
      
      failedResults.forEach((result) => {
        markdown += `#### ${result.method} ${result.path}\n\n`;
        markdown += `- **Status:** ${result.status}\n`;
        markdown += `- **Error:** ${result.errorMessage || result.statusText}\n`;
        
        if (result.errorDetails) {
          markdown += `- **Details:**\n\n`;
          markdown += "```\n";
          markdown += result.errorDetails;
          markdown += "\n```\n";
        }
        
        markdown += "\n";
      });
    }

    markdown += "---\n\n";
  });

  markdown += "## Endpoints from MOIO_PUBLIC_API_REFERENCE.md Not Yet Implemented\n\n";
  markdown += "The following endpoints are documented in the public API reference but may not be implemented in the backend:\n\n";

  markdown += "### Platform Experience\n";
  markdown += "- `GET /content/pages/{slug}`\n";
  markdown += "- `POST /conversations/session`\n";
  markdown += "- `POST /meetings/slots`\n\n";

  markdown += "### Settings\n";
  markdown += "- `POST /settings/integrations/{id}/connect`\n\n";

  markdown += "### Contacts\n";
  markdown += "- `POST /contacts/import`\n\n";

  return markdown;
}
