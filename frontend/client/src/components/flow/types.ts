// ============================================================================
// FlowBuilder Data Model Specification (v2) - Core Types
// ============================================================================

/**
 * FlowDefinition - Root structure for a flow
 * Matches spec v2: embeds nodes and edges directly
 */
export interface FlowDefinition {
  id: string;
  name: string;
  description?: string;
  version: number;
  status: "draft" | "armed" | "published" | "archived";
  nodes: FlowNode[];
  edges: FlowEdge[];
  /**
   * config_schema / config_values - flow-scoped, versioned configuration variables.
   *
   * Canonical namespace in expressions: `config.*`
   *
   * - config_schema defines available keys + types (schema-defined, NOT inferred)
   * - config_values are immutable constants injected at runtime (deterministic, replay-safe)
   */
  config_schema?: unknown;
  config_values?: Record<string, unknown>;
  metadata?: {
    created_at?: string;
    updated_at?: string;
    created_by?: string;
  };
}

/**
 * FlowNode - Represents a node in the flow graph
 * Matches spec v2: minimal data model, UI state separated
 */
export interface FlowNode {
  id: string;
  kind: string;
  name?: string;
  position: {
    x: number;
    y: number;
  };
  config: Record<string, any>;
}

/**
 * FlowEdge - Represents an edge connecting nodes
 * Matches spec v2: sourceHandle is mandatory
 */
export interface FlowEdge {
  id: string;
  source: string;
  sourceHandle: string;  // Mandatory in v2 spec
  target: string;
  targetHandle?: string;
}

// ============================================================================
// Schema System (v2 Spec)
// ============================================================================

/**
 * SchemaNode - Discriminated union for schema types
 * Matches spec v2: kind discriminator required
 * Nested data structures are preserved exactly as-is - no flattening
 */
export type SchemaNode =
  | PrimitiveSchema
  | ObjectSchema
  | ArraySchema
  | UnknownSchema;

/**
 * PrimitiveSchema - Primitive type schema
 */
export interface PrimitiveSchema {
  kind: "primitive";
  type: "string" | "number" | "boolean" | "any";
}

/**
 * ObjectSchema - Object type schema with properties
 * Nested objects preserve their structure exactly as-is
 */
export interface ObjectSchema {
  kind: "object";
  properties: Record<string, SchemaNode>;
}

/**
 * ArraySchema - Array type schema with item type
 * Arrays preserve their nested structure exactly as-is
 */
export interface ArraySchema {
  kind: "array";
  items: SchemaNode;  // Schema for array items (preserves nested structure)
}

/**
 * UnknownSchema - Unknown type schema (blocks deep access)
 */
export interface UnknownSchema {
  kind: "unknown";
}

/**
 * PASSTHROUGH - Special marker for passthrough outputs
 * Schema inherits from parent output
 */
export const PASSTHROUGH = Symbol("PASSTHROUGH");
export type PASSTHROUGH = typeof PASSTHROUGH;

// ============================================================================
// Legacy Types (to be migrated)
// ============================================================================

/**
 * @deprecated Use SchemaNode instead
 * Legacy PortSchema for backward compatibility during migration
 */
export interface PortSchema {
  type: string;
  description?: string;
  properties?: Record<string, {
    type: string;
    description?: string;
    [key: string]: any;
  }>;
  [key: string]: any;
}

export interface PortDefinition {
  name: string;
  description?: string;
  schema?: PortSchema;
  schema_preview?: string;
}

// Node data effects declaration - what a node does to data passing through
export interface NodeDataEffects {
  // Fields that this node validates (e.g., branch checking if email exists)
  validates?: string[];
  // Fields that this node transforms (e.g., format_text changing a string)
  transforms?: Array<{
    field: string;
    description: string;
  }>;
  // Fields that this node computes/adds (e.g., creating full_name from first+last)
  computes?: Array<{
    field: string;
    type: string;
    description: string;
    fromFields?: string[];  // Source fields used to compute this
  }>;
}

/**
 * NodeOutput - Represents a single output port with its schema
 * Matches spec v2: each output has a name and schema
 */
export interface NodeOutput {
  name: string;           // e.g., "success", "error", "else", "out"
  schema: SchemaNode | typeof PASSTHROUGH;  // Schema produced by this output, or PASSTHROUGH
}

/**
 * BackendNodeDefinition - Node definition registry entry
 * Matches spec v2: outputs array, passthrough flag, configSchema
 */
