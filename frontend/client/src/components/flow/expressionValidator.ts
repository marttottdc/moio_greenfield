/**
 * Expression Validator - Validates expressions against schema
 * Matches spec v2: validates paths exist in schema, respects unknown blocking
 */

import { SchemaNode, UnknownSchema, ObjectSchema, PrimitiveSchema } from "./types";

/**
 * Extracted path from an expression
 */
export interface ExtractedPath {
  path: string;           // e.g., "input.body.email"
  namespace: string;      // "input", "context", or "vars"
  fullPath: string;       // Full path including namespace
}

/**
 * Validation error for an expression
 */
export interface ExpressionValidationError {
  expression: string;
  path: string;
  reason: string;
  nodeId?: string;
  nodeLabel?: string;
}

/**
 * Validation result for a flow
 */
export interface FlowValidationResult {
  isValid: boolean;
  errors: ExpressionValidationError[];
  warnings: ExpressionValidationError[];
}

/**
 * Extract field paths from an expression
 * Supports Python-like expressions and template strings
 * Namespace-aware: extracts input.*, nodes.<nodeId>.output.*, config.*, system.*
 */
export function extractPathsFromExpression(expr: string): ExtractedPath[] {
  const paths: ExtractedPath[] = [];
  
  // Patterns to match:
  // - input.field, input.field.subfield
  // - config.field
  // - system.field
  // - nodes.<nodeId>.output.field
  // - ${input.field} (template strings)
  // - {input.field} (f-strings)
  
  const patterns = [
    // Template strings: ${input.field} / ${config.field} / ${system.field} / ${nodes.<id>.output.field}
    /\$\{([a-zA-Z_][a-zA-Z0-9_]*\.(?:[a-zA-Z_][a-zA-Z0-9_]*\.?)*)\}/g,
    // F-strings: {input.field}
    /\{([a-zA-Z_][a-zA-Z0-9_]*\.(?:[a-zA-Z_][a-zA-Z0-9_]*\.?)*)\}/g,
    // Direct access: input.field, config.field, system.field
    /\b(input|config|system)\.([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*)/g,
    // Direct access: nodes.<nodeId>.output.field
    /\bnodes\.([a-zA-Z0-9_-]+)\.output\.([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*)/g,
  ];
  
  for (const pattern of patterns) {
    let match;
    while ((match = pattern.exec(expr)) !== null) {
      let namespace: string;
      let path: string;
      
      if (match[1] && (match[1] === 'input' || match[1] === 'config' || match[1] === 'system')) {
        // Pattern matched namespace.field format
        namespace = match[1];
        path = match[2] || '';
      } else if (match[0] && match[0].startsWith("nodes.") && match[1] && match[2]) {
        namespace = "nodes";
        path = `${match[1]}.output.${match[2]}`;
      } else if (match[1] && match[1].includes('.')) {
        // Pattern matched full path (e.g., "input.field.subfield")
        const parts = match[1].split('.');
        namespace = parts[0];
        path = parts.slice(1).join('.');
      } else {
        continue;
      }
      
      if (namespace && (namespace === 'input' || namespace === 'nodes' || namespace === 'config' || namespace === 'system')) {
        paths.push({
          path,
          namespace,
          fullPath: `${namespace}.${path}`,
        });
      }
    }
  }
  
  // Deduplicate
  const seen = new Set<string>();
  return paths.filter(p => {
    const key = p.fullPath;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

/**
 * Check if a path exists in a schema
 * Respects UnknownSchema blocking - returns false if path goes through unknown
 */
export function pathExistsInSchema(
  path: string,
  schema: SchemaNode | undefined,
  namespace: string = "input"
): { exists: boolean; reason?: string } {
  if (!schema) {
    return { exists: false, reason: "Schema is undefined" };
  }
  
  // UnknownSchema blocks deep access
  if (schema.kind === "unknown") {
    if (path) {
      return { 
        exists: false, 
        reason: `Cannot access "${path}" - schema is unknown. Declare the schema in the webhook config (expected_schema) or add a normalization node before this branch.` 
      };
    }
    return { exists: false, reason: "Cannot access nested properties of unknown type" };
  }
  
  // PrimitiveSchema - only root path exists
  if (schema.kind === "primitive") {
    return { exists: path === "" || path === namespace, reason: path ? "Primitive type has no nested properties" : undefined };
  }
  
  // ObjectSchema - check path recursively (preserves nested structure)
  if (schema.kind === "object") {
    if (!path || path === "") {
      return { exists: true };
    }
    
    const parts = path.split('.');
    let currentSchema: SchemaNode = schema;
    
    for (let i = 0; i < parts.length; i++) {
      const part = parts[i];
      
      if (currentSchema.kind !== "object") {
        return { exists: false, reason: `Path "${parts.slice(0, i).join('.')}" is not an object` };
      }
      
      const objSchema = currentSchema as ObjectSchema;
      if (!(part in objSchema.properties)) {
        const availableProps = Object.keys(objSchema.properties).join(", ");
        const pathSoFar = parts.slice(0, i).join(".");
        const fullPathSoFar = pathSoFar ? `${namespace}.${pathSoFar}` : namespace;
        
        // Special case: if we're at the root of "input" and "body" exists, suggest using input.body.*
        let suggestion = "";
        if (namespace === "input" && pathSoFar === "" && "body" in objSchema.properties) {
          const bodySchema = objSchema.properties["body"];
          if (bodySchema) {
            if (bodySchema.kind === "unknown") {
              suggestion = ` The webhook body schema is unknown. Declare the schema in the webhook config (expected_schema) or use "${namespace}.body.${part}" if the field exists.`;
            } else if (bodySchema.kind === "object") {
              const bodyProps = Object.keys((bodySchema as ObjectSchema).properties);
              if (bodyProps.length > 0) {
                suggestion = ` Did you mean "${namespace}.body.${part}"? Available properties in body: ${bodyProps.join(", ")}.`;
              } else {
                suggestion = ` Did you mean "${namespace}.body.${part}"?`;
              }
            } else {
              suggestion = ` Did you mean "${namespace}.body.${part}"?`;
            }
          }
        }
        
        return { 
          exists: false, 
          reason: `Property "${part}" does not exist in schema at "${fullPathSoFar}". Available properties: ${availableProps || "none"}.${suggestion} Add a normalization node to define "${part}" or check the upstream schema.` 
        };
      }
      
      const nextSchema = objSchema.properties[part];
      
      // Check for unknown blocking
      if (nextSchema.kind === "unknown" && i < parts.length - 1) {
        return { exists: false, reason: `Cannot access nested properties of "${part}" (unknown type)` };
      }
      
      // Handle arrays - nested paths can access array items
      if (nextSchema.kind === "array" && i < parts.length - 1) {
        // Continue validation with array items schema
        currentSchema = nextSchema.items;
        continue;
      }
      
      currentSchema = nextSchema;
    }
    
    return { exists: true };
  }
  
  // ArraySchema - validate against item schema (preserves nested structure)
  if (schema.kind === "array") {
    if (!path || path === "") {
      return { exists: true };
    }
    // For arrays, validate path against item schema
    return pathExistsInSchema(path, schema.items, namespace);
  }
  
  return { exists: false, reason: "Unknown schema type" };
}

/**
 * Validate an expression against available schemas
 */
export function validateExpression(
  expr: string,
  availableSchemas: Map<string, SchemaNode>, // namespace -> schema
  nodeId?: string,
  nodeLabel?: string
): ExpressionValidationError[] {
  const errors: ExpressionValidationError[] = [];
  const paths = extractPathsFromExpression(expr);
  
  for (const extractedPath of paths) {
    const schema = availableSchemas.get(extractedPath.namespace);
    const { exists, reason } = pathExistsInSchema(extractedPath.path, schema, extractedPath.namespace);
    
    if (!exists) {
      errors.push({
        expression: expr,
        path: extractedPath.fullPath,
        reason: reason || `Path "${extractedPath.fullPath}" does not exist`,
        nodeId,
        nodeLabel,
      });
    }
  }
  
  return errors;
}

/**
 * Validate all expressions in a flow
 * Checks expressions in node configs (branch rules, set_values, etc.)
 */
export function validateFlow(
  nodes: Array<{ id: string; data: { type: string; label: string; config?: Record<string, any> } }>,
  edges: Array<{ source: string; target: string; sourceHandle: string }>,
  nodeSchemas: Map<string, Map<string, SchemaNode>>, // node_id -> output_name -> schema
  availableDataAtNode: Map<string, SchemaNode> // node_id -> aggregate schema (for backward compatibility)
): FlowValidationResult {
  const errors: ExpressionValidationError[] = [];
  const warnings: ExpressionValidationError[] = [];
  
  for (const node of nodes) {
    const availableSchemas = new Map<string, SchemaNode>();

    // Prefer schema-driven aggregate at the node (built from the data-flow analysis),
    // then slice by namespace: input / nodes / config / system.
    const aggregate = availableDataAtNode.get(node.id);
    if (aggregate && aggregate.kind === "object") {
      const root = aggregate as ObjectSchema;
      const inputSchema = root.properties["input"];
      const nodesSchema = root.properties["nodes"];
      const configSchema = root.properties["config"];
      const systemSchema = root.properties["system"];

      if (inputSchema) availableSchemas.set("input", inputSchema);
      if (nodesSchema) availableSchemas.set("nodes", nodesSchema);
      if (configSchema) availableSchemas.set("config", configSchema);
      if (systemSchema) availableSchemas.set("system", systemSchema);
    }

    // Validate expressions in node config
    const config = node.data.config || {};
    
    // Branch nodes: validate rule expressions
    if (node.data.type === 'branch' || node.data.type === 'logic_branch') {
      const rules = config.rules as Array<{ expr?: string }> | undefined;
      if (rules) {
        for (const rule of rules) {
          if (rule.expr) {
            const ruleErrors = validateExpression(
              rule.expr,
              availableSchemas,
              node.id,
              node.data.label
            );
            errors.push(...ruleErrors);
          }
        }
      }
    }
    
    // Set values nodes: validate value expressions
    if (node.data.type === 'set_values' || node.data.type === 'data_set_values') {
      const values = config.values;
      if (values) {
        const valuePairs = Array.isArray(values) 
          ? values 
          : typeof values === 'object' 
            ? Object.entries(values).map(([k, v]) => ({ key: k, value: String(v) }))
            : [];
        
        for (const pair of valuePairs) {
          if (pair.value && typeof pair.value === 'string') {
            // Check if value contains expressions
            const valueErrors = validateExpression(
              pair.value,
              availableSchemas,
              node.id,
              node.data.label
            );
            warnings.push(...valueErrors); // Warnings for set_values (might be literal strings)
          }
        }
      }
    }
  }
  
  return {
    isValid: errors.length === 0,
    errors,
    warnings,
  };
}

