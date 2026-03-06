import { Node, Edge } from "reactflow";
import { 
  CustomNodeData, 
  AvailableDataField, 
  PortSchema, 
  PortDefinition,
  BackendNodeDefinition,
  DataEffect,
  DataEffectType,
  SchemaNode,
  PrimitiveSchema,
  ObjectSchema,
  UnknownSchema,
  PASSTHROUGH,
  NodeOutput
} from "./types";
import { isBranchNodeType, deriveBranchOutputs, normalizeBranchConfig } from "./branchUtils";

// ============================================================================
// CYCLE DETECTION
// ============================================================================

/**
 * Check if adding an edge from source to target would create a cycle.
 * Uses DFS to detect if target can reach source (which would mean source->target creates a cycle).
 */
export function wouldCreateCycle(
  edges: Edge[],
  newSource: string,
  newTarget: string
): boolean {
  // Build adjacency list from existing edges
  const adjacency = new Map<string, string[]>();
  for (const edge of edges) {
    if (!adjacency.has(edge.source)) {
      adjacency.set(edge.source, []);
    }
    adjacency.get(edge.source)!.push(edge.target);
  }
  
  // Add the new edge temporarily
  if (!adjacency.has(newSource)) {
    adjacency.set(newSource, []);
  }
  adjacency.get(newSource)!.push(newTarget);
  
  // DFS from newTarget to see if we can reach newSource
  const visited = new Set<string>();
  const stack = [newTarget];
  
  while (stack.length > 0) {
    const current = stack.pop()!;
    if (current === newSource) {
      return true; // Cycle detected!
    }
    if (visited.has(current)) continue;
    visited.add(current);
    
    const neighbors = adjacency.get(current) || [];
    for (const neighbor of neighbors) {
      if (!visited.has(neighbor)) {
        stack.push(neighbor);
      }
    }
  }
  
  return false;
}

// ============================================================================
// TOPOLOGICAL SORT (Kahn's Algorithm)
// ============================================================================

/**
 * Topological sort using Kahn's algorithm.
 * Returns node IDs in execution order.
 * Returns partial order if cycle exists (cycles are handled at edge creation time).
 */
function topologicalSort(nodes: Node<CustomNodeData>[], edges: Edge[]): { order: string[]; hasCycle: boolean; cycleNodeIds: string[] } {
  const inDegree = new Map<string, number>();
  const adjacency = new Map<string, string[]>();
  
  // Initialize
  for (const node of nodes) {
    inDegree.set(node.id, 0);
    adjacency.set(node.id, []);
  }
  
  // Build graph
  for (const edge of edges) {
    // Only process edges where both nodes exist
    if (inDegree.has(edge.source) && inDegree.has(edge.target)) {
      adjacency.get(edge.source)!.push(edge.target);
      inDegree.set(edge.target, inDegree.get(edge.target)! + 1);
    }
  }
  
  // Find nodes with no incoming edges (triggers/starts)
  const queue: string[] = [];
  inDegree.forEach((deg, id) => {
    if (deg === 0) queue.push(id);
  });
  
  const order: string[] = [];
  
  while (queue.length > 0) {
    const id = queue.shift()!;
    order.push(id);
    
    for (const next of adjacency.get(id)!) {
      inDegree.set(next, inDegree.get(next)! - 1);
      if (inDegree.get(next) === 0) {
        queue.push(next);
      }
    }
  }
  
  // If we didn't process all nodes, there's a cycle
  const hasCycle = order.length !== nodes.length;
  const cycleNodeIds = hasCycle 
    ? nodes.filter(n => !order.includes(n.id)).map(n => n.id)
    : [];
  
  return { order, hasCycle, cycleNodeIds };
}

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

function cloneEffect(e: DataEffect): DataEffect {
  return {
    type: e.type,
    appliedBy: e.appliedBy,
    nodeType: e.nodeType,
    description: e.description
  };
}

function cloneFieldDeep(field: AvailableDataField): AvailableDataField {
  return {
    key: field.key,
    type: field.type,
    description: field.description,
    source: field.source,
    effects: field.effects ? field.effects.map(cloneEffect) : undefined
  };
}

function addEffectIfNotExists(field: AvailableDataField, effect: DataEffect): void {
  if (!field.effects) {
    field.effects = [];
  }
  const effectKey = `${effect.type}|${effect.appliedBy}|${effect.nodeType || ''}|${effect.description || ''}`;
  const exists = field.effects.some(e => 
    `${e.type}|${e.appliedBy}|${e.nodeType || ''}|${e.description || ''}` === effectKey
  );
  if (!exists) {
    field.effects.push(cloneEffect(effect));
  }
}

function extractValidatedFieldsFromExpr(expr: string): string[] {
  const fields: string[] = [];
  const existsPatterns = [
    /(\w+(?:\.\w+)*)\s+(?:is\s+not\s+None|exists|!= ""|!= '')/gi,
    /(\w+(?:\.\w+)*)\s*(?:!=\s*null|!==\s*null)/gi,
    /bool\((\w+(?:\.\w+)*)\)/gi,
    /len\((\w+(?:\.\w+)*)\)\s*>\s*0/gi,
  ];
  
  for (const pattern of existsPatterns) {
    let match;
    while ((match = pattern.exec(expr)) !== null) {
      fields.push(match[1]);
    }
  }
  
  return Array.from(new Set(fields));
}

// ============================================================================
// SCHEMA EXTRACTION
// ============================================================================

/**
 * Extract fields from an example payload object (flat object with sample values)
 * Converts { deal_id: "uuid", title: "Test", value: 1000 } into field definitions
 */
