import { PropsWithChildren, useState, useCallback, useEffect } from "react";
import { Link, useLocation } from "wouter";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { DocsSidebar } from "./docs-sidebar";
import { DocsSearch } from "./docs-search";
import { DocsToc } from "./docs-toc";
import { DocsBreadcrumb, type BreadcrumbItem } from "./docs-breadcrumb";
import { DocsProvider, useDocs } from "@/contexts/DocsContext";
import { Menu, X, ArrowLeft } from "lucide-react";
import { cn } from "@/lib/utils";
import moioLogo from "@assets/Moio_New_Logo_Transparent_1764783655330.png";
import type { TocItem } from "./markdown-renderer";

interface DocsLayoutContentProps extends PropsWithChildren {
  breadcrumbs?: BreadcrumbItem[];
  showToc?: boolean;
  tocItems?: TocItem[];
  showBackButton?: boolean;
  backHref?: string;
  backLabel?: string;
}

function DocsLayoutContent({
  children,
  breadcrumbs = [],
  showToc = false,
  tocItems = [],
  showBackButton = false,
  backHref = "/docs",
  backLabel = "Back",
}: DocsLayoutContentProps) {
  const [location] = useLocation();
  const { sidebarOpen, setSidebarOpen } = useDocs();
  const [scrolled, setScrolled] = useState(false);

  // Close sidebar on route change
  useEffect(() => {
    setSidebarOpen(false);
  }, [location, setSidebarOpen]);

  // Track scroll for sticky header effect
  const handleScroll = useCallback((e: React.UIEvent<HTMLDivElement>) => {
    const target = e.target as HTMLDivElement;
    setScrolled(target.scrollTop > 10);
  }, []);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-50">
      <div className="flex h-screen">
        {/* Desktop Sidebar */}
        <aside className="hidden lg:block w-72 flex-shrink-0 border-r border-slate-800 bg-slate-900/80 backdrop-blur">
          <DocsSidebar />
        </aside>

        {/* Mobile Sidebar Sheet */}
        <Sheet open={sidebarOpen} onOpenChange={setSidebarOpen}>
          <SheetContent side="left" className="w-72 p-0 bg-slate-900 border-slate-800">
            <DocsSidebar />
          </SheetContent>
        </Sheet>

        {/* Main Content */}
        <div className="flex-1 flex flex-col min-w-0">
          {/* Sticky Header */}
          <header
            className={cn(
              "sticky top-0 z-40 border-b border-slate-800 bg-slate-900/95 backdrop-blur supports-[backdrop-filter]:bg-slate-900/80 transition-shadow",
              scrolled && "shadow-lg shadow-slate-950/50"
            )}
          >
            <div className="px-4 lg:px-6 py-3">
              <div className="flex items-center justify-between gap-4">
                <div className="flex items-center gap-3">
                  {/* Mobile menu button */}
                  <Button
                    variant="ghost"
                    size="icon"
                    className="lg:hidden text-slate-400 hover:text-slate-100"
                    onClick={() => setSidebarOpen(true)}
                    aria-label="Open navigation"
                  >
                    <Menu className="h-5 w-5" />
                  </Button>

                  <Link href="/docs">
                    <a className="flex items-center gap-3 hover:opacity-80 transition-opacity">
                      <img
                        src={moioLogo}
                        alt="Moio"
                        className="h-8 w-8 lg:h-10 lg:w-10 object-contain"
                      />
                      <div className="hidden sm:block">
                        <p className="text-[10px] uppercase text-slate-400 tracking-[0.2em]">Documentation</p>
                        <h1 className="text-lg font-semibold text-slate-50">Moio Platform</h1>
                      </div>
                    </a>
                  </Link>
                </div>
                
                <div className="flex-1 max-w-xl hidden md:block">
                  <DocsSearch />
                </div>

                {/* Mobile search trigger - can be expanded later */}
                <Button
                  variant="ghost"
                  size="icon"
                  className="md:hidden text-slate-400 hover:text-slate-100"
                  onClick={() => {
                    // Focus on search - could be enhanced with a modal
                    const searchInput = document.querySelector<HTMLInputElement>('[data-docs-search]');
                    searchInput?.focus();
                  }}
                  aria-label="Search"
                >
                  <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                  </svg>
                </Button>
              </div>

              {/* Mobile search bar */}
              <div className="md:hidden mt-3">
                <DocsSearch />
              </div>
            </div>

            {/* Breadcrumb bar */}
            {breadcrumbs.length > 0 && (
              <div className="px-4 lg:px-6 py-2 border-t border-slate-800/50 bg-slate-900/50">
                <div className="flex items-center gap-3">
                  {showBackButton && (
                    <Link href={backHref}>
                      <a className="flex items-center gap-1 text-sm text-slate-400 hover:text-cyan-400 transition-colors">
                        <ArrowLeft className="h-4 w-4" />
                        <span className="hidden sm:inline">{backLabel}</span>
                      </a>
                    </Link>
                  )}
                  <DocsBreadcrumb items={breadcrumbs} />
                </div>
              </div>
            )}
          </header>

          {/* Content Area with optional TOC */}
          <div className="flex-1 flex overflow-hidden">
            {/* Main content */}
            <ScrollArea className="flex-1" onScroll={handleScroll as any}>
              <div className="p-4 lg:p-8 space-y-6 max-w-4xl">
                {children}
              </div>
            </ScrollArea>

            {/* Right sidebar TOC - only on large screens */}
            {showToc && tocItems.length > 0 && (
              <aside className="hidden xl:block w-64 flex-shrink-0 border-l border-slate-800 bg-slate-900/30">
                <div className="sticky top-0 p-4 max-h-screen overflow-auto">
                  <DocsToc items={tocItems} />
                </div>
              </aside>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// Wrapper with provider
export interface DocsLayoutProps extends DocsLayoutContentProps {}

export function DocsLayout(props: DocsLayoutProps) {
  return (
    <DocsProvider>
      <DocsLayoutContent {...props} />
    </DocsProvider>
  );
}

export default DocsLayout;
