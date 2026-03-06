// flows/static/js/builder_manager.js
// Provides a factory for FlowBuilder manager instances without running any
// side effects on load. Consumers must explicitly create an instance via the
// FlowBuilder global.

(function (global) {
  const createEmptyGraph = () => ({ nodes: [], edges: [] });

  const sanitizeGraph = (value) => {
    if (!value || typeof value !== 'object') {
      return createEmptyGraph();
    }
    const clone = {
      nodes: Array.isArray(value.nodes) ? value.nodes : [],
      edges: Array.isArray(value.edges) ? value.edges : [],
    };
    return clone;
  };

  const cloneGraphValue = (value) => {
    try {
      return sanitizeGraph(JSON.parse(JSON.stringify(value || {})));
    } catch (error) {
      console.warn('[FlowBuilder][manager]', 'cloneGraph failed, returning empty graph', error);
      return createEmptyGraph();
    }
  };

  const createManager = () => {
    let graph = createEmptyGraph();
    let rawDefinitions = {};
    let nodeDefinitions = {};
    let activeStage = null;
    let debug = false;

    const log = (...args) => {
      if (debug) {
        console.log('[FlowBuilder][manager]', ...args);
      }
    };

    const warn = (...args) => {
      if (debug) {
        console.warn('[FlowBuilder][manager]', ...args);
      }
    };

    const normalizeStage = (value) => {
      if (typeof value !== 'string') return null;
      const normalised = value.trim().toLowerCase();
      return normalised || null;
    };

    const deepClone = (value) => (value == null ? value : JSON.parse(JSON.stringify(value)));

    const ensureArray = (val) => (Array.isArray(val) ? val : []);

    const schemaPreview = (schema, preview) => {
      if (preview) return preview;
      return schema ? JSON.stringify(schema, null, 2) : '';
    };

    const normaliseStageFlags = (value) => {
      if (!value || typeof value !== 'object') {
        return {};
      }
      return Object.entries(value).reduce((acc, entry) => {
        const [stageName, allowed] = entry;
        if (stageName == null) return acc;
        const key = String(stageName).trim().toLowerCase();
        if (!key) return acc;
        acc[key] = Boolean(allowed);
        return acc;
      }, {});
    };

    const computeStageAvailability = (definition, stage) => {
      const flags = normaliseStageFlags(definition?.stages || definition?.availability);
      const entries = Object.entries(flags);
      if (!entries.length) {
        return { flags, is_available: true };
      }
      if (!stage) {
        return { flags, is_available: entries.some(([, allowed]) => allowed) };
      }
      return { flags, is_available: Boolean(flags[stage]) };
    };

    const rebuildDefinitions = () => {
      nodeDefinitions = {};
      const entries = Object.entries(rawDefinitions || {});
      entries.forEach(([kind, definition]) => {
        const clone = deepClone(definition) || {};
        const { flags, is_available } = computeStageAvailability(clone, activeStage);
        clone.stages = flags;
        clone.availability = flags;
        const flagValues = Object.values(flags);
        const computedStageLimited = Boolean(flagValues.length) && !flagValues.every((value) => Boolean(value));
        const stageLimited = Boolean(clone.stage_limited) || computedStageLimited;
        clone.stage_limited = stageLimited;
        clone.__stage = {
          active: activeStage,
          flags,
          is_available,
          stage_limited: clone.stage_limited,
        };
        nodeDefinitions[kind] = clone;
      });
      global.__nodeDefinitions = deepClone(nodeDefinitions);
    };

    const setGraph = (value) => {
      graph = sanitizeGraph(value);
      global.__graph__ = graph;
      return graph;
    };

    const setDefinitions = (definitions) => {
      rawDefinitions = definitions && typeof definitions === 'object' ? deepClone(definitions) : {};
      rebuildDefinitions();
    };

    const getDefinition = (kind) => nodeDefinitions[kind] || null;

    const setStage = (value) => {
      activeStage = normalizeStage(value);
      rebuildDefinitions();
    };

    const GENERIC_INPUT_SCHEMA = { type: 'object', description: 'Incoming JSON payload' };
    const GENERIC_OUTPUT_SCHEMA = { type: 'object', description: 'Payload emitted by the node' };
    const TRIGGER_OUTPUT_SCHEMA = {
      type: 'object',
      description: 'Trigger payload',
      properties: {
        trigger: { type: 'string' },
        data: { type: 'object' },
      },
    };

    const clonePortEntry = (entry) => {
      if (!entry) return null;
      const schema = entry.schema ? deepClone(entry.schema) : null;
      return {
        name: entry.name || '',
        description: entry.description || '',
        schema,
        schema_preview: schemaPreview(schema, entry.schema_preview),
      };
    };

    const clonePortMap = (ports) => {
      const result = {
        in: ensureArray(ports?.in).map(clonePortEntry).filter(Boolean),
        out: ensureArray(ports?.out).map(clonePortEntry).filter(Boolean),
      };
      if (ports?.meta) {
        result.meta = deepClone(ports.meta);
      }
      return result;
    };

    const fallbackPortsFor = (node) => {
      if (node.kind?.startsWith('trigger_')) {
        const schema = deepClone(TRIGGER_OUTPUT_SCHEMA);
        return {
          in: [],
          out: [{
            name: 'out',
            description: 'Trigger payload',
            schema,
            schema_preview: schemaPreview(schema),
          }],
        };
      }

      if (node.kind?.startsWith('output_')) {
        const schema = deepClone(GENERIC_INPUT_SCHEMA);
        return {
          in: [{
            name: 'in',
            description: 'Payload received',
            schema,
            schema_preview: schemaPreview(schema),
          }],
          out: [],
        };
      }

      const inputSchema = deepClone(GENERIC_INPUT_SCHEMA);
      const outputSchema = deepClone(GENERIC_OUTPUT_SCHEMA);
      return {
        in: [{
          name: 'in',
          description: 'Input payload',
          schema: inputSchema,
          schema_preview: schemaPreview(inputSchema),
        }],
        out: [{
          name: 'out',
          description: 'Output payload',
          schema: outputSchema,
          schema_preview: schemaPreview(outputSchema),
        }],
      };
    };

    const buildDefinitionPorts = (node) => {
      const definition = getDefinition(node.kind);
      if (!definition) {
        return fallbackPortsFor(node);
      }

      const base = clonePortMap(definition.ports);

      if (node.kind === 'logic_branch') {
        const template = base.out[0] || { description: '', schema: null, schema_preview: '' };
        const config = node.config || {};
        const rules = Array.isArray(config.rules) && config.rules.length ? config.rules : [{ name: 'true' }, { name: 'false' }];
        const outputs = rules.map((rule, index) => ({
          name: rule?.name || `rule_${index + 1}`,
          description: template.description || 'Branch path payload',
          schema: template.schema ? deepClone(template.schema) : null,
          schema_preview: schemaPreview(template.schema, template.schema_preview),
        }));
        if (config.else) {
          outputs.push({
            name: 'else',
            description: template.description || 'Branch fallback payload',
            schema: template.schema ? deepClone(template.schema) : null,
            schema_preview: schemaPreview(template.schema, template.schema_preview),
          });
        }
        const inputTemplate = base.in[0] || {
          name: 'in',
          description: 'Payload evaluated by the branch',
          schema: deepClone(GENERIC_INPUT_SCHEMA),
          schema_preview: schemaPreview(GENERIC_INPUT_SCHEMA),
        };
        return {
          in: [clonePortEntry(inputTemplate)],
          out: outputs,
        };
      }

      if (node.kind === 'logic_while') {
        return base.in.length || base.out.length ? base : fallbackPortsFor(node);
      }

      return base.in.length || base.out.length ? base : fallbackPortsFor(node);
    };

    const enrichPortsWithDefinition = (node, current) => {
      const definitionPorts = buildDefinitionPorts(node);
      const mergeSide = (side) => {
        const existing = ensureArray(current[side]);
        if (!existing.length) return ensureArray(definitionPorts[side]);
        const templates = ensureArray(definitionPorts[side]);
        const fallback = templates[0] || null;
        return existing.map((entry) => {
          const clone = clonePortEntry(entry);
          const match = templates.find((item) => item.name === clone.name) || fallback;
          if (match) {
            if (!clone.description && match.description) clone.description = match.description;
            if (!clone.schema && match.schema) clone.schema = deepClone(match.schema);
            if (!clone.schema_preview) clone.schema_preview = schemaPreview(clone.schema, match.schema_preview);
          } else if (!clone.schema_preview) {
            clone.schema_preview = schemaPreview(clone.schema);
          }
          return clone;
        });
      };
      return {
        in: mergeSide('in'),
        out: mergeSide('out'),
      };
    };

    const computePorts = (node) => {
      const current = clonePortMap(node.ports);
      const hasExisting = current.in.length || current.out.length;
      const result = hasExisting ? enrichPortsWithDefinition(node, current) : buildDefinitionPorts(node);
      node.ports = result;
      return result;
    };

    const findNode = (id) => graph.nodes.find((n) => n.id === id) || null;
    const findEdge = (id) => graph.edges.find((e) => e.id === id) || null;

    const addNode = (node) => {
      if (!node || !node.id) {
        throw new Error('Cannot add node without id');
      }
      graph.nodes.push(node);
    };

    const removeNode = (id) => {
      graph.nodes = graph.nodes.filter((node) => node.id !== id);
      graph.edges = graph.edges.filter((edge) => edge.source !== id && edge.target !== id);
    };

    const updateNode = (id, updater) => {
      const node = findNode(id);
      if (!node) return null;
      const result = typeof updater === 'function' ? updater(node) : Object.assign(node, updater);
      return result;
    };

    const addEdge = (edge) => {
      if (!edge || !edge.id) {
        throw new Error('Cannot add edge without id');
      }
      graph.edges.push(edge);
    };

    const removeEdge = (id) => {
      graph.edges = graph.edges.filter((edge) => edge.id !== id);
    };

    const setDebug = (value) => {
      debug = Boolean(value);
    };

    const manager = {};

    manager.init = ({ initialGraph, initialDefinitions, debug: debugFlag, stage }) => {
      setDebug(debugFlag);
      setStage(stage);
      setDefinitions(initialDefinitions || {});
      setGraph(initialGraph || createEmptyGraph());
      log('Manager initialised', {
        nodeCount: graph.nodes.length,
        edgeCount: graph.edges.length,
        definitionCount: Object.keys(nodeDefinitions).length,
        availableDefinitions: Object.values(nodeDefinitions).filter((definition) => definition?.__stage?.is_available !== false).length,
        stage: activeStage,
      });
      return graph;
    };

    manager.destroy = () => {
      graph = createEmptyGraph();
      rawDefinitions = {};
      nodeDefinitions = {};
      activeStage = null;
      debug = false;
      delete global.__graph__;
      delete global.__nodeDefinitions;
    };

    manager.getGraph = () => graph;
    manager.cloneGraph = () => cloneGraphValue(graph);
    manager.setGraph = setGraph;
    manager.getNodes = () => graph.nodes;
    manager.getEdges = () => graph.edges;
    manager.findNode = findNode;
    manager.findEdge = findEdge;
    manager.addNode = addNode;
    manager.removeNode = removeNode;
    manager.updateNode = updateNode;
    manager.addEdge = addEdge;
    manager.removeEdge = removeEdge;
    manager.computePorts = computePorts;
    manager.getDefinition = getDefinition;
    manager.getStage = () => activeStage;
    manager.setStage = (value) => {
      setStage(value);
      return activeStage;
    };
    manager.listDefinitions = ({ includeUnavailable = false } = {}) => {
      const result = {};
      Object.entries(nodeDefinitions).forEach(([kind, definition]) => {
        if (includeUnavailable || definition?.__stage?.is_available !== false) {
          result[kind] = deepClone(definition);
        }
      });
      return result;
    };
    manager.isDefinitionAvailable = (kind) => {
      const definition = nodeDefinitions[kind];
      if (!definition) return false;
      return definition.__stage?.is_available !== false;
    };
    manager.clonePortEntry = clonePortEntry;
    manager.clonePortMap = clonePortMap;
    manager.ensureArray = ensureArray;
    manager.deepClone = deepClone;
    manager.schemaPreview = schemaPreview;
    manager.fallbackPortsFor = fallbackPortsFor;

    return manager;
  };

  global.FlowBuilderManagerFactory = {
    create: () => createManager(),
  };
})(window);
