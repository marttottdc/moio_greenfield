/**
 * Flow Validator - Comprehensive validation for flows
 * Matches spec v2: validates structure, expressions, schemas, edges, branches
 * 
 * Flow Data Rules - Input & Context Immutability:
 * 
 * Rule 1.1 - Input Origin (REGLA ÚNICA - sin excepciones):
 *   - Webhook → input.body = request.body
 *   - Event → input.body = event.payload
 *   - Scheduled → input.body = {}
 *   Todos los triggers exponen su payload bajo input.body (sin excepciones)
 * 
 * Rule 1.2 - Input Immutability:
 *   - input is immutable during entire flow execution
 *   - No node can modify input
 *   - No node can overwrite keys of input
 *   - No node can delete keys of input
 *   - Any attempt to modify is invalid by design
 * 
 * Rule 2.1 - Context Origin:
 *   - context is the space for flow-derived data
 *   - Initially empty: context = {}
 *   - Built progressively by transformation nodes
 * 
 * Rule 2.2 - Context Writing:
 *   - Only transformation nodes can write to context
 *   - Examples: data_set_values, fetch_*, query_*, compute_*
 * 
 * Rule 2.3 - Context Extension:
 *   - Each node extends context, doesn't replace it
 *   - New keys → added
 *   - Existing keys → explicitly overwritten
 * 
 * Rule 3.1 - Reading Data:
 *   - All nodes can read: input.* and context.*
 * 
 * Rule 3.2 - Namespace Priority:
 *   - input and context are distinct namespaces
 *   - input.foo ≠ context.foo
 *   - No implicit shadowing
 *   - All ambiguity must be resolved explicitly
 * 
 * Rule 4.1 - Branch Evaluation:
 *   - Branch evaluates conditions on input and/or context
 *   - Examples: input.mensaje == 'alerta', context.priority == 'high'
 * 
 * Rule 4.2 - Branch No Mutation:
 *   - Branch never modifies input nor context
 *   - Branch only decides paths
 * 
 * Rule 5.1 - Tool Reading:
 *   - Tools can read input and context
 * 
 * Rule 5.2 - Tool Writing:
 *   - Tools should NOT modify context unless explicitly declared
 *   - (e.g., tools that return structured results)
 * 
 * Rule 6.1 - Editor Validation:
 *   - Editor MUST validate:
 *     - No writes to input exist
 *     - Expressions access only input and context
 *     - Paths exist according to schema
 * 
 * Rule 7.1 - Runtime Trust:
 *   - Runtime trusts the editor
 *   - If flow was published:
 *     - Runtime doesn't revalidate schemas
 *     - Doesn't fix invalid accesses
 *     - Executes faithfully
 * 
 * Absolute Rule (summary):
 *   "input enters once and doesn't change.
 *    context is built step by step."
 * 
 * Closing phrase (for the team):
 *   "If you need to change data, don't touch input.
 *    Derive context."
 */

import { Node, Edge } from "reactflow";
import { CustomNodeData, BackendNodeDefinition } from "./types";
import { convertPortsToOutputs } from "./dataFlowAnalyzer";
import { normalizeBranchConfig, deriveBranchOutputs, isBranchNodeType } from "./branchUtils";
import {
  flattenCtxSchemaToAvailableData,
  ctxPathExistsInFlattenedSchema,
  validateCtxPath,
  validateNormalizeSourcePath,
  validateSandboxedExpression,
} from "./sandboxedExpressions";

/**
 * Comprehensive flow validation result
 */
export interface FlowValidationResult {
  isValid: boolean;
  errors: ValidationError[];
  warnings: ValidationError[];
}

export interface ValidationError {
  type: string;
  message: string;
  nodeId?: string;
  nodeLabel?: string;
  edgeId?: string;
  details?: string;
}

/**
 * Validate all edges have mandatory sourceHandle (v2 spec)
 */
function validateEdgesHaveSourceHandle(
  edges: Edge[]
): ValidationError[] {
  const errors: ValidationError[] = [];
  
  for (const edge of edges) {
    if (!edge.sourceHandle) {
      errors.push({
        type: "missing_source_handle",
        message: `Edge ${edge.id} is missing required sourceHandle`,
        edgeId: edge.id,
        details: "All edges must specify which output port they connect from (v2 spec requirement)",
      });
    }
  }
  
  return errors;
}

