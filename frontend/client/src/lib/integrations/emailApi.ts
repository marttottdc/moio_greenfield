import { apiRequest, fetchJson } from "@/lib/queryClient";
import { apiV1 } from "@/lib/api";
import type {
  EmailAccount,
  EmailMessagesResponse,
  EmailMessage,
  IntegrationProvider,
  Ownership,
} from "./types";

const EMAIL_BASE = "/integrations/email";

export const emailApi = {
  accountsPath: () => apiV1(`${EMAIL_BASE}/accounts`),

  listAccounts: () => fetchJson<EmailAccount[]>(emailApi.accountsPath()),

  getAccount: (id: string) => fetchJson<EmailAccount>(apiV1(`${EMAIL_BASE}/accounts/${id}`)),

  deleteAccount: (id: string) => apiRequest("DELETE", apiV1(`${EMAIL_BASE}/accounts/${id}`)),

  enableAccount: (id: string) => apiRequest("POST", apiV1(`${EMAIL_BASE}/accounts/${id}/enable`)),

  disableAccount: (id: string) => apiRequest("POST", apiV1(`${EMAIL_BASE}/accounts/${id}/disable`)),

  health: (id: string) =>
    fetchJson<{ status: string; provider: IntegrationProvider }>(apiV1(`${EMAIL_BASE}/accounts/${id}/health`)),

  flowAccounts: (scope: Ownership) =>
    fetchJson<EmailAccount[]>(apiV1(`${EMAIL_BASE}/flow/accounts`), { scope }),

  oauthStart: async (provider: Extract<IntegrationProvider, "google" | "microsoft">, ownership: Ownership) => {
    const res = await apiRequest("POST", apiV1(`${EMAIL_BASE}/oauth/start`), {
      data: { provider, ownership },
    });
    return res.json() as Promise<{ authorize_url: string; state: string }>;
  },

  imapConnect: async (payload: {
    ownership: Ownership;
    email_address: string;
    username: string;
    password: string;
    host: string;
    port: number;
    use_ssl: boolean;
    smtp: {
      host: string;
      port: number;
      username: string;
      password: string;
      use_ssl: boolean;
    };
  }) => {
    const res = await apiRequest("POST", apiV1(`${EMAIL_BASE}/imap/connect`), { data: payload });
    return res.json() as Promise<{ ok: boolean; account_id: string }>;
  },

  listMessages: (accountId: string, params?: { cursor?: string; page_size?: number }) =>
    fetchJson<EmailMessagesResponse>(apiV1(`${EMAIL_BASE}/accounts/${accountId}/messages`), params),

  getMessage: (accountId: string, messageId: string) =>
    fetchJson<EmailMessage>(apiV1(`${EMAIL_BASE}/accounts/${accountId}/messages/${messageId}`)),

  sendMessage: async (
    accountId: string,
    payload: {
      to: string[];
      cc?: string[];
      bcc?: string[];
      subject?: string;
      text?: string;
      html?: string;
      attachments?: Array<{
        filename: string;
        mime_type: string;
        content_base64: string;
      }>;
    }
  ) => {
    const res = await apiRequest("POST", apiV1(`${EMAIL_BASE}/accounts/${accountId}/send`), { data: payload });
    return res.json() as Promise<{ ok: boolean; id?: string }>;
  },

  deleteMessage: (accountId: string, messageId: string) =>
    apiRequest("DELETE", apiV1(`${EMAIL_BASE}/accounts/${accountId}/messages/${messageId}`)),
};

