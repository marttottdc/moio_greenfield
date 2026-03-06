
import { useQuery } from "@tanstack/react-query";
import { fetchJson } from "@/lib/queryClient";
import { apiV1 } from "@/lib/api";
import { Workflow } from "../types";

interface WorkflowsResponse {
  flows?: Workflow[];
  results?: Workflow[];
  data?: Workflow[];
  count?: number;
}

function normalizeCollection<T>(data: unknown, fallbackKey?: string): T[] {
  if (!data) return [];
  if (Array.isArray(data)) return data as T[];
  
  if (typeof data === "object" && data !== null) {
    const record = data as Record<string, unknown>;
    const fallbackValue = fallbackKey ? record[fallbackKey] : undefined;
    
    if (fallbackValue && Array.isArray(fallbackValue)) return fallbackValue as T[];
    if (Array.isArray(record.results)) return record.results as T[];
    if (Array.isArray(record.data)) return record.data as T[];
    if (Array.isArray(record.items)) return record.items as T[];
  }
  
  return [];
}

export function useWorkflowsData(page: number = 1, pageSize: number = 20) {
  const FLOWS_PATH = apiV1("/flows/");
  
  const query = useQuery<WorkflowsResponse>({
    queryKey: [FLOWS_PATH, { page, page_size: pageSize }],
    queryFn: () => fetchJson<WorkflowsResponse>(FLOWS_PATH, { 
      page: page.toString(), 
      page_size: pageSize.toString() 
    }),
  });
  
  const workflows = normalizeCollection<Workflow>(query.data, "flows").filter((flow) => Boolean(flow?.id));
  
  return {
    workflows,
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
    refetch: query.refetch,
  };
}
