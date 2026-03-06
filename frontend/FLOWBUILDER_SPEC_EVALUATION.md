# FlowBuilder Data Model Specification - Evaluation Report

## Executive Summary

This document evaluates the current FlowBuilder implementation against the provided Data Model Specification (v1). The evaluation identifies alignment points, gaps, and areas requiring refactoring to match the specification.

**Overall Assessment**: The current implementation has a solid foundation with a working Data Flow Analyzer and schema propagation system. However, there are significant structural differences and missing components that need to be addressed to fully align with the specification.

---

## 1. FlowDefinition Structure

### Specification Requirements
```ts
interface FlowDefinition {
  id: string;
  name: string;
  description?: string;
  version: number;
  status: "draft" | "armed" | "published" | "archived";
  nodes: FlowNode[];
  edges: FlowEdge[];
  metadata?: {
    created_at?: string;
    updated_at?: string;
    created_by?: string;
  };
}
```

### Current Implementation
**Location**: `client/src/pages/flow-builder.tsx`

**Current Structure**:
```ts
type FlowData = {
  ok: boolean;
  flow: {
    id: string;
    name: string;
    description: string;
    status: string;  // "active|inactive|draft" (different from spec)
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
    edges: Edge[] 
  };
};
```

**Gaps & Differences**:
1. ❌ **Status values differ**: Current uses `"active|inactive|draft"`, spec requires `"draft|armed|published|archived"`
2. ❌ **Version structure**: Current has separate `FlowVersion` type with `is_published`, `preview_armed` flags. Spec embeds `version: number` directly
3. ⚠️ **Graph separation**: Current separates `graph` from flow metadata. Spec embeds `nodes` and `edges` directly
4. ✅ **Metadata**: Current has `created_at`, `updated_at`, `created_by` (matches spec)

**Recommendation**: Refactor to align status values and embed nodes/edges directly in FlowDefinition.

---

## 2. FlowNode Structure

### Specification Requirements
```ts
interface FlowNode {
  id: string;
  kind: string;
  name?: string;
  position: { x: number; y: number };
  config: Record<string, any>;
}
```

### Current Implementation
**Location**: `client/src/pages/flow-builder.tsx`, `client/src/components/flow/types.ts`

**Current Structure**:
```ts
interface NodeData {
  label: string;        // Maps to spec's "name"
  type: string;          // Maps to spec's "kind"
  icon?: React.ComponentType;
  description?: string;
  config?: Record<string, any>;
  formComponent?: string;
  outputs?: string[];
  inputs?: string[];
  portSchemas?: any;
  availableData?: any[];
  hints?: {...};
  onConfig?: (nodeId: string) => void;
  onDelete?: (nodeId: string) => void;
  onAddElif?: (nodeId: string) => void;
  onRemoveElif?: (nodeId: string) => void;
}

// ReactFlow Node wrapper
type SerializedNode = Omit<Node<NodeData>, "data"> & {
  data: SerializableNodeData;
};
```

**Gaps & Differences**:
1. ✅ **Core fields**: `id`, `kind` (as `type`), `name` (as `label`), `position`, `config` all present
2. ⚠️ **UI-specific fields**: Current includes React-specific fields (`icon`, `onConfig`, `onDelete`, etc.) that should be separated from data model
3. ⚠️ **Schema metadata**: Current includes `portSchemas`, `availableData` which are computed/derived, not part of persisted data
4. ✅ **Position**: Matches spec structure `{ x: number; y: number }`

**Recommendation**: Create a clean separation between:
- **FlowNode** (spec-compliant, persisted): `id`, `kind`, `name`, `position`, `config`
- **NodeUIState** (frontend-only): `icon`, `availableData`, `portSchemas`, callbacks

---

## 3. FlowEdge Structure

### Specification Requirements
```ts
interface FlowEdge {
  id: string;
  source: string;
  target: string;
  sourceHandle?: string;
  targetHandle?: string;
}
```

### Current Implementation
**Location**: Uses ReactFlow's `Edge` type directly

**Current Structure**:
```ts
// ReactFlow Edge with custom data
interface CustomEdgeData {
  schema?: PortSchema;
  sourcePort?: string;   // Maps to sourceHandle
  targetPort?: string;   // Maps to targetHandle
  dataPreview?: AvailableDataField[];
  onDelete?: (edgeId: string) => void;
}

// ReactFlow Edge
type Edge = {
  id: string;
  source: string;
  target: string;
  sourceHandle?: string;
  targetHandle?: string;
  type?: string;
  data?: CustomEdgeData;
  // ... other ReactFlow fields
}
```

**Gaps & Differences**:
1. ✅ **Core fields**: `id`, `source`, `target`, `sourceHandle`, `targetHandle` all match spec
2. ⚠️ **UI-specific data**: `schema`, `dataPreview`, `onDelete` are frontend-only and should not be persisted
3. ✅ **Handle names**: `sourceHandle`/`targetHandle` match spec's `sourceHandle`/`targetHandle`

