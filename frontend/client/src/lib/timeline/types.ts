import type { CaptureEntry } from "@/lib/capture/types";

export interface TimelineBaseItem {
  type: string;
  id: string;
  created_at?: string;
}

export interface CaptureEntryTimelineItem extends TimelineBaseItem {
  type: "capture_entry";
  entry: CaptureEntry;
}

export interface ActivityTimelineItem extends TimelineBaseItem {
  type: "activity";
  title?: string;
  kind?: string;
  visibility?: string;
  scheduled_at?: string;
  status?: string;
  // Fallback payload passthrough when backend returns arbitrary keys.
  [key: string]: unknown;
}

export type TimelineItem = CaptureEntryTimelineItem | ActivityTimelineItem | (TimelineBaseItem & Record<string, unknown>);

export interface TimelineResponse {
  items: TimelineItem[];
  next_cursor: string | null;
}

/** Unified row model for table view: smart when, type, title/summary, anchor ids, author, status, visibility. */
export interface TimelineRowModel {
  id: string;
  type: "activity" | "capture_entry";
  kind: "task" | "note" | "idea" | "event" | "note_captured";
  whenIso: string;
  dayKey: string;
  whenDisplay: string;
  titleSummary: string;
  anchorModel?: string;
  anchorId?: string;
  author: string;
  status: string;
  visibility: string;
  item: TimelineItem;
}

