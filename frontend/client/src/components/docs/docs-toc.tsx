import { useEffect, useState, useCallback, useRef } from "react";
import { cn } from "@/lib/utils";
import type { TocItem } from "./markdown-renderer";
import { List } from "lucide-react";

interface DocsTocProps {
  items: TocItem[];
  className?: string;
}

export function DocsToc({ items, className }: DocsTocProps) {
  const [activeId, setActiveId] = useState<string | null>(null);
  const observerRef = useRef<IntersectionObserver | null>(null);

  // Set up intersection observer to track which heading is in view
  useEffect(() => {
    if (items.length === 0) return;

    const handleIntersect = (entries: IntersectionObserverEntry[]) => {
      // Find the first visible heading
      const visibleEntries = entries.filter((entry) => entry.isIntersecting);
      if (visibleEntries.length > 0) {
        // Sort by their position in the document
        const sorted = visibleEntries.sort((a, b) => {
          return a.boundingClientRect.top - b.boundingClientRect.top;
        });
        setActiveId(sorted[0].target.id);
      }
    };

    observerRef.current = new IntersectionObserver(handleIntersect, {
      rootMargin: "-80px 0px -70% 0px",
      threshold: 0,
    });

    // Observe all headings
    items.forEach((item) => {
      const element = document.getElementById(item.id);
      if (element) {
        observerRef.current?.observe(element);
      }
    });

    return () => {
      observerRef.current?.disconnect();
    };
  }, [items]);

  const handleClick = useCallback((e: React.MouseEvent, id: string) => {
    e.preventDefault();
    const element = document.getElementById(id);
    if (element) {
      element.scrollIntoView({ behavior: "smooth", block: "start" });
      window.history.pushState(null, "", `#${id}`);
      setActiveId(id);
    }
  }, []);

  if (items.length === 0) {
    return null;
  }

  // Filter to only show h2 and h3 (skip h1 which is usually the title)
  const filteredItems = items.filter((item) => item.level >= 2 && item.level <= 3);

  if (filteredItems.length === 0) {
    return null;
  }

  return (
    <nav
      aria-label="Table of contents"
      className={cn("text-sm", className)}
    >
      <div className="flex items-center gap-2 mb-3 text-slate-400">
        <List className="h-4 w-4" />
        <span className="font-medium text-slate-300">On this page</span>
      </div>
      <ul className="space-y-1.5">
        {filteredItems.map((item) => (
          <li
            key={item.id}
            style={{
              paddingLeft: `${(item.level - 2) * 12}px`,
            }}
          >
            <a
              href={`#${item.id}`}
              onClick={(e) => handleClick(e, item.id)}
              className={cn(
                "block py-1 transition-colors border-l-2 pl-3 -ml-px",
                activeId === item.id
                  ? "border-cyan-500 text-cyan-400"
                  : "border-transparent text-slate-400 hover:text-slate-200 hover:border-slate-600"
              )}
            >
              <span className="line-clamp-2">{item.text}</span>
            </a>
          </li>
        ))}
      </ul>
    </nav>
  );
}

export default DocsToc;