/**
 * Validate sourceHandle matches an output in source node
 */
function validateSourceHandleMatchesOutput(
  edges: Edge[],
  nodes: Node<CustomNodeData>[],
  nodeDefinitions: Record<string, BackendNodeDefinition>
): ValidationError[] {
  const errors: ValidationError[] = [];
  const nodeMap = new Map(nodes.map(n => [n.id, n]));
  
  for (const edge of edges) {
    if (!edge.sourceHandle) continue; // Already validated above
    
    const sourceNode = nodeMap.get(edge.source);
    if (!sourceNode) continue;
    
    // For branch nodes, use deriveBranchOutputs to get actual outputs from config
    let outputNames: string[];
    if (isBranchNodeType(sourceNode.data.type)) {
      const config = normalizeBranchConfig(sourceNode.data.config);
      outputNames = deriveBranchOutputs(config);
    } else {
      const nodeDef = nodeDefinitions[sourceNode.data.type];
      const outputs = convertPortsToOutputs(nodeDef, sourceNode);
      outputNames = outputs.map(o => o.name);
    }
    
    if (!outputNames.includes(edge.sourceHandle)) {
      errors.push({
        type: "invalid_source_handle",
        message: `Edge ${edge.id} references non-existent output "${edge.sourceHandle}" (Node: ${sourceNode.data.label})`,
        edgeId: edge.id,
        nodeId: edge.source,
        nodeLabel: sourceNode.data.label,
        details: `Available outputs: ${outputNames.join(", ")}`,
      });
    }
  }
  
  return errors;
}

// ============================================================================
// Spec-aligned validation (ctx contract + sandboxed expressions)
// ============================================================================

const CONTROL_NODE_TYPES = new Set<string>(["logic_branch", "logic_condition", "logic_while"]);
const LEGACY_CONTROL_NODE_TYPES = new Set<string>(["branch", "condition", "while"]);

function isControlNodeType(nodeType?: string): boolean {
  if (!nodeType) return false;
  return CONTROL_NODE_TYPES.has(nodeType) || LEGACY_CONTROL_NODE_TYPES.has(nodeType);
}

function isNormalizeNodeType(nodeType?: string): boolean {
  return nodeType === "logic_normalize" || nodeType === "normalize";
}

function isTriggerNodeType(nodeType?: string): boolean {
  if (!nodeType) return false;
  return (
    nodeType.startsWith("trigger_") ||
    nodeType === "webhook" ||
    nodeType === "event" ||
    nodeType === "scheduled" ||
    nodeType === "trigger_webhook" ||
    nodeType === "trigger_event" ||
    nodeType === "trigger_scheduled"
  );
}

function topologicalSort(
  nodes: Node<CustomNodeData>[],
  edges: Edge[]
): { order: string[]; hasCycle: boolean; cycleNodeIds: string[]; predecessors: Map<string, string[]> } {
  const inDegree = new Map<string, number>();
  const adjacency = new Map<string, string[]>();
  const predecessors = new Map<string, string[]>();

  for (const n of nodes) {
    inDegree.set(n.id, 0);
    adjacency.set(n.id, []);
    predecessors.set(n.id, []);
  }

  for (const e of edges) {
    if (!inDegree.has(e.source) || !inDegree.has(e.target)) continue;
    adjacency.get(e.source)!.push(e.target);
    predecessors.get(e.target)!.push(e.source);
    inDegree.set(e.target, (inDegree.get(e.target) || 0) + 1);
  }

  const queue: string[] = [];
  for (const [id, deg] of inDegree.entries()) {
    if (deg === 0) queue.push(id);
  }

  const order: string[] = [];
  while (queue.length > 0) {
    const id = queue.shift()!;
    order.push(id);
    for (const nxt of adjacency.get(id) || []) {
      inDegree.set(nxt, (inDegree.get(nxt) || 0) - 1);
      if (inDegree.get(nxt) === 0) queue.push(nxt);
    }
  }

  const hasCycle = order.length !== nodes.length;
  const cycleNodeIds = hasCycle ? nodes.filter((n) => !order.includes(n.id)).map((n) => n.id) : [];
  return { order, hasCycle, cycleNodeIds, predecessors };
}

