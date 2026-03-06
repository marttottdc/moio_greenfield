import { Link } from "wouter";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ArrowRight } from "lucide-react";
import { cn } from "@/lib/utils";
import type { DocsEndpoint } from "@/hooks/use-docs";

const methodColors: Record<string, string> = {
  get: "bg-emerald-500",
  post: "bg-blue-500",
  put: "bg-amber-500",
  patch: "bg-amber-600",
  delete: "bg-rose-500",
};

interface EndpointCardProps {
  endpoint: DocsEndpoint;
  compact?: boolean;
}

export function EndpointCard({ endpoint, compact = false }: EndpointCardProps) {
  const method = endpoint.method?.toLowerCase?.() ?? "get";
  const color = methodColors[method] ?? "bg-slate-500";

  if (compact) {
    return (
      <Link href={`/docs/api/${endpoint.operation_id}`}>
        <a className="block group">
          <div className="p-3 rounded-lg border border-slate-800 bg-slate-900/50 hover:border-cyan-500/50 hover:bg-slate-900 transition-all">
            <div className="flex items-center gap-2 mb-1.5">
              <Badge className={`${color} text-slate-900 uppercase text-[10px] px-1.5 py-0`}>
                {method}
              </Badge>
              <code className="font-mono text-xs text-cyan-200 truncate flex-1">
                {endpoint.path}
              </code>
            </div>
            <p className="text-xs text-slate-400 line-clamp-1">
              {endpoint.summary || "No description"}
            </p>
          </div>
        </a>
      </Link>
    );
  }

  return (
    <Link href={`/docs/api/${endpoint.operation_id}`}>
      <a className="block group">
        <Card className="bg-slate-900/70 border-slate-800 hover:border-cyan-500/50 hover:bg-slate-900 transition-all">
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-slate-100">
              <Badge className={`${color} text-slate-900 uppercase font-bold`}>{method}</Badge>
              <code className="font-mono text-sm text-cyan-200 truncate flex-1">
                {endpoint.path}
              </code>
              <ArrowRight className="h-4 w-4 text-slate-600 group-hover:text-cyan-400 transition-colors flex-shrink-0" />
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-0">
            <p className="text-sm text-slate-400 line-clamp-2">
              {endpoint.summary || "No description"}
            </p>
            {endpoint.tags && endpoint.tags.length > 0 && (
              <div className="flex flex-wrap gap-1 mt-2">
                {endpoint.tags.slice(0, 3).map((tag) => (
                  <Badge
                    key={tag}
                    variant="outline"
                    className="border-slate-700 text-slate-500 text-[10px]"
                  >
                    {tag}
                  </Badge>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </a>
    </Link>
  );
}

export default EndpointCard;
