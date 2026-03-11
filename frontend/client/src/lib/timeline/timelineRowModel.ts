import type { TimelineItem, TimelineRowModel } from "./types";

function parseTime(value?: string): number {
  if (!value) return 0;
  const t = new Date(value).getTime();
  return Number.isFinite(t) ? t : 0;
}

/**
 * Smart when: event.start, task.due_date, else created_at.
 */
export function getItemWhen(item: TimelineItem): string {
  const created = (item as any).created_at ?? "";
  if (item.type === "activity") {
    const activity = (item as any).activity ?? item;
    const content = activity?.content ?? {};
    const kind = String(activity?.kind ?? "").toLowerCase();
    if (kind === "event" && content?.start) return String(content.start);
    if (kind === "task" && content?.due_date) return String(content.due_date);
  }
  return created;
}

export function getItemDayKey(whenIso: string): string {
  if (!whenIso) return "";
  try {
    const d = new Date(whenIso);
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
  } catch {
    return "";
  }
}

function formatTimeOnly(iso?: string): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleTimeString(undefined, {
      hour: "numeric",
      minute: "2-digit",
      hour12: true,
    });
  } catch {
    return iso;
  }
}

function shortId(id: string, keep: number = 6): string {
  const v = String(id || "").trim();
  if (!v) return "";
  return v.length <= keep * 2 + 3 ? v : `${v.slice(0, keep)}…${v.slice(-keep)}`;
}

export function itemToRowModel(item: TimelineItem, currentUserId?: string | null): TimelineRowModel {
  const whenIso = getItemWhen(item);
  const dayKey = getItemDayKey(whenIso);
  const whenDisplay = formatTimeOnly(whenIso);

  if (item.type === "capture_entry") {
    const entry: any = (item as any).entry ?? item;
    const actorId = entry.actor_id ? String(entry.actor_id) : "";
    const author = !actorId ? "—" : currentUserId && actorId === currentUserId ? "You" : `User ${shortId(actorId)}`;
    return {
      id: String(item.id),
      type: "capture_entry",
      kind: "note_captured",
      whenIso,
      dayKey,
      whenDisplay,
      titleSummary: String(entry.summary ?? entry.raw_text ?? "").trim() || "—",
      anchorModel: entry.anchor_model ? String(entry.anchor_model).trim().toLowerCase() : undefined,
      anchorId: entry.anchor_id ? String(entry.anchor_id).trim() : undefined,
      author,
      status: String(entry.status ?? "captured"),
      visibility: String(entry.visibility ?? "internal"),
      item,
    };
  }

  const activity: any = (item as any).activity ?? item;
  const kind = String(activity?.kind ?? "note").toLowerCase() as TimelineRowModel["kind"];
  const author = (() => {
    if (activity?.author && String(activity.author).trim()) return String(activity.author).trim();
    const userId = activity?.user_id ? String(activity.user_id) : "";
    if (!userId) return "—";
    if (currentUserId && userId === currentUserId) return "You";
    return `User ${shortId(userId)}`;
  })();
  const content = activity?.content ?? {};
  const status =
    kind === "task" ? String(content?.status ?? "open") : String(activity?.status ?? "—");

  return {
    id: String(item.id),
    type: "activity",
    kind: kind === "task" || kind === "note" || kind === "idea" || kind === "event" ? kind : "note",
    whenIso,
    dayKey,
    whenDisplay,
    titleSummary: String(activity?.title ?? "").trim() || "—",
    author,
    status,
    visibility: String(activity?.visibility ?? "private"),
    item,
  };
}

export function groupRowsByDay(rows: TimelineRowModel[]): Map<string, TimelineRowModel[]> {
  const map = new Map<string, TimelineRowModel[]>();
  for (const row of rows) {
    const key = row.dayKey || "no-date";
    const list = map.get(key) ?? [];
    list.push(row);
    map.set(key, list);
  }
  for (const list of map.values()) {
    list.sort((a, b) => parseTime(b.whenIso) - parseTime(a.whenIso));
  }
  return map;
}