function extractFieldsFromExamplePayload(
  payload: Record<string, any>,
  prefix: string = "",
  sourceName: string
): AvailableDataField[] {
  if (!payload || typeof payload !== 'object') return [];
  
  const fields: AvailableDataField[] = [];
  
  for (const [key, value] of Object.entries(payload)) {
    const fieldKey = prefix ? `${prefix}.${key}` : key;
    const valueType = Array.isArray(value) ? 'array' : typeof value;
    
    fields.push({
      key: fieldKey,
      type: valueType,
      description: `Example: ${JSON.stringify(value).substring(0, 50)}`,
      source: sourceName,
    });
    
    // Recurse into nested objects
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      fields.push(...extractFieldsFromExamplePayload(value, fieldKey, sourceName));
    }
    
    // Handle arrays with object items
    if (Array.isArray(value) && value.length > 0 && typeof value[0] === 'object') {
      // Include array root key as selectable (whole array)
      fields.push({
        key: fieldKey,
        type: "array",
        description: `Example: ${JSON.stringify(value).substring(0, 50)}`,
        source: sourceName,
      });
      fields.push(...extractFieldsFromExamplePayload(value[0], `${fieldKey}[]`, sourceName));
    }
  }
  
  return fields;
}

/**
 * Convert legacy PortSchema to SchemaNode (v2 spec)
 */
function convertPortSchemaToSchemaNode(schema: PortSchema | SchemaNode | undefined): SchemaNode | undefined {
  if (!schema) return undefined;
  
  // Already a SchemaNode (has kind discriminator)
  if ('kind' in schema) {
    return schema as SchemaNode;
  }
  
  // Legacy PortSchema - convert to SchemaNode
  const portSchema = schema as PortSchema;

  // JSON Schema sometimes uses `type: string | string[]` (e.g. ["string", "null"]).
  // Our PortSchema typing is looser at runtime, so normalize here.
  const normalizeType = (t: any): string | undefined => {
    if (typeof t === "string") return t;
    if (Array.isArray(t)) {
      // Prefer first non-nullish type
      const firstNonNull = t.find((x) => typeof x === "string" && x !== "null");
      return (firstNonNull ?? t.find((x) => typeof x === "string")) as string | undefined;
    }
    return undefined;
  };

  const normalizedType = normalizeType((portSchema as any).type);
  const SEGMENT_RE = /^[A-Za-z0-9_-]+$/;
  
  // Check for unknown type
  if (normalizedType === "unknown" || (!normalizedType && !(portSchema as any).properties && !(portSchema as any).items)) {
    return { kind: "unknown" };
  }
  
  // Array type - preserve nested structure
  if (normalizedType === "array" || (portSchema as any).items) {
    const itemsSchema = (portSchema as any).items;
    if (itemsSchema) {
      return {
        kind: "array",
        items: convertPortSchemaToSchemaNode(itemsSchema) || { kind: "unknown" },
      };
    }
    // Array without items schema - default to unknown items
    return {
      kind: "array",
      items: { kind: "unknown" },
    };
  }
  
  // Primitive types
  if (normalizedType && normalizedType !== "object" && normalizedType !== "array") {
    return {
      kind: "primitive",
      type: normalizedType as PrimitiveSchema["type"],
    };
  }
  
  // Object type with properties - preserve nested structure
  if ((portSchema as any).properties) {
    const properties: Record<string, SchemaNode> = {};
    for (const [key, prop] of Object.entries((portSchema as any).properties)) {
      // Source paths in the Normalize UI must be strict dot-segments (no spaces, etc.)
      // Skip invalid property names because they cannot be referenced safely as `input.body.<seg>`.
      if (!SEGMENT_RE.test(key)) {
        continue;
      }
      const propSchema = prop as any;
      const propType = normalizeType(propSchema.type);
      const isObjectLike = propType === "object" || !!propSchema.properties;
      const isArrayLike = propType === "array" || !!propSchema.items;

      if (isObjectLike && propSchema.properties) {
        // Nested object - recursively convert preserving nesting
        properties[key] = convertPortSchemaToSchemaNode(propSchema) || { kind: "unknown" };
      } else if (isArrayLike) {
        // Array property - preserve array structure
        const itemsSchema = propSchema.items;
        properties[key] = {
          kind: "array",
          items: itemsSchema ? (convertPortSchemaToSchemaNode(itemsSchema) || { kind: "unknown" }) : { kind: "unknown" },
        };
      } else if (propType && propType !== "object" && propType !== "array") {
        properties[key] = {
          kind: "primitive",
          type: propType as PrimitiveSchema["type"],
        };
      } else {
        properties[key] = { kind: "unknown" };
      }
    }
    return {
      kind: "object",
      properties,
    };
  }
  
  // Default to unknown
  return { kind: "unknown" };
}

/**
 * Extract fields from SchemaNode (v2 spec)
 * Respects UnknownSchema blocking - does not expand unknown types
 */
function extractFieldsFromSchemaNode(
  schemaNode: SchemaNode | undefined,
  prefix: string = "",
  sourceName: string
): AvailableDataField[] {
  if (!schemaNode) return [];

  const fields: AvailableDataField[] = [];
  
  // UnknownSchema blocks deep access - only return top-level marker
  if (schemaNode.kind === "unknown") {
    if (prefix) {
      fields.push({
        key: prefix,
        type: "unknown",
        description: "Unknown type - cannot access nested properties",
        source: sourceName,
      });
    }
    return fields;
  }
  
  // PrimitiveSchema - return as-is
  if (schemaNode.kind === "primitive") {
    fields.push({
      key: prefix || "value",
      type: schemaNode.type,
      source: sourceName,
    });
    return fields;
  }
  
  // ObjectSchema - recursively extract properties (preserves nested structure)
  if (schemaNode.kind === "object") {
    for (const [key, propSchema] of Object.entries(schemaNode.properties)) {
      const fieldKey = prefix ? `${prefix}.${key}` : key;
      // Recursively extract from nested schema (preserves nested structure exactly as-is)
      const nestedFields = extractFieldsFromSchemaNode(propSchema, fieldKey, sourceName);
      fields.push(...nestedFields);
    }
  }
  
  // ArraySchema - extract from item schema (preserves nested structure in arrays)
  if (schemaNode.kind === "array") {
    // Include the array field itself (so Normalize can map whole arrays)
    if (prefix) {
      fields.push({
        key: prefix,
        type: "array",
        source: sourceName,
      });
    }

    const arrayPrefix = prefix ? `${prefix}[]` : "[]";
    const itemFields = extractFieldsFromSchemaNode(schemaNode.items, arrayPrefix, sourceName);
    fields.push(...itemFields);
  }
  
  return fields;
}

