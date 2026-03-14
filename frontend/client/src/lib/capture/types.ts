// Backend enum (moio_platform a8da10d): crm.deal | crm.contact | crm.client
// Note: backend normalizes crm.account -> crm.client for capture/timeline.
export type AnchorModel = "crm.deal" | "crm.contact" | "crm.client" | "crm.account";

export type CaptureEntryStatus =
  | "captured"
  | "classifying"
  | "classified"
  | "needs_review"
  | "reviewed"
  | "applying"
  | "applied"
  | "failed";

export type CaptureVisibility = "internal" | "confidential" | "restricted" | "public";

export interface CaptureEntryAppliedRef {
  model?: string;
  id: string;
  label?: string;
}

export interface CaptureEntry {
  id: string;
  raw_text?: string;
  status: CaptureEntryStatus | string;
  needs_review?: boolean;
  visibility?: CaptureVisibility | string;
  created_at?: string;
  updated_at?: string;

  summary?: string;
  confidence?: number;
  review_reasons?: string[];

  applied_refs?: CaptureEntryAppliedRef[];

  anchor_model?: AnchorModel | string;
  anchor_id?: string;

  /** Set after classification (sync or async). */
  suggested_activities?: ProposedActivity[];
  classification?: Record<string, unknown>;
  error_details?: Record<string, unknown>;
}

export interface CreateCaptureEntryRequest {
  raw_text: string;
  anchor_model: AnchorModel | string;
  anchor_id: string;
  visibility?: CaptureVisibility;
  idempotency_key?: string;
  // Optional: client-side flag; backend may ignore.
  needs_review?: boolean;
}

/** Request for POST /capture/classify-sync/ */
export interface ClassifySyncRequest {
  raw_text: string;
  anchor_model: AnchorModel | string;
  anchor_id: string;
}

/** Proposed activity from classify-sync (e.g. task with due date). */
export interface ProposedActivity {
  kind?: string;
  type?: string;
  title?: string;
  due_date?: string;
  due_at?: string;
  description?: string;
  body?: string;
  start_at?: string;
  end_at?: string;
  status?: "planned" | "completed";
  location?: string;
  attendees?: unknown[];
  reason?: string;
  needs_time_confirmation?: boolean;
  owner_id?: string | null;
  owner_name?: string | null;
  [key: string]: unknown;
}

/** Response from POST /capture/classify-sync/ */
export interface ClassifySyncResponse {
  entry: { id: string };
  classification?: Record<string, unknown>;
  suggested_activities?: ProposedActivity[];
  proposed_activity?: ProposedActivity;
  proposed_activities?: ProposedActivity[];
}

/** Item to send when applying with user-confirmed edits (dates, times, etc.). */
export interface ConfirmedActivityItem {
  kind: "task" | "event" | "deal";
  title: string;
  description?: string;
  due_at?: string;
  start_at?: string;
  end_at?: string;
  status?: "planned" | "completed";
  location?: string;
  attendees?: string[];
  owner_id?: string | null;
  proposed_value?: string | number;
  proposed_currency?: string;
}

/** Response from POST /capture/entries/<id>/apply-sync/ */
export interface ApplySyncResponse {
  applied_refs: CaptureEntryAppliedRef[];
}

