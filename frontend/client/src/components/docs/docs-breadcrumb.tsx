import { Link } from "wouter";
import { ChevronRight, Home } from "lucide-react";
import { cn } from "@/lib/utils";

export interface BreadcrumbItem {
  label: string;
  href?: string;
}

interface DocsBreadcrumbProps {
  items: BreadcrumbItem[];
  className?: string;
}

export function DocsBreadcrumb({ items, className }: DocsBreadcrumbProps) {
  const allItems: BreadcrumbItem[] = [
    { label: "Docs", href: "/docs" },
    ...items,
  ];

  return (
    <nav
      aria-label="Breadcrumb"
      className={cn("flex items-center text-sm text-slate-400", className)}
    >
      <ol className="flex items-center flex-wrap gap-1">
        {allItems.map((item, index) => {
          const isLast = index === allItems.length - 1;
          const isFirst = index === 0;

          return (
            <li key={`${item.label}-${index}`} className="flex items-center">
              {index > 0 && (
                <ChevronRight className="h-3.5 w-3.5 mx-1 text-slate-600 flex-shrink-0" />
              )}
              {item.href && !isLast ? (
                <Link href={item.href}>
                  <a className="flex items-center gap-1 hover:text-cyan-400 transition-colors">
                    {isFirst && <Home className="h-3.5 w-3.5" />}
                    <span className={cn(isFirst && "sr-only md:not-sr-only")}>
                      {item.label}
                    </span>
                  </a>
                </Link>
              ) : (
                <span
                  className={cn(
                    "truncate max-w-[200px]",
                    isLast ? "text-slate-200 font-medium" : "text-slate-400"
                  )}
                  title={item.label}
                >
                  {item.label}
                </span>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

export default DocsBreadcrumb;