/**
 * Extract fields from schema (supports both legacy PortSchema and new SchemaNode)
 */
function extractFieldsFromSchema(
  schema: PortSchema | SchemaNode | undefined,
  prefix: string = "",
  sourceName: string
): AvailableDataField[] {
  if (!schema) return [];
  
  // Handle { schema: {...} } wrapper
  if ((schema as any).schema && typeof (schema as any).schema === 'object') {
    return extractFieldsFromSchema((schema as any).schema, prefix, sourceName);
  }
  
  // Handle { data: {...} } wrapper
  if ((schema as any).data && typeof (schema as any).data === 'object' && !('kind' in schema)) {
    const dataWrapper = (schema as any).data;
    if (dataWrapper.kind || dataWrapper.type || dataWrapper.properties) {
      return extractFieldsFromSchema(dataWrapper, prefix ? `${prefix}.data` : 'data', sourceName);
    }
  }
  
  // Convert to SchemaNode and extract
  const schemaNode = convertPortSchemaToSchemaNode(schema);
  return extractFieldsFromSchemaNode(schemaNode, prefix, sourceName);
}

/**
 * Build webhook output schema according to v2 spec
 * If DECLARED_SCHEMA (expected_schema) exists, use it; otherwise use unknown
 * Structure: { input: { body: {...}, headers: {...}, query: {...}, method: "string" } }
 */
function buildWebhookOutputSchemaFromConfig(
  config: Record<string, any>
): SchemaNode {
  const expectedSchema = config.expected_schema ?? config.schema?.expected_schema;
  
  let bodySchema: SchemaNode = { kind: "unknown" };
  
  if (expectedSchema) {
    try {
      const parsedSchema = typeof expectedSchema === 'string' 
        ? JSON.parse(expectedSchema) 
        : expectedSchema;
      bodySchema = convertPortSchemaToSchemaNode(parsedSchema) || { kind: "unknown" };
    } catch (e) {
      console.error(`[DataFlow] Failed to parse webhook expected_schema:`, e);
      bodySchema = { kind: "unknown" };
    }
  }
  
  // Build webhook output schema according to spec
  // Nested data in payload is preserved exactly as-is under input.body
  return {
    kind: "object",
    properties: {
      input: {
        kind: "object",
        properties: {
          body: bodySchema,
          headers: {
            kind: "object",
            properties: {},
          },
          query: {
            kind: "object",
            properties: {},
          },
          method: {
            kind: "primitive",
            type: "string",
          },
        },
      },
    },
  };
}

/**
 * Build event trigger output schema according to v2 spec
 * REGLA ÚNICA: Todos los triggers exponen su payload bajo input.body (sin excepciones)
 * 
 * Webhook → input.body = request.body
 * Event → input.body = event.payload
 * Scheduled → input.body = {}
 * 
 * Structure: { input: { body: {...} } } (igual que webhooks)
 */
function buildEventOutputSchemaFromConfig(
  config: Record<string, any>
): SchemaNode {
  // IMPORTANT: config.event_schema contains ONLY payload_schema (the schema of what the event sends)
  // NOT the full event definition. payload_schema defines the structure available as input.body.*
  const payloadSchema = config.event_schema ?? config.schema?.event_schema;
  
  let bodySchema: SchemaNode = { kind: "unknown" };
  
  if (payloadSchema) {
    try {
      const parsedSchema = typeof payloadSchema === 'string' 
        ? JSON.parse(payloadSchema) 
        : payloadSchema;
      
      // payload_schema is a JSON Schema that defines the structure of input.body
      // Check if this is a JSON Schema (has type/properties) or an example payload (flat object)
      const isJsonSchema = parsedSchema.type || parsedSchema.properties;
      
      if (isJsonSchema) {
        // JSON Schema - convert to SchemaNode
        // This defines the structure of what will be available as input.body.*
        bodySchema = convertPortSchemaToSchemaNode(parsedSchema) || { kind: "unknown" };
        } else {
        // Example payload - convert nested structure to SchemaNode preserving nesting
        bodySchema = convertExamplePayloadToSchemaNode(parsedSchema);
      }
    } catch (e) {
      console.error(`[DataFlow] Failed to parse event payload_schema:`, e);
      bodySchema = { kind: "unknown" };
    }
  }
  
  // Build event output schema - nested data preserved exactly as-is under input.body
  // REGLA ÚNICA: Todos los triggers usan input.body (sin excepciones)
  // payload_schema defines what will be available as input.body.*
  return {
    kind: "object",
    properties: {
      input: {
        kind: "object",
        properties: {
          body: bodySchema, // payload_schema defines the structure here (igual que webhooks)
        },
      },
    },
  };
}

/**
 * Convert an example payload object to SchemaNode, preserving nested structure
 * Nested objects and arrays are preserved exactly as-is - no flattening
 */
function convertExamplePayloadToSchemaNode(payload: any): SchemaNode {
  if (!payload || typeof payload !== 'object') {
    return { kind: "unknown" };
  }
  
  if (Array.isArray(payload)) {
    // Array type - if first element is object, infer schema from it (preserves nested structure)
    if (payload.length > 0 && typeof payload[0] === 'object') {
      return {
        kind: "array",
        items: convertExamplePayloadToSchemaNode(payload[0]),
      };
    }
    // Array of primitives - use unknown items (can't infer primitive type from example)
    return {
      kind: "array",
      items: { kind: "unknown" },
    };
  }
  
  // Object type - recursively convert properties preserving nesting
  const properties: Record<string, SchemaNode> = {};
  
  for (const [key, value] of Object.entries(payload)) {
    if (value === null || value === undefined) {
      properties[key] = { kind: "unknown" };
    } else if (Array.isArray(value)) {
      // Array property - preserve array structure
      if (value.length > 0 && typeof value[0] === 'object') {
        properties[key] = {
          kind: "array",
          items: convertExamplePayloadToSchemaNode(value[0]),
        };
    } else {
        // Array of primitives - use unknown items (can't infer primitive type from example)
        properties[key] = {
          kind: "array",
          items: { kind: "unknown" },
        };
      }
    } else if (typeof value === 'object') {
      // Nested object - recursively convert preserving nesting
      properties[key] = convertExamplePayloadToSchemaNode(value);
    } else {
      // Primitive value
      const type = typeof value as "string" | "number" | "boolean";
      properties[key] = { kind: "primitive", type };
    }
  }
  
  return {
    kind: "object",
    properties,
  };
}

