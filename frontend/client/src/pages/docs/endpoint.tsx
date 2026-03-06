import { useMemo } from "react";
import { Link, useRoute } from "wouter";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DocsLayout } from "@/components/docs/docs-layout";
import { CodeBlock } from "@/components/docs/code-block";
import { MarkdownRenderer } from "@/components/docs/markdown-renderer";
import { SchemaViewer } from "@/components/docs/schema-viewer";
import { useDocsEndpoint } from "@/hooks/use-docs";
import { ArrowLeft, AlertTriangle, Clock, Copy, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useState } from "react";

const methodColors: Record<string, string> = {
  get: "bg-emerald-500",
  post: "bg-blue-500",
  put: "bg-amber-500",
  patch: "bg-amber-600",
  delete: "bg-rose-500",
};

const statusDescriptions: Record<string, { label: string; color: string }> = {
  "200": { label: "Success", color: "text-emerald-400" },
  "201": { label: "Created", color: "text-emerald-400" },
  "204": { label: "No Content", color: "text-emerald-400" },
  "400": { label: "Bad Request", color: "text-amber-400" },
  "401": { label: "Unauthorized", color: "text-rose-400" },
  "403": { label: "Forbidden", color: "text-rose-400" },
  "404": { label: "Not Found", color: "text-amber-400" },
  "422": { label: "Validation Error", color: "text-amber-400" },
  "500": { label: "Server Error", color: "text-rose-400" },
};

