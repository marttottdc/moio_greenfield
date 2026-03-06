import { apiRequest, fetchJson } from "@/lib/queryClient";
import { apiV1 } from "@/lib/api";
import type {
  CalendarAccount,
  CalendarEvent,
  CalendarEventsResponse,
  IntegrationProvider,
  Ownership,
} from "./types";

const CAL_BASE = "/integrations/calendar";

export const calendarApi = {
  accountsPath: () => apiV1(`${CAL_BASE}/accounts`),

  listAccounts: () => fetchJson<CalendarAccount[]>(calendarApi.accountsPath()),

  getAccount: (id: string) => fetchJson<CalendarAccount>(apiV1(`${CAL_BASE}/accounts/${id}`)),

  deleteAccount: (id: string) => apiRequest("DELETE", apiV1(`${CAL_BASE}/accounts/${id}`)),

  health: (id: string) =>
    fetchJson<{ status: string; provider: IntegrationProvider }>(apiV1(`${CAL_BASE}/accounts/${id}/health`)),

  flowAccounts: (scope: Ownership) =>
    fetchJson<CalendarAccount[]>(apiV1(`${CAL_BASE}/flow/accounts`), { scope }),

  listEvents: (
    accountId: string,
    params?: { start?: string; end?: string; cursor?: string; page_size?: number }
  ) => fetchJson<CalendarEventsResponse>(apiV1(`${CAL_BASE}/accounts/${accountId}/events`), params),

  getEvent: (accountId: string, eventId: string) =>
    fetchJson<CalendarEvent>(apiV1(`${CAL_BASE}/accounts/${accountId}/events/${eventId}`)),

  createEvent: async (
    accountId: string,
    payload: { title: string; start: string; end: string; attendees?: string[] }
  ) => {
    const res = await apiRequest("POST", apiV1(`${CAL_BASE}/accounts/${accountId}/events`), { data: payload });
    return res.json() as Promise<{ ok: boolean; id: string }>;
  },

  updateEvent: async (
    accountId: string,
    eventId: string,
    payload: Partial<{ title: string; start: string; end: string; attendees: string[] }>
  ) => {
    const res = await apiRequest("PATCH", apiV1(`${CAL_BASE}/accounts/${accountId}/events/${eventId}`), { data: payload });
    return res.json() as Promise<CalendarEvent>;
  },

  deleteEvent: (accountId: string, eventId: string) =>
    apiRequest("DELETE", apiV1(`${CAL_BASE}/accounts/${accountId}/events/${eventId}`)),
};