/**
 * Convert legacy ports to NodeOutput[] format (v2 spec)
 * For webhook triggers, the schema is built dynamically from config.expected_schema
 */
export function convertPortsToOutputs(
  definition: BackendNodeDefinition | undefined,
  node?: Node<CustomNodeData>
): NodeOutput[] {
  // If node instance provides dynamic portSchemas (UI-derived), prefer them.
  // This enables nodes like `tool_crm_crud` to expose operation-specific output schemas.
  if (node?.data?.portSchemas?.out) {
    const ports = Object.values(node.data.portSchemas.out) as any[];
    if (ports.length > 0) {
      return ports.map((port) => {
        const schema = port?.schema
          ? convertPortSchemaToSchemaNode(port.schema) || { kind: "unknown" as const }
          : { kind: "unknown" as const };
        return {
          name: String(port?.name || "out"),
          schema,
        };
      });
    }
  }

  if (!definition) return [];
  
  // If outputs already defined (v2 spec), use them
  if (definition.outputs && definition.outputs.length > 0) {
    return definition.outputs;
  }
  
  // Special handling for webhook triggers - build schema from config.expected_schema
  if ((definition.kind === 'trigger_webhook' || definition.kind === 'webhook') && node) {
    const config = node.data.config || {};
    const webhookSchema = buildWebhookOutputSchemaFromConfig(config);
    return [{ name: "out", schema: webhookSchema }];
  }
  
  // Special handling for event triggers - build schema from config.event_schema
  // Event → input = event.payload (payload goes directly to input, NOT input.body)
  if ((definition.kind === 'trigger_event' || definition.kind === 'event') && node) {
    const config = node.data.config || {};
    const eventSchema = buildEventOutputSchemaFromConfig(config);
    return [{ name: "out", schema: eventSchema }];
  }
  
  // Special handling for branch nodes - outputs are dynamic based on rules
  // v2 spec: branch nodes have passthrough outputs (inherit from parent)
  if (node && isBranchNodeType(node.data.type)) {
    const config = normalizeBranchConfig(node.data.config);
    const outputNames = deriveBranchOutputs(config);
    // Each output uses PASSTHROUGH schema (inherits from parent)
    return outputNames.map(name => ({
      name,
      schema: PASSTHROUGH,
    }));
  }
  
  // Convert legacy ports.out to outputs
  if (definition.ports?.out && definition.ports.out.length > 0) {
    return definition.ports.out.map(port => {
      const schema = port.schema 
        ? convertPortSchemaToSchemaNode(port.schema) || { kind: "unknown" as const }
        : { kind: "unknown" as const };
      return {
        name: port.name,
        schema,
      };
    });
  }
  
  // Default: single "out" output with unknown schema
  return [{ name: "out", schema: { kind: "unknown" } }];
}

function getNodePorts(
  node: Node<CustomNodeData>,
  nodeDefinitions: Record<string, BackendNodeDefinition>
): { in?: PortDefinition[]; out?: PortDefinition[] } {
  if (node.data.portSchemas) {
    const ports: { in?: PortDefinition[]; out?: PortDefinition[] } = {};
    if (node.data.portSchemas.in) {
      ports.in = Object.values(node.data.portSchemas.in);
    }
    if (node.data.portSchemas.out) {
      ports.out = Object.values(node.data.portSchemas.out);
    }
    return ports;
  }
  
  const definition = nodeDefinitions[node.data.type];
  return definition?.ports || {};
}

// ============================================================================
// NODE OUTPUT CALCULATION
// ============================================================================

/**
 * Calculate the output fields for a single node given its input fields.
 * Each node type can transform, filter, or add to the fields.
 */
