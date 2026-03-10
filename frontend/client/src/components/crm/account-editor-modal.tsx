"use client";

import { useEffect } from "react";
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

const ACCOUNT_TYPE_OPTIONS = [
  { value: "Person", label: "Person" },
  { value: "Business", label: "Business" },
  { value: "Household", label: "Household" },
];

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
}

export function AccountEditorModal({ open, onClose, onSaved }: AccountEditorModalProps) {
  const { toast } = useToast();

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
      form.reset({
        name: "",
        legal_name: "",
        type: "Business",
        email: "",
        phone: "",
      });
    }
  }, [open, form]);

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

      await apiRequest("POST", apiV1("/crm/customers/"), { data: payload });
      toast({
        title: "Account created",
        description: "The account has been created successfully.",
      });
      onSaved();
      onClose();
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : "Failed to create account";
      toast({
        title: "Save failed",
        description: message,
        variant: "destructive",
      });
    }
  };

  return (
    <Dialog open={open} onOpenChange={(isOpen) => !isOpen && onClose()}>
      <DialogContent className="max-w-md" data-testid="dialog-account-editor">
        <DialogHeader>
          <DialogTitle>Add Account</DialogTitle>
          <DialogDescription>Create a new account (customer) to track organizations in your CRM.</DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4 py-2">
            <FormField
              control={form.control}
              name="name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Name *</FormLabel>
                  <FormControl>
                    <Input placeholder="Account name" {...field} data-testid="input-account-name" />
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
                  <FormLabel>Legal name</FormLabel>
                  <FormControl>
                    <Input placeholder="Legal entity name" {...field} data-testid="input-account-legal-name" />
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
                  <Select value={field.value} onValueChange={field.onChange}>
                    <FormControl>
                      <SelectTrigger data-testid="select-account-type">
                        <SelectValue />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      {ACCOUNT_TYPE_OPTIONS.map((opt) => (
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
                  <FormLabel>Email</FormLabel>
                  <FormControl>
                    <Input type="email" placeholder="contact@company.com" {...field} data-testid="input-account-email" />
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
                    <Input placeholder="+598..." {...field} data-testid="input-account-phone" />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <DialogFooter className="gap-2 pt-4">
              <Button type="button" variant="outline" onClick={onClose}>
                Cancel
              </Button>
              <Button type="submit" disabled={form.formState.isSubmitting} data-testid="button-save-account">
                {form.formState.isSubmitting ? "Saving..." : "Create Account"}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