function validateNormalizeNodeConfigs(nodes: Node<CustomNodeData>[]): ValidationError[] {
  const errors: ValidationError[] = [];

  const allowedTypes = new Set(["string", "number", "integer", "boolean", "object", "array"]);

  for (const node of nodes) {
    if (!isNormalizeNodeType(node.data.type)) continue;
    const cfg = node.data.config || {};
    const mappings = (cfg as any).mappings;

    if (!Array.isArray(mappings) || mappings.length === 0) {
      errors.push({
        type: "normalize_missing_mappings",
        message: `Normalize node "${node.data.label}" must define config.mappings[]`,
        nodeId: node.id,
        nodeLabel: node.data.label,
        details: "Add at least one mapping to define ctx.*",
      });
      continue;
    }

    for (let i = 0; i < mappings.length; i++) {
      const m = mappings[i] ?? {};
      const ctxPath = String(m.ctx_path ?? "").trim();
      const sourcePath = String(m.source_path ?? "").trim();
      const t = String(m.type ?? "").trim();

      const ctxCheck = validateCtxPath(ctxPath);
      if (!ctxCheck.ok) {
        errors.push({
          type: "invalid_ctx_path",
          message: `Normalize mapping #${i + 1} has invalid ctx_path "${ctxPath}"`,
          nodeId: node.id,
          nodeLabel: node.data.label,
          details: ctxCheck.reason,
        });
      }

      const srcCheck = validateNormalizeSourcePath(sourcePath);
      if (!srcCheck.ok) {
        errors.push({
          type: "invalid_source_path",
          message: `Normalize mapping #${i + 1} has invalid source_path "${sourcePath}"`,
          nodeId: node.id,
          nodeLabel: node.data.label,
          details: srcCheck.reason,
        });
      }

      if (t && !allowedTypes.has(t)) {
        errors.push({
          type: "invalid_mapping_type",
          message: `Normalize mapping #${i + 1} has invalid type "${t}"`,
          nodeId: node.id,
          nodeLabel: node.data.label,
          details: "Allowed: string | number | integer | boolean | object | array",
        });
      }
    }
  }

  return errors;
}

function validateControlNodesRequireNormalizeUpstream(
  nodes: Node<CustomNodeData>[],
  edges: Edge[]
): ValidationError[] {
  const errors: ValidationError[] = [];

  // Only sandboxed control-flow nodes require Normalize/ctx.* upstream:
  // - logic_branch / logic_condition / logic_while (and their legacy aliases)
  const isSandboxedControlNode = (type?: string) =>
    type === "logic_branch" ||
    type === "branch" ||
    type === "logic_condition" ||
    type === "condition" ||
    type === "logic_while" ||
    type === "while";

  const nodesThatRequireCtx = nodes.filter((n) => isSandboxedControlNode(n.data.type));
  if (nodesThatRequireCtx.length === 0) return errors;

  const normalizeNodes = nodes.filter((n) => isNormalizeNodeType(n.data.type));
  if (normalizeNodes.length === 0) {
    // More explicit error (in addition to per-node checks)
    errors.push({
      type: "missing_normalize_node",
      message: "Flow contains control-flow nodes (Branch/Condition/While) but no Normalize node (logic_normalize)",
      details: "Add a Normalize node after the trigger to define ctx for sandboxed expressions.",
    });
    // still continue so we can flag each control node too
  }

  const { order, predecessors } = topologicalSort(nodes, edges);
  const nodeById = new Map(nodes.map((n) => [n.id, n]));

  const normalizedOnAllPaths = new Map<string, boolean>();
  for (const id of order) {
    const node = nodeById.get(id);
    if (!node) continue;
    const preds = predecessors.get(id) || [];
    const isNormalize = isNormalizeNodeType(node.data.type);
    if (isNormalize) {
      normalizedOnAllPaths.set(id, true);
      continue;
    }
    if (preds.length === 0) {
      normalizedOnAllPaths.set(id, false);
      continue;
    }
    normalizedOnAllPaths.set(id, preds.every((p) => normalizedOnAllPaths.get(p) === true));
  }

  for (const node of nodesThatRequireCtx) {
    // Spec A: "hasCtx" is true if there is a Normalize upstream from a Trigger.
    // For validation we still require Normalize upstream; we treat "any path" as having ctx,
    // and rely on backend for stricter execution-path guarantees.
    // (This matches UX: ctx exists after Normalize.)
    const ok = normalizedOnAllPaths.get(node.id) === true;
    if (!ok) {
      errors.push({
        type: "missing_normalize_upstream",
        message: `Node "${node.data.label}" requires a Normalize node upstream in every path`,
        nodeId: node.id,
        nodeLabel: node.data.label,
        details: "No contract defined. Add a logic_normalize node upstream to define ctx.",
      });
    }
  }

  return errors;
}

