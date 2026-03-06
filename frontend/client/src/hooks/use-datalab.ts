/**
 * React hooks for Data Lab API operations
 */

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { dataLabApi } from "@/lib/api";
import type {
  DataLabFile,
  ResultSet,
  FileSet,
  Script,
  Pipeline,
  Panel,
  Snapshot,
  PaginatedResponse,
  ImportProcess,
  ImportRun,
} from "@/lib/moio-types";

// Files
export function useDataLabFiles(page = 1, pageSize = 20) {
  return useQuery({
    queryKey: ["datalab", "files", page, pageSize],
    queryFn: async () => {
      const response = await dataLabApi.listFiles(page, pageSize);
      console.log("Files API response:", response);
      return response;
    },
    staleTime: 0, // Always consider data stale - fetch fresh every time
    gcTime: 0, // Don't cache (React Query v5) - always fetch fresh
    refetchOnMount: "always", // Always refetch when component mounts
    refetchOnWindowFocus: true, // Refetch when window regains focus
    refetchOnReconnect: true, // Refetch when network reconnects
  });
}

export function useDataLabFileUpload() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      file,
      filename,
      onProgress,
    }: {
      file: File;
      filename?: string;
      onProgress?: (progress: number) => void;
    }) => dataLabApi.uploadFile(file, filename, onProgress),
    onSuccess: () => {
      // Invalidate and refetch all file queries
      queryClient.invalidateQueries({ queryKey: ["datalab", "files"] });
      // Also refetch immediately
      queryClient.refetchQueries({ queryKey: ["datalab", "files"] });
    },
  });
}

// FileSets
export function useDataLabFileSets() {
  return useQuery({
    queryKey: ["datalab", "filesets"],
    queryFn: () => dataLabApi.listFileSets(),
  });
}

export function useDataLabFileSetCreate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: {
      name: string;
      description?: string;
      files: string[];
    }) => dataLabApi.createFileSet(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["datalab", "filesets"] });
    },
  });
}

// ResultSets
export function useDataLabResultSet(id: string | undefined) {
  return useQuery({
    queryKey: ["datalab", "resultsets", id],
    queryFn: () => (id ? dataLabApi.getResultSet(id) : null),
    enabled: !!id,
  });
}

export function useDataLabResultSets(
  origin?: string,
  page = 1,
  pageSize = 20
) {
  return useQuery({
    queryKey: ["datalab", "resultsets", origin, page, pageSize],
    queryFn: () => dataLabApi.listResultSets(origin, page, pageSize),
  });
}

// Datasets - durable, versioned data products (from pipelines or promotion)
export function useDataLabDatasets(page = 1, pageSize = 20) {
  return useQuery({
    queryKey: ["datalab", "datasets", page, pageSize],
    queryFn: () => dataLabApi.listDatasets(page, pageSize),
  });
}

export function useDataLabDataset(id: string | undefined) {
  return useQuery({
    queryKey: ["datalab", "datasets", id],
    queryFn: () => dataLabApi.getDataset(id!),
    enabled: Boolean(id),
  });
}

export function useDataLabResultSetPromote() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, name }: { id: string; name?: string }) =>
      dataLabApi.promoteResultSet(id, name),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["datalab", "datasets"] });
      queryClient.invalidateQueries({ queryKey: ["datalab", "resultsets"] });
    },
  });
}

export function useDataLabResultSetUpdate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: { name?: string } }) =>
      dataLabApi.updateResultSet(id, data),
    onSuccess: (_, { id }) => {
      queryClient.invalidateQueries({ queryKey: ["datalab", "resultsets"] });
      queryClient.invalidateQueries({ queryKey: ["datalab", "resultsets", id] });
    },
  });
}

export function useDataLabResultSetDelete() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => dataLabApi.deleteResultSet(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["datalab", "resultsets"] });
    },
  });
}

export function useDataLabResultSetMaterialize() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => dataLabApi.materializeResultSet(id),
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({
        queryKey: ["datalab", "resultsets", id],
      });
    },
  });
}

// CRM Views
export function useDataLabCRMViews() {
  return useQuery({
    queryKey: ["datalab", "crm", "views"],
    queryFn: async () => {
      try {
        const result = await dataLabApi.listCRMViews();
        console.log("CRM Views API response:", result);
        return result;
      } catch (error) {
        console.error("CRM Views API error:", error);
        throw error;
      }
    },
    retry: 1,
  });
}

