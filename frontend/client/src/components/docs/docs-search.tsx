import { FormEvent, useEffect, useRef, useState, useCallback } from "react";
import { useLocation } from "wouter";
import { Search, Command, X } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function DocsSearch() {
  const [location, setLocation] = useLocation();
  const [value, setValue] = useState("");
  const [isFocused, setIsFocused] = useState(false);
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    const url = new URL(window.location.href);
    const q = url.searchParams.get("q");
    if (location.startsWith("/docs/search") && q) {
      setValue(q);
    }
  }, [location]);

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        inputRef.current?.focus();
      }
      // Escape to clear and blur
      if (event.key === "Escape" && document.activeElement === inputRef.current) {
        inputRef.current?.blur();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  const onSubmit = useCallback((e: FormEvent) => {
    e.preventDefault();
    const query = value.trim();
    if (!query) return;
    setLocation(`/docs/search?q=${encodeURIComponent(query)}`);
    inputRef.current?.blur();
  }, [value, setLocation]);

  const handleClear = useCallback(() => {
    setValue("");
    inputRef.current?.focus();
  }, []);

  return (
    <form onSubmit={onSubmit} className="relative group">
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500 pointer-events-none" />
        <Input
          ref={inputRef}
          data-docs-search
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onFocus={() => setIsFocused(true)}
          onBlur={() => setIsFocused(false)}
          placeholder="Search docs..."
          className={cn(
            "bg-slate-900/80 border-slate-800 pl-9 pr-32 text-slate-100 placeholder:text-slate-500",
            "focus:ring-1 focus:ring-cyan-500/50 focus:border-cyan-500/50",
            "transition-all duration-200"
          )}
        />
        <div className="absolute right-2 top-1/2 -translate-y-1/2 flex items-center gap-1.5">
          {value && (
            <Button
              type="button"
              size="icon"
              variant="ghost"
              className="h-6 w-6 text-slate-500 hover:text-slate-300"
              onClick={handleClear}
            >
              <X className="h-3.5 w-3.5" />
            </Button>
          )}
          <kbd className="hidden sm:flex items-center gap-0.5 rounded border border-slate-700 bg-slate-800 px-1.5 py-0.5 text-[10px] text-slate-400">
            <Command className="h-2.5 w-2.5" />
            <span>K</span>
          </kbd>
          <Button 
            type="submit" 
            size="sm" 
            variant="secondary" 
            className="h-7 px-2.5 text-xs"
            disabled={!value.trim()}
          >
            Search
          </Button>
        </div>
      </div>
      
      {/* Focus indicator line */}
      <div 
        className={cn(
          "absolute bottom-0 left-0 right-0 h-0.5 bg-gradient-to-r from-cyan-500 to-purple-500 rounded-b",
          "transform transition-transform duration-200 origin-left",
          isFocused ? "scale-x-100" : "scale-x-0"
        )}
      />
    </form>
  );
}

export default DocsSearch;
