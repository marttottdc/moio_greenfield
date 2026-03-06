# Moio Data Lab API Specification — Analysis & Implementation Guide

## Executive Summary

This document provides a **frontend-only** analysis of the **Moio Data Lab Frontend Specification** and outlines implementation recommendations for integrating it into the ReactMoioCRM-UI codebase.

**Focus**: Pure frontend implementation — API consumption, UI components, and user experience  
**Status**: ✅ Specification is well-structured and comprehensive  
**Integration Complexity**: Medium-High (new module, multiple complex workflows)  
**Estimated Implementation**: 15-20 components, 5-7 pages, TypeScript types, API client

**Frontend Responsibilities**:
- ✅ TypeScript type definitions
- ✅ API client implementation
- ✅ React components and pages
- ✅ User interface and UX
- ✅ Client-side validation
- ✅ Error handling and user feedback
- ✅ Loading states and progress indicators

---

## 1. Specification Analysis

### 1.1 Strengths

✅ **Well-Defined Data Model**
- Clear ResultSet structure with lineage tracking
- Comprehensive ImportContract with versioning
- Proper separation of concerns (Files, FileSets, Imports, Scripts, Pipelines)

✅ **Complete API Coverage**
- All CRUD operations defined
- Preview functionality before execution
- Proper error handling structure
- Pagination support

✅ **Security Considerations**
- Multi-tenancy built-in
- Script sandboxing mentioned
- Authentication requirements clear

✅ **Developer-Friendly**
- Detailed request/response examples
- TypeScript interfaces provided
- Clear workflow examples

### 1.2 Areas for Clarification

⚠️ **Async Operations**
- Script execution returns `task_id` but no polling endpoint documented
- Need to clarify: How to check task status? Webhook support?
- Pipeline execution is synchronous (could be slow for large datasets)

⚠️ **File Upload**
- No mention of file size limits
- No progress tracking endpoint
- Chunked upload support unclear

⚠️ **Widget Rendering**
- Cache invalidation strategy not specified
- Real-time refresh mechanism unclear
- Widget data refresh intervals not defined

⚠️ **ResultSet Expiration**
- `expires_at` field exists but no automatic cleanup policy documented
- How to extend expiration?

⚠️ **Snapshot Versioning**
- Version increment logic not fully specified
- What happens when creating snapshot with existing name?

---

## 2. TypeScript Type Definitions

### 2.1 Core Types (Add to `moio-types.ts`)