export function useDataLabCRMView(key: string | undefined) {
  return useQuery({
    queryKey: ["datalab", "crm", "views", key],
    queryFn: async () => {
      if (!key) return null;
      try {
        console.log("Fetching CRM view with key:", key);
        const result = await dataLabApi.getCRMView(key);
        console.log("CRM view API response:", result);
        return result;
      } catch (error) {
        console.error("CRM view API error:", error, "for key:", key);
        throw error;
      }
    },
    enabled: !!key,
    retry: 1,
  });
}

export function useDataLabCRMQuery() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: {
      view_key: string;
      filters?: Record<string, any>;
      limit?: number;
      materialize?: boolean;
    }) => dataLabApi.executeCRMQuery(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["datalab", "resultsets"] });
    },
  });
}

// Scripts
export function useDataLabScripts() {
  return useQuery({
    queryKey: ["datalab", "scripts"],
    queryFn: () => dataLabApi.listScripts(),
  });
}

export function useDataLabScript(id: string | undefined) {
  return useQuery({
    queryKey: ["datalab", "scripts", id],
    queryFn: () => dataLabApi.getScript(id!),
    enabled: Boolean(id),
  });
}

export function useDataLabScriptCreate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: {
      name: string;
      slug?: string;
      description?: string;
      code: string;
      input_spec_json: Record<string, any>;
      output_spec_json: Record<string, any>;
      version_notes?: string;
    }) => dataLabApi.createScript(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["datalab", "scripts"] });
    },
  });
}

export function useDataLabScriptExecute(scriptId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: {
      inputs: Record<string, string>;
      params?: Record<string, any>;
    }) => dataLabApi.executeScript(scriptId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["datalab", "resultsets"] });
    },
  });
}

// Pipelines
export function useDataLabPipelines() {
  return useQuery({
    queryKey: ["datalab", "pipelines"],
    queryFn: async () => {
      try {
        const result = await dataLabApi.listPipelines();
        console.log("Pipelines API response:", result);
        return result;
      } catch (error) {
        console.error("Pipelines API error:", error);
        throw error;
      }
    },
    retry: 1,
  });
}

export function useDataLabPipelineCreate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: {
      name: string;
      description?: string;
      steps_json: any[];
      params_json: any[];
    }) => dataLabApi.createPipeline(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["datalab", "pipelines"] });
    },
  });
}

export function useDataLabPipelineExecute(pipelineId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (params: Record<string, any>) =>
      dataLabApi.executePipeline(pipelineId, { params }),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["datalab", "pipelines", pipelineId, "runs"],
      });
      queryClient.invalidateQueries({ queryKey: ["datalab", "resultsets"] });
    },
  });
}

export function useDataLabPipelineRuns(pipelineId: string) {
  return useQuery({
    queryKey: ["datalab", "pipelines", pipelineId, "runs"],
    queryFn: () => dataLabApi.listPipelineRuns(pipelineId),
    enabled: !!pipelineId,
  });
}

// Panels
export function useDataLabPanels() {
  return useQuery({
    queryKey: ["datalab", "panels"],
    queryFn: async () => {
      try {
        const result = await dataLabApi.listPanels();
        console.log("Panels API response:", result);
        return result;
      } catch (error) {
        console.error("Panels API error:", error);
        throw error;
      }
    },
    retry: 1,
  });
}

export function useDataLabPanelCreate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: {
      name: string;
      description?: string;
      layout_json: any;
      is_public?: boolean;
      shared_with_roles?: string[];
    }) => dataLabApi.createPanel(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["datalab", "panels"] });
    },
  });
}

export function useDataLabPanelRender(panelId: string | undefined) {
  return useQuery({
    queryKey: ["datalab", "panels", panelId, "render"],
    queryFn: () => (panelId ? dataLabApi.renderPanel(panelId) : null),
    enabled: !!panelId,
  });
}

