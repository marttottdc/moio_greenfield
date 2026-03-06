import { useMemo } from "react";
import { cn } from "@/lib/utils";

interface SearchHighlightProps {
  text: string;
  query: string;
  className?: string;
  highlightClassName?: string;
}

/**
 * Highlights occurrences of the search query within the text
 */
export function SearchHighlight({
  text,
  query,
  className,
  highlightClassName = "bg-cyan-500/30 text-cyan-200 rounded px-0.5",
}: SearchHighlightProps) {
  const parts = useMemo(() => {
    if (!query || !text) {
      return [{ text, highlight: false }];
    }

    const escapedQuery = query.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const regex = new RegExp(`(${escapedQuery})`, "gi");
    const splitParts = text.split(regex);

    return splitParts.map((part) => ({
      text: part,
      highlight: part.toLowerCase() === query.toLowerCase(),
    }));
  }, [text, query]);

  return (
    <span className={className}>
      {parts.map((part, index) =>
        part.highlight ? (
          <mark key={index} className={cn("bg-transparent", highlightClassName)}>
            {part.text}
          </mark>
        ) : (
          <span key={index}>{part.text}</span>
        )
      )}
    </span>
  );
}

export default SearchHighlight;
