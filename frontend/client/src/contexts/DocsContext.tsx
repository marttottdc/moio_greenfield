import { createContext, useContext, useState, useCallback, ReactNode, useMemo } from "react";
import type { TocItem } from "@/components/docs/markdown-renderer";

interface DocsContextValue {
  // Tag filtering
  activeTag: string | null;
  setActiveTag: (tag: string | null) => void;
  
  // TOC state
  tocItems: TocItem[];
  setTocItems: (items: TocItem[]) => void;
  activeTocId: string | null;
  setActiveTocId: (id: string | null) => void;
  
  // Mobile sidebar
  sidebarOpen: boolean;
  setSidebarOpen: (open: boolean) => void;
  toggleSidebar: () => void;
  
  // View preferences
  endpointViewMode: "list" | "grid";
  setEndpointViewMode: (mode: "list" | "grid") => void;
  
  // Search
  searchQuery: string;
  setSearchQuery: (query: string) => void;
  
  // Breadcrumb
  breadcrumbs: BreadcrumbItem[];
  setBreadcrumbs: (items: BreadcrumbItem[]) => void;
}

export interface BreadcrumbItem {
  label: string;
  href?: string;
}

const DocsContext = createContext<DocsContextValue | null>(null);

export function DocsProvider({ children }: { children: ReactNode }) {
  const [activeTag, setActiveTag] = useState<string | null>(null);
  const [tocItems, setTocItems] = useState<TocItem[]>([]);
  const [activeTocId, setActiveTocId] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [endpointViewMode, setEndpointViewMode] = useState<"list" | "grid">("list");
  const [searchQuery, setSearchQuery] = useState("");
  const [breadcrumbs, setBreadcrumbs] = useState<BreadcrumbItem[]>([]);

  const toggleSidebar = useCallback(() => {
    setSidebarOpen((prev) => !prev);
  }, []);

  const value = useMemo(
    () => ({
      activeTag,
      setActiveTag,
      tocItems,
      setTocItems,
      activeTocId,
      setActiveTocId,
      sidebarOpen,
      setSidebarOpen,
      toggleSidebar,
      endpointViewMode,
      setEndpointViewMode,
      searchQuery,
      setSearchQuery,
      breadcrumbs,
      setBreadcrumbs,
    }),
    [
      activeTag,
      tocItems,
      activeTocId,
      sidebarOpen,
      toggleSidebar,
      endpointViewMode,
      searchQuery,
      breadcrumbs,
    ]
  );

  return <DocsContext.Provider value={value}>{children}</DocsContext.Provider>;
}

export function useDocs() {
  const context = useContext(DocsContext);
  if (!context) {
    throw new Error("useDocs must be used within a DocsProvider");
  }
  return context;
}

export default DocsContext;
