import { apiV1 } from "@/lib/api";
import { apiRequest, fetchJson } from "@/lib/queryClient";
import type {
  CaptureEntry,
  CreateCaptureEntryRequest,
  ClassifySyncRequest,
  ClassifySyncResponse,
  ApplySyncResponse,
  ConfirmedActivityItem,
} from "./types";

export interface CaptureEntriesListResponse {
  entries: CaptureEntry[];
  pagination?: {
    current_page: number;
    total_pages: number;
    total_items: number;
    items_per_page: number;
  };
}

export const captureApi = {
  createEntry: async (payload: CreateCaptureEntryRequest): Promise<CaptureEntry> => {
    const res = await apiRequest("POST", apiV1("/capture/entries/"), {
      data: payload,
    });
    return res.json();
  },

  getEntry: async (id: string): Promise<CaptureEntry> => {
    return fetchJson<CaptureEntry>(apiV1(`/capture/entries/${id}/`));
  },

  listEntries: async (params?: {
    page?: number;
    limit?: number;
    status?: string;
    anchor_model?: string;
    anchor_id?: string;
  }): Promise<CaptureEntriesListResponse> => {
    return fetchJson<CaptureEntriesListResponse>(apiV1("/capture/entries/"), {
      page: params?.page ?? 1,
      limit: params?.limit ?? 20,
      status: params?.status ?? undefined,
      anchor_model: params?.anchor_model ?? undefined,
      anchor_id: params?.anchor_id ?? undefined,
    });
  },

  /** Classify capture text synchronously; returns entry.id and proposed_activity for preview. */
  classifySync: async (payload: ClassifySyncRequest): Promise<ClassifySyncResponse> => {
    const res = await apiRequest("POST", apiV1("/capture/classify-sync/"), {
      data: {
        raw_text: payload.raw_text,
        anchor_model: payload.anchor_model,
        anchor_id: payload.anchor_id,
      },
    });
    return res.json();
  },

  /** Apply the classified entry synchronously; creates activity and returns applied_refs. */
  applySync: async (
    entryId: string,
    options?: {
      confirmed_activities?: ConfirmedActivityItem[];
      deal_id?: string | null;
      contact_id?: string | null;
      customer_id?: string | null;
    }
  ): Promise<ApplySyncResponse> => {
    const data: Record<string, unknown> = {};
    if (options?.confirmed_activities) data.confirmed_activities = options.confirmed_activities;
    if (options?.deal_id) data.deal_id = options.deal_id;
    if (options?.contact_id) data.contact_id = options.contact_id;
    if (options?.customer_id) data.customer_id = options.customer_id;
    const res = await apiRequest("POST", apiV1(`/capture/entries/${entryId}/apply-sync/`), {
      data: Object.keys(data).length ? data : undefined,
    });
    return res.json();
  },
};

