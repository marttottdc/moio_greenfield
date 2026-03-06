import { useState } from "react";
import { MessageCircle, Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useToast } from "@/hooks/use-toast";

interface TemplateComponent {
  type: "HEADER" | "BODY" | "FOOTER" | "BUTTONS";
  format?: "IMAGE" | "DOCUMENT" | "TEXT";
  text?: string;
  example?: {
    header_handle?: string[];
    body_text?: string[];
    body_text_named_params?: Record<string, string>;
  };
  buttons?: Array<{
    text: string;
    type?: string;
  }>;
}

interface WhatsAppTemplate {
  id?: string;
  name: string;
  category?: string;
  language?: string;
  components: TemplateComponent[];
}

function extractPlaceholders(text: string): string[] {
  const matches = text.match(/\{\{([^}]+)\}\}/g) || [];
  return matches
    .map((m) => m.replace(/[{}]/g, ""))
    .filter((v, i, a) => a.indexOf(v) === i);
}

function replacePlaceholders(
  text: string,
  params?: string[] | Record<string, string>
): string {
  if (!params) return text;

  if (typeof params === "object" && !Array.isArray(params)) {
    let result = text;
    Object.entries(params).forEach(([key, value]) => {
      result = result.replace(`{{${key}}}`, value || `{{${key}}}`);
    });
    return result;
  }

  if (Array.isArray(params)) {
    let result = text;
    params.forEach((value) => {
      result = result.replace(/\{\{[^}]*\}\}/, value || "");
    });
    return result;
  }

  return text;
}

interface WhatsAppTemplatePreviewProps {
  template: WhatsAppTemplate;
  timestamp?: string;
  mode?: "preview" | "test";
  onModeChange?: (mode: "preview" | "test") => void;
  onTest?: (params: Record<string, string>, phone: string) => Promise<void>;
  onConfirm?: () => void;
  isLoading?: boolean;
}