```typescript
// Core Data Lab Types
export interface ColumnDefinition {
  name: string;
  type: 'string' | 'integer' | 'decimal' | 'boolean' | 'date' | 'datetime';
  nullable: boolean;
  original_type?: string;
}

export interface ResultSet {
  id: string;
  name: string | null;
  origin: 'import' | 'crm_query' | 'script' | 'pipeline';
  schema_json: ColumnDefinition[];
  row_count: number;
  storage: 'memory' | 'parquet';
  storage_key?: string;
  preview_json: Record<string, any>[];
  lineage_json: {
    inputs?: any[];
    filters?: Record<string, any>;
    contract?: ImportContract;
    [key: string]: any;
  };
  created_by?: string;
  created_at: string;
  expires_at?: string | null;
}

// Import Contract Types
export interface ImportContract {
  version: "1";
  parser: {
    type: "csv" | "excel";
    delimiter?: string;
    header_row?: number;
    skip_rows?: number;
    sheet?: string | number;
    encoding?: string;
    range?: {
      start_row?: number;
      end_row?: number;
      start_col?: string;
      end_col?: string;
    };
  };
  mapping: MappingItem[];
  dedupe?: {
    keys: string[];
    strategy: "keep_first" | "keep_last";
  };
  output: {
    name: string;
    materialize?: boolean;
    accumulation_strategy?: "append" | "merge";
    merge_keys?: string[];
  };
}

export interface MappingItem {
  source: string;
  target: string;
  type: "string" | "integer" | "decimal" | "boolean" | "date" | "datetime";
  clean?: ("trim" | "upper" | "lower" | "capitalize" | "remove_non_numeric" | "currency_to_decimal")[];
}

// File & FileSet Types
export interface DataLabFile {
  id: string;
  filename: string;
  content_type: string;
  size: number;
  storage_key?: string;
  created_at: string;
}

export interface FileSet {
  id: string;
  name: string;
  description?: string;
  file_count: number;
  created_at: string;
  updated_at: string;
}

// CRM DataSource Types
export interface CRMView {
  id: string;
  key: string;
  label: string;
  description?: string;
  schema_json: ColumnDefinition[];
  allowed_filters_json: string[];
  default_filters_json: Record<string, any>;
  is_active: boolean;
}

export interface CRMQueryRequest {
  view_key: string;
  filters?: Record<string, any>;
  limit?: number;
  materialize?: boolean;
}

// Script Types
export interface Script {
  id: string;
  name: string;
  slug: string;
  description?: string;
  code: string;
  input_spec_json: Record<string, ScriptInputSpec>;
  output_spec_json: Record<string, ScriptOutputSpec>;
  created_at: string;
  updated_at: string;
}

export interface ScriptInputSpec {
  name: string;
  type: "dataframe";
  required: boolean;
}

export interface ScriptOutputSpec {
  name: string;
  type: "number" | "string" | "dataframe" | "boolean";
}

export interface ScriptExecuteRequest {
  inputs: Record<string, string>; // DataSource ID
  params?: Record<string, any>;
}

export interface ScriptExecuteResponse {
  task_id: string;
  status: "pending" | "running" | "success" | "failed";
  script_id: string;
}

// Pipeline Types
export interface PipelineStep {
  id: string;
  type: "crm_query" | "script";
  config: {
    view_key?: string;
    filters?: Record<string, any>;
    script_id?: string;
    inputs?: Record<string, string>;
    params?: Record<string, any>;
  };
  output?: string;
}

export interface Pipeline {
  id: string;
  name: string;
  description?: string;
  steps_json: PipelineStep[];
  params_json: PipelineParam[];
  is_active: boolean;
  created_at: string;
}

export interface PipelineParam {
  name: string;
  type: "string" | "number" | "date" | "boolean";
  default?: string;
}

export interface PipelineRun {
  id: string;
  pipeline: string;
  pipeline_name: string;
  status: "pending" | "running" | "success" | "failed";
  params_json: Record<string, any>;
  outputs_json: Record<string, string>; // ResultSet IDs
  step_results_json: Record<string, string>; // Step ID -> ResultSet ID
  started_at: string;
  completed_at?: string;
  duration_seconds?: number;
}

// Panel & Widget Types
export interface Panel {
  id: string;
  name: string;
  description?: string;
  layout_json: {
    grid: {
      columns: number;
      rowHeight: number;
    };
  };
  is_public: boolean;
  shared_with_roles: string[];
  widget_count: number;
  created_at: string;
}

export type WidgetType = "table" | "kpi" | "linechart" | "barchart" | "piechart";

export interface Widget {
  id: string;
  panel: string;
  name: string;
  widget_type: WidgetType;
  datasource_id: string;
  config_json: WidgetConfig;
  position_x: number;
  position_y: number;
  width: number;
  height: number;
  order: number;
}

export interface WidgetConfig {
  // Table Widget
  columns?: string[];
  page?: number;
  page_size?: number;
  sort_by?: string;
  sort_ascending?: boolean;
  filters?: Record<string, any>;
  
  // KPI Widget
  value_column?: string;
  aggregation?: "sum" | "avg" | "min" | "max" | "count";
  format?: string;
  label?: string;
  comparison_column?: string;
  
  // Chart Widgets
  x_column?: string;
  y_column?: string;
  limit?: number;
  x_label?: string;
  y_label?: string;
}

export interface RenderedWidget {
  id: string;
  name: string;
  type: WidgetType;
  position: {
    x: number;
    y: number;
    width: number;
    height: number;
  };
  data: WidgetData;
}

export interface WidgetData {
  type: WidgetType;
  // KPI Data
  value?: number;
  formatted_value?: string;
  aggregation?: string;
  label?: string;
  // Table Data
  columns?: string[];
  rows?: Record<string, any>[];
  pagination?: {
    page: number;
    page_size: number;
    total_rows: number;
    total_pages: number;
  };
  // Chart Data
  x_column?: string;
  y_column?: string;
  data_points?: Array<{ x: any; y: any }>;
}

// Snapshot Types
export interface Snapshot {
  id: string;
  name: string;
  version: number;
  resultset: ResultSet;
  fileset?: string;
  description?: string;
  created_at: string;
}
```