function validateSandboxedControlExpressions(
  nodes: Node<CustomNodeData>[],
  ctxSchema?: unknown
): { errors: ValidationError[]; warnings: ValidationError[] } {
  const errors: ValidationError[] = [];
  const warnings: ValidationError[] = [];

  const ctxFields = flattenCtxSchemaToAvailableData(ctxSchema);

  for (const node of nodes) {
    const nodeType = node.data.type;
    const nodeLabel = node.data.label || nodeType;
    const cfg = node.data.config || {};

    // Branch: config.rules[].expr
    if (nodeType === "logic_branch" || nodeType === "branch") {
      const rules = Array.isArray((cfg as any).rules) ? ((cfg as any).rules as Array<any>) : [];
      for (const rule of rules) {
        const expr = typeof rule?.expr === "string" ? rule.expr : "";
        if (!expr.trim()) continue;
        const v = validateSandboxedExpression(expr);
        if (!v.ok) {
          errors.push({
            type: "invalid_sandboxed_expression",
            message: `Invalid sandboxed expression in "${nodeLabel}" (rule "${rule?.name || "rule"}"): ${v.errors[0]?.message || "invalid"}`,
            nodeId: node.id,
            nodeLabel,
            details: "Las expresiones solo pueden leer ctx.* (no payload ni input).",
          });
        } else if (ctxFields.length > 0) {
          for (const p of v.referencedCtxPaths) {
            if (!ctxPathExistsInFlattenedSchema(ctxFields, p)) {
              warnings.push({
                type: "unknown_ctx_path",
                message: `Expression references undefined path "${p}" (node "${nodeLabel}")`,
                nodeId: node.id,
                nodeLabel,
                details: "The backend builds ctx_schema from Normalize mappings. Add a mapping or fix the path.",
              });
            }
          }
        }
      }
    }

    // Condition: config.expr
    if (nodeType === "logic_condition" || nodeType === "condition") {
      const expr = typeof (cfg as any).expr === "string" ? ((cfg as any).expr as string) : "";
      if (expr.trim()) {
        const v = validateSandboxedExpression(expr);
        if (!v.ok) {
          errors.push({
            type: "invalid_sandboxed_expression",
            message: `Invalid sandboxed expression in "${nodeLabel}": ${v.errors[0]?.message || "invalid"}`,
            nodeId: node.id,
            nodeLabel,
            details: "Las expresiones solo pueden leer ctx.* (no payload ni input).",
          });
        } else if (ctxFields.length > 0) {
          for (const p of v.referencedCtxPaths) {
            if (!ctxPathExistsInFlattenedSchema(ctxFields, p)) {
              warnings.push({
                type: "unknown_ctx_path",
                message: `Expression references undefined path "${p}" (node "${nodeLabel}")`,
                nodeId: node.id,
                nodeLabel,
              });
            }
          }
        }
      }
    }

    // While: config.expr
    if (nodeType === "logic_while" || nodeType === "while") {
      const expr =
        typeof (cfg as any).expr === "string"
          ? ((cfg as any).expr as string)
          : typeof (cfg as any).condition === "string"
            ? ((cfg as any).condition as string)
            : "";
      if (expr.trim()) {
        const v = validateSandboxedExpression(expr);
        if (!v.ok) {
          errors.push({
            type: "invalid_sandboxed_expression",
            message: `Invalid sandboxed expression in "${nodeLabel}": ${v.errors[0]?.message || "invalid"}`,
            nodeId: node.id,
            nodeLabel,
            details: "Las expresiones solo pueden leer ctx.* (no payload ni input).",
          });
        } else if (ctxFields.length > 0) {
          for (const p of v.referencedCtxPaths) {
            if (!ctxPathExistsInFlattenedSchema(ctxFields, p)) {
              warnings.push({
                type: "unknown_ctx_path",
                message: `Expression references undefined path "${p}" (node "${nodeLabel}")`,
                nodeId: node.id,
                nodeLabel,
              });
            }
          }
        }
      }
    }
  }

  // If schema missing, don't block; but we can surface a UX hint as warning.
  const hasControlNodes = nodes.some((n) => isControlNodeType(n.data.type));
  if (hasControlNodes && ctxFields.length === 0) {
    warnings.push({
      type: "ctx_schema_missing",
      message: "ctx_schema not available: autocomplete and undefined-path warnings are disabled",
      details: "You can still edit expressions, but they remain restricted to ctx.* only.",
    });
  }

  return { errors, warnings };
}