**Recommendation**: When serializing to backend, strip `data` field and only send `id`, `source`, `target`, `sourceHandle`, `targetHandle`.

---

## 4. Schema System

### Specification Requirements
```ts
type SchemaNode =
  | PrimitiveSchema
  | ObjectSchema
  | UnknownSchema;

interface PrimitiveSchema {
  kind: "primitive";
  type: "string" | "number" | "boolean" | "any";
}

interface ObjectSchema {
  kind: "object";
  properties: Record<string, SchemaNode>;
}

interface UnknownSchema {
  kind: "unknown";
}
```

### Current Implementation
**Location**: `client/src/components/flow/types.ts`, `client/src/components/flow/schemaUtils.ts`

**Current Structure**:
```ts
interface PortSchema {
  type: string;  // "string" | "number" | "boolean" | "object" | "array" | etc.
  description?: string;
  properties?: Record<string, {
    type: string;
    description?: string;
    [key: string]: any;
  }>;
  [key: string]: any;  // Flexible, allows additional fields
}
```

**Gaps & Differences**:
1. ❌ **No `kind` discriminator**: Current uses `type` field directly, spec requires `kind: "primitive" | "object" | "unknown"`
2. ❌ **No explicit `UnknownSchema`**: Current doesn't have a dedicated "unknown" type representation
3. ⚠️ **Flexible structure**: Current allows arbitrary fields via `[key: string]: any`, spec is more strict
4. ✅ **Nested properties**: Both support nested object schemas via `properties`

**Recommendation**: 
- Refactor `PortSchema` to use discriminated union with `kind` field
- Add explicit `UnknownSchema` type for unknown data
- Ensure schema extraction functions handle `kind: "unknown"` correctly

---

## 5. Node Definition Registry

### Specification Requirements
```ts
interface NodeDefinition {
  kind: string;
  label: string;
  outputs: SchemaNode;
  passthrough?: boolean;
  configSchema: SchemaNode;
}
```

### Current Implementation
**Location**: `client/src/components/flow/types.ts`, `client/src/pages/flow-builder.tsx`

**Current Structure**:
```ts
interface BackendNodeDefinition {
  kind: string;
  title: string;        // Maps to "label"
  icon: string;
  category: string;
  description?: string;
  default_config?: Record<string, any>;
  form_component?: string;
  hints?: {...};
  data_effects?: NodeDataEffects;
  ports?: {
    in?: PortDefinition[];
    out?: PortDefinition[];
  };
}
```

**Gaps & Differences**:
1. ❌ **No `outputs: SchemaNode`**: Current uses `ports.out[]` array, spec requires single `outputs: SchemaNode`
2. ❌ **No `passthrough` flag**: Current infers passthrough from `data_effects`, spec requires explicit flag
3. ❌ **No `configSchema`**: Current doesn't define schema for `config`, spec requires `configSchema: SchemaNode`
4. ⚠️ **UI fields**: Current includes `icon`, `category`, `hints` which are UI concerns, not data model
5. ✅ **Kind**: Both use `kind` as identifier

**Recommendation**: 
- Add `outputs: SchemaNode` (single schema, not array)
- Add `passthrough?: boolean` flag
- Add `configSchema: SchemaNode` for config validation
- Keep UI fields separate in a `NodeUIDefinition` type

---

## 6. Data Flow Analyzer (DFA)

### Specification Requirements
- Resolve schema initial (from trigger nodes)
- Propagate schemas node-to-node
- Validate expressions
- Detect invalid flows
- Merge rules: new properties added, existing overwritten, `unknown` not expanded

### Current Implementation
**Location**: `client/src/components/flow/dataFlowAnalyzer.ts`

**Current Behavior**:
1. ✅ **Schema resolution**: `extractFieldsFromSchema()` extracts from trigger nodes
2. ✅ **Topological propagation**: `analyzeDataFlow()` uses topological sort to propagate schemas
3. ✅ **Merge logic**: `calculateNodeOutput()` merges input fields with node outputs
4. ⚠️ **Expression validation**: `extractValidatedFieldsFromExpr()` extracts fields but doesn't validate paths exist
5. ❌ **Unknown handling**: No explicit handling of `kind: "unknown"` schemas
6. ✅ **Cycle detection**: `topologicalSort()` detects cycles

**Gaps & Differences**:
1. ❌ **No expression path validation**: Current extracts paths from expressions but doesn't validate they exist in schema
2. ❌ **No `unknown` blocking**: Spec says `unknown` blocks deep access, current doesn't enforce this
3. ⚠️ **Passthrough inference**: Current infers passthrough from node type, spec requires explicit flag
4. ✅ **Merge behavior**: Matches spec (new properties added, existing overwritten)

