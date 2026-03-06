import { useEffect, useMemo, useState } from "react";
import { Link, useLocation } from "wouter";
import { DocsLayout } from "@/components/docs/docs-layout";
import { EndpointCard } from "@/components/docs/endpoint-card";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useDocsEndpoints, useDocsGuides } from "@/hooks/use-docs";
import {
  BookOpen,
  Network,
  ArrowRight,
  LayoutGrid,
  LayoutList,
  Calendar,
  Sparkles,
} from "lucide-react";
import { cn } from "@/lib/utils";

function formatRelativeTime(dateStr?: string): string | null {
  if (!dateStr) return null;
  try {
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

    if (diffDays === 0) return "Today";
    if (diffDays === 1) return "Yesterday";
    if (diffDays < 7) return `${diffDays}d ago`;
    if (diffDays < 30) return `${Math.floor(diffDays / 7)}w ago`;
    return `${Math.floor(diffDays / 30)}mo ago`;
  } catch {
    return null;
  }
}

export default function DocsHomePage() {
  const [location] = useLocation();
  const [tag, setTag] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<"list" | "grid">("list");

  useEffect(() => {
    const readTag = () => {
      try {
        const url = new URL(window.location.href);
        setTag(url.searchParams.get("tag"));
      } catch {
        setTag(null);
      }
    };
    readTag();
    window.addEventListener("popstate", readTag);
    window.addEventListener("docs:tag-change", readTag);
    return () => {
      window.removeEventListener("popstate", readTag);
      window.removeEventListener("docs:tag-change", readTag);
    };
  }, [location]);

  const { data: guidesData, isLoading: guidesLoading } = useDocsGuides();
  const { data: endpointsData, isLoading: endpointsLoading } = useDocsEndpoints(tag || undefined);

  const featuredGuides = useMemo(() => {
    const cats = guidesData?.categories ?? [];
    const all = cats.flatMap((c) =>
      (c.guides || []).map((g) => ({
        ...g,
        category_name: c.name,
        category_slug: c.slug,
      }))
    );
    return all.slice(0, 6);
  }, [guidesData]);

  const clearTagFilter = () => {
    window.history.pushState(null, "", "/docs");
    setTag(null);
    window.dispatchEvent(new Event("docs:tag-change"));
  };

  return (
    <DocsLayout>
      <div className="space-y-8">
        {/* Hero Section */}
        <Card className="bg-gradient-to-br from-slate-900 via-slate-900/80 to-slate-950 border-slate-800 overflow-hidden relative">
          <div className="absolute inset-0 bg-gradient-to-r from-cyan-500/5 via-transparent to-purple-500/5" />
          <CardHeader className="relative">
            <div className="flex items-center gap-2 mb-2">
              <Sparkles className="h-5 w-5 text-cyan-400" />
              <span className="text-xs uppercase tracking-wider text-cyan-400">Documentation</span>
            </div>
            <CardTitle className="text-2xl lg:text-3xl text-slate-50">
              Welcome to the Moio Documentation
            </CardTitle>
          </CardHeader>
          <CardContent className="text-slate-300 space-y-4 relative">
            <p className="text-base lg:text-lg leading-relaxed">
              Explore guides, API reference, and live code examples. Use the search bar to find
              endpoints, or browse the sidebar.
            </p>
            {tag && (
              <div className="flex items-center gap-2">
                <Badge
                  variant="secondary"
                  className="bg-cyan-500/20 text-cyan-200 border-cyan-500/40"
                >
                  Filtering by: {tag}
                </Badge>
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-slate-400 hover:text-slate-100 h-6 px-2"
                  onClick={clearTagFilter}
                >
                  Clear filter
                </Button>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Two Column Layout */}
        <div className="grid gap-6 lg:grid-cols-2">
          {/* Featured Guides */}
          <Card className="bg-slate-900/70 border-slate-800">
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle className="text-slate-100 flex items-center gap-2">
                <BookOpen className="h-5 w-5 text-cyan-400" />
                Featured Guides
              </CardTitle>
              <Link href="/docs/search?type=guide">
                <a className="text-xs text-cyan-400 hover:text-cyan-300 flex items-center gap-1">
                  View all
                  <ArrowRight className="h-3 w-3" />
                </a>
              </Link>
            </CardHeader>
            <CardContent className="space-y-2">
              {guidesLoading && (
                <div className="flex items-center gap-2 text-slate-400 text-sm py-4">
                  <div className="h-4 w-4 border-2 border-slate-600 border-t-cyan-500 rounded-full animate-spin" />
                  Loading guides...
                </div>
              )}
              {!guidesLoading && featuredGuides.length === 0 && (
                <p className="text-sm text-slate-500 py-4">No guides available yet.</p>
              )}
              {featuredGuides.map((guide) => (
                <Link key={guide.slug} href={`/docs/guides/${guide.slug}`}>
                  <a className="block p-3 rounded-lg hover:bg-slate-800/70 transition-colors group">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-semibold text-slate-100 group-hover:text-cyan-300 transition-colors">
                          {guide.title}
                        </p>
                        {guide.summary && (
                          <p className="text-sm text-slate-400 mt-1 line-clamp-2">
                            {guide.summary}
                          </p>
                        )}
                        <div className="flex items-center gap-3 mt-2">
                          {guide.category_name && (
                            <span className="text-[11px] text-slate-500 bg-slate-800 px-2 py-0.5 rounded">
                              {guide.category_name}
                            </span>
                          )}
                          {guide.updated_at && (
                            <span className="text-[11px] text-slate-600 flex items-center gap-1">
                              <Calendar className="h-3 w-3" />
                              {formatRelativeTime(guide.updated_at)}
                            </span>
                          )}
                        </div>
                      </div>
                      <ArrowRight className="h-4 w-4 text-slate-600 group-hover:text-cyan-400 transition-colors flex-shrink-0 mt-1" />
                    </div>
                  </a>
                </Link>
              ))}
            </CardContent>
          </Card>

          {/* API Reference */}
          <Card className="bg-slate-900/70 border-slate-800">
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle className="text-slate-100 flex items-center gap-2">
                <Network className="h-5 w-5 text-cyan-400" />
                API Reference
                {tag && (
                  <Badge variant="outline" className="border-slate-700 text-slate-400 text-xs ml-2">
                    {tag}
                  </Badge>
                )}
              </CardTitle>
              <div className="flex items-center gap-2">
                {/* View mode toggle */}
                <div className="flex items-center border border-slate-700 rounded-md overflow-hidden">
                  <Button
                    variant="ghost"
                    size="sm"
                    className={cn(
                      "h-7 px-2 rounded-none",
                      viewMode === "list"
                        ? "bg-slate-800 text-slate-100"
                        : "text-slate-400 hover:text-slate-100"
                    )}
                    onClick={() => setViewMode("list")}
                  >
                    <LayoutList className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    className={cn(
                      "h-7 px-2 rounded-none",
                      viewMode === "grid"
                        ? "bg-slate-800 text-slate-100"
                        : "text-slate-400 hover:text-slate-100"
                    )}
                    onClick={() => setViewMode("grid")}
                  >
                    <LayoutGrid className="h-4 w-4" />
                  </Button>
                </div>
                <Link href="/docs/search">
                  <a className="text-xs text-cyan-400 hover:text-cyan-300 flex items-center gap-1">
                    View all
                    <ArrowRight className="h-3 w-3" />
                  </a>
                </Link>
              </div>
            </CardHeader>
            <CardContent>
              {endpointsLoading && (
                <div className="flex items-center gap-2 text-slate-400 text-sm py-4">
                  <div className="h-4 w-4 border-2 border-slate-600 border-t-cyan-500 rounded-full animate-spin" />
                  Loading endpoints...
                </div>
              )}
              {!endpointsLoading && (endpointsData?.endpoints?.length ?? 0) === 0 && (
                <p className="text-sm text-slate-500 py-4">No endpoints found.</p>
              )}
              <div
                className={cn(
                  viewMode === "grid"
                    ? "grid grid-cols-1 sm:grid-cols-2 gap-3"
                    : "space-y-3"
                )}
              >
                {endpointsData?.endpoints?.slice(0, viewMode === "grid" ? 8 : 6).map((endpoint) => (
                  <EndpointCard key={endpoint.operation_id} endpoint={endpoint} compact={viewMode === "grid"} />
                ))}
              </div>
              {endpointsData && endpointsData.endpoints.length > (viewMode === "grid" ? 8 : 6) && (
                <div className="mt-4 pt-4 border-t border-slate-800">
                  <Link href="/docs/search">
                    <a className="text-sm text-cyan-300 hover:text-cyan-200 flex items-center gap-1">
                      View all {endpointsData.endpoints.length} endpoints
                      <ArrowRight className="h-4 w-4" />
                    </a>
                  </Link>
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Quick Links */}
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Link href="/docs/guides/getting-started">
            <a className="group p-4 rounded-lg border border-slate-800 bg-slate-900/50 hover:border-cyan-500/50 hover:bg-slate-900 transition-all">
              <h3 className="font-medium text-slate-100 group-hover:text-cyan-300 transition-colors">
                Getting Started
              </h3>
              <p className="text-sm text-slate-400 mt-1">
                Learn the basics and set up your first integration.
              </p>
            </a>
          </Link>
          <Link href="/docs/guides/authentication">
            <a className="group p-4 rounded-lg border border-slate-800 bg-slate-900/50 hover:border-cyan-500/50 hover:bg-slate-900 transition-all">
              <h3 className="font-medium text-slate-100 group-hover:text-cyan-300 transition-colors">
                Authentication
              </h3>
              <p className="text-sm text-slate-400 mt-1">
                Understand how to authenticate API requests.
              </p>
            </a>
          </Link>
          <Link href="/docs/search?q=examples">
            <a className="group p-4 rounded-lg border border-slate-800 bg-slate-900/50 hover:border-cyan-500/50 hover:bg-slate-900 transition-all">
              <h3 className="font-medium text-slate-100 group-hover:text-cyan-300 transition-colors">
                Examples
              </h3>
              <p className="text-sm text-slate-400 mt-1">
                Browse code examples and use cases.
              </p>
            </a>
          </Link>
        </div>
      </div>
    </DocsLayout>
  );
}
