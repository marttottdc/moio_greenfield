import { Node, Edge } from "reactflow";
import { AvailableDataField } from "@/components/flow/types";
import { DataNode } from "@/components/flow/DataVisualizer";
import { WebhookRecord } from "@/hooks/useBuilderData";

export interface SchemaSource {
  webhooks?: WebhookRecord[];
}

// Data source types - backend compatible with Django context variables
export type DataSourceType = "$input" | "$trigger" | "ctx";

interface UpstreamNode {
  node: Node;
  sourcePort: string;
  depth: number; // 0 = immediate previous, 1+ = further upstream
  isTrigger: boolean;
}

/**
 * Recursively update source field for all children
 */
function updateSourceRecursive(node: DataNode, newSource: string): void {
  node.source = newSource;
  if (node.children) {
    node.children.forEach(child => updateSourceRecursive(child, newSource));
  }
}

/**
 * Calculates available data at a specific point in the flow
 * 
 * SCHEMA-DRIVEN ONLY: Uses ONLY declared schemas, never runtime context.
 * 
 * Canonical namespace model:
 * - input.body.*        ← trigger payload (schema-defined)
 * - nodes.<id>.output.* ← node outputs (schema-defined)
 * - state.*             ← persisted flow state (schema-defined, if applicable)
 * 
 * FORBIDDEN: ctx.*, runtime context, preview artifacts, executor internals
 */
export function getAvailableDataForNode(
  nodeId: string,
  nodes: Node[],
  edges: Edge[],
  nodeDefinitions: Record<string, any>,
  schemaSources?: SchemaSource
): DataNode[] {
  const visited = new Set<string>();
  const upstreamNodes: UpstreamNode[] = [];

  // Collect all upstream nodes with their depth
  function collectUpstreamNodes(currentNodeId: string, depth: number, path: Set<string> = new Set()) {
    if (path.has(currentNodeId)) return;
    path.add(currentNodeId);

    const incomingEdges = edges.filter(e => e.target === currentNodeId);
    
    incomingEdges.forEach(edge => {
      const sourceNode = nodes.find(n => n.id === edge.source);
      if (!sourceNode || visited.has(sourceNode.id)) return;
      visited.add(sourceNode.id);

      const sourcePort = edge.sourceHandle || "out";
      const nodeType = sourceNode.data.type;
      const isTrigger = isWebhookTrigger(nodeType) || isTriggerNode(nodeType);

      upstreamNodes.push({
        node: sourceNode,
        sourcePort,
        depth,
        isTrigger,
      });

      // Recurse upstream
      collectUpstreamNodes(sourceNode.id, depth + 1, new Set(path));
    });
  }

  collectUpstreamNodes(nodeId, 0);

  // Build data nodes from DECLARED SCHEMAS ONLY
  const dataNodes: DataNode[] = [];
  
  // 1. Extract input.body.* from trigger (schema-defined)
  // All triggers normalize to input.body.* structure
  const triggerNode = upstreamNodes.find(n => n.isTrigger);
  if (triggerNode) {
    const inputData = extractNodeDataWithSource(
      triggerNode.node,
      triggerNode.sourcePort,
      "input",  // Will generate input.body.* structure
      nodeDefinitions,
      schemaSources
    );
    // Update source to $input for grouping/display (recursively for all children)
    inputData.forEach(d => updateSourceRecursive(d, "$input"));
    dataNodes.push(...inputData);
  }

  // 2. Extract nodes.<id>.output.* from upstream nodes (schema-defined)
  // Each upstream node exposes its declared output schema under nodes.<node_id>.output.*
  upstreamNodes.forEach(upstream => {
    // Skip trigger - already handled above
    if (upstream.isTrigger) {
      return;
    }
    
    const nodeId = upstream.node.id;
    const nodeLabel = upstream.node.data.label || upstream.node.data.type;
    const nodeData = extractNodeDataWithSource(
      upstream.node,
      upstream.sourcePort,
      `nodes.${nodeId}.output`,  // Use nodes.<id>.output.* namespace
      nodeDefinitions,
      schemaSources
    );
    
    // Group under nodes.<id> for display
    if (nodeData.length > 0) {
      dataNodes.push({
        key: `nodes.${nodeId}`,
        type: "object",
        description: `Output from ${nodeLabel}`,
        source: `nodes.${nodeId}`,
        children: nodeData.map(d => ({
          ...d,
          // Ensure keys are prefixed with nodes.<id>.output.*
          key: d.key.startsWith(`nodes.${nodeId}.output`) ? d.key : `nodes.${nodeId}.output.${d.key}`,
        })),
      });
    }
  });

  // 3. State schema (if applicable) - would be added here
  // For now, state.* is not implemented, but structure is ready

  return dataNodes;
}