---

## 3. API Client Implementation

### 3.1 Complete API Client (Add to `api.ts`)

```typescript
import { apiRequest } from './queryClient';
import type { 
  DataLabFile, FileSet, ResultSet, ImportContract, 
  CRMView, CRMQueryRequest, Script, ScriptExecuteRequest,
  Pipeline, PipelineRun, Panel, Widget, Snapshot 
} from './moio-types';

export const dataLabApi = {
  // Files
  uploadFile: async (file: File, filename?: string, onProgress?: (progress: number) => void): Promise<DataLabFile> => {
    const formData = new FormData();
    formData.append('file', file);
    if (filename) formData.append('filename', filename);
    
    // Use XMLHttpRequest for progress tracking (fetch doesn't support progress)
    if (onProgress) {
      return new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        const url = createApiUrl(apiV1('/datalab/files/'));
        const headers = getAuthHeaders();
        
        xhr.upload.addEventListener('progress', (e) => {
          if (e.lengthComputable) {
            onProgress((e.loaded / e.total) * 100);
          }
        });
        
        xhr.addEventListener('load', () => {
          if (xhr.status >= 200 && xhr.status < 300) {
            resolve(JSON.parse(xhr.responseText));
          } else {
            reject(new Error(`Upload failed: ${xhr.statusText}`));
          }
        });
        
        xhr.addEventListener('error', () => reject(new Error('Upload failed')));
        
        xhr.open('POST', url);
        Object.entries(headers).forEach(([key, value]) => {
          if (typeof value === 'string') {
            xhr.setRequestHeader(key, value);
          }
        });
        xhr.send(formData);
      });
    }
    
    // Fallback to fetch if no progress callback
    const res = await apiRequest('POST', apiV1('/datalab/files/'), { body: formData });
    return res;
  },
  
  listFiles: async (page = 1, pageSize = 20): Promise<PaginatedResponse<DataLabFile>> => {
    return apiRequest('GET', apiV1('/datalab/files/'), {
      params: { page, page_size: pageSize }
    });
  },
  
  // FileSets
  createFileSet: async (data: { name: string; description?: string; files: string[] }): Promise<FileSet> => {
    return apiRequest('POST', apiV1('/datalab/filesets/'), { data });
  },
  
  listFileSets: async (): Promise<FileSet[]> => {
    return apiRequest('GET', apiV1('/datalab/filesets/'));
  },
  
  // Imports
  previewImport: async (data: { source: { file_id: string }; contract: ImportContract }): Promise<{
    detected_schema: ColumnDefinition[];
    sample_rows: Record<string, any>[];
    row_count: number;
    warnings: string[];
  }> => {
    return apiRequest('POST', apiV1('/datalab/imports/preview/'), { data });
  },
  
  executeImport: async (data: {
    source: { file_id?: string; fileset_id?: string };
    contract: ImportContract;
    rebuild?: boolean;
  }): Promise<{
    resultset_id: string;
    schema: ColumnDefinition[];
    row_count: number;
    preview: Record<string, any>[];
    snapshot_id?: string;
  }> => {
    return apiRequest('POST', apiV1('/datalab/imports/execute/'), { data });
  },
  
  // CRM DataSources
  listCRMViews: async (): Promise<CRMView[]> => {
    return apiRequest('GET', apiV1('/datalab/crm/views/'));
  },
  
  getCRMView: async (key: string): Promise<CRMView> => {
    return apiRequest('GET', apiV1(`/datalab/crm/views/${key}/`));
  },
  
  executeCRMQuery: async (data: CRMQueryRequest): Promise<{
    resultset_id: string;
    schema: ColumnDefinition[];
    row_count: number;
    preview: Record<string, any>[];
  }> => {
    return apiRequest('POST', apiV1('/datalab/crm/query/query/'), { data });
  },
  
  // Scripts
  createScript: async (data: {
    name: string;
    slug?: string;
    description?: string;
    code: string;
    input_spec_json: Record<string, any>;
    output_spec_json: Record<string, any>;
    version_notes?: string;
  }): Promise<Script> => {
    return apiRequest('POST', apiV1('/datalab/scripts/'), { data });
  },
  
  listScripts: async (): Promise<Script[]> => {
    return apiRequest('GET', apiV1('/datalab/scripts/'));
  },
  
  getScriptSpec: async (id: string): Promise<{ input_spec: any; output_spec: any }> => {
    return apiRequest('GET', apiV1(`/datalab/scripts/${id}/spec/`));
  },
  
  executeScript: async (id: string, data: ScriptExecuteRequest): Promise<{
    task_id: string;
    status: 'pending' | 'running' | 'success' | 'failed';
    script_id: string;
  }> => {
    return apiRequest('POST', apiV1(`/datalab/scripts/${id}/execute/`), { data });
  },
  
  // Pipelines
  createPipeline: async (data: {
    name: string;
    description?: string;
    steps_json: PipelineStep[];
    params_json: PipelineParam[];
  }): Promise<Pipeline> => {
    return apiRequest('POST', apiV1('/datalab/pipelines/'), { data });
  },
  
  listPipelines: async (): Promise<Pipeline[]> => {
    return apiRequest('GET', apiV1('/datalab/pipelines/'));
  },
  
  executePipeline: async (id: string, data: { params: Record<string, any> }): Promise<PipelineRun> => {
    return apiRequest('POST', apiV1(`/datalab/pipelines/${id}/run/`), { data });
  },
  
  listPipelineRuns: async (id: string): Promise<PipelineRun[]> => {
    return apiRequest('GET', apiV1(`/datalab/pipelines/${id}/runs/`));
  },
  
  getPipelineRunHistory: async (pipeline?: string): Promise<PipelineRun[]> => {
    return apiRequest('GET', apiV1('/datalab/pipeline-runs/'), {
      params: pipeline ? { pipeline } : undefined
    });
  },
  
  // Panels & Widgets
  createPanel: async (data: {
    name: string;
    description?: string;
    layout_json: any;
    is_public?: boolean;
    shared_with_roles?: string[];
  }): Promise<Panel> => {
    return apiRequest('POST', apiV1('/datalab/panels/'), { data });
  },
  
  listPanels: async (): Promise<Panel[]> => {
    return apiRequest('GET', apiV1('/datalab/panels/'));
  },
  
  renderPanel: async (id: string): Promise<{
    panel: Panel;
    widgets: RenderedWidget[];
    layout: any;
  }> => {
    return apiRequest('GET', apiV1(`/datalab/panels/${id}/render/`));
  },
  
  createWidget: async (data: {
    panel: string;
    name: string;
    widget_type: WidgetType;
    datasource_id: string;
    config_json: WidgetConfig;
    position_x: number;
    position_y: number;
    width: number;
    height: number;
    order: number;
  }): Promise<Widget> => {
    return apiRequest('POST', apiV1('/datalab/widgets/'), { data });
  },
  
  renderWidget: async (id: string): Promise<{
    widget: Widget;
    data: WidgetData;
  }> => {
    return apiRequest('GET', apiV1(`/datalab/widgets/${id}/render/`));
  },
  
  // ResultSets & Snapshots
  getResultSet: async (id: string): Promise<ResultSet> => {
    return apiRequest('GET', apiV1(`/datalab/resultsets/${id}/`));
  },
  
  listResultSets: async (origin?: string, page = 1, pageSize = 20): Promise<PaginatedResponse<ResultSet>> => {
    return apiRequest('GET', apiV1('/datalab/resultsets/'), {
      params: { origin, page, page_size: pageSize }
    });
  },
  
  materializeResultSet: async (id: string): Promise<ResultSet> => {
    return apiRequest('POST', apiV1(`/datalab/resultsets/${id}/materialize/`));
  },
  
  createSnapshot: async (data: {
    name: string;
    resultset_id: string;
    fileset?: string;
    description?: string;
  }): Promise<Snapshot> => {
    return apiRequest('POST', apiV1('/datalab/snapshots/'), { data });
  },
  
  listSnapshots: async (name?: string): Promise<Snapshot[]> => {
    return apiRequest('GET', apiV1('/datalab/snapshots/'), {
      params: name ? { name } : undefined
    });
  },
};
```

