import { ReactNode } from "react";
import { Link, useLocation } from "wouter";
import { cn } from "@/lib/utils";
import { ScrollArea } from "@/components/ui/scroll-area";

type NavItem = { label: string; href: string; matchPrefix?: string };

const sections: Array<{ title: string; items: NavItem[] }> = [
  {
    title: "Datasets",
    items: [{ label: "Datasets", href: "/datalab/datasets", matchPrefix: "/datalab/datasets" }],
  },
  {
    title: "Sources",
    items: [
      { label: "Files", href: "/datalab/files", matchPrefix: "/datalab/files" },
      { label: "CRM", href: "/datalab/datasources", matchPrefix: "/datalab/datasources" },
    ],
  },
  {
    title: "Processes",
    items: [
      {
        label: "Import Processes",
        href: "/datalab/processes/imports",
        matchPrefix: "/datalab/processes/imports",
      },
      { label: "Imports", href: "/datalab/imports", matchPrefix: "/datalab/imports" },
      { label: "Scripts", href: "/datalab/scripts", matchPrefix: "/datalab/scripts" },
      { label: "Pipelines", href: "/datalab/pipelines", matchPrefix: "/datalab/pipelines" },
    ],
  },
  {
    title: "Visualize",
    items: [
      { label: "Panels", href: "/datalab/panels", matchPrefix: "/datalab/panels" },
      // Widgets are managed through panels for now; keep link for future.
      { label: "Widgets", href: "/datalab/panels", matchPrefix: "/datalab/panels" },
    ],
  },
  {
    title: "Runs / History",
    items: [{ label: "Runs", href: "/datalab/runs", matchPrefix: "/datalab/runs" }],
  },
];

export function DataLabWorkspace({ children }: { children: ReactNode }) {
  const [location] = useLocation();

  const isActive = (item: NavItem) => {
    const prefix = item.matchPrefix ?? item.href;
    return location === item.href || location.startsWith(prefix + "/") || location.startsWith(prefix + "?");
  };

  return (
    <div className="h-full flex">
      <div className="w-64 border-r border-border bg-background flex flex-col shrink-0">
        <div className="p-3 border-b border-border">
          <h2 className="font-semibold text-sm">Data Lab</h2>
          <p className="text-xs text-muted-foreground mt-0.5">Datasets-first workspace</p>
        </div>

        <div className="p-2 space-y-4">
          {sections.map((section) => (
            <div key={section.title} className="space-y-1">
              <div className="px-3 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                {section.title}
              </div>
              {section.items.map((item) => {
                const active = isActive(item);
                return (
                  <Link key={item.href + item.label} href={item.href}>
                    <a
                      className={cn(
                        "w-full flex items-center gap-2 px-3 py-2 text-sm rounded-md transition-colors",
                        active ? "bg-accent text-accent-foreground" : "text-muted-foreground hover-elevate"
                      )}
                    >
                      {item.label}
                    </a>
                  </Link>
                );
              })}
            </div>
          ))}
        </div>
      </div>

      <div className="flex-1 flex flex-col bg-muted/20 overflow-hidden">
        <ScrollArea className="flex-1">
          <div className="pl-2 pr-4 py-4">{children}</div>
        </ScrollArea>
      </div>
    </div>
  );
}