/**
 * Validate branch else output name is valid (unique, non-empty if set)
 */
function validateBranchElseOutput(
  nodes: Node<CustomNodeData>[],
  nodeDefinitions: Record<string, BackendNodeDefinition>
): ValidationError[] {
  const errors: ValidationError[] = [];
  
  for (const node of nodes) {
    if (!isBranchNodeType(node.data.type)) continue;
    
    const config = normalizeBranchConfig(node.data.config);
    const ruleOutputs = (config.rules || []).map((r: any, idx: number) => String(r?.name ?? `rule_${idx + 1}`).trim()).filter(Boolean);
    
    if (config.else && typeof config.else === "string") {
      const elseName = config.else.trim();
      if (!elseName) {
        errors.push({
          type: "invalid_branch_else",
          message: `Branch node "${node.data.label}" has an empty else output name`,
          nodeId: node.id,
          nodeLabel: node.data.label,
        });
        continue;
      }

      // Else must be a unique output handle (cannot collide with a rule output name).
      if (ruleOutputs.includes(elseName)) {
        errors.push({
          type: "invalid_branch_else",
          message: `Branch node "${node.data.label}" has else output "${elseName}" that collides with a rule output name`,
          nodeId: node.id,
          nodeLabel: node.data.label,
          details: `Rule outputs: ${ruleOutputs.join(", ")}`,
        });
      }
    }
  }
  
  return errors;
}

/**
 * Validate Input & Context Immutability Rules
 * Rule 1.2: input is immutable - no node can modify input
 * Rule 2.2: Only transformation nodes can write to context
 * Rule 3.1: All nodes can read input.* and context.*
 */
