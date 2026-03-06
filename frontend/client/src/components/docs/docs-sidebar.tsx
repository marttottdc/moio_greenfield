import { useEffect, useMemo, useState, useCallback, useRef, KeyboardEvent } from "react";
import { Link, useLocation } from "wouter";
import { Loader2, ChevronRight, BookOpen, Network, FileText, Home } from "lucide-react";
import { useDocsNavigation, DocsNavigationNode } from "@/hooks/use-docs";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";

function NodeIcon({ type }: { type: DocsNavigationNode["type"] }) {
  if (type === "guide") return <FileText className="h-4 w-4" />;
  if (type === "guide-category") return <BookOpen className="h-4 w-4" />;
  return <Network className="h-4 w-4" />;
}

interface FlatNode {
  node: DocsNavigationNode;
  depth: number;
  parent?: string;
}

export function DocsSidebar() {
  const { data, isLoading } = useDocsNavigation();
  const [location, navigate] = useLocation();
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const [focusedIndex, setFocusedIndex] = useState<number>(-1);
  const navRef = useRef<HTMLDivElement>(null);

  const nodes = useMemo(() => data?.navigation ?? [], [data]);

  // Flatten visible nodes for keyboard navigation
  const flatNodes = useMemo(() => {
    const result: FlatNode[] = [];
    const walk = (items: DocsNavigationNode[], depth = 0, parent?: string) => {
      for (const node of items) {
        result.push({ node, depth, parent });
        const hasChildren = node.children && node.children.length > 0;
        const isOpen = hasChildren ? open[node.slug] ?? false : false;
        if (hasChildren && isOpen) {
          walk(node.children!, depth + 1, node.slug);
        }
      }
    };
    walk(nodes);
    return result;
  }, [nodes, open]);

  const toggle = useCallback((slug: string) => {
    setOpen((prev) => ({ ...prev, [slug]: !prev[slug] }));
  }, []);

  const isNodeActive = useCallback((node: DocsNavigationNode): boolean => {
    if (node.type === "guide") {
      return location.startsWith(`/docs/guides/${node.slug}`);
    }
    if (node.type === "api-tag") {
      try {
        const url = new URL(window.location.href);
        const tagParam = url.searchParams.get("tag");
        return url.pathname === "/docs" && (tagParam === node.title || tagParam === node.slug);
      } catch {
        return false;
      }
    }
    return false;
  }, [location]);

  // Auto-expand to show active item
  useEffect(() => {
    const nextOpen: Record<string, boolean> = {};
    const walk = (items: DocsNavigationNode[], parentOpen = false): boolean => {
      let anyActive = parentOpen;
      for (const n of items) {
        const childActive = n.children ? walk(n.children) : false;
        const active = isNodeActive(n) || childActive;
        if (active) {
          nextOpen[n.slug] = true;
          anyActive = true;
        }
      }
      return anyActive;
    };
    walk(nodes);
    setOpen((prev) => ({ ...prev, ...nextOpen }));
  }, [location, nodes, isNodeActive]);

  // Keyboard navigation handler
  const handleKeyDown = useCallback((e: KeyboardEvent<HTMLDivElement>) => {
    const { key } = e;
    
    if (key === "ArrowDown") {
      e.preventDefault();
      setFocusedIndex((prev) => Math.min(prev + 1, flatNodes.length - 1));
    } else if (key === "ArrowUp") {
      e.preventDefault();
      setFocusedIndex((prev) => Math.max(prev - 1, 0));
    } else if (key === "ArrowRight") {
      e.preventDefault();
      const focused = flatNodes[focusedIndex];
      if (focused?.node.children?.length && !open[focused.node.slug]) {
        toggle(focused.node.slug);
      }
    } else if (key === "ArrowLeft") {
      e.preventDefault();
      const focused = flatNodes[focusedIndex];
      if (focused?.node.children?.length && open[focused.node.slug]) {
        toggle(focused.node.slug);
      } else if (focused?.parent) {
        // Move focus to parent
        const parentIndex = flatNodes.findIndex((f) => f.node.slug === focused.parent);
        if (parentIndex !== -1) {
          setFocusedIndex(parentIndex);
        }
      }
    } else if (key === "Enter" || key === " ") {
      e.preventDefault();
      const focused = flatNodes[focusedIndex];
      if (!focused) return;
      
      if (focused.node.type === "guide") {
        navigate(`/docs/guides/${focused.node.slug}`);
      } else if (focused.node.type === "api-tag") {
        navigate(`/docs?tag=${encodeURIComponent(focused.node.title)}`);
        setTimeout(() => window.dispatchEvent(new Event("docs:tag-change")), 0);
      } else if (focused.node.children?.length) {
        toggle(focused.node.slug);
      }
    } else if (key === "Home") {
      e.preventDefault();
      setFocusedIndex(0);
    } else if (key === "End") {
      e.preventDefault();
      setFocusedIndex(flatNodes.length - 1);
    }
  }, [flatNodes, focusedIndex, open, toggle, navigate]);

  // Scroll focused item into view
  useEffect(() => {
    if (focusedIndex >= 0) {
      const focusedEl = navRef.current?.querySelector(`[data-nav-index="${focusedIndex}"]`);
      focusedEl?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  }, [focusedIndex]);

  const renderNode = (node: DocsNavigationNode, depth = 0, index: number) => {
    const hasChildren = node.children && node.children.length > 0;
    const isOpen = hasChildren ? open[node.slug] ?? false : false;
    const isActiveGuide = node.type === "guide" && location.startsWith(`/docs/guides/${node.slug}`);
    const isActiveTag =
      node.type === "api-tag" &&
      (() => {
        try {
          const url = new URL(window.location.href);
          return url.pathname === "/docs" && url.searchParams.get("tag") === node.slug;
        } catch {
          return false;
        }
      })();
    const isFocused = focusedIndex === index;

    const baseClasses =
      "flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors outline-none";
    const paddingStyle = { paddingLeft: `${Math.min(depth, 4) * 12}px` };

    const linkTarget = node.type === "guide" ? `/docs/guides/${node.slug}` : undefined;

    return (
      <div key={`${node.type}-${node.slug}`} className="space-y-0.5">
        <div className="flex items-center group" data-nav-index={index}>
          {hasChildren ? (
            <button
              onClick={() => toggle(node.slug)}
              className="p-1 text-slate-400 hover:text-slate-100 focus:outline-none"
              aria-label={`${isOpen ? "Collapse" : "Expand"} ${node.title}`}
              tabIndex={-1}
            >
              <ChevronRight
                className={cn("h-4 w-4 transition-transform duration-200", isOpen && "rotate-90")}
              />
            </button>
          ) : (
            <div className="w-6" />
          )}
          {node.type === "api-tag" ? (
            <button
              onClick={() => {
                navigate(`/docs?tag=${encodeURIComponent(node.title)}`);
                setTimeout(() => window.dispatchEvent(new Event("docs:tag-change")), 0);
              }}
              className={cn(
                baseClasses,
                isActiveTag && "bg-cyan-500/10 text-cyan-300 border-l-2 border-cyan-500",
                !isActiveTag && "hover:bg-slate-800/70 text-slate-300",
                isFocused && "ring-1 ring-cyan-500/50 bg-slate-800/50"
              )}
              style={paddingStyle}
              tabIndex={-1}
            >
              <NodeIcon type={node.type} />
              <span className="truncate">{node.title}</span>
            </button>
          ) : linkTarget ? (
            <Link href={linkTarget}>
              <a
                className={cn(
                  baseClasses,
                  isActiveGuide && "bg-cyan-500/10 text-cyan-300 border-l-2 border-cyan-500",
                  !isActiveGuide && "hover:bg-slate-800/70 text-slate-300",
                  isFocused && "ring-1 ring-cyan-500/50 bg-slate-800/50"
                )}
                style={paddingStyle}
                tabIndex={-1}
              >
                <NodeIcon type={node.type} />
                <span className="truncate">{node.title}</span>
              </a>
            </Link>
          ) : (
            <div 
              className={cn(
                baseClasses, 
                "text-slate-400 font-medium",
                isFocused && "ring-1 ring-cyan-500/50 bg-slate-800/50"
              )} 
              style={paddingStyle}
            >
              <NodeIcon type={node.type} />
              <span className="truncate">{node.title}</span>
            </div>
          )}
        </div>
        {hasChildren && isOpen && (
          <div className="ml-2 border-l border-slate-800/50">
            {/* Children are rendered from flatNodes in the main loop */}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="px-4 py-3 border-b border-slate-800">
        <Link href="/docs">
          <a className="flex items-center gap-2 text-slate-100 hover:text-cyan-400 transition-colors">
            <Home className="h-4 w-4" />
            <div>
              <p className="text-xs uppercase text-slate-400 tracking-[0.2em]">Docs</p>
              <p className="text-sm font-semibold">Navigation</p>
            </div>
          </a>
        </Link>
      </div>

      {/* Keyboard hint */}
      <div className="px-4 py-2 border-b border-slate-800/50 text-[10px] text-slate-500 hidden lg:block">
        Use <kbd className="px-1 py-0.5 bg-slate-800 rounded text-slate-400">↑↓</kbd> to navigate,{" "}
        <kbd className="px-1 py-0.5 bg-slate-800 rounded text-slate-400">←→</kbd> to expand/collapse
      </div>

      {/* Navigation tree */}
      <ScrollArea className="flex-1">
        <div 
          ref={navRef}
          className="p-3 space-y-1"
          role="tree"
          tabIndex={0}
          onKeyDown={handleKeyDown}
          onFocus={() => {
            if (focusedIndex === -1 && flatNodes.length > 0) {
              setFocusedIndex(0);
            }
          }}
          onBlur={() => setFocusedIndex(-1)}
        >
          {isLoading && (
            <div className="flex items-center gap-2 text-slate-400 text-sm p-2">
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading navigation...
            </div>
          )}
          {!isLoading && flatNodes.map((flat, index) => (
            <div key={`${flat.node.type}-${flat.node.slug}`} style={{ marginLeft: `${flat.depth * 12}px` }}>
              {renderNode(flat.node, flat.depth, index)}
            </div>
          ))}
          {!isLoading && nodes.length === 0 && (
            <p className="text-sm text-slate-500 p-2">No navigation available.</p>
          )}
        </div>
      </ScrollArea>
    </div>
  );
}

export default DocsSidebar;