**Recommendation**:
- Add expression path validation before saving flows
- Add `unknown` schema handling to block deep access
- Use explicit `passthrough` flag instead of inference

---

## 7. Expression Model

### Specification Requirements
- Expressions can only access: `input.*`, `context.*`, `vars.*`
- Before saving: parse expressions, extract paths, validate existence, error if missing

### Current Implementation
**Location**: `client/src/components/flow/dataFlowAnalyzer.ts`, `client/src/components/flow/NodeConfigForms.tsx`

**Current Behavior**:
1. ⚠️ **Path extraction**: `extractValidatedFieldsFromExpr()` extracts field paths from expressions
2. ❌ **No validation**: No validation that extracted paths exist in available schema
3. ❌ **No context/vars support**: Current doesn't distinguish `input.*`, `context.*`, `vars.*` namespaces
4. ⚠️ **Expression parsing**: Basic regex-based extraction, not full parser

**Gaps & Differences**:
1. ❌ **Missing validation**: No pre-save validation of expression paths
2. ❌ **No namespace awareness**: Doesn't enforce `input.*`, `context.*`, `vars.*` structure
3. ⚠️ **Limited parsing**: Regex-based, may miss edge cases

**Recommendation**:
- Implement expression parser that extracts paths and validates against schema
- Add namespace awareness (`input.*`, `context.*`, `vars.*`)
- Add validation step before flow save/publish

---

## 8. Branch Node

### Specification Requirements
```ts
interface BranchRule {
  id: string;
  expr: string;
  output: string;
}

interface BranchConfig {
  mode: "first" | "all";
  rules: BranchRule[];
  else?: string;
}
```

### Current Implementation
**Location**: `client/src/components/flow/branchUtils.ts`, `client/src/components/flow/NodeConfigForms.tsx`

**Current Structure**:
```ts
interface BranchRule {
  name: string;    // Maps to spec's "output"
  expr?: string;
  // Missing: id field
}

interface BranchConfig {
  rules: BranchRule[];
  else?: boolean;  // Spec requires string (output name), current uses boolean
  // Missing: mode field
}
```

**Gaps & Differences**:
1. ❌ **No `id` field**: Spec requires `id: string` per rule, current uses array index
2. ❌ **No `mode` field**: Spec requires `mode: "first" | "all"`, current doesn't have this
3. ❌ **`else` type mismatch**: Spec requires `else?: string` (output name), current uses `else?: boolean`
4. ✅ **Rules array**: Both have `rules: BranchRule[]`
5. ✅ **Expression**: Both have `expr: string`

**Recommendation**:
- Add `id: string` to `BranchRule`
- Add `mode: "first" | "all"` to `BranchConfig`
- Change `else?: boolean` to `else?: string` (output name)

---

## 9. Flow Status/State

### Specification Requirements
| Estado    | Condición         |
| --------- | ----------------- |
| draft     | libre             |
| armed     | validado          |
| published | validado + activo |
| archived  | solo lectura      |

### Current Implementation
**Location**: `client/src/pages/flow-builder.tsx`

**Current States**:
```ts
type VersionStatus = "draft" | "testing" | "published" | "archived";

type FlowVersion = {
  id: string;
  flow_id: string;
  version?: number;
  is_published: boolean;      // Maps to "published"
  is_editable: boolean;       // Maps to "draft"
  preview_armed: boolean;     // Maps to "armed"
  preview_armed_at: string | null;
  status: VersionStatus;
  // ...
};
```

**Gaps & Differences**:
1. ⚠️ **Status mapping**: Current uses `is_published`, `is_editable`, `preview_armed` flags. Spec uses single `status` field
2. ✅ **States match**: All four states exist (`draft`, `armed`/`preview_armed`, `published`, `archived`)
3. ⚠️ **"testing" vs "armed"**: Current has `"testing"` status, spec uses `"armed"`

**Recommendation**:
- Align status values: use `"armed"` instead of `"testing"`
- Consider if single `status` field is sufficient or if flags are needed for UI

---

## 10. Validation Rules

### Specification Requirements
**Structural Rules**:
- Flow must have ≥1 trigger
- No cycles
- Branch doesn't create data
- Tool nodes don't alter schema

**Publication Rules**:
- Cannot publish if: invalid expressions, unknown schema access, branches without normalized data upstream

### Current Implementation
**Location**: `client/src/components/flow/dataFlowAnalyzer.ts`, `client/src/pages/flow-builder.tsx`

**Current Validation**:
1. ✅ **Cycle detection**: `wouldCreateCycle()` prevents cycles at edge creation
2. ✅ **Topological validation**: `topologicalSort()` detects cycles
3. ❌ **No trigger validation**: Doesn't enforce ≥1 trigger requirement
4. ❌ **No expression validation**: Doesn't validate expressions before save/publish
5. ❌ **No schema access validation**: Doesn't check for unknown schema access
6. ❌ **No branch validation**: Doesn't validate branches have normalized data upstream

