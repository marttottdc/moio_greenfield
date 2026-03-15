import { useQuery } from "@tanstack/react-query";
import { fetchJson } from "@/lib/queryClient";

const DOCS_BASE = "/api/docs";

export type DocsNavigationNode = {
  type: "guide-category" | "guide" | "section" | "api-tag";
  slug: string;
  title: string;
  children?: DocsNavigationNode[];
};

export interface DocsNavigationResponse {
  navigation: DocsNavigationNode[];
}

export interface DocsGuide {
  slug: string;
  title: string;
  summary?: string;
  content?: string;
  content_html?: string;
  category?: string;
  prev?: { slug: string; title: string } | null;
  next?: { slug: string; title: string } | null;
}

export interface DocsGuideCategory {
  id: string;
  slug: string;
  name: string;
  description?: string;
  icon?: string;
  guides: Array<
    Omit<DocsGuide, "content" | "content_html" | "prev" | "next"> & {
      category_name?: string;
      category_slug?: string;
      updated_at?: string;
    }
  >;
}

export interface DocsGuideListResponse {
  categories: DocsGuideCategory[];
}

export interface DocsEndpointExample {
  language: string;
  code: string;
}

export interface DocsEndpointResponseFormatItem {
  status?: string;
  content_type?: string;
  schema?: string;
  description?: string;
}

export interface DocsEndpointRequestBodyItem {
  content_type?: string;
  schema?: string;
}

export interface DocsEndpointListItem {
  operation_id: string;
  path: string;
  method: string;
  summary?: string;
  description?: string;
  tags?: string[];
  deprecated?: boolean;
  response_format?: DocsEndpointResponseFormatItem[];
  request_body?: DocsEndpointRequestBodyItem[] | null;
}

// Alias for endpoint card component compatibility
export type DocsEndpoint = DocsEndpointListItem;

export interface DocsEndpointListResponse {
  endpoints: DocsEndpointListItem[];
  count?: number;
  total_count?: number;
  page?: number;
  page_size?: number;
  total_pages?: number;
}

export interface DocsEndpointDetail {
  spec: {
    path: string;
    method: string;
    operationId: string;
    summary?: string;
    description?: string;
    tags?: string[];
    parameters?: any[];
    responses?: Record<string, any>;
    requestBody?: any;
  };
  response_format?: DocsEndpointResponseFormatItem[];
  request_body?: DocsEndpointRequestBodyItem[] | null;
  examples?: DocsEndpointExample[];
  notes?: Array<{
    id: string;
    operation_id: string;
    note_type: string;
    title: string;
    content: string;
  }>;
  schemas?: Record<string, any>;
}

export interface DocsSearchResponse {
  guides: Array<{
    id: string;
    slug: string;
    title: string;
    summary?: string;
    category_name?: string;
    category_slug?: string;
    updated_at?: string;
  }>;
  endpoints: Array<{
    operation_id: string;
    path: string;
    method: string;
    summary?: string;
    tags?: string[];
  }>;
}

export function useDocsNavigation() {
  return useQuery<DocsNavigationResponse>({
    queryKey: ["docs", "navigation"],
    queryFn: () => fetchJson<DocsNavigationResponse>(`${DOCS_BASE}/navigation/`),
    staleTime: 5 * 60 * 1000,
  });
}

export function useDocsGuides() {
  return useQuery<DocsGuideListResponse>({
    queryKey: ["docs", "guides"],
    queryFn: () => fetchJson<DocsGuideListResponse>(`${DOCS_BASE}/guides/`),
    staleTime: 5 * 60 * 1000,
  });
}

export function useDocsGuide(slug?: string) {
  return useQuery<{ guide: DocsGuide; prev: DocsGuide | null; next: DocsGuide | null }>({
    queryKey: ["docs", "guide", slug],
    queryFn: () => fetchJson<{ guide: DocsGuide; prev: DocsGuide | null; next: DocsGuide | null }>(`${DOCS_BASE}/guides/${slug}/`),
    enabled: Boolean(slug),
  });
}

export interface UseDocsEndpointsParams {
  tag?: string;
  search?: string;
  page?: number;
  page_size?: number;
}

export function useDocsEndpoints(params?: UseDocsEndpointsParams | string) {
  const resolved =
    typeof params === "string" ? { tag: params } : params ?? {};
  const { tag, search, page, page_size } = resolved;
  const queryParams: Record<string, string | number | undefined> = {};
  if (tag) queryParams.tag = tag;
  if (search) queryParams.search = search;
  if (page != null) queryParams.page = page;
  if (page_size != null) queryParams.page_size = page_size;

  return useQuery<DocsEndpointListResponse>({
    queryKey: ["docs", "endpoints", tag, search, page, page_size],
    queryFn: () =>
      fetchJson<DocsEndpointListResponse>(
        `${DOCS_BASE}/endpoints/`,
        Object.keys(queryParams).length ? queryParams : undefined
      ),
    staleTime: 5 * 60 * 1000,
  });
}

export function useDocsEndpoint(operationId?: string) {
  return useQuery<DocsEndpointDetail>({
    queryKey: ["docs", "endpoint", operationId],
    queryFn: () => fetchJson<DocsEndpointDetail>(`${DOCS_BASE}/endpoints/${operationId}/`),
    enabled: Boolean(operationId),
    staleTime: 5 * 60 * 1000,
  });
}

export function useDocsSearch(query: string) {
  return useQuery<DocsSearchResponse>({
    queryKey: ["docs", "search", query],
    queryFn: () => fetchJson<DocsSearchResponse>(`${DOCS_BASE}/search/`, { q: query }),
    enabled: query.trim().length > 0,
  });
}
