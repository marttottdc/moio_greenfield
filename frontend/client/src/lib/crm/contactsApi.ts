import { apiRequest } from "@/lib/queryClient";
import { apiV1 } from "@/lib/api";

export type JsonObject = Record<string, unknown>;

export interface CreateContactPayload {
  name?: string;
  fullname?: string;
  whatsapp_name?: string;
  email?: string;
  phone?: string;
  company?: string;
  source?: string;
  type?: string;
  tags?: string[] | string;
  custom_fields?: JsonObject;
  activity_summary?: JsonObject;
  is_blacklisted?: boolean;
  do_not_contact?: boolean;
}

export interface PatchContactPayload {
  name?: string;
  email?: string;
  phone?: string;
  company?: string;
  type?: string;
  tags?: string[] | string;
  custom_fields?: JsonObject;
  activity_summary?: JsonObject;
  is_blacklisted?: boolean;
  do_not_contact?: boolean;
}

function trimOrUndefined(value: unknown): string | undefined {
  if (typeof value !== "string") return undefined;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : undefined;
}

export function normalizeTags(value: unknown): string[] | undefined {
  if (Array.isArray(value)) {
    const normalized = value
      .filter((v): v is string => typeof v === "string")
      .map((v) => v.trim())
      .filter((v) => v.length > 0);
    return normalized.length > 0 ? Array.from(new Set(normalized)) : undefined;
  }

  const asString = trimOrUndefined(value);
  if (!asString) return undefined;
  const parts = asString
    .split(",")
    .map((p) => p.trim())
    .filter((p) => p.length > 0);
  return parts.length > 0 ? Array.from(new Set(parts)) : undefined;
}

export function parseJsonObject(value: unknown): JsonObject | undefined {
  if (value == null) return undefined;
  if (typeof value === "object" && !Array.isArray(value)) return value as JsonObject;
  if (typeof value !== "string") return undefined;
  const trimmed = value.trim();
  if (!trimmed) return undefined;
  const parsed = JSON.parse(trimmed) as unknown;
  if (parsed == null || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("Expected a JSON object");
  }
  return parsed as JsonObject;
}

export function sanitizeCreatePayload(input: CreateContactPayload): CreateContactPayload {
  const tags = normalizeTags(input.tags);

  const payload: CreateContactPayload = {
    name: trimOrUndefined(input.name),
    fullname: trimOrUndefined(input.fullname),
    whatsapp_name: trimOrUndefined(input.whatsapp_name),
    email: trimOrUndefined(input.email),
    phone: trimOrUndefined(input.phone),
    company: trimOrUndefined(input.company),
    source: trimOrUndefined(input.source),
    type: trimOrUndefined(input.type),
    tags,
    custom_fields: input.custom_fields,
    activity_summary: input.activity_summary,
    is_blacklisted: typeof input.is_blacklisted === "boolean" ? input.is_blacklisted : undefined,
    do_not_contact: typeof input.do_not_contact === "boolean" ? input.do_not_contact : undefined,
  };

  // Drop empty identity keys; backend requires at least one non-empty anyway.
  if (!payload.name) delete payload.name;
  if (!payload.fullname) delete payload.fullname;
  if (!payload.whatsapp_name) delete payload.whatsapp_name;
  if (!payload.email) delete payload.email;
  if (!payload.phone) delete payload.phone;
  if (!payload.company) delete payload.company;
  if (!payload.source) delete payload.source;
  if (!payload.type) delete payload.type;
  if (!payload.tags || payload.tags.length === 0) delete payload.tags;
  if (!payload.custom_fields || Object.keys(payload.custom_fields).length === 0) delete payload.custom_fields;
  if (!payload.activity_summary || Object.keys(payload.activity_summary).length === 0) delete payload.activity_summary;
  // Important: do NOT delete boolean flags when false; backend expects explicit false to clear.

  return payload;
}

export function sanitizePatchPayload(input: PatchContactPayload): PatchContactPayload {
  const tags = normalizeTags(input.tags);
  const payload: PatchContactPayload = {
    name: trimOrUndefined(input.name),
    email: trimOrUndefined(input.email),
    phone: trimOrUndefined(input.phone),
    company: trimOrUndefined(input.company),
    type: trimOrUndefined(input.type),
    tags,
    custom_fields: input.custom_fields,
    activity_summary: input.activity_summary,
    is_blacklisted: typeof input.is_blacklisted === "boolean" ? input.is_blacklisted : undefined,
    do_not_contact: typeof input.do_not_contact === "boolean" ? input.do_not_contact : undefined,
  };

  if (!payload.name) delete payload.name;
  if (!payload.email) delete payload.email;
  if (!payload.phone) delete payload.phone;
  if (!payload.company) delete payload.company;
  if (!payload.type) delete payload.type;
  if (!payload.tags || payload.tags.length === 0) delete payload.tags;
  if (!payload.custom_fields || Object.keys(payload.custom_fields).length === 0) delete payload.custom_fields;
  if (!payload.activity_summary || Object.keys(payload.activity_summary).length === 0) delete payload.activity_summary;
  // Important: do NOT delete boolean flags when false; backend expects explicit false to clear.

  return payload;
}

export async function createContact(payload: CreateContactPayload) {
  const res = await apiRequest("POST", apiV1("/crm/contacts/"), { data: payload });
  return res.json();
}

export async function patchContact(contactId: string, payload: PatchContactPayload) {
  const res = await apiRequest("PATCH", apiV1(`/crm/contacts/${contactId}/`), { data: payload });
  return res.json();
}