**Gaps & Differences**:
1. ❌ **Missing validations**: Most publication rules are not enforced
2. ✅ **Cycle prevention**: Works correctly

**Recommendation**:
- Add trigger count validation (≥1 trigger required)
- Add expression validation before save/publish
- Add schema access validation (block unknown access)
- Add branch validation (require normalized data upstream)

---

## 11. Output Schemas by Node Type

### Specification Examples

#### `trigger_webhook`
```ts
outputs = {
  kind: "object",
  properties: {
    input: {
      kind: "object",
      properties: {
        body: { kind: "unknown" },
        headers: { kind: "object", properties: {} },
        query: { kind: "object", properties: {} },
        method: { kind: "primitive", type: "string" }
      }
    }
  }
}
```

#### `data_set_values` (Normalize)
```ts
outputs = {
  kind: "object",
  properties: {
    // defined by user
  }
}
```

#### `logic_branch`
```ts
passthrough = true
outputs = SAME_AS_INPUT
```

### Current Implementation
**Location**: `client/src/components/flow/dataFlowAnalyzer.ts`

**Current Behavior**:
1. ✅ **Webhook trigger**: Extracts schema from `config.expected_schema`
2. ✅ **Set values**: Adds fields from `config.values`
3. ✅ **Branch**: Passes through input (inferred, not explicit)
4. ❌ **No explicit output schemas**: Outputs are computed dynamically, not defined statically

**Gaps & Differences**:
1. ❌ **No static output definitions**: Spec requires static `outputs: SchemaNode` per node type
2. ⚠️ **Dynamic computation**: Current computes outputs at runtime, spec suggests static definitions

**Recommendation**:
- Define static `outputs: SchemaNode` in `NodeDefinition` registry
- Use static definitions as source of truth, compute dynamically only for user-defined nodes (e.g., `data_set_values`)

---

## Summary of Critical Gaps

### High Priority
1. **Schema System**: Missing `kind` discriminator and `UnknownSchema` type
2. **Expression Validation**: No pre-save validation of expression paths
3. **Branch Node**: Missing `id`, `mode`, and correct `else` type
4. **Node Definition**: Missing `outputs: SchemaNode`, `passthrough`, `configSchema`
5. **Flow Status**: Status values don't match spec (`"testing"` vs `"armed"`)

### Medium Priority
1. **FlowDefinition Structure**: Embed nodes/edges directly, align status values
2. **Validation Rules**: Add trigger count, expression, schema access, branch validations
3. **Unknown Schema Handling**: Block deep access to `unknown` schemas

### Low Priority
1. **UI Separation**: Separate data model from UI state (icons, callbacks, etc.)
2. **Namespace Awareness**: Add `input.*`, `context.*`, `vars.*` namespace support

---

## Recommended Implementation Plan

### Phase 1: Core Data Model Alignment
1. Refactor `FlowDefinition` to embed nodes/edges directly
2. Align `FlowNode` structure (separate UI fields)
3. Align `FlowEdge` structure (strip UI data on serialize)
4. Update status values (`"armed"` instead of `"testing"`)

### Phase 2: Schema System Refactoring
1. Add `kind` discriminator to schema types
2. Implement `UnknownSchema` type
3. Update schema extraction to handle `kind: "unknown"`

### Phase 3: Node Definition Registry
1. Add `outputs: SchemaNode` to `NodeDefinition`
2. Add `passthrough?: boolean` flag
3. Add `configSchema: SchemaNode` for validation
4. Define static output schemas for each node type

### Phase 4: Expression Validation
1. Implement expression parser with namespace awareness
2. Add path extraction and validation
3. Add pre-save validation hook

### Phase 5: Branch Node Refactoring
1. Add `id` field to `BranchRule`
2. Add `mode: "first" | "all"` to `BranchConfig`
3. Change `else` from boolean to string (output name)

### Phase 6: Validation Rules
1. Add trigger count validation (≥1 trigger)
2. Add expression validation before publish
3. Add schema access validation (block unknown)
4. Add branch validation (normalized data upstream)

---

## Conclusion

The current FlowBuilder implementation has a solid foundation with working data flow analysis and schema propagation. However, significant structural changes are needed to fully align with the specification:

- **Data Model**: Needs refactoring to match spec structure
- **Schema System**: Needs `kind` discriminator and `UnknownSchema` support
- **Validation**: Missing critical pre-save/publish validations
- **Node Definitions**: Missing `outputs`, `passthrough`, `configSchema` fields

The recommended implementation plan provides a phased approach to align the codebase with the specification while maintaining backward compatibility where possible.

