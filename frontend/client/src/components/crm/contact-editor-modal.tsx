import { useEffect, useMemo, useState, useCallback } from "react";
import { useTranslation } from "react-i18next";
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
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";

import { useToast } from "@/hooks/use-toast";
import { fetchJson, apiRequest } from "@/lib/queryClient";
import { apiV1 } from "@/lib/api";
import { ChevronsUpDown, Check, Building2, Loader2, Trash2 } from "lucide-react";
import { cn } from "@/lib/utils";
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
  account_ids?: string[] | null;
}

interface ContactTypeOption {
  id: string;
  name: string;
  description?: string;
  is_default?: boolean;
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

const UUID_REGEX = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
function isUuid(s: string): boolean {
  return UUID_REGEX.test(s);
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
    account: z.string().optional(), // Account: uuid (existing) or free text (create new)

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
  onDelete?: (contactId: string) => Promise<void>;
}) {
  const { t } = useTranslation();
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

  const [accountPopoverOpen, setAccountPopoverOpen] = useState(false);
  const [accountSearch, setAccountSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(accountSearch), 200);
    return () => clearTimeout(t);
  }, [accountSearch]);

  const accountsSearchQuery = useQuery<{ customers?: Array<{ id: string; name: string }> }>({
    queryKey: [apiV1("/crm/customers/"), "search", debouncedSearch],
    queryFn: () =>
      fetchJson<{ customers?: Array<{ id: string; name: string }> }>(apiV1("/crm/customers/"), {
        page: 1,
        limit: 30,
        search: debouncedSearch || undefined,
      }),
    enabled: accountPopoverOpen,
  });

  const accountByIdQuery = useQuery<{ id: string; name: string }>({
    queryKey: [apiV1("/crm/customers/"), "by-id", (contact?.account_ids ?? [])[0]],
    queryFn: () => fetchJson<{ id: string; name: string }>(apiV1(`/crm/customers/${(contact?.account_ids ?? [])[0]}/`)),
    enabled: Boolean(props.open && (contact?.account_ids ?? [])[0]),
  });

  const contactTypes = extractContactTypeOptions(contactTypesQuery.data);
  const accountSearchResults = accountsSearchQuery.data?.customers ?? [];

  const defaultValues: ContactEditorValues = useMemo(
    () => ({
      name: contact?.name ?? "",
      email: contact?.email ?? "",
      phone: contact?.phone ?? "",
      account: (contact?.account_ids ?? [])[0] ?? "__none__", // uuid or __none__
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
    setAccountSearch("");
  }, [props.open, props.mode, defaultValues, form]);

  useEffect(() => {
    if (props.mode !== "create" || !props.open) return;
    const currentType = form.getValues("type");
    if (currentType) return;
    const defaultType = contactTypes.find((ct) => ct.is_default);
    if (defaultType) {
      form.setValue("type", defaultType.name);
    }
  }, [props.mode, props.open, contactTypes, form]);

  const tagsValue = watch("tags");
  const tagsPreview = useMemo(() => normalizeTags(tagsValue ?? "") ?? [], [tagsValue]);

  const advancedIdentityDisabledReason = isEdit ? t("crm.advanced_readonly_hint") : undefined;

  const customFieldsJson = watch("custom_fields_json");
  const activitySummaryJson = watch("activity_summary_json");

  const activitySummaryPreview = useMemo<Record<string, any>>(() => {
    try {
      return parseJsonObject(activitySummaryJson) ?? (contact?.activity_summary as any) ?? {};
    } catch {
      return (contact?.activity_summary as any) ?? {};
    }
  }, [activitySummaryJson, contact]);

  const accountValue = watch("account");
  const accountDisplayName = useMemo(() => {
    if (!accountValue || accountValue === "__none__") return "";
    if (isUuid(accountValue)) {
      const found = accountSearchResults.find((a) => a.id === accountValue);
      if (found) return found.name;
      if (accountByIdQuery.data && accountByIdQuery.data.id === accountValue) return accountByIdQuery.data.name;
      return accountByIdQuery.isLoading ? "…" : accountValue.slice(0, 8) + "…";
    }
    return accountValue; // free text = new account name
  }, [accountValue, accountSearchResults, accountByIdQuery.data, accountByIdQuery.isLoading]);

  const resolveAccount = useCallback(
    async (value: string): Promise<{ account_ids: string[]; company?: string }> => {
      if (!value || value === "__none__") return { account_ids: [], company: "" };
      if (isUuid(value)) {
        const customer = await fetchJson<{ name: string }>(apiV1(`/crm/customers/${value}/`));
        return { account_ids: [value], company: customer?.name };
      }
      const name = value.trim();
      if (!name) return { account_ids: [] };
      const created = await apiRequest("POST", apiV1("/crm/customers/"), {
        data: { name, legal_name: name, type: "Business" },
      }).then((r) => r.json());
      return { account_ids: [created.id], company: created.name };
    },
    []
  );

  const handleSubmit = async (values: ContactEditorValues) => {
    try {
      const tags = normalizeTags(values.tags);

      if (props.mode === "create") {
        const custom_fields = parseJsonObject(values.custom_fields_json);
        const activity_summary = parseJsonObject(values.activity_summary_json);
        const { account_ids, company } = await resolveAccount(values.account ?? "__none__");
        const payload = sanitizeCreatePayload({
          name: values.name,
          fullname: values.fullname,
          whatsapp_name: values.whatsapp_name,
          email: values.email,
          phone: values.phone,
          company,
          source: values.source,
          type: values.type,
          tags,
          custom_fields,
          activity_summary,
          is_blacklisted: values.is_blacklisted,
          do_not_contact: values.do_not_contact,
          account_ids,
        });

        const created = await createContact(payload);
        toast({
          title: t("crm.contact_created"),
          description: t("crm.contact_created_description"),
        });
        props.onSaved(created);
        props.onClose();
        return;
      }

      if (!contact?.id) {
        toast({
          title: t("crm.cannot_edit_contact"),
          description: t("crm.missing_contact_id"),
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
      if (dirty.type) patchInput.type = values.type;
      if (dirty.account) {
        const { account_ids, company } = await resolveAccount(values.account ?? "__none__");
        patchInput.account_ids = account_ids;
        patchInput.company = company;
      }

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
          title: t("crm.no_changes"),
          description: t("crm.nothing_to_update"),
        });
        props.onClose();
        return;
      }

      const updated = await patchContact(contact.id, payload);
      toast({
        title: t("crm.contact_updated"),
        description: t("crm.contact_updated_description"),
      });
      props.onSaved(updated);
      props.onClose();
    } catch (error: any) {
      toast({
        title: t("crm.save_failed"),
        description: error?.message || t("crm.failed_to_save_contact"),
        variant: "destructive",
      });
    }
  };

  const title = props.mode === "create" ? t("crm.add_contact") : t("crm.edit_contact");
  const description =
    props.mode === "create"
      ? t("crm.contact_form_description_create")
      : t("crm.contact_form_description_edit");

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
                        <FormLabel>{t("crm.name_required")}</FormLabel>
                        <FormControl>
                          <Input placeholder={t("crm.placeholder_full_name")} {...field} data-testid="input-contact-name" />
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
                        <FormLabel>{t("crm.email_label")}</FormLabel>
                        <FormControl>
                          <Input type="email" placeholder={t("crm.placeholder_email")} {...field} data-testid="input-contact-email" />
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
                        <FormLabel>{t("crm.phone_label")}</FormLabel>
                        <FormControl>
                          <Input placeholder={t("crm.phone_placeholder")} {...field} data-testid="input-contact-phone" />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  <FormField
                    control={form.control}
                    name="account"
                    render={({ field }) => (
                      <FormItem className="md:col-span-2">
                        <FormLabel>{t("crm.account_label")}</FormLabel>
                        <Popover open={accountPopoverOpen} onOpenChange={setAccountPopoverOpen}>
                          <PopoverTrigger asChild>
                            <FormControl>
                              <Button
                                variant="outline"
                                role="combobox"
                                aria-expanded={accountPopoverOpen}
                                className={cn(
                                  "w-full justify-between font-normal",
                                  !field.value || field.value === "__none__" ? "text-muted-foreground" : ""
                                )}
                                data-testid="select-contact-account"
                              >
                                {accountDisplayName || t("crm.account_search_placeholder")}
                                <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                              </Button>
                            </FormControl>
                          </PopoverTrigger>
                          <PopoverContent className="w-[300px] p-0" align="start">
                            <Command shouldFilter={false}>
                              <CommandInput
                                placeholder={t("crm.account_search_placeholder")}
                                value={accountSearch}
                                onValueChange={setAccountSearch}
                              />
                              <CommandList>
                                {accountsSearchQuery.isFetching && (
                                  <div className="flex items-center justify-center gap-2 py-4 text-sm text-muted-foreground">
                                    <Loader2 className="h-4 w-4 animate-spin" />
                                    {t("crm.searching")}
                                  </div>
                                )}
                                <CommandGroup>
                                  <CommandItem
                                    value="__none__"
                                    onSelect={() => {
                                      field.onChange("__none__");
                                      setAccountPopoverOpen(false);
                                      setAccountSearch("");
                                    }}
                                  >
                                    <Check className={cn("mr-2 h-4 w-4", (!field.value || field.value === "__none__") ? "opacity-100" : "opacity-0")} />
                                    <span className="text-muted-foreground">{t("crm.account_none")}</span>
                                  </CommandItem>
                                  {accountSearchResults.map((acc) => (
                                    <CommandItem
                                      key={acc.id}
                                      value={acc.id}
                                      onSelect={() => {
                                        field.onChange(acc.id);
                                        setAccountPopoverOpen(false);
                                        setAccountSearch("");
                                      }}
                                    >
                                      <Check className={cn("mr-2 h-4 w-4", field.value === acc.id ? "opacity-100" : "opacity-0")} />
                                      {acc.name}
                                    </CommandItem>
                                  ))}
                                  {accountSearch.trim() && !accountsSearchQuery.isFetching && (
                                    <CommandItem
                                      value={`__create__${accountSearch.trim()}`}
                                      onSelect={() => {
                                        field.onChange(accountSearch.trim());
                                        setAccountPopoverOpen(false);
                                        setAccountSearch("");
                                      }}
                                    >
                                      <Building2 className="mr-2 h-4 w-4" />
                                      {t("crm.create_account_name", { name: accountSearch.trim() })}
                                    </CommandItem>
                                  )}
                                </CommandGroup>
                                {!accountSearch.trim() && accountSearchResults.length === 0 && (
                                  <CommandEmpty>{t("crm.type_to_search_or_create")}</CommandEmpty>
                                )}
                              </CommandList>
                            </Command>
                          </PopoverContent>
                        </Popover>
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  <FormField
                    control={form.control}
                    name="type"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>{t("crm.type_label")}</FormLabel>
                        <Select value={field.value || ""} onValueChange={field.onChange} disabled={contactTypesQuery.isLoading}>
                          <FormControl>
                            <SelectTrigger data-testid="select-contact-type">
                              <SelectValue placeholder={contactTypesQuery.isLoading ? t("crm.loading") : t("crm.select_type_optional")} />
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
                                <SelectItem value="Lead">{t("crm.lead")}</SelectItem>
                                <SelectItem value="Customer">{t("crm.customer")}</SelectItem>
                                <SelectItem value="Partner">{t("crm.partner")}</SelectItem>
                                <SelectItem value="Vendor">{t("crm.vendor")}</SelectItem>
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
                    {showAdvanced ? t("crm.hide_advanced") : t("crm.show_advanced")}
                  </Button>
                </div>

                {isEdit && (
                  <div className="rounded-lg border bg-card p-4">
                    <div className="flex items-center justify-between">
                      <div className="text-sm font-semibold">{t("crm.activity_summary_label")}</div>
                    </div>

                    <div className="mt-3 grid grid-cols-3 gap-3">
                      <div className="rounded-lg bg-muted/50 p-3 text-center">
                        <div className="text-2xl font-semibold">
                          {Number(activitySummaryPreview?.total_deals ?? 0)}
                        </div>
                        <div className="text-xs text-muted-foreground">{t("crm.deals_count")}</div>
                      </div>
                      <div className="rounded-lg bg-muted/50 p-3 text-center">
                        <div className="text-2xl font-semibold">
                          {Number(activitySummaryPreview?.total_tickets ?? 0)}
                        </div>
                        <div className="text-xs text-muted-foreground">{t("crm.tickets_count")}</div>
                      </div>
                      <div className="rounded-lg bg-muted/50 p-3 text-center">
                        <div className="text-2xl font-semibold">
                          {Number(activitySummaryPreview?.total_messages ?? 0)}
                        </div>
                        <div className="text-xs text-muted-foreground">{t("crm.messages_count")}</div>
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
                                {t("crm.activity_summary_json_label")}
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
                          {t("crm.activity_summary_placeholder")}
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
                      <div className="text-sm font-semibold">{t("crm.advanced_label")}</div>
                      {advancedIdentityDisabledReason && (
                        <div className="text-xs text-muted-foreground">
                          {t("crm.advanced_readonly_hint")}
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
                        {t("crm.edit_button")}
                      </Button>
                    )}
                  </div>

                  <ScrollArea className="h-[55vh] pr-3">
                    <div className="space-y-3">
                      <div className="rounded-lg border bg-card p-3">
                        <div className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                          {t("crm.identity_label")}
                        </div>
                        {advancedEditEnabled ? (
                          <div className="mt-2 grid grid-cols-1 gap-3">
                            <div className="space-y-1">
                              <Label htmlFor="fullname" className="text-xs text-muted-foreground">{t("crm.full_name_label")}</Label>
                              <FormField
                                control={form.control}
                                name="fullname"
                                render={({ field }) => (
                                  <FormItem>
                                    <FormControl>
                                      <Input
                                        id="fullname"
                                        placeholder={t("crm.full_legal_name_placeholder")}
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
                              <Label htmlFor="whatsapp_name" className="text-xs text-muted-foreground">{t("crm.whatsapp_name_label")}</Label>
                              <FormField
                                control={form.control}
                                name="whatsapp_name"
                                render={({ field }) => (
                                  <FormItem>
                                    <FormControl>
                                      <Input
                                        id="whatsapp_name"
                                        placeholder={t("crm.whatsapp_display_placeholder")}
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
                                      placeholder={t("crm.source_placeholder")}
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
                                  <FormLabel className="text-xs text-muted-foreground">{t("crm.comma_separated")}</FormLabel>
                                  <FormControl>
                                    <Input
                                      placeholder={t("crm.tags_placeholder")}
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
                                    <FormLabel className="text-sm">{t("crm.do_not_contact")}</FormLabel>
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
                                    <FormLabel className="text-sm">{t("crm.blacklisted")}</FormLabel>
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
                              <span className="text-sm">{form.getValues("do_not_contact") ? t("crm.yes") : t("crm.no")}</span>
                            </div>
                            <div className="flex items-center justify-between">
                              <span className="text-xs text-muted-foreground">{t("crm.blacklisted")}</span>
                              <span className="text-sm">{form.getValues("is_blacklisted") ? t("crm.yes") : t("crm.no")}</span>
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
                                      placeholder={t("crm.custom_fields_placeholder")}
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
              {isEdit && contact?.id && props.onDelete && (
                <Button
                  type="button"
                  variant="destructive"
                  className="mr-auto"
                  onClick={async () => {
                    const confirmed = window.confirm(t("contact.delete_contact_description"));
                    if (!confirmed) return;
                    await props.onDelete?.(contact.id as string);
                  }}
                  disabled={isSubmitting}
                  data-testid="button-delete-contact-in-editor"
                >
                  <Trash2 className="h-4 w-4 mr-2" />
                  {t("contact.delete")}
                </Button>
              )}
              <Button type="button" variant="outline" onClick={props.onClose} disabled={isSubmitting}>
                {t("crm.cancel")}
              </Button>
              <Button type="submit" disabled={isSubmitting} data-testid="button-save-contact">
                {isSubmitting ? t("crm.saving") : t("crm.save")}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}