/**
 * Extract data from a node with a specific source prefix
 */
function extractNodeDataWithSource(
  sourceNode: Node,
  sourcePort: string,
  sourcePrefix: string,
  nodeDefinitions: Record<string, any>,
  schemaSources?: SchemaSource
): DataNode[] {
  const nodeType = sourceNode.data.type;
  const results: DataNode[] = [];
  
  // Handle trigger nodes - all normalize to input.body.* structure
  // SCHEMA-DRIVEN ONLY: Extract from declared schemas only
  
  // 1. Webhook triggers
  if (isWebhookTrigger(nodeType) && schemaSources?.webhooks) {
    const webhookId = sourceNode.data.config?.webhook_id;
    if (webhookId) {
      const webhook = schemaSources.webhooks.find(w => w.id === webhookId);
      if (webhook?.expected_schema) {
        // Build the complete webhook schema structure
        const expectedSchema = webhook.expected_schema;
        let bodySchema: any = { type: "object", properties: {} };
        
        try {
          const parsedSchema = typeof expectedSchema === 'string' 
            ? JSON.parse(expectedSchema) 
            : expectedSchema;
          bodySchema = parsedSchema;
        } catch (e) {
          console.error(`[DataFlowUtils] Failed to parse webhook expected_schema:`, e);
        }
        
        // Build the inner part of webhook schema: { body: {...}, headers: {...}, query: {...}, method: "string" }
        // We pass this with sourcePrefix="input" so it generates input.body.mensaje, not input.input.body.mensaje
        const webhookInnerSchema = {
          type: "object",
          properties: {
            body: bodySchema,
            headers: { type: "object", properties: {} },
            query: { type: "object", properties: {} },
            method: { type: "string" },
          },
        };
        
        // Extract fields from the inner schema structure
        // This will produce input.body.mensaje, input.body.phone, etc. (not input.input.body.mensaje)
        const webhookFields = extractSchemaFields(
          webhookInnerSchema,
          sourcePrefix,  // "input" - this becomes the prefix for all fields
          "out"
        );
        results.push(...webhookFields);
      }
    }
    // If no webhook schema, add generic placeholder
    if (results.length === 0) {
      results.push({
        key: `${sourcePrefix}.body`,
        type: "object",
        description: "Webhook body (unknown schema)",
        source: sourcePrefix,
        children: [],
      });
    }
  }
  
  // 2. Event triggers - normalize to input.body.* (same as webhooks)
  if ((nodeType === 'trigger_event' || nodeType === 'event') && sourcePrefix === "input") {
    const config = sourceNode.data.config || {};
    const payloadSchema = config.event_schema ?? config.schema?.event_schema;
    
    if (payloadSchema) {
      try {
        const parsedSchema = typeof payloadSchema === 'string' 
          ? JSON.parse(payloadSchema) 
          : payloadSchema;
        
        // Build schema structure: { body: payload_schema }
        // This normalizes events to input.body.* (same as webhooks)
        const eventInnerSchema = {
          type: "object",
          properties: {
            body: parsedSchema,
          },
        };
        
        const eventFields = extractSchemaFields(
          eventInnerSchema,
          sourcePrefix,  // "input" - generates input.body.*
          "out"
        );
        results.push(...eventFields);
      } catch (e) {
        console.error(`[DataFlowUtils] Failed to parse event payload_schema:`, e);
      }
    }
    
    // If no event schema, add generic placeholder
    if (results.length === 0) {
      results.push({
        key: `${sourcePrefix}.body`,
        type: "object",
        description: "Event payload (unknown schema)",
        source: sourcePrefix,
        children: [],
      });
    }
  }
  
  // 3. Scheduled triggers - normalize to input.body = {} (empty)
  if ((nodeType === 'trigger_scheduled' || nodeType === 'scheduled' || nodeType === 'cron') && sourcePrefix === "input") {
    // Scheduled triggers have empty input.body
    results.push({
      key: `${sourcePrefix}.body`,
      type: "object",
      description: "Scheduled trigger payload (empty)",
      source: sourcePrefix,
      children: [],
    });
  }
  
  // Extract from node definition's output schema
  // Prefer instance-provided portSchemas when available (UI-derived dynamic outputs)
  const instanceOutPorts = (sourceNode.data as any)?.portSchemas?.out;
  if (instanceOutPorts && typeof instanceOutPorts === "object") {
    Object.values(instanceOutPorts).forEach((port: any) => {
      if (port?.name === sourcePort && port?.schema) {
        const fields = extractSchemaFields(port.schema, sourcePrefix, sourcePort);
        results.push(...fields);
      }
    });
  } else {
    const nodeDef = nodeDefinitions[nodeType];
    if (nodeDef?.ports?.out) {
      nodeDef.ports.out.forEach((port: any) => {
        if (port.name === sourcePort && port.schema) {
          const fields = extractSchemaFields(port.schema, sourcePrefix, sourcePort);
          results.push(...fields);
        }
      });
    }
  }

  return results;
}