function validateInputContextImmutability(
  nodes: Node<CustomNodeData>[],
  nodeDefinitions: Record<string, BackendNodeDefinition>
): ValidationError[] {
  const errors: ValidationError[] = [];
  
  // Transformation nodes that are allowed to write to context
  const transformationNodeTypes = [
    'data_set_values',
    'set_values',
    'set_value',
    'assign',
    'data.set_values',
  ];
  
  // Nodes that fetch/compute data (also write to context)
  const computeNodeTypes = [
    'fetch_',
    'query_',
    'compute_',
  ];
  
  const isTransformationNode = (nodeType: string): boolean => {
    if (transformationNodeTypes.some(t => nodeType === t || nodeType.includes(t))) {
      return true;
    }
    return computeNodeTypes.some(prefix => nodeType.startsWith(prefix));
  };
  
  for (const node of nodes) {
    const nodeType = node.data.type;
    const nodeLabel = node.data.label || nodeType;
    const config = node.data.config || {};
    
    // Check data_set_values nodes for attempts to write to input.*
    if (nodeType === 'data_set_values' || 
        nodeType === 'set_values' || 
        nodeType === 'set_value' ||
        nodeType === 'assign' ||
        nodeType === 'data.set_values' ||
        nodeType.includes('set_values') ||
        nodeType.includes('set_value')) {
      
      const configValues = config.values;
      const pairs: Array<{key: string; value: string}> = configValues 
        ? (Array.isArray(configValues) 
            ? configValues.filter((p: any) => p.key && p.key.trim() !== '')
            : (typeof configValues === 'object' 
                ? Object.entries(configValues).map(([k, v]) => ({ key: k, value: String(v) })) 
                : []))
        : [];
      
      // Rule 1.2: Check for attempts to write to input.*
      for (const pair of pairs) {
        const key = pair.key.trim();
        
        // Check if key starts with "input."
        if (key.startsWith('input.')) {
          errors.push({
            type: "input_immutability_violation",
            message: `Node "${nodeLabel}" attempts to write to "${key}" - input is immutable`,
            nodeId: node.id,
            nodeLabel: nodeLabel,
            details: "input can only be read, never modified. Use context.* for derived data.",
          });
        }
        
        // Check if key is exactly "input"
        if (key === 'input') {
          errors.push({
            type: "input_immutability_violation",
            message: `Node "${nodeLabel}" attempts to overwrite "input" - input is immutable`,
            nodeId: node.id,
            nodeLabel: nodeLabel,
            details: "input can only be read, never modified. Use context.* for derived data.",
          });
        }

        // Flow config variables are read-only: block writes to config.*
        if (key === 'config' || key.startsWith('config.')) {
          errors.push({
            type: "config_immutability_violation",
            message: `Node "${nodeLabel}" attempts to write to "${key}" - config is immutable`,
            nodeId: node.id,
            nodeLabel: nodeLabel,
            details: "config.* can only be read, never modified. Change config values in Flow Properties.",
          });
        }

        // Node outputs are read-only: block writes to nodes.*
        if (key === 'nodes' || key.startsWith('nodes.')) {
          errors.push({
            type: "nodes_immutability_violation",
            message: `Node "${nodeLabel}" attempts to write to "${key}" - nodes.* is read-only`,
            nodeId: node.id,
            nodeLabel: nodeLabel,
            details: "nodes.<nodeId>.output.* represents node outputs and cannot be written to directly.",
          });
        }

        // System is read-only: block writes to system.*
        if (key === 'system' || key.startsWith('system.')) {
          errors.push({
            type: "system_immutability_violation",
            message: `Node "${nodeLabel}" attempts to write to "${key}" - system.* is read-only`,
            nodeId: node.id,
            nodeLabel: nodeLabel,
            details: "system.* contains finite execution facts and cannot be written to.",
          });
        }
      }
    }
    
    // Check node definitions for explicit input modifications
    const nodeDef = nodeDefinitions[nodeType];
    if (nodeDef?.data_effects) {
      const effects = nodeDef.data_effects;
      
      // Check transforms for input.* fields
      if (effects.transforms) {
        for (const transform of effects.transforms) {
          if (transform.field.startsWith('input.')) {
            errors.push({
              type: "input_immutability_violation",
              message: `Node definition "${nodeType}" declares transformation of "${transform.field}" - input is immutable`,
              nodeId: node.id,
              nodeLabel: nodeLabel,
              details: "input can only be read, never modified. Use context.* for derived data.",
            });
          }
        }
      }
      
      // Check computes for input.* fields
      if (effects.computes) {
        for (const compute of effects.computes) {
          if (compute.field.startsWith('input.')) {
            errors.push({
              type: "input_immutability_violation",
              message: `Node definition "${nodeType}" declares computation of "${compute.field}" - input is immutable`,
              nodeId: node.id,
              nodeLabel: nodeLabel,
              details: "input can only be read, never modified. Use context.* for derived data.",
            });
          }
        }
      }
    }
  }
  
  return errors;
}

/**
 * Validate that expressions only access input.* and context.*
 * Rule 3.1: All nodes can read input.* and context.*
 * Rule 3.2: input and context are distinct namespaces
 */
