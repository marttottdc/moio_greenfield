import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";

import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";

import { useToast } from "@/hooks/use-toast";
import { fetchJson } from "@/lib/queryClient";
import { apiV1 } from "@/lib/api";
import {
  createContact,
  normalizeTags,
  parseJsonObject,
  patchContact,
  sanitizeCreatePayload,
  sanitizePatchPayload,
} from "@/lib/crm/contactsApi";

type Mode = "create" | "edit";

export interface ContactLike {
  id?: string;
  name?: string;
  fullname?: string | null;
  whatsapp_name?: string | null;
  email?: string | null;
  phone?: string | null;
  company?: string | null;
  source?: string | null;
  type?: string | null;
  is_blacklisted?: boolean | null;
  do_not_contact?: boolean | null;
  tags?: string[] | null;
  custom_fields?: Record<string, unknown> | null;
  activity_summary?: Record<string, unknown> | null;
}

interface ContactTypeOption {
  id: string;
  name: string;
  description?: string;
}

type ContactTypesOptionsResponse = {
  // Legacy/non-paginated shape
  contact_types?: ContactTypeOption[];
  // Paginated shape (common)
  count?: number;
  next?: string | null;
  previous?: string | null;
  results?: ContactTypeOption[] | { contact_types?: ContactTypeOption[] };
};

function extractContactTypeOptions(
  data: ContactTypesOptionsResponse | undefined
): ContactTypeOption[] {
  if (!data) return [];
  if (Array.isArray(data.contact_types)) return data.contact_types;
  const results: any = (data as any).results;
  if (Array.isArray(results)) return results as ContactTypeOption[];
  if (results && Array.isArray(results.contact_types)) return results.contact_types as ContactTypeOption[];
  return [];
}

function stringifyJson(value: unknown) {
  if (value == null) return "";
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return "";
  }
}

function safeTrim(value: unknown) {
  return typeof value === "string" ? value.trim() : "";
}

function isJsonObjectOrEmpty(value: unknown) {
  if (value == null) return true;
  if (typeof value !== "string") return true;
  const trimmed = value.trim();
  if (!trimmed) return true;
  try {
    parseJsonObject(trimmed);
    return true;
  } catch {
    return false;
  }
}

const contactEditorSchema = z
  .object({
    // Basic
    name: z.string().optional(),
    email: z.string().email("Invalid email").optional().or(z.literal("")),
    phone: z.string().optional(),
    company: z.string().optional(),
    type: z.string().optional(),

    // Advanced
    fullname: z.string().optional(),
    whatsapp_name: z.string().optional(),
    source: z.string().optional(),
    tags: z.string().optional(), // comma-separated
    custom_fields_json: z.string().optional(),
    activity_summary_json: z.string().optional(),

    // Compliance / contactability
    is_blacklisted: z.boolean().optional(),
    do_not_contact: z.boolean().optional(),
  })
  .superRefine((values, ctx) => {
    const name = safeTrim(values.name);
    const fullname = safeTrim(values.fullname);
    const whatsappName = safeTrim(values.whatsapp_name);

    // Create: backend requires at least one of name/fullname/whatsapp_name
    // Edit: PATCH only allows `name`, but we still keep the rule aligned with create for safety.
    if (!name && !fullname && !whatsappName) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["name"],
        message: "Provide at least one of Name, Full name, or WhatsApp name.",
      });
    }

    if (!isJsonObjectOrEmpty(values.custom_fields_json)) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["custom_fields_json"],
        message: "Must be a JSON object (e.g. {\"key\":\"value\"}).",
      });
    }

    if (!isJsonObjectOrEmpty(values.activity_summary_json)) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["activity_summary_json"],
        message: "Must be a JSON object (e.g. {\"total_deals\":3}).",
      });
    }
  });

type ContactEditorValues = z.infer<typeof contactEditorSchema>;

