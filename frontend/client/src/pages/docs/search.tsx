import { useEffect, useState, useMemo } from "react";
import { Link, useLocation } from "wouter";
import { DocsLayout } from "@/components/docs/docs-layout";
import { SearchHighlight } from "@/components/docs/search-highlight";
import { useDocsSearch } from "@/hooks/use-docs";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { FileText, Network, SearchX, ArrowRight } from "lucide-react";

const methodColors: Record<string, string> = {
  get: "bg-emerald-500",
  post: "bg-blue-500",
  put: "bg-amber-500",
  patch: "bg-amber-600",
  delete: "bg-rose-500",
};

export default function DocsSearchPage() {
  const [location] = useLocation();
  const [query, setQuery] = useState("");

  useEffect(() => {
    const url = new URL(window.location.href);
    setQuery(url.searchParams.get("q") ?? "");
  }, [location]);

  const { data, isLoading } = useDocsSearch(query);

  const results = useMemo(() => {
    const items: Array<{
      type: "guide" | "endpoint";
      title: string;
      summary?: string;
      href: string;
      method?: string;
      category?: string;
    }> = [];
    data?.guides?.forEach((g) => {
      items.push({
        type: "guide",
        title: g.title,
        summary: g.summary,
        href: `/docs/guides/${g.slug}`,
        category: g.category_name,
      });
    });
    data?.endpoints?.forEach((e) => {
      items.push({
        type: "endpoint",
        title: e.path,
        summary: e.summary,
        href: `/docs/api/${e.operation_id}`,
        method: e.method,
      });
    });
    return items;
  }, [data]);

  const guidesCount = data?.guides?.length ?? 0;
  const endpointsCount = data?.endpoints?.length ?? 0;

  return (
    <DocsLayout
      breadcrumbs={[
        { label: "Search", href: "/docs/search" },
        ...(query ? [{ label: query }] : []),
      ]}
    >
      <div className="space-y-6">
        {/* Header */}
        <div className="space-y-2">
          <h1 className="text-2xl font-semibold text-slate-50">
            {query ? (
              <>
                Search results for "<span className="text-cyan-400">{query}</span>"
              </>
            ) : (
              "Search Documentation"
            )}
          </h1>
          {!isLoading && query && results.length > 0 && (
            <p className="text-sm text-slate-400">
              Found {results.length} result{results.length !== 1 ? "s" : ""}{" "}
              ({guidesCount} guide{guidesCount !== 1 ? "s" : ""}, {endpointsCount} endpoint
              {endpointsCount !== 1 ? "s" : ""})
            </p>
          )}
        </div>

        {/* Loading state */}
        {isLoading && (
          <div className="flex items-center gap-3 text-slate-400 py-8">
            <div className="h-5 w-5 border-2 border-slate-600 border-t-cyan-500 rounded-full animate-spin" />
            Searching documentation...
          </div>
        )}

        {/* Empty state */}
        {!isLoading && query && results.length === 0 && (
          <Card className="bg-slate-900/50 border-slate-800">
            <CardContent className="flex flex-col items-center justify-center py-12 text-center">
              <SearchX className="h-12 w-12 text-slate-600 mb-4" />
              <h3 className="text-lg font-medium text-slate-300 mb-2">No results found</h3>
              <p className="text-sm text-slate-500 max-w-md">
                We couldn't find any documentation matching "{query}". Try different keywords or
                browse the sidebar.
              </p>
            </CardContent>
          </Card>
        )}

        {/* No query state */}
        {!isLoading && !query && (
          <Card className="bg-slate-900/50 border-slate-800">
            <CardContent className="flex flex-col items-center justify-center py-12 text-center">
              <p className="text-sm text-slate-400">
                Enter a search term to find guides, endpoints, and more.
              </p>
            </CardContent>
          </Card>
        )}

        {/* Results */}
        {!isLoading && results.length > 0 && (
          <div className="space-y-3">
            {results.map((item, idx) => (
              <Link key={`${item.type}-${idx}`} href={item.href}>
                <a className="block">
                  <Card className="bg-slate-900/70 border-slate-800 hover:border-cyan-500/50 hover:bg-slate-900 transition-all group">
                    <CardHeader className="pb-2">
                      <CardTitle className="flex items-center gap-2 text-slate-100">
                        {item.type === "guide" ? (
                          <>
                            <FileText className="h-4 w-4 text-cyan-400" />
                            <Badge
                              variant="outline"
                              className="border-cyan-500/40 text-cyan-300 text-xs"
                            >
                              Guide
                            </Badge>
                          </>
                        ) : (
                          <>
                            <Network className="h-4 w-4 text-slate-400" />
                            <Badge
                              className={`${
                                methodColors[item.method?.toLowerCase() ?? "get"]
                              } text-slate-900 uppercase text-xs`}
                            >
                              {item.method}
                            </Badge>
                          </>
                        )}
                        <SearchHighlight
                          text={item.title}
                          query={query}
                          className="font-mono text-sm"
                        />
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="flex items-center justify-between text-sm">
                      <div className="flex-1 min-w-0">
                        {item.summary && (
                          <SearchHighlight
                            text={item.summary}
                            query={query}
                            className="text-slate-400 line-clamp-2"
                          />
                        )}
                        {item.category && (
                          <p className="text-xs text-slate-500 mt-1">{item.category}</p>
                        )}
                      </div>
                      <ArrowRight className="h-4 w-4 text-slate-600 group-hover:text-cyan-400 transition-colors ml-4 flex-shrink-0" />
                    </CardContent>
                  </Card>
                </a>
              </Link>
            ))}
          </div>
        )}
      </div>
    </DocsLayout>
  );
}