function validateExpressionNamespaces(
  nodes: Node<CustomNodeData>[],
  nodeDefinitions: Record<string, BackendNodeDefinition>
): ValidationError[] {
  const errors: ValidationError[] = [];
  
  // Extract all expressions from nodes
  for (const node of nodes) {
    const nodeType = node.data.type;
    const nodeLabel = node.data.label || nodeType;
    const config = node.data.config || {};

    // Hard-ban legacy namespaces in the flow language contract
    const banLegacyNamespaces = (expr: string, fieldLabel: string) => {
      if (/\b(context|vars|ctx)\./.test(expr)) {
        errors.push({
          type: "invalid_namespace_access",
          message: `${fieldLabel} expression "${expr}" accesses legacy namespace (context/vars/ctx). Allowed: input.*, nodes.<id>.output.*, config.*, system.*`,
          nodeId: node.id,
          nodeLabel: nodeLabel,
          details: "Update the expression to use the canonical namespaces. `config.*` is for flow config variables.",
        });
      }
    };
    
    // Check branch node expressions
    if (isBranchNodeType(nodeType)) {
      const rules = config.rules as Array<{ expr?: string }> | undefined;
      if (rules) {
        for (const rule of rules) {
          if (rule.expr) {
            banLegacyNamespaces(rule.expr, "Branch rule");
            const paths = extractPathsFromExpression(rule.expr);
            for (const path of paths) {
              // Only allow input.*, nodes.*, config.*, system.*
              if (path.namespace !== 'input' && path.namespace !== 'nodes' && path.namespace !== 'config' && path.namespace !== 'system') {
                errors.push({
                  type: "invalid_namespace_access",
                  message: `Branch rule expression "${rule.expr}" accesses "${path.fullPath}" - only input.*, nodes.*, config.*, system.* are allowed`,
                  nodeId: node.id,
                  nodeLabel: nodeLabel,
                  details: `Invalid namespace: ${path.namespace}. Allowed: input, nodes, config, system.`,
                });
              }
            }
          }
        }
      }
    }
    
    // Check data_set_values value expressions
    if (nodeType === 'data_set_values' || 
        nodeType === 'set_values' || 
        nodeType === 'set_value' ||
        nodeType === 'assign' ||
        nodeType === 'data.set_values' ||
        nodeType.includes('set_values') ||
        nodeType.includes('set_value')) {
      
      const configValues = config.values;
      const pairs: Array<{key: string; value: string}> = configValues 
        ? (Array.isArray(configValues) 
            ? configValues.filter((p: any) => p.key && p.key.trim() !== '')
            : (typeof configValues === 'object' 
                ? Object.entries(configValues).map(([k, v]) => ({ key: k, value: String(v) })) 
                : []))
        : [];
      
      for (const pair of pairs) {
        if (pair.value) {
          banLegacyNamespaces(pair.value, "Value");
          const paths = extractPathsFromExpression(pair.value);
          for (const path of paths) {
            // Only allow input.*, nodes.*, config.*, system.*
            if (path.namespace !== 'input' && path.namespace !== 'nodes' && path.namespace !== 'config' && path.namespace !== 'system') {
              errors.push({
                type: "invalid_namespace_access",
                message: `Value expression "${pair.value}" accesses "${path.fullPath}" - only input.*, nodes.*, config.*, system.* are allowed`,
                nodeId: node.id,
                nodeLabel: nodeLabel,
                details: `Invalid namespace: ${path.namespace}. Allowed: input, nodes, config, system.`,
              });
            }
          }
        }
      }
    }
  }
  
  return errors;
}

/**
 * Comprehensive flow validation
 * Validates all v2 spec requirements
 */
export function validateFlowComprehensive(
  nodes: Node<CustomNodeData>[],
  edges: Edge[],
  nodeDefinitions: Record<string, BackendNodeDefinition>,
  _configSchema?: unknown,
  _configValues?: Record<string, unknown>,
  ctxSchema?: unknown
): FlowValidationResult {
  const errors: ValidationError[] = [];
  const warnings: ValidationError[] = [];
  
  // 1. Validate edges have sourceHandle (v2 spec: mandatory)
  errors.push(...validateEdgesHaveSourceHandle(edges));
  
  // 2. Validate sourceHandle matches outputs
  errors.push(...validateSourceHandleMatchesOutput(edges, nodes, nodeDefinitions));

  // 3. Cycle detection (should already be prevented at edge creation time)
  const topo = topologicalSort(nodes, edges);
  if (topo.hasCycle) {
    errors.push({
      type: "cycle_detected",
      message: `Flow contains a cycle involving ${topo.cycleNodeIds.length} node(s)`,
      details: `Cyclic nodes: ${topo.cycleNodeIds.join(", ")}`,
    });
    return { isValid: false, errors, warnings };
  }

  // 4. Branch else output names
  errors.push(...validateBranchElseOutput(nodes, nodeDefinitions));

  // 5. Normalize config validation
  errors.push(...validateNormalizeNodeConfigs(nodes));

  // 6. Control nodes require Normalize upstream
  errors.push(...validateControlNodesRequireNormalizeUpstream(nodes, edges));

  // 7. Sandboxed expressions (Branch / Condition / While)
  const exprValidation = validateSandboxedControlExpressions(nodes, ctxSchema);
  errors.push(...exprValidation.errors);
  warnings.push(...exprValidation.warnings);
  
  return {
    isValid: errors.length === 0,
    errors,
    warnings,
  };
}

