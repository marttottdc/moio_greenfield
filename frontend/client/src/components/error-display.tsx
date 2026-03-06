import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { formatErrorForDisplay } from "@/lib/errors";
import { AlertCircle } from "lucide-react";

const isDevelopment = import.meta.env.DEV;

interface ErrorDisplayProps {
  error: unknown;
  endpoint?: string;
  action?: {
    label: string;
    onClick: () => void;
  };
  className?: string;
}

/**
 * Reusable error display component
 * - Development: Shows summary with expandable technical details
 * - Production: Shows polite user-friendly message
 */
export function ErrorDisplay({ error, endpoint, action, className }: ErrorDisplayProps) {
  if (!error) {
    return null;
  }
  
  const errorInfo = formatErrorForDisplay(error, endpoint);

  return (
    <div className={className}>
      <div className="space-y-6 max-w-2xl w-full mx-auto">
        <div className="text-center space-y-3">
          <div className="text-destructive text-4xl">
            <AlertCircle className="h-12 w-12 mx-auto" />
          </div>
          <h2 className="text-xl font-semibold" data-testid="text-error-summary">
            {errorInfo.summary}
          </h2>

          {errorInfo.statusCode && (
            <div className="flex items-center justify-center gap-2 text-sm text-muted-foreground">
              <Badge variant="destructive" className="font-mono" data-testid="badge-status-code">
                {errorInfo.statusCode}
              </Badge>
              {errorInfo.endpoint && (
                <code className="bg-muted px-2 py-1 rounded text-xs" data-testid="text-endpoint">
                  {errorInfo.endpoint}
                </code>
              )}
            </div>
          )}
        </div>

        {/* Expandable technical details (dev only) */}
        {isDevelopment && (errorInfo.requestDetails || errorInfo.errorMessage || errorInfo.stackTrace || errorInfo.responseBody) && (
          <Accordion type="single" collapsible className="w-full">
            {errorInfo.requestDetails && (
              <AccordionItem value="request">
                <AccordionTrigger className="text-sm" data-testid="accordion-request-details">
                  Request Details
                </AccordionTrigger>
                <AccordionContent>
                  <pre className="text-xs bg-muted p-3 rounded overflow-auto max-h-20 whitespace-pre-wrap break-all font-mono">
                    {errorInfo.requestDetails}
                  </pre>
                </AccordionContent>
              </AccordionItem>
            )}
            
            {errorInfo.errorMessage && (
              <AccordionItem value="error-message">
                <AccordionTrigger className="text-sm" data-testid="accordion-error-message">
                  Error Message
                </AccordionTrigger>
                <AccordionContent>
                  <pre className="text-xs bg-muted p-3 rounded overflow-auto max-h-40 whitespace-pre-wrap break-all">
                    {errorInfo.errorMessage}
                  </pre>
                </AccordionContent>
              </AccordionItem>
            )}

            {errorInfo.responseBody && (
              <AccordionItem value="response">
                <AccordionTrigger className="text-sm" data-testid="accordion-response">
                  Response Body
                </AccordionTrigger>
                <AccordionContent>
                  <pre className="text-xs bg-muted p-3 rounded overflow-auto max-h-40 whitespace-pre-wrap break-all font-mono">
                    {errorInfo.responseBody}
                  </pre>
                </AccordionContent>
              </AccordionItem>
            )}

            {errorInfo.stackTrace && (
              <AccordionItem value="stack">
                <AccordionTrigger className="text-sm" data-testid="accordion-stack-trace">
                  Stack Trace
                </AccordionTrigger>
                <AccordionContent>
                  <pre className="text-xs bg-muted p-3 rounded overflow-auto max-h-60 whitespace-pre-wrap break-all font-mono text-destructive">
                    {errorInfo.stackTrace}
                  </pre>
                </AccordionContent>
              </AccordionItem>
            )}
          </Accordion>
        )}

        {action && (
          <div className="flex justify-center">
            <Button onClick={action.onClick} variant="outline" data-testid="button-error-action">
              {action.label}
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