/**
 * Check if a node type is a webhook trigger
 */
function isWebhookTrigger(nodeType: string): boolean {
  return nodeType === "trigger_webhook" || 
         nodeType === "webhook_trigger" || 
         nodeType.toLowerCase().includes("webhook");
}

/**
 * Check if a node type is any kind of trigger
 */
function isTriggerNode(nodeType: string): boolean {
  return nodeType.toLowerCase().includes("trigger") ||
         nodeType.toLowerCase().includes("start") ||
         nodeType.toLowerCase().includes("schedule");
}

/**
 * Extract field definitions from a schema object
 */
function extractSchemaFields(
  schema: any,
  sourceName: string,
  portName: string = "out"
): DataNode[] {
  const fields: DataNode[] = [];

  function buildNode(propSchema: any, fieldPath: string, depth: number): DataNode {
    const fieldKey = `${sourceName}.${fieldPath}`;
    const node: DataNode = {
      key: fieldKey,
      type: propSchema.type || "unknown",
      description: propSchema.description,
      source: sourceName,
      children: [],
    };

    // Recursively build children for nested objects/arrays
    if (depth < 5 && propSchema.properties) {
      Object.entries(propSchema.properties).forEach(([nestedKey, nestedSchema]: [string, any]) => {
        const nestedPath = `${fieldPath}.${nestedKey}`;
        const nestedNode = buildNode(nestedSchema, nestedPath, depth + 1);
        node.children!.push(nestedNode);
      });
    }

    return node;
  }

  function traverse(obj: any, path: string = "", depth: number = 0) {
    if (depth > 5) return; // Prevent infinite recursion
    
    if (!obj || typeof obj !== "object") return;

    if (obj.properties) {
      Object.entries(obj.properties).forEach(([key, propSchema]: [string, any]) => {
        const fieldPath = path ? `${path}.${key}` : key;
        const node = buildNode(propSchema, fieldPath, 0);
        fields.push(node);
      });
    }
  }

  try {
    const parsed = typeof schema === "string" ? JSON.parse(schema) : schema;
    traverse(parsed);
  } catch {
    // Invalid schema, skip
  }

  return fields;
}

/**
 * Check if a node type represents a branching logic node
 */
function isBranchNode(nodeType: string): boolean {
  return nodeType.includes("branch") || 
         nodeType.includes("condition") || 
         nodeType.includes("while");
}

/**
 * Flatten a tree of DataNodes into a flat list of AvailableDataField
 * This is used to populate the data picker in node configuration forms
 */
