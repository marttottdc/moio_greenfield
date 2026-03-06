import { useState, useMemo, useEffect, useRef } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Search, Plus, Eye, Filter, Edit, Trash2, Mail, Phone, Building, X, Tag } from "lucide-react";
import { Checkbox } from "@/components/ui/checkbox";
import { PageLayout } from "@/components/layout/page-layout";
import { GlassPanel } from "@/components/radiant/glass-panel";
import { EmptyState } from "@/components/empty-state";
import { ErrorDisplay } from "@/components/error-display";
import { fetchJson, apiRequest, queryClient, ApiError } from "@/lib/queryClient";
import { apiV1 } from "@/lib/api";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useToast } from "@/hooks/use-toast";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Contact, PaginatedResponse } from "@/lib/moio-types";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { ContactDetailsModal, type ContactDetailsContact } from "@/components/crm/contact-details-modal";

const contactSchema = z.object({
  name: z.string().min(1, "Name is required"),
  email: z.string().email("Invalid email").optional().or(z.literal("")),
  phone: z.string().optional(),
  company: z.string().optional(),
  type: z.enum(["Lead", "Customer", "Partner", "Vendor"]).optional(),
});

type ContactFormData = z.infer<typeof contactSchema>;

interface ContactsSummary {
  total?: number;
  with_email?: number;
  with_phone?: number;
  do_not_contact?: number;
  bounced?: number;
  latest_updated?: string;
  by_type?: Record<string, number>;
}

const SUMMARY_PATH = apiV1("/crm/contacts/summary/");

function contactToDetailsContact(c: Contact): ContactDetailsContact {
  return {
    id: c.id,
    name: c.name,
    email: c.email ?? null,
    phone: c.phone ?? null,
    company: c.company ?? null,
    type: c.type ?? null,
    tags: c.tags ?? undefined,
    activity_summary: c.activity_summary as ContactDetailsContact["activity_summary"],
  };
}

function detailsContactToContact(c: ContactDetailsContact): Contact {
  return {
    id: c.id,
    name: c.name,
    email: c.email ?? null,
    phone: c.phone ?? null,
    company: c.company ?? null,
    type: (c.type as string) || "Lead",
    tags: c.tags,
    created_at: "",
    updated_at: "",
  };
}

