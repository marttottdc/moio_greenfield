import React from "react";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useWebhookHandlers } from "@/hooks/useWebhookHandlers";
import { AuthConfigFields, AuthConfig } from "./AuthConfigFields";
import { Loader2 } from "lucide-react";

const AUTH_TYPES = [
  { value: "none", label: "No Authentication" },
  { value: "bearer", label: "Bearer Token" },
  { value: "basic", label: "HTTP Basic" },
  { value: "hmac", label: "HMAC-SHA256" },
  { value: "header", label: "Custom Header" },
  { value: "query", label: "Query Parameter" },
  { value: "jwt", label: "JWT Token" },
];

export interface WebhookFormData {
  name: string;
  description: string;
  auth_type: string;
  expected_content_type: string;
  handler_path?: string;
  auth_config?: AuthConfig;
  locked?: boolean;
}

interface WebhookFormFieldsProps {
  formData: WebhookFormData;
  onChange: (data: WebhookFormData) => void;
  showLocked?: boolean;
  showHandler?: boolean;
  defaultHandler?: string;
}

export function WebhookFormFields({
  formData,
  onChange,
  showLocked = true,
  showHandler = false,
  defaultHandler,
}: WebhookFormFieldsProps) {
  // Always fetch real handlers from the API
  const handlersQuery = useWebhookHandlers();
  const handlers = handlersQuery.data || [];

  // Auto-set handler_path if defaultHandler is provided and not already set
  React.useEffect(() => {
    if (defaultHandler && !formData.handler_path) {
      onChange({ ...formData, handler_path: defaultHandler });
    }
  }, [defaultHandler, formData, onChange]);

  return (
    <div className="space-y-4">
      <div>
        <Label htmlFor="name">Name *</Label>
        <Input
          id="name"
          value={formData.name}
          onChange={(e) => onChange({ ...formData, name: e.target.value })}
          placeholder="Webhook name"
          data-testid="input-webhook-name"
        />
      </div>

      <div>
        <Label htmlFor="description">Description</Label>
        <Textarea
          id="description"
          value={formData.description}
          onChange={(e) =>
            onChange({ ...formData, description: e.target.value })
          }
          placeholder="Describe the purpose of this webhook"
          data-testid="input-webhook-description"
          className="resize-none"
          rows={3}
        />
      </div>

      {showHandler && (
        <div>
          <Label htmlFor="handler-path">Handler</Label>
          <Select
            value={formData.handler_path || ""}
            onValueChange={(value) =>
              onChange({ ...formData, handler_path: value })
            }
          >
            <SelectTrigger data-testid="select-handler">
              {handlersQuery.isLoading ? (
                <div className="flex items-center gap-2">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  <span>Loading handlers...</span>
                </div>
              ) : (
                <SelectValue />
              )}
            </SelectTrigger>
            <SelectContent>
              {handlers.map((handler) => (
                <SelectItem
                  key={handler.name}
                  value={handler.name}
                >
                  {handler.name}
                  {handler.description && (
                    <span className="ml-2 text-xs text-muted-foreground">
                      - {handler.description}
                    </span>
                  )}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}

      <div className="grid grid-cols-2 gap-4">
        <div>
          <Label htmlFor="auth-type">Authentication Type</Label>
          <Select
            value={formData.auth_type}
            onValueChange={(value) =>
              onChange({ ...formData, auth_type: value })
            }
          >
            <SelectTrigger data-testid="select-auth-type">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {AUTH_TYPES.map((type) => (
                <SelectItem key={type.value} value={type.value}>
                  {type.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div>
          <Label htmlFor="content-type">Content Type</Label>
          <Input
            id="content-type"
            value={formData.expected_content_type}
            onChange={(e) =>
              onChange({
                ...formData,
                expected_content_type: e.target.value,
              })
            }
            placeholder="application/json"
            data-testid="input-content-type"
          />
        </div>
      </div>

      {formData.auth_type !== "none" && (
        <AuthConfigFields
          authType={formData.auth_type}
          authConfig={formData.auth_config || {}}
          onChange={(config) =>
            onChange({ ...formData, auth_config: config })
          }
        />
      )}

      {showLocked && (
        <div className="flex items-center gap-2">
          <input
            type="checkbox"
            id="locked"
            checked={formData.locked || false}
            onChange={(e) =>
              onChange({ ...formData, locked: e.target.checked })
            }
            data-testid="checkbox-locked"
          />
          <Label htmlFor="locked" className="cursor-pointer mb-0">
            Lock this configuration (prevent automatic updates)
          </Label>
        </div>
      )}
    </div>
  );
}