export function flattenDataNodes(nodes: DataNode[]): AvailableDataField[] {
  const flattened: AvailableDataField[] = [];

  function traverse(node: DataNode) {
    flattened.push({
      key: node.key,
      type: node.type,
      source: node.source,
      description: node.description,
    });

    if (node.children && node.children.length > 0) {
      node.children.forEach(traverse);
    }
  }

  nodes.forEach(traverse);
  return flattened;
}

/**
 * Deep clone a DataNode tree to avoid mutation
 */
function deepCloneDataNodes(nodes: DataNode[]): DataNode[] {
  return nodes.map(node => ({
    ...node,
    children: node.children ? deepCloneDataNodes(node.children) : undefined,
  }));
}

/**
 * Merge computed fields from data flow analysis into the nested DataNode structure.
 * 
 * SCHEMA-DRIVEN ONLY: Only merges fields that come from declared node output schemas.
 * Uses nodes.<id>.output.* namespace, never ctx.*
 * 
 * @param dataNodes - The hierarchical DataNode[] from getAvailableDataForNode
 * @param computedFields - Flat AvailableDataField[] from analyzeDataFlow cache (must be schema-derived)
 * @param nodes - Array of all nodes to map source labels to nodeIds
 * @returns DataNode[] with computed fields merged in under nodes.<id>.output.*
 */
