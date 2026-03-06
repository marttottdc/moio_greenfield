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
  type?: string;
  title?: string;
  due_date?: string;
  description?: string;
  [key: string]: unknown;
}

/** Response from POST /capture/classify-sync/ */
export interface ClassifySyncResponse {
  entry: { id: string };
  classification?: Record<string, unknown>;
  proposed_activity?: ProposedActivity;
}

/** Response from POST /capture/entries/<id>/apply-sync/ */
export interface ApplySyncResponse {
  applied_refs: CaptureEntryAppliedRef[];
}