// Widgets
export function useDataLabWidgetRender(
  widgetId: string | undefined,
  interval?: number
) {
  return useQuery({
    queryKey: ["datalab", "widgets", widgetId, "render"],
    queryFn: () => (widgetId ? dataLabApi.renderWidget(widgetId) : null),
    enabled: !!widgetId,
    refetchInterval: interval,
    staleTime: interval ? interval / 2 : undefined,
  });
}

export function useDataLabWidgetCreate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: {
      panel: string;
      name: string;
      widget_type: "table" | "kpi" | "linechart" | "barchart" | "piechart";
      datasource_id: string;
      config_json: any;
      position_x: number;
      position_y: number;
      width: number;
      height: number;
      order: number;
    }) => dataLabApi.createWidget(data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({
        queryKey: ["datalab", "panels", variables.panel, "render"],
      });
    },
  });
}

// Snapshots
export function useDataLabSnapshots(name?: string) {
  return useQuery({
    queryKey: ["datalab", "snapshots", name],
    queryFn: () => dataLabApi.listSnapshots(name),
  });
}

export function useDataLabSnapshotCreate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: {
      name: string;
      resultset_id: string;
      fileset?: string;
      description?: string;
    }) => dataLabApi.createSnapshot(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["datalab", "snapshots"] });
    },
  });
}

// Import operations
export function useDataLabImportPreview() {
  return useMutation({
    mutationFn: (data: {
      source: { file_id: string };
      contract: any;
    }) => dataLabApi.previewImport(data),
  });
}

export function useDataLabImportExecute() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: {
      source: { file_id?: string; fileset_id?: string };
      contract: any;
      rebuild?: boolean;
    }) => dataLabApi.executeImport(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["datalab", "resultsets"] });
    },
  });
}

// Inspect shape (PDF and other files via import-processes endpoint)
export function useDataLabImportInspectShape() {
  return useMutation({
    mutationFn: (data: { file_id: string; file_type: "csv" | "excel" | "pdf" }) =>
      dataLabApi.inspectProcessShape(data),
  });
}

// Import Processes (control plane)
export function useDataLabImportProcesses(
  page = 1,
  pageSize = 20,
  filters?: Record<string, any>
) {
  return useQuery({
    queryKey: ["datalab", "import-processes", page, pageSize, filters],
    queryFn: () => dataLabApi.listImportProcesses(page, pageSize, filters),
  });
}

export function useDataLabImportProcess(id: string | undefined) {
  return useQuery({
    queryKey: ["datalab", "import-processes", id],
    queryFn: () => (id ? dataLabApi.getImportProcess(id) : null),
    enabled: !!id,
  });
}

export function useDataLabImportProcessCreate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: {
      name: string;
      file_type: "csv" | "excel" | "pdf";
      file_id: string;
    }) => dataLabApi.createImportProcess(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["datalab", "import-processes"] });
    },
  });
}

export function useDataLabImportProcessUpdate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<ImportProcess> }) =>
      dataLabApi.updateImportProcess(id, data),
    onSuccess: (_result, variables) => {
      queryClient.invalidateQueries({ queryKey: ["datalab", "import-processes"] });
      queryClient.invalidateQueries({ queryKey: ["datalab", "import-processes", variables.id] });
    },
  });
}

export function useDataLabImportProcessRun(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: { raw_dataset_id: string }) =>
      dataLabApi.runImportProcess(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["datalab", "import-runs"] });
      queryClient.invalidateQueries({ queryKey: ["datalab", "resultsets"] });
    },
  });
}

export function useDataLabImportProcessClone() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (variables: { id: string; name?: string }) =>
      dataLabApi.cloneImportProcess(variables.id, variables.name ? { name: variables.name } : undefined),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ["datalab", "import-processes"] });
      queryClient.invalidateQueries({ queryKey: ["datalab", "import-processes", variables.id] });
    },
  });
}

export function useDataLabImportRuns(
  page = 1,
  pageSize = 20,
  filters?: Record<string, any>
) {
  return useQuery({
    queryKey: ["datalab", "import-runs", page, pageSize, filters],
    queryFn: () => dataLabApi.listImportRuns(page, pageSize, filters),
  });
}

export function useDataLabProcessShapeInspect() {
  return useMutation({
    mutationFn: (data: { file_id: string; file_type: "csv" | "excel" | "pdf" }) =>
      dataLabApi.inspectProcessShape(data),
  });
}