export function mergeComputedFieldsIntoDataNodes(
  dataNodes: DataNode[],
  computedFields: AvailableDataField[],
  nodes: Node[] = []
): DataNode[] {
  if (!computedFields || computedFields.length === 0) {
    return dataNodes;
  }

  // Get all existing keys in the DataNode tree (including nested children)
  // Also collect keys from $input to avoid duplicating trigger data
  const existingKeys = new Set<string>();
  const inputKeys = new Set<string>(); // Keys that are already in $input
  
  function collectKeys(nodes: DataNode[], isInputSource = false) {
    for (const node of nodes) {
      existingKeys.add(node.key);
      
      // Track keys from $input source separately to avoid duplicates
      if (isInputSource || node.source === "$input") {
        inputKeys.add(node.key);
        // Also add nested keys from input (e.g., input.body.deal_id)
        if (node.children) {
          node.children.forEach(child => {
            inputKeys.add(child.key);
            if (child.children) {
              child.children.forEach(grandchild => inputKeys.add(grandchild.key));
            }
          });
        }
      }
      
      if (node.children) {
        collectKeys(node.children, isInputSource || node.source === "$input");
      }
    }
  }
  collectKeys(dataNodes);

  // Find computed fields that don't exist in the tree
  // Also filter out fields that are already in $input (to avoid duplicates)
  const newFields = computedFields.filter(f => {
    // Skip if key already exists in tree
    if (existingKeys.has(f.key)) {
      return false;
    }
    
    // Skip if this is a trigger field that's already in $input
    // Fields from triggers should only appear under $input, not in ctx
    if (f.key.startsWith('input.') && inputKeys.has(f.key)) {
      return false;
    }
    
    // Skip if this field is from a trigger node (should be in $input, not ctx)
    const isFromTrigger = f.source && (
      f.source.includes('trigger') || 
      f.source.includes('webhook') ||
      (f.source.includes('event') && !f.source.includes('computed'))
    );
    if (isFromTrigger && inputKeys.has(f.key.replace(/^ctx\.\w+\./, ''))) {
      return false;
    }
    
    return true;
  });
  
  if (newFields.length === 0) {
    return dataNodes;
  }

  // Deep clone the dataNodes to avoid mutation
  const result = deepCloneDataNodes(dataNodes);

  // Group new fields by namespace.
  // Canonical namespaces:
  // - input.body.*
  // - nodes.<nodeId>.output.*
  // - config.*
  // - system.*
  const fieldsByGroupKey: Record<string, { qualifiedKey: string; field: AvailableDataField }[]> = {};
  
  // Build a map from node label to nodeId for efficient lookup
  const labelToNodeId = new Map<string, string>();
  nodes.forEach(node => {
    const label = node.data.label || node.data.type;
    labelToNodeId.set(label, node.id);
  });
  
  for (const field of newFields) {
    let groupKey: string;
    let qualifiedKey: string;

    if (field.key.startsWith("nodes.")) {
      const parts = field.key.split(".");
      const nodeId = parts[1] || "unknown";
      groupKey = `nodes.${nodeId}`;
      qualifiedKey = field.key;
    } else if (field.key.startsWith("config.")) {
      groupKey = "config";
      qualifiedKey = field.key;
    } else if (field.key.startsWith("system.")) {
      groupKey = "system";
      qualifiedKey = field.key;
    } else if (field.key.startsWith("input.")) {
      groupKey = "input";
      qualifiedKey = field.key;
    } else {
      // Legacy/unqualified computed field fallback: attach under nodes.<nodeId>.output.*
      const sourceLabel = (field.source || '').replace(/\s*\(.*\)\s*$/, '').trim();
      const nodeId = labelToNodeId.get(sourceLabel) ||
        nodes.find(n => (n.data.label || n.data.type) === sourceLabel)?.id ||
        `unknown_${sourceLabel.replace(/\s+/g, '_').toLowerCase()}`;
      groupKey = `nodes.${nodeId}`;
      qualifiedKey = `nodes.${nodeId}.output.${field.key}`;
    }

    if (!fieldsByGroupKey[groupKey]) {
      fieldsByGroupKey[groupKey] = [];
    }
    fieldsByGroupKey[groupKey].push({ qualifiedKey, field });
  }

  // Add computed fields under their namespace group structure
  for (const [groupKey, fieldEntries] of Object.entries(fieldsByGroupKey)) {
    let nodeGroup = result.find(n => n.key === groupKey);
    
    if (!nodeGroup) {
      if (groupKey.startsWith("nodes.")) {
        const nodeLabel = fieldEntries[0]?.field.source?.replace(/\s*\(.*\)\s*$/, '').trim() || groupKey;
        nodeGroup = {
          key: groupKey,
          type: 'object',
          description: `Output from ${nodeLabel}`,
          source: groupKey,
          children: [],
        };
      } else if (groupKey === "config") {
        nodeGroup = {
          key: "config",
          type: "object",
          description: "Flow config variables",
          source: "config",
          children: [],
        };
      } else if (groupKey === "system") {
        nodeGroup = {
          key: "system",
          type: "object",
          description: "System execution facts",
          source: "system",
          children: [],
        };
      } else if (groupKey === "input") {
        nodeGroup = {
          key: "input",
          type: "object",
          description: "Trigger input data",
          source: "$input",
          children: [],
        };
      } else {
        nodeGroup = {
          key: groupKey,
          type: "object",
          description: groupKey,
          source: groupKey,
          children: [],
        };
      }
      result.push(nodeGroup);
    }
    
    if (!nodeGroup.children) {
      nodeGroup.children = [];
    }
    
    // Add each field under its fully-qualified key
    for (const { qualifiedKey, field } of fieldEntries) {
      // Check if field already exists to avoid duplicates
      const existingField = nodeGroup.children.find(c => c.key === qualifiedKey);
      
      if (!existingField) {
        nodeGroup.children.push({
          key: qualifiedKey,
          type: field.type,
          description: field.description || `Output field: ${field.key}`,
          source: groupKey,
        });
      }
    }
  }

  return result;
}

/**
 * Get data available on a specific edge
 * This shows the data that flows through that connection
 */
export function getDataOnEdge(
  edgeId: string,
  edges: Edge[],
  nodes: Node[],
  nodeDefinitions: Record<string, any>
): DataNode[] {
  const edge = edges.find(e => e.id === edgeId);
  if (!edge) return [];

  const sourceNode = nodes.find(n => n.id === edge.source);
  if (!sourceNode) return [];

  const sourcePort = edge.sourceHandle || "out";
  const nodeDef = nodeDefinitions[sourceNode.data.type];

  if (!nodeDef?.ports?.out) return [];

  const fields: DataNode[] = [];
  nodeDef.ports.out.forEach((port: any) => {
    if (port.name === sourcePort && port.schema) {
      fields.push(
        ...extractSchemaFields(
          port.schema,
          sourceNode.data.label || sourceNode.data.type,
          sourcePort
        )
      );
    }
  });

  return fields;
}