export default function DocsEndpointPage() {
  const [, params] = useRoute<{ operationId: string }>("/docs/api/:operationId");
  const operationId = params?.operationId;
  const { data: endpoint, isLoading } = useDocsEndpoint(operationId);
  const [copied, setCopied] = useState(false);

  const method = endpoint?.spec?.method?.toLowerCase?.() ?? "get";
  const color = methodColors[method] ?? "bg-slate-500";

  const handleCopyPath = async () => {
    if (endpoint?.spec?.path) {
      await navigator.clipboard.writeText(endpoint.spec.path);
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    }
  };

  const breadcrumbs = useMemo(() => {
    const items = [{ label: "API Reference", href: "/docs" }];
    if (endpoint?.spec?.tags?.[0]) {
      items.push({ label: endpoint.spec.tags[0], href: `/docs?tag=${endpoint.spec.tags[0]}` });
    }
    if (endpoint?.spec?.summary) {
      items.push({ label: endpoint.spec.summary });
    }
    return items;
  }, [endpoint]);

  return (
    <DocsLayout
      breadcrumbs={breadcrumbs}
      showBackButton
      backHref="/docs"
      backLabel="All Endpoints"
    >
      {isLoading && (
        <div className="flex items-center gap-3 text-slate-400 py-8">
          <div className="h-5 w-5 border-2 border-slate-600 border-t-cyan-500 rounded-full animate-spin" />
          Loading endpoint...
        </div>
      )}

      {!isLoading && !endpoint && (
        <Card className="bg-slate-900/50 border-slate-800">
          <CardContent className="flex flex-col items-center justify-center py-12 text-center">
            <AlertTriangle className="h-12 w-12 text-amber-500 mb-4" />
            <h3 className="text-lg font-medium text-slate-300 mb-2">Endpoint not found</h3>
            <p className="text-sm text-slate-500 mb-4">
              The endpoint "{operationId}" could not be found.
            </p>
            <Link href="/docs">
              <a className="text-cyan-400 hover:text-cyan-300">← Back to documentation</a>
            </Link>
          </CardContent>
        </Card>
      )}

      {endpoint?.spec && (
        <div className="space-y-6">
          {/* Header */}
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-3">
              <Badge className={`${color} text-slate-900 uppercase font-bold px-3 py-1`}>
                {method}
              </Badge>
              <div className="flex items-center gap-2 flex-1 min-w-0">
                <code className="font-mono text-cyan-200 text-lg truncate">
                  {endpoint.spec.path}
                </code>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8 text-slate-400 hover:text-slate-100 flex-shrink-0"
                  onClick={handleCopyPath}
                >
                  {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                </Button>
              </div>
            </div>

            <h1 className="text-3xl font-semibold text-slate-50">{endpoint.spec.summary}</h1>

            {endpoint.spec.deprecated && (
              <div className="flex items-center gap-2 p-3 rounded-lg bg-amber-500/10 border border-amber-500/30">
                <AlertTriangle className="h-5 w-5 text-amber-400" />
                <span className="text-amber-300 text-sm">
                  This endpoint is deprecated and may be removed in a future version.
                </span>
              </div>
            )}

            {endpoint.spec.description && (
              <MarkdownRenderer content={endpoint.spec.description} />
            )}

            {endpoint.spec.tags && endpoint.spec.tags.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {endpoint.spec.tags.map((tag) => (
                  <Link key={tag} href={`/docs?tag=${encodeURIComponent(tag)}`}>
                    <a>
                      <Badge
                        variant="outline"
                        className="border-slate-700 text-slate-300 hover:border-cyan-500/50 hover:text-cyan-300 transition-colors"
                      >
                        {tag}
                      </Badge>
                    </a>
                  </Link>
                ))}
              </div>
            )}
          </div>

          {/* Request Section */}
          <Card className="bg-slate-900/70 border-slate-800">
            <CardHeader>
              <CardTitle className="text-slate-100 flex items-center gap-2">
                <span>Request</span>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {/* Path Parameters */}
              {endpoint.spec.parameters?.some((p: any) => p.in === "path") && (
                <div className="space-y-2">
                  <h4 className="text-sm font-semibold text-slate-200">Path Parameters</h4>
                  <div className="space-y-2">
                    {endpoint.spec.parameters
                      .filter((p: any) => p.in === "path")
                      .map((param: any, idx: number) => (
                        <div
                          key={`path-${param.name}-${idx}`}
                          className="rounded-lg border border-slate-800 bg-slate-900/60 p-3"
                        >
                          <div className="flex items-center gap-2 flex-wrap">
                            <code className="font-mono text-cyan-300">{param.name}</code>
                            <Badge variant="outline" className="border-slate-700 text-slate-400 text-xs">
                              {param.schema?.type || "string"}
                            </Badge>
                            <Badge className="bg-rose-500/20 text-rose-300 border-rose-500/40 text-xs">
                              required
                            </Badge>
                          </div>
                          {param.description && (
                            <p className="text-sm text-slate-400 mt-2">{param.description}</p>
                          )}
                        </div>
                      ))}
                  </div>
                </div>
              )}

              {/* Query Parameters */}
              {endpoint.spec.parameters?.some((p: any) => p.in === "query") && (
                <div className="space-y-2">
                  <h4 className="text-sm font-semibold text-slate-200">Query Parameters</h4>
                  <div className="space-y-2">
                    {endpoint.spec.parameters
                      .filter((p: any) => p.in === "query")
                      .map((param: any, idx: number) => (
                        <div
                          key={`query-${param.name}-${idx}`}
                          className="rounded-lg border border-slate-800 bg-slate-900/60 p-3"
                        >
                          <div className="flex items-center gap-2 flex-wrap">
                            <code className="font-mono text-cyan-300">{param.name}</code>
                            <Badge variant="outline" className="border-slate-700 text-slate-400 text-xs">
                              {param.schema?.type || "string"}
                            </Badge>
                            {param.required && (
                              <Badge className="bg-rose-500/20 text-rose-300 border-rose-500/40 text-xs">
                                required
                              </Badge>
                            )}
                          </div>
                          {param.description && (
                            <p className="text-sm text-slate-400 mt-2">{param.description}</p>
                          )}
                          {param.schema?.default !== undefined && (
                            <p className="text-xs text-slate-500 mt-1">
                              Default: <code className="text-slate-300">{JSON.stringify(param.schema.default)}</code>
                            </p>
                          )}
                        </div>
                      ))}
                  </div>
                </div>
              )}

              {/* Request Body */}
              {endpoint.spec.requestBody && (
                <div className="space-y-2">
                  <h4 className="text-sm font-semibold text-slate-200">Request Body</h4>
                  <SchemaViewer schema={endpoint.spec.requestBody} title="Body Schema" />
                </div>
              )}

              {/* No parameters */}
              {!endpoint.spec.parameters?.length && !endpoint.spec.requestBody && (
                <p className="text-sm text-slate-500 italic">No parameters required.</p>
              )}
            </CardContent>
          </Card>

          {/* Responses Section */}
          {endpoint.spec.responses && Object.keys(endpoint.spec.responses).length > 0 && (
            <Card className="bg-slate-900/70 border-slate-800">
              <CardHeader>
                <CardTitle className="text-slate-100">Responses</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {Object.entries(endpoint.spec.responses).map(([status, schema]) => {
                  const statusInfo = statusDescriptions[status] || {
                    label: "Response",
                    color: "text-slate-400",
                  };
                  return (
                    <div key={status} className="space-y-2">
                      <div className="flex items-center gap-2">
                        <Badge
                          variant="outline"
                          className={`border-slate-700 ${statusInfo.color} font-mono`}
                        >
                          {status}
                        </Badge>
                        <span className="text-slate-300 text-sm">{statusInfo.label}</span>
                      </div>
                      <SchemaViewer
                        schema={schema}
                        title={`${status} Response`}
                        defaultExpanded={status.startsWith("2")}
                      />
                    </div>
                  );
                })}
              </CardContent>
            </Card>
          )}

          {/* Code Examples */}
          {endpoint.examples && endpoint.examples.length > 0 && (
            <CodeBlock title="Code Examples" examples={endpoint.examples} />
          )}

          {/* Notes */}
          {endpoint.notes && endpoint.notes.length > 0 && (
            <Card className="bg-slate-900/70 border-slate-800">
              <CardHeader>
                <CardTitle className="text-slate-100">Notes</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {endpoint.notes.map((note) => (
                  <div key={note.id} className="space-y-2">
                    <h4 className="text-sm font-semibold text-cyan-300">{note.title}</h4>
                    <MarkdownRenderer content={note.content} />
                  </div>
                ))}
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </DocsLayout>
  );
}
