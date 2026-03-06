import { useState, useCallback, useRef, useEffect, useMemo } from "react";
import { useRoute, useLocation } from "wouter";
import { useQuery, useMutation } from "@tanstack/react-query";
import ReactFlow, {
  Node,
  Edge,
  Controls,
  Background,
  BackgroundVariant,
  MiniMap,
  Panel,
  useNodesState,
  useEdgesState,
  addEdge,
  Connection,
  ReactFlowProvider,
  useReactFlow,
  NodeTypes,
} from "reactflow";
import "reactflow/dist/style.css";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Save,
  Play,
  ArrowLeft,
  Trash2,
  Download,
  Eye,
  Rocket,
  FlaskConical,
  ChevronLeft,
  ChevronRight,
  Zap,
  Bot,
  Shuffle,
  Mail,
  MessageSquare,
  Globe,
  Calendar,
  FileCode,
  User,
  CheckCircle,
  Send,
  Database,
  Code,
  Settings,
  History,
  Clock,
  GitBranch,
  Shield,
  ShieldOff,
  Sparkles,
  ChevronDown,
  HelpCircle,
  Activity,
  Loader2,
} from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import CustomNode from "@/components/flow/CustomNode";
import CustomEdge from "@/components/flow/CustomEdge";
import { NodePalette } from "@/components/flow/NodePalette";
import { apiRequest, fetchJson, queryClient, ApiError } from "@/lib/queryClient";
import { apiV1 } from "@/lib/api";
import { useToast } from "@/hooks/use-toast";
import { ErrorDisplay } from "@/components/error-display";
import { CustomNodeData, CustomEdgeData, BackendNodeDefinition, FlowNode, FlowEdge, FlowDefinition, type AvailableDataField } from "@/components/flow/types";
import { analyzeDataFlow, getEdgeDataPreview, wouldCreateCycle, getOutputSchema } from "@/components/flow/dataFlowAnalyzer";
import { validateFlow, FlowValidationResult as ExpressionValidationResult } from "@/components/flow/expressionValidator";
import { validateFlowComprehensive, FlowValidationResult } from "@/components/flow/flowValidator";
import { flattenCtxSchemaToAvailableData, validateCtxPath } from "@/components/flow/sandboxedExpressions";
import { SchemaNode } from "@/components/flow/types";
import { getAvailableDataForNode, SchemaSource, flattenDataNodes, mergeComputedFieldsIntoDataNodes } from "@/components/flow/dataFlowUtils";
import { useWebhookList } from "@/hooks/useBuilderData";
import { DynamicNodeConfigForm } from "@/components/flow/NodeConfigForms";
import { BuilderDataProviders } from "@/components/flow/BuilderDataContext";
import {
  buildBranchOutPortMap,
  deriveBranchOutputs,
  isBranchNodeType,
  normalizeBranchConfig,
} from "@/components/flow/branchUtils";
import { MiniWSDebugger } from "@/components/flow/MiniWSDebugger";
import { useFlowPreviewStream, type FlowPreviewEvent } from "@/hooks/useWebSocket";
import {
  getFlowSchedule,
  createFlowSchedule,
  updateFlowSchedule,
  deleteFlowSchedule,
} from "@/lib/scheduleApi";
import type { ScheduleConfig } from "@/components/flow/triggers/types";

// Node type definitions
interface NodeData {
  label: string;
  type: string;
  icon?: React.ComponentType<{ className?: string }>;
  iconKey?: string;
  description?: string;
  config?: Record<string, any>;
  formComponent?: string;
  outputs?: string[];
  handlesNonce?: number; // force handle remount after config changes
  inputs?: string[];
  portSchemas?: any;
  availableData?: any[];
  hints?: {
    description?: string;
    example_config?: Record<string, any>;
    use_cases?: string[];
    expression_examples?: Array<{
      expr: string;
      description: string;
    }>;
    tips?: string;
  };
  onConfig?: (nodeId: string) => void;
  onDelete?: (nodeId: string) => void;
  onAddElif?: (nodeId: string) => void;
  onRemoveElif?: (nodeId: string) => void;
}

// Custom node types for ReactFlow
const nodeTypes: NodeTypes = {
  custom: CustomNode,
};

// Custom edge types
const edgeTypes = {
  custom: CustomEdge,
};

// Icons mapping for node restoration
const iconMap: Record<string, any> = {
  Zap,
  Bot,
  Shuffle,
  Mail,
  MessageSquare,
  Globe,
  Calendar,
  FileCode,
  Play,
  User,
  CheckCircle,
  Send,
  Database,
  Code,
};

type NodePortDefinition = {
  name: string;
  description?: string;
  schema?: any;
  schema_preview?: string;
};

type PortSchemaMap = {
  in?: Record<string, NodePortDefinition>;
  out?: Record<string, NodePortDefinition>;
};

// Version status: draft -> armed -> published -> archived
// - draft: editable, can be armed for testing
// - armed: receiving events for preview, can be published or disarmed
// - published: frozen, active version of the flow
// - archived: frozen, previous published version
type VersionStatus = "draft" | "armed" | "published" | "archived";

type FlowVersion = {
  id: string;
  flow_id: string;
  version?: number;
  major?: number;
  minor?: number;
  label: string;
  status: VersionStatus;
  is_published: boolean;
  is_active: boolean;
  is_editable: boolean;
  preview_armed: boolean;
  preview_armed_at: string | null;
  notes?: string;
  created_at?: string;
  updated_at?: string;
};

// Legacy FlowData type (backend API format)
// Will be transformed to FlowDefinition when needed
type FlowData = {
  ok: boolean;
  flow: {
    id: string;
    name: string;
    description: string;
    status: string;
    created_at: string;
    updated_at: string;
    created_by?: { id: string; name: string };
    current_version_id?: string;
    published_version?: FlowVersion | null;
  };
  versions?: FlowVersion[];
  version?: FlowVersion;
  graph: { 
    nodes: SerializedNode[]; 
    edges: Edge[];
    config_schema?: unknown;
    config_values?: Record<string, unknown>;
    ctx_schema?: unknown;
  };
};

// Helper: Convert FlowData (backend format) to FlowDefinition (spec v2 format)
const convertFlowDataToFlowDefinition = (flowData: FlowData, version: FlowVersion | undefined): FlowDefinition => {
  const flow = flowData.flow;
  const graph = flowData.graph;
  
  // Convert nodes from backend format to FlowNode
  const flowNodes: FlowNode[] = (graph?.nodes || []).map((backendNode: any) => ({
    id: backendNode.id,
    kind: backendNode.kind || backendNode.type,
    name: backendNode.name || backendNode.label,
    position: {
      x: backendNode.x || backendNode.position?.x || 0,
      y: backendNode.y || backendNode.position?.y || 0,
    },
    config: backendNode.config || {},
  }));
  
  // Convert edges from backend format to FlowEdge
  const flowEdges: FlowEdge[] = (graph?.edges || []).map((backendEdge: any) => ({
    id: backendEdge.id,
    source: backendEdge.source,
    sourceHandle: backendEdge.source_port || backendEdge.sourceHandle || "out", // Default for legacy data
    target: backendEdge.target,
    targetHandle: backendEdge.target_port || backendEdge.targetHandle,
  }));
  
  // Map status: "active" -> "published", "inactive" -> "archived", etc.
  let status: FlowDefinition["status"] = "draft";
  if (version?.is_published) {
    status = version.is_active ? "published" : "archived";
  } else if (version?.preview_armed) {
    status = "armed";
  } else {
    status = "draft";
  }
  
  return {
    id: flow.id,
    name: flow.name,
    description: flow.description || undefined,
    version: version?.version || version?.major || 1,
    status,
    nodes: flowNodes,
    edges: flowEdges,
    config_schema: graph?.config_schema,
    config_values: graph?.config_values,
    metadata: {
      created_at: flow.created_at,
      updated_at: flow.updated_at,
      created_by: flow.created_by?.id,
    },
  };
};

// Helper: derive is_enabled from presence of published version
const flowHasPublishedVersion = (flow: FlowData["flow"], versions?: FlowVersion[]) => {
  if (flow.published_version) return true;
  if (versions) return versions.some(v => v.is_published);
  return false;
};

const formatApiErrorForToast = (error: unknown): { title: string; description: string } => {
  if (error instanceof ApiError) {
    const status = error.status;
    const base = error.message || `HTTP ${status}`;

    // Try to enrich with JSON body if possible
    try {
      const parsed = JSON.parse(error.body || "{}") as any;
      const details =
        (Array.isArray(parsed?.errors) ? parsed.errors.join(", ") : undefined) ||
        (typeof parsed?.detail === "string" ? parsed.detail : undefined) ||
        (typeof parsed?.message === "string" ? parsed.message : undefined) ||
        (typeof parsed?.error === "string" ? parsed.error : undefined);

      const fields =
        parsed?.fields && typeof parsed.fields === "object"
          ? Object.entries(parsed.fields)
              .map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(", ") : String(v)}`)
              .join(" | ")
          : undefined;

      const extra = [details, fields].filter(Boolean).join(" — ");
      return {
        title: `Request failed (${status})`,
        description: extra ? `${base} — ${extra}` : base,
      };
    } catch {
      return {
        title: `Request failed (${status})`,
        description: base,
      };
    }
  }

  if (error instanceof Error) {
    return { title: "Request failed", description: error.message };
  }

  return { title: "Request failed", description: "An unknown error occurred" };
};

// Helper: format version display with unique identifiers
const formatVersionDisplay = (flowName: string, version: FlowVersion, allVersions?: FlowVersion[]) => {
  // Build version number from available data
  const versionNum = version.version || (version.major !== undefined ? `${version.major}.${version.minor || 0}` : null);
  
  // Check if version number is duplicated among other versions
  const isDuplicate = versionNum && allVersions && allVersions.filter(v => 
    (v.version || (v.major !== undefined ? `${v.major}.${v.minor || 0}` : null)) === versionNum
  ).length > 1;
  
  // If no version number or duplicate, add date suffix for uniqueness
  if (!versionNum) {
    const shortId = version.id.substring(0, 6);
    return `${flowName} #${shortId}`;
  }
  
  if (isDuplicate && version.created_at) {
    const date = new Date(version.created_at);
    const dateStr = date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
    return `${flowName} v${versionNum} (${dateStr})`;
  }
  
  return `${flowName} v${versionNum}`;
};

// Helper: filter versions to show only relevant ones (not superseded archived)
const filterRelevantVersions = (versions: FlowVersion[]) => {
  // Always show: draft, armed, published (active), and the most recent archived
  const nonArchived = versions.filter(v => v.status !== "archived");
  const archived = versions.filter(v => v.status === "archived");
  
  // Keep only the most recent archived version (if any) as reference
  const recentArchived = archived.length > 0 
    ? [archived.sort((a, b) => 
        new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime()
      )[0]]
    : [];
  
  return [...nonArchived, ...recentArchived];
};

type JsonSchema = any;

function validateConfigValuesAgainstJsonSchema(schema: JsonSchema | null | undefined, values: any): string | null {
  if (!values || typeof values !== "object" || Array.isArray(values)) {
    return "config_values must be a JSON object.";
  }
  // Backend strict contract rule:
  // If config_values is provided (non-empty), config_schema must also be provided.
  if (!schema) {
    const keys = Object.keys(values || {});
    if (keys.length > 0) {
      return "config_values provided without config_schema";
    }
    return null;
  }

  const resolveType = (v: any) => (Array.isArray(v) ? "array" : v === null ? "null" : typeof v);

  const validate = (subSchema: any, subValue: any, path: string): string | null => {
    if (!subSchema || typeof subSchema !== "object") return null;

    const t = subSchema.type;
    const required: string[] = Array.isArray(subSchema.required) ? subSchema.required : [];

    // Object
    if (t === "object" || (t === undefined && subSchema.properties)) {
      if (!subValue || typeof subValue !== "object" || Array.isArray(subValue)) {
        return `${path} must be an object (got ${resolveType(subValue)}).`;
      }
      const props = subSchema.properties && typeof subSchema.properties === "object" ? subSchema.properties : {};

      for (const reqKey of required) {
        if (!(reqKey in subValue)) {
          return `${path}.${reqKey} is required.`;
        }
      }

      for (const [k, v] of Object.entries(subValue)) {
        if (props[k]) {
          const err = validate(props[k], v, `${path}.${k}`);
          if (err) return err;
        }
      }
      return null;
    }

    // Array
    if (t === "array") {
      if (!Array.isArray(subValue)) {
        return `${path} must be an array (got ${resolveType(subValue)}).`;
      }
      if (subSchema.items) {
        for (let i = 0; i < subValue.length; i++) {
          const err = validate(subSchema.items, subValue[i], `${path}[${i}]`);
          if (err) return err;
        }
      }
      return null;
    }

    // Primitive
    if (t === "string" && typeof subValue !== "string") return `${path} must be string (got ${resolveType(subValue)}).`;
    if (t === "number" && typeof subValue !== "number") return `${path} must be number (got ${resolveType(subValue)}).`;
    if (t === "boolean" && typeof subValue !== "boolean") return `${path} must be boolean (got ${resolveType(subValue)}).`;

    return null;
  };

  return validate(schema, values, "config");
}

function inferConfigSchemaFromValues(values: any): JsonSchema {
  const SEG_RE = /^[A-Za-z0-9_-]+$/;

  const infer = (v: any): any => {
    if (v === null || v === undefined) {
      return { type: "null" };
    }

    if (Array.isArray(v)) {
      if (v.length === 0) {
        return { type: "array", items: {} };
      }
      // Infer from first item; if heterogeneous, keep items as {}
      const first = v[0];
      const firstSchema = infer(first);
      const homogeneous = v.every((x) => {
        const t1 = Array.isArray(x) ? "array" : x === null ? "null" : typeof x;
        const t0 = Array.isArray(first) ? "array" : first === null ? "null" : typeof first;
        return t1 === t0;
      });
      return { type: "array", items: homogeneous ? firstSchema : {} };
    }

    if (typeof v === "object") {
      const properties: Record<string, any> = {};
      const required: string[] = [];
      for (const [kRaw, child] of Object.entries(v)) {
        const k = String(kRaw);
        // Only include keys that can be referenced as strict dot-segments (matches Normalize rules).
        if (!SEG_RE.test(k)) continue;
        properties[k] = infer(child);
        required.push(k);
      }
      return {
        type: "object",
        properties,
        required,
        additionalProperties: false,
      };
    }

    if (typeof v === "string") return { type: "string" };
    if (typeof v === "boolean") return { type: "boolean" };
    if (typeof v === "number") return { type: Number.isInteger(v) ? "integer" : "number" };

    return {};
  };

  // Root schema is always `config` object.
  const root = infer(values);
  if (root?.type !== "object") {
    return { type: "object", properties: {}, required: [], additionalProperties: false };
  }
  return root;
}

const FLOW_DEFINITIONS_PATH = apiV1("/flows/definitions/");
const FLOWS_PATH = apiV1("/flows/");

type NodeDefinition = {
  kind: string;
  title: string;
  icon: string;
  category: string;
  description?: string;
  default_config?: Record<string, any>;
  form_component?: string;
  ports?: {
    in?: Array<{
      name: string;
      description?: string;
      schema?: any;
      schema_preview?: string;
    }>;
    out?: Array<{
      name: string;
      description?: string;
      schema?: any;
      schema_preview?: string;
    }>;
  };
  stage?: string;
  enabled?: boolean;
};

type PaletteCategory = {
  id: string;
  label: string;
  items: Array<{
    kind: string;
    title: string;
    icon: string;
    description?: string;
  }>;
};

type NodeDefinitionsResponse = {
  node_definitions: Record<string, NodeDefinition>;
  palette: PaletteCategory[];
};

export type SerializableNodeData = Pick<
  NodeData,
  "label" | "type" | "description" | "config" | "outputs" | "inputs" | "formComponent" | "portSchemas"
> & {
  iconKey?: string | null;
};

export type SerializedNode = Omit<Node<NodeData>, "data"> & {
  data: SerializableNodeData;
};

export const getIconKey = (icon?: React.ComponentType<any>) => {
  if (!icon) return null;
  for (const [key, value] of Object.entries(iconMap)) {
    if (value === icon) return key;
  }
  return null;
};

const buildPortSchemaMap = (definition?: NodeDefinition): PortSchemaMap | undefined => {
  if (!definition?.ports) return undefined;

  const schemaMap: PortSchemaMap = {};

  if (definition.ports.in && definition.ports.in.length > 0) {
    schemaMap.in = definition.ports.in.reduce<Record<string, NodePortDefinition>>(
      (acc, port) => {
        acc[port.name] = port;
        return acc;
      },
      {}
    );
  }

  if (definition.ports.out && definition.ports.out.length > 0) {
    schemaMap.out = definition.ports.out.reduce<Record<string, NodePortDefinition>>(
      (acc, port) => {
        acc[port.name] = port;
        return acc;
      },
      {}
    );
  }

  if (!schemaMap.in && !schemaMap.out) {
    return undefined;
  }

  return schemaMap;
};

type BranchAwareData = Pick<NodeData, "type" | "config" | "outputs" | "portSchemas">;

const applyBranchMetadataToData = <T extends BranchAwareData>(
  data: T,
  definition?: NodeDefinition
): T => {
  if (!isBranchNodeType(data.type)) {
    return data;
  }

  const normalizedConfig = normalizeBranchConfig(data.config);
  const outputs = deriveBranchOutputs(normalizedConfig);
  const handlesNonce = Date.now();
  const definitionSchemas = buildPortSchemaMap(definition);
  const template =
    (definitionSchemas?.out && Object.values(definitionSchemas.out)[0]) ||
    (data.portSchemas?.out && Object.values(data.portSchemas.out)[0]);

  const portSchemas: PortSchemaMap = {
    ...(definitionSchemas?.in || data.portSchemas?.in
      ? { in: definitionSchemas?.in ?? data.portSchemas?.in }
      : {}),
    out: buildBranchOutPortMap(normalizedConfig, template),
  };

  return {
    ...data,
    config: normalizedConfig,
    outputs,
    handlesNonce,
    portSchemas,
  } as T;
};

export const mergeNodeDataWithDefinitions = (
  data: SerializableNodeData,
  nodeDefinitions?: Record<string, NodeDefinition>
): SerializableNodeData => {
  const definition = nodeDefinitions?.[data.type];

  // For branch nodes, outputs are derived dynamically from config, not from definition
  // So we need to apply branch metadata first, then merge other properties
  const isBranch = isBranchNodeType(data.type);
  
  // If it's a branch node, apply branch metadata first to get correct outputs
  const dataWithBranch = isBranch 
    ? applyBranchMetadataToData(data, definition)
    : data;

  // For non-branch nodes, derive outputs/inputs from definition if not present
  const derivedOutputs = isBranch
    ? dataWithBranch.outputs // Branch outputs come from applyBranchMetadataToData
    : (data.outputs ?? definition?.ports?.out?.map((port) => port.name) ?? []);
  const derivedInputs =
    data.inputs ?? definition?.ports?.in?.map((port) => port.name) ?? [];
  const derivedPortSchemas = isBranch
    ? dataWithBranch.portSchemas // Branch portSchemas come from applyBranchMetadataToData
    : (data.portSchemas ?? buildPortSchemaMap(definition));
  const derivedFormComponent = data.formComponent ?? definition?.form_component;

  const mergedData: SerializableNodeData = {
    ...dataWithBranch,
    outputs: derivedOutputs,
    inputs: derivedInputs,
    portSchemas: derivedPortSchemas,
    formComponent: derivedFormComponent,
  };

  // For branch nodes, we already applied metadata, so just return
  // For non-branch nodes, no additional processing needed
  return mergedData;
};

export const normalizeNodesForSave = (nodes: Node<NodeData>[]): any[] => {
  const canonicalizeKind = (kind: string) => {
    // Canonical runtime kinds (spec). Backend/runtime is authority.
    // Accept legacy UI kinds but always serialize canonical ones.
    switch (kind) {
      case "normalize":
        return "logic_normalize";
      case "branch":
        return "logic_branch";
      case "condition":
        return "logic_condition";
      case "while":
        return "logic_while";
      default:
        return kind;
    }
  };

  return nodes.map((node) => {
    return {
      id: node.id,
      kind: canonicalizeKind(node.data.type),
      name: node.data.label,
      x: Math.round(node.position.x),
      y: Math.round(node.position.y),
      config: node.data.config || {},
    };
  });
};

const buildGraphPayloadForBackend = (
  nodes: Node<NodeData>[],
  edges: Edge[],
  flowConfigSchema: unknown,
  flowConfigValues: Record<string, unknown>
) => {
  const normalizedNodes = normalizeNodesForSave(nodes);

  // v2 spec: sourceHandle is mandatory
  const normalizedEdges = edges.map((edge) => {
    if (!edge.sourceHandle) {
      throw new Error(
        `Edge ${edge.id} is missing required sourceHandle. All edges must specify which output port they connect from.`
      );
    }

    // Handles are output names; use directly
    const sourcePort = edge.sourceHandle;

    return {
      id: edge.id,
      source: edge.source,
      target: edge.target,
      source_port: sourcePort,
      target_port: edge.targetHandle || "in",
    };
  });

  return {
    graph: {
      nodes: normalizedNodes,
      edges: normalizedEdges,
      config_schema: flowConfigSchema,
      config_values: flowConfigValues,
    },
  };
};

