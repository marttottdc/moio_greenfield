import { useState, useCallback, useRef, useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { useToast } from "@/hooks/use-toast";
import { apiRequest, fetchJson } from "@/lib/queryClient";
import { apiV1 } from "@/lib/api";
import { useCampaignFlow, useCreateCampaignDraft } from "@/hooks/use-campaign-flow";
import type {
  CampaignChannel,
  CampaignKind,
  CampaignTemplate,
  StagingImport,
  StagingColumn,
  FieldMapping,
  MappingValidationResult,
  DripStep,
  CampaignSchedule,
} from "@shared/schema";
import {
  Loader2,
  Upload,
  FileSpreadsheet,
  Check,
  X,
  AlertCircle,
  MessageSquare,
  Mail,
  Send,
  Calendar,
  Clock,
  Zap,
  CalendarCheck,
  ArrowRight,
  ChevronLeft,
  ChevronRight,
  Plus,
  Trash2,
} from "lucide-react";

export interface ResumeCampaignData {
  id: string;
  name: string;
  description?: string | null;
  channel: CampaignChannel;
  kind: CampaignKind;
  config?: {
    message?: {
      template_id?: string;
      template_name?: string;
      map?: Array<{ source: string; target: string }>;
    };
    schedule?: {
      date?: string | null;
      timezone?: string | null;
    };
  };
  configuration_state?: {
    template?: boolean;
    mapping?: boolean;
    data_ready?: boolean;
    schedule?: boolean;
  };
}

interface CampaignWizardV2Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  resumeCampaign?: ResumeCampaignData | null;
}

interface WizardState {
  campaignId: string | null;
  name: string;
  description: string;
  channel: CampaignChannel;
  kind: CampaignKind;
  templateId: string;
  template: CampaignTemplate | null;
  stagingId: string;
  stagingData: StagingImport | null;
  mappings: FieldMapping[];
  schedule: CampaignSchedule;
}

const initialState: WizardState = {
  campaignId: null,
  name: "",
  description: "",
  channel: "whatsapp",
  kind: "express",
  templateId: "",
  template: null,
  stagingId: "",
  stagingData: null,
  mappings: [],
  schedule: {
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
  },
};

const steps = [
  { id: 1, title: "Channel & Type", icon: MessageSquare },
  { id: 2, title: "Template", icon: FileSpreadsheet },
  { id: 3, title: "Data Upload", icon: Upload },
  { id: 4, title: "Field Mapping", icon: ArrowRight },
  { id: 5, title: "Timing", icon: Clock },
  { id: 6, title: "Review", icon: Check },
];

const channelOptions: { value: CampaignChannel; label: string; icon: typeof MessageSquare; description: string }[] = [
  { value: "whatsapp", label: "WhatsApp", icon: MessageSquare, description: "Send messages via WhatsApp Business" },
  { value: "email", label: "Email", icon: Mail, description: "Send email campaigns" },
  { value: "sms", label: "SMS", icon: Send, description: "Send SMS text messages" },
];

const kindOptions: { value: CampaignKind; label: string; icon: typeof Zap; description: string }[] = [
  { value: "express", label: "Express", icon: Zap, description: "Send immediately to all recipients" },
  { value: "one_shot", label: "Scheduled", icon: Calendar, description: "Schedule for a specific date and time" },
  { value: "drip", label: "Drip", icon: Clock, description: "Send in sequence with delays" },
  { value: "planned", label: "Planned", icon: CalendarCheck, description: "Plan sends over a date range" },
];

const TEMPLATES_PATH = apiV1("/resources/whatsapp-templates/");
const CAMPAIGNS_PATH = apiV1("/campaigns/campaigns/");

const getChannelParam = (channel: CampaignChannel): string => {
  const channelMap: Record<CampaignChannel, string> = {
    whatsapp: "WhatsApp",
    email: "Email",
    sms: "SMS",
  };
  return channelMap[channel] || channel;
};