export interface BackendNodeDefinition {
  kind: string;
  title: string;
  icon: string;
  category: string;
  description?: string;
  default_config?: Record<string, any>;
  form_component?: string;
  
  // v2 spec: Multiple outputs per node
  outputs?: NodeOutput[];  // 0..N outputs possible
  
  // v2 spec: Passthrough flag (if true, all outputs inherit from parent)
  passthrough?: boolean;
  
  // v2 spec: Config schema for validation
  configSchema?: SchemaNode;
  
  hints?: {
    description?: string;                              // Rich description (overrides node description)
    example_config?: Record<string, any>;              // Example configuration for this node
    use_cases?: string[];                              // Common use cases
    expression_examples?: Array<{                      // For expression-based nodes
      expr: string;
      description: string;
    }>;
    tips?: string;                                     // Configuration guidance
  };
  data_effects?: NodeDataEffects;                      // What this node does to data
  
  // Legacy: ports (to be migrated to outputs)
  ports?: {
    in?: PortDefinition[];
    out?: PortDefinition[];
  };
}

// Data effect types that nodes can apply to fields
export type DataEffectType = 'passthrough' | 'transformed' | 'validated' | 'computed' | 'filtered';

export interface DataEffect {
  type: DataEffectType;
  appliedBy: string;  // Node label that applied this effect
  nodeType: string;   // Node kind/type
  description?: string;  // e.g., "Validated email exists", "Formatted as uppercase"
}

export interface AvailableDataField {
  key: string;
  type: string;
  description?: string;
  source: string;
  effects?: DataEffect[];  // Track transformations/validations applied to this field
}

export interface PreviewTimelineEntry {
  id: string;
  status: string;
  timestamp: string;
  message?: string;
  payload?: any;
  nodeId?: string;
  nodeType?: string;
  action?: string;
  htmlSnippet?: string;
}

export interface PreviewExecution {
  id: string;
  status: string;
  entries: PreviewTimelineEntry[];
  summary?: string;
  summaryHtml?: string;
  startedAt?: string;
  completedAt?: string;
}

/**
 * NodeUIState - UI-specific state for ReactFlow nodes
 * Separated from data model (FlowNode) per spec v2
 */
export interface NodeUIState {
  icon?: React.ComponentType<{ className?: string }>;
  iconKey?: string;
  formComponent?: string;
  outputs?: string[];
  inputs?: string[];
  portSchemas?: {
    in?: Record<string, PortDefinition>;
    out?: Record<string, PortDefinition>;
  };
  availableData?: AvailableDataField[];
  hints?: BackendNodeDefinition['hints'];
  onConfig?: (nodeId: string) => void;
  onDelete?: (nodeId: string) => void;
  onAddElif?: (nodeId: string) => void;
  onRemoveElif?: (nodeId: string) => void;
}

/**
 * CustomNodeData - Combines FlowNode data model with UI state
 * Used by ReactFlow for rendering
 */
export interface CustomNodeData {
  // Data model fields (from FlowNode)
  label: string;  // Maps to FlowNode.name
  type: string;   // Maps to FlowNode.kind
  description?: string;
  config?: Record<string, any>;

  // UI state (separated per spec v2)
  ui?: NodeUIState;

  // Legacy: keeping for backward compatibility during migration
  icon?: React.ComponentType<{ className?: string }>;
  iconKey?: string;
  formComponent?: string;
  outputs?: string[];
  inputs?: string[];
  portSchemas?: {
    in?: Record<string, PortDefinition>;
    out?: Record<string, PortDefinition>;
  };
  availableData?: AvailableDataField[];
  hints?: BackendNodeDefinition['hints'];
  onConfig?: (nodeId: string) => void;
  onDelete?: (nodeId: string) => void;
  onAddElif?: (nodeId: string) => void;
  onRemoveElif?: (nodeId: string) => void;
}

export interface CustomEdgeData {
  schema?: PortSchema;
  sourcePort?: string;
  targetPort?: string;
  dataPreview?: AvailableDataField[];
  onDelete?: (edgeId: string) => void;
  sourceHandle?: string; // Name of the output port (e.g., rule name for branch nodes)
  isBranchEdge?: boolean; // Whether this edge comes from a branch node
  readOnly?: boolean; // UI-only: hide destructive edge actions when flow is locked
}