function FlowCanvas({ flowId }: { flowId?: string }) {
  const [, navigate] = useLocation();
  const reactFlowInstance = useReactFlow();
  const { toast } = useToast();
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  
  // Fetch webhooks for schema expansion in data visualizer
  const webhooksQuery = useWebhookList();
  const [selectedNode, setSelectedNode] = useState<Node<NodeData> | null>(null);
  const [isConfigOpen, setIsConfigOpen] = useState(false);
  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false);
  const [isDeleteVersionDialogOpen, setIsDeleteVersionDialogOpen] = useState(false);
  const [versionToDelete, setVersionToDelete] = useState<FlowVersion | null>(null);
  const [isPropertiesOpen, setIsPropertiesOpen] = useState(false);
  const [flowName, setFlowName] = useState("New Workflow");
  const [flowDescription, setFlowDescription] = useState("");
  const [flowStatus, setFlowStatus] = useState<string>("draft");
  const [flowIsEnabled, setFlowIsEnabled] = useState<boolean>(false);
  const [flowConfigSchemaText, setFlowConfigSchemaText] = useState<string>("");
  const [flowConfigSchemaError, setFlowConfigSchemaError] = useState<string | null>(null);
  const [flowConfigSchema, setFlowConfigSchema] = useState<unknown>(null);

  const [flowConfigValuesText, setFlowConfigValuesText] = useState<string>("{}");
  const [flowConfigValuesError, setFlowConfigValuesError] = useState<string | null>(null);
  const [flowConfigValues, setFlowConfigValues] = useState<Record<string, unknown>>({});

  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);

  // ctx_schema (compiled by backend from Normalize mappings) for ctx.* autocomplete + warnings
  const [ctxSchema, setCtxSchema] = useState<unknown>(null);
  const ctxSchemaFields = useMemo(() => flattenCtxSchemaToAvailableData(ctxSchema), [ctxSchema]);

  // Fallback ctx fields derived from current Normalize mappings (UX only).
  // This is NOT authoritative; backend ctx_schema (if present) always wins.
  const derivedCtxFields = useMemo((): AvailableDataField[] => {
    const out: AvailableDataField[] = [];
    const seen = new Set<string>();

    const add = (key: string, type: string, description?: string) => {
      if (seen.has(key)) return;
      seen.add(key);
      out.push({ key, type, source: "normalize (local)", description });
    };

    const normalizeNodes = (nodes as Node<CustomNodeData>[]).filter(
      (n) => n.data.type === "logic_normalize" || n.data.type === "normalize"
    );
    for (const n of normalizeNodes) {
      const cfg = n.data.config || {};
      const mappings = Array.isArray((cfg as any).mappings) ? ((cfg as any).mappings as any[]) : [];
      for (const m of mappings) {
        const ctxPath = String(m?.ctx_path || "").trim();
        if (!ctxPath) continue;
        const check = validateCtxPath(ctxPath);
        if (!check.ok) continue;

        // Add parents as objects for nicer pickers (ctx.a, ctx.a.b, ...)
        const parts = ctxPath.split(".");
        for (let i = 2; i < parts.length; i++) {
          add(parts.slice(0, i).join("."), "object");
        }

        const t = String(m?.type || "unknown");
        add(ctxPath, t, n.data.label ? `Defined by ${n.data.label}` : "Defined by Normalize");
      }
    }

    return out;
  }, [nodes]);

  // IMPORTANT UX: backend ctx_schema is authoritative but not live-updated while editing mappings.
  // If there are unsaved changes, prefer the derived fields from current Normalize mappings
  // to avoid showing stale ctx paths.
  const ctxFieldsForUI: AvailableDataField[] =
    hasUnsavedChanges || ctxSchemaFields.length === 0
      ? derivedCtxFields
      : (ctxSchemaFields as AvailableDataField[]);

  const configFieldsForUI = useMemo((): AvailableDataField[] => {
    const CONFIG_SEGMENT_RE = /^[A-Za-z0-9_-]+$/;
    const out: AvailableDataField[] = [];
    const visit = (obj: any, pfx: string) => {
      if (!obj || typeof obj !== "object" || Array.isArray(obj)) return;
      for (const [kRaw, v] of Object.entries(obj)) {
        const k = String(kRaw);
        if (!CONFIG_SEGMENT_RE.test(k)) continue;
        const key = `${pfx}.${k}`;
        let t: string = "unknown";
        if (v === null || v === undefined) t = "unknown";
        else if (Array.isArray(v)) t = "array";
        else if (typeof v === "object") t = "object";
        else if (typeof v === "string") t = "string";
        else if (typeof v === "number") t = Number.isInteger(v) ? "integer" : "number";
        else if (typeof v === "boolean") t = "boolean";

        out.push({
          key,
          type: t,
          description: "Flow config value",
          source: "config",
        });

        if (v && typeof v === "object" && !Array.isArray(v)) {
          visit(v, key);
        }
      }
    };
    visit(flowConfigValues || {}, "config");
    return out;
  }, [flowConfigValues]);

  // --------------------------------------------------------------------------
  // Scope resolver (input/ctx visibility) - spec-aligned
  // --------------------------------------------------------------------------

  const isTriggerNodeType = useCallback((type?: string) => {
    if (!type) return false;
    return (
      type.startsWith("trigger_") ||
      type === "webhook" ||
      type === "event" ||
      type === "scheduled" ||
      type === "trigger_webhook" ||
      type === "trigger_event" ||
      type === "trigger_scheduled"
    );
  }, []);

  const isNormalizeNodeType = useCallback((type?: string) => type === "logic_normalize" || type === "normalize", []);

  const isControlNodeType = useCallback((type?: string) => {
    if (!type) return false;
    return type === "logic_branch" || type === "logic_condition" || type === "logic_while" || type === "branch" || type === "condition" || type === "while";
  }, []);

  type NodeScope = {
    canSeeInput: boolean;
    canSeeCtx: boolean;
    schemaAvailable: boolean;
    hasNormalizeUpstream: boolean;
    isControl: boolean;
  };

  const getScopeMap = useCallback(
    (currentNodes: Array<Node<CustomNodeData>>, currentEdges: Edge[]): Map<string, NodeScope> => {
      const nodeById = new Map(currentNodes.map((n) => [n.id, n]));
      const inDegree = new Map<string, number>();
      const preds = new Map<string, string[]>();
      const adjacency = new Map<string, string[]>();

      for (const n of currentNodes) {
        inDegree.set(n.id, 0);
        preds.set(n.id, []);
        adjacency.set(n.id, []);
      }
      for (const e of currentEdges) {
        if (!inDegree.has(e.source) || !inDegree.has(e.target)) continue;
        inDegree.set(e.target, (inDegree.get(e.target) || 0) + 1);
        preds.get(e.target)!.push(e.source);
        adjacency.get(e.source)!.push(e.target);
      }

      // Reachability: traverse graph starting from triggers
      const triggerIds = currentNodes.filter((n) => isTriggerNodeType(n.data.type)).map((n) => n.id);
      const reachable = new Set<string>();
      const bfs: string[] = [...triggerIds];
      for (const t of triggerIds) reachable.add(t);
      while (bfs.length > 0) {
        const id = bfs.shift()!;
        for (const nxt of adjacency.get(id) || []) {
          if (reachable.has(nxt)) continue;
          reachable.add(nxt);
          bfs.push(nxt);
        }
      }

      // Kahn topo order (cycles already prevented, but we keep it safe)
      const queue: string[] = [];
      inDegree.forEach((deg, id) => {
        if (deg === 0) queue.push(id);
      });
      const order: string[] = [];
      while (queue.length > 0) {
        const id = queue.shift()!;
        order.push(id);
        for (const nxt of adjacency.get(id) || []) {
          inDegree.set(nxt, (inDegree.get(nxt) || 0) - 1);
          if (inDegree.get(nxt) === 0) queue.push(nxt);
        }
      }

      // DP (spec A): ctx exists if there's a Normalize upstream from the Trigger.
      // i.e., if any trigger->...->node path includes logic_normalize before node.
      const hasNormalizeUpstream = new Map<string, boolean>();
      for (const id of order) {
        const node = nodeById.get(id);
        if (!node) continue;
        if (!reachable.has(id)) {
          hasNormalizeUpstream.set(id, false);
          continue;
        }

        const isTrigger = isTriggerNodeType(node.data.type);
        const isNormalize = isNormalizeNodeType(node.data.type);
        if (isTrigger) {
          hasNormalizeUpstream.set(id, false);
          continue;
        }
        if (isNormalize) {
          // Normalize itself defines ctx for downstream, but ctx does not exist inside Normalize.
          hasNormalizeUpstream.set(id, true);
          continue;
        }

        const p = (preds.get(id) || []).filter((pid) => reachable.has(pid));
        if (p.length === 0) {
          hasNormalizeUpstream.set(id, false);
        } else {
          hasNormalizeUpstream.set(id, p.some((pid) => hasNormalizeUpstream.get(pid) === true));
        }
      }

      const schemaAvailable = ctxSchemaFields.length > 0;

      const scopeMap = new Map<string, NodeScope>();
      for (const n of currentNodes) {
        const type = n.data.type;
        const isTrigger = isTriggerNodeType(type);
        const isNormalize = isNormalizeNodeType(type);
        const isControl = isControlNodeType(type);
        const hasCtx = !isNormalize && hasNormalizeUpstream.get(n.id) === true;
        scopeMap.set(n.id, {
          canSeeInput: Boolean(isNormalize),
          canSeeCtx: Boolean(!isTrigger && !isNormalize && hasCtx),
          schemaAvailable: Boolean(!isTrigger && !isNormalize && hasCtx && schemaAvailable),
          hasNormalizeUpstream: hasCtx,
          isControl,
        });
      }
      return scopeMap;
    },
    [ctxSchemaFields.length, isControlNodeType, isNormalizeNodeType, isTriggerNodeType, ctxFieldsForUI.length]
  );

  const getVisibleFieldsForNode = useCallback(
    (nodeId: string, rawFields: Array<{ key: string; type?: string }> = []) => {
      const scopeMap = getScopeMap(nodes as Node<CustomNodeData>[], edges);
      const scope = scopeMap.get(nodeId);
      if (!scope) return { scope: undefined, fields: [] as any[] };

      if (scope.canSeeInput) {
        const filtered = (rawFields || []).filter((f: any) => {
          const k = String(f?.key || "");
          return (
            k === "input.body" ||
            k.startsWith("input.body.") ||
            k.startsWith("nodes.") ||
            k === "config" ||
            k.startsWith("config.")
          );
        });
        return { scope, fields: filtered };
      }

      if (scope.canSeeCtx) {
        // Spec: downstream nodes see ctx.* and may also reference config.* (global, read-only).
        const merged = [...ctxFieldsForUI, ...configFieldsForUI];
        return { scope, fields: merged };
      }

      return { scope, fields: [] as any[] };
    },
    [configFieldsForUI, ctxSchemaFields, edges, getScopeMap, nodes, ctxFieldsForUI]
  );
  const [flowVersion, setFlowVersion] = useState<FlowVersion | null>(null);
  const [allVersions, setAllVersions] = useState<FlowVersion[]>([]);
  const [isVersionHistoryOpen, setIsVersionHistoryOpen] = useState(false);
  const [isExecutionHistoryOpen, setIsExecutionHistoryOpen] = useState(false);
  const [executionHistoryPage, setExecutionHistoryPage] = useState(1);
  const [executionHistoryModeFilter, setExecutionHistoryModeFilter] = useState<"all" | "production" | "testing" | "preview">("all");
  const [selectedExecution, setSelectedExecution] = useState<Execution | null>(null);
  const [isPublishConfirmOpen, setIsPublishConfirmOpen] = useState(false);
  const [isNewVersionModalOpen, setIsNewVersionModalOpen] = useState(false);
  const [previewRunId, setPreviewRunId] = useState<string | null>(null);
  const [isPreviewArmed, setIsPreviewArmed] = useState(false);
  const [isEventMonitorOpen, setIsEventMonitorOpen] = useState(false);
  const [latestWsEvent, setLatestWsEvent] = useState<{ eventType: string; payload: any } | null>(null);
  const [isPreviewPayloadDialogOpen, setIsPreviewPayloadDialogOpen] = useState(false);
  const [previewPayload, setPreviewPayload] = useState("");
  const [previewPayloadError, setPreviewPayloadError] = useState<string | null>(null);

  // Locked/read-only flows: allow viewing but disallow any graph mutations.
  // Backend defines editability per version via `is_editable`.
  const canEditFlow = flowVersion ? Boolean(flowVersion.is_editable) : true;

  // Sync isPreviewArmed with flowVersion when it changes
  useEffect(() => {
    setIsPreviewArmed(flowVersion?.preview_armed || false);
  }, [flowVersion?.preview_armed]);
  
  const nodeIdCounter = useRef(1);
  const draggedNodeInfo = useRef<{
    type: string;
    label: string;
    icon: any;
    outputs?: string[];
    inputs?: string[];
    portSchemas?: any;
    defaultConfig?: Record<string, any>;
    formComponent?: string;
  } | null>(null);
  const nodeDefinitionsRef = useRef<Record<string, NodeDefinition> | undefined>();
  const getNodeDefinition = (nodeType: string) => nodeDefinitionsRef.current?.[nodeType];
  const flowDataLoadedRef = useRef(false);
  const [graphReloadNonce, setGraphReloadNonce] = useState(0);
  const fitViewAppliedRef = useRef<string | null>(null);
  
  // Data flow cache - only recalculated on explicit graph mutations
  const dataFlowCacheRef = useRef<Map<string, any[]>>(new Map());
  const [graphVersion, setGraphVersion] = useState(0); // Incremented to trigger recalculation
  
  // Trigger data flow recalculation - call after any graph mutation
  // Uses queueMicrotask to ensure state has flushed before recalculation
  const triggerDataFlowRecalc = useCallback(() => {
    queueMicrotask(() => {
      setGraphVersion(v => v + 1);
    });
  }, []);
  
  // Refs to access latest nodes/edges in the data flow effect without depending on them
  // Update synchronously in component body to ensure refs are current before effects run
  const nodesRef = useRef(nodes);
  const edgesRef = useRef(edges);
  nodesRef.current = nodes;
  edgesRef.current = edges;

  const DEFAULT_CANVAS_ZOOM = 0.75;
  const applyDefaultViewport = useCallback(() => {
  if (!reactFlowInstance) return;
    const current = nodesRef.current as any[];
    if (!current || current.length === 0) return;
    // Wait for ReactFlow to commit nodes to its internal store before fitting.
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        try {
        reactFlowInstance.fitView({
          padding: 0.2,
          minZoom: DEFAULT_CANVAS_ZOOM,
          maxZoom: DEFAULT_CANVAS_ZOOM,
          duration: 0,
        });
        } catch {
          // ignore
        }
      });
    });
  }, [reactFlowInstance]);

  // Ensure initial fit once React Flow instance is ready and nodes are present
  useEffect(() => {
    if (!reactFlowInstance) return;
    if (!nodes || nodes.length === 0) return;
    const key = flowId ? `flow-${flowId}` : "flow-default";
    if (fitViewAppliedRef.current === key) return;
    applyDefaultViewport();
    fitViewAppliedRef.current = key;
  }, [reactFlowInstance, nodes, flowId, applyDefaultViewport]);

  // CRM schema cache (slug -> resource details payload)
  const crmDetailsCacheRef = useRef<Map<string, any>>(new Map());
  const crmFetchInFlightRef = useRef<Set<string>>(new Set());
  const crmAppliedKeyRef = useRef<Map<string, string>>(new Map()); // nodeId -> `${slug}|${operation}`
  const httpAppliedSchemaHashRef = useRef<Map<string, string>>(new Map()); // nodeId -> JSON.stringify(output_schema)

  // Hydrate operation-specific output schemas for tool_crm_crud into node.data.portSchemas.out
  // This is UI-only metadata (not saved to backend) used for better downstream availableData.
  useEffect(() => {
    const currentNodes = nodesRef.current as any[];
    const crmNodes = currentNodes.filter((n) => n?.data?.type === "tool_crm_crud");
    if (crmNodes.length === 0) return;

    const wantedSlugs = Array.from(
      new Set(
        crmNodes
          .map((n) => (n?.data?.config?.resource_slug ?? "").toString().trim())
          .filter(Boolean)
      )
    );

    const parseJsonMaybe = (v: any) => {
      if (typeof v === "string") {
        try {
          return JSON.parse(v);
        } catch {
          return v;
        }
      }
      return v;
    };

    // Kick off fetches for missing slugs
    wantedSlugs.forEach((slug) => {
      if (crmDetailsCacheRef.current.has(slug)) return;
      if (crmFetchInFlightRef.current.has(slug)) return;
      crmFetchInFlightRef.current.add(slug);

      fetchJson<any>(apiV1(`/flows/crm/${slug}/`))
        .then((data) => {
          // Backend may return { model: {...} } or { resource: {...} }
          const payload = data?.model ?? data?.resource ?? data?.data?.model ?? data?.data?.resource ?? data;
          const normalized = {
            ...payload,
            operations:
              payload?.operations ??
              payload?.model?.operations ??
              data?.operations ??
              data?.model?.operations ??
              data?.resource?.operations ??
              {},
          };
          crmDetailsCacheRef.current.set(slug, normalized);
        })
        .catch((err) => {
          console.warn("[CRM] Failed to load resource details:", slug, err);
        })
        .finally(() => {
          crmFetchInFlightRef.current.delete(slug);
          // Apply schemas after fetch completes (success or not)
          const nextNodes = nodesRef.current as any[];
          let changed = false;

          const updated = nextNodes.map((n) => {
            if (n?.data?.type !== "tool_crm_crud") return n;
            const slug = (n?.data?.config?.resource_slug ?? "").toString().trim();
            const op = (n?.data?.config?.operation ?? "").toString().trim();
            if (!slug || !op) return n;

            const appliedKey = `${slug}|${op}`;
            if (crmAppliedKeyRef.current.get(n.id) === appliedKey) {
              return n;
            }

            const details = crmDetailsCacheRef.current.get(slug);
            const opSchema = details?.operations?.[op];
            const outputSchema = parseJsonMaybe(opSchema?.output_schema);
            if (!outputSchema || typeof outputSchema !== "object") {
              return n;
            }

            const prevPortSchemas = (n.data as any).portSchemas;
            const nextPortSchemas = {
              ...(prevPortSchemas?.in ? { in: prevPortSchemas.in } : {}),
              out: {
                ...(prevPortSchemas?.out ?? {}),
                out: { name: "out", schema: outputSchema },
              },
            };

            changed = true;
            crmAppliedKeyRef.current.set(n.id, appliedKey);
            return {
              ...n,
              data: {
                ...n.data,
                portSchemas: nextPortSchemas,
              },
            };
          });

          if (changed) {
            setNodes(updated as any);
            // Ensure downstream availableData recalculates (analyzer depends on graphVersion)
            triggerDataFlowRecalc();
          }
        });
    });

    // Apply schemas for already-cached slugs synchronously
    {
      const nextNodes = nodesRef.current as any[];
      let changed = false;
      const updated = nextNodes.map((n) => {
        if (n?.data?.type !== "tool_crm_crud") return n;
        const slug = (n?.data?.config?.resource_slug ?? "").toString().trim();
        const op = (n?.data?.config?.operation ?? "").toString().trim();
        if (!slug || !op) return n;

        const appliedKey = `${slug}|${op}`;
        if (crmAppliedKeyRef.current.get(n.id) === appliedKey) {
          return n;
        }

        const details = crmDetailsCacheRef.current.get(slug);
        if (!details) return n;
        const opSchema = details?.operations?.[op];
        const outputSchema = parseJsonMaybe(opSchema?.output_schema);
        if (!outputSchema || typeof outputSchema !== "object") return n;

        const prevPortSchemas = (n.data as any).portSchemas;
        const nextPortSchemas = {
          ...(prevPortSchemas?.in ? { in: prevPortSchemas.in } : {}),
          out: {
            ...(prevPortSchemas?.out ?? {}),
            out: { name: "out", schema: outputSchema },
          },
        };

        changed = true;
        crmAppliedKeyRef.current.set(n.id, appliedKey);
        return {
          ...n,
          data: {
            ...n.data,
            portSchemas: nextPortSchemas,
          },
        };
      });

      if (changed) {
        setNodes(updated as any);
        triggerDataFlowRecalc();
      }
    }
  }, [nodes, setNodes, triggerDataFlowRecalc]);

  // Hydrate HTTP node output_schema (stored in node.config.output_schema) into node.data.portSchemas.out.
  // IMPORTANT: config.output_schema describes the RESPONSE BODY, but the runtime output exposes it under:
  // nodes.<id>.output.response_data.*
  // So for UI/autocomplete we wrap it here as { response_data: <output_schema> }.
  useEffect(() => {
    const currentNodes = nodesRef.current as any[];
    const httpNodes = currentNodes.filter((n) => {
      const fc = String(n?.data?.formComponent ?? "");
      const t = String(n?.data?.type ?? "");
      return fc === "form_http_request" || fc === "http" || t.includes("http");
    });
    if (httpNodes.length === 0) return;

    const parseJsonMaybe = (v: any) => {
      if (typeof v === "string") {
        try {
          return JSON.parse(v);
        } catch {
          return v;
        }
      }
      return v;
    };

    const safeStringify = (v: any) => {
      try {
        return JSON.stringify(v);
      } catch {
        return String(v ?? "");
      }
    };

    let changed = false;
    const updated = currentNodes.map((n) => {
      const fc = String(n?.data?.formComponent ?? "");
      const t = String(n?.data?.type ?? "");
      const isHttp = fc === "form_http_request" || fc === "http" || t.includes("http");
      if (!isHttp) return n;

      const raw = n?.data?.config?.output_schema;
      const bodySchema = parseJsonMaybe(raw);
      const hasSchema = bodySchema && typeof bodySchema === "object";
      const schemaHash = hasSchema ? safeStringify(bodySchema) : "";
      const prevHash = httpAppliedSchemaHashRef.current.get(n.id) ?? "";

      const prevPortSchemas = (n.data as any).portSchemas;
      const nextPortSchemas = {
        ...(prevPortSchemas?.in ? { in: prevPortSchemas.in } : {}),
        out: {
          ...(prevPortSchemas?.out ?? {}),
        },
      } as any;

      const existingOutNames = Object.keys((prevPortSchemas?.out ?? {}) as any).filter(Boolean);
      const defOutNames = (getNodeDefinition(n.data.type)?.ports?.out ?? []).map((p: any) => String(p?.name ?? "")).filter(Boolean);
      const outNames = (existingOutNames.length ? existingOutNames : defOutNames.length ? defOutNames : ["out"]) as string[];

      const hasInjectedSchemaOnAllPorts = () => {
        if (!hasSchema) return false;
        for (const name of outNames) {
          const port = (prevPortSchemas?.out ?? {})?.[name];
          const schema = port?.schema;
          if (!(schema && typeof schema === "object" && (schema as any).kind === "object" && (schema as any).properties?.response_data)) {
            return false;
          }
        }
        return true;
      };

      // Skip work only if schema hasn't changed AND the injected schema is already present on all out ports.
      if (schemaHash === prevHash && hasInjectedSchemaOnAllPorts()) {
        return n;
      }

      if (hasSchema) {
        // Expose under response_data.* in the UI dataflow model.
        // IMPORTANT: attach to the node's actual output handle name(s) (from definition/instance),
        // not just "out", so downstream schema extraction matches edge.sourceHandle.
        const wrapped = {
          kind: "object",
          properties: {
            response_data: bodySchema,
          },
        };

        outNames.forEach((name) => {
          nextPortSchemas.out[name] = { name, schema: wrapped };
        });
      } else {
        // If schema cleared, remove our injected port if present.
        // We don't know which out name was used, so remove any ports that look like our injected schema.
        Object.keys(nextPortSchemas.out || {}).forEach((k) => {
          const port = nextPortSchemas.out?.[k];
          const schema = port?.schema;
          if (schema && typeof schema === "object" && (schema as any).kind === "object" && (schema as any).properties?.response_data) {
            delete nextPortSchemas.out[k];
          }
        });
      }

      changed = true;
      httpAppliedSchemaHashRef.current.set(n.id, schemaHash);
      return {
        ...n,
        data: {
          ...n.data,
          portSchemas: nextPortSchemas,
        },
      };
    });

    if (changed) {
      setNodes(updated as any);
      triggerDataFlowRecalc();
    }
  }, [nodes, setNodes, triggerDataFlowRecalc]);

  // WebSocket hook for flow preview streaming
  // Keep WebSocket connected when flowId exists, not just when runId exists
  // This ensures connection is ready when preview starts
  const flowPreviewStream = useFlowPreviewStream({
    flowId: flowId || null,
    runId: previewRunId,
    enabled: Boolean(flowId),
    onNodeStarted: (event: FlowPreviewEvent) => {
      setLatestWsEvent({ eventType: "node_started", payload: event });
    },
    onNodeFinished: (event: FlowPreviewEvent) => {
      setLatestWsEvent({ eventType: "node_finished", payload: event });
    },
    onNodeError: (event: FlowPreviewEvent) => {
      setLatestWsEvent({ eventType: "node_error", payload: event });
    },
    onCompleted: (event: FlowPreviewEvent) => {
      setLatestWsEvent({ eventType: "completed", payload: event });
    },
    onEvent: (eventType: string, payload: FlowPreviewEvent) => {
      // Capture all WebSocket events for the debug panel
      setLatestWsEvent({ eventType, payload });
    },
  });

  // Node action handlers (defined before useEffect to avoid dependency issues)
  const handleNodeConfig = useCallback((nodeId: string) => {
    setNodes((nds) => {
      const node = nds.find(n => n.id === nodeId);
      if (node) {
        setSelectedNode(node as Node<NodeData>);
        setIsConfigOpen(true);
      }
      return nds;
    });
  }, [setNodes]);

  const handleNodeDelete = useCallback((nodeId: string) => {
    // Don't allow deletion if flow is locked/read-only
    if (!canEditFlow) return;
    setNodes((nds) => nds.filter((node) => node.id !== nodeId));
    setEdges((eds) =>
      eds.filter((edge) => edge.source !== nodeId && edge.target !== nodeId)
    );
    if (flowDataLoadedRef.current) {
      setHasUnsavedChanges(true);
      triggerDataFlowRecalc();
    }
  }, [setNodes, setEdges, triggerDataFlowRecalc, canEditFlow]);

  const handleEdgeDelete = useCallback((edgeId: string) => {
    // Don't allow deletion if flow is locked/read-only
    if (!canEditFlow) return;
    setEdges((eds) => eds.filter((edge) => edge.id !== edgeId));
    if (flowDataLoadedRef.current) {
      setHasUnsavedChanges(true);
      triggerDataFlowRecalc();
    }
  }, [setEdges, triggerDataFlowRecalc, canEditFlow]);

  // Keep existing edges in sync with editability.
  // (Edges can be restored/created before flowVersion is fully loaded; without this,
  // delete buttons can remain disabled even after the version becomes editable.)
  useEffect(() => {
    setEdges((eds) =>
      eds.map((e) => ({
        ...e,
        data: {
          ...(e.data as any),
          onDelete: canEditFlow ? handleEdgeDelete : undefined,
          readOnly: !canEditFlow,
        } as any,
      }))
    );
  }, [canEditFlow, handleEdgeDelete, setEdges]);

  const pruneEdgesForNode = useCallback(
    (nodeId: string, allowedHandles: string[], previousHandles?: string[]) => {
      setEdges((eds) => {
        return eds.filter((edge) => {
          if (edge.source !== nodeId) return true;
          if (!edge.sourceHandle) return true;
          return allowedHandles.includes(edge.sourceHandle);
        });
      });
    },
    [setEdges, nodes]
  );

  const handleConfigDone = useCallback(() => {
    if (!selectedNode) {
      setIsConfigOpen(false);
      return;
    }

    let updatedNode: Node<NodeData> | undefined;
    setNodes((nds) =>
      nds.map((node) => {
        if (node.id !== selectedNode.id) return node;

        const def = getNodeDefinition(node.data.type);
        const data = isBranchNodeType(node.data.type)
          ? applyBranchMetadataToData(node.data, def)
          : node.data;

        updatedNode = { ...node, data };
        return updatedNode;
      })
    );

    if (updatedNode) {
      setSelectedNode(updatedNode);
      if (flowDataLoadedRef.current && canEditFlow) {
        setHasUnsavedChanges(true);
        triggerDataFlowRecalc();
      }
    }

    setIsConfigOpen(false);
  }, [
    selectedNode,
    setNodes,
    getNodeDefinition,
    setSelectedNode,
    triggerDataFlowRecalc,
    canEditFlow,
  ]);

  const handleAddElif = useCallback((nodeId: string) => {
    if (!canEditFlow) return;
    let nextHandles: string[] | undefined;
    let updatedData: NodeData | undefined;

    setNodes((nds) =>
      nds.map((node) => {
        if (node.id !== nodeId || !isBranchNodeType(node.data.type)) return node;

        const branchConfig = normalizeBranchConfig(node.data.config);
        const nextRules = [
          ...branchConfig.rules,
          { id: `rule_${branchConfig.rules.length + 1}_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`, name: `rule_${branchConfig.rules.length + 1}`, expr: "True" },
        ];
        const dataWithBranch = applyBranchMetadataToData(
          { ...node.data, config: { ...branchConfig, rules: nextRules } },
          getNodeDefinition(node.data.type)
        );
        nextHandles = dataWithBranch.outputs;
        updatedData = dataWithBranch;
        return { ...node, data: dataWithBranch };
      })
    );

    if (nextHandles) {
      pruneEdgesForNode(nodeId, nextHandles);
    }

    if (updatedData) {
      setSelectedNode((prev) =>
        prev && prev.id === nodeId ? { ...prev, data: updatedData! } : prev
      );
      if (flowDataLoadedRef.current && canEditFlow) {
        setHasUnsavedChanges(true);
        triggerDataFlowRecalc();
      }
    }
  }, [getNodeDefinition, pruneEdgesForNode, setNodes, setSelectedNode, triggerDataFlowRecalc, canEditFlow]);

  const handleRemoveElif = useCallback((nodeId: string) => {
    if (!canEditFlow) return;
    let nextHandles: string[] | undefined;
    let updatedData: NodeData | undefined;

    setNodes((nds) =>
      nds.map((node) => {
        if (node.id !== nodeId || !isBranchNodeType(node.data.type)) return node;

        const branchConfig = normalizeBranchConfig(node.data.config);
        if (branchConfig.rules.length <= 1) {
          nextHandles = node.data.outputs;
          return node;
        }

        const nextRules = branchConfig.rules.slice(0, -1);
        const dataWithBranch = applyBranchMetadataToData(
          { ...node.data, config: { ...branchConfig, rules: nextRules } },
          getNodeDefinition(node.data.type)
        );
        nextHandles = dataWithBranch.outputs;
        updatedData = dataWithBranch;
        return { ...node, data: dataWithBranch };
      })
    );

    if (nextHandles) {
      pruneEdgesForNode(nodeId, nextHandles);
    }

    if (updatedData) {
      setSelectedNode((prev) =>
        prev && prev.id === nodeId ? { ...prev, data: updatedData! } : prev
      );
      if (flowDataLoadedRef.current && canEditFlow) {
        setHasUnsavedChanges(true);
        triggerDataFlowRecalc();
      }
    }
  }, [getNodeDefinition, pruneEdgesForNode, setNodes, setSelectedNode, triggerDataFlowRecalc, canEditFlow]);

  // Fetch node definitions and palette (global for all flows)
  const definitionsQuery = useQuery<NodeDefinitionsResponse>({
    queryKey: ["flow-definitions"],
    queryFn: async () => {
      // Backend returns: { ok, stage, definitions: {...} }
      const response = await fetchJson<{
        ok: boolean;
        stage: string;
        definitions: Record<string, NodeDefinition>;
      }>(FLOW_DEFINITIONS_PATH);

      // Transform backend format to frontend format
      const node_definitions = response.definitions;

      // Group definitions by category to create palette
      const categoriesMap = new Map<string, PaletteCategory>();

      Object.entries(node_definitions).forEach(([kind, def]) => {
        // Do not show disabled nodes in the palette (enabled=false). Default is enabled.
        if (def.enabled === false) return;
        const categoryId = def.category.toLowerCase().replace(/\s+/g, '-');

        if (!categoriesMap.has(categoryId)) {
          categoriesMap.set(categoryId, {
            id: categoryId,
            label: def.category,
            items: [],
          });
        }

        categoriesMap.get(categoryId)!.items.push({
          kind: def.kind,
          title: def.title,
          icon: def.icon,
          description: def.description,
        });
      });

      const palette = Array.from(categoriesMap.values());

      return { node_definitions, palette };
    },
  });

  useEffect(() => {
    nodeDefinitionsRef.current = definitionsQuery.data?.node_definitions;
  }, [definitionsQuery.data?.node_definitions]);

  // Fetch flow data if editing existing flow
  const flowQuery = useQuery<FlowData | null>({
    queryKey: [FLOWS_PATH, flowId],
    queryFn: async () => {
      if (!flowId) return null;
      // Include graph + derived ctx_schema for editor autocomplete/validation
      return await fetchJson<FlowData>(apiV1(`/flows/${flowId}/?include_graph=1`));
    },
    enabled: Boolean(flowId),
  });

  // Fetch version history
  type VersionListResponse = {
    ok: boolean;
    versions: FlowVersion[];
  };
  
  const versionsQuery = useQuery<VersionListResponse | null>({
    queryKey: [FLOWS_PATH, flowId, "versions"],
    queryFn: async () => {
      if (!flowId) return null;
      return await fetchJson<VersionListResponse>(apiV1(`/flows/${flowId}/versions/`));
    },
    enabled: Boolean(flowId),
  });

  // Execution type
  type ExecutionMode = "production" | "testing" | "preview" | "unknown";
  
  type Execution = {
    id: string;
    version_label: string;
    status: "pending" | "running" | "completed" | "failed" | "cancelled" | "success" | "awaiting_trigger";
    started_at: string;
    finished_at: string | null;
    trigger_type: string;
    trigger_data?: any;
    steps_count?: number;
    error?: string | { message: string };
    execution_mode?: ExecutionMode;
    duration_ms?: number;
    input_data?: any;
    input?: any;
    output_data?: any;
    output?: { steps?: ExecutionStep[]; context?: Record<string, any>; [key: string]: any };
    timeline?: ExecutionStep[];
    context?: Record<string, any>;
  };
  
  type ExecutionStep = {
    kind: string;
    name: string;
    node_id: string;
    status: string;
    input?: any;
    output?: any;
    started_at?: string;
    finished_at?: string;
    transitions?: Array<{ target: string; source_port: string; target_port: string }>;
    incoming_port?: string | null;
  };
  
  // Helper to extract error message from error field (can be string or object)
  const getErrorMessage = (error: string | { message: string } | undefined): string | null => {
    if (!error) return null;
    if (typeof error === "string") return error.trim() ? error : null;
    if (typeof error === "object" && "message" in error) return error.message?.trim() ? error.message : null;
    // Don't show empty objects
    const jsonStr = JSON.stringify(error);
    return jsonStr === "{}" || jsonStr === "[]" ? null : jsonStr;
  };

  // Helper to check if there's a real error to display
  const hasRealError = (error: any): boolean => {
    if (!error) return false;
    if (typeof error === "string") return error.trim().length > 0;
    if (typeof error === "object" && "message" in error) return (error.message?.trim() ?? "").length > 0;
    const jsonStr = JSON.stringify(error);
    return jsonStr !== "{}" && jsonStr !== "[]";
  };
  
  // Helper to transform execution data - extracts nested steps/context from output/output_data
  const transformExecution = (execution: Execution): Execution => {
    // API may return data in 'output' or 'output_data' depending on endpoint
    const output = execution.output ?? execution.output_data;
    if (!output || typeof output !== "object") return execution;
    
    return {
      ...execution,
      timeline: output.steps ?? execution.timeline,
      context: output.context ?? execution.context,
    };
  };

  // Normalize execution metadata across backend shapes so filtering/UI is reliable.
  const normalizeExecution = (raw: any): Execution => {
    const modeRaw =
      raw?.execution_mode ??
      raw?.executionMode ??
      raw?.mode ??
      raw?.stage ??
      raw?.execution_stage ??
      "unknown";
    const modeStr = String(modeRaw || "unknown").toLowerCase();
    const execution_mode: ExecutionMode =
      modeStr === "production" || modeStr === "testing" || modeStr === "preview"
        ? (modeStr as ExecutionMode)
        : "unknown";

    const version_label =
      typeof raw?.version_label === "string"
        ? raw.version_label
        : typeof raw?.version?.label === "string"
          ? raw.version.label
          : typeof raw?.flow_version?.label === "string"
            ? raw.flow_version.label
            : typeof raw?.version === "string"
              ? raw.version
              : "Unknown";

    return {
      ...(raw as Execution),
      execution_mode,
      version_label,
    };
  };
  
  type ExecutionListResponse = {
    ok: boolean;
    executions: Execution[];
    pagination?: {
      total_items: number;
      current_page: number;
      total_pages: number;
      page_size: number;
    };
  };
  
  const MODE_ICON_MAP: Record<ExecutionMode, typeof Rocket> = {
    production: Rocket,
    testing: FlaskConical,
    preview: Eye,
    unknown: HelpCircle,
  };

  const MODE_COLORS: Record<ExecutionMode, string> = {
    production: "text-green-600 dark:text-green-400",
    testing: "text-amber-600 dark:text-amber-400",
    preview: "text-blue-600 dark:text-blue-400",
    unknown: "text-muted-foreground",
  };
  
  const MODE_BADGE_VARIANTS: Record<ExecutionMode, "default" | "secondary" | "outline"> = {
    production: "default",
    testing: "secondary",
    preview: "outline",
    unknown: "outline",
  };

  // Fetch execution history with pagination and filters
  const executionsQuery = useQuery<ExecutionListResponse | null>({
    queryKey: [FLOWS_PATH, flowId, "executions", executionHistoryPage, executionHistoryModeFilter],
    queryFn: async () => {
      if (!flowId) return null;
      const params = new URLSearchParams();
      params.append("page", String(executionHistoryPage));
      params.append("page_size", "20");
      if (executionHistoryModeFilter !== "all") {
        params.append("execution_mode", executionHistoryModeFilter);
      }

      const normalizeExecutionsResponse = (raw: any): ExecutionListResponse => {
        // Supported shapes:
        // 1) { ok, executions, pagination }
        // 2) { executions, pagination }
        // 3) { results, count, ... } (Django REST style)
        // 4) Array<Execution>
        if (Array.isArray(raw)) {
          return { ok: true, executions: raw.map((e) => normalizeExecution(e)) };
        }
        if (raw && typeof raw === "object") {
          if (Array.isArray(raw.executions)) {
            return {
              ok: raw.ok ?? true,
              executions: raw.executions.map((e: any) => normalizeExecution(e)),
              pagination: raw.pagination,
            };
          }
          if (Array.isArray(raw.results)) {
            const total = typeof raw.count === "number" ? raw.count : raw.results.length;
            return {
              ok: raw.ok ?? true,
              executions: raw.results.map((e: any) => normalizeExecution(e)),
              pagination: raw.pagination ?? {
                total_items: total,
                current_page: executionHistoryPage,
                total_pages: Math.max(1, Math.ceil(total / 20)),
                page_size: 20,
              },
            };
          }
        }
        return { ok: true, executions: [] };
      };

      // Try the flow-scoped endpoint first.
      try {
        const raw = await fetchJson<any>(apiV1(`/flows/${flowId}/executions/?${params.toString()}`));
        return normalizeExecutionsResponse(raw);
      } catch (err) {
        // Fallback to the newer executions endpoint used by the event monitor.
        // This backend typically expects flow_id/version_id filters.
        if (err instanceof ApiError && (err.status === 404 || err.status === 405)) {
          const params2 = new URLSearchParams(params.toString());
          params2.set("flow_id", flowId);
          const raw = await fetchJson<any>(apiV1(`/flows/api/executions/?${params2.toString()}`));
          return normalizeExecutionsResponse(raw);
        }
        throw err;
      }
    },
    enabled: Boolean(flowId) && isExecutionHistoryOpen,
    staleTime: 0,
    refetchOnMount: "always",
    refetchOnWindowFocus: true,
    // Keep the history fresh while the sheet is open.
    refetchInterval: isExecutionHistoryOpen ? 10_000 : false,
  });

  const visibleExecutions = useMemo(() => {
    const list = (executionsQuery.data?.executions ?? []).map((e) => normalizeExecution(e));
    const filtered =
      executionHistoryModeFilter === "all"
        ? list
        : list.filter((e) => e.execution_mode === executionHistoryModeFilter);
    return filtered;
  }, [executionsQuery.data?.executions, executionHistoryModeFilter]);

  // Keep detail view in sync when the list refreshes.
  useEffect(() => {
    if (!selectedExecution) return;
    const list = executionsQuery.data?.executions ?? [];
    const updated = list.find((e) => String((e as any)?.id) === selectedExecution.id);
    if (!updated) return;
    setSelectedExecution(transformExecution(normalizeExecution(updated)));
  }, [executionsQuery.data?.executions]);
  
  // Reset page when filter changes
  useEffect(() => {
    setExecutionHistoryPage(1);
  }, [executionHistoryModeFilter]);

  // Reset the loaded flag when flowId changes
  useEffect(() => {
    flowDataLoadedRef.current = false;
  }, [flowId]);

  // Keep local allVersions in sync with the server list
  useEffect(() => {
    if (versionsQuery.data?.versions) {
      setAllVersions(versionsQuery.data.versions);
    }
  }, [versionsQuery.data?.versions]);

  // Ensure flowVersion is set from versionsQuery if not already set
  // Priority: 1) Published version (default), 2) Draft version if no published exists
  useEffect(() => {
    console.log('[VERSIONS_EFFECT] Running - flowVersion:', flowVersion?.id, 'versionsQuery.data:', versionsQuery.data?.versions?.length ?? 0);
    if (!flowVersion && versionsQuery.data?.versions && versionsQuery.data.versions.length > 0) {
      const versions = versionsQuery.data.versions;
      // Prefer published version as default, fall back to draft if no published
      const publishedVersion = versions.find(v => v.is_published);
      const draftVersion = versions.find(v => v.status === "draft");
      const defaultVersion = publishedVersion || draftVersion || versions[0];
      console.log('[VERSIONS_EFFECT] Setting flowVersion to:', defaultVersion.id, defaultVersion.label, '(published:', !!publishedVersion, ')');
      setFlowVersion(defaultVersion);
    }
  }, [flowVersion, versionsQuery.data]);

  // Load flow data
  useEffect(() => {
    if (!flowId) return;
    if (!definitionsQuery.data?.node_definitions) return;
    if (flowDataLoadedRef.current) return;
    if (!flowQuery.data) return;

    const { flow, graph, version, versions } = flowQuery.data;
    setFlowName(flow.name || "Untitled Flow");
    setFlowDescription(flow.description || "");
    setFlowStatus(flow.status || "draft");
    // is_enabled is now derived from having a published version
    setFlowIsEnabled(flowHasPublishedVersion(flow, versions));
    
    // Set current version - prefer version from response, fall back to latest draft version
    if (version) {
      setFlowVersion(version);
    } else if (versions && versions.length > 0) {
      // Find the latest draft version if no current version specified
      const draftVersion = versions.find(v => v.status === "draft") || versions[0];
      setFlowVersion(draftVersion);
    }
    
    // Store all versions for version selector
    if (versions) {
      setAllVersions(versions);
    }

    // Load flow config schema + values (per-version, stored under graph.config_schema / graph.config_values)
    const loadedConfigSchema = graph?.config_schema !== undefined ? graph.config_schema : null;
    const loadedConfigValues =
      graph?.config_values && typeof graph.config_values === "object" && !Array.isArray(graph.config_values)
        ? (graph.config_values as Record<string, unknown>)
        : {};

    setFlowConfigSchema(loadedConfigSchema);
    setFlowConfigSchemaText(loadedConfigSchema ? JSON.stringify(loadedConfigSchema, null, 2) : "");
    setFlowConfigSchemaError(null);

    setFlowConfigValues(loadedConfigValues);
    setFlowConfigValuesText(JSON.stringify(loadedConfigValues, null, 2));

    // Validate loaded values (includes strict rule: values require schema)
    setFlowConfigValuesError(validateConfigValuesAgainstJsonSchema(loadedConfigSchema, loadedConfigValues));

    // ctx_schema (optional; used for ctx.* autocomplete + warnings)
    if ((graph as any)?.ctx_schema !== undefined) {
      setCtxSchema((graph as any).ctx_schema);
    } else {
      setCtxSchema(null);
    }

    const nodeDefinitions = definitionsQuery.data.node_definitions;

    let restoredNodes: Node<NodeData>[] = [];

    try {
      if (graph?.nodes) {
        // Transform backend nodes to ReactFlow format
        restoredNodes = graph.nodes.map((backendNode: any) => {
          console.log(`[RESTORE] Backend node ${backendNode.id} config:`, backendNode.config);
          // Backend returns: { id, kind, name, x, y, config, ports }
          // ReactFlow expects: { id, type, position, data }
          const nodeData: SerializableNodeData = {
            label: backendNode.name,
            type: backendNode.kind,
            config: backendNode.config || {},
            description: backendNode.description,
          };
          console.log(`[RESTORE] Node ${backendNode.id} after NodeData creation - config:`, nodeData.config);

          const mergedData = mergeNodeDataWithDefinitions(
            nodeData,
            nodeDefinitions
          );
          console.log(`[RESTORE] Node ${backendNode.id} after merge - config:`, mergedData.config);

          return {
            id: backendNode.id,
            type: "custom",
            position: { x: backendNode.x, y: backendNode.y },
            data: {
              ...mergedData,
              icon: mergedData.iconKey ? iconMap[mergedData.iconKey] : undefined,
              onConfig: handleNodeConfig,
              onDelete: handleNodeDelete,
              onAddElif: handleAddElif,
              onRemoveElif: handleRemoveElif,
            },
          } as Node<NodeData>;
        });
        setNodes(restoredNodes);

        // Re-seed node ID counter
        let maxId = 0;
        graph.nodes.forEach((node) => {
          const match = node.id.match(/node_(\d+)/);
          if (match) {
            const numId = parseInt(match[1], 10);
            if (numId > maxId) {
              maxId = numId;
            }
          }
        });
        nodeIdCounter.current = maxId + 1;
      }
      if (graph?.edges) {
        // Transform backend edges to ReactFlow format
        // v2 spec: sourceHandle is mandatory, but provide default for legacy data
        const restoredEdges = graph.edges.map((backendEdge: any) => {
          const sourceHandle = backendEdge.source_port || backendEdge.sourceHandle || "out";
          const sourceNode = restoredNodes.find((n: Node<NodeData>) => n.id === backendEdge.source);
          const isBranchEdge = sourceNode && isBranchNodeType(sourceNode.data.type);
          
          // Handles == output names; use as-is
          const uiSourceHandle = sourceHandle;
          const ruleName = sourceHandle;
          
          return {
            id: backendEdge.id,
            source: backendEdge.source,
            target: backendEdge.target,
            sourceHandle: uiSourceHandle,
            targetHandle: backendEdge.target_port || backendEdge.targetHandle,
            type: "custom",
            data: { 
              onDelete: canEditFlow ? handleEdgeDelete : undefined,
              sourceHandle: uiSourceHandle,
              ruleName,
              isBranchEdge: isBranchEdge || false,
              readOnly: !canEditFlow,
            } as CustomEdgeData,
          };
        });
        setEdges(restoredEdges);
      }

      flowDataLoadedRef.current = true;
      setHasUnsavedChanges(false);
      // Trigger initial data flow calculation after graph loads
      triggerDataFlowRecalc();
      // Center graph at the default zoom (desktop-friendly, avoids oversized nodes).
      applyDefaultViewport();
    } catch (error) {
      console.error("[FLOW_LOAD] Error loading flow data:", error);
      toast({
        title: "Error loading flow",
        description: error instanceof Error ? error.message : "Failed to load flow data. Please try again.",
        variant: "destructive",
      });
      // Reset loading flag so user can retry
      flowDataLoadedRef.current = false;
    }
  }, [
    flowQuery.data,
    definitionsQuery.data?.node_definitions,
    setNodes,
    setEdges,
    handleNodeConfig,
    handleNodeDelete,
    handleEdgeDelete,
    handleAddElif,
    handleRemoveElif,
    flowId,
    triggerDataFlowRecalc,
    applyDefaultViewport,
    toast,
    graphReloadNonce,
  ]);

  // Fallback: if a flow was marked loaded but nodes are empty while graph has nodes (often on locked flows),
  // trigger one reload attempt.
  useEffect(() => {
    const graphHasNodes = (flowQuery.data?.graph?.nodes?.length ?? 0) > 0;
    if (!flowDataLoadedRef.current) return;
    if (!graphHasNodes) return;
    if (nodes.length > 0) return;
    setGraphReloadNonce((n) => n + 1);
    flowDataLoadedRef.current = false;
  }, [nodes.length, flowQuery.data?.graph?.nodes]);

  // Track changes to nodes and edges
  const handleNodesChangeWithTracking = useCallback(
    (changes: any) => {
      // In read-only mode, allow selection but block mutations.
      if (!canEditFlow) {
        const safe = Array.isArray(changes) ? changes.filter((c: any) => c?.type === "select" || c?.type === "reset") : changes;
        onNodesChange(safe);
        return;
      }

      onNodesChange(changes);
      // Only mark as changed for actual modifications (not selection changes)
      const hasRealChanges = changes.some((c: any) => 
        c.type !== 'select' && c.type !== 'reset'
      );
      if (hasRealChanges && flowDataLoadedRef.current) {
        setHasUnsavedChanges(true);
        triggerDataFlowRecalc();
      }
    },
    [onNodesChange, triggerDataFlowRecalc, canEditFlow]
  );

  const handleEdgesChangeWithTracking = useCallback(
    (changes: any) => {
      // In read-only mode, allow selection but block mutations.
      if (!canEditFlow) {
        const safe = Array.isArray(changes) ? changes.filter((c: any) => c?.type === "select" || c?.type === "reset") : changes;
        onEdgesChange(safe);
        return;
      }

      onEdgesChange(changes);
      const hasRealChanges = changes.some((c: any) => 
        c.type !== 'select' && c.type !== 'reset'
      );
      if (hasRealChanges && flowDataLoadedRef.current) {
        setHasUnsavedChanges(true);
        triggerDataFlowRecalc();
      }
    },
    [onEdgesChange, triggerDataFlowRecalc, canEditFlow]
  );

  const onConnect = useCallback(
    (params: Connection) => {
      if (!params.source || !params.target) return;
      if (!canEditFlow) return;
      
      // v2 spec: sourceHandle is mandatory
      if (!params.sourceHandle) {
        const sourceNode = nodesRef.current.find((n) => n.id === params.source);
        const isBranch = sourceNode && isBranchNodeType(sourceNode.data.type);
        toast({
          title: "Cannot create connection",
          description: isBranch
            ? "Branch nodes have multiple outputs. Start the connection from a specific branch output dot."
            : "Please connect from a specific output port. Click on an output handle to create the connection.",
          variant: "destructive",
        });
        return;
      }
      
      // Check if this connection would create a cycle
      if (wouldCreateCycle(edgesRef.current, params.source, params.target)) {
        toast({
          title: "Cannot create connection",
          description: "This connection would create a cycle. Cycles are not allowed in flows.",
          variant: "destructive",
        });
        return;
      }
      
      const sourceNode = nodes.find(n => n.id === params.source);
      const isBranchEdge = sourceNode && isBranchNodeType(sourceNode.data.type);
      const ruleName = isBranchEdge ? params.sourceHandle || undefined : undefined;
      
      const newEdge = {
        ...params,
        type: "custom",
        data: { 
          onDelete: canEditFlow ? handleEdgeDelete : undefined,
          sourceHandle: params.sourceHandle,
          ruleName,
          isBranchEdge: isBranchEdge || false,
          readOnly: !canEditFlow,
        } as CustomEdgeData,
      };
      setEdges((eds) => addEdge(newEdge, eds));
      if (flowDataLoadedRef.current && canEditFlow) {
        setHasUnsavedChanges(true);
        triggerDataFlowRecalc();
      }
    },
    [setEdges, handleEdgeDelete, triggerDataFlowRecalc, toast, canEditFlow]
  );

  // Data flow analyzer: recalculate available data only when graphVersion changes (explicit triggers)
  // Uses refs to access latest nodes/edges without causing dependency-triggered re-runs
  useEffect(() => {
    if (!definitionsQuery.data?.node_definitions) return;
    // Skip initial render before graph is loaded
    if (graphVersion === 0) return;

    const currentNodes = nodesRef.current;
    const currentEdges = edgesRef.current;
    const nodeDefinitions = definitionsQuery.data.node_definitions as unknown as Record<string, BackendNodeDefinition>;

    const { dataMap, hasCycle, cycleNodeIds } = analyzeDataFlow(
      currentNodes as Node<CustomNodeData>[],
      currentEdges,
      nodeDefinitions,
      flowConfigSchema,
      flowConfigValues
    );

    // If cycle detected, show error and clear all data to prevent stale/misleading info
    if (hasCycle) {
      toast({
        title: "Cycle detected in flow",
        description: `This flow contains a cycle and cannot be analyzed. Please remove the cyclic connections involving ${cycleNodeIds.length} node(s).`,
        variant: "destructive",
      });
      
      // Clear cache to prevent stale data
      dataFlowCacheRef.current = new Map();
      
      // Clear all node available data to show explicit empty state
      const clearedNodes = currentNodes.map((node) => ({
        ...node,
        data: {
          ...node.data,
          availableData: [],
        },
      }));
      setNodes(clearedNodes);
      return;
    }

    // Update cache
    dataFlowCacheRef.current = dataMap;

    const scopeMap = getScopeMap(currentNodes as Node<CustomNodeData>[], currentEdges);

    let nodesChanged = false;
    const updatedNodes = currentNodes.map((node) => {
      const rawAvailable = dataMap.get(node.id) || [];
      const scope = scopeMap.get(node.id);

      // Spec-aligned visibility:
      // - Trigger: no input, no ctx
      // - Normalize: input-only (input.body.*, nodes.*.output.*, config.*)
      // - Control-flow: ctx-only (requires Normalize upstream)
      // - Action/templates: ctx-only (optional config.*), requires Normalize upstream
      let availableData = rawAvailable;
      if (!scope) {
        availableData = [];
      } else if (scope.canSeeInput) {
        availableData = rawAvailable.filter((f) => {
          const k = f.key || "";
          return k === "input.body" || k.startsWith("input.body.") || k.startsWith("nodes.") || k === "config" || k.startsWith("config.");
        });
      } else if (scope.canSeeCtx) {
        // Spec B: once ctx exists, do NOT show input.* at all.
        // Show ctx.* (schema compiled from Normalize) + config.* (global read-only).
        availableData = [...ctxFieldsForUI, ...configFieldsForUI];
      } else {
        availableData = [];
      }

      const currentData = node.data.availableData || [];

      const dataChanged = 
        availableData.length !== currentData.length ||
        availableData.some((field, idx) => 
          !currentData[idx] || 
          field.key !== currentData[idx].key || 
          field.type !== currentData[idx].type
        );

      if (dataChanged) {
        nodesChanged = true;
        return {
          ...node,
          data: {
            ...node.data,
            availableData,
          },
        };
      }
      return node;
    });

    let edgesChanged = false;
    const updatedEdges = currentEdges.map((edge) => {
      const sourceNode = currentNodes.find(n => n.id === edge.source);
      const isBranchEdge = sourceNode && isBranchNodeType(sourceNode.data.type);
      const sourceHandle = edge.sourceHandle || (edge.data as CustomEdgeData)?.sourceHandle;
      
      const dataPreview = getEdgeDataPreview(
        edge,
        currentNodes as Node<CustomNodeData>[],
        nodeDefinitions,
        dataMap
      );
      const currentPreview = (edge.data as CustomEdgeData)?.dataPreview || [];
      const currentIsBranchEdge = (edge.data as CustomEdgeData)?.isBranchEdge;
      const currentSourceHandle = (edge.data as CustomEdgeData)?.sourceHandle;

      const previewChanged = 
        dataPreview.length !== currentPreview.length ||
        dataPreview.some((field, idx) => 
          !currentPreview[idx] || 
          field.key !== currentPreview[idx].key ||
          field.type !== currentPreview[idx].type
        );
      
      const branchInfoChanged = 
        isBranchEdge !== currentIsBranchEdge ||
        sourceHandle !== currentSourceHandle;

      if (previewChanged || branchInfoChanged) {
        edgesChanged = true;
        return {
          ...edge,
          data: {
            ...edge.data,
            dataPreview,
            sourceHandle: sourceHandle,
            isBranchEdge: isBranchEdge || false,
          } as CustomEdgeData,
        };
      }
      return edge;
    });

    if (nodesChanged) {
      setNodes(updatedNodes);
    }
    if (edgesChanged) {
      setEdges(updatedEdges);
    }
  }, [
    graphVersion,
    definitionsQuery.data?.node_definitions,
    setNodes,
    setEdges,
    flowConfigSchema,
    flowConfigValues,
    ctxSchemaFields,
    ctxFieldsForUI,
    getScopeMap,
  ]);

  // Keyboard shortcuts for deletion
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      // Don't trigger deletion if user is typing in an input field
      const target = event.target as HTMLElement;
      const isEditingText = 
        target.tagName === "INPUT" ||
        target.tagName === "TEXTAREA" ||
        target.tagName === "SELECT" ||
        target.isContentEditable;

      if (isEditingText) {
        return;
      }

      if (event.key === "Delete" || event.key === "Backspace") {
        if (!canEditFlow) return;
        // Delete selected nodes
        const selectedNodes = nodes.filter((node) => node.selected);
        selectedNodes.forEach((node) => handleNodeDelete(node.id));

        // Delete selected edges
        const selectedEdges = edges.filter((edge) => edge.selected);
        selectedEdges.forEach((edge) => handleEdgeDelete(edge.id));
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [nodes, edges, handleNodeDelete, handleEdgeDelete, canEditFlow]);

  // Handle node drag from palette
  const onNodeDragStart = (
    nodeType: string, 
    label: string, 
    icon: any, 
    outputs?: string[], 
    inputs?: string[],
    portSchemas?: any,
    defaultConfig?: Record<string, any>,
    formComponent?: string
  ) => {
    // Don't allow dragging nodes if flow is locked/read-only
    if (!canEditFlow) return;
    draggedNodeInfo.current = { type: nodeType, label, icon, outputs, inputs, portSchemas, defaultConfig, formComponent };
  };

  // Handle drop on canvas
  const onDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault();
      // Don't allow adding nodes if flow is locked/read-only
      if (!canEditFlow) return;

      const type = event.dataTransfer.getData("application/reactflow");
      if (!type || !reactFlowInstance) return;

      const position = reactFlowInstance.screenToFlowPosition({
        x: event.clientX,
        y: event.clientY,
      });

      const label = event.dataTransfer.getData("nodeLabel");
      const outputs = JSON.parse(event.dataTransfer.getData("nodeOutputs") || "[]");
      const inputs = JSON.parse(event.dataTransfer.getData("nodeInputs") || "[]");
      const portSchemas = JSON.parse(event.dataTransfer.getData("nodePortSchemas") || "{}");
      const defaultConfig = JSON.parse(event.dataTransfer.getData("nodeDefaultConfig") || "{}");
      const formComponent = event.dataTransfer.getData("nodeFormComponent") || "";
      const hints = JSON.parse(event.dataTransfer.getData("nodeHints") || "{}");

      const id = `node_${nodeIdCounter.current++}`;
      const newNode: Node<NodeData> = {
        id,
        type: "custom",
        position,
        data: {
          label,
          type,
          icon: draggedNodeInfo.current?.icon,
          outputs,
          inputs,
          portSchemas,
          config: defaultConfig,
          formComponent: formComponent || undefined,
          hints: Object.keys(hints).length > 0 ? hints : undefined,
          onConfig: handleNodeConfig,
          onDelete: handleNodeDelete,
          onAddElif: handleAddElif,
          onRemoveElif: handleRemoveElif,
        },
      };

      if (isBranchNodeType(type)) {
        newNode.data = applyBranchMetadataToData(
          newNode.data,
          getNodeDefinition(type)
        );
      }

      setNodes((nds) => [...nds, newNode]);
      draggedNodeInfo.current = null;
      if (flowDataLoadedRef.current && canEditFlow) {
        setHasUnsavedChanges(true);
        triggerDataFlowRecalc();
      }
    },
    [
      reactFlowInstance,
      setNodes,
      handleNodeConfig,
      handleNodeDelete,
      handleAddElif,
      handleRemoveElif,
      getNodeDefinition,
      triggerDataFlowRecalc,
      canEditFlow,
    ]
  );

  const onDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
  }, []);

  const onNodeClick = useCallback((_event: React.MouseEvent, node: Node<NodeData>) => {
    // Locked flows should allow viewing node config (read-only).
    setSelectedNode(node);
    setIsConfigOpen(true);
  }, []);

  // Calculate available data for selected node
  // Uses getAvailableDataForNode for nested structure, then merges computed fields from cache
  useEffect(() => {
    if (selectedNode && definitionsQuery.data?.node_definitions && !webhooksQuery.isLoading) {
      try {
        // Build schema sources with webhook data
        const schemaSources: SchemaSource = {
          webhooks: webhooksQuery.data?.webhooks || [],
        };
        
        // Get nested DataNode[] structure from getAvailableDataForNode
        const dataNodes = getAvailableDataForNode(
          selectedNode.id,
          nodes,
          edges,
          definitionsQuery.data.node_definitions,
          schemaSources
        );
        
        // Get computed fields from cache (from analyzeDataFlow topological analysis)
        const cachedFields = dataFlowCacheRef.current.get(selectedNode.id) || [];
        
        // Merge computed fields into the nested structure (pass nodes for proper nodeId mapping)
        const mergedDataNodes = mergeComputedFieldsIntoDataNodes(dataNodes, cachedFields, nodes);
        
        // Get current config from nodes state to avoid overwriting with stale data
        const currentNodeInState = nodes.find(n => n.id === selectedNode.id);
        const currentConfig = currentNodeInState?.data?.config || selectedNode.data.config;
        
        setSelectedNode(prev => prev ? { 
          ...prev, 
          data: { 
            ...prev.data, 
            config: currentConfig,
            availableData: mergedDataNodes as any 
          } 
        } : null);
      } catch (error) {
        console.error("Error calculating available data:", error);
      }
    }
  }, [selectedNode?.id, nodes, edges, definitionsQuery.data?.node_definitions, webhooksQuery.data?.webhooks, webhooksQuery.isLoading]);

  const updateSelectedNode = (updates: Partial<NodeData>) => {
    if (!selectedNode) return;
    if (!canEditFlow) return;
    let nextData: NodeData | undefined;
    let shouldPrune = false;

    setNodes((nds) =>
      nds.map((node) => {
        if (node.id !== selectedNode.id) return node;

        let newData: NodeData = { ...node.data, ...updates };

        if (isBranchNodeType(node.data.type) && updates.config !== undefined) {
          const previousHandles = (node.data.outputs || []) as string[];

          newData = applyBranchMetadataToData(
            newData,
            getNodeDefinition(node.data.type)
          );
          const nextHandles = (newData.outputs || []) as string[];

          const handlesChanged =
            previousHandles.length !== nextHandles.length ||
            previousHandles.some((h, idx) => h !== nextHandles[idx]);

          if (handlesChanged) {
            shouldPrune = true;
            (newData as any).__previousHandles = previousHandles;
          }
        }

        // HTTP nodes: if config.output_schema exists, immediately hydrate instance portSchemas
        // so downstream nodes can see nodes.<id>.output.response_data.* without needing a refresh.
        if (updates.config !== undefined) {
          const typeKey = String(node.data.type || "");
          const fc = String((node.data as any).formComponent || "");
          const isHttp =
            fc === "form_http_request" ||
            fc === "http" ||
            typeKey.includes("http");

          if (isHttp) {
            const def = getNodeDefinition(node.data.type);
            const definitionSchemas = buildPortSchemaMap(def);
            const basePortSchemas = (newData as any).portSchemas ?? definitionSchemas ?? {};
            const outPorts = (basePortSchemas as any)?.out ?? {};
            const outNames = Object.keys(outPorts).filter(Boolean);

            const bodySchema = (newData as any)?.config?.output_schema;
            if (bodySchema && typeof bodySchema === "object") {
              const wrapped = {
                kind: "object",
                properties: {
                  response_data: bodySchema,
                },
              };
              const nextOut: any = { ...(outPorts || {}) };
              const names = outNames.length ? outNames : ["out"];
              names.forEach((name) => {
                nextOut[name] = { ...(nextOut[name] || { name }), name, schema: wrapped };
              });
              (newData as any).portSchemas = {
                ...(basePortSchemas as any),
                out: nextOut,
              };
            }
          }
        }

        nextData = newData;
        return { ...node, data: newData };
      })
    );

    if (nextData) {
      const nextNode = { ...selectedNode, data: nextData };
      setSelectedNode(nextNode);
      if (shouldPrune) {
        pruneEdgesForNode(nextNode.id, nextNode.data.outputs || []);
      }
      // Mark as unsaved when node config changes (only if editable)
      if (flowDataLoadedRef.current && canEditFlow) {
        setHasUnsavedChanges(true);
        // If Normalize mappings changed, invalidate backend-derived ctx_schema (it may now be stale).
        if (
          (nextNode.data.type === "logic_normalize" || nextNode.data.type === "normalize") &&
          updates.config !== undefined
        ) {
          setCtxSchema(null);
        }
        triggerDataFlowRecalc();
      }
    }
  };

  const deleteSelectedNode = () => {
    if (!selectedNode) return;
    // Don't allow deletion if flow is locked/read-only
    if (!canEditFlow) return;

    setNodes((nds) => nds.filter((node) => node.id !== selectedNode.id));
    setEdges((eds) =>
      eds.filter(
        (edge) => edge.source !== selectedNode.id && edge.target !== selectedNode.id
      )
    );
    setIsConfigOpen(false);
    setSelectedNode(null);
    // Mark as unsaved when node is deleted
    if (flowDataLoadedRef.current) {
      setHasUnsavedChanges(true);
      triggerDataFlowRecalc();
    }
  };

  // Validation: Check if flow is fully connected (no lonely nodes or islands)
  const validateFlowConnection = () => {
    if (nodes.length === 0) {
      return { isValid: false, message: "Flow must contain at least one node" };
    }

    // Single node flows are always valid (e.g., trigger-only flows)
    if (nodes.length === 1) {
      return { isValid: true, message: "" };
    }

    // If there are multiple nodes but no edges, it's invalid
    if (edges.length === 0) {
      return {
        isValid: false,
        message: "Flow with multiple nodes must have at least one connection"
      };
    }

    // Build adjacency list for connected graph validation
    const adjacency = new Map<string, Set<string>>();
    nodes.forEach(node => adjacency.set(node.id, new Set()));

    edges.forEach(edge => {
      adjacency.get(edge.source)?.add(edge.target);
      adjacency.get(edge.target)?.add(edge.source);
    });

    // Check for islands using DFS - all nodes should be reachable from any starting node
    const visited = new Set<string>();
    const dfs = (nodeId: string) => {
      visited.add(nodeId);
      adjacency.get(nodeId)?.forEach(neighbor => {
        if (!visited.has(neighbor)) {
          dfs(neighbor);
        }
      });
    };

    // Start DFS from first node
    dfs(nodes[0].id);

    // Check if all nodes were visited - if not, there are disconnected islands
    if (visited.size !== nodes.length) {
      const disconnectedCount = nodes.length - visited.size;
      return {
        isValid: false,
        message: `Flow contains ${disconnectedCount} disconnected node(s). All nodes must be connected in a single graph.`
      };
    }

    return { isValid: true, message: "" };
  };

  // Validation: Check trigger count (v2 spec: ≥1 trigger required)
  const validateTriggerCount = () => {
    const triggerNodes = nodes.filter(node => {
      const type = node.data.type;
      return type.startsWith('trigger_') || 
             type === 'webhook' || 
             type === 'event' ||
             type === 'scheduled' ||
             type === 'trigger_webhook' ||
             type === 'trigger_event' ||
             type === 'trigger_scheduled';
    });
    
    if (triggerNodes.length === 0) {
      return {
        isValid: false,
        message: "Flow must have at least one trigger node. Add a webhook, event, or schedule trigger."
      };
    }
    
    return { isValid: true, message: "" };
  };

  // Validation: Check if all required node configurations are present
  const validateNodeConfigurations = () => {
    const isAgentNodeType = (type?: string) => {
      const t = String(type || "").toLowerCase();
      const agentTokenRe = /(^|[_\-.])agent($|[_\-.])/;
      return (
        t === "agent" ||
        t === "ai" ||
        t === "ai_agent" ||
        t === "tool_ai_agent" ||
        t === "tool_agent" ||
        t.endsWith("_agent") ||
        t.includes("ai_agent") ||
        agentTokenRe.test(t)
      );
    };

    const extractTemplatePlaceholders = (template: string): string[] => {
      const out: string[] = [];
      const re = /\{\{\s*([^}]+?)\s*\}\}/g;
      let m: RegExpExecArray | null;
      while ((m = re.exec(template)) !== null) {
        const raw = String(m[1] || "").trim();
        if (raw) out.push(raw);
      }
      return out;
    };

    const allowedWorkflowCtx = new Set<string>([
      "ctx.workflow.input_as_text",
      "ctx.workflow.input",
    ]);

    for (const node of nodes) {
      // Check if Event trigger nodes have required event configuration
      if (node.data.type.includes("event") || node.data.type === "trigger_event") {
        const config = node.data.config || {};
        // Event trigger requires event_name to be configured
        if (!config.event_name) {
          return {
            isValid: false,
            message: `Event trigger node "${node.data.label}" requires an event type to be configured. Please open the node configuration and select an event.`
          };
        }
      }

      // Agent node validation (desktop-agent runtime contract)
      if (isAgentNodeType(node.data.type) || node.data.formComponent === "form_agent") {
        const config = node.data.config || {};
        const agentId = String(config.agent_id || "").trim();
        if (!agentId) {
          return {
            isValid: false,
            message: `Agent node "${node.data.label}" requires agent_id. Please open the node configuration and select an agent.`,
          };
        }

        const inputMessage = String(config.input_message || config.prompt_template || "").trim();
        if (!inputMessage) {
          return {
            isValid: false,
            message: `Agent node "${node.data.label}" requires input_message. Please open the node configuration and provide an input message.`,
          };
        }

        const placeholders = extractTemplatePlaceholders(inputMessage);
        for (const ph of placeholders) {
          // Contract: only {{ctx.*}} placeholders allowed in agent composer
          if (!ph.startsWith("ctx.")) {
            return {
              isValid: false,
              message: `Agent node "${node.data.label}" has unsupported placeholder "{{ ${ph} }}". Only {{ctx.*}} is supported.`,
            };
          }

          // Special workflow inputs are always allowed (even if not in ctx_schema)
          if (allowedWorkflowCtx.has(ph)) continue;
          // Agent nodes can run without Normalize. If ctx_schema is present, the backend may still
          // enforce contract rules; we do not block saves here for non-workflow ctx.* paths.
        }
      }
    }
    return { isValid: true, message: "" };
  };

  // Save flow mutation
  const saveFlowMutation = useMutation({
    mutationFn: async () => {
      // Block save if config schema/values are invalid under strict contract rules
      if (flowConfigSchemaError || flowConfigValuesError) {
        throw new Error(flowConfigSchemaError || flowConfigValuesError || "Invalid flow config");
      }
      // v2 spec: Validate trigger count
      const triggerValidation = validateTriggerCount();
      if (!triggerValidation.isValid) {
        throw new Error(triggerValidation.message);
      }

      // Validate flow connection
      const connectionValidation = validateFlowConnection();
      if (!connectionValidation.isValid) {
        throw new Error(connectionValidation.message);
      }

      // Validate node configurations
      const configValidation = validateNodeConfigurations();
      if (!configValidation.isValid) {
        throw new Error(configValidation.message);
      }

      // v2 spec: Comprehensive flow validation (allow warnings, block errors)
      if (definitionsQuery.data?.node_definitions) {
        const nodeDefinitions = definitionsQuery.data.node_definitions as unknown as Record<string, BackendNodeDefinition>;
        const validationResult = validateFlowComprehensive(
          nodes as Node<CustomNodeData>[],
          edges,
          nodeDefinitions,
          flowConfigSchema,
          flowConfigValues,
          ctxSchema
        );
        
        // Block save if there are errors
        if (!validationResult.isValid && validationResult.errors.length > 0) {
          const errorMessages = validationResult.errors.map(e => 
            e.nodeLabel 
              ? `${e.type}: ${e.message} (Node: ${e.nodeLabel})`
              : `${e.type}: ${e.message}`
          ).join('\n');
          throw new Error(`Flow validation failed:\n${errorMessages}`);
        }
        
        // Show warnings but allow save
        if (validationResult.warnings.length > 0) {
          console.warn('Flow validation warnings:', validationResult.warnings);
        }
      }

      if (!flowId) {
        throw new Error("Flow ID is required. Please create a flow first.");
      }

      // Step 1: Update flow properties (name, description, is_enabled)
      const propertiesPayload = {
        name: flowName,
        description: flowDescription,
        is_enabled: flowIsEnabled,
      };

      console.log('[FLOW UPDATE] Updating properties:', JSON.stringify(propertiesPayload, null, 2));
      const propsRes = await apiRequest("PATCH", apiV1(`/flows/${flowId}/`), { data: propertiesPayload });
      await propsRes.json();

      // Step 2: Save the graph structure
      console.log(
        "[FLOW SAVE] Nodes before normalization:",
        nodes.map((n) => ({ id: n.id, type: n.data.type, config: n.data.config }))
      );
      const graphPayload = buildGraphPayloadForBackend(
        nodes as unknown as Node<NodeData>[],
        edges,
        flowConfigSchema,
        flowConfigValues
      );
      console.log(
        "[FLOW SAVE] Normalized nodes:",
        (graphPayload.graph.nodes || []).map((n: any) => ({ id: n.id, kind: n.kind, config: n.config }))
      );

      // Step 3: Fetch existing schedule BEFORE graph save (read-only, no mutation yet)
      const scheduleTriggerNode = nodes.find(n => n.data.type === "trigger_scheduled");
      let existingSchedule: Awaited<ReturnType<typeof getFlowSchedule>> = null;
      
      try {
        existingSchedule = await getFlowSchedule(flowId);
      } catch (e) {
        console.warn('[FLOW SAVE] Could not fetch existing schedule:', e);
      }

      // Step 4: Save the graph structure FIRST (before any schedule mutations)
      console.log('[FLOW SAVE] Saving graph:', JSON.stringify(graphPayload, null, 2));
      const res = await apiRequest("POST", apiV1(`/flows/${flowId}/save/`), { data: graphPayload });
      const saveResult = await res.json();

      // Step 5: Schedule sync AFTER successful graph save (transactional safety)
      // Delete orphaned schedule only after confirming graph save succeeded
      if (!scheduleTriggerNode && existingSchedule) {
        console.log('[FLOW SAVE] Removing orphaned schedule:', existingSchedule.id);
        try {
          await deleteFlowSchedule(flowId, existingSchedule.id);
        } catch (deleteError) {
          console.error('[FLOW SAVE] Schedule deletion failed:', deleteError);
        }
      }

      // Create/update schedule after successful graph save (propagate errors for transactional safety)
      let newScheduleId: string | null = null;
      if (scheduleTriggerNode) {
        const scheduleConfig = scheduleTriggerNode.data.config as ScheduleConfig;
        if (scheduleConfig && scheduleConfig.schedule_type) {
          const nodeScheduleId = scheduleTriggerNode.data.config?.schedule_id;
          const scheduleIdToUse = nodeScheduleId || existingSchedule?.id;
          
          if (scheduleIdToUse) {
            console.log('[FLOW SAVE] Updating existing schedule:', scheduleIdToUse);
            const updated = await updateFlowSchedule(flowId, scheduleIdToUse, scheduleConfig, flowIsEnabled);
            newScheduleId = updated.id;
          } else {
            console.log('[FLOW SAVE] Creating new schedule');
            const created = await createFlowSchedule(flowId, scheduleConfig, flowIsEnabled);
            newScheduleId = created.id;
          }
        }
      }

      // Try to extract the saved draft version (backend may return it in different shapes)
      const versionFromSave =
        (saveResult as any)?.version ??
        (saveResult as any)?.flow_version ??
        (saveResult as any)?.current_version ??
        (saveResult as any)?.save?.version ??
        (saveResult as any)?.graph?.version ??
        null;

      return {
        saveResult,
        version: versionFromSave,
        scheduleUpdate: scheduleTriggerNode ? { nodeId: scheduleTriggerNode.id, scheduleId: newScheduleId } : null,
      };
    },
    onSuccess: (data) => {
      setHasUnsavedChanges(false);

      // If backend returns ctx_schema on save, consume it as authoritative.
      const maybeCtxSchema =
        (data as any)?.saveResult?.graph?.ctx_schema ??
        (data as any)?.saveResult?.ctx_schema ??
        (data as any)?.graph?.ctx_schema;
      if (maybeCtxSchema !== undefined) {
        setCtxSchema(maybeCtxSchema);
      }

      // If backend returned an updated draft version (common), keep UI in sync.
      const maybeVersion = (data as any)?.version;
      if (maybeVersion?.id) {
        setFlowVersion(maybeVersion);
        queryClient.invalidateQueries({ queryKey: [FLOWS_PATH, flowId, "versions"] });
      }
      
      // Update node state immutably with schedule_id if schedule was created/updated
      if (data.scheduleUpdate?.nodeId && data.scheduleUpdate?.scheduleId) {
        setNodes((nds) =>
          nds.map((node) => {
            if (node.id === data.scheduleUpdate!.nodeId) {
              return {
                ...node,
                data: {
                  ...node.data,
                  config: {
                    ...node.data.config,
                    schedule_id: data.scheduleUpdate!.scheduleId,
                  },
                },
              };
            }
            return node;
          })
        );
      }
      
      toast({
        title: "Flow saved",
        description: "Your workflow has been saved successfully.",
      });
      queryClient.invalidateQueries({ queryKey: [FLOWS_PATH] });
      queryClient.invalidateQueries({ queryKey: [FLOWS_PATH, flowId] });
    },
    onError: (error) => {
      console.error("[FLOW SAVE] Failed:", error);
      if (error instanceof ApiError) {
        console.error("[FLOW SAVE] ApiError body:", error.body);
      }
      const formatted = formatApiErrorForToast(error);
      toast({
        title: formatted.title,
        description: formatted.description,
        variant: "destructive",
      });
    },
  });

  // Validate flow mutation (call before publish)
  const validateFlowMutation = useMutation({
    mutationFn: async () => {
      if (!flowId) throw new Error("Flow must be saved before validating");
      // Send current graph for richer backend diagnostics (if supported).
      // Backend may ignore it and validate the saved graph; both are fine.
      const graphPayload = buildGraphPayloadForBackend(
        nodes as unknown as Node<NodeData>[],
        edges,
        flowConfigSchema,
        flowConfigValues
      );
      const res = await apiRequest("POST", apiV1(`/flows/${flowId}/validate/`), { data: graphPayload });
      return await res.json();
    },
  });

  // Publish flow mutation - publishes current version, archives previous published
  const publishFlowMutation = useMutation({
    mutationFn: async () => {
      // Block publish early if config schema/values are invalid under strict contract rules
      if (flowConfigSchemaError || flowConfigValuesError) {
        throw new Error(flowConfigSchemaError || flowConfigValuesError || "Invalid flow config");
      }
      if (!flowId) throw new Error("Flow is required for publishing");

      const resolveDraftVersionId = async (fallbackId?: string) => {
        // Prefer a provided id if it looks valid
        if (fallbackId) return fallbackId;
        try {
          const list = await fetchJson<{ ok: boolean; versions: FlowVersion[] }>(apiV1(`/flows/${flowId}/versions/`));
          const versions = list?.versions ?? [];
          const draft =
            versions.find((v) => !v.is_published && (v.status === "draft" || v.is_editable)) ??
            versions.find((v) => !v.is_published) ??
            versions[0];
          return draft?.id;
        } catch {
          return undefined;
        }
      };

      // IMPORTANT: publish must operate on the latest saved graph.
      // If the user has unsaved changes (especially Normalize mappings / kinds), save first.
      let versionIdToPublish: string | undefined = flowVersion?.id;
      if (hasUnsavedChanges) {
        const saveOutcome: any = await saveFlowMutation.mutateAsync();
        const savedId =
          saveOutcome?.version?.id ??
          saveOutcome?.saveResult?.version?.id ??
          saveOutcome?.saveResult?.version_id ??
          undefined;
        versionIdToPublish = await resolveDraftVersionId(savedId ?? versionIdToPublish);
      } else {
        versionIdToPublish = await resolveDraftVersionId(versionIdToPublish);
      }

      if (!versionIdToPublish) {
        throw new Error("No draft version found to publish. Create/select a draft version first.");
      }

      // v2 spec: Validate trigger count before publishing
      const triggerValidation = validateTriggerCount();
      if (!triggerValidation.isValid) {
        throw new Error(triggerValidation.message);
      }

      // Validate flow connection before publishing
      const connectionValidation = validateFlowConnection();
      if (!connectionValidation.isValid) {
        throw new Error(connectionValidation.message);
      }

      // Validate node configurations before publishing
      const configValidation = validateNodeConfigurations();
      if (!configValidation.isValid) {
        throw new Error(configValidation.message);
      }

      // v2 spec: Comprehensive flow validation before publishing (must pass, no errors)
      if (definitionsQuery.data?.node_definitions) {
        const nodeDefinitions = definitionsQuery.data.node_definitions as unknown as Record<string, BackendNodeDefinition>;
        const validationResult = validateFlowComprehensive(
          nodes as Node<CustomNodeData>[],
          edges,
          nodeDefinitions,
          flowConfigSchema,
          flowConfigValues,
          ctxSchema
        );
        
        if (!validationResult.isValid && validationResult.errors.length > 0) {
          const errorMessages = validationResult.errors.map(e => 
            e.nodeLabel 
              ? `${e.type}: ${e.message} (Node: ${e.nodeLabel})`
              : `${e.type}: ${e.message}`
          ).join('\n');
          throw new Error(`Cannot publish flow with validation errors:\n${errorMessages}`);
        }
        
        // Warnings are allowed but logged
        if (validationResult.warnings.length > 0) {
          console.warn('Publish warnings:', validationResult.warnings);
        }
      }

      // Call backend validation endpoint
      const validateRes = await validateFlowMutation.mutateAsync();
      if (!validateRes?.ok) {
        if (Array.isArray(validateRes?.errors) && validateRes.errors.length > 0) {
          throw new Error(validateRes.errors.join(", "));
        }
        throw new Error(
          `Backend validation failed: ${typeof validateRes === "object" ? JSON.stringify(validateRes) : String(validateRes)}`
        );
      }

      // Use versioned endpoint: /flows/{flowId}/versions/{versionId}/publish/
      const res = await apiRequest("POST", apiV1(`/flows/${flowId}/versions/${versionIdToPublish}/publish/`), {});
      return await res.json();
    },
    onSuccess: (data) => {
      setIsPublishConfirmOpen(false);
      toast({
        title: "Flow published",
        description: data.version
          ? `${formatVersionDisplay(flowName, data.version)} is now the active published version.` 
          : "Your workflow is now active.",
      });
      setFlowStatus("published");
      setFlowIsEnabled(true);
      if (data.version) {
        setFlowVersion(data.version);
      }
      // Refresh flow data and versions
      queryClient.invalidateQueries({ queryKey: [FLOWS_PATH] });
      queryClient.invalidateQueries({ queryKey: [FLOWS_PATH, flowId] });
      queryClient.invalidateQueries({ queryKey: [FLOWS_PATH, flowId, "versions"] });
    },
    onError: (error) => {
      console.error("[FLOW PUBLISH] Failed:", error);
      if (error instanceof ApiError) {
        console.error("[FLOW PUBLISH] ApiError body:", error.body);
      }
      const formatted = formatApiErrorForToast(error);
      toast({
        title: formatted.title,
        description: formatted.description,
        variant: "destructive",
      });
    },
  });

  // Toggle active mutation - deactivates flow by archiving published version
  const toggleActiveMutation = useMutation({
    mutationFn: async () => {
      if (!flowId) throw new Error("Flow ID is required");
      const res = await apiRequest("POST", apiV1(`/flows/${flowId}/toggle-active/`), {});
      return await res.json();
    },
    onSuccess: (data) => {
      toast({
        title: "Flow deactivated",
        description: "The published version has been archived. Create a new version to reactivate.",
      });
      setFlowIsEnabled(false);
      if (data.version) {
        setFlowVersion(data.version);
      }
      // Refresh all flow data
      queryClient.invalidateQueries({ queryKey: [FLOWS_PATH] });
      queryClient.invalidateQueries({ queryKey: [FLOWS_PATH, flowId] });
      queryClient.invalidateQueries({ queryKey: [FLOWS_PATH, flowId, "versions"] });
    },
    onError: (error) => {
      toast({
        title: "Failed to deactivate flow",
        description: error instanceof Error ? error.message : "An error occurred",
        variant: "destructive",
      });
    },
  });

  // New version mutation - can create blank draft or clone from published
  const newVersionMutation = useMutation({
    mutationFn: async ({ clone = true }: { clone?: boolean } = {}) => {
      if (!flowId) throw new Error("Flow ID is required");
      const res = await apiRequest("POST", apiV1(`/flows/${flowId}/new-version/`), { 
        data: { clone } 
      });
      return await res.json();
    },
    onSuccess: (data) => {
      setIsNewVersionModalOpen(false);

      toast({
        title: "New version created",
        description: data.version
          ? `${formatVersionDisplay(flowName, data.version)} - you can now edit this flow.`
          : "Draft created - you can now edit this flow.",
      });

      if (data.version) {
        setFlowVersion(data.version);
      }

      // Refresh flow and reload graph
      flowDataLoadedRef.current = false;
      queryClient.invalidateQueries({ queryKey: [FLOWS_PATH] });
      queryClient.invalidateQueries({ queryKey: [FLOWS_PATH, flowId] });
      queryClient.invalidateQueries({ queryKey: [FLOWS_PATH, flowId, "versions"] });
    },
    onError: (error) => {
      toast({
        title: "Failed to create new version",
        description: error instanceof Error ? error.message : "An error occurred",
        variant: "destructive",
      });
    },
  });

  // Delete version mutation (unpublished versions only)
  const deleteVersionMutation = useMutation({
    mutationFn: async ({ versionId }: { versionId: string }) => {
      if (!flowId) throw new Error("Flow ID is required");
      // Expected REST shape (confirm backend): DELETE /flows/{flowId}/versions/{versionId}/
      const res = await apiRequest("DELETE", apiV1(`/flows/${flowId}/versions/${versionId}/`), {});
      // Some backends return 204 No Content; others return JSON.
      if (res.status === 204) return { ok: true };
      try {
        return await res.json();
      } catch {
        return { ok: res.ok };
      }
    },
    onSuccess: () => {
      toast({
        title: "Version deleted",
        description: "The version has been removed.",
      });
      setIsDeleteVersionDialogOpen(false);
      setVersionToDelete(null);
      queryClient.invalidateQueries({ queryKey: [FLOWS_PATH, flowId, "versions"] });
      queryClient.invalidateQueries({ queryKey: [FLOWS_PATH, flowId] });
    },
    onError: (error) => {
      console.error("[FLOW VERSION DELETE] Failed:", error);
      if (error instanceof ApiError) {
        console.error("[FLOW VERSION DELETE] ApiError body:", error.body);
      }
      const formatted = formatApiErrorForToast(error);
      toast({
        title: formatted.title || "Failed to delete version",
        description: formatted.description,
        variant: "destructive",
      });
    },
  });

  // Manual run mutation (trigger execution on published flow)
  const manualRunMutation = useMutation({
    mutationFn: async () => {
      if (!flowId) throw new Error("Flow ID is required");
      const res = await apiRequest("POST", apiV1(`/flows/${flowId}/manual-run/`), {});
      return await res.json();
    },
    onSuccess: (data) => {
      toast({
        title: "Manual run triggered",
        description: data.execution_id ? `Execution ${data.execution_id} started.` : "Execution started.",
      });
    },
    onError: (error) => {
      toast({
        title: "Failed to trigger manual run",
        description: error instanceof Error ? error.message : "An error occurred",
        variant: "destructive",
      });
    },
  });

  // Arm preview mutation (for draft versions - enables live testing)
  const armPreviewMutation = useMutation({
    mutationFn: async ({ versionId }: { versionId?: string } = {}) => {
      if (!flowId) throw new Error("Flow ID required");
      const id = versionId ?? flowVersion?.id;
      if (!id) throw new Error("Version ID required");
      const res = await apiRequest("POST", apiV1(`/flows/${flowId}/versions/${id}/arm/`), {});
      return await res.json();
    },
    onSuccess: (data) => {
      toast({
        title: "Preview armed",
        description: "This draft will now receive live events for testing.",
      });
      if (data.version) {
        setFlowVersion(data.version);
      }
      queryClient.invalidateQueries({ queryKey: [FLOWS_PATH, flowId] });
      queryClient.invalidateQueries({ queryKey: [FLOWS_PATH, flowId, "versions"] });
    },
    onError: (error) => {
      toast({
        title: "Failed to arm preview",
        description: error instanceof Error ? error.message : "An error occurred",
        variant: "destructive",
      });
    },
  });

  // Disarm preview mutation (stop receiving events)
  const disarmPreviewMutation = useMutation({
    mutationFn: async ({ versionId }: { versionId?: string } = {}) => {
      if (!flowId) throw new Error("Flow ID required");
      const id = versionId ?? flowVersion?.id;
      if (!id) throw new Error("Version ID required");
      const res = await apiRequest("POST", apiV1(`/flows/${flowId}/versions/${id}/disarm/`), {});
      return await res.json();
    },
    onSuccess: (data) => {
      toast({
        title: "Preview disarmed",
        description: "This draft will no longer receive live events.",
      });
      if (data.version) {
        setFlowVersion(data.version);
      }
      queryClient.invalidateQueries({ queryKey: [FLOWS_PATH, flowId] });
      queryClient.invalidateQueries({ queryKey: [FLOWS_PATH, flowId, "versions"] });
    },
    onError: (error) => {
      toast({
        title: "Failed to disarm preview",
        description: error instanceof Error ? error.message : "An error occurred",
        variant: "destructive",
      });
    },
  });

  // Preview flow mutation
  const previewFlowMutation = useMutation({
    mutationFn: async ({ payload = {} }: { payload?: any } = {}) => {
      if (!flowId) throw new Error("Flow must be saved before previewing");

      const endpoint = apiV1(`/flows/${flowId}/preview/`);
      console.log("[PREVIEW] ==================== PREVIEW START ====================");
      console.log("[PREVIEW] Endpoint:", endpoint);
      console.log("[PREVIEW] Flow ID:", flowId);
      console.log("[PREVIEW] Payload:", JSON.stringify(payload, null, 2));
      console.log("[PREVIEW] Timestamp:", new Date().toISOString());

      const res = await apiRequest("POST", endpoint, { data: { payload } });
      console.log("[PREVIEW] Response status:", res.status);
      console.log("[PREVIEW] Response headers:", Object.fromEntries(res.headers.entries()));

      const data = await res.json();
      console.log("[PREVIEW] Response data:", JSON.stringify(data, null, 2));
      console.log("[PREVIEW] run_id:", data.run_id);
      console.log("[PREVIEW] stream_url:", data.stream_url);
      console.log("[PREVIEW] ==================== PREVIEW END ====================");

      return data;
    },
    onSuccess: (data) => {
      console.log("[PREVIEW] Preview started successfully:", data);
      console.log("[PREVIEW] run_id:", data.run_id);

      const runId = data.run_id || data.id || `preview-${Date.now()}`;
      
      // Set the run ID to trigger WebSocket connection via useFlowPreviewStream hook
      console.log("[PREVIEW] Setting run ID for WebSocket stream:", runId);
      setPreviewRunId(runId);

      // Close payload dialog and clear state
      setIsPreviewPayloadDialogOpen(false);
      setPreviewPayload("");
      setPreviewPayloadError(null);

      // Open the event monitor instead of showing a toast
      setIsEventMonitorOpen(true);
    },
    onError: (error) => {
      console.error("[PREVIEW] Preview failed:", error);
      toast({
        title: "Preview failed",
        description: error instanceof Error ? error.message : "An error occurred",
        variant: "destructive",
      });
    },
  });

  // Poll preview status (backup for WebSocket)
  const previewStatusQuery = useQuery({
    queryKey: [FLOWS_PATH, flowId, "preview", previewRunId],
    queryFn: async () => {
      if (!flowId || !previewRunId) return null;
      return await fetchJson<{
        ok: boolean;
        run_id: string;
        status: string;
        started_at: string;
        finished_at: string | null;
        steps: Array<{
          node_id: string;
          node_name: string;
          status: string;
          started_at: string;
          finished_at: string | null;
          output?: any;
          error?: string;
        }>;
      }>(apiV1(`/flows/${flowId}/preview/${previewRunId}/`));
    },
    enabled: Boolean(flowId && previewRunId),
    refetchInterval: (query) => {
      const data = query.state.data;
      if (data?.status === "completed" || data?.status === "failed") {
        return false;
      }
      return 2000;
    },
  });

  const handleSave = () => {
    saveFlowMutation.mutate();
  };

  // Check if there's currently a published version that will be archived
  const hasCurrentPublishedVersion = allVersions.some(v => v.is_published);

  const handlePublish = () => {
    // If there's already a published version, show confirmation dialog
    if (hasCurrentPublishedVersion) {
      setIsPublishConfirmOpen(true);
    } else {
      // No existing published version, publish directly
      publishFlowMutation.mutate();
    }
  };

  const handleConfirmPublish = () => {
    publishFlowMutation.mutate();
  };

  const handlePreview = async () => {
    // Open payload dialog
    setIsPreviewPayloadDialogOpen(true);
    setPreviewPayload("");
    setPreviewPayloadError(null);
  };

  const handleConfirmPreview = async () => {
    let parsedPayload = {};
    if (previewPayload.trim()) {
      try {
        parsedPayload = JSON.parse(previewPayload);
        setPreviewPayloadError(null);
      } catch (error) {
        setPreviewPayloadError("Invalid JSON format");
        return;
      }
    }

    // Save flow first before preview
    try {
      await saveFlowMutation.mutateAsync();
      // After successful save, proceed with preview
      setIsPreviewArmed(true);
      console.log("[Preview] Preview armed");
      previewFlowMutation.mutate({ payload: parsedPayload });
    } catch (error) {
      // Save failed, error toast is already shown by saveFlowMutation.onError
      // Don't proceed with preview if save failed
      return;
    }
  };

  const handleExport = () => {
    const normalizedNodes = normalizeNodesForSave(nodes);

    const normalizedEdges = edges.map(edge => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      sourceHandle: edge.sourceHandle,
      targetHandle: edge.targetHandle,
      type: edge.type,
    }));

    const flowData = {
      name: flowName,
      description: flowDescription,
      config_schema: flowConfigSchema,
      config_values: flowConfigValues,
      nodes: normalizedNodes,
      edges: normalizedEdges,
    };

    const blob = new Blob([JSON.stringify(flowData, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${flowName.replace(/\s+/g, "_")}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  // Handle version selection from dropdown
  const handleVersionSelect = async (version: FlowVersion) => {
    console.log('[VERSION_SELECT] handleVersionSelect called with:', version.id, version.label, version.status);
    if (version.id === flowVersion?.id) {
      console.log('[VERSION_SELECT] Same version, skipping');
      return;
    }

    // Check for unsaved changes
    if (hasUnsavedChanges) {
      const confirmed = window.confirm(
        "You have unsaved changes. Switching versions will discard them. Continue?"
      );
      if (!confirmed) return;
    }

    try {
      // Set the new version immediately for UI feedback
      setFlowVersion(version);
      setHasUnsavedChanges(false);

      // Fetch the graph data for this version
      // The version endpoint doesn't include graph data, so we need to fetch the flow with version_id parameter
      // Try fetching from the main flow endpoint with version parameter first
      const versionEndpoint = apiV1(`/flows/${flowId}/?version_id=${version.id}&include_graph=1`);
      console.log('[VERSION_SELECT] Fetching version data from:', versionEndpoint);
      const rawVersionData = await fetchJson<any>(versionEndpoint);
      console.log('[VERSION_SELECT] Raw version data received:', JSON.stringify(rawVersionData).substring(0, 500));
      
      // Handle different response structures - API may return:
      // 1. { graph: { nodes, edges } } - direct graph
      // 2. { version: {...}, graph: { nodes, edges } } - with version info
      // 3. { nodes, edges } - flat structure at root
      const versionData = {
        graph: rawVersionData?.graph || 
               (rawVersionData?.nodes ? { nodes: rawVersionData.nodes, edges: rawVersionData.edges || [] } : null)
      };
      console.log('[VERSION_SELECT] Normalized version data:', versionData?.graph ? `${versionData.graph.nodes?.length || 0} nodes, ${versionData.graph.edges?.length || 0} edges` : 'NO GRAPH DATA');

      // Load the graph into canvas
      if (versionData?.graph) {
        // Load config schema/values (if provided)
        const configSchemaFromGraph = (versionData.graph as any)?.config_schema;
        const loadedSchema = configSchemaFromGraph !== undefined ? configSchemaFromGraph : null;
        if (configSchemaFromGraph !== undefined) {
          setFlowConfigSchema(configSchemaFromGraph);
          setFlowConfigSchemaText(JSON.stringify(configSchemaFromGraph, null, 2));
          setFlowConfigSchemaError(null);
        } else {
          setFlowConfigSchema(null);
          setFlowConfigSchemaText("");
          setFlowConfigSchemaError(null);
        }

        const configValuesFromGraph = (versionData.graph as any)?.config_values;
        const loadedValues =
          configValuesFromGraph && typeof configValuesFromGraph === "object" && !Array.isArray(configValuesFromGraph)
            ? (configValuesFromGraph as Record<string, unknown>)
            : {};
        if (configValuesFromGraph && typeof configValuesFromGraph === "object" && !Array.isArray(configValuesFromGraph)) {
          setFlowConfigValues(configValuesFromGraph as Record<string, unknown>);
          setFlowConfigValuesText(JSON.stringify(configValuesFromGraph, null, 2));
        } else {
          setFlowConfigValues({});
          setFlowConfigValuesText("{}");
        }

        // Validate loaded values (includes strict rule: values require schema)
        setFlowConfigValuesError(validateConfigValuesAgainstJsonSchema(loadedSchema, loadedValues));

        const ctxSchemaFromGraph = (versionData.graph as any)?.ctx_schema;
        if (ctxSchemaFromGraph !== undefined) {
          setCtxSchema(ctxSchemaFromGraph);
        } else {
          setCtxSchema(null);
        }

        const nodeDefinitions = nodeDefinitionsRef.current;
        
        // Transform backend nodes to ReactFlow format (same logic as initial load)
        const restoredNodes = (versionData.graph.nodes || []).map((backendNode: any) => {
          const nodeData: SerializableNodeData = {
            label: backendNode.name,
            type: backendNode.kind,
            config: backendNode.config || {},
            description: backendNode.description,
          };

          const mergedData = mergeNodeDataWithDefinitions(nodeData, nodeDefinitions);

          return {
            id: backendNode.id,
            type: "custom",
            position: { x: backendNode.x, y: backendNode.y },
            data: {
              ...mergedData,
              icon: mergedData.iconKey ? iconMap[mergedData.iconKey] : undefined,
              onConfig: handleNodeConfig,
              onDelete: handleNodeDelete,
              onAddElif: handleAddElif,
              onRemoveElif: handleRemoveElif,
            },
          } as Node<NodeData>;
        });

        // Transform backend edges to ReactFlow format
        const restoredEdges = (versionData.graph.edges || []).map((backendEdge: any) => {
          const sourceHandle = backendEdge.source_port || backendEdge.sourceHandle || "out";
          const sourceNode = restoredNodes.find((n: Node<NodeData>) => n.id === backendEdge.source);
          const isBranchEdge = sourceNode && isBranchNodeType(sourceNode.data.type);
          
          return {
            id: backendEdge.id,
            source: backendEdge.source,
            target: backendEdge.target,
            sourceHandle: sourceHandle,
            targetHandle: backendEdge.target_port || backendEdge.targetHandle,
            type: "custom",
            data: { 
              onDelete: handleEdgeDelete,
              sourceHandle: sourceHandle,
              isBranchEdge: isBranchEdge || false,
            } as CustomEdgeData,
          };
        });

        setNodes(restoredNodes);
        setEdges(restoredEdges);

        // Re-seed node ID counter
        let maxId = 0;
        versionData.graph.nodes.forEach((node: any) => {
          const match = node.id?.match(/node_(\d+)/);
          if (match) {
            const numId = parseInt(match[1], 10);
            if (numId > maxId) {
              maxId = numId;
            }
          }
        });
        nodeIdCounter.current = maxId + 1;
        triggerDataFlowRecalc();
        applyDefaultViewport();
      } else {
        // No graph data, start with empty canvas
        console.log('[VERSION_SELECT] NO GRAPH DATA - clearing nodes!');
        setNodes([]);
        setEdges([]);
        triggerDataFlowRecalc();
      }

      toast({
        title: "Version loaded",
        description: `Switched to ${formatVersionDisplay(flowName, version)}`,
      });
    } catch (error) {
      console.error("Failed to load version:", error);
      // Revert to previous version on error
      setFlowVersion(flowVersion);
      toast({
        title: "Failed to load version",
        description: "Could not load the selected version. Please try again.",
        variant: "destructive",
      });
    }
  };

  // Show error if definitions query fails
  if (definitionsQuery.isError) {
    return (
      <div className="h-full flex items-center justify-center bg-background p-4">
        <ErrorDisplay
          error={definitionsQuery.error}
          endpoint="flows/definitions/"
          action={{
            label: "Back to Automation Studio",
            onClick: () => navigate("/workflows"),
          }}
        />
      </div>
    );
  }

  // Show loading state
  if (definitionsQuery.isLoading) {
    return (
      <div className="h-full flex items-center justify-center bg-background">
        <div className="text-center space-y-4">
          <div className="animate-spin text-4xl">⚙️</div>
          <p className="text-muted-foreground">Loading flow definitions...</p>
        </div>
      </div>
    );
  }

  // Show error if flow query fails (when editing existing flow)
  if (flowId && flowQuery.isError) {
    return (
      <div className="h-full flex items-center justify-center bg-background p-4">
        <ErrorDisplay
          error={flowQuery.error}
          endpoint={`flows/${flowId}/`}
          action={{
            label: "Back to Automation Studio",
            onClick: () => navigate("/workflows"),
          }}
        />
      </div>
    );
  }

  return (
    <>
      <div className="h-full min-h-0 w-full flex overflow-hidden">
        {/* Left Sidebar - Node Palette */}
        <NodePalette 
          onNodeDragStart={onNodeDragStart}
          paletteData={definitionsQuery.data?.palette}
          nodeDefinitions={definitionsQuery.data?.node_definitions}
        />

        {/* Main Canvas Area */}
        <div className="flex-1 flex flex-col min-w-0 min-h-0">
          {/* Top Toolbar */}
          <div className="flex flex-col gap-2 px-3 py-2 border-b bg-background sm:flex-row sm:items-center sm:justify-between min-w-0">
            <div className="flex items-center gap-3 min-w-0 flex-1">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => navigate("/workflows")}
                data-testid="button-back"
              >
                <ArrowLeft className="h-4 w-4" />
              </Button>
              <div className="flex flex-col min-w-0">
                <Input
                  value={flowName}
                  onChange={(e) => setFlowName(e.target.value)}
                  className="font-semibold text-base border-0 shadow-none focus-visible:ring-0 px-2 h-auto py-1 w-[220px] sm:w-[280px] md:w-[360px] max-w-full"
                  placeholder="Workflow name"
                  disabled={flowVersion ? !flowVersion.is_editable : false}
                  data-testid="input-flow-name"
                />
                <div className="flex items-center gap-2 ml-2 mt-1">
                  {flowVersion ? (
                    <>
                      {/* Version Selector Dropdown */}
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="outline" size="sm" className="h-6 px-2 text-xs gap-1" data-testid="dropdown-version-selector">
                            {flowVersion.label}
                            <ChevronDown className="h-3 w-3" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="start" className="w-56">
                          {filterRelevantVersions(allVersions).filter(v => v.is_editable || v.is_published).map(v => (
                            <DropdownMenuItem
                              key={v.id}
                              onClick={() => handleVersionSelect(v)}
                              className={flowVersion?.id === v.id ? "bg-accent" : ""}
                              data-testid={`menu-version-${v.id}`}
                            >
                              <div className="flex items-center justify-between w-full">
                                <span>{formatVersionDisplay(flowName, v, allVersions)}</span>
                                <div className="flex items-center gap-1">
                                  {v.is_published && <Badge variant="default" className="text-xs h-4">Published</Badge>}
                                  {v.is_editable && !v.is_published && <Badge variant="outline" className="text-xs h-4">Draft</Badge>}
                                  {v.preview_armed && <Shield className="h-3 w-3 text-amber-600" />}
                                </div>
                              </div>
                            </DropdownMenuItem>
                          ))}
                          {filterRelevantVersions(allVersions).filter(v => v.is_editable || v.is_published).length === 0 && (
                            <DropdownMenuItem disabled>No versions available</DropdownMenuItem>
                          )}
                        </DropdownMenuContent>
                      </DropdownMenu>
                      {flowVersion.is_published ? (
                        <Badge variant={flowVersion.is_active ? "default" : "secondary"}>
                          {flowVersion.is_active ? "Active" : "Inactive"}
                        </Badge>
                      ) : (
                        <Badge variant="outline">Draft</Badge>
                      )}
                      {!flowVersion.is_editable && (
                        <Badge variant="secondary" className="text-xs">Locked</Badge>
                      )}
                      {flowVersion.preview_armed && (
                        <Badge variant="outline" className="text-xs text-amber-600 border-amber-500">
                          <Shield className="h-3 w-3 mr-1" />
                          Armed
                        </Badge>
                      )}
                    </>
                  ) : flowStatus && (
                    <Badge variant={flowStatus === "active" ? "default" : "outline"}>
                      {flowStatus}
                    </Badge>
                  )}
                </div>
              </div>
            </div>
            <div className="flex items-center gap-2 flex-wrap justify-end sm:flex-nowrap flex-shrink-0">
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setIsPropertiesOpen(true)}
                    data-testid="button-properties"
                  >
                    <Settings className="h-4 w-4" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>Flow Properties</TooltipContent>
              </Tooltip>
              {flowId && (
                <>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setIsVersionHistoryOpen(true)}
                        data-testid="button-version-history"
                      >
                        <History className="h-4 w-4" />
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent>Version History</TooltipContent>
                  </Tooltip>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setIsExecutionHistoryOpen(true)}
                        data-testid="button-execution-history"
                      >
                        <Clock className="h-4 w-4" />
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent>Execution History</TooltipContent>
                  </Tooltip>
                </>
              )}
              <Button
                variant="outline"
                size="sm"
                onClick={handleExport}
                data-testid="button-export"
              >
                <Download className="h-4 w-4" />
              </Button>
              {flowVersion?.is_published ? (
                <>
                  {/* Monitor button for published flows - opens execution monitor */}
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setIsEventMonitorOpen(true)}
                    data-testid="button-monitor"
                  >
                    <Activity className="h-4 w-4 mr-2" />
                    <span className="hidden sm:inline">Monitor</span>
                  </Button>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => toggleActiveMutation.mutate()}
                        disabled={toggleActiveMutation.isPending}
                        data-testid="button-toggle-active"
                      >
                        <Zap className="h-4 w-4 mr-2" />
                        {flowVersion.is_active ? "Deactivate" : "Activate"}
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent>
                      {flowVersion.is_active ? "Stop receiving events" : "Start receiving events"}
                    </TooltipContent>
                  </Tooltip>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button
                        size="sm"
                        onClick={() => setIsNewVersionModalOpen(true)}
                        disabled={newVersionMutation.isPending}
                        data-testid="button-new-version"
                      >
                        <GitBranch className="h-4 w-4 mr-2" />
                        New Version
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent>Create a new editable draft version</TooltipContent>
                  </Tooltip>
                </>
              ) : (
                <>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handlePreview}
                    disabled={!flowId || previewFlowMutation.isPending || saveFlowMutation.isPending}
                    data-testid="button-preview"
                  >
                    <Eye className="h-4 w-4 mr-2" />
                    Preview
                  </Button>
                  {flowId && flowVersion && !flowVersion.is_published && flowVersion.is_editable && (
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Button
                          variant={flowVersion.preview_armed ? "default" : "outline"}
                          size="sm"
                          onClick={async () => {
                            if (flowVersion.preview_armed) {
                              disarmPreviewMutation.mutate({ versionId: flowVersion.id });
                            } else {
                              // Save flow first before arming
                              try {
                                const saveOutcome: any = await saveFlowMutation.mutateAsync();
                                const savedId =
                                  saveOutcome?.version?.id ??
                                  saveOutcome?.saveResult?.version?.id ??
                                  saveOutcome?.saveResult?.version_id ??
                                  flowVersion?.id;
                                // After successful save, proceed with arm using the saved draft version id
                                armPreviewMutation.mutate({ versionId: savedId });
                              } catch (error) {
                                // Save failed, error toast is already shown by saveFlowMutation.onError
                                // Don't proceed with arm if save failed
                                return;
                              }
                            }
                          }}
                          disabled={armPreviewMutation.isPending || disarmPreviewMutation.isPending || saveFlowMutation.isPending}
                          data-testid="button-arm-preview"
                        >
                          {flowVersion.preview_armed ? (
                            <>
                              <ShieldOff className="h-4 w-4 mr-2" />
                              Disarm
                            </>
                          ) : (
                            <>
                              <Shield className="h-4 w-4 mr-2" />
                              {saveFlowMutation.isPending ? "Saving..." : "Arm Preview"}
                            </>
                          )}
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent>
                        {flowVersion.preview_armed
                          ? "Stop receiving live events for testing"
                          : "Enable live event testing for this draft"}
                      </TooltipContent>
                    </Tooltip>
                  )}
                  <Button
                    size="sm"
                    onClick={handlePublish}
                    disabled={!flowId || publishFlowMutation.isPending}
                    className="bg-amber-400 hover:bg-amber-500 text-amber-950"
                    data-testid="button-publish"
                  >
                    <Rocket className="h-4 w-4 mr-2" />
                    Publish
                  </Button>
                  <div className="flex items-center gap-2">
                    {hasUnsavedChanges && !saveFlowMutation.isPending && !flowVersion?.is_published && (
                      <span className="text-xs text-muted-foreground">
                        Unsaved changes
                      </span>
                    )}
                    <Button
                      size="sm"
                      onClick={handleSave}
                      disabled={saveFlowMutation.isPending || (flowVersion ? !flowVersion.is_editable : false)}
                      data-testid="button-save"
                    >
                      <Save className="h-4 w-4 mr-2" />
                      {saveFlowMutation.isPending ? "Saving..." : "Save"}
                    </Button>
                  </div>
                </>
              )}
            </div>
          </div>

          {/* ReactFlow Canvas */}
          <div className="flex-1 min-h-0 bg-muted/20 overflow-hidden">
            <ReactFlow
              nodes={nodes}
              edges={edges}
              onNodesChange={handleNodesChangeWithTracking}
              onEdgesChange={handleEdgesChangeWithTracking}
              onConnect={onConnect}
              onNodeClick={onNodeClick}
              onDrop={canEditFlow ? onDrop : undefined}
              onDragOver={canEditFlow ? onDragOver : undefined}
              nodeTypes={nodeTypes}
              edgeTypes={edgeTypes}
              nodesDraggable={canEditFlow}
              nodesConnectable={canEditFlow}
              edgesUpdatable={canEditFlow}
              elementsSelectable={true}
              defaultEdgeOptions={{
                type: "custom",
                animated: false,
              }}
              defaultViewport={{ x: 0, y: 0, zoom: 0.75 }}
              minZoom={0.1}
              maxZoom={2}
              className="bg-muted/10"
            >
              <Background variant={BackgroundVariant.Dots} gap={20} size={1.5} className="[&>*]:stroke-muted-foreground/30" />
              <Controls className="bg-background border rounded-lg shadow-sm" />
              <MiniMap
                className="bg-background border rounded-lg shadow-sm"
                nodeColor={(node) => {
                  const category = (node.data as NodeData).type.split("_")[0];
                  const colors: Record<string, string> = {
                    trigger: "#3b82f6",
                    action: "#22c55e",
                    logic: "#a855f7",
                    output: "#ec4899",
                    tool: "#14b8a6",
                  };
                  return colors[category] || "#64748b";
                }}
              />
              <Panel position="bottom-left" className="bg-background/95 border rounded-lg p-2 shadow-sm">
                <div className="text-xs text-muted-foreground space-y-0.5">
                  <div>Nodes: {nodes.length}</div>
                  <div>Connections: {edges.length}</div>
                </div>
              </Panel>
            </ReactFlow>
          </div>
        </div>
      </div>

      {/* Node Configuration Dialog */}
      <Dialog open={isConfigOpen} onOpenChange={setIsConfigOpen}>
        <DialogContent className="max-w-4xl max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Configure Node</DialogTitle>
            <DialogDescription>
              Adjust node properties and behavior
            </DialogDescription>
          </DialogHeader>
          {selectedNode && (
            <div className="space-y-4 py-2">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label htmlFor="node-label">Label</Label>
                  <Input
                    id="node-label"
                    value={selectedNode.data.label}
                    onChange={(e) => updateSelectedNode({ label: e.target.value })}
                    disabled={!canEditFlow}
                    data-testid="input-node-label"
                  />
                  {!canEditFlow && (
                    <p className="text-xs text-muted-foreground mt-1">
                      This flow version is locked (read-only). You can view configuration but cannot edit nodes or edges.
                    </p>
                  )}
                </div>
                <div>
                  <Label htmlFor="node-type">Type</Label>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Input
                        id="node-type"
                        value={selectedNode.data.type}
                        disabled
                        className="bg-muted cursor-help"
                      />
                    </TooltipTrigger>
                    <TooltipContent side="bottom" className="max-w-xs">
                      <p className="text-sm">{selectedNode.data.description || "Node-specific settings for " + selectedNode.data.type}</p>
                    </TooltipContent>
                  </Tooltip>
                </div>
              </div>

              <Tabs defaultValue="configuration" className="w-full mt-2">
                <TabsList className="grid w-full grid-cols-3">
                  <TabsTrigger value="configuration" data-testid="tab-configuration">Configuration</TabsTrigger>
                  <TabsTrigger value="input-data" data-testid="tab-input-data">Input Data</TabsTrigger>
                  <TabsTrigger value="output-data" data-testid="tab-output-data">Output Data</TabsTrigger>
                </TabsList>
                
                <TabsContent value="configuration" className="mt-4">
                  <div className="p-3 bg-muted/50 rounded-md">
                    {(() => {
                      const currentNode = nodes.find((n) => n.id === selectedNode.id) ?? selectedNode;
                      const rawFields = flattenDataNodes((currentNode.data as any).availableData || []);
                      const { scope, fields } = getVisibleFieldsForNode(currentNode.id, rawFields);
                      return (
                        <fieldset disabled={!canEditFlow} className={!canEditFlow ? "opacity-70" : ""}>
                          <DynamicNodeConfigForm
                            formComponent={selectedNode.data.formComponent}
                            nodeType={selectedNode.data.type}
                            config={selectedNode.data.config || {}}
                            onConfigChange={(newConfig) => updateSelectedNode({ config: newConfig })}
                            availableData={fields}
                            dataNodes={fields}
                            hints={selectedNode.data.hints}
                            scope={scope}
                          />
                        </fieldset>
                      );
                    })()}
                  </div>
                </TabsContent>
                
                <TabsContent value="input-data" className="mt-4">
                  <div className="p-3 bg-muted/50 rounded-md">
                    {(() => {
                      const currentNode = nodes.find((n) => n.id === selectedNode.id) ?? selectedNode;
                      const nodeType = currentNode.data.type;
                      const isTrigger =
                        nodeType.startsWith("trigger_") ||
                        nodeType === "webhook" ||
                        nodeType === "event" ||
                        nodeType === "scheduled" ||
                        nodeType === "trigger_webhook" ||
                        nodeType === "trigger_event" ||
                        nodeType === "trigger_scheduled";
                      const isNormalize = nodeType === "logic_normalize" || nodeType === "normalize";

                      const nodeDefinitions =
                        (definitionsQuery.data?.node_definitions as unknown as Record<string, BackendNodeDefinition>) || {};

                      const dedupeByKey = (arr: any[]) => {
                        const seen = new Set<string>();
                        const out: any[] = [];
                        for (const f of arr) {
                          const k = String(f?.key ?? "");
                          if (!k || seen.has(k)) continue;
                          seen.add(k);
                          out.push(f);
                        }
                        return out;
                      };

                      let fields: any[] = [];
                      let emptyMessage = "No input available.";

                      if (isTrigger) {
                        // Triggers do not receive input (they originate input.body.*)
                        fields = [];
                        emptyMessage = "Triggers do not receive input.";
                      } else if (isNormalize) {
                        // Normalize can map from upstream node outputs + trigger input + config.*
                        const incomingEdges = edges.filter((e) => e.target === currentNode.id);
                        const incomingFields = incomingEdges.flatMap((e) =>
                          getEdgeDataPreview(
                            e,
                            nodes as Node<CustomNodeData>[],
                            nodeDefinitions,
                            dataFlowCacheRef.current
                          )
                        );
                        const merged = dedupeByKey([...incomingFields, ...configFieldsForUI]);
                        fields = merged.filter((f) => {
                          const k = String(f?.key ?? "");
                          return (
                            k === "input.body" ||
                            k.startsWith("input.body.") ||
                            k.startsWith("nodes.") ||
                            k === "config" ||
                            k.startsWith("config.")
                          );
                        });
                        emptyMessage = "No upstream data available. Connect a Trigger (and/or nodes) upstream.";
                      } else {
                        // Most nodes operate in ctx-mode: they read ctx.* + config.* only if Normalize exists upstream.
                        const { scope, fields: visible } = getVisibleFieldsForNode(currentNode.id, []);
                        fields = dedupeByKey(visible);
                        emptyMessage = scope?.canSeeCtx
                          ? "No input fields available."
                          : "No data available for this node scope. Add a Normalize node upstream to define ctx.*.";
                      }

                      if (fields.length === 0) {
                        return (
                          <p className="text-sm text-muted-foreground text-center py-4">{emptyMessage}</p>
                        );
                      }
                      return (
                      <ScrollArea className="h-[400px]">
                        <div className="space-y-2 pr-4">
                          {fields.map((field: any) => (
                            <div
                              key={field.key}
                              className="flex items-start justify-between gap-4 p-2 bg-background/50 rounded border border-border/50 text-xs"
                            >
                              <div className="flex-1">
                                <code className="font-mono text-foreground">{field.key}</code>
                                {field.description && (
                                  <div className="text-xs text-muted-foreground mt-1 italic">
                                    {field.description}
                                  </div>
                                )}
                              </div>
                              <Badge variant="secondary" className="flex-shrink-0">
                                {field.type}
                              </Badge>
                            </div>
                          ))}
                        </div>
                      </ScrollArea>
                      );
                    })()}
                  </div>
                </TabsContent>

                <TabsContent value="output-data" className="mt-4">
                  <div className="p-3 bg-muted/50 rounded-md">
                    {(() => {
                      const currentNode = nodes.find((n) => n.id === selectedNode.id) ?? selectedNode;
                      const nodeType = currentNode.data.type;
                      const isTrigger =
                        nodeType.startsWith("trigger_") ||
                        nodeType === "webhook" ||
                        nodeType === "event" ||
                        nodeType === "scheduled" ||
                        nodeType === "trigger_webhook" ||
                        nodeType === "trigger_event" ||
                        nodeType === "trigger_scheduled";
                      const isNormalize = nodeType === "logic_normalize" || nodeType === "normalize";

                      const dedupeByKey = (arr: any[]) => {
                        const seen = new Set<string>();
                        const out: any[] = [];
                        for (const f of arr) {
                          const k = String(f?.key ?? "");
                          if (!k || seen.has(k)) continue;
                          seen.add(k);
                          out.push(f);
                        }
                        return out;
                      };

                      const raw = dataFlowCacheRef.current.get(currentNode.id) || [];
                      let fields: any[] = [];
                      let nodeOutputFields: any[] | null = null;
                      let passthroughFields: any[] | null = null;
                      let emptyMessage = "No output available.";

                      if (isNormalize) {
                        // Normalize defines ctx.* for downstream
                        fields = dedupeByKey(ctxFieldsForUI);
                        emptyMessage = "No ctx schema available yet. Configure Normalize mappings to define ctx.*.";
                      } else if (isTrigger) {
                        // Triggers produce input.body.* (the canonical input namespace)
                        fields = dedupeByKey(raw).filter((f) => {
                          const k = String(f?.key ?? "");
                          return k === "input.body" || k.startsWith("input.body.");
                        });
                        emptyMessage = "No trigger output schema available.";
                      } else {
                        // Actions/tools/etc: downstream receives the full (passthrough + any added fields) set.
                        const prefix = `nodes.${currentNode.id}.output.`;
                        const all = dedupeByKey(raw);
                        const own = all.filter((f) => String(f?.key ?? "").startsWith(prefix));
                        const { scope } = getVisibleFieldsForNode(currentNode.id, []);

                        // If this node operates in ctx-mode, treat ctx.* as the passthrough contract
                        // (input.* is not visible once Normalize exists upstream).
                        const passthrough =
                          scope?.canSeeCtx
                            ? dedupeByKey([...ctxFieldsForUI, ...configFieldsForUI])
                            : all.filter((f) => !String(f?.key ?? "").startsWith(prefix));
                        nodeOutputFields = own;
                        passthroughFields = passthrough;
                        fields = [...own, ...passthrough];
                        emptyMessage = "No output data available (schema unknown or no upstream).";
                      }

                      if (fields.length === 0) {
                        return (
                          <p className="text-sm text-muted-foreground text-center py-4">{emptyMessage}</p>
                        );
                      }

                      const renderField = (field: any) => (
                        <div
                          key={field.key}
                          className="flex items-start justify-between gap-4 p-2 bg-background/50 rounded border border-border/50 text-xs"
                        >
                          <div className="flex-1">
                            <code className="font-mono text-foreground">{field.key}</code>
                            {field.description && (
                              <div className="text-xs text-muted-foreground mt-1 italic">
                                {field.description}
                              </div>
                            )}
                          </div>
                          <Badge variant="secondary" className="flex-shrink-0">
                            {field.type}
                          </Badge>
                        </div>
                      );

                      const renderSection = (title: string, subtitle: string | null, list: any[]) => (
                        <div className="space-y-2">
                          <div className="flex items-baseline justify-between gap-2">
                            <div className="text-xs font-semibold text-muted-foreground">{title}</div>
                            <Badge variant="outline" className="text-[10px]">{list.length}</Badge>
                          </div>
                          {subtitle && (
                            <div className="text-[11px] text-muted-foreground">
                              {subtitle}
                            </div>
                          )}
                          <div className="space-y-2">
                            {list.map(renderField)}
                          </div>
                        </div>
                      );

                      return (
                        <ScrollArea className="h-[400px]">
                          <div className="space-y-4 pr-4">
                            {nodeOutputFields && passthroughFields ? (
                              <>
                                {nodeOutputFields.length > 0
                                  ? renderSection(
                                      "Node Output",
                                      `Fields produced by this node (nodes.${currentNode.id}.output.*)`,
                                      nodeOutputFields
                                    )
                                  : (
                                    <div className="text-sm text-muted-foreground text-center py-3">
                                      No node-specific output fields.
                                    </div>
                                  )}

                                {passthroughFields.length > 0
                                  ? renderSection(
                                      "Passthrough",
                                      "Fields forwarded from upstream.",
                                      passthroughFields
                                    )
                                  : (
                                    <div className="text-sm text-muted-foreground text-center py-3">
                                      No passthrough fields.
                                    </div>
                                  )}
                              </>
                            ) : (
                              <div className="space-y-2">
                                {fields.map(renderField)}
                              </div>
                            )}
                          </div>
                        </ScrollArea>
                      );
                    })()}
                  </div>
                </TabsContent>
              </Tabs>

              <div className="flex justify-between pt-4 border-t gap-2">
                <Button
                  variant="destructive"
                  onClick={() => {
                    setIsDeleteDialogOpen(true);
                  }}
                  disabled={!canEditFlow}
                  data-testid="button-delete-node"
                >
                  <Trash2 className="h-4 w-4 mr-2" />
                  Delete
                </Button>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    onClick={() => setIsConfigOpen(false)}
                    data-testid="button-cancel-config"
                  >
                    Cancel
                  </Button>
                  {canEditFlow ? (
                    <Button onClick={handleConfigDone}>Done</Button>
                  ) : (
                    <Button onClick={() => setIsConfigOpen(false)}>Close</Button>
                  )}
                </div>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Flow Properties Dialog */}
      <Dialog open={isPropertiesOpen} onOpenChange={setIsPropertiesOpen}>
        <DialogContent className="max-w-2xl max-h-[90vh] flex flex-col">
          <DialogHeader>
            <DialogTitle>Flow Properties</DialogTitle>
            <DialogDescription>
              Configure the properties and settings for this workflow
            </DialogDescription>
          </DialogHeader>
          <Tabs defaultValue="general" className="w-full flex-1 min-h-0">
            <TabsList className="grid w-full grid-cols-2">
              <TabsTrigger value="general" data-testid="tab-flow-properties-general">General</TabsTrigger>
              <TabsTrigger value="config" data-testid="tab-flow-properties-config">Config</TabsTrigger>
            </TabsList>

            <TabsContent value="general" className="mt-4 flex-1 min-h-0">
              <ScrollArea className="h-[55vh] pr-4">
                <div className="space-y-4 pb-4">
                  <div>
                    <Label htmlFor="prop-name">Workflow Name</Label>
                    <Input
                      id="prop-name"
                      value={flowName}
                      onChange={(e) => setFlowName(e.target.value)}
                      placeholder="Enter workflow name"
                      className="mt-2"
                      data-testid="input-prop-name"
                      disabled={!canEditFlow}
                    />
                  </div>
                  <div>
                    <Label htmlFor="prop-description">Description</Label>
                    <Textarea
                      id="prop-description"
                      value={flowDescription}
                      onChange={(e) => setFlowDescription(e.target.value)}
                      placeholder="Describe what this workflow does..."
                      rows={6}
                      className="mt-2"
                      data-testid="textarea-prop-description"
                      disabled={!canEditFlow}
                    />
                  </div>
                  <div className="flex items-center justify-between p-4 border rounded-lg">
                    <div className="space-y-1">
                      <Label htmlFor="prop-enabled" className="text-base">Enable Workflow</Label>
                      <p className="text-sm text-muted-foreground">
                        When enabled, this workflow will be active and can process events
                      </p>
                    </div>
                    <Switch
                      id="prop-enabled"
                      checked={flowIsEnabled}
                      onCheckedChange={setFlowIsEnabled}
                      data-testid="switch-prop-enabled"
                    />
                  </div>
                </div>
              </ScrollArea>
            </TabsContent>

            <TabsContent value="config" className="mt-4 flex-1 min-h-0">
              <ScrollArea className="h-[55vh] pr-4">
                <div className="space-y-4 pb-4">
                  <div>
                    <div className="flex items-center justify-between gap-2">
                      <Label htmlFor="prop-config-schema">Config Schema (JSON Schema)</Label>
                      <Button
                        variant="outline"
                        size="sm"
                        className="h-7 text-xs"
                        onClick={() => {
                          // Only generate if current values are valid JSON object and non-empty
                          const keys = Object.keys(flowConfigValues || {});
                          if (keys.length === 0) {
                            toast({
                              title: "Nothing to infer",
                              description: "config_values is empty.",
                            });
                            return;
                          }
                          if (flowConfigValuesError && flowConfigValuesError !== "config_values provided without config_schema") {
                            toast({
                              title: "Fix config_values first",
                              description: flowConfigValuesError,
                              variant: "destructive",
                            });
                            return;
                          }

                          const schema = inferConfigSchemaFromValues(flowConfigValues);
                          setFlowConfigSchema(schema);
                          setFlowConfigSchemaText(JSON.stringify(schema, null, 2));
                          setFlowConfigSchemaError(null);
                          setFlowConfigValuesError(validateConfigValuesAgainstJsonSchema(schema, flowConfigValues));

                        if (flowDataLoadedRef.current && canEditFlow) {
                            setHasUnsavedChanges(true);
                            triggerDataFlowRecalc();
                          }

                          toast({
                            title: "Schema generated",
                            description: "config_schema was inferred from config_values.",
                          });
                        }}
                        disabled={!canEditFlow}
                        data-testid="button-generate-config-schema"
                        title="Generate a strict config_schema from current config_values"
                      >
                        <Sparkles className="h-3.5 w-3.5 mr-1" />
                        Generate from values
                      </Button>
                    </div>
                    <Textarea
                      id="prop-config-schema"
                      value={flowConfigSchemaText}
                      onChange={(e) => {
                        if (!canEditFlow) return;
                        const nextText = e.target.value;
                        setFlowConfigSchemaText(nextText);

                        if (!nextText.trim()) {
                          setFlowConfigSchema(null);
                          setFlowConfigSchemaError(null);
                          // Re-validate values without schema constraints
                          setFlowConfigValuesError(null);
                          if (flowDataLoadedRef.current && canEditFlow) {
                            setHasUnsavedChanges(true);
                            triggerDataFlowRecalc();
                          }
                          return;
                        }

                        try {
                          const parsed = JSON.parse(nextText);
                          if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
                            setFlowConfigSchemaError("config_schema must be a JSON object (JSON Schema).");
                            return;
                          }
                          setFlowConfigSchema(parsed);
                          setFlowConfigSchemaError(null);

                          // Validate current values against new schema
                          const schemaErr = validateConfigValuesAgainstJsonSchema(parsed, flowConfigValues);
                          setFlowConfigValuesError(schemaErr);
                          if (flowDataLoadedRef.current && canEditFlow) {
                            setHasUnsavedChanges(true);
                            triggerDataFlowRecalc();
                          }
                        } catch {
                          setFlowConfigSchemaError("Invalid JSON.");
                        }
                      }}
                      placeholder='{"type":"object","properties":{"support_phone":{"type":"string"}}}'
                      rows={8}
                      className={`mt-2 font-mono text-sm ${flowConfigSchemaError ? "border-destructive" : ""}`}
                      data-testid="textarea-prop-config-schema"
                      disabled={!canEditFlow}
                    />
                    {flowConfigSchemaError ? (
                      <p className="text-sm text-destructive mt-2" data-testid="text-prop-config-schema-error">
                        {flowConfigSchemaError}
                      </p>
                    ) : (
                      <p className="text-xs text-muted-foreground mt-2">
                        Declares available keys/types under <code>config.*</code>. Versioned with the flow.
                      </p>
                    )}
                  </div>

                  <div>
                    <Label htmlFor="prop-config-values">Config Values (JSON object)</Label>
                    <Textarea
                      id="prop-config-values"
                      value={flowConfigValuesText}
                      onChange={(e) => {
                        if (!canEditFlow) return;
                        const nextText = e.target.value;
                        setFlowConfigValuesText(nextText);

                        if (!nextText.trim()) {
                          setFlowConfigValues({});
                          setFlowConfigValuesError(null);
                          if (flowDataLoadedRef.current && canEditFlow) {
                            setHasUnsavedChanges(true);
                            triggerDataFlowRecalc();
                          }
                          return;
                        }

                        try {
                          const parsed = JSON.parse(nextText);
                          if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
                            setFlowConfigValuesError("config_values must be a JSON object.");
                            return;
                          }

                          // Enforce: values are constants (no placeholders / no references)
                          const serialized = JSON.stringify(parsed);
                          if (/\{\{|\$\{/.test(serialized) || /\b(input|nodes|system)\./.test(serialized)) {
                            setFlowConfigValuesError("config_values must be literals only (no {{}} / ${} / input.* / nodes.* / system.* references).");
                            return;
                          }

                          setFlowConfigValues(parsed as Record<string, unknown>);
                          const schemaErr = validateConfigValuesAgainstJsonSchema(flowConfigSchema, parsed);
                          setFlowConfigValuesError(schemaErr);
                          if (flowDataLoadedRef.current && canEditFlow) {
                            setHasUnsavedChanges(true);
                            triggerDataFlowRecalc();
                          }
                        } catch {
                          setFlowConfigValuesError("Invalid JSON.");
                        }
                      }}
                      placeholder='{"support_phone":"+15551234567","enable_whatsapp":true}'
                      rows={8}
                      className={`mt-2 font-mono text-sm ${flowConfigValuesError ? "border-destructive" : ""}`}
                      data-testid="textarea-prop-config-values"
                      disabled={!canEditFlow}
                    />
                    {flowConfigValuesError ? (
                      <p className="text-sm text-destructive mt-2" data-testid="text-prop-config-values-error">
                        {flowConfigValuesError}
                      </p>
                    ) : (
                      <p className="text-xs text-muted-foreground mt-2">
                        Available in expressions as <code>config.&lt;key&gt;</code>. Read-only and deterministic.
                      </p>
                    )}
                  </div>
                </div>
              </ScrollArea>
            </TabsContent>
          </Tabs>

          <div className="flex items-center justify-between pt-3 border-t mt-3">
            <div className="text-sm text-muted-foreground">
              Status: <Badge variant={flowStatus === "active" ? "default" : "outline"}>{flowStatus}</Badge>
            </div>
            <DialogFooter className="gap-2">
              <Button variant="outline" onClick={() => setIsPropertiesOpen(false)} data-testid="button-cancel-properties">
                Cancel
              </Button>
              <Button
                onClick={() => {
                  setIsPropertiesOpen(false);
                  handleSave();
                }}
                disabled={!canEditFlow || !!flowConfigSchemaError || !!flowConfigValuesError}
                data-testid="button-save-properties"
              >
                Save
              </Button>
            </DialogFooter>
          </div>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <AlertDialog open={isDeleteDialogOpen} onOpenChange={setIsDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Node?</AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently delete the node "{selectedNode?.data.label}" and all its connections. This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel data-testid="button-cancel-delete">Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                deleteSelectedNode();
                setIsDeleteDialogOpen(false);
              }}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              data-testid="button-confirm-delete"
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Delete Version Confirmation Dialog */}
      <AlertDialog open={isDeleteVersionDialogOpen} onOpenChange={setIsDeleteVersionDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Version?</AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently delete{" "}
              <span className="font-medium">
                {versionToDelete ? formatVersionDisplay(flowName, versionToDelete, versionsQuery.data?.versions) : "this version"}
              </span>
              . This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel
              onClick={() => setVersionToDelete(null)}
              disabled={deleteVersionMutation.isPending}
              data-testid="button-cancel-delete-version"
            >
              Cancel
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                if (!versionToDelete?.id) return;
                deleteVersionMutation.mutate({ versionId: versionToDelete.id });
              }}
              disabled={!versionToDelete?.id || deleteVersionMutation.isPending}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              data-testid="button-confirm-delete-version"
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Event Monitor */}
      <MiniWSDebugger
        isConnected={flowPreviewStream.isConnected}
        latestEvent={latestWsEvent}
        isOpen={isEventMonitorOpen}
        onOpenChange={setIsEventMonitorOpen}
        flowId={flowId}
        versionId={flowVersion?.id}
      />

      {/* Version History Sheet */}
      <Sheet open={isVersionHistoryOpen} onOpenChange={setIsVersionHistoryOpen}>
        <SheetContent className="sm:max-w-md">
          <SheetHeader>
            <SheetTitle className="flex items-center gap-2">
              <GitBranch className="h-5 w-5" />
              Version History
            </SheetTitle>
            <SheetDescription>
              View and manage workflow versions
            </SheetDescription>
          </SheetHeader>
          <ScrollArea className="h-[calc(100vh-10rem)] mt-4">
            {versionsQuery.isLoading ? (
              <div className="flex items-center justify-center py-8">
                <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-primary" />
              </div>
            ) : versionsQuery.error ? (
              <div className="text-sm text-destructive p-4">
                Failed to load versions
              </div>
            ) : (
              <div className="space-y-2 pr-4">
                {filterRelevantVersions(versionsQuery.data?.versions || []).map((version) => (
                  <div
                    key={version.id}
                    className={`p-3 rounded-lg border ${
                      flowVersion?.id === version.id 
                        ? "border-primary bg-primary/5" 
                        : version.status === "archived"
                        ? "border-border/50 opacity-60"
                        : "border-border hover-elevate"
                    }`}
                    data-testid={`version-item-${version.id}`}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <span className="font-medium">{formatVersionDisplay(flowName, version, versionsQuery.data?.versions)}</span>
                        {flowVersion?.id === version.id && (
                          <Badge variant="outline" className="text-xs">Current</Badge>
                        )}
                      </div>
                      <div className="flex items-center gap-1">
                        {version.status === "archived" ? (
                          <Badge variant="secondary" className="text-xs">Archived</Badge>
                        ) : version.is_published ? (
                          <Badge variant={version.is_active ? "default" : "secondary"} className="text-xs">
                            {version.is_active ? "Active" : "Inactive"}
                          </Badge>
                        ) : version.status === "armed" ? (
                          <Badge variant="outline" className="text-xs bg-amber-500/10 text-amber-600 border-amber-500/30">Armed</Badge>
                        ) : (
                          <Badge variant="outline" className="text-xs">Draft</Badge>
                        )}
                        {version.preview_armed && (
                          <Tooltip>
                            <TooltipTrigger>
                              <Shield className="h-3.5 w-3.5 text-amber-500" />
                            </TooltipTrigger>
                            <TooltipContent>Preview Armed</TooltipContent>
                          </Tooltip>
                        )}
                      </div>
                    </div>
                    {version.created_at && (
                      <div className="text-xs text-muted-foreground flex items-center gap-1">
                        <Clock className="h-3 w-3" />
                        {new Date(version.created_at).toLocaleDateString(undefined, {
                          year: "numeric",
                          month: "short",
                          day: "numeric",
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </div>
                    )}
                    {flowVersion?.id !== version.id && (
                      <div className="mt-2 flex gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => {
                            navigate(`/flows/${flowId}/edit?version=${version.id}`);
                            setIsVersionHistoryOpen(false);
                          }}
                          data-testid={`button-view-version-${version.id}`}
                        >
                          <Eye className="h-3.5 w-3.5 mr-1" />
                          View
                        </Button>
                        {version.is_published && (
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => {
                              newVersionMutation.mutate({ clone: true });
                              setIsVersionHistoryOpen(false);
                            }}
                            disabled={newVersionMutation.isPending}
                            data-testid={`button-clone-version-${version.id}`}
                          >
                            <GitBranch className="h-3.5 w-3.5 mr-1" />
                            Clone
                          </Button>
                        )}
                        {!version.is_published && version.status !== "archived" && (
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => {
                              setVersionToDelete(version);
                              setIsDeleteVersionDialogOpen(true);
                            }}
                            disabled={deleteVersionMutation.isPending}
                            data-testid={`button-delete-version-${version.id}`}
                          >
                            <Trash2 className="h-3.5 w-3.5 mr-1" />
                            Delete
                          </Button>
                        )}
                      </div>
                    )}
                  </div>
                ))}
                {(!versionsQuery.data?.versions || versionsQuery.data.versions.length === 0) && (
                  <div className="text-sm text-muted-foreground text-center py-8">
                    No versions found
                  </div>
                )}
              </div>
            )}
          </ScrollArea>
        </SheetContent>
      </Sheet>

      {/* Execution History Sheet */}
      <Sheet open={isExecutionHistoryOpen} onOpenChange={(open) => {
        setIsExecutionHistoryOpen(open);
        if (!open) setSelectedExecution(null);
      }}>
        <SheetContent className="sm:max-w-xl">
          <SheetHeader>
            <SheetTitle className="flex items-center gap-2">
              <Clock className="h-5 w-5" />
              {selectedExecution ? "Execution Detail" : "Execution History"}
            </SheetTitle>
            <SheetDescription>
              {selectedExecution 
                ? `Execution ${selectedExecution.id.slice(0, 8)}...`
                : "View past workflow executions"
              }
            </SheetDescription>
          </SheetHeader>
          
          {selectedExecution ? (
            <div className="mt-4">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setSelectedExecution(null)}
                className="mb-2"
                data-testid="button-back-to-executions"
              >
                <ChevronLeft className="h-4 w-4 mr-1" />
                Back to list
              </Button>
              
              <ScrollArea className="h-[calc(100vh-12rem)]">
              <div className="space-y-3 pr-4">
                <div className="flex items-center gap-2 flex-wrap">
                  <Badge 
                    variant={
                      selectedExecution.status === "failed" ? "destructive" :
                      selectedExecution.status === "running" ? "secondary" :
                      "outline"
                    }
                    className={
                      selectedExecution.status === "completed" || selectedExecution.status === "success"
                        ? "bg-green-600 hover:bg-green-700 text-white"
                        : ""
                    }
                  >
                    {selectedExecution.status}
                  </Badge>
                  {selectedExecution.execution_mode && (
                    <Badge variant={MODE_BADGE_VARIANTS[selectedExecution.execution_mode]}>
                      {(() => {
                        const ModeIcon = MODE_ICON_MAP[selectedExecution.execution_mode!];
                        return <ModeIcon className={`h-3 w-3 mr-1 ${MODE_COLORS[selectedExecution.execution_mode!]}`} />;
                      })()}
                      {selectedExecution.execution_mode}
                    </Badge>
                  )}
                  <Badge variant="outline">{selectedExecution.trigger_type}</Badge>
                </div>
                
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <div className="text-muted-foreground text-xs mb-1">Started</div>
                    <div>{new Date(selectedExecution.started_at).toLocaleString()}</div>
                  </div>
                  {selectedExecution.finished_at && (
                    <div>
                      <div className="text-muted-foreground text-xs mb-1">Finished</div>
                      <div>{new Date(selectedExecution.finished_at).toLocaleString()}</div>
                    </div>
                  )}
                  <div>
                    <div className="text-muted-foreground text-xs mb-1">Duration</div>
                    <div>
                      {selectedExecution.duration_ms 
                        ? `${(selectedExecution.duration_ms / 1000).toFixed(2)}s`
                        : selectedExecution.finished_at 
                          ? `${((new Date(selectedExecution.finished_at).getTime() - new Date(selectedExecution.started_at).getTime()) / 1000).toFixed(2)}s`
                          : "Running..."
                      }
                    </div>
                  </div>
                  <div>
                    <div className="text-muted-foreground text-xs mb-1">Version</div>
                    <div>{selectedExecution.version_label}</div>
                  </div>
                  {selectedExecution.steps_count !== undefined && (
                    <div>
                      <div className="text-muted-foreground text-xs mb-1">Steps</div>
                      <div>{selectedExecution.steps_count} executed</div>
                    </div>
                  )}
                </div>
                
                {hasRealError(selectedExecution.error) && (
                  <div className="mt-4">
                    <div className="text-muted-foreground text-xs mb-1">Error</div>
                    <div className="text-sm text-destructive bg-destructive/10 p-3 rounded">
                      {getErrorMessage(selectedExecution.error)}
                    </div>
                  </div>
                )}
                
                {selectedExecution.input_data && Object.keys(selectedExecution.input_data).length > 0 && (
                  <div className="mt-4">
                    <div className="text-muted-foreground text-xs mb-1">Input Data</div>
                    <ScrollArea className="h-32 border rounded p-2">
                      <pre className="text-xs">
                        {JSON.stringify(selectedExecution.input_data, null, 2)}
                      </pre>
                    </ScrollArea>
                  </div>
                )}
                
                {selectedExecution.output_data && Object.keys(selectedExecution.output_data).length > 0 && (
                  <div className="mt-4">
                    <div className="text-muted-foreground text-xs mb-1">Output Data</div>
                    <ScrollArea className="h-32 border rounded p-2">
                      <pre className="text-xs">
                        {JSON.stringify(selectedExecution.output_data, null, 2)}
                      </pre>
                    </ScrollArea>
                  </div>
                )}
                
                {/* Execution Timeline */}
                {selectedExecution.timeline && selectedExecution.timeline.length > 0 && (
                  <div className="mt-6">
                    <div className="text-sm font-medium mb-3 flex items-center gap-2">
                      <GitBranch className="h-4 w-4" />
                      Execution Timeline ({selectedExecution.timeline.length} steps)
                    </div>
                    <div className="space-y-2">
                      {selectedExecution.timeline.map((step, index) => (
                        <div 
                          key={`${step.node_id}-${index}`}
                          className="relative pl-6 pb-3 border-l-2 border-border last:border-l-transparent"
                        >
                          <div className={`absolute left-[-5px] top-0 w-2 h-2 rounded-full ${
                            step.status === "completed" || step.status === "success" ? "bg-green-500" :
                            step.status === "failed" ? "bg-red-500" :
                            step.status === "running" ? "bg-amber-500" :
                            "bg-muted-foreground"
                          }`} />
                          <div className="bg-muted/50 rounded-lg p-3 text-sm">
                            <div className="flex items-center justify-between gap-2 mb-1">
                              <div className="flex items-center gap-2">
                                <span className="font-medium">{step.name || step.kind}</span>
                                <Badge variant="outline" className="text-xs">
                                  {step.kind}
                                </Badge>
                              </div>
                              <Badge 
                                variant={
                                  step.status === "completed" || step.status === "success" ? "default" :
                                  step.status === "failed" ? "destructive" :
                                  "secondary"
                                }
                                className="text-xs"
                              >
                                {step.status}
                              </Badge>
                            </div>
                            {step.started_at && (
                              <div className="text-xs text-muted-foreground mb-2">
                                {new Date(step.started_at).toLocaleTimeString()}
                                {step.finished_at && ` → ${new Date(step.finished_at).toLocaleTimeString()}`}
                              </div>
                            )}
                            {step.input && Object.keys(step.input).length > 0 && (
                              <details className="text-xs mt-2">
                                <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
                                  Input data
                                </summary>
                                <pre className="mt-1 p-2 bg-background rounded text-xs overflow-x-auto">
                                  {JSON.stringify(step.input, null, 2)}
                                </pre>
                              </details>
                            )}
                            {step.output && Object.keys(step.output).length > 0 && (
                              <details className="text-xs mt-2">
                                <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
                                  Output data
                                </summary>
                                <pre className="mt-1 p-2 bg-background rounded text-xs overflow-x-auto">
                                  {JSON.stringify(step.output, null, 2)}
                                </pre>
                              </details>
                            )}
                            {step.transitions && step.transitions.length > 0 && (
                              <div className="text-xs text-muted-foreground mt-2">
                                → {step.transitions.map(t => t.target).join(", ")}
                              </div>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                
                {/* Context Data */}
                {selectedExecution.context && Object.keys(selectedExecution.context).length > 0 && (
                  <div className="mt-4">
                    <div className="text-muted-foreground text-xs mb-1">Execution Context</div>
                    <ScrollArea className="h-32 border rounded p-2">
                      <pre className="text-xs">
                        {JSON.stringify(selectedExecution.context, null, 2)}
                      </pre>
                    </ScrollArea>
                  </div>
                )}
              </div>
              </ScrollArea>
            </div>
          ) : (
            <>
              {/* Mode Filter */}
              <div className="mt-4 mb-3 flex items-center gap-2">
                <span className="text-xs text-muted-foreground">Filter by mode:</span>
                <div className="flex gap-1">
                  {(["all", "production", "testing", "preview"] as const).map((mode) => {
                    const isActive = executionHistoryModeFilter === mode;
                    const ModeIcon = mode !== "all" ? MODE_ICON_MAP[mode] : null;
                    return (
                      <Button
                        key={mode}
                        variant={isActive ? "secondary" : "ghost"}
                        size="sm"
                        className="h-7 text-xs"
                        onClick={() => setExecutionHistoryModeFilter(mode)}
                        data-testid={`button-filter-${mode}`}
                      >
                        {ModeIcon && <ModeIcon className={`h-3 w-3 mr-1 ${mode !== "all" ? MODE_COLORS[mode] : ""}`} />}
                        {mode === "all" ? "All" : mode.charAt(0).toUpperCase() + mode.slice(1)}
                      </Button>
                    );
                  })}
                </div>
              </div>
              
              <ScrollArea className="h-[calc(100vh-16rem)]">
                {executionsQuery.isLoading ? (
                  <div className="flex items-center justify-center py-8">
                    <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-primary" />
                  </div>
                ) : executionsQuery.error ? (
                  <div className="text-sm text-destructive p-4 space-y-2">
                    <div>Failed to load executions</div>
                    <div className="text-xs text-muted-foreground whitespace-pre-wrap break-words">
                      {executionsQuery.error instanceof ApiError
                        ? `${executionsQuery.error.message}\n${executionsQuery.error.body}`
                        : executionsQuery.error instanceof Error
                          ? executionsQuery.error.message
                          : String(executionsQuery.error)}
                    </div>
                  </div>
                ) : (
                  <div className="space-y-2 pr-4">
                    {visibleExecutions.map((execution) => {
                      const ModeIcon = execution.execution_mode ? MODE_ICON_MAP[execution.execution_mode] : null;
                      return (
                        <div
                          key={execution.id}
                          className="p-3 rounded-lg border border-border hover-elevate cursor-pointer"
                          onClick={() => setSelectedExecution(transformExecution(execution))}
                          data-testid={`execution-item-${execution.id}`}
                        >
                          <div className="flex items-center justify-between mb-2">
                            <div className="flex items-center gap-2 flex-wrap">
                              <Badge 
                                variant={
                                  execution.status === "failed" ? "destructive" :
                                  execution.status === "running" ? "secondary" :
                                  "outline"
                                }
                                className={`text-xs ${
                                  execution.status === "completed" || execution.status === "success"
                                    ? "bg-green-600 hover:bg-green-700 text-white"
                                    : ""
                                }`}
                              >
                                {execution.status}
                              </Badge>
                              {execution.execution_mode && ModeIcon && (
                                <Badge 
                                  variant={MODE_BADGE_VARIANTS[execution.execution_mode]} 
                                  className="text-xs"
                                >
                                  <ModeIcon className={`h-2.5 w-2.5 mr-1 ${MODE_COLORS[execution.execution_mode]}`} />
                                  {execution.execution_mode}
                                </Badge>
                              )}
                              <span className="text-xs text-muted-foreground">
                                {execution.version_label}
                              </span>
                            </div>
                            <span className="text-xs text-muted-foreground">
                              {execution.trigger_type}
                            </span>
                          </div>
                          <div className="text-xs text-muted-foreground flex items-center gap-1">
                            <Clock className="h-3 w-3" />
                            {new Date(execution.started_at).toLocaleDateString(undefined, {
                              year: "numeric",
                              month: "short",
                              day: "numeric",
                              hour: "2-digit",
                              minute: "2-digit",
                            })}
                            {execution.finished_at && (
                              <span className="ml-2">
                                ({Math.round((new Date(execution.finished_at).getTime() - new Date(execution.started_at).getTime()) / 1000)}s)
                              </span>
                            )}
                          </div>
                          {hasRealError(execution.error) && (
                            <div className="mt-2 text-xs text-destructive bg-destructive/10 p-2 rounded line-clamp-2">
                              {getErrorMessage(execution.error)}
                            </div>
                          )}
                          {execution.steps_count !== undefined && (
                            <div className="mt-1 text-xs text-muted-foreground">
                              {execution.steps_count} steps executed
                            </div>
                          )}
                        </div>
                      );
                    })}
                    {visibleExecutions.length === 0 && (
                      <div className="text-sm text-muted-foreground text-center py-8">
                        No executions found
                      </div>
                    )}
                  </div>
                )}
              </ScrollArea>
              
              {/* Pagination Controls */}
              {executionsQuery.data?.pagination && executionsQuery.data.pagination.total_pages > 1 && (
                <div className="flex items-center justify-between mt-4 pt-4 border-t">
                  <div className="text-xs text-muted-foreground">
                    Page {executionsQuery.data.pagination.current_page} of {executionsQuery.data.pagination.total_pages}
                    {" "}({executionsQuery.data.pagination.total_items} total)
                  </div>
                  <div className="flex gap-1">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setExecutionHistoryPage(p => Math.max(1, p - 1))}
                      disabled={executionHistoryPage <= 1 || executionsQuery.isFetching}
                      data-testid="button-prev-page"
                    >
                      <ChevronLeft className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setExecutionHistoryPage(p => p + 1)}
                      disabled={executionHistoryPage >= (executionsQuery.data?.pagination?.total_pages || 1) || executionsQuery.isFetching}
                      data-testid="button-next-page"
                    >
                      <ChevronRight className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              )}
            </>
          )}
        </SheetContent>
      </Sheet>

      {/* Publish Confirmation Dialog */}
      <AlertDialog open={isPublishConfirmOpen} onOpenChange={setIsPublishConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Publish Version?</AlertDialogTitle>
            <AlertDialogDescription>
              Publishing this version will make it the active workflow. The currently published version will be archived and can no longer receive events.
              <br /><br />
              <strong>Current version:</strong> {flowVersion ? formatVersionDisplay(flowName, flowVersion) : "Draft"}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel data-testid="button-cancel-publish">Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleConfirmPublish}
              disabled={publishFlowMutation.isPending}
              className="bg-amber-400 hover:bg-amber-500 text-amber-950"
              data-testid="button-confirm-publish"
            >
              {publishFlowMutation.isPending ? "Publishing..." : "Publish"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* New Version Modal */}
      <Dialog open={isNewVersionModalOpen} onOpenChange={setIsNewVersionModalOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Create New Version</DialogTitle>
            <DialogDescription>
              Choose how to create your new draft version
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-4">
            <Button
              variant="outline"
              className="w-full justify-start h-auto py-4 px-4"
              onClick={() => newVersionMutation.mutate({ clone: true })}
              disabled={newVersionMutation.isPending}
              data-testid="button-clone-from-published"
            >
              <div className="flex items-start gap-3">
                <GitBranch className="h-5 w-5 mt-0.5 text-primary" />
                <div className="text-left">
                  <div className="font-medium">Clone from Published</div>
                  <div className="text-sm text-muted-foreground">
                    Start with a copy of the current published version
                  </div>
                </div>
              </div>
            </Button>
            <Button
              variant="outline"
              className="w-full justify-start h-auto py-4 px-4"
              onClick={() => newVersionMutation.mutate({ clone: false })}
              disabled={newVersionMutation.isPending}
              data-testid="button-start-blank"
            >
              <div className="flex items-start gap-3">
                <FileCode className="h-5 w-5 mt-0.5 text-muted-foreground" />
                <div className="text-left">
                  <div className="font-medium">Start Blank</div>
                  <div className="text-sm text-muted-foreground">
                    Begin with an empty workflow canvas
                  </div>
                </div>
              </div>
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Preview Payload Dialog */}
      <Dialog open={isPreviewPayloadDialogOpen} onOpenChange={(open) => {
        setIsPreviewPayloadDialogOpen(open);
        if (!open) {
          setPreviewPayload("");
          setPreviewPayloadError(null);
        }
      }}>
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>Preview Payload</DialogTitle>
            <DialogDescription>
              Enter a JSON payload to test the flow with. Leave empty to use default payload.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="preview-payload">Payload (JSON)</Label>
              <Textarea
                id="preview-payload"
                value={previewPayload}
                onChange={(e) => {
                  const value = e.target.value;
                  setPreviewPayload(value);
                  if (value.trim()) {
                    try {
                      JSON.parse(value);
                      setPreviewPayloadError(null);
                    } catch {
                      setPreviewPayloadError("Invalid JSON format");
                    }
                  } else {
                    setPreviewPayloadError(null);
                  }
                }}
                placeholder='{"key": "value"}'
                className={`min-h-[200px] font-mono text-sm ${previewPayloadError ? "border-destructive" : ""}`}
                data-testid="textarea-preview-payload"
              />
              {previewPayloadError ? (
                <p className="text-sm text-destructive">{previewPayloadError}</p>
              ) : (
                <p className="text-xs text-muted-foreground">
                  Paste or type JSON payload. Leave empty to use default payload.
                </p>
              )}
            </div>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setIsPreviewPayloadDialogOpen(false);
                setPreviewPayload("");
                setPreviewPayloadError(null);
              }}
              data-testid="button-cancel-preview-payload"
            >
              Cancel
            </Button>
            <Button
              onClick={handleConfirmPreview}
              disabled={!!previewPayloadError || previewFlowMutation.isPending || saveFlowMutation.isPending}
              data-testid="button-confirm-preview-payload"
            >
              {saveFlowMutation.isPending ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Saving...
                </>
              ) : previewFlowMutation.isPending ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Running Preview...
                </>
              ) : (
                "Run Preview"
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

export default function FlowBuilder() {
  const [, params] = useRoute("/flows/:id/edit");
  const flowId = params?.id;

  return (
    <ReactFlowProvider>
      <BuilderDataProviders flowId={flowId}>
        <div className="h-full min-h-0 w-full">
          <FlowCanvas flowId={flowId} />
        </div>
      </BuilderDataProviders>
    </ReactFlowProvider>
  );
}