function calculateNodeOutput(
  node: Node<CustomNodeData>,
  inputFields: AvailableDataField[],
  nodeDefinitions: Record<string, BackendNodeDefinition>
): AvailableDataField[] {
  const nodeType = node.data.type;
  const nodeLabel = node.data.label;
  const nodeDef = nodeDefinitions[nodeType];
  
  // Start with cloned input fields
  let outputFields = inputFields.map(cloneFieldDeep);
  
  // Ensure all fields have effects array
  for (const field of outputFields) {
    if (!field.effects) field.effects = [];
  }
  
  // 1. Extract declared output schemas from ports (nodeDefinitions or instance portSchemas)
  // IMPORTANT: For webhook triggers, we handle them separately in section 2 to ensure correct schema structure (input.body.*)
  // IMPORTANT: For event triggers, we handle them separately in section 3 to enforce input.body.* canonical model
  const nodePorts = getNodePorts(node, nodeDefinitions);
  const isTrigger = nodeType.startsWith('trigger_') || 
                    nodeType === 'webhook' || 
                    nodeType === 'event' ||
                    nodeType === 'scheduled';
  const isWebhook = nodeType === 'trigger_webhook' || nodeType === 'webhook';
                    
  const isEventTrigger = nodeType === "trigger_event" || nodeType === "event";

  // For all nodes (including non-triggers), include declared port schemas so downstream nodes can autocomplete
  // nodes.<id>.output.*. Skip webhook + event triggers because they are handled explicitly below.
  if (!isWebhook && !isEventTrigger && nodePorts.out) {
    for (const outPort of nodePorts.out) {
      if (outPort.schema) {
        const fields = extractFieldsFromSchema(outPort.schema, "", `${nodeLabel} (${outPort.name})`);
        outputFields.push(...fields);
      }
    }
  }
  
  // 2. Handle webhook triggers with expected_schema in config
  // IMPORTANT: Webhook schema structure is { input: { body: {...}, headers: {...}, query: {...}, method: "string" } }
  // We must use the FULL schema structure, not just the expected_schema directly
  // This ensures fields are extracted as input.body.mensaje, not mensaje
  if (isWebhook) {
    const config = node.data.config || {};
    // Use buildWebhookOutputSchemaFromConfig to get the complete schema structure
    const webhookOutputSchema = buildWebhookOutputSchemaFromConfig(config);
    // Extract fields from the complete schema (will produce input.body.*, input.headers.*, etc.)
    const webhookFields = extractFieldsFromSchemaNode(webhookOutputSchema, "", nodeLabel);
        outputFields.push(...webhookFields);
  }
  
  // 3. Handle event triggers with event_schema in config
  // REGLA ÚNICA: Todos los triggers exponen su payload bajo input.body (sin excepciones)
  // Event → input.body = event.payload (igual que webhooks: input.body = request.body)
  // Structure: { input: { body: {...} } } (igual que webhooks)
  // Nested data in payload is preserved exactly as-is under input.body.*
  if (nodeType === 'trigger_event' || nodeType === 'event') {
    const config = node.data.config || {};
    // Use buildEventOutputSchemaFromConfig to get the complete schema structure
    const eventOutputSchema = buildEventOutputSchemaFromConfig(config);
    // Extract fields from the complete schema (will produce input.body.* preserving nested structure)
    const eventFields = extractFieldsFromSchemaNode(eventOutputSchema, "", nodeLabel);
    console.log(`[DataFlow] Event trigger "${nodeLabel}": extracted ${eventFields.length} fields`, {
      eventSchema: config.event_schema,
      outputSchema: eventOutputSchema,
      extractedFields: eventFields.map(f => f.key),
    });
        outputFields.push(...eventFields);
  }
  
  // 4. Handle set_values nodes (various type names used by different backends)
  const isSetValuesNode = nodeType === 'set_values' || 
                          nodeType === 'data_set_values' || 
                          nodeType === 'set_value' || 
                          nodeType === 'assign' ||
                          nodeType === 'data.set_values' ||
                          nodeType.includes('set_values') ||
                          nodeType.includes('set_value');
                          
  if (isSetValuesNode) {
    const config = node.data.config || {};
    const configValues = config.values;
    const mergeWithInput = config.merge_with_input !== false; // default true
    
    const pairs: Array<{key: string; value: string}> = configValues 
      ? (Array.isArray(configValues) 
          ? configValues.filter((p: any) => p.key && p.key.trim() !== '')
          : (typeof configValues === 'object' ? Object.entries(configValues).map(([k, v]) => ({ key: k, value: String(v) })) : []))
      : [];
    
    const hasConfiguredValues = pairs.length > 0;
    
    // If merge_with_input is false AND there are configured values, clear upstream fields
    if (!mergeWithInput && hasConfiguredValues) {
      outputFields = [];
    }
    
    if (hasConfiguredValues) {
      for (const pair of pairs) {
        const existingIdx = outputFields.findIndex(f => f.key === pair.key);
        if (existingIdx === -1) {
          // Add new field
          const valueStr = String(pair.value).substring(0, 50) + (String(pair.value).length > 50 ? '...' : '');
          outputFields.push({
            key: pair.key,
            type: 'string',
            description: `"${pair.key}" = "${valueStr}"`,
            source: `${nodeLabel} (set)`,
            effects: [{
              type: 'computed',
              appliedBy: nodeLabel,
              nodeType: nodeType,
              description: `Value set by ${nodeLabel}`
            }]
          });
        } else {
          // Mark existing field as transformed
          addEffectIfNotExists(outputFields[existingIdx], {
            type: 'transformed',
            appliedBy: nodeLabel,
            nodeType: nodeType,
            description: `Value overwritten by ${nodeLabel}`
          });
        }
      }
    }
  }
  
  // 5. Handle branch nodes - add validated effects
  if (nodeType === 'branch' || nodeType === 'logic_branch') {
    const config = node.data.config || {};
    const rules = config.rules as Array<{ name: string; expr: string }> | undefined;
    
    if (rules) {
      for (const rule of rules) {
        if (rule.expr) {
          const validatedFields = extractValidatedFieldsFromExpr(rule.expr);
          for (const fieldKey of validatedFields) {
            const field = outputFields.find(f => f.key === fieldKey || f.key.startsWith(`${fieldKey}.`));
            if (field) {
              addEffectIfNotExists(field, {
                type: 'validated',
                appliedBy: nodeLabel,
                nodeType: nodeType,
                description: `Validated by condition: ${rule.expr}`
              });
            }
          }
        }
      }
    }
  }

  // 5.5. AI Agent node output fallback
  // If the backend node definition does not publish a detailed output schema yet,
  // we still expose a stable, JSON-safe set of fields so downstream Normalize can map them.
  // These keys will be canonicalized under nodes.<nodeId>.output.* later in this function.
  const t = (nodeType || "").toLowerCase();
  const agentTokenRe = /(^|[_\-.])agent($|[_\-.])/;
  const isAgentNodeType =
    t === "agent" ||
    t === "ai" ||
    t === "ai_agent" ||
    t === "tool_ai_agent" ||
    t === "tool_agent" ||
    t.endsWith("_agent") ||
    t.includes("ai_agent") ||
    agentTokenRe.test(t);

  if (isAgentNodeType) {
    const existing = new Set(outputFields.map((f) => f.key));
    const source = `${nodeLabel} (agent)`;
    const add = (key: string, type: string, description: string) => {
      if (existing.has(key)) return;
      existing.add(key);
      outputFields.push({ key, type, description, source });
    };

    add("success", "boolean", "Whether the agent call succeeded.");
    add("agent", "object", "Agent metadata (id/name/model, if available).");
    add("turn_id", "string", "Agent turn id / trace id (if available).");
    add("output", "unknown", "Structured output (JSON-safe), if returned by the agent.");
    add("response", "string", "Best-effort human-readable response / text.");
    add("messages", "array", "Conversation/messages exchanged during the turn (if available).");
    add("tool_calls", "array", "Tool calls invoked by the agent (if available).");
    add("error", "unknown", "Error payload (if any).");
  }
  
  // 6. Apply effects from node definition
  if (nodeDef?.data_effects) {
    const effects = nodeDef.data_effects;
    
    if (effects.validates) {
      for (const fieldKey of effects.validates) {
        const field = outputFields.find(f => f.key === fieldKey);
        if (field) {
          addEffectIfNotExists(field, {
            type: 'validated',
            appliedBy: nodeLabel,
            nodeType: nodeType
          });
        }
      }
    }
    
    if (effects.transforms) {
      for (const transform of effects.transforms) {
        const field = outputFields.find(f => f.key === transform.field);
        if (field) {
          addEffectIfNotExists(field, {
            type: 'transformed',
            appliedBy: nodeLabel,
            nodeType: nodeType,
            description: transform.description
          });
        }
      }
    }
    
    if (effects.computes) {
      for (const compute of effects.computes) {
        const existingField = outputFields.find(f => f.key === compute.field);
        if (!existingField) {
          outputFields.push({
            key: compute.field,
            type: compute.type,
            description: compute.description,
            source: `${nodeLabel} (computed)`,
            effects: [{
              type: 'computed',
              appliedBy: nodeLabel,
              nodeType: nodeType,
              description: compute.description
            }]
          });
        }
      }
    }
  }
  
  // Canonicalize: node-produced fields live under nodes.<nodeId>.output.*
  // (input.*, config.*, system.*, nodes.* are reserved/read-only namespaces)
  const reservedPrefixes = ["input.", "nodes.", "config.", "system."];
  outputFields = outputFields.map((field) => {
    const key = field.key;
    if (!key) return field;
    if (reservedPrefixes.some((p) => key.startsWith(p))) {
      return field;
    }
    return {
      ...field,
      key: `nodes.${node.id}.output.${key}`,
    };
  });

  // Deduplicate by key, preferring richer metadata
  const result = deduplicateFields(outputFields);
  
  console.log(`[DataFlow] "${nodeLabel}" output: [${result.map(f => f.key).join(', ')}]`);
  
  return result;
}

