import { apiV1 } from "@/lib/api";
import { fetchJson } from "@/lib/queryClient";
import type { TimelineItem, TimelineResponse } from "./types";

function normalizeTimelineResponse(data: any): TimelineResponse {
  if (data && Array.isArray(data.items)) {
    return {
      items: data.items as TimelineItem[],
      next_cursor: data.next_cursor ?? null,
    };
  }

  // Fallback: some APIs might return `{results:[], next:...}`.
  if (data && Array.isArray(data.results)) {
    return {
      items: data.results as TimelineItem[],
      next_cursor: data.next_cursor ?? data.next ?? null,
    };
  }

  return { items: [], next_cursor: null };
}

export const timelineApi = {
  // Backend (moio_platform a8da10d) implements an anchor-scoped timeline:
  // GET /api/v1/timeline/?anchor_model=crm.deal|crm.contact|crm.client&anchor_id=...
  listForAnchor: async (params: {
    anchor_model: string;
    anchor_id: string;
    limit?: number;
    cursor?: string | null;
  }): Promise<TimelineResponse> => {
    const data = await fetchJson<any>(apiV1("/timeline/"), {
      anchor_model: params.anchor_model,
      anchor_id: params.anchor_id,
      limit: params.limit ?? 20,
      cursor: params.cursor ?? undefined,
    });
    return normalizeTimelineResponse(data);
  },

  // Kept for backwards-compatibility with earlier frontend iterations.
  // Most backends require anchor_model+anchor_id for this endpoint.
  listGlobal: async (params?: { limit?: number; cursor?: string | null }): Promise<TimelineResponse> => {
    const data = await fetchJson<any>(apiV1("/timeline/"), {
      limit: params?.limit ?? 20,
      cursor: params?.cursor ?? undefined,
    });
    return normalizeTimelineResponse(data);
  },
};