---

### 3.2 React Hooks for Data Lab

**Recommended Custom Hooks** (create in `client/src/hooks/`):

```typescript
// hooks/useDataLabFiles.ts
export function useDataLabFiles() {
  return useQuery({
    queryKey: ['datalab', 'files'],
    queryFn: () => dataLabApi.listFiles(),
  });
}

// hooks/useDataLabResultSet.ts
export function useDataLabResultSet(id: string | undefined) {
  return useQuery({
    queryKey: ['datalab', 'resultsets', id],
    queryFn: () => id ? dataLabApi.getResultSet(id) : null,
    enabled: !!id,
  });
}

// hooks/useScriptExecution.ts
export function useScriptExecution(scriptId: string) {
  const [taskId, setTaskId] = useState<string | null>(null);
  
  const executeMutation = useMutation({
    mutationFn: (data: ScriptExecuteRequest) => 
      dataLabApi.executeScript(scriptId, data),
    onSuccess: (data) => setTaskId(data.task_id),
  });
  
  // Poll for task status (if endpoint exists)
  const taskStatus = useQuery({
    queryKey: ['datalab', 'tasks', taskId],
    queryFn: () => taskId ? checkTaskStatus(taskId) : null,
    enabled: !!taskId,
    refetchInterval: (data) => 
      data?.status === 'pending' || data?.status === 'running' ? 2000 : false,
  });
  
  return { executeMutation, taskStatus };
}

// hooks/useWidgetRefresh.ts
export function useWidgetRefresh(widgetId: string, interval = 30000) {
  return useQuery({
    queryKey: ['datalab', 'widgets', widgetId, 'render'],
    queryFn: () => dataLabApi.renderWidget(widgetId),
    refetchInterval: interval,
    staleTime: interval / 2,
  });
}
```

