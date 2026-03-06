import { useCallback, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest, fetchJson } from "@/lib/queryClient";
import { apiV1 } from "@/lib/api";
import type {
  CampaignFlowState,
  CampaignFlowStateResponse,
  CampaignTransitionAction,
  CampaignTransitionResponse,
  SelectTemplatePayload,
  ImportDataPayload,
  ConfigureMappingPayload,
  SetAudiencePayload,
  SetSchedulePayload,
} from "@shared/schema";

type TransitionPayload =
  | SelectTemplatePayload
  | ImportDataPayload
  | ConfigureMappingPayload
  | SetAudiencePayload
  | SetSchedulePayload
  | Record<string, never>;

interface UseCampaignFlowOptions {
  campaignId: string | null;
  enabled?: boolean;
  onTransitionSuccess?: (response: CampaignTransitionResponse) => void;
  onTransitionError?: (error: Error) => void;
}

interface UseCampaignFlowReturn {
  flowState: CampaignFlowStateResponse | null;
  isLoading: boolean;
  isError: boolean;
  error: Error | null;
  canDo: (action: CampaignTransitionAction) => boolean;
  executeTransition: (action: CampaignTransitionAction, payload?: TransitionPayload) => Promise<CampaignTransitionResponse>;
  isTransitioning: boolean;
  refetch: (overrideCampaignId?: string) => Promise<CampaignFlowStateResponse | null>;
}

export function useCampaignFlow(options: UseCampaignFlowOptions): UseCampaignFlowReturn {
  const { campaignId, enabled = true, onTransitionSuccess, onTransitionError } = options;
  const queryClient = useQueryClient();
  const [isTransitioning, setIsTransitioning] = useState(false);

  const flowStateQueryKey = campaignId ? [apiV1(`/campaigns/${campaignId}/flow-state/`)] : null;

  const flowStateQuery = useQuery<CampaignFlowStateResponse>({
    queryKey: flowStateQueryKey || ["disabled"],
    queryFn: () => fetchJson<CampaignFlowStateResponse>(apiV1(`/campaigns/${campaignId}/flow-state/`)),
    enabled: enabled && !!campaignId,
    staleTime: 5000,
    refetchOnWindowFocus: true,
    retry: false,
  });

  const transitionMutation = useMutation<
    CampaignTransitionResponse,
    Error,
    { action: CampaignTransitionAction; payload?: TransitionPayload }
  >({
    mutationFn: async ({ action, payload }) => {
      if (!campaignId) {
        throw new Error("Campaign ID is required");
      }

      const res = await apiRequest(
        "POST",
        apiV1(`/campaigns/${campaignId}/transitions/${action}`),
        { data: payload || {} }
      );
      return res.json();
    },
    onSuccess: (response) => {
      if (flowStateQueryKey) {
        queryClient.invalidateQueries({ queryKey: flowStateQueryKey });
      }
      queryClient.invalidateQueries({ queryKey: [apiV1("/campaigns/campaigns/")] });
      onTransitionSuccess?.(response);
    },
    onError: (error) => {
      onTransitionError?.(error);
    },
    onSettled: () => {
      setIsTransitioning(false);
    },
  });

  const canDo = useCallback(
    (action: CampaignTransitionAction): boolean => {
      if (!flowStateQuery.data) return false;
      return flowStateQuery.data.allowed_actions.includes(action);
    },
    [flowStateQuery.data]
  );

  const executeTransition = useCallback(
    async (action: CampaignTransitionAction, payload?: TransitionPayload): Promise<CampaignTransitionResponse> => {
      if (!campaignId) {
        throw new Error("Campaign ID is required");
      }

      setIsTransitioning(true);
      return transitionMutation.mutateAsync({ action, payload });
    },
    [campaignId, transitionMutation]
  );

  const refetch = useCallback(async (overrideCampaignId?: string): Promise<CampaignFlowStateResponse | null> => {
    const effectiveId = overrideCampaignId || campaignId;
    if (!effectiveId) {
      return null;
    }
    
    try {
      const queryKey = [apiV1(`/campaigns/${effectiveId}/flow-state/`)];
      await queryClient.invalidateQueries({ queryKey });
      const result = await queryClient.fetchQuery<CampaignFlowStateResponse>({
        queryKey,
        queryFn: () => fetchJson<CampaignFlowStateResponse>(apiV1(`/campaigns/${effectiveId}/flow-state/`)),
      });
      return result;
    } catch (error: unknown) {
      console.error("Failed to fetch flow state:", error);
      const apiError = error as { status?: number; message?: string };
      if (apiError.status === 404) {
        throw new Error("Campaign workflow not available yet. The campaign was created but advanced features are being set up.");
      }
      throw new Error(apiError.message || "Failed to load campaign state");
    }
  }, [queryClient, campaignId]);

  return {
    flowState: flowStateQuery.data ?? null,
    isLoading: flowStateQuery.isLoading,
    isError: flowStateQuery.isError,
    error: flowStateQuery.error,
    canDo,
    executeTransition,
    isTransitioning: isTransitioning || transitionMutation.isPending,
    refetch,
  };
}

export function useCreateCampaignDraft() {
  const queryClient = useQueryClient();

  return useMutation<
    { id: string; name: string },
    Error,
    { name: string; description?: string; channel: string; kind: string }
  >({
    mutationFn: async (data) => {
      const res = await apiRequest("POST", apiV1("/campaigns/campaigns/"), { data });
      if (!res.ok) {
        const status = res.status;
        if (status === 404) {
          throw new Error("Campaign creation endpoint not available. Please try again later.");
        } else if (status === 400) {
          const body = await res.json().catch(() => ({}));
          throw new Error(body.message || body.detail || "Invalid campaign data. Please check your inputs.");
        } else if (status >= 500) {
          throw new Error("Server error. Please try again later.");
        }
        throw new Error(`Failed to create campaign (${status})`);
      }
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [apiV1("/campaigns/campaigns/")] });
    },
  });
}

export function getFlowStateLabel(state: CampaignFlowState): string {
  const labels: Record<CampaignFlowState, string> = {
    DRAFT: "Draft",
    SELECT_TEMPLATE: "Select Template",
    IMPORT_DATA: "Import Data",
    CONFIGURE_MAPPING: "Configure Mapping",
    SET_AUDIENCE: "Set Audience",
    READY: "Ready",
    SCHEDULED: "Scheduled",
    ACTIVE: "Active",
    ENDED: "Ended",
    ARCHIVED: "Archived",
  };
  return labels[state] || state;
}

export function getFlowStateStep(state: CampaignFlowState): number {
  const steps: Record<CampaignFlowState, number> = {
    DRAFT: 1,
    SELECT_TEMPLATE: 2,
    IMPORT_DATA: 3,
    CONFIGURE_MAPPING: 4,
    SET_AUDIENCE: 5,
    READY: 6,
    SCHEDULED: 7,
    ACTIVE: 8,
    ENDED: 9,
    ARCHIVED: 10,
  };
  return steps[state] || 0;
}

export function isFlowStateActive(state: CampaignFlowState): boolean {
  return state === "ACTIVE";
}

export function isFlowStateEditable(state: CampaignFlowState): boolean {
  return ["DRAFT", "SELECT_TEMPLATE", "IMPORT_DATA", "CONFIGURE_MAPPING", "SET_AUDIENCE", "READY"].includes(state);
}