export function CampaignWizardV2({ open, onOpenChange, resumeCampaign }: CampaignWizardV2Props) {
  const [step, setStep] = useState(1);
  const [state, setState] = useState<WizardState>(initialState);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [isUploading, setIsUploading] = useState(false);
  const [mappingValidation, setMappingValidation] = useState<MappingValidationResult | null>(null);
  const [isInitialized, setIsInitialized] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const queryClient = useQueryClient();
  const { toast } = useToast();

  const createDraftMutation = useCreateCampaignDraft();

  const { executeTransition, isTransitioning, flowState, refetch: refetchFlowState } = useCampaignFlow({
    campaignId: state.campaignId,
    enabled: !!state.campaignId,
    onTransitionSuccess: (response) => {
      if (response.new_state === "ACTIVE" || response.new_state === "SCHEDULED") {
        queryClient.invalidateQueries({ queryKey: [CAMPAIGNS_PATH] });
        toast({
          title: response.new_state === "SCHEDULED" ? "Campaign scheduled" : "Campaign launched",
          description: response.message,
        });
        handleClose();
      }
    },
    onTransitionError: (error) => {
      toast({
        variant: "destructive",
        title: "Transition failed",
        description: error.message || "Please try again.",
      });
    },
  });

  const templatesQuery = useQuery<CampaignTemplate[]>({
    queryKey: [TEMPLATES_PATH, { channel: getChannelParam(state.channel) }],
    queryFn: async () => {
      const response = await fetchJson<{ templates: CampaignTemplate[] }>(TEMPLATES_PATH, { channel: getChannelParam(state.channel) });
      return response.templates || [];
    },
    enabled: open,
  });

  const isProcessing = createDraftMutation.isPending || isTransitioning || isUploading;

  useEffect(() => {
    if (open && resumeCampaign && !isInitialized) {
      const savedMappings: FieldMapping[] = resumeCampaign.config?.message?.map?.map(m => ({
        variable_name: m.target,
        column_name: m.source,
      })) || [];

      setState({
        campaignId: resumeCampaign.id,
        name: resumeCampaign.name,
        description: resumeCampaign.description || "",
        channel: resumeCampaign.channel,
        kind: resumeCampaign.kind,
        templateId: resumeCampaign.config?.message?.template_id || "",
        template: null,
        stagingId: "",
        stagingData: null,
        mappings: savedMappings,
        schedule: {
          timezone: resumeCampaign.config?.schedule?.timezone || Intl.DateTimeFormat().resolvedOptions().timeZone,
          start_at: resumeCampaign.config?.schedule?.date || undefined,
        },
      });
      
      setStep(2);
      setIsInitialized(true);
      
      toast({
        title: "Continuing campaign",
        description: "Please verify your template and upload your data to continue.",
      });
      
      refetchFlowState(resumeCampaign.id).catch(() => {});
    }
  }, [open, resumeCampaign, isInitialized, refetchFlowState, toast]);

  useEffect(() => {
    if (templatesQuery.data && state.templateId && !state.template) {
      const matchingTemplate = templatesQuery.data.find(t => t.id === state.templateId);
      if (matchingTemplate) {
        setState(prev => ({ ...prev, template: matchingTemplate }));
      }
    }
  }, [templatesQuery.data, state.templateId, state.template]);

  useEffect(() => {
    if (!open) {
      setIsInitialized(false);
    }
  }, [open]);

  const handleClose = () => {
    onOpenChange(false);
    setStep(1);
    setState(initialState);
    setUploadProgress(0);
    setMappingValidation(null);
    setIsInitialized(false);
  };

  const handleFileUpload = useCallback(async (file: File) => {
    if (!file) return;

    const validTypes = [
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      "application/vnd.ms-excel",
      "text/csv",
    ];

    if (!validTypes.includes(file.type) && !file.name.match(/\.(xlsx|xls|csv)$/i)) {
      toast({
        variant: "destructive",
        title: "Invalid file type",
        description: "Please upload an Excel (.xlsx, .xls) or CSV file.",
      });
      return;
    }

    setIsUploading(true);
    setUploadProgress(0);

    const formData = new FormData();
    formData.append("file", file);

    try {
      const progressInterval = setInterval(() => {
        setUploadProgress((prev) => Math.min(prev + 10, 90));
      }, 200);

      const res = await apiRequest("POST", apiV1("/campaigns/data/import"), {
        body: formData,
      });

      clearInterval(progressInterval);
      setUploadProgress(100);

      const data = (await res.json()) as StagingImport;
      setState((prev) => {
        const autoMapped = autoMapColumns(data.columns, state.template?.variables || []);
        const validSavedMappings = prev.mappings.filter(savedMapping => 
          data.columns.some(col => col.name === savedMapping.column_name)
        );
        const mergedMappings = [...autoMapped];
        for (const savedMapping of validSavedMappings) {
          const existsInAuto = mergedMappings.some(m => m.variable_name === savedMapping.variable_name);
          if (!existsInAuto) {
            mergedMappings.push(savedMapping);
          } else {
            const idx = mergedMappings.findIndex(m => m.variable_name === savedMapping.variable_name);
            if (idx >= 0) {
              mergedMappings[idx] = savedMapping;
            }
          }
        }
        return {
          ...prev,
          stagingId: data.staging_id,
          stagingData: data,
          mappings: mergedMappings,
        };
      });

      toast({
        title: "File uploaded",
        description: `${data.total_rows} rows found with ${data.columns.length} columns.`,
      });
    } catch (error) {
      toast({
        variant: "destructive",
        title: "Upload failed",
        description: error instanceof Error ? error.message : "Failed to upload file.",
      });
    } finally {
      setIsUploading(false);
    }
  }, [state.template, toast]);

  const autoMapColumns = (columns: StagingColumn[], variables: CampaignTemplate["variables"]): FieldMapping[] => {
    const mappings: FieldMapping[] = [];

    for (const variable of variables) {
      const matchingColumn = columns.find((col) => {
        const colName = col.name.toLowerCase();
        const varName = variable.name.toLowerCase();
        return colName === varName || colName.includes(varName) || varName.includes(colName);
      });

      if (matchingColumn) {
        mappings.push({
          column_name: matchingColumn.name,
          variable_name: variable.name,
        });
      }
    }

    return mappings;
  };

  const validateMappings = useCallback(async () => {
    if (!state.stagingId || state.mappings.length === 0) return;

    try {
      const res = await apiRequest("POST", apiV1("/campaigns/data/map"), {
        data: {
          staging_id: state.stagingId,
          mappings: state.mappings,
        },
      });

      const result = (await res.json()) as MappingValidationResult;
      setMappingValidation(result);
      return result.valid;
    } catch (error) {
      setMappingValidation({
        valid: false,
        errors: [{ column: "system", message: "Failed to validate mappings" }],
      });
      return false;
    }
  }, [state.stagingId, state.mappings]);

  const updateMapping = (variableName: string, columnName: string) => {
    setState((prev) => {
      const newMappings = prev.mappings.filter((m) => m.variable_name !== variableName);
      if (columnName) {
        newMappings.push({ variable_name: variableName, column_name: columnName });
      }
      return { ...prev, mappings: newMappings };
    });
    setMappingValidation(null);
  };

  const addDripStep = () => {
    setState((prev) => ({
      ...prev,
      schedule: {
        ...prev.schedule,
        drip_steps: [
          ...(prev.schedule.drip_steps || []),
          {
            step_number: (prev.schedule.drip_steps?.length || 0) + 1,
            delay_days: 1,
            delay_hours: 0,
          },
        ],
      },
    }));
  };

  const removeDripStep = (index: number) => {
    setState((prev) => ({
      ...prev,
      schedule: {
        ...prev.schedule,
        drip_steps: prev.schedule.drip_steps?.filter((_, i) => i !== index).map((step, i) => ({
          ...step,
          step_number: i + 1,
        })),
      },
    }));
  };

  const updateDripStep = (index: number, updates: Partial<DripStep>) => {
    setState((prev) => ({
      ...prev,
      schedule: {
        ...prev.schedule,
        drip_steps: prev.schedule.drip_steps?.map((step, i) =>
          i === index ? { ...step, ...updates } : step
        ),
      },
    }));
  };

  const canProceed = (): boolean => {
    switch (step) {
      case 1:
        return state.name.trim().length > 0;
      case 2:
        return !!state.templateId;
      case 3:
        return !!state.stagingId && !!state.stagingData;
      case 4:
        const requiredVariables = state.template?.variables?.filter((v) => v.required) || [];
        const mappedVariables = state.mappings.map((m) => m.variable_name);
        return requiredVariables.every((v) => mappedVariables.includes(v.name));
      case 5:
        if (state.kind === "one_shot" || state.kind === "planned") {
          return !!state.schedule.start_at;
        }
        if (state.kind === "drip") {
          return (state.schedule.drip_steps?.length || 0) > 0;
        }
        return true;
      case 6:
        return true;
      default:
        return false;
    }
  };

  const handleNext = async () => {
    try {
      if (step === 1) {
        if (state.campaignId) {
          setStep(2);
          return;
        }
        
        const result = await createDraftMutation.mutateAsync({
          name: state.name,
          description: state.description || undefined,
          channel: state.channel,
          kind: state.kind,
        });
        setState((prev) => ({ ...prev, campaignId: result.id }));
        
        try {
          await refetchFlowState(result.id);
        } catch {
          toast({
            title: "Campaign created",
            description: "Your campaign draft was saved. Some advanced features may not be available yet.",
          });
        }
        
        setStep(2);
        return;
      }

      if (step === 2) {
        await executeTransition("select-template", { template_id: state.templateId });
        setStep(3);
        return;
      }

      if (step === 3) {
        if (state.stagingData) {
          await executeTransition("import-data", {
            staging_id: state.stagingId,
            headers: state.stagingData.columns.map((c) => c.name),
            row_count: state.stagingData.total_rows,
          });
        }
        setStep(4);
        return;
      }

      if (step === 4) {
        const isValid = await validateMappings();
        if (!isValid) {
          toast({
            variant: "destructive",
            title: "Mapping validation failed",
            description: "Please fix the mapping errors before continuing.",
          });
          return;
        }
        const phoneColumn = state.stagingData?.columns.find(
          (c) => c.name.toLowerCase().includes("phone") || c.name.toLowerCase().includes("whatsapp")
        );
        await executeTransition("configure-mapping", {
          mapping: state.mappings.map((m) => ({
            source: m.column_name,
            target: m.variable_name,
          })),
          contact_name_field: phoneColumn?.name || state.stagingData?.columns[0]?.name || "phone",
        });
        setStep(5);
        return;
      }

      if (step === 5) {
        setStep(6);
        return;
      }

      if (step === 6) {
        await executeTransition("mark-ready", {});
        
        if (state.kind === "express") {
          await executeTransition("launch-now", {});
        } else if (state.kind === "one_shot" || state.kind === "planned") {
          await executeTransition("set-schedule", {
            schedule_date: state.schedule.start_at || new Date().toISOString(),
          });
        } else if (state.kind === "drip") {
          await executeTransition("launch-now", {});
        }
        return;
      }
    } catch (error) {
      console.error("Step transition error:", error);
      const errorMessage = error instanceof Error ? error.message : "An unexpected error occurred";
      
      let title = "Something went wrong";
      let description = "Please try again later.";
      
      if (errorMessage.includes("404") || errorMessage.includes("not available")) {
        title = "Feature not available";
        description = "This feature is being set up. Please try again later.";
      } else if (errorMessage.includes("401") || errorMessage.includes("unauthorized")) {
        title = "Session expired";
        description = "Please refresh the page and try again.";
      } else if (errorMessage.includes("500") || errorMessage.includes("Server error")) {
        title = "Server issue";
        description = "We're experiencing technical difficulties. Please try again later.";
      } else if (errorMessage.includes("network") || errorMessage.includes("fetch")) {
        title = "Connection problem";
        description = "Please check your internet connection and try again.";
      } else if (errorMessage && !errorMessage.includes("Transition failed")) {
        description = errorMessage;
      }
      
      toast({
        variant: "destructive",
        title,
        description,
      });
    }
  };

  const handleBack = () => setStep((prev) => Math.max(prev - 1, 1));

  const selectTemplate = (template: CampaignTemplate) => {
    setState((prev) => ({
      ...prev,
      templateId: template.id,
      template,
      mappings: prev.stagingData
        ? autoMapColumns(prev.stagingData.columns, template.variables || [])
        : [],
    }));
  };

  const renderStepIndicator = () => (
    <div className="flex items-center justify-between mb-6">
      {steps.map((s, index) => {
        const Icon = s.icon;
        const isActive = s.id === step;
        const isCompleted = s.id < step;

        return (
          <div key={s.id} className="flex items-center">
            <div
              className={`flex items-center justify-center w-10 h-10 rounded-full border-2 transition-colors ${
                isActive
                  ? "border-primary bg-primary text-primary-foreground"
                  : isCompleted
                    ? "border-primary bg-primary/10 text-primary"
                    : "border-muted-foreground/30 text-muted-foreground"
              }`}
            >
              {isCompleted ? <Check className="w-5 h-5" /> : <Icon className="w-5 h-5" />}
            </div>
            {index < steps.length - 1 && (
              <div
                className={`w-8 h-0.5 mx-1 ${
                  isCompleted ? "bg-primary" : "bg-muted-foreground/30"
                }`}
              />
            )}
          </div>
        );
      })}
    </div>
  );

  const renderStep1 = () => (
    <div className="space-y-4">
      <div className="space-y-3">
        <div>
          <Label htmlFor="campaign-name">Campaign Name</Label>
          <Input
            id="campaign-name"
            data-testid="input-campaign-name"
            placeholder="Enter campaign name"
            value={state.name}
            onChange={(e) => setState((prev) => ({ ...prev, name: e.target.value }))}
          />
        </div>
        <div>
          <Label htmlFor="campaign-description">Description (optional)</Label>
          <Textarea
            id="campaign-description"
            data-testid="input-campaign-description"
            placeholder="Describe your campaign objectives"
            rows={2}
            value={state.description}
            onChange={(e) => setState((prev) => ({ ...prev, description: e.target.value }))}
          />
        </div>
      </div>

      <Separator />

      <div className="space-y-2">
        <Label>Channel</Label>
        <div className="grid grid-cols-3 gap-2">
          {channelOptions.map((option) => {
            const Icon = option.icon;
            const isSelected = state.channel === option.value;

            return (
              <button
                key={option.value}
                type="button"
                data-testid={`button-channel-${option.value}`}
                onClick={() => setState((prev) => ({ ...prev, channel: option.value, templateId: "", template: null }))}
                className={`p-2.5 rounded-md border text-left transition-colors hover-elevate ${
                  isSelected ? "border-primary bg-primary/5" : "border-border"
                }`}
              >
                <div className="flex items-center gap-2">
                  <Icon className={`w-4 h-4 ${isSelected ? "text-primary" : "text-muted-foreground"}`} />
                  <span className="font-medium text-sm">{option.label}</span>
                </div>
              </button>
            );
          })}
        </div>
      </div>

      <div className="space-y-2">
        <Label>Campaign Type</Label>
        <div className="grid grid-cols-2 gap-2">
          {kindOptions.map((option) => {
            const Icon = option.icon;
            const isSelected = state.kind === option.value;

            return (
              <button
                key={option.value}
                type="button"
                data-testid={`button-kind-${option.value}`}
                onClick={() => setState((prev) => ({ ...prev, kind: option.value }))}
                className={`p-2.5 rounded-md border text-left transition-colors hover-elevate ${
                  isSelected ? "border-primary bg-primary/5" : "border-border"
                }`}
              >
                <div className="flex items-center gap-2">
                  <Icon className={`w-4 h-4 ${isSelected ? "text-primary" : "text-muted-foreground"}`} />
                  <span className="font-medium text-sm">{option.label}</span>
                </div>
                <p className="text-xs text-muted-foreground mt-1 line-clamp-1">{option.description}</p>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );

  const renderStep2 = () => (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-semibold">Select Template</h3>
          <p className="text-sm text-muted-foreground">
            Choose a {state.channel} template for your campaign
          </p>
        </div>
        <Badge variant="outline">{state.channel}</Badge>
      </div>

      {templatesQuery.isLoading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
        </div>
      ) : !templatesQuery.data?.length ? (
        <Card className="p-6 text-center">
          <AlertCircle className="w-10 h-10 mx-auto text-muted-foreground mb-3" />
          <p className="font-medium">No templates available</p>
          <p className="text-sm text-muted-foreground mt-1">
            Create a {state.channel} template first, then come back to create your campaign.
          </p>
        </Card>
      ) : (
        <ScrollArea className="h-[400px] pr-4">
          <div className="space-y-3">
            {templatesQuery.data.map((template) => {
              const isSelected = state.templateId === template.id;

              return (
                <button
                  key={template.id}
                  type="button"
                  data-testid={`button-template-${template.id}`}
                  onClick={() => selectTemplate(template)}
                  className={`w-full p-4 rounded-lg border text-left transition-colors hover-elevate ${
                    isSelected ? "border-primary bg-primary/5" : "border-border"
                  }`}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <p className="font-medium">{template.name}</p>
                        {template.status && (
                          <Badge variant={template.status === "APPROVED" ? "default" : "secondary"} className="text-xs">
                            {template.status}
                          </Badge>
                        )}
                      </div>
                      {template.category && (
                        <p className="text-xs text-muted-foreground mt-1">
                          {template.category} · {template.language?.toUpperCase() || "EN"}
                        </p>
                      )}
                      {template.variables && template.variables.length > 0 && (
                        <div className="flex flex-wrap gap-1 mt-2">
                          {template.variables.map((v) => (
                            <Badge key={v.name} variant="outline" className="text-xs">
                              {`{{${v.name}}}`}
                              {v.required && <span className="text-destructive ml-0.5">*</span>}
                            </Badge>
                          ))}
                        </div>
                      )}
                    </div>
                    {isSelected && (
                      <div className="w-6 h-6 rounded-full bg-primary flex items-center justify-center">
                        <Check className="w-4 h-4 text-primary-foreground" />
                      </div>
                    )}
                  </div>
                </button>
              );
            })}
          </div>
        </ScrollArea>
      )}
    </div>
  );

  const renderStep3 = () => (
    <div className="space-y-6">
      <div>
        <h3 className="font-semibold">Upload Data</h3>
        <p className="text-sm text-muted-foreground">
          Upload an Excel or CSV file with your recipient data
        </p>
      </div>

      <input
        ref={fileInputRef}
        type="file"
        accept=".xlsx,.xls,.csv"
        className="hidden"
        onChange={(e) => e.target.files?.[0] && handleFileUpload(e.target.files[0])}
      />

      {!state.stagingData ? (
        <div
          onClick={() => fileInputRef.current?.click()}
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            const file = e.dataTransfer.files[0];
            if (file) handleFileUpload(file);
          }}
          className="border-2 border-dashed rounded-lg p-12 text-center cursor-pointer hover:border-primary transition-colors"
        >
          {isUploading ? (
            <div className="space-y-4">
              <Loader2 className="w-10 h-10 mx-auto animate-spin text-primary" />
              <p className="text-sm text-muted-foreground">Uploading...</p>
              <Progress value={uploadProgress} className="max-w-xs mx-auto" />
            </div>
          ) : (
            <>
              <Upload className="w-10 h-10 mx-auto text-muted-foreground mb-4" />
              <p className="font-medium">Drop your file here or click to browse</p>
              <p className="text-sm text-muted-foreground mt-1">
                Supports Excel (.xlsx, .xls) and CSV files
              </p>
            </>
          )}
        </div>
      ) : (
        <Card className="p-4">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
                <FileSpreadsheet className="w-5 h-5 text-primary" />
              </div>
              <div>
                <p className="font-medium">{state.stagingData.filename}</p>
                <p className="text-sm text-muted-foreground">
                  {state.stagingData.total_rows.toLocaleString()} rows · {state.stagingData.columns.length} columns
                </p>
              </div>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setState((prev) => ({ ...prev, stagingId: "", stagingData: null, mappings: [] }));
                if (fileInputRef.current) fileInputRef.current.value = "";
              }}
            >
              <X className="w-4 h-4 mr-1" />
              Remove
            </Button>
          </div>

          <Separator className="my-4" />

          <div>
            <p className="text-sm font-medium mb-2">Preview</p>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b">
                    {state.stagingData.columns.map((col) => (
                      <th key={col.name} className="text-left p-2 font-medium">
                        {col.name}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {state.stagingData.preview_rows.slice(0, 3).map((row, idx) => (
                    <tr key={idx} className="border-b last:border-0">
                      {state.stagingData!.columns.map((col) => (
                        <td key={col.name} className="p-2 text-muted-foreground">
                          {row[col.name] || "-"}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </Card>
      )}
    </div>
  );

  const renderStep4 = () => {
    const variables = state.template?.variables || [];
    const columns = state.stagingData?.columns || [];

    return (
      <div className="space-y-6">
        <div>
          <h3 className="font-semibold">Map Fields</h3>
          <p className="text-sm text-muted-foreground">
            Connect your data columns to template variables
          </p>
        </div>

        {mappingValidation && !mappingValidation.valid && (
          <Card className="p-4 border-destructive bg-destructive/5">
            <div className="flex items-start gap-3">
              <AlertCircle className="w-5 h-5 text-destructive shrink-0 mt-0.5" />
              <div>
                <p className="font-medium text-destructive">Validation Errors</p>
                <ul className="text-sm text-destructive/90 mt-1 list-disc pl-4">
                  {mappingValidation.errors?.map((err, idx) => (
                    <li key={idx}>{err.message}</li>
                  ))}
                </ul>
              </div>
            </div>
          </Card>
        )}

        <div className="space-y-3">
          {variables.map((variable) => {
            const currentMapping = state.mappings.find((m) => m.variable_name === variable.name);
            const mappedColumn = currentMapping?.column_name || "";

            return (
              <div
                key={variable.name}
                className="flex items-center gap-4 p-3 rounded-lg border"
              >
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <Badge variant="secondary">{`{{${variable.name}}}`}</Badge>
                    {variable.required && (
                      <span className="text-xs text-destructive">Required</span>
                    )}
                  </div>
                  {variable.description && (
                    <p className="text-xs text-muted-foreground mt-1">{variable.description}</p>
                  )}
                </div>

                <ArrowRight className="w-4 h-4 text-muted-foreground shrink-0" />

                <Select
                  value={mappedColumn || "unmapped"}
                  onValueChange={(value) => updateMapping(variable.name, value === "unmapped" ? "" : value)}
                >
                  <SelectTrigger className="w-[200px]" data-testid={`select-mapping-${variable.name}`}>
                    <SelectValue placeholder="Select column" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="unmapped">Not mapped</SelectItem>
                    {columns.map((col) => (
                      <SelectItem key={col.name} value={col.name}>
                        {col.name}
                        {col.inferred_type && (
                          <span className="text-muted-foreground ml-1">({col.inferred_type})</span>
                        )}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            );
          })}
        </div>

        {mappingValidation?.sample_output && (
          <>
            <Separator />
            <div>
              <p className="text-sm font-medium mb-2">Sample Output</p>
              <Card className="p-3 bg-muted/30">
                <pre className="text-xs overflow-x-auto">
                  {JSON.stringify(mappingValidation.sample_output[0], null, 2)}
                </pre>
              </Card>
            </div>
          </>
        )}
      </div>
    );
  };

  const renderStep5 = () => (
    <div className="space-y-6">
      <div>
        <h3 className="font-semibold">Timing Configuration</h3>
        <p className="text-sm text-muted-foreground">
          Configure when to send your campaign messages
        </p>
      </div>

      {state.kind === "express" && (
        <Card className="p-6 text-center">
          <Zap className="w-10 h-10 mx-auto text-primary mb-3" />
          <p className="font-medium">Immediate Send</p>
          <p className="text-sm text-muted-foreground mt-1">
            Messages will be sent immediately after campaign launch
          </p>
        </Card>
      )}

      {(state.kind === "one_shot" || state.kind === "planned") && (
        <div className="space-y-4">
          <div>
            <Label htmlFor="start-date">
              {state.kind === "one_shot" ? "Send Date & Time" : "Start Date"}
            </Label>
            <Input
              id="start-date"
              type="datetime-local"
              data-testid="input-start-date"
              value={state.schedule.start_at || ""}
              onChange={(e) =>
                setState((prev) => ({
                  ...prev,
                  schedule: { ...prev.schedule, start_at: e.target.value },
                }))
              }
            />
          </div>

          {state.kind === "planned" && (
            <div>
              <Label htmlFor="end-date">End Date</Label>
              <Input
                id="end-date"
                type="datetime-local"
                data-testid="input-end-date"
                value={state.schedule.end_at || ""}
                onChange={(e) =>
                  setState((prev) => ({
                    ...prev,
                    schedule: { ...prev.schedule, end_at: e.target.value },
                  }))
                }
              />
            </div>
          )}

          <div>
            <Label htmlFor="timezone">Timezone</Label>
            <Select
              value={state.schedule.timezone}
              onValueChange={(value) =>
                setState((prev) => ({
                  ...prev,
                  schedule: { ...prev.schedule, timezone: value },
                }))
              }
            >
              <SelectTrigger data-testid="select-timezone">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="UTC">UTC</SelectItem>
                <SelectItem value="America/New_York">Eastern Time</SelectItem>
                <SelectItem value="America/Chicago">Central Time</SelectItem>
                <SelectItem value="America/Denver">Mountain Time</SelectItem>
                <SelectItem value="America/Los_Angeles">Pacific Time</SelectItem>
                <SelectItem value="America/Montevideo">Uruguay</SelectItem>
                <SelectItem value="America/Sao_Paulo">Brazil</SelectItem>
                <SelectItem value="Europe/London">London</SelectItem>
                <SelectItem value="Europe/Madrid">Madrid</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
      )}

      {state.kind === "drip" && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <Label>Drip Steps</Label>
            <Button variant="outline" size="sm" onClick={addDripStep} data-testid="button-add-drip-step">
              <Plus className="w-4 h-4 mr-1" />
              Add Step
            </Button>
          </div>

          {(state.schedule.drip_steps?.length || 0) === 0 ? (
            <Card className="p-6 text-center border-dashed">
              <Clock className="w-8 h-8 mx-auto text-muted-foreground mb-2" />
              <p className="text-sm text-muted-foreground">
                Add steps to create your drip sequence
              </p>
            </Card>
          ) : (
            <div className="space-y-3">
              {state.schedule.drip_steps?.map((dripStep, idx) => (
                <Card key={idx} className="p-4">
                  <div className="flex items-center justify-between mb-3">
                    <Badge>Step {dripStep.step_number}</Badge>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => removeDripStep(idx)}
                      data-testid={`button-remove-drip-${idx}`}
                    >
                      <Trash2 className="w-4 h-4" />
                    </Button>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <Label>Days after previous</Label>
                      <Input
                        type="number"
                        min="0"
                        value={dripStep.delay_days}
                        onChange={(e) =>
                          updateDripStep(idx, { delay_days: parseInt(e.target.value) || 0 })
                        }
                      />
                    </div>
                    <div>
                      <Label>Hours</Label>
                      <Input
                        type="number"
                        min="0"
                        max="23"
                        value={dripStep.delay_hours}
                        onChange={(e) =>
                          updateDripStep(idx, { delay_hours: parseInt(e.target.value) || 0 })
                        }
                      />
                    </div>
                  </div>
                </Card>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );

  const renderStep6 = () => (
    <div className="space-y-6">
      <div>
        <h3 className="font-semibold">Review & Create</h3>
        <p className="text-sm text-muted-foreground">
          Review your campaign settings before creating
        </p>
      </div>

      <Card className="divide-y">
        <div className="p-4 flex justify-between">
          <span className="text-muted-foreground">Campaign Name</span>
          <span className="font-medium">{state.name}</span>
        </div>
        <div className="p-4 flex justify-between">
          <span className="text-muted-foreground">Channel</span>
          <Badge variant="outline">{state.channel}</Badge>
        </div>
        <div className="p-4 flex justify-between">
          <span className="text-muted-foreground">Type</span>
          <Badge variant="outline">{state.kind}</Badge>
        </div>
        <div className="p-4 flex justify-between">
          <span className="text-muted-foreground">Template</span>
          <span className="font-medium">{state.template?.name || "-"}</span>
        </div>
        <div className="p-4 flex justify-between">
          <span className="text-muted-foreground">Recipients</span>
          <span className="font-medium">
            {state.stagingData?.total_rows.toLocaleString() || "0"} contacts
          </span>
        </div>
        <div className="p-4 flex justify-between">
          <span className="text-muted-foreground">Field Mappings</span>
          <span className="font-medium">{state.mappings.length} mapped</span>
        </div>
        {state.schedule.start_at && (
          <div className="p-4 flex justify-between">
            <span className="text-muted-foreground">Scheduled For</span>
            <span className="font-medium">
              {new Date(state.schedule.start_at).toLocaleString()}
            </span>
          </div>
        )}
        {state.kind === "drip" && (
          <div className="p-4 flex justify-between">
            <span className="text-muted-foreground">Drip Steps</span>
            <span className="font-medium">{state.schedule.drip_steps?.length || 0} steps</span>
          </div>
        )}
      </Card>

      {state.description && (
        <div>
          <Label className="text-muted-foreground">Description</Label>
          <p className="text-sm mt-1">{state.description}</p>
        </div>
      )}
    </div>
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[90vh] flex flex-col">
        <DialogHeader>
          <DialogTitle>Create Campaign</DialogTitle>
          <DialogDescription>
            {steps[step - 1].title} - Step {step} of {steps.length}
          </DialogDescription>
        </DialogHeader>

        {renderStepIndicator()}

        <ScrollArea className="flex-1 -mx-6 px-6">
          <div className="min-h-[400px]">
            {step === 1 && renderStep1()}
            {step === 2 && renderStep2()}
            {step === 3 && renderStep3()}
            {step === 4 && renderStep4()}
            {step === 5 && renderStep5()}
            {step === 6 && renderStep6()}
          </div>
        </ScrollArea>

        <div className="flex items-center justify-between pt-4 border-t mt-4">
          <Button variant="ghost" onClick={handleClose} disabled={isProcessing}>
            Cancel
          </Button>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              onClick={handleBack}
              disabled={step === 1 || isProcessing}
            >
              <ChevronLeft className="w-4 h-4 mr-1" />
              Back
            </Button>
            <Button
              onClick={handleNext}
              disabled={!canProceed() || isProcessing}
              data-testid="button-next-step"
            >
              {isProcessing ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  {step === 1 ? "Creating Draft..." : step === 6 ? "Launching..." : "Processing..."}
                </>
              ) : step === 6 ? (
                <>
                  {state.kind === "express" || state.kind === "drip" ? "Launch Campaign" : "Schedule Campaign"}
                  <Check className="w-4 h-4 ml-1" />
                </>
              ) : step === 1 ? (
                <>
                  Create Draft
                  <ChevronRight className="w-4 h-4 ml-1" />
                </>
              ) : (
                <>
                  Next
                  <ChevronRight className="w-4 h-4 ml-1" />
                </>
              )}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