export function ContactEditorModal(props: {
  open: boolean;
  mode: Mode;
  contact?: ContactLike | null;
  onClose: () => void;
  onSaved: (contact: any) => void;
}) {
  const { toast } = useToast();
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [advancedEditEnabled, setAdvancedEditEnabled] = useState(() => props.mode === "create");
  const isEdit = props.mode === "edit";
  const contact = props.contact ?? null;

  const contactTypesQuery = useQuery<ContactTypesOptionsResponse>({
    queryKey: [apiV1("/crm/contact_types/")],
    queryFn: () => fetchJson<ContactTypesOptionsResponse>(apiV1("/crm/contact_types/"), { page_size: 200 }),
    enabled: props.open,
  });

  const contactTypes = extractContactTypeOptions(contactTypesQuery.data);

  const defaultValues: ContactEditorValues = useMemo(
    () => ({
      name: contact?.name ?? "",
      email: contact?.email ?? "",
      phone: contact?.phone ?? "",
      company: contact?.company ?? "",
      type: contact?.type ?? "",

      fullname: contact?.fullname ?? "",
      whatsapp_name: contact?.whatsapp_name ?? "",
      source: contact?.source ?? "",

      tags: (contact?.tags ?? []).join(", "),
      custom_fields_json: stringifyJson(contact?.custom_fields ?? undefined),
      activity_summary_json: stringifyJson(contact?.activity_summary ?? undefined),

      is_blacklisted: Boolean(contact?.is_blacklisted),
      do_not_contact: Boolean(contact?.do_not_contact),
    }),
    [contact]
  );

  const form = useForm<ContactEditorValues>({
    resolver: zodResolver(contactEditorSchema),
    defaultValues,
  });

  const {
    formState: { isSubmitting },
    watch,
  } = form;

  useEffect(() => {
    if (!props.open) return;
    form.reset(defaultValues);
    setShowAdvanced(false);
    setAdvancedEditEnabled(props.mode === "create");
  }, [props.open, props.mode, defaultValues, form]);

  const tagsValue = watch("tags");
  const tagsPreview = useMemo(() => normalizeTags(tagsValue ?? "") ?? [], [tagsValue]);

  const advancedIdentityDisabledReason =
    isEdit ? "Not editable yet (backend PATCH doesn’t accept fullname/whatsapp_name/source)." : undefined;

  const customFieldsJson = watch("custom_fields_json");
  const activitySummaryJson = watch("activity_summary_json");

  const activitySummaryPreview = useMemo<Record<string, any>>(() => {
    try {
      return parseJsonObject(activitySummaryJson) ?? (contact?.activity_summary as any) ?? {};
    } catch {
      return (contact?.activity_summary as any) ?? {};
    }
  }, [activitySummaryJson, contact]);

  const handleSubmit = async (values: ContactEditorValues) => {
    try {
      const tags = normalizeTags(values.tags);

      if (props.mode === "create") {
        const custom_fields = parseJsonObject(values.custom_fields_json);
        const activity_summary = parseJsonObject(values.activity_summary_json);
        const payload = sanitizeCreatePayload({
          name: values.name,
          fullname: values.fullname,
          whatsapp_name: values.whatsapp_name,
          email: values.email,
          phone: values.phone,
          company: values.company,
          source: values.source,
          type: values.type,
          tags,
          custom_fields,
          activity_summary,
          is_blacklisted: values.is_blacklisted,
          do_not_contact: values.do_not_contact,
        });

        const created = await createContact(payload);
        toast({
          title: "Contact created",
          description: "The contact has been created successfully.",
        });
        props.onSaved(created);
        props.onClose();
        return;
      }

      if (!contact?.id) {
        toast({
          title: "Cannot edit contact",
          description: "Missing contact id.",
          variant: "destructive",
        });
        return;
      }

      // PATCH: send only fields the user actually changed.
      const dirty = form.formState.dirtyFields as Partial<Record<keyof ContactEditorValues, boolean>>;

      const patchInput: Parameters<typeof sanitizePatchPayload>[0] = {};

      if (dirty.name) patchInput.name = values.name;
      if (dirty.email) patchInput.email = values.email;
      if (dirty.phone) patchInput.phone = values.phone;
      if (dirty.company) patchInput.company = values.company;
      if (dirty.type) patchInput.type = values.type;

      if (dirty.tags) patchInput.tags = tags;

      if (dirty.custom_fields_json) {
        patchInput.custom_fields = parseJsonObject(values.custom_fields_json);
      }

      if (dirty.activity_summary_json) {
        patchInput.activity_summary = parseJsonObject(values.activity_summary_json);
      }

      if (dirty.is_blacklisted) patchInput.is_blacklisted = values.is_blacklisted;
      if (dirty.do_not_contact) patchInput.do_not_contact = values.do_not_contact;

      const payload = sanitizePatchPayload(patchInput);

      if (Object.keys(payload).length === 0) {
        toast({
          title: "No changes",
          description: "Nothing to update.",
        });
        props.onClose();
        return;
      }

      const updated = await patchContact(contact.id, payload);
      toast({
        title: "Contact updated",
        description: "The contact has been updated successfully.",
      });
      props.onSaved(updated);
      props.onClose();
    } catch (error: any) {
      toast({
        title: "Save failed",
        description: error?.message || "Failed to save contact",
        variant: "destructive",
      });
    }
  };

  const title = props.mode === "create" ? "Add New Contact" : "Edit Contact";
  const description =
    props.mode === "create"
      ? "Fill in the basic fields fast, or open Advanced for more."
      : "Update contact information. Some advanced identity fields are read-only for now.";

  return (
    <Dialog open={props.open} onOpenChange={(isOpen) => !isOpen && props.onClose()}>
      <DialogContent className="max-w-4xl" data-testid="dialog-contact-editor">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(handleSubmit)} className="py-2">
            <div
              className={`grid gap-6 ${showAdvanced ? "md:grid-cols-[1fr_22rem]" : "md:grid-cols-1"}`}
            >
              {/* Left: Basic (fast) */}
              <div className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <FormField
                    control={form.control}
                    name="name"
                    render={({ field }) => (
                      <FormItem className="md:col-span-2">
                        <FormLabel>Name *</FormLabel>
                        <FormControl>
                          <Input placeholder="Full name" {...field} data-testid="input-contact-name" />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  <FormField
                    control={form.control}
                    name="email"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Email</FormLabel>
                        <FormControl>
                          <Input type="email" placeholder="email@example.com" {...field} data-testid="input-contact-email" />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  <FormField
                    control={form.control}
                    name="phone"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Phone</FormLabel>
                        <FormControl>
                          <Input placeholder="+598..." {...field} data-testid="input-contact-phone" />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  <FormField
                    control={form.control}
                    name="company"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Company</FormLabel>
                        <FormControl>
                          <Input placeholder="Company name" {...field} data-testid="input-contact-company" />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  <FormField
                    control={form.control}
                    name="type"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Type</FormLabel>
                        <Select value={field.value || ""} onValueChange={field.onChange} disabled={contactTypesQuery.isLoading}>
                          <FormControl>
                            <SelectTrigger data-testid="select-contact-type">
                              <SelectValue placeholder={contactTypesQuery.isLoading ? "Loading..." : "Select type (optional)"} />
                            </SelectTrigger>
                          </FormControl>
                          <SelectContent>
                            {contactTypes.length > 0 ? (
                              contactTypes.map((t) => (
                                <SelectItem key={t.id} value={t.name}>
                                  {t.name}
                                </SelectItem>
                              ))
                            ) : (
                              <>
                                <SelectItem value="Lead">Lead</SelectItem>
                                <SelectItem value="Customer">Customer</SelectItem>
                                <SelectItem value="Partner">Partner</SelectItem>
                                <SelectItem value="Vendor">Vendor</SelectItem>
                              </>
                            )}
                          </SelectContent>
                        </Select>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </div>

                <div className="flex items-center justify-between">
                  <Button
                    type="button"
                    variant="ghost"
                    onClick={() => setShowAdvanced((v) => !v)}
                    className="px-0"
                    data-testid="button-toggle-advanced"
                  >
                    {showAdvanced ? "Hide advanced" : "Show advanced"}
                  </Button>
                </div>

                {isEdit && (
                  <div className="rounded-lg border bg-card p-4">
                    <div className="flex items-center justify-between">
                      <div className="text-sm font-semibold">Activity Summary</div>
                    </div>

                    <div className="mt-3 grid grid-cols-3 gap-3">
                      <div className="rounded-lg bg-muted/50 p-3 text-center">
                        <div className="text-2xl font-semibold">
                          {Number(activitySummaryPreview?.total_deals ?? 0)}
                        </div>
                        <div className="text-xs text-muted-foreground">Deals</div>
                      </div>
                      <div className="rounded-lg bg-muted/50 p-3 text-center">
                        <div className="text-2xl font-semibold">
                          {Number(activitySummaryPreview?.total_tickets ?? 0)}
                        </div>
                        <div className="text-xs text-muted-foreground">Tickets</div>
                      </div>
                      <div className="rounded-lg bg-muted/50 p-3 text-center">
                        <div className="text-2xl font-semibold">
                          {Number(activitySummaryPreview?.total_messages ?? 0)}
                        </div>
                        <div className="text-xs text-muted-foreground">Messages</div>
                      </div>
                    </div>

                    {showAdvanced && advancedEditEnabled && (
                      <div className="mt-4">
                        <FormField
                          control={form.control}
                          name="activity_summary_json"
                          render={({ field }) => (
                            <FormItem>
                              <FormLabel className="text-xs text-muted-foreground">
                                activity_summary (JSON)
                              </FormLabel>
                              <FormControl>
                                <Textarea
                                  placeholder='{"total_deals":3,"total_tickets":5,"total_messages":47}'
                                  className="min-h-[120px] font-mono text-xs"
                                  {...field}
                                  data-testid="textarea-activity-summary"
                                />
                              </FormControl>
                              <FormMessage />
                            </FormItem>
                          )}
                        />
                        <p className="text-xs text-muted-foreground mt-2">
                          Often computed.
                        </p>
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* Right: Advanced (scrollable) */}
              {showAdvanced && (
                <div className="md:border-l md:pl-6">
                  <div className="mb-3 flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="text-sm font-semibold">Advanced</div>
                      {advancedIdentityDisabledReason && (
                        <div className="text-xs text-muted-foreground">
                          {advancedIdentityDisabledReason}
                        </div>
                      )}
                    </div>
                    {!advancedEditEnabled && (
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() => setAdvancedEditEnabled(true)}
                        data-testid="button-edit-advanced"
                      >
                        Edit
                      </Button>
                    )}
                  </div>

                  <ScrollArea className="h-[55vh] pr-3">
                    <div className="space-y-3">
                      <div className="rounded-lg border bg-card p-3">
                        <div className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                          Identity
                        </div>
                        {advancedEditEnabled ? (
                          <div className="mt-2 grid grid-cols-1 gap-3">
                            <div className="space-y-1">
                              <Label htmlFor="fullname" className="text-xs text-muted-foreground">Full name</Label>
                              <FormField
                                control={form.control}
                                name="fullname"
                                render={({ field }) => (
                                  <FormItem>
                                    <FormControl>
                                      <Input
                                        id="fullname"
                                        placeholder="Full legal name"
                                        {...field}
                                        disabled={isEdit}
                                        data-testid="input-contact-fullname"
                                        className="h-8"
                                      />
                                    </FormControl>
                                    <FormMessage />
                                  </FormItem>
                                )}
                              />
                            </div>

                            <div className="space-y-1">
                              <Label htmlFor="whatsapp_name" className="text-xs text-muted-foreground">WhatsApp name</Label>
                              <FormField
                                control={form.control}
                                name="whatsapp_name"
                                render={({ field }) => (
                                  <FormItem>
                                    <FormControl>
                                      <Input
                                        id="whatsapp_name"
                                        placeholder="WhatsApp display name"
                                        {...field}
                                        disabled={isEdit}
                                        data-testid="input-contact-whatsapp-name"
                                        className="h-8"
                                      />
                                    </FormControl>
                                    <FormMessage />
                                  </FormItem>
                                )}
                              />
                            </div>

                            {isEdit && (
                              <p className="text-xs text-muted-foreground">
                                Full name / WhatsApp name are create-only for now.
                              </p>
                            )}
                          </div>
                        ) : (
                          <div className="mt-2 grid gap-2 text-sm">
                            <div>
                              <div className="text-xs text-muted-foreground">Full name</div>
                              <div className="mt-0.5">{safeTrim(form.getValues("fullname")) || "—"}</div>
                            </div>
                            <div>
                              <div className="text-xs text-muted-foreground">WhatsApp name</div>
                              <div className="mt-0.5">{safeTrim(form.getValues("whatsapp_name")) || "—"}</div>
                            </div>
                          </div>
                        )}
                      </div>

                      <div className="rounded-lg border bg-card p-3">
                        <div className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                          Attribution
                        </div>
                        {advancedEditEnabled ? (
                          <div className="mt-2 space-y-1">
                            <Label htmlFor="source" className="text-xs text-muted-foreground">Source</Label>
                            <FormField
                              control={form.control}
                              name="source"
                              render={({ field }) => (
                                <FormItem>
                                  <FormControl>
                                    <Input
                                      id="source"
                                      placeholder="Website, referral, event..."
                                      {...field}
                                      disabled={isEdit}
                                      data-testid="input-contact-source"
                                      className="h-8"
                                    />
                                  </FormControl>
                                  <FormMessage />
                                </FormItem>
                              )}
                            />
                            {isEdit && (
                              <p className="text-xs text-muted-foreground">
                                Source is create-only for now.
                              </p>
                            )}
                          </div>
                        ) : (
                          <div className="mt-2">
                            <div className="text-xs text-muted-foreground">Source</div>
                            <div className="mt-0.5 text-sm">{safeTrim(form.getValues("source")) || "—"}</div>
                          </div>
                        )}
                      </div>

                      <div className="rounded-lg border bg-card p-3">
                        <div className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                          Tags
                        </div>
                        {advancedEditEnabled ? (
                          <div className="mt-2">
                            <FormField
                              control={form.control}
                              name="tags"
                              render={({ field }) => (
                                <FormItem>
                                  <FormLabel className="text-xs text-muted-foreground">Comma-separated</FormLabel>
                                  <FormControl>
                                    <Input
                                      placeholder="vip, priority, spanish"
                                      {...field}
                                      data-testid="input-contact-tags"
                                      className="h-8"
                                    />
                                  </FormControl>
                                  <FormMessage />
                                </FormItem>
                              )}
                            />

                            {tagsPreview.length > 0 && (
                              <div className="flex flex-wrap gap-2 mt-2">
                                {tagsPreview.map((tag) => (
                                  <Badge key={tag} variant="secondary">
                                    {tag}
                                  </Badge>
                                ))}
                              </div>
                            )}
                          </div>
                        ) : (
                          <div className="mt-2">
                            {tagsPreview.length > 0 ? (
                              <div className="flex flex-wrap gap-2">
                                {tagsPreview.map((tag) => (
                                  <Badge key={tag} variant="secondary">
                                    {tag}
                                  </Badge>
                                ))}
                              </div>
                            ) : (
                              <div className="text-sm">—</div>
                            )}
                          </div>
                        )}
                      </div>

                      <div className="rounded-lg border bg-card p-3">
                        <div className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                          Compliance
                        </div>
                        {advancedEditEnabled ? (
                          <div className="mt-2 space-y-2">
                            <FormField
                              control={form.control}
                              name="do_not_contact"
                              render={({ field }) => (
                                <FormItem className="flex items-center justify-between gap-3 rounded-md border p-2">
                                  <div className="min-w-0">
                                    <FormLabel className="text-sm">Do not contact</FormLabel>
                                    <p className="text-xs text-muted-foreground">
                                      Mark as not contactable.
                                    </p>
                                  </div>
                                  <FormControl>
                                    <Switch checked={Boolean(field.value)} onCheckedChange={field.onChange} />
                                  </FormControl>
                                </FormItem>
                              )}
                            />

                            <FormField
                              control={form.control}
                              name="is_blacklisted"
                              render={({ field }) => (
                                <FormItem className="flex items-center justify-between gap-3 rounded-md border p-2">
                                  <div className="min-w-0">
                                    <FormLabel className="text-sm">Blacklisted</FormLabel>
                                    <p className="text-xs text-muted-foreground">
                                      Block across the CRM.
                                    </p>
                                  </div>
                                  <FormControl>
                                    <Switch checked={Boolean(field.value)} onCheckedChange={field.onChange} />
                                  </FormControl>
                                </FormItem>
                              )}
                            />
                          </div>
                        ) : (
                          <div className="mt-2 grid gap-2 text-sm">
                            <div className="flex items-center justify-between">
                              <span className="text-xs text-muted-foreground">Do not contact</span>
                              <span className="text-sm">{form.getValues("do_not_contact") ? "Yes" : "No"}</span>
                            </div>
                            <div className="flex items-center justify-between">
                              <span className="text-xs text-muted-foreground">Blacklisted</span>
                              <span className="text-sm">{form.getValues("is_blacklisted") ? "Yes" : "No"}</span>
                            </div>
                          </div>
                        )}
                      </div>

                      <div className="rounded-lg border bg-card p-3">
                        <div className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                          Custom fields
                        </div>
                        {advancedEditEnabled ? (
                          <div className="mt-2">
                            <FormField
                              control={form.control}
                              name="custom_fields_json"
                              render={({ field }) => (
                                <FormItem>
                                  <FormControl>
                                    <Textarea
                                      placeholder='{"source":"Website","industry":"Retail"}'
                                      className="min-h-[120px] font-mono text-xs"
                                      {...field}
                                      data-testid="textarea-custom-fields"
                                    />
                                  </FormControl>
                                  <FormMessage />
                                </FormItem>
                              )}
                            />
                          </div>
                        ) : (
                          <div className="mt-2">
                            {safeTrim(customFieldsJson) ? (
                              <pre className="max-h-48 overflow-auto rounded-md border bg-muted/50 p-2 text-xs leading-relaxed">
{customFieldsJson}
                              </pre>
                            ) : (
                              <div className="text-sm">—</div>
                            )}
                          </div>
                        )}
                      </div>
                    </div>
                  </ScrollArea>
                </div>
              )}
            </div>

            <DialogFooter className="pt-4">
              <Button type="button" variant="outline" onClick={props.onClose} disabled={isSubmitting}>
                Cancel
              </Button>
              <Button type="submit" disabled={isSubmitting} data-testid="button-save-contact">
                {isSubmitting ? "Saving..." : "Save"}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}

