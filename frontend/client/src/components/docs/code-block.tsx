import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { DocsEndpointExample } from "@/hooks/use-docs";
import { Copy, Check } from "lucide-react";

interface CodeBlockProps {
  title?: string;
  examples?: DocsEndpointExample[];
  language?: string;
  code?: string;
}

export function CodeBlock({ title, examples, language, code }: CodeBlockProps) {
  const tabs = useMemo(() => {
    if (examples && examples.length > 0) {
      return examples.map((ex) => ({
        language: ex.language,
        code: ex.code,
        title: (ex as any).title,
      }));
    }
    if (code) {
      return [{ language: language || "text", code }];
    }
    return [];
  }, [examples, code, language]);

  const [active, setActive] = useState(() => tabs[0]?.language ?? "");
  const [copiedLang, setCopiedLang] = useState<string | null>(null);

  const activeExample = tabs.find((t) => t.language === active) ?? tabs[0];

  const handleCopy = async () => {
    if (!activeExample?.code) return;
    await navigator.clipboard.writeText(activeExample.code);
    setCopiedLang(activeExample.language);
    setTimeout(() => setCopiedLang(null), 1200);
  };

  if (tabs.length === 0) {
    return null;
  }

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/70">
      <div className="flex items-center justify-between border-b border-slate-800 px-3 py-2">
        <div className="flex items-center gap-2">
          {title && <span className="text-sm text-slate-200">{title}</span>}
          <div className="flex items-center gap-1">
            {tabs.map((tab) => (
              <Badge
                key={tab.language}
                variant={tab.language === active ? "default" : "outline"}
                className={cn(
                  "cursor-pointer capitalize",
                  tab.language === active
                    ? "bg-cyan-500 text-slate-900 hover:bg-cyan-400"
                    : "border-slate-700 text-slate-300 hover:border-slate-500"
                )}
                onClick={() => setActive(tab.language)}
              >
                {tab.language}
              </Badge>
            ))}
          </div>
        </div>
        <Button
          type="button"
          size="icon"
          variant="ghost"
          className="text-slate-300 hover:text-slate-50"
          onClick={handleCopy}
        >
          {copiedLang === activeExample?.language ? (
            <Check className="h-4 w-4" />
          ) : (
            <Copy className="h-4 w-4" />
          )}
        </Button>
      </div>
      <pre className="overflow-x-auto p-4 text-sm text-slate-100 font-mono leading-6">
        {activeExample?.code || "No code available"}
      </pre>
    </div>
  );
}

export default CodeBlock;
