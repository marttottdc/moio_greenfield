import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "@/lib/queryClient";

export interface WebhookHandler {
  name: string;
  path?: string;
  description?: string;
}

export function useWebhookHandlers() {
  return useQuery<WebhookHandler[]>({
    queryKey: ["/api/v1/resources/webhooks/handlers/"],
    queryFn: async () => {
      const response = await apiRequest("GET", "/api/v1/resources/webhooks/handlers/", {});
      const data = await response.json();
      // API returns { handlers: [...] }
      return Array.isArray(data) ? data : data?.handlers || data?.results || [];
    },
    staleTime: 5 * 60 * 1000,
  });
}