/**
 * Deduplicate fields by key, merging effects and preferring richer metadata.
 */
function deduplicateFields(fields: AvailableDataField[]): AvailableDataField[] {
  const seen = new Map<string, AvailableDataField>();
  
  for (const field of fields) {
    const key = field.key;
    if (!seen.has(key)) {
      seen.set(key, cloneFieldDeep(field));
    } else {
      const existing = seen.get(key)!;
      
      // Prefer more specific type (not 'unknown')
      const preferNewType = existing.type === 'unknown' && field.type !== 'unknown';
      // Prefer longer description
      const preferNewDesc = (!existing.description || existing.description.length < (field.description?.length || 0));
      
      // Merge effects
      const existingEffects = existing.effects || [];
      const newEffects = field.effects?.filter(e => 
        !existingEffects.some(ex => 
          `${ex.type}|${ex.appliedBy}` === `${e.type}|${e.appliedBy}`
        )
      ) || [];
      
      seen.set(key, {
        key: existing.key,
        type: preferNewType ? field.type : existing.type,
        description: preferNewDesc ? field.description : existing.description,
        source: existing.source,
        effects: newEffects.length > 0 
          ? [...existingEffects.map(cloneEffect), ...newEffects.map(cloneEffect)]
          : existingEffects.length > 0 ? existingEffects.map(cloneEffect) : undefined
      });
    }
  }
  
  return Array.from(seen.values());
}

// ============================================================================
// MAIN DATA FLOW ANALYSIS (Topological Sort)
// ============================================================================

/**
 * DataFlowResult - Result of data flow analysis
 * v2 spec: Tracks schemas per (node_id, output_name) pair
 */
export interface DataFlowResult {
  // Legacy: per-node data (for backward compatibility)
  dataMap: Map<string, AvailableDataField[]>;
  
  // v2 spec: per-output data
  outputDataMap: Map<string, Map<string, AvailableDataField[]>>; // node_id -> output_name -> fields
  
  hasCycle: boolean;
  cycleNodeIds: string[];
}

/**
 * Get schema for a specific (node_id, output_name) pair
 */
export function getOutputSchema(
  result: DataFlowResult,
  nodeId: string,
  outputName: string
): AvailableDataField[] {
  const nodeOutputs = result.outputDataMap.get(nodeId);
  if (nodeOutputs) {
    return nodeOutputs.get(outputName) || [];
  }
  // Fallback to legacy per-node data
  return result.dataMap.get(nodeId) || [];
}

/**
 * Analyze data flow through the graph using topological sort.
 * Each node is processed in order, receiving data from all predecessors.
 * Returns result object with data map and cycle detection info.
 */
