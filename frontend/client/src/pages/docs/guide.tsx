import { useState, useMemo, useCallback } from "react";
import { Link, useRoute } from "wouter";
import { ArrowLeft, ArrowRight, Calendar, Clock, AlertTriangle } from "lucide-react";
import { DocsLayout } from "@/components/docs/docs-layout";
import { MarkdownRenderer, type TocItem } from "@/components/docs/markdown-renderer";
import { useDocsGuide } from "@/hooks/use-docs";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";

function formatDate(dateStr?: string): string | null {
  if (!dateStr) return null;
  try {
    const date = new Date(dateStr);
    return date.toLocaleDateString("en-US", {
      year: "numeric",
      month: "long",
      day: "numeric",
    });
  } catch {
    return null;
  }
}

function formatRelativeTime(dateStr?: string): string | null {
  if (!dateStr) return null;
  try {
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

    if (diffDays === 0) return "Today";
    if (diffDays === 1) return "Yesterday";
    if (diffDays < 7) return `${diffDays} days ago`;
    if (diffDays < 30) return `${Math.floor(diffDays / 7)} weeks ago`;
    if (diffDays < 365) return `${Math.floor(diffDays / 30)} months ago`;
    return `${Math.floor(diffDays / 365)} years ago`;
  } catch {
    return null;
  }
}

export default function DocsGuidePage() {
  const [, params] = useRoute<{ slug: string }>("/docs/guides/:slug");
  const slug = params?.slug;
  const { data, isLoading } = useDocsGuide(slug);
  const [tocItems, setTocItems] = useState<TocItem[]>([]);

  const handleTocGenerated = useCallback((items: TocItem[]) => {
    setTocItems(items);
  }, []);

  const breadcrumbs = useMemo(() => {
    const items = [{ label: "Guides", href: "/docs" }];
    if (data?.guide?.category) {
      items.push({ label: data.guide.category });
    }
    if (data?.guide?.title) {
      items.push({ label: data.guide.title });
    }
    return items;
  }, [data]);

  const formattedDate = formatDate((data?.guide as any)?.updated_at);
  const relativeTime = formatRelativeTime((data?.guide as any)?.updated_at);

  return (
    <DocsLayout
      breadcrumbs={breadcrumbs}
      showToc={tocItems.length > 0}
      tocItems={tocItems}
      showBackButton
      backHref="/docs"
      backLabel="All Guides"
    >
      {isLoading && (
        <div className="flex items-center gap-3 text-slate-400 py-8">
          <div className="h-5 w-5 border-2 border-slate-600 border-t-cyan-500 rounded-full animate-spin" />
          Loading guide...
        </div>
      )}

      {!isLoading && !data && (
        <Card className="bg-slate-900/50 border-slate-800">
          <CardContent className="flex flex-col items-center justify-center py-12 text-center">
            <AlertTriangle className="h-12 w-12 text-amber-500 mb-4" />
            <h3 className="text-lg font-medium text-slate-300 mb-2">Guide not found</h3>
            <p className="text-sm text-slate-500 mb-4">
              The guide "{slug}" could not be found.
            </p>
            <Link href="/docs">
              <a className="text-cyan-400 hover:text-cyan-300">← Back to documentation</a>
            </Link>
          </CardContent>
        </Card>
      )}

      {data?.guide && (
        <article className="space-y-6">
          {/* Header */}
          <header className="space-y-4 pb-6 border-b border-slate-800">
            <div className="flex flex-wrap items-center gap-3">
              <Badge
                variant="secondary"
                className="bg-cyan-500/20 text-cyan-200 border-cyan-500/40"
              >
                Guide
              </Badge>
              {data.guide.category && (
                <Badge variant="outline" className="border-slate-700 text-slate-400">
                  {data.guide.category}
                </Badge>
              )}
            </div>

            <h1 className="text-3xl lg:text-4xl font-bold text-slate-50 leading-tight">
              {data.guide.title}
            </h1>

            {data.guide.summary && (
              <p className="text-lg text-slate-300 leading-relaxed">{data.guide.summary}</p>
            )}

            {/* Metadata */}
            {(formattedDate || relativeTime) && (
              <div className="flex items-center gap-4 text-sm text-slate-500">
                {formattedDate && (
                  <div className="flex items-center gap-1.5">
                    <Calendar className="h-4 w-4" />
                    <span>{formattedDate}</span>
                  </div>
                )}
                {relativeTime && (
                  <div className="flex items-center gap-1.5">
                    <Clock className="h-4 w-4" />
                    <span>Updated {relativeTime}</span>
                  </div>
                )}
              </div>
            )}
          </header>

          {/* Content */}
          <div className="min-h-[200px]">
            <MarkdownRenderer
              content={data.guide.content}
              content_html={data.guide.content_html}
              onTocGenerated={handleTocGenerated}
            />
          </div>

          {/* Navigation */}
          <nav className="flex items-center justify-between pt-8 border-t border-slate-800">
            {data.prev ? (
              <Link href={`/docs/guides/${data.prev.slug}`}>
                <a className="group flex items-center gap-3 p-4 rounded-lg hover:bg-slate-900/70 transition-colors max-w-[45%]">
                  <ArrowLeft className="h-5 w-5 text-slate-500 group-hover:text-cyan-400 transition-colors flex-shrink-0" />
                  <div className="min-w-0">
                    <p className="text-xs text-slate-500 uppercase tracking-wide">Previous</p>
                    <p className="text-cyan-300 group-hover:text-cyan-200 font-medium truncate">
                      {data.prev.title}
                    </p>
                  </div>
                </a>
              </Link>
            ) : (
              <div />
            )}
            {data.next ? (
              <Link href={`/docs/guides/${data.next.slug}`}>
                <a className="group flex items-center gap-3 p-4 rounded-lg hover:bg-slate-900/70 transition-colors max-w-[45%] text-right">
                  <div className="min-w-0">
                    <p className="text-xs text-slate-500 uppercase tracking-wide">Next</p>
                    <p className="text-cyan-300 group-hover:text-cyan-200 font-medium truncate">
                      {data.next.title}
                    </p>
                  </div>
                  <ArrowRight className="h-5 w-5 text-slate-500 group-hover:text-cyan-400 transition-colors flex-shrink-0" />
                </a>
              </Link>
            ) : (
              <div />
            )}
          </nav>
        </article>
      )}
    </DocsLayout>
  );
}
