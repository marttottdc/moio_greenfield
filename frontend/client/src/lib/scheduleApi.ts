import { apiRequest } from "@/lib/queryClient";
import { apiV1 } from "@/lib/api";
import type { FlowSchedule, ScheduleConfig } from "@/components/flow/triggers/types";

export interface ScheduleApiResponse {
  id: string;
  flow: string;
  schedule_type: "cron" | "interval" | "one_off";
  cron_expression: string | null;
  interval_seconds: number | null;
  run_at: string | null;
  timezone: string;
  is_active: boolean;
  next_run_at: string | null;
  last_run_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface CreateScheduleRequest {
  schedule_type: "cron" | "interval" | "one_off";
  cron_expression?: string | null;
  interval_seconds?: number | null;
  run_at?: string | null;
  timezone: string;
  is_active: boolean;
}

export async function getFlowSchedule(flowId: string): Promise<ScheduleApiResponse | null> {
  try {
    const res = await apiRequest("GET", apiV1(`/flows/${flowId}/schedules/`));
    if (!res.ok) {
      if (res.status === 404) {
        return null;
      }
      throw new Error(`Failed to get schedule: ${res.status}`);
    }
    const data = await res.json();
    if (Array.isArray(data) && data.length > 0) {
      return data[0];
    }
    if (data && typeof data === "object" && data.id) {
      return data as ScheduleApiResponse;
    }
    return null;
  } catch (error) {
    console.error("[ScheduleAPI] Error fetching schedule:", error);
    return null;
  }
}

export async function createFlowSchedule(
  flowId: string,
  config: ScheduleConfig,
  isActive: boolean = true
): Promise<ScheduleApiResponse> {
  const payload: CreateScheduleRequest = {
    schedule_type: config.schedule_type,
    timezone: config.timezone,
    is_active: isActive,
  };

  if (config.schedule_type === "cron") {
    payload.cron_expression = config.cron_expression;
  } else if (config.schedule_type === "interval") {
    payload.interval_seconds = config.interval_seconds;
  } else if (config.schedule_type === "one_off") {
    payload.run_at = config.run_at;
  }

  console.log("[ScheduleAPI] Creating schedule:", { flowId, payload });
  const res = await apiRequest("POST", apiV1(`/flows/${flowId}/schedules/`), { data: payload });
  if (!res.ok) {
    const errorText = await res.text();
    throw new Error(`Failed to create schedule: ${res.status} - ${errorText}`);
  }
  return await res.json();
}

export async function updateFlowSchedule(
  flowId: string,
  scheduleId: string,
  config: ScheduleConfig,
  isActive: boolean = true
): Promise<ScheduleApiResponse> {
  const payload: CreateScheduleRequest = {
    schedule_type: config.schedule_type,
    timezone: config.timezone,
    is_active: isActive,
  };

  if (config.schedule_type === "cron") {
    payload.cron_expression = config.cron_expression;
  } else if (config.schedule_type === "interval") {
    payload.interval_seconds = config.interval_seconds;
  } else if (config.schedule_type === "one_off") {
    payload.run_at = config.run_at;
  }

  console.log("[ScheduleAPI] Updating schedule:", { flowId, scheduleId, payload });
  const res = await apiRequest("PUT", apiV1(`/flows/${flowId}/schedules/${scheduleId}/`), { data: payload });
  if (!res.ok) {
    const errorText = await res.text();
    throw new Error(`Failed to update schedule: ${res.status} - ${errorText}`);
  }
  return await res.json();
}

export async function deleteFlowSchedule(flowId: string, scheduleId: string): Promise<void> {
  console.log("[ScheduleAPI] Deleting schedule:", { flowId, scheduleId });
  const res = await apiRequest("DELETE", apiV1(`/flows/${flowId}/schedules/${scheduleId}/`));
  if (!res.ok && res.status !== 404) {
    const errorText = await res.text();
    throw new Error(`Failed to delete schedule: ${res.status} - ${errorText}`);
  }
}

export async function toggleFlowSchedule(flowId: string, scheduleId: string): Promise<ScheduleApiResponse> {
  console.log("[ScheduleAPI] Toggling schedule:", { flowId, scheduleId });
  const res = await apiRequest("POST", apiV1(`/flows/${flowId}/schedules/${scheduleId}/toggle/`));
  if (!res.ok) {
    const errorText = await res.text();
    throw new Error(`Failed to toggle schedule: ${res.status} - ${errorText}`);
  }
  return await res.json();
}

export function configToSchedulePayload(config: ScheduleConfig): Partial<CreateScheduleRequest> {
  return {
    schedule_type: config.schedule_type,
    cron_expression: config.schedule_type === "cron" ? config.cron_expression : null,
    interval_seconds: config.schedule_type === "interval" ? config.interval_seconds : null,
    run_at: config.schedule_type === "one_off" ? config.run_at : null,
    timezone: config.timezone,
  };
}

export function scheduleToConfig(schedule: ScheduleApiResponse): ScheduleConfig {
  return {
    schedule_type: schedule.schedule_type,
    cron_expression: schedule.cron_expression,
    interval_seconds: schedule.interval_seconds,
    run_at: schedule.run_at,
    timezone: schedule.timezone,
  };
}

export function isScheduleConfigEqual(a: ScheduleConfig, b: ScheduleConfig): boolean {
  if (a.schedule_type !== b.schedule_type) return false;
  if (a.timezone !== b.timezone) return false;
  
  switch (a.schedule_type) {
    case "cron":
      return a.cron_expression === b.cron_expression;
    case "interval":
      return a.interval_seconds === b.interval_seconds;
    case "one_off":
      return a.run_at === b.run_at;
    default:
      return true;
  }
}
