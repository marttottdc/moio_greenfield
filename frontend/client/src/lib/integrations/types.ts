// Shared integration types for Email and Calendar

export type IntegrationProvider = "google" | "microsoft" | "imap";
export type Ownership = "tenant" | "user";

export interface ExternalAccount {
  id: string;
  provider: IntegrationProvider;
  ownership: Ownership;
  email_address: string;
  is_active: boolean;
  owner_user: string | null;
}

export interface EmailAccount {
  id: string;
  inbox: string;
  external_account: ExternalAccount;
}

export interface CalendarAccount {
  id: string;
  calendar_id: string;
  external_account: ExternalAccount;
}

export interface EmailAttachment {
  filename: string;
  mime_type: string;
  size?: number;
  content_base64?: string;
}

export interface EmailMessage {
  id: string;
  thread_id?: string;
  from: string;
  to: string[];
  cc?: string[];
  bcc?: string[];
  subject?: string;
  text?: string;
  html?: string;
  attachments?: EmailAttachment[];
  received_at?: string;
}

export interface EmailMessagesResponse {
  items: EmailMessage[];
  next_cursor: string | null;
}

export interface CalendarEvent {
  id: string;
  title: string;
  start: string;
  end: string;
  attendees?: string[];
}

export interface CalendarEventsResponse {
  items: CalendarEvent[];
  next_cursor: string | null;
}

export interface ErrorPayload {
  error?: { code?: string; message?: string } | string;
  message?: string;
  detail?: string;
}