export function analyzeDataFlow(
  nodes: Node<CustomNodeData>[],
  edges: Edge[],
  nodeDefinitions: Record<string, BackendNodeDefinition>,
  configSchema?: unknown,
  configValues?: Record<string, unknown>
): DataFlowResult {
  console.log('[DataFlow] analyzeDataFlow called:', {
    nodeCount: nodes.length,
    edgeCount: edges.length,
    nodes: nodes.map(n => ({ id: n.id, type: n.data.type, label: n.data.label }))
  });
  
  const dataAvailableAtNode = new Map<string, AvailableDataField[]>();
  const outputDataMap = new Map<string, Map<string, AvailableDataField[]>>(); // v2 spec: node_id -> output_name -> fields
  const nodeMap = new Map(nodes.map(n => [n.id, n]));
  
  // Build edge map: target -> [{ source, sourceHandle }]
  const incomingEdges = new Map<string, Array<{ source: string; sourceHandle: string }>>();
  for (const node of nodes) {
    incomingEdges.set(node.id, []);
  }
  for (const edge of edges) {
    if (incomingEdges.has(edge.target) && edge.sourceHandle) {
      incomingEdges.get(edge.target)!.push({ source: edge.source, sourceHandle: edge.sourceHandle });
    }
  }
  
  // Initialize ALL nodes with empty arrays first - ensures consumers always get a defined value
  for (const node of nodes) {
    dataAvailableAtNode.set(node.id, []);
    outputDataMap.set(node.id, new Map());
  }
  
  // Build predecessor map (which nodes feed into each node)
  const predecessors = new Map<string, string[]>();
  for (const node of nodes) {
    predecessors.set(node.id, []);
  }
  for (const edge of edges) {
    if (predecessors.has(edge.target)) {
      predecessors.get(edge.target)!.push(edge.source);
    }
  }
  
  // Get topological order
  const { order, hasCycle, cycleNodeIds } = topologicalSort(nodes, edges);
  const processedNodeIds = new Set<string>();
  
  console.log('[DataFlow] Topological order:', order.map(id => {
    const node = nodeMap.get(id);
    return node ? `${node.data.label} (${node.data.type})` : id;
  }));
  
  // If cycle detected, return early with cycle info (don't process cyclic graph)
  if (hasCycle) {
    console.error('Cycle detected in flow graph. Nodes in cycle:', cycleNodeIds);
    return { dataMap: dataAvailableAtNode, outputDataMap, hasCycle, cycleNodeIds };
  }
  

  /**
   * Flow config variables are globally available and read-only.
   * Canonical namespace: `config.*`
   *
   * Prefer deriving keys/types from the declared schema.
   * If schema is missing, fall back to `configValues` (explicit user-provided values).
   */
  let configSchemaNode: SchemaNode | undefined = undefined;
  try {
    const parsed = typeof configSchema === "string" ? JSON.parse(configSchema) : configSchema;
    // Reuse existing conversion (PortSchema-shaped JSON Schema or SchemaNode)
    configSchemaNode = convertPortSchemaToSchemaNode(parsed as any);
  } catch {
    configSchemaNode = undefined;
  }

  const CONFIG_SEGMENT_RE = /^[A-Za-z0-9_-]+$/;
  const deriveConfigFieldsFromValues = (
    values: Record<string, unknown> | undefined,
    prefix = "config"
  ): AvailableDataField[] => {
    if (!values || typeof values !== "object") return [];
    const out: AvailableDataField[] = [];
    const visit = (obj: any, pfx: string) => {
      if (!obj || typeof obj !== "object" || Array.isArray(obj)) return;
      for (const [kRaw, v] of Object.entries(obj)) {
        const k = String(kRaw);
        // Only include keys that can be referenced in strict dot-paths.
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
          source: "Flow config",
          description: "Flow config value",
        });

        // Expand nested objects (no arrays) for convenience: config.a.b
        if (v && typeof v === "object" && !Array.isArray(v)) {
          visit(v, key);
        }
      }
    };
    visit(values, prefix);
    return out;
  };

  const configFields: AvailableDataField[] = configSchemaNode
    ? extractFieldsFromSchemaNode(configSchemaNode, "config", "Flow config")
    : deriveConfigFieldsFromValues(configValues, "config");

  /**
   * Calculate schema for a specific output of a node
   * v2 spec: schema(node, output) = if PASSTHROUGH: schema(parent, parentOutput) else: merge(schema(parent), output.schema)
   * For triggers (webhooks, events), use calculateNodeOutput to extract fields from config
   */
  function calculateOutputSchema(
    node: Node<CustomNodeData>,
    output: NodeOutput,
    inputFields: AvailableDataField[],
    baseFields: AvailableDataField[],
    nodeDefinitions: Record<string, BackendNodeDefinition>
  ): AvailableDataField[] {
    const nodeType = node.data.type;
    const nodeLabel = node.data.label;

    const withNodeOutputPrefix = (fields: AvailableDataField[]): AvailableDataField[] => {
      const reservedPrefixes = ["input.", "nodes.", "config.", "system."];
      return fields.map((f) => {
        const key = f.key || "";
        if (!key) return f;
        if (reservedPrefixes.some((p) => key.startsWith(p))) return f;
        return { ...f, key: `nodes.${node.id}.output.${key}` };
      });
    };

    // Fallback: if backend doesn't publish a schema yet for some nodes,
    // still expose stable outputs so the UI can correctly classify "node output".
    const fallbackNodeOutputFields = (): AvailableDataField[] => {
      const t = String(nodeType || "").toLowerCase();

      // AI Agent-like nodes
      const agentTokenRe = /(^|[_\-.])agent($|[_\-.])/;
      const isAgent =
        t === "agent" ||
        t === "ai" ||
        t === "ai_agent" ||
        t === "tool_ai_agent" ||
        t === "tool_agent" ||
        t.endsWith("_agent") ||
        t.includes("ai_agent") ||
        agentTokenRe.test(t);

      if (isAgent) {
        const source = `${nodeLabel} (agent)`;
        return [
          { key: "success", type: "boolean", description: "Whether the agent call succeeded.", source },
          { key: "agent", type: "object", description: "Agent metadata (id/name/model, if available).", source },
          { key: "turn_id", type: "string", description: "Agent turn id / trace id (if available).", source },
          { key: "output", type: "unknown", description: "Structured output (JSON-safe), if returned by the agent.", source },
          { key: "response", type: "string", description: "Best-effort human-readable response / text.", source },
          { key: "messages", type: "array", description: "Conversation/messages exchanged during the turn (if available).", source },
          { key: "tool_calls", type: "array", description: "Tool calls invoked by the agent (if available).", source },
          { key: "error", type: "unknown", description: "Error payload (if any).", source },
        ];
      }

      // WhatsApp template sender nodes
      const isWhatsappTemplate =
        t === "whatsapp" ||
        t === "whatsapp_template" ||
        t.includes("whatsapp") && t.includes("template");

      if (isWhatsappTemplate) {
        const source = `${nodeLabel} (whatsapp)`;
        return [
          { key: "message_id", type: "string", description: "Provider message id (if available).", source },
          { key: "status", type: "string", description: "Delivery/send status (if available).", source },
        ];
      }

      return [];
    };

    // If PASSTHROUGH, inherit from parent (use inputFields)
    if (output.schema === PASSTHROUGH) {
      return deduplicateFields([
        ...baseFields.map(cloneFieldDeep),
        ...inputFields.map(cloneFieldDeep),
      ]);
    }
    
    // For triggers (webhooks, events), use calculateNodeOutput to extract fields from config
    // This ensures that event_schema and expected_schema are properly processed
    const isTrigger = nodeType.startsWith('trigger_') || 
                      nodeType === 'webhook' || 
                      nodeType === 'event' ||
                      nodeType === 'scheduled';
    
    if (isTrigger && inputFields.length === 0) {
      // For triggers with no input, use calculateNodeOutput to extract fields from config
      const triggerFields = calculateNodeOutput(node, [], nodeDefinitions);
      return deduplicateFields([
        ...baseFields.map(cloneFieldDeep),
        ...triggerFields.map(cloneFieldDeep),
      ]);
    }
    
    // Otherwise, merge parent schema with output schema
    const mergedFields = [
      ...baseFields.map(cloneFieldDeep),
      ...inputFields.map(cloneFieldDeep),
    ];
    
    // Extract fields from output schema
    if (typeof output.schema === 'object' && 'kind' in output.schema) {
      const schemaFields = extractFieldsFromSchemaNode(output.schema, "", node.data.label);
      const schemaWithPrefix = withNodeOutputPrefix(schemaFields);
      mergedFields.push(...schemaWithPrefix);

      // If schema is unknown/empty, try a conservative fallback for known nodes
      if (schemaFields.length === 0 || output.schema.kind === "unknown") {
        mergedFields.push(...withNodeOutputPrefix(fallbackNodeOutputFields()));
      }
    } else {
      mergedFields.push(...withNodeOutputPrefix(fallbackNodeOutputFields()));
    }
    
    return deduplicateFields(mergedFields);
  }
  
  // Process nodes in order
  for (const nodeId of order) {
    const node = nodeMap.get(nodeId);
    if (!node) continue;
    
    // Collect inputs from all predecessors (via edges with sourceHandle)
    const inputFields: AvailableDataField[] = [];
    const incoming = incomingEdges.get(nodeId) || [];
    
    for (const { source, sourceHandle } of incoming) {
      // Get schema from specific output of source node
      const sourceOutputs = outputDataMap.get(source);
      if (sourceOutputs) {
        const sourceOutputFields = sourceOutputs.get(sourceHandle) || [];
        inputFields.push(...sourceOutputFields.map(cloneFieldDeep));
      } else {
        // Fallback to legacy per-node data
        const sourceFields = dataAvailableAtNode.get(source) || [];
        inputFields.push(...sourceFields.map(cloneFieldDeep));
      }
    }
    
    // If no incoming edges, use empty input (for trigger nodes)
    const nodeDef = nodeDefinitions[node.data.type];
    const outputs = convertPortsToOutputs(nodeDef, node);
    
    // Calculate schema for each output
    const nodeOutputMap = new Map<string, AvailableDataField[]>();
    for (const output of outputs) {
      const outputSchema = calculateOutputSchema(node, output, inputFields, configFields, nodeDefinitions);
      nodeOutputMap.set(output.name, outputSchema);
    }
    
    outputDataMap.set(nodeId, nodeOutputMap);
    
    // Legacy: Calculate aggregate output (union of all outputs) for backward compatibility
    const aggregateOutput: AvailableDataField[] = [];
    for (const outputFields of Array.from(nodeOutputMap.values())) {
      aggregateOutput.push(...outputFields.map(cloneFieldDeep));
    }
    const deduplicatedOutput = deduplicateFields(aggregateOutput);
    dataAvailableAtNode.set(nodeId, deduplicatedOutput);
    
    processedNodeIds.add(nodeId);
  }
  
  // Process any nodes not in topological order (disconnected nodes)
  // Calculate their output even if empty (trigger nodes need schema extraction)
  for (const node of nodes) {
    if (!processedNodeIds.has(node.id)) {
      const nodeDef = nodeDefinitions[node.data.type];
      const outputs = convertPortsToOutputs(nodeDef, node);
      const nodeOutputMap = new Map<string, AvailableDataField[]>();
      
      for (const output of outputs) {
        const outputSchema = calculateOutputSchema(node, output, [], configFields, nodeDefinitions);
        nodeOutputMap.set(output.name, outputSchema);
      }
      
      outputDataMap.set(node.id, nodeOutputMap);
      
      // Legacy aggregate
      const aggregateOutput: AvailableDataField[] = [];
      for (const outputFields of Array.from(nodeOutputMap.values())) {
        aggregateOutput.push(...outputFields.map(cloneFieldDeep));
      }
      dataAvailableAtNode.set(node.id, deduplicateFields(aggregateOutput));
    }
  }
  
  return { dataMap: dataAvailableAtNode, outputDataMap, hasCycle: false, cycleNodeIds: [] };
}

// ============================================================================
// EDGE DATA PREVIEW
// ============================================================================

export function getEdgeDataPreview(
  edge: Edge,
  nodes: Node<CustomNodeData>[],
  nodeDefinitions: Record<string, BackendNodeDefinition>,
  dataAvailableAtNode: Map<string, AvailableDataField[]>
): AvailableDataField[] {
  const sourceNode = nodes.find((n) => n.id === edge.source);
  if (!sourceNode) return [];
  
  const sourcePorts = getNodePorts(sourceNode, nodeDefinitions);
  if (!sourcePorts.out) return [];
  
  const sourcePortId = edge.sourceHandle || "out";
  const sourcePort = sourcePorts.out.find((p) => p.name === sourcePortId);
  
  if (!sourcePort?.schema) return [];
  
  return extractFieldsFromSchema(
    sourcePort.schema,
    "",
    `${sourceNode.data.label} (${sourcePortId})`
  );
}
