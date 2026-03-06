import { useMemo, useEffect, useCallback } from "react";
import { marked } from "marked";
import DOMPurify from "dompurify";

export interface TocItem {
  id: string;
  text: string;
  level: number;
}

interface MarkdownRendererProps {
  content?: string;
  content_html?: string;
  onTocGenerated?: (toc: TocItem[]) => void;
}

// Configure marked to add IDs to headings for deep linking
const renderer = new marked.Renderer();
const headings: TocItem[] = [];

renderer.heading = function (text: string, level: number) {
  const slug = text
    .toLowerCase()
    .replace(/[^\w\s-]/g, "")
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-")
    .trim();
  
  headings.push({ id: slug, text, level });
  
  return `<h${level} id="${slug}" class="group relative">
    <a href="#${slug}" class="absolute -left-6 opacity-0 group-hover:opacity-100 text-cyan-400 hover:text-cyan-300 transition-opacity" aria-label="Link to ${text}">
      #
    </a>
    ${text}
  </h${level}>`;
};

marked.setOptions({ renderer });

export function MarkdownRenderer({ content, content_html, onTocGenerated }: MarkdownRendererProps) {
  const { html, toc } = useMemo(() => {
    // Reset headings for each render
    headings.length = 0;
    
    let rawHtml: string;
    if (content_html) {
      rawHtml = content_html;
    } else if (content) {
      rawHtml = marked.parse(content) as string;
    } else {
      return { html: null, toc: [] };
    }
    
    // Sanitize HTML to prevent XSS attacks
    const sanitizedHtml = DOMPurify.sanitize(rawHtml, {
      ADD_ATTR: ["target", "rel", "id"],
      ADD_TAGS: ["iframe"],
      ALLOW_DATA_ATTR: false,
    });
    
    return { html: sanitizedHtml, toc: [...headings] };
  }, [content, content_html]);

  // Notify parent of TOC items
  useEffect(() => {
    if (onTocGenerated && toc.length > 0) {
      onTocGenerated(toc);
    }
  }, [toc, onTocGenerated]);

  // Handle anchor click for smooth scrolling
  const handleClick = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    const target = e.target as HTMLElement;
    const anchor = target.closest("a[href^='#']");
    if (anchor) {
      e.preventDefault();
      const id = anchor.getAttribute("href")?.slice(1);
      if (id) {
        const element = document.getElementById(id);
        if (element) {
          element.scrollIntoView({ behavior: "smooth", block: "start" });
          // Update URL without triggering navigation
          window.history.pushState(null, "", `#${id}`);
        }
      }
    }
  }, []);

  if (!html) {
    return <p className="text-slate-400">No content available.</p>;
  }

  return (
    <div
      onClick={handleClick}
      className="prose prose-invert max-w-none 
        prose-headings:scroll-mt-24 prose-headings:font-semibold
        prose-h1:text-2xl prose-h1:border-b prose-h1:border-slate-800 prose-h1:pb-2
        prose-h2:text-xl prose-h2:mt-8 prose-h2:mb-4
        prose-h3:text-lg prose-h3:mt-6
        prose-pre:bg-slate-900 prose-pre:border prose-pre:border-slate-800 prose-pre:rounded-lg
        prose-code:before:content-[''] prose-code:after:content-['']
        prose-code:bg-slate-800 prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded prose-code:text-cyan-300
        prose-a:text-cyan-400 prose-a:no-underline hover:prose-a:text-cyan-300 hover:prose-a:underline
        prose-strong:text-slate-100
        prose-blockquote:border-l-cyan-500 prose-blockquote:bg-slate-900/50 prose-blockquote:py-1 prose-blockquote:px-4
        prose-li:marker:text-cyan-500
        prose-table:border prose-table:border-slate-800
        prose-th:bg-slate-900 prose-th:border prose-th:border-slate-800 prose-th:px-3 prose-th:py-2
        prose-td:border prose-td:border-slate-800 prose-td:px-3 prose-td:py-2"
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}

export default MarkdownRenderer;