---

## 4. Frontend Component Structure

### 4.1 Recommended Page Components

```
client/src/pages/
├── datalab/
│   ├── index.tsx                    # Data Lab landing/dashboard
│   ├── files.tsx                    # File management
│   ├── imports/
│   │   ├── index.tsx                # Import list
│   │   ├── new-import.tsx           # New import wizard
│   │   └── import-preview.tsx       # Import preview & mapping
│   ├── datasources/
│   │   ├── index.tsx                # DataSource browser
│   │   └── crm-query-builder.tsx    # CRM query builder
│   ├── scripts/
│   │   ├── index.tsx                # Script list (reuse existing?)
│   │   ├── editor.tsx               # Script editor
│   │   └── executor.tsx             # Script execution UI
│   ├── pipelines/
│   │   ├── index.tsx                # Pipeline list
│   │   ├── builder.tsx              # Pipeline builder (visual)
│   │   └── runs.tsx                 # Pipeline run history
│   ├── panels/
│   │   ├── index.tsx                # Panel list
│   │   ├── designer.tsx             # Panel designer (drag-drop)
│   │   └── viewer.tsx               # Panel viewer (read-only)
│   └── resultsets/
│       ├── index.tsx                # ResultSet browser
│       └── viewer.tsx               # ResultSet data viewer
```

### 4.2 Recommended Shared Components

```
client/src/components/datalab/
├── file-uploader.tsx                # File upload with progress
├── import-contract-builder.tsx      # ImportContract form builder
├── column-mapper.tsx                # Column mapping interface
├── resultset-preview.tsx            # ResultSet preview table
├── script-editor.tsx                # Code editor for scripts
├── pipeline-step-node.tsx           # Pipeline step visual node
├── widget/
│   ├── widget-renderer.tsx          # Widget renderer dispatcher
│   ├── table-widget.tsx             # Table widget
│   ├── kpi-widget.tsx               # KPI widget
│   ├── line-chart-widget.tsx        # Line chart widget
│   ├── bar-chart-widget.tsx         # Bar chart widget
│   └── pie-chart-widget.tsx         # Pie chart widget
└── datasource-selector.tsx          # DataSource picker component
```

---

## 5. Implementation Recommendations

### 5.1 Phase 1: Core Infrastructure (Week 1-2)

1. **Type Definitions**
   - Add all TypeScript types to `moio-types.ts`
   - Create `datalab-types.ts` if separation preferred

