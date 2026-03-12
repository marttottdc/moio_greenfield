"use client";

import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";

import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

import { useToast } from "@/hooks/use-toast";
import { apiRequest } from "@/lib/queryClient";
import { apiV1 } from "@/lib/api";

const ACCOUNT_TYPE_VALUES = ["Person", "Business", "Household"] as const;

const accountEditorSchema = z.object({
  name: z.string().min(1, "Name is required"),
  legal_name: z.string().optional(),
  type: z.enum(["Person", "Business", "Household"]).default("Business"),
  email: z.string().email("Invalid email").optional().or(z.literal("")),
  phone: z.string().optional(),
});

type AccountEditorValues = z.infer<typeof accountEditorSchema>;

export interface AccountEditorModalProps {
  open: boolean;
  onClose: () => void;
  onSaved: () => void;
  account?: {
    id: string;
    name: string;
    legal_name?: string | null;
    type?: string | null;
    email?: string | null;
    phone?: string | null;
  } | null;
}

export function AccountEditorModal({ open, onClose, onSaved, account }: AccountEditorModalProps) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const isEdit = Boolean(account?.id);
  const accountTypeOptions = [
    { value: "Person", label: t("crm.person") },
    { value: "Business", label: t("crm.business") },
    { value: "Household", label: t("crm.household") },
  ];

  const form = useForm<AccountEditorValues>({
    resolver: zodResolver(accountEditorSchema),
    defaultValues: {
      name: "",
      legal_name: "",
      type: "Business",
      email: "",
      phone: "",
    },
  });

  useEffect(() => {
    if (open) {
      if (account?.id) {
        form.reset({
          name: account.name ?? "",
          legal_name: account.legal_name ?? account.name ?? "",
          type: (account.type as "Person" | "Business" | "Household") ?? "Business",
          email: account.email ?? "",
          phone: account.phone ?? "",
        });
      } else {
        form.reset({
          name: "",
          legal_name: "",
          type: "Business",
          email: "",
          phone: "",
        });
      }
    }
  }, [open, account, form]);

  const handleSubmit = async (values: AccountEditorValues) => {
    try {
      const payload: Record<string, unknown> = {
        name: values.name.trim(),
        legal_name: (values.legal_name || values.name).trim(),
        type: values.type,
      };
      const email = (values.email || "").trim();
      const phone = (values.phone || "").trim();
      if (email) payload.email = email;
      if (phone) payload.phone = phone;

      if (isEdit && account?.id) {
        await apiRequest("PATCH", apiV1(`/crm/customers/${account.id}/`), { data: payload });
        toast({
          title: t("crm.account_updated"),
          description: t("crm.account_updated_description"),
        });
      } else {
        await apiRequest("POST", apiV1("/crm/customers/"), { data: payload });
        toast({
          title: t("crm.account_created"),
          description: t("crm.account_created_description"),
        });
      }
      onSaved();
      onClose();
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : t("crm.account_create_failed");
      toast({
        title: t("crm.save_failed"),
        description: message,
        variant: "destructive",
      });
    }
  };

  return (
    <Dialog open={open} onOpenChange={(isOpen) => !isOpen && onClose()}>
      <DialogContent className="max-w-md" data-testid="dialog-account-editor">
        <DialogHeader>
          <DialogTitle>{isEdit ? t("crm.edit_account") : t("crm.add_account")}</DialogTitle>
          <DialogDescription>
            {isEdit ? t("crm.account_form_description_edit") : t("crm.account_form_description_create")}
          </DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4 py-2">
            <FormField
              control={form.control}
              name="name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{t("crm.name_required")}</FormLabel>
                  <FormControl>
                    <Input placeholder={t("crm.account_name_placeholder")} {...field} data-testid="input-account-name" />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="legal_name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{t("crm.legal_name_label")}</FormLabel>
                  <FormControl>
                    <Input placeholder={t("crm.legal_name_placeholder")} {...field} data-testid="input-account-legal-name" />
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
                  <FormLabel>{t("crm.type_label")}</FormLabel>
                  <Select value={field.value} onValueChange={field.onChange}>
                    <FormControl>
                      <SelectTrigger data-testid="select-account-type">
                        <SelectValue />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      {accountTypeOptions.map((opt) => (
                        <SelectItem key={opt.value} value={opt.value}>
                          {opt.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
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
                    <Input type="email" placeholder={t("crm.contact_email_placeholder")} {...field} data-testid="input-account-email" />
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
                    <Input placeholder={t("crm.phone_placeholder")} {...field} data-testid="input-account-phone" />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <DialogFooter className="gap-2 pt-4">
              <Button type="button" variant="outline" onClick={onClose}>
                {t("crm.cancel")}
              </Button>
              <Button type="submit" disabled={form.formState.isSubmitting} data-testid="button-save-account">
                {form.formState.isSubmitting ? t("crm.saving") : isEdit ? t("crm.save") : t("crm.create_account_button")}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
