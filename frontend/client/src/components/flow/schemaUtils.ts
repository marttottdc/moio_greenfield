import { SchemaField } from "@/components/flow/SchemaFieldSelector";
import { PortSchema, SchemaNode, UnknownSchema, ObjectSchema, PrimitiveSchema } from "@/components/flow/types";

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
  
  // Check for unknown type
  if (portSchema.type === "unknown" || (!portSchema.type && !portSchema.properties)) {
    return { kind: "unknown" };
  }
  
  // Primitive types
  if (portSchema.type && portSchema.type !== "object" && portSchema.type !== "array") {
    return {
      kind: "primitive",
      type: portSchema.type as PrimitiveSchema["type"],
    };
  }
  
  // Object type with properties
  if (portSchema.properties) {
    const properties: Record<string, SchemaNode> = {};
    for (const [key, prop] of Object.entries(portSchema.properties)) {
      const propSchema = prop as any;
      if (propSchema.type === "object" && propSchema.properties) {
        properties[key] = convertPortSchemaToSchemaNode(propSchema) || { kind: "unknown" };
      } else if (propSchema.type && propSchema.type !== "object" && propSchema.type !== "array") {
        properties[key] = {
          kind: "primitive",
          type: propSchema.type as PrimitiveSchema["type"],
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
  sourcePrefix: string,
  path: string = ""
): SchemaField[] {
  if (!schemaNode) return [];
  
  const fields: SchemaField[] = [];
  
  // UnknownSchema blocks deep access - only return top-level marker
  if (schemaNode.kind === "unknown") {
    if (path) {
      fields.push({
        path: `${sourcePrefix}.${path}`,
        type: "unknown",
        description: "Unknown type - cannot access nested properties",
        source: sourcePrefix,
      });
    }
    return fields;
  }
  
  // PrimitiveSchema - return as-is
  if (schemaNode.kind === "primitive") {
    fields.push({
      path: path ? `${sourcePrefix}.${path}` : sourcePrefix,
      type: schemaNode.type,
      source: sourcePrefix,
    });
    return fields;
  }
  
  // ObjectSchema - recursively extract properties
  if (schemaNode.kind === "object") {
    for (const [key, propSchema] of Object.entries(schemaNode.properties)) {
      const fieldPath = path ? `${path}.${key}` : key;
      // Recursively extract from nested schema
      const nestedFields = extractFieldsFromSchemaNode(propSchema, sourcePrefix, fieldPath);
      fields.push(...nestedFields);
    }
  }
  
  return fields;
}

/**
 * Parse a JSON schema and extract all available fields
 * Returns fields in the format: webhook.form.email, webhook.body.name, etc
 * Supports both legacy PortSchema and new SchemaNode (v2 spec)
 */
export function extractFieldsFromSchema(
  schema: PortSchema | SchemaNode | string | undefined,
  sourcePrefix: string
): SchemaField[] {
  if (!schema) return [];

  let parsed: PortSchema | SchemaNode;
  
  try {
    if (typeof schema === "string") {
      parsed = JSON.parse(schema);
    } else {
      parsed = schema;
    }
  } catch {
    return [];
  }

  // Convert to SchemaNode and extract
  const schemaNode = convertPortSchemaToSchemaNode(parsed);
  return extractFieldsFromSchemaNode(schemaNode, sourcePrefix);
}

/**
 * Parse a webhook trigger's expected_schema field
 * and return available fields for downstream nodes
 */
export function getWebhookFields(
  webhookId: string,
  webhookName: string,
  expectedSchema?: string
): SchemaField[] {
  if (!expectedSchema) return [];

  const fields = extractFieldsFromSchema(expectedSchema, `webhook_${webhookId}`);
  
  // Add a description noting the webhook source
  return fields.map(f => ({
    ...f,
    description: f.description || `From ${webhookName}`,
    source: webhookName,
  }));
}

/**
 * Build available fields based on flow node outputs
 * Accumulates data available at a specific point in the flow
 */
export function buildAvailableFieldsForNode(
  nodes: any[],
  edges: any[],
  nodeId: string,
  nodeDefinitions: Record<string, any>
): SchemaField[] {
  const fields: SchemaField[] = [];
  const visited = new Set<string>();

  // BFS to find all upstream nodes
  function collectUpstreamNodes(currentNodeId: string, upstream: Set<string>) {
    const incomingEdges = edges.filter(e => e.target === currentNodeId);
    incomingEdges.forEach(edge => {
      if (!upstream.has(edge.source)) {
        upstream.add(edge.source);
        collectUpstreamNodes(edge.source, upstream);
      }
    });
  }

  const upstreamNodeIds = new Set<string>();
  collectUpstreamNodes(nodeId, upstreamNodeIds);

  // Extract fields from each upstream node
  upstreamNodeIds.forEach(upstreamId => {
    const node = nodes.find(n => n.id === upstreamId);
    if (!node) return;

    const nodeDef = nodeDefinitions[node.data.type];
    if (!nodeDef?.ports?.out) return;

    // Get output schema from node ports
    nodeDef.ports.out.forEach((port: any) => {
      if (port.schema) {
        const nodePrefix = node.data.label || node.data.type;
        const portFields = extractFieldsFromSchema(port.schema, nodePrefix);
        fields.push(...portFields);
      }
    });
  });

  return fields;
}