2. **API Client**
   - Implement `dataLabApi` in `api.ts`
   - Add request/response handlers
   - Implement error handling

3. **Basic Pages**
   - File upload/management
   - ResultSet browser
   - Basic import flow

### 5.2 Phase 2: Import & Data Sources (Week 3-4)

1. **Import Wizard**
   - File upload → Preview → Mapping → Execute
   - ImportContract builder UI
   - Column mapping interface

2. **CRM DataSources**
   - CRM view browser
   - Query builder UI
   - Filter interface

### 5.3 Phase 3: Scripts & Pipelines (Week 5-6)

1. **Script Management**
   - Script editor (Monaco or CodeMirror)
   - Input/output spec builder
   - Execution UI with async handling

2. **Pipeline Builder**
   - Visual pipeline builder (React Flow?)
   - Step configuration
   - Parameter management

### 5.4 Phase 4: Panels & Widgets (Week 7-8)

1. **Panel Designer**
   - Drag-and-drop layout (react-grid-layout?)
   - Widget placement
   - Layout persistence

2. **Widget System**
   - Widget renderers (table, KPI, charts)
   - Data binding
   - Refresh mechanism

### 5.5 Phase 5: Polish & Optimization (Week 9-10)

1. **Performance**
   - Widget caching
   - Lazy loading
   - Virtual scrolling for large tables

2. **UX Improvements**
   - Loading states
   - Error boundaries
   - Toast notifications
   - Help tooltips

---

## 6. Technical Considerations

### 6.1 Async Operations

**Issue**: Script execution is async but no polling endpoint documented.

**Frontend Implementation**:
- **Polling Strategy**: Implement polling mechanism (check every 2-5 seconds) until status changes
- **Timeout Handling**: Add timeout (30-60 seconds) with user notification
- **Loading States**: Show progress indicators and allow cancellation
- **WebSocket Option**: If backend supports WebSockets, use for real-time updates
- **Fallback**: If no polling endpoint exists, show "Processing..." with manual refresh button

### 6.2 File Upload