export default function Contacts() {
  const { toast } = useToast();
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedType, setSelectedType] = useState("all");
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [contactsOffset, setContactsOffset] = useState(0);
  const [allAccumulatedContacts, setAllAccumulatedContacts] = useState<Contact[]>([]);
  const [totalContactsCount, setTotalContactsCount] = useState(0);
  const [hasMoreContacts, setHasMoreContacts] = useState(true);
  const tableBodyRef = useRef<HTMLTableSectionElement>(null);
  const [tagFilterOpen, setTagFilterOpen] = useState(false);
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [viewModalOpen, setViewModalOpen] = useState(false);
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
  const [selectedContact, setSelectedContact] = useState<Contact | null>(null);

  const handleSearchChange = (value: string) => {
    setSearchTerm(value);
    setContactsOffset(0);
    setAllAccumulatedContacts([]);
  };

  const handleTypeChange = (value: string) => {
    setSelectedType(value);
    setContactsOffset(0);
    setAllAccumulatedContacts([]);
  };

  const summaryQuery = useQuery<ContactsSummary>({
    queryKey: [SUMMARY_PATH],
    queryFn: async () => {
      try {
        return await fetchJson<ContactsSummary>(SUMMARY_PATH);
      } catch {
        return {};
      }
    },
    retry: false,
  });

  const { data, isLoading, isError, error } = useQuery<PaginatedResponse<Contact>, ApiError>({
    queryKey: [apiV1("/crm/contacts"), contactsOffset, searchTerm, selectedType, selectedTags],
    queryFn: async () => {
      const params: Record<string, string | number> = {
        offset: contactsOffset,
        limit: 20,
      };
      
      if (searchTerm) params.search = searchTerm;
      if (selectedType !== "all") params.contact_type = selectedType;
      if (selectedTags.length > 0) params.tags = selectedTags.join(",");
      
      const apiResponse = await fetchJson<any>(apiV1("/crm/contacts"), params);
      
      const contacts = apiResponse.contacts || [];
      const totalCount = apiResponse.count !== undefined ? apiResponse.count : contacts.length;
      
      if (contactsOffset === 0) {
        setAllAccumulatedContacts(contacts);
        setTotalContactsCount(totalCount);
        setHasMoreContacts(contacts.length >= 20);
      } else if (contacts.length > 0) {
        setAllAccumulatedContacts(prev => [...prev, ...contacts]);
        setHasMoreContacts(contacts.length >= 20);
      }
      
      const result: PaginatedResponse<Contact> = {
        count: totalCount,
        next: contacts.length >= 20 ? "has_more" : null,
        previous: contactsOffset > 0 ? "has_prev" : null,
        results: contacts,
      };
      
      return result;
    },
  });

  const createForm = useForm<ContactFormData>({
    resolver: zodResolver(contactSchema),
    defaultValues: {
      name: "",
      email: "",
      phone: "",
      company: "",
      type: "Lead",
    },
  });

  const editForm = useForm<ContactFormData>({
    resolver: zodResolver(contactSchema),
  });

  const createMutation = useMutation({
    mutationFn: async (data: ContactFormData) => {
      const res = await apiRequest("POST", apiV1("/crm/contacts"), { data });
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [apiV1("/crm/contacts")] });
      toast({
        title: "Contact created",
        description: "The contact has been created successfully.",
      });
      setCreateModalOpen(false);
      createForm.reset();
    },
    onError: (error: ApiError) => {
      toast({
        title: "Creation failed",
        description: error.message || "Failed to create contact",
        variant: "destructive",
      });
    },
  });

  const updateMutation = useMutation({
    mutationFn: async ({ id, data }: { id: string; data: ContactFormData }) => {
      const res = await apiRequest("PATCH", apiV1(`/crm/contacts/${id}`), { data });
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [apiV1("/crm/contacts")] });
      toast({
        title: "Contact updated",
        description: "The contact has been updated successfully.",
      });
      setEditModalOpen(false);
      setSelectedContact(null);
    },
    onError: (error: ApiError) => {
      toast({
        title: "Update failed",
        description: error.message || "Failed to update contact",
        variant: "destructive",
      });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: async (id: string) => {
      const res = await apiRequest("DELETE", apiV1(`/crm/contacts/${id}`), {});
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [apiV1("/crm/contacts")] });
      toast({
        title: "Contact deleted",
        description: "The contact has been deleted successfully.",
      });
      setDeleteConfirmOpen(false);
      setSelectedContact(null);
    },
    onError: (error: ApiError) => {
      toast({
        title: "Deletion failed",
        description: error.message || "Failed to delete contact",
        variant: "destructive",
      });
    },
  });

  const contacts = useMemo(() => {
    return allAccumulatedContacts;
  }, [allAccumulatedContacts]);

  // Extract unique tags from all contacts for the filter
  const availableTags = useMemo(() => {
    const tagSet = new Set<string>();
    contacts.forEach((contact) => {
      contact.tags?.forEach((tag) => tagSet.add(tag));
    });
    return Array.from(tagSet).sort();
  }, [contacts]);

  const handleToggleTag = (tag: string) => {
    setSelectedTags((prev) =>
      prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag]
    );
    setContactsOffset(0);
    setAllAccumulatedContacts([]);
  };

  const handleClearTags = () => {
    setSelectedTags([]);
    setContactsOffset(0);
    setAllAccumulatedContacts([]);
  };

  const handleTableScroll = (event: React.UIEvent<HTMLDivElement>) => {
    const element = event.currentTarget;
    const isNearBottom = element.scrollHeight - element.scrollTop <= element.clientHeight + 100;
    if (isNearBottom && hasMoreContacts && !isLoading) {
      setContactsOffset(prev => prev + 20);
    }
  };

  const handleCreateContact = (data: ContactFormData) => {
    createMutation.mutate(data);
  };

  const handleEditContact = (data: ContactFormData) => {
    if (selectedContact) {
      updateMutation.mutate({ id: selectedContact.id, data });
    }
  };

  const openEditModal = (contact: Contact) => {
    setSelectedContact(contact);
    editForm.reset({
      name: contact.name,
      email: contact.email || "",
      phone: contact.phone || "",
      company: contact.company || "",
      type: (contact.type as any) || "Lead",
    });
    setEditModalOpen(true);
  };

  const openViewModal = (contact: Contact) => {
    setSelectedContact(contact);
    setViewModalOpen(true);
  };

  const openDeleteConfirm = (contact: Contact) => {
    setSelectedContact(contact);
    setDeleteConfirmOpen(true);
  };

  const handleDeleteConfirm = () => {
    if (selectedContact) {
      deleteMutation.mutate(selectedContact.id);
    }
  };

  // Calculate metrics from the summary endpoint or fallback to local data
  const summary = summaryQuery.data;
  const metrics = useMemo(() => {
    const total = summary?.total ?? totalContactsCount;
    if (!total && !contacts.length) return undefined;
    
    // Fallback to local counts if summary is unavailable
    const localWithEmail = allAccumulatedContacts.filter(c => c.email).length;
    const localWithPhone = allAccumulatedContacts.filter(c => c.phone).length;
    
    const withEmail = summary?.with_email ?? localWithEmail;
    const withPhone = summary?.with_phone ?? localWithPhone;
    
    return [
      {
        label: "Total",
        value: (total || 0).toLocaleString(),
        testId: "text-total-contacts",
      },
      {
        label: "With Email",
        value: withEmail.toLocaleString(),
        testId: "text-with-email",
      },
      {
        label: "With Phone",
        value: withPhone.toLocaleString(),
        testId: "text-with-phone",
      },
    ];
  }, [summary, contacts, totalContactsCount, allAccumulatedContacts]);

  const hasContacts = contacts.length > 0;

  return (
    <PageLayout
      title="Contactos"
      description="Manage your customer contacts and relationships"
      metrics={metrics}
      ctaLabel="Nuevo Contacto"
      ctaIcon={Plus}
      onCtaClick={() => setCreateModalOpen(true)}
      ctaTestId="button-nuevo-contacto"
      toolbar={
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-3 flex-1">
            <div className="relative flex-1 max-w-md">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
              <Input
                placeholder="Search contacts..."
                value={searchTerm}
                onChange={(e) => handleSearchChange(e.target.value)}
                className="pl-10"
                data-testid="input-search"
              />
            </div>
            <select
              value={selectedType}
              onChange={(e) => handleTypeChange(e.target.value)}
              className="h-10 px-4 py-2 rounded-md border border-input bg-background text-sm hover-elevate active-elevate-2 cursor-pointer focus:outline-none focus:ring-2 focus:ring-primary"
              data-testid="select-filter"
            >
              <option value="all">All Types</option>
              <option value="Lead">Lead</option>
              <option value="Customer">Customer</option>
              <option value="Partner">Partner</option>
              <option value="Vendor">Vendor</option>
            </select>

            {/* Tag Filter */}
            <Popover open={tagFilterOpen} onOpenChange={setTagFilterOpen}>
              <PopoverTrigger asChild>
                <Button
                  variant="outline"
                  size="default"
                  className="gap-2"
                  data-testid="button-tag-filter"
                >
                  <Tag className="h-4 w-4" />
                  Tags
                  {selectedTags.length > 0 && (
                    <Badge variant="secondary" className="ml-1 rounded-full h-5 w-5 p-0 flex items-center justify-center text-xs">
                      {selectedTags.length}
                    </Badge>
                  )}
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-64 p-0" align="start">
                <Command>
                  <CommandInput placeholder="Search tags..." data-testid="input-tag-search" />
                  <CommandList>
                    <CommandEmpty>No tags found.</CommandEmpty>
                    <CommandGroup>
                      {availableTags.map((tag) => (
                        <CommandItem
                          key={tag}
                          onSelect={() => handleToggleTag(tag)}
                          className="cursor-pointer"
                          data-testid={`tag-option-${tag}`}
                        >
                          <Checkbox
                            checked={selectedTags.includes(tag)}
                            className="mr-2"
                          />
                          {tag}
                        </CommandItem>
                      ))}
                    </CommandGroup>
                  </CommandList>
                  {selectedTags.length > 0 && (
                    <div className="border-t p-2">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={handleClearTags}
                        className="w-full"
                        data-testid="button-clear-tags"
                      >
                        Clear filters
                      </Button>
                    </div>
                  )}
                </Command>
              </PopoverContent>
            </Popover>

            {/* Selected Tags Display */}
            {selectedTags.length > 0 && (
              <div className="flex items-center gap-2 flex-wrap">
                {selectedTags.map((tag) => (
                  <Badge
                    key={tag}
                    variant="secondary"
                    className="gap-1 pr-1"
                    data-testid={`selected-tag-${tag}`}
                  >
                    {tag}
                    <button
                      onClick={() => handleToggleTag(tag)}
                      className="hover:bg-accent rounded-full p-0.5"
                      data-testid={`button-remove-tag-${tag}`}
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </Badge>
                ))}
              </div>
            )}
          </div>
        </div>
      }
    >
      <GlassPanel className="overflow-hidden">
        {isLoading ? (
          <EmptyState
            title="Loading contacts"
            description="Fetching contacts from the backend..."
            isLoading
          />
        ) : isError ? (
          <div className="py-12">
            <ErrorDisplay
              error={error}
              endpoint="api/v1/crm/contacts"
            />
          </div>
        ) : !hasContacts ? (
          <EmptyState
            title="No contacts found"
            description="Create a new contact or adjust your search filters."
          />
        ) : (
          <div className="overflow-x-auto h-full flex flex-col">
            <div className="overflow-y-auto flex-1" onScroll={handleTableScroll}>
              <table className="w-full">
                <thead className="bg-white/40 border-b border-white/60 sticky top-0">
                  <tr>
                    <th className="text-left py-3 px-4 w-12">
                      <Checkbox data-testid="checkbox-select-all" />
                    </th>
                    <th className="text-left py-3 px-4 text-xs font-semibold uppercase tracking-wider text-[#58a6ff]">
                      Name
                    </th>
                    <th className="text-left py-3 px-4 text-xs font-semibold uppercase tracking-wider text-[#58a6ff]">
                      Email
                    </th>
                    <th className="text-left py-3 px-4 text-xs font-semibold uppercase tracking-wider text-[#58a6ff]">
                      Company
                    </th>
                    <th className="text-left py-3 px-4 text-xs font-semibold uppercase tracking-wider text-[#58a6ff]">
                      Phone
                    </th>
                    <th className="text-left py-3 px-4 text-xs font-semibold uppercase tracking-wider text-[#58a6ff]">
                      Type
                    </th>
                    <th className="w-24"></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/40 bg-white/60" ref={tableBodyRef}>
                {contacts.map((contact) => (
                  <tr
                    key={contact.id}
                    className="hover:bg-white/80 transition-all"
                    data-testid={`row-contact-${contact.id}`}
                  >
                    <td className="py-3 px-4">
                      <Checkbox data-testid={`checkbox-contact-${contact.id}`} />
                    </td>
                    <td className="py-3 px-4 font-medium" data-testid={`text-name-${contact.id}`}>
                      {contact.name}
                    </td>
                    <td className="py-3 px-4 text-muted-foreground text-sm">
                      {contact.email || "-"}
                    </td>
                    <td className="py-3 px-4 text-muted-foreground text-sm">
                      {contact.company || "-"}
                    </td>
                    <td className="py-3 px-4 text-sm" data-testid={`text-phone-${contact.id}`}>
                      {contact.phone || "-"}
                    </td>
                    <td className="py-3 px-4">
                      <Badge variant="secondary" className="font-normal" data-testid={`badge-type-${contact.id}`}>
                        {contact.type || "Unknown"}
                      </Badge>
                    </td>
                    <td className="py-3 px-4">
                      <div className="flex items-center gap-1">
                        <Button
                          size="icon"
                          variant="ghost"
                          onClick={() => openViewModal(contact)}
                          data-testid={`button-view-${contact.id}`}
                        >
                          <Eye className="h-4 w-4" />
                        </Button>
                        <Button
                          size="icon"
                          variant="ghost"
                          onClick={() => openEditModal(contact)}
                          data-testid={`button-edit-${contact.id}`}
                        >
                          <Edit className="h-4 w-4" />
                        </Button>
                        <Button
                          size="icon"
                          variant="ghost"
                          onClick={() => openDeleteConfirm(contact)}
                          data-testid={`button-delete-${contact.id}`}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
              </table>
            </div>
            {hasMoreContacts && !isLoading && (
              <div className="flex justify-center py-3 border-t border-white/60">
                <p className="text-xs text-muted-foreground">Scroll to load more contacts</p>
              </div>
            )}
            {isLoading && contactsOffset > 0 && (
              <div className="flex justify-center py-3">
                <p className="text-xs text-muted-foreground">Loading more contacts...</p>
              </div>
            )}
          </div>
        )}
      </GlassPanel>

      {/* Create Contact Modal */}
      <Dialog open={createModalOpen} onOpenChange={setCreateModalOpen}>
        <DialogContent data-testid="dialog-create-contact">
          <DialogHeader>
            <DialogTitle>Create New Contact</DialogTitle>
            <DialogDescription>
              Add a new contact to your CRM
            </DialogDescription>
          </DialogHeader>

          <Form {...createForm}>
            <form onSubmit={createForm.handleSubmit(handleCreateContact)} className="space-y-4">
              <FormField
                control={createForm.control}
                name="name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Name</FormLabel>
                    <FormControl>
                      <Input {...field} data-testid="input-contact-name" />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={createForm.control}
                name="email"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Email</FormLabel>
                    <FormControl>
                      <Input type="email" {...field} data-testid="input-contact-email" />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={createForm.control}
                name="phone"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Phone</FormLabel>
                    <FormControl>
                      <Input {...field} data-testid="input-contact-phone" />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={createForm.control}
                name="company"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Company</FormLabel>
                    <FormControl>
                      <Input {...field} data-testid="input-contact-company" />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={createForm.control}
                name="type"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Type</FormLabel>
                    <Select onValueChange={field.onChange} value={field.value}>
                      <FormControl>
                        <SelectTrigger data-testid="select-contact-type">
                          <SelectValue placeholder="Select type" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value="Lead">Lead</SelectItem>
                        <SelectItem value="Customer">Customer</SelectItem>
                        <SelectItem value="Partner">Partner</SelectItem>
                        <SelectItem value="Vendor">Vendor</SelectItem>
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <DialogFooter>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setCreateModalOpen(false)}
                  data-testid="button-cancel-create"
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  disabled={createMutation.isPending}
                  data-testid="button-save-contact"
                >
                  {createMutation.isPending ? "Creating..." : "Create Contact"}
                </Button>
              </DialogFooter>
            </form>
          </Form>
        </DialogContent>
      </Dialog>

      {/* Edit Contact Modal */}
      <Dialog open={editModalOpen} onOpenChange={setEditModalOpen}>
        <DialogContent data-testid="dialog-edit-contact">
          <DialogHeader>
            <DialogTitle>Edit Contact</DialogTitle>
            <DialogDescription>
              Update contact information
            </DialogDescription>
          </DialogHeader>

          <Form {...editForm}>
            <form onSubmit={editForm.handleSubmit(handleEditContact)} className="space-y-4">
              <FormField
                control={editForm.control}
                name="name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Name</FormLabel>
                    <FormControl>
                      <Input {...field} data-testid="input-edit-name" />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={editForm.control}
                name="email"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Email</FormLabel>
                    <FormControl>
                      <Input type="email" {...field} data-testid="input-edit-email" />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={editForm.control}
                name="phone"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Phone</FormLabel>
                    <FormControl>
                      <Input {...field} data-testid="input-edit-phone" />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={editForm.control}
                name="company"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Company</FormLabel>
                    <FormControl>
                      <Input {...field} data-testid="input-edit-company" />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={editForm.control}
                name="type"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Type</FormLabel>
                    <Select onValueChange={field.onChange} value={field.value}>
                      <FormControl>
                        <SelectTrigger data-testid="select-edit-type">
                          <SelectValue placeholder="Select type" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value="Lead">Lead</SelectItem>
                        <SelectItem value="Customer">Customer</SelectItem>
                        <SelectItem value="Partner">Partner</SelectItem>
                        <SelectItem value="Vendor">Vendor</SelectItem>
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <DialogFooter>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setEditModalOpen(false)}
                  data-testid="button-cancel-edit"
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  disabled={updateMutation.isPending}
                  data-testid="button-update-contact"
                >
                  {updateMutation.isPending ? "Updating..." : "Update Contact"}
                </Button>
              </DialogFooter>
            </form>
          </Form>
        </DialogContent>
      </Dialog>

      {/* View Contact Modal */}
      <ContactDetailsModal
        open={viewModalOpen}
        onOpenChange={setViewModalOpen}
        contactId={selectedContact?.id ?? null}
        initialContact={selectedContact ? contactToDetailsContact(selectedContact) : null}
        onEdit={(c) => {
          setViewModalOpen(false);
          openEditModal(detailsContactToContact(c));
        }}
      />

      {/* Delete Confirmation */}
      <AlertDialog open={deleteConfirmOpen} onOpenChange={setDeleteConfirmOpen}>
        <AlertDialogContent data-testid="dialog-delete-confirm">
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Contact</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete {selectedContact?.name}? This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel data-testid="button-cancel-delete">Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDeleteConfirm}
              data-testid="button-confirm-delete"
            >
              {deleteMutation.isPending ? "Deleting..." : "Delete"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </PageLayout>
  );
}