export function WhatsAppTemplatePreview({
  template,
  timestamp = "3:58 am",
  mode = "preview",
  onModeChange,
  onTest,
  onConfirm,
  isLoading = false,
}: WhatsAppTemplatePreviewProps) {
  const { toast } = useToast();
  const [testMode, setTestMode] = useState(mode === "test");
  const [testParams, setTestParams] = useState<Record<string, string>>({});
  const [phoneNumber, setPhoneNumber] = useState("");
  const [isSending, setIsSending] = useState(false);

  const bodyComponent = template.components.find((c) => c.type === "BODY");
  const placeholders = bodyComponent?.text
    ? extractPlaceholders(bodyComponent.text)
    : [];

  const handleTestModeToggle = () => {
    const newMode = !testMode;
    setTestMode(newMode);
    onModeChange?.(newMode ? "test" : "preview");
  };

  const handleSendTest = async () => {
    if (!phoneNumber.trim()) {
      toast({
        title: "Error",
        description: "Please enter a phone number",
        variant: "destructive",
      });
      return;
    }

    if (placeholders.length > 0) {
      const missingParams = placeholders.filter((p) => !testParams[p]?.trim());
      if (missingParams.length > 0) {
        toast({
          title: "Missing Parameters",
          description: `Please fill in: ${missingParams.join(", ")}`,
          variant: "destructive",
        });
        return;
      }
    }

    try {
      setIsSending(true);
      await onTest?.(testParams, phoneNumber);
      toast({
        title: "Success",
        description: "Test message sent successfully",
      });
      setPhoneNumber("");
      setTestParams({});
    } catch (error) {
      toast({
        title: "Error",
        description: error instanceof Error ? error.message : "Failed to send test message",
        variant: "destructive",
      });
    } finally {
      setIsSending(false);
    }
  };

  const previewParams: Record<string, string> = testMode
    ? testParams
    : bodyComponent?.example?.body_text_named_params || {};

  return (
    <div className="flex justify-center items-start min-h-screen bg-gradient-to-br from-slate-100 to-slate-200 p-4">
      {/* Phone Frame */}
      <div className="w-full max-w-sm bg-slate-900 rounded-3xl shadow-2xl overflow-hidden border-8 border-slate-800">
        {/* Phone Status Bar */}
        <div className="bg-slate-950 text-white px-4 py-2 flex items-center justify-between text-xs">
          <span>9:41</span>
          <MessageCircle className="w-4 h-4" />
        </div>

        {/* Chat Header */}
        <div className="bg-slate-100 px-4 py-3 border-b border-slate-200">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-gradient-to-br from-green-400 to-green-600 flex items-center justify-center text-white font-bold text-sm">
              {template.name.charAt(0)}
            </div>
            <div className="flex-1">
              <h3 className="font-semibold text-slate-900 text-sm">
                {template.name}
              </h3>
              <p className="text-xs text-slate-500">Tu plantilla</p>
            </div>
          </div>
        </div>

        {/* Chat Messages Area */}
        <div
          className="bg-gradient-to-br from-slate-50 via-white to-slate-50 p-3 min-h-96 max-h-[600px] overflow-y-auto flex flex-col gap-3"
          style={{
            backgroundImage:
              "url(\"data:image/svg+xml,%3Csvg width='60' height='60' viewBox='0 0 60 60' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none' fill-rule='evenodd'%3E%3Cg fill='%23f1f5f9' fill-opacity='0.05'%3E%3Cpath d='M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E\")",
          }}
        >
          {/* Message Bubble */}
          <div className="flex justify-start">
            <div className="bg-white rounded-2xl rounded-tl-md shadow-sm max-w-xs p-0 overflow-hidden">
              {/* Header Component */}
              {template.components
                .filter((c) => c.type === "HEADER")
                .map((component, idx) => (
                  <div key={`header-${idx}`}>
                    {component.format === "IMAGE" && component.example?.header_handle?.[0] && (
                      <img
                        src={component.example.header_handle[0]}
                        alt="Template header"
                        className="w-full h-40 object-cover"
                      />
                    )}
                    {component.format === "DOCUMENT" && component.example?.header_handle?.[0] && (
                      <div className="bg-slate-100 p-3 text-center text-sm text-slate-600">
                        📎 Document
                      </div>
                    )}
                    {component.format === "TEXT" && component.text && (
                      <div className="bg-slate-50 px-4 py-2 border-b border-slate-100 font-bold text-slate-900">
                        {component.text}
                      </div>
                    )}
                  </div>
                ))}

              {/* Body Component */}
              {template.components
                .filter((c) => c.type === "BODY")
                .map((component, idx) => {
                  const bodyText = replacePlaceholders(
                    component.text || "",
                    previewParams
                  );

                  return (
                    <div
                      key={`body-${idx}`}
                      className="px-4 py-3 text-slate-900 text-sm leading-relaxed whitespace-pre-wrap"
                    >
                      {bodyText}
                    </div>
                  );
                })}

              {/* Footer Component */}
              {template.components
                .filter((c) => c.type === "FOOTER")
                .map((component, idx) => (
                  <div
                    key={`footer-${idx}`}
                    className="px-4 py-2 text-xs text-slate-500 italic border-t border-slate-100"
                  >
                    {component.text}
                  </div>
                ))}

              {/* Buttons Component */}
              {template.components
                .filter((c) => c.type === "BUTTONS")
                .map((component, idx) => (
                  <div key={`buttons-${idx}`} className="px-4 py-3 border-t border-slate-100 flex flex-col gap-2">
                    {component.buttons?.map((button, btnIdx) => (
                      <button
                        key={btnIdx}
                        disabled
                        className="w-full px-3 py-2 text-center text-sm font-medium text-blue-500 border border-blue-500 rounded hover:bg-blue-50 disabled:opacity-70 disabled:cursor-not-allowed"
                      >
                        {button.text}
                      </button>
                    ))}
                  </div>
                ))}

              {/* Timestamp */}
              <div className="px-4 py-1 text-xs text-slate-400 text-right">
                {timestamp}
              </div>
            </div>
          </div>
        </div>

        {/* Input Bar */}
        <div className="bg-slate-100 px-3 py-2 border-t border-slate-200 flex items-center gap-2">
          <div className="flex-1 bg-white rounded-full px-4 py-2 text-xs text-slate-400">
            Message...
          </div>
          <button className="text-green-500 font-bold text-lg">→</button>
        </div>
      </div>

      {/* Right Panel - Test/Confirm */}
      <div className="flex-1 ml-6 max-w-md">
        {testMode ? (
          <div className="bg-white rounded-lg shadow-lg p-6 space-y-4">
            <h3 className="font-semibold text-lg">Test Message</h3>

            {/* Phone Number Input */}
            <div className="space-y-2">
              <label className="text-sm font-medium">WhatsApp Phone Number</label>
              <Input
                type="tel"
                placeholder="Enter phone number"
                value={phoneNumber}
                onChange={(e) => setPhoneNumber(e.target.value)}
                disabled={isSending || isLoading}
                data-testid="input-test-phone"
              />
            </div>

            {/* Parameter Inputs */}
            {placeholders.length > 0 && (
              <div className="space-y-3 border-t pt-4">
                <p className="text-sm font-medium">Template Parameters</p>
                {placeholders.map((param) => (
                  <div key={param} className="space-y-1">
                    <label className="text-xs font-medium">{param}</label>
                    <Input
                      type="text"
                      placeholder={`Enter ${param}`}
                      value={testParams[param] || ""}
                      onChange={(e) =>
                        setTestParams((prev) => ({
                          ...prev,
                          [param]: e.target.value,
                        }))
                      }
                      disabled={isSending || isLoading}
                      data-testid={`input-param-${param}`}
                    />
                  </div>
                ))}
              </div>
            )}

            {/* Action Buttons */}
            <div className="flex gap-2 pt-4 border-t">
              <Button
                variant="outline"
                size="sm"
                onClick={handleTestModeToggle}
                disabled={isSending || isLoading}
                data-testid="button-back-to-preview"
              >
                Back
              </Button>
              <Button
                size="sm"
                onClick={handleSendTest}
                disabled={isSending || isLoading}
                data-testid="button-send-test"
              >
                {isSending ? "Sending..." : "Send Test"}
                <Send className="w-4 h-4 ml-2" />
              </Button>
            </div>
          </div>
        ) : (
          <div className="bg-white rounded-lg shadow-lg p-6 space-y-4">
            <h3 className="font-semibold text-lg">Template Details</h3>

            {template.category && (
              <div>
                <p className="text-xs text-muted-foreground">Category</p>
                <p className="text-sm font-medium">{template.category}</p>
              </div>
            )}

            {template.language && (
              <div>
                <p className="text-xs text-muted-foreground">Language</p>
                <p className="text-sm font-medium">{template.language}</p>
              </div>
            )}

            {placeholders.length > 0 && (
              <div>
                <p className="text-xs text-muted-foreground">Required Parameters</p>
                <div className="flex flex-wrap gap-2 mt-2">
                  {placeholders.map((param) => (
                    <span
                      key={param}
                      className="text-xs bg-slate-100 px-2 py-1 rounded"
                    >
                      {param}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Action Buttons */}
            <div className="flex gap-2 pt-4 border-t">
              <Button
                variant="outline"
                size="sm"
                onClick={handleTestModeToggle}
                disabled={isLoading}
                data-testid="button-test-template"
              >
                Test Message
              </Button>
              <Button
                size="sm"
                onClick={onConfirm}
                disabled={isLoading}
                data-testid="button-confirm-template"
              >
                Confirm
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