**Frontend Implementation**:
- **Progress Tracking**: Use `XMLHttpRequest` for upload progress (fetch API doesn't support progress events)
- **Progress UI**: Show percentage, speed, and ETA
- **Error Handling**: Retry logic for failed uploads (3 attempts with exponential backoff)
- **File Validation**: Client-side validation for file type and size (if limits known)
- **Chunked Upload**: If backend supports, implement for files > 10MB
- **Multiple Files**: Support drag-and-drop for multiple file selection

### 6.3 Large Dataset Handling

**Issue**: ResultSets can be very large (Parquet storage).

**Recommendation**:
- Always use pagination for table views
- Implement virtual scrolling (react-window or react-virtual)
- Lazy load preview data
- Show row count and storage type indicators

### 6.4 Widget Refresh

**Issue**: Refresh mechanism not specified.

**Recommendation**:
- Implement configurable refresh intervals (30s, 1m, 5m, manual)
- Add refresh button per widget
- Cache widget data with TTL
- Show last updated timestamp

### 6.5 Error Handling

**Frontend Implementation**:
- **Error Boundary**: Create `DataLabErrorBoundary` component to catch React errors
- **API Error Handling**: Parse backend error responses and show user-friendly messages
- **Retry Logic**: Implement retry for transient failures (network errors, 5xx responses)
- **Error Logging**: Log errors to console in development, consider error tracking service in production
- **User Feedback**: Use toast notifications for operation feedback (success/error)
- **Validation**: Client-side validation before API calls to reduce errors

---

## 7. Integration Points

### 7.1 Existing Codebase Patterns

✅ **Follow Existing Patterns**:
- Use `apiV1()` helper for endpoints
- Follow `PaginatedResponse<T>` pattern
- Use existing error handling (`MoioErrorResponse`)
- Follow component structure (pages in `pages/`, shared in `components/`)

### 7.2 Navigation Integration

**Add to App Sidebar**:
```typescript
{
  title: "Data Lab",
  icon: Database,
  path: "/datalab",
  children: [
    { title: "Overview", path: "/datalab" },
    { title: "Files", path: "/datalab/files" },
    { title: "Imports", path: "/datalab/imports" },
    { title: "Data Sources", path: "/datalab/datasources" },
    { title: "Scripts", path: "/datalab/scripts" },
    { title: "Pipelines", path: "/datalab/pipelines" },
    { title: "Panels", path: "/datalab/panels" },
    { title: "ResultSets", path: "/datalab/resultsets" },
  ]
}
```

### 7.3 Reusable Components

**Leverage Existing UI Components**:
- `Button`, `Input`, `Select` from `components/ui/`
- `Table` component for data display
- `Card` for panel/widget containers
- `Dialog` for modals
- `Toast` for notifications

---

## 8. Testing Strategy

### 8.1 Unit Tests

- Type definitions validation
- API client functions
- Utility functions (mapping, formatting)

### 8.2 Integration Tests

- File upload flow
- Import workflow (upload → preview → execute)
- Script execution flow
- Pipeline execution flow

### 8.3 E2E Tests

- Complete import workflow
- Dashboard creation workflow
- Pipeline creation and execution

---

## 9. Frontend Implementation Questions (API Clarifications Needed)

**Note**: As a frontend-only implementation, we need clarification on these API behaviors:

1. **Task Polling**: Script execution returns `task_id` but no polling endpoint is documented. How should we check execution status?
   - Is there a `/api/v1/datalab/tasks/{task_id}/` endpoint?
   - What's the polling interval recommendation?
   - Should we use WebSockets for real-time updates?

2. **File Upload Limits**: 
   - Maximum file size for uploads?
   - Supported file types beyond CSV/Excel?
   - Chunked upload support for large files?

3. **Widget Refresh Strategy**:
   - Cache-Control headers on `/render/` endpoints?
   - Recommended refresh intervals?
   - Any rate limits on widget rendering?

4. **ResultSet Expiration**:
   - How to extend `expires_at`?
   - Warning before expiration?
   - Auto-cleanup behavior?

5. **Snapshot Versioning**:
   - Exact behavior when creating snapshot with existing name?
   - How to access specific versions?

6. **Error Response Details**:
   - Are validation errors returned with field-level details?
   - Format for script execution errors?

7. **Pagination**:
   - Default and maximum `page_size` values?
   - Consistent pagination format across all list endpoints?

8. **Async Operations**:
   - Timeout recommendations for script execution?
   - Webhook support for completion notifications?

---

## 10. Dependencies to Add

```json
{
  "dependencies": {
    "react-grid-layout": "^1.4.4",        // Panel designer
    "react-flow-renderer": "^10.3.17",    // Pipeline builder (optional)
    "monaco-editor": "^0.44.0",           // Script editor
    "react-window": "^1.8.10",            // Virtual scrolling
    "recharts": "^2.10.3",                // Chart widgets
    "papaparse": "^5.4.1",                // CSV parsing (preview)
    "xlsx": "^0.18.5"                     // Excel parsing (preview)
  }
}
```

---

## 11. Conclusion

The **Moio Data Lab API Specification** is comprehensive and well-structured for frontend implementation. The main challenges are:

1. **Complexity**: Multiple interconnected workflows (imports → scripts → pipelines → panels)
2. **Async Operations**: Need to implement polling mechanism for script execution (pending API clarification)
3. **Large Datasets**: Proper handling of Parquet-stored ResultSets with virtual scrolling
4. **UI Complexity**: Drag-and-drop panel designer, visual pipeline builder

**Frontend-Only Implementation Approach**:
- ✅ Start with core infrastructure (TypeScript types, API client)
- ✅ Build basic file/import flow first (most straightforward)
- ✅ Iteratively add features (scripts → pipelines → panels)
- ✅ Focus on UX for complex workflows (wizards, visual builders)
- ✅ Handle API limitations gracefully (polling, error handling, loading states)

**Estimated Timeline**: 8-10 weeks for full implementation with 1-2 frontend developers.

**Next Steps**:
1. Clarify API questions (Section 9) with backend team
2. Implement TypeScript types and API client
3. Build MVP with file upload and basic import flow
4. Iterate based on user feedback and API behavior

---

**Document Version**: 1.0  
**Last Updated**: 2025-01-15  
**Author**: AI Analysis
